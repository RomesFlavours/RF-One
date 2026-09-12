"""Shared Attention Management service (TASK_ATTENTION_ORG_RUNTIME;
`00 Core/ConceptualArchitecture/12_Attention_Management.md`).

The ONE place any Domain raises "something requires human attention" and
asks "who does this currently reach" — never a per-Domain notification
mechanism (Core doc 12 §1: "not a notification system"; task's own
instruction not to build a Tips-specific shortcut). Foundation, not
integration — no Tips (or any other Domain) code is imported here.

Priority is never computed here from a fixed event->priority table (task
§10, Core doc 12 §3): it is always supplied by the calling Domain/Process,
which is the only party that actually knows the context. This module only
conserves, orders, exposes, and allows authorized re-evaluation of it — and
refuses to let CRITICAL ever be silenced (see `list_attention_for_identity`)
or acknowledged/resolved away without an explicit actor.

Delivery boundary (task §11): `route_attention` determines and records the
resolved recipient; it does NOT deliver anything anywhere (no email/SMS/
push/Cognito call is made by this module). A future Cognito Human
Interaction capability, or any other channel, is expected to call
`list_attention_for_identity`/`route_attention` itself — this module is the
clean boundary such a caller consumes, never a delivery mechanism of its
own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .organizational_responsibility_service import ScopeContext, resolve_effective_recipient

UTC = timezone.utc


class AttentionError(ValueError):
    """A malformed call (invalid priority/status, or an action on an item
    in a state that does not allow it) — always a caller bug, never a
    normal outcome."""


def create_attention(
    session: Session, *, source_domain: str, reason: str, priority: str, source_module: str | None = None,
    source_process_name: str | None = None, source_phase: str | None = None, source_reference: str | None = None,
    detail: str | None = None, proposed_action: str | None = None, scope: ScopeContext | None = None,
) -> "m.AttentionItem":
    """Creates one OPEN Attention Item. Does NOT resolve routing — call
    `route_attention` separately (kept as two steps so a Domain can create
    the item first and route it, or re-route it later, without recreating
    it — Historical Integrity: one item, one row, for its whole lifecycle)."""
    if priority not in m.ATTENTION_PRIORITIES:
        raise AttentionError(f"Invalid priority {priority!r} — must be one of {m.ATTENTION_PRIORITIES}.")
    if not source_domain or not reason:
        raise AttentionError("create_attention() requires source_domain and reason.")
    item = m.AttentionItem(
        source_domain=source_domain, source_module=source_module, source_process_name=source_process_name,
        source_phase=source_phase, source_reference=source_reference, reason=reason, detail=detail,
        proposed_action=proposed_action, priority=priority, status=m.ATTENTION_STATUS_OPEN,
        scope_type=scope.scope_type if scope is not None else None,
        scope_id=scope.scope_id if scope is not None else None,
        scope_key=scope.scope_key if scope is not None else None,
    )
    session.add(item)
    session.flush()
    return item


def route_attention(session: Session, *, item: "m.AttentionItem", now: datetime | None = None) -> "m.AttentionItem":
    """Resolves Process/Phase -> Position owner -> Scope -> Occupant ->
    Coverage -> effective recipient for `item`'s own source_domain/module/
    process_name/phase/scope, and records the outcome on the item itself.
    `item.status` is left exactly as it was (task §9: unresolved routing
    stays OPEN, never assigned arbitrarily and never silently escalated to
    a guessed target) — this function only ever fills in `resolved_*`/
    `routing_unresolved_reason`, never changes `status`."""
    if item.source_process_name is None:
        item.routing_unresolved_reason = "This Attention Item names no source_process_name to route against."
        item.resolved_process_owner_position_id = None
        item.resolved_recipient_acting_identity_id = None
        item.resolution_path = None
        session.flush()
        return item

    context = (
        ScopeContext(scope_type=item.scope_type, scope_id=item.scope_id, scope_key=item.scope_key)
        if item.scope_type is not None else None
    )
    resolution = resolve_effective_recipient(
        session, domain=item.source_domain, process_name=item.source_process_name, module=item.source_module,
        phase=item.source_phase, context=context, now=now,
    )
    item.resolved_process_owner_position_id = resolution.owner_position.id if resolution.owner_position else None
    item.resolved_recipient_acting_identity_id = (
        resolution.acting_identity.id if resolution.acting_identity else None
    )
    item.resolution_path = resolution.resolution_path
    item.routing_unresolved_reason = resolution.unresolved_reason
    session.flush()
    return item


def acknowledge_attention(
    session: Session, *, item: "m.AttentionItem", by: "m.ActingIdentity", now: datetime | None = None,
) -> "m.AttentionItem":
    if item.status not in (m.ATTENTION_STATUS_OPEN,):
        raise AttentionError(f"Cannot acknowledge an Attention Item in status {item.status!r}.")
    item.status = m.ATTENTION_STATUS_ACKNOWLEDGED
    item.acknowledged_at = now or datetime.now(UTC)
    item.acknowledged_by_identity_id = by.id
    session.flush()
    return item


def resolve_attention(
    session: Session, *, item: "m.AttentionItem", by: "m.ActingIdentity", now: datetime | None = None,
) -> "m.AttentionItem":
    if item.status not in (m.ATTENTION_STATUS_OPEN, m.ATTENTION_STATUS_ACKNOWLEDGED):
        raise AttentionError(f"Cannot resolve an Attention Item in status {item.status!r}.")
    item.status = m.ATTENTION_STATUS_RESOLVED
    item.resolved_at = now or datetime.now(UTC)
    item.resolved_by_identity_id = by.id
    session.flush()
    return item


def cancel_attention(
    session: Session, *, item: "m.AttentionItem", by: "m.ActingIdentity", now: datetime | None = None,
) -> "m.AttentionItem":
    """A source Process withdrawing its own request (e.g. the condition
    that raised it no longer applies) — distinct from RESOLVED (a human
    acted on it). CRITICAL items may be cancelled (the source Process is
    the authority on whether the condition still exists) but this is never
    silent — `by`/`now` are always recorded, exactly like resolution."""
    if item.status in (m.ATTENTION_STATUS_RESOLVED, m.ATTENTION_STATUS_CANCELLED):
        raise AttentionError(f"Cannot cancel an Attention Item already in status {item.status!r}.")
    item.status = m.ATTENTION_STATUS_CANCELLED
    item.resolved_at = now or datetime.now(UTC)
    item.resolved_by_identity_id = by.id
    session.flush()
    return item


def reprioritize_attention(session: Session, *, item: "m.AttentionItem", new_priority: str) -> "m.AttentionItem":
    """Authorized re-evaluation of priority (task §10: "permetterne
    rivalutazione autorizzata") — a plain field update, deliberately with no
    separate audit table here (this Foundation's own minimal scope); a
    Domain requiring a full history of re-prioritizations can layer that on
    top later without this function's signature changing."""
    if new_priority not in m.ATTENTION_PRIORITIES:
        raise AttentionError(f"Invalid priority {new_priority!r} — must be one of {m.ATTENTION_PRIORITIES}.")
    item.priority = new_priority
    session.flush()
    return item


_PRIORITY_ORDER = {p: i for i, p in enumerate(m.ATTENTION_PRIORITIES)}  # CRITICAL=0 ... LOW=3


@dataclass(frozen=True)
class AttentionListEntry:
    item: "m.AttentionItem"


def list_attention_for_identity(
    session: Session, *, identity: "m.ActingIdentity", include_statuses: tuple[str, ...] = (m.ATTENTION_STATUS_OPEN, m.ATTENTION_STATUS_ACKNOWLEDGED),
) -> list["m.AttentionItem"]:
    """Every Attention Item currently routed to `identity`, ordered
    CRITICAL first (task §10: CRITICAL must never be aggregated/silenced —
    it is therefore always surfaced first here, never buried under volume of
    lower-priority items). This is the attention list, never a general
    report (Core doc 12 §5) — callers wanting "everything is running
    normally" must ask for that separately; this function only ever returns
    items that actually need attention."""
    items = list(
        session.scalars(
            select(m.AttentionItem).where(
                m.AttentionItem.resolved_recipient_acting_identity_id == identity.id,
                m.AttentionItem.status.in_(include_statuses),
            )
        )
    )
    items.sort(key=lambda i: (_PRIORITY_ORDER.get(i.priority, len(_PRIORITY_ORDER)), i.created_at))
    return items


def list_unresolved_routing(session: Session) -> list["m.AttentionItem"]:
    """Every OPEN/ACKNOWLEDGED Attention Item whose routing could not
    determine an effective recipient (task §9) — the admin/test-harness view
    of "nobody is currently seeing this," never silently dropped."""
    return list(
        session.scalars(
            select(m.AttentionItem).where(
                m.AttentionItem.status.in_((m.ATTENTION_STATUS_OPEN, m.ATTENTION_STATUS_ACKNOWLEDGED)),
                m.AttentionItem.resolved_recipient_acting_identity_id.is_(None),
            )
        )
    )
