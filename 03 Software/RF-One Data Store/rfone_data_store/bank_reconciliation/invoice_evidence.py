"""Invoice evidence: what an invoice line means, and what a counterparty
is capable of supplying (BANK_INVOICE_EVIDENCE_COLLABORATION_001).

Bank Assessment remains the accounting control point. Nothing here posts
to a P&L, and nothing here is a second accounting area. This module turns
invoice lines into EVIDENCE that Bank Assessment consumes when it decides
how many allocations a bank movement needs.

The operator is never asked an accounting question
-------------------------------------------------
"Should this be 5100 or 7830?" is a question RF-One must answer for
itself, from the invoice item. "Were these items for Winter Park or Mount
Dora?" is an operational question only a person can answer, and is the
only kind this module asks.

Accordingly there is no way, anywhere in this module, to choose an
account. An operator picks a WHY; the canonical destination follows from
it through `BankTransactionReason`, exactly as it already does for bank
decisions.

WHO capability
--------------
`MULTI_CATEGORY_CAPABLE` means one thing and nothing more:

    WHEN A MATCHING INVOICE EXISTS, ITS LINES MUST BE EXAMINED.

It does not mean a given payment contains several categories — most
Cheney invoices are food and nothing else. It means WHO alone may never
decide WHY for this counterparty while a document exists to be read.

Supplier item learning
----------------------
Supplier product substance is stable, so two consistent human
confirmations of the same (supplier item, WHY) are enough to propose that
mapping automatically afterwards. Two, not ten — a Product Owner
decision. One confirmation teaches nothing. A competing confirmed mapping
contradicts rather than overwrites, and automatic proposal stops until a
person resolves it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import destination_evidence

# The normalization applied before a description may be used as an item
# identity. Versioned in the same spirit as
# `FinancialTransaction.payee_normalization_version`: if the rule ever
# changes, previously learned descriptions stay explainable.
DESCRIPTION_NORMALIZATION_VERSION = "1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# WHO <-> Supplier
# ---------------------------------------------------------------------------


def link_occurrence_supplier(
    session: Session,
    *,
    occurrence_id: int,
    supplier_id: int,
    link_source: str = "HUMAN",
    notes: str | None = None,
) -> "m.BankOccurrenceSupplier":
    """Record that a bank counterparty and a purchasing Supplier are the
    same commercial party.

    Idempotent. Confers no classification whatsoever: knowing that Amazon
    the Occurrence is Amazon the Supplier says nothing about why any
    payment to it exists."""
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Bank Occurrence {occurrence_id} does not exist.")
    supplier = session.get(m.Supplier, supplier_id)
    if supplier is None:
        raise ValueError(f"Supplier {supplier_id} does not exist.")

    existing = session.scalar(
        select(m.BankOccurrenceSupplier).where(
            m.BankOccurrenceSupplier.occurrence_id == occurrence_id,
            m.BankOccurrenceSupplier.supplier_id == supplier_id,
        )
    )
    if existing is not None:
        return existing

    link = m.BankOccurrenceSupplier(
        occurrence_id=occurrence_id,
        supplier_id=supplier_id,
        link_source=link_source,
        notes=notes,
    )
    session.add(link)
    session.flush()
    return link


def supplier_ids_for_occurrence(session: Session, *, occurrence_id: int) -> list[int]:
    """Every Supplier this bank counterparty corresponds to — possibly one
    per Restaurant, since Suppliers are Restaurant-scoped."""
    return list(
        session.scalars(
            select(m.BankOccurrenceSupplier.supplier_id)
            .where(m.BankOccurrenceSupplier.occurrence_id == occurrence_id)
            .order_by(m.BankOccurrenceSupplier.supplier_id)
        )
    )


def occurrence_ids_for_supplier(session: Session, *, supplier_id: int) -> list[int]:
    return list(
        session.scalars(
            select(m.BankOccurrenceSupplier.occurrence_id)
            .where(m.BankOccurrenceSupplier.supplier_id == supplier_id)
            .order_by(m.BankOccurrenceSupplier.occurrence_id)
        )
    )


# ---------------------------------------------------------------------------
# WHO accounting-category capability
# ---------------------------------------------------------------------------


def set_who_capability(
    session: Session,
    *,
    occurrence_id: int,
    capability: str,
    source: str = m.CAPABILITY_SOURCE_HUMAN,
    evidence: str | None = None,
    allow_downgrade: bool = False,
) -> "m.BankOccurrence":
    """Set what a counterparty is capable of supplying.

    **Never downgraded automatically.** Once a real invoice has shown that
    a supplier can issue several accounting categories on one document,
    the next ten single-category invoices do not unlearn it: a supplier
    that CAN decompose still can. Only an explicit operator decision
    (`allow_downgrade=True`) may move a counterparty back off
    MULTI_CATEGORY_CAPABLE, and that is a deliberate act with its own
    recorded evidence."""
    if capability not in m.WHO_CATEGORY_CAPABILITIES:
        raise ValueError(
            f"Capability must be one of {', '.join(m.WHO_CATEGORY_CAPABILITIES)}, "
            f"got {capability!r}."
        )
    if source not in m.CAPABILITY_SOURCES:
        raise ValueError(
            f"Capability source must be one of {', '.join(m.CAPABILITY_SOURCES)}, got {source!r}."
        )

    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Bank Occurrence {occurrence_id} does not exist.")

    is_downgrade = (
        occurrence.category_capability == m.WHO_MULTI_CATEGORY_CAPABLE
        and capability != m.WHO_MULTI_CATEGORY_CAPABLE
    )
    if is_downgrade and not allow_downgrade:
        raise ValueError(
            f"{occurrence.canonical_name!r} is already MULTI_CATEGORY_CAPABLE. A supplier that "
            "has been shown to issue several accounting categories is never downgraded "
            "automatically — pass allow_downgrade=True to record a deliberate operator decision."
        )
    if is_downgrade and source != m.CAPABILITY_SOURCE_HUMAN:
        raise ValueError(
            "Only an explicit human decision may downgrade a MULTI_CATEGORY_CAPABLE counterparty."
        )

    occurrence.category_capability = capability
    occurrence.capability_source = source
    occurrence.capability_established_at = _now()
    occurrence.capability_evidence = evidence
    session.flush()
    return occurrence


def discover_capability_from_document(
    session: Session, *, occurrence_id: int, purchase_document_id: int,
) -> "m.BankOccurrence":
    """Let a real invoice establish the capability by itself (§18).

    A document whose confirmed line classifications resolve to two or more
    DIFFERENT canonical accounts is direct proof that this counterparty
    can issue several categories. No prior configuration is required
    before RF-One may discover that fact.

    One category proves nothing either way, so an UNKNOWN counterparty
    stays UNKNOWN rather than being declared SINGLE_CATEGORY on one
    document — and a MULTI_CATEGORY_CAPABLE one is never touched."""
    codes = distinct_accounting_codes_on_document(
        session, purchase_document_id=purchase_document_id
    )
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Bank Occurrence {occurrence_id} does not exist.")

    if len(codes) < 2:
        return occurrence
    if occurrence.category_capability == m.WHO_MULTI_CATEGORY_CAPABLE:
        return occurrence

    document = session.get(m.PurchaseDocument, purchase_document_id)
    reference = (document.document_number if document else None) or str(purchase_document_id)
    return set_who_capability(
        session,
        occurrence_id=occurrence_id,
        capability=m.WHO_MULTI_CATEGORY_CAPABLE,
        source=m.CAPABILITY_SOURCE_INVOICE_EVIDENCE,
        evidence=(
            f"Document {reference} carries {len(codes)} distinct canonical accounts "
            f"({', '.join(codes)}), which only a multi-category supplier can produce."
        ),
    )


def distinct_accounting_codes_on_document(
    session: Session, *, purchase_document_id: int,
) -> list[str]:
    """The distinct canonical accounts this document's CONFIRMED line
    classifications resolve to. Proposals are excluded: a machine's guess
    is not evidence about a supplier."""
    codes: set[str] = set()
    for line in product_lines(session, purchase_document_id=purchase_document_id):
        current = current_classification(session, purchase_line_id=line.id)
        if current is not None and current.is_confirmed:
            if current.accounting_classification_code_snapshot:
                codes.add(current.accounting_classification_code_snapshot)
    return sorted(codes)


# ---------------------------------------------------------------------------
# Supplier item identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemIdentity:
    """How RF-One recognizes the same supplier item across invoices.

    `kind` records WHICH evidence was strong enough to use, so a mapping
    learned from a stable supplier code is never confused with one learned
    from a description that happened to read the same."""

    kind: str
    value: str
    supplier_product_id: int | None

    @property
    def is_strong(self) -> bool:
        """Whether this identity rests on a stable supplier identifier
        rather than on free text."""
        return self.kind in (
            m.ITEM_IDENTITY_SUPPLIER_PRODUCT, m.ITEM_IDENTITY_SUPPLIER_ITEM_CODE,
        )


def normalize_description(raw: str | None) -> str:
    """Reduce a free-text item description to a stable comparison key.

    Upper-cased, punctuation dropped, whitespace collapsed. Deliberately
    conservative: this is a LAST-RESORT identity, and an aggressive
    normalizer would merge items that are genuinely different."""
    if not raw:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", raw)
    return re.sub(r"\s+", " ", cleaned).strip().upper()


def resolve_item_identity(
    session: Session, *, purchase_line: "m.PurchaseLine",
) -> ItemIdentity | None:
    """The strongest stable identity this line offers, in fixed order:

    1. the canonical `SupplierProduct` it resolved to — the pair
       (Supplier, Supplier Item Code) that Purchasing already treats as
       supplier product memory;
    2. the supplier's own item code as printed;
    3. a normalized description, ONLY when the source gave no code at all.

    Returns None when even a description is missing — an item RF-One
    cannot recognize is one it must not learn from."""
    if purchase_line.supplier_product_id is not None:
        return ItemIdentity(
            kind=m.ITEM_IDENTITY_SUPPLIER_PRODUCT,
            value=str(purchase_line.supplier_product_id),
            supplier_product_id=purchase_line.supplier_product_id,
        )
    code = (purchase_line.supplier_item_code or "").strip()
    if code:
        return ItemIdentity(
            kind=m.ITEM_IDENTITY_SUPPLIER_ITEM_CODE, value=code.upper(), supplier_product_id=None,
        )
    description = normalize_description(purchase_line.raw_description)
    if description:
        return ItemIdentity(
            kind=m.ITEM_IDENTITY_NORMALIZED_DESCRIPTION,
            value=description,
            supplier_product_id=None,
        )
    return None


# ---------------------------------------------------------------------------
# Supplier item learning
# ---------------------------------------------------------------------------


def record_item_confirmation(
    session: Session,
    *,
    supplier_id: int,
    identity: ItemIdentity,
    transaction_reason_id: int,
) -> "m.SupplierItemCategoryLearning":
    """Record ONE human confirmation that this supplier item means this WHY.

    Learning is per (supplier, identity, WHY), so the same description
    from two different suppliers never shares a mapping, and a competing
    WHY accumulates its own evidence instead of erasing the first."""
    supplier = session.get(m.Supplier, supplier_id)
    if supplier is None:
        raise ValueError(f"Supplier {supplier_id} does not exist.")
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Transaction Reason {transaction_reason_id} does not exist.")

    row = session.scalar(
        select(m.SupplierItemCategoryLearning).where(
            m.SupplierItemCategoryLearning.supplier_id == supplier_id,
            m.SupplierItemCategoryLearning.identity_kind == identity.kind,
            m.SupplierItemCategoryLearning.identity_value == identity.value,
            m.SupplierItemCategoryLearning.transaction_reason_id == transaction_reason_id,
        )
    )
    now = _now()
    if row is None:
        row = m.SupplierItemCategoryLearning(
            supplier_id=supplier_id,
            identity_kind=identity.kind,
            identity_value=identity.value,
            supplier_product_id=identity.supplier_product_id,
            transaction_reason_id=transaction_reason_id,
            confirmation_count=1,
            status=m.LEARNING_OBSERVED,
            first_confirmed_at=now,
            last_confirmed_at=now,
        )
        session.add(row)
    else:
        row.confirmation_count += 1
        row.last_confirmed_at = now
        if row.first_confirmed_at is None:
            row.first_confirmed_at = now
    session.flush()

    _reevaluate_identity(session, supplier_id=supplier_id, identity=identity)
    session.flush()
    return row


def _reevaluate_identity(session: Session, *, supplier_id: int, identity: ItemIdentity) -> None:
    """Decide, for one supplier item, which mapping (if any) may be
    proposed automatically.

    * No mapping has reached the threshold -> everything stays OBSERVED
      and nothing is proposed.
    * Exactly one has -> it is LEARNED. If other mappings hold
      confirmations too, the disagreement is RECORDED on the learned row
      rather than hidden: a single override does not overturn two
      confirmations, but it is never silently forgotten either.
    * Two or more have -> the item is CONTRADICTED. Automatic proposal
      stops entirely, because a genuine disagreement between two
      twice-confirmed mappings is a question for a person, not something
      to resolve by picking the larger number."""
    rows = list(
        session.scalars(
            select(m.SupplierItemCategoryLearning)
            .where(
                m.SupplierItemCategoryLearning.supplier_id == supplier_id,
                m.SupplierItemCategoryLearning.identity_kind == identity.kind,
                m.SupplierItemCategoryLearning.identity_value == identity.value,
            )
            .order_by(m.SupplierItemCategoryLearning.id)
        )
    )
    threshold = m.ITEM_LEARNING_CONFIRMATION_THRESHOLD
    qualified = [r for r in rows if r.confirmation_count >= threshold]

    if len(qualified) >= 2:
        names = ", ".join(
            f"{r.transaction_reason.code} x{r.confirmation_count}" for r in qualified
        )
        for row in rows:
            if row in qualified:
                row.status = m.LEARNING_CONTRADICTED
                row.contradiction_note = (
                    f"Two or more mappings reached {threshold} confirmations for this item "
                    f"({names}). Automatic proposal is suspended until a person decides."
                )
            else:
                row.status = m.LEARNING_OBSERVED
        return

    if len(qualified) == 1:
        learned = qualified[0]
        competing = [r for r in rows if r is not learned and r.confirmation_count > 0]
        learned.status = m.LEARNING_LEARNED
        if competing:
            detail = ", ".join(
                f"{r.transaction_reason.code} x{r.confirmation_count}" for r in competing
            )
            learned.contradiction_note = (
                f"A human has also classified this item as {detail}. The learned mapping stands "
                f"because it holds {learned.confirmation_count} confirmations, but the "
                "disagreement is on record."
            )
        else:
            learned.contradiction_note = None
        for row in competing:
            row.status = m.LEARNING_OBSERVED
        return

    for row in rows:
        row.status = m.LEARNING_OBSERVED
        row.contradiction_note = None


def learned_mapping_for(
    session: Session, *, supplier_id: int, identity: ItemIdentity,
) -> "m.SupplierItemCategoryLearning | None":
    """The mapping RF-One may propose for this item, or None.

    None covers three different situations on purpose — never learned,
    learned but contradicted, and not enough confirmations yet — because
    in all three the correct behaviour is identical: propose nothing and
    let a person decide."""
    rows = list(
        session.scalars(
            select(m.SupplierItemCategoryLearning).where(
                m.SupplierItemCategoryLearning.supplier_id == supplier_id,
                m.SupplierItemCategoryLearning.identity_kind == identity.kind,
                m.SupplierItemCategoryLearning.identity_value == identity.value,
            )
        )
    )
    proposable = [r for r in rows if r.may_propose]
    return proposable[0] if len(proposable) == 1 else None


# ---------------------------------------------------------------------------
# Invoice line classification
# ---------------------------------------------------------------------------


def product_lines(session: Session, *, purchase_document_id: int) -> list["m.PurchaseLine"]:
    """The document's PRODUCT lines, in source order. SURCHARGE and
    DISCOUNT lines are deliberately absent: they are never classified in
    their own right, they are apportioned across these
    (`purchasing.repository.get_purchased_lines_with_allocation`)."""
    return list(
        session.scalars(
            select(m.PurchaseLine)
            .where(
                m.PurchaseLine.purchase_document_id == purchase_document_id,
                m.PurchaseLine.line_type == "PRODUCT",
            )
            .order_by(m.PurchaseLine.id)
        )
    )


def current_classification(
    session: Session, *, purchase_line_id: int,
) -> "m.PurchaseLineClassification | None":
    """The line's CURRENT decision — its highest-`id` row. Earlier rows
    remain as history and are never rewritten."""
    return session.scalar(
        select(m.PurchaseLineClassification)
        .where(m.PurchaseLineClassification.purchase_line_id == purchase_line_id)
        .order_by(m.PurchaseLineClassification.id.desc())
        .limit(1)
    )


def classification_history(
    session: Session, *, purchase_line_id: int,
) -> list["m.PurchaseLineClassification"]:
    return list(
        session.scalars(
            select(m.PurchaseLineClassification)
            .where(m.PurchaseLineClassification.purchase_line_id == purchase_line_id)
            .order_by(m.PurchaseLineClassification.id)
        )
    )


def classify_line(
    session: Session,
    *,
    purchase_line_id: int,
    transaction_reason_id: int | None = None,
    reporting_entity_id: int | None = None,
    decision_source: str = m.LINE_DECISION_HUMAN,
    status: str = m.LINE_CLASSIFICATION_CONFIRMED,
    confidence: str | None = None,
    evidence: str | None = None,
    learning_id: int | None = None,
    decided_by_account_id: int | None = None,
    learn: bool = True,
) -> "m.PurchaseLineClassification":
    """Record one decision about one invoice line.

    Appends; never updates. The accounting destination is DERIVED from the
    WHY and snapshotted — there is no parameter for choosing an account,
    because an operator choosing one independently of the reason is
    exactly what the WHY -> WHAT chain exists to prevent.

    A HUMAN CONFIRMED decision also feeds supplier item learning, which is
    how two consistent confirmations eventually make this automatic. A
    machine proposal never teaches itself: `LEARNED` and
    `DOCUMENT_EVIDENCE` decisions record no confirmation."""
    if decision_source not in m.LINE_DECISION_SOURCES:
        raise ValueError(
            f"Decision source must be one of {', '.join(m.LINE_DECISION_SOURCES)}, "
            f"got {decision_source!r}."
        )
    if status not in m.LINE_CLASSIFICATION_STATUSES:
        raise ValueError(
            f"Status must be one of {', '.join(m.LINE_CLASSIFICATION_STATUSES)}, got {status!r}."
        )

    line = session.get(m.PurchaseLine, purchase_line_id)
    if line is None:
        raise ValueError(f"Purchase Line {purchase_line_id} does not exist.")
    if line.line_type != "PRODUCT":
        raise ValueError(
            f"Purchase Line {purchase_line_id} is a {line.line_type} line. Only PRODUCT lines "
            "carry an economic classification; surcharges and discounts are apportioned across "
            "them instead."
        )

    reason = None
    classification = None
    if transaction_reason_id is not None:
        reason = session.get(m.BankTransactionReason, transaction_reason_id)
        if reason is None:
            raise ValueError(f"Transaction Reason {transaction_reason_id} does not exist.")
        classification = reason.accounting_classification
        if classification is None:
            raise ValueError(
                f"WHY {reason.code!r} has no accounting destination configured, so it cannot "
                "classify an invoice line."
            )

    if reporting_entity_id is not None and session.get(
        m.ReportingEntity, reporting_entity_id
    ) is None:
        raise ValueError(f"Reporting Entity {reporting_entity_id} does not exist.")

    previous = current_classification(session, purchase_line_id=purchase_line_id)

    row = m.PurchaseLineClassification(
        purchase_line_id=purchase_line_id,
        purchase_document_id=line.purchase_document_id,
        transaction_reason_id=transaction_reason_id,
        reporting_entity_id=reporting_entity_id,
        accounting_classification_id=classification.id if classification else None,
        accounting_classification_code_snapshot=classification.code if classification else None,
        accounting_statement_type_snapshot=(
            classification.statement_type if classification else None
        ),
        transaction_reason_name_snapshot=reason.name if reason else None,
        decision_source=decision_source,
        status=status,
        confidence=confidence,
        evidence=evidence,
        learning_id=learning_id,
        is_override=previous is not None,
        decided_by_account_id=decided_by_account_id,
        decided_at=_now(),
    )
    session.add(row)
    session.flush()

    if (
        learn
        and decision_source == m.LINE_DECISION_HUMAN
        and status == m.LINE_CLASSIFICATION_CONFIRMED
        and transaction_reason_id is not None
    ):
        identity = resolve_item_identity(session, purchase_line=line)
        if identity is not None:
            document = session.get(m.PurchaseDocument, line.purchase_document_id)
            if document is not None:
                record_item_confirmation(
                    session,
                    supplier_id=document.supplier_id,
                    identity=identity,
                    transaction_reason_id=transaction_reason_id,
                )

    return row


def propose_line_classifications(
    session: Session, *, purchase_document_id: int,
) -> list["m.PurchaseLineClassification"]:
    """Propose a WHY for every unclassified PRODUCT line that RF-One has
    genuinely learned.

    Proposes nothing for items it has not learned, and nothing for items
    whose learning is contradicted. Silence is the correct output of not
    knowing — the alternative would be handing an operator a confident
    guess to rubber-stamp."""
    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Purchase Document {purchase_document_id} does not exist.")

    proposals: list[m.PurchaseLineClassification] = []
    for line in product_lines(session, purchase_document_id=purchase_document_id):
        if current_classification(session, purchase_line_id=line.id) is not None:
            continue
        identity = resolve_item_identity(session, purchase_line=line)
        if identity is None:
            continue
        learned = learned_mapping_for(
            session, supplier_id=document.supplier_id, identity=identity,
        )
        if learned is None:
            continue
        proposals.append(
            classify_line(
                session,
                purchase_line_id=line.id,
                transaction_reason_id=learned.transaction_reason_id,
                decision_source=m.LINE_DECISION_LEARNED,
                status=m.LINE_CLASSIFICATION_PROPOSED,
                confidence="HIGH",
                evidence=(
                    f"Learned from {learned.confirmation_count} consistent human confirmations "
                    f"of {identity.kind} {identity.value!r} for this supplier."
                ),
                learning_id=learned.id,
                learn=False,
            )
        )
    return proposals


# ---------------------------------------------------------------------------
# FOR WHOM — document evidence, else the operator, never a guess
# ---------------------------------------------------------------------------


def resolve_owner_from_document_evidence(
    session: Session, *, purchase_document_id: int,
) -> "m.ReportingEntity | None":
    """The beneficiary the DOCUMENT itself establishes, or None.

    Two sources of evidence, in order:

    1. **The destination mapping catalog**
       (`destination_evidence.resolve_document_destination`,
       BANK_REPORTING_CONFIGURATION_001). Real suppliers write a trading
       name, a store label or an address, never "Angeli E Demoni, LLC", so
       a configured mapping — scoped to that supplier where the evidence
       is supplier-specific — is the primary answer.
    2. **An exact reporting-entity name or code**, kept as a secondary
       path because a document that literally names the entity does
       establish the beneficiary, and discarding that would lose real
       evidence.

    Ambiguity returns None rather than a choice: a destination that means
    different entities for different suppliers is a question for an
    operator, not something to settle by picking the first row.

    It is never inferred from the payer, from a historical majority, from
    the supplier's identity, or from what similar items usually turn out
    to be. When this returns None, only an operator may answer."""
    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Purchase Document {purchase_document_id} does not exist.")

    resolution = destination_evidence.resolve_document_destination(
        session, purchase_document_id=purchase_document_id,
    )
    if resolution.is_resolved:
        return session.get(m.ReportingEntity, resolution.reporting_entity_id)
    if resolution.needs_operator:
        # Genuine ambiguity. Answering it here would be exactly the guess
        # this whole mechanism exists to avoid.
        return None

    destination = normalize_description(document.destination_location)
    if not destination:
        return None

    matches = [
        entity
        for entity in session.scalars(
            select(m.ReportingEntity).where(m.ReportingEntity.status == "ACTIVE")
        )
        if normalize_description(entity.name) == destination
        or normalize_description(entity.code) == destination
    ]
    return matches[0] if len(matches) == 1 else None


def assign_economic_owner(
    session: Session,
    *,
    purchase_line_ids: list[int],
    reporting_entity_id: int,
    decision_source: str = m.LINE_DECISION_HUMAN,
    evidence: str | None = None,
    decided_by_account_id: int | None = None,
) -> list["m.PurchaseLineClassification"]:
    """Answer "who were these items for?" for one or more lines at once.

    Bulk on purpose: an Amazon order of eleven items usually has two or
    three answers, and asking eleven separate questions would be a worse
    version of the same question. Each line keeps its own appended
    decision row, so a bulk answer is still individually auditable.

    The line's existing WHY is carried forward unchanged — this answers
    FOR WHOM, and nothing else."""
    if session.get(m.ReportingEntity, reporting_entity_id) is None:
        raise ValueError(f"Reporting Entity {reporting_entity_id} does not exist.")
    if not purchase_line_ids:
        raise ValueError("No purchase lines were given to assign.")

    written: list[m.PurchaseLineClassification] = []
    for line_id in purchase_line_ids:
        previous = current_classification(session, purchase_line_id=line_id)
        written.append(
            classify_line(
                session,
                purchase_line_id=line_id,
                transaction_reason_id=(
                    previous.transaction_reason_id if previous is not None else None
                ),
                reporting_entity_id=reporting_entity_id,
                decision_source=decision_source,
                status=(
                    previous.status if previous is not None else m.LINE_CLASSIFICATION_CONFIRMED
                ),
                confidence=previous.confidence if previous is not None else None,
                evidence=evidence or "Operator assigned the beneficiary.",
                learning_id=previous.learning_id if previous is not None else None,
                decided_by_account_id=decided_by_account_id,
                # Answering FOR WHOM teaches nothing about what an item IS,
                # so it must not count as a category confirmation.
                learn=False,
            )
        )
    return written


# ---------------------------------------------------------------------------
# Document readiness
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentEvidenceState:
    """Whether a document's lines are ready to drive bank allocations."""

    purchase_document_id: int
    product_line_count: int
    classified_line_count: int
    confirmed_line_count: int
    lines_without_reason: tuple[int, ...]
    lines_without_owner: tuple[int, ...]
    distinct_accounting_codes: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        """Ready means every PRODUCT line states both a WHY and a
        beneficiary. A single unanswered line is enough to stop it — a
        partially understood invoice cannot produce a balanced allocation
        set."""
        return (
            self.product_line_count > 0
            and not self.lines_without_reason
            and not self.lines_without_owner
        )

    @property
    def is_multi_category(self) -> bool:
        return len(self.distinct_accounting_codes) > 1


