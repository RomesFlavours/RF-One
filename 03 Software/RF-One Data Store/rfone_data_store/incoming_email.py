"""Phase 1 incoming email: owned mailbox configuration and header-only arrivals.

Callers own commit/rollback. No passwords, bodies or attachments in these tables.
"""
from __future__ import annotations

from email.utils import parseaddr
import re
import uuid

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String,
                        UniqueConstraint, CheckConstraint, select, update)
from .models import Base
from .email_service import now

RECEIVER_STATE_ID = 2
LEASE_SECONDS = 300
ERRORS = {
    'AUTHENTICATION_FAILED': 'Sign-in failed. Check the username and mailbox or app password.',
    'CONNECTION_FAILED': 'The mail server could not be reached. Another check will be scheduled.',
    'TLS_FAILED': 'The server certificate could not be verified.',
    'FOLDER_UNAVAILABLE': 'The selected folder could not be opened.',
    'IMAP_FAILED': 'The server could not complete the check.',
    'CREDENTIALS_UNAVAILABLE': 'The saved credentials are unavailable to this Windows user.',
    'UNSAFE_SERVER': 'Use a public IMAP server with a valid TLS certificate.',
    'CHECK_INTERRUPTED': 'The previous check was interrupted. It will be repeated safely.',
    'OWNER_INACTIVE': 'Monitoring stopped because the owning RF-One identity is no longer active.',
    'UIDVALIDITY_CHANGED': 'The mailbox was reset. Monitoring restarted from the latest message.',
}


