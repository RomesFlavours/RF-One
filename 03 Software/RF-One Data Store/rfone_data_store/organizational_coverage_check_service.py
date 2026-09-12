"""Organizational Coverage Check (TASK_ORG_CHART_ADMIN_PAGE §12-13).

Answers, for every Process/Phase RF-One actually has evidence of (from
configured `ProcessOwnership` rows AND from `AttentionItem` rows that have
actually been raised at runtime — there is no canonical, exhaustive registry
of "every Process that exists," so this is deliberately evidence-based,
never invented, per task §12's own "NON inventare Business Rules mancanti.
Se manca semantica sufficiente: segnalare UNKNOWN / NEEDS CONFIGURATION"):

    "If this Process/Phase raised Attention right now, is there a Position
    that can actually receive it?"

Foundation, not integration — no Domain package is imported here. Every
classification below is derived strictly from `organizational_
responsibility_service`/`attention_service`'s own existing resolution
logic; this module adds no new resolution rule of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import attention_service as att_svc
from . import models as m
from . import organizational_responsibility_service as org_svc

UTC = timezone.utc

STATUS_FULLY_COVERED = "FULLY_COVERED"
STATUS_COVERED_VIA_BACKUP = "COVERED_VIA_BACKUP"
STATUS_COVERED_VIA_FALLBACK = "COVERED_VIA_FALLBACK"
STATUS_GAP = "GAP"
STATUS_NO_OWNER = "NO_OWNER"
STATUS_AMBIGUOUS_OWNER = "AMBIGUOUS_OWNER"


@dataclass(frozen=True)
class ProcessCoverageEntry:
    domain: str
    module: str | None
    process_name: str
    phase: str | None
    status: str
    owner_position: "m.Position | None"
    resolution: "org_svc.EffectiveRecipientResolution | None"
    detail: str


@dataclass(frozen=True)
class CoverageCheckResult:
    entries: list[ProcessCoverageEntry] = field(default_factory=list)
    positions_missing_required_backup: list["m.Position"] = field(default_factory=list)
    unresolved_attention_items: list["m.AttentionItem"] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        c = {
            "processes_known": len(self.entries),
            STATUS_FULLY_COVERED: 0, STATUS_COVERED_VIA_BACKUP: 0, STATUS_COVERED_VIA_FALLBACK: 0,
            STATUS_GAP: 0, STATUS_NO_OWNER: 0, STATUS_AMBIGUOUS_OWNER: 0,
        }
        for e in self.entries:
            c[e.status] = c.get(e.status, 0) + 1
        c["partial_coverage"] = c[STATUS_COVERED_VIA_BACKUP] + c[STATUS_COVERED_VIA_FALLBACK]
        c["unowned_responsibilities"] = c[STATUS_NO_OWNER] + c[STATUS_AMBIGUOUS_OWNER] + c[STATUS_GAP]
        c["fallback_to_organizational_fallback"] = c[STATUS_COVERED_VIA_FALLBACK]
        c["positions_missing_required_backup"] = len(self.positions_missing_required_backup)
        c["unresolved_attention_items"] = len(self.unresolved_attention_items)
        return c


def _known_process_keys(session: Session) -> set[tuple[str, str | None, str, str | None]]:
    """Every (domain, module, process_name, phase) this Foundation has ANY
    evidence of — from configured ownership, or from an Attention Item that
    was actually raised. Never a guess at processes RF-One has no evidence
    for at all."""
    keys: set[tuple[str, str | None, str, str | None]] = set()
    for row in session.scalars(select(m.ProcessOwnership)):
        keys.add((row.domain, row.module, row.process_name, row.phase))
    for row in session.scalars(
        select(m.AttentionItem).where(m.AttentionItem.source_process_name.is_not(None))
    ):
        keys.add((row.source_domain, row.source_module, row.source_process_name, row.source_phase))
    return keys


def run_organizational_coverage_check(session: Session, *, now: datetime | None = None) -> CoverageCheckResult:
    now = now or datetime.now(UTC)
    entries: list[ProcessCoverageEntry] = []

    for domain, module, process_name, phase in sorted(_known_process_keys(session), key=lambda k: (k[0], k[2], k[3] or "")):
        owner_resolution = org_svc.resolve_process_owner(
            session, domain=domain, process_name=process_name, module=module, phase=phase,
        )
        resolution = org_svc.resolve_effective_recipient(
            session, domain=domain, process_name=process_name, module=module, phase=phase, now=now,
        )

        ownership_issue = None
        if owner_resolution.position is None:
            ownership_issue = (
                STATUS_AMBIGUOUS_OWNER if owner_resolution.unresolved_reason and "Ambiguous" in owner_resolution.unresolved_reason
                else STATUS_NO_OWNER
            )

        if resolution.acting_identity is not None:
            status = {
                org_svc.RESOLUTION_PATH_DIRECT_OCCUPANT: STATUS_FULLY_COVERED,
                org_svc.RESOLUTION_PATH_TEMPORARY_COVERAGE: STATUS_FULLY_COVERED,
                org_svc.RESOLUTION_PATH_BACKUP_POSITION: STATUS_COVERED_VIA_BACKUP,
                org_svc.RESOLUTION_PATH_ORGANIZATIONAL_FALLBACK: STATUS_COVERED_VIA_FALLBACK,
            }.get(resolution.resolution_path, STATUS_GAP)
            detail = f"Resolves to {resolution.acting_identity.display_name!r} via {resolution.resolution_path}."
            if ownership_issue is not None:
                detail = f"{ownership_issue}, but {detail[0].lower()}{detail[1:]}"
        else:
            # No effective recipient at all — the underlying reason (no
            # owner / ambiguous owner / vacant with no working backup or
            # fallback) is itself the finding; never a generic GAP that
            # hides which of those it actually was.
            status = ownership_issue or STATUS_GAP
            detail = resolution.unresolved_reason or owner_resolution.unresolved_reason or "Unresolved."

        entries.append(ProcessCoverageEntry(
            domain=domain, module=module, process_name=process_name, phase=phase, status=status,
            owner_position=owner_resolution.position, resolution=resolution, detail=detail,
        ))

    positions_missing_backup = [
        p for p in session.scalars(select(m.Position).where(m.Position.backup_required.is_(True)))
        if not org_svc.list_position_backups(session, position=p)
    ]

    return CoverageCheckResult(
        entries=entries, positions_missing_required_backup=positions_missing_backup,
        unresolved_attention_items=att_svc.list_unresolved_routing(session),
    )
