"""Shared identity orchestration over the actual Registry, never a new roster."""
import hashlib
from sqlalchemy import select, func, or_, text
from . import models as m, employee_directory as directory


class IdentityReviewRequired(ValueError):
    pass


def normal(value):
    return ' '.join((value or '').casefold().split())


def phone_key(value):
    return ''.join(c for c in (value or '') if c.isdigit())


def lock_evidence(db, name, email, phone):
    if db.bind.dialect.name == 'postgresql':
        for value in sorted({normal(name), normal(email), phone_key(phone)} - {''}):
            key=int.from_bytes(hashlib.sha256(('registry:'+value).encode()).digest()[:8],'big',signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})


def resolve_person(db, *, name, email=None, phone=None, actor=None, employee_id=None,
                   candidate=None, account=None, training=None, require_new=False):
    name=(name or '').strip();email=(email or '').strip();phone=(phone or '').strip()
    if not name or len(name)>255 or len(email)>255 or len(phone)>64:
        raise ValueError('Inserisci nome e contatti validi per il Registry.')
    lock_evidence(db,name,email,phone)
    confirmed=set()
    if employee_id is not None:
        canonical=directory.resolve_employee_id(db,int(employee_id))
        if not db.get(m.Employee,canonical):raise ValueError('Persona Registry non trovata.')
        confirmed.add(canonical)
    contexts=[(kind,row) for kind,row in [('CANDIDATE',candidate),('RFONE_ACCOUNT',account),('TRAINING',training)] if row is not None]
    for kind,row in contexts:
        known=directory.context_person_id(db,kind,row.id)
        if known is not None:confirmed.add(known)
    matches=set()
    mail=normal(email);tel=phone_key(phone)
    for row in db.scalars(select(m.Employee)):
        if (mail and normal(row.email)==mail) or (tel and phone_key(row.phone)==tel):
            matches.add(directory.resolve_employee_id(db,row.id))
    matching_accounts=[]
    for row in db.scalars(select(m.RFOneAccount)):
        if (mail and mail in {normal(row.email),normal(row.contact_email)}) or (tel and phone_key(row.contact_phone)==tel):
            matching_accounts.append(row)
            known=directory.context_person_id(db,'RFONE_ACCOUNT',row.id)
            if known is not None:matches.add(known)
    if len(confirmed)>1 or (confirmed and matches-confirmed) or (not confirmed and len(matches)>1):
        raise IdentityReviewRequired('Contatti o collegamenti identificano persone diverse: verifica il Registry. Nessuna identità modificata.')
    matching_candidates=[]
    for row in db.scalars(select(m.CandidatePerson)):
        if (mail and normal(row.primary_email)==mail) or (tel and phone_key(row.primary_phone)==tel):
            matching_candidates.append(row)
            known=directory.context_person_id(db,'CANDIDATE',row.id)
            if known is not None:matches.add(known)
    if (confirmed and matches-confirmed) or (not confirmed and len(matches)>1):
        raise IdentityReviewRequired('Contatti Selection in conflitto con il Registry: verifica le identità.')
    unresolved=[row for row in matching_candidates if directory.context_person_id(db,'CANDIDATE',row.id) is None]
    if len(unresolved)>1 and candidate is None:
        raise IdentityReviewRequired('Più anagrafiche Selection condividono i contatti: verifica le corrispondenze.')
    selected=next(iter(confirmed or matches),None)
    existing_facet=candidate_for_person(db,selected) if selected is not None and (candidate is not None or len(unresolved)==1) else None
    existing_candidate=existing_facet.id if existing_facet is not None else None
    if candidate is None and len(unresolved)==1 and existing_candidate is None:
        contexts.append(('CANDIDATE',unresolved[0]))
    if candidate is not None and existing_candidate is not None and existing_candidate!=candidate.id:
        raise IdentityReviewRequired('La persona Registry ha già un’anagrafica Selection: verifica i record storici prima di collegarne un’altra.')
    if require_new and (selected is not None or matching_accounts):
        raise IdentityReviewRequired('Persona o account già presenti nel Registry: apri e modifica il record esistente.')
    if selected is None:
        same_names=[row.id for row in db.scalars(select(m.Employee)) if normal(row.display_name)==normal(name)]
        if same_names and employee_id is None:
            raise IdentityReviewRequired('Esiste una persona con lo stesso nome. Selezionala dal Registry o verifica l’omonimia prima di creare un’altra identità.')
        if len(matching_accounts)>1:
            raise IdentityReviewRequired('Più account hanno gli stessi contatti: verifica i collegamenti nel Registry.')
        person=directory.create_person(db,display_name=name,email=email or None,phone=phone or None,account_id=actor)
    else:
        person=db.get(m.Employee,selected)
    # Contact evidence may recover an existing login, but never changes credentials.
    if account is None and len(matching_accounts)==1:
        contexts.append(('RFONE_ACCOUNT',matching_accounts[0]))
    for kind,row in contexts:
        directory.link_context(db,employee_id=person.id,kind=kind,target_id=row.id,account_id=actor)
    # A previously account-only Registry record keeps all company qualifications
    # when the same explicitly linked identity gains its central person bridge.
    from . import access_profiles as profiles
    related=[row.id for row in db.scalars(select(m.RFOneAccount)) if directory.context_person_id(db,'RFONE_ACCOUNT',row.id)==person.id]
    codes=set(db.scalars(select(profiles.PersonCompanyStatus.code).where(profiles.PersonCompanyStatus.employee_id==person.id)))
    moved=[]
    for status in db.scalars(select(profiles.PersonCompanyStatus).where(profiles.PersonCompanyStatus.account_id.in_(related))):
        moved.append(dict(source_id=status.id,account_id=status.account_id,code=status.code,assigned_at=str(status.assigned_at)))
        if status.code in codes:db.delete(status)
        else:
            status.account_id=None;status.employee_id=person.id;codes.add(status.code)
    if moved:profiles.event(db,'COMPANY_STATUS_IDENTITY_LINKED',actor,employee_id=person.id,sources=moved)
    db.flush()
    return person


def bind_context(db, person, kind, row, actor=None):
    return directory.link_context(db,employee_id=person.id,kind=kind,target_id=row.id,account_id=actor)


def training_eligible(db, person_id):
    from . import access_profiles as profiles
    if not db.get(m.Employee,person_id):return False
    if db.scalar(select(profiles.PersonCompanyStatus.id).where(profiles.PersonCompanyStatus.employee_id==person_id,profiles.PersonCompanyStatus.code=='EMPLOYEE').limit(1)):
        return True
    return db.scalar(select(m.EmployeeContextLink.id).where(m.EmployeeContextLink.employee_id==person_id,m.EmployeeContextLink.training_account_id.is_not(None)).limit(1)) is not None


def candidate_for_person(db, person_id):
    from . import people_registry as links
    ids=set(db.scalars(select(m.EmployeeContextLink.candidate_person_id).where(m.EmployeeContextLink.employee_id==person_id,m.EmployeeContextLink.candidate_person_id.is_not(None))))
    from sqlalchemy import inspect
    if inspect(db.connection()).has_table('person_employee_links'):
        ids.update(row.person_id for row in db.scalars(select(links.PersonEmployeeLink)) if directory.resolve_employee_id(db,row.employee_id)==person_id)
    if len(ids)>1:raise IdentityReviewRequired('Più identità Selection già collegate: verifica la riconciliazione senza modificarne lo storico.')
    return db.get(m.CandidatePerson,next(iter(ids))) if ids else None
