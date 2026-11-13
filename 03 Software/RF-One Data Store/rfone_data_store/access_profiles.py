"""Shared role profiles, company memberships and additive effective permissions.

No network, commits or employment/payroll changes. Caller owns transactions.
"""
from contextvars import ContextVar
from datetime import datetime, timezone
from types import SimpleNamespace
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, select, func, text, inspect
from . import models as m
from . import employee_directory as directory

company_context = ContextVar('rfone_access_company', default=None)
Index('uq_shared_profile_role_name',func.lower(m.RestaurantRole.name),unique=True,
      postgresql_where=text('restaurant_id IS NULL'),sqlite_where=text('restaurant_id IS NULL'))
Index('uq_shared_profile_area_name',func.lower(m.OperationalArea.name),unique=True,
      postgresql_where=text('restaurant_id IS NULL'),sqlite_where=text('restaurant_id IS NULL'))


class CompanyContext(m.Base):
    __tablename__='rfone_company_contexts'
    __table_args__=(CheckConstraint("kind IN ('COMPANY','GROUP')",name='ck_rfone_company_kind'),)
    id=Column(Integer,primary_key=True)
    name=Column(String(255),nullable=False,unique=True)
    kind=Column(String(16),nullable=False,default='COMPANY')
    legal_entity_id=Column(ForeignKey('legal_entities.id'),unique=True)
    active=Column(Boolean,nullable=False,default=True,server_default=text('true'))


class CompanyMembership(m.Base):
    __tablename__='rfone_person_company_memberships'
    __table_args__=(
        CheckConstraint('(employee_id IS NOT NULL AND account_id IS NULL) OR (employee_id IS NULL AND account_id IS NOT NULL)',name='ck_company_membership_target'),
        Index('uq_company_employee_open','employee_id','company_id',unique=True,postgresql_where=text('valid_to IS NULL AND employee_id IS NOT NULL'),sqlite_where=text('valid_to IS NULL AND employee_id IS NOT NULL')),
        Index('uq_company_account_open','account_id','company_id',unique=True,postgresql_where=text('valid_to IS NULL AND account_id IS NOT NULL'),sqlite_where=text('valid_to IS NULL AND account_id IS NOT NULL')),
    )
    id=Column(Integer,primary_key=True)
    employee_id=Column(ForeignKey('employees.id'),index=True)
    account_id=Column(ForeignKey('rfone_accounts.id'),index=True)
    company_id=Column(ForeignKey('rfone_company_contexts.id'),nullable=False,index=True)
    valid_from=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    valid_to=Column(DateTime(timezone=True))


class RoleProfileAssignment(m.Base):
    __tablename__='rfone_role_profile_assignments'
    __table_args__=(Index('uq_profile_assignment_open','membership_id','role_id','area_id',unique=True,postgresql_where=text('valid_to IS NULL'),sqlite_where=text('valid_to IS NULL')),)
    id=Column(Integer,primary_key=True)
    membership_id=Column(ForeignKey('rfone_person_company_memberships.id'),nullable=False,index=True)
    role_id=Column(ForeignKey('restaurant_roles.id'),nullable=False,index=True)
    area_id=Column(ForeignKey('operational_areas.id'),nullable=False)
    valid_from=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    valid_to=Column(DateTime(timezone=True))


class RolePermission(m.Base):
    __tablename__='rfone_role_permissions'
    __table_args__=(UniqueConstraint('role_id','domain_code',name='uq_profile_role_domain'),CheckConstraint("scope IN ('ALL','SELECTED')",name='ck_profile_permission_scope'))
    id=Column(Integer,primary_key=True)
    role_id=Column(ForeignKey('restaurant_roles.id'),nullable=False,index=True)
    domain_code=Column(String(64),nullable=False)
    scope=Column(String(16),nullable=False,default='ALL')
    role_code=Column(String(64))
    items=Column(JSON,nullable=False,default=list)


