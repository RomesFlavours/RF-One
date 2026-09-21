"""Credit Card configuration — settlement account and cardholder history
(BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).

Two historized facts about a Credit Card, kept strictly apart because
they have different consequences:

    Credit Card -> Settlement Bank Account -> Company / Legal Entity
    Credit Card -> Cardholder (responsibility only)

The **settlement account** is an accounting fact. It derives the Company
of the card's transactions and scopes accounting deduplication. The
**cardholder** is a responsibility fact and is inert for accounting: this
module never reads a holder when resolving a settlement account, a
Company, or a duplicate key, and there is no code path by which it could.

Everything here is historized rather than overwritten (`valid_from` /
`valid_to`), because a transaction posted in 2025 must be attributed to
the configuration that was true in 2025. Reassignment closes the previous
row and inserts a new one; nothing is ever physically deleted.

Nothing is invented for an existing card. A card with no settlement
account configured stays visibly unconfigured, and
`accounting_dedup.py` reports its transactions as un-deduplicable rather
than guessing an account for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m

CREDIT_CARD = "CREDIT_CARD"
BANK_ACCOUNT = "BANK_ACCOUNT"

# How deep a settlement chain may be followed before it is treated as
# cyclic. A legitimate chain is Card -> Bank Account, i.e. one hop; this
# bound exists so a pre-existing cycle in data can never hang a caller.
_MAX_SETTLEMENT_CHAIN = 10


# ---------------------------------------------------------------------------
# Settlement account — Card -> Bank Account -> Company
# ---------------------------------------------------------------------------


def _require_credit_card(session: Session, instrument_id: int) -> "m.PaymentInstrument":
    instrument = session.get(m.PaymentInstrument, instrument_id)
    if instrument is None:
        raise ValueError(f"Payment Instrument {instrument_id} does not exist.")
    if instrument.instrument_type != CREDIT_CARD:
        raise ValueError(
            f"{instrument.display_name!r} is a {instrument.instrument_type}, not a credit card. "
            "A settlement account and a cardholder apply to credit cards only."
        )
    return instrument


def _require_bank_account(session: Session, instrument_id: int | None) -> "m.PaymentInstrument":
    if instrument_id is None:
        raise ValueError("Select the bank account this card settles to.")
    account = session.get(m.PaymentInstrument, instrument_id)
    if account is None:
        raise ValueError(f"Payment Instrument {instrument_id} does not exist.")
    if account.instrument_type != BANK_ACCOUNT:
        raise ValueError(
            f"{account.display_name!r} is a {account.instrument_type}. A card must settle to a "
            "BANK_ACCOUNT — never to another card."
        )
    return account


def _reject_settlement_cycle(session: Session, *, card_id: int, settlement_account_id: int) -> None:
    """A card never settles to itself, and following the settlement chain
    from the proposed account must never lead back to the card. The chain
    is walked through both the historized open assignments and the legacy
    `linked_instrument_id`, so a cycle cannot be smuggled in through the
    older column."""
    if card_id == settlement_account_id:
        raise ValueError("A card cannot settle to itself.")

    current_id: int | None = settlement_account_id
    seen: set[int] = {card_id}
    for _ in range(_MAX_SETTLEMENT_CHAIN):
        if current_id is None:
            return
        if current_id in seen:
            raise ValueError(
                "That settlement account would create a circular settlement chain."
            )
        seen.add(current_id)

        open_assignment = session.scalars(
            select(m.BankCardSettlementAccount).where(
                m.BankCardSettlementAccount.credit_card_payment_instrument_id == current_id,
                m.BankCardSettlementAccount.valid_to.is_(None),
            )
        ).first()
        if open_assignment is not None:
            current_id = open_assignment.settlement_bank_account_id
            continue

        instrument = session.get(m.PaymentInstrument, current_id)
        current_id = instrument.linked_instrument_id if instrument is not None else None

    raise ValueError("That settlement account would create a circular settlement chain.")


def _overlapping_assignment(
    session: Session, *, card_id: int, valid_from: date, valid_to: date | None,
    exclude_id: int | None = None,
) -> "m.BankCardSettlementAccount | None":
    """Two assignments for the same card must never cover the same day.
    Half-open comparison: a row is [valid_from, valid_to), so closing one
    on the day the next starts is legitimate, not an overlap."""
    query = select(m.BankCardSettlementAccount).where(
        m.BankCardSettlementAccount.credit_card_payment_instrument_id == card_id,
    )
    if exclude_id is not None:
        query = query.where(m.BankCardSettlementAccount.id != exclude_id)
    for existing in session.scalars(query).all():
        starts_before_other_ends = valid_to is None or existing.valid_from < valid_to
        other_starts_before_this_ends = existing.valid_to is None or valid_from < existing.valid_to
        if starts_before_other_ends and other_starts_before_this_ends:
            return existing
    return None


def assign_settlement_account(
    session: Session, *, credit_card_payment_instrument_id: int,
    settlement_bank_account_id: int | None, valid_from: date,
    notes: str | None = None, created_by_account_id: int | None = None,
) -> "m.BankCardSettlementAccount":
    """Assign (or re-assign) the bank account a card settles to, effective
    `valid_from`.

    Re-assignment CLOSES the currently open row on `valid_from` and
    inserts a new one — the previous configuration stays readable, so a
    transaction posted while it was in force is still explainable.
    Re-assigning to the same account on the same date is idempotent.

    `PaymentInstrument.linked_instrument_id` is kept in step with whichever
    assignment is now open, so cross-ledger matching (which has always
    read that column) keeps working and the two can never disagree."""
    card = _require_credit_card(session, credit_card_payment_instrument_id)
    account = _require_bank_account(session, settlement_bank_account_id)
    _reject_settlement_cycle(
        session, card_id=card.id, settlement_account_id=account.id,
    )

    open_assignment = session.scalars(
        select(m.BankCardSettlementAccount).where(
            m.BankCardSettlementAccount.credit_card_payment_instrument_id == card.id,
            m.BankCardSettlementAccount.valid_to.is_(None),
        )
    ).first()

    if open_assignment is not None:
        if (
            open_assignment.settlement_bank_account_id == account.id
            and open_assignment.valid_from == valid_from
        ):
            return open_assignment  # idempotent: nothing actually changed
        if valid_from <= open_assignment.valid_from:
            raise ValueError(
                f"The current settlement account for {card.display_name!r} is effective from "
                f"{open_assignment.valid_from.isoformat()}. A new assignment must start after that "
                "date, so the history stays in order."
            )
        open_assignment.valid_to = valid_from
        session.flush()

    clash = _overlapping_assignment(
        session, card_id=card.id, valid_from=valid_from, valid_to=None,
    )
    if clash is not None:
        raise ValueError(
            f"That period overlaps an existing settlement assignment for {card.display_name!r} "
            f"({clash.valid_from.isoformat()} - "
            f"{clash.valid_to.isoformat() if clash.valid_to else 'open'})."
        )

    assignment = m.BankCardSettlementAccount(
        credit_card_payment_instrument_id=card.id,
        settlement_bank_account_id=account.id,
        valid_from=valid_from,
        notes=(notes or "").strip() or None,
        created_by_account_id=created_by_account_id,
    )
    session.add(assignment)
    card.linked_instrument_id = account.id
    session.flush()
    return assignment


def settlement_account_on(
    session: Session, *, credit_card_payment_instrument_id: int, on_date: date | None,
) -> "m.PaymentInstrument | None":
    """The bank account the card settled to on `on_date`.

    Falls back to `PaymentInstrument.linked_instrument_id` ONLY when no
    historized assignment covers that date — this is what lets a card
    configured before this task, through the older column alone, still be
    attributed correctly instead of suddenly becoming unresolved. The
    fallback still requires the linked instrument to be a BANK_ACCOUNT;
    anything else resolves to nothing rather than to a guess."""
    if on_date is not None:
        for assignment in session.scalars(
            select(m.BankCardSettlementAccount)
            .where(
                m.BankCardSettlementAccount.credit_card_payment_instrument_id
                == credit_card_payment_instrument_id,
                m.BankCardSettlementAccount.valid_from <= on_date,
                or_(
                    m.BankCardSettlementAccount.valid_to.is_(None),
                    m.BankCardSettlementAccount.valid_to > on_date,
                ),
            )
            .order_by(m.BankCardSettlementAccount.valid_from.desc())
        ).all():
            return session.get(m.PaymentInstrument, assignment.settlement_bank_account_id)

    card = session.get(m.PaymentInstrument, credit_card_payment_instrument_id)
    if card is None or card.linked_instrument_id is None:
        return None
    linked = session.get(m.PaymentInstrument, card.linked_instrument_id)
    if linked is not None and linked.instrument_type == BANK_ACCOUNT:
        return linked
    return None


def current_settlement_account(
    session: Session, credit_card_payment_instrument_id: int,
) -> "m.PaymentInstrument | None":
    return settlement_account_on(
        session, credit_card_payment_instrument_id=credit_card_payment_instrument_id,
        on_date=date.today(),
    )


def settlement_history(
    session: Session, credit_card_payment_instrument_id: int,
) -> list["m.BankCardSettlementAccount"]:
    """Most recent first. The open assignment, when there is one, is the
    first row."""
    return list(session.scalars(
        select(m.BankCardSettlementAccount)
        .where(
            m.BankCardSettlementAccount.credit_card_payment_instrument_id
            == credit_card_payment_instrument_id
        )
        .order_by(m.BankCardSettlementAccount.valid_from.desc(), m.BankCardSettlementAccount.id.desc())
    ).all())


def correct_settlement_assignment(
    session: Session, *, assignment_id: int, settlement_bank_account_id: int | None,
    valid_from: date, notes: str | None = None,
) -> "m.BankCardSettlementAccount":
    """Fix an assignment that was recorded wrongly — a correction, not a
    new period. The row is edited in place (so no phantom period appears
    in the history) and `notes` is what carries the trace of why; the row
    is never deleted, and the change is still bounded by the same overlap
    and cycle rules as a new assignment."""
    assignment = session.get(m.BankCardSettlementAccount, assignment_id)
    if assignment is None:
        raise ValueError(f"Settlement assignment {assignment_id} does not exist.")
    account = _require_bank_account(session, settlement_bank_account_id)
    _reject_settlement_cycle(
        session, card_id=assignment.credit_card_payment_instrument_id,
        settlement_account_id=account.id,
    )
    if assignment.valid_to is not None and valid_from >= assignment.valid_to:
        raise ValueError(
            f"This assignment ends on {assignment.valid_to.isoformat()}, so it must start before that."
        )
    clash = _overlapping_assignment(
        session, card_id=assignment.credit_card_payment_instrument_id,
        valid_from=valid_from, valid_to=assignment.valid_to, exclude_id=assignment.id,
    )
    if clash is not None:
        raise ValueError(
            "That period overlaps another settlement assignment for this card "
            f"({clash.valid_from.isoformat()} - "
            f"{clash.valid_to.isoformat() if clash.valid_to else 'open'})."
        )

    assignment.settlement_bank_account_id = account.id
    assignment.valid_from = valid_from
    if notes is not None:
        assignment.notes = notes.strip() or None
    session.flush()

    if assignment.valid_to is None:
        card = session.get(m.PaymentInstrument, assignment.credit_card_payment_instrument_id)
        if card is not None:
            card.linked_instrument_id = account.id
            session.flush()
    return assignment


# ---------------------------------------------------------------------------
# Company derivation — always through the settlement account
# ---------------------------------------------------------------------------


def accounting_account_for(
    session: Session, *, instrument: "m.PaymentInstrument", on_date: date | None,
) -> "m.PaymentInstrument | None":
    """The instrument whose Legal Entity owns this movement, accounting-wise.

    A BANK_ACCOUNT stands for itself. A CREDIT_CARD resolves through its
    settlement account for `on_date` — so the Company of a card
    transaction comes from the account the card is paid from, never from
    the card's own `legal_entity_id` and never from whoever holds the
    card. A PAYPAL instrument is unchanged by this task and stands for
    itself, exactly as before."""
    if instrument.instrument_type == CREDIT_CARD:
        return settlement_account_on(
            session, credit_card_payment_instrument_id=instrument.id, on_date=on_date,
        )
    return instrument


def legal_entity_for(
    session: Session, *, instrument: "m.PaymentInstrument", on_date: date | None,
) -> "m.LegalEntity | None":
    """The Company/Legal Entity of a transaction on this instrument.
    Returns None rather than falling back to the card's own Legal Entity:
    an unconfigured card must be visibly unconfigured, not quietly
    attributed to whichever company someone once typed on the card."""
    account = accounting_account_for(session, instrument=instrument, on_date=on_date)
    if account is None or account.legal_entity_id is None:
        return None
    return session.get(m.LegalEntity, account.legal_entity_id)


# ---------------------------------------------------------------------------
# Cardholder — responsibility only
# ---------------------------------------------------------------------------


def _validated_holder(
    session: Session, *, holder_kind: str, holder_acting_identity_id: int | None,
    holder_employee_id: int | None, holder_display_name: str | None,
) -> dict:
    """One place decides what a valid holder reference is, so the create
    and correct paths can never disagree. A canonical identity is used
    whenever one is supplied; `UNLINKED_PERSON` is the explicit, honest
    fallback rather than a silently empty reference."""
    if holder_kind not in m.CARD_HOLDER_KINDS:
        raise ValueError(
            f"Holder kind must be one of {', '.join(m.CARD_HOLDER_KINDS)}, got {holder_kind!r}."
        )

    display_name = (holder_display_name or "").strip()

    if holder_kind == m.CARD_HOLDER_KIND_ACTING_IDENTITY:
        if holder_acting_identity_id is None:
            raise ValueError("Select the identity holding this card.")
        identity = session.get(m.ActingIdentity, holder_acting_identity_id)
        if identity is None:
            raise ValueError(f"Acting Identity {holder_acting_identity_id} does not exist.")
        return {
            "holder_kind": holder_kind,
            "holder_acting_identity_id": identity.id,
            "holder_employee_id": None,
            "holder_display_name": display_name or identity.display_name,
        }

    if holder_kind == m.CARD_HOLDER_KIND_EMPLOYEE:
        if holder_employee_id is None:
            raise ValueError("Select the employee holding this card.")
        employee = session.get(m.Employee, holder_employee_id)
        if employee is None:
            raise ValueError(f"Employee {holder_employee_id} does not exist.")
        return {
            "holder_kind": holder_kind,
            "holder_acting_identity_id": None,
            "holder_employee_id": employee.id,
            "holder_display_name": display_name or employee.display_name or f"Employee {employee.id}",
        }

    if not display_name:
        raise ValueError("State the name of the person holding this card.")
    return {
        "holder_kind": m.CARD_HOLDER_KIND_UNLINKED_PERSON,
        "holder_acting_identity_id": None,
        "holder_employee_id": None,
        "holder_display_name": display_name,
    }


def _overlapping_holder(
    session: Session, *, card_id: int, valid_from: date, valid_to: date | None,
    exclude_id: int | None = None,
) -> "m.BankCardHolderAssignment | None":
    query = select(m.BankCardHolderAssignment).where(
        m.BankCardHolderAssignment.credit_card_payment_instrument_id == card_id,
    )
    if exclude_id is not None:
        query = query.where(m.BankCardHolderAssignment.id != exclude_id)
    for existing in session.scalars(query).all():
        starts_before_other_ends = valid_to is None or existing.valid_from < valid_to
        other_starts_before_this_ends = existing.valid_to is None or valid_from < existing.valid_to
        if starts_before_other_ends and other_starts_before_this_ends:
            return existing
    return None


def assign_cardholder(
    session: Session, *, credit_card_payment_instrument_id: int, holder_kind: str,
    valid_from: date, holder_acting_identity_id: int | None = None,
    holder_employee_id: int | None = None, holder_display_name: str | None = None,
    notes: str | None = None, created_by_account_id: int | None = None,
) -> "m.BankCardHolderAssignment":
    """Record who holds this card from `valid_from`.

    A reassignment closes the open assignment on that date and inserts a
    new one, so the previous holder's period survives intact — which is
    the whole point: responsibility for a past charge belongs to whoever
    held the card then, not to whoever holds it now. Two overlapping
    holders for one card are refused."""
    card = _require_credit_card(session, credit_card_payment_instrument_id)
    holder = _validated_holder(
        session, holder_kind=holder_kind,
        holder_acting_identity_id=holder_acting_identity_id,
        holder_employee_id=holder_employee_id,
        holder_display_name=holder_display_name,
    )

    open_assignment = session.scalars(
        select(m.BankCardHolderAssignment).where(
            m.BankCardHolderAssignment.credit_card_payment_instrument_id == card.id,
            m.BankCardHolderAssignment.valid_to.is_(None),
        )
    ).first()

    if open_assignment is not None:
        same_holder = (
            open_assignment.holder_kind == holder["holder_kind"]
            and open_assignment.holder_acting_identity_id == holder["holder_acting_identity_id"]
            and open_assignment.holder_employee_id == holder["holder_employee_id"]
            and open_assignment.holder_display_name == holder["holder_display_name"]
        )
        if same_holder and open_assignment.valid_from == valid_from:
            return open_assignment  # idempotent
        if valid_from <= open_assignment.valid_from:
            raise ValueError(
                f"The current holder of {card.display_name!r} is recorded from "
                f"{open_assignment.valid_from.isoformat()}. A new assignment must start after that "
                "date, so the history stays in order."
            )
        open_assignment.valid_to = valid_from
        session.flush()

    clash = _overlapping_holder(
        session, card_id=card.id, valid_from=valid_from, valid_to=None,
    )
    if clash is not None:
        raise ValueError(
            f"That period overlaps an existing cardholder assignment for {card.display_name!r} "
            f"({clash.valid_from.isoformat()} - "
            f"{clash.valid_to.isoformat() if clash.valid_to else 'open'})."
        )

    assignment = m.BankCardHolderAssignment(
        credit_card_payment_instrument_id=card.id,
        valid_from=valid_from,
        notes=(notes or "").strip() or None,
        created_by_account_id=created_by_account_id,
        **holder,
    )
    session.add(assignment)
    session.flush()
    return assignment


def correct_cardholder_assignment(
    session: Session, *, assignment_id: int, holder_kind: str, valid_from: date,
    holder_acting_identity_id: int | None = None, holder_employee_id: int | None = None,
    holder_display_name: str | None = None, notes: str | None = None,
) -> "m.BankCardHolderAssignment":
    """Fix a holder assignment recorded wrongly, in place, keeping the row
    and its `notes` as the trace of the correction. Never a delete."""
    assignment = session.get(m.BankCardHolderAssignment, assignment_id)
    if assignment is None:
        raise ValueError(f"Cardholder assignment {assignment_id} does not exist.")
    holder = _validated_holder(
        session, holder_kind=holder_kind,
        holder_acting_identity_id=holder_acting_identity_id,
        holder_employee_id=holder_employee_id,
        holder_display_name=holder_display_name,
    )
    if assignment.valid_to is not None and valid_from >= assignment.valid_to:
        raise ValueError(
            f"This assignment ends on {assignment.valid_to.isoformat()}, so it must start before that."
        )
    clash = _overlapping_holder(
        session, card_id=assignment.credit_card_payment_instrument_id,
        valid_from=valid_from, valid_to=assignment.valid_to, exclude_id=assignment.id,
    )
    if clash is not None:
        raise ValueError(
            "That period overlaps another cardholder assignment for this card "
            f"({clash.valid_from.isoformat()} - "
            f"{clash.valid_to.isoformat() if clash.valid_to else 'open'})."
        )

    for field, value in holder.items():
        setattr(assignment, field, value)
    assignment.valid_from = valid_from
    if notes is not None:
        assignment.notes = notes.strip() or None
    session.flush()
    return assignment


def cardholder_on(
    session: Session, *, credit_card_payment_instrument_id: int, on_date: date,
) -> "m.BankCardHolderAssignment | None":
    return session.scalars(
        select(m.BankCardHolderAssignment)
        .where(
            m.BankCardHolderAssignment.credit_card_payment_instrument_id
            == credit_card_payment_instrument_id,
            m.BankCardHolderAssignment.valid_from <= on_date,
            or_(
                m.BankCardHolderAssignment.valid_to.is_(None),
                m.BankCardHolderAssignment.valid_to > on_date,
            ),
        )
        .order_by(m.BankCardHolderAssignment.valid_from.desc())
    ).first()


def current_cardholder(
    session: Session, credit_card_payment_instrument_id: int,
) -> "m.BankCardHolderAssignment | None":
    return session.scalars(
        select(m.BankCardHolderAssignment).where(
            m.BankCardHolderAssignment.credit_card_payment_instrument_id
            == credit_card_payment_instrument_id,
            m.BankCardHolderAssignment.valid_to.is_(None),
        )
    ).first()


def cardholder_history(
    session: Session, credit_card_payment_instrument_id: int,
) -> list["m.BankCardHolderAssignment"]:
    return list(session.scalars(
        select(m.BankCardHolderAssignment)
        .where(
            m.BankCardHolderAssignment.credit_card_payment_instrument_id
            == credit_card_payment_instrument_id
        )
        .order_by(m.BankCardHolderAssignment.valid_from.desc(), m.BankCardHolderAssignment.id.desc())
    ).all())


# ---------------------------------------------------------------------------
# Recovery of settlement configuration saved through the legacy field
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LegacyRecoveryCandidate:
    """One card whose settlement account was configured through the older
    `PaymentInstrument.linked_instrument_id` field before the historized
    table existed. `valid_from` is None exactly when the card has no
    imported transaction to date the period from — that case is reported
    for a human, never dated on a guess."""

    credit_card_id: int
    credit_card_name: str
    settlement_account_id: int
    settlement_account_name: str
    valid_from: date | None
    transaction_count: int
    skip_reason: str | None = None

    @property
    def recoverable(self) -> bool:
        return self.skip_reason is None


RECOVERY_NOTE = "Recovered from legacy Settles to configuration"


def plan_legacy_settlement_recovery(session: Session) -> list[LegacyRecoveryCandidate]:
    """Preview, writing nothing.

    The ONE source of truth is `linked_instrument_id` — the value a human
    actually saved. File names, `last_four` and institution are never
    consulted: inventing a link from those would be guessing, and the
    whole point of this recovery is that the human already decided.

    A card is a candidate only when all of the following hold:

    * it is a CREDIT_CARD;
    * `linked_instrument_id` points at an existing BANK_ACCOUNT;
    * it has NO historized settlement row yet — a card already configured
      through the canonical path is left completely alone, so a human
      decision is never overwritten.

    `valid_from` is the earliest posting date among that card's imported
    transactions, so the recovered period covers the whole history the
    database actually holds. A card with no transactions yields no date
    and is reported with a `skip_reason` instead."""
    candidates: list[LegacyRecoveryCandidate] = []

    cards = session.scalars(
        select(m.PaymentInstrument)
        .where(
            m.PaymentInstrument.instrument_type == CREDIT_CARD,
            m.PaymentInstrument.linked_instrument_id.is_not(None),
        )
        .order_by(m.PaymentInstrument.id)
    ).all()

    for card in cards:
        existing = session.scalars(
            select(m.BankCardSettlementAccount).where(
                m.BankCardSettlementAccount.credit_card_payment_instrument_id == card.id
            )
        ).first()
        if existing is not None:
            continue  # already historized — never touched again

        account = session.get(m.PaymentInstrument, card.linked_instrument_id)
        transaction_count = session.scalar(
            select(func.count(m.FinancialTransaction.id))
            .where(m.FinancialTransaction.payment_instrument_id == card.id)
        ) or 0
        earliest = session.scalar(
            select(func.min(m.FinancialTransaction.posting_date))
            .where(
                m.FinancialTransaction.payment_instrument_id == card.id,
                m.FinancialTransaction.posting_date.is_not(None),
            )
        )

        skip_reason = None
        if account is None:
            skip_reason = (
                f"the linked instrument {card.linked_instrument_id} does not exist"
            )
        elif account.instrument_type != BANK_ACCOUNT:
            skip_reason = (
                f"the linked instrument {account.display_name!r} is a "
                f"{account.instrument_type}, not a BANK_ACCOUNT"
            )
        elif account.id == card.id:
            skip_reason = "the card is linked to itself"
        elif earliest is None:
            skip_reason = (
                "the card has no imported transaction, so there is no evidence of when "
                "this settlement configuration started — a human must state the date"
            )

        candidates.append(LegacyRecoveryCandidate(
            credit_card_id=card.id,
            credit_card_name=card.display_name,
            settlement_account_id=account.id if account is not None else card.linked_instrument_id,
            settlement_account_name=account.display_name if account is not None else "(missing)",
            valid_from=earliest,
            transaction_count=transaction_count,
            skip_reason=skip_reason,
        ))

    return candidates


def apply_legacy_settlement_recovery(
    session: Session, *, created_by_account_id: int | None = None,
) -> list[LegacyRecoveryCandidate]:
    """Write the recoverable candidates into the historized table, and
    return exactly those that were written.

    Idempotent by construction: `plan_legacy_settlement_recovery` excludes
    any card that already has a historized row, so running this a second
    time finds nothing left to do, creates no duplicate row, and changes
    no existing one.

    Each row carries `RECOVERY_NOTE`, so a reader can always tell a
    recovered configuration from one a human entered through the UI."""
    written: list[LegacyRecoveryCandidate] = []
    for candidate in plan_legacy_settlement_recovery(session):
        if not candidate.recoverable:
            continue
        assignment = m.BankCardSettlementAccount(
            credit_card_payment_instrument_id=candidate.credit_card_id,
            settlement_bank_account_id=candidate.settlement_account_id,
            valid_from=candidate.valid_from,
            notes=RECOVERY_NOTE,
            created_by_account_id=created_by_account_id,
        )
        session.add(assignment)
        written.append(candidate)
    session.flush()
    return written


def configuration_warning(session: Session, instrument: "m.PaymentInstrument") -> str | None:
    """The one sentence the Payment Instruments page shows when a card is
    not yet usable for accounting. A missing cardholder is deliberately
    NOT a warning: it has no accounting consequence."""
    if instrument.instrument_type != CREDIT_CARD:
        return None
    account = current_settlement_account(session, instrument.id)
    if account is None:
        return (
            "No settlement account configured — this card's transactions cannot be attributed to a "
            "Company and cannot be deduplicated for accounting."
        )
    if account.legal_entity_id is None:
        return (
            f"The settlement account {account.display_name!r} has no Company/Legal Entity, so this "
            "card's transactions have no Company."
        )
    return None
