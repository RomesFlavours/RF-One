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
    ai_rules, card_configuration, flow, reconciliation_runner)


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