class ProfileEvent(m.Base):
    __tablename__='rfone_access_profile_events'
    id=Column(Integer,primary_key=True)
    account_id=Column(ForeignKey('rfone_accounts.id'))
    action=Column(String(64),nullable=False)
    details=Column(JSON,nullable=False,default=dict)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())


def event(db,action,actor=None,**details):
    db.add(ProfileEvent(account_id=actor,action=action,details=details))


def active(value):
    return value is not None and value.active is not False


def _name(value):
    value=' '.join((value or '').split())
    if not value or len(value)>255:raise ValueError('Enter a name of 1–255 characters.')
    return value


def save_area(db,*,name,area_id=None,actor=None):
    name=_name(name)
    area=db.get(m.OperationalArea,area_id) if area_id else m.OperationalArea(restaurant_id=None,active=True)
    if area is None:raise ValueError('Area not found.')
    duplicate=db.scalar(select(m.OperationalArea.id).where(func.lower(m.OperationalArea.name)==name.lower(),
        m.OperationalArea.id!=(area.id or -1)))
    if duplicate:raise ValueError('This area already exists in the same catalog.')
    before=area.name;area.name=name;db.add(area);db.flush()
    event(db,'AREA_SAVE',actor,id=area.id,before=before,name=name)
    return area


def save_role(db,*,name,area_ids,role_id=None,actor=None):
    name=_name(name);area_ids=set(int(i) for i in area_ids)
    if not area_ids:raise ValueError('Choose at least one area.')
    areas=list(db.scalars(select(m.OperationalArea).where(m.OperationalArea.id.in_(area_ids))))
    if len(areas)!=len(area_ids) or not all(active(a) for a in areas):raise ValueError('Choose active areas only.')
    role=db.get(m.RestaurantRole,role_id) if role_id else m.RestaurantRole(restaurant_id=None,active=True)
    if role is None:raise ValueError('Role not found.')
    duplicate=db.scalar(select(m.RestaurantRole.id).where(func.lower(m.RestaurantRole.name)==name.lower(),
        m.RestaurantRole.id!=(role.id or -1)))
    if duplicate:raise ValueError('This role already exists in the same catalog.')
    before=role.name;role.name=name;db.add(role);db.flush()
    previous=list(db.scalars(select(m.OperationalAreaRole).where(m.OperationalAreaRole.restaurant_role_id==role.id)))
    for pair in previous:
        if pair.operational_area_id not in area_ids:db.delete(pair)
    old={p.operational_area_id for p in previous}
    for identity in area_ids-old:db.add(m.OperationalAreaRole(restaurant_role_id=role.id,operational_area_id=identity))
    event(db,'ROLE_SAVE',actor,id=role.id,before=before,name=name,area_ids=sorted(area_ids))
    db.flush();return role


def set_archived(db,kind,identity,archived,actor=None):
    model={'role':m.RestaurantRole,'area':m.OperationalArea,'company':CompanyContext}.get(kind)
    value=db.get(model,identity) if model else None
    if value is None:raise ValueError('Record not found.')
    value.active=not archived;event(db,'CATALOG_ARCHIVE' if archived else 'CATALOG_RESTORE',actor,kind=kind,id=identity)
    db.flush()


