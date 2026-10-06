"""Actionable Classification Learning (BANK_ACTIONABLE_CLASSIFICATION_LEARNING_001).

Classification Learning shows ONLY what needs a human decision. On a
throwaway database migrated to head this proves:

   1-3  a pattern an ACTIVE General / WHO / WHY Rule already expresses is
        recorded as covered and never shown;
   4-6  approved and rejected suggestions leave the list; a rejected one
        returns only on materially new evidence;
   7-8  a genuinely new pattern is shown; with nothing to decide the page
        says so plainly, with no empty table;
  9-10  the backtest is not on the page, and still works as a tool;
 11-12  the Zelle (approved -> General Rule) and Chase (covered) cases;
 13-15  General, WHO and WHY Rules are unchanged by discovery and display.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_actionable_learning_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-actionable-learning-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import pattern_discovery as pd  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition, why_rules  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def learning_section(page: str) -> str:
    return page[page.index('id="classification-learning"'):page.index('id="general-rules"')]


def shown_ids(page: str) -> set[int]:
    return {int(x) for x in re.findall(r'data-suggestion-id="(\d+)"', learning_section(page))}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ------------------------------------------------------------- fixture
    with SessionFactory() as s:
        for username, admin in (("learner", False), ("learn_admin", True)):
            account_service.create_account(s, username=username, display_name=username,
                                           password="LearningRules123!", status="ACTIVE", is_admin=admin)
            s.flush()
            acct = s.query(m.RFOneAccount).filter_by(username=username).one()
            account_service.set_domain_access(s, account_id=acct.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Learning LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Learning Checking", institution="CHASE", last_four="0011",
                                       currency="USD")
        s.add(checking)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="6" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        why = {c: s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == c)).one()
               for c in ("FOOD_PURCHASES", "EMPLOYER_PAYROLL_TAX", "BOH_REGULAR_PAYROLL")}

        def who(name):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                 optional_notes="Canonical WHO.")
            s.add(o)
            s.flush()
            return o

        W = {n: who(n) for n in ("ALICE BAKER", "BRUNO CARUSO", "CARLA DIAZ", "DAVID EVANS", "Acme Payroll",
                                 "Fresh Fish Co", "Bakery Supply", "Linen Co",
                                 "MERCHANT BANKCD", "GORDON FOOD SERV", "CHENEY BROTHERS")}
        # 2 — an ACTIVE WHO Rule already knows Linen Co.
        rule_linen = recognition.create_or_reuse_rule(
            s, match_type="CONTAINS_TEXT", normalized_pattern="LINEN CO SERVICE", occurrence_id=W["Linen Co"].id,
            transaction_reason_id=None, payment_instrument_id=None, direction=None, auto_apply_enabled=True,
            created_from_transaction_id=None)
        # 3 — an ACTIVE WHY Rule already gives Fresh Fish Co its WHY.
        why_rules.create_rule(s, occurrence_id=W["Fresh Fish Co"].id, transaction_reason_id=why["FOOD_PURCHASES"].id,
                              description_contains=None, direction=None, instrument_type=None,
                              approved_by_account_id=None, evidence=None, origin="MANUAL")
        seq = [0]

        def tx(description, day, *, who_=None, why_=None, source="HUMAN"):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=day, transaction_date=day, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"act-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if who_ is not None or why_ is not None:
                recognition._create_decision_row(
                    s, t, occurrence_id=who_.id if who_ else None, transaction_reason_id=why_.id if why_ else None,
                    recognition_rule_id=rule_linen.id if source == "RULE_LINEN" else None,
                    decision_source="HUMAN" if source == "HUMAN" else "RULE",
                    decision_status="HUMAN_CONFIRMED" if source == "HUMAN" else "NEEDS_HUMAN_REVIEW",
                    confidence=None, explanation_notes="seed")
            return t

        for i, day in enumerate(date(2025, mo, 10) for mo in range(1, 10)):
            for j, name in enumerate(("ALICE BAKER", "BRUNO CARUSO", "CARLA DIAZ", "DAVID EVANS")):
                tx(f"Zelle payment to {name.title()} REF55{i}{j}xq", day, who_=W[name], why_=why["FOOD_PURCHASES"])
            # 1 / 12 — covered by the migration's active Chase ACH General Rule.
            for name in ("MERCHANT BANKCD", "GORDON FOOD SERV", "CHENEY BROTHERS"):
                tx(f"ORIG CO NAME:{name}       ORIG ID:1{i} DESC DATE:2501 CO ENTRY DESCR:PAY", day,
                   who_=W[name], source="RULE")
            tx(f"ACME PAYROLL TAX {i}0{i}", day, who_=W["Acme Payroll"], why_=why["EMPLOYER_PAYROLL_TAX"])
            tx(f"ACME PAYROLL WAGE {i}1{i}", day, who_=W["Acme Payroll"], why_=why["BOH_REGULAR_PAYROLL"])
            tx(f"FRESH FISH CO ORDER {i}2{i}", day, who_=W["Fresh Fish Co"], why_=why["FOOD_PURCHASES"])
            tx(f"LINEN CO SERVICE {i}5{i}", day, who_=W["Linen Co"], source="RULE_LINEN")
            if i < 4:
                tx(f"BAKERY SUPPLY ORLANDO {i}7{i}", day, who_=W["Bakery Supply"], why_=why["FOOD_PURCHASES"])
            else:
                tx(f"BAKERY SUPPLY ORLANDO {i}7{i}", day)
        s.commit()
        W_ids = {k: v.id for k, v in W.items()}
        why_ids = {k: v.id for k, v in why.items()}

    def rules_snapshot():
        with SessionFactory() as s:
            return (
                [(r.id, r.name, r.start_marker, r.end_marker, r.status) for r in s.scalars(select(m.BankGeneralRule))],
                [(r.id, r.normalized_pattern, r.occurrence_id, r.status) for r in s.scalars(select(m.BankRecognitionRule))],
                [(r.id, r.occurrence_id, r.transaction_reason_id, r.status) for r in s.scalars(select(m.BankWhyRule))],
            )

    def stored():
        with SessionFactory() as s:
            out = {}
            for x in s.scalars(select(m.BankPatternSuggestion)):
                p = json.loads(x.proposal)
                out[x.id] = (x.pattern_type, p, x.status, x.determinism)
            return out

    def find(kind, pred):
        return [i for i, (t, p, st, d) in stored().items() if t == kind and pred(p)]

    general_before, who_before, why_before = rules_snapshot()
    with SessionFactory() as s:
        chase_rule = [r for r in s.scalars(select(m.BankGeneralRule)) if r.start_marker.upper() == "ORIG CO NAME:"]
    check("fixture: the migration's Chase ACH General Rule is active",
          len(chase_rule) == 1 and chase_rule[0].status == "ACTIVE", str(general_before))

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "learner", "password": "LearningRules123!", "csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    csrf = CSRF_RE.search(page).group(1)
    section = learning_section(page)

    # ------------------------------------------------- 8, 9 before anything
    check("8. with nothing to decide the page says so plainly, with no table",
          "No new classification patterns to review." in section and "<table" not in section)
    check("9. no Run Backtest button and no backtest table on the page",
          "Run Backtest" not in page and "backtest" not in section.lower() and "/bank/learning/backtest" not in page)
    check("5. Discover Patterns is the one learning action on the page",
          "Discover Patterns" in section and section.count("<button") == 1)

    # ------------------------------------------------------------ discover
    resp = client.post("/bank/learning/discover", data={"csrf_token": csrf}, follow_redirects=True)
    page = resp.data.decode()
    section = learning_section(page)
    shown = shown_ids(page)
    zelle = find("STRUCTURAL", lambda p: p["start_marker"].upper().startswith("ZELLE"))
    chase = find("STRUCTURAL", lambda p: p["start_marker"].upper() == "ORIG CO NAME:")
    linen = find("WHO", lambda p: p["who_id"] == W_ids["Linen Co"])
    fish = find("WHY", lambda p: p["who_id"] == W_ids["Fresh Fish Co"])
    bakery = find("WHO", lambda p: p["who_id"] == W_ids["Bakery Supply"])
    acme = [i for i in find("WHY", lambda p: p["who_id"] == W_ids["Acme Payroll"])
            if stored()[i][3] == "DETERMINISTIC"]
    st = stored()

    check("11. discovery reports the count of NEW patterns only",
          re.search(r"New patterns found: \d+", page) is not None, page[:0])
    check("1/12. Chase: the pattern an active General Rule holds is recorded as covered",
          len(chase) == 1 and st[chase[0]][2] == "COVERED", str(chase))
    check("1/12. ... and it is NOT shown — no Covered / already covered / Test / Reject row for it",
          chase[0] not in shown and "ORIG CO NAME" not in section and "overed" not in section)
    check("2. a pattern an active WHO Rule holds (Linen Co) is not shown",
          all(i not in shown and st[i][2] == "COVERED" for i in linen), str([st[i][2] for i in linen]))
    check("3. a pattern an active WHY Rule holds (Fresh Fish Co -> food) is recorded as covered and not shown",
          len(fish) >= 1 and all(st[i][2] == "COVERED" and i not in shown for i in fish),
          str([(st[i][1], st[i][2]) for i in fish]))
    check("7. genuinely new patterns are shown (Zelle structural, Bakery WHO, Acme WHY)",
          zelle and bakery and acme and {zelle[0], bakery[0], acme[0]} <= shown,
          f"zelle={zelle} bakery={bakery} acme={acme} shown={shown}")
    check("5. the list has exactly the decision columns",
          all(f"<th>{h}</th>" in section for h in ("Type", "Pattern", "Target", "Evidence", "Exceptions", "Actions"))
          and "<th>Status</th>" not in section)
    check("5. every shown row offers Review, Test, Approve, Reject",
          all(x in section for x in ("<summary>Review</summary>", ">Test<", ">Approve<", ">Reject<")))
    check("4. only SUGGESTED deterministic patterns are listed",
          all(st[i][2] == "SUGGESTED" and st[i][3] == "DETERMINISTIC" for i in shown), str(shown))
    check("13-15. discovery changes no General, WHO or WHY Rule", rules_snapshot() == (general_before, who_before, why_before))

    # ----------------------------------------------- a second, empty discovery
    page = client.post("/bank/learning/discover", data={"csrf_token": csrf}, follow_redirects=True).data.decode()
    check("11. re-running discovery with nothing new says: No new classification patterns to review.",
          "No new classification patterns to review." in page and "New patterns found" not in page)
    check("11. ... and the same suggestions stay listed, once each",
          shown_ids(page) == shown, f"{shown_ids(page)} vs {shown}")

    # ------------------------------------------------- approve (Zelle case)
    client.post(f"/bank/learning/suggestions/{zelle[0]}/approve", data={"csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    with SessionFactory() as s:
        zs = s.get(m.BankPatternSuggestion, zelle[0])
        routed = zs.routed_to
        new_rule = s.get(m.BankGeneralRule, int(routed.split(":")[1])) if routed else None
    check("4/9. an approved suggestion becomes a General Rule (general_rule:N) and leaves the list",
          zs.status == "APPROVED" and routed and routed.startswith("general_rule:") and zelle[0] not in shown_ids(page))
    check("4/9. ... it now belongs to General Rules",
          new_rule is not None and new_rule.status == "ACTIVE"
          and new_rule.start_marker in page[page.index('id="general-rules"'):])
    page = client.post("/bank/learning/discover", data={"csrf_token": csrf}, follow_redirects=True).data.decode()
    # "Zelle" may still appear in the examples of other, legitimate WHY
    # suggestions (Alice Baker -> food); what must not appear is the
    # structural Zelle pattern itself, in any form.
    zelle_rows = find("STRUCTURAL", lambda p: p["start_marker"].upper().startswith("ZELLE"))
    check("11. the approved Zelle pattern never comes back as a suggestion",
          zelle[0] not in shown_ids(page) and len(zelle_rows) == 1
          and not any(stored()[i][0] == "STRUCTURAL" for i in shown_ids(page))
          and "ZELLE PAYMENT TO</code>" not in learning_section(page).upper(),
          str([(i, stored()[i]) for i in shown_ids(page)]))

    # ------------------------------------------------------------- reject
    client.post(f"/bank/learning/suggestions/{acme[0]}/reject", data={"csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    check("5. a rejected suggestion leaves the list", acme[0] not in shown_ids(page))
    page = client.post("/bank/learning/discover", data={"csrf_token": csrf}, follow_redirects=True).data.decode()
    check("5. ... and rejection memory keeps it away on the next discovery",
          acme[0] not in shown_ids(page) and stored()[acme[0]][2] == "REJECTED")

    with SessionFactory() as s:
        t0 = s.scalars(select(m.FinancialTransaction)).first()
        for k in range(12):
            extra = m.FinancialTransaction(
                payment_instrument_id=t0.payment_instrument_id, bank_source="CHASE_BANK_ACCOUNT",
                import_batch_id=t0.import_batch_id, posting_date=date(2025, 9, 25), transaction_date=date(2025, 9, 25),
                description_original=f"ACME PAYROLL TAX X{k}9", description_normalized="x", amount_minor=-5000 - k,
                status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"acme-extra-{k}", classification="UNKNOWN")
            s.add(extra)
            s.flush()
            recognition._create_decision_row(s, extra, occurrence_id=W_ids["Acme Payroll"],
                                             transaction_reason_id=why_ids["EMPLOYER_PAYROLL_TAX"],
                                             recognition_rule_id=None, decision_source="HUMAN",
                                             decision_status="HUMAN_CONFIRMED", confidence=None,
                                             explanation_notes="more evidence")
        s.commit()
    page = client.post("/bank/learning/discover", data={"csrf_token": csrf}, follow_redirects=True).data.decode()
    check("6. materially new evidence brings a rejected suggestion back, saying so",
          acme[0] in shown_ids(page) and "Previously rejected" in learning_section(page)
          and "New patterns found: " in page)

    # ------------------------------------------------- empty state at the end
    for sid in shown_ids(page):
        client.post(f"/bank/learning/suggestions/{sid}/reject", data={"csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    section = learning_section(page)
    check("8. once everything is decided: No new classification patterns to review., no table",
          "No new classification patterns to review." in section and "<table" not in section)

    # ----------------------------------------------------------- backtest
    with SessionFactory() as s:
        run = pd.backtest(s)
        summary = json.loads(run.summary)
        s.rollback()
    check("10. the backtest engine still works as a tool (months, metrics)",
          run.kind == "BACKTEST" and summary.get("months"), str(list(summary)[:6]))
    check("10. the backtest route is not open to a normal operator",
          client.post("/bank/learning/backtest", data={"csrf_token": csrf}).status_code == 403)
    admin = web_app.app.test_client()
    a_csrf = CSRF_RE.search(admin.get("/login").data.decode()).group(1)
    admin.post("/login", data={"username": "learn_admin", "password": "LearningRules123!", "csrf_token": a_csrf})
    a_csrf = CSRF_RE.search(admin.get("/bank/classification").data.decode()).group(1)
    resp = admin.post("/bank/learning/backtest", data={"csrf_token": a_csrf})
    check("10. ... and stays available to an administrator", resp.status_code == 302, str(resp.status_code))
    check("9. even after a backtest run, the page shows no backtest",
          "backtest" not in learning_section(admin.get("/bank/classification").data.decode()).lower())

    # ----------------------------------------------- 13-15 rules unchanged
    general_after, who_after, why_after = rules_snapshot()
    check("13. General Rules: the existing ones unchanged, only the approved one added",
          [r for r in general_after if r[0] != new_rule.id] == general_before and len(general_after) == len(general_before) + 1)
    check("14. WHO Rules unchanged (nothing WHO was approved)", who_after == who_before)
    check("15. WHY Rules unchanged (nothing WHY was approved)", why_after == why_before)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
