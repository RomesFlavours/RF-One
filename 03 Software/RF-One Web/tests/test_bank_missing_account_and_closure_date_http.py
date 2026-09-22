#!/usr/bin/env python
"""Missing-account control and the DERIVED account closure date.

Two behaviours, one workflow:

  * an expected financial account that the imported data does not
    represent must become visible and demand a human decision — the
    file/data is still missing, or the account is closed;
  * when the human chooses to close it, RF-One dates the closure itself,
    from `MAX(FinancialTransaction.posting_date)` over that instrument's
    eligible transactions. The operator never types it.

The invariant both rest on, unchanged: absence of a source file NEVER
closes, deactivates or dates an instrument. Only a named human decision
does, and even then the DATE is evidence, not opinion.

Eligibility, as decided by the Product Owner: every transaction of the
instrument EXCEPT a known duplicate copy — `duplicate_status =
CONFIRMED_DUPLICATE` or `accounting_status = DUPLICATE_SUPPRESSED`. NULL
stays eligible on both columns, `UNRESOLVED_NO_SETTLEMENT_ACCOUNT` stays
eligible, and `FinancialTransaction.status` is not consulted at all.

Runs entirely against a DISPOSABLE SQLite database created here and deleted
at the end. The local QA database is never touched. No Excel file is opened,
read or referenced anywhere in this suite or in the feature.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_missing_account_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "missing-account-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import accounting_dedup  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = (2026, 8)


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

    def mk_instrument(session, name, last_four, *, status="ACTIVE", start=date(2026, 1, 1)):
        inst = m.PaymentInstrument(
            instrument_type="CREDIT_CARD", display_name=name, institution="CHASE",
            last_four=last_four, status=status, effective_start_date=start,
        )
        session.add(inst)
        session.flush()
        return inst

    def mk_txn(session, instrument_id, posting_date, *, amount=-1000,
               duplicate_status=None, accounting_status=None, status="COMPLETED"):
        txn = m.FinancialTransaction(
            payment_instrument_id=instrument_id, posting_date=posting_date,
            amount_minor=amount, status=status, classification="UNKNOWN",
            duplicate_status=duplicate_status, accounting_status=accounting_status,
            description_original="test row",
        )
        session.add(txn)
        session.flush()
        return txn

    # ---- world -------------------------------------------------------
    with SessionFactory() as db:
        account_service.create_account(
            db, username="bank_op", display_name="Bank Operator",
            password="OperatorPass123!", status="ACTIVE", is_admin=True)
        db.commit()
        operator = db.query(m.RFOneAccount).filter_by(username="bank_op").one()
        account_service.set_domain_access(
            db, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        db.commit()

        ids = {}
        # 'covered' gets a source file for August; every other instrument does not.
        for key, name, four in (
            ("covered", "Covered Card", "1111"),
            ("plain", "Plain Card", "2222"),
            ("dupes", "Dupes Card", "3333"),
            ("suppressed", "Suppressed Card", "4444"),
            ("unresolved", "Unresolved Card", "5555"),
            ("reversed", "Reversed Card", "6666"),
            ("empty", "Empty Card", "7777"),
            ("nulldates", "Null Dates Card", "8888"),
            ("missing_file", "Missing File Card", "9999"),
            ("override", "Override Card", "1212"),
        ):
            ids[key] = mk_instrument(db, name, four).id

        # --- eligible: plain rows, latest 2026-07-20 ------------------
        mk_txn(db, ids["plain"], date(2026, 7, 10))
        mk_txn(db, ids["plain"], date(2026, 7, 20))

        # --- 5. the LATEST row is a CONFIRMED_DUPLICATE ---------------
        mk_txn(db, ids["dupes"], date(2026, 6, 15))
        mk_txn(db, ids["dupes"], date(2026, 9, 30), duplicate_status="CONFIRMED_DUPLICATE")

        # --- 6. the LATEST row is DUPLICATE_SUPPRESSED ----------------
        mk_txn(db, ids["suppressed"], date(2026, 6, 16))
        mk_txn(db, ids["suppressed"], date(2026, 9, 30),
               accounting_status=accounting_dedup.DUPLICATE_SUPPRESSED)

        # --- 7. the LATEST row is UNRESOLVED_NO_SETTLEMENT_ACCOUNT ----
        mk_txn(db, ids["unresolved"], date(2026, 6, 17))
        mk_txn(db, ids["unresolved"], date(2026, 9, 29),
               accounting_status=accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT)

        # --- 8. the LATEST rows are REVERSED / FAILED -----------------
        mk_txn(db, ids["reversed"], date(2026, 6, 18))
        mk_txn(db, ids["reversed"], date(2026, 9, 28), status="REVERSED")
        mk_txn(db, ids["reversed"], date(2026, 9, 27), status="FAILED")

        # --- 10. rows exist but every posting_date is NULL ------------
        mk_txn(db, ids["nulldates"], None)
        mk_txn(db, ids["nulldates"], None, status="PENDING")

        # --- 4e. one eligible row, so a crafted date has something to lose to
        mk_txn(db, ids["override"], date(2026, 5, 5))

        # 'empty' deliberately gets nothing at all (9).
        db.commit()

        period = monthly_source.get_or_create_period(db, *AUG)
        # One accepted source file, covering August, for 'covered' only.
        batch = m.BankImportBatch(
            detected_format="CHASE_CREDIT_CARD_WITH_CARD", original_file_name="covered.csv",
            raw_file_bytes=b"x", sha256="sha-covered", row_count=1,
            payment_instrument_id=ids["covered"],
            date_range_start=date(2026, 8, 3), date_range_end=date(2026, 8, 28),
            status="RECEIVED",
        )
        db.add(batch)
        db.commit()
        monthly_source.refresh_coverage(db, period)
        db.commit()
        period_id = period.id

    client = web_app.app.test_client()
    page = client.get("/login")
    client.post("/login", data={"username": "bank_op", "password": "OperatorPass123!",
                                "csrf_token": extract_csrf(page.data)})

    def coverage_id_for(instrument_id):
        with SessionFactory() as db:
            period = monthly_source.get_period(db, *AUG)
            return {c.payment_instrument_id: c.id
                    for c in monthly_source.coverages(db, period)}[instrument_id]

    def resolve(instrument_key, **data):
        cid = coverage_id_for(ids[instrument_key])
        page = client.get("/bank/monthly")
        payload = {"csrf_token": extract_csrf(page.data)}
        payload.update(data)
        return client.post(f"/bank/monthly/{period_id}/coverage/{cid}/resolve",
                           data=payload, follow_redirects=True)

    def instrument(key):
        with SessionFactory() as db:
            return db.get(m.PaymentInstrument, ids[key])

    def coverage(key):
        with SessionFactory() as db:
            period = monthly_source.get_period(db, *AUG)
            return {c.payment_instrument_id: c
                    for c in monthly_source.coverages(db, period)}[ids[key]]

    # =================================================================
    print("\n1. Expected account PRESENT -> no resolution required")
    # =================================================================
    cov = coverage("covered")
    check("1. the instrument its source file covers is marked received",
          cov.source_received and cov.import_batch_id is not None)
    check("1b. it needs no resolution and is not a blocker",
          cov.resolution is None)
    with SessionFactory() as db:
        report = monthly_source.evaluate(db, monthly_source.get_period(db, *AUG))
    covered_blockers = [b for b in report.blockers if "Covered Card" in b]
    check("1c. it appears in no blocker", not covered_blockers, str(covered_blockers))

    # =================================================================
    print("\n2. Expected account ABSENT -> the existing requirement surfaces")
    # =================================================================
    check("2. every instrument with no source file is named as a blocker",
          all(any(name in b for b in report.blockers)
              for name in ("Plain Card", "Dupes Card", "Empty Card", "Missing File Card")),
          str(report.blockers))
    check("2b. the month cannot be completed while they are unexplained",
          not report.can_complete and report.missing_unresolved >= 8)
    monthly_page = client.get("/bank/monthly").data.decode()
    check("2c. the operator is offered exactly the two decisions",
          'value="SOURCE_FILE_MISSING"' in monthly_page and 'value="CLOSED"' in monthly_page)

    # =================================================================
    print("\n3. 'Missing file/data' keeps the instrument alive")
    # =================================================================
    resolve("missing_file", resolution="SOURCE_FILE_MISSING", note="Bank portal was down")
    inst = instrument("missing_file")
    check("3. instrument stays ACTIVE", inst.status == "ACTIVE")
    check("3b. no lifecycle end date and no end reason",
          inst.effective_end_date is None and inst.lifecycle_end_reason is None)
    cov = coverage("missing_file")
    check("3c. the coverage is recorded but deliberately NOT resolved",
          cov.resolution == m.RESOLUTION_SOURCE_FILE_MISSING and not cov.is_resolved)
    with SessionFactory() as db:
        report = monthly_source.evaluate(db, monthly_source.get_period(db, *AUG))
    check("3d. it still blocks completeness, as designed",
          any("Missing File Card" in b and "still owed" in b for b in report.blockers),
          str(report.blockers))

    # =================================================================
    print("\n4. 'Close account' derives the date; none is asked for")
    # =================================================================
    check("4a. the form no longer offers a date input at all",
          'name="effective_date"' not in monthly_page)
    resolve("plain", resolution="CLOSED", note="Statement confirms closure")
    inst = instrument("plain")
    check("4. CLOSED ends the life through the existing mechanism",
          inst.status == "INACTIVE" and inst.lifecycle_end_reason == "CLOSED")
    check("4b. effective_end_date = MAX(eligible posting_date) = 2026-07-20",
          inst.effective_end_date == date(2026, 7, 20), str(inst.effective_end_date))
    check("4c. the coverage row records the same derived date, so the two agree",
          coverage("plain").resolution_effective_date == date(2026, 7, 20))
    check("4d. identity is untouched",
          inst.last_four == "2222" and inst.display_name == "Plain Card")

    # No second manual override, at either level. Over HTTP the route does
    # not read a date at all, so a crafted request carrying one changes
    # nothing; in the service a supplied date is refused outright rather
    # than silently dropped.
    resolve("override", resolution="CLOSED", note="crafted request carrying a date",
            effective_date="2026-01-01")
    inst = instrument("override")
    check("4e. a crafted POST carrying effective_date is ignored — the DERIVED date wins",
          inst.effective_end_date == date(2026, 5, 5), str(inst.effective_end_date))
    with SessionFactory() as db:
        period = monthly_source.get_period(db, *AUG)
        cov = {c.payment_instrument_id: c for c in monthly_source.coverages(db, period)}[ids["empty"]]
        try:
            monthly_source.resolve_coverage(
                db, coverage=cov, resolution="CLOSED", note="x", effective_date=date(2026, 1, 1))
            refused = False
        except ValueError:
            db.rollback()
            refused = True
    check("4f. the service itself refuses a supplied closure date", refused)
    check("4g. the refused call changed nothing — the instrument is still ACTIVE",
          instrument("empty").status == "ACTIVE")

    # =================================================================
    print("\n5/6/7/8. which transactions may date a closure")
    # =================================================================
    resolve("dupes", resolution="CLOSED", note="closed")
    check("5. a CONFIRMED_DUPLICATE row (2026-09-30) does NOT date the closure; "
          "the eligible 2026-06-15 does",
          instrument("dupes").effective_end_date == date(2026, 6, 15),
          str(instrument("dupes").effective_end_date))

    resolve("suppressed", resolution="CLOSED", note="closed")
    check("6. a DUPLICATE_SUPPRESSED row (2026-09-30) does NOT date the closure; "
          "the eligible 2026-06-16 does",
          instrument("suppressed").effective_end_date == date(2026, 6, 16),
          str(instrument("suppressed").effective_end_date))

    resolve("unresolved", resolution="CLOSED", note="closed")
    check("7. an UNRESOLVED_NO_SETTLEMENT_ACCOUNT row DOES date the closure — incomplete "
          "settlement configuration must not make an account look closed earlier",
          instrument("unresolved").effective_end_date == date(2026, 9, 29),
          str(instrument("unresolved").effective_end_date))

    resolve("reversed", resolution="CLOSED", note="closed")
    check("8. a REVERSED row still dates the closure — status is not a lifecycle filter",
          instrument("reversed").effective_end_date == date(2026, 9, 28),
          str(instrument("reversed").effective_end_date))

    # =================================================================
    print("\n9/10. nothing to derive from -> UNKNOWN, and the closure still happens")
    # =================================================================
    resolve("empty", resolution="CLOSED", note="closed with no history")
    inst = instrument("empty")
    check("9. an instrument with no transactions still closes",
          inst.status == "INACTIVE" and inst.lifecycle_end_reason == "CLOSED")
    check("9b. its effective_end_date is NULL = UNKNOWN, not today and not invented",
          inst.effective_end_date is None)
    check("9c. it says so in words rather than showing a made-up date",
          "UNKNOWN" in inst.lifecycle_label, inst.lifecycle_label)

    resolve("nulldates", resolution="CLOSED", note="closed, source carries no posting date")
    inst = instrument("nulldates")
    check("10. an instrument whose posting dates are all NULL still closes",
          inst.status == "INACTIVE" and inst.lifecycle_end_reason == "CLOSED")
    check("10b. no fallback to transaction_date / transaction_datetime / created_at",
          inst.effective_end_date is None)

    # =================================================================
    print("\n11/12/13. nothing else moved")
    # =================================================================
    with SessionFactory() as db:
        period = monthly_source.get_period(db, *AUG)
        report = monthly_source.evaluate(db, period)
        check("11. monthly completeness still evaluates and still refuses to complete",
              report.expected >= 1 and not report.can_complete)
        outcome = monthly_source.complete_period(db, period=period, account_id=None)
        check("11b. the completeness gate still has no override: it refuses and says why",
              not outcome.can_complete and outcome.blockers
              and period.status != "COMPLETE", period.status)

        untouched = db.get(m.PaymentInstrument, ids["covered"])
        check("12. an instrument nobody resolved was never touched by any of this",
              untouched.status == "ACTIVE" and untouched.effective_end_date is None
              and untouched.lifecycle_end_reason is None)

        rows = db.query(m.FinancialTransaction).all()
        check("13. no transaction's amount, dates, duplicate or accounting state changed",
              len(rows) == 14
              and sum(1 for r in rows if r.duplicate_status == "CONFIRMED_DUPLICATE") == 1
              and sum(1 for r in rows
                      if r.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED) == 1
              and sum(1 for r in rows
                      if r.accounting_status
                      == accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT) == 1
              and all(r.amount_minor == -1000 for r in rows),
              f"{len(rows)} rows")
        check("13b. accounting visibility rules are untouched and still stricter than "
              "lifecycle eligibility",
              accounting_dedup.ACCOUNTING_VISIBLE_STATUSES == (accounting_dedup.CANONICAL,))

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILURES:")
        for f in failed:
            print("   -", f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    code = main()
    try:
        from db import engine
        engine.dispose()
    except Exception:
        pass
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = _TEST_DB_PATH + suffix
        if os.path.exists(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass
    sys.exit(code)
