#!/usr/bin/env python
"""The Reconciliation Control Start — where history ends and control begins.

RF-One imports and keeps financial data for any period. That is not the
same claim as proving a period complete, and this boundary is what keeps
the two apart:

  * BEFORE it, a month is HISTORICAL. Importing a file that covers it opens
    nothing, demands no missing account, and certifies nothing. A
    pre-threshold month an operator deliberately created stays exactly as
    they left it.
  * FROM it onward, RF-One takes responsibility: the month is opened if it
    does not exist, reused if it does, and evaluated by the completeness
    rules that were already there.

The months an import touches come only from `BankImportBatch.date_range_start`
/`date_range_end` — never from a file name, an upload date, today, or when a
row happened to be written.

Runs entirely against a DISPOSABLE SQLite database created here and deleted
at the end. The local QA database is never touched. No Excel file is opened,
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_control_start_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "control-start-test-secret"

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

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


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

    def mk_instrument(session, name, last_four, *, start=date(2024, 1, 1)):
        inst = m.PaymentInstrument(
            instrument_type="CREDIT_CARD", display_name=name, institution="CHASE",
            last_four=last_four, status="ACTIVE", effective_start_date=start,
        )
        session.add(inst)
        session.flush()
        return inst

    counter = {"n": 0}

    def mk_batch(session, instrument_id, start, end, *, rows=1):
        """An accepted source file whose authoritative covered range is
        exactly (start, end). Nothing else says which months it touches."""
        counter["n"] += 1
        batch = m.BankImportBatch(
            detected_format="CHASE_CREDIT_CARD_WITH_CARD",
            original_file_name=f"source{counter['n']}.csv",
            raw_file_bytes=b"x", sha256=f"sha-{counter['n']}", row_count=rows,
            payment_instrument_id=instrument_id,
            date_range_start=start, date_range_end=end, status="RECEIVED",
        )
        session.add(batch)
        session.flush()
        return batch

    def months_of(batch_id):
        with SessionFactory() as db:
            return bank_routes._months_spanned(
                db.get(m.BankImportBatch, batch_id))

    def existing_periods():
        with SessionFactory() as db:
            return sorted(p.period_month for p in monthly_source.list_periods(db))

    def run_import(batch_ids):
        """The post-import step exactly as the upload route calls it."""
        with web_app.app.test_request_context():
            with SessionFactory() as db:
                months = set()
                for bid in batch_ids:
                    months |= bank_routes._months_spanned(
                        db.get(m.BankImportBatch, bid))
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
        card = mk_instrument(db, "Main Card", "1111").id
        absent = mk_instrument(db, "Absent Card", "2222").id
        db.commit()

    client = web_app.app.test_client()
    page = client.get("/login")
    client.post("/login", data={"username": "bank_op", "password": "OperatorPass123!",
                                "csrf_token": extract_csrf(page.data)})

    def set_control_start(value, note="test"):
        page = client.get("/bank/monthly")
        return client.post("/bank/monthly/control-start", data={
            "csrf_token": extract_csrf(page.data),
            "control_start_date": value, "note": note,
        }, follow_redirects=True)

    # =================================================================
    print("\n0. the setting itself")
    # =================================================================
    with SessionFactory() as db:
        check("0. unset by default — no value is inferred from today, data or files",
              monthly_source.get_control_start_month(db) is None)
    with SessionFactory() as db:
        b = mk_batch(db, card, date(2025, 6, 2), date(2025, 6, 28))
        db.commit()
        unset_batch = b.id
    run_import([unset_batch])
    check("0b. with no control start configured, an import controls NOTHING",
          existing_periods() == [], str(existing_periods()))

    resp = set_control_start("2026-01-15")
    body = resp.data.decode()
    check("0c. a MID-MONTH date is refused, not rounded, and says what was meant",
          "middle of a month" in body and "2026-01-01" in body and "2026-02-01" in body)
    with SessionFactory() as db:
        check("0d. and nothing was stored by the refusal",
              monthly_source.get_control_start_month(db) is None)

    set_control_start("2026-01-01", note="RF-One takes over from January")
    with SessionFactory() as db:
        config = monthly_source.get_control_config(db)
        check("0e. a first-of-month date is accepted and stored as YYYY-MM",
              config is not None and config.control_start_month == "2026-01")
        check("0f. the date is derived from the month, not stored twice",
              config.control_start_date == date(2026, 1, 1))
        check("0g. the operator's reason and identity are kept",
              config.note == "RF-One takes over from January"
              and config.updated_by_account_id is not None)

    # =================================================================
    print("\n1. PRE-THRESHOLD IMPORT (2025-05 .. 2025-12)")
    # =================================================================
    with SessionFactory() as db:
        b = mk_batch(db, card, date(2025, 5, 4), date(2025, 12, 30), rows=120)
        db.commit()
        pre_batch, pre_rows = b.id, b.row_count
    check("1a. the batch's own range spans all eight historical months",
          len(months_of(pre_batch)) == 8 and (2025, 5) in months_of(pre_batch)
          and (2025, 12) in months_of(pre_batch))
    run_import([pre_batch])
    check("1. no monthly period was created by a purely historical import",
          existing_periods() == [], str(existing_periods()))
    with SessionFactory() as db:
        check("1b. no coverage row, so no automatic missing-account blocker",
              db.query(m.BankMonthlyInstrumentCoverage).count() == 0)
        check("1c. the transactions/batch are kept exactly as imported — data is retained, "
              "it is simply not certified",
              db.get(m.BankImportBatch, pre_batch) is not None
              and db.get(m.BankImportBatch, pre_batch).row_count == pre_rows)
        check("1d. and nothing claims those months are COMPLETE",
              db.query(m.BankMonthlySourcePeriod).filter_by(status="COMPLETE").count() == 0)

    # =================================================================
    print("\n2. POST-THRESHOLD IMPORT (2026-01 .. 2026-04)")
    # =================================================================
    with SessionFactory() as db:
        b = mk_batch(db, card, date(2026, 1, 7), date(2026, 4, 26))
        db.commit()
        post_batch = b.id
    run_import([post_batch])
    check("2. January, February, March and April all exist",
          existing_periods() == ["2026-01", "2026-02", "2026-03", "2026-04"],
          str(existing_periods()))
    with SessionFactory() as db:
        periods = monthly_source.list_periods(db)
        check("2b. no duplicates — one row per month",
              len({p.period_month for p in periods}) == len(periods))
        jan = monthly_source.get_period(db, 2026, 1)
        rows = monthly_source.coverages(db, jan)
        check("2c. coverage was refreshed for every instrument, by the existing rules",
              len(rows) == 2 and all(r.expectation in m.COVERAGE_EXPECTATIONS for r in rows))
        report = monthly_source.evaluate(db, jan)
        check("2d. completeness was evaluated and refuses to complete",
              not report.can_complete and report.blockers)

    # =================================================================
    print("\n3. CROSS-BOUNDARY IMPORT (2025-10 .. 2026-03)")
    # =================================================================
    with SessionFactory() as db:
        b = mk_batch(db, card, date(2025, 10, 5), date(2026, 3, 20))
        db.commit()
        cross_batch = b.id
    before = existing_periods()
    run_import([cross_batch])
    after = existing_periods()
    check("3. the historical side (2025-10..12) is still uncontrolled",
          not any(p.startswith("2025") for p in after), str(after))
    check("3b. the controlled side (2026-01..03) is under control",
          {"2026-01", "2026-02", "2026-03"} <= set(after))
    check("3c. crossing the boundary created no new month beyond what already existed",
          after == before, f"{before} -> {after}")

    # =================================================================
    print("\n4/5. missing accounts, on each side of the line")
    # =================================================================
    with SessionFactory() as db:
        hist = monthly_source.get_period(db, 2025, 10)
        check("4. a historical month with an expected account and no file produces no "
              "period and therefore no automatic blocker",
              hist is None)
        jan = monthly_source.get_period(db, 2026, 1)
        report = monthly_source.evaluate(db, jan)
        check("5. in a CONTROLLED month the absent account is surfaced for resolution",
              any("Absent Card" in b for b in report.blockers), str(report.blockers))
        absent_inst = db.get(m.PaymentInstrument, absent)
        check("5b. and its absence alone closed nothing",
              absent_inst.status == "ACTIVE" and absent_inst.effective_end_date is None
              and absent_inst.lifecycle_end_reason is None)

    # =================================================================
    print("\n6. LARGE HISTORICAL FILE — no arbitrary month limit")
    # =================================================================
    with SessionFactory() as db:
        b = mk_batch(db, card, date(2024, 3, 1), date(2026, 8, 31), rows=9000)
        db.commit()
        big_batch = b.id
    spanned = months_of(big_batch)
    check("6a. the file's own range spans 30 months, 2024-03 to 2026-08",
          len(spanned) == 30 and (2024, 3) in spanned and (2026, 8) in spanned,
          str(len(spanned)))
    run_import([big_batch])
    controlled = existing_periods()
    check("6. every controlled month it covers was created — all eight of 2026-01..08, "
          "with no cap",
          controlled == [f"2026-0{i}" for i in range(1, 9)], str(controlled))
    check("6b. and not one of its 22 historical months was",
          not any(p < "2026-01" for p in controlled), str(controlled))

    # =================================================================
    print("\n7/8/9. existing periods and idempotency")
    # =================================================================
    with SessionFactory() as db:
        feb = monthly_source.get_period(db, 2026, 2)
        feb_id, feb_created = feb.id, feb.created_at
    run_import([post_batch])
    with SessionFactory() as db:
        feb2 = monthly_source.get_period(db, 2026, 2)
        check("7. an existing controlled period is REUSED, not duplicated",
              feb2.id == feb_id and feb2.created_at == feb_created)
        check("7b. coverage was refreshed in place, still one row per instrument",
              len(monthly_source.coverages(db, feb2)) == 2)

    # A pre-threshold month an operator created on purpose, and resolved.
    with SessionFactory() as db:
        hist = monthly_source.get_or_create_period(db, 2025, 11)
        monthly_source.refresh_coverage(db, hist)
        db.commit()
        cov = {c.payment_instrument_id: c
               for c in monthly_source.coverages(db, hist)}[absent]
        monthly_source.resolve_coverage(
            db, coverage=cov, resolution="NO_ACTIVITY", note="operator checked this by hand")
        db.commit()
        hist_id, hist_cov_id = hist.id, cov.id
    run_import([pre_batch, cross_batch, big_batch])
    with SessionFactory() as db:
        hist = monthly_source.get_period(db, 2025, 11)
        cov = db.get(m.BankMonthlyInstrumentCoverage, hist_cov_id)
        check("8. a pre-threshold period an operator created is PRESERVED, not deleted",
              hist is not None and hist.id == hist_id)
        check("8b. and its human resolution was not rewritten merely because the month is "
              "before the threshold",
              cov.resolution == m.RESOLUTION_NO_ACTIVITY
              and cov.resolution_note == "operator checked this by hand")
        check("8c. no sibling historical month was opened alongside it",
              [p for p in existing_periods() if p.startswith("2025")] == ["2025-11"],
              str(existing_periods()))

    before_periods = existing_periods()
    with SessionFactory() as db:
        before_cov = db.query(m.BankMonthlyInstrumentCoverage).count()
        before_batches = db.query(m.BankImportBatch).count()
    run_import([post_batch, cross_batch, big_batch])
    run_import([post_batch, cross_batch, big_batch])
    with SessionFactory() as db:
        check("9. re-running the same import creates no duplicate monthly period",
              existing_periods() == before_periods)
        check("9b. and no duplicate coverage row",
              db.query(m.BankMonthlyInstrumentCoverage).count() == before_cov)
        check("9c. import idempotency itself is untouched — no batch was added",
              db.query(m.BankImportBatch).count() == before_batches)

    # =================================================================
    print("\n10/11. control must never touch a lifecycle")
    # =================================================================
    with SessionFactory() as db:
        for key, inst_id in (("Main Card", card), ("Absent Card", absent)):
            inst = db.get(m.PaymentInstrument, inst_id)
            check(f"10. {key}: creating and evaluating controlled months closed nothing",
                  inst.status == "ACTIVE" and inst.effective_end_date is None
                  and inst.lifecycle_end_reason is None)

    # 11 — the approved forward-only behaviour, unchanged by any of this.
    with SessionFactory() as db:
        aug = monthly_source.get_or_create_period(db, 2026, 8)
        monthly_source.refresh_coverage(db, aug)
        db.commit()
        cov = {c.payment_instrument_id: c
               for c in monthly_source.coverages(db, aug)}[absent]
        monthly_source.resolve_coverage(db, coverage=cov, resolution="CLOSED", note="closed")
        db.commit()
        inst = db.get(m.PaymentInstrument, absent)
        check("11. CLOSED with no eligible posting date still leaves the date UNKNOWN",
              inst.status == "INACTIVE" and inst.lifecycle_end_reason == "CLOSED"
              and inst.effective_end_date is None)
        sept = monthly_source.get_or_create_period(db, 2026, 9)
        monthly_source.refresh_coverage(db, sept)
        july = monthly_source.get_or_create_period(db, 2026, 7)
        monthly_source.refresh_coverage(db, july)
        db.commit()
        s = {c.payment_instrument_id: c for c in monthly_source.coverages(db, sept)}[absent]
        j = {c.payment_instrument_id: c for c in monthly_source.coverages(db, july)}[absent]
        check("11b. September is NOT_EXPECTED by the human's August decision",
              s.expectation == m.COVERAGE_NOT_EXPECTED, s.expectation)
        check("11c. July is untouched — history is still history",
              j.expectation != m.COVERAGE_NOT_EXPECTED, j.expectation)

    # =================================================================
    print("\n12. moving the boundary destroys nothing")
    # =================================================================
    set_control_start("2026-06-01", note="moved forward")
    with SessionFactory() as db:
        check("12. the value moved",
              monthly_source.get_control_start_month(db) == "2026-06")
        check("12b. every already-controlled month still exists, untouched",
              {"2026-01", "2026-02", "2026-03", "2026-04"} <= set(existing_periods()),
              str(existing_periods()))
        cov = db.get(m.BankMonthlyInstrumentCoverage, hist_cov_id)
        check("12c. and the historical operator resolution is still there",
              cov.resolution == m.RESOLUTION_NO_ACTIVITY)
    set_control_start("2025-01-01", note="moved backward")
    check("12d0. moving it BACKWARD applies it to the files ALREADY imported — the newly "
          "controlled months exist before any file is uploaded again",
          {"2025-05", "2025-12"} <= set(existing_periods()), str(existing_periods()))
    run_import([pre_batch])
    check("12d. moving it BACKWARD simply lets the same machinery control more months",
          {"2025-05", "2025-12"} <= set(existing_periods()), str(existing_periods()))
    with SessionFactory() as db:
        cov = db.get(m.BankMonthlyInstrumentCoverage, hist_cov_id)
        check("12e. still without disturbing what the operator had already decided",
              cov.resolution == m.RESOLUTION_NO_ACTIVITY)

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
