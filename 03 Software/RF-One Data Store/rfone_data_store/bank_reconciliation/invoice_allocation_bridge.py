"""From invoice evidence to Bank economic allocations
(BANK_INVOICE_EVIDENCE_COLLABORATION_001 §11, §12, §15, §16).

This is the join between the two halves of the task. Invoices supply
evidence; Bank Assessment decides. Nothing here is a second accounting
area, and no invoice row ever reaches a P&L on its own — the only output
is a `BankTransactionAllocation` set, which is what reporting has always
read.

    BANK TRANSACTION   CHENEY  -2000
      matched invoice evidence, ancillary costs apportioned
      lines aggregated by (economic owner, WHY)
    ALLOCATIONS        -1500 -> entity A -> FOOD_PURCHASES              -> 5100
                        -300 -> entity A -> TO_GO_PACKAGING             -> 5300
                        -200 -> entity A -> RESTAURANT_OPERATING_SUPPLIES -> 7830

The parent stays ONE bank transaction. Three economic meanings do not make
three bank movements.

A single category stays a single allocation
-------------------------------------------
A multi-category-capable supplier whose invoice happens to be entirely
food produces exactly ONE allocation. The capability says the lines must
be READ, never that they must be SPLIT.

Ancillary costs are not reinvented here
---------------------------------------
Tax, freight, shipping and service fees are apportioned across item lines
in proportion to item value by
`purchasing.repository.get_purchased_lines_with_allocation`, which is the
existing, tested implementation of the rule Purchasing already approved.
This module CALLS it. The only proportional arithmetic written here is at
a different level — distributing a payment across category totals — and it
follows the same deterministic rule: proportional shares, with the last
share absorbing the odd cent so the total always reconciles exactly.

Missing documents are not guessed around
----------------------------------------
When a multi-category-capable counterparty's invoice is absent, the bank
movement may still be financially reconciled, but its allocation stays
PENDING_EVIDENCE. RF-One does not fall back to what that supplier usually
meant. The only way past it is an explicit, recorded human authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..purchasing import repository as purchasing_repository
from . import economic_allocation, invoice_evidence, invoice_matching


def _now() -> datetime:
    return datetime.now(timezone.utc)


def proportional_split(total: int, weights: list[int]) -> list[int]:
    """Split `total` across `weights` in proportion, exactly.

    The same deterministic rule `get_purchased_lines_with_allocation` uses
    for ancillary costs: proportional rounding, with the LAST share taking
    whatever the rounding left over, so the parts always sum to the whole.
    Not a second algorithm — the same rule, applied one level up, to
    category totals rather than item lines.

    A zero weight base produces zero shares rather than an arbitrary
    distribution: there is nothing to be in proportion to."""
    if not weights:
        return []
    base = sum(weights)
    if base == 0:
        return [0] * len(weights)

    shares: list[int] = []
    allocated = 0
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            shares.append(total - allocated)
        else:
            share = round(total * weight / base)
            shares.append(share)
            allocated += share
    return shares


# ---------------------------------------------------------------------------
# What evidence does this transaction need?
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceRequirement:
    """Whether a bank movement may be classified yet, and what is missing.

    Separates three genuinely different situations that a single boolean
    would have flattened: evidence is not required, evidence is required
    and present, evidence is required and absent."""

    financial_transaction_id: int
    occurrence_id: int | None
    occurrence_name: str | None
    capability: str
    requires_invoice: bool
    matched_document_ids: tuple[int, ...]
    documents_ready: bool
    bypass_authorized: bool
    blocking_reason: str | None

    @property
    def may_complete(self) -> bool:
        """Whether an accounting-complete allocation is permitted now."""
        if not self.requires_invoice:
            return True
        if self.bypass_authorized:
            return True
        return bool(self.matched_document_ids) and self.documents_ready


def _current_occurrence(
    session: Session, *, transaction: "m.FinancialTransaction",
) -> "m.BankOccurrence | None":
    explanation = session.get(m.BankTransactionExplanation, transaction.explanation_id or -1)
    if explanation is None or explanation.occurrence_id is None:
        return None
    return session.get(m.BankOccurrence, explanation.occurrence_id)


def evidence_requirement(
    session: Session, *, financial_transaction_id: int,
) -> EvidenceRequirement:
    """What this movement needs before its accounting may be closed."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")

    occurrence = _current_occurrence(session, transaction=transaction)
    capability = occurrence.category_capability if occurrence else m.WHO_CATEGORY_UNKNOWN
    requires = bool(occurrence and occurrence.requires_invoice_line_examination)

    matches = invoice_matching.confirmed_documents_for_transaction(
        session, financial_transaction_id=financial_transaction_id
    )
    document_ids = tuple(match.purchase_document_id for match in matches)

    ready = bool(document_ids)
    for document_id in document_ids:
        state = invoice_evidence.document_evidence_state(
            session, purchase_document_id=document_id
        )
        if not state.is_ready:
            ready = False
            break

    bypass = bypass_for(session, financial_transaction_id=financial_transaction_id) is not None

    blocking: str | None = None
    if requires and not bypass:
        if not document_ids:
            blocking = (
                f"{occurrence.canonical_name if occurrence else 'This counterparty'} is "
                "MULTI_CATEGORY_CAPABLE and no invoice is matched to this movement. Its "
                "accounting allocation stays PENDING_EVIDENCE: what this supplier usually "
                "supplies is not evidence of what it supplied here."
            )
        elif not ready:
            blocking = (
                "The matched invoice still has lines with no WHY or no beneficiary, so the "
                "allocation cannot be completed from it yet."
            )

    return EvidenceRequirement(
        financial_transaction_id=financial_transaction_id,
        occurrence_id=occurrence.id if occurrence else None,
        occurrence_name=occurrence.canonical_name if occurrence else None,
        capability=capability,
        requires_invoice=requires,
        matched_document_ids=document_ids,
        documents_ready=ready,
        bypass_authorized=bypass,
        blocking_reason=blocking,
    )


