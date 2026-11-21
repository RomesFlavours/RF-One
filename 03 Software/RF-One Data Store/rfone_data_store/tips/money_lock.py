"""One serialization point for every Tips step that creates or moves money for a restaurant
(CLOVER_MULTISITE_001, Product Owner 2026-11-21): saving/finalizing a period, preparing a Payment
Cycle, approving it and retrying a payment.

`lock_restaurant` takes a PostgreSQL row lock on the restaurant (`SELECT ... FOR UPDATE`) for the rest
of the current transaction. A second process — the scheduler and a person, or two people — doing any of
these steps for the SAME restaurant waits until the first transaction ends, then re-reads the state the
first one left (a cycle already open, entitlements already aggregated, a period already final) and acts
on that. Different restaurants never wait for each other. On SQLite (local tests) the statement is
accepted and the database already serializes writers.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def lock_restaurant(session: Session, restaurant_id: int) -> None:
    """Serializes the money-related Tips steps of one restaurant until the transaction ends."""
    session.flush()
    session.execute(select(m.Restaurant.id).where(m.Restaurant.id == restaurant_id).with_for_update())
