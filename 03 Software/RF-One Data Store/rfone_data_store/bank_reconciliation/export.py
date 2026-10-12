"""Monthly Accountant Export — `RfBank_YYYY_MM.xlsx`.

`RfBank.xlsx` is an OUTPUT format this module reproduces; it is never read
or written as a runtime datastore (spec: "Non usare Excel come datastore
runtime"). The 12-column order below is fixed by the accountant's existing
process, not by this schema's own model — `models.py`'s
`FinancialTransaction` may evolve independently of it.

Canonical Financial Model Convergence — Phase 4B (FINANCIAL_MODEL_
CONVERGENCE_001, Product Owner Decisions 1, 6, 8, 12, 13): reads the ONE
canonical reconciliation decision via `FinancialTransaction.explanation_id`
-> the current `BankTransactionExplanation` row, produced by the Bank
Recognition Expert System (`bank_reconciliation/recognition.py`) — there
is no longer a second, independent legacy classification mechanism.
Every Kermali column sourced from the decision (Supplier/Receiving,
Food $, Oper, Deduct, What) is read from that row's immutable snapshot
fields ONLY, never from the live `BankOccurrence`/`BankTransactionReason
ExportMapping` — so a later rename/edit of either never changes a
transaction's already-exported historical values.

BANK_RECONCILIATION_WHO_WHY_WHAT_001: the same rule now also governs the
hierarchical WHO -> WHY -> WHAT classification. The export reads the
decision's `accounting_classification_*_snapshot` values, never the
current `BankOccurrence.default_transaction_reason_id` /
`BankTransactionReason.accounting_classification_id` associations, which
are editable at any time. The blockers below therefore check the CHAIN
for anything not yet decided, and the SNAPSHOT for anything already
decided — an inactive What blocks nothing that already carries a valid
snapshot of it.

Supplier settlement stays a bank-side fact: a supplier paid by invoice
may legitimately classify to an Accounts Payable settlement What
(a Balance Sheet line). This module never infers the Food/Operating
composition of that invoice's lines from the bank movement — that
classification continues to come from the invoice (Invoice Intake/
Purchased), exactly as before."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup
from . import card_configuration
from . import recognition
from . import reconciliation_status

KERMALI_COLUMNS = (
    "Account", "Date", "Description", "Amount", "Supplier/Receiving",
    "Food $", "Oper", "Deduct", "What", "Month", "Year", "Company",
)
# BANK_EXPORT_BY_OWNER_001 — appended after the accountant's 12 columns, which
# keep their order: For Whom (who the movement was for, from its allocation),
# and the Owning Entity of the Source (a Company, or a person with no LLC).
EXPORT_COLUMNS = KERMALI_COLUMNS + ("For Whom", "Owner", "Owner Type")


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _not_confirmed_duplicate():
    """The ONE predicate that keeps a transaction in a month's scope unless a
    human confirmed it as a duplicate.

    Only `duplicate_status == 'CONFIRMED_DUPLICATE'` excludes. A NULL status
    — rows loaded before the duplicate flow set 'NONE' on every import —
    means "never judged a duplicate", not "duplicate". A bare
    `duplicate_status != 'CONFIRMED_DUPLICATE'` is NULL, not TRUE, for those
    rows in SQL, which silently emptied the month; NULL is therefore kept
    explicitly."""
    return or_(
        m.FinancialTransaction.duplicate_status.is_(None),
        m.FinancialTransaction.duplicate_status != "CONFIRMED_DUPLICATE",
    )


def in_scope_transactions(session: Session, year: int, month: int) -> list["m.FinancialTransaction"]:
    """The transactions this month's export is about.

    BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001: a row SUPPRESSED as
    an accounting duplicate is excluded — it is kept in the ledger and
    stays visible on the import/audit screens, but it never reaches the
    accountant, which is the whole point of the deduplication.

    A row whose settlement account is unknown is deliberately KEPT in this
    scope even though it can never be exported: it must still be checked
    for every other reason it is not ready (an undecided candidate
    duplicate, a missing Who), and `compute_export_blockers` adds its own
    reason on top. `build_kermali_workbook` skips it defensively, so it can
    never reach a sheet even if a caller ignored the blockers.

    A row acquired before this mechanism existed has
    `accounting_status = NULL` and is treated as visible, so an
    un-recomputed database exports exactly what it exported before rather
    than emptying."""
    start, end = month_bounds(year, month)
    return list(session.scalars(
        select(m.FinancialTransaction).where(
            m.FinancialTransaction.posting_date >= start,
            m.FinancialTransaction.posting_date <= end,
            _not_confirmed_duplicate(),
            accounting_dedup.not_suppressed_filter(),
        ).order_by(m.FinancialTransaction.posting_date, m.FinancialTransaction.id)
    ).all())



# ---------------------------------------------------------------------------
# Owning Entity of a Source (BANK_EXPORT_BY_OWNER_001)
#
# The report is generated per owner of the Sources: a Company (an LLC, as its
# LEGAL ReportingEntity when it has one) or a person (a PERSONAL
# ReportingEntity in `owner_reporting_entity_id`). Ownership is read exactly
# where it already lives, through the existing derivation: a bank account
# stands for itself; a card belongs to the owner of the account it settles to
# ON THE TRANSACTION'S DATE (`card_configuration.accounting_account_for`).
# Never from the WHO, never from For Whom — a payment from a person's own
# account for MD stays in that person's report, with MD as For Whom.
# ---------------------------------------------------------------------------

OWNER_COMPANY = "Company"
OWNER_PERSON = "Person"


@dataclass(frozen=True)
class Owner:
    key: str            # "re:<ReportingEntity id>" or "le:<LegalEntity id>" — same keys as the Source modal
    name: str
    kind: str           # OWNER_COMPANY | OWNER_PERSON


class OwnerIndex:
    """Owners and the owner of each transaction, for one request. Loads the
    instruments and entities once; a card's settlement account is resolved
    once per (card, date)."""

    def __init__(self, session: Session):
        self.session = session
        self.instruments = {i.id: i for i in session.scalars(select(m.PaymentInstrument))}
        self.entities = {e.id: e for e in session.scalars(select(m.ReportingEntity))}
        self.legals = {le.id: le for le in session.scalars(select(m.LegalEntity))}
        self.entity_by_legal = {e.legal_entity_id: e.id for e in self.entities.values()
                                if e.legal_entity_id is not None}
        self._accounts: dict[tuple, "m.PaymentInstrument | None"] = {}

    def account_key(self, account: "m.PaymentInstrument | None") -> str | None:
        if account is None:
            return None
        if account.owner_reporting_entity_id is not None:
            return f"re:{account.owner_reporting_entity_id}"
        if account.legal_entity_id is not None:
            entity_id = self.entity_by_legal.get(account.legal_entity_id)
            return f"re:{entity_id}" if entity_id else f"le:{account.legal_entity_id}"
        return None

    def account_for(self, instrument_id: int | None, on_date: date | None) -> "m.PaymentInstrument | None":
        instrument = self.instruments.get(instrument_id)
        if instrument is None:
            return None
        if instrument.instrument_type != card_configuration.CREDIT_CARD:
            return instrument
        cache_key = (instrument.id, on_date)
        if cache_key not in self._accounts:
            self._accounts[cache_key] = card_configuration.accounting_account_for(
                self.session, instrument=instrument, on_date=on_date)
        return self._accounts[cache_key]

    def key_for(self, transaction: "m.FinancialTransaction") -> str | None:
        return self.account_key(self.account_for(transaction.payment_instrument_id, transaction.posting_date))

    def owner(self, key: str | None) -> Owner | None:
        kind, _, raw = (key or "").partition(":")
        if not raw.isdigit():
            return None
        if kind == "re":
            entity = self.entities.get(int(raw))
            if entity is None:
                return None
            person = entity.entity_type == m.REPORTING_ENTITY_PERSONAL
            return Owner(key, entity.name, OWNER_PERSON if person else OWNER_COMPANY)
        if kind == "le":
            legal = self.legals.get(int(raw))
            return Owner(key, legal.legal_name, OWNER_COMPANY) if legal is not None else None
        return None

    def owners(self) -> list[Owner]:
        """The owners already present on payment Sources — companies and
        people, each once, by name. A card's owner is its settlement
        account's, so the accounts themselves name every owner."""
        keys = {self.account_key(i) for i in self.instruments.values()
                if i.is_payment_source and i.instrument_type != card_configuration.CREDIT_CARD}
        owners = [self.owner(k) for k in keys if k]
        return sorted((o for o in owners if o), key=lambda o: (o.name.casefold(), o.key))


