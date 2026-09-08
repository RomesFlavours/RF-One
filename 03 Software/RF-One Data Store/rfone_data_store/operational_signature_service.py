"""Shared RF-One Operational Signature service
(RFONE_SHARED_IDENTITY_AUTHORITY_SIGNATURE_001).

The ONE place any Domain records the evidence that makes an authenticated,
authorized action stand in for a handwritten signature on an ordinary
operational Decision (Identity Authority and Security Architecture.md
§9-10; Core doc §5-6). No Domain writes `models.OperationalSignature`
directly — every Domain calls `record_operational_signature()` below.

Append-only (Historical Integrity): this module exposes NO update/delete
function for `OperationalSignature`. A correction is `record_operational_
signature()` called again with `corrects=<the original row>` — a brand new
row whose own `corrects_signature_id` points back at it; the original row's
columns are never touched by any code in this module.

Audit scalability (task requirement): this function's signature does not
promise synchronous persistence to its callers — it takes a `Session` and
flushes within it exactly like every other write in this codebase, so a
later change to make the actual write asynchronous (e.g. queued and
persisted by a background worker) would only change this function's body,
never any Domain caller. No queue/broker is introduced now — the existing
canonical database is sufficient at present scale (task instruction: do not
add SQS/Redis/Kafka/etc. merely for future scale).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models as m

UTC = timezone.utc


def record_operational_signature(
    session: Session, *, actor: m.ActingIdentity, action: str, domain: str,
    assurance_level: str, scope_type: str, scope_id: int | None, module: str | None = None,
    object_type: str | None = None, object_id: int | str | None = None,
    before_state: dict | list | None = None, after_state: dict | list | None = None,
    applicable_version: str | None = None, authority_used: str | None = None, reason: str | None = None,
    occurred_at: datetime | None = None, corrects: m.OperationalSignature | None = None,
) -> m.OperationalSignature:
    """Records one RF-One Operational Signature. `actor`, `action`,
    `domain`/`module`/`scope_type`/`scope_id` (context — task requirement
    "every ... evaluation must carry explicit tenant/company/context
    scope", applied here identically to Authority), `object_type`/
    `object_id`, `before_state`/`after_state`, `applicable_version`,
    `authority_used`, `reason`, and `assurance_level` together cover every
    documented audit field (Architecture doc §9, §12) except `actor_kind`
    and the timestamps, both captured automatically below.

    `scope_type`/`scope_id` follow `authority_service`'s own validation
    rule (reused, not duplicated) — GLOBAL is the only scope allowed to
    omit `scope_id`; every other scope must state it explicitly.

    `corrects=<a previously recorded OperationalSignature>` is the ONLY
    supported correction mechanism: it sets the NEW row's own
    `corrects_signature_id`, never modifies `corrects` itself."""
    from .authority_service import validate_authority_context  # local import avoids a hard import-cycle at module load

    if not action:
        raise ValueError("record_operational_signature() requires a non-empty action.")
    if assurance_level not in m.OPERATIONAL_SIGNATURE_ASSURANCE_LEVELS:
        raise ValueError(
            f"Invalid assurance_level {assurance_level!r} — must be one of "
            f"{m.OPERATIONAL_SIGNATURE_ASSURANCE_LEVELS}."
        )
    validate_authority_context(domain=domain, scope_type=scope_type, scope_id=scope_id)

    signature = m.OperationalSignature(
        acting_identity_id=actor.id,
        actor_kind=actor.kind,
        action=action,
        domain=domain,
        module=module,
        scope_type=scope_type,
        scope_id=scope_id,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        before_state=before_state,
        after_state=after_state,
        applicable_version=applicable_version,
        authority_used=authority_used,
        reason=reason,
        assurance_level=assurance_level,
        occurred_at=occurred_at or datetime.now(UTC),
        corrects_signature_id=corrects.id if corrects is not None else None,
    )
    session.add(signature)
    session.flush()
    return signature


def get_signature(session: Session, signature_id: int) -> m.OperationalSignature | None:
    return session.get(m.OperationalSignature, signature_id)
