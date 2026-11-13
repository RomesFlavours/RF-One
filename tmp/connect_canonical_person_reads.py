from pathlib import Path
root=Path('tmp/git-anagrafica-release/03 Software')
p=root/'RF-One Web/role_profile_routes.py';s=p.read_text(encoding='utf-8');needle='        people_rows=[]';s=s.replace(needle,'''        from rfone_data_store import person_reconciliation as identities
        identity_graph = identities.IdentityGraph(db) if load_people and identities.ready(db) else None
        people_rows=[]''',1)
needle="            people_rows.append({'key':key,'account_label':account_label,"
s=s.replace(needle,"""            central_person_id=None;identity_conflict=False
            if identity_graph:
                try:central_person_id=identity_graph.person_id('employee' if kind=='employee' else 'account',identity)
                except ValueError:identity_conflict=True
            people_rows.append({'central_person_id':central_person_id,'identity_conflict':identity_conflict,'key':key,'account_label':account_label,""")
p.write_text(s,encoding='utf-8',newline='\n')
p=root/'RF-One Web/templates/role_profiles.html';s=p.read_text(encoding='utf-8').replace('<td>{{ row.name }}</td>','<td>{{ row.name }}{% if row.central_person_id %}<div class="muted">Person #{{ row.central_person_id }}</div>{% elif row.identity_conflict %}<div class="muted">Identity conflict - review required</div>{% endif %}</td>');p.write_text(s,encoding='utf-8',newline='\n')
p=root/'RF-One Data Store/rfone_data_store/training/workspace.py';s=p.read_text(encoding='utf-8');needle='    return [dict(id=a.id, name=i.display_name,';assert needle in s;s=s.replace(needle,'''    from .. import person_reconciliation as identities
    graph=identities.IdentityGraph(db) if identities.ready(db) else None
    def central(a):
        if graph:
            try:return graph.person_id('training',a.id),False
            except ValueError:return None,True
        return None,False
    # Preserve domain-owned records; expose the same central person reference.
    references={a.id:central(a) for a,i,p,r in rows}
    return [dict(central_person_id=references[a.id][0],identity_conflict=references[a.id][1],id=a.id, name=(graph.rows['person'][references[a.id][0]].full_name if references[a.id][0] else i.display_name),''',1);p.write_text(s,encoding='utf-8',newline='\n')
# Avoid a module import cycle: profile metadata is already registered by workspace.
p=root/'RF-One Data Store/rfone_data_store/person_reconciliation.py';s=p.read_text(encoding='utf-8').replace('from .training.workspace import TrainingStudentProfile\n','');s=s.replace("        if TrainingStudentProfile.__tablename__ in tables:","        from .training.workspace import TrainingStudentProfile\n        if TrainingStudentProfile.__tablename__ in tables:");p.write_text(s,encoding='utf-8',newline='\n')
