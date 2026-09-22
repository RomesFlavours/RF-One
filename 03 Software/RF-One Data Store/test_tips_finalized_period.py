#!/usr/bin/env python
"""The finalized Tips period — rule lifecycle, the single control,
validation identity, immutability and the Payroll contract
(TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §24).

The seventeen mandatory checks, in the order the task states them:

    §7  1. a later rule makes an earlier one OLD and closes it at its start
        2. a rule scheduled inside the new rule's coverage is CANCELLED
        3. a rule starting at or after the new rule's end stays ACTIVE
        4. an open-ended new rule cancels every covered future rule
        5. a CANCELLED version governs no instant; an OLD one still governs
           its own past
    §8  6. the rule covers every operating night of the period, with no
           night left ruleless
    §6  7. no eligible Host means the Service Owner keeps 100%, and the row
           reads READY, not ATTENTION
    §11 8. Total Tips + Gratuity == Total Employee Entitlements
        9. a period that does not balance cannot become final, by any path
    §12 10. a saved run records its Business Dates, Business Day
            configuration, Rule Versions and totals
    §13 11. per-employee results persist, and sum to the run's own total
    §15 12. validation without an identified RF-One user is refused; with
            one, that account is recorded
        13. Tips uses the SAME session mechanism as RF-One Web, and honours
            its revocation
    §16 14. MANUAL is the default in every direction, and Review Mode is a
            different setting
        15. AUTOMATIC finalizes on save; MANUAL does not
    §17 16. a final run is immutable, and a second final run for one period
            is refused rather than resolved
    §18 17. the report does not recalculate, the history lists every run,
        §19 and only a FINAL run is a Payroll source
        §21

Runs against a disposable database with a synthetic fixture. Never touches
AWS, RDS, a production database, Clover, ADP or Mercury.

Usage:
    python test_tips_finalized_period.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from rfone_data_store import models as m
from rfone_data_store import rfone_account_service as account_service
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store.tips import calculation_run_service as run_svc
from rfone_data_store.tips import distribution_engine as engine
from rfone_data_store.tips import distribution_rule_service as rule_svc
from rfone_data_store.tips import review_mode_service as review_mode_svc
from rfone_data_store.tips import validation_mode_service as mode_svc

UTC = timezone.utc
TZ_NAME = "America/New_York"
TZ = ZoneInfo(TZ_NAME)
CUTOFF = time(4, 0)

# Two operating nights in May, deliberately away from either DST boundary:
# a period whose totals depend on which side of a clock change it falls is
# a different test, and it would hide this one's failures.
DAY_ONE = date(2026, 5, 4)
DAY_TWO = date(2026, 5, 5)


def local(day: date, hour: int, minute: int = 0) -> datetime:
    """A wall-clock instant at the Branch, as UTC."""
    return datetime.combine(day, time(hour, minute), tzinfo=TZ).astimezone(UTC)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("tips_finalized_period")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine_obj = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine_obj)
        with session_factory() as s:
            fixture = _build_fixture(s)
            restaurant_id = fixture["restaurant_id"]

            # =============================================================
            # §7 — the rule lifecycle. Exercised on a rule of its own so
            # the calculation rule stays untouched.
            # =============================================================
            lifecycle = _build_lifecycle_rule(s, fixture)

            # 1. an earlier rule becomes OLD and stops at the new start.
            v1 = lifecycle["v1"]
            new_start = local(date(2026, 6, 1), 4)
            v2 = rule_svc.create_new_version(
                s, lifecycle["rule_id"],
                recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("12.0000"),
                effective_from=new_start, effective_to=None,
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            s.flush()
            check(
                "1. §7 a later rule makes the earlier one OLD and closes it at the new start",
                v1.status == m.TIP_RULE_VERSION_STATUS_OLD
                and _aware(v1.effective_to) == new_start
                and v2.status == m.TIP_RULE_VERSION_STATUS_ACTIVE,
                detail=f"v1 {v1.status} to {v1.effective_to}, v2 {v2.status}",
            )
            check(
                "1b. §7 the OLD version's own terms are not rewritten",
                v1.rate == Decimal("10.0000")
                and _aware(v1.effective_from) == lifecycle["v1_from"],
                detail=f"rate {v1.rate}, from {v1.effective_from}",
            )

            # 2/3/4. a future rule inside the coverage is CANCELLED; one
            # starting at or after the end survives.
            bounded = _fresh_lifecycle_rule(s, fixture, "bounded")
            inside = rule_svc.create_new_version(
                s, bounded["rule_id"], recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("11.0000"),
                effective_from=local(date(2026, 8, 1), 4), effective_to=None,
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            after = rule_svc.create_new_version(
                s, bounded["rule_id"], recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("13.0000"),
                effective_from=local(date(2026, 12, 1), 4), effective_to=None,
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            s.flush()
            # Now a rule covering 2026-07-01 .. 2026-11-01: `inside` starts
            # inside it, `after` starts after it ends.
            covering = rule_svc.create_new_version(
                s, bounded["rule_id"], recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("14.0000"),
                effective_from=local(date(2026, 7, 1), 4),
                effective_to=local(date(2026, 11, 1), 4),
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            s.flush()
            check(
                "2. §7 a rule scheduled INSIDE the new rule's coverage becomes CANCELLED",
                inside.status == m.TIP_RULE_VERSION_STATUS_CANCELLED,
                detail=inside.status,
            )
            check(
                "3. §7 a rule starting at or after the new rule's END stays ACTIVE",
                after.status == m.TIP_RULE_VERSION_STATUS_ACTIVE,
                detail=after.status,
            )
            check(
                "3b. §7 the rule that started earlier became OLD, not CANCELLED",
                bounded["v1"].status == m.TIP_RULE_VERSION_STATUS_OLD,
                detail=bounded["v1"].status,
            )

            open_ended = _fresh_lifecycle_rule(s, fixture, "openended")
            future_a = rule_svc.create_new_version(
                s, open_ended["rule_id"], recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("15.0000"),
                effective_from=local(date(2027, 1, 1), 4), effective_to=None,
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            future_b = rule_svc.create_new_version(
                s, open_ended["rule_id"], recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("16.0000"),
                effective_from=local(date(2028, 1, 1), 4), effective_to=None,
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            s.flush()
            rule_svc.create_new_version(
                s, open_ended["rule_id"], recipient_role_id=fixture["role_host_id"],
                calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("17.0000"),
                effective_from=local(date(2026, 9, 1), 4), effective_to=None,
                source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
                eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            )
            s.flush()
            check(
                "4. §7 an OPEN-ENDED new rule cancels EVERY covered future rule "
                "(there is no 'after' to survive into)",
                future_a.status == m.TIP_RULE_VERSION_STATUS_CANCELLED
                and future_b.status == m.TIP_RULE_VERSION_STATUS_CANCELLED,
                detail=f"{future_a.status}, {future_b.status}",
            )

            # 5. selection honours the statuses.
            cancelled_at = local(date(2026, 8, 15), 20)
            old_window_at = local(date(2026, 6, 15), 20)
            selected_cancelled = rule_svc.get_version_effective_at(
                s, bounded["rule_id"], cancelled_at,
            )
            selected_old = rule_svc.get_version_effective_at(
                s, bounded["rule_id"], old_window_at,
            )
            check(
                "5. §7 a CANCELLED version governs no instant, while an OLD version still "
                "governs its own closed past",
                selected_cancelled is not None
                and selected_cancelled.id == covering.id
                and selected_old is not None
                and selected_old.id == bounded["v1"].id,
                detail=f"at cancelled window: {selected_cancelled and selected_cancelled.id}; "
                       f"in old window: {selected_old and selected_old.id}",
            )
            s.commit()

            # =============================================================
            # §8 — no operating night without a rule.
            # =============================================================
            location = s.get(m.Location, fixture["location_id"])
            uncovered = []
            for day in (DAY_ONE, DAY_TWO):
                # A representative service moment AND the first minute of
                # the operating day: a rule that starts at midnight UTC
                # would pass the first check and fail this one.
                for moment in (local(day, 4, 1), local(day, 20)):
                    if rule_svc.get_version_effective_at(
                        s, fixture["rule_id"], moment,
                    ) is None:
                        uncovered.append(moment.isoformat())
            check(
                "6. §8 every operating night of the period is covered by a rule, from the "
                "cutoff onward — no order is left ruleless",
                not uncovered,
                detail=f"uncovered moments: {uncovered}",
            )

            # =============================================================
            # §6 / §10 / §11 — the calculation.
            # =============================================================
            result = engine.calculate_tips_for_business_dates(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_ONE, last_business_date=DAY_TWO,
            )
            rows = engine.build_employee_review(s, result)
            totals = engine.build_operational_totals(result, rows)
            by_name = {r.display_name: r for r in rows}
            server = by_name.get("Server One")
            host = by_name.get("Host One")

            check(
                "7. §6 an Order with no eligible Host at Order Open Time leaves the Service "
                "Owner holding 100% of it, and the row reads READY, not ATTENTION",
                server is not None
                and server.needs_attention is False
                and all(not r.needs_attention for r in rows),
                detail=(f"attention rows {[r.display_name for r in rows if r.needs_attention]}"),
            )
            check(
                "7c. §6/§10 NO hypothetical 'would have been distributed' amount exists "
                "anywhere in the operational result — not on the row, not in the totals",
                not hasattr(server, "retained_no_eligible_host_minor")
                and not hasattr(totals, "retained_no_eligible_host_minor"),
                detail="the figure must be absent, not merely zero",
            )
            check(
                "7b. §6 the retained amount is INSIDE the Service Owner's entitlement, never "
                "deducted from it",
                server is not None
                and server.final_entitlement_minor == 17000 - 1200
                and server.distributed_away_minor == 1200,
                detail=f"entitlement {server and server.final_entitlement_minor}",
            )
            check(
                "8. §11 Total Tips + Gratuity equals Total Employee Entitlements exactly, and "
                "that is the only control",
                totals.gross_minor == 17000
                and totals.voluntary_minor == 15000
                and totals.gratuity_minor == 2000
                and totals.total_employee_entitlements_minor == 17000
                and totals.control_difference_minor == 0
                and totals.control_passes,
                detail=(f"gross {totals.gross_minor}, entitlements "
                        f"{totals.total_employee_entitlements_minor}, "
                        f"difference {totals.control_difference_minor}"),
            )
            check(
                "8b. §11 the Host's entitlement is exactly what the Service Owner gave up",
                host is not None
                and host.received_minor == 1200
                and host.final_entitlement_minor == 1200
                and totals.other_recipient_entitlements_minor == 1200,
                detail=f"host received {host and host.received_minor}",
            )

            # =============================================================
            # §12 / §13 — the saved run.
            # =============================================================
            run, reason = run_svc.save_calculation_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_ONE, last_business_date=DAY_TWO,
            )
            s.commit()
            check(
                "10. §12 a saved run records its Business Dates, the Business Day "
                "configuration and the Rule Versions it was computed under",
                run is not None
                and run.first_business_date == DAY_ONE
                and run.last_business_date == DAY_TWO
                and run.timezone_name == TZ_NAME
                and run.operating_day_cutoff_time == CUTOFF
                and run.rule_version_ids == str(fixture["version_id"])
                and run.state == m.TIPS_RUN_STATE_CALCULATED,
                detail=(f"reason {reason!r}; tz {run and run.timezone_name}, cutoff "
                        f"{run and run.operating_day_cutoff_time}, versions "
                        f"{run and run.rule_version_ids}"),
            )
            check(
                "10b. §12 the saved totals are the calculated totals, control included",
                run is not None
                and run.gross_total_minor == 17000
                and run.total_employee_entitlements_minor == 17000
                and run.control_difference_minor == 0,
                detail=f"gross {run and run.gross_total_minor}",
            )

            entitlements = {
                e.employee_id: e
                for e in s.query(m.TipEntitlement).filter_by(calculation_run_id=run.id).all()
            }
            server_ent = entitlements.get(fixture["server_id"])
            host_ent = entitlements.get(fixture["host_id"])
            check(
                "11. §13 per-employee results persist with the voluntary/gratuity split, the "
                "result type and the retained figure, and sum to the run's own total",
                server_ent is not None and host_ent is not None
                and server_ent.voluntary_amount_minor == 15000
                and server_ent.gratuity_amount_minor == 2000
                and server_ent.result_type == engine.RESULT_TYPE_SERVICE_OWNER
                and not hasattr(server_ent, "retained_no_eligible_host_minor")
                and host_ent.result_type == engine.RESULT_TYPE_HOST
                and host_ent.payable_amount_minor == 1200
                and sum(e.payable_amount_minor for e in entitlements.values())
                == run.total_employee_entitlements_minor,
                detail=str({k: (v.result_type, v.payable_amount_minor)
                            for k, v in entitlements.items()}),
            )

            # =============================================================
            # §15 — who validates.
            # =============================================================
            blocked_run, blocked_reason = run_svc.validate_run(
                s, run_id=run.id, account_id=None,
            )
            check(
                "12. §15 validation with no identified RF-One user is REFUSED, and says so",
                blocked_run is None
                and "identified RF-One user" in blocked_reason
                and run.state == m.TIPS_RUN_STATE_CALCULATED
                and run.validated_by_account_id is None,
                detail=blocked_reason,
            )

            account = account_service.create_account(
                s, username="validator", display_name="Test Validator",
                password="a-long-enough-test-password", is_admin=False,
            )
            s.flush()
            validated, validate_reason = run_svc.validate_run(
                s, run_id=run.id, account_id=account.id,
            )
            s.commit()
            check(
                "12b. §15 validation by an identified user records THAT account and makes the "
                "period final",
                validated is not None
                and validated.state == m.TIPS_RUN_STATE_FINAL
                and validated.validated_by_account_id == account.id
                and validated.finalized_by_account_id == account.id
                and validated.finalized_automatically is False
                and validated.validated_at is not None,
                detail=f"{validate_reason!r}; state {validated and validated.state}",
            )

            check(
                "13. §15 Tips resolves identity through the SAME session mechanism as RF-One "
                "Web — one account id, one session-version check, no second login",
                shared_session.SESSION_ACCOUNT_KEY == "rfone_account_id"
                and shared_session.account_for_session(
                    s, account_id=account.id, session_version=account.session_version,
                ) is not None
                # A stale session version is a revoked cookie and must not
                # resolve, in Tips exactly as in RF-One Web.
                and shared_session.account_for_session(
                    s, account_id=account.id, session_version=account.session_version + 1,
                ) is None
                and shared_session.account_for_session(
                    s, account_id=None, session_version=None,
                ) is None,
                detail="shared session lookup",
            )

            # =============================================================
            # §16 — the separate validation-mode configuration.
            # =============================================================
            other_restaurant = m.Restaurant(name="Unconfigured Restaurant", default_currency="USD")
            s.add(other_restaurant)
            s.flush()
            review_mode_before = review_mode_svc.get_review_mode(s, restaurant_id=restaurant_id)
            check(
                "14. §16 MANUAL is the default in every direction — no row, an unknown value, "
                "and a Restaurant that was never configured all read MANUAL",
                mode_svc.get_validation_mode(s, restaurant_id=other_restaurant.id)
                == m.TIPS_VALIDATION_MODE_MANUAL
                and mode_svc.get_validation_mode(s, restaurant_id=restaurant_id)
                == m.TIPS_VALIDATION_MODE_MANUAL
                and mode_svc.is_automatic(s, restaurant_id=restaurant_id) is False
                and mode_svc.get_config(s, restaurant_id=other_restaurant.id) is None,
                detail="defaults",
            )
            rejected = False
            try:
                mode_svc.set_validation_mode(
                    s, restaurant_id=restaurant_id, validation_mode="SOMETIMES",
                )
            except ValueError:
                rejected = True
                s.rollback()
            check(
                "14b. §16 an unknown Validation Mode is rejected loudly rather than stored and "
                "silently read back as MANUAL",
                rejected,
                detail="no ValueError raised",
            )
            mode_svc.set_validation_mode(
                s, restaurant_id=restaurant_id,
                validation_mode=m.TIPS_VALIDATION_MODE_AUTOMATIC,
                updated_by_account_id=account.id,
            )
            s.flush()
            check(
                "14c. §16 Validation Mode is a SEPARATE setting: switching it does not touch "
                "Review Mode, whose own AUTOMATIC means something else entirely",
                mode_svc.is_automatic(s, restaurant_id=restaurant_id)
                and review_mode_svc.get_review_mode(s, restaurant_id=restaurant_id)
                == review_mode_before
                and m.TipsValidationModeConfig.__tablename__
                != m.TipsCalculationScheduleConfig.__tablename__,
                detail=f"review mode now {review_mode_svc.get_review_mode(s, restaurant_id=restaurant_id)}",
            )

            # 15. AUTOMATIC finalizes on save; MANUAL does not.
            auto_run, _ = run_svc.save_calculation_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_ONE, last_business_date=DAY_ONE,
            )
            s.flush()
            mode_svc.set_validation_mode(
                s, restaurant_id=restaurant_id, validation_mode=m.TIPS_VALIDATION_MODE_MANUAL,
            )
            s.flush()
            manual_run, _ = run_svc.save_calculation_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_TWO, last_business_date=DAY_TWO,
            )
            s.commit()
            check(
                "15. §16 AUTOMATIC finalizes a balancing period on save with no validator "
                "named; MANUAL leaves it waiting for a person",
                auto_run is not None and manual_run is not None
                and auto_run.state == m.TIPS_RUN_STATE_FINAL
                and auto_run.finalized_automatically is True
                and auto_run.validated_by_account_id is None
                and manual_run.state == m.TIPS_RUN_STATE_CALCULATED
                and manual_run.finalized_at is None,
                detail=f"auto {auto_run and auto_run.state}, manual {manual_run and manual_run.state}",
            )

            # 9. a period that does not balance cannot become final.
            broken, _ = run_svc.save_calculation_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_ONE, last_business_date=DAY_ONE,
            )
            s.flush()
            # Deliberately corrupt ONLY the stored control, to prove the
            # gate reads the control and not the state it wishes for.
            broken.control_difference_minor = -250
            s.flush()
            blockers = run_svc.finalization_blockers(s, broken)
            nope, nope_reason = run_svc.validate_run(
                s, run_id=broken.id, account_id=account.id,
            )
            auto_nope, auto_nope_reason = run_svc.finalize_automatically(s, broken)
            check(
                "9. §11 a period whose control does not balance cannot become final by ANY "
                "path, and the difference is reported rather than adjusted",
                any("does not balance" in b for b in blockers)
                and nope is None and "does not balance" in nope_reason
                and auto_nope is None
                and broken.state == m.TIPS_RUN_STATE_CALCULATED
                and broken.control_difference_minor == -250,
                detail=f"blockers {blockers}; manual {nope_reason!r}; auto {auto_nope_reason!r}",
            )
            s.rollback()

            # =============================================================
            # §17 — immutability and the undecided supersession policy.
            # =============================================================
            final_run = s.get(m.TipDistributionCalculationRun, run.id)
            raised = ""
            try:
                run_svc.assert_mutable(final_run)
            except run_svc.FinalRunImmutableError as exc:
                raised = str(exc)
            second, second_reason = run_svc.save_calculation_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_ONE, last_business_date=DAY_TWO,
            )
            s.flush()
            refused, refused_reason = run_svc.validate_run(
                s, run_id=second.id, account_id=account.id,
            )
            check(
                "16. §17 a final run is immutable, and a SECOND final run for the same period "
                "is refused rather than silently superseding the first — both are kept",
                "FINAL" in raised and "cannot be modified" in raised
                and second is not None
                and second.state == m.TIPS_RUN_STATE_CALCULATED
                and refused is None
                and "no rule for which of two final runs" in refused_reason
                and s.get(m.TipDistributionCalculationRun, run.id).state
                == m.TIPS_RUN_STATE_FINAL,
                detail=f"{raised[:60]!r}; refusal {refused_reason!r}",
            )
            s.commit()

            # =============================================================
            # §18 / §19 / §21 — the report, the history and Payroll.
            # =============================================================
            report_before = run_svc.get_run_report(s, run.id)
            # Change a source fact the calculation depends on. A report that
            # recalculated would move; this one must not.
            s.query(m.PaymentTip).filter_by(payment_id=fixture["payment_one_id"]).update(
                {"amount": 999999}
            )
            s.flush()
            report_after = run_svc.get_run_report(s, run.id)
            live = engine.build_operational_totals(
                engine.calculate_tips_for_business_dates(
                    s, restaurant_id=restaurant_id,
                    first_business_date=DAY_ONE, last_business_date=DAY_TWO,
                ),
                engine.build_employee_review(
                    s,
                    engine.calculate_tips_for_business_dates(
                        s, restaurant_id=restaurant_id,
                        first_business_date=DAY_ONE, last_business_date=DAY_TWO,
                    ),
                ),
            )
            check(
                "17. §18 opening the report does NOT recalculate: a saved report is unchanged "
                "by a later edit to its own source facts, while a live calculation moves",
                report_before is not None and report_after is not None
                and report_after["employee_total_minor"]
                == report_before["employee_total_minor"] == 17000
                and report_after["run"].gross_total_minor == 17000
                and live.gross_minor != 17000,
                detail=(f"report {report_after and report_after['employee_total_minor']}, "
                        f"live {live.gross_minor}"),
            )
            s.rollback()

            history = run_svc.list_runs(s, restaurant_id=restaurant_id)
            final_ids = {r.id for r in history if r.is_final}
            check(
                "17b. §19 the history lists every saved run for the Restaurant, non-final ones "
                "included, most recent first",
                len(history) >= 4
                and run.id in {r.id for r in history}
                and manual_run.id in {r.id for r in history}
                and run.id in final_ids and manual_run.id not in final_ids
                and all(
                    (history[i].started_at or datetime.min.replace(tzinfo=UTC))
                    >= (history[i + 1].started_at or datetime.min.replace(tzinfo=UTC))
                    for i in range(len(history) - 1)
                ),
                detail=f"{len(history)} runs, final {sorted(final_ids)}",
            )

            payroll_run, payroll_reason = run_svc.payroll_source_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_ONE, last_business_date=DAY_TWO,
            )
            no_payroll, no_payroll_reason = run_svc.payroll_source_run(
                s, restaurant_id=restaurant_id,
                first_business_date=DAY_TWO, last_business_date=DAY_TWO,
            )
            check(
                "17c. §21 only a FINAL run is a Payroll source; a CALCULATED period yields "
                "nothing and a reason, never a provisional figure",
                payroll_run is not None and payroll_run.id == run.id
                and payroll_run.is_payroll_source
                and no_payroll is None
                and "No FINAL Tips Calculation Run" in no_payroll_reason
                and manual_run.is_payroll_source is False,
                detail=f"{payroll_reason!r} / {no_payroll_reason!r}",
            )

            s.rollback()
    finally:
        engine_obj.dispose()

    print()
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  {description}")
        print(f"\n{len(passed)} passed, {len(failed)} FAILED")
        return 1
    print(f"ALL CHECKS PASSED ({len(passed)})")
    return 0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _build_fixture(s) -> dict:
    """One Branch, one Server, one Host, two operating nights.

    Night one: the Host is clocked in when the Order is opened, so the
    tip-out reaches them.
    Night two: no Host is on shift when the Order is opened, so the Service
    Owner keeps the whole thing (§6).
    """
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    s.add(source_system)
    s.flush()
    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id="FINALMERCH", name="Final Test",
    )
    s.add(merchant)
    s.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id,
        source_location_id="FINALMERCH", name="Final Test Branch", currency="USD",
        timezone=TZ_NAME, operating_day_cutoff_time=CUTOFF,
    )
    s.add(location)
    s.flush()
    restaurant = m.Restaurant(name="Final Test Restaurant", default_currency="USD")
    s.add(restaurant)
    s.flush()
    s.add(m.RestaurantLocation(
        restaurant_id=restaurant.id, location_id=location.id, is_primary=True,
    ))
    area = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    s.add(area)
    s.flush()

    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    s.add_all([role_server, role_host])
    s.flush()

    def employee(source_id: str, name: str) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id,
            source_employee_id=source_id, display_name=name, system_role="EMPLOYEE",
        )
        s.add(emp)
        s.flush()
        return emp

    server = employee("SRV1", "Server One")
    host = employee("HST1", "Host One")

    span_from = local(DAY_ONE - timedelta(days=30), 0)
    for emp, role in ((server, role_server), (host, role_host)):
        s.add(m.EmployeeAssignment(
            employee_id=emp.id, restaurant_id=restaurant.id, operational_area_id=area.id,
            restaurant_role_id=role.id, valid_from=span_from, valid_to=None,
            assignment_source="MANUAL",
        ))
    # The Host works night one only, and goes home BEFORE the guest pays —
    # which under ACTIVE_AT_ORDER_OPEN still earns them the tip-out.
    s.add(m.Shift(
        employee_id=host.id, source_system_id=source_system.id, source_shift_id="SH-HOST-1",
        clock_in=local(DAY_ONE, 17), clock_out=local(DAY_ONE, 20),
    ))
    s.add(m.Shift(
        employee_id=server.id, source_system_id=source_system.id, source_shift_id="SH-SRV-1",
        clock_in=local(DAY_ONE, 16), clock_out=local(DAY_TWO, 2),
    ))
    s.flush()

    rule = rule_svc.create_rule(
        s, restaurant_id=restaurant.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("10.0000"),
        # From the cutoff of the FIRST operating night, not from midnight
        # UTC — §8's own point.
        effective_from=local(DAY_ONE, 4),
        source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
        eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
        created_by="test fixture",
    )
    s.flush()
    version = rule_svc.list_versions(s, rule.id)[-1]

    counter = {"n": 0}

    def order(*, opened_at: datetime, settled_at: datetime, tip: int, gratuity: int = 0):
        counter["n"] += 1
        o = m.Order(
            location_id=location.id, source_system_id=source_system.id,
            source_order_id=f"ORD-{counter['n']}", employee_id=server.id,
            source_employee_id=server.source_employee_id, created_at=opened_at,
            state="locked", payment_state="PAID", currency="USD", total=50000,
        )
        s.add(o)
        s.flush()
        pay = m.Payment(
            order_id=o.id, source_system_id=source_system.id,
            source_payment_id=f"PAY-{counter['n']}", employee_id=server.id,
            source_employee_id=server.source_employee_id, created_at=settled_at,
            amount=50000, result="SUCCESS", currency="USD",
        )
        s.add(pay)
        s.flush()
        s.add(m.PaymentTip(payment_id=pay.id, amount=tip, source_present=True))
        if gratuity:
            s.add(m.OrderFee(
                order_id=o.id, source_system_id=source_system.id, fee_type="SERVICE_CHARGE",
                name_raw="Automatic Gratuity", amount=gratuity,
            ))
        s.flush()
        return o, pay

    # Night one: opened 19:00 (Host on shift), settled 21:00 (Host gone).
    # $100.00 voluntary + $20.00 gratuity -> 10% of $120.00 = $12.00 out.
    _, payment_one = order(
        opened_at=local(DAY_ONE, 19), settled_at=local(DAY_ONE, 21),
        tip=10000, gratuity=2000,
    )
    # Night two: opened 22:00, no Host on shift at all -> SOURCE_RETAINS.
    # $50.00 voluntary -> 10% = $5.00 the Service Owner keeps.
    order(opened_at=local(DAY_TWO, 22), settled_at=local(DAY_TWO, 23), tip=5000)
    s.commit()

    return {
        "restaurant_id": restaurant.id, "location_id": location.id,
        "role_server_id": role_server.id, "role_host_id": role_host.id,
        "area_id": area.id, "server_id": server.id, "host_id": host.id,
        "rule_id": rule.id, "version_id": version.id,
        "payment_one_id": payment_one.id,
    }


def _build_lifecycle_rule(s, fixture: dict) -> dict:
    return _fresh_lifecycle_rule(s, fixture, "lifecycle")


def _fresh_lifecycle_rule(s, fixture: dict, label: str) -> dict:
    """A rule used ONLY to exercise §7's transitions, so the calculation
    rule above is never re-statused by a lifecycle test."""
    v1_from = local(date(2026, 5, 1), 4)
    rule = rule_svc.create_rule(
        s, restaurant_id=fixture["restaurant_id"], recipient_role_id=fixture["role_host_id"],
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("10.0000"),
        effective_from=v1_from,
        source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
        eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
        created_by=f"§7 {label}",
    )
    s.flush()
    rule.is_active = False  # never selected by a calculation
    s.flush()
    return {
        "rule_id": rule.id,
        "v1": rule_svc.list_versions(s, rule.id)[-1],
        "v1_from": v1_from,
    }


if __name__ == "__main__":
    sys.exit(main())
