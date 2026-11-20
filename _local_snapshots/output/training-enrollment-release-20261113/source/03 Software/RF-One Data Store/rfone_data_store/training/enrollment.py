"""Pending invitations over the existing RF-One person directory, never another registry."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, select, func
from .. import models as m, people_registry as people, student_registry as registry
from .. import rfone_account_service as accounts, rfone_web_session as shared
from ..selection import workspace_models as selection


class EnrollmentInvitation(m.Base):
    __tablename__ = 'training_enrollment_invitations'
    id = Column(Integer, primary_key=True)
    token_digest = Column(String(64), unique=True, nullable=False)
    email = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False, default='')
    phone = Column(String(64), nullable=False, default='')
    person_id = Column(Integer, ForeignKey('candidate_persons.id'))
    account_id = Column(Integer, ForeignKey('rfone_accounts.id'))
    selection_id = Column(Integer, ForeignKey('selection_workspace_position_candidates.id'))
    created_by_id = Column(Integer, ForeignKey('rfone_accounts.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    failed_attempts = Column(Integer, nullable=False, default=0)


def now():
    return datetime.now(timezone.utc)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def phone_key(phone):
    return re.sub(r'\D', '', phone or '')


def identity_matches(db, name, email, phone):
    found = {row['key']: row['name'] for row in registry.candidates(db, name, email, '')}
    key = phone_key(phone)
    if key:
        for person in db.scalars(select(m.CandidatePerson).where(m.CandidatePerson.primary_phone.is_not(None))):
            if phone_key(person.primary_phone) == key:
                found[f'person:{person.id}'] = person.full_name or 'Existing person'
    return [dict(key=k, name=v) for k, v in found.items()]


def selection_position_allowed(db, actor, position):
    if not shared.account_may_enter_domain(db, actor, 'SELECTION'):
        return False
    access = next(g for g in accounts.list_domain_access_for_account(db, actor.id) if g.domain_code == 'SELECTION')
    return (access.role_code or '').upper() != 'SUPERVISOR' and (shared.account_is_domain_admin(db, actor, 'SELECTION') or (access.role_code or '').upper() == 'OWNER' or position.manager_account_id == actor.id)


def confirmed_candidates(db, actor):
    if not shared.account_may_enter_domain(db, actor, 'SELECTION'):
        return []
    latest = select(selection.WorkspaceDecision.position_candidate_id, func.max(selection.WorkspaceDecision.id).label('id')).group_by(selection.WorkspaceDecision.position_candidate_id).subquery()
    rows = db.execute(select(selection.WorkspacePositionCandidate, selection.WorkspacePosition)
        .join(selection.WorkspacePosition, selection.WorkspacePosition.id == selection.WorkspacePositionCandidate.position_id)
        .join(latest, latest.c.position_candidate_id == selection.WorkspacePositionCandidate.id)
        .join(selection.WorkspaceDecision, selection.WorkspaceDecision.id == latest.c.id)
        .where(selection.WorkspaceDecision.decision == selection.D_HIRED)).all()
    result = []
    for pc, position in rows:
        if not selection_position_allowed(db, actor, position):
            continue
        application = db.get(m.Application, pc.application_id)
        person = db.get(m.CandidatePerson, application.person_id)
        candidate = db.get(m.Candidate, pc.candidate_id)
        result.append(dict(id=pc.id, person_id=person.id, name=candidate.full_name or pc.declared_name or person.full_name or '',
            email=candidate.email or pc.declared_email or person.primary_email or '',
            phone=candidate.phone or pc.declared_phone or person.primary_phone or '', position=position.title))
    return sorted(result, key=lambda r: r['name'].casefold())


def account_for(db, invitation):
    if invitation.account_id:
        return db.get(m.RFOneAccount, invitation.account_id)
    link = db.scalar(select(people.PersonAccountLink).where(people.PersonAccountLink.person_id == invitation.person_id)) if invitation.person_id else None
    return db.get(m.RFOneAccount, link.account_id) if link else None


def issue(db, *, actor, email, name='', phone='', selection_id=None, confirmation=None):
    email = accounts._validate_email_format(email)
    name, phone = name.strip(), phone.strip()
    if len(name) > 255 or len(phone) > 64 or (phone and len(phone_key(phone)) < 5):
        raise ValueError('Check the name and phone number (up to 64 characters).')
    people.lock_identity_evidence(db, email, name, phone_key(phone))
    person_id = account_id = None
    if selection_id:
        candidates = {r['id']: r for r in confirmed_candidates(db, actor)}
        source = candidates.get(selection_id)
        if not source:
            raise ValueError('Candidate not confirmed or position not authorized. Reload the list.')
        person_id = source['person_id']
        name = name or source['name']
        phone = phone or source['phone']
    else:
        matches = identity_matches(db, name, email, phone)
        if matches and confirmation not in {r['key'] for r in matches}:
            raise registry.ConfirmationRequired(matches)
        if confirmation:
            if confirmation not in {r['key'] for r in matches}:
                raise ValueError('The identity match changed. Review the details.')
            kind, key = confirmation.split(':')
            if kind == 'person': person_id = int(key)
            else: account_id = int(key)
    # Contact evidence cannot belong to a different known person/account.
    selected = EnrollmentInvitation(person_id=person_id, account_id=account_id)
    account = account_for(db, selected)
    owners = list(db.scalars(select(m.RFOneAccount).where(func.lower(m.RFOneAccount.email) == email)))
    persons = list(db.scalars(select(m.CandidatePerson).where(func.lower(m.CandidatePerson.primary_email) == email)))
    if any(not account or a.id != account.id for a in owners) or any(p.id != person_id for p in persons):
        raise ValueError('This contact belongs to another RF-One identity. Ask for a Registry review.')
    if account and (account.status != 'ACTIVE' or account.email != email):
        raise ValueError('Use the email of the existing active account. No credentials will be changed.')
    stamp = now()
    prior = list(db.scalars(select(EnrollmentInvitation).where(EnrollmentInvitation.email == email).with_for_update()))
    if any(r.created_at > stamp - timedelta(seconds=60) for r in prior) or sum(r.created_at > stamp - timedelta(hours=1) for r in prior) >= 5:
        raise ValueError('Wait at least one minute before creating another invitation (up to five per hour).')
    for row in prior:
        if not row.consumed_at and not row.revoked_at: row.revoked_at = stamp
    token = secrets.token_urlsafe(32)
    invitation = EnrollmentInvitation(token_digest=digest(token), email=email, name=name, phone=phone,
        person_id=person_id, account_id=account_id, selection_id=selection_id, created_by_id=actor.id,
        created_at=stamp, expires_at=stamp + timedelta(hours=48), failed_attempts=0)
    db.add(invitation); db.flush()
    return invitation, token


def lookup(db, token, *, lock=False):
    if not token or len(token) != 43 or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        return None
    query = select(EnrollmentInvitation).where(EnrollmentInvitation.token_digest == digest(token))
    row = db.scalar(query.with_for_update() if lock else query)
    if not row or row.consumed_at or row.revoked_at or row.expires_at <= now() or row.failed_attempts >= 5:
        return None
    return row