def owner_choices(session: Session) -> list[Owner]:
    return OwnerIndex(session).owners()


@dataclass
class UnattributedSource:
    """In-scope transactions no owner can be read for: a card with no
    settlement account on that date, or an account with no owner."""
    label: str
    reason: str
    count: int
    instrument_id: int | None = None
    batch_id: int | None = None


def unattributed(session: Session, *, year: int, month: int,
                 index: OwnerIndex | None = None) -> list[UnattributedSource]:
    """Reported on every owner's page, separately: never assigned to anyone,
    never silently dropped, never blocking an owner they may not belong to."""
    index = index or OwnerIndex(session)
    by_instrument: dict[int | None, int] = {}
    for t in in_scope_transactions(session, year, month):
        if index.key_for(t) is None:
            by_instrument[t.payment_instrument_id] = by_instrument.get(t.payment_instrument_id, 0) + 1
    issues = []
    for instrument_id, count in sorted(by_instrument.items(), key=lambda kv: kv[0] or 0):
        instrument = index.instruments.get(instrument_id)
        if instrument is None:
            reason = "no Source"
        elif instrument.instrument_type == card_configuration.CREDIT_CARD:
            account = card_configuration.accounting_account_for(session, instrument=instrument, on_date=None)
            reason = ("its settlement account has no owner" if account is not None
                      else "no settlement account for these dates")
        else:
            reason = "no owner (Company or person)"
        issues.append(UnattributedSource(
            label=instrument.display_name if instrument is not None else "Unknown Source",
            reason=reason, count=count, instrument_id=instrument_id))
    start, end = month_bounds(year, month)
    rows_waiting = exists().where(
        m.RawBankTransaction.import_batch_id == m.BankImportBatch.id,
        m.RawBankTransaction.parse_status != "UNREADABLE",
        m.RawBankTransaction.normalized_transaction_id.is_(None),
    )
    for batch in session.scalars(select(m.BankImportBatch).where(
            m.BankImportBatch.payment_instrument_id.is_(None), rows_waiting)):
        if (batch.date_range_start is None or batch.date_range_end is None
                or (batch.date_range_start <= end and batch.date_range_end >= start)):
            issues.append(UnattributedSource(
                label=batch.original_file_name, reason="file with no Source identified", count=0,
                batch_id=batch.id))
    return issues


