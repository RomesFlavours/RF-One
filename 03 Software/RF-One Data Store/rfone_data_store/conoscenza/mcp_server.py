"""Minimal MCP server (stdio, JSON-RPC 2.0, newline-delimited) for Conoscenza.

Dependency-free on purpose: the RF-One Python environment has no MCP SDK,
and the protocol subset needed (initialize, tools/list, tools/call, ping)
is small. Started by the client (Claude Code via `.mcp.json`, Codex via its
`mcp_servers` configuration) as:

    python conoscenza.py mcp --client claude

The client name selects the token file; the register attributes every
write to the token's client.
"""

from __future__ import annotations

import json
import sys
import uuid

from .api import backend, dispatch

PROTOCOL_VERSION = "2025-06-18"

_COMMON_RECORD = {
    "domain": {"type": "string", "description": "Dominio/modulo RF-One, es. 'Restaurant/Tips', 'System/Conoscenza'."},
    "title": {"type": "string", "description": "Titolo breve e riconoscibile."},
    "statement": {"type": "string", "description": "La regola, decisione o il risultato, in italiano."},
    "rationale": {"type": "string", "description": "Il PERCHÉ dato da Pino (o dall'evidenza). Vuoto = motivazione sconosciuta."},
    "validity_conditions": {"type": "string", "description": "Quando vale la regola."},
    "exceptions": {"type": "string", "description": "Limiti ed eccezioni: quando NON vale."},
    "keywords": {"type": "string", "description": "Parole alternative/sinonimi (italiano e inglese) con cui Pino potrebbe riferirsi al tema."},
    "authority": {"type": "string", "enum": ["PO_EXPLICIT", "PROPOSAL", "AI_HYPOTHESIS"],
                  "description": ("PO_EXPLICIT solo se Pino l'ha detto o confermato esplicitamente; PROPOSAL per la "
                                  "proposta di un'altra persona; AI_HYPOTHESIS per una lettura dell'AI.")},
    "decided_by": {"type": "string", "description": "Chi ha deciso (es. 'Pino'); obbligatorio per PO_EXPLICIT."},
    "decided_on": {"type": "string", "description": "Data della decisione AAAA-MM-GG."},
    "source_type": {"type": "string", "enum": ["CHAT_SESSION", "DECISION_LOG", "REPORT", "REPOSITORY_DOC", "IMPORTED_EXTRACT"]},
    "source_ref": {"type": "string", "description": "Riferimento al passaggio originale (sessione, file#sezione, commit)."},
    "source_excerpt": {"type": "string", "description": "Parole testuali di Pino, se disponibili."},
    "session_ref": {"type": "string", "description": "Identificativo della sessione corrente."},
    "request_key": {"type": "string", "description": "Chiave per ripetere in sicurezza la stessa scrittura senza duplicati."},
}

