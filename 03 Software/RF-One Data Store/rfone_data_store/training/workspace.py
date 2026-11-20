"""Student roster metadata and assignment orchestration; canonical Training data."""
from datetime import datetime, timezone
import secrets
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, select, func
from .. import models as m, rfone_account_service as accounts
from . import service


class TrainingStudentProfile(m.Base):
    __tablename__ = 'training_student_profiles'
    training_account_id = Column(Integer, ForeignKey('training_accounts.id'), primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), unique=True, nullable=True)
    phone = Column(String(80), nullable=False, default='', server_default='')
    archived_at = Column(DateTime(timezone=True), nullable=True)
    must_change_password = Column(Boolean, nullable=False, default=False, server_default='false')


class TrainingAssignmentSubmission(m.Base):
    __tablename__ = 'training_assignment_submissions'
    token = Column(String(64), primary_key=True)
    trainer_id = Column(Integer, ForeignKey('training_accounts.id'), nullable=False)


def profile(db, training_id):
    row = db.get(TrainingStudentProfile, training_id)
    if row is None:
        row = TrainingStudentProfile(training_account_id=training_id, phone='', must_change_password=False)
        db.add(row)
        db.flush()
    return row


def roster(db):
    rows = db.execute(select(m.TrainingAccount, m.ActingIdentity, TrainingStudentProfile,
                            m.RFOneAccount).join(m.ActingIdentity, m.TrainingAccount.acting_identity_id==m.ActingIdentity.id)
        .outerjoin(TrainingStudentProfile, TrainingStudentProfile.training_account_id==m.TrainingAccount.id)
        .outerjoin(m.RFOneTrainingIdentityLink, m.RFOneTrainingIdentityLink.training_account_id==m.TrainingAccount.id)
        .outerjoin(m.RFOneAccount, m.RFOneAccount.id==m.RFOneTrainingIdentityLink.rfone_account_id)
        .where(m.TrainingAccount.role=='student').order_by(m.ActingIdentity.display_name)).all()
    return [dict(id=a.id, name=i.display_name, username=a.username, email=r.email if r else '',
                 phone=p.phone if p else '', archived=bool(p and p.archived_at),
                 employee_id=p.employee_id if p else None, pending=bool(p and p.must_change_password),
                 account_id=r.id if r else None,active=(r is None or r.status=='ACTIVE')) for a,i,p,r in rows]


def linked_account(db, training_id):
    link = db.scalar(select(m.RFOneTrainingIdentityLink).where(m.RFOneTrainingIdentityLink.training_account_id==training_id))
    return db.get(m.RFOneAccount, link.rfone_account_id) if link else None


def editable_student(db, training_id):
    a=db.get(m.TrainingAccount,training_id)
    if a is None or a.role!='student':
        raise ValueError('Student not found.')
    p=profile(db,a.id)
    if p.employee_id:
        raise ValueError('This recipient belongs to the employee directory.')
    r=linked_account(db,a.id)
    if r:
        from .. import access_profiles as profiles
        companies = profiles.company_ids_for_account(db, r.id) | {None}
        grants = [g for company in companies for g in profiles.effective_permissions(db, r.id, company_id=company).items()]
        if r.is_admin or not grants or any(code != 'TRAINING' or value['role_code'] != 'student' for code,value in grants):
            raise ValueError('An RF-One administrator must manage this account’s credentials.')
    return a,p,r