def owner_transactions(session: Session, year: int, month: int, owner_key: str,
                       index: OwnerIndex | None = None) -> list["m.FinancialTransaction"]:
    """The month's in-scope transactions of ONE owner — each exactly once."""
    index = index or OwnerIndex(session)
    return [t for t in in_scope_transactions(session, year, month) if index.key_for(t) == owner_key]


def _unresolved_settlement_transactions(
    session: Session, year: int, month: int,
) -> list["m.FinancialTransaction"]:
    """In-month rows that could not be given an accounting identity because
    their instrument has no settlement account configured for that date.
    Reported precisely rather than guessed into some account."""
    start, end = month_bounds(year, month)
    return list(session.scalars(
        select(m.FinancialTransaction).where(
            m.FinancialTransaction.posting_date >= start,
            m.FinancialTransaction.posting_date <= end,
            _not_confirmed_duplicate(),
            m.FinancialTransaction.accounting_status
            == accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT,
        ).order_by(m.FinancialTransaction.posting_date, m.FinancialTransaction.id)
    ).all())


# What a blocker is about (BANK_EXPORT_ACTIONABLE_BLOCKERS_001). The reason
# text is unchanged; the kind and the subject ids only let the Monthly
# Accountant Export page group the reasons and link each group to the page
# that fixes it (`export_readiness`). They never change WHETHER the export is
# blocked.
BLOCKER_UNRESOLVED_SOURCE = "UNRESOLVED_SOURCE"        # a batch with no Source
BLOCKER_PARSING_ERRORS = "PARSING_ERRORS"              # a batch that did not parse cleanly
BLOCKER_NO_SETTLEMENT_ACCOUNT = "NO_SETTLEMENT_ACCOUNT"  # a card with no settlement account
BLOCKER_NO_LEGAL_ENTITY = "NO_LEGAL_ENTITY"            # an account with no Company/Legal Entity
BLOCKER_CANDIDATE_DUPLICATE = "CANDIDATE_DUPLICATE"    # a transaction awaiting a duplicate decision
BLOCKER_NEEDS_REVIEW = "NEEDS_REVIEW"                  # a transaction neither Confirmed nor Automatic
BLOCKER_CLASSIFICATION = "CLASSIFICATION"              # a decided transaction with an incomplete WHO/WHY/WHAT
SOURCE_BLOCKERS = (BLOCKER_UNRESOLVED_SOURCE, BLOCKER_PARSING_ERRORS,
                   BLOCKER_NO_SETTLEMENT_ACCOUNT, BLOCKER_NO_LEGAL_ENTITY)


@dataclass
class ExportBlocker:
    reason: str
    kind: str = BLOCKER_NEEDS_REVIEW
    transaction_id: int | None = None
    batch_id: int | None = None
    instrument_id: int | None = None