# ---------------------------------------------------------------------------
# Explicit human bypass
# ---------------------------------------------------------------------------


def authorize_bypass(
    session: Session,
    *,
    financial_transaction_id: int,
    reason: str,
    missing_document_note: str | None = None,
    authorized_by_account_id: int | None = None,
    authorized_by_name: str | None = None,
) -> "m.BankEvidenceBypassAuthorization":
    """A person taking explicit responsibility for classifying without the
    invoice.

    Never a silent fallback: nothing calls this on RF-One's behalf, and a
    reason is mandatory. The row is append-only and is never deleted, not
    even when the missing invoice turns up later — that the decision was
    once made without the document remains true."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")
    if not (reason or "").strip():
        raise ValueError(
            "A bypass needs a stated reason. Classifying without the required document is a "
            "decision somebody owns."
        )

    occurrence = _current_occurrence(session, transaction=transaction)
    authorization = m.BankEvidenceBypassAuthorization(
        financial_transaction_id=financial_transaction_id,
        reason=reason.strip(),
        missing_document_note=missing_document_note,
        occurrence_id=occurrence.id if occurrence else None,
        occurrence_name_snapshot=occurrence.canonical_name if occurrence else None,
        capability_snapshot=occurrence.category_capability if occurrence else None,
        authorized_by_account_id=authorized_by_account_id,
        authorized_by_name=authorized_by_name,
        authorized_at=_now(),
    )
    session.add(authorization)
    session.flush()
    return authorization


def bypass_for(
    session: Session, *, financial_transaction_id: int,
) -> "m.BankEvidenceBypassAuthorization | None":
    """The most recent authorization for this movement, if any."""
    return session.scalar(
        select(m.BankEvidenceBypassAuthorization)
        .where(
            m.BankEvidenceBypassAuthorization.financial_transaction_id
            == financial_transaction_id
        )
        .order_by(m.BankEvidenceBypassAuthorization.id.desc())
        .limit(1)
    )


def bypass_history(
    session: Session, *, financial_transaction_id: int,
) -> list["m.BankEvidenceBypassAuthorization"]:
    """Every authorization ever recorded for this movement, oldest first."""
    return list(
        session.scalars(
            select(m.BankEvidenceBypassAuthorization)
            .where(
                m.BankEvidenceBypassAuthorization.financial_transaction_id
                == financial_transaction_id
            )
            .order_by(m.BankEvidenceBypassAuthorization.id)
        )
    )


# ---------------------------------------------------------------------------
# Aggregating invoice evidence into allocation specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EconomicGroup:
    """One (beneficiary, WHY) total drawn from invoice evidence."""

    reporting_entity_id: int
    transaction_reason_id: int
    amount_minor: int
    line_count: int
    document_ids: tuple[int, ...]


def economic_groups_for_transaction(
    session: Session, *, financial_transaction_id: int,
) -> list[EconomicGroup]:
    """Aggregate every matched invoice's classified lines by beneficiary
    and WHY, with ancillary costs already apportioned.

    Ancillary apportionment is delegated to Purchasing's own
    `get_purchased_lines_with_allocation`, so tax and freight land on item
    lines in proportion to item value exactly as that module already
    tested. When a payment settles only part of an invoice, that
    invoice's contribution is scaled down proportionally across its own
    categories, deterministically, so partial payments never distort the
    mix of what was bought."""
    matches = invoice_matching.confirmed_documents_for_transaction(
        session, financial_transaction_id=financial_transaction_id
    )
    accumulated: dict[tuple[int, int], dict] = {}

    for match in matches:
        document_id = match.purchase_document_id
        allocated_lines = purchasing_repository.get_purchased_lines_with_allocation(
            session, document_id
        )

        per_group: dict[tuple[int, int], dict] = {}
        for row in allocated_lines:
            classification = invoice_evidence.current_classification(
                session, purchase_line_id=row["purchase_line_id"]
            )
            if (
                classification is None
                or classification.transaction_reason_id is None
                or classification.reporting_entity_id is None
            ):
                # An unanswered line cannot contribute. The caller has
                # already been told the document is not ready.
                continue
            key = (classification.reporting_entity_id, classification.transaction_reason_id)
            bucket = per_group.setdefault(
                key, {"amount": 0, "lines": 0},
            )
            bucket["amount"] += abs(int(row["allocated_amount_minor"] or 0))
            bucket["lines"] += 1

        if not per_group:
            continue

        # Scale this document's categories to the amount actually matched.
        keys = sorted(per_group)
        weights = [per_group[key]["amount"] for key in keys]
        document_total = sum(weights)
        matched_magnitude = abs(match.matched_amount_minor)
        shares = (
            weights
            if document_total == matched_magnitude
            else proportional_split(matched_magnitude, weights)
        )

        for key, share in zip(keys, shares):
            entry = accumulated.setdefault(
                key, {"amount": 0, "lines": 0, "documents": set()},
            )
            entry["amount"] += share
            entry["lines"] += per_group[key]["lines"]
            entry["documents"].add(document_id)

    return [
        EconomicGroup(
            reporting_entity_id=key[0],
            transaction_reason_id=key[1],
            amount_minor=value["amount"],
            line_count=value["lines"],
            document_ids=tuple(sorted(value["documents"])),
        )
        for key, value in sorted(accumulated.items())
        if value["amount"] != 0
    ]


@dataclass
class AllocationPlan:
    """What RF-One intends to write, and why — inspectable before it is
    applied."""

    financial_transaction_id: int
    specs: list[economic_allocation.AllocationSpec] = field(default_factory=list)
    groups: list[EconomicGroup] = field(default_factory=list)
    unexplained_minor: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def is_single_category(self) -> bool:
        return len(self.groups) == 1

    @property
    def is_complete(self) -> bool:
        return self.unexplained_minor == 0 and bool(self.groups)


def build_allocation_plan(
    session: Session, *, financial_transaction_id: int,
) -> AllocationPlan:
    """Turn matched invoice evidence into a balanced allocation set.

    The set ALWAYS sums to the bank parent. When invoice evidence accounts
    for only part of the payment, the remainder becomes its own
    NEEDS_OPERATOR allocation rather than being folded into a category
    nobody chose — the difference stays visible and the transaction stays
    accounting-open."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")

    plan = AllocationPlan(financial_transaction_id=financial_transaction_id)
    groups = economic_groups_for_transaction(
        session, financial_transaction_id=financial_transaction_id
    )
    plan.groups = groups
    if not groups:
        return plan

    sign = 1 if transaction.amount_minor > 0 else -1
    evidence_magnitude = sum(group.amount_minor for group in groups)
    parent_magnitude = abs(transaction.amount_minor)

    for group in groups:
        plan.specs.append(
            economic_allocation.AllocationSpec(
                amount_minor=sign * group.amount_minor,
                reporting_entity_id=group.reporting_entity_id,
                transaction_reason_id=group.transaction_reason_id,
                status=economic_allocation.COMPLETE,
                decision_source="HUMAN",
                evidence_kind="INVOICE",
                evidence_reference=",".join(str(d) for d in group.document_ids),
                notes=(
                    f"Derived from {group.line_count} classified invoice line(s) on document(s) "
                    f"{', '.join(str(d) for d in group.document_ids)}."
                ),
            )
        )

    remainder = parent_magnitude - evidence_magnitude
    if remainder != 0:
        plan.unexplained_minor = sign * remainder
        plan.specs.append(
            economic_allocation.AllocationSpec(
                amount_minor=sign * remainder,
                reporting_entity_id=None,
                transaction_reason_id=None,
                status=economic_allocation.NEEDS_OPERATOR,
                decision_source=None,
                notes=(
                    f"{abs(remainder)} minor units of this payment are not explained by the "
                    "matched invoices. Stated rather than absorbed into a category."
                ),
            )
        )
        plan.notes.append(
            f"Invoice evidence accounts for {evidence_magnitude} of {parent_magnitude} minor "
            "units; the difference is left explicitly unresolved."
        )

    if plan.is_single_category:
        plan.notes.append(
            "One economic category on this invoice, so one allocation. A multi-category-capable "
            "supplier is not split artificially."
        )
    return plan