def save_permissions(db,role_id,values,domains,actor=None):
    role=db.get(m.RestaurantRole,role_id)
    if not active(role):raise ValueError('An active role is required.')
    registry={d.code:d for d in domains}
    if set(values)-set(registry):raise ValueError('Unknown domain.')
    normalized={}
    for code,entry in values.items():
        mode=entry.get('mode','none');level=(entry.get('role') or '').strip().lower()
        if mode not in ('none','all','selected'):raise ValueError('Invalid permission scope.')
        permitted={'','admin','trainer','student'} if code=='TRAINING' else {'','admin'}
        if getattr(registry[code],'view_level',False):permitted=permitted|{'view'}
        if level not in permitted:raise ValueError('Invalid domain role.')
        items=sorted(set(entry.get('items',[])))
        allowed={i.code for i in registry[code].items}
        if set(items)-allowed:raise ValueError('Unknown domain function.')
        if mode=='selected' and (not items or not allowed):raise ValueError('Choose at least one function or the whole domain.')
        if mode!='none':normalized[code]={'scope':'ALL' if mode=='all' else 'SELECTED','role_code':level or None,'items':items if mode=='selected' else []}
    previous=list(db.scalars(select(RolePermission).where(RolePermission.role_id==role_id)))
    before={p.domain_code:{'scope':p.scope,'role_code':p.role_code,'items':p.items} for p in previous}
    by_code={p.domain_code:p for p in previous}
    for code,p in by_code.items():
        if code not in normalized:db.delete(p)
    for code,entry in normalized.items():
        p=by_code.get(code) or RolePermission(role_id=role_id,domain_code=code)
        p.scope,p.role_code,p.items=entry['scope'],entry['role_code'],entry['items'];db.add(p)
    event(db,'ROLE_PERMISSIONS',actor,role_id=role_id,before=before,after=normalized)
    db.flush()


def person_target(db,target,*,allow_inactive_account=False):
    try:kind,identity=target.split(':');identity=int(identity)
    except (ValueError,AttributeError):raise ValueError('Choose a person or external account.')
    if kind=='account':
        account=db.get(m.RFOneAccount,identity)
        if account is None or (account.status!='ACTIVE' and not allow_inactive_account):raise ValueError('Choose an active account.')
        person_id=directory.context_person_id(db,'RFONE_ACCOUNT',identity)
        if person_id is None:return None,identity
        identity=person_id
    elif kind!='employee':raise ValueError('Invalid person reference.')
    identity=directory.resolve_employee_id(db,identity)
    person=db.get(m.Employee,identity)
    if person is None or not directory.employee_is_active(person,[]):raise ValueError('Dismissed people cannot receive new assignments.')
    return identity,None


def membership(db,target,company_id,actor=None):
    employee,account=person_target(db,target)
    company=db.get(CompanyContext,company_id)
    if not active(company):raise ValueError('Choose an active company.')
    condition=membership_target_condition(db,employee,account)
    row=db.scalar(select(CompanyMembership).where(condition,CompanyMembership.company_id==company_id,CompanyMembership.valid_to.is_(None)))
    if row:
        if employee is not None and row.employee_id is None:
            previous_account=row.account_id;row.account_id=None;row.employee_id=employee
            event(db,'MEMBERSHIP_IDENTITY_LINKED',actor,membership_id=row.id,employee_id=employee,previous_account_id=previous_account)
            db.flush()
        return row
    row=CompanyMembership(employee_id=employee,account_id=account,company_id=company_id)
    db.add(row);db.flush();event(db,'COMPANY_ASSIGN',actor,membership_id=row.id,employee_id=employee,account_id=account,company_id=company_id)
    return row


def membership_target_condition(db,employee_id=None,account_id=None):
    if employee_id is None:return CompanyMembership.account_id==account_id
    # Existing external-account memberships remain visible after explicit identity
    # linkage; a subsequent membership POST normalizes the same row, not a copy.
    related=[identity for identity in db.scalars(select(m.RFOneAccount.id))
             if directory.context_person_id(db,'RFONE_ACCOUNT',identity)==employee_id]
    return (CompanyMembership.employee_id==employee_id) | CompanyMembership.account_id.in_(related)


