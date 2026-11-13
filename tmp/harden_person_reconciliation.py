from pathlib import Path
base=Path('tmp/git-anagrafica-release/03 Software');p=base/'RF-One Data Store/rfone_data_store/person_reconciliation.py';s=p.read_text(encoding='utf-8');s=s.replace("group['state']='conflict' if group['conflicts'] else 'confirmed' if group['person_ids'] else 'unlinked'","group['state']=('conflict' if group['conflicts'] else 'person-only' if all(k=='person' for k,_ in component)\n                            else 'confirmed' if group['person_ids'] else 'unlinked')")
s=s.replace("for state in ('confirmed','unlinked','conflict')","for state in ('confirmed','unlinked','conflict','person-only')")
pos=s.index('\ndef reconcile(');s=s[:pos]+'''
def validate_link(db, person_id, kind, source_id):
    """Guard every shared link writer against conflicting confirmed bridges."""
    graph=IdentityGraph(db)
    source=graph.by_node.get((kind,source_id));destination=graph.by_node.get(('person',person_id))
    if not source or not destination:raise ValueError('Person or source record not found.')
    if source['conflicts'] or destination['conflicts']:raise ValueError('Conflicting identity links require reconciliation.')
    combined=source['nodes'] | destination['nodes']
    for identity_kind in ('person','account','training'):
        if sum(k==identity_kind for k,_ in combined)>1:
            raise ValueError(f'This link conflicts with another confirmed {identity_kind} identity.')


def person_for_source(db, kind, source_id):
    """Shared read API. An unresolved identity stays unresolved, never guessed."""
    graph=IdentityGraph(db);identity=graph.person_id(kind,source_id)
    return graph.rows['person'].get(identity) if identity is not None else None

'''+s[pos:]
needle='    with db.begin_nested():';s=s.replace(needle,'''    locked=IdentityGraph(db);current=locked.groups.get(key)
    if not current or current['fingerprint']!=fingerprint:raise ValueError('Identity data changed while locking. Reload and review.')
    if person_id and locked.by_node[('person',int(person_id))]['fingerprint']!=destination['fingerprint']:
        raise ValueError('The selected person changed while locking. Reload and review.')
    with db.begin_nested():''',1);p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Data Store/rfone_data_store/people_registry.py';s=p.read_text(encoding='utf-8');needle='    if source is None:\n        raise ValueError("Source record not found.")';assert needle in s;s=s.replace(needle,needle+'''\n    from .person_reconciliation import validate_link
    validate_link(db, person_id, kind, source_id)''',1);p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Data Store/rfone_data_store/student_registry.py';s=p.read_text(encoding='utf-8');needle='def attach(db, person, account, training):';s=s.replace(needle,needle+'''\n    from .person_reconciliation import validate_link
    validate_link(db, person.id, 'account', account.id)
    validate_link(db, person.id, 'training', training.id)''',1);p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/templates/registry_identity_reconciliation.html';s=p.read_text(encoding='utf-8').replace('<strong>{{ report.counts.confirmed }} linked groups</strong>','<strong>{{ report.counts[\'person-only\'] }} central people without operational links</strong> · {{ report.counts.confirmed }} linked groups');p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/person_reconciliation_routes.py';s=p.read_text(encoding='utf-8').replace('from sqlalchemy import select','from sqlalchemy import select\nfrom sqlalchemy.exc import IntegrityError').replace('except (ValueError,KeyError) as exc:', 'except (ValueError,KeyError,IntegrityError) as exc:').replace("db.rollback();flash(str(exc),'error');status=400","db.rollback();flash('Identity links changed or already exist. Reload and review.' if isinstance(exc,IntegrityError) else str(exc),'error');status=400");p.write_text(s,encoding='utf-8',newline='\n')
