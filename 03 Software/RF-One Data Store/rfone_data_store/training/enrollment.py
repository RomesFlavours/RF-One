"""Pending invitations over the existing RF-One person directory, never another registry.

Approved sequence (Product Owner, 2026-11-21 — OQ-7 completion):

1. Selection releases an eligible (Hired) candidate to Training: `release` records who released it and
   the Training operator now in charge (event `training.released`). Nothing else: no Student, no
   invitation, no Clover record.
2. The Training operator confirms the candidate has arrived: `confirm_arrival` records it once (event
   `training.arrival_confirmed`) and only then registers the existing person in the Registry as a
   Student (the STUDENT qualification). Training then enrolls the candidate in the school with the
   existing invitation (`issue`), whose activation creates or reuses the RF-One login and Training
   student account. A repeated confirmation changes nothing and never issues a second live invitation.
3. Creating the person in Clover and saving the returned employee ID is NOT done here: it waits for the
   Product Owner decisions on the site and on the identity record (see the OQ-7 report).
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, select, func
from .. import models as m, people_registry as people, student_registry as registry, access_profiles as profiles
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


RELEASED = 'training.released'
ARRIVED = 'training.arrival_confirmed'


def _selection_events(db, action, selection_ids=None):
    """{selection_id: latest event} for one Training hand-off action (rfone_access_profile_events)."""
    out = {}
    for row in db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == action)
                          .order_by(profiles.ProfileEvent.id)):
        sid = (row.details or {}).get('selection_id')
        if sid is not None and (selection_ids is None or sid in selection_ids):
            out[sid] = row
    return out


def _hired(db):
    latest = select(selection.WorkspaceDecision.position_candidate_id, func.max(selection.WorkspaceDecision.id).label('id')).group_by(selection.WorkspaceDecision.position_candidate_id).subquery()
    return db.execute(select(selection.WorkspacePositionCandidate, selection.WorkspacePosition)
        .join(selection.WorkspacePosition, selection.WorkspacePosition.id == selection.WorkspacePositionCandidate.position_id)
        .join(latest, latest.c.position_candidate_id == selection.WorkspacePositionCandidate.id)
        .join(selection.WorkspaceDecision, selection.WorkspaceDecision.id == latest.c.id)
        .where(selection.WorkspaceDecision.decision == selection.D_HIRED)).all()


def confirmed_candidates(db, actor):
    """Hired candidates the actor may handle: Selection rights on the position (as before), or the Training
    operator the candidate was released to. Each row says whether it was released and whether the arrival
    was confirmed."""
    rows = _hired(db)
    ids = [pc.id for pc, _ in rows]
    released = _selection_events(db, RELEASED, set(ids))
    arrived = _selection_events(db, ARRIVED, set(ids))
    may_select = shared.account_may_enter_domain(db, actor, 'SELECTION')
    result = []
    for pc, position in rows:
        release = released.get(pc.id)
        operator_id = (release.details or {}).get('operator_account_id') if release else None
        if not ((may_select and selection_position_allowed(db, actor, position)) or (operator_id and operator_id == actor.id)):
            continue
        application = db.get(m.Application, pc.application_id)
        person = db.get(m.CandidatePerson, application.person_id)
        candidate = db.get(m.Candidate, pc.candidate_id)
        result.append(dict(id=pc.id, person_id=person.id, name=candidate.full_name or pc.declared_name or person.full_name or '',
            email=candidate.email or pc.declared_email or person.primary_email or '',
            phone=candidate.phone or pc.declared_phone or person.primary_phone or '', position=position.title,
            released=release is not None, operator_account_id=operator_id, arrived=pc.id in arrived))
    return sorted(result, key=lambda r: r['name'].casefold())


def _lock_candidate(db, selection_id):
    return db.scalar(select(selection.WorkspacePositionCandidate)
                     .where(selection.WorkspacePositionCandidate.id == selection_id).with_for_update())


def release(db, *, selection_id, released_by, operator):
    """Step 1: Selection hands the Hired candidate to Training; `operator` (a Training trainer) is now in
    charge. Records only the hand-off. Returns 'released' or 'already'."""
    if _lock_candidate(db, selection_id) is None:
        raise ValueError('Candidate not found.')
    if selection_id not in {pc.id for pc, _ in _hired(db)}:
        raise ValueError('Not currently Hired in Selection.')
    if _selection_events(db, RELEASED, {selection_id}):
        return 'already'
    pc = db.get(selection.WorkspacePositionCandidate, selection_id)
    person_id = db.get(m.Application, pc.application_id).person_id
    profiles.event(db, RELEASED, actor=released_by.id, selection_id=selection_id, person_id=person_id,
                   operator_account_id=operator.id, at=now().isoformat())
    db.flush()
    return 'released'


def confirm_arrival(db, *, actor, selection_id):
    """Step 2: the Training operator confirms the candidate arrived. Only this authorizes the enrollment:
    the existing person becomes a Student in the Registry. Idempotent: (person_id, True) the first time,
    (person_id, False) when it was already confirmed."""
    source = _arrival_source(db, actor=actor, selection_id=selection_id)
    if source['arrived']:
        return source['person_id'], False
    mark_trainee(db, source['person_id'])
    profiles.event(db, ARRIVED, actor=actor.id, selection_id=selection_id, person_id=source['person_id'],
                   at=now().isoformat())
    db.flush()
    return source['person_id'], True


def _arrival_source(db, *, actor, selection_id):
    """The checks of step 2 (read-only): the candidate exists, is Hired, was released to Training and the
    actor is the operator in charge. Returns the candidate row of `confirmed_candidates`."""
    if _lock_candidate(db, selection_id) is None:
        raise ValueError('Candidate not found.')
    source = {r['id']: r for r in confirmed_candidates(db, actor)}.get(selection_id)
    if not source:
        raise ValueError('Candidate not confirmed or position not authorized. Reload the list.')
    # Codex review 2026-11-22 §3 — step 1 is mandatory for every caller: Selection must have released the
    # candidate (event `training.released`) and the actor must be the Training operator put in charge by
    # that release. Selection rights on the position alone never confirm an arrival. Checked before any
    # Registry mark, event or invitation.
    if not source['released'] or not source['operator_account_id']:
        raise ValueError('Selection has not released this candidate to Training yet: the arrival cannot be '
                         'confirmed. Nothing was changed.')
    if source['operator_account_id'] != actor.id:
        raise ValueError('This candidate was released to another Training operator, who confirms the arrival. '
                         'Nothing was changed.')
    return source


def live_invitation(db, selection_id):
    """True when this Selection candidate already has a pending (unexpired) or completed invitation."""
    stamp = now()

    def aware(value):
        return value if value.tzinfo else value.replace(tzinfo=stamp.tzinfo)
    return any(r.consumed_at or (not r.revoked_at and aware(r.expires_at) > stamp) for r in db.scalars(
        select(EnrollmentInvitation).where(EnrollmentInvitation.selection_id == selection_id)))


def mark_trainee(db, person_id):
    """The person is a Student (Trainee) in the one Registry from now, before activation: after the arrival
    confirmation (Selection path) or with the direct invitation. The mark is the existing STUDENT
    qualification, never added to an employee (an Employee keeps the status)."""
    if person_id and 'EMPLOYEE' not in people.company_statuses(db, person_id)             and not db.get(registry.PersonQualification, (person_id, 'STUDENT')):
        db.add(registry.PersonQualification(person_id=person_id, code='STUDENT'))
        db.flush()


def account_for(db, invitation):
    if invitation.account_id:
        return db.get(m.RFOneAccount, invitation.account_id)
    link = db.scalar(select(people.PersonAccountLink).where(people.PersonAccountLink.person_id == invitation.person_id)) if invitation.person_id else None
    return db.get(m.RFOneAccount, link.account_id) if link else None


# Job boards hand out forwarding addresses instead of the applicant's own email.
# They may never deliver a Training invitation, so an invitation needs the real one.
FORWARDING_EMAIL_DOMAINS = ('indeedemail.com',)
FORWARDING_EMAIL_MESSAGE = "This is an Indeed forwarding address. Ask for their real email."


def is_forwarding_email(email):
    domain = (email or '').strip().lower().rpartition('@')[2]
    return any(domain == d or domain.endswith('.' + d) for d in FORWARDING_EMAIL_DOMAINS)


def training_sites(db, actor):
    """Sites the Training operator may enter a person at (central per-site authorization)."""
    from .. import site_selection, employee_directory as directory
    allowed = site_selection.account_restaurant_ids(db, actor, 'TRAINING')
    return [site for site in directory.sites(db) if site.id in allowed]


def _check_site(db, actor, restaurant_id, role_id, area_id):
    from .. import employee_directory as directory
    if restaurant_id is None or restaurant_id not in {site.id for site in training_sites(db, actor)}:
        raise ValueError('Choose the training site (a site you may work on).')
    if (role_id, area_id) not in {(r.id, a.id) for r, a in directory.site_role_choices(db, restaurant_id)}:
        raise ValueError('Choose the role the person trains for at this site.')


def _ensure_person(db, actor, *, person_id, account_id, name, email, phone):
    """REGISTRY_MULTISITE_001: the Training entry creates or reuses the Registry card at once, so the physical
    person must exist now: reuse the selected person (or the person of the selected account), otherwise
    create it from the invitation details. Returns the person id."""
    if person_id:
        return person_id
    if account_id:
        linked = people.person_for_account(db, account_id)
        if linked is not None:
            return linked.id
    person = people.create_identity(db, full_name=name or email, email=email, phone=phone or None,
                                    normalized_name=' '.join((name or email).casefold().split()),
                                    normalized_phone=phone_key(phone) or None)
    if account_id:
        db.add(people.PersonAccountLink(account_id=account_id, person_id=person.id, linked_by_id=actor.id,
                                        linked_at=now()))
        db.flush()
    return person.id


def resolve_trainee_card(db, *, actor, person_id, restaurant_id, role_id, area_id, card_confirmation=None):
    """REGISTRY_MULTISITE_001 (Codex review 3): a legacy Trainee without a Registry card gets the card and the
    training site through the same authorized Training entry rules (operator's sites, identity resolved
    first, confirmation when uncertain), without a new invitation. Returns (card, created)."""
    from .. import employee_directory as directory
    person = db.get(m.CandidatePerson, person_id)
    if person is None:
        raise ValueError('Person not found.')
    if not db.get(registry.PersonQualification, (person_id, 'STUDENT')) and             'EMPLOYEE' not in people.company_statuses(db, person_id):
        raise ValueError('This person is not a Trainee in the Registry.')
    _check_site(db, actor, restaurant_id, role_id, area_id)
    card_id = directory.resolve_training_card(db, person_id=person_id, email=person.primary_email,
                                              phone=person.primary_phone, confirmation=card_confirmation)
    return directory.training_card(db, person_id=person_id, restaurant_id=restaurant_id, role_id=role_id,
                                   area_id=area_id, actor=actor, card_id=card_id)


def issue(db, *, actor, email, name='', phone='', selection_id=None, confirmation=None,
          restaurant_id=None, role_id=None, area_id=None, card_confirmation=None):
    email = accounts._validate_email_format(email)
    if is_forwarding_email(email):
        raise ValueError(FORWARDING_EMAIL_MESSAGE)
    name, phone = name.strip(), phone.strip()
    if len(name) > 255 or len(phone) > 64 or (phone and len(phone_key(phone)) < 5):
        raise ValueError('Check the name and phone number (up to 64 characters).')
    people.lock_identity_evidence(db, email, name, phone_key(phone))
    person_id = account_id = None
    if selection_id:
        # The invitation from Selection is the enrollment: it follows the arrival confirmation, and a
        # candidate already enrolled (pending or completed invitation) is never enrolled twice.
        # Checks only (no write yet): the arrival is recorded after the Registry identity is resolved.
        source = _arrival_source(db, actor=actor, selection_id=selection_id)
        person_id = source['person_id']
        if live_invitation(db, selection_id):
            raise ValueError('Arrival already confirmed and the enrollment is already in progress for this candidate.')
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
    # REGISTRY_MULTISITE_001 (Codex review 2): site and Registry identity are settled before anything is
    # written — arrival, Trainee mark, person, card or invitation. An uncertain identity raises
    # CardConfirmationRequired and nothing is saved.
    from .. import employee_directory as directory
    _check_site(db, actor, restaurant_id, role_id, area_id)
    known_person = person_id or (people.person_for_account(db, account_id).id
                                 if account_id and people.person_for_account(db, account_id) else None)
    card_id = directory.resolve_training_card(db, person_id=known_person, email=email, phone=phone,
                                              confirmation=card_confirmation)
    if selection_id:
        confirm_arrival(db, actor=actor, selection_id=selection_id)
    stamp = now()
    prior = list(db.scalars(select(EnrollmentInvitation).where(EnrollmentInvitation.email == email).with_for_update()))
    if any(r.created_at > stamp - timedelta(seconds=60) for r in prior) or sum(r.created_at > stamp - timedelta(hours=1) for r in prior) >= 5:
        raise ValueError('Wait at least one minute before creating another invitation (up to five per hour).')
    for row in prior:
        if not row.consumed_at and not row.revoked_at: row.revoked_at = stamp
    # REGISTRY_MULTISITE_001: create or reuse the Registry card for the training site; a new entry is a
    # Trainee, an Employee keeps the status. Repeating it reuses the same identity and card.
    person_id = _ensure_person(db, actor, person_id=person_id, account_id=account_id, name=name, email=email,
                               phone=phone)
    mark_trainee(db, person_id)
    directory.training_card(db, person_id=person_id, restaurant_id=restaurant_id, role_id=role_id,
                            area_id=area_id, actor=actor, card_id=card_id)
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