def assign_role(db,*,membership_id,role_id,area_id,actor=None):
    member=db.scalar(select(CompanyMembership).where(CompanyMembership.id==membership_id).with_for_update())
    if member is None or member.valid_to is not None or not active(db.get(CompanyContext,member.company_id)):raise ValueError('Choose a current company membership.')
    person_target(db,f'employee:{member.employee_id}' if member.employee_id is not None else f'account:{member.account_id}')
    role,area=db.get(m.RestaurantRole,role_id),db.get(m.OperationalArea,area_id)
    pair=db.get(m.OperationalAreaRole,(area_id,role_id))
    if not active(role) or not active(area) or pair is None:raise ValueError('Choose an active role and one of its configured areas.')
    row=db.scalar(select(RoleProfileAssignment).where(RoleProfileAssignment.membership_id==member.id,
        RoleProfileAssignment.role_id==role_id,RoleProfileAssignment.area_id==area_id,RoleProfileAssignment.valid_to.is_(None)))
    if row:return row
    row=RoleProfileAssignment(membership_id=member.id,role_id=role_id,area_id=area_id)
    db.add(row);db.flush();event(db,'ROLE_ASSIGN',actor,id=row.id,membership_id=member.id,role_id=role_id,area_id=area_id)
    return row


def withdraw(db,kind,identity,actor=None):
    model=CompanyMembership if kind=='membership' else RoleProfileAssignment if kind=='assignment' else None
    row=db.scalar(select(model).where(model.id==identity).with_for_update()) if model else None
    if row is None:raise ValueError('Assignment not found.')
    if row.valid_to is not None:return
    now=datetime.now(timezone.utc);row.valid_to=now
    if kind=='membership':
        for assignment in db.scalars(select(RoleProfileAssignment).where(RoleProfileAssignment.membership_id==identity,RoleProfileAssignment.valid_to.is_(None))):assignment.valid_to=now
    event(db,'PROFILE_WITHDRAW',actor,kind=kind,id=identity);db.flush()


def _target_condition(db,account_id):
    identity=directory.context_person_id(db,'RFONE_ACCOUNT',account_id)
    condition=CompanyMembership.account_id==account_id
    if identity is not None:condition=condition | (CompanyMembership.employee_id==identity)
    return condition,identity


def company_ids_for_account(db,account_id):
    account=db.get(m.RFOneAccount,account_id)
    if account is None or account.status!='ACTIVE':return set()
    if account.is_admin or account.is_owner:return set(db.scalars(select(CompanyContext.id).where(CompanyContext.active.is_(True))))
    condition,identity=_target_condition(db,account_id)
    if identity is not None and not directory.employee_is_active(db.get(m.Employee,identity),[]):return set()
    now=datetime.now(timezone.utc)
    return set(db.scalars(select(CompanyMembership.company_id).join(CompanyContext).where(condition,
        CompanyMembership.valid_from<=now,(CompanyMembership.valid_to.is_(None) | (CompanyMembership.valid_to>now)),CompanyContext.active.is_(True))))


