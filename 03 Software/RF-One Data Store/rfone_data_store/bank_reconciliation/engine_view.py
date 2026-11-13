"""Read current single-engine values in Review without writing movement decisions.

Use the actual reconciliation Engine, including matching and human protections;
never reconstruct purpose from legacy saved RULE explanations or a second policy.
"""
import os
from pathlib import Path
import sys

from sqlalchemy import event
from sqlalchemy.orm import Session
from . import single_engine

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
                    Path(__file__).resolve().parents[4].parent / 'rf-one-c-bank-prototype' /
                    '03 Software' / 'C-Bank Prototype')
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from cbank.engine import Engine
        session.info[_CACHE] = (Engine(session, None), {})
    engine, cached = session.info[_CACHE]
    for txn in transactions:
        if txn.id in engine.by_id and txn.id not in cached:
            cached[txn.id] = engine.evaluate(engine.by_id[txn.id])
    return {t.id: cached[t.id] for t in transactions if t.id in cached}
