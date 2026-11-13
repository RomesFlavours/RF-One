"""P&L and intercompany reporting, driven by Economic Allocations
(BANK_ECONOMIC_ALLOCATION_FOUNDATION_001).

**The P&L is generated from allocations, never from bank parent rows.**

That sentence is the whole design. Every query in this module reads
`bank_transaction_allocations` and joins to `financial_transactions` only
to find out WHEN the movement happened. Not one query reads
`FinancialTransaction.classification` or a parent's
`BankTransactionExplanation` accounting snapshot. There is therefore no
arithmetic anywhere that could add a $2,000 parent to its own $2,000 of
children: double counting is not prevented by a filter that someone has to
remember, it is absent from the model.

Two consequences worth stating plainly, because they are properties rather
than corrections:

* **Multi-category.** A $2,000 payment split into $1,500 food, $300
  packaging and $200 supplies contributes exactly $2,000 to the P&L,
  across three lines. The parent contributes nothing, because nothing
  reads it.
* **Cross-entity.** When RF Gelati pays a vendor for RF Mount Dora, the
  cost appears once, on RF Mount Dora. The offsetting Due From / Due To is
  a Balance Sheet position and is reported separately, by
  `intercompany_positions`, which is not part of any P&L. So a
  consolidated P&L over the group contains the external cost exactly once
  — not twice, and not zero times.

What counts and what does not
-----------------------------
Only allocations whose `status` is COMPLETE enter a P&L. An allocation
still waiting on evidence, or waiting on an operator, is a stated unknown
and is never treated as accounting-closed. `unallocated_transactions` and
`allocation_exceptions` exist so that unknown is visible rather than
silently missing from a total.

Sign convention: the parent's, unchanged. Money out is negative, money in
positive. There is no second sign system in RF-One and this module does not
introduce one — expenses read as negative amounts, and a caller that wants
to print them positively flips them at the point of display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfitAndLossLine:
    """One canonical P&L account and what landed on it."""

    code: str
    name: str
    amount_minor: int
    allocation_count: int

    @property
    def display_label(self) -> str:
        return f"{self.code} — {self.name}"


@dataclass(frozen=True)
class ProfitAndLossReport:
    """A P&L for one reporting entity or one consolidation perimeter.

    `scope_kind` is REPORTING_ENTITY or REPORTING_GROUP. A VIRTUAL entity
    produces a management P&L here exactly as a LEGAL one produces its
    LLC's P&L — same query, same shape, no special case."""

    scope_kind: str
    scope_id: int
    scope_label: str
    date_from: date | None
    date_to: date | None
    lines: tuple[ProfitAndLossLine, ...]
    total_minor: int
    allocation_count: int

    def line_for(self, code: str) -> ProfitAndLossLine | None:
        for line in self.lines:
            if line.code == code:
                return line
        return None


@dataclass(frozen=True)
class IntercompanyPosition:
    """One directed Balance Sheet position between two Legal Entities.

    Read it as: `payer_legal_entity` has a receivable (1610 Due From
    Related Parties) of `amount_minor` against `owner_legal_entity`, which
    has the mirror payable (2710 Due To Related Parties).

    Never a P&L line. A later reimbursement settles this position; it does
    not create a second expense, and nothing in this module would let it."""

    payer_legal_entity_id: int
    payer_legal_entity_name: str | None
    owner_legal_entity_id: int
    owner_legal_entity_name: str | None
    amount_minor: int
    allocation_count: int
    due_from_code: str
    due_to_code: str


@dataclass(frozen=True)
class AllocationException:
    """A transaction whose economic meaning is not settled, and why.

    Present so that "we do not know" is reported rather than rounded to
    zero inside a total."""

    financial_transaction_id: int
    amount_minor: int
    reason: str


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------


def _date_predicates(date_from: date | None, date_to: date | None) -> list:
    """Filter on the movement's own date. `posting_date` is the accounting
    date when the source supplies one; `transaction_date` is the fallback.
    A transaction carrying neither is never silently dated to today — it
    simply falls outside any bounded window and is reported by
    `allocation_exceptions`."""
    effective = func.coalesce(
        m.FinancialTransaction.posting_date, m.FinancialTransaction.transaction_date
    )
    predicates = []
    if date_from is not None:
        predicates.append(effective >= date_from)
    if date_to is not None:
        predicates.append(effective <= date_to)
    return predicates


