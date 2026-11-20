"""Bank <-> Invoice matching (BANK_INVOICE_EVIDENCE_COLLABORATION_001 §8-§10).

Real suppliers are not paid one invoice at a time, so matching is
many-to-many from the start:

    A. one payment  -> one invoice
    B. one payment  -> several invoices
    C. several payments -> one invoice
    D. an amount difference somebody can explain

`BankInvoiceMatch.matched_amount_minor` is what makes that representable.
Without a per-link amount, "this $5,000 covers those three invoices" is an
assertion nobody can check.

Two amount controls, both hard
------------------------------
* A transaction may never have more matched to it than it is worth.
* An invoice may never have more matched to it than it is payable for.

Neither difference is ever absorbed. What is left over is reported by
`unmatched_difference` and `unsettled_amount`, in words and in figures.

Auto-matching is deliberately timid
-----------------------------------
RF-One confirms a match automatically only when exactly one candidate is
strong and nothing else is close. Two different combinations of invoices
that both sum to the payment are AMBIGUOUS by definition, and ambiguity
is reported, never resolved by picking one. Everything else is proposed
for a person to confirm.

Amounts here follow the BANK parent's sign convention throughout, so a
transaction's matched total is directly comparable with its own
`amount_minor`. Invoice payable amounts are positive as the document
discloses them, and the two are compared in magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from itertools import combinations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import invoice_evidence

# How far either side of the bank movement an invoice may sit and still be
# considered. Generous before (terms are commonly 30-60 days) and short
# after (a prepayment is rare and must be looked at by a person).
LOOKBACK_DAYS = 120
LOOKAHEAD_DAYS = 15

# Bounds on combination search, so the candidate generator is always fast
# and always deterministic. A payment settling more than four invoices at
# once is proposed by an operator, not discovered by enumeration.
MAX_COMBINATION_SIZE = 4
MAX_COMBINATION_POOL = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Amounts already committed
# ---------------------------------------------------------------------------


def _counting_statuses(include_proposed: bool) -> tuple[str, ...]:
    """Which matches occupy amount. A PROPOSED match reserves nothing —
    it is a suggestion — so by default only CONFIRMED rows count."""
    return (
        (m.MATCH_CONFIRMED, m.MATCH_PROPOSED) if include_proposed else (m.MATCH_CONFIRMED,)
    )


def matched_total_for_transaction(
    session: Session, *, financial_transaction_id: int, include_proposed: bool = False,
) -> int:
    """How much of this bank movement is already accounted for by matches,
    in the bank's own sign convention."""
    total = session.scalar(
        select(func.sum(m.BankInvoiceMatch.matched_amount_minor)).where(
            m.BankInvoiceMatch.financial_transaction_id == financial_transaction_id,
            m.BankInvoiceMatch.status.in_(_counting_statuses(include_proposed)),
        )
    )
    return int(total or 0)


def matched_total_for_document(
    session: Session, *, purchase_document_id: int, include_proposed: bool = False,
) -> int:
    """How much of this invoice has already been paid, as a POSITIVE
    magnitude — comparable with the document's own payable amount."""
    total = session.scalar(
        select(func.sum(func.abs(m.BankInvoiceMatch.matched_amount_minor))).where(
            m.BankInvoiceMatch.purchase_document_id == purchase_document_id,
            m.BankInvoiceMatch.status.in_(_counting_statuses(include_proposed)),
        )
    )
    return int(total or 0)


def document_payable_minor(session: Session, *, purchase_document_id: int) -> int:
    """What the document says it is worth.

    Its disclosed total when the source gave one; otherwise the sum of its
    own lines, which for a well-formed invoice is the same number. Never
    guessed beyond that — a document with neither is worth 0 here, and a
    match against it will be refused rather than sized by assumption."""
    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Purchase Document {purchase_document_id} does not exist.")
    if document.total_amount_minor is not None:
        return abs(int(document.total_amount_minor))
    line_total = session.scalar(
        select(func.sum(m.PurchaseLine.source_amount_minor)).where(
            m.PurchaseLine.purchase_document_id == purchase_document_id
        )
    )
    return abs(int(line_total or 0))


