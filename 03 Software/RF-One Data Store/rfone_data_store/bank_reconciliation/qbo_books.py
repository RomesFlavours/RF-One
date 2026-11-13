"""QuickBooks Online: what each reconciled bank movement becomes, checked, previewed and exported to a file, PER
COMPANY (BANK_UPLOAD_AND_RECONCILE_001, 2026-11-03). Builds on `qbo_export` (Purchase, maps, duplicate table).

Each company (LEGAL ReportingEntity) is its own QBO company: its own chart of accounts (`bank_qbo_accounts`), its
own correspondences (`bank_qbo_account_maps`), its own export files (`bank_qbo_export_batches`). Nothing is assumed
shared: a correspondence can be COPIED from another company only as a PROPOSAL, which a person verifies in the
destination company's chart; an account of another company's chart is refused; a correspondence made before this
was per company (GLOBAL_LEGACY) is never attributed to a company, only offered as a proposal. A movement whose
company cannot be determined is blocked with the reason (`owner_reason`).

ONE movement -> ONE QBO transaction, with its lines (the movement's allocations = the split):

| Movement                                              | QBO API entity (preview)               | Journal entry (file)                  |
|-------------------------------------------------------|----------------------------------------|---------------------------------------|
| money out, bank account or card                       | Purchase (one line per allocation)     | Cr bank/card; Dr each WHAT account    |
| money in on a card (refund)                            | Purchase with Credit = true            | Dr card; Cr each WHAT account         |
| money in on a bank account                             | Deposit (DepositLineDetail lines)      | Dr bank; Cr each WHAT account         |
| own-account transfer / card payment, matched pair      | Transfer, ONCE for the two legs        | Dr receiving; Cr paying — ONE entry   |

A matched pair whose legs belong to different companies, or whose relationship is still to decide, is blocked; a
movement of a Source owned by a person is not in a company's books (excluded, not blocked). Amounts are integer
cents; the lines must equal the movement exactly; the sign follows the movement. One movement has exactly ONE line
on its bank / card account, so one payment with several categories stays ONE register entry.

Stages and states, kept distinct (the file is not the import, the import is not the API):
  PREVIEW          — `plan`: the entity, the lines, the checks. Writes nothing.
  FILE GENERATED   — `generate_batch`: the QBO "Import journal entries" CSV of the ready movements of ONE company
                     (`BankQboExportBatch`, GENERATED); each movement recorded FILE_EXPORTED in that batch, so it is
                     never put in another file.
  FILE DOWNLOADED  — `download`: the SAME kept content; counts the download, creates nothing. Proves nothing about
                     QBO.
  IMPORT CONFIRMED — `confirm_import`: a person states the file was imported in that QBO company. Only then are
                     the movements "imported". `withdraw` (only before that) states it was NOT imported: the
                     movements become exportable again, the file stays in the history as withdrawn.
  API ACCEPTED     — not implemented: Bank has no QBO connection (`SEND_PREREQUISITES`). The API payloads of the
                     preview are what a sender would post, with the stable `requestid` of `qbo_export.request_id`.
A movement changed after it went into a file (lines, accounts, company) is reported CHANGED_AFTER_EXPORT and is
never put in a new file silently.

The file format, checked against Intuit's official help (2026-11-03; references in BANK_UPLOAD_AND_RECONCILE_001):
a journal entry is NOT the same as a Purchase / Deposit / Transfer. It keeps the amounts, the accounts and the one
register line per payment, but in QBO it is a "Journal Entry": no payee (Name is only for A/R and A/P lines), not
in vendor / expense reports, and — the decisive point — Intuit's list of records a downloaded bank-feed transaction
can be matched to (checks, receipts, bills, transfers, credit card payments and refunds...) does not include
journal entries. So a file is generated only after the person states that the company's accounts in it are NOT
also taken from the bank feed in QBO (or that those feed items will be excluded, not added); otherwise the same
movement would be in the books twice. Where bank feeds are used, the matching-compatible path is the API
(Purchase / Deposit / Transfer), which needs the QBO connection of SEND_PREREQUISITES.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import inspect, select, text

from .. import models as m
from . import card_configuration, qbo_export

PURCHASE, DEPOSIT, TRANSFER = "Purchase", "Deposit", "Transfer"
LIST_FILE, API = "ACCOUNT_LIST_FILE", "QBO_API"
FILE_EXPORTED = "FILE_EXPORTED"
VERIFIED, PROPOSED, GLOBAL_LEGACY = "VERIFIED", "PROPOSED", "GLOBAL_LEGACY"
GENERATED, IMPORT_CONFIRMED, WITHDRAWN = "GENERATED", "IMPORT_CONFIRMED", "WITHDRAWN"
JOURNAL_CSV = "QBO_JOURNAL_ENTRIES_CSV"
# Blockers (in addition to qbo_export's).
NOT_CONFIRMED = "NOT_CONFIRMED"
INTER_COMPANY = "INTER_COMPANY"
RELATIONSHIP_OPEN = "RELATIONSHIP_OPEN"
NO_OWNER = "NO_OWNER"
NOT_VERIFIED = "NOT_VERIFIED"
MAP_PROPOSED = "MAP_PROPOSED"
OTHER_COMPANY = "OTHER_COMPANY"
LABELS = {
    **qbo_export.LABELS,
    qbo_export.CATEGORY_NOT_MAPPED: "QBO account of a WHAT not set for this company",
    qbo_export.PAYMENT_ACCOUNT_NOT_MAPPED: "QBO account of the Source not set for this company",
    qbo_export.ALREADY_EXPORTED: "Already in an export file",
    qbo_export.CHANGED_AFTER_EXPORT: "Changed after it went into an export file",
    qbo_export.UNBALANCED: "Lines do not add up to the movement",
    qbo_export.SPLIT_INCOMPLETE: "Split incomplete",
    qbo_export.NO_SPLIT: "No confirmed lines",
    NOT_CONFIRMED: "Not reconciled yet",
    INTER_COMPANY: "Transfer between two companies: not one QBO transaction",
    RELATIONSHIP_OPEN: "Relationship between the owners still to decide",
    NO_OWNER: "Company of the movement not determinable",
    NOT_VERIFIED: "QBO account not found in this company's imported chart",
    MAP_PROPOSED: "Correspondence proposed, to verify in this company's chart",
    OTHER_COMPANY: "QBO account of another company",
}
TYPE_FOR_SOURCE = {"BANK_ACCOUNT": ("Bank",), "CREDIT_CARD": ("Credit Card",), "PAYPAL": ("Bank",)}
STATE_LABELS = {GENERATED: "in a generated file, import not confirmed", IMPORT_CONFIRMED: "imported in QBO (confirmed by a person)",
                WITHDRAWN: "withdrawn: not imported", "SENT": "accepted by the QBO API", "PREPARED": "prepared for the QBO API", FILE_EXPORTED: "in an export file"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _money(minor: int) -> str:
    return f"{abs(minor) / 100:.2f}"


# ---------------------------------------------------------------- companies, charts and correspondences

def companies(db) -> list["m.ReportingEntity"]:
    """The companies that can have QBO books: LEGAL reporting entities. A person's books are not in QBO."""
    return list(db.scalars(select(m.ReportingEntity).where(m.ReportingEntity.entity_type == "LEGAL")
                           .order_by(m.ReportingEntity.name)))