def document_evidence_state(
    session: Session, *, purchase_document_id: int,
) -> DocumentEvidenceState:
    """What is known, and what is still missing, about one document."""
    lines = product_lines(session, purchase_document_id=purchase_document_id)
    classified = 0
    confirmed = 0
    without_reason: list[int] = []
    without_owner: list[int] = []
    codes: set[str] = set()

    for line in lines:
        current = current_classification(session, purchase_line_id=line.id)
        if current is None:
            without_reason.append(line.id)
            without_owner.append(line.id)
            continue
        classified += 1
        if current.is_confirmed:
            confirmed += 1
        if current.transaction_reason_id is None:
            without_reason.append(line.id)
        elif current.accounting_classification_code_snapshot:
            codes.add(current.accounting_classification_code_snapshot)
        if current.reporting_entity_id is None:
            without_owner.append(line.id)

    return DocumentEvidenceState(
        purchase_document_id=purchase_document_id,
        product_line_count=len(lines),
        classified_line_count=classified,
        confirmed_line_count=confirmed,
        lines_without_reason=tuple(without_reason),
        lines_without_owner=tuple(without_owner),
        distinct_accounting_codes=tuple(sorted(codes)),
    )


def lines_needing_owner(session: Session, *, purchase_document_id: int) -> list["m.PurchaseLine"]:
    """The lines an operator still has to answer "who was this for?" about
    — the smallest useful question, asked only where it is genuinely
    unanswerable from the document."""
    state = document_evidence_state(session, purchase_document_id=purchase_document_id)
    if not state.lines_without_owner:
        return []
    return list(
        session.scalars(
            select(m.PurchaseLine)
            .where(m.PurchaseLine.id.in_(state.lines_without_owner))
            .order_by(m.PurchaseLine.id)
        )
    )


