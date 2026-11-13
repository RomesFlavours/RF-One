#!/usr/bin/env python
"""HTTP test for the AI rules check (BANK_AI_RULE_CHECK_001), on an ISOLATED COPY of the local database:
every operative rule is run on every movement, shown per rule with the human decision and the engine
result; the conflicts and the unread movements are listed; nothing is written."""
from __future__ import annotations

import atexit, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path

APP_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path[:0] = [APP_DIR, os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))]
_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
if not _SOURCE.exists():
    print("SKIPPED: no local Bank database to copy.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_rule_check_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_s = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True); _d = sqlite3.connect(_COPY); _s.backup(_d); _d.close(); _s.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "rule-check-test-secret"
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import flow  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def snapshot(db):
    return (sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id)).all()),
            db.scalar(select(func.count(m.BankTransactionExplanation.id))), db.scalar(select(func.count(m.BankAiRule.id))))


def main() -> int:
    passed, failed = [], []

    def check(d, ok, detail=""):
        (passed if ok else failed).append(d)
        print(f"  {'PASS' if ok else 'FAIL'}  {d}" + ("" if ok or not detail else f"   [{str(detail)[:300]}]"))

    with SessionFactory() as db:
        before = snapshot(db)
        account_service.create_account(db, username="rc_operator", display_name="rc_operator", password="OperatorPass123!", status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="rc_operator").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
        operative = len(flow.entries(db))
    c = web_app.app.test_client()
    c.post("/login", data={"username": "rc_operator", "password": "OperatorPass123!", "csrf_token": CSRF_RE.search(c.get("/login").data.decode()).group(1)})
    check("1. the check page opens and is linked from AI Rules", c.get("/bank/ai-rules/check").status_code == 200
          and 'href="/bank/ai-rules/check"' in c.get("/bank/ai-rules/advanced").data.decode())
    data = c.get("/bank/ai-rules/check/data").get_json()
    s = data["summary"]
    check("2. every operative rule is run on every movement", s["rules"] == operative == len(data["rules"])
          and s["movements"] == len(before[0]) and s["read"] + s["unread"] == s["movements"], s)
    top = data["rules"][0]
    rows = c.get(f"/bank/ai-rules/check/rules/{top['id']}").get_json()["rows"]
    check("3. a rule shows every movement it intercepts with its WHO/WHY, the human decision and the engine result",
          len(rows) == top["movements"] and all({"source", "date", "description", "amount", "who", "why", "human_who", "engine"} <= set(r) for r in rows), top)
    conf = c.get("/bank/ai-rules/check/list/conflicts").get_json()["rows"]
    unread = c.get("/bank/ai-rules/check/list/unread").get_json()["rows"]
    check("4. conflicts and unread movements are listed", len(conf) == s["conflicts"] and len(unread) == s["unread"])
    with SessionFactory() as db:
        check("5. nothing was written (movements, decisions, rules)", snapshot(db) == before)
    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        try:
            from db import _engine
            _engine.dispose()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(code)
