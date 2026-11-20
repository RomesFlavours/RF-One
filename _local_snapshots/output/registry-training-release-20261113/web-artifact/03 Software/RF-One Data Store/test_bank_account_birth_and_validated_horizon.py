#!/usr/bin/env python
"""Account birth + validated data horizon — BANK_ACCOUNT_BIRTH_AND_VALIDATED_HORIZON_001.

Proves, on a throwaway database:

* BIRTH = the first ELIGIBLE posting date (a confirmed or suppressed
  duplicate never dates it); no posting date → birth stays UNKNOWN;
* months before birth are NOT_EXPECTED through the existing expectation
  rule, and the birth month is expected normally;
* the LAST transaction never ends a life: an instrument that goes quiet
  stays ACTIVE with no end date until a human decides. CLOSED derives the
  end from MAX(eligible posting date); NO_ACTIVITY ("existed, stayed active,
  nothing happened") writes no end date;
* months after VALIDATED THROUGH are provisional: data kept, gaps shown but
  never enforced, never COMPLETE; advancing the horizon brings them under
  the ordinary rules without any re-import.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import monthly_source as ms
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    url = resolve_test_database_url("bank_account_birth_horizon")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            le = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
            s.add(le)
            s.flush()

            def instrument(name, last_four, status="ACTIVE"):
                inst = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name=name,
                                           institution="Chase", last_four=last_four,
                                           legal_entity_id=le.id, status=status)
                s.add(inst)
                s.flush()
                return inst

            new_card = instrument("New Card", "1111")      # born mid-period
            ghost = instrument("Ghost", "2222", status="INACTIVE")   # no transactions (Chase-2915 case)
            quiet_a = instrument("Quiet A", "3333")         # stops in March (Amex case) — human: still active
            quiet_b = instrument("Quiet B", "4444")         # stops in March — human: closed
            saver = instrument("Saver", "5555")             # data through August (RF Saving case)

            n = [0]

            def batch(inst, start, end):
                n[0] += 1
                b = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name=f"f{n[0]}.csv",
                                      raw_file_bytes=b"x", sha256=f"{n[0]:064d}", status="NORMALIZED",
                                      payment_instrument_id=inst.id, date_range_start=start, date_range_end=end)
                s.add(b)
                s.flush()
                return b

            def txn(inst, posting, **extra):
                n[0] += 1
                s.add(m.FinancialTransaction(payment_instrument_id=inst.id, posting_date=posting,
                                             transaction_date=posting, description_original="x",
                                             amount_minor=-100, status="COMPLETED", classification="UNKNOWN",
                                             fingerprint=f"fp{n[0]}:0", **extra))

            batch(new_card, date(2026, 5, 1), date(2026, 9, 10))
            txn(new_card, date(2026, 2, 1), duplicate_status="CONFIRMED_DUPLICATE")
            txn(new_card, date(2026, 3, 1), accounting_status="DUPLICATE_SUPPRESSED")
            txn(new_card, date(2026, 5, 14))
            txn(new_card, date(2026, 9, 5))
            for inst in (quiet_a, quiet_b):
                batch(inst, date(2025, 8, 1), date(2026, 3, 31))
                txn(inst, date(2025, 8, 1))
                txn(inst, date(2026, 3, 31))
            batch(saver, date(2025, 10, 1), date(2026, 8, 31))
            txn(saver, date(2025, 10, 2))
            txn(saver, date(2026, 8, 31))
            s.flush()
            # September already exists, as on the golden database (partial test files).
            sep = ms.get_or_create_period(s, 2026, 9)
            ms.refresh_coverage(s, sep)
            s.commit()
            counts = lambda: (s.scalar(select(func.count(m.FinancialTransaction.id))),  # noqa: E731
                              s.scalar(select(func.count(m.BankImportBatch.id))))
            before = counts()

            config, _prev, outcome = ms.activate_control_start(s, year=2026, month=1)
            ms.set_validated_through(s, year=2026, month=8)
            outcome = ms.apply_control_to_existing_batches(s)
            s.commit()
            for inst in (new_card, ghost, quiet_a, quiet_b, saver):
                s.refresh(inst)

            def cov(month, inst):
                period = ms.get_period(s, 2026, month)
                return next(c for c in ms.coverages(s, period) if c.payment_instrument_id == inst.id)

            def blocked(month, inst):
                return any(inst.display_name in b for b in ms.evaluate(s, ms.get_period(s, 2026, month)).blockers)

            # 1 / 2 / 3 — birth
            check("1. birth = first eligible posting date", new_card.effective_start_date == date(2026, 5, 14),
                  str(new_card.effective_start_date))
            check("2. an earlier duplicate or suppressed row does not date the birth",
                  new_card.effective_start_date != date(2026, 2, 1)
                  and new_card.effective_start_date != date(2026, 3, 1))
            check("3. no transactions → birth stays UNKNOWN", ghost.effective_start_date is None)
            # 4 / 5 — expectation around birth
            check("4. pre-birth months are NOT_EXPECTED, no blocker",
                  all(cov(mo, new_card).expectation == m.COVERAGE_NOT_EXPECTED and not blocked(mo, new_card)
                      for mo in (1, 2, 3, 4)))
            check("5. the birth month is expected normally (and received here)",
                  cov(5, new_card).expectation == m.COVERAGE_EXPECTED and cov(5, new_card).source_received)
            # 6 / 13 — the last transaction ends nothing
            check("6. an instrument that went quiet is NOT closed automatically",
                  quiet_a.status == "ACTIVE" and quiet_a.effective_end_date is None
                  and quiet_a.lifecycle_end_reason is None)
            check("13. its quiet validated months (Apr–Aug) wait for a HUMAN decision",
                  all(blocked(mo, quiet_a) for mo in (4, 5, 6, 7, 8)))
            # 15 — no transactions at all
            check("15. no transactions → no birth, no end, and a human decision per month",
                  ghost.effective_start_date is None and ghost.effective_end_date is None
                  and all(blocked(mo, ghost) for mo in range(1, 9)))
            # 9 / 10 / 14 — validated horizon
            check("9. January–August are enforced", {p.period_month for p in ms.list_periods(s)}
                  >= {f"2026-{mo:02d}" for mo in range(1, 9)})
            check("9b. September is listed as provisional, not controlled",
                  outcome.provisional_months == ["2026-09"], str(outcome.provisional_months))
            sep_report = ms.evaluate(s, sep)
            check("10. September's data is preserved and its period kept",
                  counts() == before and ms.get_period(s, 2026, 9) is not None)
            check("10b. September gaps are shown but produce no enforced blocker",
                  sep_report.provisional and sep_report.blockers == [] and len(sep_report.provisional_gaps) > 0)
            ms.complete_period(s, period=sep)
            s.commit()
            check("10c. September cannot be certified, and its status is left as it was",
                  sep.status == "OPEN")
            check("14. data ending in August concludes nothing from September",
                  saver.status == "ACTIVE" and saver.effective_end_date is None and not blocked(9, saver))

            # 8 — human STILL ACTIVE (existing NO_ACTIVITY resolution)
            ms.resolve_coverage(s, coverage=cov(4, quiet_a), resolution=m.RESOLUTION_NO_ACTIVITY,
                                note="still open, no activity")
            s.commit()
            s.refresh(quiet_a)
            check("8. STILL ACTIVE (NO_ACTIVITY) writes no end date and keeps the account ACTIVE",
                  quiet_a.status == "ACTIVE" and quiet_a.effective_end_date is None and not blocked(4, quiet_a))
            # 7 — human CLOSED
            ms.resolve_coverage(s, coverage=cov(4, quiet_b), resolution=m.RESOLUTION_CLOSED)
            s.commit()
            s.refresh(quiet_b)
            check("7. CLOSED derives the end from MAX(eligible posting date)",
                  quiet_b.status == "INACTIVE" and quiet_b.effective_end_date == date(2026, 3, 31),
                  str(quiet_b.effective_end_date))

            # idempotency
            again = ms.apply_control_to_existing_batches(s)
            s.commit()
            check("a second run derives no birth and creates no period",
                  again.births == [] and again.created == [])

            # 11 — advance the horizon (disposable DB only)
            _config, previous, advanced = ms.activate_validated_through(s, year=2026, month=9)
            s.commit()
            sep_report = ms.evaluate(s, sep)
            check("11. advancing to 2026-09 brings September under the ordinary rules, no re-import",
                  previous == "2026-08" and advanced is not None and not sep_report.provisional
                  and counts() == before)
            check("11b. its gaps are now enforced blockers", len(sep_report.blockers) > 0,
                  str(sep_report.blockers))
            _config, _previous, back = ms.activate_validated_through(s, year=2026, month=8)
            s.commit()
            check("11c. moving it back writes only the setting and deletes nothing",
                  back is None and ms.get_period(s, 2026, 9) is not None and ms.evaluate(s, sep).provisional)
    finally:
        engine.dispose()

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
