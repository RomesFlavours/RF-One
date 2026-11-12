"""What stands between a month and its Monthly Accountant Export
(BANK_EXPORT_ACTIONABLE_BLOCKERS_001).

The export's gate is unchanged: `export.compute_export_blockers` decides
WHETHER the month may be exported, and an empty list means it may. This
module only reads that same list and the month's authoritative states and
arranges them for a person to act on:

    status        the month's counts — To Reconcile (the Review tab),
                  Reconciled but Needs review, Confirmed — from
                  `review_queues` and `reconciliation_status`, never a
                  second status model;
    groups        the blockers grouped by what fixes them, each with a
                  count of distinct subjects (a transaction is counted
                  once, in the first group that applies):

        SOURCE          a file with no Source, a file that did not parse,
                        a card with no settlement account, an account with
                        no Company / Legal Entity;
        TO_RECONCILE    transactions on the To Reconcile tab (WHO not
                        resolved, or a duplicate question open);
        RECONCILED      transactions on the Reconciled tab still Needs
                        review;
        OTHER           any other real blocker — an incomplete WHO / WHY /
                        WHAT on an already-accepted row.

Per-transaction detail is built only for a group a person asked to see, so
a month with hundreds of open rows renders counts, not hundreds of messages.

BANK_EXPORT_BY_OWNER_001 — with an Owning Entity everything above is that
owner's report only, `content` is exactly what its file will contain (rows,
totals per currency), and Sources with no owner are listed separately
(`unattributed`) without blocking it. An owner with no transaction in the
month is never READY: there is nothing to export.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import export as export_service
from . import reconciliation_status
from . import review_queues

SOURCE = "source"
TO_RECONCILE = "to_reconcile"
RECONCILED = "reconciled"
OTHER = "other"
GROUPS = (SOURCE, TO_RECONCILE, RECONCILED, OTHER)
DETAIL_LIMIT = 500


@dataclass
class SourceIssue:
    """One Source-side blocker: a batch or an instrument, and what is wrong."""
    kind: str
    label: str
    reason: str
    batch_id: int | None = None
    instrument_id: int | None = None


@dataclass
class TransactionIssue:
    """One blocking transaction, with every reason it blocks."""
    transaction: "m.FinancialTransaction"
    instrument_name: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class Readiness:
    year: int
    month: int
    transaction_count: int
    status: dict[str, int]
    counts: dict[str, int]
    source_issues: list[SourceIssue]
    details: dict[str, list[TransactionIssue]]
    blocker_count: int
    owner: "export_service.Owner | None" = None
    content: "export_service.ExportContent | None" = None
    unattributed: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.transaction_count == 0

    @property
    def ready(self) -> bool:
        return self.blocker_count == 0 and not self.empty


# The short label a person reads in the detail rows; the full reason stays
# in `ExportBlocker.reason`.
_SHORT_REASON = {
    export_service.BLOCKER_NEEDS_REVIEW: "Needs review",
    export_service.BLOCKER_CANDIDATE_DUPLICATE: "Possible duplicate — decide it",
}


def _short(blocker: export_service.ExportBlocker) -> str:
    if blocker.kind in _SHORT_REASON:
        return _SHORT_REASON[blocker.kind]
    # Classification reasons start with their own short title ("Missing Who: …").
    return blocker.reason.split(":", 1)[0]


def readiness(session: Session, *, year: int, month: int, detail: str | None = None,
              owner_key: str | None = None) -> Readiness:
    """The month's export readiness — for one owner when `owner_key` is given.
    `detail` names the one group whose transactions are listed (`GROUPS`);
    the others carry counts only."""
    blockers = export_service.compute_export_blockers(session, year=year, month=month, owner_key=owner_key)
    index = export_service.OwnerIndex(session)
    transactions = (export_service.owner_transactions(session, year, month, owner_key, index)
                    if owner_key is not None else export_service.in_scope_transactions(session, year, month))
    statuses = reconciliation_status.statuses_for(session, transactions)
    reconciled = review_queues.reconciled_ids(
        session, review_queues.ReviewFilters(year=year, month=month),
    )

    # --- Source issues: few by nature, always listed.
    source_issues: list[SourceIssue] = []
    batch_ids = {b.batch_id for b in blockers if b.kind in export_service.SOURCE_BLOCKERS and b.batch_id}
    batches = {
        b.id: b for b in session.scalars(
            select(m.BankImportBatch).where(m.BankImportBatch.id.in_(batch_ids))
        )
    } if batch_ids else {}
    for b in blockers:
        if b.kind not in export_service.SOURCE_BLOCKERS:
            continue
        if b.batch_id is not None:
            batch = batches.get(b.batch_id)
            label = batch.original_file_name if batch is not None else f"batch {b.batch_id}"
        else:
            instrument = session.get(m.PaymentInstrument, b.instrument_id) if b.instrument_id else None
            label = instrument.display_name if instrument is not None else f"Source {b.instrument_id}"
        source_issues.append(SourceIssue(
            kind=b.kind, label=label, reason=b.reason, batch_id=b.batch_id, instrument_id=b.instrument_id,
        ))

    # --- Transactions: each in ONE group, with all of its reasons.
    group_of: dict[int, str] = {}
    reasons_of: dict[int, list[str]] = {}
    order = {TO_RECONCILE: 0, RECONCILED: 1, OTHER: 2}
    for b in blockers:
        if b.transaction_id is None:
            continue
        if b.transaction_id not in reconciled:
            group = TO_RECONCILE
        elif b.kind == export_service.BLOCKER_CLASSIFICATION:
            group = OTHER
        else:
            group = RECONCILED
        current = group_of.get(b.transaction_id)
        if current is None or order[group] < order[current]:
            group_of[b.transaction_id] = group
        short = _short(b)
        if short not in reasons_of.setdefault(b.transaction_id, []):
            reasons_of[b.transaction_id].append(short)

    counts = {SOURCE: len(source_issues), TO_RECONCILE: 0, RECONCILED: 0, OTHER: 0}
    for group in group_of.values():
        counts[group] += 1

    details: dict[str, list[TransactionIssue]] = {}
    if detail in (TO_RECONCILE, RECONCILED, OTHER):
        by_id = {t.id: t for t in transactions}
        instruments = {i.id: i for i in session.scalars(select(m.PaymentInstrument))}
        rows = []
        for transaction_id, group in group_of.items():
            if group != detail or transaction_id not in by_id:
                continue
            t = by_id[transaction_id]
            instrument = instruments.get(t.payment_instrument_id)
            rows.append(TransactionIssue(
                transaction=t,
                instrument_name=instrument.display_name if instrument is not None else "—",
                reasons=reasons_of[transaction_id],
            ))
        rows.sort(key=lambda r: (r.transaction.posting_date, r.transaction.id))
        details[detail] = rows[:DETAIL_LIMIT]

    status_counts = {
        TO_RECONCILE: sum(1 for t in transactions if t.id not in reconciled),
        RECONCILED: counts[RECONCILED],
        reconciliation_status.CONFIRMED: sum(1 for v in statuses.values() if v == reconciliation_status.CONFIRMED),
    }
    return Readiness(
        year=year, month=month, transaction_count=len(transactions), status=status_counts,
        counts=counts, source_issues=source_issues, details=details, blocker_count=len(blockers),
        owner=index.owner(owner_key) if owner_key is not None else None,
        content=export_service.export_content(session, year=year, month=month, owner_key=owner_key),
        unattributed=export_service.unattributed(session, year=year, month=month, index=index),
    )