def effective_permissions(db,account_id,*,company_id):
    """Fresh union; None retains only legacy direct grants, never all-company roles."""
    account=db.get(m.RFOneAccount,account_id)
    if account is None or account.status!='ACTIVE':return {}
    condition,identity=_target_condition(db,account_id)
    if identity is not None and not account.is_owner and not directory.employee_is_active(db.get(m.Employee,identity),[]):return {}
    grants=[]
    for row in db.scalars(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==account_id,m.RFOneAccountDomainAccess.enabled.is_(True))):
        items=list(db.scalars(select(m.RFOneAccountDomainItemAccess.item_code).where(m.RFOneAccountDomainItemAccess.account_id==account_id,m.RFOneAccountDomainItemAccess.domain_code==row.domain_code)))
        grants.append((row.domain_code,row.scope,row.role_code,items,'Direct'))
    if company_id is not None:
        now=datetime.now(timezone.utc)
        query=select(RolePermission,m.RestaurantRole.name).join(m.RestaurantRole,m.RestaurantRole.id==RolePermission.role_id).join(
            RoleProfileAssignment,RoleProfileAssignment.role_id==RolePermission.role_id).join(CompanyMembership,
            CompanyMembership.id==RoleProfileAssignment.membership_id).join(CompanyContext,
            CompanyContext.id==CompanyMembership.company_id).join(m.OperationalArea,
            m.OperationalArea.id==RoleProfileAssignment.area_id).join(m.OperationalAreaRole,
            (m.OperationalAreaRole.operational_area_id==RoleProfileAssignment.area_id)&(m.OperationalAreaRole.restaurant_role_id==RoleProfileAssignment.role_id)).where(
                condition,CompanyMembership.company_id==company_id,CompanyContext.active.is_(True),
                CompanyMembership.valid_from<=now,(CompanyMembership.valid_to.is_(None)|(CompanyMembership.valid_to>now)),
                RoleProfileAssignment.valid_from<=now,(RoleProfileAssignment.valid_to.is_(None)|(RoleProfileAssignment.valid_to>now)),
                m.RestaurantRole.active.is_not(False),m.OperationalArea.active.is_not(False))
        for row,name in db.execute(query):grants.append((row.domain_code,row.scope,row.role_code,row.items,name))
    # The highest level wins. View (read only, below User) applies only when
    # no grant gives User or more; '' / None is User.
    result={};best={};rank={'view':-1,'':0,'student':1,'trainer':2,'admin':3}
    for code,scope,level,items,provenance in grants:
        if scope=='SELECTED' and not items:continue
        original_level=level
        level=(level or '').strip().lower()
        current=result.setdefault(code,{'scope':'SELECTED','role_code':None,'items':set(),'sources':set()})
        if scope=='ALL':current['scope']='ALL'
        current['items'].update(items);current['sources'].add(provenance)
        level_rank=rank.get(level,0);value=(level if level in rank else original_level) or None
        if code not in best or level_rank>best[code] or (level_rank==best[code] and current['role_code'] is None and value):
            current['role_code']=value;best[code]=level_rank
    return result


def effective_access_rows(db,account_id):
    return [SimpleNamespace(id=None,account_id=account_id,domain_code=code,enabled=True,scope=value['scope'],role_code=value['role_code'])
            for code,value in effective_permissions(db,account_id,company_id=company_context.get()).items()]


def effective_item_rows(db,account_id):
    return {code:set(value['items']) for code,value in effective_permissions(db,account_id,company_id=company_context.get()).items()}


def employee_scope_ids(db,account):
    """Legacy explicit Directory grants stay global; profile-only access is company-scoped."""
    if account.is_admin or account.is_owner:return None
    direct=db.scalar(select(m.RFOneAccountDomainAccess.id).where(m.RFOneAccountDomainAccess.account_id==account.id,
        m.RFOneAccountDomainAccess.domain_code=='EMPLOYEES',m.RFOneAccountDomainAccess.enabled.is_(True)))
    if direct:return None
    company=company_context.get()
    if company not in company_ids_for_account(db,account.id):return set()
    now=datetime.now(timezone.utc)
    return set(db.scalars(select(CompanyMembership.employee_id).where(CompanyMembership.company_id==company,
        CompanyMembership.employee_id.is_not(None),CompanyMembership.valid_from<=now,
        (CompanyMembership.valid_to.is_(None)|(CompanyMembership.valid_to>now)))))


def seed_companies(db):
    """Reference existing legal entities; RFGroup is explicitly an operating group."""
    existing=set(db.scalars(select(CompanyContext.legal_entity_id)))
    labels={'RF-Winter Park':'WP','RF-Mount Dora':'MD'}
    for entity in db.scalars(select(m.LegalEntity)):
        if entity.id not in existing:db.add(CompanyContext(name=labels.get(entity.legal_name,entity.legal_name),kind='COMPANY',legal_entity_id=entity.id,active=entity.status=='ACTIVE'))
    if db.scalar(select(CompanyContext.id).where(func.lower(CompanyContext.name)=='rfgroup')) is None:
        db.add(CompanyContext(name='RFGroup',kind='GROUP',active=True))
    db.flush()


_CONTACT_UNSET=object()