def _company(db, entity_id) -> "m.ReportingEntity":
    entity = db.get(m.ReportingEntity, entity_id) if entity_id else None
    if entity is None or entity.entity_type != "LEGAL":
        raise ValueError("Choose a company: each company has its own QuickBooks chart and correspondences.")
    return entity


def import_account_list(db, content: bytes, *, entity_id: int, account_id: int | None) -> dict:
    """Read QBO's Account List export (CSV; title lines before the header are skipped) into the chart of ONE
    company: each account's full name and type. No Id is read (the export has none). The file is a full list: an
    account of the company's chart no longer in it is deactivated (its correspondences stop being verified). The
    title lines are returned so the person sees which QBO company the file came from."""
    entity = _company(db, entity_id)
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    header_at = next((i for i, r in enumerate(rows)
                      if {c.strip().lower() for c in r} & {"account", "full name", "account name", "name"}
                      and any(c.strip().lower() == "type" for c in r)), None)
    if header_at is None:
        raise ValueError("This is not a QuickBooks Online Account List: it needs the columns Account (or Full name) "
                         "and Type.")
    title = " · ".join(c.strip() for r in rows[:header_at] for c in r if c.strip())[:200]
    head = [c.strip().lower() for c in rows[header_at]]
    name_col = next(head.index(c) for c in ("full name", "account", "account name", "name") if c in head)
    type_col = head.index("type")
    detail_col = head.index("detail type") if "detail type" in head else None
    existing = {a.name: a for a in db.scalars(select(m.BankQboAccount).where(
        m.BankQboAccount.reporting_entity_id == entity.id))}
    added = updated = 0
    seen = set()
    for r in rows[header_at + 1:]:
        if len(r) <= max(name_col, type_col) or not r[name_col].strip() or not r[type_col].strip():
            continue
        name = r[name_col].strip()
        seen.add(name)
        row = existing.get(name)
        if row is None:
            row = existing[name] = m.BankQboAccount(name=name, source=LIST_FILE, reporting_entity_id=entity.id)
            db.add(row)
            added += 1
        elif row.source == API:
            row.active = True
            continue            # an account read from QBO itself keeps its Id and type
        else:
            updated += 1
        row.account_type = r[type_col].strip()
        row.detail_type = r[detail_col].strip() if detail_col is not None and len(r) > detail_col else None
        row.active, row.imported_by_account_id = True, account_id
    if not added and not updated:
        raise ValueError("No account was read from the file.")
    gone = 0
    for name, row in existing.items():
        if name not in seen and row.active and row.source == LIST_FILE:
            row.active, gone = False, gone + 1
    db.flush()
    return dict(added=added, updated=updated, deactivated=gone, title=title, company=entity.name)