def _confirmed_internal_transfer_ids(
    session: Session, transactions: list["m.FinancialTransaction"],
) -> set[int]:
    """Ids among `transactions` that are a CONFIRMED internal transfer
    (Financial Model Convergence Phase 6B, Product Owner Decisions A/B):
    `classification == 'INTERNAL_TRANSFER'` is never trusted alone — a
    genuine, confirmed `FinancialTransactionMatch` of type
    `INTERNAL_TRANSFER` involving the transaction must also exist.
    `bank_reconciliation/matching.py` is the only place that ever creates
    such a match or sets this classification, so this is the ONE
    authoritative check both `compute_export_blockers` and
    `build_kermali_workbook` use — never re-derived independently."""
    candidate_ids = {t.id for t in transactions if t.classification == "INTERNAL_TRANSFER"}
    if not candidate_ids:
        return set()
    matches = session.scalars(
        select(m.FinancialTransactionMatch).where(
            m.FinancialTransactionMatch.match_type == "INTERNAL_TRANSFER",
            or_(
                m.FinancialTransactionMatch.transaction_a_id.in_(candidate_ids),
                m.FinancialTransactionMatch.transaction_b_id.in_(candidate_ids),
            ),
        )
    ).all()
    confirmed: set[int] = set()
    for match in matches:
        if match.transaction_a_id in candidate_ids:
            confirmed.add(match.transaction_a_id)
        if match.transaction_b_id in candidate_ids:
            confirmed.add(match.transaction_b_id)
    return confirmed


def _classification_blockers(
    session: Session, *, transactions: list["m.FinancialTransaction"],
    transfer_ids: set[int], resolved_explanation_ids: set[int],
) -> list[ExportBlocker]:
    """BANK_RECONCILIATION_WHO_WHY_WHAT_001 — every way the hierarchical
    classification can be incomplete for a month, stated as the concrete
    thing a human must go and fix.

    The rule that keeps this honest: an already-decided transaction is
    judged on its OWN SNAPSHOT, never on the live chain. So re-pointing a
    Why at another What, or deactivating a What, never retroactively
    blocks a month that was already correctly classified — only a
    transaction whose snapshot is itself incomplete does. Applying the
    new chain to such a transaction is the explicit `Reclassify` action,
    never an automatic consequence of an edit."""
    blockers: list[ExportBlocker] = []

    explanations_by_id = {}
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    if explanation_ids:
        explanations_by_id = {
            e.id: e for e in session.scalars(
                select(m.BankTransactionExplanation)
                .where(m.BankTransactionExplanation.id.in_(explanation_ids))
            ).all()
        }

    for txn in transactions:
        if txn.id in transfer_ids:
            continue
        if txn.explanation_id is None or txn.explanation_id not in resolved_explanation_ids:
            continue  # no decided WHO -> WHY -> WHAT to judge (reported as Needs review above)
        explanation = explanations_by_id.get(txn.explanation_id)
        if explanation is None:
            continue

        where = (
            f"transaction id={txn.id} ({txn.posting_date.isoformat()}, "
            f"{txn.description_original!r})"
        )

        if explanation.occurrence_id is None and not explanation.occurrence_name_snapshot:
            blockers.append(ExportBlocker(
                f"Missing Who: {where} has a decision that records no Who.",
                kind=BLOCKER_CLASSIFICATION, transaction_id=txn.id,
            ))
            continue
        if explanation.transaction_reason_id is None:
            blockers.append(ExportBlocker(
                f"Who without Why: {where} was decided for Who "
                f"{explanation.occurrence_name_snapshot or explanation.occurrence_id!r} but records no Why. "
                "Give that Who a default Why in Bank > Configuration, then Reclassify this transaction.",
                kind=BLOCKER_CLASSIFICATION, transaction_id=txn.id,
            ))
            continue
        if not explanation.accounting_classification_code_snapshot:
            blockers.append(ExportBlocker(
                f"Why without What: {where} was decided for Why "
                f"{explanation.transaction_reason_name_snapshot or explanation.transaction_reason_id!r} "
                "but its decision records no What (accounting classification). This is an incomplete "
                "historical classification — assign the Why a What in Bank > Configuration, then "
                "Reclassify this transaction.",
                kind=BLOCKER_CLASSIFICATION, transaction_id=txn.id,
            ))
            continue
        if explanation.accounting_statement_type_snapshot is None:
            blockers.append(ExportBlocker(
                f"Incomplete historical classification: {where} carries What "
                f"{explanation.accounting_classification_code_snapshot} with no statement type "
                "(Profit & Loss or Balance Sheet). Complete that What in Bank > Configuration, "
                "then Reclassify this transaction.",
                kind=BLOCKER_CLASSIFICATION, transaction_id=txn.id,
            ))

    return blockers


