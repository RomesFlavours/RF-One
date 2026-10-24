"""Every usable WHY has a valid WHAT (BANK_WHY_REQUIRES_WHAT_001, Product
Owner, 2026-10-21).

This supersedes BANK_WHY_WITHOUT_WHAT_001 ("reconciliation is WHO + WHY,
bookkeeping comes later"):

* a WHY with no valid accounting classification is a DRAFT. It may be kept
  in the catalog and completed later, but it can never classify a movement;
* a WHY's WHAT is DERIVED from the WHY. A decision or allocation whose WHAT
  differs from its WHY's is refused (no transaction-level WHAT exception for
  a new assignment);
* the WHAT of a usable WHY cannot be removed, and a WHAT still required by
  an active WHY cannot be deactivated or turned into a reporting group.

"WHAT" here is the WHY's single accounting classification
(`accounting_classification_id`): a P&L posting category, or the Balance
Sheet destination of a WHY that settles a liability or moves money — the
catalog's own model, where a Balance Sheet WHY deliberately has no P&L line.

`install()` registers ONE server-side check on every flush, so every path —
manual reconciliation, AI rules, BANK_FLOW_2 rules, imports, bulk
applications, allocations, configuration — meets the same rule, whatever
service wrote the row. The explicit checks in `recognition` and the AI
`Planner` only give the same answer earlier, with a readable outcome.

History is never reclassified: a new decision that merely CARRIES OVER the
WHY and WHAT the movement already had (e.g. an AI rule changing only the
WHO) is not a new assignment and is allowed, even if that WHY is now a
draft."""

from __future__ import annotations

from sqlalchemy import event, select
from sqlalchemy.orm import Session, attributes

from .. import models as m

NO_WHAT_MESSAGE = "This WHY has no associated WHAT. Complete its configuration before using it."
LEGACY_MESSAGE = ("This WHY is a legacy entry to resolve and cannot be used for new classifications. "
                  "Choose a canonical WHY.")
# The "Legacy - To Resolve" WHY group (BANK_WHY_LEGACY_001).
LEGACY_GROUP_CODE = "TO_REVIEW"
# Provisional WHYs (Product Owner decisions 74-76 and 79, 2026-10-24): the ONLY explicit exception to this
# rule. Exactly these WHYs, in the "Provisional" group and with no WHAT, may be assigned: they describe a
# movement whose nature is not known yet, and the reconciliation engine keeps it an Exception.
PROVISIONAL_GROUP_CODE = "PROVISIONAL"
PROVISIONAL_WHY_CODES = frozenset({"ONLINE_PURCHASE_UNIDENTIFIED", "CASH_CHECK_DEPOSIT", "WITHDRAWAL"})


class WhyWithoutWhatError(ValueError):
    """A draft WHY (no valid WHAT) was proposed for a movement."""

    def __init__(self, message: str = NO_WHAT_MESSAGE):
        super().__init__(message)


class IncoherentWhyWhatError(ValueError):
    """A WHAT different from the one associated with the WHY."""


def valid_what(what: "m.BankAccountingClassification | None") -> bool:
    """An accounting classification a WHY may resolve to for new work."""
    return what is not None and what.is_complete and what.is_posting_account


def usable_what(session: Session, reason: "m.BankTransactionReason | None") -> "m.BankAccountingClassification | None":
    """The WHAT a WHY classifies to, or None when the WHY is a draft. Read by
    id, so a mapping edited earlier in the same session is the one used."""
    if reason is None or reason.accounting_classification_id is None:
        return None
    what = session.get(m.BankAccountingClassification, reason.accounting_classification_id)
    return what if valid_what(what) else None


def is_legacy(session: Session, reason: "m.BankTransactionReason | None") -> bool:
    """BANK_WHY_LEGACY_001 — a legacy WHY with no unambiguous canonical
    meaning: kept visible for the movements it already classifies, never
    used for a new assignment, whatever WHAT it has."""
    if reason is None or reason.reason_group_id is None:
        return False
    group = session.get(m.BankReasonGroup, reason.reason_group_id)
    return group is not None and group.code == LEGACY_GROUP_CODE


def is_provisional(session: Session, reason: "m.BankTransactionReason | None") -> bool:
    """One of the approved provisional WHYs: listed code, Provisional group, no WHAT."""
    if reason is None or reason.code not in PROVISIONAL_WHY_CODES or reason.accounting_classification_id is not None:
        return False
    group = session.get(m.BankReasonGroup, reason.reason_group_id) if reason.reason_group_id else None
    return group is not None and group.code == PROVISIONAL_GROUP_CODE


def assignment_problem(session: Session, reason: "m.BankTransactionReason | None") -> str | None:
    """Why this WHY cannot classify a movement now, or None when it can."""
    if reason is None:
        return "This WHY does not exist."
    if reason.status != "ACTIVE":
        return f"WHY “{reason.name}” is inactive; choose its canonical WHY."
    if is_legacy(session, reason):
        return LEGACY_MESSAGE
    if is_provisional(session, reason):
        return None
    if usable_what(session, reason) is None:
        return NO_WHAT_MESSAGE
    return None


def is_usable(session: Session, reason: "m.BankTransactionReason | None") -> bool:
    return assignment_problem(session, reason) is None


