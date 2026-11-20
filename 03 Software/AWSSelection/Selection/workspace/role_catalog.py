"""Persistent Selection job roles; no implicit schema or account changes."""
from datetime import datetime, timezone
import unicodedata
from uuid import uuid4
from collections.abc import Mapping

from sqlalchemy import Boolean, DateTime, Integer, String, func, inspect, select, update
from sqlalchemy.orm import Mapped, mapped_column
from rfone_data_store.models import Base

class JobRole(Base):
    __tablename__ = 'selection_workspace_job_roles'
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now())


def clean_name(value):
    name = ' '.join((value or '').split())
    if not name or len(name) > 120 or any(unicodedata.category(c).startswith('C') for c in name):
        raise ValueError('Inserisci un nome da 1 a 120 caratteri, senza caratteri di controllo.')
    return name, unicodedata.normalize('NFKC', name).casefold()


def initialize(engine):
    """Explicit local additive setup, never run from app import or on AWS."""
    if engine.dialect.name != 'sqlite' and (engine.url.host, engine.url.port, engine.url.database) != ('127.0.0.1', 55436, 'rfone_aws_copy'):
        raise RuntimeError('Job-role initialization requires the canonical loopback database.')
    with engine.begin() as connection:
        if inspect(connection).has_table(JobRole.__tablename__):
            return
        JobRole.__table__.create(connection)


def choices(db, *, current=None):
    query = select(JobRole).where(JobRole.active.is_(True) | (JobRole.code == current))
    return [(r.code, r.name) for r in db.scalars(query.order_by(func.lower(JobRole.name), JobRole.code))]


def enabled(db, code):
    return bool(db.scalar(select(JobRole.active).where(JobRole.code == code)))


class RoleLabels(Mapping):
    """Request-local names, including inactive roles needed by historical Jobs."""
    def __init__(self, defaults, factory):
        self.defaults, self.factory = defaults, factory

    def values_for_request(self):
        from flask import g, has_request_context
        if not has_request_context():
            return self.defaults
        if 'selection_job_role_labels' not in g:
            with self.factory() as db:
                g.selection_job_role_labels = dict(self.defaults, **{r.code: r.name for r in db.scalars(select(JobRole))})
        return g.selection_job_role_labels

    def __getitem__(self, key):
        return self.values_for_request()[key]

    def __iter__(self):
        return iter(self.values_for_request())

    def __len__(self):
        return len(self.values_for_request())


def save(db, *, code=None, name, version=None):
    name, key = clean_name(name)
    duplicate = db.scalar(select(JobRole.code).where(JobRole.name_key == key, JobRole.code != (code or '')))
    if duplicate:
        raise ValueError('Esiste già una Posizione di Lavoro con questo nome.')
    if code is None:
        role = JobRole(code='ROLE_' + uuid4().hex, name=name, name_key=key, active=True, version=1)
        db.add(role)
        db.flush()
        return role
    try:
        version = int(version)
    except (TypeError, ValueError):
        raise ValueError('Riapri la Posizione di Lavoro prima di salvarla.') from None
    result = db.execute(update(JobRole).where(JobRole.code == code, JobRole.active.is_(True), JobRole.version == version).values(
        name=name, name_key=key, version=version + 1, updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        raise ValueError('La Posizione di Lavoro è stata modificata o rimossa dall’elenco. I dati inseriti sono conservati; chiudi e riapri per confrontarli.')
    db.flush()
    return db.get(JobRole, code, populate_existing=True)