def _resolution_facts(
    session: Session, transactions: list["m.FinancialTransaction"],
) -> tuple[set[int], set[int]]:
    """The ids of the current decisions among `transactions` that are
    sufficiently resolved, and the ids of the transactions that are a
    confirmed internal transfer.

    Canonical Financial Model Convergence — Phase 4B (Decision 13): a
    transaction is unresolved unless it has a sufficiently resolved
    canonical reconciliation decision — no pointer at all (Recognition
    never ran, e.g. pre-Phase-4B data awaiting migration), or a pointer
    to a decision still awaiting HUMAN review, count equally.

    Phase 6B (Product Owner Decision B): a CONFIRMED internal transfer is
    sufficient economic classification on its own (Decision A) — Kermali is
    an output consumer, never the source of RF-One's own reconciliation
    semantics, so it must not force a fake Occurrence/Reason/Explanation
    onto a transaction that already has a genuine, confirmed
    FinancialTransactionMatch. The exemption requires BOTH conditions
    together (`_confirmed_internal_transfer_ids`)."""
    # BANK_RECONCILIATION_STANDARDS_001 — "sufficiently resolved" is now the
    # persisted reconciliation status: AUTOMATIC (completed by an approved
    # Standard) or CONFIRMED (accepted by a person). A WHO/WHY decision alone,
    # automatic or human, is NEEDS REVIEW and blocks the export.
    statuses = reconciliation_status.statuses_for(session, transactions)
    resolved_explanation_ids = {
        t.explanation_id for t in transactions
        if t.explanation_id is not None and statuses[t.id] in reconciliation_status.EXPORTABLE
    }
    return resolved_explanation_ids, _confirmed_internal_transfer_ids(session, transactions)


def _decided_explanation_ids(
    session: Session, transactions: list["m.FinancialTransaction"],
) -> set[int]:
    """Current decisions in a resolved decision status — the rows whose
    WHO -> WHY -> WHAT snapshot the classification-integrity blockers judge."""
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    if not explanation_ids:
        return set()
    return set(session.scalars(
        select(m.BankTransactionExplanation.id).where(
            m.BankTransactionExplanation.id.in_(explanation_ids),
            m.BankTransactionExplanation.decision_status.in_(recognition.RESOLVED_DECISION_STATUSES),
        )
    ).all())


def unresolved_transactions(
    session: Session, *, year: int, month: int,
) -> list["m.FinancialTransaction"]:
    """The month's transactions that still need a human decision — the ONE
    read-only definition shared by this export's "Missing Who" blocker and
    the Bank Import and Review page.

    In scope as `in_scope_transactions`; unresolved when the current
    decision is missing or not in `RESOLVED_DECISION_STATUSES`, unless the
    transaction is a confirmed internal transfer. Ordered by posting date,
    then id."""
    transactions = in_scope_transactions(session, year, month)
    resolved_explanation_ids, transfer_ids = _resolution_facts(session, transactions)
    return _unresolved_among(transactions, resolved_explanation_ids, transfer_ids)


def _unresolved_among(
    transactions: list["m.FinancialTransaction"], resolved_explanation_ids: set[int],
    transfer_ids: set[int],
) -> list["m.FinancialTransaction"]:
    return [
        t for t in transactions
        if (t.explanation_id is None or t.explanation_id not in resolved_explanation_ids)
        and t.id not in transfer_ids
    ]


