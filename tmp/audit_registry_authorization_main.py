"""HTTP acceptance against a disposable SQLite database, with the real shell/auth."""
from pathlib import Path
import os,sys,tempfile,re,json
ROOT=Path('C:\\Users\\servi\\AppData\\Local\\RF-One\\Employee Directory\\AWS-20261110T120743Z\\development-source')
sys.path[:0]=[str(ROOT/'RF-One Web'),str(ROOT/'RF-One Data Store')]
testdir=tempfile.TemporaryDirectory(prefix='role-company-http-',dir=Path('C:\\Users\\servi\\.codex\\worktrees\\edee\\RF One\\tmp'),ignore_cleanup_errors=True)
assert Path(testdir.name).resolve().is_relative_to(Path('C:\\Users\\servi\\.codex\\worktrees\\edee\\RF One\\tmp').resolve())
os.environ['RFONE_DATABASE_URL']='sqlite:///'+str(Path(testdir.name)/'test.db').replace('\\','/')
os.environ['RFONE_FLASK_SECRET_KEY']='isolated-http-test-only'
from rfone_data_store import models as m,access_profiles as p
import app as web
from db import SessionFactory,_engine
from sqlalchemy import select,func
m.Base.metadata.create_all(_engine)
web.app.config['TESTING']=True
audit=[]
def record(name,expected,actual,detail=None):
    audit.append({'check':name,'expected':expected,'actual':actual,'passed':expected==actual,'detail':detail})
for domain in web.DOMAINS:
    web.app.add_url_rule('/_audit/gate/'+domain.code,endpoint='audit_'+domain.code,
        view_func=web.require_domain_access(domain.code)(lambda:'allowed'))
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
home=owner.get('/').get_data(as_text=True)
administration=home.split('<div class="domain-name">Administration</div>',1)[1].split('<div class="domain-name">Settings</div>',1)[0]
settings=home.split('<div class="domain-name">Settings</div>',1)[1]
check('Registry in Administration points to new page','href="/admin/roles?tab=people"' in administration and '<strong>Registry' in administration)
check('No Registry duplicate in Settings','/admin/roles' not in settings and 'Anagrafica' not in settings)
check('Legacy directory entry removed from home','href="/administration/employees"' not in home)
check('Registry module title', '<h1>Registry</h1>' in owner.get('/admin/roles?tab=people').get_data(as_text=True))
check('Registry respects administration permissions','href="/admin/roles?tab=people"' not in staff.get('/').get_data(as_text=True))
default_page=owner.get('/admin/roles').get_data(as_text=True)
nav=default_page.split('<nav class="profile-tabs"',1)[1].split('</nav>',1)[0]
check('People tab is first',nav.index('People &amp; assignments')<nav.index('>Roles<') if 'People &amp; assignments' in nav else nav.index('People & assignments')<nav.index('>Roles<'))
check('People opens by default','tab=people' in nav.split('aria-current="page"',1)[0] and 'id="people-table"' in default_page)
check('Unknown tab falls back to People','id="people-table"' in owner.get('/admin/roles?tab=unknown').get_data(as_text=True))
check('Accounts removed from MyRF','href="/admin/accounts"' not in home)
check('Registry exposes contact and reset controls','name="email"' in default_page and 'name="phone"' in default_page and 'id="person-reset-password"' in default_page)
with SessionFactory() as db:
    account=db.get(m.RFOneAccount,user_id);account.email='login@example.com';from datetime import datetime,timezone
    account.email_verified_at=datetime.now(timezone.utc);db.commit();login_email=account.email;verified=account.email_verified_at;version=account.session_version;hash_before=account.password_hash
check('External contacts save',post(action='person_save',person=target,name='Updated Staff',company_ids=[str(company_id)],person_roles=json.dumps(payload[:1]),email='contact@example.com',phone='+1 (407) 555-0100').status_code==302)
with SessionFactory() as db:
    account=db.get(m.RFOneAccount,user_id)
    check('External contact fields stored',account.contact_email=='contact@example.com' and account.contact_phone=='+1 (407) 555-0100')
    check('Contacts do not alter recovery or credentials',account.email==login_email and account.email_verified_at.replace(tzinfo=None)==verified.replace(tzinfo=None) and account.session_version==version and account.password_hash==hash_before)