def apply_invoice_evidence(
    session: Session, *, financial_transaction_id: int,
) -> list["m.BankTransactionAllocation"]:
    """Write the allocation set implied by matched invoice evidence.

    Refuses when a MULTI_CATEGORY_CAPABLE counterparty's document is
    missing or unfinished and no bypass has been authorized — that is the
    rule this task exists to enforce, and it is enforced here rather than
    left to a caller's discipline."""
    requirement = evidence_requirement(
        session, financial_transaction_id=financial_transaction_id
    )
    if requirement.blocking_reason:
        raise ValueError(requirement.blocking_reason)

    plan = build_allocation_plan(session, financial_transaction_id=financial_transaction_id)
    if not plan.specs:
        raise ValueError(
            "No classified invoice evidence is matched to this movement, so no allocation can "
            "be derived from it."
        )
    return economic_allocation.set_allocations(
        session,
        financial_transaction_id=financial_transaction_id,
        specs=plan.specs,
    )


def mark_pending_evidence(
    session: Session, *, financial_transaction_id: int, note: str | None = None,
) -> list["m.BankTransactionAllocation"]:
    """Record that this movement's accounting is waiting on a document.

    One allocation for the full amount, status PENDING_EVIDENCE, with no
    WHY and no beneficiary — because RF-One does not know them and will
    not pretend to. The existing canonical status is reused; no new
    vocabulary is invented for this case.

    The transaction stays a perfectly valid financial fact throughout. Its
    `accounting_status` is untouched here: being financially canonical and
    being accounting-complete are different questions."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")

    requirement = evidence_requirement(
        session, financial_transaction_id=financial_transaction_id
    )
    return economic_allocation.set_allocations(
        session,
        financial_transaction_id=financial_transaction_id,
        specs=[
            economic_allocation.AllocationSpec(
                amount_minor=transaction.amount_minor,
                reporting_entity_id=None,
                transaction_reason_id=None,
                status=economic_allocation.PENDING_EVIDENCE,
                decision_source=None,
                notes=note or requirement.blocking_reason or (
                    "Waiting on the invoice that explains what this payment bought."
                ),
            )
        ],
    )


def complete_with_bypass(
    session: Session,
    *,
    financial_transaction_id: int,
    specs: list[economic_allocation.AllocationSpec],
    reason: str,
    missing_document_note: str | None = None,
    authorized_by_account_id: int | None = None,
    authorized_by_name: str | None = None,
) -> tuple["m.BankEvidenceBypassAuthorization", list["m.BankTransactionAllocation"]]:
    """Classify a movement without the document a person has decided to do
    without.

    The authorization is written FIRST, so it exists even if the
    allocation write then fails. Every resulting allocation carries the
    bypass in its evidence, and the authorization itself outlives any
    later restatement of the split."""
    authorization = authorize_bypass(
        session,
        financial_transaction_id=financial_transaction_id,
        reason=reason,
        missing_document_note=missing_document_note,
        authorized_by_account_id=authorized_by_account_id,
        authorized_by_name=authorized_by_name,
    )

    stamped = [
        economic_allocation.AllocationSpec(
            amount_minor=spec.amount_minor,
            reporting_entity_id=spec.reporting_entity_id,
            transaction_reason_id=spec.transaction_reason_id,
            personal_funding_treatment=spec.personal_funding_treatment,
            status=spec.status,
            decision_source=spec.decision_source or "HUMAN",
            decided_by_account_id=spec.decided_by_account_id or authorized_by_account_id,
            evidence_kind="OPERATOR_BYPASS",
            evidence_reference=f"bypass:{authorization.id}",
            notes=(
                (spec.notes + " " if spec.notes else "")
                + f"Classified without the required document under authorization "
                f"{authorization.id}: {authorization.reason}"
            ),
        )
        for spec in specs
    ]
    allocations = economic_allocation.set_allocations(
        session, financial_transaction_id=financial_transaction_id, specs=stamped,
    )
    return authorization, allocations
