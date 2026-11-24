#!/usr/bin/env python
"""Conoscenza command line (`10 System/Conoscenza/README.md`).

Register commands — they use the AWS service when this PC is pointed at it
(`Secrets/conoscenza/remote.json` or RFONE_CONOSCENZA_URL), otherwise the
local register:

    contesto [--domain D] [--hook]   start-of-session brief
    cerca "problema" [--storia]      search with free words
    leggi ID
    registra --json '{...}'          decision / correction / proposal / work update
    cambia ID --json '{...}'         new version of a changed decision
    approva ID [--nota N]            Pino approves a proposal (the proposal is kept)
    collega DA A AMENDS|RELATES
    accessi [--session S] [--client-filtro C]
    riprova                          send writes queued while the register was unreachable (once each)
    mcp                              MCP stdio server (Claude Code / Codex); proxies to AWS when configured

Local administration:

    init                             create the local register and missing tokens (Secrets/conoscenza/)
    importa                          import the heritage into the local register
    importa-estratto FILE.jsonl      import an extract from another AI, with sources
    migra-esporta FILE.json          export the first-release local register (read-only) for AWS
    manifest FILE.json               row counts + SHA-256 per table of an export

Every register command needs `--client` (claude, codex, chatgpt, importer):
its token in `Secrets/conoscenza/` identifies the person and the tool.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _print(obj) -> int:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1, default=str) + "\n")
    return 0 if obj.get("ok", True) else 1


def _hook_brief(api) -> int:
    """Plain-text context for a Claude Code SessionStart hook. Never fails the
    session: an unreachable register is reported in the text itself."""
    session_ref = None
    if not sys.stdin.isatty():
        try:  # Claude Code passes the hook input (with session_id) as JSON on stdin
            session_ref = json.loads(sys.stdin.read() or "{}").get("session_id")
        except (ValueError, OSError):
            session_ref = None
    out = api.call_tool("conoscenza_contesto", {"session_ref": f"claude-{session_ref}" if session_ref else None})
    lines = ["## Conoscenza RF-One (registro persistente condiviso)"]
    if not out.get("ok"):
        lines += [f"ATTENZIONE: {out.get('errore')}",
                  "Il registro Conoscenza NON è disponibile: dillo a Pino prima di proporre soluzioni."]
    else:
        lines += [f"Registro raggiungibile ({out.get('servizio', 'locale')}): {out['voci_vigenti']} voci vigenti.",
                  "Prima di proporre o riprendere un incarico usa conoscenza_cerca (anche più volte, con parole "
                  "diverse) e applica le voci vigenti; registra subito con conoscenza_registra ogni decisione o "
                  "correzione esplicita di Pino, con il suo perché, e con conoscenza_lavoro gli esiti con evidenza.",
                  "Voci vigenti più recenti (id · data · dominio · titolo):"]
        lines += [f"- {row}" for row in out["decisioni_e_correzioni_recenti"][:25]]
        if out["stato_lavori"]:
            lines.append("Stato lavori recente:")
            lines += [f"- {row}" for row in out["stato_lavori"][:10]]
    if out.get("scritture_in_coda"):
        lines.append(f"SCRITTURE NON AVVENUTE IN CODA: {len(out['scritture_in_coda'])}.")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Conoscenza RF-One")
    p.add_argument("--client", default=os.environ.get("RFONE_CONOSCENZA_CLIENT"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("importa")
    s = sub.add_parser("importa-estratto"); s.add_argument("file")
    s = sub.add_parser("migra-esporta"); s.add_argument("file"); s.add_argument("--db")
    s = sub.add_parser("manifest"); s.add_argument("file")
    s = sub.add_parser("contesto"); s.add_argument("--domain"); s.add_argument("--session"); s.add_argument("--hook", action="store_true")
    s = sub.add_parser("cerca"); s.add_argument("query"); s.add_argument("--domain"); s.add_argument("--kind")
    s.add_argument("--storia", action="store_true"); s.add_argument("--limit", type=int, default=8); s.add_argument("--session")
    s = sub.add_parser("leggi"); s.add_argument("id", type=int); s.add_argument("--session")
    s = sub.add_parser("registra"); s.add_argument("--json", required=True)
    s = sub.add_parser("cambia"); s.add_argument("id", type=int); s.add_argument("--json", required=True)
    s = sub.add_parser("approva"); s.add_argument("id", type=int); s.add_argument("--nota"); s.add_argument("--session")
    s = sub.add_parser("collega"); s.add_argument("da", type=int); s.add_argument("a", type=int)
    s.add_argument("relazione"); s.add_argument("--nota"); s.add_argument("--session")
    s = sub.add_parser("accessi"); s.add_argument("--session"); s.add_argument("--client-filtro"); s.add_argument("--limit", type=int, default=50)
    sub.add_parser("riprova")
    sub.add_parser("mcp")
    a = p.parse_args()

    from rfone_data_store.conoscenza import migration
    from rfone_data_store.conoscenza.store import (DEFAULT_DB, database_url, ensure_schema, issue_missing_tokens,
                                                    make_engine, session_factory)
    if a.cmd == "init":
        engine = make_engine()
        ensure_schema(engine)
        with session_factory(engine)() as db:
            issued = issue_missing_tokens(db)
        return _print({"ok": True, "registro": database_url().split("///")[-1], "token_creati": issued})
    if a.cmd == "migra-esporta":
        data = migration.export_v1_sqlite(Path(a.db) if a.db else DEFAULT_DB)
        Path(a.file).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return _print({"ok": True, "file": a.file, "manifest": migration.manifest(data)})
    if a.cmd == "manifest":
        return _print({"ok": True, "manifest": migration.manifest(json.loads(Path(a.file).read_text(encoding="utf-8")))})

    if not a.client:
        return _print({"ok": False, "errore": "Indicare --client (claude, codex, chatgpt, importer)."})
    if a.cmd == "mcp":
        from rfone_data_store.conoscenza.mcp_server import serve
        serve(a.client)
        return 0

    from rfone_data_store.conoscenza.api import Conoscenza, backend
    from rfone_data_store.conoscenza.store import AuthenticationError
    try:
        api = Conoscenza(client=a.client) if a.cmd in ("importa", "importa-estratto") else backend(a.client)
    except AuthenticationError as exc:
        if a.cmd == "contesto" and a.hook:
            sys.stdout.write(f"## Conoscenza RF-One\nATTENZIONE: registro non utilizzabile: {exc}\n")
            return 0
        return _print({"ok": False, "errore": str(exc)})

    call = api.call_tool
    if a.cmd == "contesto":
        return _hook_brief(api) if a.hook else _print(call("conoscenza_contesto", {"domain": a.domain,
                                                                                  "session_ref": a.session}))
    if a.cmd == "cerca":
        return _print(call("conoscenza_cerca", {"query": a.query, "domain": a.domain, "kind": a.kind,
                                                "include_history": a.storia, "limit": a.limit,
                                                "session_ref": a.session}))
    if a.cmd == "leggi":
        return _print(call("conoscenza_leggi", {"id": a.id, "session_ref": a.session}))
    if a.cmd == "registra":
        fields = json.loads(a.json)
        tool = "conoscenza_lavoro" if fields.get("kind") == "WORK_UPDATE" else "conoscenza_registra"
        return _print(call(tool, fields))
    if a.cmd == "cambia":
        return _print(call("conoscenza_cambia", {"old_id": a.id, **json.loads(a.json)}))
    if a.cmd == "approva":
        return _print(call("conoscenza_approva", {"id": a.id, "note": a.nota, "session_ref": a.session}))
    if a.cmd == "collega":
        return _print(call("conoscenza_collega", {"from_id": a.da, "to_id": a.a, "relation": a.relazione,
                                                  "note": a.nota, "session_ref": a.session}))
    if a.cmd == "accessi":
        return _print(call("conoscenza_storico", {"filter_session": a.session, "client": a.client_filtro,
                                                  "limit": a.limit}))
    if a.cmd == "riprova":
        return _print(api.retry_pending())
    from rfone_data_store.conoscenza import importer
    if a.cmd == "importa":
        return _print({"ok": True, **importer.import_heritage(api)})
    if a.cmd == "importa-estratto":
        return _print({"ok": True, **importer.import_extract(api, Path(a.file))})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
