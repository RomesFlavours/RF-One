"""Read-only gateway to the operational Bank (decision 57).

Opens the Bank database with SQLite `mode=ro` plus `PRAGMA query_only`, so any
write attempted by reused code fails instead of reaching Bank data. Reuses the
Bank code (models, WHO extraction, rule execution, Source ownership, ChatGPT
adapter) by import; nothing of it is copied or modified.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import cached_property

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from . import config

# Importing Bank code must not even write bytecode caches into the Bank worktree.
sys.dont_write_bytecode = True

_DS = config.BANK_CODE_ROOT / "03 Software" / "RF-One Data Store"
_WEB = config.BANK_CODE_ROOT / "03 Software" / "RF-One Web"
for _p in (str(_DS), str(_WEB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.bank_reconciliation import (  # noqa: E402
    ai_rules, card_configuration, flow, reconciliation_runner, who_search_text, who_why_rules, why_patterns, why_what)


def engine():
    if not config.BANK_DB.exists():
        raise FileNotFoundError(f"Bank database not found: {config.BANK_DB}")
    url = f"sqlite:///file:{config.BANK_DB.as_posix()}?mode=ro&uri=true"
    eng = create_engine(url, connect_args={"uri": True, "check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _read_only(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA query_only = ON")

    return eng


_Session = None


def session():
    """A read-only session on the operational Bank database."""
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=engine(), autoflush=False, expire_on_commit=False)
    db = _Session()
    db.info["cbank_read_only"] = True
    return db


_Writers: dict = {}


def _writer_session():
    """The ONLY writable session the engine package opens: for a person's decision, recorded by Bank's own
    manual decision service (Phase 3A). The engine itself always reads through `session()`. Bound to the
    database `config.BANK_DB` names now."""
    path = config.BANK_DB.as_posix()
    if path not in _Writers:
        eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30})
        _Writers[path] = sessionmaker(bind=eng, expire_on_commit=False)
    return _Writers[path]()


def record_human_decision(txn_id: int, *, who_name: str, why_id: int, category_id: int | None = None,
                          note: str | None = None, account_id: int | None = None, associate: bool = False, beneficiary_id: int | None = None) -> int:
    """A person's WHO + WHY for one movement, through `recognition.record_human_decision` (the path Review
    uses): protected as HUMAN, WHO -> WHY association recorded, WHAT derived from the WHY. A WHO not yet in
    the catalog is created as Review's "+ New WHO" creates it. Returns the explanation id."""
    from rfone_data_store.bank_reconciliation import manual_reconciliation, recognition
    db = _writer_session()
    try:
        reason = db.get(m.BankTransactionReason, why_id)
        what = why_what.require_what(db, why_id) if reason is not None else None
        if category_id and what is not None and category_id != what.id:
            raise ValueError(f"The WHAT derives from the WHY: “{reason.name}” is {what.code} {what.name}.")
        who = next((o for o in db.scalars(select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))
                    if clean(o.canonical_name) == clean(who_name)), None)
        if who is None:
            who = manual_reconciliation.create_who(db, name=who_name).occurrence
        explanation = recognition.record_human_decision(db, recognition.HumanDecisionRequest(
            transaction_id=txn_id, occurrence_id=who.id, confirmed_by_account_id=account_id,
            transaction_reason_id=why_id, notes=note, record_association=associate))
        if beneficiary_id is not None:
            from rfone_data_store.bank_reconciliation import row_reconciliation
            row_reconciliation.set_for_whom(db, transaction_id=txn_id,
                reporting_entity_id=beneficiary_id, account_id=account_id)
        db.commit()
        return explanation.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def current_human_decisions() -> dict[int, dict]:
    db = session()
    try:
        rows = db.execute(select(m.FinancialTransaction.id, m.BankTransactionExplanation).join(
            m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id).where(
            m.BankTransactionExplanation.decision_source == "HUMAN"))
        return {tid: dict(txn_id=tid, who_name=e.occurrence_name_snapshot, why_id=e.transaction_reason_id,
                          category_id=e.accounting_classification_id, beneficiary_id=None, note=e.explanation_notes)
                for tid, e in rows}
    finally:
        db.close()


def human_decision_history(txn_id: int) -> list[dict]:
    """The human decisions Bank holds for one movement (current one marked active)."""
    db = session()
    try:
        txn = db.get(m.FinancialTransaction, txn_id)
        rows = db.scalars(select(m.BankTransactionExplanation).where(
            m.BankTransactionExplanation.financial_transaction_id == txn_id,
            m.BankTransactionExplanation.decision_source == "HUMAN").order_by(m.BankTransactionExplanation.id))
        return [dict(created_at=str(e.created_at), who_name=e.occurrence_name_snapshot, why_id=e.transaction_reason_id,
                     active=bool(txn and txn.explanation_id == e.id)) for e in rows]
    finally:
        db.close()


