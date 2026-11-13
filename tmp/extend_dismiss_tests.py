from pathlib import Path
p=Path('tmp/test_role_company_http.py');t=p.read_text(encoding='utf-8');i=t.index("print(json.dumps(");t=t[:i]+'''check('Dismiss date mandatory',post(action='person_dismiss',person=target,dismissal_date='',tab='people').status_code==422)
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
''' +t[i:];p.write_text(t,encoding='utf-8')
