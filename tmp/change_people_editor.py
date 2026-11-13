from pathlib import Path
root=Path.cwd(); p=root/'03 Software/RF-One Web/role_profile_routes.py'
t=p.read_text(encoding='utf-8').replace('from collections import defaultdict','import json\nfrom collections import defaultdict')
t=t.replace("if action=='area_save':", """if action=='person_save':
                        profiles.save_person_profile(db,person,name=request.form.get('name'),company_ids=request.form.getlist('company_ids'),assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id)
                        anchor='people-table'
                    elif action=='area_save':""")
t=t.replace('except (ValueError,IntegrityError) as exc:', 'except (ValueError,IntegrityError,TypeError,KeyError) as exc:')
needle="        events=list(db.scalars(select(profiles.ProfileEvent)"
idx=t.index(needle)
t=t[:idx]+'''        people_rows=[]
        for key,label in choices.items():
            kind,identity=key.split(':');identity=int(identity)
            target=db.get(m.Employee if kind=='employee' else m.RFOneAccount,identity)
            condition=profiles.membership_target_condition(db,identity if kind=='employee' else None,identity if kind=='account' else None)
            current=list(db.scalars(select(profiles.CompanyMembership).where(condition,profiles.CompanyMembership.valid_to.is_(None))))
            current_roles=list(db.scalars(select(profiles.RoleProfileAssignment).where(profiles.RoleProfileAssignment.membership_id.in_([v.id for v in current]),profiles.RoleProfileAssignment.valid_to.is_(None))))
            company_map={v.id:v.company_id for v in current}
            people_rows.append({'key':key,'name':target.display_name or 'Name to complete','companies':sorted({v.company_id for v in current}),
                'assignments':[{'company_id':company_map[a.membership_id],'role_id':a.role_id,'area_id':a.area_id} for a in current_roles]})
''' +t[idx:]
t=t.replace("return render_template('role_profiles.html',tab=tab", "return render_template('role_profiles.html',people_rows=people_rows,tab=tab")
t=t.replace("'name':r.name,'areas':pairs[r.id]", "'name':r.name,'active':r.active is not False,'areas':pairs[r.id]")
p.write_text(t,encoding='utf-8')
p=root/'03 Software/RF-One Data Store/rfone_data_store/access_profiles.py'
t=p.read_text(encoding='utf-8')
t+='''

def save_person_profile(db,target,*,name,company_ids,assignments,actor=None):
    """Atomic editor; preserve ended history and central identity, no POS writes."""
    employee,account=person_target(db,target)
    name=_name(name)
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
        directory.update_management(db,record,display_name=name,custom_id=record.custom_id,active=record.active,account_id=actor)
    else:
        before=record.display_name;record.display_name=name
        event(db,'ACCOUNT_NAME_UPDATE',actor,account_id=account,before=before,name=name)
    event(db,'PERSON_PROFILE_SAVE',actor,target=target,company_ids=sorted(company_ids))
    db.flush()
'''
p.write_text(t,encoding='utf-8')
p=root/'03 Software/RF-One Web/templates/role_profiles.html';t=p.read_text(encoding='utf-8')
a=t.index('<h2>People & assignments</h2>');b=t.index('\n{% endif %}\n\n<details',a)
t=t[:a]+'''<h2>People & assignments</h2>
<details id="people-table" class="profile-people-table"><summary>People ({{ people_rows|length }})</summary>
<div class="table-scroll"><table><thead><tr>
<th>Name<label class="sr-only" for="filter-name">Filter Name</label><select id="filter-name" data-person-filter="name"><option value="">All names</option>{% for row in people_rows %}<option value="{{ row.key }}">{{ row.name }}</option>{% endfor %}</select></th>
<th>Company<label class="sr-only" for="filter-company">Filter Company</label><select id="filter-company" data-person-filter="company"><option value="">All companies</option>{% for company in companies %}<option value="{{ company.id }}">{{ company.name }}</option>{% endfor %}</select></th>
<th>Role<label class="sr-only" for="filter-role">Filter Role</label><select id="filter-role" data-person-filter="role"><option value="">All roles</option>{% for role in roles %}<option value="{{ role.id }}">{{ role.name }}</option>{% endfor %}</select></th><th>Actions</th></tr></thead><tbody>
{% for row in people_rows %}<tr data-person-row="{{ row.key }}"><td>{{ row.name }}</td><td>{% for id in row.companies %}<span class="profile-chip">{{ company_by_id[id].name }}</span>{% else %}—{% endfor %}</td><td>{% for item in row.assignments %}<div>{{ role_by_id[item.role_id].name }} · {{ company_by_id[item.company_id].name }} · {{ area_by_id[item.area_id].name }}</div>{% else %}—{% endfor %}</td><td><button type="button" class="link-button" data-edit-person="{{ row.key }}">Edit</button></td></tr>{% endfor %}
<tr id="people-empty" hidden><td colspan="4">No matching people.</td></tr></tbody></table></div></details>
''' +t[b:]
idx=t.index("{% call profile_modal('role-dialog'")
t=t[:idx]+'''{% call profile_modal('person-dialog','Edit person') %}<form method="post" id="person-editor">{{ hidden('person_save','people-table') }}
<label>Name <input name="name" maxlength="255" required></label>
<fieldset><legend>Company · select one or more</legend><div class="profile-area-list">{% for company in companies %}<label><input type="checkbox" name="company_ids" value="{{ company.id }}" data-company-active="{{ 'true' if company.active else 'false' }}"> {{ company.name }}{% if not company.active %} · archived{% endif %}</label>{% endfor %}</div></fieldset>
<fieldset><legend>Roles by company and area</legend><div id="person-role-rows"></div><button type="button" class="link-button" id="person-add-role">Add role</button></fieldset>
<input type="hidden" name="person_roles" value="[]">
<button type="button" disabled title="Available in a future update">Other system authorizations</button>
<div class="btn-row"><button>Save changes</button><button type="button" class="link-button" data-modal-close>Cancel</button></div></form>{% endcall %}
''' +t[idx:]
t=t.replace("'roles':role_payload,'areas':area_payload", "'people':people_rows,'companies':companies|map(attribute='id')|list,'roles':role_payload,'areas':area_payload")
t=t.replace('?v=1','?v=2');p.write_text(t,encoding='utf-8')