def _contact(value,limit,label):
    value=(value or '').strip()
    if len(value)>limit or any(ord(char)<32 for char in value):raise ValueError(f'Invalid {label}.')
    if value and label=='email':
        import re
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise ValueError('Enter a valid email address.')
    return value or None

def save_person_profile(db,target,*,name,company_ids,assignments,actor=None,email=_CONTACT_UNSET,phone=_CONTACT_UNSET,company_statuses=_CONTACT_UNSET,account_status=_CONTACT_UNSET):
    """Atomic editor; preserve ended history and central identity, no POS writes."""
    employee,account=person_target(db,target,allow_inactive_account=True)
    if company_statuses is not _CONTACT_UNSET:
        validate_company_statuses(company_statuses)
    if account_status is not _CONTACT_UNSET:
        save_account_status(db,target,account_status,actor)
    name=_name(name)
    if email is not _CONTACT_UNSET:email=_contact(email,255,'email')
    if phone is not _CONTACT_UNSET:phone=_contact(phone,64,'phone')
    company_ids={int(v) for v in company_ids}
    if not isinstance(assignments,list):raise ValueError('Invalid role assignments.')
    desired=set()
    for row in assignments:
        if not isinstance(row,dict):raise ValueError('Invalid role assignment.')
        key=(int(row['company_id']),int(row['role_id']),int(row['area_id']))
        if key[0] not in company_ids:raise ValueError('Each role must belong to a selected company.')
        desired.add(key)
    condition=membership_target_condition(db,employee,account)
    current=list(db.scalars(select(CompanyMembership).where(condition,CompanyMembership.valid_to.is_(None)).with_for_update()))
    current_companies={v.company_id for v in current}
    for company_id in company_ids-current_companies:
        if not active(db.get(CompanyContext,company_id)):raise ValueError('Choose an active company.')
    for member in current:
        if member.company_id not in company_ids:withdraw(db,'membership',member.id,actor)
    members={v.company_id:v for v in current if v.company_id in company_ids}
    for company_id in company_ids-current_companies:members[company_id]=membership(db,target,company_id,actor)
    for company_id,member in members.items():
        existing=list(db.scalars(select(RoleProfileAssignment).where(RoleProfileAssignment.membership_id==member.id,RoleProfileAssignment.valid_to.is_(None))))
        existing_keys={(company_id,v.role_id,v.area_id) for v in existing}
        for row in existing:
            if (company_id,row.role_id,row.area_id) not in desired:withdraw(db,'assignment',row.id,actor)
        for key in desired-existing_keys:
            if key[0]==company_id:assign_role(db,membership_id=member.id,role_id=key[1],area_id=key[2],actor=actor)
    record=db.get(m.Employee,employee) if employee is not None else db.get(m.RFOneAccount,account)
    if employee is not None:
        directory.update_management(db,record,display_name=name,custom_id=record.custom_id,active=record.active,account_id=actor,
            email=record.email if email is _CONTACT_UNSET else email,phone=record.phone if phone is _CONTACT_UNSET else phone)
    else:
        contact_before={'email':record.contact_email,'phone':record.contact_phone}
        if email is not _CONTACT_UNSET:record.contact_email=email
        if phone is not _CONTACT_UNSET:record.contact_phone=phone
        if email is not _CONTACT_UNSET or phone is not _CONTACT_UNSET:event(db,'EXTERNAL_CONTACT_UPDATE',actor,account_id=account,before=contact_before,after={'email':record.contact_email,'phone':record.contact_phone})
        before=record.display_name;record.display_name=name
        event(db,'ACCOUNT_NAME_UPDATE',actor,account_id=account,before=before,name=name)
    event(db,'PERSON_PROFILE_SAVE',actor,target=target,company_ids=sorted(company_ids))
    if company_statuses is not _CONTACT_UNSET:
        save_company_statuses(db,target,company_statuses,actor)
    db.flush()