def document_remaining_minor(session: Session, *, purchase_document_id: int) -> int:
    """What is still owed on this invoice: payable, less what is already
    matched. Already-matched amount can never be spent twice."""
    return document_payable_minor(
        session, purchase_document_id=purchase_document_id
    ) - matched_total_for_document(session, purchase_document_id=purchase_document_id)


def transaction_remaining_minor(session: Session, *, financial_transaction_id: int) -> int:
    """How much of the bank movement is still unaccounted for, in the
    bank's sign convention."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")
    return transaction.amount_minor - matched_total_for_transaction(
        session, financial_transaction_id=financial_transaction_id
    )


# ---------------------------------------------------------------------------
# Writing matches
# ---------------------------------------------------------------------------


class MatchAmountError(ValueError):
    """A match would commit more than either side is worth.

    Its own class because this is the failure an operator most needs
    explained, and because quietly allowing it is how an invoice ends up
    looking paid twice."""


def create_match(
    session: Session,
    *,
    financial_transaction_id: int,
    purchase_document_id: int,
    matched_amount_minor: int,
    match_method: str = "HUMAN",
    status: str = m.MATCH_CONFIRMED,
    confidence: str | None = None,
    match_basis: str | None = None,
    difference_kind: str | None = None,
    difference_note: str | None = None,
    decided_by_account_id: int | None = None,
) -> "m.BankInvoiceMatch":
    """Link a bank movement to an invoice for a stated amount.

    Both amount controls are checked BEFORE anything is written, so a
    refused match leaves the ledger exactly as it was."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")
    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Purchase Document {purchase_document_id} does not exist.")
    if status not in m.BANK_INVOICE_MATCH_STATUSES:
        raise ValueError(
            f"Status must be one of {', '.join(m.BANK_INVOICE_MATCH_STATUSES)}, got {status!r}."
        )
    if match_method not in m.BANK_INVOICE_MATCH_METHODS:
        raise ValueError(
            f"Match method must be one of {', '.join(m.BANK_INVOICE_MATCH_METHODS)}, "
            f"got {match_method!r}."
        )
    if matched_amount_minor == 0:
        raise ValueError("A match of zero accounts for nothing.")

    existing = session.scalar(
        select(m.BankInvoiceMatch).where(
            m.BankInvoiceMatch.financial_transaction_id == financial_transaction_id,
            m.BankInvoiceMatch.purchase_document_id == purchase_document_id,
        )
    )
    if existing is not None:
        raise ValueError(
            f"Transaction {financial_transaction_id} is already matched to document "
            f"{purchase_document_id}. Adjust or reject that match instead of adding a second."
        )

    if status == m.MATCH_CONFIRMED:
        _assert_amounts_fit(
            session,
            transaction=transaction,
            purchase_document_id=purchase_document_id,
            matched_amount_minor=matched_amount_minor,
        )

    payable = document_payable_minor(session, purchase_document_id=purchase_document_id)
    difference = payable - abs(matched_amount_minor)

    match = m.BankInvoiceMatch(
        financial_transaction_id=financial_transaction_id,
        purchase_document_id=purchase_document_id,
        matched_amount_minor=matched_amount_minor,
        status=status,
        match_method=match_method,
        confidence=confidence,
        match_basis=match_basis,
        difference_minor=difference or None,
        difference_kind=(
            difference_kind
            if difference_kind is not None
            else (m.DIFFERENCE_NONE if difference == 0 else m.DIFFERENCE_UNEXPLAINED)
        ),
        difference_note=difference_note,
        decided_by_account_id=decided_by_account_id,
        decided_at=_now() if status != m.MATCH_PROPOSED else None,
    )
    session.add(match)
    session.flush()
    return match