def _profit_and_loss(
    session: Session,
    *,
    entity_predicate,
    scope_kind: str,
    scope_id: int,
    scope_label: str,
    date_from: date | None,
    date_to: date | None,
) -> ProfitAndLossReport:
    A = m.BankTransactionAllocation

    stmt = (
        select(
            A.accounting_classification_code_snapshot,
            A.accounting_classification_name_snapshot,
            func.sum(A.amount_minor),
            func.count(A.id),
        )
        .join(m.FinancialTransaction, m.FinancialTransaction.id == A.financial_transaction_id)
        .join(m.ReportingEntity, m.ReportingEntity.id == A.reporting_entity_id)
        .where(
            A.status == m.ALLOCATION_COMPLETE,
            # Only the P&L side. A Balance Sheet allocation is not a
            # smaller P&L line; it belongs to a different statement.
            A.accounting_statement_type_snapshot == "PROFIT_LOSS",
            entity_predicate,
            *_date_predicates(date_from, date_to),
        )
        .group_by(
            A.accounting_classification_code_snapshot,
            A.accounting_classification_name_snapshot,
        )
        .order_by(A.accounting_classification_code_snapshot)
    )

    lines = tuple(
        ProfitAndLossLine(
            code=code, name=name or "", amount_minor=int(total or 0), allocation_count=int(count),
        )
        for code, name, total, count in session.execute(stmt).all()
    )

    return ProfitAndLossReport(
        scope_kind=scope_kind,
        scope_id=scope_id,
        scope_label=scope_label,
        date_from=date_from,
        date_to=date_to,
        lines=lines,
        total_minor=sum(line.amount_minor for line in lines),
        allocation_count=sum(line.allocation_count for line in lines),
    )


