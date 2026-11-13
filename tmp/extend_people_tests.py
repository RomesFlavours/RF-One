from pathlib import Path
p=Path('tmp/test_role_company_http.py');t=p.read_text(encoding='utf-8').replace("'Effective permissions' in page and 'Manager' in page and 'WP' in page", "'data-edit-person' in page and 'Manager' in page and 'WP' in page")
i=t.index("check('Archive role'")
t=t[:i]+'''check('Table starts collapsed','id="people-table" class="profile-people-table"' in page and 'data-person-filter="role"' in page)
check('Other authorizations disabled','disabled title="Available in a future update">Other system authorizations' in page)
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
''' +t[i:];p.write_text(t,encoding='utf-8')