def chart(db, entity_id) -> dict[str, "m.BankQboAccount"]:
    """The active chart of ONE company, by account name."""
    if not entity_id:
        return {}
    return {a.name: a for a in db.scalars(select(m.BankQboAccount).where(
        m.BankQboAccount.reporting_entity_id == entity_id, m.BankQboAccount.active.is_(True))
        .order_by(m.BankQboAccount.name))}


def _check_type(db, kind, local_id, account) -> None:
    if kind == qbo_export.PAYMENT_ACCOUNT:
        source = db.get(m.PaymentInstrument, local_id)
        allowed = TYPE_FOR_SOURCE.get(source.instrument_type if source else None, ())
        if allowed and account.account_type not in allowed:
            raise ValueError(f"{source.display_name} is a {source.instrument_type.replace('_', ' ').lower()}: its QBO "
                             f"account must be of type {' or '.join(allowed)}, not {account.account_type}.")


def set_map(db, entity_id: int, kind: str, local_id: int, name: str, *, account_id: int | None) -> "m.BankQboAccountMap":
    """A person's reusable correspondence for ONE company, verified against THAT company's chart (name and type).
    An account of another company's chart is refused."""
    entity = _company(db, entity_id)
    if kind not in (qbo_export.CATEGORY, qbo_export.PAYMENT_ACCOUNT):
        raise ValueError("Unknown kind of correspondence.")
    name = (name or "").strip()
    account = chart(db, entity.id).get(name)
    if account is None:
        elsewhere = db.scalar(select(m.BankQboAccount).where(m.BankQboAccount.name == name,
                                                             m.BankQboAccount.reporting_entity_id != entity.id).limit(1))
        if elsewhere is not None:
            raise ValueError(f"“{name}” is an account of another company's chart, not of {entity.name}'s: choose an "
                             f"account of {entity.name}'s chart.")
        raise ValueError(f"Choose an account of {entity.name}'s QuickBooks chart (import its Account List first).")
    _check_type(db, kind, local_id, account)
    row = db.scalar(select(m.BankQboAccountMap).where(m.BankQboAccountMap.reporting_entity_id == entity.id,
                                                      m.BankQboAccountMap.kind == kind,
                                                      m.BankQboAccountMap.local_id == local_id))
    if row is None:
        row = m.BankQboAccountMap(kind=kind, local_id=local_id, reporting_entity_id=entity.id)
        db.add(row)
    row.qbo_account_name, row.qbo_account_type = account.name, account.account_type
    row.qbo_account_id = account.qbo_account_id             # None unless read from QBO
    row.qbo_account_row_id, row.status = account.id, VERIFIED
    row.verified_by, row.updated_by_account_id = account.source, account_id
    db.flush()
    return row


def copy_as_proposals(db, from_entity_id: int, to_entity_id: int, *, account_id: int | None) -> int:
    """Copy one company's verified WHAT correspondences to another company as PROPOSALS, used for nothing until a
    person verifies each in the destination company's chart. Source correspondences are not copied: a Source's
    bank or card account is in the books of its own company. Existing rows are never overwritten."""
    src, dst = _company(db, from_entity_id), _company(db, to_entity_id)
    if src.id == dst.id:
        raise ValueError("Choose two different companies.")
    have = {(r.kind, r.local_id) for r in db.scalars(select(m.BankQboAccountMap).where(
        m.BankQboAccountMap.reporting_entity_id == dst.id))}
    n = 0
    for r in db.scalars(select(m.BankQboAccountMap).where(m.BankQboAccountMap.reporting_entity_id == src.id,
                                                          m.BankQboAccountMap.status == VERIFIED,
                                                          m.BankQboAccountMap.kind == qbo_export.CATEGORY)):
        if (r.kind, r.local_id) in have:
            continue
        db.add(m.BankQboAccountMap(kind=r.kind, local_id=r.local_id, reporting_entity_id=dst.id, status=PROPOSED,
                                   qbo_account_name=r.qbo_account_name, qbo_account_type=r.qbo_account_type,
                                   proposed_from=src.name, updated_by_account_id=account_id))
        n += 1
    db.flush()
    return n


def verify_proposal(db, map_id: int, *, account_id: int | None) -> "m.BankQboAccountMap":
    """A person confirms a proposal: verified in the destination company's chart, or refused with the reason."""
    row = db.get(m.BankQboAccountMap, map_id)
    if row is None or row.status != PROPOSED:
        raise ValueError("This proposal no longer exists.")
    if row.qbo_account_name not in chart(db, row.reporting_entity_id):
        raise ValueError(f"“{row.qbo_account_name}” is not in this company's imported chart: choose its account.")
    return set_map(db, row.reporting_entity_id, row.kind, row.local_id, row.qbo_account_name, account_id=account_id)


def maps(db) -> dict:
    """(company id, kind, local id) -> correspondence. GLOBAL_LEGACY rows have company None."""
    return {(r.reporting_entity_id, r.kind, r.local_id): r for r in db.scalars(select(m.BankQboAccountMap))}