check('Create employee with contacts',post(action='person_create',name='Contact Person',person_roles='[]',email='person@example.com',phone='+1 555 0123').status_code==302)
with SessionFactory() as db:
    employee=db.scalar(select(m.Employee).where(m.Employee.display_name=='Contact Person'));contact_id=employee.id
    check('Canonical employee owns contact fields',employee.email=='person@example.com' and employee.phone=='+1 555 0123')
check('Omitted contact fields preserve values',post(action='person_save',person=f'employee:{contact_id}',name='Contact Person',person_roles='[]').status_code==302)
with SessionFactory() as db:check('Contacts preserved',db.get(m.Employee,contact_id).email=='person@example.com')
check('Invalid email rejected',post(action='person_save',person=f'employee:{contact_id}',name='Should rollback',person_roles='[]',email='invalid').status_code==422)
check('Long phone rejected',post(action='person_save',person=f'employee:{contact_id}',name='Should rollback',person_roles='[]',phone='1'*65).status_code==422)
with SessionFactory() as db:check('Invalid contact update atomic',db.get(m.Employee,contact_id).display_name=='Contact Person' and db.get(m.Employee,contact_id).email=='person@example.com')
check('Explicit clear contact fields',post(action='person_save',person=f'employee:{contact_id}',name='Contact Person',person_roles='[]',email='',phone='').status_code==302)
with SessionFactory() as db:check('Cleared contact values persist',db.get(m.Employee,contact_id).email is None and db.get(m.Employee,contact_id).phone is None)
reset_open=post(action='person_password',person=f'employee:{unlinked_id}')
check('Registry reset opens canonical existing account',reset_open.status_code==302 and f'/admin/accounts/{aid}/edit#reset-password' in reset_open.location)
with SessionFactory() as db:reset_version=db.get(m.RFOneAccount,aid).session_version
check('Existing reset page survives',owner.get(f'/admin/accounts/{aid}/edit').status_code==200)
check('Reset password CSRF required',owner.post(f'/admin/accounts/{aid}/reset-password',data={'password':'TestNewPass123!','password_confirm':'TestNewPass123!'}).status_code==400)
check('Nonadministrator reset rejected',staff.post(f'/admin/accounts/{aid}/reset-password',data={'csrf_token':'staff-company-token','password':'TestNewPass123!','password_confirm':'TestNewPass123!'}).status_code==403)
check('Password reset works on synthetic account',owner.post(f'/admin/accounts/{aid}/reset-password',data={'csrf_token':token,'password':'TestNewPass123!','password_confirm':'TestNewPass123!'}).status_code==302)
with SessionFactory() as db:
    from werkzeug.security import check_password_hash
    account=db.get(m.RFOneAccount,aid)
    check('Reset changes hash and revokes sessions',check_password_hash(account.password_hash,'TestNewPass123!') and account.session_version==reset_version+1)
    check('Reset does not reactivate inactive account',account.status=='INACTIVE')


OUTPUT='C:\\Users\\servi\\.codex\\worktrees\\edee\\RF One\\tmp\\registry-authorization-main-audit.json'

with SessionFactory() as db:
    employee=m.Employee(display_name='Authorization audit person',active=True)
    au=m.RFOneAccount(username='audit-matrix',display_name='Audit matrix',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1)
    db.add_all([employee,au]);db.flush();au_id,person_id=au.id,employee.id
    db.add(m.EmployeeContextLink(employee_id=person_id,rfone_account_id=au_id));db.flush()
    member=p.membership(db,f'employee:{person_id}',company_id,admin_id)
    role=p.save_role(db,name='Audit permission role',area_ids=[area_id],actor=admin_id)
    p.assign_role(db,membership_id=member.id,role_id=role.id,area_id=area_id,actor=admin_id);audit_role=role.id
    p.membership(db,f'employee:{person_id}',other_id,admin_id);db.commit()
