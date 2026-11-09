"""Kitchen-owned state in the canonical RF-One database, not a second POS DB."""
from datetime import datetime, timezone

import bootstrap  # noqa: F401
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, select, update
from sqlalchemy.orm import Mapped, mapped_column
from rfone_data_store import models as m


def now():
    return datetime.now(timezone.utc)


class Board(m.Base):
    __tablename__ = 'kitchen_boards'
    location_id: Mapped[int] = mapped_column(ForeignKey('locations.id'), primary_key=True)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visible_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(Text)


class Ticket(m.Base):
    __tablename__ = 'kitchen_tickets'
    location_id: Mapped[int] = mapped_column(ForeignKey('kitchen_boards.location_id'), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    rfone_order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    released_by: Mapped[str | None] = mapped_column(String(255))


def initialize(engine, location_id, since):
    from display_settings import DisplaySettings
    # Explicit DDL; only Kitchen Board's additive tables, never Base.create_all.
    m.Base.metadata.create_all(engine, tables=[Board.__table__, Ticket.__table__, DisplaySettings.__table__])
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        if not session.get(m.Location, location_id):
            raise ValueError('Location does not exist')
        if not session.get(Board, location_id):
            session.add(Board(location_id=location_id, since=since, visible_count=5))
            session.commit()


def pending(session, location_id):
    return list(session.scalars(select(Ticket).where(
        Ticket.location_id == location_id, Ticket.released_at.is_(None)
    ).order_by(Ticket.created_at, Ticket.order_id)))


def save_ticket(session, *, location_id, order, payload, synced_at):
    key = (location_id, order.source_order_id)
    ticket = session.get(Ticket, key)
    if ticket is None:
        session.add(Ticket(location_id=location_id, order_id=order.source_order_id,
                           rfone_order_id=order.id, created_at=order.created_at,
                           payload=payload, synced_at=synced_at))
    else:
        # Conditional SQL also protects against a release in another web process.
        session.execute(update(Ticket).where(
            Ticket.location_id == location_id, Ticket.order_id == order.source_order_id,
            Ticket.released_at.is_(None)
        ).values(payload=payload, synced_at=synced_at).execution_options(synchronize_session=False))


def release(session, location_id, order_id, actor):
    changed = session.execute(update(Ticket).where(
        Ticket.location_id == location_id, Ticket.order_id == order_id,
        Ticket.released_at.is_(None)
    ).values(released_at=now(), released_by=actor)).rowcount
    if session.get(Ticket, (location_id, order_id)) is None:
        raise LookupError('Order not found')
    session.commit()
    return {'order_id': order_id, 'released': True, 'already_released': not bool(changed)}
