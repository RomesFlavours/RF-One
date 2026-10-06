"""The two Review queues: To Reconcile and Reconciled (BANK_TWO_STAGE_REVIEW_001).

Both are VIEWS over facts already persisted — no status is stored to decide
where a transaction belongs:

    Reconciled    the WHO question is ANSWERED — which is not the same as a
                  WHO being named. Either:
                  * its CURRENT decision (`FinancialTransaction.explanation_id`
                    -> `BankTransactionExplanation.occurrence_id`) names a
                    WHO — from a recognition rule, a person, a Standard, or an
                    earlier decision; or
                  * it is an own-account movement, for which the model
                    deliberately records NO WHO: its current WHO recognition
                    is STRUCTURAL (the counterparty is RF-One itself — a
                    registered instrument, one of its legal entities, or a
                    card settlement paid from its own funds), or it is one
                    side of a confirmed INTERNAL_TRANSFER match
                    (`FinancialTransactionMatch`, the authority the Monthly
                    Export trusts).
                  WHY, WHAT or For Whom may still be open: the row is
                  finished on the Reconciled tab.
    To Reconcile  everything else in scope: no decision, or a decision naming
                  no WHO (no rule matched, rules contradicted each other, or
                  only a raw recognizer proposal exists) — and any transaction
                  whose duplicate question is still open, because a possible
                  duplicate is not yet a transaction anyone should reconcile.

A raw DETERMINISTIC or PROPOSED WHO recognition (`BankWhoRecognition`) alone
does not resolve the WHO: it is the recognizer's proposal, and the operator
turns it into an authoritative WHO with Select Who or a Rule. A STRUCTURAL
recognition is different in kind: it is not a proposed WHO but the
recognizer's proof, from registered RF-One data, that no external WHO applies
— so no WHO is ever invented for it to leave To Reconcile.

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
from . import who_recognition

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


def own_account_movement():
    """True for a transaction the model resolves WITHOUT a WHO: a STRUCTURAL
    current WHO recognition, or a confirmed INTERNAL_TRANSFER match."""
    structural = exists().where(
        m.BankWhoRecognition.financial_transaction_id == m.FinancialTransaction.id,
        m.BankWhoRecognition.recognizer_version == who_recognition.RECOGNIZER_VERSION,
        m.BankWhoRecognition.tier == m.WHO_TIER_STRUCTURAL,
    )
    matched = exists().where(
        m.FinancialTransactionMatch.match_type == "INTERNAL_TRANSFER",
        or_(m.FinancialTransactionMatch.transaction_a_id == m.FinancialTransaction.id,
            m.FinancialTransactionMatch.transaction_b_id == m.FinancialTransaction.id),
    )
    return or_(structural, matched)


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


def queue(session: Session, view: str, filters: ReviewFilters,
          limit: int = ROW_LIMIT) -> list["m.FinancialTransaction"]:
    """The transactions of ONE queue — the other queue's rows are never
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
    return list(session.scalars(query.limit(limit)).all())
