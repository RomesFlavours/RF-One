"""The two Review queues: To Reconcile and Reconciled (BANK_TWO_STAGE_REVIEW_001).

Both are VIEWS over facts already persisted — no status is stored to decide
where a transaction belongs:

    Reconciled    the WHO question is ANSWERED — which is not the same as a
                  WHO being named. Either:
                  * its CURRENT decision (`FinancialTransaction.explanation_id`
                    -> `BankTransactionExplanation.occurrence_id`) names a
                    WHO — from a person, an AI rule, or an earlier decision;
                    or
                  * it is an own-account movement, for which the model
                    deliberately records NO WHO: one side of a confirmed
                    INTERNAL_TRANSFER match (`FinancialTransactionMatch`,
                    the authority the Monthly Export trusts).
                  WHY, WHAT or For Whom may still be open: the row is
                  finished on the Reconciled tab.
    To Reconcile  everything else in scope: no decision, or a decision naming
                  no WHO — and any transaction whose duplicate question is
                  still open, because a possible duplicate is not yet a
                  transaction anyone should reconcile.

(The structural WHO recognitions of the old rule system, which could also
answer the WHO question, were retired by BANK_RULES_RESET_001.)

Scope: the transactions the books are about — the same scope as the Monthly
Export (`export._not_confirmed_duplicate`, `accounting_dedup.
not_suppressed_filter`). A copy suppressed as an accounting duplicate needs no
WHO work and is never counted; it stays VISIBLE at the end of To Reconcile,
marked as excluded, because the Review is also the audit view of what the
deduplication removed (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).

Everything here is a bounded number of SQL statements, whatever the month's
size: the counts are one grouped query, each queue one query.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup
from . import export as export_service

TO_RECONCILE = "to_reconcile"
RECONCILED = "reconciled"
VIEWS = (TO_RECONCILE, RECONCILED)
ROW_LIMIT = 500


@dataclass(frozen=True)
class ReviewFilters:
    year: int | None = None
    month: int | None = None
    payment_instrument_id: int | None = None
    batch_id: int | None = None
    # BANK_REVIEW_SEARCH_001 — one literal text, ANDed with the filters above.
    search: str | None = None


_LIKE_ESCAPE = "\\"


def _contains(column, text: str):
    """`column` contains `text`, case-insensitive, LITERALLY: `%`, `_` and the
    escape character itself are escaped, and the value is a bound parameter."""
    escaped = text.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2).replace("%", _LIKE_ESCAPE + "%").replace(
        "_", _LIKE_ESCAPE + "_")
    return column.ilike(f"%{escaped}%", escape=_LIKE_ESCAPE)


def _search_condition(text: str):
    """BANK_REVIEW_SEARCH_001 — the text appears in ONE of four fields, and
    only these: the description, the name of the current decision's WHO, the
    name of its WHY, the name of the Source. Correlated EXISTS, so a
    transaction is never repeated whatever it is joined to; an empty field
    simply does not match."""
    explanation = m.BankTransactionExplanation
    return or_(
        _contains(m.FinancialTransaction.description_original, text),
        exists().where(m.BankOccurrence.id == explanation.occurrence_id,
                       _contains(m.BankOccurrence.canonical_name, text)),
        exists().where(m.BankTransactionReason.id == explanation.transaction_reason_id,
                       _contains(m.BankTransactionReason.name, text)),
        exists().where(m.PaymentInstrument.id == m.FinancialTransaction.payment_instrument_id,
                       _contains(m.PaymentInstrument.display_name, text)),
    )


def own_account_movement():
    """True for a transaction the model resolves WITHOUT a WHO: a confirmed
    INTERNAL_TRANSFER match. (The STRUCTURAL WHO recognitions this once also
    read belonged to the old rule system, retired by BANK_RULES_RESET_001.)"""
    return exists().where(
        m.FinancialTransactionMatch.match_type == "INTERNAL_TRANSFER",
        or_(m.FinancialTransactionMatch.transaction_a_id == m.FinancialTransaction.id,
            m.FinancialTransactionMatch.transaction_b_id == m.FinancialTransaction.id),
    )


def _who_resolved():
    """The ONE split condition, on the current decision joined in: the WHO
    question is answered (a WHO named, or an own-account movement that has
    none) and no duplicate question is open."""
    return and_(
        or_(m.BankTransactionExplanation.occurrence_id.is_not(None), own_account_movement()),
        or_(m.FinancialTransaction.duplicate_status.is_(None),
            m.FinancialTransaction.duplicate_status != "CANDIDATE_DUPLICATE"),
    )


def _scoped(query, filters: ReviewFilters, *, with_suppressed: bool = False):
    query = query.outerjoin(
        m.BankTransactionExplanation,
        m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id,
    ).where(export_service._not_confirmed_duplicate())
    if not with_suppressed:
        query = query.where(accounting_dedup.not_suppressed_filter())
    if filters.year and filters.month:
        last_day = calendar.monthrange(filters.year, filters.month)[1]
        query = query.where(
            m.FinancialTransaction.posting_date >= date(filters.year, filters.month, 1),
            m.FinancialTransaction.posting_date <= date(filters.year, filters.month, last_day),
        )
    if filters.payment_instrument_id:
        query = query.where(m.FinancialTransaction.payment_instrument_id == filters.payment_instrument_id)
    if filters.batch_id:
        query = query.where(m.FinancialTransaction.import_batch_id == filters.batch_id)
    if filters.search:
        query = query.where(_search_condition(filters.search))
    return query


def counts(session: Session, filters: ReviewFilters) -> dict[str, int]:
    """{To Reconcile: n, Reconciled: m} for the same filters — one query."""
    resolved = case((_who_resolved(), 1), else_=0)
    rows = session.execute(
        _scoped(select(resolved, func.count(m.FinancialTransaction.id))
                .select_from(m.FinancialTransaction), filters)
        .group_by(resolved)
    ).all()
    by_flag = {flag: count for flag, count in rows}
    return {TO_RECONCILE: by_flag.get(0, 0), RECONCILED: by_flag.get(1, 0)}


def reconciled_ids(session: Session, filters: ReviewFilters) -> set[int]:
    """The ids of the transactions on the Reconciled tab for these filters —
    the same split condition as the tabs, ids only. Lets the Monthly
    Accountant Export say which tab a blocking transaction is fixed on."""
    return set(session.scalars(
        _scoped(select(m.FinancialTransaction.id), filters).where(_who_resolved())
    ).all())


# BANK_REVIEW_SORT_001 — the only columns a list may be sorted by, and the
# expression each one sorts on (never a name taken from the request).
SORT_INSTRUMENT, SORT_DATE, SORT_DESCRIPTION, SORT_AMOUNT = "instrument", "date", "description", "amount"
SORTS = (SORT_INSTRUMENT, SORT_DATE, SORT_DESCRIPTION, SORT_AMOUNT)
ASC, DESC = "asc", "desc"


def valid_sort(sort: str | None, direction: str | None) -> tuple[str | None, str | None]:
    """(column, direction) when both are allowed, else (None, None): the
    list's own default order, without an error."""
    if sort in SORTS and direction in (ASC, DESC):
        return sort, direction
    return None, None


