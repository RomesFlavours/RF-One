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


# Keys the sync never receives from Clover; they survive every payload refresh.
KEPT_KEYS = ('changes', 'release_history', 'addition_to', 'addition')
UNDO_MINUTES = 15


def _line_view(line):
    return (line.get('name'), line.get('quantity'), line.get('note'), tuple(line.get('modifiers') or ()))


def _track_changes(old, new):
    """Remember what changed on an open ticket after the kitchen first saw it."""
    previous = old.get('changes') or {}
    old_lines = {l.get('id'): l for l in old.get('lines', []) if l.get('id')}
    new_lines = {l.get('id'): l for l in new.get('lines', []) if l.get('id')}
    added = [i for i in new_lines if i not in old_lines]
    edited = [i for i in new_lines if i in old_lines and _line_view(new_lines[i]) != _line_view(old_lines[i])]
    gone = [{'id': i, 'name': l.get('name') or '', 'quantity': l.get('quantity')}
            for i, l in old_lines.items() if i not in new_lines]
    if not (added or edited or gone):
        return previous or None
    keep = lambda ids: [i for i in ids if i in new_lines]
    removed = [r for r in previous.get('removed', []) if r['id'] not in new_lines]
    removed += [r for r in gone if r['id'] not in {x['id'] for x in removed}]
    return {
        'new': keep(list(dict.fromkeys(previous.get('new', []) + added))),
        'changed': [i for i in dict.fromkeys(previous.get('changed', []) + edited)
                    if i in new_lines and i not in added and i not in previous.get('new', [])],
        'removed': removed,
        'at': now().isoformat(),
    }


def additions(session, location_id, order_id):
    return list(session.scalars(select(Ticket).where(
        Ticket.location_id == location_id, Ticket.order_id.like(order_id + '-add%')
    ).order_by(Ticket.created_at)))


def save_ticket(session, *, location_id, order, payload, synced_at):
    key = (location_id, order.source_order_id)
    ticket = session.get(Ticket, key)
    if ticket is None:
        session.add(Ticket(location_id=location_id, order_id=order.source_order_id,
                           rfone_order_id=order.id, created_at=order.created_at,
                           payload=payload, synced_at=synced_at))
        return
    if ticket.released_at is not None:
        _save_addition(session, location_id, order, ticket, payload, synced_at)
        return
    merged = {**payload, **{k: ticket.payload[k] for k in KEPT_KEYS if k in ticket.payload}}
    changes = _track_changes(ticket.payload, payload)
    if changes:
        merged['changes'] = changes
    # Conditional SQL also protects against a release in another web process.
    session.execute(update(Ticket).where(
        Ticket.location_id == location_id, Ticket.order_id == order.source_order_id,
        Ticket.released_at.is_(None)
    ).values(payload=merged, synced_at=synced_at).execution_options(synchronize_session=False))


def _save_addition(session, location_id, order, ticket, payload, synced_at):
    """Lines added in Clover after a release become their own ticket, never lost."""
    extra = additions(session, location_id, ticket.order_id)
    sent = {l.get('id') for t in [ticket] + [t for t in extra if t.released_at] for l in t.payload.get('lines', [])}
    lines = [l for l in payload.get('lines', []) if l.get('id') not in sent]
    open_extra = next((t for t in extra if t.released_at is None), None)
    if open_extra is not None:
        body = {**payload, 'lines': lines, **{k: open_extra.payload[k] for k in KEPT_KEYS if k in open_extra.payload}}
        session.execute(update(Ticket).where(
            Ticket.location_id == location_id, Ticket.order_id == open_extra.order_id,
            Ticket.released_at.is_(None)
        ).values(payload=body, synced_at=synced_at).execution_options(synchronize_session=False))
    elif lines:
        number = len(extra) + 1
        session.add(Ticket(location_id=location_id, order_id=f'{ticket.order_id}-add{number}',
                           rfone_order_id=order.id, created_at=synced_at,
                           payload={**payload, 'lines': lines, 'addition_to': ticket.order_id,
                                    'addition': number}, synced_at=synced_at))


def release(session, location_id, order_id, actor):
    changed = session.execute(update(Ticket).where(
        Ticket.location_id == location_id, Ticket.order_id == order_id,
        Ticket.released_at.is_(None)
    ).values(released_at=now(), released_by=actor)).rowcount
    if session.get(Ticket, (location_id, order_id)) is None:
        raise LookupError('Order not found')
    session.commit()
    return {'order_id': order_id, 'released': True, 'already_released': not bool(changed)}


def undo_release(session, location_id, order_id, actor):
    """Bring a ticket back to the board shortly after a mistaken release."""
    ticket = session.get(Ticket, (location_id, order_id))
    if ticket is None:
        raise LookupError('Order not found')
    if ticket.released_at is None:
        return {'order_id': order_id, 'released': False, 'already_open': True}
    released = ticket.released_at if ticket.released_at.tzinfo else ticket.released_at.replace(tzinfo=timezone.utc)
    if (now() - released).total_seconds() > UNDO_MINUTES * 60:
        raise PermissionError('Too late to undo')
    if any(t.created_at and (t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)) >= released
           for t in additions(session, location_id, order_id)):
        # Lines added after this release already sit on their own ticket.
        raise PermissionError('An addition ticket already exists')
    history = list(ticket.payload.get('release_history', []))
    history.append({'released_at': released.isoformat(), 'released_by': ticket.released_by,
                    'undone_at': now().isoformat(), 'undone_by': actor})
    changed = session.execute(update(Ticket).where(
        Ticket.location_id == location_id, Ticket.order_id == order_id,
        Ticket.released_at == ticket.released_at
    ).values(released_at=None, released_by=None,
             payload={**ticket.payload, 'release_history': history})).rowcount
    session.commit()
    return {'order_id': order_id, 'released': False, 'already_open': not bool(changed)}