def _hints(cmaps) -> dict:
    """(kind, local id) -> what other companies or the old global setting have: offered as a proposal only."""
    out = defaultdict(list)
    for (entity_id, kind, local_id), r in cmaps.items():
        if r.status in (VERIFIED, GLOBAL_LEGACY) and r.qbo_account_name:
            out[(kind, local_id)].append(dict(name=r.qbo_account_name, entity_id=entity_id,
                                              origin="previous correspondence for no company" if r.status == GLOBAL_LEGACY
                                              else "verified for another company"))
    return out


def owner_reason(db, source, day) -> str:
    """Why the company of a movement cannot be determined (the movement is blocked with this reason)."""
    if source is None:
        return "the Source of the movement is unknown"
    if source.instrument_type == "CREDIT_CARD":
        account = card_configuration.accounting_account_for(db, instrument=source, on_date=day)
        if account is None:
            return f"{source.display_name}: no settlement account configured for {day}"
        source = account
    if source.owner_reporting_entity_id is None and source.legal_entity_id is None:
        return f"{source.display_name}: no owner configured"
    return f"{source.display_name}: its owner has no company (reporting entity) configured"


# ---------------------------------------------------------------- what each movement becomes

def _matches(db, ids) -> dict[int, SimpleNamespace]:
    """The matched pairs touching `ids`. Read with SQL: `relationship` (SAME_OWNER / TO_DECIDE) is a column the
    single engine's migration added and the ORM model does not map."""
    out = {}
    if not ids:
        return out
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("financial_transaction_matches")}
    rel = "relationship" if "relationship" in columns else "NULL"
    marks = ",".join(str(int(i)) for i in ids)
    for row in db.execute(text(
            f"select transaction_a_id, transaction_b_id, match_type, {rel} from financial_transaction_matches "
            f"where transaction_a_id in ({marks}) or transaction_b_id in ({marks})")):
        x = SimpleNamespace(transaction_a_id=row[0], transaction_b_id=row[1], match_type=row[2], relationship=row[3])
        out[x.transaction_a_id] = x
        out[x.transaction_b_id] = x
    return out


def _owner_spans(db, sources) -> dict[int, list]:
    """Per Source, the date spans in which its owner cannot change: a card's settlement assignments
    (`card_configuration.settlement_account_on`), one span for any other Source. A day outside every span is
    looked up on its own."""
    spans = {sid: [(None, None)] for sid, s in sources.items() if s.instrument_type != "CREDIT_CARD"}
    for a in db.scalars(select(m.BankCardSettlementAccount).order_by(m.BankCardSettlementAccount.valid_from)):
        spans.setdefault(a.credit_card_payment_instrument_id, []).append((a.valid_from, a.valid_to))
    return spans


def _exports(db) -> dict[int, "m.BankQboExport"]:
    out = {}
    for r in db.scalars(select(m.BankQboExport)):
        out[r.financial_transaction_id] = r
        if r.counterpart_transaction_id:
            out[r.counterpart_transaction_id] = r
    return out


