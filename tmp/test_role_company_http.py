"""HTTP acceptance against a disposable SQLite database, with the real shell/auth."""
from pathlib import Path
import os,sys,tempfile,re,json
ROOT=Path(__file__).resolve().parent/'role-company-development'
sys.path[:0]=[str(ROOT/'RF-One Web'),str(ROOT/'RF-One Data Store')]
testdir=tempfile.TemporaryDirectory(prefix='role-company-http-',dir=ROOT.parent,ignore_cleanup_errors=True)
assert Path(testdir.name).resolve().is_relative_to(ROOT.parent.resolve())
os.environ['RFONE_DATABASE_URL']='sqlite:///'+str(Path(testdir.name)/'test.db').replace('\\','/')
os.environ['RFONE_FLASK_SECRET_KEY']='isolated-http-test-only'
from rfone_data_store import models as m,access_profiles as p
import app as web
from db import SessionFactory,_engine
from sqlalchemy import select,func
m.Base.metadata.create_all(_engine)
web.app.config['TESTING']=True
passed=[]
def check(name,condition):
    assert condition,name
    passed.append(name)

with SessionFactory() as db:
    admin=m.RFOneAccount(username='owner',display_name='Owner',password_hash='!',status='ACTIVE',is_admin=True,is_owner=True,session_version=1)
    user=m.RFOneAccount(username='staff',display_name='Staff',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1)
    company=p.CompanyContext(name='WP',kind='COMPANY');db.add_all([admin,user,company]);db.flush()
    admin_id,user_id,company_id=admin.id,user.id,company.id;db.commit()

def client(identity=None):
    c=web.app.test_client()
    if identity:
        with c.session_transaction() as session:session['rfone_account_id']=identity;session['rfone_session_version']=1
    return c
owner=client(admin_id);staff=client(user_id)
check('Anonymous cannot configure profiles',client().get('/admin/roles').status_code==302)
check('Ordinary account cannot configure profiles',staff.get('/admin/roles').status_code==403)
for tab in ('roles','areas','companies','people'):
    check('Render '+tab,owner.get('/admin/roles?tab='+tab).status_code==200)
page=owner.get('/admin/roles').get_data(as_text=True)
token=re.search(r'name="csrf_token" value="([^"]+)"',page)[1]
check('CSRF required',owner.post('/admin/roles',data={'action':'area_save','name':'FOH'}).status_code==400)
def post(**data):return owner.post('/admin/roles',data={'csrf_token':token,**data})
check('Create area',post(action='area_save',name='FOH',tab='areas').status_code==302)
with SessionFactory() as db:area_id=db.scalar(select(m.OperationalArea.id))
check('Duplicate area is refused and modal reopens',post(action='area_save',name='foh',tab='areas').status_code==422)
check('Create role',post(action='role_save',name='Manager',area_ids=str(area_id),tab='roles').status_code==302)
with SessionFactory() as db:role_id=db.scalar(select(m.RestaurantRole.id))
bank=next(d for d in web.DOMAINS if d.code=='BANK');item=bank.items[0].code
check('Save selected item permission',post(action='permissions',id=role_id,access_BANK='selected',items_BANK=item,role_BANK='admin').status_code==302)
check('Invalid domain role refused',post(action='permissions',id=role_id,access_BANK='all',role_BANK='owner').status_code==422)
target='account:'+str(user_id)
check('Add company to external account',post(action='membership',person=target,company_id=company_id,tab='people').status_code==302)
with SessionFactory() as db:membership_id=db.scalar(select(p.CompanyMembership.id))
check('Assign role',post(action='assignment',person=target,membership_id=membership_id,role_id=role_id,area_id=area_id,tab='people').status_code==302)
check('Role policy cannot grant platform administration',staff.get('/admin/roles').status_code==403)
with staff.session_transaction() as session:session['rfone_csrf_token']='staff-company-token'
check('Company switch accepts assigned company',staff.post('/admin/access-company',data={'csrf_token':'staff-company-token','company_id':company_id}).status_code==302)
check('Company switch rejects manipulated scope',staff.post('/admin/access-company',data={'csrf_token':'staff-company-token','company_id':'9999'}).status_code==403)
page=owner.get('/admin/roles?tab=people&person='+target).get_data(as_text=True)
check('Effective permission and company visible','data-edit-person' in page and 'Manager' in page and 'WP' in page)
check('Table starts collapsed','id="people-table" class="profile-people-table"' in page and 'data-person-filter="role"' in page)
check('Other authorizations available','person-system-authorizations' in page)
with SessionFactory() as db:
    other=p.CompanyContext(name='MD',kind='COMPANY');db.add(other);db.commit();other_id=other.id
payload=[{'company_id':company_id,'role_id':role_id,'area_id':area_id},{'company_id':other_id,'role_id':role_id,'area_id':area_id}]
check('Unified editor saves two companies',post(action='person_save',person=target,name='Updated Staff',company_ids=[str(company_id),str(other_id)],person_roles=json.dumps(payload),tab='people').status_code==302)
with SessionFactory() as db:
    check('Name updates canonical account',db.get(m.RFOneAccount,user_id).display_name=='Updated Staff')
    check('Both company assignments work',all(p.effective_permissions(db,user_id,company_id=c).get('BANK') for c in (company_id,other_id)))
check('Invalid edit rejected atomically',post(action='person_save',person=target,name='Must rollback',company_ids=[str(company_id)],person_roles=json.dumps([{'company_id':company_id,'role_id':99999,'area_id':area_id}]),tab='people').status_code==422)
with SessionFactory() as db:
    check('Invalid edit preserves name and memberships',db.get(m.RFOneAccount,user_id).display_name=='Updated Staff' and len(list(db.scalars(select(p.CompanyMembership).where(p.CompanyMembership.valid_to.is_(None)))))==2)
