"""RFBank — link each confirmed Zelle payment to its bank movement (Product Owner, 2026-11-20).

The Chase "Payment Activity" print carries the memo (causale) of every Zelle payment; the bank statement only says
"Zelle payment to <name> <reference>". This module ties the two together so the memo becomes visible evidence on
the movement. It never changes the movement, its description, WHO, WHY, rules or decisions.

    bank_zelle_payments (confirmed by the person)  ->  bank_source_documents (one ZELLE_PAYMENT per payment)
                                                   ->  bank_transaction_document_links (movement <-> payment)

Matching, deterministic and without AI:
* only payments with status Completed and direction OUT; Rejected / Pending / ambiguous payments are never linked;
* a candidate movement is an outgoing "Zelle payment to <name> ..." with the same amount, posted 0-3 days after the
  date sent, whose name is the same recipient (trimmed, case-insensitive, small typos tolerated);
* same date, recipient name contained and same amount -> certain, linked automatically (Product Owner, 2026-11-20);
* otherwise exactly one candidate on both sides within 0-3 days -> linked automatically (AUTO, CONFIRMED);
* several candidates -> one PROPOSED link per candidate pair: the person chooses (HUMAN, CONFIRMED / REJECTED);
* links already decided are never touched again; re-running is idempotent.

The two tables follow the evidence-link design of Bank 1.0 (models BankSourceDocument / BankTransactionDocumentLink)
and are created here only when missing, empty, as plain SQLite tables.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import text

import bank_zelle

KIND = "ZELLE_PAYMENT"
ROLE = "PAYMENT_DETAIL"
MAX_DAYS = 3
NAME_SIMILARITY = 0.85

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS bank_source_documents (
        id INTEGER PRIMARY KEY,
        source_kind VARCHAR(32) NOT NULL,
        source_key VARCHAR(255) NOT NULL,
        parent_id INTEGER REFERENCES bank_source_documents(id),
        artifact_id INTEGER REFERENCES bank_flow_artifacts(id),
        purchase_document_id INTEGER REFERENCES purchase_documents(id),
        document_date DATE,
        amount_minor INTEGER,
        currency VARCHAR(3),
        counterparty VARCHAR(255),
        reference VARCHAR(255),
        detail_json TEXT,
        status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_bsd_kind_key UNIQUE (source_kind, source_key),
        CONSTRAINT ck_bsd_kind CHECK (source_kind IN ('ZELLE_PAYMENT', 'PAYPAL_TRANSACTION', 'AMAZON_ORDER',
            'AMAZON_ITEM', 'ADP_PAYROLL_COMPONENT', 'PURCHASE_DOCUMENT', 'OTHER')),
        CONSTRAINT ck_bsd_status CHECK (status IN ('ACTIVE', 'SUPERSEDED', 'VOID')))""",
    "CREATE INDEX IF NOT EXISTS ix_bsd_parent_id ON bank_source_documents (parent_id)",
    "CREATE INDEX IF NOT EXISTS ix_bsd_document_date ON bank_source_documents (document_date)",
    """CREATE TABLE IF NOT EXISTS bank_transaction_document_links (
        id INTEGER PRIMARY KEY,
        financial_transaction_id INTEGER NOT NULL REFERENCES financial_transactions(id),
        source_document_id INTEGER NOT NULL REFERENCES bank_source_documents(id),
        allocation_id INTEGER REFERENCES bank_transaction_allocations(id),
        role VARCHAR(16) NOT NULL,
        linked_amount_minor INTEGER,
        status VARCHAR(16) NOT NULL DEFAULT 'PROPOSED',
        match_method VARCHAR(8) NOT NULL,
        match_basis TEXT,
        decided_by_account_id INTEGER REFERENCES rfone_accounts(id),
        decided_at DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_btdl_link UNIQUE (financial_transaction_id, source_document_id, allocation_id),
        CONSTRAINT ck_btdl_role CHECK (role IN ('PAYMENT_DETAIL', 'ORDER', 'ITEM', 'PAYROLL', 'SUPPORT')),
        CONSTRAINT ck_btdl_status CHECK (status IN ('PROPOSED', 'CONFIRMED', 'REJECTED')),
        CONSTRAINT ck_btdl_match_method CHECK (match_method IN ('AUTO', 'HUMAN')))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_btdl_link_without_allocation
        ON bank_transaction_document_links (financial_transaction_id, source_document_id) WHERE allocation_id IS NULL""",
    "CREATE INDEX IF NOT EXISTS ix_btdl_financial_transaction_id ON bank_transaction_document_links (financial_transaction_id)",
    "CREATE INDEX IF NOT EXISTS ix_btdl_source_document_id ON bank_transaction_document_links (source_document_id)",
)