def _assert_amounts_fit(
    session: Session,
    *,
    transaction: "m.FinancialTransaction",
    purchase_document_id: int,
    matched_amount_minor: int,
    excluding_match_id: int | None = None,
) -> None:
    """Neither side may be over-committed. Checked in magnitude, so the
    bank's signed convention and the invoice's positive totals compare
    without either being rewritten."""
    committed = session.scalar(
        select(func.sum(func.abs(m.BankInvoiceMatch.matched_amount_minor))).where(
            m.BankInvoiceMatch.financial_transaction_id == transaction.id,
            m.BankInvoiceMatch.status == m.MATCH_CONFIRMED,
            m.BankInvoiceMatch.id != (excluding_match_id or -1),
        )
    )
    committed = int(committed or 0)
    if committed + abs(matched_amount_minor) > abs(transaction.amount_minor):
        raise MatchAmountError(
            f"Matching {abs(matched_amount_minor)} minor units would bring transaction "
            f"{transaction.id} to {committed + abs(matched_amount_minor)}, more than the "
            f"{abs(transaction.amount_minor)} that actually moved. A transaction cannot pay for "
            "more than it is worth."
        )

    payable = document_payable_minor(session, purchase_document_id=purchase_document_id)
    doc_committed = session.scalar(
        select(func.sum(func.abs(m.BankInvoiceMatch.matched_amount_minor))).where(
            m.BankInvoiceMatch.purchase_document_id == purchase_document_id,
            m.BankInvoiceMatch.status == m.MATCH_CONFIRMED,
            m.BankInvoiceMatch.id != (excluding_match_id or -1),
        )
    )
    doc_committed = int(doc_committed or 0)
    if doc_committed + abs(matched_amount_minor) > payable:
        raise MatchAmountError(
            f"Matching {abs(matched_amount_minor)} minor units would bring document "
            f"{purchase_document_id} to {doc_committed + abs(matched_amount_minor)} paid against "
            f"a payable amount of {payable}. Overpayment is not represented by this model — "
            "record a supplier credit instead."
        )


def confirm_match(
    session: Session,
    *,
    match_id: int,
    decided_by_account_id: int | None = None,
    difference_kind: str | None = None,
    difference_note: str | None = None,
) -> "m.BankInvoiceMatch":
    """Promote a proposal to a confirmed match, re-checking both amount
    controls at the moment it actually starts occupying amount."""
    match = session.get(m.BankInvoiceMatch, match_id)
    if match is None:
        raise ValueError(f"Bank Invoice Match {match_id} does not exist.")
    if match.status == m.MATCH_CONFIRMED:
        return match
    if match.status == m.MATCH_REJECTED:
        raise ValueError(f"Match {match_id} was rejected and cannot be confirmed.")

    _assert_amounts_fit(
        session,
        transaction=match.financial_transaction,
        purchase_document_id=match.purchase_document_id,
        matched_amount_minor=match.matched_amount_minor,
        excluding_match_id=match.id,
    )
    match.status = m.MATCH_CONFIRMED
    match.decided_by_account_id = decided_by_account_id
    match.decided_at = _now()
    if difference_kind is not None:
        if difference_kind not in m.MATCH_DIFFERENCE_KINDS:
            raise ValueError(
                f"Difference kind must be one of {', '.join(m.MATCH_DIFFERENCE_KINDS)}, "
                f"got {difference_kind!r}."
            )
        match.difference_kind = difference_kind
    if difference_note is not None:
        match.difference_note = difference_note
    session.flush()
    return match


def reject_match(
    session: Session, *, match_id: int, reason: str, decided_by_account_id: int | None = None,
) -> "m.BankInvoiceMatch":
    """Reject a match. The row stays — a rejected candidate is part of how
    the eventual answer was reached."""
    match = session.get(m.BankInvoiceMatch, match_id)
    if match is None:
        raise ValueError(f"Bank Invoice Match {match_id} does not exist.")
    match.status = m.MATCH_REJECTED
    match.difference_note = reason
    match.decided_by_account_id = decided_by_account_id
    match.decided_at = _now()
    session.flush()
    return match


def confirmed_documents_for_transaction(
    session: Session, *, financial_transaction_id: int,
) -> list["m.BankInvoiceMatch"]:
    return list(
        session.scalars(
            select(m.BankInvoiceMatch)
            .where(
                m.BankInvoiceMatch.financial_transaction_id == financial_transaction_id,
                m.BankInvoiceMatch.status == m.MATCH_CONFIRMED,
            )
            .order_by(m.BankInvoiceMatch.id)
        )
    )