def supplier_learning_summary(session: Session, *, supplier_id: int) -> dict[str, int]:
    """Counts by learning state for one supplier — a small operational
    read, never an input to any decision."""
    rows = session.execute(
        select(m.SupplierItemCategoryLearning.status, func.count(m.SupplierItemCategoryLearning.id))
        .where(m.SupplierItemCategoryLearning.supplier_id == supplier_id)
        .group_by(m.SupplierItemCategoryLearning.status)
    ).all()
    return {status: int(count) for status, count in rows}


# ---------------------------------------------------------------------------
# WHO -> Supplier discovery (BANK_REPORTING_CONFIGURATION_001 §10-§11)
# ---------------------------------------------------------------------------

# Outcomes of a discovery attempt.
LINK_PROPOSED = "PROPOSED"
LINK_ALREADY_LINKED = "ALREADY_LINKED"
LINK_NEEDS_OPERATOR = "NEEDS_OPERATOR"
LINK_NO_MATCH = "NO_MATCH"

# How a candidate was found. Both are EXACT matches after normalization —
# there is no fuzzy tier, by design.
MATCH_CANONICAL_NAME = "CANONICAL_SUPPLIER_NAME"
MATCH_SUPPLIER_ALIAS = "SUPPLIER_ALIAS"

# A normalized name shorter than this is not strong enough to link on by
# itself. This is not a stylistic rule: the real supplier catalog contains
# OCR artefacts such as a single letter, and a bank counterparty exactly
# matching one of those would be a coincidence, not an identification. An
# operator may still confirm such a link explicitly.
MINIMUM_AUTOMATIC_NAME_LENGTH = 3