def _sorted(query, sort: str, direction: str):
    """The chosen order, applied after the filters and before the row limit:
    missing values always last, then the value (text case-insensitive, the
    signed amount as a number, the posting date as a date), then the
    transaction id as the stable tie-break."""
    if sort == SORT_INSTRUMENT:
        name = (select(m.PaymentInstrument.display_name)
                .where(m.PaymentInstrument.id == m.FinancialTransaction.payment_instrument_id)
                .scalar_subquery())
        value, missing = func.lower(name), or_(name.is_(None), name == "")
    elif sort == SORT_DESCRIPTION:
        text = m.FinancialTransaction.description_original
        value, missing = func.lower(text), or_(text.is_(None), text == "")
    elif sort == SORT_AMOUNT:
        value = m.FinancialTransaction.amount_minor
        missing = value.is_(None)
    else:
        value = m.FinancialTransaction.posting_date
        missing = value.is_(None)
    ordered = value.desc() if direction == DESC else value.asc()
    tie = m.FinancialTransaction.id.desc() if direction == DESC else m.FinancialTransaction.id.asc()
    return query.order_by(None).order_by(case((missing, 1), else_=0), ordered, tie)


def queue(session: Session, view: str, filters: ReviewFilters,
          limit: int = ROW_LIMIT, sort: str | None = None,
          direction: str | None = None) -> list["m.FinancialTransaction"]:
    query = _queue_query(view, filters)
    sort, direction = valid_sort(sort, direction)
    if sort is not None:
        query = _sorted(query, sort, direction)
    return list(session.scalars(query.limit(limit)).all())