def save_student(db, training_id, *, name, username, email, phone, password=''):
    a,p,r=editable_student(db,training_id)
    name,username,email,phone=name.strip(),username.strip().lower(),email.strip().lower(),phone.strip()
    if not name or not username or len(name)>255 or len(username)>64 or len(phone)>80:
        raise ValueError('Enter the full name and a valid username (up to 64 characters).')
    if not email or '@' not in email or email.startswith('@') or email.endswith('@'):
        raise ValueError('Enter a valid email address.')
    if db.scalar(select(m.TrainingAccount.id).where(m.TrainingAccount.username==username,m.TrainingAccount.id!=a.id)):
        raise ValueError('This username is already in use.')
    other=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username==username))
    if other and (r is None or other.id!=r.id):
        raise ValueError('This username is already in use.')
    accounts.check_email_available(db,email,exclude_account_id=r.id if r else None)
    if r is None:
        if not password:
            raise ValueError('Set an initial password to enable RF-One access.')
        r=accounts.create_account(db,username=username,display_name=name,password=password,email=email)
        accounts.set_domain_access(db,account_id=r.id,domain_code='TRAINING',enabled=True,role_code='student')
        db.add(m.RFOneTrainingIdentityLink(rfone_account_id=r.id,training_account_id=a.id))
    if password:
        if len(password)<8:
            raise ValueError('The password must contain at least 8 characters.')
        accounts.set_password(db,r,password)
        p.must_change_password=True
    if r.username!=username:
        r.session_version+=1
    if r.email!=email:
        r.email_verified_at=None
    a.username=r.username=username
    r.display_name=name
    r.email=email
    db.get(m.ActingIdentity,a.acting_identity_id).display_name=name
    p.phone=phone
    db.flush()
    return a


def archive_student(db, training_id, archived):
    a,p,r=editable_student(db,training_id)
    p.archived_at=datetime.now(timezone.utc) if archived else None
    if r:
        r.status='INACTIVE' if archived else 'ACTIVE'
        r.session_version+=1
    db.flush()


def assign(db, *, trainer_id, recipients, pill_ids, purpose, token):
    if not purpose.strip() or not recipients or not pill_ids:
        raise ValueError('Provide the objective, at least one recipient and at least one content item.')
    trainer=db.get(m.TrainingAccount,trainer_id)
    if not trainer or trainer.role!='trainer':
        raise ValueError('The trainer role is required.')
    if not token or len(token)>64:
        raise ValueError('Reopen the page to confirm the assignment.')
    if db.get(TrainingAssignmentSubmission,token):
        raise ValueError('This assignment has already been saved.')
    db.add(TrainingAssignmentSubmission(token=token,trainer_id=trainer_id))
    db.flush()
    pills=[p.id for p in service.list_all_pills(db) if p.id in pill_ids]
    if set(pills)!=set(pill_ids):
        raise ValueError('A selected content item is no longer available.')
    # Serialize requests from this trainer, including employee identity creation.
    db.execute(select(m.TrainingAccount.id).where(m.TrainingAccount.id==trainer_id).with_for_update())
    students=[]
    for value in sorted(set(recipients)):
        try:
            kind,raw=value.split(':'); key=int(raw)
        except (ValueError,AttributeError):
            raise ValueError('Invalid recipient.')
        if kind=='student':
            a=db.get(m.TrainingAccount,key)
            p=db.get(TrainingStudentProfile,key)
            r=linked_account(db,key)
            if not a or a.role!='student' or (p and (p.archived_at or p.employee_id)) or (r and r.status!='ACTIVE'):
                raise ValueError('A selected student is not active.')
        elif kind=='employee':
            employee=db.get(m.Employee,key)
            if not employee or employee.active is False:
                raise ValueError('A selected employee is not active.')
            p=db.scalar(select(TrainingStudentProfile).where(TrainingStudentProfile.employee_id==key))
            if p:
                a=db.get(m.TrainingAccount,p.training_account_id)
            else:
                a=service.create_account(db,display_name=employee.display_name or f'Dipendente {key}',
                    username='employee-'+str(key)+'-'+secrets.token_hex(4),password=secrets.token_urlsafe(32),role='student',created_by_account_id=trainer_id)
                p=profile(db,a.id);p.employee_id=key
        else:
            raise ValueError('Invalid recipient type.')
        students.append(a.id)
    for student_id in set(students):
        need=service.create_need(db,student_account_id=student_id,text=purpose,origin='other',created_by_account_id=trainer_id)
        for pill_id in sorted(set(pill_ids)):
            service.assign_pill(db,need_id=need.id,pill_id=pill_id,assigned_by_account_id=trainer_id)
    return len(set(students))*len(set(pill_ids))
