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
    people.lock_identity_evidence(db, name, email, username)
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
    if person is None:
        person = people.create_identity(db, full_name=name.strip(), email=email.strip().lower(),
            normalized_name=' '.join(name.casefold().split()))
    return person, account


def attach(db, person, account, training):
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
    if 'EMPLOYEE' not in people.company_statuses(db, person.id) and not db.get(PersonQualification, (person.id, 'STUDENT')):
        db.add(PersonQualification(person_id=person.id, code='STUDENT'))
    db.flush()


def eligible_for_training(db, person_id):
    """Eligibility never grants login or permissions and requires no STUDENT for employees."""
    if not db.get(m.CandidatePerson, person_id):
        return False
    if 'EMPLOYEE' in people.company_statuses(db, person_id):
        return True
    return bool(db.get(PersonQualification, (person_id, 'STUDENT')) or
                db.scalar(select(TrainingPersonLink.training_account_id).where(TrainingPersonLink.person_id == person_id)))


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
        if inspect(db.connection()).has_table('person_company_statuses'):
            qualified_employees = set(db.scalars(select(m.TrainingAccount.acting_identity_id)
                .join(TrainingPersonLink, TrainingPersonLink.training_account_id == m.TrainingAccount.id)
                .join(people.PersonCompanyStatus, people.PersonCompanyStatus.person_id == TrainingPersonLink.person_id)
                .where(people.PersonCompanyStatus.code == 'EMPLOYEE')))
            students -= qualified_employees
    return [i for i in db.scalars(select(m.ActingIdentity.id)) if i not in students]
