from pathlib import Path
p=Path('tmp/clover_15day_local.py');t=p.read_text(encoding='utf-8');t=t.replace("    if instants:last[identity]=max(last.get(identity,0),*instants)","""    if instants:last[identity]=max(last.get(identity,0),*instants)
    for field,timefield in (('overrideInEmployee','overrideInTime'),('overrideOutEmployee','overrideOutTime')):
        other=(row.get(field) or {}).get('id')
        instant=row.get(timefield)
        if other and instant:last[other]=max(last.get(other,0),instant)""")
t=t.replace("path=root/'tmp/clover_15day_local_plan.json'", """    names={e['id']:e.get('name') or ' '.join(str(e.get(k) or '') for k in ('firstName','lastName')).strip() for e in employees}
    plan['unmapped_recent']=[{'external_id':i,'name':names.get(i)} for i in plan['unmapped_recent_identities']]
    normalized=lambda name:' '.join(sorted((name or '').casefold().split()))
    ambiguous={normalized(names.get(i)) for i in plan['unmapped_recent_identities'] if names.get(i)}
    held=[v for v in plan['dismiss'] if normalized(v['name']) in ambiguous]
    for v in held:v['reason']='Recent unlinked Clover identity with matching name; reconciliation required';plan['skip'].append(v)
    plan['dismiss']=[v for v in plan['dismiss'] if v not in held]
path=root/'tmp/clover_15day_local_plan.json'""")
p.write_text(t,encoding='utf-8')