def profit_and_loss_for_entity(
    session: Session,
    *,
    reporting_entity_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ProfitAndLossReport:
    """The P&L of one reporting entity — the LLC's P&L for a LEGAL entity,
    the management P&L for a VIRTUAL one.

    Contains what that entity ECONOMICALLY bore or earned, regardless of
    whose card paid. A transaction paid by another entity's card, and
    allocated here, appears here; a transaction paid by this entity's card
    but allocated elsewhere does not."""
    entity = session.get(m.ReportingEntity, reporting_entity_id)
    if entity is None:
        raise ValueError(f"Reporting Entity {reporting_entity_id} does not exist.")

    return _profit_and_loss(
        session,
        entity_predicate=(m.BankTransactionAllocation.reporting_entity_id == reporting_entity_id),
        scope_kind="REPORTING_ENTITY",
        scope_id=reporting_entity_id,
        scope_label=entity.display_label,
        date_from=date_from,
        date_to=date_to,
    )


def consolidated_profit_and_loss(
    session: Session,
    *,
    reporting_group_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ProfitAndLossReport:
    """The consolidated P&L of a whole perimeter.

    Correct by construction, not by adjustment. Each allocation names
    exactly one reporting entity, and each entity belongs to at most one
    group, so summing the group's allocations counts every economic fact
    exactly once. The intercompany Due From / Due To that a cross-entity
    payment creates is a Balance Sheet position and never enters this
    query, which is why an external cost paid by one LLC for another
    appears here once rather than twice."""
    group = session.get(m.ReportingGroup, reporting_group_id)
    if group is None:
        raise ValueError(f"Reporting Group {reporting_group_id} does not exist.")

    return _profit_and_loss(
        session,
        entity_predicate=(m.ReportingEntity.reporting_group_id == reporting_group_id),
        scope_kind="REPORTING_GROUP",
        scope_id=reporting_group_id,
        scope_label=group.name,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# Intercompany positions — Balance Sheet, never P&L
# ---------------------------------------------------------------------------


def intercompany_positions(
    session: Session, *, date_from: date | None = None, date_to: date | None = None,
) -> list[IntercompanyPosition]:
    """Every Due From / Due To position the allocations imply.

    Derived, not recorded by an operator: a position exists precisely
    where a COMPLETE allocation's payer Legal Entity differs from its
    economic owner's. Amounts stay in the parent's sign convention, so a
    cost paid on somebody else's behalf carries the same sign it had on
    the bank line."""
    A = m.BankTransactionAllocation

    stmt = (
        select(
            A.payer_legal_entity_id,
            A.economic_owner_legal_entity_id,
            func.sum(A.amount_minor),
            func.count(A.id),
        )
        .join(m.FinancialTransaction, m.FinancialTransaction.id == A.financial_transaction_id)
        .where(
            A.status == m.ALLOCATION_COMPLETE,
            A.intercompany_outcome == m.INTERCOMPANY_CROSS_ENTITY,
            *_date_predicates(date_from, date_to),
        )
        .group_by(A.payer_legal_entity_id, A.economic_owner_legal_entity_id)
        .order_by(A.payer_legal_entity_id, A.economic_owner_legal_entity_id)
    )

    positions: list[IntercompanyPosition] = []
    for payer_id, owner_id, total, count in session.execute(stmt).all():
        payer = session.get(m.LegalEntity, payer_id) if payer_id else None
        owner = session.get(m.LegalEntity, owner_id) if owner_id else None
        positions.append(
            IntercompanyPosition(
                payer_legal_entity_id=payer_id,
                payer_legal_entity_name=payer.legal_name if payer else None,
                owner_legal_entity_id=owner_id,
                owner_legal_entity_name=owner.legal_name if owner else None,
                amount_minor=int(total or 0),
                allocation_count=int(count),
                due_from_code=m.DUE_FROM_RELATED_PARTIES_CODE,
                due_to_code=m.DUE_TO_RELATED_PARTIES_CODE,
            )
        )
    return positions


# ---------------------------------------------------------------------------
# What the P&L deliberately does not contain
# ---------------------------------------------------------------------------


def allocation_exceptions(
    session: Session, *, date_from: date | None = None, date_to: date | None = None,
) -> list[AllocationException]:
    """Transactions whose economic meaning is not settled.

    Three kinds, all of them stated rather than absorbed:

    * no allocation at all — nobody has decided who bore this yet;
    * allocations that do not sum to the parent — refused on write, so
      this can only appear after a direct database edit, and it is
      reported rather than trusted;
    * allocations that exist but are not all COMPLETE.

    A financially canonical transaction appearing here is normal. It means
    the money is understood and the meaning is not."""
    A = m.BankTransactionAllocation
    T = m.FinancialTransaction

    exceptions: list[AllocationException] = []

    unallocated = session.execute(
        select(T.id, T.amount_minor)
        .outerjoin(A, A.financial_transaction_id == T.id)
        .where(A.id.is_(None), *_date_predicates(date_from, date_to))
        .order_by(T.id)
    ).all()
    for transaction_id, amount in unallocated:
        exceptions.append(
            AllocationException(
                financial_transaction_id=transaction_id,
                amount_minor=amount,
                reason="No economic allocation has been decided for this transaction.",
            )
        )

    grouped = session.execute(
        select(T.id, T.amount_minor, func.sum(A.amount_minor))
        .join(A, A.financial_transaction_id == T.id)
        .where(*_date_predicates(date_from, date_to))
        .group_by(T.id, T.amount_minor)
        .order_by(T.id)
    ).all()

    incomplete_ids = {
        row[0]
        for row in session.execute(
            select(A.financial_transaction_id)
            .where(A.status != m.ALLOCATION_COMPLETE)
            .distinct()
        ).all()
    }

    for transaction_id, parent_amount, allocated in grouped:
        allocated = int(allocated or 0)
        if allocated != parent_amount:
            exceptions.append(
                AllocationException(
                    financial_transaction_id=transaction_id,
                    amount_minor=parent_amount,
                    reason=(
                        f"Allocations sum to {allocated} minor units but the transaction is "
                        f"{parent_amount}."
                    ),
                )
            )
        elif transaction_id in incomplete_ids:
            exceptions.append(
                AllocationException(
                    financial_transaction_id=transaction_id,
                    amount_minor=parent_amount,
                    reason="One or more allocations are not COMPLETE.",
                )
            )

    return exceptions


def allocation_driven_transaction_ids(session: Session) -> set[int]:
    """Transactions that have at least one allocation.

    Useful to any future consumer that still reads parent-level accounting
    (the Kermali export does, and this task deliberately does not change
    it): a transaction in this set carries its economic truth in its
    allocations, and reading its parent classification as well would count
    the same money twice."""
    A = m.BankTransactionAllocation
    return {
        row[0]
        for row in session.execute(select(A.financial_transaction_id).distinct()).all()
    }


def transactions_with_competing_parent_classification(session: Session) -> list[int]:
    """Transactions that have allocations AND a current parent decision
    resolving to a P&L account.

    Not an error and not repaired here: the parent decision remains
    legitimate reconciliation provenance, and this module's own P&L never
    reads it. This function exists so the boundary is auditable from
    outside — anything that DOES read parent classifications can ask which
    transactions it must not count."""
    A = m.BankTransactionAllocation
    T = m.FinancialTransaction
    E = m.BankTransactionExplanation

    rows = session.execute(
        select(T.id)
        .join(A, A.financial_transaction_id == T.id)
        .join(E, E.id == T.explanation_id)
        .where(
            or_(
                E.accounting_statement_type_snapshot == "PROFIT_LOSS",
                E.what_label_snapshot.is_not(None),
            )
        )
        .distinct()
        .order_by(T.id)
    ).all()
    return [row[0] for row in rows]


# ---------------------------------------------------------------------------
# Period completeness — two different questions, never one
# (BANK_INVOICE_EVIDENCE_COLLABORATION_001 §21)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodCompleteness:
    """What a month knows, split into the three questions it actually has.

    These are NOT the same thing and are never reported as one:

    * `source_period_status` — did every instrument's source file arrive?
      Owned by `BankMonthlySourcePeriod` and untouched here.
    * `financially_reconciled` — is every movement in the month a resolved
      financial fact (canonical, or deliberately suppressed as a
      duplicate)?
    * `accounting_complete` — has somebody decided what every movement
      MEANS, with the evidence that required?

    A month can be fully reconciled financially and still be accounting
    incomplete, because a multi-category supplier's invoice has not
    arrived. Collapsing the two would let that month be signed off as
    finished when its P&L is still missing a category split nobody has
    made.
    """

    period_month: str
    source_period_status: str | None
    transaction_count: int
    financially_resolved_count: int
    accounting_complete_count: int
    pending_evidence_count: int
    needs_operator_count: int
    unallocated_count: int
    unbalanced_transaction_ids: tuple[int, ...]
    blocking_transaction_ids: tuple[int, ...]

    @property
    def financially_reconciled(self) -> bool:
        """Every movement is a resolved financial fact. Says nothing
        whatever about what any of them means."""
        return (
            self.transaction_count > 0
            and self.financially_resolved_count == self.transaction_count
        )

    @property
    def accounting_complete(self) -> bool:
        """Every movement's economic meaning is settled and balanced."""
        return (
            self.transaction_count > 0
            and self.accounting_complete_count == self.transaction_count
            and not self.unbalanced_transaction_ids
        )

    @property
    def summary(self) -> str:
        if self.transaction_count == 0:
            return f"{self.period_month}: no bank movements."
        financial = "reconciled" if self.financially_reconciled else "not fully reconciled"
        if self.accounting_complete:
            accounting = "accounting complete"
        else:
            accounting = (
                f"ACCOUNTING INCOMPLETE — {len(self.blocking_transaction_ids)} movement(s) "
                "still without a settled economic meaning"
            )
        return f"{self.period_month}: financially {financial}; {accounting}."


def evaluate_period_completeness(
    session: Session, *, period_month: str, period_start: date, period_end: date,
) -> PeriodCompleteness:
    """Evaluate one month on both axes at once, without conflating them.

    `period_month`/`period_start`/`period_end` are passed in rather than
    looked up, so this works for a month that has no
    `BankMonthlySourcePeriod` row yet — an unopened month is still a real
    month with real movements in it."""
    A = m.BankTransactionAllocation
    T = m.FinancialTransaction

    transactions = list(
        session.scalars(
            select(T).where(*_date_predicates(period_start, period_end)).order_by(T.id)
        )
    )

    financially_resolved = 0
    accounting_complete = 0
    pending_evidence = 0
    needs_operator = 0
    unallocated = 0
    unbalanced: list[int] = []
    blocking: list[int] = []

    for transaction in transactions:
        # A resolved financial fact: RF-One knows which occurrence of this
        # movement is the real one. UNRESOLVED_NO_SETTLEMENT_ACCOUNT and a
        # missing status are both "not yet".
        if transaction.accounting_status in ("CANONICAL", "DUPLICATE_SUPPRESSED"):
            financially_resolved += 1

        rows = list(
            session.scalars(
                select(A).where(A.financial_transaction_id == transaction.id)
            )
        )
        if not rows:
            unallocated += 1
            blocking.append(transaction.id)
            continue

        allocated = sum(row.amount_minor for row in rows)
        if allocated != transaction.amount_minor:
            unbalanced.append(transaction.id)

        statuses = {row.status for row in rows}
        if m.ALLOCATION_PENDING_EVIDENCE in statuses:
            pending_evidence += 1
        if m.ALLOCATION_NEEDS_OPERATOR in statuses:
            needs_operator += 1

        if statuses == {m.ALLOCATION_COMPLETE} and allocated == transaction.amount_minor:
            accounting_complete += 1
        else:
            blocking.append(transaction.id)

    return PeriodCompleteness(
        period_month=period_month,
        source_period_status=session.scalar(
            select(m.BankMonthlySourcePeriod.status).where(
                m.BankMonthlySourcePeriod.period_month == period_month
            )
        ),
        transaction_count=len(transactions),
        financially_resolved_count=financially_resolved,
        accounting_complete_count=accounting_complete,
        pending_evidence_count=pending_evidence,
        needs_operator_count=needs_operator,
        unallocated_count=unallocated,
        unbalanced_transaction_ids=tuple(unbalanced),
        blocking_transaction_ids=tuple(blocking),
    )
