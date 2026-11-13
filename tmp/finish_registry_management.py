from pathlib import Path
base=Path('tmp/git-anagrafica-release/03 Software')
p=base/'RF-One Web/templates/admin_account_access.html';s=p.read_text(encoding='utf-8');needle='<p class="muted">{{ account.display_name }} ({{ account.username }})</p>';s=s.replace(needle,needle+'''\n<p><a href="{{ url_for('admin_account_training_link',account_id=account.id) }}">Training identity and history</a> &mdash; link an existing identity explicitly, or create it when needed. Registry remains the source of access permissions.</p>''');p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/tests/test_role_company_http.py';s=p.read_text(encoding='utf-8');needle="with SessionFactory() as db:\n    db.get(m.Employee,person_id).active=False";assert needle in s;s=s.replace(needle,'''# Password administration must consider privileges in every company, not
# just the current trainer's company.
post(action='permissions',id=audit_role,access_TRAINING='all',role_TRAINING='student')
with SessionFactory() as db:
    second_role=p.save_role(db,name='Other company privilege',area_ids=[area_id],actor=admin_id)
    member=p.membership(db,f'employee:{person_id}',other_id,admin_id)
    p.assign_role(db,membership_id=member.id,role_id=second_role.id,area_id=area_id,actor=admin_id)
    db.add(p.RolePermission(role_id=second_role.id,domain_code='BANK',scope='ALL',items=[]));db.commit()
    context=p.company_context.set(company_id)
    try:check('Trainer cannot reset a student privileged in another company',not ti.is_pure_training_student(db,db.get(m.RFOneAccount,au_id)))
    finally:p.company_context.reset(context)
'''+needle);p.write_text(s,encoding='utf-8',newline='\n')
