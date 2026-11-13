"""Student qualification and explicit links over the one CandidatePerson registry."""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, select, func, or_, inspect
from . import models as m, people_registry as people


class PersonQualification(m.Base):
    __tablename__ = 'person_qualifications'
    person_id = Column(Integer, ForeignKey('candidate_persons.id'), primary_key=True)
    code = Column(String(32), primary_key=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TrainingPersonLink(m.Base):
    __tablename__ = 'training_person_links'
    training_account_id = Column(Integer, ForeignKey('training_accounts.id'), primary_key=True)
    person_id = Column(Integer, ForeignKey('candidate_persons.id'), nullable=False, unique=True)


class ConfirmationRequired(ValueError):
    def __init__(self, candidates):
        super().__init__('Esiste una possibile corrispondenza. Conferma la persona prima di salvare.')
        self.candidates = candidates


def candidates(db, name, email, username):
    """Candidates are evidence for human review, never automatic identity matches."""
    normalized = ' '.join(name.casefold().split())
    persons = list(db.scalars(select(m.CandidatePerson).where(or_(
        func.lower(m.CandidatePerson.primary_email) == email.strip().lower(),
        m.CandidatePerson.normalized_name == normalized))))
    accounts = list(db.scalars(select(m.RFOneAccount).where(or_(
        func.lower(m.RFOneAccount.email) == email.strip().lower(),
        m.RFOneAccount.username == username.strip().lower(),
        func.lower(m.RFOneAccount.display_name) == name.strip().lower()))))
    result = {f'person:{p.id}': p.full_name for p in persons}
    for account in accounts:
        link = db.get(people.PersonAccountLink, account.id)
        key = f'person:{link.person_id}' if link else f'account:{account.id}'
        result[key] = account.display_name
    return [dict(key=key, name=name) for key, name in result.items()]


def resolve(db, *, name, email, username, confirmation=None):
    if db.bind.dialect.name == 'postgresql':
        # Serialize concurrent onboarding with overlapping identity evidence.
        import hashlib
        from sqlalchemy import text
        keys = {name.casefold().strip(), email.casefold().strip(), username.casefold().strip()}
        for value in sorted(keys):
            lock = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big', signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock})
    matches = candidates(db, name, email, username)
    if matches and confirmation not in {r['key'] for r in matches}:
        raise ConfirmationRequired(matches)
    person = account = None
    if confirmation:
        if confirmation not in {r['key'] for r in matches}:
            raise ValueError('La corrispondenza è cambiata. Ricarica e verifica i dati.')
        kind, key = confirmation.split(':'); key = int(key)
        if kind == 'person':
            person = db.scalar(select(m.CandidatePerson).where(m.CandidatePerson.id == key).with_for_update())
            link = db.scalar(select(people.PersonAccountLink).where(people.PersonAccountLink.person_id == key))
            account = db.get(m.RFOneAccount, link.account_id) if link else None
        else:
            account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.id == key).with_for_update())
        # A different email/username owner cannot be merged into this identity.
        owners = list(db.scalars(select(m.RFOneAccount).where(or_(
            func.lower(m.RFOneAccount.email) == email.strip().lower(),
            m.RFOneAccount.username == username.strip().lower()))))
        if any(not account or row.id != account.id for row in owners):
            raise ValueError('Email o nome utente appartengono a un altro account. Nessun collegamento eseguito.')
    from . import registry_identity as registry
    canonical=registry.resolve_person(db,name=name,email=email,candidate=person,account=account)
    if person is None:
        person=registry.candidate_for_person(db,canonical.id)
        if person is None:
            person=m.CandidatePerson(full_name=name.strip(),primary_email=email.strip().lower(),normalized_name=' '.join(name.casefold().split()))
            db.add(person);db.flush()
            registry.bind_context(db,canonical,'CANDIDATE',person)
    return person, account


def attach(db, person, account, training):
    from .person_reconciliation import validate_link
    validate_link(db, person.id, 'account', account.id)
    validate_link(db, person.id, 'training', training.id)
    existing = db.get(people.PersonAccountLink, account.id)
    if existing and existing.person_id != person.id:
        raise ValueError('Account già collegato a una persona diversa.')
    if not existing:
        db.add(people.PersonAccountLink(account_id=account.id, person_id=person.id,
            linked_by_id=account.id, linked_at=datetime.now(timezone.utc)))
    link = db.get(TrainingPersonLink, training.id)
    if link and link.person_id != person.id:
        raise ValueError('Studente già collegato a una persona diversa.')
    if not link:
        db.add(TrainingPersonLink(training_account_id=training.id, person_id=person.id))
    from . import registry_identity as registry
    registry.resolve_person(db,name=person.full_name,email=person.primary_email,candidate=person,account=account,training=training)
    db.flush()


def operational_identity_ids(db):
    """Exclude student-only people, including legacy students, independently of grants.

    Preserve employees explicitly linked to the same person. Existing assignments
    are not removed; this governs only new candidate selection.
    """
    students = set(db.scalars(select(m.TrainingAccount.acting_identity_id).where(m.TrainingAccount.role == 'student')))
    if inspect(db.connection()).has_table('training_person_links') and people.available(db):
        employed = set(db.scalars(select(m.TrainingAccount.acting_identity_id)
            .join(TrainingPersonLink, TrainingPersonLink.training_account_id == m.TrainingAccount.id)
            .join(people.PersonEmployeeLink, people.PersonEmployeeLink.person_id == TrainingPersonLink.person_id)))
        students -= employed
    from . import access_profiles as profiles, employee_directory as directory
    if inspect(db.connection()).has_table(profiles.PersonCompanyStatus.__tablename__):
        employed=set(db.scalars(select(profiles.PersonCompanyStatus.employee_id).where(profiles.PersonCompanyStatus.code=='EMPLOYEE',profiles.PersonCompanyStatus.employee_id.is_not(None))))
        for account in db.scalars(select(m.TrainingAccount).where(m.TrainingAccount.role=='student')):
            if directory.context_person_id(db,'TRAINING',account.id) in employed:
                students.discard(account.acting_identity_id)
    return [i for i in db.scalars(select(m.ActingIdentity.id)) if i not in students]
