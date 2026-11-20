#!/usr/bin/env python
"""HTTP test for WHO Search Text (BANK_WHO_SEARCH_TEXT_001), on an ISOLATED COPY of the local database.

Every movement shows the WHO recognised in its description; the text to search is saved as an alias of an
existing WHO or, with no WHO, as a new WHO; a WHO without WHO-WHY-WHAT association asks for it, saved by
`configuration.save_who`; nothing changes a movement's decisions.
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

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
_FOLDER = tempfile.mkdtemp(prefix="rfone_who_search_text_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "who-search-text-test-secret"
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')


def decisions(db):
    return sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id)).all()), \
        db.scalar(select(func.count(m.BankTransactionExplanation.id)))


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    with SessionFactory() as db:
        before = decisions(db)
        account_service.create_account(db, username="st_operator", display_name="st_operator", password="OperatorPass123!",
                                       status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="st_operator").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
    client = web_app.app.test_client()
    client.post("/login", data={"username": "st_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    check("1. the rules page links WHO Search Text", 'href="/bank/who-search-text"' in client.get("/bank/ai-rules").data.decode())
    page = client.get("/bank/who-search-text").data.decode()
    csrf = BANK_CSRF_RE.search(page).group(1)
    check("2. the page has its breadcrumb, the two modals with X, Save WHO and Cancel",
          "WHO Rules" in page and 'data-cancel="st-text" aria-label="Close"' in page and 'data-cancel="st-assoc" aria-label="Close"' in page and "Save WHO" in page and "Cancel" in page)
    check("2b. both WHO recognitions are shown by name: WHO recognition rules, then WHO Search Text",
          '<h2 id="extractors-heading">WHO recognition rules' in page and '<h2 id="st-list-h">WHO Search Text' in page
          and page.index('id="extractors-heading"') < page.index('id="st-list-h"'))
    data = client.get("/bank/who-search-text/data").get_json()
    rows = data["movements"]
    names = [w["name"] for w in data["whos"]]
    check("3. every movement is listed with source, date, description, amount and recognised WHO",
          len(rows) == len(before[0]) and all({"source", "date", "description", "amount", "whos"} <= set(r) for r in rows))
    check("4. the WHO list is alphabetical (names only, not aliases)", names == sorted(names, key=str.casefold))
    recognised = sum(1 for r in rows if r["whos"])
    check("5. recognition finds WHO in most movements", recognised > len(rows) // 2, recognised)

    unknown = next(r for r in rows if not r["whos"] and len(r["description"]) > 10)
    text = client.get(f"/bank/who-search-text/movement/{unknown['id']}").get_json()
    check("6. the modal shows the movement's raw text", text["ok"] and text["description"] == unknown["description"] and text["fields"])

    # A new WHO (no WHO chosen): created with the text as name, and it asks for its association.
    new_name = "ZZ SEARCH TEXT TEST WHO"
    r = client.post("/bank/who-search-text/save", data={"csrf_token": csrf, "text": new_name, "who_id": "",
                                                         "transaction_id": unknown["id"]}).get_json()
    check("7. empty WHO -> new WHO created, association requested", r.get("outcome") == "created" and r.get("needs_association"), r)
    new_id = r.get("who_id")
    # An alias of that WHO: the alias recognises it on a movement.
    alias = " ".join(unknown["description"].split()[:3])
    r2 = client.post("/bank/who-search-text/save", data={"csrf_token": csrf, "text": alias, "who_id": new_id,
                                                          "transaction_id": unknown["id"]}).get_json()
    after = {x["id"]: x for x in client.get("/bank/who-search-text/data").get_json()["movements"]}
    check("8. alias saved and the movement is now recognised as that WHO",
          r2.get("outcome") == "alias" and new_name in after[unknown["id"]]["whos"], (r2, after[unknown["id"]]))
    # The same text for another WHO is refused.
    other = next(w for w in data["whos"] if w["id"] != new_id)
    r3 = client.post("/bank/who-search-text/save", data={"csrf_token": csrf, "text": alias, "who_id": other["id"]})
    check("9. a text already held by another WHO is refused", r3.status_code == 409 and "already an alias" in r3.get_json()["error"])
    check("10. a too-short text is refused",
          client.post("/bank/who-search-text/save", data={"csrf_token": csrf, "text": "ab", "who_id": new_id}).status_code == 409)
    # The association.
    why = data["whys"][0]
    r4 = client.post("/bank/who-search-text/association", data={"csrf_token": csrf, "who_id": new_id, "why_ids": why["id"],
                                                                 "default_why_id": why["id"]}).get_json()
    with SessionFactory() as db:
        assoc = db.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id)).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == new_id, m.BankOccurrenceReasonAssociation.active.is_(True)))
        who = db.get(m.BankOccurrence, new_id)
        check("11. the association is saved (possible WHY and default WHY)", r4.get("ok") and assoc == 1
              and who.default_transaction_reason_id == why["id"], r4)
    r5 = client.post("/bank/who-search-text/save", data={"csrf_token": csrf, "text": alias + " X1", "who_id": new_id}).get_json()
    check("12. a WHO with an association does not ask for it again", r5.get("ok") and not r5.get("needs_association"), r5)
    no_token = client.post("/bank/who-search-text/save", data={"text": "NO TOKEN TEXT", "who_id": ""})
    with SessionFactory() as db:
        check("13. writes need the CSRF token", no_token.status_code in (400, 403, 409) and not db.scalar(
            select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "NO TOKEN TEXT")), no_token.status_code)
        check("14. nothing changed any movement's decisions", decisions(db) == before)

    # --- WHO recognition rules run first (the AI rules of the flow editor, with the "require" condition) ----------
    from rfone_data_store.bank_reconciliation import flow
    paypal = "ORIG CO NAME:PAYPAL ORIG ID:PAYPALSI77 DESC DATE:260928 CO ENTRY DESCR:PURCHASE SEC:WEB TRACE#:091000010553062 EED:260929 IND ID:JETBLUEAIRW 081 IND NAME:GIUSEPPE MIRAGLIA INSTANT TRANSFER TRN: 2710553062TC"
    spec = dict(engine=flow.ENGINE, kind="EXTRACTOR", require=["PAYPAL"], start="IND ID:", end_mode="marker", end_markers=["IND NAME:"], suffix_policy="numbers")
    with SessionFactory() as db:
        flow.validate(db, spec)
    check("15. rule: if PAYPAL, WHO between IND ID: and IND NAME: (trailing number removed)",
          flow.extract(spec, paypal) == "JETBLUEAIRW" and flow.extract(spec, paypal.replace("PAYPAL", "ACME")) is None
          and flow.extract(spec, paypal.replace("JETBLUEAIRW 081", "1050950454780")) is None and not flow.is_generic(spec))
    padded = dict(spec, require=["ORIG CO NAME:PAYPAL ORIG"], suffix_policy="none")
    check("15b. a required text matches the bank's padded spaces (typed with one space)",
          flow.extract(padded, paypal.replace("NAME:PAYPAL ORIG", "NAME:PAYPAL                 ORIG")) == "JETBLUEAIRW 081")
    letters = dict(padded, name_cleanup="letters")
    check("15c. name cleanup 'letters': digits and special characters removed; nothing left -> no WHO",
          flow.extract(letters, paypal) == "JETBLUEAIRW"
          and flow.extract(letters, paypal.replace("JETBLUEAIRW 081", "SPOTIFY*P4742E4")) == "SPOTIFY PE"
          and flow.extract(letters, paypal.replace("JETBLUEAIRW 081", "1050950454780")) is None)
    from bank_flow_routes import extractor_family, extractor_key
    plain = dict(spec); plain.pop("require")
    check("16. a required text makes a different rule family and key; rules without it keep their key",
          extractor_family(spec) != extractor_family(plain) and extractor_key(spec) != extractor_key(plain) and '"require"' not in extractor_key(plain))
    # The rule saved as the editor saves it (BankAiRule + CODE version): the page reads it before names and aliases.
    import json
    with SessionFactory() as db:
        rule = m.BankAiRule(title="PayPal IND ID", organization_kind="GENERAL", status="ACTIVE", apply_future=True)
        db.add(rule)
        db.flush()
        db.add(m.BankAiRuleVersion(rule_id=rule.id, version_no=1, rule_text="If PAYPAL, WHO between IND ID: and IND NAME:",
                                   spec=json.dumps(spec), method="CODE", create_missing_who=False, override_protected=True))
        db.commit()
        paypal_rows = [t.id for t in db.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.description_original.like("%PAYPAL%IND ID:JETBLUEAIRW%")))]
    after = {x["id"]: x for x in client.get("/bank/who-search-text/data").get_json()["movements"]}
    shown = [after[i] for i in paypal_rows]
    check("17. the PAYPAL movement is read by the rule: one WHO, JETBLUEAIRW, not the names/aliases found in the text",
          shown and all(x["by"] == "RULE" and x["whos"] == ["JETBLUEAIRW"] for x in shown), shown[:1])
    page = client.get("/bank/who-search-text").data.decode()
    check("18. the page carries the shared AI rule editor (+ AI rule, rules list, conversation dialog)",
          'id="new-extractor"' in page and 'id="rules-list"' in page and 'id="flow-chat"' in page and "flow.js" in page)
    rules_page = client.get("/bank/ai-rules").data.decode()
    check("19. Rules and profiles still has the same editor", 'id="flow-chat"' in rules_page and 'id="photos-list"' in rules_page)
    with SessionFactory() as db:
        try:
            ok = bool(flow.signature(db))  # the Preview's catalog snapshot, matches included (column "relationship")
        except Exception as exc:  # noqa: BLE001
            ok = exc
    check("20. the rule Preview can snapshot the catalog (a column mapped under another name)", ok is True, ok)

    # --- BANK_WHO_RULES_001: one shared path, WHO Rules in the Bank menu -----------------------------------
    home = client.get("/bank").data.decode()
    check("21. WHO Rules is in the Bank menu and opens this page", 'href="/bank/who-search-text"' in home and ">WHO Rules<" in home)
    rules_page = client.get("/bank/ai-rules").data.decode()
    check("22. the experimental WHO Pattern Training link is out of the main path", "/bank/who-training" not in rules_page)
    from types import SimpleNamespace
    from rfone_data_store.bank_reconciliation import who_search_text
    with SessionFactory() as db:
        rec = who_search_text.WhoRecogniser(db, rules=[])
        names = sorted(rec.names[i] for _, i in rec.keys if len(rec.names[i]) > 5)[:2] if rec.keys else []
        a, b = sorted({k for k, _ in rec.keys if len(k) > 6 and len(rec.by_key[k]) == 1})[:2]
        one = rec.recognise(SimpleNamespace(description_original=f"PAYMENT TO {a} REF 1"))
        two = rec.recognise(SimpleNamespace(description_original=f"PAYMENT {a} AND {b}"))
        none = rec.recognise(SimpleNamespace(description_original="ZZQX UNKNOWN COUNTERPARTY 000"))
    check("23. name/alias search: one WHO -> proposed; several -> review; none -> no WHO (never invented)",
          one.outcome == who_search_text.FOUND and one.method == who_search_text.TEXT
          and two.outcome == who_search_text.TEXT_AMBIGUOUS and len(two.candidates) == 2
          and none.outcome == who_search_text.NONE and none.who is None, (one, two, none))
    data = client.get("/bank/who-search-text/data").get_json()
    check("24. the page reports the same outcomes as the shared path (RULE / TEXT / review / none)",
          {r["by"] for r in data["movements"]} <= {"RULE", "TEXT", "RULES_DISAGREE", "TEXT_AMBIGUOUS", None})

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
