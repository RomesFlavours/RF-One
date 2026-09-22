#!/usr/bin/env python
"""Monthly Bank source completeness (BANK_MONTHLY_SOURCE_COMPLETENESS_001).

The control this pins down: for a given month, RF-One must know which
bank/card instruments were expected, which original source files arrived,
which remain unexplained, and therefore whether the month may be declared
source-complete.

The two invariants that matter most, and that this file exists to keep:

  * RF-One cannot mark a monthly Bank source period COMPLETE while an
    expected or unresolved account/card remains unexplained;
  * absence of a source file NEVER closes or deactivates a Payment
    Instrument — only an explicit human decision does.

Runs entirely against a DISPOSABLE SQLite database created here and deleted
at the end. The local QA database is never touched, and no Payment
Instrument is ever seeded into it: the real ones live in AWS, and inventing
look-alikes locally would be the opposite of useful. No XLS/XLSB/Excel file
is opened, read, or referenced anywhere in this suite or in the feature.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_monthly_source_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "monthly-source-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import parsers  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG_START, AUG_END = date(2026, 8, 1), date(2026, 8, 31)


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

    def mk(session, name, *, status="ACTIVE", start=None, end=None, reason=None,
           institution="CHASE", last_four="0001", itype="CREDIT_CARD"):
        inst = m.PaymentInstrument(
            display_name=name, instrument_type=itype, institution=institution,
            last_four=last_four, status=status, effective_start_date=start,
            effective_end_date=end, lifecycle_end_reason=reason,
        )
        session.add(inst)
        session.flush()
        return inst

    try:
        # =============================================================
        # §7 — expectation from evidence. Pure function, no database.
        # =============================================================
        E = monthly_source.evaluate_expectation
        check(
            "1. active during the month => EXPECTED",
            E(status="ACTIVE", effective_start_date=date(2026, 1, 5), effective_end_date=None,
              period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_EXPECTED,
        )
        check(
            "1b. started mid-month => EXPECTED",
            E(status="ACTIVE", effective_start_date=date(2026, 8, 20), effective_end_date=None,
              period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_EXPECTED,
        )
        check(
            "2. ended before the month began => NOT EXPECTED",
            E(status="INACTIVE", effective_start_date=date(2025, 1, 1),
              effective_end_date=date(2026, 7, 15),
              period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_NOT_EXPECTED,
        )
        check(
            "2b. not yet in existence => NOT EXPECTED",
            E(status="ACTIVE", effective_start_date=date(2026, 9, 1), effective_end_date=None,
              period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_NOT_EXPECTED,
        )
        check(
            "3. no dates at all => NEEDS HUMAN CONFIRMATION",
            E(status="ACTIVE", effective_start_date=None, effective_end_date=None,
              period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_NEEDS_CONFIRMATION,
        )
        check(
            "3b. INACTIVE today with no end date => NEEDS HUMAN CONFIRMATION "
            "(today's status does not prove when it stopped)",
            E(status="INACTIVE", effective_start_date=date(2026, 1, 1), effective_end_date=None,
              period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_NEEDS_CONFIRMATION,
        )
        check(
            "3c. the verdict always carries the sentence that justifies it",
            all(E(status=s, effective_start_date=a, effective_end_date=b,
                  period_start=AUG_START, period_end=AUG_END).basis.strip()
                for s, a, b in (("ACTIVE", None, None), ("ACTIVE", date(2026, 1, 1), None),
                                ("INACTIVE", date(2025, 1, 1), date(2026, 7, 1)))),
        )
        check(
            "3d. created_at is never used as a substitute for an unknown start date",
            "created_at" in E(status="ACTIVE", effective_start_date=None, effective_end_date=None,
                              period_start=AUG_START, period_end=AUG_END).basis,
        )
        check(
            "21. August and September go through identical generic logic",
            E(status="ACTIVE", effective_start_date=date(2026, 1, 5), effective_end_date=None,
              period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)).verdict
            == E(status="ACTIVE", effective_start_date=date(2026, 1, 5), effective_end_date=None,
                 period_start=AUG_START, period_end=AUG_END).verdict == m.COVERAGE_EXPECTED
            and monthly_source.period_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28)),
        )

        # =============================================================
        # Fixture: synthetic instruments in the DISPOSABLE database only.
        # =============================================================
        with SessionFactory() as db:
            account_service.create_account(
                db, username="src_operator", display_name="Source Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="src_operator").one()
            account_service.set_domain_access(
                db, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )
            active = mk(db, "Active Checking", start=date(2026, 1, 1),
                        itype="BANK_ACCOUNT", last_four="1111")
            gone = mk(db, "Closed Card 2025", status="INACTIVE", start=date(2024, 1, 1),
                      end=date(2026, 7, 1), reason="CLOSED", last_four="2222")
            unknown = mk(db, "Unknown History Card", last_four="3333")
            to_close = mk(db, "Card To Close", start=date(2026, 1, 1), last_four="4444")
            to_lose = mk(db, "Card To Lose", start=date(2026, 1, 1), last_four="5555")
            to_replace = mk(db, "Card To Replace", start=date(2026, 1, 1), last_four="6666")
            successor = mk(db, "Replacement Card", start=date(2026, 8, 15), last_four="7777")
            db.commit()
            ids = {k: v.id for k, v in dict(
                active=active, gone=gone, unknown=unknown, to_close=to_close,
                to_lose=to_lose, to_replace=to_replace, successor=successor,
            ).items()}

        client = web_app.app.test_client()
        resp = client.get("/login")
        client.post("/login", data={
            "username": "src_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(resp.data),
        })

        # ---- the page exists and creates a month ----------------------
        page = client.get("/bank/monthly")
        check("15. /bank/monthly returns 200", page.status_code == 200, str(page.status_code))
        csrf = extract_csrf(page.data)
        client.post("/bank/monthly/select", data={
            "year": "2026", "month": "8", "csrf_token": csrf}, follow_redirects=True)

        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            check("4. the month was created with the right bounds and status OPEN",
                  period is not None and period.period_month == "2026-08"
                  and period.period_start == AUG_START and period.period_end == AUG_END
                  and period.status == "OPEN")
            cov = {c.payment_instrument_id: c for c in monthly_source.coverages(db, period)}
            check("5. one coverage row per instrument", len(cov) == len(ids), str(len(cov)))
            check("5b. active-during-month instrument is EXPECTED",
                  cov[ids["active"]].expectation == m.COVERAGE_EXPECTED)
            check("5c. instrument closed before the month is NOT EXPECTED",
                  cov[ids["gone"]].expectation == m.COVERAGE_NOT_EXPECTED)
            check("5d. instrument with no lifecycle evidence NEEDS HUMAN CONFIRMATION",
                  cov[ids["unknown"]].expectation == m.COVERAGE_NEEDS_CONFIRMATION)
            check("5e. successor that started mid-month is EXPECTED",
                  cov[ids["successor"]].expectation == m.COVERAGE_EXPECTED)

        # ---- 11. unresolved expected instrument blocks COMPLETE -------
        page = client.get("/bank/monthly")
        csrf = extract_csrf(page.data)
        with SessionFactory() as db:
            period_id = monthly_source.get_period(db, 2026, 8).id
        client.post(f"/bank/monthly/{period_id}/complete", data={"csrf_token": csrf},
                    follow_redirects=True)
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            report = monthly_source.evaluate(db, period)
            check("11. an unresolved expected instrument blocks COMPLETE",
                  period.status == "INCOMPLETE" and not report.can_complete
                  and report.missing_unresolved > 0, str(report.blockers[:2]))
            check("11b. the blockers name the instrument, not a row id",
                  all("Active Checking" in b or "·" in b for b in report.blockers[:1]),
                  str(report.blockers[:1]))

        # ---- 4/14. absence never closes an instrument -----------------
        with SessionFactory() as db:
            inst = db.get(m.PaymentInstrument, ids["active"])
            check(
                "4/14. a month with no source file left every instrument untouched — "
                "still ACTIVE, no closure date, no reason",
                inst.status == "ACTIVE" and inst.effective_end_date is None
                and inst.lifecycle_end_reason is None,
            )

        def resolve(coverage_key, **data):
            page = client.get("/bank/monthly")
            with SessionFactory() as db:
                p = monthly_source.get_period(db, 2026, 8)
                cid = {c.payment_instrument_id: c.id
                       for c in monthly_source.coverages(db, p)}[ids[coverage_key]]
                pid = p.id
            payload = {"csrf_token": extract_csrf(page.data)}
            payload.update(data)
            return client.post(
                f"/bank/monthly/{pid}/coverage/{cid}/resolve", data=payload,
                follow_redirects=True,
            )

        # ---- 5. NO ACTIVITY resolves but keeps the instrument active --
        resolve("active", resolution="NO_ACTIVITY", note="Dormant month, account still open")
        with SessionFactory() as db:
            inst = db.get(m.PaymentInstrument, ids["active"])
            p = monthly_source.get_period(db, 2026, 8)
            c = {x.payment_instrument_id: x for x in monthly_source.coverages(db, p)}[ids["active"]]
            check("5. NO ACTIVITY resolves the month for that instrument",
                  c.resolution == m.RESOLUTION_NO_ACTIVITY and c.is_resolved)
            check("5b. NO ACTIVITY leaves the instrument ACTIVE with no closure whatsoever",
                  inst.status == "ACTIVE" and inst.effective_end_date is None
                  and inst.lifecycle_end_reason is None)

        # ---- 6/7/8. lifecycle resolutions -----------------------------
        # SUPERSEDED by BANK_MISSING_ACCOUNT_CONTROL: this call used to post
        # effective_date="2026-08-20" and assert the instrument closed on the
        # date the operator typed. The Product Owner has since decided that a
        # closure date is DERIVED from the instrument's last eligible posting
        # date and is never typed, so no date is sent here any more and the
        # assertion below checks the derived outcome instead. The rest of what
        # this case protects — that CLOSED ends the life, preserves identity,
        # and that an unknown date stays UNKNOWN — is unchanged.
        resolve("to_close", resolution="CLOSED", note="Statement says closed")
        resolve("to_lose", resolution="LOST", note="Card lost, replacement date unknown")
        resolve("to_replace", resolution="REPLACED",
                replaced_by_instrument_id=str(ids["successor"]), note="Reissued with new number")
        with SessionFactory() as db:
            closed = db.get(m.PaymentInstrument, ids["to_close"])
            lost = db.get(m.PaymentInstrument, ids["to_lose"])
            repl = db.get(m.PaymentInstrument, ids["to_replace"])
            succ = db.get(m.PaymentInstrument, ids["successor"])
            check("6. CLOSED marks the instrument inactive, dated from its own transactions "
                  "(none here, so UNKNOWN) and never from a typed date",
                  closed.status == "INACTIVE" and closed.lifecycle_end_reason == "CLOSED"
                  and closed.effective_end_date is None)
            check("6b. the closed instrument is preserved, not deleted, and still queryable",
                  db.get(m.PaymentInstrument, ids["to_close"]) is not None
                  and closed.last_four == "4444" and closed.display_name == "Card To Close")
            check("7. LOST marks it inactive and keeps the unknown date UNKNOWN",
                  lost.status == "INACTIVE" and lost.lifecycle_end_reason == "LOST"
                  and lost.effective_end_date is None)
            check("8. REPLACED preserves the old instrument's identity untouched",
                  repl.status == "INACTIVE" and repl.lifecycle_end_reason == "REPLACED"
                  and repl.last_four == "6666" and repl.display_name == "Card To Replace")
            check("8b. the replacement is a DIFFERENT instrument, linked but not merged",
                  repl.replaced_by_instrument_id == succ.id and succ.id != repl.id
                  and succ.last_four == "7777" and succ.status == "ACTIVE")

        # ---- 10. NOT EXPECTED demands an explicit reason --------------
        resp = resolve("unknown", resolution="NOT_EXPECTED_CONFIRMED")
        with SessionFactory() as db:
            p = monthly_source.get_period(db, 2026, 8)
            c = {x.payment_instrument_id: x for x in monthly_source.coverages(db, p)}[ids["unknown"]]
            check("10. NOT EXPECTED without a reason is refused — never silently inferred",
                  c.resolution is None, str(c.resolution))
        resolve("unknown", resolution="NOT_EXPECTED_CONFIRMED", note="Opened only in 2027")
        with SessionFactory() as db:
            p = monthly_source.get_period(db, 2026, 8)
            c = {x.payment_instrument_id: x for x in monthly_source.coverages(db, p)}[ids["unknown"]]
            check("10b. NOT EXPECTED with a reason is accepted and recorded",
                  c.resolution == m.RESOLUTION_NOT_EXPECTED and c.resolution_note)

        # ---- 9. SOURCE FILE MISSING blocks COMPLETE -------------------
        resolve("successor", resolution="SOURCE_FILE_MISSING", note="Issuer has not sent it yet")
        page = client.get("/bank/monthly")
        csrf = extract_csrf(page.data)
        client.post(f"/bank/monthly/{period_id}/complete", data={"csrf_token": csrf},
                    follow_redirects=True)
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            report = monthly_source.evaluate(db, period)
            check("9. SOURCE FILE MISSING keeps the month INCOMPLETE",
                  period.status == "INCOMPLETE" and not report.can_complete)
            check("9b. and it is named as the blocker",
                  any("SOURCE FILE MISSING" in b for b in report.blockers), str(report.blockers))
            succ = db.get(m.PaymentInstrument, ids["successor"])
            check("9c. SOURCE FILE MISSING changed nothing about the instrument",
                  succ.status == "ACTIVE" and succ.effective_end_date is None
                  and succ.lifecycle_end_reason is None)

        # ---- 12. everything resolved => COMPLETE allowed --------------
        resolve("successor", resolution="NO_ACTIVITY", note="Confirmed no activity after all")
        page = client.get("/bank/monthly")
        csrf = extract_csrf(page.data)
        client.post(f"/bank/monthly/{period_id}/complete", data={"csrf_token": csrf},
                    follow_redirects=True)
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            check("12. with every instrument resolved the month becomes COMPLETE",
                  period.status == "COMPLETE" and period.completed_at is not None,
                  period.status)
            check("12b. COMPLETE records who declared it and when",
                  period.completed_by_account_id is not None and period.audit_log)
            snapshot = {c.payment_instrument_id: c for c in monthly_source.coverages(db, period)}
            check("18. completing snapshots the facts the decision rested on",
                  snapshot[ids["to_close"]].instrument_status_snapshot == "INACTIVE"
                  and snapshot[ids["to_close"]].last_four_snapshot == "4444"
                  and snapshot[ids["active"]].instrument_status_snapshot == "ACTIVE")

        # ---- 20. later status change does not rewrite the closed month -
        with SessionFactory() as db:
            inst = db.get(m.PaymentInstrument, ids["active"])
            inst.status = "INACTIVE"
            inst.lifecycle_end_reason = "CLOSED"
            inst.effective_end_date = date(2026, 11, 30)
            db.commit()
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            monthly_source.refresh_coverage(db, period)
            db.commit()
            c = {x.payment_instrument_id: x for x in monthly_source.coverages(db, period)}[ids["active"]]
            check(
                "20. closing a card in November does not rewrite what August had concluded",
                period.status == "COMPLETE" and c.instrument_status_snapshot == "ACTIVE"
                and c.expectation == m.COVERAGE_EXPECTED,
                f"{c.instrument_status_snapshot} / {c.expectation}",
            )
            check("20b. a COMPLETE month refuses in-place resolution edits",
                  isinstance(_expect_error(
                      lambda: monthly_source.resolve_coverage(
                          db, coverage=c, resolution=m.RESOLUTION_NO_ACTIVITY, note="x")), ValueError))

        # ---- 17. reopening keeps the prior audit facts ----------------
        page = client.get("/bank/monthly")
        csrf = extract_csrf(page.data)
        client.post(f"/bank/monthly/{period_id}/reopen",
                    data={"reason": "New statement arrived", "csrf_token": csrf},
                    follow_redirects=True)
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            check("17. reopening sets INCOMPLETE without erasing the completion facts",
                  period.status == "INCOMPLETE" and period.completed_at is not None
                  and "COMPLETE by account" in period.audit_log
                  and "REOPENED" in period.audit_log)

        # =============================================================
        # §9/§10/§11 — file identity, exact duplicates, overlap.
        # =============================================================
        chase = (
            b"Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
            b"DEBIT,08/05/2026,SOURCE TEST ONE,-10.00,ACH_DEBIT,100.00,\n"
            b"DEBIT,08/06/2026,SOURCE TEST TWO,-20.00,ACH_DEBIT,80.00,\n"
        )
        chase_other = chase.replace(b"SOURCE TEST TWO", b"SOURCE TEST THREE")
        check("9. the fingerprint is SHA-256 over the original bytes",
              parsers.sha256_bytes(chase) == __import__("hashlib").sha256(chase).hexdigest())
        check("14. the same bytes under a different name hash identically",
              parsers.sha256_bytes(chase) == parsers.sha256_bytes(bytes(chase)))
        check("15b. different bytes hash differently",
              parsers.sha256_bytes(chase) != parsers.sha256_bytes(chase_other))

        with SessionFactory() as db:
            first = bank_service.import_csv(
                db, file_bytes=chase, original_file_name="chase_august.csv",
                uploaded_by_account_id=operator.id, payment_instrument_id=ids["active"],
            )
            db.commit()
            first_id, first_created = first.batch.id, first.created
        check("13. the first import of a file creates a batch", first_created)

        with SessionFactory() as db:
            again = bank_service.import_csv(
                db, file_bytes=chase, original_file_name="chase_august (1).csv",
                uploaded_by_account_id=operator.id, payment_instrument_id=ids["active"],
            )
            db.commit()
            check(
                "13/14. the identical file RENAMED is still an exact duplicate — the existing "
                "batch is returned and no second batch is created",
                again.created is False and again.batch.id == first_id,
            )
            check("13b. no duplicate transactions were produced",
                  db.scalar(select(__import__("sqlalchemy").func.count(m.FinancialTransaction.id))
                            .where(m.FinancialTransaction.import_batch_id == first_id)) == 2)

        with SessionFactory() as db:
            different = bank_service.import_csv(
                db, file_bytes=chase_other, original_file_name="chase_august.csv",
                uploaded_by_account_id=operator.id, payment_instrument_id=ids["active"],
            )
            db.commit()
            check(
                "15. the SAME file name with different bytes is NOT an exact duplicate — "
                "identity is content, never the name",
                different.created is True and different.batch.id != first_id,
            )
            overlapping_batch_id = different.batch.id

        with SessionFactory() as db:
            total = db.scalar(
                select(__import__("sqlalchemy").func.count(m.FinancialTransaction.id))
            )
            check(
                "18b. the overlapping reissued file did not double-count the rows it shares "
                "with the first (canonical transaction deduplication still owns that)",
                db.scalar(
                    select(__import__("sqlalchemy").func.count(m.FinancialTransaction.id))
                    .where(m.FinancialTransaction.duplicate_status == "CANDIDATE_DUPLICATE")
                ) >= 1,
                f"total={total}",
            )
            batch = db.get(m.BankImportBatch, overlapping_batch_id)
            check("11. the overlapping source file was accepted, not rejected",
                  batch is not None and batch.status != "REJECTED")

        # ---- 16/17. source -> instrument resolution -------------------
        # Deterministic: the identifier the FILE ITSELF carries matches
        # exactly one instrument, so nothing needs a human.
        with SessionFactory() as db:
            fc = mk(db, "First Citizens Operating", institution="FIRST_CITIZENS",
                    last_four="9090", itype="BANK_ACCOUNT", start=date(2026, 1, 1))
            db.commit()
            fc_id = fc.id
            decided = bank_service.resolve_instrument_for_source(
                db, detected_format=parsers.FIRST_CITIZENS, account_hint="9090",
            )
            check(
                "16. deterministic source evidence (the account identifier inside the file) "
                "resolves to exactly one instrument and auto-assigns",
                decided.instrument is not None and decided.instrument.id == fc_id
                and not decided.ambiguous,
                f"{decided.instrument} / {decided.basis}",
            )
        # Ambiguous: two equally plausible instruments and nothing in the
        # file to separate them. RF-One must refuse rather than pick one.
        with SessionFactory() as db:
            mk(db, "Second First Citizens", institution="FIRST_CITIZENS",
               last_four=None, itype="BANK_ACCOUNT", start=date(2026, 1, 1))
            mk(db, "Third First Citizens", institution="FIRST_CITIZENS",
               last_four=None, itype="BANK_ACCOUNT", start=date(2026, 1, 1))
            db.commit()
            undecided = bank_service.resolve_instrument_for_source(
                db, detected_format=parsers.FIRST_CITIZENS, account_hint=None,
                original_file_name="AccountHistory.csv",
            )
            check(
                "17. ambiguous source evidence resolves to NOTHING and requires a human — "
                "RF-One never picks among plausible instruments",
                undecided.instrument is None and undecided.ambiguous,
                f"{undecided.instrument} / {len(undecided.candidates)} candidates",
            )

        # ---- source file makes the month resolved --------------------
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            monthly_source.refresh_coverage(db, period)
            db.commit()
            c = {x.payment_instrument_id: x for x in monthly_source.coverages(db, period)}[ids["active"]]
            check("source received: the August file now covers the August month",
                  c.source_received and c.import_batch_id is not None)

        # ---- 19. closed historical instrument stays matchable ---------
        with SessionFactory() as db:
            closed = db.get(m.PaymentInstrument, ids["to_close"])
            all_instruments = monthly_source.relevant_instruments(db)
            check("19. a closed historical instrument is still returned by normal queries",
                  closed in all_instruments and closed.status == "INACTIVE")
            sept = monthly_source.get_or_create_period(db, 2026, 9)
            monthly_source.refresh_coverage(db, sept)
            db.commit()
            sc = {x.payment_instrument_id: x for x in monthly_source.coverages(db, sept)}
            # SUPERSEDED by BANK_MISSING_ACCOUNT_CONTROL. This used to assert
            # NOT EXPECTED, which held only because the operator had typed
            # 2026-08-20 as the closure date. Now that the date is DERIVED and
            # this instrument has no transactions, it closes with its end date
            # UNKNOWN — and `evaluate_expectation`, unchanged, correctly refuses
            # to conclude anything from an INACTIVE status with no end date. So
            # the instrument still appears in every later month, and still asks
            # a human. That is the honest answer, not a regression: nothing
            # proves when it stopped.
            check("19b. it appears in a later month too; with its end date UNKNOWN the "
                  "expectation rule asks a human rather than assuming it was over",
                  ids["to_close"] in sc
                  and sc[ids["to_close"]].expectation == m.COVERAGE_NEEDS_CONFIRMATION,
                  sc[ids["to_close"]].expectation if ids["to_close"] in sc else "absent")
            check("21b. September used the same generic machinery, nothing month-specific",
                  sept.period_start == date(2026, 9, 1) and sept.period_end == date(2026, 9, 30))

        # ---- 22. no spreadsheet anywhere ------------------------------
        feature_files = [
            os.path.join(_DATA_STORE_DIR, "rfone_data_store", "bank_reconciliation", "monthly_source.py"),
            os.path.join(APP_DIR, "bank_routes.py"),
            os.path.join(APP_DIR, "templates", "bank_monthly.html"),
            os.path.abspath(__file__),
        ]
        # Naming a forbidden file inside a comment that forbids it is not
        # consulting it — the check looks for actual CONSUMPTION: a
        # spreadsheet library, or code that opens/reads a workbook.
        consumption_markers = (
            "import openpyxl", "from openpyxl", "import pandas", "from pandas",
            "import xlrd", "pyxlsb", "read_excel", "load_workbook",
            'open("2026 wp control', "open('2026 wp control", "rfbank.xlsx\"", "rfbank.xlsx'",
        )
        offenders = [
            (os.path.basename(f), marker)
            for f in feature_files
            if f != os.path.abspath(__file__)
            for marker in consumption_markers
            if marker in open(f, encoding="utf-8").read().lower()
        ]
        check("22. no XLS/XLSB/Excel source is consulted anywhere in the feature "
              "(no spreadsheet library, no workbook read)",
              not offenders, str(offenders))
        check("22b. the feature does not open any file at all — it reads the database only",
              not any(
                  marker in open(os.path.join(
                      _DATA_STORE_DIR, "rfone_data_store", "bank_reconciliation",
                      "monthly_source.py"), encoding="utf-8").read()
                  for marker in ("open(", "Path(", "read_bytes", "read_text")
              ))

        # ---- CSRF on every new writing route --------------------------
        for path in (
            "/bank/monthly/select",
            f"/bank/monthly/{period_id}/complete",
            f"/bank/monthly/{period_id}/reopen",
        ):
            check(f"CSRF enforced on {path}",
                  client.post(path, data={}).status_code in (400, 403),
                  str(client.post(path, data={}).status_code))

    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for c in failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


def _expect_error(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — the type is what is being asserted
        return exc
    return None


if __name__ == "__main__":
    sys.exit(main())