# "Zelle payment to Tatiana Ceban JPM99cy7jlfh" / "Zelle payment to Leo Windows Cleaning 30912033433"
_BANK_NAME = re.compile(r"^\s*ZELLE\s+PAYMENT\s+TO\s+(?P<name>.+?)\s+\S+\s*$", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure(db) -> None:
    for statement in SCHEMA:
        db.execute(text(statement))


def exists(db) -> bool:
    return bool(db.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bank_transaction_document_links'")).scalar())


def bank_name(description: str | None) -> str | None:
    match = _BANK_NAME.match(description or "")
    return match.group("name") if match else None


def _letters(name: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", bank_zelle.who_key(name))


def same_recipient(a: str | None, b: str | None) -> bool:
    """Same Zelle recipient: equal after normalisation, one name contained in the other ("BBC" / "BBC Wine"), or a
    small typo ("Fosterr King", "Michael Costruction")."""
    x, y = _letters(a), _letters(b)
    if not x or not y:
        return False
    return x == y or x in y or y in x or SequenceMatcher(None, x, y).ratio() >= NAME_SIMILARITY


def _completed(status: str | None) -> bool:
    return " ".join(str(status or "").split()).casefold() == "completed"


def _document(db, p: dict) -> int:
    """The ZELLE_PAYMENT source document of one stored payment (created once, keyed by the payment row)."""
    key = f"bank_zelle_payments:{p['id']}"
    found = db.execute(text("SELECT id FROM bank_source_documents WHERE source_kind=:k AND source_key=:s"),
                       {"k": KIND, "s": key}).scalar()
    if found:
        return found
    db.execute(text("""INSERT INTO bank_source_documents (source_kind,source_key,document_date,amount_minor,currency,
                       counterparty,reference,detail_json,status) VALUES (:k,:s,:d,:a,'USD',:c,:r,:j,'ACTIVE')"""),
               dict(k=KIND, s=key, d=p["sent_on"], a=p["amount_minor"], c=p["recipient"], r=p.get("payment_id"),
                    j=json.dumps(dict(memo=p.get("memo"), status=p.get("status"), file_names=p.get("file_names")),
                                 ensure_ascii=False)))
    return db.execute(text("SELECT last_insert_rowid()")).scalar()


def match(db) -> dict:
    """Link confirmed Zelle payments to bank movements. Never commits. Returns the counts of the run."""
    ensure(db)
    if not bank_zelle.exists(db):
        return dict(linked=0, proposed=0, already=0, no_movement=0, skipped=0)
    payments = [dict(r) for r in db.execute(text(
        """SELECT id,sent_on,status,direction,recipient,memo,amount_minor,payment_id,file_names,status_basis
           FROM bank_zelle_payments ORDER BY sent_on,id""")).mappings()]
    eligible = [p for p in payments if (p.get("direction") or "OUT") == "OUT" and _completed(p.get("status"))
                and p.get("status_basis") != "AMBIGUOUS"]
    # payments / movements already settled (a confirmed link) or with a decision pending are left alone
    decided_docs, decided_txns, rejected = set(), set(), set()
    existing = set()
    for r in db.execute(text("""SELECT l.financial_transaction_id t, d.source_key k, l.status s
                                FROM bank_transaction_document_links l JOIN bank_source_documents d
                                ON d.id=l.source_document_id WHERE d.source_kind=:k"""), {"k": KIND}).mappings():
        pid = int(r["k"].split(":")[1])
        existing.add((pid, r["t"]))
        if r["s"] == "CONFIRMED":
            decided_docs.add(pid)
            decided_txns.add(r["t"])
        elif r["s"] == "REJECTED":
            rejected.add((pid, r["t"]))
    if not eligible:
        return dict(linked=0, proposed=0, already=len(decided_docs), no_movement=0,
                    skipped=len(payments) - len(eligible))
    first = min(p["sent_on"] for p in eligible)
    last = (date.fromisoformat(max(p["sent_on"] for p in eligible)) + timedelta(days=MAX_DAYS)).isoformat()
    movements = defaultdict(list)
    for t in db.execute(text("""SELECT id,posting_date,amount_minor,description_original FROM financial_transactions
                                WHERE amount_minor<0 AND posting_date BETWEEN :a AND :b
                                AND upper(description_original) LIKE 'ZELLE PAYMENT TO %'
                                AND COALESCE(duplicate_status,'NONE')='NONE'"""), {"a": first, "b": last}).mappings():
        movements[-t["amount_minor"]].append(dict(t))

    candidates = {}
    for p in eligible:
        if p["id"] in decided_docs:
            continue
        sent = date.fromisoformat(p["sent_on"])
        candidates[p["id"]] = [
            t for t in movements.get(p["amount_minor"], [])
            if t["id"] not in decided_txns and (p["id"], t["id"]) not in rejected
            and 0 <= (date.fromisoformat(str(t["posting_date"])[:10]) - sent).days <= MAX_DAYS
            and same_recipient(p["recipient"], bank_name(t["description_original"]))]
    by_txn = defaultdict(list)
    for pid, ts in candidates.items():
        for t in ts:
            by_txn[t["id"]].append(pid)

    by_id = {p["id"]: p for p in eligible}
    now, linked, proposed, no_movement = _now(), 0, 0, 0
    proposed_ids = {}
    for r in db.execute(text("""SELECT l.id, l.financial_transaction_id t, d.source_key k FROM bank_transaction_document_links l
                                JOIN bank_source_documents d ON d.id=l.source_document_id
                                WHERE d.source_kind=:k AND l.status='PROPOSED'"""), {"k": KIND}).mappings():
        proposed_ids[(int(r["k"].split(":")[1]), r["t"])] = r["id"]

    def confirm(p, t, basis):
        """Record (or upgrade a PROPOSED pair to) a certain AUTO link and discard the other proposals of the same
        payment and of the same movement."""
        nonlocal linked
        doc = _document(db, p)
        if (p["id"], t["id"]) in proposed_ids:
            db.execute(text("""UPDATE bank_transaction_document_links SET status='CONFIRMED',match_basis=:b,decided_at=:at
                               WHERE id=:i AND status='PROPOSED'"""), dict(b=basis, at=now, i=proposed_ids[(p["id"], t["id"])]))
        else:
            db.execute(text("""INSERT INTO bank_transaction_document_links (financial_transaction_id,source_document_id,
                               role,linked_amount_minor,status,match_method,match_basis,decided_at)
                               VALUES (:t,:d,:r,:a,'CONFIRMED','AUTO',:b,:at)"""),
                       dict(t=t["id"], d=doc, r=ROLE, a=t["amount_minor"], b=basis, at=now))
        db.execute(text("""UPDATE bank_transaction_document_links SET status='REJECTED',decided_at=:at,
                           match_basis=COALESCE(match_basis,'')||' | scartato: abbinamento certo trovato'
                           WHERE status='PROPOSED' AND match_method='AUTO' AND NOT (financial_transaction_id=:t AND source_document_id=:d)
                           AND (financial_transaction_id=:t OR source_document_id=:d)
                           AND source_document_id IN (SELECT id FROM bank_source_documents WHERE source_kind=:k)"""),
                   dict(at=now, t=t["id"], d=doc, k=KIND))
        existing.add((p["id"], t["id"]))
        linked += 1

    def day(t):
        return str(t["posting_date"])[:10]

    def describe(p, t):
        days = (date.fromisoformat(day(t)) - date.fromisoformat(p["sent_on"])).days
        return (f"Zelle {p['sent_on']} {p['recipient']} {p['amount_minor'] / 100:.2f} -> movimento {day(t)} "
                f"{-t['amount_minor'] / 100:.2f} (+{days} g)")

    # 1. Certain (Product Owner, 2026-11-20): same date, recipient name contained in the bank description, same
    #    amount. Certain unless two payments or two movements share all three (then the person chooses).
    same_day = {pid: [t for t in ts if day(t) == by_id[pid]["sent_on"]] for pid, ts in candidates.items()}
    same_day_txn = defaultdict(list)
    for pid, ts in same_day.items():
        for t in ts:
            same_day_txn[t["id"]].append(pid)
    taken_p, taken_t = set(), set()
    for pid, ts in same_day.items():
        if len(ts) == 1 and len(same_day_txn[ts[0]["id"]]) == 1:
            confirm(by_id[pid], ts[0], describe(by_id[pid], ts[0]) + "; certo: stessa data, stesso nome, stesso importo")
            taken_p.add(pid)
            taken_t.add(ts[0]["id"])

    # 2. The rest: a single candidate on both sides within 0-3 days is linked; otherwise the person chooses.
    rest = {pid: [t for t in ts if t["id"] not in taken_t] for pid, ts in candidates.items() if pid not in taken_p}
    by_txn = defaultdict(list)
    for pid, ts in rest.items():
        for t in ts:
            by_txn[t["id"]].append(pid)
    for pid, ts in rest.items():
        p = by_id[pid]
        if not ts:
            if not candidates[pid]:
                no_movement += 1
            continue
        if len(ts) == 1 and len(by_txn[ts[0]["id"]]) == 1:
            confirm(p, ts[0], describe(p, ts[0]) + "; unico candidato")
            continue
        for t in ts:
            if (pid, t["id"]) in existing:
                continue
            db.execute(text("""INSERT INTO bank_transaction_document_links (financial_transaction_id,source_document_id,
                               role,linked_amount_minor,status,match_method,match_basis)
                               VALUES (:t,:d,:r,:a,'PROPOSED','AUTO',:b)"""),
                       dict(t=t["id"], d=_document(db, p), r=ROLE, a=t["amount_minor"],
                            b=describe(p, t) + f"; {len(ts)} movimenti / {len(by_txn[t['id']])} pagamenti candidati"))
            existing.add((pid, t["id"]))
            proposed += 1
    return dict(linked=linked, proposed=proposed, already=len(decided_docs), no_movement=no_movement,
                skipped=len(payments) - len(eligible))


def decide(db, link_id: int, choice: str, account_id: int) -> None:
    """The person resolves an ambiguous pair: CONFIRMED rejects the competing proposals of the same payment and of
    the same movement; REJECTED discards this pair only. Never commits."""
    if choice not in ("CONFIRMED", "REJECTED"):
        raise ValueError("Scelta non valida.")
    row = db.execute(text("""SELECT l.id,l.status,l.financial_transaction_id t,l.source_document_id d
                             FROM bank_transaction_document_links l JOIN bank_source_documents s ON s.id=l.source_document_id
                             WHERE l.id=:i AND s.source_kind=:k"""), {"i": link_id, "k": KIND}).mappings().first()
    if row is None or row["status"] != "PROPOSED":
        raise ValueError("Questo abbinamento non è più in attesa di decisione.")
    now = _now()
    db.execute(text("""UPDATE bank_transaction_document_links SET status=:s,match_method='HUMAN',
                       decided_by_account_id=:a,decided_at=:t WHERE id=:i"""),
               dict(s=choice, a=account_id, t=now, i=link_id))
    if choice == "CONFIRMED":
        db.execute(text("""UPDATE bank_transaction_document_links SET status='REJECTED',match_method='HUMAN',
                           decided_by_account_id=:a,decided_at=:t
                           WHERE status='PROPOSED' AND id<>:i AND (source_document_id=:d OR financial_transaction_id=:x)
                           AND source_document_id IN (SELECT id FROM bank_source_documents WHERE source_kind=:k)"""),
                   dict(a=account_id, t=now, i=link_id, d=row["d"], x=row["t"], k=KIND))


def memos(db) -> dict[int, dict]:
    """{movement id: {memo, recipient, sent_on}} for every confirmed Zelle link (read-only)."""
    if not exists(db) or not bank_zelle.exists(db):
        return {}
    out = {}
    for r in db.execute(text("""SELECT l.financial_transaction_id t, d.source_key k FROM bank_transaction_document_links l
                                JOIN bank_source_documents d ON d.id=l.source_document_id
                                WHERE d.source_kind=:k AND l.status='CONFIRMED'"""), {"k": KIND}).mappings():
        out[r["t"]] = int(r["k"].split(":")[1])
    if not out:
        return {}
    rows = {r["id"]: dict(r) for r in db.execute(text(
        "SELECT id,memo,recipient,sent_on FROM bank_zelle_payments")).mappings()}
    return {t: dict(memo=rows[p]["memo"], recipient=rows[p]["recipient"], sent_on=rows[p]["sent_on"])
            for t, p in out.items() if p in rows}


def overview(db) -> dict | None:
    """Counts and the open (ambiguous) pairs for the Documenti Zelle card."""
    if not exists(db) or not bank_zelle.exists(db):
        return None
    pending = [dict(r) for r in db.execute(text(
        """SELECT l.id, l.match_basis, t.posting_date, t.description_original, t.amount_minor,
                  p.sent_on, p.recipient, p.memo, p.id AS payment, p.amount_minor AS zelle_amount_minor
           FROM bank_transaction_document_links l
           JOIN bank_source_documents d ON d.id=l.source_document_id AND d.source_kind=:k
           JOIN financial_transactions t ON t.id=l.financial_transaction_id
           JOIN bank_zelle_payments p ON p.id=CAST(substr(d.source_key, 21) AS INTEGER)
           WHERE l.status='PROPOSED' ORDER BY p.sent_on, p.id, t.posting_date"""), {"k": KIND}).mappings()]
    counts = dict(db.execute(text("""SELECT l.status, COUNT(*) FROM bank_transaction_document_links l
        JOIN bank_source_documents d ON d.id=l.source_document_id AND d.source_kind=:k GROUP BY l.status"""),
                             {"k": KIND}).all())
    linked_payments = db.execute(text("""SELECT COUNT(DISTINCT d.id) FROM bank_transaction_document_links l
        JOIN bank_source_documents d ON d.id=l.source_document_id AND d.source_kind=:k WHERE l.status='CONFIRMED'"""),
                                 {"k": KIND}).scalar()
    completed = [r for r in db.execute(text(
        "SELECT id,sent_on,status,direction,status_basis FROM bank_zelle_payments")).mappings()
        if (r["direction"] or "OUT") == "OUT" and _completed(r["status"]) and r["status_basis"] != "AMBIGUOUS"]
    pending_payments = {r["payment"] for r in pending}
    linked_ids = {int(k.split(":")[1]) for (k,) in db.execute(text(
        """SELECT d.source_key FROM bank_transaction_document_links l JOIN bank_source_documents d
           ON d.id=l.source_document_id AND d.source_kind=:k WHERE l.status='CONFIRMED'"""), {"k": KIND})}
    without = defaultdict(int)
    for r in completed:
        if r["id"] not in linked_ids and r["id"] not in pending_payments:
            without[r["sent_on"][:7]] += 1
    zelle_movements = db.execute(text("""SELECT COUNT(*) FROM financial_transactions WHERE amount_minor<0
        AND upper(description_original) LIKE 'ZELLE PAYMENT TO %' AND COALESCE(duplicate_status,'NONE')='NONE'""")).scalar()
    return dict(confirmed=counts.get("CONFIRMED", 0), linked_payments=linked_payments,
                pending=pending, pending_payments=len(pending_payments), rejected=counts.get("REJECTED", 0),
                completed=len(completed), without_movement=sorted(without.items()),
                without_total=sum(without.values()), zelle_movements=zelle_movements,
                movements_without=zelle_movements - counts.get("CONFIRMED", 0))