def history_key(description: str | None) -> str:
    """Bank's own precedent key (same description; Zelle/ACH references tolerated)."""
    return reconciliation_runner.history_key(description)


def clean(value) -> str:
    return flow.clean(value)


@dataclass
class Catalog:
    """Everything the engine needs from Bank, loaded once per run."""
    db: object
    instruments: dict = field(default_factory=dict)
    entities: dict = field(default_factory=dict)          # ReportingEntity id -> row
    whos: dict = field(default_factory=dict)              # id -> canonical name
    who_by_name: dict = field(default_factory=dict)       # clean name -> id
    whys: dict = field(default_factory=dict)              # id -> reason
    classes: dict = field(default_factory=dict)           # id -> accounting classification
    settlement: dict = field(default_factory=dict)        # card instrument id -> bank account id
    rules: list = field(default_factory=list)             # flow entries (rule, version, spec)

    @classmethod
    def load(cls, db) -> "Catalog":
        c = cls(db=db)
        c.instruments = {i.id: i for i in db.scalars(select(m.PaymentInstrument))}
        c.entities = {e.id: e for e in db.scalars(select(m.ReportingEntity))}
        for o in db.scalars(select(m.BankOccurrence)):
            if o.status == "ACTIVE":
                c.whos[o.id] = o.canonical_name
                c.who_by_name[clean(o.canonical_name)] = o.id
        c.whys = {r.id: r for r in db.scalars(select(m.BankTransactionReason)) if r.status == "ACTIVE"}
        c.classes = {a.id: a for a in db.scalars(select(m.BankAccountingClassification))}
        for s in db.scalars(select(m.BankCardSettlementAccount)):
            if s.valid_to is None:
                c.settlement[s.credit_card_payment_instrument_id] = s.settlement_bank_account_id
        for i in c.instruments.values():
            if i.instrument_type == "CREDIT_CARD" and i.id not in c.settlement and i.linked_instrument_id:
                c.settlement[i.id] = i.linked_instrument_id
        c.rules = flow.entries(db, future=True)
        return c

    @cached_property
    def row_builder(self):
        return ai_rules.RowBuilder(self.db)

    def owner(self, txn) -> "m.ReportingEntity | None":
        instrument = self.instruments.get(txn.payment_instrument_id)
        if instrument is None:
            return None
        return card_configuration.owner_entity_for(
            self.db, instrument=instrument, on_date=txn.posting_date or txn.transaction_date)

    def rule_row(self, txn):
        """The Bank rule row WITHOUT the current Bank decision: C-Bank decides
        independently of what Bank already assigned (dry-run comparison)."""
        return self.row_builder.row(txn, None)

    def entity_name(self, entity_id) -> str | None:
        e = self.entities.get(entity_id)
        return e.name if e else None

    def class_label(self, class_id) -> str | None:
        a = self.classes.get(class_id)
        return f"{a.code} {a.name}" if a else None


def current_bank_decision(db, txn) -> dict:
    """What operational Bank holds today for this movement (for comparison and
    for protecting human decisions)."""
    e = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
    allocs = list(db.scalars(select(m.BankTransactionAllocation).where(
        m.BankTransactionAllocation.financial_transaction_id == txn.id)))
    alloc = allocs[0] if len(allocs) == 1 else None
    category = None
    if e is not None:
        category = e.accounting_classification_id
        if category is None and e.transaction_reason_id:
            reason = db.get(m.BankTransactionReason, e.transaction_reason_id)
            category = reason.accounting_classification_id if reason else None
    return dict(
        who_id=e.occurrence_id if e else None,
        why_id=e.transaction_reason_id if e else None,
        category_id=category,
        beneficiary_id=alloc.reporting_entity_id if alloc else None,
        beneficiary_human=bool(alloc and alloc.decision_source == "HUMAN"),
        split=len(allocs) > 1,
        source=e.decision_source if e else None,
        status=e.decision_status if e else None,
        review_status=txn.review_status,
    )


def generate_json(prompt: str, *, web_research: bool = False) -> dict:
    """OpenAI through the ChatGPT/Codex login Bank already uses (decision 51:
    one centralized adapter; no other provider, no fallback)."""
    import bank_chatgpt
    return bank_chatgpt.generate_json(prompt, web_research=web_research)


AI_PROVIDER = "OPENAI_CHATGPT_CODEX"


def register_rule_whos(names):
    """Catalog-only write for names extracted by approved rules. No movement decision is written."""
    from sqlalchemy import text
    from rfone_data_store.bank_reconciliation import who_registration
    with _writer_session() as db:
        # Serialize the identity check and insert across processes too.
        db.execute(text("BEGIN IMMEDIATE"))
        result = who_registration.register_candidates(db, names)
        db.commit()
        return result


def ensure_source_classification_pairs(pairs):
    from sqlalchemy import text
    from rfone_data_store.bank_reconciliation import source_classification
    with _writer_session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        count = source_classification.ensure_pairs(db, pairs)
        db.commit()
        return count