def create_profile_person(db,*,name,company_ids,assignments,actor=None,email=_CONTACT_UNSET,phone=_CONTACT_UNSET,company_statuses=_CONTACT_UNSET,account_status=_CONTACT_UNSET):
    from . import registry_identity as registry
    person=registry.resolve_person(db,name=_name(name),email=None if email is _CONTACT_UNSET else email,phone=None if phone is _CONTACT_UNSET else phone,actor=actor,require_new=True)
    if hasattr(directory,'ensure_employee_account'):
        directory.ensure_employee_account(db,person)
    else:
        from uuid import uuid4
        account=m.RFOneAccount(username='employee-'+uuid4().hex,display_name=person.display_name,password_hash='!',status='INACTIVE',is_admin=False,is_owner=False,session_version=1)
        db.add(account);db.flush()
        db.add(m.EmployeeContextLink(employee_id=person.id,rfone_account_id=account.id));db.flush()
    save_person_profile(db,f'employee:{person.id}',name=name,company_ids=company_ids,assignments=assignments,actor=actor,email=email,phone=phone,company_statuses=company_statuses,account_status=account_status)
    return person


def dismiss_profile_person(db,target,*,dismissal_date,actor=None):
    from datetime import date
    try:
        day=date.fromisoformat(dismissal_date or '')
    except (ValueError,TypeError):raise ValueError('Enter a valid dismissal date.')
    if day>datetime.now(timezone.utc).date():raise ValueError('Dismissal date cannot be in the future.')
    employee,account=person_target(db,target)
    if employee is None:raise ValueError('Dismiss person applies to employees, not external accounts.')
    person=db.scalar(select(m.Employee).where(m.Employee.id==employee).with_for_update())
    person.active=False
    if hasattr(person,'dismissed_at'):person.dismissed_at=datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc)
    if hasattr(person,'directory_eligible'):person.directory_eligible=True
    directory._event(db,'DISMISSED',employee_id=employee,account_id=actor,details={'dismissal_date':day.isoformat(),'reason':'MANUAL_RF1'})
    protected=[]
    for linked in db.scalars(select(m.RFOneAccount)):
        if directory.context_person_id(db,'RFONE_ACCOUNT',linked.id)!=employee:continue
        if linked.is_owner:
            protected.append(linked.id)
            directory._event(db,'OWNER_ACCESS_PROTECTED',employee_id=employee,account_id=actor,details={'account_id':linked.id})
        else:
            linked.status='INACTIVE';linked.session_version=(linked.session_version or 0)+1
    event(db,'PERSON_DISMISSED',actor,employee_id=employee,dismissal_date=day.isoformat(),owner_accounts_protected=protected)
    db.flush()


def ensure_profile_account(db,target,actor=None):
    employee,account_id=person_target(db,target)
    if account_id is not None:return db.get(m.RFOneAccount,account_id)
    person=db.scalar(select(m.Employee).where(m.Employee.id==employee).with_for_update())
    linked=[a for a in db.scalars(select(m.RFOneAccount)) if directory.context_person_id(db,'RFONE_ACCOUNT',a.id)==employee]
    if len(linked)>1:raise ValueError('Resolve multiple linked accounts in Employee Directory first.')
    if linked:return linked[0]
    if hasattr(directory,'ensure_employee_account'):return directory.ensure_employee_account(db,person)
    from uuid import uuid4
    account=m.RFOneAccount(username='employee-'+uuid4().hex,display_name=person.display_name,password_hash='!',status='INACTIVE',is_admin=False,is_owner=False,session_version=1)
    db.add(account);db.flush();db.add(m.EmployeeContextLink(employee_id=employee,rfone_account_id=account.id));db.flush()
    event(db,'ACCOUNT_PROVISIONED',actor,employee_id=employee,account_id=account.id)
    return account


COMPANY_STATUSES = ('CANDIDATE', 'EXTERNAL', 'EMPLOYEE')


