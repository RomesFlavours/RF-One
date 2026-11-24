#!/usr/bin/env python
"""Conoscenza first-release test suite (`10 System/Conoscenza/README.md`).

Runs against a disposable SQLite register under the Git-ignored `RF One/tmp/`
folder (inside the authorized project boundary) and deletes it afterwards.
Never touches the working register `data/conoscenza.db`.

Usage:
    python test_conoscenza.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rfone_data_store.conoscenza import importer  # noqa: E402
from rfone_data_store.conoscenza.api import Conoscenza  # noqa: E402
from rfone_data_store.conoscenza.store import (REPO_ROOT, ensure_schema, issue_missing_tokens,  # noqa: E402
                                                make_engine, session_factory)

CHECKS: list[str] = []


def check(condition: bool, label: str, detail=None) -> None:
    if not condition:
        raise AssertionError(f"FAIL: {label}" + (f" — {detail}" if detail is not None else ""))
    CHECKS.append(label)


TIPS_ALLOCATION = dict(
    kind="DECISION", authority="PO_EXPLICIT", decided_by="Pino", decided_on="2026-11-24",
    domain="Restaurant/Tips", title="Tips: ripartizione per sede, poi somma per persona",
    statement="Ripartire ogni ordine con la regola della sede in cui è nato; poi sommare per persona le quote "
              "ottenute in tutte le sedi.",
    rationale="Le sedi sono LLC distinte e una persona può lavorare in entrambe.",
    validity_conditions="Ogni calcolo Tips con più sedi.",
    exceptions="Non si applica una regola unica di gruppo agli ordini di sedi diverse.",
    keywords="mance tips ripartizione sedi LLC persona dipendente somma",
    source_type="CHAT_SESSION", source_ref="test:session-1", session_ref="test-session-1")


def multi_person_checks(url: str, work: Path) -> None:
    """A future collaborator (Shelbi) with limited rules; proposals and approval."""
    from rfone_data_store.conoscenza import models as k
    from rfone_data_store.conoscenza.store import token_hash, utcnow
    engine = make_engine(url)
    with session_factory(engine)() as db:
        shelbi = k.KnowledgePerson(name="Shelbi", is_owner=False, status="ACTIVE", created_at=utcnow())
        db.add(shelbi)
        db.flush()
        for perm in ("READ", "CONTRIBUTE"):
            db.add(k.KnowledgeAccessRule(person_id=shelbi.id, permission=perm, domain_pattern="Restaurant/Tips",
                                         active=True, created_at=utcnow()))
        db.add(k.KnowledgeClient(client="CLAUDE", person_id=shelbi.id, token_sha256=token_hash("shelbi-claude"),
                                 active=True, created_at=utcnow()))
        db.commit()
    engine.dispose()
    pino = Conoscenza((work / "tokens" / "claude.token").read_text(), url=url, pending_dir=work / "pending")
    shelbi = Conoscenza("shelbi-claude", url=url, pending_dir=work / "pending")
    proposal = dict(kind="DECISION", domain="Restaurant/Tips", title="Proposta: arrotondamento quote al dollaro",
                    statement="Arrotondare le quote Tips al dollaro intero.", rationale="Semplicità di pagamento.",
                    source_ref="test:shelbi-1")
    r = shelbi.record(**proposal, authority="PO_EXPLICIT")
    check(not r["ok"], "a collaborator cannot create an owner decision", r)
    r = shelbi.record(**proposal, authority="PROPOSAL")
    check(r["ok"] and r["item"]["fornito_da"] == "Shelbi" and r["item"]["registrato_tramite"] == "CLAUDE"
          and "deciso_o_approvato_da" not in r["item"], "proposal attributed to Shelbi via Claude", r)
    pid = r["item"]["id"]
    r = shelbi.record(**{**proposal, "domain": "System/Conoscenza", "authority": "PROPOSAL"})
    check(not r["ok"], "no contribution outside the allowed domains")
    seen = shelbi.search("conoscenza registro tips mance", limit=25)["risultati"]
    check(seen and all(x["dominio"].startswith("Restaurant/Tips") for x in seen), "reading limited to allowed domains")
    check(not shelbi.approve(pid)["ok"], "a collaborator cannot approve")
    check(not shelbi.access_log()["ok"], "access history reserved to the owner")
    a = pino.approve(pid, note="ok")
    check(a["ok"] and a["esito"] == "APPROVATA" and a["item"]["deciso_o_approvato_da"] == "Pino"
          and a["item"]["fornito_da"] == "Shelbi", "owner approval keeps the proposer", a)
    check([v["stato"] for v in a["item"]["versioni"]] == ["sostituita", "vigente"] and a["item"]["approvazioni"],
          "original proposal kept and approval recorded")
    check(pino.approve(pid)["esito"] == "GIA_REGISTRATO", "repeated approval is idempotent")
    pino.close()
    shelbi.close()


def http_checks(url: str, work: Path, tok: dict) -> None:
    """The AWS service in-process: MCP over HTTP, OAuth for ChatGPT, remote proxy and its queue."""
    import base64
    import hashlib
    import threading
    from urllib.parse import parse_qs, urlsplit
    import logging
    from werkzeug.serving import make_server
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    os.environ["RFONE_CONOSCENZA_DATABASE_URL"] = url
    from rfone_data_store.conoscenza import http_app
    from rfone_data_store.conoscenza.api import RemoteConoscenza
    http_app._factory = None
    client = http_app.app.test_client()
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    check(r.status_code == 401 and "resource_metadata" in r.headers.get("WWW-Authenticate", ""),
          "unauthenticated MCP refused with OAuth discovery")
    meta = client.get("/.well-known/oauth-authorization-server").get_json()
    check(meta["code_challenge_methods_supported"] == ["S256"] and meta["registration_endpoint"].endswith("/oauth/register"),
          "OAuth metadata published")
    reg = client.post("/oauth/register", json={"client_name": "ChatGPT", "redirect_uris": ["https://chatgpt.com/cb"]})
    cid = reg.get_json()["client_id"]
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = dict(response_type="code", client_id=cid, redirect_uri="https://chatgpt.com/cb", code_challenge=challenge,
             code_challenge_method="S256", state="xyz")
    page = client.get("/oauth/authorize", query_string=q)
    check(page.status_code == 200 and b"How this page works" in page.data, "authorization page with help")
    wrong = client.post("/oauth/authorize", data={**q, "access_key": tok["claude"]})
    check(wrong.status_code == 200 and b"not valid" in wrong.data, "only the ChatGPT key authorizes ChatGPT")
    ok = client.post("/oauth/authorize", data={**q, "access_key": tok["chatgpt"]})
    loc = urlsplit(ok.headers["Location"])
    code = parse_qs(loc.query)["code"][0]
    check(ok.status_code == 302 and parse_qs(loc.query)["state"] == ["xyz"], "authorization code issued")
    bad = client.post("/oauth/token", data=dict(grant_type="authorization_code", code=code, client_id=cid,
                                                redirect_uri="https://chatgpt.com/cb", code_verifier="x" * 64))
    check(bad.status_code == 400, "PKCE enforced")
    t = client.post("/oauth/token", data=dict(grant_type="authorization_code", code=code, client_id=cid,
                                              redirect_uri="https://chatgpt.com/cb", code_verifier=verifier)).get_json()
    check(t.get("access_token") and t.get("refresh_token"), "access token issued", t)
    reuse = client.post("/oauth/token", data=dict(grant_type="authorization_code", code=code, client_id=cid,
                                                  redirect_uri="https://chatgpt.com/cb", code_verifier=verifier))
    check(reuse.status_code == 400, "authorization code single use")
    t2 = client.post("/oauth/token", data=dict(grant_type="refresh_token", refresh_token=t["refresh_token"])).get_json()
    check(t2.get("access_token") and client.post("/oauth/token", data=dict(
        grant_type="refresh_token", refresh_token=t["refresh_token"])).status_code == 400, "refresh token rotation")
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "conoscenza_registra", "arguments": {
        "kind": "DECISION", "authority": "PO_EXPLICIT", "domain": "Restaurant/Tips", "title": "Decisione da ChatGPT",
        "statement": "Prova di scrittura da ChatGPT.", "rationale": "Test.", "source_ref": "chatgpt:test"}}}
    r = client.post("/mcp", json=call, headers={"Authorization": f"Bearer {t2['access_token']}"})
    payload = json.loads(r.get_json()["result"]["content"][0]["text"])
    check(payload["ok"] and payload["item"]["registrato_tramite"] == "CHATGPT" and payload["item"]["fornito_da"] == "Pino",
          "ChatGPT write attributed to Pino via ChatGPT", payload)
    tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                        headers={"Authorization": f"Bearer {tok['codex']}"}).get_json()["result"]["tools"]
    check(len(tools) == 9, "tools listed over HTTP for a tool credential")

    server = make_server("127.0.0.1", 0, http_app.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    live_url = f"http://127.0.0.1:{server.server_port}"
    pend = work / "remote-pending"
    try:
        remote = RemoteConoscenza(live_url, tok["claude"], pending_dir=pend)
        check(remote.call_tool("conoscenza_cerca", {"query": "mance due sedi"})["ok"], "remote proxy search")
        down = RemoteConoscenza("http://127.0.0.1:9", tok["claude"], pending_dir=pend, timeout=3)
        w = down.call_tool("conoscenza_registra", {"kind": "CORRECTION", "authority": "PO_EXPLICIT",
                                                   "domain": "Restaurant/Tips", "title": "Scritta offline",
                                                   "statement": "Scritta mentre il servizio era giù.",
                                                   "source_ref": "test:offline"})
        check(not w["ok"] and w.get("in_coda") and len(down.pending()) == 1, "offline write queued, not lost", w)
        again = down.retry_pending()
        check(not again["ok"] and len(down.pending()) == 1, "still offline: queue kept without copies")
        b = remote.call_tool("conoscenza_contesto", {})
        check(b["ok"] and not remote.pending(), "queue replayed automatically on reconnection", b)
        found = remote.call_tool("conoscenza_cerca", {"query": "Scritta offline servizio giù", "limit": 25})
        check(sum(1 for x in found["risultati"] if x["titolo"] == "Scritta offline") == 1,
              "queued write reached the register exactly once")
    finally:
        server.shutdown()
        os.environ.pop("RFONE_CONOSCENZA_DATABASE_URL", None)
        if http_app._factory is not None:
            http_app._factory.kw["bind"].dispose()
            http_app._factory = None


def migration_checks(work: Path) -> None:
    """Dry run of the AWS migration on the real first-release register (read-only)."""
    from rfone_data_store.conoscenza import migration
    from rfone_data_store.conoscenza.store import DEFAULT_DB
    if not DEFAULT_DB.is_file():
        return
    data = migration.export_v1_sqlite(DEFAULT_DB) if _is_v1(DEFAULT_DB) else None
    if data is None:
        return
    target = make_engine(f"sqlite:///{(work / 'migrated.db').as_posix()}")
    ensure_schema(target)
    migration.load(target, data)
    check(migration.manifest(migration.read_all(target)) == migration.manifest(data),
          "migration dry run: destination identical to the source", migration.manifest(data))
    try:
        migration.load(target, data)
        check(False, "second import refused")
    except RuntimeError:
        check(True, "import refused on a non-empty register")
    target.dispose()


def _is_v1(path: Path) -> bool:
    import sqlite3
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return "conoscenza_people" not in {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    finally:
        con.close()


def main() -> int:
    work = REPO_ROOT / "tmp" / f"conoscenza-test-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True)
    url = f"sqlite:///{(work / 'register.db').as_posix()}"
    opened: list[Conoscenza] = []
    real_init = Conoscenza.__init__

    def tracking_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        opened.append(self)

    Conoscenza.__init__ = tracking_init
    try:
        engine = make_engine(url)
        ensure_schema(engine)
        tokens = work / "tokens"
        with session_factory(engine)() as db:
            issued = issue_missing_tokens(db, tokens)
        engine.dispose()
        check(sorted(issued) == ["CHATGPT", "CLAUDE", "CODEX", "IMPORTER"], "one token per client", issued)
        tok = {c: (tokens / f"{c}.token").read_text() for c in ("claude", "codex", "importer", "chatgpt")}
        claude = Conoscenza(tok["claude"], url=url, pending_dir=work / "pending")
        codex = Conoscenza(tok["codex"], url=url, pending_dir=work / "pending")

        # Authentication
        bad = Conoscenza("not-a-token", url=url, pending_dir=work / "pending").search("tips")
        check(not bad["ok"] and bad["tipo_errore"] == "AUTENTICAZIONE", "invalid token refused")

        # Record + read-back confirmation, attribution from the token
        out = claude.record(**TIPS_ALLOCATION, recorded_by="CODEX")
        check(out["ok"] and out["esito"] == "REGISTRATO", "write confirmed by the register", out)
        item = out["item"]
        check(item["registrato_tramite"] == "CLAUDE", "recording tool taken from the token, not declared")
        check(item["fornito_da"] == "Pino" and item["deciso_o_approvato_da"] == "Pino",
              "person who provided and person who decided are recorded", item)
        check(item["autorita"].startswith("Decisione esplicita"), "PO decision recognizable")
        # Safe repetition
        again = claude.record(**TIPS_ALLOCATION)
        check(again["esito"] == "GIA_REGISTRATO" and again["item"]["id"] == item["id"], "repeat creates no duplicate")

        # Refusals
        r = claude.record(**{**TIPS_ALLOCATION, "kind": "BOGUS", "title": "x"})
        check(not r["ok"] and r["tipo_errore"] == "RIFIUTATA", "invalid entry refused")

        # Search with different words (no shared literal word with the title)
        found = codex.search("Come divido le gratuity di un cameriere che fa turni in due ristoranti?",
                             session_ref="test-session-2")
        check(found["ok"] and found["risultati"] and found["risultati"][0]["id"] == item["id"],
              "retrieval with different words", found)

        # Versions: AI cannot override Pino; PO change supersedes
        r = codex.supersede(item["id"], authority="AI_HYPOTHESIS", statement="ipotesi", source_ref="test:s3")
        check(not r["ok"], "AI hypothesis cannot supersede a PO decision")
        changed = claude.supersede(item["id"], statement=TIPS_ALLOCATION["statement"] + " Le quote si arrotondano al "
                                   "centesimo per sede.", source_ref="test:session-3", decided_on="2026-11-25")
        check(changed["ok"] and changed["item"]["versione"] == 2, "PO change creates version 2", changed)
        retry = claude.supersede(item["id"], statement=TIPS_ALLOCATION["statement"] + " Le quote si arrotondano al "
                                 "centesimo per sede.", source_ref="test:session-3", decided_on="2026-11-25")
        check(retry["ok"] and retry["esito"] == "GIA_REGISTRATO", "repeated supersede is idempotent", retry)
        old = claude.read(item["id"])["item"]
        check(old["stato"] == "sostituita" and len(old["versioni"]) == 2, "old version kept and marked superseded")
        cur = codex.search("mance sedi persona")["risultati"]
        check([x["id"] for x in cur].count(changed["item"]["id"]) == 1 and item["id"] not in [x["id"] for x in cur],
              "search returns only the current version")

        # Work status with evidence
        r = claude.record(kind="WORK_UPDATE", domain="System/Conoscenza", title="t", statement="s",
                          work_ref="CONOSCENZA_01", work_stage="VERIFIED", source_ref="test:w",
                          evidence=[{"kind": "FILE", "reference": "x.py"}])
        check(not r["ok"], "VERIFIED without test evidence refused")
        r = claude.record(kind="WORK_UPDATE", domain="System/Conoscenza", title="Registro verificato",
                          statement="Test superati", work_ref="CONOSCENZA_01", work_stage="VERIFIED",
                          source_ref="test:w", evidence=[{"kind": "TEST", "reference": "test_conoscenza.py"}])
        check(r["ok"] and r["item"]["stadio"] == "verificato", "work update with stage and evidence", r)

        # Unreachable register: write queued, reported, retried without duplicates
        down = Conoscenza(tok["claude"], url="postgresql+psycopg2://nobody:none@127.0.0.1:1/none?connect_timeout=2",
                          pending_dir=work / "pending")
        fail = down.record(**{**TIPS_ALLOCATION, "title": "Scrittura durante guasto", "source_ref": "test:down"})
        check(not fail["ok"] and fail["tipo_errore"] == "REGISTRO_IRRAGGIUNGIBILE" and fail.get("in_coda"),
              "failed write reported and queued", fail)
        b = down.brief()
        check(not b["ok"] and b["scritture_in_coda"], "unreachable register visible in the brief", b)
        first = claude.retry_pending()
        check(first["ok"] and len(first["ripetute"]) == 1, "queued write replayed", first)
        check(not claude.pending(), "queue empty after replay")

        # Access log proves who consulted what
        log = codex.access_log(session_ref="test-session-2")["accessi"]
        check(any(a["operazione"] == "SEARCH" and a["strumento"] == "CODEX" and a["persona"] == "Pino"
                  and str(item["id"]) in (a["voci"] or "") for a in log),
              "access log records person, tool, search and results")

        multi_person_checks(url, work)
        http_checks(url, work, tok)
        migration_checks(work)

        # Heritage import on the real sources (read-only), idempotent
        imp = Conoscenza(tok["importer"], url=url, pending_dir=work / "pending")
        rep1 = importer.import_heritage(imp)
        n1 = rep1["Decisioni RF1.md"]["nuove"] + rep1["CLAUDE.md"]["nuove"]
        check(n1 > 10 and not rep1["Decisioni RF1.md"]["fallite"] and not rep1["CLAUDE.md"]["fallite"],
              "heritage imported", rep1)
        rep2 = importer.import_heritage(imp)
        check(rep2["Decisioni RF1.md"]["nuove"] == 0 and rep2["CLAUDE.md"]["nuove"] == 0, "re-import adds nothing")
        tips_ready = codex.search("quando posso iniziare a calcolare le mance del periodo?")["risultati"]
        check(any("Tips pronte" in x["titolo"] for x in tips_ready[:3]), "imported decision retrievable", tips_ready[:3])

        # Extract import (another AI's conversation excerpt)
        extract = work / "extract.jsonl"
        extract.write_text(json.dumps({"kind": "DECISION", "authority": "AI_HYPOTHESIS", "domain": "Restaurant/Tips",
                                       "title": "Ipotesi ChatGPT di prova", "statement": "s",
                                       "source_ref": "chatgpt:conversation/test#1"}) + "\n", encoding="utf-8")
        e1 = importer.import_extract(imp, extract)
        e2 = importer.import_extract(imp, extract)
        check(e1["nuove"] == 1 and e2["nuove"] == 0, "extract import with source, idempotent", (e1, e2))

        # MCP server round trip over stdio
        env = dict(os.environ, RFONE_CONOSCENZA_DATABASE_URL=url, RFONE_CONOSCENZA_TOKEN=tok["claude"],
                   RFONE_CONOSCENZA_URL="")
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "conoscenza_cerca", "arguments": {"query": "gratuity camerieri due locali"}}}]
        proc = subprocess.run([sys.executable, str(HERE / "conoscenza.py"), "--client", "claude", "mcp"],
                              input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True,
                              text=True, encoding="utf-8", env=env, timeout=60)
        replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        check(len(replies) == 3 and replies[0]["result"]["serverInfo"]["name"] == "rf-one-conoscenza",
              "MCP initialize", proc.stderr[-500:])
        check(len(replies[1]["result"]["tools"]) == 9, "MCP tools listed")
        payload = json.loads(replies[2]["result"]["content"][0]["text"])
        check(payload["ok"] and payload["risultati"][0]["dominio"] == "Restaurant/Tips", "MCP search works", payload)
    finally:
        Conoscenza.__init__ = real_init
        for api in opened:
            api.close()
        shutil.rmtree(work, ignore_errors=True)
    print(f"PASS: {len(CHECKS)} controlli Conoscenza superati")
    for label in CHECKS:
        print(f"  ok  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
