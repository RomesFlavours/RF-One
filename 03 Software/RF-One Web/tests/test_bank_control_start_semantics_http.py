#!/usr/bin/env python
"""What the Reconciliation Control Start does NOT do.

BANK_RECONCILIATION_CONTROL_START_SEMANTICS_001.

The boundary has exactly one job: it is the earliest month from which
RF-One AUTOMATICALLY requires systematic source completeness. Everything
else about Bank evidence is deliberately outside its reach, and this suite
exists to keep it that way — the previous suite proves what the date DOES,
this one proves what it must never touch.

Three things it must never do:

  * open dozens of historical months because one old file reaches back
    into 2018;
  * hide evidence. Data before the threshold stays importable,
    reconcilable, classifiable and analysable, and an account or card
    referenced there stays discoverable even when RF-One has never heard
    of it;
  * forbid anything. A human who explicitly asks for a pre-threshold month
    gets it, under the ordinary completeness rules.

It is an RF-One OPERATIONAL CONTROL POLICY, not a fact about any real
account. It is never written into `effective_start_date`,
`effective_end_date` or `lifecycle_end_reason`, and nothing about an
instrument's life is derived from it.

Runs entirely against a DISPOSABLE SQLite database created here and deleted
at the end. The authoritative local database is never touched, no
historical transaction is imported into it, and no Excel file is opened,
read or referenced anywhere in this suite or in the feature.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_control_semantics_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "control-semantics-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


# A real Chase credit-card export carrying its own `Card` identifier. The
# ONLY thing that says which instrument each row belongs to.
def chase_card_csv(rows: list[tuple[str, str, str, str]]) -> bytes:
    head = "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    body = "".join(
        f"{card},{txn},{post},{desc},Merchandise & Inventory,Sale,-10.00,\n"
        for card, txn, post, desc in rows
    )
    return (head + body).encode("utf-8")


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

    def existing_periods():
        with SessionFactory() as db:
            return sorted(p.period_month for p in monthly_source.list_periods(db))

    def run_post_import(batch_ids):
        """The post-import step exactly as the upload route calls it."""
        with web_app.app.test_request_context():
            with SessionFactory() as db:
                months = set()
                for bid in batch_ids:
                    months |= bank_routes._months_spanned(db.get(m.BankImportBatch, bid))
                bank_routes._report_missing_accounts(db, months)

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
        operator_id = operator.id
        # One First Citizens account, registered. ··9191 deliberately is NOT.
        fc = m.PaymentInstrument(
            instrument_type="BANK_ACCOUNT", display_name="FC Checking",
            institution="FIRST_CITIZENS", last_four="7470", status="ACTIVE",
            effective_start_date=date(2018, 1, 1),
        )
        known_card = m.PaymentInstrument(
            instrument_type="CREDIT_CARD", display_name="Known Card",
            institution="CHASE", last_four="1111", status="ACTIVE",
            effective_start_date=date(2024, 1, 1),
        )
        db.add_all([fc, known_card])
        db.commit()
        fc_id, known_id = fc.id, known_card.id
        monthly_source.set_control_start(
            db, year=2026, month=1, note="RF-One takes over from January 2026",
            account_id=operator_id)
        db.commit()

    client = web_app.app.test_client()
    page = client.get("/login")
    client.post("/login", data={"username": "bank_op", "password": "OperatorPass123!",
                                "csrf_token": extract_csrf(page.data)})

    # =================================================================
    print("\n9. THE FIRST CITIZENS 94-MONTH TEST")
    # =================================================================
    # A source reaching back to 2018-12 and running to 2026-09.
    with SessionFactory() as db:
        batch = m.BankImportBatch(
            detected_format="FIRST_CITIZENS", original_file_name="AccountHistory.csv",
            raw_file_bytes=b"x", sha256="sha-fc-history", row_count=7890,
            payment_instrument_id=fc_id,
            date_range_start=date(2018, 12, 10), date_range_end=date(2026, 9, 21),
            status="RECEIVED",
        )
        db.add(batch)
        db.commit()
        fc_batch = batch.id

    spanned = None
    with SessionFactory() as db:
        spanned = bank_routes._months_spanned(db.get(m.BankImportBatch, fc_batch))
    check("9a. the file's own range spans 94 months, 2018-12 through 2026-09",
          len(spanned) == 94 and (2018, 12) in spanned and (2026, 9) in spanned,
          str(len(spanned)))

    run_post_import([fc_batch])
    created = existing_periods()
    check("9. NOT ONE of 2018-12 .. 2025-12 was created merely because the source exists",
          not any(p < "2026-01" for p in created), str(created))
    check("9b. automatic coverage starts exactly at 2026-01",
          created and min(created) == "2026-01", str(created))
    check("9c. and runs to the end of what the file covers, with no cap",
          created == [f"2026-{i:02d}" for i in range(1, 10)], str(created))
    check("9d. 85 historical months were skipped, not created and not certified",
          len(spanned) - len(created) == 85, f"{len(spanned)} - {len(created)}")
    with SessionFactory() as db:
        check("9e. the historical evidence itself is untouched and still on file",
              db.get(m.BankImportBatch, fc_batch).row_count == 7890
              and db.get(m.BankImportBatch, fc_batch).date_range_start == date(2018, 12, 10))
        check("9f. and no historical month claims to be COMPLETE",
              db.query(m.BankMonthlySourcePeriod).filter_by(status="COMPLETE").count() == 0)

    # =================================================================
    print("\n10. THE 9191 TEST — discovery is not limited by the date")
    # =================================================================
    # A genuine 2025-06 source, wholly before the threshold, carrying two
    # in-file `Card` identifiers: one registered, one RF-One has never seen.
    historical_csv = chase_card_csv([
        ("1111", "06/03/2025", "06/04/2025", "KNOWN CARD PURCHASE"),
        ("9191", "06/05/2025", "06/06/2025", "UNKNOWN CARD PURCHASE"),
        ("9191", "06/09/2025", "06/10/2025", "UNKNOWN CARD AGAIN"),
    ])
    with SessionFactory() as db:
        result = bank_service.import_csv(
            db, file_bytes=historical_csv, original_file_name="Chase_2025_06.csv",
            uploaded_by_account_id=operator_id,
        )
        db.commit()
        hist_batch_id = result.batch.id
        # The CANONICAL unresolved-instrument state, recomputed from the
        # preserved raw rows — not a field written once at import.
        review = bank_service.compute_batch_review_state(db, result.batch)
        detail = " ".join(review.reasons)
        transient = result.resolution_detail or ""
        unresolved_rows = result.unresolved_row_count
        raw_rows = db.query(m.RawBankTransaction).filter_by(
            import_batch_id=hist_batch_id).count()
        normalized = db.query(m.FinancialTransaction).filter_by(
            import_batch_id=hist_batch_id).all()

    check("10a. the pre-threshold file was imported normally — nothing was refused "
          "for being old",
          result.created and raw_rows == 3, f"created={result.created} raw={raw_rows}")
    check("10. ··9191 IS SURFACED by name in the canonical unresolved-instrument state",
          "9191" in detail and "unregistered" in detail.lower()
          and review.status == "REQUIRES_REVIEW", f"{review.status}: {detail}")
    with SessionFactory() as fresh:
        again = bank_service.compute_batch_review_state(
            fresh, fresh.get(m.BankImportBatch, hist_batch_id))
    check("10b. the state survives the request — recomputed in a new session from the "
          "preserved raw rows, it still names ··9191",
          "9191" in " ".join(again.reasons) and again.status == "REQUIRES_REVIEW",
          f"{again.status}: {' '.join(again.reasons)}")
    check("10b2. and the import result names it to the operator at upload time too",
          "9191" in transient, transient)
    check("10b3. it was NOT suppressed for predating the control start",
          "9191" in detail and review.action is not None, str(review.action))
    check("10b4. surfacing it did NOT turn it into a parsing error or an export blocker",
          result.batch.error_summary is None, str(result.batch.error_summary))
    check("10c. its rows are the unresolved ones, kept as raw evidence rather than "
          "attributed to the wrong instrument",
          unresolved_rows == 2 and len(normalized) == 1,
          f"unresolved={unresolved_rows} normalized={len(normalized)}")
    check("10d. the registered ··1111 row DID normalize — discovery did not block the "
          "rest of the file",
          len(normalized) == 1 and normalized[0].payment_instrument_id == known_id)
    with SessionFactory() as db:
        check("10e. ··9191 was NOT auto-created as a PaymentInstrument — RF-One reports, "
              "it does not invent",
              db.query(m.PaymentInstrument).filter_by(last_four="9191").count() == 0)
        check("10f. and it was NOT treated as closed",
              db.query(m.PaymentInstrument).filter(
                  m.PaymentInstrument.lifecycle_end_reason.is_not(None)).count() == 0)
        batch = db.get(m.BankImportBatch, hist_batch_id)
        check("10g. the batch itself stays unresolved, which is how the source census "
              "keeps it visible",
              batch.payment_instrument_id is None)
        check("10h. and the whole 2025-06 source is still on file, not discarded",
              batch.row_count == 3 and batch.date_range_start.year == 2025)

    # The threshold must not have moved, and no month must have appeared.
    run_post_import([hist_batch_id])
    check("10i. importing that pre-threshold source created no monthly period",
          not any(p < "2026-01" for p in existing_periods()), str(existing_periods()))
    with SessionFactory() as db:
        check("10j. and the control start itself was not touched by any of this",
              monthly_source.get_control_start_month(db) == "2026-01")

    # =================================================================
    print("\n11. EXPLICIT HISTORICAL REQUEST — a default, not a prohibition")
    # =================================================================
    page = client.get("/bank/monthly")
    resp = client.post("/bank/monthly/select", data={
        "csrf_token": extract_csrf(page.data), "year": 2025, "month": 8,
    }, follow_redirects=True)
    check("11a. the request was accepted", resp.status_code == 200)
    with SessionFactory() as db:
        aug2025 = monthly_source.get_period(db, 2025, 8)
        check("11. a pre-threshold month IS created when a human explicitly asks",
              aug2025 is not None and aug2025.period_month == "2025-08")
        rows = monthly_source.coverages(db, aug2025)
        check("11b. the ordinary coverage rules then apply to it — every instrument "
              "evaluated, nothing special-cased",
              len(rows) == 2 and all(r.expectation in m.COVERAGE_EXPECTATIONS for r in rows))
        report = monthly_source.evaluate(db, aug2025)
        check("11c. and the ordinary completeness rules apply too: it refuses to complete "
              "while accounts are unexplained",
              not report.can_complete and report.blockers, str(report.blockers))
        outcome = monthly_source.complete_period(db, period=aug2025, account_id=operator_id)
        check("11d. the completeness gate treats it exactly like any other month",
              not outcome.can_complete and aug2025.status != "COMPLETE")
        db.rollback()

    body = client.get("/bank/monthly?year=2025&month=8").data.decode()
    check("11e. the page says plainly that this month is pre-threshold and was opened "
          "on request",
          "historical month" in body and "opened on request" in body)

    # An automatic import must still not adopt it or its neighbours.
    before = existing_periods()
    run_post_import([fc_batch])
    check("11f. a later automatic import neither removes it nor opens its neighbours",
          existing_periods() == before, f"{before} -> {existing_periods()}")

    # =================================================================
    print("\n12. the policy never becomes a fact about an instrument")
    # =================================================================
    with SessionFactory() as db:
        for inst_id, name in ((fc_id, "FC Checking"), (known_id, "Known Card")):
            inst = db.get(m.PaymentInstrument, inst_id)
            check(f"12. {name}: the control start was never written into its lifecycle",
                  inst.effective_start_date != date(2026, 1, 1)
                  and inst.effective_end_date is None
                  and inst.lifecycle_end_reason is None,
                  f"{inst.effective_start_date} {inst.effective_end_date}")
        config = monthly_source.get_control_config(db)
        check("12b. the value lives in Bank operational policy, on its own row, not on "
              "any PaymentInstrument",
              config.__tablename__ == "bank_reconciliation_control_configs" and config.id == 1)
        columns = {c.name for c in m.PaymentInstrument.__table__.columns}
        check("12c. and PaymentInstrument carries no control-start column at all",
              not any("control" in c for c in columns), str(sorted(columns)))

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
