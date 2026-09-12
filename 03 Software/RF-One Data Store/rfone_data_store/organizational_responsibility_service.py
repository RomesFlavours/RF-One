"""Shared Organizational Responsibility service (TASK_ATTENTION_ORG_RUNTIME;
`00 Core/Organizational Responsibility.md`).

The ONE place any Domain resolves "which Position owns this Process/Phase,
who currently occupies that Position, and who is the effective recipient
right now (accounting for active temporary coverage)" — never re-derived
per-Domain, exactly the same discipline `authority_service.py` already
establishes for Authority.

Deliberately lives at the top level of `rfone_data_store`, same placement
rationale as `authority_service.py`/`acting_identity_service.py`: this
substrate must be usable by any Domain (Tips, Compensation, Purchasing,
Selection, ...), not owned by whichever Domain integrates it first. THIS
MODULE INTEGRATES NO DOMAIN — foundation, not integration; no Tips (or any
other Domain) code is imported or referenced here.

Escalation policy (Core doc 12 §9: "Core does not fix a universal
escalation rule") is deliberately NOT implemented here: `resolve_effective_
recipient` determines the current PRIMARY recipient only (owning Position's
occupant, or its active temporary coverage) — if that is unresolved (a
vacant Position with no active coverage), this module reports exactly that,
it never falls back to a hardcoded "escalate to the superior" or any other
guessed target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m

UTC = timezone.utc


class OrganizationalResponsibilityError(ValueError):
    """Raised for a malformed call (an invalid scope_type, or a scope_type
    requiring a value with none supplied) — always a caller bug, never a
    normal "not resolved" outcome. Callers must not catch this to mean
    "vacant"/"unresolved" — see `ResolutionResult` for that."""


@dataclass(frozen=True)
class ScopeContext:
    """An explicit scope to resolve against — the same
    Corporate/Brand/Legal Entity/Operational Unit/Restaurant/Operational
    Area/Domain/Module/Process/Process Phase/Global dimensions
    `models.POSITION_SCOPE_KINDS` defines. `scope_type=None` means the
    caller supplies no context at all (only GLOBAL/unscoped Positions or
    Process Ownerships can match)."""

    scope_type: str | None = None
    scope_id: int | None = None
    scope_key: str | None = None


def validate_scope_value(*, scope_type: str, scope_id: int | None, scope_key: str | None) -> None:
    if scope_type not in m.POSITION_SCOPE_KINDS:
        raise OrganizationalResponsibilityError(
            f"Invalid scope_type {scope_type!r} — must be one of {m.POSITION_SCOPE_KINDS}."
        )
    if scope_type == m.POSITION_SCOPE_GLOBAL:
        return
    if scope_type in m.POSITION_SCOPE_ID_KINDS and scope_id is None:
        raise OrganizationalResponsibilityError(f"scope_type={scope_type!r} requires an explicit scope_id.")
    if scope_type in m.POSITION_SCOPE_KEY_KINDS and not scope_key:
        raise OrganizationalResponsibilityError(f"scope_type={scope_type!r} requires a non-empty scope_key.")


# ---------------------------------------------------------------------------
# Position / Scope / Occupant / Temporary Coverage
# ---------------------------------------------------------------------------


def create_position(
    session: Session, *, name: str, description: str | None = None, parent: "m.Position | None" = None,
) -> "m.Position":
    if not name:
        raise OrganizationalResponsibilityError("create_position() requires a non-empty name.")
    position = m.Position(
        name=name, description=description, parent_position_id=parent.id if parent is not None else None,
    )
    session.add(position)
    session.flush()
    return position


def add_position_scope(
    session: Session, *, position: "m.Position", scope_type: str, scope_id: int | None = None,
    scope_key: str | None = None,
) -> "m.PositionScope":
    validate_scope_value(scope_type=scope_type, scope_id=scope_id, scope_key=scope_key)
    scope = m.PositionScope(position_id=position.id, scope_type=scope_type, scope_id=scope_id, scope_key=scope_key)
    session.add(scope)
    session.flush()
    return scope


def _scope_matches(position_scopes: list["m.PositionScope"], context: ScopeContext | None) -> bool:
    """True if `position_scopes` (a Position's own set of scope statements,
    OR a single-item list representing a `ProcessOwnership`'s own override)
    covers `context`. An EMPTY scope set is treated as globally applicable
    (`Organizational Responsibility.md` never requires a Position to state
    a scope) — same for an explicit GLOBAL row. Otherwise, matches if ANY
    one scope statement matches `context`'s own type+value (a Position may
    legitimately cover more than one Restaurant, etc. — the union of its
    rows is its perimeter). When the CALLER supplies no context at all
    (`context is None`), only an empty scope set or an explicit GLOBAL row
    matches — a Position scoped to one specific Restaurant must never match
    a request that names no Restaurant at all (never guess)."""
    if not position_scopes:
        return True
    if context is None:
        return any(s.scope_type == m.POSITION_SCOPE_GLOBAL for s in position_scopes)
    for s in position_scopes:
        if s.scope_type == m.POSITION_SCOPE_GLOBAL:
            return True
        if s.scope_type != context.scope_type:
            continue
        if s.scope_type in m.POSITION_SCOPE_ID_KINDS and s.scope_id == context.scope_id:
            return True
        if s.scope_type in m.POSITION_SCOPE_KEY_KINDS and s.scope_key == context.scope_key:
            return True
    return False


def position_matches_scope(session: Session, *, position: "m.Position", context: ScopeContext | None) -> bool:
    scopes = list(session.scalars(select(m.PositionScope).where(m.PositionScope.position_id == position.id)))
    return _scope_matches(scopes, context)


def assign_occupant(
    session: Session, *, position: "m.Position", occupant: "m.ActingIdentity", valid_from: datetime,
    valid_to: datetime | None = None,
) -> "m.PositionAssignment":
    """Creates a new occupancy row — never overwrites/deletes a prior one
    (Historical Integrity; `Organizational Responsibility.md` §3). Ending a
    prior occupant's tenure (e.g. before assigning a new one) is the
    caller's own explicit act (set that row's `valid_to`), never inferred
    or silently done here."""
    assignment = m.PositionAssignment(
        position_id=position.id, acting_identity_id=occupant.id, valid_from=valid_from, valid_to=valid_to,
    )
    session.add(assignment)
    session.flush()
    return assignment


def resolve_current_occupant(
    session: Session, *, position: "m.Position", now: datetime | None = None,
) -> "m.ActingIdentity | None":
    """The Acting Identity currently occupying `position`, or `None` if
    VACANT (task §5 — a normal, expected state, never an error)."""
    now = now or datetime.now(UTC)
    assignment = session.scalars(
        select(m.PositionAssignment)
        .where(
            m.PositionAssignment.position_id == position.id, m.PositionAssignment.valid_from <= now,
            (m.PositionAssignment.valid_to.is_(None)) | (m.PositionAssignment.valid_to > now),
        )
        .order_by(m.PositionAssignment.valid_from.desc())
    ).first()
    return assignment.acting_identity if assignment is not None else None


def create_temporary_coverage(
    session: Session, *, covered_position: "m.Position", valid_from: datetime, valid_to: datetime | None = None,
    delegate_position: "m.Position | None" = None, delegate_acting_identity: "m.ActingIdentity | None" = None,
    granted_by: "m.ActingIdentity | None" = None,
) -> "m.PositionTemporaryCoverage":
    if (delegate_position is None) == (delegate_acting_identity is None):
        raise OrganizationalResponsibilityError(
            "create_temporary_coverage() requires exactly one of delegate_position/delegate_acting_identity."
        )
    coverage = m.PositionTemporaryCoverage(
        covered_position_id=covered_position.id,
        delegate_position_id=delegate_position.id if delegate_position is not None else None,
        delegate_acting_identity_id=delegate_acting_identity.id if delegate_acting_identity is not None else None,
        granted_by_identity_id=granted_by.id if granted_by is not None else None,
        valid_from=valid_from, valid_to=valid_to,
    )
    session.add(coverage)
    session.flush()
    return coverage


def revoke_temporary_coverage(
    session: Session, *, coverage: "m.PositionTemporaryCoverage", now: datetime | None = None,
) -> "m.PositionTemporaryCoverage":
    coverage.revoked_at = now or datetime.now(UTC)
    session.flush()
    return coverage


def resolve_active_coverage(
    session: Session, *, position: "m.Position", now: datetime | None = None,
) -> "m.PositionTemporaryCoverage | None":
    """The currently active temporary coverage for `position`, if any. If
    more than one is technically active at once (a configuration situation
    this Foundation does not forbid outright), the most recently CREATED
    one wins, deterministically — mirroring `payroll/payment_execution.py`'s
    own `approved_provider_at` precedent for the identical kind of tie."""
    now = now or datetime.now(UTC)
    candidates = list(
        session.scalars(
            select(m.PositionTemporaryCoverage).where(
                m.PositionTemporaryCoverage.covered_position_id == position.id,
                m.PositionTemporaryCoverage.revoked_at.is_(None),
                m.PositionTemporaryCoverage.valid_from <= now,
                (m.PositionTemporaryCoverage.valid_to.is_(None)) | (m.PositionTemporaryCoverage.valid_to > now),
            )
        )
    )
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c.created_at, c.id), reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# Process Ownership
# ---------------------------------------------------------------------------


def set_process_ownership(
    session: Session, *, domain: str, process_name: str, position: "m.Position", module: str | None = None,
    phase: str | None = None, scope_type: str | None = None, scope_id: int | None = None,
    scope_key: str | None = None,
) -> "m.ProcessOwnership":
    if not domain or not process_name:
        raise OrganizationalResponsibilityError("set_process_ownership() requires domain and process_name.")
    if phase is not None and phase not in m.PROCESS_PHASES:
        raise OrganizationalResponsibilityError(f"Invalid phase {phase!r} — must be one of {m.PROCESS_PHASES} or None.")
    if scope_type is not None:
        validate_scope_value(scope_type=scope_type, scope_id=scope_id, scope_key=scope_key)
    ownership = m.ProcessOwnership(
        domain=domain, module=module, process_name=process_name, phase=phase, position_id=position.id,
        scope_type=scope_type, scope_id=scope_id, scope_key=scope_key,
    )
    session.add(ownership)
    session.flush()
    return ownership


@dataclass(frozen=True)
class ProcessOwnerResolution:
    position: "m.Position | None"
    unresolved_reason: str | None = None


def resolve_process_owner(
    session: Session, *, domain: str, process_name: str, module: str | None = None, phase: str | None = None,
    context: ScopeContext | None = None,
) -> ProcessOwnerResolution:
    """Resolves the single Position responsible for (`domain`, `module`,
    `process_name`, `phase`) — disambiguated by `context` only when more
    than one candidate Position actually exists for it; never guesses among
    multiple genuine candidates (task §9: unresolved stays unresolved).

    When the caller supplies no `context` at all, scope is NOT used to
    filter candidates (there being no context to filter against) — a
    Position's own Scope exists to disambiguate BETWEEN several candidate
    owners of the same Process, not to gate resolution when the caller
    legitimately has nothing to disambiguate by (e.g. a single-Restaurant
    deployment). A genuine conflict (more than one distinct Position still
    matching) is still always caught below, context or not."""
    base_query = select(m.ProcessOwnership).where(
        m.ProcessOwnership.domain == domain, m.ProcessOwnership.process_name == process_name,
    )
    if module is not None:
        base_query = base_query.where(m.ProcessOwnership.module == module)

    exact_phase = list(session.scalars(base_query.where(m.ProcessOwnership.phase == phase))) if phase else []
    whole_process = list(session.scalars(base_query.where(m.ProcessOwnership.phase.is_(None))))
    # Exact-phase ownership takes precedence over whole-process ownership;
    # whole-process rows are the fallback only when no phase-specific row matches.
    candidates = exact_phase or whole_process

    if context is None:
        matching = candidates
    else:
        matching = []
        for row in candidates:
            if row.scope_type is not None:
                row_scope = [m.PositionScope(scope_type=row.scope_type, scope_id=row.scope_id, scope_key=row.scope_key)]
                if _scope_matches(row_scope, context):
                    matching.append(row)
            else:
                position = session.get(m.Position, row.position_id)
                if position_matches_scope(session, position=position, context=context):
                    matching.append(row)

    if not matching:
        return ProcessOwnerResolution(
            position=None,
            unresolved_reason=(
                f"No Process Ownership found for domain={domain!r} process_name={process_name!r} "
                f"phase={phase!r} matching the given scope."
            ),
        )
    distinct_positions = {row.position_id for row in matching}
    if len(distinct_positions) > 1:
        return ProcessOwnerResolution(
            position=None,
            unresolved_reason=(
                f"Ambiguous Process Ownership: {len(distinct_positions)} different Positions match "
                f"domain={domain!r} process_name={process_name!r} phase={phase!r} for the given scope."
            ),
        )
    return ProcessOwnerResolution(position=session.get(m.Position, matching[0].position_id))


# ---------------------------------------------------------------------------
# Effective recipient
# ---------------------------------------------------------------------------


RESOLUTION_PATH_DIRECT_OCCUPANT = "DIRECT_OCCUPANT"
RESOLUTION_PATH_TEMPORARY_COVERAGE = "TEMPORARY_COVERAGE"
RESOLUTION_PATH_BACKUP_POSITION = "BACKUP_POSITION"
RESOLUTION_PATH_ORGANIZATIONAL_FALLBACK = "ORGANIZATIONAL_FALLBACK"


@dataclass(frozen=True)
class EffectiveRecipientResolution:
    acting_identity: "m.ActingIdentity | None"
    owner_position: "m.Position | None"
    coverage_applied: "m.PositionTemporaryCoverage | None"
    resolution_path: str | None = None
    used_backup_position: "m.Position | None" = None
    used_fallback_position: "m.Position | None" = None
    unresolved_reason: str | None = None


def _resolve_via_coverage_or_occupant(
    session: Session, *, position: "m.Position", now: datetime,
) -> tuple["m.ActingIdentity | None", str | None, "m.PositionTemporaryCoverage | None"]:
    """`position`'s own resolution, ONE position at a time: its active
    Temporary Coverage takes precedence over its own Occupant (task §9);
    falls back to its Occupant otherwise. Returns `(identity, path, coverage)`
    — `identity is None` means this one Position could not resolve on its
    own (vacant, no coverage) — never recurses into anything beyond this
    single Position."""
    coverage = resolve_active_coverage(session, position=position, now=now)
    if coverage is not None:
        if coverage.delegate_acting_identity_id is not None:
            return coverage.delegate_acting_identity, RESOLUTION_PATH_TEMPORARY_COVERAGE, coverage
        delegate_occupant = resolve_current_occupant(session, position=coverage.delegate_position, now=now)
        if delegate_occupant is not None:
            return delegate_occupant, RESOLUTION_PATH_TEMPORARY_COVERAGE, coverage
        return None, None, coverage
    occupant = resolve_current_occupant(session, position=position, now=now)
    if occupant is not None:
        return occupant, RESOLUTION_PATH_DIRECT_OCCUPANT, None
    return None, None, None


def resolve_effective_recipient(
    session: Session, *, domain: str, process_name: str, module: str | None = None, phase: str | None = None,
    context: ScopeContext | None = None, now: datetime | None = None,
) -> EffectiveRecipientResolution:
    """Process/Phase -> Position owner -> applicable Scope -> current
    Occupant -> Temporary Coverage -> Backup Position chain ->
    Organizational Fallback Policy -> effective recipient (task §9/§13's
    full chain — TASK_ORG_CHART_ADMIN_PAGE extends the original chain with
    Backup Position and Organizational Fallback).

    Only ONE hop is followed at each step (a covering/backup/fallback
    Position's own Occupant or Temporary Coverage — never that Position's
    OWN backup chain, task §8's "NON inventare escalation automatica
    verticale universale"). The owning Position's ordered Backup Position
    list (`PositionBackup`, active rows, by `sequence`) is walked in order
    until one resolves; if none does, the Organizational Fallback Policy
    matching `context` (or GLOBAL) is tried; if that also cannot resolve,
    the item is reported unresolved, never assigned arbitrarily."""
    now = now or datetime.now(UTC)
    owner_resolution = resolve_process_owner(
        session, domain=domain, process_name=process_name, module=module, phase=phase, context=context,
    )
    owner_position = owner_resolution.position
    base_unresolved_reason = owner_resolution.unresolved_reason

    if owner_position is not None:
        identity, path, coverage = _resolve_via_coverage_or_occupant(session, position=owner_position, now=now)
        if identity is not None:
            return EffectiveRecipientResolution(
                acting_identity=identity, owner_position=owner_position, coverage_applied=coverage,
                resolution_path=path,
            )
        if coverage is not None:
            base_unresolved_reason = f"Position {owner_position.id}'s active Temporary Coverage delegate is itself vacant."

        for backup in list_position_backups(session, position=owner_position):
            backup_identity, _, backup_coverage = _resolve_via_coverage_or_occupant(
                session, position=backup.backup_position, now=now,
            )
            if backup_identity is not None:
                return EffectiveRecipientResolution(
                    acting_identity=backup_identity, owner_position=owner_position, coverage_applied=backup_coverage,
                    resolution_path=RESOLUTION_PATH_BACKUP_POSITION, used_backup_position=backup.backup_position,
                )
        if base_unresolved_reason is None:
            base_unresolved_reason = (
                f"Position {owner_position.id} ({owner_position.name!r}) is vacant, no active coverage, and its "
                "Backup Position chain (if any) did not resolve."
            )

    # Task §14: the Organizational Fallback Policy is the last resort
    # whenever NO responsible Position could be resolved AT ALL (no owner
    # found, ambiguous ownership) OR the owner was found but its own
    # Occupant/Coverage/Backup chain was exhausted — never only for the
    # "vacant owner" case. Still never a Core-level universal rule: only
    # applied if an organization has actually configured one (task §14).
    fallback_position = resolve_fallback_position(session, context=context)
    if fallback_position is not None:
        fallback_identity, _, fallback_coverage = _resolve_via_coverage_or_occupant(
            session, position=fallback_position, now=now,
        )
        if fallback_identity is not None:
            return EffectiveRecipientResolution(
                acting_identity=fallback_identity, owner_position=owner_position, coverage_applied=fallback_coverage,
                resolution_path=RESOLUTION_PATH_ORGANIZATIONAL_FALLBACK, used_fallback_position=fallback_position,
            )
        return EffectiveRecipientResolution(
            acting_identity=None, owner_position=owner_position, coverage_applied=None,
            used_fallback_position=fallback_position,
            unresolved_reason=(
                f"{base_unresolved_reason} The configured Organizational Fallback Position "
                f"{fallback_position.id} ({fallback_position.name!r}) is itself vacant."
            ),
        )

    return EffectiveRecipientResolution(
        acting_identity=None, owner_position=owner_position, coverage_applied=None,
        unresolved_reason=f"{base_unresolved_reason} No Organizational Fallback Policy applies either.",
    )


# ---------------------------------------------------------------------------
# Backup Position (TASK_ORG_CHART_ADMIN_PAGE §8) — distinct from Temporary Coverage.
# ---------------------------------------------------------------------------


def add_position_backup(
    session: Session, *, covered_position: "m.Position", backup_position: "m.Position", sequence: int | None = None,
) -> "m.PositionBackup":
    if covered_position.id == backup_position.id:
        raise OrganizationalResponsibilityError("A Position cannot be its own Backup Position.")
    if sequence is None:
        existing = list_position_backups(session, position=covered_position, include_inactive=True)
        sequence = (max((b.sequence for b in existing), default=0)) + 1
    backup = m.PositionBackup(
        covered_position_id=covered_position.id, backup_position_id=backup_position.id, sequence=sequence,
    )
    session.add(backup)
    session.flush()
    return backup


def list_position_backups(
    session: Session, *, position: "m.Position", include_inactive: bool = False,
) -> list["m.PositionBackup"]:
    stmt = select(m.PositionBackup).where(m.PositionBackup.covered_position_id == position.id)
    if not include_inactive:
        stmt = stmt.where(m.PositionBackup.is_active.is_(True))
    return list(session.scalars(stmt.order_by(m.PositionBackup.sequence)))


def deactivate_position_backup(session: Session, *, backup: "m.PositionBackup") -> "m.PositionBackup":
    backup.is_active = False
    session.flush()
    return backup


# ---------------------------------------------------------------------------
# Organizational Fallback Policy (TASK_ORG_CHART_ADMIN_PAGE §14) — company
# configuration, never a Core rule.
# ---------------------------------------------------------------------------


def set_organizational_fallback_policy(
    session: Session, *, fallback_position: "m.Position", scope_type: str = m.POSITION_SCOPE_GLOBAL,
    scope_id: int | None = None, scope_key: str | None = None,
) -> "m.OrganizationalFallbackPolicy":
    validate_scope_value(scope_type=scope_type, scope_id=scope_id, scope_key=scope_key)
    policy = m.OrganizationalFallbackPolicy(
        scope_type=scope_type, scope_id=scope_id, scope_key=scope_key, fallback_position_id=fallback_position.id,
    )
    session.add(policy)
    session.flush()
    return policy


def deactivate_organizational_fallback_policy(
    session: Session, *, policy: "m.OrganizationalFallbackPolicy",
) -> "m.OrganizationalFallbackPolicy":
    policy.is_active = False
    session.flush()
    return policy


def resolve_fallback_position(session: Session, *, context: ScopeContext | None) -> "m.Position | None":
    """The Organizational Fallback Position applicable to `context`, if any
    is configured — a scope-specific policy wins over a GLOBAL one; if
    several equally-specific policies exist, the most recently created one
    wins deterministically (same tie-break convention as `payroll/
    payment_execution.py`'s `approved_provider_at`). Returns `None`
    (never a guess) when nothing is configured — task §14's explicit "NON
    rendere universale Unowned Attention -> CEO"."""
    policies = list(
        session.scalars(select(m.OrganizationalFallbackPolicy).where(m.OrganizationalFallbackPolicy.is_active.is_(True)))
    )
    if not policies:
        return None
    specific = [p for p in policies if p.scope_type != m.POSITION_SCOPE_GLOBAL and _policy_matches(p, context)]
    global_policies = [p for p in policies if p.scope_type == m.POSITION_SCOPE_GLOBAL]
    candidates = specific or global_policies
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.created_at, p.id), reverse=True)
    return session.get(m.Position, candidates[0].fallback_position_id)


def _policy_matches(policy: "m.OrganizationalFallbackPolicy", context: ScopeContext | None) -> bool:
    if context is None or policy.scope_type != context.scope_type:
        return False
    if policy.scope_type in m.POSITION_SCOPE_ID_KINDS:
        return policy.scope_id == context.scope_id
    return policy.scope_key == context.scope_key