def compute_export_blockers(session: Session, *, year: int, month: int,
                            owner_key: str | None = None) -> list[ExportBlocker]:
    """Every reason this export cannot run, precisely stated (spec: "Mostra
    sempre il motivo preciso del blocco"). An empty list means the export
    may proceed.

    BANK_EXPORT_BY_OWNER_001 — with `owner_key`, every check applies to that
    owner's report only: its own transactions, and the files of its own
    Sources. Another owner's problems never block it; Sources with no owner
    are reported separately (`unattributed`), not here. Without an owner the
    whole month is checked, as before. A Source owned by a person is never a
    blocker: a person is a valid owner and needs no LLC."""
    blockers: list[ExportBlocker] = []
    start, end = month_bounds(year, month)
    index = OwnerIndex(session) if owner_key is not None else None

    def batch_in_scope(batch: "m.BankImportBatch") -> bool:
        if index is None:
            return True
        return index.account_key(index.account_for(batch.payment_instrument_id, batch.date_range_start or start)) \
            == owner_key

    # A batch with no Source blocks only while some of its rows still wait
    # for one (BANK_EXPORT_ACTIONABLE_BLOCKERS_001). A file covering several
    # cards has no single Source BY DESIGN — each row is assigned from its own
    # account identifier — so once every readable row is normalized nothing
    # in it is unresolved, and there is nothing a person could fix.
    rows_waiting = exists().where(
        m.RawBankTransaction.import_batch_id == m.BankImportBatch.id,
        m.RawBankTransaction.parse_status != "UNREADABLE",
        m.RawBankTransaction.normalized_transaction_id.is_(None),
    )
    unresolved_batches = session.scalars(
        select(m.BankImportBatch).where(m.BankImportBatch.payment_instrument_id.is_(None), rows_waiting)
    ).all()
    for batch in unresolved_batches:
        if index is not None:
            break  # a file with no Source has no owner: reported as unattributed
        overlaps_month = (
            batch.date_range_start is None or batch.date_range_end is None
            or (batch.date_range_start <= end and batch.date_range_end >= start)
        )
        if overlaps_month:
            blockers.append(ExportBlocker(
                f"Unresolved instrument for batch {batch.original_file_name!r} "
                f"(id={batch.id}) — its Payment Instrument must be resolved before export.",
                kind=BLOCKER_UNRESOLVED_SOURCE, batch_id=batch.id,
            ))

    error_batches = session.scalars(
        select(m.BankImportBatch).where(m.BankImportBatch.error_summary.is_not(None))
    ).all()
    for batch in error_batches:
        if not batch_in_scope(batch):
            continue
        overlaps_month = (
            batch.date_range_start is None or batch.date_range_end is None
            or (batch.date_range_start <= end and batch.date_range_end >= start)
        )
        if overlaps_month:
            blockers.append(ExportBlocker(
                f"Parsing errors in batch {batch.original_file_name!r} (id={batch.id}): {batch.error_summary}",
                kind=BLOCKER_PARSING_ERRORS, batch_id=batch.id,
            ))

    transactions = (in_scope_transactions(session, year, month) if index is None
                    else owner_transactions(session, year, month, owner_key, index))

    undecided_duplicates = [t for t in transactions if t.duplicate_status == "CANDIDATE_DUPLICATE"]
    for txn in undecided_duplicates:
        blockers.append(ExportBlocker(
            f"Undecided candidate duplicate: transaction id={txn.id} "
            f"({txn.posting_date.isoformat()}, {txn.description_original!r}, "
            f"{txn.amount_minor / 100:.2f}) requires a human duplicate decision.",
            kind=BLOCKER_CANDIDATE_DUPLICATE, transaction_id=txn.id,
        ))

    # A transaction blocks export unless it has a sufficiently resolved
    # canonical decision or is a confirmed internal transfer — the one
    # definition `unresolved_transactions` also gives the Bank page. A
    # legacy catalog row no longer existing is not a distinct blocker —
    # that mechanism has been retired (Decision 1/10).
    resolved_explanation_ids, transfer_ids = _resolution_facts(session, transactions)

    unresolved = _unresolved_among(transactions, resolved_explanation_ids, transfer_ids)
    for txn in unresolved:
        blockers.append(ExportBlocker(
            f"Needs review: transaction id={txn.id} "
            f"({txn.posting_date.isoformat()}, {txn.description_original!r}) is neither Confirmed "
            "by a person nor Automatic from an approved Standard (Bank Reconciliation).",
            kind=BLOCKER_NEEDS_REVIEW, transaction_id=txn.id,
        ))

    blockers.extend(_classification_blockers(
        session, transactions=transactions, transfer_ids=transfer_ids,
        # The classification-integrity blockers keep judging every decided
        # row, confirmed or not (BANK_RECONCILIATION_STANDARDS_001 changed
        # only WHEN a row is done, not what makes a classification complete).
        resolved_explanation_ids=_decided_explanation_ids(session, transactions),
    ))

    # BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001: a transaction whose
    # settlement account is unknown has no accounting identity at all — it
    # cannot be deduplicated and cannot be attributed to a Company. It is
    # reported per instrument (not per row) so one unconfigured card does
    # not produce hundreds of identical blockers, and it blocks only the
    # months it actually appears in.
    if index is not None:
        # An owner's transactions all have an owner by construction; Sources
        # without one are the separate unattributed list.
        return blockers
    unresolved = _unresolved_settlement_transactions(session, year, month)
    if unresolved:
        by_instrument: dict[int | None, int] = {}
        for txn in unresolved:
            by_instrument[txn.payment_instrument_id] = by_instrument.get(txn.payment_instrument_id, 0) + 1
        for instrument_id, count in sorted(by_instrument.items(), key=lambda kv: (kv[0] or 0)):
            instrument = session.get(m.PaymentInstrument, instrument_id) if instrument_id else None
            name = instrument.display_name if instrument is not None else str(instrument_id)
            blockers.append(ExportBlocker(
                f"No settlement account configured for {name!r} (id={instrument_id}): {count} "
                "transaction(s) this month have no accounting identity and could not be "
                "deduplicated. Configure the card's settlement account in Bank > Source "
                "(Card settings), then recompute.",
                kind=BLOCKER_NO_SETTLEMENT_ACCOUNT, instrument_id=instrument_id,
            ))

    # The Company of a transaction comes from its SETTLEMENT ACCOUNT, never
    # from the card itself and never from whoever holds the card. A card
    # whose own `legal_entity_id` is set but whose settlement account has
    # none is therefore still blocked — the card's value is not a fallback.
    instruments_in_scope = {t.payment_instrument_id for t in transactions}
    if instruments_in_scope:
        instruments = session.scalars(
            select(m.PaymentInstrument).where(m.PaymentInstrument.id.in_(instruments_in_scope))
        ).all()
        reported: set[int] = set()
        for instrument in instruments:
            posting_dates = [
                t.posting_date for t in transactions
                if t.payment_instrument_id == instrument.id and t.posting_date is not None
            ]
            on_date = min(posting_dates) if posting_dates else None
            account = card_configuration.accounting_account_for(
                session, instrument=instrument, on_date=on_date,
            )
            if account is None:
                continue  # already reported as an unresolved settlement account above
            owned = account.legal_entity_id is not None or account.owner_reporting_entity_id is not None
            if not owned and account.id not in reported:
                reported.add(account.id)
                via = (
                    "" if account.id == instrument.id
                    else f" (settlement account for {instrument.display_name!r})"
                )
                blockers.append(ExportBlocker(
                    f"Missing owner (Company or person) for instrument "
                    f"{account.display_name!r} (id={account.id}){via}.",
                    kind=BLOCKER_NO_LEGAL_ENTITY, instrument_id=account.id,
                ))

    return blockers