# ---------------------------------------------------------------------------
# Unresolved differences — stated, never absorbed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnmatchedDifference:
    """What a bank movement still has not accounted for."""

    financial_transaction_id: int
    transaction_amount_minor: int
    matched_amount_minor: int
    remaining_minor: int
    explanation: str

    @property
    def is_fully_matched(self) -> bool:
        return self.remaining_minor == 0


def unmatched_difference(
    session: Session, *, financial_transaction_id: int,
) -> UnmatchedDifference:
    """The gap between a payment and the invoices matched to it.

    Always computed, always reported, never rounded away. A remaining
    amount is not an error — it may simply mean the rest of the payment
    covers something no invoice was issued for — but it is never invisible."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")
    matched = matched_total_for_transaction(
        session, financial_transaction_id=financial_transaction_id
    )
    remaining = transaction.amount_minor - matched
    if remaining == 0:
        explanation = "Every unit of this movement is accounted for by a confirmed invoice match."
    elif matched == 0:
        explanation = "No confirmed invoice match accounts for any part of this movement."
    else:
        explanation = (
            f"{abs(remaining)} minor units of this movement are not accounted for by any "
            "confirmed invoice match."
        )
    return UnmatchedDifference(
        financial_transaction_id=financial_transaction_id,
        transaction_amount_minor=transaction.amount_minor,
        matched_amount_minor=matched,
        remaining_minor=remaining,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchCandidate:
    """One deterministic proposal: these documents, for this amount,
    because of these facts."""

    purchase_document_ids: tuple[int, ...]
    amount_minor: int
    confidence: str
    basis: tuple[str, ...]
    difference_minor: int
    difference_kind: str
    is_ambiguous: bool = False

    @property
    def is_combination(self) -> bool:
        return len(self.purchase_document_ids) > 1

    @property
    def may_auto_confirm(self) -> bool:
        """Only an unambiguous, high-confidence, exactly-balancing single
        proposal is ever confirmed without a person."""
        return (
            self.confidence == "HIGH"
            and not self.is_ambiguous
            and self.difference_minor == 0
        )


@dataclass
class CandidateReport:
    """Everything the generator found, including why it refused to act."""

    financial_transaction_id: int
    candidates: list[MatchCandidate] = field(default_factory=list)
    ambiguity_note: str | None = None

    @property
    def auto_confirmable(self) -> MatchCandidate | None:
        """The single candidate safe to confirm automatically, if there is
        exactly one. Two equally good answers means no answer."""
        if self.ambiguity_note:
            return None
        usable = [c for c in self.candidates if c.may_auto_confirm]
        return usable[0] if len(usable) == 1 else None


def _candidate_supplier_ids(
    session: Session, *, transaction: "m.FinancialTransaction", supplier_ids: list[int] | None,
) -> list[int]:
    """Whose invoices to look at.

    Either the caller says, or the transaction's own current WHO decision
    says through the WHO <-> Supplier link. Never every supplier in the
    database: matching on amount alone across unrelated suppliers is how
    a coincidence becomes an accounting entry."""
    if supplier_ids:
        return sorted(set(supplier_ids))
    explanation = session.get(m.BankTransactionExplanation, transaction.explanation_id or -1)
    if explanation is None or explanation.occurrence_id is None:
        return []
    return invoice_evidence.supplier_ids_for_occurrence(
        session, occurrence_id=explanation.occurrence_id
    )


def _effective_date(transaction: "m.FinancialTransaction") -> date | None:
    return transaction.posting_date or transaction.transaction_date


def _reference_text(transaction: "m.FinancialTransaction") -> str:
    """Everything the bank told us in free text, in one upper-cased
    haystack — description, memo and reference together."""
    parts = [
        transaction.description_original,
        transaction.description_normalized,
        transaction.source_memo,
        transaction.reference,
    ]
    return " ".join(part.upper() for part in parts if part)


def generate_candidates(
    session: Session,
    *,
    financial_transaction_id: int,
    supplier_ids: list[int] | None = None,
) -> CandidateReport:
    """Find invoices this payment could be settling.

    Deterministic throughout: the same database produces the same
    candidates in the same order, every time. No fuzzy scoring, no
    randomness, no tie broken by chance — when two answers are equally
    good, the report says so and proposes neither."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")

    report = CandidateReport(financial_transaction_id=financial_transaction_id)
    remaining = transaction_remaining_minor(
        session, financial_transaction_id=financial_transaction_id
    )
    if remaining == 0:
        return report

    suppliers = _candidate_supplier_ids(
        session, transaction=transaction, supplier_ids=supplier_ids,
    )
    if not suppliers:
        return report

    effective = _effective_date(transaction)
    stmt = select(m.PurchaseDocument).where(m.PurchaseDocument.supplier_id.in_(suppliers))
    if effective is not None:
        stmt = stmt.where(
            m.PurchaseDocument.issue_date.is_(None)
            | (
                m.PurchaseDocument.issue_date
                >= datetime.combine(effective - timedelta(days=LOOKBACK_DAYS), datetime.min.time())
            )
        ).where(
            m.PurchaseDocument.issue_date.is_(None)
            | (
                m.PurchaseDocument.issue_date
                <= datetime.combine(
                    effective + timedelta(days=LOOKAHEAD_DAYS), datetime.max.time()
                )
            )
        )

    open_documents = [
        document
        for document in session.scalars(stmt.order_by(m.PurchaseDocument.id))
        if document_remaining_minor(session, purchase_document_id=document.id) > 0
    ]
    if not open_documents:
        return report

    haystack = _reference_text(transaction)
    target = abs(remaining)

    # --- single documents ---------------------------------------------------
    for document in open_documents:
        doc_remaining = document_remaining_minor(session, purchase_document_id=document.id)
        basis: list[str] = [f"supplier {document.supplier_id}"]
        number = (document.document_number or "").strip().upper()
        number_matched = bool(number) and number in haystack
        if number_matched:
            basis.append(f"document number {number} appears in the bank reference")
        if effective is not None and document.issue_date is not None:
            basis.append(f"issued {document.issue_date.date().isoformat()}")

        if doc_remaining == target:
            report.candidates.append(
                MatchCandidate(
                    purchase_document_ids=(document.id,),
                    amount_minor=remaining,
                    confidence="HIGH",
                    basis=tuple(basis + ["amount matches exactly"]),
                    difference_minor=0,
                    difference_kind=m.DIFFERENCE_NONE,
                )
            )
        elif doc_remaining > target:
            # The payment covers part of the invoice. Real, common, and
            # never auto-confirmed: only a person knows whether the rest is
            # still coming or was credited.
            report.candidates.append(
                MatchCandidate(
                    purchase_document_ids=(document.id,),
                    amount_minor=remaining,
                    confidence="HIGH" if number_matched else "MEDIUM",
                    basis=tuple(basis + ["payment is smaller than the invoice"]),
                    difference_minor=doc_remaining - target,
                    difference_kind=m.DIFFERENCE_PARTIAL_PAYMENT,
                )
            )
        elif number_matched:
            # The bank line names this invoice but pays more than it is
            # worth — tax, freight or a fee usually explains it, but RF-One
            # does not decide which. The difference is stated, unexplained.
            report.candidates.append(
                MatchCandidate(
                    purchase_document_ids=(document.id,),
                    amount_minor=(
                        doc_remaining if remaining > 0 else -doc_remaining
                    ),
                    confidence="MEDIUM",
                    basis=tuple(basis + ["payment exceeds this invoice alone"]),
                    difference_minor=target - doc_remaining,
                    difference_kind=m.DIFFERENCE_UNEXPLAINED,
                )
            )

    # --- combinations -------------------------------------------------------
    pool = open_documents[:MAX_COMBINATION_POOL]
    exact_combinations: list[tuple[int, ...]] = []
    for size in range(2, min(MAX_COMBINATION_SIZE, len(pool)) + 1):
        for group in combinations(pool, size):
            total = sum(
                document_remaining_minor(session, purchase_document_id=d.id) for d in group
            )
            if total == target:
                exact_combinations.append(tuple(d.id for d in group))

    if len(exact_combinations) == 1:
        ids = exact_combinations[0]
        report.candidates.append(
            MatchCandidate(
                purchase_document_ids=ids,
                amount_minor=remaining,
                confidence="HIGH",
                basis=(f"{len(ids)} open invoices sum exactly to this payment",),
                difference_minor=0,
                difference_kind=m.DIFFERENCE_NONE,
            )
        )
    elif len(exact_combinations) > 1:
        report.ambiguity_note = (
            f"{len(exact_combinations)} different combinations of open invoices sum to this "
            "payment. RF-One will not choose between them — an operator must say which invoices "
            "were actually paid."
        )
        for ids in exact_combinations:
            report.candidates.append(
                MatchCandidate(
                    purchase_document_ids=ids,
                    amount_minor=remaining,
                    confidence="LOW",
                    basis=("one of several equally valid combinations",),
                    difference_minor=0,
                    difference_kind=m.DIFFERENCE_NONE,
                    is_ambiguous=True,
                )
            )

    # Several single invoices each matching exactly is the same problem.
    exact_singles = [
        c for c in report.candidates if not c.is_combination and c.difference_minor == 0
    ]
    if len(exact_singles) > 1 and report.ambiguity_note is None:
        report.ambiguity_note = (
            f"{len(exact_singles)} different open invoices each match this payment exactly. "
            "RF-One will not guess which one was paid."
        )
        report.candidates = [
            MatchCandidate(
                purchase_document_ids=c.purchase_document_ids,
                amount_minor=c.amount_minor,
                confidence="LOW",
                basis=c.basis + ("several invoices match this amount equally well",),
                difference_minor=c.difference_minor,
                difference_kind=c.difference_kind,
                is_ambiguous=True,
            )
            if c in exact_singles
            else c
            for c in report.candidates
        ]

    report.candidates.sort(
        key=lambda c: (
            {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(c.confidence, 3),
            abs(c.difference_minor),
            c.purchase_document_ids,
        )
    )
    return report


def auto_match(
    session: Session, *, financial_transaction_id: int, supplier_ids: list[int] | None = None,
) -> list["m.BankInvoiceMatch"]:
    """Confirm the one unambiguous, exactly-balancing candidate, if there
    is exactly one. Otherwise write nothing at all and let the candidate
    report speak for itself."""
    report = generate_candidates(
        session,
        financial_transaction_id=financial_transaction_id,
        supplier_ids=supplier_ids,
    )
    candidate = report.auto_confirmable
    if candidate is None:
        return []

    written: list[m.BankInvoiceMatch] = []
    for document_id in candidate.purchase_document_ids:
        amount = document_remaining_minor(session, purchase_document_id=document_id)
        signed = -amount if candidate.amount_minor < 0 else amount
        written.append(
            create_match(
                session,
                financial_transaction_id=financial_transaction_id,
                purchase_document_id=document_id,
                matched_amount_minor=signed,
                match_method="AUTO",
                status=m.MATCH_CONFIRMED,
                confidence=candidate.confidence,
                match_basis="; ".join(candidate.basis),
                difference_kind=m.DIFFERENCE_NONE,
            )
        )
    return written


def propose_candidates(
    session: Session, *, financial_transaction_id: int, supplier_ids: list[int] | None = None,
) -> list["m.BankInvoiceMatch"]:
    """Persist the generator's best non-ambiguous proposal as PROPOSED
    rows for a person to confirm. Ambiguous reports persist nothing."""
    report = generate_candidates(
        session,
        financial_transaction_id=financial_transaction_id,
        supplier_ids=supplier_ids,
    )
    if report.ambiguity_note or not report.candidates:
        return []

    candidate = report.candidates[0]
    if candidate.is_ambiguous:
        return []

    written: list[m.BankInvoiceMatch] = []
    for document_id in candidate.purchase_document_ids:
        amount = min(
            document_remaining_minor(session, purchase_document_id=document_id),
            abs(candidate.amount_minor),
        )
        signed = -amount if candidate.amount_minor < 0 else amount
        written.append(
            create_match(
                session,
                financial_transaction_id=financial_transaction_id,
                purchase_document_id=document_id,
                matched_amount_minor=signed,
                match_method="AUTO",
                status=m.MATCH_PROPOSED,
                confidence=candidate.confidence,
                match_basis="; ".join(candidate.basis),
                difference_kind=candidate.difference_kind,
            )
        )
    return written
