"""Economic Allocation — what a bank movement MEANS, as opposed to where
the money went (BANK_ECONOMIC_ALLOCATION_FOUNDATION_001).

    BANK TRANSACTION    = the movement of money. WHO PAID / WHO WAS PAID.
    ECONOMIC ALLOCATION = FOR WHOM the cost was borne or the revenue
                          earned, and which canonical account it belongs
                          to.

One bank transaction supports 1..N allocations. A $2,000 payment to Cheney
covering food, packaging and supplies is ONE bank transaction with THREE
allocations — never three invented bank transactions. A $1,000 payment to
Gordon Food with a single economic category is ONE bank transaction with
ONE allocation, the same shape, so no consumer ever has to handle a
"split" case and an "unsplit" case differently.

This module owns four things and nothing else:

1. **The balance invariant.** `SUM(allocation.amount_minor)` equals the
   parent's `amount_minor` exactly, in the parent's own sign convention.
   Both sides are integer minor units, so there is nothing to round; a set
   that does not balance is REFUSED. There is no tolerance, hidden or
   otherwise, and no remainder is quietly absorbed into the last line — a
   caller splitting by percentage must decide where the odd cent goes and
   say so.

2. **WHY -> accounting destination.** Derived from the Reason, exactly as
   `BankTransactionReason` already defines it: a P&L Reason yields a WHAT,
   a non-P&L Reason yields a Balance Sheet destination and the allocation
   legitimately has no WHAT at all. There is no per-allocation accounting
   override — an operator picks the WHY, never the account.

3. **Payer versus economic owner.** The payer is resolved through the
   SETTLEMENT ACCOUNT by the existing
   `card_configuration.accounting_account_for` / `legal_entity_for`, which
   this module calls rather than reimplements. The economic owner comes
   from the allocation's `ReportingEntity`. They are allowed to disagree,
   and that disagreement is the point.

4. **The intercompany consequence, derived.** When an LLC pays for another
   LLC's cost, `1610 Due From Related Parties` and `2710 Due To Related
   Parties` follow deterministically. An operator never chooses a
   direction; there is no UI question to get wrong.

Explicitly NOT in this module: invoice matching, invoice line reading,
supplier-item learning, ancillary cost allocation, WHO recognition, learned
WHY rules, QBO/CSV export, and any reimbursement workflow. The next task
(Invoice evidence) builds on this engine; it is not anticipated here beyond
the two deliberately-open `evidence_*` columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import card_configuration

# Re-exported so callers never spell these strings themselves.
UNALLOCATED = m.ALLOCATION_UNALLOCATED
PENDING_EVIDENCE = m.ALLOCATION_PENDING_EVIDENCE
NEEDS_OPERATOR = m.ALLOCATION_NEEDS_OPERATOR
COMPLETE = m.ALLOCATION_COMPLETE


# ---------------------------------------------------------------------------
# Payer resolution — through the settlement account, never the card's own
# `legal_entity_id`
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PayerResolution:
    """WHO paid, in accounting terms.

    Three genuinely different answers, kept apart because conflating them
    is how a personal card ends up looking like a company:

    * `LEGAL_ENTITY` — the settlement account belongs to an LLC.
    * `PERSONAL`     — the settlement account exists and deliberately has
                       no Legal Entity: a personal instrument. Not a gap
                       to be filled with a fictitious LLC.
    * `UNRESOLVED`   — the card has no settlement account configured for
                       that date, so the payer is genuinely unknown.
                       Reported, never guessed.
    """

    kind: str
    legal_entity_id: int | None
    legal_entity_name: str | None
    explanation: str


def resolve_payer(
    session: Session, *, financial_transaction: "m.FinancialTransaction",
) -> PayerResolution:
    """The Legal Entity whose cash actually moved.

    Reuses `card_configuration` verbatim: a BANK_ACCOUNT stands for
    itself, a CREDIT_CARD resolves through its settlement account on the
    transaction's own date. The card's own `legal_entity_id` is never
    consulted, and neither is the cardholder — that is the existing
    canonical rule for deriving a Company, and this module does not
    invent a second one."""
    instrument = session.get(m.PaymentInstrument, financial_transaction.payment_instrument_id)
    if instrument is None:
        return PayerResolution(
            kind=m.PAYER_KIND_UNRESOLVED,
            legal_entity_id=None,
            legal_entity_name=None,
            explanation="The transaction's payment instrument no longer exists.",
        )

    on_date = financial_transaction.posting_date or financial_transaction.transaction_date
    account = card_configuration.accounting_account_for(
        session, instrument=instrument, on_date=on_date,
    )
    if account is None:
        return PayerResolution(
            kind=m.PAYER_KIND_UNRESOLVED,
            legal_entity_id=None,
            legal_entity_name=None,
            explanation=(
                f"Card {instrument.display_name!r} has no settlement account configured for "
                f"{on_date}, so the paying Legal Entity cannot be derived."
            ),
        )
    if account.legal_entity_id is None:
        return PayerResolution(
            kind=m.PAYER_KIND_PERSONAL,
            legal_entity_id=None,
            legal_entity_name=None,
            explanation=(
                f"The settlement account {account.display_name!r} has no Legal Entity: this is a "
                "personal instrument, not a company one."
            ),
        )

    legal_entity = session.get(m.LegalEntity, account.legal_entity_id)
    return PayerResolution(
        kind=m.PAYER_KIND_LEGAL_ENTITY,
        legal_entity_id=account.legal_entity_id,
        legal_entity_name=legal_entity.legal_name if legal_entity else None,
        explanation=(
            f"Paid through settlement account {account.display_name!r}, which belongs to "
            f"{legal_entity.legal_name if legal_entity else 'an unnamed Legal Entity'}."
        ),
    )


# ---------------------------------------------------------------------------
# Intercompany — a deterministic consequence, never an operator's choice
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntercompanyDerivation:
    """What follows, on the Balance Sheet, from payer != economic owner.

    `due_from_code` is what the PAYER records (an asset: the other entity
    owes it money). `due_to_code` is what the ECONOMIC OWNER records (a
    liability). Both are existing canonical accounts, read by code —
    1610 and 2710 — and neither is a P&L line. That is the whole reason a
    future reimbursement settles this position instead of creating a
    second expense.
    """

    outcome: str
    payer_legal_entity_id: int | None
    economic_owner_legal_entity_id: int | None
    due_from_code: str | None
    due_to_code: str | None
    notes: str

    @property
    def creates_position(self) -> bool:
        return self.outcome == m.INTERCOMPANY_CROSS_ENTITY


def derive_intercompany(
    *,
    payer: PayerResolution,
    economic_owner_legal_entity_id: int | None,
    economic_owner_is_virtual: bool,
    personal_funding_treatment: str = m.PERSONAL_FUNDING_REIMBURSABLE,
) -> IntercompanyDerivation:
    """Pure function. Same inputs, same answer, every time — no session,
    no configuration lookup, no operator question.

    The four cases, all of them deliberate:

    1. Payer LLC == economic owner LLC -> NONE. The ordinary case.
    2. Payer LLC != economic owner LLC -> CROSS_ENTITY. 1610 on the
       payer, 2710 on the owner.
    3. Economic owner is a VIRTUAL reporting entity -> NONE. A virtual
       entity is a management view, not a juridical person: it cannot owe
       anybody anything, so no legal position arises. The management P&L
       still lands on it.
    4. Payer is PERSONAL -> no LLC-to-LLC position is invented, because
       there is no second LLC. The business owes the individual back:
       2710 by default, 3300 only on an explicit operator choice.
    5. Payer is UNRESOLVED -> nothing is derived, and that is reported.
    """
    if payer.kind == m.PAYER_KIND_UNRESOLVED:
        return IntercompanyDerivation(
            outcome=m.INTERCOMPANY_NOT_DERIVABLE,
            payer_legal_entity_id=None,
            economic_owner_legal_entity_id=economic_owner_legal_entity_id,
            due_from_code=None,
            due_to_code=None,
            notes=(
                "No intercompany position derived: the paying Legal Entity is unknown. "
                + payer.explanation
            ),
        )

    if payer.kind == m.PAYER_KIND_PERSONAL:
        # A personal instrument paid a legitimate business cost. The
        # allocation records the expense against the right entity; what
        # this decides is the OTHER side of it, on the business's books.
        #
        # Product Owner decision (BANK_INVOICE_EVIDENCE_COLLABORATION_001
        # §19): the default is 2710 Due To Related Parties — the business
        # owes the individual back. It is NOT 3300 Member Contributions,
        # because treating a reimbursable payment as permanent equity
        # would assert something nobody said. 3300 requires the operator
        # to state explicitly that the funding is non-reimbursable.
        #
        # No LLC-to-LLC position arises either way: there is no second
        # Legal Entity, and none is invented for the individual.
        if personal_funding_treatment == m.PERSONAL_FUNDING_MEMBER_CONTRIBUTION:
            return IntercompanyDerivation(
                outcome=m.INTERCOMPANY_PERSONAL_PAYER_CONTRIBUTION,
                payer_legal_entity_id=None,
                economic_owner_legal_entity_id=economic_owner_legal_entity_id,
                due_from_code=None,
                due_to_code=m.MEMBER_CONTRIBUTIONS_CODE,
                notes=(
                    "A personal payment instrument bore this cost, and an operator explicitly "
                    f"classified the funding as a non-reimbursable Member Contribution, so the "
                    f"business side is {m.MEMBER_CONTRIBUTIONS_CODE} Member Contributions rather "
                    f"than {m.DUE_TO_RELATED_PARTIES_CODE}. No Legal Entity is created for the "
                    "individual. " + payer.explanation
                ),
            )
        if personal_funding_treatment != m.PERSONAL_FUNDING_REIMBURSABLE:
            raise ValueError(
                "Personal funding treatment must be one of "
                f"{', '.join(m.PERSONAL_FUNDING_TREATMENTS)}, got "
                f"{personal_funding_treatment!r}."
            )
        return IntercompanyDerivation(
            outcome=m.INTERCOMPANY_PERSONAL_PAYER_DUE_TO,
            payer_legal_entity_id=None,
            economic_owner_legal_entity_id=economic_owner_legal_entity_id,
            due_from_code=None,
            due_to_code=m.DUE_TO_RELATED_PARTIES_CODE,
            notes=(
                "A personal payment instrument bore this cost, so the business records "
                f"{m.DUE_TO_RELATED_PARTIES_CODE} Due To Related Parties: it owes the individual "
                "back. This is the default and is never silently treated as a Member "
                "Contribution. No LLC-to-LLC intercompany position is created and no Legal "
                "Entity is invented for the individual. " + payer.explanation
            ),
        )

    if economic_owner_is_virtual or economic_owner_legal_entity_id is None:
        return IntercompanyDerivation(
            outcome=m.INTERCOMPANY_NONE,
            payer_legal_entity_id=payer.legal_entity_id,
            economic_owner_legal_entity_id=None,
            due_from_code=None,
            due_to_code=None,
            notes=(
                "No intercompany position: the economic owner is a VIRTUAL reporting entity, "
                "which is a management view rather than a juridical person and therefore cannot "
                "hold a receivable or a payable."
            ),
        )

    if payer.legal_entity_id == economic_owner_legal_entity_id:
        return IntercompanyDerivation(
            outcome=m.INTERCOMPANY_NONE,
            payer_legal_entity_id=payer.legal_entity_id,
            economic_owner_legal_entity_id=economic_owner_legal_entity_id,
            due_from_code=None,
            due_to_code=None,
            notes="The paying Legal Entity is also the economic owner; nothing is owed.",
        )

    return IntercompanyDerivation(
        outcome=m.INTERCOMPANY_CROSS_ENTITY,
        payer_legal_entity_id=payer.legal_entity_id,
        economic_owner_legal_entity_id=economic_owner_legal_entity_id,
        due_from_code=m.DUE_FROM_RELATED_PARTIES_CODE,
        due_to_code=m.DUE_TO_RELATED_PARTIES_CODE,
        notes=(
            "The paying Legal Entity is not the economic owner. The payer records "
            f"{m.DUE_FROM_RELATED_PARTIES_CODE} Due From Related Parties and the economic owner "
            f"records {m.DUE_TO_RELATED_PARTIES_CODE} Due To Related Parties. Both are Balance "
            "Sheet positions: the future reimbursement settles them and never creates a second "
            "P&L expense."
        ),
    )


# ---------------------------------------------------------------------------
# Writing allocations
# ---------------------------------------------------------------------------


@dataclass
class AllocationSpec:
    """One requested line of economic meaning.

    `amount_minor` follows the parent's sign convention — money out is
    negative, money in positive. There is no second sign system and no
    "absolute value plus a direction flag"."""

    amount_minor: int
    reporting_entity_id: int | None = None
    transaction_reason_id: int | None = None
    # Only consulted when the PAYER is a personal instrument (§19). The
    # default means "the business owes the individual back" -> 2710.
    # MEMBER_CONTRIBUTION is an explicit operator statement -> 3300, and
    # is never reached by omission.
    personal_funding_treatment: str = m.PERSONAL_FUNDING_REIMBURSABLE
    status: str = COMPLETE
    decision_source: str | None = "HUMAN"
    decided_by_account_id: int | None = None
    evidence_kind: str | None = None
    evidence_reference: str | None = None
    notes: str | None = None


class AllocationBalanceError(ValueError):
    """The requested allocations do not sum to the parent transaction.

    Its own class because this is the one failure a caller is most likely
    to want to catch and explain to a person, and because silently
    tolerating it is precisely what this foundation exists to prevent."""


def _resolve_reason(
    session: Session, transaction_reason_id: int | None,
) -> tuple["m.BankTransactionReason | None", "m.BankAccountingClassification | None"]:
    if transaction_reason_id is None:
        return None, None
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Transaction Reason {transaction_reason_id} does not exist.")
    return reason, reason.accounting_classification


def set_allocations(
    session: Session,
    *,
    financial_transaction_id: int,
    specs: list[AllocationSpec],
    replace_existing: bool = True,
) -> list["m.BankTransactionAllocation"]:
    """Write the COMPLETE set of allocations for one transaction, atomically.

    Set-based on purpose. An incremental "add one line" API would make it
    possible for a transaction to sit, even briefly, allocated to $1,500
    of a $2,000 movement — a state in which every report is wrong and
    nothing says so. Here a transaction's allocations are always either
    absent or balanced.

    Every derived value is computed here, from the WHY and from the payer,
    and stored as a snapshot: the caller supplies WHO it is for and WHY,
    never an account and never a Due From/Due To direction."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")
    if not specs:
        raise ValueError(
            "An allocation set must contain at least one line. To leave a transaction "
            "unallocated, write no allocations at all."
        )

    total = sum(spec.amount_minor for spec in specs)
    if total != transaction.amount_minor:
        raise AllocationBalanceError(
            f"Allocations sum to {total} minor units but the bank transaction is "
            f"{transaction.amount_minor}. The difference of {total - transaction.amount_minor} "
            "is not absorbed: an allocation set must match its bank transaction exactly, in the "
            "same sign convention."
        )

    existing = list(
        session.scalars(
            select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == financial_transaction_id
            )
        )
    )
    if existing and not replace_existing:
        raise ValueError(
            f"Financial Transaction {financial_transaction_id} already has "
            f"{len(existing)} allocation(s). Pass replace_existing=True to restate them."
        )

    # EVERY spec is validated and resolved BEFORE the existing set is
    # touched. A restatement that turns out to be invalid must leave the
    # previous, valid allocations exactly as they were — losing them to a
    # typo in the replacement would be far worse than the typo.
    resolved: list[
        tuple[
            AllocationSpec,
            "m.ReportingEntity | None",
            "m.BankTransactionReason | None",
            "m.BankAccountingClassification | None",
        ]
    ] = []
    for spec in specs:
        if spec.status not in m.ALLOCATION_STATUSES:
            raise ValueError(
                f"Allocation status must be one of {', '.join(m.ALLOCATION_STATUSES)}, "
                f"got {spec.status!r}."
            )
        if spec.amount_minor == 0:
            raise ValueError("An allocation of zero carries no economic meaning.")

        entity: m.ReportingEntity | None = None
        if spec.reporting_entity_id is not None:
            entity = session.get(m.ReportingEntity, spec.reporting_entity_id)
            if entity is None:
                raise ValueError(f"Reporting Entity {spec.reporting_entity_id} does not exist.")

        reason, classification = _resolve_reason(session, spec.transaction_reason_id)

        if spec.status == COMPLETE:
            if entity is None:
                raise ValueError(
                    "A COMPLETE allocation must say who it is for: no Reporting Entity was given."
                )
            if reason is None:
                raise ValueError("A COMPLETE allocation must have a WHY.")
            if classification is None:
                raise ValueError(
                    f"WHY {reason.code!r} has no accounting destination configured, so this "
                    "allocation cannot be completed. The destination is derived from the WHY and "
                    "is never chosen per allocation."
                )

        resolved.append((spec, entity, reason, classification))

    for row in existing:
        session.delete(row)
    session.flush()

    payer = resolve_payer(session, financial_transaction=transaction)
    now = datetime.now(timezone.utc)

    written: list[m.BankTransactionAllocation] = []
    for index, (spec, entity, reason, classification) in enumerate(resolved):
        derivation = derive_intercompany(
            payer=payer,
            economic_owner_legal_entity_id=entity.legal_entity_id if entity else None,
            economic_owner_is_virtual=bool(entity and entity.is_virtual),
            personal_funding_treatment=spec.personal_funding_treatment,
        )

        allocation = m.BankTransactionAllocation(
            financial_transaction_id=financial_transaction_id,
            allocation_index=index,
            amount_minor=spec.amount_minor,
            reporting_entity_id=spec.reporting_entity_id,
            transaction_reason_id=spec.transaction_reason_id,
            accounting_classification_id=classification.id if classification else None,
            accounting_classification_code_snapshot=classification.code if classification else None,
            accounting_classification_name_snapshot=(
                classification.name if classification else None
            ),
            accounting_statement_type_snapshot=(
                classification.statement_type if classification else None
            ),
            transaction_reason_name_snapshot=reason.name if reason else None,
            reporting_entity_name_snapshot=entity.name if entity else None,
            payer_legal_entity_id=payer.legal_entity_id,
            payer_kind=payer.kind,
            economic_owner_legal_entity_id=entity.legal_entity_id if entity else None,
            intercompany_outcome=derivation.outcome,
            intercompany_due_from_code_snapshot=derivation.due_from_code,
            intercompany_due_to_code_snapshot=derivation.due_to_code,
            intercompany_notes=derivation.notes,
            status=spec.status,
            decision_source=spec.decision_source,
            decided_by_account_id=spec.decided_by_account_id,
            decided_at=now if spec.decision_source else None,
            evidence_kind=spec.evidence_kind,
            evidence_reference=spec.evidence_reference,
            notes=spec.notes,
        )
        session.add(allocation)
        written.append(allocation)

    session.flush()
    return written


