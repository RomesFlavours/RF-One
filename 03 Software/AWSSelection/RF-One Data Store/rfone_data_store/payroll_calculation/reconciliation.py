"""Manual return of Payroll Provider results, and reconciliation against
what RF-One approved (`01 Domains/Shared Domains/Personnel Management/
Compensation/PAYROLL_HANDOFF_CONNECTOR.md`, "optional Connector return /
manual recording" — this task makes that return path part of Compensation
V1).

`record_manual_provider_result` reuses the EXISTING Administration/Payroll
return model (`PayrollRun`/`EmployeePayrollResult`/`PayrollEarningFact` —
`rfone_data_store/payroll/adp_importer.py`'s own target schema), so a
manually keyed-in Provider result and a future automated import are
indistinguishable to every downstream reader. It is a thin, form-driven
persistence path into those same tables — never a new payroll-result model.

`reconcile` compares only semantically comparable values between what
RF-One approved (`ApprovedEmployeeCompensationResult`) and what the
Provider reported (`PayrollEarningFact`, classified by `earning_type`) —
Regular Pay to Regular Pay, Tips to Tips, Recognized Incentive to a
Provider bonus/incentive line. It never compares the Provider's net pay to
any Compensation total (Compensation `README.md`, "Provider
Reconciliation... not defined [here]" — this module is where that
comparison is finally, deliberately narrowly, defined)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc
_CENTS = Decimal("0.01")

STATUS_MATCH = "MATCH"
STATUS_DIFFERENT = "DIFFERENT"
STATUS_MISSING_IN_PROVIDER = "MISSING_IN_PROVIDER"
STATUS_MISSING_IN_RFONE = "MISSING_IN_RFONE"

_RESOLUTION_STATUSES = ("OPEN", "EXPLAINED", "ACCEPTED")

# Which RF-One component each Provider `earning_type` bucket is compared
# against. Deliberately excludes anything resembling net pay/total gross —
# Provider net pay is never compared to a Compensation total (Compensation
# README.md; Administration/Payroll/Payment Execution.md).
_COMPONENT_EARNING_TYPES: dict[str, tuple[str, ...]] = {
    "Regular Pay": ("REGULAR", "REGULAR_HOURS", "REGULAR_PAY"),
    "Tips": ("TIPS", "CASH_TIPS", "CHARGE_TIPS", "REPORTED_TIPS"),
    "Recognized Incentive": ("BONUS", "INCENTIVE", "COMMISSION"),
}


@dataclass(frozen=True)
class ManualEarningEntry:
    """One free-text component reported by the Provider for one Employee,
    as manually keyed in from the Provider's own report — mirrors
    `PayrollEarningFact`'s own free-string `earning_type`/`source_label`
    convention (never a hardcoded whitelist)."""

    earning_type: str
    source_label: str
    amount: Decimal
    paid_to_employee: bool = True


@dataclass(frozen=True)
class ManualEmployeeResult:
    employee_id: int
    entries: list[ManualEarningEntry] = field(default_factory=list)
    source_note: str | None = None


class DuplicateProviderResultError(ValueError):
    """Raised when a manual Provider result is recorded for a
    (source_system_id, restaurant_id, period_start, period_end, pay_date,
    run_type) combination that already has a non-SUPERSEDED `PayrollRun` —
    the same natural key `rfone_data_store.payroll.adp_importer` uses
    content-hash idempotency for on the file-import path. A manual form has
    no file hash to key on, so this is the equivalent guard for a double
    submission (e.g. an operator double-clicking "Record result"). To
    correct an already-recorded result, pass `supersedes_payroll_run_id`
    explicitly — never silently create a second, competing PayrollRun for
    the same result."""


def record_manual_provider_result(
    session: Session,
    *,
    source_system_id: int,
    restaurant_id: int,
    period_start: datetime,
    period_end: datetime,
    pay_date: datetime,
    run_type: str,
    employee_results: list[ManualEmployeeResult],
    created_by: str,
    provider_reference: str | None = None,
    supersedes_payroll_run_id: int | None = None,
) -> m.PayrollRun:
    """Persists one manually-keyed-in Provider result, reusing exactly the
    same tables an automated import would write. Employee identity is
    recorded directly against `employee_id` — the operator is a human who
    already knows which RF-One Employee this is (unlike the file-based ADP
    import, there is no provider-only name string to resolve here).

    Raises `DuplicateProviderResultError` if a non-SUPERSEDED `PayrollRun`
    already exists for the same (source_system_id, restaurant_id,
    period_start, period_end, pay_date, run_type) and `supersedes_payroll_run_id`
    was not given — never silently records a second copy of the same
    result. Does not commit."""

    if not created_by or not created_by.strip():
        raise ValueError(
            "record_manual_provider_result requires a non-empty created_by actor reference"
        )
    if not employee_results:
        raise ValueError("record_manual_provider_result requires at least one employee result")

    if supersedes_payroll_run_id is None:
        existing = session.scalars(
            select(m.PayrollRun).where(
                m.PayrollRun.source_system_id == source_system_id,
                m.PayrollRun.restaurant_id == restaurant_id,
                m.PayrollRun.period_start == period_start,
                m.PayrollRun.period_end == period_end,
                m.PayrollRun.pay_date == pay_date,
                m.PayrollRun.run_type == run_type,
                m.PayrollRun.status != "SUPERSEDED",
            )
        ).first()
        if existing is not None:
            raise DuplicateProviderResultError(
                f"A PayrollRun ({existing.id}) already exists for this source/restaurant/period/"
                "pay date/run type — pass supersedes_payroll_run_id to explicitly record a "
                "correction, never a silent duplicate"
            )

    run = m.PayrollRun(
        restaurant_id=restaurant_id,
        source_system_id=source_system_id,
        period_start=period_start,
        period_end=period_end,
        pay_date=pay_date,
        run_type=run_type,
        provider_reference=provider_reference,
        status="COMPLETE",
    )
    session.add(run)
    session.flush()

    if supersedes_payroll_run_id is not None:
        prior = session.get(m.PayrollRun, supersedes_payroll_run_id)
        if prior is not None:
            prior.status = "SUPERSEDED"
            prior.superseded_by_payroll_run_id = run.id

    for employee_result in employee_results:
        result_row = m.EmployeePayrollResult(
            payroll_run_id=run.id,
            employee_id=employee_result.employee_id,
            review_status="OK",
            source_note=employee_result.source_note,
        )
        session.add(result_row)
        session.flush()

        for entry in employee_result.entries:
            session.add(
                m.PayrollEarningFact(
                    employee_payroll_result_id=result_row.id,
                    earning_type=entry.earning_type,
                    source_label=entry.source_label,
                    amount_minor=int(entry.amount.quantize(_CENTS) * 100),
                    paid_to_employee=entry.paid_to_employee,
                )
            )

    session.flush()
    return run


class LegalEntityMismatchError(ValueError):
    """Raised when the requested `PayrollRun`'s own Restaurant belongs to a
    DIFFERENT `LegalEntity` than the `ApprovedCompensationSnapshot` being
    reconciled — reconciling across Legal Entities would either silently
    compare unrelated employees or spuriously flag every component as
    missing, neither of which is a meaningful reconciliation. Never
    reconciled automatically; the operator must pick the matching Provider
    result explicitly. A `PayrollRun` whose Restaurant has no `legal_entity_id`
    on file yet is not rejected here (a data-readiness gap, not a proven
    mismatch) — never guessed either way."""


def reconcile(
    session: Session, *, snapshot_id: int, payroll_run_id: int, created_by: str,
) -> m.CompensationReconciliation:
    """Idempotent per (snapshot, run) pair — a repeated call returns the
    existing reconciliation pass unchanged (its lines, and any
    note/resolution already recorded on them, are never recreated or
    reopened). Does not commit."""

    if not created_by or not created_by.strip():
        raise ValueError("reconcile requires a non-empty created_by actor reference")

    snapshot = session.get(m.ApprovedCompensationSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError(f"ApprovedCompensationSnapshot {snapshot_id} does not exist")
    payroll_run = session.get(m.PayrollRun, payroll_run_id)
    if payroll_run is None:
        raise ValueError(f"PayrollRun {payroll_run_id} does not exist")

    restaurant = session.get(m.Restaurant, payroll_run.restaurant_id)
    if (
        restaurant is not None
        and restaurant.legal_entity_id is not None
        and restaurant.legal_entity_id != snapshot.legal_entity_id
    ):
        raise LegalEntityMismatchError(
            f"PayrollRun {payroll_run_id}'s Restaurant belongs to Legal Entity "
            f"{restaurant.legal_entity_id}, not Snapshot {snapshot_id}'s Legal Entity "
            f"{snapshot.legal_entity_id} — refusing to reconcile across Legal Entities"
        )

    existing = session.scalars(
        select(m.CompensationReconciliation).where(
            m.CompensationReconciliation.snapshot_id == snapshot_id,
            m.CompensationReconciliation.payroll_run_id == payroll_run_id,
        )
    ).first()
    if existing is not None:
        return existing

    reconciliation = m.CompensationReconciliation(
        snapshot_id=snapshot_id, payroll_run_id=payroll_run_id, created_by=created_by,
    )
    session.add(reconciliation)
    session.flush()

    provider_results_by_employee = {r.employee_id: r for r in payroll_run.employee_results}
    rfone_results_by_employee = {r.employee_id: r for r in snapshot.employee_results}
    all_employee_ids = set(rfone_results_by_employee) | set(provider_results_by_employee)

    for employee_id in sorted(all_employee_ids):
        rfone_result = rfone_results_by_employee.get(employee_id)
        provider_result = provider_results_by_employee.get(employee_id)

        rfone_components: dict[str, Decimal] = {}
        if rfone_result is not None:
            rfone_components["Regular Pay"] = rfone_result.regular_pay
            rfone_components["Tips"] = rfone_result.tips_amount
            rfone_components["Recognized Incentive"] = rfone_result.incentive_recognized_amount

        provider_components: dict[str, Decimal] = {}
        unmatched_provider_facts: list[m.PayrollEarningFact] = []
        if provider_result is not None:
            for fact in provider_result.earning_facts:
                matched_label = next(
                    (
                        label
                        for label, types in _COMPONENT_EARNING_TYPES.items()
                        if fact.earning_type.upper() in types
                    ),
                    None,
                )
                amount = Decimal(fact.amount_minor) / Decimal(100)
                if matched_label is None:
                    unmatched_provider_facts.append(fact)
                else:
                    provider_components[matched_label] = (
                        provider_components.get(matched_label, Decimal("0")) + amount
                    )

        for label in sorted(set(rfone_components) | set(provider_components)):
            rfone_value = rfone_components.get(label)
            provider_value = provider_components.get(label)
            if rfone_value is None:
                status = STATUS_MISSING_IN_RFONE
            elif provider_value is None:
                status = STATUS_MISSING_IN_PROVIDER
            elif rfone_value.quantize(_CENTS) == provider_value.quantize(_CENTS):
                status = STATUS_MATCH
            else:
                status = STATUS_DIFFERENT
            session.add(
                m.CompensationReconciliationLine(
                    reconciliation_id=reconciliation.id,
                    employee_id=employee_id,
                    component_label=label,
                    rfone_value=rfone_value,
                    provider_value=provider_value,
                    status=status,
                )
            )

        for fact in unmatched_provider_facts:
            session.add(
                m.CompensationReconciliationLine(
                    reconciliation_id=reconciliation.id,
                    employee_id=employee_id,
                    component_label=f"Provider: {fact.source_label}",
                    rfone_value=None,
                    provider_value=Decimal(fact.amount_minor) / Decimal(100),
                    status=STATUS_MISSING_IN_RFONE,
                )
            )

    session.flush()
    return reconciliation


def annotate_reconciliation_line(
    session: Session,
    *,
    line_id: int,
    note: str | None = None,
    resolution_status: str | None = None,
    resolved_by: str | None = None,
) -> m.CompensationReconciliationLine:
    """Records a human explanation and/or resolution for one reconciliation
    line. `resolution_status` moving away from `OPEN` requires a non-empty
    `resolved_by`. Does not commit."""

    line = session.get(m.CompensationReconciliationLine, line_id)
    if line is None:
        raise ValueError(f"CompensationReconciliationLine {line_id} does not exist")

    if note is not None:
        line.note = note
    if resolution_status is not None:
        if resolution_status not in _RESOLUTION_STATUSES:
            raise ValueError(f"invalid resolution_status {resolution_status!r}")
        if resolution_status != "OPEN" and (not resolved_by or not resolved_by.strip()):
            raise ValueError("annotate_reconciliation_line requires resolved_by when resolving")
        line.resolution_status = resolution_status
        if resolution_status != "OPEN":
            line.resolved_by = resolved_by
            line.resolved_at = datetime.now(UTC)

    session.flush()
    return line


def get_reconciliation(session: Session, reconciliation_id: int) -> m.CompensationReconciliation | None:
    return session.get(m.CompensationReconciliation, reconciliation_id)


def get_reconciliation_by_pair(
    session: Session, *, snapshot_id: int, payroll_run_id: int,
) -> m.CompensationReconciliation | None:
    return session.scalars(
        select(m.CompensationReconciliation).where(
            m.CompensationReconciliation.snapshot_id == snapshot_id,
            m.CompensationReconciliation.payroll_run_id == payroll_run_id,
        )
    ).first()


def list_reconciliations_for_snapshot(
    session: Session, *, snapshot_id: int,
) -> list[m.CompensationReconciliation]:
    return list(
        session.scalars(
            select(m.CompensationReconciliation)
            .where(m.CompensationReconciliation.snapshot_id == snapshot_id)
            .order_by(m.CompensationReconciliation.created_at)
        ).all()
    )