au_client=client(au_id)
with au_client.session_transaction() as browser:browser['rfone_company_context']=company_id
access_url=post(action='person_access',person=f'employee:{person_id}').location
record('Registry resolves canonical account permissions',True,f'/admin/accounts/{au_id}/access' in access_url)
for domain in web.DOMAINS:
    probe='/_audit/gate/'+domain.code
    record('No grant denies '+domain.code,403,au_client.get(probe).status_code)
    values={'csrf_token':token,'access_'+domain.code:'all','role_'+domain.code:'student' if domain.code=='TRAINING' else ''}
    response=owner.post(access_url,data=values)
    record('Registry personal grant saved '+domain.code,302,response.status_code)
    record('Personal grant opens '+domain.code,200,au_client.get(probe).status_code)
    owner.post(access_url,data={'csrf_token':token})
    record('Personal revoke closes '+domain.code,403,au_client.get(probe).status_code)
    response=post(action='permissions',id=audit_role,**{'access_'+domain.code:'all','role_'+domain.code:'student' if domain.code=='TRAINING' else ''})
    record('Role grant opens '+domain.code,200,au_client.get(probe).status_code)
    with au_client.session_transaction() as browser:browser['rfone_company_context']=other_id
    record('Other company denies role '+domain.code,403,au_client.get(probe).status_code)
    with au_client.session_transaction() as browser:browser['rfone_company_context']=company_id
    with SessionFactory() as db:
        account=db.get(m.RFOneAccount,au_id)
        outside=web.shared_session.account_may_enter_domain(db,account,domain.code)
    record('Company role available without shell context '+domain.code,True,outside,'Standalone services must install company context; current library sees None')
    post(action='permissions',id=audit_role)
# Exercise actual mounted destination routes with no grants, not only gate probes.
for domain in web.DOMAINS:
    candidates=[rule for rule in web.app.url_map.iter_rules() if 'GET' in rule.methods and not rule.arguments and not rule.rule.startswith('/_audit/') and getattr(web.app.view_functions[rule.endpoint],'rfone_domain_gate',None)==domain.code]
    if candidates:
        path=min(candidates,key=lambda r:len(r.rule)).rule
        record('Actual URL denied '+domain.code,403,au_client.get(path,follow_redirects=True).status_code,path)
# Selected functions cannot be entered by direct URL after removal.
owner.post(access_url,data={'csrf_token':token,'access_BANK':'selected','items_BANK':'review'})
record('Selected function permits review',200,au_client.get('/_audit/gate/BANK').status_code)
record('Unselected Bank configuration denied',403,au_client.get('/bank/configuration').status_code)
owner.post(access_url,data={'csrf_token':token})
# EMPLOYEES remains an authorization choice, but its Home entry was replaced by admin-only Registry.
owner.post(access_url,data={'csrf_token':token,'access_EMPLOYEES':'all'})
body=au_client.get('/').get_data(as_text=True)
record('Granted employee directory visible in Home',True,'/administration/employees' in body or '/admin/roles' in body)
owner.post(access_url,data={'csrf_token':token})
# Training depends on a separate linked role that role-profile writes do not synchronize.
post(action='permissions',id=audit_role,access_TRAINING='all',role_TRAINING='student')
with SessionFactory() as db:
    import training_integration as ti
    ti.create_and_link_training_identity(db,rfone_account_id=au_id,role_code='student');db.commit()
record('Training student role matches and opens',200,au_client.get('/training',follow_redirects=False).status_code)
post(action='permissions',id=audit_role,access_TRAINING='all',role_TRAINING='trainer')
record('Training role update opens without stale role mismatch',200,au_client.get('/training',follow_redirects=False).status_code)
post(action='permissions',id=audit_role,access_KITCHEN='all')
import sqlite3
src=sqlite3.connect(str(Path(testdir.name)/'test.db'));dst=sqlite3.connect(str(Path(OUTPUT).with_name('registry-auth-synthetic-fixture.db')));src.backup(dst);dst.close();src.close()
Path(OUTPUT).with_name('registry-auth-synthetic-identities.json').write_text(json.dumps({'id':au_id,'company_id':company_id}))
result={'baseline_http_checks_passed' :len(passed),'audit_checks':audit,'failures':[v for v in audit if not v['passed']]}
Path(OUTPUT).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'baseline':len(passed),'audit_checks':len(audit),'failures':len(result['failures'])}))
_engine.dispose();testdir.cleanup()