def get_allocations(
    session: Session, *, financial_transaction_id: int,
) -> list["m.BankTransactionAllocation"]:
    """This transaction's allocations, in the order they were decided."""
    return list(
        session.scalars(
            select(m.BankTransactionAllocation)
            .where(
                m.BankTransactionAllocation.financial_transaction_id == financial_transaction_id
            )
            .order_by(m.BankTransactionAllocation.allocation_index)
        )
    )


def clear_allocations(session: Session, *, financial_transaction_id: int) -> int:
    """Remove every allocation for a transaction, returning it to
    UNALLOCATED. Used when a decision turns out to be wrong; the parent
    bank movement itself is untouched."""
    rows = get_allocations(session, financial_transaction_id=financial_transaction_id)
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


# ---------------------------------------------------------------------------
# Reading the allocation state of a transaction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllocationState:
    """The ACCOUNTING state of a transaction, which is a different
    question from whether the transaction is a canonical financial fact.

    `FinancialTransaction.accounting_status = CANONICAL` says the movement
    is the one true occurrence of that bank event. It says nothing about
    whether anybody has decided who bore its cost. A canonical transaction
    may sit here UNALLOCATED indefinitely, and that is not an error."""

    financial_transaction_id: int
    transaction_amount_minor: int
    allocated_amount_minor: int
    allocation_count: int
    status: str
    is_balanced: bool
    incomplete_statuses: tuple[str, ...] = field(default_factory=tuple)

    @property
    def difference_minor(self) -> int:
        return self.allocated_amount_minor - self.transaction_amount_minor

    @property
    def is_accounting_closed(self) -> bool:
        """Whether this transaction's economic meaning is fully settled.
        Requires every line COMPLETE and the set balanced — an allocation
        still waiting on evidence is never treated as closed."""
        return self.status == COMPLETE and self.is_balanced