def to_reconcile_ids(session: Session, transaction_ids: list[int]) -> set[int]:
    """BANK_REVIEW_BULK_WHO_WHY_001 — which of these transactions are on the
    To Reconcile tab right now (no filter): the same query as the tab."""
    if not transaction_ids:
        return set()
    query = _queue_query(TO_RECONCILE, ReviewFilters()).with_only_columns(m.FinancialTransaction.id).order_by(None)
    return set(session.scalars(query.where(m.FinancialTransaction.id.in_(list(transaction_ids)))).all())


def search_summary(session: Session, view: str, filters: ReviewFilters) -> dict:
    """BANK_REVIEW_SEARCH_001 — every transaction of ONE queue for these
    filters (search included), not only the rows shown: how many, and the
    algebraic total of their amounts PER CURRENCY (the Source's currency;
    currencies are never added together). Each transaction counted once."""
    ids = _queue_query(view, filters).with_only_columns(m.FinancialTransaction.id).order_by(None).subquery()
    rows = session.execute(
        select(m.PaymentInstrument.currency, func.count(m.FinancialTransaction.id),
               func.coalesce(func.sum(m.FinancialTransaction.amount_minor), 0))
        .select_from(m.FinancialTransaction)
        .outerjoin(m.PaymentInstrument, m.PaymentInstrument.id == m.FinancialTransaction.payment_instrument_id)
        .where(m.FinancialTransaction.id.in_(select(ids.c.id)))
        .group_by(m.PaymentInstrument.currency)
        .order_by(m.PaymentInstrument.currency)
    ).all()
    return {"count": sum(count for _currency, count, _total in rows),
            "totals": [{"currency": currency or "", "count": count, "total_minor": int(total)}
                       for currency, count, total in rows]}


def _queue_query(view: str, filters: ReviewFilters):
    """The query of ONE queue — the other queue's rows are never
    loaded. To Reconcile: newest first, as the Review always listed them.
    Reconciled: rows still waiting for an acceptance (no COMPLETE allocation
    yet) before the accepted ones, each newest first; the exact status is
    then read by `reconciliation_status`. Suppressed accounting copies close
    To Reconcile, for audit only."""
    if view == RECONCILED:
        query = _scoped(select(m.FinancialTransaction), filters)
        accepted = exists().where(
            m.BankTransactionAllocation.financial_transaction_id == m.FinancialTransaction.id,
            m.BankTransactionAllocation.status == m.ALLOCATION_COMPLETE,
        )
        query = query.where(_who_resolved()).order_by(
            case((accepted, 1), else_=0),
            m.FinancialTransaction.posting_date.desc(), m.FinancialTransaction.id.desc(),
        )
    else:
        suppressed = m.FinancialTransaction.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
        query = _scoped(select(m.FinancialTransaction), filters, with_suppressed=True).where(
            or_(~_who_resolved(), suppressed)
        ).order_by(
            case((suppressed, 1), else_=0),
            m.FinancialTransaction.posting_date.desc(), m.FinancialTransaction.id.desc(),
        )
    return query
