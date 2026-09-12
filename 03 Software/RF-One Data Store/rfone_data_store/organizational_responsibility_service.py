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


@dataclass(frozen=True)
class EffectiveRecipientResolution:
    acting_identity: "m.ActingIdentity | None"
    owner_position: "m.Position | None"
    coverage_applied: "m.PositionTemporaryCoverage | None"
    unresolved_reason: str | None = None


def resolve_effective_recipient(
    session: Session, *, domain: str, process_name: str, module: str | None = None, phase: str | None = None,
    context: ScopeContext | None = None, now: datetime | None = None,
) -> EffectiveRecipientResolution:
    """Process/Phase -> Position owner -> applicable Scope -> current
    Occupant -> temporary Coverage/Delegation -> effective recipient (task
    §9's full chain). Only ONE hop of coverage is followed (a covering
    Position's own occupant, or a directly-named covering Acting Identity)
    — a covering Position that is itself vacant or itself covered by yet
    another Position is reported unresolved rather than recursed
    indefinitely; this is a deliberate, documented simplification, not a
    Core limitation."""
    now = now or datetime.now(UTC)
    owner_resolution = resolve_process_owner(
        session, domain=domain, process_name=process_name, module=module, phase=phase, context=context,
    )
    if owner_resolution.position is None:
        return EffectiveRecipientResolution(
            acting_identity=None, owner_position=None, coverage_applied=None,
            unresolved_reason=owner_resolution.unresolved_reason,
        )
    owner_position = owner_resolution.position

    coverage = resolve_active_coverage(session, position=owner_position, now=now)
    if coverage is not None:
        if coverage.delegate_acting_identity_id is not None:
            return EffectiveRecipientResolution(
                acting_identity=coverage.delegate_acting_identity, owner_position=owner_position,
                coverage_applied=coverage,
            )
        delegate_position = coverage.delegate_position
        delegate_occupant = resolve_current_occupant(session, position=delegate_position, now=now)
        if delegate_occupant is None:
            return EffectiveRecipientResolution(
                acting_identity=None, owner_position=owner_position, coverage_applied=coverage,
                unresolved_reason=(
                    f"Position {owner_position.id} is covered by Position {delegate_position.id}, "
                    "which is itself vacant."
                ),
            )
        return EffectiveRecipientResolution(
            acting_identity=delegate_occupant, owner_position=owner_position, coverage_applied=coverage,
        )

    occupant = resolve_current_occupant(session, position=owner_position, now=now)
    if occupant is None:
        return EffectiveRecipientResolution(
            acting_identity=None, owner_position=owner_position, coverage_applied=None,
            unresolved_reason=f"Position {owner_position.id} ({owner_position.name!r}) is vacant, no active coverage.",
        )
    return EffectiveRecipientResolution(acting_identity=occupant, owner_position=owner_position, coverage_applied=None)