def plan(db, txn_ids, *, confirmed: set[int] | None = None) -> dict:
    """Every movement of `txn_ids` as it would go to QBO: entity, company, lines, checks. Writes nothing.
    `confirmed` = the movements whose reconciliation is complete (decided); matched pairs need no decision."""
    from . import reconciliation_status
    ids = sorted(set(txn_ids))
    txns = {t.id: t for t in db.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.id.in_(ids)))}
    sources = {s.id: s for s in db.scalars(select(m.PaymentInstrument))}
    matches = _matches(db, ids)
    done = _exports(db)
    cmaps = maps(db)
    hints = _hints(cmaps)
    charts: dict = {}
    batches = {b.id: b for b in db.scalars(select(m.BankQboExportBatch))}
    allocations = defaultdict(list)
    for a in db.scalars(select(m.BankTransactionAllocation).where(
            m.BankTransactionAllocation.financial_transaction_id.in_(ids)).order_by(m.BankTransactionAllocation.allocation_index)):
        allocations[a.financial_transaction_id].append(a)
    if confirmed is None:
        statuses = reconciliation_status.statuses_for(db, list(txns.values()))
        confirmed = {i for i, s in statuses.items() if s in reconciliation_status.EXPORTABLE}
    items, seen, excluded = [], set(), Counter()
    need = defaultdict(lambda: dict(sources=Counter(), whats=Counter()))

    owners: dict = {}
    spans = _owner_spans(db, sources)

    def owner_of(t):
        # The Source owner at the movement date. Ownership changes rarely: it is computed once per Source and
        # per configuration span (settlement assignments), not once per movement.
        day = t.posting_date or t.transaction_date
        span = next((i for i, (a, b) in enumerate(spans.get(t.payment_instrument_id, [])) if (a is None or a <= day)
                     and (b is None or day < b)), None) if day else None
        key = (t.payment_instrument_id, span if span is not None else day)
        if key not in owners:
            source = sources.get(t.payment_instrument_id)
            owners[key] = card_configuration.owner_entity_for(db, instrument=source, on_date=day) if source else None
        return owners[key]

    wanted: list = []   # correspondences missing for the current movement: (company, group, (local id, label))

    def account(kind, local_id, blockers, label, entity):
        # The correspondence of THIS company only; another company's account is never used.
        if entity is None:
            return None                       # NO_OWNER already blocks: which chart is unknown
        names = charts.setdefault(entity.id, chart(db, entity.id))
        row = cmaps.get((entity.id, kind, local_id))
        group = "whats" if kind == qbo_export.CATEGORY else "sources"
        if row is None or not row.qbo_account_name or row.status != VERIFIED:
            blockers.append(dict(code=MAP_PROPOSED if row is not None and row.status == PROPOSED
                                 else qbo_export.CATEGORY_NOT_MAPPED if kind == qbo_export.CATEGORY
                                 else qbo_export.PAYMENT_ACCOUNT_NOT_MAPPED, detail=label))
            wanted.append((entity.id, group, (local_id, label)))
            return None
        held = names.get(row.qbo_account_name)
        if held is None:
            blockers.append(dict(code=NOT_VERIFIED, detail=row.qbo_account_name))
            wanted.append((entity.id, group, (local_id, label)))
        elif row.qbo_account_row_id is not None and row.qbo_account_row_id != held.id:
            blockers.append(dict(code=OTHER_COMPANY, detail=row.qbo_account_name))
        return row

    for tid in ids:
        if tid in seen or tid not in txns:
            continue
        t = txns[tid]
        owner = owner_of(t)
        if owner is not None and owner.entity_type != "LEGAL":
            excluded["Source owned by a person: not in a company's books"] += 1
            continue
        blockers, lines, counterpart = [], [], None
        wanted.clear()
        source = sources.get(t.payment_instrument_id)
        no_owner = None if owner else owner_reason(db, source, t.posting_date or t.transaction_date)
        match = matches.get(tid)
        if match is not None and match.match_type in ("TRANSFER", "INTERNAL_TRANSFER", "CARD_SETTLEMENT"):
            other_id = match.transaction_b_id if match.transaction_a_id == tid else match.transaction_a_id
            other = txns.get(other_id) or db.get(m.FinancialTransaction, other_id)
            out_leg, in_leg = (t, other) if t.amount_minor < 0 else (other, t)
            counterpart = other.id if other else None
            seen.update({tid, other_id})
            entity = TRANSFER
            if other is None:
                blockers.append(dict(code=NOT_CONFIRMED, detail="the other leg is not in Bank"))
            elif match.relationship == "TO_DECIDE":
                blockers.append(dict(code=RELATIONSHIP_OPEN, detail=""))
            else:
                other_owner = owner_of(other)
                if owner is None or other_owner is None:
                    blockers.append(dict(code=NO_OWNER, detail=no_owner or owner_reason(
                        db, sources.get(other.payment_instrument_id), other.posting_date or other.transaction_date)))
                elif other_owner.id != owner.id:
                    blockers.append(dict(code=INTER_COMPANY, detail=f"{owner.name} / {other_owner.name}"))
            frm = account(qbo_export.PAYMENT_ACCOUNT, out_leg.payment_instrument_id, blockers,
                          sources[out_leg.payment_instrument_id].display_name, owner) if out_leg else None
            to = account(qbo_export.PAYMENT_ACCOUNT, in_leg.payment_instrument_id, blockers,
                         sources[in_leg.payment_instrument_id].display_name, owner) if in_leg else None
            amount = abs(out_leg.amount_minor) if out_leg else abs(t.amount_minor)
            if out_leg and in_leg and abs(in_leg.amount_minor) != amount:
                blockers.append(dict(code=qbo_export.UNBALANCED, detail="the two legs differ"))
            lines = [dict(account=to.qbo_account_name if to else None, debit=amount, credit=0),
                     dict(account=frm.qbo_account_name if frm else None, debit=0, credit=amount)]
            day = (out_leg or t).posting_date or (out_leg or t).transaction_date
            payload = dict(TxnDate=str(day), Amount=_money(amount),
                           FromAccountRef=dict(value=frm.qbo_account_id if frm else None, name=frm.qbo_account_name if frm else None),
                           ToAccountRef=dict(value=to.qbo_account_id if to else None, name=to.qbo_account_name if to else None),
                           PrivateNote=f"RF-One Bank movements #{out_leg.id if out_leg else tid} and #{in_leg.id if in_leg else '—'}")
            key_id = out_leg.id if out_leg else tid
        else:
            seen.add(tid)
            card = bool(source and source.instrument_type == "CREDIT_CARD")
            entity = DEPOSIT if t.amount_minor > 0 and not card else PURCHASE
            if owner is None:
                blockers.append(dict(code=NO_OWNER, detail=no_owner))
            allocs = allocations.get(tid, [])
            if tid not in confirmed:
                blockers.append(dict(code=NOT_CONFIRMED, detail=""))
            elif not allocs:
                blockers.append(dict(code=qbo_export.NO_SPLIT, detail=""))
            elif any(a.status != m.ALLOCATION_COMPLETE for a in allocs):
                blockers.append(dict(code=qbo_export.SPLIT_INCOMPLETE, detail=""))
            if allocs and sum(a.amount_minor for a in allocs) != t.amount_minor:
                blockers.append(dict(code=qbo_export.UNBALANCED, detail=f"{sum(a.amount_minor for a in allocs) / 100:.2f} "
                                     f"vs {t.amount_minor / 100:.2f}"))
            pay = account(qbo_export.PAYMENT_ACCOUNT, t.payment_instrument_id, blockers,
                          source.display_name if source else f"Source #{t.payment_instrument_id}", owner)
            # The payment account: credited when money goes out, debited when it comes in.
            lines.append(dict(account=pay.qbo_account_name if pay else None,
                              debit=t.amount_minor if t.amount_minor > 0 else 0,
                              credit=-t.amount_minor if t.amount_minor < 0 else 0))
            api_lines = []
            for a in allocs:
                label = " ".join(x for x in (a.accounting_classification_code_snapshot,
                                             a.accounting_classification_name_snapshot) if x) or "—"
                row = account(qbo_export.CATEGORY, a.accounting_classification_id, blockers, label, owner) \
                    if a.accounting_classification_id else None
                if a.accounting_classification_id is None:
                    blockers.append(dict(code=qbo_export.CATEGORY_NOT_MAPPED, detail="line without WHAT"))
                # Each line mirrors the movement: an expense line (negative) is a debit, a positive one a credit.
                lines.append(dict(account=row.qbo_account_name if row else None,
                                  debit=-a.amount_minor if a.amount_minor < 0 else 0,
                                  credit=a.amount_minor if a.amount_minor > 0 else 0,
                                  description=a.description or a.transaction_reason_name_snapshot or ""))
                ref = dict(value=row.qbo_account_id if row else None, name=row.qbo_account_name if row else None)
                api_lines.append(dict(Amount=_money(a.amount_minor), Description=(a.description or
                                      a.transaction_reason_name_snapshot or "")[:4000],
                                      **({"DetailType": "DepositLineDetail", "DepositLineDetail": {"AccountRef": ref}}
                                         if entity == DEPOSIT else
                                         {"DetailType": "AccountBasedExpenseLineDetail",
                                          "AccountBasedExpenseLineDetail": {"AccountRef": ref}})))
            day = t.transaction_date or t.posting_date
            pay_ref = dict(value=pay.qbo_account_id if pay else None, name=pay.qbo_account_name if pay else None)
            note = f"RF-One Bank movement #{t.id} · {t.description_original or ''}"[:4000]
            if entity == DEPOSIT:
                payload = dict(TxnDate=str(day), DepositToAccountRef=pay_ref, TotalAmt=_money(t.amount_minor),
                               Line=api_lines, PrivateNote=note)
            else:
                payload = dict(TxnDate=str(day), PaymentType="CreditCard" if card else "Cash", AccountRef=pay_ref,
                               TotalAmt=_money(t.amount_minor), Line=api_lines, PrivateNote=note,
                               DocNumber=f"FT{t.id}", **({"Credit": True} if card and t.amount_minor > 0 else {}))
            key_id = tid
        if any(b["code"] == NOT_CONFIRMED for b in blockers):
            # Not reconciled yet: that is the reason; mapping or totals would only be noise.
            blockers = [b for b in blockers if b["code"] in (NOT_CONFIRMED, NO_OWNER)]
            wanted.clear()
        debits = sum(x["debit"] for x in lines)
        credits = sum(x["credit"] for x in lines)
        if lines and debits != credits and not any(b["code"] in (qbo_export.UNBALANCED, NOT_CONFIRMED) for b in blockers):
            blockers.append(dict(code=qbo_export.UNBALANCED, detail=f"debits {debits / 100:.2f} credits {credits / 100:.2f}"))
        # The company is part of what was exported: the same lines for another company are a change.
        sha = qbo_export.digest(dict(entity=entity, payload=payload, lines=lines, company=owner.id if owner else None))
        prior = done.get(tid) or (done.get(counterpart) if counterpart else None)
        state = None
        if prior is not None:
            batch = batches.get(prior.batch_id)
            state = batch.status if batch is not None and prior.status == FILE_EXPORTED else prior.status
            where = f"{STATE_LABELS.get(state, state)} · {prior.export_file or str(prior.created_at)[:16]}"
            moved = (owner is not None and prior.reporting_entity_id is not None
                     and prior.reporting_entity_id != owner.id)
            if moved:
                was = db.get(m.ReportingEntity, prior.reporting_entity_id)
                where += f" · exported for {was.name if was else prior.reporting_entity_id}, now of {owner.name}"
            blockers.append(dict(code=qbo_export.CHANGED_AFTER_EXPORT if prior.payload_sha256 != sha or moved
                                 else qbo_export.ALREADY_EXPORTED, detail=where))
        # A correspondence is asked only for a movement that nothing else blocks.
        mapping_codes = (qbo_export.CATEGORY_NOT_MAPPED, qbo_export.PAYMENT_ACCOUNT_NOT_MAPPED, NOT_VERIFIED,
                         MAP_PROPOSED)
        if all(b["code"] in mapping_codes for b in blockers):
            for entity_id, group, key in wanted:
                need[entity_id][group][key] += 1
        for b in blockers:
            b["label"] = LABELS.get(b["code"], b["code"])
        changed = any(b["code"] == qbo_export.CHANGED_AFTER_EXPORT for b in blockers)
        items.append(dict(txn_id=key_id, counterpart_id=counterpart, entity=entity,
                          owner_id=owner.id if owner else None, owner=owner.name if owner else None,
                          date=str(((txns.get(key_id) or t).posting_date or t.transaction_date) or ""),
                          description=t.description_original or "", amount_minor=t.amount_minor,
                          request_id=qbo_export.request_id(key_id), sha256=sha, payload=payload, lines=lines,
                          blockers=blockers, ready=not blockers, export_state=state, changed=changed,
                          exported=prior is not None and not changed))
    kinds = dict(sources=qbo_export.PAYMENT_ACCOUNT, whats=qbo_export.CATEGORY)
    need = {entity_id: {group: [dict(local_id=k[0], label=k[1], movements=n, kind=kinds[group],
                                     current=_row_view(cmaps.get((entity_id, kinds[group], k[0]))),
                                     hints=[h for h in hints.get((kinds[group], k[0]), []) if h["entity_id"] != entity_id])
                                for k, n in counter.most_common()]
                        for group, counter in groups.items()}
            for entity_id, groups in need.items()}
    return dict(items=items, excluded=dict(excluded), need=need,
                ready=sum(i["ready"] for i in items), blocked=sum(not i["ready"] and not i["exported"] for i in items),
                exported=sum(i["exported"] for i in items), changed=sum(i["changed"] for i in items),
                by_entity=dict(Counter(i["entity"] for i in items)))


