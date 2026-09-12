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

# --- Two INDEPENDENT dimensions (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §2) ---
#
# DELIVERY COVERAGE — "will the Attention actually reach somebody?"
STATUS_FULLY_COVERED = "FULLY_COVERED"
STATUS_COVERED_VIA_BACKUP = "COVERED_VIA_BACKUP"
STATUS_COVERED_VIA_FALLBACK = "COVERED_VIA_FALLBACK"
STATUS_GAP = "GAP"  # nothing resolves at all — genuinely undelivered.
DELIVERY_STATUSES = (STATUS_FULLY_COVERED, STATUS_COVERED_VIA_BACKUP, STATUS_COVERED_VIA_FALLBACK, STATUS_GAP)

# ORGANIZATIONAL CONFIGURATION HEALTH — "does a correctly configured PRIMARY
# ownership actually exist?" — independent of whether Backup/Fallback
# happens to still deliver the Attention today. A Fallback resolving an
# Attention does NOT make ownership CONFIGURED; it only changes delivery.
OWNERSHIP_CONFIGURED = "CONFIGURED"
OWNERSHIP_NO_OWNER = "NO_OWNER"
OWNERSHIP_AMBIGUOUS = "AMBIGUOUS_OWNER"
OWNERSHIP_HEALTHS = (OWNERSHIP_CONFIGURED, OWNERSHIP_NO_OWNER, OWNERSHIP_AMBIGUOUS)

# Back-compat aliases: earlier callers imported STATUS_NO_OWNER/STATUS_
# AMBIGUOUS_OWNER as if they were DELIVERY statuses (task's own prior
# report flagged exactly this conflation as the issue being fixed here) —
# kept pointing at the new, correctly-dimensioned constants so no import
# breaks, never re-used as a `status` value by this module itself.
STATUS_NO_OWNER = OWNERSHIP_NO_OWNER
STATUS_AMBIGUOUS_OWNER = OWNERSHIP_AMBIGUOUS


@dataclass(frozen=True)
class ProcessCoverageEntry:
    domain: str
    module: str | None
    process_name: str
    phase: str | None
    status: str
    """DELIVERY COVERAGE only — one of `DELIVERY_STATUSES`."""
    ownership_health: str
    """ORGANIZATIONAL CONFIGURATION HEALTH only — one of `OWNERSHIP_HEALTHS`.
    Independent of `status`: a Process can be `COVERED_VIA_FALLBACK` (someone
    receives it) while `ownership_health` is still `NO_OWNER` (nobody is
    actually, correctly configured as its owner) — both must be visible at
    once, never collapsed into a single field."""
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
            # Delivery dimension.
            STATUS_FULLY_COVERED: 0, STATUS_COVERED_VIA_BACKUP: 0, STATUS_COVERED_VIA_FALLBACK: 0, STATUS_GAP: 0,
            # Ownership-health dimension — counted independently of delivery,
            # so a Process rescued by Fallback still counts here (task §2's
            # own explicit requirement: Fallback must never hide this).
            OWNERSHIP_CONFIGURED: 0, OWNERSHIP_NO_OWNER: 0, OWNERSHIP_AMBIGUOUS: 0,
        }
        for e in self.entries:
            c[e.status] = c.get(e.status, 0) + 1
            c[e.ownership_health] = c.get(e.ownership_health, 0) + 1
        c["partial_coverage"] = c[STATUS_COVERED_VIA_BACKUP] + c[STATUS_COVERED_VIA_FALLBACK]
        # "unowned_responsibilities" is now an ORGANIZATIONAL HEALTH count
        # (no-owner or ambiguous-owner Processes), independent of whether
        # they are currently delivered via Backup/Fallback — never masked by
        # delivery succeeding.
        c["unowned_responsibilities"] = c[OWNERSHIP_NO_OWNER] + c[OWNERSHIP_AMBIGUOUS]
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

        # ORGANIZATIONAL CONFIGURATION HEALTH — structured, never string-
        # matched (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §3: no more `"Ambiguous"
        # in unresolved_reason`). Determined purely from `owner_resolution.
        # unresolved_code`, which `resolve_process_owner` sets to an
        # enumerated constant, never inferred from message text.
        ownership_health = {
            org_svc.PROCESS_OWNER_NOT_FOUND: OWNERSHIP_NO_OWNER,
            org_svc.PROCESS_OWNER_AMBIGUOUS: OWNERSHIP_AMBIGUOUS,
        }.get(owner_resolution.unresolved_code, OWNERSHIP_CONFIGURED)

        # DELIVERY COVERAGE — purely "did an effective recipient resolve, and
        # how" (§2: never downgraded/conflated by an ownership-health issue;
        # a Fallback-delivered Process is still FULLY... no, COVERED_VIA_
        # FALLBACK here, full stop — its ownership problem is reported
        # separately via `ownership_health`, not by relabelling delivery).
        if resolution.acting_identity is not None:
            status = {
                org_svc.RESOLUTION_PATH_DIRECT_OCCUPANT: STATUS_FULLY_COVERED,
                org_svc.RESOLUTION_PATH_TEMPORARY_COVERAGE: STATUS_FULLY_COVERED,
                org_svc.RESOLUTION_PATH_BACKUP_POSITION: STATUS_COVERED_VIA_BACKUP,
                org_svc.RESOLUTION_PATH_ORGANIZATIONAL_FALLBACK: STATUS_COVERED_VIA_FALLBACK,
            }.get(resolution.resolution_path, STATUS_GAP)
            detail = f"Resolves to {resolution.acting_identity.display_name!r} via {resolution.resolution_path}."
            if ownership_health != OWNERSHIP_CONFIGURED:
                # Both facts stated side by side, never merged into one
                # label — delivery succeeding must not hide the health gap.
                detail = f"{detail} Organizational health: {ownership_health} (primary ownership not correctly configured)."
        else:
            # No effective recipient at all — the underlying reason (no
            # owner / ambiguous owner / vacant with no working backup or
            # fallback) is itself the finding; never a generic GAP that
            # hides which of those it actually was.
            status = STATUS_GAP
            detail = resolution.unresolved_reason or owner_resolution.unresolved_reason or "Unresolved."

        entries.append(ProcessCoverageEntry(
            domain=domain, module=module, process_name=process_name, phase=phase, status=status,
            ownership_health=ownership_health,
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