check('Removing company preserves ended history',post(action='person_save',person=target,name='Updated Staff',company_ids=[str(company_id)],person_roles=json.dumps(payload[:1]),tab='people').status_code==302)
with SessionFactory() as db:check('Removed company loses permissions',not p.effective_permissions(db,user_id,company_id=other_id))
check('Archive role',post(action='archive',kind='role',id=role_id).status_code==302)
with SessionFactory() as db:check('Archive immediately revokes role permission',p.effective_permissions(db,user_id,company_id=company_id)=={})
check('Restore role',post(action='restore',kind='role',id=role_id).status_code==302)
with SessionFactory() as db:check('Restore recomputes policy',item in p.effective_permissions(db,user_id,company_id=company_id)['BANK']['items'])
check('Withdraw membership',post(action='withdraw_membership',id=membership_id,person=target,tab='people').status_code==302)
with SessionFactory() as db:
    check('Withdraw revokes and preserves history',p.effective_permissions(db,user_id,company_id=company_id)=={} and db.get(p.CompanyMembership,membership_id).valid_to is not None)
    check('Legacy workforce assignments unchanged',db.scalar(select(func.count()).select_from(m.EmployeeAssignment))==0)
    check('Audit events retained',db.scalar(select(func.count()).select_from(p.ProfileEvent))>=7)
check('Dismiss date mandatory',post(action='person_dismiss',person=target,dismissal_date='',tab='people').status_code==422)
check('External accounts cannot be employee-dismissed',post(action='person_dismiss',person=target,dismissal_date='2026-01-01',tab='people').status_code==422)
check('Add person outside table', 'data-new-person' in page)
check('Create person with company and role',post(action='person_create',name='New Local Person',company_ids=[str(company_id)],person_roles=json.dumps(payload[:1]),tab='people').status_code==302)
with SessionFactory() as db:
    new_person=db.scalar(select(m.Employee).where(m.Employee.display_name=='New Local Person'));new_id=new_person.id
    linked=directory_id=db.scalar(select(m.EmployeeContextLink.rfone_account_id).where(m.EmployeeContextLink.employee_id==new_id))
    check('New person has non-login account',db.get(m.RFOneAccount,linked).status=='INACTIVE' and db.get(m.RFOneAccount,linked).password_hash=='!')
new_target='employee:'+str(new_id)
check('Reject missing dismissal date',post(action='person_dismiss',person=new_target,dismissal_date='',tab='people').status_code==422)
check('Reject invalid dismissal date',post(action='person_dismiss',person=new_target,dismissal_date='oops',tab='people').status_code==422)
check('Reject future dismissal date',post(action='person_dismiss',person=new_target,dismissal_date='2999-01-01',tab='people').status_code==422)
check('Dismiss person with date',post(action='person_dismiss',person=new_target,dismissal_date='2026-01-01',tab='people').status_code==302)
with SessionFactory() as db:
    check('Dismissed is inactive and date retained',db.get(m.Employee,new_id).active is False and db.scalar(select(p.ProfileEvent).where(p.ProfileEvent.action=='PERSON_DISMISSED')).details['dismissal_date']=='2026-01-01')
    check('Dismissed absent from active options',new_id not in [v.id for v in p.directory.employee_options(db)])
check('Cannot assign dismissed person',post(action='membership',person=new_target,company_id=other_id,tab='people').status_code==422)
check('Creation rollback on invalid role',post(action='person_create',name='Rollback Person',company_ids=[str(company_id)],person_roles=json.dumps([{'company_id':company_id,'role_id':99999,'area_id':area_id}]),tab='people').status_code==422)
with SessionFactory() as db:check('Invalid creation leaves no person',db.scalar(select(m.Employee.id).where(m.Employee.display_name=='Rollback Person')) is None)
access_page=owner.get(f'/admin/accounts/{user_id}/access?from_person=account:{user_id}')
check('Person authorization page opens',access_page.status_code==200 and 'Back to person' in access_page.get_data(as_text=True))
check('Mismatched person rejected',owner.get(f'/admin/accounts/{user_id}/access?from_person=employee:999999').status_code==400)
check('Personal permissions save',owner.post(f'/admin/accounts/{user_id}/access',data={'csrf_token':token,'from_person':target,'access_BANK':'all','role_BANK':''}).status_code==302)
with SessionFactory() as db:check('Personal authorization persisted on linked account',db.scalar(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==user_id,m.RFOneAccountDomainAccess.domain_code=='BANK')).enabled)
check('Nonadministrator cannot edit personal grants',staff.get(f'/admin/accounts/{user_id}/access').status_code==403)
check('Person button opens their canonical access page',post(action='person_access',person=target,tab='people').location.endswith(f'/access?from_person=account:{user_id}'))
with SessionFactory() as db:
    person=p.directory.create_person(db,display_name='Existing unlinked person');db.commit();unlinked_id=person.id
check('Unlinked person receives account shell',post(action='person_access',person=f'employee:{unlinked_id}',tab='people').status_code==302)
with SessionFactory() as db:
    aid=db.scalar(select(m.EmployeeContextLink.rfone_account_id).where(m.EmployeeContextLink.employee_id==unlinked_id))
    check('Provisioned account cannot log in',db.get(m.RFOneAccount,aid).status=='INACTIVE' and db.get(m.RFOneAccount,aid).password_hash=='!')
check('Repeated opening reuses account',f'/admin/accounts/{aid}/access' in post(action='person_access',person=f'employee:{unlinked_id}',tab='people').location)
print(json.dumps({'checks_passed':len(passed),'checks':passed},indent=2))
_engine.dispose();testdir.cleanup()