def _row_view(r) -> dict | None:
    return None if r is None else dict(id=r.id, name=r.qbo_account_name, status=r.status, proposed_from=r.proposed_from)


# ---------------------------------------------------------------- the export file (one company per file)

# Intuit's "Import journal entries" (Settings > Import data > Journal entries; every plan, Simple Start to
# Advanced) requires Journal No., Journal Date, Account Name, Description, Debits, Credits — only those are written.
# Name is required by Intuit only on A/R and A/P lines, which this file never has; Memo / Currency / Class /
# Location are not in Intuit's list and are not written. Sub-accounts must be "Parent:Sub" (the Account List's full
# name). Intuit's import accepts files of fewer than 1,000 rows: a batch holds whole entries up to MAX_ROWS lines,
# the rest go in the next file. The date format is not stated by Intuit: MM/DD/YYYY (US company) — to check in the
# test import.
JE_COLUMNS = ("Journal No", "Journal Date", "Account Name", "Debits", "Credits", "Description")
MAX_ROWS = 990


def _csv(planned) -> tuple[str, int]:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(JE_COLUMNS)
    n = 0
    for i in planned:
        day = datetime.fromisoformat(i["date"]).strftime("%m/%d/%Y")
        ref = f"RF-One Bank #{i['txn_id']}" + (f"+#{i['counterpart_id']}" if i["counterpart_id"] else "")
        for ln in i["lines"]:
            w.writerow((i["journal_no"], day, ln["account"],
                        _money(ln["debit"]) if ln["debit"] else "", _money(ln["credit"]) if ln["credit"] else "",
                        f"{ref} · {ln.get('description') or i['description']}"[:4000]))
            n += 1
    return out.getvalue(), n


