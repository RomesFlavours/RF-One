from pathlib import Path
p=Path('03 Software/RF-One Data Store/rfone_data_store/access_profiles.py');t=p.read_text(encoding='utf-8');t+='''

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
''';p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/role_profile_routes.py');t=p.read_text(encoding='utf-8').replace("if action=='person_create':", """if action=='person_access':
                        linked=profiles.ensure_profile_account(db,person,account.id)
                        db.commit()
                        return redirect(url_for('admin_account_access',account_id=linked.id,from_person=person))
                    elif action=='person_create':""");p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/templates/role_profiles.html');t=p.read_text(encoding='utf-8');t=t.replace('<a id="person-system-authorizations" class="person-authorizations-button" target="_blank" rel="noopener" hidden>Other system authorizations</a>', '<button type="submit" id="person-system-authorizations" form="person-access-form" hidden>Other system authorizations</button>');needle='<script id="profile-data"';idx=t.index(needle);t=t[:idx]+'''<form id="person-access-form" method="post" target="_blank" rel="noopener">{{ hidden('person_access') }}</form>
''' +t[idx:];p.write_text(t.replace('?v=7','?v=8'),encoding='utf-8')
p=Path('03 Software/RF-One Web/static/js/role-profiles.js');t=p.read_text(encoding='utf-8');a=t.index('    link.hidden=!person');b=t.index('\n  }',a);t=t[:a]+'''    link.hidden=!person;
    var accessForm=document.getElementById('person-access-form');field(accessForm,'person',person?person.key:'');
    help.textContent=person?'Opens Domain Access for this person in a separate window. Your unsaved changes here are retained.':'Save the person first to manage their system authorizations.';''' +t[b:];p.write_text(t,encoding='utf-8')