class Mailbox(Base):
    __tablename__ = 'email_mailboxes'
    __table_args__ = (UniqueConstraint('owner_account_id', 'host', 'username', 'folder'),
                      CheckConstraint('interval_seconds >= 60 AND interval_seconds <= 3600'))
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_account_id = Column(Integer, ForeignKey('rfone_accounts.id'), nullable=False, index=True)
    label = Column(String(120), nullable=False)
    address = Column(String(254), nullable=False)
    host = Column(String(253), nullable=False)
    username = Column(String(254), nullable=False)
    folder = Column(String(120), nullable=False, default='INBOX')
    credential_ref = Column(String(80), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    interval_seconds = Column(Integer, nullable=False, default=60)
    config_version = Column(Integer, nullable=False, default=1)
    generation = Column(Integer, nullable=False, default=1)
    uidvalidity = Column(String(20))
    last_uid = Column(BigInteger, nullable=False, default=0)
    next_check_at = Column(DateTime(timezone=True), nullable=False, default=now, index=True)
    last_checked_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    failures = Column(Integer, nullable=False, default=0)
    last_error = Column(String(40))
    lease_owner = Column(String(36))
    lease_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class Arrival(Base):
    __tablename__ = 'email_arrivals'
    __table_args__ = (UniqueConstraint('mailbox_id', 'generation', 'uidvalidity', 'uid'),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mailbox_id = Column(String(36), ForeignKey('email_mailboxes.id'), nullable=False, index=True)
    uidvalidity = Column(String(20), nullable=False)
    generation = Column(Integer, nullable=False)
    uid = Column(BigInteger, nullable=False)
    sender = Column(String(1000), nullable=False)
    recipient = Column(String(1000), nullable=False)
    subject = Column(String(1000), nullable=False)
    message_id = Column(String(1000))
    message_date = Column(DateTime(timezone=True))
    size_bytes = Column(BigInteger)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=now, index=True)


class MailboxCheck(Base):
    __tablename__ = 'email_mailbox_checks'
    id = Column(Integer, primary_key=True)
    mailbox_id = Column(String(36), ForeignKey('email_mailboxes.id'), nullable=False, index=True)
    lease_owner = Column(String(36), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=now)
    finished_at = Column(DateTime(timezone=True))
    outcome = Column(String(24), nullable=False, default='CHECKING')
    found = Column(Integer, nullable=False, default=0)
    error = Column(String(40))


class MailboxAudit(Base):
    __tablename__ = 'email_mailbox_audit'
    id = Column(Integer, primary_key=True)
    mailbox_id = Column(String(36), ForeignKey('email_mailboxes.id'), nullable=False, index=True)
    actor_account_id = Column(Integer, ForeignKey('rfone_accounts.id'), nullable=False)
    action = Column(String(24), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


TABLES = [Mailbox.__table__, Arrival.__table__, MailboxCheck.__table__, MailboxAudit.__table__]


def configuration(*, label, address, host, username, folder='INBOX', interval_seconds=60):
    fields = dict(label=label, address=address, host=host, username=username, folder=folder)
    limits = dict(label=120, address=254, host=253, username=254, folder=120)
    for key, value in fields.items():
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limits[key] or any(ord(c) < 32 for c in value):
            raise ValueError('Enter valid mailbox settings.')
        fields[key] = value.strip()
    if parseaddr(fields['address'])[1] != fields['address'] or fields['address'].count('@') != 1:
        raise ValueError('Enter one valid mailbox email address.')
    try:
        fields['host'] = fields['host'].rstrip('.').encode('idna').decode('ascii').lower()
        interval_seconds = int(interval_seconds)
    except (ValueError, UnicodeError):
        raise ValueError('Enter a valid server and checking interval.') from None
    if not re.fullmatch(r'(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', fields['host']) or '..' in fields['host']:
        raise ValueError('Enter the IMAP hostname without a URL, path or port.')
    if not fields['folder'].isascii():
        raise ValueError('Use an ASCII IMAP folder name, for example INBOX.')
    if fields['folder'].upper() == 'INBOX':
        fields['folder'] = 'INBOX'
    if not 60 <= interval_seconds <= 3600:
        raise ValueError('Choose a checking interval from 60 to 3600 seconds.')
    fields['interval_seconds'] = interval_seconds
    return fields


def owned(db, owner, mailbox_id):
    return db.scalar(select(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.owner_account_id == owner))


def configure(db, *, owner, credential_ref=None, mailbox_id=None, **values):
    fields = configuration(**values)
    if mailbox_id is None:
        if not credential_ref:
            raise ValueError('Enter the mailbox password or app password.')
        row = Mailbox(owner_account_id=owner, credential_ref=credential_ref, **fields)
        db.add(row)
        action = 'CREATE'
    else:
        row = owned(db, owner, mailbox_id)
        if row is None:
            raise LookupError('Mailbox not found.')
        if any(getattr(row, key) != fields[key] for key in ('host', 'username')) and not credential_ref:
            raise ValueError('Re-enter the password when changing the IMAP server or sign-in username.')
        # Configuration changes must not race an outstanding network check.
        available = db.execute(update(Mailbox).where(Mailbox.id == mailbox_id,
            Mailbox.owner_account_id == owner,
            (Mailbox.lease_until.is_(None)) | (Mailbox.lease_until <= now())).values(
                config_version=Mailbox.config_version + 1)).rowcount
        if not available:
            raise ValueError('A check is running. Try again when it finishes.')
        reset = any(getattr(row, key) != fields[key] for key in ('host', 'username', 'folder'))
        for key, value in fields.items():
            setattr(row, key, value)
        if reset:
            row.uidvalidity, row.last_uid = None, 0
            row.generation += 1
        if credential_ref:
            row.credential_ref = credential_ref
        row.next_check_at, row.last_error, row.failures = now(), None, 0
        action = 'UPDATE'
    db.flush()
    db.add(MailboxAudit(mailbox_id=row.id, actor_account_id=owner, action=action))
    return row


def control(db, *, owner, mailbox_id, action):
    row = owned(db, owner, mailbox_id)
    if row is None:
        raise LookupError('Mailbox not found.')
    if action not in ('pause', 'resume', 'check'):
        raise ValueError('Unknown mailbox operation.')
    if action == 'check' and not row.enabled:
        raise ValueError('Resume monitoring before requesting a check.')
    changes = dict(next_check_at=now())
    if action != 'check':
        changes.update(enabled=action == 'resume', config_version=Mailbox.config_version + 1,
                       lease_owner=None, lease_until=None)
    db.execute(update(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.owner_account_id == owner).values(**changes))
    if action != 'check':
        db.execute(update(MailboxCheck).where(MailboxCheck.mailbox_id == mailbox_id,
            MailboxCheck.outcome == 'CHECKING').values(outcome='SUPERSEDED', finished_at=now()))
    db.add(MailboxAudit(mailbox_id=mailbox_id, actor_account_id=owner, action=action.upper()))


def arrivals(db, owner, *, mailbox_id=None, search='', offset=0):
    query = select(Arrival, Mailbox.label, Mailbox.address).join(Mailbox, Arrival.mailbox_id == Mailbox.id).where(
        Mailbox.owner_account_id == owner)
    if mailbox_id:
        query = query.where(Mailbox.id == mailbox_id)
    if search:
        query = query.where(Arrival.subject.contains(search, autoescape=True) |
                            Arrival.sender.contains(search, autoescape=True))
    return query.order_by(Arrival.detected_at.desc(), Arrival.id).limit(50).offset(offset)
