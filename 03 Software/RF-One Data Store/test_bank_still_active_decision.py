#!/usr/bin/env python
"""Explicit human STILL ACTIVE decision — BANK_EXPLICIT_STILL_ACTIVE_DECISION_001.

Proves, on a throwaway database:

* STILL_ACTIVE on an INACTIVE instrument with no recorded end resolves the
  month and makes the instrument ACTIVE — and writes no date of any kind;
* it is refused for an instrument that is already ACTIVE (NO_ACTIVITY is the
  unchanged answer there), for one with an end date or lifecycle reason, and
  for one with a lifecycle-ending resolution in any month;
* it resolves only the selected month;
* CLOSED is unchanged: end date = MAX(eligible posting date), or UNKNOWN;
* both human answers are possible for a Chase-2915-like instrument.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

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

    def refused(fn, fragment: str) -> bool:
        try:
            fn()
        except ValueError as exc:
            return fragment.lower() in str(exc).lower()
        return False

    url = resolve_test_database_url("bank_still_active_decision")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            le = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
            s.add(le)
            s.flush()

            def instrument(name, status="INACTIVE", **extra):
                inst = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name=name,
                                           institution="Chase", legal_entity_id=le.id, status=status, **extra)
                s.add(inst)
                s.flush()
                return inst

            ambiguous = instrument("Ambiguous", effective_start_date=date(2025, 3, 1))
            ghost_a = instrument("Ghost A")          # Chase-2915 analogue → STILL ACTIVE
            ghost_b = instrument("Ghost B")          # Chase-2915 analogue → CLOSED
            active = instrument("Active", status="ACTIVE")
            dated_end = instrument("Dated End", effective_end_date=date(2025, 12, 31))
            reasoned = instrument("Reasoned", lifecycle_end_reason="LOST")
            prior_closed = instrument("Prior Closed")
            with_tx = instrument("With Tx", status="ACTIVE")
            s.add(m.FinancialTransaction(payment_instrument_id=with_tx.id, posting_date=date(2026, 2, 14),
                                         description_original="x", amount_minor=-100, status="COMPLETED",
                                         classification="UNKNOWN", fingerprint="t:0"))
            s.flush()

            periods = {}
            for month in (3, 4, 5):
                periods[month] = ms.get_or_create_period(s, 2026, month)
                ms.refresh_coverage(s, periods[month])
            s.commit()

            def cov(month, inst):
                return next(c for c in ms.coverages(s, periods[month]) if c.payment_instrument_id == inst.id)

            def blocked(month, inst):
                return any(inst.display_name in b for b in ms.evaluate(s, periods[month]).blockers)

            # A lifecycle-ending resolution recorded in an EARLIER month, but with
            # the instrument's own fields cleared — the resolution alone must refuse.
            ms.resolve_coverage(s, coverage=cov(3, prior_closed), resolution=m.RESOLUTION_CLOSED)
            prior_closed.status, prior_closed.lifecycle_end_reason, prior_closed.effective_end_date = (
                "INACTIVE", None, None)
            s.commit()

            # 1 — ambiguous INACTIVE instrument
            ms.resolve_coverage(s, coverage=cov(4, ambiguous), resolution=m.RESOLUTION_STILL_ACTIVE,
                                note="confirmed open by the owner")
            s.commit()
            s.refresh(ambiguous)
            check("1. STILL ACTIVE resolves the month", cov(4, ambiguous).is_resolved and not blocked(4, ambiguous))
            check("1b. the instrument becomes ACTIVE", ambiguous.status == "ACTIVE")
            check("1c. start unchanged, end and reason still empty",
                  ambiguous.effective_start_date == date(2025, 3, 1) and ambiguous.effective_end_date is None
                  and ambiguous.lifecycle_end_reason is None)

            # 2 / 8a — no transactions
            ms.resolve_coverage(s, coverage=cov(4, ghost_a), resolution=m.RESOLUTION_STILL_ACTIVE)
            s.commit()
            s.refresh(ghost_a)
            check("2. no transactions: ACTIVE, birth stays UNKNOWN, no date invented",
                  ghost_a.status == "ACTIVE" and ghost_a.effective_start_date is None
                  and ghost_a.effective_end_date is None and ghost_a.lifecycle_end_reason is None
                  and cov(4, ghost_a).resolution_effective_date is None)

            # 6 — only the selected month
            check("6. only the selected month is resolved; a later quiet month still asks",
                  cov(5, ghost_a).resolution is None and blocked(5, ghost_a))

            # 3 — already ACTIVE: NO_ACTIVITY unchanged, STILL_ACTIVE refused
            before = (active.status, active.effective_start_date, active.effective_end_date,
                      active.lifecycle_end_reason)
            ms.resolve_coverage(s, coverage=cov(4, active), resolution=m.RESOLUTION_NO_ACTIVITY)
            s.commit()
            s.refresh(active)
            check("3. NO_ACTIVITY unchanged: resolves the month, leaves the instrument as it was",
                  cov(4, active).is_resolved and (active.status, active.effective_start_date,
                  active.effective_end_date, active.lifecycle_end_reason) == before)
            check("3b. STILL_ACTIVE on an already-ACTIVE instrument is refused (use NO_ACTIVITY)",
                  refused(lambda: ms.resolve_coverage(s, coverage=cov(5, active),
                                                      resolution=m.RESOLUTION_STILL_ACTIVE), "NO_ACTIVITY"))
            s.rollback()

            # 4 — real closure on the instrument
            for inst in (dated_end, reasoned):
                check(f"4. refused for an instrument with a recorded end ({inst.display_name})",
                      refused(lambda inst=inst: ms.resolve_coverage(s, coverage=cov(4, inst),
                                                                    resolution=m.RESOLUTION_STILL_ACTIVE),
                              "never reopens"))
                s.rollback()
                s.refresh(inst)
            check("4b. and no lifecycle history was overwritten",
                  dated_end.status == "INACTIVE" and dated_end.effective_end_date == date(2025, 12, 31)
                  and reasoned.lifecycle_end_reason == "LOST" and cov(4, dated_end).resolution is None)

            # 5 — prior lifecycle-ending resolution
            check("5. refused after a CLOSED resolution in an earlier month",
                  refused(lambda: ms.resolve_coverage(s, coverage=cov(4, prior_closed),
                                                      resolution=m.RESOLUTION_STILL_ACTIVE), "never overrides"))
            s.rollback()
            s.refresh(prior_closed)
            check("5b. its status stays INACTIVE", prior_closed.status == "INACTIVE")

            # 7 — CLOSED unchanged
            ms.resolve_coverage(s, coverage=cov(4, with_tx), resolution=m.RESOLUTION_CLOSED)
            s.commit()
            s.refresh(with_tx)
            check("7. CLOSED unchanged: end = MAX eligible posting date",
                  with_tx.status == "INACTIVE" and with_tx.lifecycle_end_reason == "CLOSED"
                  and with_tx.effective_end_date == date(2026, 2, 14))

            # 8b — Chase-2915 analogue, the other human answer
            ms.resolve_coverage(s, coverage=cov(4, ghost_b), resolution=m.RESOLUTION_CLOSED)
            s.commit()
            s.refresh(ghost_b)
            check("8. CLOSED on a no-transaction instrument: INACTIVE/CLOSED, end date UNKNOWN",
                  ghost_b.status == "INACTIVE" and ghost_b.lifecycle_end_reason == "CLOSED"
                  and ghost_b.effective_end_date is None)
            check("8b. and STILL ACTIVE is then refused for it",
                  refused(lambda: ms.resolve_coverage(s, coverage=cov(5, ghost_b),
                                                      resolution=m.RESOLUTION_STILL_ACTIVE), "never reopens"))
            s.rollback()

            # the UI eligibility function agrees with the server
            eligible = {i.display_name for i in (ambiguous, ghost_a, ghost_b, active, dated_end, reasoned,
                                                 prior_closed, with_tx, instrument("Fresh Ghost"))
                        if ms.still_active_refusal(s, i) is None}
            check("UI eligibility = only INACTIVE instruments with no recorded end",
                  eligible == {"Fresh Ghost"}, str(eligible))

            # clearing a STILL_ACTIVE resolution follows the existing convention
            ms.clear_resolution(s, coverage=cov(4, ghost_a))
            s.commit()
            s.refresh(ghost_a)
            check("clearing the resolution leaves the lifecycle as the human set it (existing rule)",
                  cov(4, ghost_a).resolution is None and ghost_a.status == "ACTIVE")
    finally:
        engine.dispose()

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
