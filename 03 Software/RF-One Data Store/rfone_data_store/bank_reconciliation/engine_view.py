"""Read current single-engine values in Review without writing movement decisions.

Use the actual reconciliation Engine, including matching and human protections;
never reconstruct purpose from legacy saved RULE explanations or a second policy.
"""
import json
import os
from pathlib import Path
import sys

from sqlalchemy import event
from sqlalchemy.orm import Session
from . import single_engine

TOAST_EVIDENCE = 'ENGINE_TOAST_RESTAURANT'


def toast_evidence(db):
    from .. import models as m
    from sqlalchemy import select
    records = db.scalars(select(m.BankFlowArtifact.payload).where(
        m.BankFlowArtifact.kind == TOAST_EVIDENCE).order_by(m.BankFlowArtifact.id))
    return {item["txn_id"]: item for item in map(json.loads, records)}


_CACHE = 'bank_review_single_engine'


@event.listens_for(Session, 'after_flush')
@event.listens_for(Session, 'after_transaction_end')
def _invalidate(session, *_args):
    session.info.pop(_CACHE, None)


def values(session, transactions):
    if not transactions or not single_engine.enabled():
        return {}
    if _CACHE not in session.info:
        root = Path(os.environ.get('RFONE_BANK_CBANK_ROOT') or
                    Path(__file__).resolve().parents[3] / 'C-Bank Prototype')   # BANK-2026-11-04: local copy
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from cbank.engine import Engine
        session.info[_CACHE] = (Engine(session, None), {})
    engine, cached = session.info[_CACHE]
    for txn in transactions:
        if txn.id in engine.by_id and txn.id not in cached:
            cached[txn.id] = engine.evaluate(engine.by_id[txn.id])
    return {t.id: cached[t.id] for t in transactions if t.id in cached}
