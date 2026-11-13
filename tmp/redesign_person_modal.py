from pathlib import Path
p=Path('03 Software/RF-One Data Store/rfone_data_store/access_profiles.py');t=p.read_text(encoding='utf-8');t+='''

def create_profile_person(db,*,name,company_ids,assignments,actor=None):
    person=directory.create_person(db,display_name=_name(name),account_id=actor)
    if hasattr(directory,'ensure_employee_account'):
        directory.ensure_employee_account(db,person)
    else:
        from uuid import uuid4
        account=m.RFOneAccount(username='employee-'+uuid4().hex,display_name=person.display_name,password_hash='!',status='INACTIVE',is_admin=False,is_owner=False,session_version=1)
        db.add(account);db.flush()
        db.add(m.EmployeeContextLink(employee_id=person.id,rfone_account_id=account.id));db.flush()
    save_person_profile(db,f'employee:{person.id}',name=name,company_ids=company_ids,assignments=assignments,actor=actor)
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
''';p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/role_profile_routes.py');t=p.read_text(encoding='utf-8').replace("if action=='person_save':", """if action=='person_create':
                        record=profiles.create_profile_person(db,name=request.form.get('name'),company_ids=request.form.getlist('company_ids'),assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id)
                        person=f'employee:{record.id}';anchor='people-table'
                    elif action=='person_dismiss':
                        profiles.dismiss_profile_person(db,person,dismissal_date=request.form.get('dismissal_date'),actor=account.id)
                        anchor='dismissed-people'
                    elif action=='person_save':""")
# Add read-only dismissed listing with persisted manual date or lifecycle date.
idx=t.index('        events=list(db.scalars(select(profiles.ProfileEvent)')
t=t[:idx]+'''        dismissed_rows=[]
        dismissal_dates={}
        for ev in db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action=='PERSON_DISMISSED').order_by(profiles.ProfileEvent.id)):
            dismissal_dates[ev.details.get('employee_id')]=ev.details.get('dismissal_date')
        for option in directory.employee_options(db,include_inactive=True):
            target=db.get(m.Employee,option.id)
            if not directory.employee_is_active(target,[]):
                dismissed_rows.append({'name':target.display_name or 'Name to complete','date':dismissal_dates.get(target.id) or getattr(target,'dismissed_at',None)})
''' +t[idx:]
t=t.replace("people_rows=people_rows,tab=tab", "people_rows=people_rows,dismissed_rows=dismissed_rows,tab=tab")
p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/templates/role_profiles.html');t=p.read_text(encoding='utf-8').replace('<h2>People & assignments</h2>','<div class="profile-toolbar"><h2>People & assignments</h2><button type="button" data-new-person>Add person</button></div>')
t=t.replace('<tr id="people-empty"', '<tr id="people-empty"')
t=t.replace('\n{% endif %}\n\n<details', '''
<details id="dismissed-people" class="profile-archive"><summary>Dismissis ({{ dismissed_rows|length }})</summary><table><thead><tr><th>Name</th><th>Dismissal date</th></tr></thead><tbody>{% for row in dismissed_rows %}<tr><td>{{ row.name }}</td><td>{{ row.date or 'Not recorded' }}</td></tr>{% else %}<tr><td colspan="2">No dismissed people.</td></tr>{% endfor %}</tbody></table></details>
{% endif %}

<details''',1)
t=t.replace('<label>Name <input name="name" maxlength="255" required></label>\n<fieldset>', '<label class="person-name-field">Name <input name="name" maxlength="255" placeholder="Full name" required></label>\n<fieldset>',1)
t=t.replace('<button type="button" disabled title="Available in a future update">Other system authorizations</button>', '''<div class="person-extra"><button type="button" disabled title="Available in a future update">Other system authorizations</button></div>
<section class="person-dismissal" id="person-dismissal"><div><h3>Dismiss person</h3><p>Keep their history and remove them from active selections.</p></div><label>Dismissal date <input type="date" name="dismissal_date" id="person-dismissal-date"></label><button type="submit" id="person-dismiss-button" disabled formnovalidate>Dismiss person</button></section>''')
t=t.replace('?v=2','?v=3');p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/static/js/role-profiles.js');t=p.read_text(encoding='utf-8')
t=t.replace("    p.assignments.forEach(roleRow);dialogs", "    field(editor,'action','person_save');document.getElementById('person-dialog-title').textContent='Edit person';document.getElementById('person-dismissal').hidden=p.key.indexOf('employee:')!==0;document.getElementById('person-dismiss-button').disabled=true;\n    p.assignments.forEach(roleRow);dialogs")
t=t.replace("  editor.addEventListener('submit',syncPersonRoles);", """  var dismissalDate=document.getElementById('person-dismissal-date'),dismissButton=document.getElementById('person-dismiss-button');
  dismissalDate.max=new Date().toISOString().slice(0,10);
  dismissalDate.addEventListener('input',function(){dismissButton.disabled=!dismissalDate.value||!dismissalDate.validity.valid;});
  document.querySelector('[data-new-person]')?.addEventListener('click',function(e){reset('person-dialog');field(editor,'person','');field(editor,'action','person_create');field(editor,'tab','people');roleRows.replaceChildren();document.getElementById('person-dialog-title').textContent='Add person';document.getElementById('person-dismissal').hidden=true;editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.checked=false;cb.disabled=cb.dataset.companyActive==='false';});dialogs['person-dialog'].open(e.currentTarget);});
  editor.addEventListener('submit',function(e){
    if(e.submitter===dismissButton){if(!dismissalDate.value||!dismissalDate.validity.valid){e.preventDefault();return;}field(editor,'action','person_dismiss');}
    syncPersonRoles();
  });""")
t=t.replace("person_save: 'person-dialog'", "person_save: 'person-dialog', person_create: 'person-dialog', person_dismiss: 'person-dialog'")
t=t.replace("if (id === 'person-dialog') { roleRows", "if (id === 'person-dialog') { document.getElementById('person-dialog-title').textContent=action==='person_create'?'Add person':'Edit person'; document.getElementById('person-dismissal').hidden=action==='person_create'||editor.elements.person.value.indexOf('employee:')!==0;dismissButton.disabled=!dismissalDate.value||!dismissalDate.validity.valid; roleRows")
p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/static/css/role-profiles.css');t=p.read_text(encoding='utf-8');t+='''
/* RF1 person editor: wide panel, soft section cards and consistent controls. */
#person-dialog .profile-modal{max-width:1280px;width:100%;padding:0;max-height:94vh;border-radius:18px}
#person-dialog .profile-toolbar{margin:0;padding:1.4rem 2rem;border-bottom:1px solid #e3e8d5;background:#fafbf6}
#person-editor{padding:1.6rem 2rem 0}
#person-editor label{display:flex;flex-direction:column;gap:.45rem;font-size:.95rem;color:#626c51}
#person-editor input:not([type=checkbox]),#person-editor select{font:inherit;color:#303a25;background:#fff;border:1px solid #cbd6b3;border-radius:9px;padding:.8rem 1rem;min-height:48px;box-sizing:border-box;width:100%;margin:0}
#person-editor input:focus,#person-editor select:focus{outline:2px solid #869959;outline-offset:2px}
#person-editor .person-name-field{max-width:640px;margin-bottom:1.4rem;font-weight:600}
#person-editor fieldset{border:1px solid #dce3ca;border-radius:12px;background:#fafbf7;padding:1.2rem 1.4rem;margin:1.2rem 0}
#person-editor legend{font-size:1rem;font-weight:600;color:#344022;padding:0 .5rem}
#person-editor .profile-area-list label{flex-direction:row;align-items:center;background:#fff;border:1px solid #dce3ca;border-radius:9px;padding:.7rem 1rem;gap:.7rem;color:#3e492f}
#person-editor input[type=checkbox]{accent-color:#55652f;width:19px;height:19px}
#person-editor .person-role-row{display:grid;grid-template-columns:1fr 1fr 1fr auto;align-items:end;background:#fff;border-radius:10px;padding:1rem;border:1px solid #e3e8d5;gap:1rem}
#person-editor .person-role-row label{min-width:0;margin:0}
#person-editor .person-extra{margin:1.4rem 0}
#person-editor .person-dismissal{display:flex;align-items:end;gap:1.2rem;flex-wrap:wrap;border-top:1px solid #e3e8d5;padding:1.2rem 0}
#person-editor .person-dismissal[hidden]{display:none}
#person-editor .person-dismissal>div{flex:1;min-width:220px}
#person-editor .person-dismissal h3{margin:0 0 .35rem;font-size:1.05rem}
#person-editor .person-dismissal p{margin:0;color:#778069;font-size:.9rem}
#person-dismiss-button{background:#fff;color:#a13e35;border:1px solid #d6aba5;border-radius:9px;min-height:48px}
#person-dismiss-button:disabled{opacity:.4;cursor:not-allowed}
#person-editor>.btn-row{position:sticky;bottom:0;background:#fff;border-top:1px solid #e3e8d5;margin:0 -2rem;padding:1.1rem 2rem;border-radius:0 0 18px 18px}
@media(max-width:700px){#person-dialog .profile-toolbar{padding:1rem}#person-editor{padding:1rem 1rem 0}#person-editor .person-role-row{grid-template-columns:1fr}#person-editor>.btn-row{margin:0 -1rem;padding:1rem}#person-editor .person-dismissal{align-items:stretch;flex-direction:column}}
''';p.write_text(t,encoding='utf-8')