class PersonCompanyStatus(m.Base):
    __tablename__ = 'rfone_person_company_statuses'
    __table_args__ = (
        CheckConstraint("code IN ('CANDIDATE','EXTERNAL','EMPLOYEE')", name='ck_profile_company_status'),
        CheckConstraint('(employee_id IS NOT NULL AND account_id IS NULL) OR (employee_id IS NULL AND account_id IS NOT NULL)', name='ck_profile_status_target'),
        UniqueConstraint('employee_id', 'code', name='uq_profile_employee_status'),
        UniqueConstraint('account_id', 'code', name='uq_profile_account_status'),
    )
    id = Column(Integer, primary_key=True)
    employee_id = Column(ForeignKey('employees.id'), index=True)
    account_id = Column(ForeignKey('rfone_accounts.id'), index=True)
    code = Column(String(32), nullable=False)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def validate_company_statuses(codes):
    if not isinstance(codes, (list, tuple, set)) or not set(codes) <= set(COMPANY_STATUSES):
        raise ValueError('Status aziendale non valido.')


def profile_account(db, target):
    employee, account = person_target(db, target, allow_inactive_account=True)
    if account is not None:
        return db.get(m.RFOneAccount, account)
    accounts = [a for a in db.scalars(select(m.RFOneAccount))
                if directory.context_person_id(db, 'RFONE_ACCOUNT', a.id) == employee]
    if len(accounts) > 1:
        raise ValueError('Più account collegati: verifica i collegamenti prima di modificare lo status.')
    return accounts[0] if accounts else None


def profile_status_snapshot(db, target, actor=None):
    employee, account = person_target(db, target, allow_inactive_account=True)
    condition = PersonCompanyStatus.employee_id == employee if employee is not None else PersonCompanyStatus.account_id == account
    codes = list(db.scalars(select(PersonCompanyStatus.code).where(condition).order_by(PersonCompanyStatus.code))) if inspect(db.connection()).has_table(PersonCompanyStatus.__tablename__) else []
    login = profile_account(db, target)
    return dict(company_statuses=codes, account_status=login.status if login else 'NONE',
                account_status_locked=bool(login and (login.is_owner or login.id == actor)))


def save_account_status(db, target, status, actor):
    if status not in ('ACTIVE', 'INACTIVE', 'NONE'):
        raise ValueError('Status dell’account non valido.')
    login = profile_account(db, target)
    if login is None:
        if status == 'NONE':
            return
        login = ensure_profile_account(db, target, actor)
    if status == 'NONE':
        raise ValueError('Un account esistente può essere attivo o inattivo, non eliminato da questo modulo.')
    if status == login.status:
        return
    if status == 'INACTIVE' and (login.is_owner or login.id == actor):
        raise ValueError('L’account proprietario o attualmente in uso deve restare attivo.')
    from . import rfone_account_service as accounts
    before = login.status
    accounts.update_account(db, login, display_name=login.display_name, status=status)
    login.session_version = (login.session_version or 0) + 1
    event(db, 'ACCOUNT_STATUS_UPDATE', actor, account_id=login.id, before=before, after=status)


def save_company_statuses(db, target, codes, actor):
    validate_company_statuses(codes)
    employee, account = person_target(db, target, allow_inactive_account=True)
    record = db.get(m.Employee, employee) if employee is not None else db.get(m.RFOneAccount, account)
    db.flush()
    db.refresh(record, with_for_update=True)
    condition = PersonCompanyStatus.employee_id == employee if employee is not None else PersonCompanyStatus.account_id == account
    existing = {row.code: row for row in db.scalars(select(PersonCompanyStatus).where(condition))}
    desired = set(codes)
    for code, row in existing.items():
        if code not in desired:
            db.delete(row)
    for code in desired - existing.keys():
        db.add(PersonCompanyStatus(employee_id=employee, account_id=account, code=code))
    event(db, 'COMPANY_STATUS_UPDATE', actor, target=target, before=sorted(existing), after=sorted(desired))
    db.flush()
