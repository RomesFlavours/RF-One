from pathlib import Path
p=Path('tmp/test_role_company_http.py');t=p.read_text(encoding='utf-8');i=t.index("print(json.dumps(");t=t[:i]+'''check('Person button opens their canonical access page',post(action='person_access',person=target,tab='people').location.endswith(f'/access?from_person=account:{user_id}'))
with SessionFactory() as db:
    person=p.directory.create_person(db,display_name='Existing unlinked person');db.commit();unlinked_id=person.id
check('Unlinked person receives account shell',post(action='person_access',person=f'employee:{unlinked_id}',tab='people').status_code==302)
with SessionFactory() as db:
    aid=db.scalar(select(m.EmployeeContextLink.rfone_account_id).where(m.EmployeeContextLink.employee_id==unlinked_id))
    check('Provisioned account cannot log in',db.get(m.RFOneAccount,aid).status=='INACTIVE' and db.get(m.RFOneAccount,aid).password_hash=='!')
check('Repeated opening reuses account',f'/admin/accounts/{aid}/access' in post(action='person_access',person=f'employee:{unlinked_id}',tab='people').location)
''' +t[i:];p.write_text(t,encoding='utf-8')