def require_what(session: Session, transaction_reason_id: int) -> "m.BankAccountingClassification | None":
    """The WHAT of a WHY about to classify a movement; refuses a draft, legacy
    or inactive WHY. None only for a provisional WHY, which has no WHAT."""
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    problem = assignment_problem(session, reason)
    if problem is not None:
        raise WhyWithoutWhatError(problem)
    return usable_what(session, reason)


def incoherent_message(reason: "m.BankTransactionReason", what: "m.BankAccountingClassification",
                       chosen: "m.BankAccountingClassification | None") -> str:
    chosen_label = f"{chosen.code} — {chosen.name}" if chosen is not None else "no WHAT"
    return (f"WHY “{reason.name}” resolves to WHAT {what.code} — {what.name}; it cannot be saved with "
            f"{chosen_label}. The WHAT is derived from the WHY.")


# ---------------------------------------------------------------------------
# The server-side check on every flush
# ---------------------------------------------------------------------------

def _changed(obj, *names: str) -> bool:
    state = attributes.instance_state(obj)
    return any(state.attrs[name].history.has_changes() for name in names)


def _carried_over(session: Session, txn_id: int, pair: tuple, exclude) -> bool:
    """Whether (WHY, WHAT) is a pair this movement already recorded — in any of
    its decisions (the chain is append-only, so a rollback restores an earlier
    one by inserting it again) or in its persistent allocations — so writing it
    again is not a new assignment. Human and AI paths refuse a draft before
    reaching here, so this only lets history be restored, never extended."""
    with session.no_autoflush:
        previous = session.scalars(
            select(m.BankTransactionExplanation)
            .where(m.BankTransactionExplanation.financial_transaction_id == txn_id)
        ).all()
        if any(e is not exclude and (e.transaction_reason_id, e.accounting_classification_id) == pair
               for e in previous):
            return True
        for allocation in session.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == txn_id)):
            if allocation is not exclude and (
                    allocation.transaction_reason_id, allocation.accounting_classification_id) == pair:
                return True
    return False


def _check_assignment(session: Session, obj) -> None:
    reason_id = obj.transaction_reason_id
    if reason_id is None:
        return
    if not (obj in session.new or _changed(obj, "transaction_reason_id", "accounting_classification_id")):
        return
    pair = (reason_id, obj.accounting_classification_id)
    with session.no_autoflush:
        reason = session.get(m.BankTransactionReason, reason_id)
        problem = assignment_problem(session, reason)
        what = usable_what(session, reason)
        if problem is None and what is None:
            # A provisional WHY: never with a WHAT, nothing to derive.
            if obj.accounting_classification_id is not None:
                raise IncoherentWhyWhatError(f"WHY “{reason.name}” is provisional and has no WHAT.")
            return
        if problem is None and obj.accounting_classification_id == what.id:
            return
        if _carried_over(session, obj.financial_transaction_id, pair, obj):
            return
        if problem is not None:
            raise WhyWithoutWhatError(problem)
        if obj.accounting_classification_id is None:
            # Derived automatically from the WHY (rule 5), never left empty.
            obj.accounting_classification_id = what.id
            return
        chosen = (session.get(m.BankAccountingClassification, obj.accounting_classification_id)
                  if obj.accounting_classification_id is not None else None)
        raise IncoherentWhyWhatError(incoherent_message(reason, what, chosen))


def _check_reason(session: Session, reason: "m.BankTransactionReason") -> None:
    if not (reason in session.new or _changed(reason, "accounting_classification_id")):
        return
    new_id = reason.accounting_classification_id
    if new_id is None:
        old = attributes.instance_state(reason).attrs["accounting_classification_id"].history.deleted
        if reason.status == "ACTIVE" and any(value is not None for value in old):
            raise ValueError(
                f"WHY “{reason.name}” is in use: its WHAT cannot be removed. Associate another WHAT, "
                "or deactivate the WHY first.")
        return
    with session.no_autoflush:
        what = session.get(m.BankAccountingClassification, new_id)
    if not valid_what(what):
        label = f"{what.code} — {what.name}" if what is not None else str(new_id)
        raise ValueError(f"WHAT {label} is inactive, incomplete or a reporting group; a WHY cannot use it.")


def _check_classification(session: Session, what: "m.BankAccountingClassification", deleted: bool) -> None:
    if not deleted and (what in session.new or valid_what(what)
                        or not _changed(what, "active", "statement_type", "node_type")):
        return
    with session.no_autoflush:
        users = session.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.accounting_classification_id == what.id,
            m.BankTransactionReason.status == "ACTIVE",
        ).order_by(m.BankTransactionReason.name)).all()
    if users:
        names = ", ".join(r.name for r in users[:5]) + (f" and {len(users) - 5} more" if len(users) > 5 else "")
        raise ValueError(
            f"WHAT {what.code} — {what.name} is the WHAT of active WHYs ({names}). Associate them with another "
            "WHAT before deactivating or removing it.")


def _before_flush(session: Session, flush_context, instances) -> None:
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, (m.BankTransactionExplanation, m.BankTransactionAllocation)):
            _check_assignment(session, obj)
        elif isinstance(obj, m.BankTransactionReason):
            _check_reason(session, obj)
        elif isinstance(obj, m.BankAccountingClassification):
            _check_classification(session, obj, deleted=False)
    for obj in list(session.deleted):
        if isinstance(obj, m.BankAccountingClassification):
            _check_classification(session, obj, deleted=True)


def install() -> None:
    """Register the check once for every Session (idempotent)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
