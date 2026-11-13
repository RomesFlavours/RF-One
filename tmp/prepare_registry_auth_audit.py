from pathlib import Path
import json
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());source=Path(state['development_source'])
base=(root/'tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_role_company_http.py').read_text(encoding='utf-8')
base=base.replace('ROOT=Path(__file__).resolve().parents[2]','ROOT=Path('+repr(str(source))+')').replace("dir=ROOT.parent,ignore_cleanup_errors=True","dir=Path("+repr(str(root/'tmp'))+"),ignore_cleanup_errors=True").replace('is_relative_to(ROOT.parent.resolve())','is_relative_to(Path('+repr(str(root/'tmp'))+').resolve())')
base=base.replace('passed=[]', '''audit=[]
def record(name,expected,actual,detail=None):
    audit.append({'check':name,'expected':expected,'actual':actual,'passed':expected==actual,'detail':detail})
for domain in web.DOMAINS:
    web.app.add_url_rule('/_audit/gate/'+domain.code,endpoint='audit_'+domain.code,
        view_func=web.require_domain_access(domain.code)(lambda:'allowed'))
passed=[]''',1)
base=base.replace("print(json.dumps({'checks_passed':len(passed),'checks':passed},indent=2))\n_engine.dispose();testdir.cleanup()",'')
append='''
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
    candidates=[rule for rule in web.app.url_map.iter_rules() if 'GET' in rule.methods and not rule.arguments and getattr(web.app.view_functions[rule.endpoint],'rfone_domain_gate',None)==domain.code]
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
record('Training student role matches and opens',200,au_client.get('/training',follow_redirects=True).status_code)
post(action='permissions',id=audit_role,access_TRAINING='all',role_TRAINING='trainer')
record('Training role update opens without stale role mismatch',200,au_client.get('/training',follow_redirects=True).status_code)
result={'baseline_http_checks_passed':len(passed),'audit_checks':audit,'failures':[v for v in audit if not v['passed']]}
Path(OUTPUT).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'baseline':len(passed),'audit_checks':len(audit),'failures':len(result['failures'])}))
_engine.dispose();testdir.cleanup()
'''
base+='\nOUTPUT='+repr(str(root/'tmp/registry-authorization-main-audit.json'))+'\n'+append
(root/'tmp/audit_registry_authorization_main.py').write_text(base,encoding='utf-8')
