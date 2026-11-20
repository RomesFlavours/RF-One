#!/usr/bin/env python
"""HTTP test for the WHO format review under Find standard formats (BANK_WHO_FORMAT_REVIEW_001).

Runs on an ISOLATED COPY of the local Bank database (SQLite backup API, removed at the end). The AI is a
deterministic stand-in: the search proposes one ACH originator extraction rule, the correction adds an
exclusion. Checked: every selected movement is listed with Source, date, description, amount and WHO;
ticks are saved as review notes only; the AI correction is validated, tested on the whole history and its
changes are shown; the coverage counts each movement once; no rule is created or activated, no WHO,
movement or human decision changes.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest import mock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
if not _SOURCE.exists():
    print("SKIPPED: no local Bank database to copy.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_who_review_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "who-review-test-secret"
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"      # as the local Bank runs it: no background import pipeline
os.environ.pop("RFONE_BANK_WHY_PATTERNS", None)

import app as web_app  # noqa: E402
import bank_assistant_preview_routes  # noqa: E402
import bank_chatgpt  # noqa: E402
import bank_flow_routes  # noqa: E402
import bank_who_format_review  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')
RULE = dict(engine="BANK_FLOW_2", kind="EXTRACTOR", start="ORIG CO NAME:", end_mode="marker", end="ORIG ID:",
            suffix_policy="none")


def state(db):
    """What may never change: rules, WHOs, decisions and the movements themselves."""
    return (db.scalar(select(func.count(m.BankAiRule.id))), db.scalar(select(func.count(m.BankAiRuleVersion.id))),
            db.scalar(select(func.count(m.BankOccurrence.id))),
            sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id,
                                                       m.FinancialTransaction.description_original,
                                                       m.FinancialTransaction.amount_minor)).all()),
            db.scalar(select(func.count(m.BankTransactionExplanation.id))))


def search_stub(prompt, **_):
    return {"formats": [dict(title="ACH originator", reply="The WHO is the originator company name.", spec=RULE, rule_id=None)]}


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    with SessionFactory() as db:
        before = state(db)
        account_service.create_account(db, username="who_operator", display_name="who_operator",
                                       password="OperatorPass123!", status="ACTIVE", is_admin=False)
        db.commit()
        operator = db.query(m.RFOneAccount).filter_by(username="who_operator").one()
        account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                          role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
        before = state(db)[:4] + (state(db)[4],)
    client = web_app.app.test_client()
    client.post("/login", data={"username": "who_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    page = client.get("/bank/ai-rules").data.decode("utf-8")
    csrf = (BANK_CSRF_RE.search(page) or [None, None])[1]
    script = client.get("/static/bank-assistant/who_review.js").data.decode("utf-8")
    check("1. the page offers Find standard formats again; Discover WHY Patterns is not shown",
          "Find standard formats" in page and 'id="discover"' in page and "Discover WHY Patterns" not in page
          and "who_review.js" in page and 'id="who-coverage"' in page)
    check("1b. Discover WHY Patterns is off: its addresses do not exist",
          client.get("/bank/flow/why-rules").status_code == 404)

    with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True), \
            mock.patch.object(bank_flow_routes.threading, "Thread"):
        scan_id = (client.post("/bank/flow/discover", data={"csrf_token": csrf}).get_json() or {}).get("id")
    bank_flow_routes.discovery(SessionFactory, scan_id, generate=search_stub)
    scan = client.get(f"/bank/flow/discover/{scan_id}").get_json() or {}
    formats = scan.get("formats", [])
    check("2. the original generator examines every movement and proposes the WHO format",
          scan.get("examined") == len(before[3]) and scan.get("groups", 0) > 0 and len(formats) == 1
          and formats[0]["spec"]["start"] == "ORIG CO NAME:", {k: scan.get(k) for k in ("status", "examined", "groups", "errors")})
    index = formats[0]["index"]
    rows = (client.get(f"/bank/flow/discover/{scan_id}/formats/{index}/movements").get_json() or {}).get("rows", [])
    ach = [t for t in before[3] if "ORIG CO NAME:" in (t[2] or "") and "ORIG ID:" in (t[2] or "")]
    check("3. EVERY movement the rule selects is listed, with Source, date, description, amount and WHO",
          len(rows) == len(ach) and rows and all(all(r.get(k) for k in ("source", "date", "description", "amount", "who")) for r in rows),
          (len(rows), len(ach)))
    check("3b. the page script shows a checkbox per movement and a scrolling table (none hidden)",
          'data-wrong="${r.id}"' in script and "who-scroll" in script and "data.rows.map" in script)
    merchant = [r["id"] for r in rows if r["who"].startswith("MERCHANT BANKCD")]
    wrong = merchant[:3]
    resp = client.post(f"/bank/flow/discover/{scan_id}/formats/{index}/review",
                       data={"csrf_token": csrf, "wrong": ",".join(map(str, wrong))})
    saved = (client.get(f"/bank/flow/discover/{scan_id}/formats/{index}/movements").get_json() or {}).get("review", {})
    check("4. several wrong recognitions can be ticked and are saved as review notes",
          resp.status_code == 200 and saved.get("wrong") == sorted(wrong) and saved.get("reviewed") is True and len(wrong) >= 2,
          saved)
    with SessionFactory() as db:
        check("4b. ticks change nothing in Bank (rules, WHOs, decisions, movements)", state(db) == before)

    cov = client.get(f"/bank/flow/discover/{scan_id}/coverage").get_json() or {}
    check("5. coverage: each movement counted once; proposed and verified kept apart",
          cov.get("movements") == len(before[3]) and cov.get("selected") == len(rows) and cov.get("flagged_wrong") == len(wrong)
          and cov.get("verified") == len(rows) - len(wrong) and cov.get("without_who") == cov["movements"] - cov["recognized"]
          and cov.get("distinct_who") == len({r["who"] for r in rows}), cov)

    prompts = []
    corrected = dict(RULE, exclude=["MERCHANT BANKCD"])

    def fix_stub(prompt, **_):
        prompts.append(prompt)
        return dict(title="ACH originator, without card deposits", reply="Card deposits are not a WHO: excluded.", spec=corrected)

    with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True), \
            mock.patch.object(bank_who_format_review.bank_chatgpt, "generate_json", side_effect=fix_stub):
        resp = client.post(f"/bank/flow/discover/{scan_id}/formats/{index}/revise",
                           data={"csrf_token": csrf, "wrong": ",".join(map(str, wrong)), "note": "MERCHANT BANKCD is a card deposit"})
    body = resp.get_json() or {}
    diff = body.get("diff") or {}
    payload = json.loads(prompts[0][prompts[0].index('{"current_rule"'):]) if prompts else {}
    check("6. the AI receives the rule, the note and at most three masked descriptions (no amounts)",
          bool(prompts) and payload.get("person_note") and len(payload["wrong_examples"]) + len(payload["right_examples"]) <= 3
          and not any("amount" in json.dumps(x) for x in payload["wrong_examples"] + payload["right_examples"]))
    check("7. the corrected rule is tested on the whole history and its changes are shown",
          resp.status_code == 200 and diff.get("before") == len(rows) and len(diff.get("removed", [])) == len(merchant)
          and diff.get("wrong_fixed") == len(wrong) and diff.get("after") == len(rows) - len(merchant), {k: diff.get(k) for k in ("before", "after", "wrong_fixed")})
    scan2 = client.get(f"/bank/flow/discover/{scan_id}").get_json() or {}
    check("8. the corrected rule replaces the proposal: Discuss and preview -> Save approves it as before",
          scan2["formats"][0]["spec"].get("exclude") == ["MERCHANT BANKCD"] and scan2["formats"][0]["title"].startswith("ACH originator"))
    with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True), \
            mock.patch.object(bank_who_format_review.bank_chatgpt, "generate_json",
                              return_value=dict(reply="x", spec=dict(RULE, start=""))):
        bad = client.post(f"/bank/flow/discover/{scan_id}/formats/{index}/revise", data={"csrf_token": csrf, "note": "x"})
    check("9. an invalid AI correction is refused and the proposal is kept", bad.status_code == 409
          and (client.get(f"/bank/flow/discover/{scan_id}").get_json() or {})["formats"][0]["spec"].get("exclude") == ["MERCHANT BANKCD"])
    with SessionFactory() as db:
        check("10. no rule was created or activated; no WHO, movement or decision changed", state(db) == before)
    from rfone_data_store.bank_reconciliation import flow
    E = lambda **k: dict(engine="BANK_FLOW_2", kind="EXTRACTOR", **k)
    cases = [(E(prefix="PURCHASE", start="PURCHASE {date} ", end_mode="marker", end_markers=["  ", " {number}"]),
              "PURCHASE 05/08 DOLLARTREE      821 US HWY17/92 LONGWOOD FL    234730", "DOLLARTREE"),
             (E(prefix="POS SIG", start="VISA #{number} ", end_mode="marker", end_markers=[" {number}"]),
              "POS SIG 03/19 VISA #5363 MILLER HARDWARE 5125 WINTER PARK FL", "MILLER HARDWARE"),
             (E(from_beginning=True, end_mode="marker", end_markers=[" #"]), "PUBLIX #1661 ALTAMONTE SPR FL   05/11", "PUBLIX"),
             (E(from_beginning=True, end_mode="last_code"), "SEASONS 52 0074503", "SEASONS 52"),
             (E(start="Zelle payment to ", end_mode="last_code"), "Zelle payment to Alice Martini JPM99cxzwg7b", "ALICE MARTINI")]
    check("11. variable parts ({date}, {number}) and a WHO opening the description are extracted",
          all(flow.extract(sp, d) == w for sp, d, w in cases), [flow.extract(sp, d) for sp, d, _ in cases])
    refused = []
    for bad in (E(end_mode="end"), E(start="A {anything} ", end_mode="end"), E(from_beginning=True, end_mode="end")):
        try:
            flow.validate(None, bad)
        except ValueError:
            refused.append(True)
    check("11b. no start, an unknown placeholder or 'the whole description is the WHO' are refused", refused == [True] * 3)
    from types import SimpleNamespace
    anchored = E(start="Zelle payment to ", end_mode="last_code")
    generic = E(from_beginning=True, end_mode="last_code")
    entries = [(SimpleNamespace(id=1), None, generic), (SimpleNamespace(id=2), None, anchored)]
    with mock.patch.object(flow, "kind", return_value="EXTRACTOR"):
        who, rules, ambiguous = flow.identity(None, SimpleNamespace(description_original="Zelle payment to Alice Martini JPM99cxzwg7b"), entries)
        who2, _r, _a = flow.identity(None, SimpleNamespace(description_original="SEASONS 52 0074503"), entries)
    check("11c. an anchored rule takes precedence over a general one; the general one reads the rest",
          who == "ALICE MARTINI" and rules == [2] and not ambiguous and who2 == "SEASONS 52", (who, rules, who2))
    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
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