def allocation_state(session: Session, *, financial_transaction_id: int) -> AllocationState:
    """Summarize a transaction's allocations without interpreting them."""
    transaction = session.get(m.FinancialTransaction, financial_transaction_id)
    if transaction is None:
        raise ValueError(f"Financial Transaction {financial_transaction_id} does not exist.")

    rows = get_allocations(session, financial_transaction_id=financial_transaction_id)
    allocated = sum(row.amount_minor for row in rows)

    if not rows:
        status = UNALLOCATED
    elif all(row.status == COMPLETE for row in rows):
        status = COMPLETE
    elif any(row.status == NEEDS_OPERATOR for row in rows):
        status = NEEDS_OPERATOR
    elif any(row.status == PENDING_EVIDENCE for row in rows):
        status = PENDING_EVIDENCE
    else:
        status = UNALLOCATED

    return AllocationState(
        financial_transaction_id=financial_transaction_id,
        transaction_amount_minor=transaction.amount_minor,
        allocated_amount_minor=allocated,
        allocation_count=len(rows),
        status=status,
        # No allocations at all is not an imbalance — it is an absence,
        # and the two must not be reported as the same problem.
        is_balanced=(not rows) or allocated == transaction.amount_minor,
        incomplete_statuses=tuple(
            sorted({row.status for row in rows if row.status != COMPLETE})
        ),
    )
