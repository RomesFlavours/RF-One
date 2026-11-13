from pathlib import Path
repo=Path('tmp/git-anagrafica-release');p=repo/'03 Software/RF-One Web/tests/test_role_company_http.py';t=p.read_text(encoding='utf-8');i=t.index('print(json.dumps(');t=t[:i]+'''check('Accounts removed from MyRF','href="/admin/accounts"' not in home)
check('Registry exposes contact and reset controls','name="email"' in default_page and 'name="phone"' in default_page and 'id="person-reset-password"' in default_page)
with SessionFactory() as db:
    account=db.get(m.RFOneAccount,user_id);account.email='login@example.com';from datetime import datetime,timezone
    account.email_verified_at=datetime.now(timezone.utc);db.commit();login_email=account.email;verified=account.email_verified_at;version=account.session_version;hash_before=account.password_hash
check('External contacts save',post(action='person_save',person=target,name='Updated Staff',company_ids=[str(company_id)],person_roles=json.dumps(payload[:1]),email='contact@example.com',phone='+1 (407) 555-0100').status_code==302)
with SessionFactory() as db:
    account=db.get(m.RFOneAccount,user_id)
    check('External contact fields stored',account.contact_email=='contact@example.com' and account.contact_phone=='+1 (407) 555-0100')
    check('Contacts do not alter recovery or credentials',account.email==login_email and account.email_verified_at==verified and account.session_version==version and account.password_hash==hash_before)
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
''' +t[i:];p.write_text(t,encoding='utf-8')
p=repo/'03 Software/RF-One Web/tests/test_home_layout_http.py';t=p.read_text(encoding='utf-8').replace('Settings, alphabetical: Accounts, Legal Entities (admins), Profile,','Settings, alphabetical: Legal Entities (admins), Profile,').replace('Settings rows are Accounts, Legal Entities, Profile, Workweek (alphabetical)','Settings rows are Legal Entities, Profile, Workweek (alphabetical)').replace('["Accounts", "Legal Entities", "Profile", "Workweek"]','["Legal Entities", "Profile", "Workweek"]').replace('["/admin/accounts", "/admin/legal-entities", "/profile", "/admin/workweek"]','["/admin/legal-entities", "/profile", "/admin/workweek"]');p.write_text(t,encoding='utf-8')
