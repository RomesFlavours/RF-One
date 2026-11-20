"""Intermediaries (Product Owner, 2026-11-18).

PayPal, Amazon and similar are not WHO: they are the channel a payment passes through, while the WHO is the real
counterparty (the seller, the person). A catalog entry marked as intermediary keeps its name and aliases, but WHO
recognition (`who_search_text.WhoRecogniser`) uses them only to record the channel: an intermediary never competes
with a WHO, and a movement where only the intermediary is found has no WHO (it waits for that intermediary's
routine). Marking writes only `bank_who_intermediaries`; no movement, WHY or rule is changed.
"""
from __future__ import annotations

from sqlalchemy import inspect, select

from .. import models as m

TABLE = "bank_who_intermediaries"


def _has_table(db) -> bool:
    return inspect(db.connection()).has_table(TABLE)


def ids(db) -> set[int]:
    """Catalog ids marked as intermediary (empty on a database without the table)."""
    if not _has_table(db):
        return set()
    return set(db.scalars(select(m.BankWhoIntermediary.occurrence_id)))


def set_intermediary(db, who_id: int, on: bool, *, account_id: int | None) -> bool:
    """A person's choice. On: listed as intermediary, its WHY mode row removed (an intermediary has no WHY).
    Off: removed from the list (it is a WHO univoco again)."""
    who = db.get(m.BankOccurrence, who_id)
    if who is None:
        raise ValueError("WHO not found.")
    if not _has_table(db):
        raise ValueError("The database needs the table bank_who_intermediaries.")
    row = db.get(m.BankWhoIntermediary, who_id)
    if on:
        mode = db.get(m.BankWhoWhyMode, who_id)
        if mode is not None:
            db.delete(mode)
        if row is None:
            db.add(m.BankWhoIntermediary(occurrence_id=who_id, updated_by_account_id=account_id))
    elif row is not None:
        db.delete(row)
    db.flush()
    return on
