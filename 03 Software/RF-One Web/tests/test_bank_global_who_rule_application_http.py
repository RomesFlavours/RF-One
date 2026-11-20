#!/usr/bin/env python
"""Learned WHO rules applied to existing Bank transactions
(BANK_GLOBAL_WHO_RULE_APPLICATION_001).

A learned WHO rule is knowledge about the whole Bank dataset, not about the
month in which a person taught it. This file pins down:

   1. Save Rule saves the rule and changes no other existing transaction;
 2/3. Save & Apply finds matching transactions in every month — also before
      the control start — and applies after an explicit confirmation;
   4. future imports still use the saved rule;
 5-7. EXACT, PREFIX and CONTAINS mean the same on import and retroactively;
 8/9. a human WHO is never overwritten (same WHO untouched, different WHO
      reported as a conflict);
  10. a transaction with no WHO receives the learned WHO;
11-13. the WHY and the WHAT are carried over verbatim (never re-derived),
      and a transaction whose WHY is open stays in human review;
  14. a second application changes nothing;
  15. a failure rolls the whole application back;
  16. /bank Automatic WHO shows the month's counts;
  17. /bank and the rule application never use Classification.

Runs against a DISPOSABLE SQLite database created here and deleted at the
end.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_global_who_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "global-who-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"

# One checking account, many months — December 2025 is BEFORE the control
# start, so it is a historical month the monthly screens never control.
FIRST_CSV = (HEADER
    + "DEBIT,12/15/2025,GORDON FOOD SVC 7788,-101.00,ACH_DEBIT,9000.00,\n"
    + "DEBIT,03/03/2026,GFS INV 1001 PAYMENT,-102.00,ACH_DEBIT,8898.00,\n"
    + "DEBIT,04/04/2026,GORDON FOOD SVC 7788,-103.00,ACH_DEBIT,8795.00,\n"
    + "DEBIT,05/05/2026,GORDON FOOD SVC 7788,-104.00,ACH_DEBIT,8691.00,\n"
    + "DEBIT,06/10/2026,GORDON FOOD SVC 7788,-105.00,ACH_DEBIT,8586.00,\n"
    + "DEBIT,07/07/2026,GFS INV 2002 PAYMENT,-106.00,ACH_DEBIT,8480.00,\n"
    + "DEBIT,08/05/2026,GORDON FOOD SVC 7788,-107.00,ACH_DEBIT,8373.00,\n"
    + "DEBIT,08/07/2026,PAYMENT TO GORDON FOOD SVC WEB,-108.00,ACH_DEBIT,8265.00,\n"
    + "DEBIT,08/09/2026,GORDON FOOD SVC 77880,-109.00,ACH_DEBIT,8156.00,\n"
    + "DEBIT,08/11/2026,UNRELATED VENDOR 55,-110.00,ACH_DEBIT,8046.00,\n"
).encode("utf-8")
# A later import, after the rules exist.
SECOND_CSV = (HEADER
    + "DEBIT,09/02/2026,GORDON FOOD SVC 7788,-201.00,ACH_DEBIT,7000.00,\n"
    + "DEBIT,09/03/2026,GFS INV 3003 PAYMENT,-202.00,ACH_DEBIT,6798.00,\n"
    + "DEBIT,09/04/2026,PAYMENT TO GORDON FOOD SVC APP,-203.00,ACH_DEBIT,6595.00,\n"
    + "DEBIT,09/05/2026,GORDON FOOD SVC 77880,-204.00,ACH_DEBIT,6391.00,\n"
).encode("utf-8")


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f"   [{detail[:300]}]" if detail else ""))

    def txn_by(db, posting: date, description: str):
        return db.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.posting_date == posting,
            m.FinancialTransaction.description_original == description)).one()

    def current(db, txn):
        return db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None

    def decision_count(db, txn_id=None) -> int:
        q = select(func.count()).select_from(m.BankTransactionExplanation)
        if txn_id is not None:
            q = q.where(m.BankTransactionExplanation.financial_transaction_id == txn_id)
        return db.scalar(q)

    def count(html: str, key: str) -> int:
        found = re.search(rf'data-count="{key}">(\d+)<', html)
        return int(found.group(1)) if found else -1

    try:
        # ------------------------------------------------------------ fixture
        with SessionFactory() as db:
            account_service.create_account(
                db, username="who_operator", display_name="Who Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            db.commit()
            operator_id = db.query(m.RFOneAccount).filter_by(username="who_operator").one().id
            account_service.set_domain_access(
                db, account_id=operator_id, domain_code="BANK", enabled=True, role_code=None,
            )
            checking = m.PaymentInstrument(
                display_name="Chase Checking 0214", instrument_type="BANK_ACCOUNT",
                institution="CHASE", last_four="0214", status="ACTIVE",
                effective_start_date=date(2025, 1, 1),
            )
            db.add(checking)
            occ_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            db.add(occ_type)
            db.flush()
            gfs = m.BankOccurrence(canonical_name="Gordon Food Service",
                                   occurrence_type_id=occ_type.id, status="ACTIVE")
            other = m.BankOccurrence(canonical_name="Other Supplier",
                                     occurrence_type_id=occ_type.id, status="ACTIVE")
            db.add_all([gfs, other])
            db.flush()
            monthly_source.set_control_start(db, year=2026, month=1, account_id=operator_id)
            posting_whats = [w for w in db.scalars(select(m.BankAccountingClassification)).all()
                             if w.active and w.statement_type is not None and w.is_posting_account]
            reason = next(r for r in db.scalars(select(m.BankTransactionReason)).all()
                          if r.status == "ACTIVE" and r.accounting_classification is not None
                          and r.accounting_classification.is_posting_account)
            other_what = next(w for w in posting_whats if w.id != reason.accounting_classification_id)
            db.commit()
            checking_id, gfs_id, other_id = checking.id, gfs.id, other.id
            reason_id, other_what_id = reason.id, other_what.id

        client = web_app.app.test_client()
        client.post("/login", data={
            "username": "who_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(client.get("/login").data),
        })
        csrf = extract_csrf(client.get("/bank").data)
        resp = client.post("/bank/upload", data={
            "files": (io.BytesIO(FIRST_CSV), "chase_0214_history.csv"),
            "payment_instrument_id": str(checking_id), "csrf_token": csrf,
        }, content_type="multipart/form-data")
        check("fixture: the multi-month file is imported", resp.status_code == 302)

        with SessionFactory() as db:
            aug = txn_by(db, date(2026, 8, 5), "GORDON FOOD SVC 7788")
            may = txn_by(db, date(2026, 5, 5), "GORDON FOOD SVC 7788")
            apr = txn_by(db, date(2026, 4, 4), "GORDON FOOD SVC 7788")
            jun = txn_by(db, date(2026, 6, 10), "GORDON FOOD SVC 7788")
            dec = txn_by(db, date(2025, 12, 15), "GORDON FOOD SVC 7788")
            ids = dict(aug=aug.id, may=may.id, apr=apr.id, jun=jun.id, dec=dec.id)
            check("fixture: nothing has a WHO before any rule exists",
                  all(current(db, t) is None or current(db, t).occurrence_id is None
                      for t in (aug, may, apr, jun, dec)))
            # April already carries an automatic WHY (and its WHAT snapshot)
            # but no WHO — the case where WHY/WHAT must survive untouched.
            recognition._create_decision_row(
                db, apr, occurrence_id=None, transaction_reason_id=reason_id,
                recognition_rule_id=None, decision_source="RULE", decision_status="AUTO_APPLIED",
                confidence="HIGH", explanation_notes="fixture: automatic WHY without WHO",
            )
            db.commit()
            apr_before = current(db, apr)
            apr_purpose_before = {f: getattr(apr_before, f) for f in recognition._PURPOSE_SNAPSHOT_FIELDS}
            apr_before_id = apr_before.id

        # --- 9 (setup): a person decides May is ANOTHER Who, learning nothing.
        review = client.get("/bank/review?year=2026&month=5")
        csrf = extract_csrf(review.data)
        client.post(f"/bank/transactions/{ids['may']}/recognition-decision", data={
            "csrf_token": csrf, "occurrence_id": str(other_id),
        }, headers={"Referer": "/bank/review?year=2026&month=5"})

        # ----------------------------- the Review offers both approved actions
        review_html = client.get("/bank/review?year=2026&month=8").data.decode("utf-8")
        check("Review offers Save Rule",
              'id="who-picker-confirm"' in review_html and ">Save Rule<" in review_html)
        check("Review offers Save & Apply to Existing Transactions",
              'id="who-picker-apply"' in review_html and 'name="apply_existing" value="1"' in review_html
              and "Save &amp; Apply to Existing Transactions" in review_html)

        # ------------------------------------------------------ 1 Save Rule
        with SessionFactory() as db:
            decisions_before = decision_count(db)
        resp = client.post(f"/bank/transactions/{ids['aug']}/why", data={
            "csrf_token": csrf, "occurrence_id": str(gfs_id), "transaction_reason_id": str(reason_id),
            "learn_description": "on",
        }, headers={"Referer": "/bank/review?year=2026&month=8"})
        with SessionFactory() as db:
            rule = db.scalars(select(m.BankRecognitionRule).where(
                m.BankRecognitionRule.normalized_pattern == "GORDON FOOD SVC 7788")).one()
            exact_rule_id = rule.id
            check("1. Save Rule saves an ACTIVE EXACT WHO rule for the description",
                  rule.status == "ACTIVE" and rule.match_type == recognition.EXACT_NORMALIZED_DESCRIPTION
                  and rule.occurrence_id == gfs_id and rule.match_field == recognition.DESCRIPTION)
            check("1. Save Rule returns to the page it came from",
                  resp.status_code == 302 and resp.headers["Location"].endswith("/bank/review?year=2026&month=8"),
                  resp.headers.get("Location", ""))
            check("1. Save Rule changes no other existing transaction (only one new decision)",
                  decision_count(db) == decisions_before + 1)
            check("1. the other months still have no WHO",
                  all((current(db, db.get(m.FinancialTransaction, ids[k])) is None
                       or current(db, db.get(m.FinancialTransaction, ids[k])).occurrence_id is None)
                      for k in ("jun", "dec", "apr")))

        # ---------------- Save & Apply: without a learned rule, nothing to apply
        resp = client.post(f"/bank/transactions/{ids['aug']}/why", data={
            "csrf_token": csrf, "occurrence_id": str(gfs_id), "transaction_reason_id": str(reason_id),
            "apply_existing": "1",
        }, headers={"Referer": "/bank/review?year=2026&month=8"})
        check("Save & Apply with no rule learned goes back, applying nothing",
              resp.headers.get("Location", "").endswith("/bank/review?year=2026&month=8"))

        # ------------------------------ Save & Apply opens the preview only
        resp = client.post(f"/bank/transactions/{ids['aug']}/why", data={
            "csrf_token": csrf, "occurrence_id": str(gfs_id), "transaction_reason_id": str(reason_id),
            "learn_description": "on", "apply_existing": "1",
        }, headers={"Referer": "/bank/review?year=2026&month=8"})
        check("Save & Apply redirects to the preview of the learned rule",
              resp.headers.get("Location") == f"/bank/rules/{exact_rule_id}/apply",
              resp.headers.get("Location", ""))

        # ------------------------------------------------ 2/3 preview, global
        with SessionFactory() as db:
            before = decision_count(db)
        preview = client.get(f"/bank/rules/{exact_rule_id}/apply")
        html = preview.data.decode("utf-8")
        with SessionFactory() as db:
            check("preview: opening the page writes nothing", decision_count(db) == before)
        check("2. the rule matches its transactions in every month (Dec 2025 to Aug 2026)",
              count(html, "matching") == 5, str(count(html, "matching")))
        check("3. the months listed include a month before the control start",
              "2025-12 (1)" in html and "2026-06 (1)" in html and "2026-08 (1)" in html)
        check("9. the different human WHO is counted as a protected conflict",
              count(html, "human-conflicts") == 1 and "Other Supplier" in html)
        check("8. the same human WHO is counted as protected, not eligible",
              count(html, "human-same") == 1)
        check("preview says how many can be updated (Dec, Apr, Jun)",
              count(html, "eligible") == 3
              and "This rule matches <strong data-count=\"matching\">5</strong>" in html
              and "Apply to 3 existing transaction(s)" in html)

        # --------------------- 12 (setup): the Why -> What chain changes later
        with SessionFactory() as db:
            db.get(m.BankTransactionReason, reason_id).accounting_classification_id = other_what_id
            db.commit()
            human_aug_decisions = decision_count(db, ids["aug"])
            human_may_decisions = decision_count(db, ids["may"])

        # -------------------------------------------------- apply (confirm)
        csrf = extract_csrf(preview.data)
        result = client.post(f"/bank/rules/{exact_rule_id}/apply", data={"csrf_token": csrf})
        rhtml = result.data.decode("utf-8")
        check("apply: the result reports 3 updated, 0 errors",
              count(rhtml, "applied") == 3 and count(rhtml, "errors") == 0
              and count(rhtml, "matching") == 5 and count(rhtml, "unchanged") == 2, rhtml[-600:])
        with SessionFactory() as db:
            for key in ("dec", "jun", "apr"):
                decision = current(db, db.get(m.FinancialTransaction, ids[key]))
                check(f"10. {key}: the learned WHO is recorded as a RULE decision naming the rule",
                      decision.occurrence_id == gfs_id and decision.decision_source == "RULE"
                      and decision.recognition_rule_id == exact_rule_id
                      and "Retroactive application of learned WHO rule" in decision.explanation_notes)
            check("3. the historical December transaction (before the control start) got its WHO",
                  current(db, db.get(m.FinancialTransaction, ids["dec"])).occurrence_id == gfs_id)
            jun_decision = current(db, db.get(m.FinancialTransaction, ids["jun"]))
            check("11. no WHY is invented where there was none",
                  jun_decision.transaction_reason_id is None
                  and jun_decision.transaction_reason_name_snapshot is None)
            check("13. a transaction whose WHY is open stays NEEDS_HUMAN_REVIEW",
                  jun_decision.decision_status == "NEEDS_HUMAN_REVIEW"
                  and jun_decision.decision_status not in recognition.RESOLVED_DECISION_STATUSES)
            check("13. it is still counted by Review Missing",
                  ids["jun"] in {t.id for t in export_service.unresolved_transactions(db, year=2026, month=6)})
            apr_after = current(db, db.get(m.FinancialTransaction, ids["apr"]))
            check("11. an existing WHY is carried over unchanged",
                  apr_after.id != apr_before_id and apr_after.transaction_reason_id == reason_id
                  and apr_after.decision_status == "AUTO_APPLIED")
            check("12. the WHAT snapshot is carried over verbatim, not re-derived from the changed chain",
                  {f: getattr(apr_after, f) for f in recognition._PURPOSE_SNAPSHOT_FIELDS} == apr_purpose_before
                  and apr_after.accounting_classification_id != other_what_id)
            check("8. the human decision with the same WHO is untouched",
                  decision_count(db, ids["aug"]) == human_aug_decisions
                  and current(db, db.get(m.FinancialTransaction, ids["aug"])).decision_source == "HUMAN")
            check("9. the human decision with a different WHO is untouched",
                  decision_count(db, ids["may"]) == human_may_decisions
                  and current(db, db.get(m.FinancialTransaction, ids["may"])).occurrence_id == other_id)
            total_after_first = decision_count(db)

        # --------------------------------------------------- 14 idempotency
        csrf = extract_csrf(client.get(f"/bank/rules/{exact_rule_id}/apply").data)
        again = client.post(f"/bank/rules/{exact_rule_id}/apply", data={"csrf_token": csrf}).data.decode("utf-8")
        with SessionFactory() as db:
            check("14. a second application updates 0 transactions and writes nothing",
                  count(again, "applied") == 0 and decision_count(db) == total_after_first
                  and count(again, "already-this-rule") == 3)

        # ---------------------- 5/6/7 same semantics on import and retroactively
        with SessionFactory() as db:
            prefix_rule = recognition.create_or_reuse_rule(
                db, match_type=recognition.PREFIX, normalized_pattern="GFS INV",
                occurrence_id=gfs_id, transaction_reason_id=reason_id, payment_instrument_id=None,
                direction=None, auto_apply_enabled=True, created_from_transaction_id=None,
            )
            contains_rule = recognition.create_or_reuse_rule(
                db, match_type=recognition.CONTAINS_TEXT, normalized_pattern="TO GORDON FOOD",
                occurrence_id=gfs_id, transaction_reason_id=reason_id, payment_instrument_id=None,
                direction=None, auto_apply_enabled=True, created_from_transaction_id=None,
            )
            db.commit()
            prefix_id, contains_id = prefix_rule.id, contains_rule.id
            everything = db.scalars(select(m.FinancialTransaction)).all()
            for label, rule_id in (("5. EXACT", exact_rule_id), ("6. PREFIX", prefix_id),
                                   ("7. CONTAINS_TEXT", contains_id)):
                rule_obj = db.get(m.BankRecognitionRule, rule_id)
                retro = {t.id for t in recognition.transactions_matching_rule(db, rule_obj)}
                on_import = {
                    t.id for t in everything if rule_id in {r.id for r in recognition.find_candidate_rules(
                        db, normalized_description=recognition.normalize_description_for_recognition(t.description_original),
                        payment_instrument_id=t.payment_instrument_id,
                        direction=recognition.direction_for_amount(t.amount_minor),
                        normalized_memo=recognition.normalize_memo_for_recognition(t.source_memo))}
                }
                check(f"{label}: the retroactive match set equals what import would match",
                      retro == on_import and len(retro) > 0, f"{sorted(retro)} vs {sorted(on_import)}")
            near_miss = txn_by(db, date(2026, 8, 9), "GORDON FOOD SVC 77880")
            check("5. EXACT does not match a longer description, retroactively",
                  near_miss.id not in {t.id for t in recognition.transactions_matching_rule(
                      db, db.get(m.BankRecognitionRule, exact_rule_id))})

        # ------------------------------- 15 rollback of the whole application
        with SessionFactory() as db:
            before_failure = decision_count(db)
        calls = {"n": 0}
        original_create = recognition._create_decision_row

        def failing_create(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated failure on the second transaction")
            return original_create(*args, **kwargs)

        recognition._create_decision_row = failing_create
        try:
            csrf = extract_csrf(client.get(f"/bank/rules/{prefix_id}/apply").data)
            failed_html = client.post(f"/bank/rules/{prefix_id}/apply", data={"csrf_token": csrf}).data.decode("utf-8")
        finally:
            recognition._create_decision_row = original_create
        with SessionFactory() as db:
            check("15. a failure mid-way rolls the WHOLE application back (no decision written)",
                  calls["n"] == 2 and decision_count(db) == before_failure
                  and count(failed_html, "errors") == 1 and count(failed_html, "applied") == 0
                  and "Nothing was applied" in failed_html, str(calls))
            march = txn_by(db, date(2026, 3, 3), "GFS INV 1001 PAYMENT")
            check("15. the first transaction's change was undone too",
                  current(db, march) is None or current(db, march).occurrence_id is None)

        csrf = extract_csrf(client.get(f"/bank/rules/{prefix_id}/apply").data)
        ok = client.post(f"/bank/rules/{prefix_id}/apply", data={"csrf_token": csrf}).data.decode("utf-8")
        check("6. the PREFIX rule then applies to both months (March and July)",
              count(ok, "applied") == 2, str(count(ok, "applied")))
        csrf = extract_csrf(client.get(f"/bank/rules/{contains_id}/apply").data)
        ok = client.post(f"/bank/rules/{contains_id}/apply", data={"csrf_token": csrf}).data.decode("utf-8")
        check("7. the CONTAINS_TEXT rule applies to its one transaction",
              count(ok, "applied") == 1, str(count(ok, "applied")))

        # ------------------------------------------------- 4 future imports
        csrf = extract_csrf(client.get("/bank").data)
        client.post("/bank/upload", data={
            "files": (io.BytesIO(SECOND_CSV), "chase_0214_september.csv"),
            "payment_instrument_id": str(checking_id), "csrf_token": csrf,
        }, content_type="multipart/form-data")
        with SessionFactory() as db:
            for description, rule_id in (("GORDON FOOD SVC 7788", exact_rule_id),
                                         ("GFS INV 3003 PAYMENT", prefix_id),
                                         ("PAYMENT TO GORDON FOOD SVC APP", contains_id)):
                t = db.scalars(select(m.FinancialTransaction).where(
                    m.FinancialTransaction.description_original == description,
                    m.FinancialTransaction.posting_date >= date(2026, 9, 1))).one()
                d = current(db, t)
                check(f"4. a future import uses the saved rule ({description})",
                      d is not None and d.occurrence_id == gfs_id and d.recognition_rule_id == rule_id,
                      f"{d.occurrence_id if d else None} {d.recognition_rule_id if d else None}")
            t = db.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.description_original == "GORDON FOOD SVC 77880",
                m.FinancialTransaction.posting_date >= date(2026, 9, 1))).one()
            check("5. on import too, EXACT does not match the longer description",
                  current(db, t) is None or current(db, t).occurrence_id is None)

        # ------------------------------------ 16 /bank Automatic WHO counts
        def refuse(*_args, **_kwargs):
            raise AssertionError("Classification candidates must not be built")

        original_build = receiver_candidates.build_candidates
        receiver_candidates.build_candidates = refuse
        try:
            for (year, month) in ((2026, 8), (2026, 6)):
                page = client.get(f"/bank?year={year}&month={month}")
                html = page.data.decode("utf-8")
                who = html[html.index('id="step-who"'):html.index('id="step-review"')]
                shown = {k: int(v) for k, v in re.findall(r'data-who-count="(\w+)">(\d+)<', who)}
                with SessionFactory() as db:
                    expected = {"learned_rule": 0, "human": 0, "missing": 0}
                    for t in export_service.in_scope_transactions(db, year, month):
                        d = current(db, t)
                        if d is None or d.occurrence_id is None:
                            expected["missing"] += 1
                        elif d.decision_source == "HUMAN":
                            expected["human"] += 1
                        elif d.recognition_rule_id is not None:
                            expected["learned_rule"] += 1
                check(f"16. /bank {year}-{month:02d} shows the month's WHO counts",
                      page.status_code == 200 and all(shown.get(k, 0) == v for k, v in expected.items()),
                      f"shown={shown} expected={expected}")
            html_jun = client.get("/bank?year=2026&month=6").data.decode("utf-8")
            check("16. the retroactive WHO is visible in another month (June: 1 from a learned rule)",
                  re.search(r'data-who-count="learned_rule">1<', html_jun) is not None)
            check("16. /bank states the number of active learned WHO rules (3)",
                  re.search(r"data-learned-rule-count>3<", html_jun) is not None)
            # ------------------------------------------ 17 no Classification
            preview_ok = client.get(f"/bank/rules/{exact_rule_id}/apply").status_code
            csrf = extract_csrf(client.get(f"/bank/rules/{exact_rule_id}/apply").data)
            apply_ok = client.post(f"/bank/rules/{exact_rule_id}/apply", data={"csrf_token": csrf}).status_code
        finally:
            receiver_candidates.build_candidates = original_build
        check("17. /bank, the preview and the application never build Classification candidates",
              preview_ok == 200 and apply_ok == 200)
        rule_page = client.get(f"/bank/rules/{exact_rule_id}/apply").data.decode("utf-8")
        body = rule_page[rule_page.index("</nav>", rule_page.index('<nav class="module-tabs"')):]
        check("17. the rule page links nowhere into Classification",
              "/bank/classification" not in body)
        check("WHO only: the rule page shows no WHY and no WHAT",
              not re.search(r"\b(why|what)\b", re.sub(r"<[^>]+>", " ", body), re.I))

        # --------------------------------------------- refusals and safety
        with SessionFactory() as db:
            memo_rule = recognition.create_or_reuse_rule(
                db, match_type=recognition.EXACT_NORMALIZED_DESCRIPTION, normalized_pattern="TIP",
                occurrence_id=gfs_id, transaction_reason_id=reason_id, payment_instrument_id=None,
                direction=None, auto_apply_enabled=True, created_from_transaction_id=None,
                match_field=recognition.MEMO,
            )
            db.commit()
            memo_id = memo_rule.id
        check("a purpose (memo) rule is refused: this operation is WHO only",
              client.get(f"/bank/rules/{memo_id}/apply").status_code == 302)
        check("an unknown rule is refused", client.get("/bank/rules/999999/apply").status_code == 302)
        with SessionFactory() as db:
            check("GET on the preview never wrote a decision for the refused rules",
                  db.scalar(select(func.count()).select_from(m.BankTransactionExplanation).where(
                      m.BankTransactionExplanation.recognition_rule_id == memo_id)) == 0)
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f" - {description}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
