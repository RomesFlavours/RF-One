"""Read-only WHO proposals for Review, using the reconciliation recogniser.

A proposal answers only the WHO question. It never writes a movement decision
or supplies WHY/WHAT, and an existing decision always keeps its WHO.
"""
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from .. import models as m
from . import who_search_text, who_recognition

_CACHE = "bank_review_who_proposals"

@event.listens_for(Session, "after_flush")
@event.listens_for(Session, "after_transaction_end")
def _invalidate(session, *_args):
    session.info.pop(_CACHE, None)


def proposals(session):
    if _CACHE in session.info:
        return session.info[_CACHE]
    recogniser = who_search_text.WhoRecogniser(session)
    ids = {who_recognition.who_key(name): oid for oid, name in recogniser.names.items()}
    query = (select(m.FinancialTransaction)
        .outerjoin(m.BankTransactionExplanation,
                   m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
        .where(m.BankTransactionExplanation.occurrence_id.is_(None),
               m.FinancialTransaction.accounting_status == "CANONICAL",
               m.FinancialTransaction.duplicate_status.is_distinct_from("CONFIRMED_DUPLICATE")))
    found = {}
    for txn in session.scalars(query):
        result = recogniser.recognise(txn)
        if result.outcome == who_search_text.FOUND and result.who:
            found[txn.id] = {"who": result.who,
                             "who_id": ids.get(who_recognition.who_key(result.who)),
                             "who_source": "auto"}
    session.info[_CACHE] = found
    return found