def journal_no(txn_id: int) -> str:
    """The entry number in QBO (its DocNumber, at most 21 characters): stable per movement, so the same movement
    never gets two numbers and QBO's duplicate-number warning can catch a second import."""
    return f"RFB-{txn_id}"


def generate_batch(db, txn_ids, *, owner_id: int, account_id: int | None,
                   feeds_excluded: bool = False) -> "m.BankQboExportBatch":
    """The journal-entry import file of the READY movements of ONE company (a new batch, GENERATED). Every
    movement is re-checked to belong to that company and to use only that company's verified accounts.
    `feeds_excluded`: the person's statement that these accounts' bank-feed items in QBO are not added (journal
    entries cannot be matched to them) — without it no file is generated."""
    if not feeds_excluded:
        raise ValueError("Confirm first that, in QuickBooks, the bank-feed items of these accounts for the same "
                         "movements will be excluded (not added): a journal entry cannot be matched to them, so "
                         "the movement would be recorded twice.")
    entity = _company(db, owner_id)
    planned = [i for i in plan(db, txn_ids)["items"] if i["ready"] and i["owner_id"] == entity.id]
    if not planned:
        raise ValueError(f"No movement of {entity.name} is ready for QuickBooks Online.")
    names = chart(db, entity.id)
    kept, rows = [], 0
    for i in planned:                      # whole entries only, under Intuit's row limit
        if rows + len(i["lines"]) > MAX_ROWS:
            break
        kept.append(i)
        rows += len(i["lines"])
    planned = kept
    for i in planned:
        bad = [ln["account"] for ln in i["lines"] if ln["account"] not in names]
        if bad:
            raise ValueError(f"Movement #{i['txn_id']} uses accounts that are not in {entity.name}'s chart: "
                             + ", ".join(map(str, bad)))
        i["journal_no"] = journal_no(i["txn_id"])
    content, n_lines = _csv(planned)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", entity.name).strip("_")
    file_name = f"QBO_journal_entries_{slug}_{stamp}.csv"
    k = 1
    while db.scalar(select(m.BankQboExportBatch.id).where(m.BankQboExportBatch.file_name == file_name)):
        k += 1
        file_name = f"QBO_journal_entries_{slug}_{stamp}_{k}.csv"
    batch = m.BankQboExportBatch(
        reporting_entity_id=entity.id, file_name=file_name, file_format=JOURNAL_CSV, content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        movements_json=json.dumps([dict(txn_id=i["txn_id"], counterpart_id=i["counterpart_id"], entity=i["entity"],
                                        journal_no=i["journal_no"], amount_minor=i["amount_minor"],
                                        sha256=i["sha256"]) for i in planned]),
        journal_count=len(planned), line_count=n_lines,
        total_minor=sum(ln["debit"] for i in planned for ln in i["lines"]),
        status=GENERATED, created_by_account_id=account_id)
    db.add(batch)
    db.flush()
    for i in planned:
        db.add(m.BankQboExport(financial_transaction_id=i["txn_id"], counterpart_transaction_id=i["counterpart_id"],
                               request_id=i["request_id"], payload_sha256=i["sha256"], status=FILE_EXPORTED,
                               qbo_entity=i["entity"], export_file=file_name, reporting_entity_id=entity.id,
                               batch_id=batch.id, created_by_account_id=account_id))
    db.flush()
    return batch


