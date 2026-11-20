"""QuickBooks Online export of split movements — model and local preview (BANK_SPLIT_ALLOCATION_001).

Format chosen: the QuickBooks Online Accounting API entity **Purchase** (the "Expense" of the QBO UI), one per
bank movement, with one `AccountBasedExpenseLineDetail` line per split line (`BankTransactionAllocation`).
Intuit documents (https://developer.intuit.com/docs/api/accounting/purchase): `PaymentType` Cash | Check |
CreditCard; `AccountRef` is the bank / credit-card account paid from; `Line[]` carries `Amount`,
`DetailType = "AccountBasedExpenseLineDetail"`, `Description` and the expense `AccountRef`; `TotalAmt` equals
the sum of the lines; `Credit = true` marks a credit-card refund (valid only for CreditCard). Idempotency: a
unique `requestid` query parameter (max 50 characters, unique per company) makes a repeated create return the
original response instead of a second Purchase.

So: ONE Purchase per movement, never one payment per product; the paying Source stays the `AccountRef`; the
RF-One movement, its bank description and the document codes stay in `PrivateNote` / `DocNumber`. Amounts are
computed in integer cents and checked before any decimal is written.

Not implemented (no QBO connection exists): OAuth, the realm, the HTTP call. `preview` writes nothing;
`record_export` is the duplicate-protection step the future sender must call. Nothing is sent to QBO.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import inspect, select

from .. import models as m

CATEGORY, PAYMENT_ACCOUNT = "CATEGORY", "PAYMENT_ACCOUNT"
NO_SPLIT = "NO_SPLIT"
SPLIT_INCOMPLETE = "SPLIT_INCOMPLETE"
UNBALANCED = "UNBALANCED"
CATEGORY_NOT_MAPPED = "CATEGORY_NOT_MAPPED"
PAYMENT_ACCOUNT_NOT_MAPPED = "PAYMENT_ACCOUNT_NOT_MAPPED"
ALREADY_EXPORTED = "ALREADY_EXPORTED"
CHANGED_AFTER_EXPORT = "CHANGED_AFTER_EXPORT"
NOT_A_PURCHASE = "NOT_A_PURCHASE"
LABELS = {
    NO_SPLIT: "Nessuna ripartizione confermata",
    SPLIT_INCOMPLETE: "Ripartizione incompleta",
    UNBALANCED: "Totale ripartito diverso dal movimento",
    CATEGORY_NOT_MAPPED: "Categoria QBO non mappata",
    PAYMENT_ACCOUNT_NOT_MAPPED: "Conto bancario/carta QBO non mappato",
    ALREADY_EXPORTED: "Già esportato in QBO",
    CHANGED_AFTER_EXPORT: "Ripartizione cambiata dopo l'esportazione",
    NOT_A_PURCHASE: "Entrata non rimborso: in QBO non è un Purchase",
}
UNMAPPED = "UNMAPPED"


def _has(db, table: str) -> bool:
    return inspect(db.get_bind()).has_table(table)


def maps(db, entity_id: int | None = None) -> dict:
    """(kind, local id) → (qbo id, qbo name) of ONE company's verified correspondences (d3a520261103: they are per
    company; one made for no company is never used). Empty on a database without the table."""
    if not _has(db, "bank_qbo_account_maps") or entity_id is None:
        return {}
    return {(r.kind, r.local_id): (r.qbo_account_id, r.qbo_account_name) for r in db.scalars(select(m.BankQboAccountMap).where(
        m.BankQboAccountMap.reporting_entity_id == entity_id, m.BankQboAccountMap.status == "VERIFIED"))}


def set_map(*_args, **_kwargs):
    """Retired (d3a520261103): a correspondence is per company and verified against that company's chart —
    `qbo_books.set_map`. A correspondence for no company is never created again."""
    raise ValueError("QBO correspondences are per company: use Upload and Reconcile > QuickBooks Online.")


def exports(db) -> dict:
    if not _has(db, "bank_qbo_exports"):
        return {}
    return {r.financial_transaction_id: r for r in db.scalars(select(m.BankQboExport))}


def request_id(txn_id: int) -> str:
    """Stable per movement: a retry of the same movement can never become a second Purchase in QBO."""
    return f"rfone-bank-ft-{txn_id}"


def _amount(minor: int) -> float:
    # Two-decimal values built from integer cents; the totals are checked in cents, never in floats.
    return float(Decimal(abs(minor)) / 100)


def digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def purchase(db, txn, allocations, *, mapping=None, sources=None) -> dict:
    """dict(payload, blockers, request_id, sha256, lines_minor, total_minor) for one movement."""
    source = (sources or {}).get(txn.payment_instrument_id) or db.get(m.PaymentInstrument, txn.payment_instrument_id)
    if mapping is None:
        from . import card_configuration
        owner = card_configuration.owner_entity_for(db, instrument=source, on_date=txn.posting_date or txn.transaction_date)             if source else None
        mapping = maps(db, owner.id if owner else None)
    blockers = []

    def block(code, detail=""):
        blockers.append(dict(code=code, label=LABELS[code], detail=detail))

    card = bool(source and source.instrument_type == "CREDIT_CARD")
    refund = txn.amount_minor > 0
    if refund and not card:
        block(NOT_A_PURCHASE, "money in on a bank account (a QBO Deposit, not part of this export)")
    if not allocations:
        block(NO_SPLIT)
    elif any(a.status != m.ALLOCATION_COMPLETE for a in allocations):
        block(SPLIT_INCOMPLETE, ", ".join(sorted({a.status for a in allocations if a.status != m.ALLOCATION_COMPLETE})))
    lines_minor = sum(a.amount_minor for a in allocations)
    if allocations and lines_minor != txn.amount_minor:
        block(UNBALANCED, f"lines {lines_minor / 100:.2f} vs movement {txn.amount_minor / 100:.2f}")
    pay = mapping.get((PAYMENT_ACCOUNT, txn.payment_instrument_id))
    if not pay:
        block(PAYMENT_ACCOUNT_NOT_MAPPED, source.display_name if source else f"Source #{txn.payment_instrument_id}")
    lines, unmapped = [], []
    for a in allocations:
        account = mapping.get((CATEGORY, a.accounting_classification_id)) if a.accounting_classification_id else None
        if not account:
            unmapped.append(f"{a.accounting_classification_code_snapshot or '—'} {a.accounting_classification_name_snapshot or ''}".strip())
        lines.append({
            "Amount": _amount(a.amount_minor),
            "DetailType": "AccountBasedExpenseLineDetail",
            "Description": (a.description or a.transaction_reason_name_snapshot or "")[:4000],
            "AccountBasedExpenseLineDetail": {"AccountRef": {
                "value": account[0] if account else UNMAPPED,
                "name": (account[1] if account else None) or a.accounting_classification_name_snapshot}},
        })
    if unmapped:
        block(CATEGORY_NOT_MAPPED, "; ".join(sorted(set(unmapped))))
    codes = sorted({a.evidence_reference for a in allocations if a.evidence_reference})
    payload = {
        "TxnDate": str(txn.transaction_date or txn.posting_date or ""),
        "PaymentType": "CreditCard" if card else "Cash",
        "AccountRef": {"value": pay[0] if pay else UNMAPPED, "name": (pay[1] if pay else None) or (source.display_name if source else None)},
        "TotalAmt": _amount(txn.amount_minor),
        "DocNumber": (", ".join(codes) or f"FT{txn.id}")[:21],
        "PrivateNote": (f"RF-One Bank movement #{txn.id} · {txn.description_original or ''}"
                        + (f" · documents: {', '.join(codes)}" if codes else ""))[:4000],
        "Line": lines,
    }
    if refund and card:
        payload["Credit"] = True
    sha = digest(payload)
    done = exports(db).get(txn.id)
    if done is not None:
        block(CHANGED_AFTER_EXPORT if done.payload_sha256 != sha else ALREADY_EXPORTED,
              f"{done.status} {str(done.created_at)[:16]} requestid {done.request_id}")
    return dict(txn_id=txn.id, request_id=request_id(txn.id), sha256=sha, payload=payload, blockers=blockers,
                total_minor=txn.amount_minor, lines_minor=lines_minor, line_count=len(lines),
                ready=not blockers)


def preview(db, txn_ids) -> dict:
    """Local, verifiable preview: one Purchase per movement, the checks, nothing written or sent."""
    sources = {s.id: s for s in db.scalars(select(m.PaymentInstrument))}
    items = []
    for txn_id in txn_ids:
        txn = db.get(m.FinancialTransaction, txn_id)
        if txn is None:
            continue
        allocations = list(db.scalars(select(m.BankTransactionAllocation)
                                      .where(m.BankTransactionAllocation.financial_transaction_id == txn_id)
                                      .order_by(m.BankTransactionAllocation.allocation_index)))
        items.append(purchase(db, txn, allocations, sources=sources))
    return dict(format="QuickBooks Online Accounting API · Purchase (create)", purchases=items,
                ready=sum(i["ready"] for i in items), blocked=sum(not i["ready"] for i in items),
                lines=sum(i["line_count"] for i in items),
                exact=all(i["lines_minor"] == i["total_minor"] for i in items if i["line_count"]))


def record_export(db, item: dict, *, status: str = "PREPARED", account_id: int | None = None) -> "m.BankQboExport":
    """Duplicate protection, called by the future sender BEFORE sending (PREPARED) and after (SENT). A
    movement already recorded is refused; a blocked preview item is refused."""
    if not item.get("ready"):
        raise ValueError("This movement is not ready for QBO: " + "; ".join(b["label"] for b in item["blockers"]))
    if db.scalar(select(m.BankQboExport).where(m.BankQboExport.financial_transaction_id == item["txn_id"])):
        raise ValueError(f"Movement {item['txn_id']} is already recorded as exported to QBO.")
    row = m.BankQboExport(financial_transaction_id=item["txn_id"], request_id=item["request_id"],
                          payload_sha256=item["sha256"], status=status, created_by_account_id=account_id)
    db.add(row)
    db.flush()
    return row