@dataclass(frozen=True)
class SupplierCandidate:
    """One Supplier a bank counterparty might be, and how it was found."""

    supplier_id: int
    supplier_name: str
    match_kind: str
    matched_text: str


@dataclass(frozen=True)
class SupplierLinkProposal:
    """What discovery concluded about a bank counterparty.

    Four outcomes, all of them real answers:

    * `ALREADY_LINKED` — nothing to do.
    * `PROPOSED`       — exactly one strong, unique match.
    * `NEEDS_OPERATOR` — several candidates, or a match too weak to act on
                         alone. A person decides.
    * `NO_MATCH`       — no candidate. The counterparty stays perfectly
                         valid and simply unlinked; nothing is created to
                         fill the hole.
    """

    occurrence_id: int
    outcome: str
    supplier_id: int | None
    candidates: tuple[SupplierCandidate, ...]
    explanation: str

    @property
    def is_actionable(self) -> bool:
        return self.outcome == LINK_PROPOSED


def find_supplier_candidates(
    session: Session, *, name: str, restaurant_id: int | None = None,
) -> list[SupplierCandidate]:
    """Suppliers whose canonical name or known alias EXACTLY matches this
    name after normalization.

    Exact-after-normalization only. There is deliberately no fuzzy tier:
    "probably the same vendor" is how a payment ends up attached to
    another company's invoices, and the cost of being wrong here is an
    incorrect P&L. Amount is never consulted — two parties being owed the
    same figure says nothing about who they are."""
    key = normalize_description(name)
    if not key:
        return []

    candidates: dict[int, SupplierCandidate] = {}

    supplier_stmt = select(m.Supplier)
    if restaurant_id is not None:
        supplier_stmt = supplier_stmt.where(m.Supplier.restaurant_id == restaurant_id)
    for supplier in session.scalars(supplier_stmt.order_by(m.Supplier.id)):
        if normalize_description(supplier.name) == key:
            candidates[supplier.id] = SupplierCandidate(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                match_kind=MATCH_CANONICAL_NAME,
                matched_text=supplier.name,
            )

    alias_stmt = select(m.SupplierAlias, m.Supplier).join(
        m.Supplier, m.Supplier.id == m.SupplierAlias.supplier_id
    )
    if restaurant_id is not None:
        alias_stmt = alias_stmt.where(m.Supplier.restaurant_id == restaurant_id)
    for alias, supplier in session.execute(alias_stmt.order_by(m.SupplierAlias.id)).all():
        if normalize_description(alias.alias_name) != key:
            continue
        # A canonical-name match is the stronger statement, so it is never
        # replaced by an alias match for the same supplier.
        if supplier.id in candidates:
            continue
        candidates[supplier.id] = SupplierCandidate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            match_kind=MATCH_SUPPLIER_ALIAS,
            matched_text=alias.alias_name,
        )

    return [candidates[supplier_id] for supplier_id in sorted(candidates)]