def download(db, batch_id: int) -> "m.BankQboExportBatch":
    """The SAME kept file: a new download creates no batch and exports nothing again; it is only counted."""
    batch = db.get(m.BankQboExportBatch, batch_id)
    if batch is None:
        raise ValueError("Export file not found.")
    now = datetime.now(timezone.utc)
    batch.download_count = (batch.download_count or 0) + 1
    batch.first_downloaded_at = batch.first_downloaded_at or now
    batch.last_downloaded_at = now
    db.flush()
    return batch


def confirm_import(db, batch_id: int, *, account_id: int | None, note: str = "") -> "m.BankQboExportBatch":
    """A person states the file was imported in that company's QBO. Only a generated file can be confirmed."""
    batch = db.get(m.BankQboExportBatch, batch_id)
    if batch is None or batch.status != GENERATED:
        raise ValueError("Only a generated file not yet confirmed or withdrawn can be confirmed as imported.")
    if not batch.download_count:
        raise ValueError("This file was never downloaded from Bank: download it and import it in QuickBooks first.")
    batch.status, batch.import_confirmed_at = IMPORT_CONFIRMED, datetime.now(timezone.utc)
    batch.import_confirmed_by_account_id, batch.import_note = account_id, (note or "").strip()[:2000] or None
    db.flush()
    return batch


def withdraw(db, batch_id: int, *, account_id: int | None, reason: str) -> "m.BankQboExportBatch":
    """A person states the file was NOT imported in QBO: its movements become exportable again (they will go into a
    NEW file, with the same journal numbers). Refused once the import is confirmed."""
    batch = db.get(m.BankQboExportBatch, batch_id)
    if batch is None or batch.status != GENERATED:
        raise ValueError("Only a generated file whose import is not confirmed can be withdrawn.")
    if not (reason or "").strip():
        raise ValueError("Say why the file is withdrawn (for example: the import in QuickBooks failed).")
    for r in db.scalars(select(m.BankQboExport).where(m.BankQboExport.batch_id == batch.id)):
        db.delete(r)
    batch.status, batch.withdrawn_at = WITHDRAWN, datetime.now(timezone.utc)
    batch.withdrawn_by_account_id, batch.withdraw_reason = account_id, reason.strip()[:2000]
    db.flush()
    return batch


def batch_list(db) -> list[dict]:
    names = {e.id: e.name for e in db.scalars(select(m.ReportingEntity))}
    return [dict(id=b.id, file_name=b.file_name, owner=names.get(b.reporting_entity_id), owner_id=b.reporting_entity_id,
                 status=b.status, state=STATE_LABELS.get(b.status, b.status), journals=b.journal_count,
                 lines=b.line_count, total_minor=b.total_minor, downloads=b.download_count,
                 created_at=b.created_at, confirmed_at=b.import_confirmed_at, note=b.import_note,
                 withdrawn_at=b.withdrawn_at, withdraw_reason=b.withdraw_reason)
            for b in db.scalars(select(m.BankQboExportBatch).order_by(m.BankQboExportBatch.id.desc()))]


SEND_PREREQUISITES = (
    "an Intuit Developer app for RF-One (Client ID and Client Secret, production keys after Intuit's review)",
    "the OAuth 2.0 authorization of each company by its QuickBooks administrator (gives the company's realm id)",
    "secure storage and renewal of the access and refresh tokens",
    "the QBO account Ids of each company, read through the API (the Account List export has none)",
    "a test against an Intuit sandbox company before the first real send",
)
