"""Destination (ship-to) evidence -> ReportingEntity
(BANK_REPORTING_CONFIGURATION_001 §5-§9).

Answers one question: **when a document says the goods went to "X", which
reporting entity bore the cost?**

It is evidence mapping, not accounting classification. It never chooses an
account, never decides a WHY, and never answers anything the document
itself did not establish.

Scope is the safety mechanism
-----------------------------
    "ROME'S FLAVOURS" on Supplier A's invoice
does not prove what the same words mean on somebody else's paperwork. So a
mapping is either:

* `SUPPLIER`-scoped — it claims only what THAT supplier's documents mean;
* `GLOBAL` — it claims the text means the same thing everywhere, which is
  reserved for text strong enough to carry that claim.

Resolution always prefers the narrowest scope that matches. A supplier
mapping beats a global one, because the more specific statement is the
better-evidenced one.

What it refuses to do
---------------------
* No fuzzy matching. Two strings match after normalization or they do not.
  A "probably the same place" mapping is how an expense silently lands on
  the wrong LLC's P&L.
* No inference from the payer, the supplier's identity, a historical
  majority, or what similar items usually turn out to be.
* No answer at all when the evidence is ambiguous — the same text meaning
  different entities for different suppliers, asked without supplier
  context, returns NEEDS_OPERATOR rather than a coin flip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

# Outcomes of a resolution attempt. Three genuinely different situations
# that a bare `ReportingEntity | None` would have flattened into one.
RESOLVED = "RESOLVED"
NEEDS_OPERATOR = "NEEDS_OPERATOR"
UNKNOWN = "UNKNOWN"
NO_EVIDENCE = "NO_EVIDENCE"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_destination(raw: str | None) -> str:
    """Reduce a destination text to a stable comparison key.

    Upper-cased, punctuation dropped, whitespace collapsed. Deliberately
    conservative — this key decides which LLC carries a cost, so an
    aggressive normalizer that merged "WINTER PARK" with "WINTER PARK
    WAREHOUSE" would be actively harmful. Same rule as
    `invoice_evidence.normalize_description`, kept separate because the two
    may legitimately diverge later without one silently changing the
    other."""
    if not raw:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", raw)
    return re.sub(r"\s+", " ", cleaned).strip().upper()


# ---------------------------------------------------------------------------
# Recording evidence
# ---------------------------------------------------------------------------


def record_destination_alias(
    session: Session,
    *,
    raw_value: str,
    reporting_entity_id: int,
    evidence: str,
    confirmation_source: str = m.DESTINATION_SOURCE_HUMAN,
    supplier_id: int | None = None,
    confirmed_by_account_id: int | None = None,
) -> "m.ReportingEntityDestinationAlias":
    """Record that a destination text means a reporting entity.

    `evidence` is mandatory and is not a formality: it is the only thing
    that distinguishes this mapping from a guess, and it is what a
    reviewer reads when an expense turns up on an unexpected P&L.

    Passing `supplier_id` scopes the claim to that supplier's paperwork.
    Omitting it makes a global claim, which the caller should only do for
    text that genuinely means the same thing everywhere."""
    raw_value = (raw_value or "").strip()
    key = normalize_destination(raw_value)
    if not key:
        raise ValueError(
            "A destination alias needs text to match on. Empty or punctuation-only "
            "destinations establish nothing."
        )
    if not (evidence or "").strip():
        raise ValueError(
            "A destination mapping needs stated evidence. Without it this is an opinion about "
            "who bore a cost, which is exactly what this table exists to prevent."
        )
    if confirmation_source not in m.DESTINATION_CONFIRMATION_SOURCES:
        raise ValueError(
            f"Confirmation source must be one of "
            f"{', '.join(m.DESTINATION_CONFIRMATION_SOURCES)}, got {confirmation_source!r}."
        )

    entity = session.get(m.ReportingEntity, reporting_entity_id)
    if entity is None:
        raise ValueError(f"Reporting Entity {reporting_entity_id} does not exist.")
    if supplier_id is not None and session.get(m.Supplier, supplier_id) is None:
        raise ValueError(f"Supplier {supplier_id} does not exist.")

    scope = (
        m.DESTINATION_SCOPE_SUPPLIER if supplier_id is not None else m.DESTINATION_SCOPE_GLOBAL
    )
    existing = session.scalar(
        select(m.ReportingEntityDestinationAlias).where(
            m.ReportingEntityDestinationAlias.normalized_key == key,
            m.ReportingEntityDestinationAlias.supplier_id.is_(None)
            if supplier_id is None
            else m.ReportingEntityDestinationAlias.supplier_id == supplier_id,
        )
    )
    if existing is not None:
        if existing.reporting_entity_id != reporting_entity_id:
            raise ValueError(
                f"{raw_value!r} is already mapped to reporting entity "
                f"{existing.reporting_entity_id} at {scope} scope. Deactivate that mapping "
                "deliberately rather than overwriting what it recorded."
            )
        return existing

    alias = m.ReportingEntityDestinationAlias(
        normalized_key=key,
        raw_value=raw_value,
        scope=scope,
        supplier_id=supplier_id,
        reporting_entity_id=reporting_entity_id,
        confirmation_source=confirmation_source,
        evidence=evidence.strip(),
        status="ACTIVE",
        confirmed_by_account_id=confirmed_by_account_id,
        confirmed_at=_now(),
    )
    session.add(alias)
    session.flush()
    return alias


def deactivate_destination_alias(
    session: Session, *, alias_id: int, reason: str,
) -> "m.ReportingEntityDestinationAlias":
    """Retire a mapping without deleting it. What RF-One once believed, and
    why it stopped believing it, both stay readable."""
    alias = session.get(m.ReportingEntityDestinationAlias, alias_id)
    if alias is None:
        raise ValueError(f"Destination alias {alias_id} does not exist.")
    if not (reason or "").strip():
        raise ValueError("Retiring a mapping needs a stated reason.")
    alias.status = "INACTIVE"
    alias.evidence = f"{alias.evidence}\n\nDEACTIVATED: {reason.strip()}"
    session.flush()
    return alias


# ---------------------------------------------------------------------------
# Resolving a destination
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DestinationResolution:
    """What the destination evidence establishes, and how sure that is."""

    outcome: str
    reporting_entity_id: int | None
    normalized_key: str
    scope: str | None
    alias_id: int | None
    explanation: str
    candidate_entity_ids: tuple[int, ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.outcome == RESOLVED

    @property
    def needs_operator(self) -> bool:
        """True only for genuine ambiguity — several entities equally
        supported. An unknown destination is NOT this: there is nothing
        for an operator to disambiguate, only something to record."""
        return self.outcome == NEEDS_OPERATOR


def resolve_destination(
    session: Session, *, raw_value: str | None, supplier_id: int | None = None,
) -> DestinationResolution:
    """Which reporting entity this destination text refers to.

    Order of authority, narrowest first:

    1. a mapping scoped to THIS supplier — the most specific statement,
       and therefore the best evidenced;
    2. a global mapping;
    3. nothing.

    When no supplier context is supplied and the text is mapped
    differently for two suppliers with no global mapping to settle it, the
    answer is NEEDS_OPERATOR. That is real ambiguity, and picking one
    would be inventing an answer."""
    key = normalize_destination(raw_value)
    if not key:
        return DestinationResolution(
            outcome=NO_EVIDENCE,
            reporting_entity_id=None,
            normalized_key="",
            scope=None,
            alias_id=None,
            explanation="The document carries no destination text at all.",
        )

    active = list(
        session.scalars(
            select(m.ReportingEntityDestinationAlias)
            .where(
                m.ReportingEntityDestinationAlias.normalized_key == key,
                m.ReportingEntityDestinationAlias.status == "ACTIVE",
            )
            .order_by(m.ReportingEntityDestinationAlias.id)
        )
    )
    if not active:
        return DestinationResolution(
            outcome=UNKNOWN,
            reporting_entity_id=None,
            normalized_key=key,
            scope=None,
            alias_id=None,
            explanation=(
                f"No destination mapping exists for {key!r}. RF-One does not guess who bore this "
                "cost; an operator must say."
            ),
        )

    if supplier_id is not None:
        for alias in active:
            if alias.supplier_id == supplier_id:
                return DestinationResolution(
                    outcome=RESOLVED,
                    reporting_entity_id=alias.reporting_entity_id,
                    normalized_key=key,
                    scope=m.DESTINATION_SCOPE_SUPPLIER,
                    alias_id=alias.id,
                    explanation=(
                        f"{alias.raw_value!r} is mapped for supplier {supplier_id} specifically."
                    ),
                )

    global_aliases = [alias for alias in active if alias.supplier_id is None]
    if len(global_aliases) == 1:
        alias = global_aliases[0]
        return DestinationResolution(
            outcome=RESOLVED,
            reporting_entity_id=alias.reporting_entity_id,
            normalized_key=key,
            scope=m.DESTINATION_SCOPE_GLOBAL,
            alias_id=alias.id,
            explanation=f"{alias.raw_value!r} is mapped globally.",
        )

    # Only supplier-scoped mappings exist, and we were not told which
    # supplier — or they disagree. Either way this is ambiguity, not an
    # answer.
    entity_ids = sorted({alias.reporting_entity_id for alias in active})
    if len(entity_ids) == 1:
        alias = active[0]
        return DestinationResolution(
            outcome=RESOLVED,
            reporting_entity_id=entity_ids[0],
            normalized_key=key,
            scope=alias.scope,
            alias_id=alias.id,
            explanation=(
                f"{key!r} is mapped to the same reporting entity by every mapping that "
                "mentions it, so the missing supplier context changes nothing."
            ),
        )
    context = (
        f"supplier {supplier_id} has no mapping of its own for it"
        if supplier_id is not None
        else "no supplier context was given"
    )
    return DestinationResolution(
        outcome=NEEDS_OPERATOR,
        reporting_entity_id=None,
        normalized_key=key,
        scope=None,
        alias_id=None,
        explanation=(
            f"{key!r} means different reporting entities for different suppliers "
            f"({', '.join(str(i) for i in entity_ids)}) and {context}. "
            "An operator must say which one this document refers to."
        ),
        candidate_entity_ids=tuple(entity_ids),
    )


def resolve_document_destination(
    session: Session, *, purchase_document_id: int,
) -> DestinationResolution:
    """Resolve a purchase document's own ship-to, using its supplier as
    scope. The supplier is always known for a document, so the narrowest
    available evidence is always used."""
    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Purchase Document {purchase_document_id} does not exist.")
    return resolve_destination(
        session,
        raw_value=document.destination_location,
        supplier_id=document.supplier_id,
    )


def list_destination_aliases(
    session: Session, *, reporting_entity_id: int | None = None, include_inactive: bool = False,
) -> list["m.ReportingEntityDestinationAlias"]:
    stmt = select(m.ReportingEntityDestinationAlias)
    if reporting_entity_id is not None:
        stmt = stmt.where(
            m.ReportingEntityDestinationAlias.reporting_entity_id == reporting_entity_id
        )
    if not include_inactive:
        stmt = stmt.where(m.ReportingEntityDestinationAlias.status == "ACTIVE")
    return list(session.scalars(stmt.order_by(m.ReportingEntityDestinationAlias.id)))


def unmapped_document_destinations(session: Session) -> list[dict]:
    """Every distinct ship-to text present on real purchase documents that
    no mapping resolves.

    The operational worklist: these are the texts somebody has to answer
    for before the documents carrying them can drive an allocation.
    Documents with no destination text at all are excluded — there is
    nothing to map, and their beneficiary comes from the operator
    instead."""
    rows = session.execute(
        select(
            m.PurchaseDocument.destination_location,
            m.PurchaseDocument.supplier_id,
            m.PurchaseDocument.id,
        ).where(m.PurchaseDocument.destination_location.is_not(None))
    ).all()

    grouped: dict[tuple[str, int], list[int]] = {}
    for destination, supplier_id, document_id in rows:
        key = normalize_destination(destination)
        if not key:
            continue
        grouped.setdefault((key, supplier_id), []).append(document_id)

    unmapped: list[dict] = []
    for (key, supplier_id), document_ids in sorted(grouped.items()):
        resolution = resolve_destination(session, raw_value=key, supplier_id=supplier_id)
        if resolution.is_resolved:
            continue
        unmapped.append(
            {
                "normalized_key": key,
                "supplier_id": supplier_id,
                "document_ids": sorted(document_ids),
                "outcome": resolution.outcome,
                "explanation": resolution.explanation,
            }
        )
    return unmapped