def propose_supplier_link_for_occurrence(
    session: Session,
    *,
    occurrence_id: int,
    restaurant_id: int | None = None,
    auto_link: bool = False,
) -> SupplierLinkProposal:
    """Work out which Supplier a real bank counterparty corresponds to.

    This is what runs when a WHO first appears during Bank ingestion. It
    reads the existing Supplier catalog and its aliases and **never writes
    to them**: no Supplier is created, renamed or merged here, so a
    counterparty RF-One cannot recognize can never become a duplicate
    supplier row.

    With `auto_link=True` a single strong unique match is linked
    immediately, recorded as an EVIDENCE-sourced link. Everything else
    returns its finding and writes nothing."""
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Bank Occurrence {occurrence_id} does not exist.")

    already = supplier_ids_for_occurrence(session, occurrence_id=occurrence_id)
    if already:
        return SupplierLinkProposal(
            occurrence_id=occurrence_id,
            outcome=LINK_ALREADY_LINKED,
            supplier_id=already[0],
            candidates=(),
            explanation=(
                f"{occurrence.canonical_name!r} is already linked to supplier(s) "
                f"{', '.join(str(i) for i in already)}."
            ),
        )

    candidates = find_supplier_candidates(
        session, name=occurrence.canonical_name, restaurant_id=restaurant_id,
    )
    key = normalize_description(occurrence.canonical_name)

    if not candidates:
        return SupplierLinkProposal(
            occurrence_id=occurrence_id,
            outcome=LINK_NO_MATCH,
            supplier_id=None,
            candidates=(),
            explanation=(
                f"No Supplier or SupplierAlias matches {occurrence.canonical_name!r}. The "
                "counterparty stays valid and unlinked; no Supplier is created to fill the gap."
            ),
        )

    if len(candidates) > 1:
        return SupplierLinkProposal(
            occurrence_id=occurrence_id,
            outcome=LINK_NEEDS_OPERATOR,
            supplier_id=None,
            candidates=tuple(candidates),
            explanation=(
                f"{len(candidates)} suppliers match {occurrence.canonical_name!r} "
                f"({', '.join(str(c.supplier_id) for c in candidates)}). RF-One will not choose "
                "between them."
            ),
        )

    candidate = candidates[0]
    if len(key) < MINIMUM_AUTOMATIC_NAME_LENGTH:
        return SupplierLinkProposal(
            occurrence_id=occurrence_id,
            outcome=LINK_NEEDS_OPERATOR,
            supplier_id=None,
            candidates=(candidate,),
            explanation=(
                f"{occurrence.canonical_name!r} normalizes to {key!r}, which is too short to "
                "identify a supplier on its own. An operator may confirm the link explicitly."
            ),
        )

    if auto_link:
        link_occurrence_supplier(
            session,
            occurrence_id=occurrence_id,
            supplier_id=candidate.supplier_id,
            link_source="EVIDENCE",
            notes=(
                f"Matched {occurrence.canonical_name!r} to supplier "
                f"{candidate.supplier_name!r} by {candidate.match_kind}."
            ),
        )

    return SupplierLinkProposal(
        occurrence_id=occurrence_id,
        outcome=LINK_PROPOSED,
        supplier_id=candidate.supplier_id,
        candidates=(candidate,),
        explanation=(
            f"{occurrence.canonical_name!r} matches exactly one supplier — "
            f"{candidate.supplier_name!r} — by {candidate.match_kind}."
        ),
    )


def confirm_supplier_link(
    session: Session,
    *,
    occurrence_id: int,
    supplier_id: int,
    notes: str | None = None,
) -> "m.BankOccurrenceSupplier":
    """An operator stating that this counterparty is this Supplier.

    The escape hatch for everything discovery refuses to decide: several
    candidates, a name too short to act on, or a correspondence only a
    person knows about. Recorded as HUMAN, and reused by every later
    transaction for that counterparty."""
    return link_occurrence_supplier(
        session,
        occurrence_id=occurrence_id,
        supplier_id=supplier_id,
        link_source="HUMAN",
        notes=notes or "Operator confirmed the counterparty/supplier correspondence.",
    )
