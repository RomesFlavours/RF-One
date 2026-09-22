"""The persisted, validatable, finalizable Tips period
(TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §12-§21).

WHAT THIS IS FOR

`distribution_engine.calculate_tips_for_business_dates` answers "what are
the Tips for these Business Dates?" on demand, from source facts, and keeps
nothing. That stays true and is still the only calculation. What it cannot
do is CLOSE a period: state that this exact answer, computed under this
Business Day configuration and these Rule Versions, was approved by this
person on this date, must not move afterwards (§17), and is the one figure
Payroll may consume (§21).

That closing act is what this module owns. It extends the existing
`TipDistributionCalculationRun` row rather than adding a parallel table
("Non creare duplicati inutili" — §12), and it persists per-Employee
results into the existing `TipEntitlement` rows (§13).

THE ONE CONTROL (§11)

    Total Tips + Gratuity  ==  Total Employee Entitlements

Nothing else gates validation or finalization, and a non-zero difference is
REPORTED, never repaired. A period whose control does not balance cannot
become final by any path, manual or automatic.

WHAT THIS MODULE REFUSES TO DO

  * recalculate when a report is opened (§18) — `get_run_report` reads only
    persisted values, so a final report cannot silently change because a
    rule or a shift record was edited afterwards;
  * finalize without an identified person in MANUAL mode (§15);
  * modify a final run (§17);
  * decide which of two final runs for the same period wins. There is no
    supersession policy, so `finalize_run` refuses the second one and names
    the first. Both runs are kept. Inventing a winner here would silently
    change which figure Payroll pays.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import distribution_engine as engine
from . import validation_mode_service as mode_svc

UTC = timezone.utc


# ---------------------------------------------------------------------------
# §12 — calculate a period and persist it
# ---------------------------------------------------------------------------


def save_calculation_run(
    session: Session, *, restaurant_id: int,
    first_business_date: date, last_business_date: date,
) -> tuple[m.TipDistributionCalculationRun | None, str]:
    """Calculate the INCLUSIVE Business Date range and persist the result as
    one Calculation Run plus its per-Employee entitlements.

    Returns `(run, "")` on success or `(None, reason)` when the calculation
    itself was blocked (an unconfigured Business Day, for instance) — no run
    row is written for a period that could not be calculated, because a
    persisted run is a record of an answer and there is no answer.

    A period that already has a FINAL run is still calculable: this creates
    a NEW CALCULATED run and leaves the final one untouched (§17). Deciding
    between them is `validate_run`/`finalize_automatically`'s problem, and
    they refuse rather than guessing.

    In AUTOMATIC mode (§16), and only when the §11 control passes, the run
    is finalized here, in the same transaction, with no person named."""
    result = engine.calculate_tips_for_business_dates(
        session, restaurant_id=restaurant_id,
        first_business_date=first_business_date, last_business_date=last_business_date,
    )
    if result.blocked_reason:
        return None, result.blocked_reason

    location, _ = engine.require_location_business_day_config(session, restaurant_id)
    rows = engine.build_employee_review(session, result)
    totals = engine.build_operational_totals(result, rows)

    # The engine already records EVERY Rule Version it resolved for this
    # period, including one that produced no allocation line (an order with
    # no eligible recipient still applied a rule). Deriving this from the
    # lines instead would silently omit exactly those.
    rule_version_ids = sorted(result.rule_version_ids)

    run = m.TipDistributionCalculationRun(
        restaurant_id=restaurant_id,
        period_start=result.period_start, period_end=result.period_end,
        status=engine.STATUS_COMPLETE, completed_at=datetime.now(UTC),
        notes=engine.summarize_notes(result),
        first_business_date=first_business_date, last_business_date=last_business_date,
        timezone_name=location.timezone if location else None,
        operating_day_cutoff_time=location.operating_day_cutoff_time if location else None,
        rule_version_ids=",".join(str(i) for i in rule_version_ids) or None,
        voluntary_total_minor=totals.voluntary_minor,
        gratuity_total_minor=totals.gratuity_minor,
        service_owner_entitlements_minor=totals.service_owner_entitlements_minor,
        other_recipient_entitlements_minor=totals.other_recipient_entitlements_minor,
        retained_no_eligible_host_minor=totals.retained_no_eligible_host_minor,
        distributed_minor=totals.distributed_minor,
        control_difference_minor=totals.control_difference_minor,
        state=m.TIPS_RUN_STATE_CALCULATED,
    )
    session.add(run)
    session.flush()

    # `business_date` on an entitlement is the single-day attribution and is
    # only meaningful for a one-day period; a multi-day run leaves it NULL
    # rather than picking one of its days.
    single_day = first_business_date if first_business_date == last_business_date else None
    engine.populate_entitlements_for_run(session, run, result, business_date=single_day)

    if mode_svc.is_automatic(session, restaurant_id=restaurant_id) and run.control_passes:
        finalize_automatically(session, run)

    session.flush()
    return run, ""


# ---------------------------------------------------------------------------
# §14 / §15 / §16 — becoming final
# ---------------------------------------------------------------------------


def _blocking_final_run(
    session: Session, run: m.TipDistributionCalculationRun,
) -> m.TipDistributionCalculationRun | None:
    """An already-FINAL run covering the SAME Business Date range for the
    same Restaurant, if one exists.

    §17 — this is the case nobody has decided. Two final runs for one period
    would give Payroll two authoritative answers, and choosing between them
    (newest wins? first wins? does the second supersede the first?) is a
    business decision, not an implementation detail."""
    if run.first_business_date is None or run.last_business_date is None:
        return None
    return session.scalars(
        select(m.TipDistributionCalculationRun).where(
            m.TipDistributionCalculationRun.restaurant_id == run.restaurant_id,
            m.TipDistributionCalculationRun.first_business_date == run.first_business_date,
            m.TipDistributionCalculationRun.last_business_date == run.last_business_date,
            m.TipDistributionCalculationRun.state == m.TIPS_RUN_STATE_FINAL,
            m.TipDistributionCalculationRun.id != run.id,
        ).order_by(m.TipDistributionCalculationRun.id)
    ).first()


def finalization_blockers(
    session: Session, run: m.TipDistributionCalculationRun,
) -> list[str]:
    """Every reason this run may not become final, stated in full.

    Returned as a list rather than the first failure, so the operator sees
    the whole picture instead of fixing one thing and being stopped by the
    next."""
    blockers: list[str] = []
    if run.status != engine.STATUS_COMPLETE:
        blockers.append(
            f"The calculation did not complete (status {run.status!r}), so there is no "
            "result to make final."
        )
    if not run.control_passes:
        blockers.append(
            "The period does not balance: Total Tips + Gratuity minus Total Employee "
            f"Entitlements is {(run.control_difference_minor or 0) / 100:+.2f}, and it must be "
            "exactly 0.00. The difference is reported, never adjusted — find where the money "
            "went before finalizing."
        )
    if run.is_final:
        blockers.append(f"Run {run.id} is already final and cannot be finalized twice.")
    existing = _blocking_final_run(session, run)
    if existing is not None:
        blockers.append(
            f"Run {existing.id} is already the FINAL run for Business Dates "
            f"{run.first_business_date} to {run.last_business_date}. RF-One has no rule for "
            "which of two final runs for the same period Payroll should pay, so it will not "
            "choose one. Both runs are kept exactly as they are. This needs a Product Owner "
            "decision on supersession before a period can be re-finalized."
        )
    return blockers


def validate_run(
    session: Session, *, run_id: int, account_id: int | None,
) -> tuple[m.TipDistributionCalculationRun | None, str]:
    """§14/§15 — a person validates a calculated period, which makes it
    final.

    `account_id` is an `RFOneAccount` id resolved from the ONE existing
    RF-One login session (`rfone_web_session.account_for_session`). `None`
    is refused outright: Tips does not record an approval it cannot attach
    to an identified person, and there is deliberately no parameter here
    that would accept a name instead.

    Validation IS the approval, so a validated run becomes final in the
    same step — nothing in the task asks a human to confirm twice."""
    run = session.get(m.TipDistributionCalculationRun, run_id)
    if run is None:
        return None, f"No Calculation Run with id {run_id}."
    if account_id is None:
        return None, (
            "Validation records WHO approved the period, so it requires an identified "
            "RF-One user. No RF-One login session was resolved for this request, and Tips "
            "will not record an anonymous or manually named validator."
        )
    account = session.get(m.RFOneAccount, account_id)
    if account is None:
        return None, (
            f"RF-One account {account_id} no longer exists, so it cannot be recorded as "
            "the validator."
        )
    blockers = finalization_blockers(session, run)
    if blockers:
        return None, " ".join(blockers)

    now = datetime.now(UTC)
    run.validated_at = now
    run.validated_by_account_id = account.id
    run.finalized_at = now
    run.finalized_by_account_id = account.id
    run.finalized_automatically = False
    run.validation_mode = mode_svc.get_validation_mode(session, restaurant_id=run.restaurant_id)
    run.state = m.TIPS_RUN_STATE_FINAL
    session.flush()
    return run, ""


def finalize_automatically(
    session: Session, run: m.TipDistributionCalculationRun,
) -> tuple[m.TipDistributionCalculationRun | None, str]:
    """§16 — finalize without a person, for a Restaurant explicitly
    configured AUTOMATIC.

    Refuses when the Restaurant is MANUAL: automatic finalization is only
    ever the consequence of somebody having chosen it, never of a default.
    `validated_by_account_id` stays NULL because nobody validated, and
    `finalized_automatically` says so on the row and on the report."""
    if not mode_svc.is_automatic(session, restaurant_id=run.restaurant_id):
        return None, (
            f"Restaurant {run.restaurant_id} is in MANUAL validation mode, so this period "
            "needs a person to validate it. Automatic finalization is never a default."
        )
    blockers = finalization_blockers(session, run)
    if blockers:
        return None, " ".join(blockers)
    run.finalized_at = datetime.now(UTC)
    run.finalized_by_account_id = None
    run.finalized_automatically = True
    run.validation_mode = m.TIPS_VALIDATION_MODE_AUTOMATIC
    run.state = m.TIPS_RUN_STATE_FINAL
    session.flush()
    return run, ""


# ---------------------------------------------------------------------------
# §17 — immutability
# ---------------------------------------------------------------------------


class FinalRunImmutableError(RuntimeError):
    """Raised on any attempt to change a run that is already final."""


def assert_mutable(run: m.TipDistributionCalculationRun) -> None:
    """§17 — the guard every mutating path calls before touching a run.

    A final run's figures, its period, its validator and its entitlements
    are fixed. Correcting a final period means calculating a NEW run, which
    is why nothing in this module offers a way to edit one."""
    if run.is_final:
        finalized = run.finalized_at.strftime("%Y-%m-%d %H:%M") if run.finalized_at else "unknown"
        raise FinalRunImmutableError(
            f"Calculation Run {run.id} is FINAL (finalized {finalized} UTC) and cannot be "
            "modified. Calculate a new run for the period instead; the final run stays "
            "exactly as it was approved."
        )


# ---------------------------------------------------------------------------
# §18 — the run report, read back, never recalculated
# ---------------------------------------------------------------------------


def get_run_report(session: Session, run_id: int) -> dict | None:
    """Everything a Calculation Run Report shows, read ENTIRELY from what
    was persisted when the run was created.

    §18 — opening a report does not recalculate, and this function has no
    access to a calculation at all: it never calls the engine. That is the
    whole point. A final report reopened next year must show the figures it
    was approved on, even if a Rule Version, a Shift or an Order has
    changed since; a report that quietly re-derived itself would be a
    different document carrying the same signature."""
    run = session.get(m.TipDistributionCalculationRun, run_id)
    if run is None:
        return None
    entitlements = list(
        session.scalars(
            select(m.TipEntitlement)
            .where(m.TipEntitlement.calculation_run_id == run.id)
            .order_by(m.TipEntitlement.employee_id)
        )
    )
    employee_rows = []
    for ent in entitlements:
        employee = session.get(m.Employee, ent.employee_id)
        employee_rows.append({
            "employee_id": ent.employee_id,
            "display_name": _employee_display_name(employee, ent.employee_id),
            "result_type": ent.result_type or engine.RESULT_TYPE_SERVICE_OWNER,
            "voluntary_minor": ent.voluntary_amount_minor or 0,
            "gratuity_minor": ent.gratuity_amount_minor or 0,
            "gross_minor": ent.gross_amount_minor,
            "distributed_away_minor": ent.outbound_amount_minor,
            "received_minor": ent.inbound_amount_minor,
            "retained_no_eligible_host_minor": ent.retained_no_eligible_host_minor or 0,
            "final_entitlement_minor": ent.payable_amount_minor,
        })
    return {
        "run": run,
        "employee_rows": employee_rows,
        # Summed from the PERSISTED per-employee rows, so the report proves
        # its own total rather than restating a stored number.
        "employee_total_minor": sum(r["final_entitlement_minor"] for r in employee_rows),
        "rule_version_ids": [
            int(x) for x in (run.rule_version_ids or "").split(",") if x.strip()
        ],
        "payroll_eligible": run.is_payroll_source,
    }


def _employee_display_name(employee, employee_id: int) -> str:
    """The same naming convention `build_employee_review` uses, so a report
    and a live calculation never label the same person differently."""
    if employee is None or not employee.display_name:
        return f"Employee #{employee_id}"
    return employee.display_name


# ---------------------------------------------------------------------------
# §19 — run history
# ---------------------------------------------------------------------------


def list_runs(
    session: Session, *, restaurant_id: int, limit: int = 100,
) -> list[m.TipDistributionCalculationRun]:
    """Every persisted Calculation Run for this Restaurant, most recent
    first. Final and non-final alike: a history that hid the runs nobody
    approved would not be a history."""
    return list(
        session.scalars(
            select(m.TipDistributionCalculationRun)
            .where(m.TipDistributionCalculationRun.restaurant_id == restaurant_id)
            .order_by(m.TipDistributionCalculationRun.started_at.desc(),
                      m.TipDistributionCalculationRun.id.desc())
            .limit(limit)
        )
    )


# ---------------------------------------------------------------------------
# §21 — the Payroll contract
# ---------------------------------------------------------------------------


def payroll_source_run(
    session: Session, *, restaurant_id: int,
    first_business_date: date, last_business_date: date,
) -> tuple[m.TipDistributionCalculationRun | None, str]:
    """THE Tips figure Payroll may use for a period, or a refusal.

    §21, in one function, and the only one Payroll should ever call:

      * Payroll reads a FINAL Calculation Run. Nothing else is a Tips
        source — not a CALCULATED run, however recent, and not a screen.
      * Payroll NEVER recalculates from Orders. It does not need to: the
        entitlements are persisted on the final run, and re-deriving them
        would reintroduce exactly the drift finalization exists to prevent.
      * If no final run exists for the period, Payroll gets nothing and a
        reason. It does not fall back to an unapproved run and it does not
        pay a provisional figure.

    The export itself is deliberately not implemented here: this task
    defines the contract, not the file format."""
    run = session.scalars(
        select(m.TipDistributionCalculationRun).where(
            m.TipDistributionCalculationRun.restaurant_id == restaurant_id,
            m.TipDistributionCalculationRun.first_business_date == first_business_date,
            m.TipDistributionCalculationRun.last_business_date == last_business_date,
            m.TipDistributionCalculationRun.state == m.TIPS_RUN_STATE_FINAL,
        ).order_by(m.TipDistributionCalculationRun.id)
    ).first()
    if run is None:
        return None, (
            f"No FINAL Tips Calculation Run exists for Business Dates {first_business_date} "
            f"to {last_business_date}. Payroll has no Tips figure for this period and must "
            "not substitute one: a period nobody has validated is not payable."
        )
    return run, ""
