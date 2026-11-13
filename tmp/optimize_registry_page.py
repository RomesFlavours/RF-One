from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/role_profile_routes.py')
s=p.read_text();s=s.replace('from sqlalchemy import select','from sqlalchemy import select, or_')
start=s.index('            for member,company in db.execute(');end=s.index("        return {'registry_it'",start)
block=s[start:end]
# Keep summary semantics but defer its two global reads until a template asks.
s=s[:start]+'''        def person_summary(kind, identity):
            if not getattr(g, '_registry_summaries_loaded', False):
                with SessionFactory() as db:
'''+''.join('    '+line+'\n' for line in block.splitlines())+'''                g._registry_summaries_loaded = True
            return summaries[(kind, identity)]
'''+s[end:]
s=s.replace("'person_profile_summary':lambda kind,identity:summaries[(kind,identity)]}","'person_profile_summary':person_summary}")
s=s.replace('    def target_choices(db):','    def target_choices(db, account_people, accounts):')
s=s.replace("        for account in db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.status=='ACTIVE').order_by(m.RFOneAccount.display_name)):\n            if directory.context_person_id(db,'RFONE_ACCOUNT',account.id) is None:","        for account in sorted((a for a in accounts if a.status == 'ACTIVE'), key=lambda a:a.display_name):\n            if account_people[account.id] is None:")
s=s.replace('        choices=target_choices(db)', '''        # Presentation-only snapshot, scoped to this render. Authorization and
        # all POST operations continue to use the authoritative shared services.
        load_people = tab == 'people'
        accounts = list(db.scalars(select(m.RFOneAccount))) if load_people or person else []
        account_by_id = {a.id:a for a in accounts}
        account_people = {a.id:directory.context_person_id(db,'RFONE_ACCOUNT',a.id) for a in accounts}
        accounts_by_person = defaultdict(list)
        for aid, employee_id in account_people.items():
            if employee_id is not None:accounts_by_person[employee_id].append(aid)
        choices=target_choices(db, account_people, accounts) if load_people else {}
        def membership_condition(kind, identity):
            if kind == 'account':return profiles.CompanyMembership.account_id == identity
            return or_(profiles.CompanyMembership.employee_id == identity,
                       profiles.CompanyMembership.account_id.in_(accounts_by_person[identity]))''')
s=s.replace("condition=profiles.membership_target_condition(db,employee_id=identity if kind=='employee' else None,account_id=identity if kind=='account' else None)","condition=membership_condition(kind, identity)")
s=s.replace("linked=next((aid for aid in db.scalars(select(m.RFOneAccount.id)) if directory.context_person_id(db,'RFONE_ACCOUNT',aid)==identity),None)","linked=next(iter(accounts_by_person[identity]),None)")
start=s.index('        people_rows=[]');end=s.index('        dismissed_rows=[]',start)
s=s[:start]+'''        people_rows=[]
        current_by_employee=defaultdict(list);current_by_account=defaultdict(list)
        roles_by_membership=defaultdict(list)
        if load_people:
            for member in db.scalars(select(profiles.CompanyMembership).where(profiles.CompanyMembership.valid_to.is_(None))):
                if member.employee_id is not None:current_by_employee[member.employee_id].append(member)
                if member.account_id is not None:current_by_account[member.account_id].append(member)
            for assignment in db.scalars(select(profiles.RoleProfileAssignment).where(profiles.RoleProfileAssignment.valid_to.is_(None))):
                roles_by_membership[assignment.membership_id].append(assignment)
            # Keep Employee objects alive in the identity map throughout rendering.
            people_by_id={p.id:p for p in db.scalars(select(m.Employee))}
        for key,label in choices.items() if load_people else []:
            kind,identity=key.split(':');identity=int(identity)
            target=people_by_id.get(identity) if kind=='employee' else account_by_id.get(identity)
            related=accounts_by_person[identity] if kind=='employee' else [identity]
            current=list(current_by_employee[identity]) if kind=='employee' else []
            for aid in related:current.extend(current_by_account[aid])
            current=list({v.id:v for v in current}.values())
            current_roles=sorted((a for v in current for a in roles_by_membership[v.id]),key=lambda a:a.id)
            company_map={v.id:v.company_id for v in current}
            account_ids=related
            access_url=url_for('admin_account_access',account_id=account_ids[0],from_person=key) if len(account_ids)==1 else None
            linked_account=account_by_id[account_ids[0]] if len(account_ids)==1 else None
            account_label=f'{linked_account.username} · {linked_account.status}' if linked_account else 'No unique RF1 account linked'
            people_rows.append({'key':key,'account_label':account_label,'email':target.email if kind=='employee' else target.contact_email,'phone':target.phone if kind=='employee' else target.contact_phone,'access_url':access_url,'name':target.display_name or 'Name to complete','companies':sorted({v.company_id for v in current}),
                'assignments':[{'company_id':company_map[a.membership_id],'role_id':a.role_id,'area_id':a.area_id} for a in current_roles]})
'''+s[end:]
start=s.index('        for ev in db.scalars(');end=s.index('        events=list(',start)
block=s[start:end];s=s[:start]+"        clover_people = directory.employee_options(db, include_inactive=True) if load_people else []\n        if load_people:\n"+''.join('    '+line+'\n' for line in block.splitlines())+s[end:]
s=s.replace('for option in directory.employee_options(db,include_inactive=True):','for option in clover_people:')
s=s.replace('clover_people=directory.employee_options(db, include_inactive=True),','clover_people=clover_people,')
p.write_text(s,encoding='utf-8',newline='\n')