@dataclass
class ExportContent:
    """Exactly what the file contains — the rows, their count and their
    totals per currency. The Check page and the download read this same
    object, so the two can never disagree."""
    owner: Owner | None
    rows: list[list] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)     # currency ("" when not set) -> minor units

    @property
    def count(self) -> int:
        return len(self.rows)


def export_content(session: Session, *, year: int, month: int,
                   owner_key: str | None = None) -> ExportContent:
    """The rows of the Monthly Accountant Export (all of the month without an
    owner; one owner's report with one). Reads only persisted facts and the
    decisions' snapshots: nothing is recalculated, no rule is applied."""
    index = OwnerIndex(session)
    owner = index.owner(owner_key) if owner_key is not None else None
    transactions = (owner_transactions(session, year, month, owner_key, index) if owner_key is not None
                    else in_scope_transactions(session, year, month))

    instrument_ids = {t.payment_instrument_id for t in transactions}
    instruments = {
        i.id: i for i in session.scalars(
            select(m.PaymentInstrument).where(m.PaymentInstrument.id.in_(instrument_ids))
        ).all()
    } if instrument_ids else {}

    # BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001: Company comes from
    # the SETTLEMENT ACCOUNT of each transaction — the account a card is
    # paid from — not from the card's own Legal Entity and never from its
    # holder. `accounting_settlement_account_id` was resolved and stored
    # when the row was keyed, so the exported Company matches exactly the
    # account the row was deduplicated under.
    settlement_ids = {
        t.accounting_settlement_account_id for t in transactions
        if t.accounting_settlement_account_id is not None
    }
    settlement_accounts = {
        i.id: i for i in session.scalars(
            select(m.PaymentInstrument).where(m.PaymentInstrument.id.in_(settlement_ids))
        ).all()
    } if settlement_ids else {}

    legal_entities = index.legals
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    explanations = {
        e.id: e for e in session.scalars(
            select(m.BankTransactionExplanation).where(m.BankTransactionExplanation.id.in_(explanation_ids))
        ).all()
    } if explanation_ids else {}
    # Canonical Financial Model Convergence — Phase 6B (Product Owner
    # Decisions A/B/D): a CONFIRMED internal transfer has no Supplier/
    # Receiving, Food $, Oper, Deduct, or What — none is invented to fill
    # the row. RF-One itself retains both transactions and the
    # `FinancialTransactionMatch` internally regardless; Kermali, as an
    # external accountant-classification output, simply never receives a
    # row it has no genuine classification to report.
    transfer_ids = _confirmed_internal_transfer_ids(session, transactions)

    # For Whom — the entity each movement was for, from its allocation(s).
    for_whom: dict[int, list[int]] = {}
    ids = [t.id for t in transactions]
    for start in range(0, len(ids), 500):
        for transaction_id, entity_id in session.execute(
                select(m.BankTransactionAllocation.financial_transaction_id,
                       m.BankTransactionAllocation.reporting_entity_id)
                .where(m.BankTransactionAllocation.financial_transaction_id.in_(ids[start:start + 500]))
                .order_by(m.BankTransactionAllocation.financial_transaction_id,
                          m.BankTransactionAllocation.allocation_index)):
            if entity_id is not None and entity_id not in for_whom.setdefault(transaction_id, []):
                for_whom[transaction_id].append(entity_id)

    content = ExportContent(owner=owner)
    for txn in transactions:
        if txn.id in transfer_ids:
            continue
        # Defensive: the caller is required to refuse to build while any
        # blocker exists, and a row with no settlement account always
        # produces one — so this is unreachable in the normal flow and is
        # here purely so an un-gated caller can never emit a row whose
        # accounting identity nobody established.
        if not accounting_dedup.is_accounting_visible(txn):
            continue
        instrument = instruments.get(txn.payment_instrument_id)
        # The settlement account stored when the row was keyed; when none was
        # stored, the same derivation the owner is read from (a card's
        # settlement account on that date) — never the card's own fields.
        accounting_account = (
            settlement_accounts.get(txn.accounting_settlement_account_id)
            if txn.accounting_settlement_account_id is not None
            else index.account_for(txn.payment_instrument_id, txn.posting_date)
        ) or instrument
        legal_entity = (
            legal_entities.get(accounting_account.legal_entity_id)
            if accounting_account and accounting_account.legal_entity_id else None
        )
        explanation = explanations.get(txn.explanation_id) if txn.explanation_id else None

        amount = Decimal(txn.amount_minor) / 100
        amount_float = float(amount)

        # Canonical Financial Model Convergence — Phase 4B (Decision 8):
        # read ONLY the immutable decision snapshot, never the live
        # BankOccurrence/BankTransactionReasonExportMapping.
        food_value = amount_float if (explanation and explanation.food_cost_snapshot) else None
        oper_value = amount_float if (explanation and explanation.operative_snapshot) else None
        deduct_value = amount_float if (explanation and explanation.deductible_snapshot) else None

        row_owner = owner or index.owner(index.key_for(txn))
        currency = (instrument.currency or "") if instrument else ""
        content.totals[currency] = content.totals.get(currency, 0) + txn.amount_minor
        content.rows.append([
            instrument.display_name if instrument else None,        # Account
            txn.posting_date,                                        # Date — real Excel date, not a string
            txn.description_original,                                # Description
            amount_float,                                            # Amount — numeric, no formula
            explanation.occurrence_name_snapshot if explanation else None,  # Supplier/Receiving
            food_value,                                              # Food $
            oper_value,                                              # Oper
            deduct_value,                                            # Deduct
            _what_cell(explanation),                                 # What
            txn.posting_date.month,                                  # Month — derived from Date
            txn.posting_date.year,                                   # Year — derived from Date
            legal_entity.legal_name if legal_entity else None,        # Company — none for a person, no fictitious LLC
            "; ".join(index.entities[e].name for e in for_whom.get(txn.id, []) if e in index.entities)
            or None,                                                 # For Whom
            row_owner.name if row_owner else None,                   # Owner
            row_owner.kind if row_owner else None,                   # Owner Type
        ])
    return content


