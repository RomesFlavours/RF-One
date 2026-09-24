#!/usr/bin/env python
"""Activating the Reconciliation Control Start over history already imported
— BANK_ACTIVATE_CONTROL_START_001.

Proves, on a throwaway database, that setting the control start for the
first time (or moving it earlier) applies the boundary to the source files
RF-One already holds, through the EXISTING monthly machinery:

* only months on or after the start, derived only from each batch's own
  `date_range_start` / `date_range_end`, are opened or reused, refreshed and
  evaluated; a REJECTED batch proves nothing;
* nothing is re-imported: batch, transaction and raw counts are unchanged;
* historical months get no automatic period, and an operator's historical
  period is not touched;
* a missing expected account becomes a blocker and its instrument stays
  ACTIVE — nothing is resolved, closed or declared COMPLETE;
* moving the start later rewrites nothing; running the backfill twice
  creates nothing.

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
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
            print(f"  PASS  {description}")
        else:
            checks_failed.append(description)
            print(f"  FAIL  {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("bank_control_start_activation")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            le = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
            s.add(le)
            s.flush()
            checking = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Checking",
                                           institution="Chase", last_four="3376", legal_entity_id=le.id,
                                           status="ACTIVE")
            absent = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Absent",
                                         institution="Chase", last_four="9999", legal_entity_id=le.id,
                                         status="ACTIVE")
            s.add_all([checking, absent])
            s.flush()

            def batch(n, start, end, status="NORMALIZED"):
                b = m.BankImportBatch(
                    detected_format="CHASE_BANK_ACCOUNT", original_file_name=f"f{n}.csv",
                    raw_file_bytes=b"x", sha256=f"{n:064d}", status=status,
                    payment_instrument_id=checking.id, date_range_start=start, date_range_end=end,
                )
                s.add(b)
                return b

            batch(1, date(2023, 1, 5), date(2025, 11, 30))    # large multi-year, historical
            batch(2, date(2025, 11, 1), date(2026, 2, 28))    # crosses the start
            batch(3, date(2026, 3, 1), date(2026, 4, 15))     # entirely controlled
            batch(4, date(2026, 5, 1), date(2026, 6, 30), status="REJECTED")
            s.add(m.FinancialTransaction(
                payment_instrument_id=checking.id, posting_date=date(2026, 1, 3),
                description_original="x", amount_minor=-100, status="COMPLETED",
                classification="UNKNOWN", fingerprint="fp:0",
            ))
            s.flush()

            # An operator's historical month, and a controlled month opened in
            # advance with a human decision on it.
            hist = ms.get_or_create_period(s, 2025, 6)
            ms.refresh_coverage(s, hist)
            for cov in ms.coverages(s, hist):
                cov.expectation_basis = "OPERATOR MARKER"
            feb = ms.get_or_create_period(s, 2026, 2)
            ms.refresh_coverage(s, feb)
            feb_absent = next(c for c in ms.coverages(s, feb) if c.payment_instrument_id == absent.id)
            ms.resolve_coverage(s, coverage=feb_absent, resolution=m.RESOLUTION_NO_ACTIVITY,
                                note="operator: no activity in February")
            s.commit()

            def counts():
                return (s.scalar(select(func.count(m.BankImportBatch.id))),
                        s.scalar(select(func.count(m.FinancialTransaction.id))),
                        s.scalar(select(func.count(m.RawBankTransaction.id))))

            def snapshot():
                periods = {p.period_month: (p.id, p.status) for p in ms.list_periods(s)}
                covs = sorted((c.period_id, c.payment_instrument_id, c.expectation, c.expectation_basis,
                               c.import_batch_id, c.resolution, c.resolution_note)
                              for c in s.scalars(select(m.BankMonthlyInstrumentCoverage)))
                return periods, covs

            before_counts = counts()
            feb_id = feb.id

            # 1 — control start set
            config, previous, outcome = ms.activate_control_start(
                s, year=2026, month=1, note="RF-One takes over from January")
            s.commit()
            check("1. one authoritative configuration row",
                  s.scalar(select(func.count(m.BankReconciliationControlConfig.id))) == 1)
            check("1b. January 2026 is the first controlled month",
                  ms.get_control_start_month(s) == "2026-01" and config.control_start_date == date(2026, 1, 1)
                  and previous is None)

            # 2 — existing batches examined, months derived from their ranges
            check("2. every non-rejected dated batch was examined", outcome.batches_examined == 3,
                  str(outcome.batches_examined))
            controlled = {c.period.period_month for c in outcome.months}
            check("2b. exactly the controlled months the batches cover: 2026-01..04",
                  controlled == {"2026-01", "2026-02", "2026-03", "2026-04"}, str(controlled))
            check("2c. the rejected batch's months were not opened",
                  ms.get_period(s, 2026, 5) is None and ms.get_period(s, 2026, 6) is None)
            check("2d. coverage exists for every instrument in every controlled month",
                  all(len(ms.coverages(s, c.period)) == 2 for c in outcome.months))
            check("2e. completeness was evaluated for each",
                  all(c.report is not None for c in outcome.months))

            # 3 — no reimport
            check("3. batch, transaction and raw counts are unchanged", counts() == before_counts,
                  f"{before_counts} -> {counts()}")

            # 4 — pre-threshold history
            check("4. no historical month was opened automatically",
                  {p.period_month for p in ms.list_periods(s)}
                  == {"2025-06", "2026-01", "2026-02", "2026-03", "2026-04"},
                  str([p.period_month for p in ms.list_periods(s)]))
            check("4b. the historical months were only listed",
                  outcome.historical_months[0] == "2023-01" and outcome.historical_months[-1] == "2025-12")
            check("4c. the operator's historical month was not refreshed or rewritten",
                  all(c.expectation_basis == "OPERATOR MARKER" for c in ms.coverages(s, hist)))

            # 5 — missing account
            jan = next(c for c in outcome.months if c.period.period_month == "2026-01")
            check("5. the absent account is a blocker in a controlled month",
                  any("Absent" in b for b in jan.report.blockers), str(jan.report.blockers))
            s.refresh(absent)
            check("5b. and stays ACTIVE with no lifecycle end — no decision was taken for the operator",
                  absent.status == "ACTIVE" and absent.lifecycle_end_reason is None
                  and absent.effective_end_date is None)
            check("5c. no month was declared COMPLETE",
                  all(p.status != "COMPLETE" for p in ms.list_periods(s)))

            # 6 — existing month reused
            check("6. the existing February period was reused, not duplicated",
                  "2026-02" in outcome.reused and ms.get_period(s, 2026, 2).id == feb_id
                  and s.scalar(select(func.count(m.BankMonthlySourcePeriod.id))
                               .where(m.BankMonthlySourcePeriod.period_month == "2026-02")) == 1)
            check("6b. its coverage was not duplicated", len(ms.coverages(s, feb)) == 2)
            feb_absent = next(c for c in ms.coverages(s, feb) if c.payment_instrument_id == absent.id)
            check("6c. and the human resolution is still authoritative",
                  feb_absent.resolution == m.RESOLUTION_NO_ACTIVITY)

            # 9 — idempotency
            snap = snapshot()
            again = ms.apply_control_to_existing_batches(s)
            s.commit()
            check("9. a second run creates no period", again.created == [], str(again.created))
            check("9b. and changes no coverage", snapshot() == snap)
            check("9c. financial counts still unchanged", counts() == before_counts)

            # 8 — move forward
            snap = snapshot()
            _config, previous, outcome = ms.activate_control_start(s, year=2026, month=3, note="later")
            s.commit()
            check("8. moving it FORWARD applies nothing", outcome is None and previous == "2026-01")
            check("8b. no period, coverage or resolution was deleted or rewritten", snapshot() == snap)

            # 7 — move backward
            _config, previous, outcome = ms.activate_control_start(s, year=2025, month=10, note="earlier")
            s.commit()
            check("7. moving it BACKWARD opens the newly controlled months from existing batches",
                  set(outcome.created) == {"2025-10", "2025-11", "2025-12"}, str(outcome.created))
            check("7b. months already controlled were reused",
                  {"2026-01", "2026-02", "2026-03", "2026-04"} <= set(outcome.reused))
            check("7c. still no reimport", counts() == before_counts)
            check("7d. the operator's 2025-06 month is still historical and untouched",
                  all(c.expectation_basis == "OPERATOR MARKER" for c in ms.coverages(s, hist)))
            feb_absent = next(c for c in ms.coverages(s, feb) if c.payment_instrument_id == absent.id)
            check("7e. the February human resolution survived every move",
                  feb_absent.resolution == m.RESOLUTION_NO_ACTIVITY)

            # no start configured -> nothing controlled
            s.delete(s.get(m.BankReconciliationControlConfig, 1))
            s.flush()
            check("0. with no control start, the backfill controls nothing",
                  ms.apply_control_to_existing_batches(s).months == [])
            s.rollback()
    finally:
        engine.dispose()

    print(f"\n{len(checks_passed)} passed, {len(checks_failed)} failed.")
    return 1 if checks_failed else 0


if __name__ == "__main__":
    sys.exit(main())