TOOLS = [
    {"name": "conoscenza_contesto",
     "description": ("Da chiamare all'INIZIO di ogni sessione RF-One: stato del registro Conoscenza, decisioni e "
                     "correzioni vigenti più recenti, stato dei lavori, scritture fallite in coda."),
     "inputSchema": {"type": "object", "properties": {
         "domain": {"type": "string", "description": "Filtro facoltativo sul dominio."},
         "session_ref": {"type": "string"}}}},
    {"name": "conoscenza_cerca",
     "description": ("Cerca nel registro Conoscenza decisioni, correzioni motivate e stato dei lavori pertinenti a "
                     "un problema, anche con parole diverse da quelle registrate. Da chiamare PRIMA di proporre una "
                     "soluzione o di riprendere un incarico. Ripetere con riformulazioni se i risultati sono scarsi."),
     "inputSchema": {"type": "object", "required": ["query"], "properties": {
         "query": {"type": "string", "description": "Il problema o l'incarico, con parole libere."},
         "domain": {"type": "string"}, "kind": {"type": "string", "enum": ["DECISION", "CORRECTION", "WORK_UPDATE"]},
         "include_history": {"type": "boolean", "description": "Includere anche le versioni sostituite."},
         "limit": {"type": "integer"}, "session_ref": {"type": "string"}}}},
    {"name": "conoscenza_leggi",
     "description": "Legge una voce completa: motivazione, validità, eccezioni, versioni, collegamenti, evidenze.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "integer"}, "session_ref": {"type": "string"}}}},
    {"name": "conoscenza_registra",
     "description": ("Registra SUBITO, mentre la sessione è attiva, una decisione o una correzione motivata appena "
                     "diventa esplicita (non aspettare la fine della chat). Restituisce la voce riletta dal registro "
                     "come conferma; in caso di errore la scrittura NON è avvenuta e va segnalata a Pino."),
     "inputSchema": {"type": "object", "required": ["kind", "domain", "title", "statement", "source_ref"],
                     "properties": {"kind": {"type": "string", "enum": ["DECISION", "CORRECTION"]}, **_COMMON_RECORD}}},
    {"name": "conoscenza_lavoro",
     "description": ("Registra un esito tecnico del lavoro quando avviene, con evidenza: DESIGNED (progettato), "
                     "IMPLEMENTED (implementato: file/commit), VERIFIED (verificato: test), RELEASED (rilasciato)."),
     "inputSchema": {"type": "object", "required": ["work_ref", "work_stage", "domain", "title", "statement",
                                                    "source_ref", "evidence"],
                     "properties": {
                         "work_ref": {"type": "string", "description": "Lavoro/incarico, es. 'CONOSCENZA_01'."},
                         "work_stage": {"type": "string", "enum": ["DESIGNED", "IMPLEMENTED", "VERIFIED", "RELEASED"]},
                         "evidence": {"type": "array", "items": {"type": "object", "required": ["kind", "reference"],
                                      "properties": {"kind": {"type": "string", "enum": ["COMMIT", "TEST", "RELEASE",
                                                                                          "DOCUMENT", "FILE", "OTHER"]},
                                                     "reference": {"type": "string"},
                                                     "description": {"type": "string"}}}},
                         **_COMMON_RECORD}}},
    {"name": "conoscenza_cambia",
     "description": ("Pino ha cambiato una decisione: crea la nuova versione vigente collegata alla precedente, che "
                     "diventa 'sostituita'. Indicare solo i campi che cambiano."),
     "inputSchema": {"type": "object", "required": ["old_id", "source_ref"],
                     "properties": {"old_id": {"type": "integer"}, **_COMMON_RECORD}}},
    {"name": "conoscenza_approva",
     "description": ("Pino approva una PROPOSTA di un'altra persona: nasce la versione 'decisione esplicita di Pino', "
                     "la proposta originale resta conservata e attribuita a chi l'ha fatta."),
     "inputSchema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "integer"}, "note": {"type": "string"}, "session_ref": {"type": "string"}}}},
    {"name": "conoscenza_storico",
     "description": "Storico delle consultazioni e scritture (chi, con quale strumento, quando). Solo per Pino.",
     "inputSchema": {"type": "object", "properties": {
         "client": {"type": "string", "enum": ["CLAUDE", "CODEX", "CHATGPT", "IMPORTER"]},
         "filter_session": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "conoscenza_collega",
     "description": "Collega due voci: AMENDS (la prima modifica in parte la seconda senza sostituirla) o RELATES.",
     "inputSchema": {"type": "object", "required": ["from_id", "to_id", "relation"], "properties": {
         "from_id": {"type": "integer"}, "to_id": {"type": "integer"},
         "relation": {"type": "string", "enum": ["AMENDS", "RELATES"]}, "note": {"type": "string"},
         "session_ref": {"type": "string"}}}},
]


def serve(client: str) -> None:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        api = backend(client)
    except Exception as exc:  # missing token: answer every call with the error
        api, startup_error = None, f"{type(exc).__name__}: {exc}"
    default_session = f"{client.lower()}-mcp-{uuid.uuid4().hex[:12]}"
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:  # notification
            continue
        if method == "initialize":
            requested = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
            result = {"protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "rf-one-conoscenza", "version": "0.1.0"},
                      "instructions": ("Registro Conoscenza di RF-One. All'inizio chiamare conoscenza_contesto; "
                                       "prima di ogni proposta conoscenza_cerca; registrare subito decisioni e "
                                       "correzioni esplicite di Pino con conoscenza_registra.")}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params") or {}
            try:
                if api is None:
                    payload = {"ok": False, "errore": f"Conoscenza non utilizzabile: {startup_error}"}
                else:
                    args = dict(params.get("arguments") or {})
                    args.setdefault("session_ref", default_session)
                    payload = api.call_tool(params.get("name"), args)
            except Exception as exc:  # never crash the client's session
                payload = {"ok": False, "errore": f"{type(exc).__name__}: {exc}"}
            result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=1)}],
                      "isError": not payload.get("ok", False)}
        else:
            out.write(json.dumps({"jsonrpc": "2.0", "id": mid,
                                  "error": {"code": -32601, "message": f"Method not found: {method}"}}) + "\n")
            out.flush()
            continue
        out.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}, ensure_ascii=False) + "\n")
        out.flush()