def build_kermali_workbook(session: Session, *, year: int, month: int,
                           owner_key: str | None = None) -> bytes:
    """Builds the `.xlsx` bytes from `export_content`. Caller MUST call
    `compute_export_blockers` (with the same owner) first and refuse to call
    this while any blocker exists — this function itself does not re-check
    (single responsibility: building, not gating).

    BANK_EXPORT_BY_OWNER_001 — the `Bank` sheet keeps the accountant's 12
    columns first, then For Whom, Owner and Owner Type; a `Report` sheet
    states owner, year, month, the row count and the totals per currency."""
    content = export_content(session, year=year, month=month, owner_key=owner_key)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bank"
    ws.append(list(EXPORT_COLUMNS))
    for row in content.rows:
        ws.append(row)

    info = wb.create_sheet("Report")
    info.append(["Monthly Accountant Export"])
    info.append(["Owner", content.owner.name if content.owner else "All owners"])
    info.append(["Owner Type", content.owner.kind if content.owner else ""])
    info.append(["Year", year])
    info.append(["Month", month])
    info.append(["Transactions", content.count])
    for currency, total in sorted(content.totals.items()):
        info.append([f"Total {currency or '(currency not set)'}", float(Decimal(total) / 100)])

    date_col = 2  # "Date"
    for row in ws.iter_rows(min_row=2, min_col=date_col, max_col=date_col):
        for cell in row:
            cell.number_format = "MM/DD/YYYY"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _what_cell(explanation: "m.BankTransactionExplanation | None") -> str | None:
    """The Kermali `What` column. A decision taken under the hierarchical
    WHO -> WHY -> WHAT model reports its accounting classification; a
    decision that predates it keeps reporting exactly the Kermali
    `what_label` it was exported with before, so no historical row's
    output changes. Both are read from the decision's own snapshot."""
    if explanation is None:
        return None
    return explanation.accounting_classification_name_snapshot or explanation.what_label_snapshot


def export_file_name(*, year: int, month: int, owner: Owner | None = None) -> str:
    """`RfBank_YYYY_MM.xlsx`, or `RfBank_YYYY_MM_<Owner>.xlsx` for one owner's
    report (letters, digits and dashes only)."""
    if owner is None:
        return f"RfBank_{year:04d}_{month:02d}.xlsx"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", owner.name).strip("-") or "Owner"
    return f"RfBank_{year:04d}_{month:02d}_{slug}.xlsx"
