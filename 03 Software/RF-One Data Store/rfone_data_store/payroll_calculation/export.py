"""Payroll Handoff Connector — V1 manual implementation (`01 Domains/Cross
Domain/Personnel Management/Compensation/PAYROLL_HANDOFF_CONNECTOR.md`: "A
human operator entering RF-One's approved values into ADP or another
Payroll Provider is a valid Connector implementation... Do not assume,
require, or design around the Connector having an API").

Builds a per-Employee export view of one `ApprovedCompensationSnapshot` for
a human operator to read/transcribe (or download as a table), and records
the operator's confirmation that the communication to the Payroll Provider
actually happened (`CompensationExportConfirmation`). Recording a
confirmation is never itself evidence that the Payroll Provider processed
or paid anything — see `rfone_data_store.payroll_calculation.reconciliation`
for recording and comparing what the Provider actually returned."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .approval import STATUS_APPROVED

UTC = timezone.utc

STATUS_EXPORTED = "EXPORTED"


class SnapshotNotFoundError(ValueError):
    """Raised when the requested `ApprovedCompensationSnapshot` does not exist."""


class SnapshotNotApprovedError(ValueError):
    """Raised when attempting to confirm communication for a run that is
    not (or no longer) eligible — never `OPEN`/`CALCULATED` (nothing was
    approved yet) and never `CLOSED`. Re-communication of an already
    `EXPORTED` run is allowed (see `confirm_manual_communication`)."""


@dataclass(frozen=True)
class ExportRow:
    """One Employee's row of the manual export view — everything a human
    operator needs to transcribe into the Payroll Provider, plus whether
    RF-One already has a resolved provider employee-ID mapping for them."""

    employee_id: int
    employee_display_name: str
    legal_entity_id: int
    legal_entity_name: str
    period_start: datetime
    period_end: datetime
    provider_external_employee_key: str | None
    provider_mapping_status: str  # RESOLVED | MISSING
    regular_hours: Decimal
    regular_pay: Decimal
    tips_amount: Decimal
    incentive_recognized_amount: Decimal
    tip_credit_makeup_amount: Decimal | None  # None = to be completed by the Payroll Provider
    bonus_amount: Decimal
    gross_pay: Decimal


def _resolve_provider_mapping(session: Session, *, employee_id: int) -> tuple[str | None, str]:
    """Looks up any RESOLVED `PayrollProviderEmployeeIdentity` row for this
    Employee. That mapping is provider+Restaurant-scoped, not Legal-Entity-
    scoped (an Employee may be mapped through any Restaurant they work at)
    — this reports the first RESOLVED mapping found and flags the row as
    MISSING when none exists, never inventing one."""

    mapping = session.scalars(
        select(m.PayrollProviderEmployeeIdentity).where(
            m.PayrollProviderEmployeeIdentity.employee_id == employee_id,
            m.PayrollProviderEmployeeIdentity.mapping_status == "RESOLVED",
        )
    ).first()
    if mapping is None:
        return None, "MISSING"
    return mapping.external_employee_key, "RESOLVED"


def build_export_rows(session: Session, *, snapshot_id: int) -> list[ExportRow]:
    snapshot = session.get(m.ApprovedCompensationSnapshot, snapshot_id)
    if snapshot is None:
        raise SnapshotNotFoundError(f"ApprovedCompensationSnapshot {snapshot_id} does not exist")

    legal_entity = session.get(m.LegalEntity, snapshot.legal_entity_id)
    legal_entity_name = legal_entity.legal_name if legal_entity is not None else (
        f"Legal Entity {snapshot.legal_entity_id}"
    )

    rows: list[ExportRow] = []
    for result in sorted(snapshot.employee_results, key=lambda r: r.employee_id):
        employee = session.get(m.Employee, result.employee_id)
        employee_display_name = (
            employee.display_name if employee is not None else f"Employee {result.employee_id}"
        )
        provider_key, mapping_status = _resolve_provider_mapping(session, employee_id=result.employee_id)
        rows.append(
            ExportRow(
                employee_id=result.employee_id,
                employee_display_name=employee_display_name,
                legal_entity_id=snapshot.legal_entity_id,
                legal_entity_name=legal_entity_name,
                period_start=snapshot.period_start,
                period_end=snapshot.period_end,
                provider_external_employee_key=provider_key,
                provider_mapping_status=mapping_status,
                regular_hours=result.regular_hours,
                regular_pay=result.regular_pay,
                tips_amount=result.tips_amount,
                incentive_recognized_amount=result.incentive_recognized_amount,
                tip_credit_makeup_amount=result.tip_credit_makeup_amount,
                bonus_amount=result.bonus_amount,
                gross_pay=result.gross_pay,
            )
        )
    return rows


def confirm_manual_communication(
    session: Session,
    *,
    snapshot_id: int,
    communicated_by: str,
    communicated_at: datetime | None = None,
    reference: str | None = None,
    note: str | None = None,
) -> m.CompensationExportConfirmation:
    """Records one human confirmation that this Snapshot's data was
    communicated to the Payroll Provider. The first confirmation for an
    `APPROVED` run transitions it to `EXPORTED`; a further confirmation
    (e.g. a re-communication) is still recorded but never changes the
    status again. Does not commit."""

    snapshot = session.get(m.ApprovedCompensationSnapshot, snapshot_id)
    if snapshot is None:
        raise SnapshotNotFoundError(f"ApprovedCompensationSnapshot {snapshot_id} does not exist")
    if not communicated_by or not communicated_by.strip():
        raise ValueError(
            "confirm_manual_communication requires a non-empty communicated_by actor reference"
        )

    run = session.get(m.CompensationPreparationRun, snapshot.compensation_preparation_run_id)
    if run is not None and run.status not in (STATUS_APPROVED, STATUS_EXPORTED):
        raise SnapshotNotApprovedError(
            f"CompensationPreparationRun {run.id} is not eligible for export communication "
            f"(status={run.status!r})"
        )

    confirmation = m.CompensationExportConfirmation(
        snapshot_id=snapshot_id,
        communicated_by=communicated_by,
        communicated_at=communicated_at or datetime.now(UTC),
        reference=reference,
        note=note,
    )
    session.add(confirmation)

    if run is not None and run.status == STATUS_APPROVED:
        run.status = STATUS_EXPORTED

    session.flush()
    return confirmation


def get_export_confirmations(
    session: Session, *, snapshot_id: int,
) -> list[m.CompensationExportConfirmation]:
    return list(
        session.scalars(
            select(m.CompensationExportConfirmation)
            .where(m.CompensationExportConfirmation.snapshot_id == snapshot_id)
            .order_by(m.CompensationExportConfirmation.communicated_at)
        ).all()
    )
