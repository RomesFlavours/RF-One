from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/registry_clover.py')
s=p.read_text(encoding='utf-8').replace('from datetime import datetime, timezone','from datetime import datetime, timezone\nfrom collections import defaultdict').replace('from sqlalchemy import select','from sqlalchemy import select, cast, String, or_').replace('from rfone_data_store.technical.connectors.clover.identity_holds import held_shifts','from rfone_data_store.technical.connectors.clover.identity_holds import _shift_employee_refs')
pos=s.index('\ndef pending_identities')
s=s[:pos]+'''
def _held_by_link(db, links):
    """One mirror scan per site, preserving each external ID's latest snapshot.

    Matching remains SQL LIKE on the same JSON cast as held_shifts. In particular,
    a shift reassigned between external IDs must not erase the older ID's view.
    This is a presentation read only; attribution still uses the shared service.
    """
    grouped=defaultdict(list)
    for link in links:grouped[link.location_id].append(link)
    result={link.id:{} for link in links}
    for location_id, site_links in grouped.items():
        ids=list(dict.fromkeys(link.external_employee_id for link in site_links))
        matches=[cast(m.SourceRecord.raw_json,String).like(f'%"{identity}"%') for identity in ids]
        query=select(m.SourceRecord.source_id,m.SourceRecord.raw_json,*matches).join(
            m.IngestionRun,m.IngestionRun.id==m.SourceRecord.ingestion_run_id).where(
            m.SourceRecord.entity_type=='shift',m.IngestionRun.location_id==location_id,
            or_(*matches)).order_by(m.SourceRecord.id)
        latest={identity:{} for identity in ids}
        for source_id,raw,*flags in db.execute(query):
            if isinstance(raw,dict):
                for identity,matched in zip(ids,flags):
                    if matched:latest[identity][source_id]=raw
        source_ids=list({source_id for shifts in latest.values() for source_id in shifts})
        canonical=set()
        for offset in range(0,len(source_ids),400):
            canonical.update(db.scalars(select(m.Shift.source_shift_id).where(
                m.Shift.source_shift_id.in_(source_ids[offset:offset+400]))))
        for link in site_links:
            result[link.id]={source_id:raw for source_id,raw in latest[link.external_employee_id].items()
                if source_id not in canonical and _shift_employee_refs(raw)[0]==link.external_employee_id}
    return result

'''+s[pos:]
s=s.replace("    for link in db.scalars(select(m.EmployeeCloverLink).where(\n            m.EmployeeCloverLink.employee_id.is_(None)).order_by(m.EmployeeCloverLink.id)):","    links=list(db.scalars(select(m.EmployeeCloverLink).where(\n            m.EmployeeCloverLink.employee_id.is_(None)).order_by(m.EmployeeCloverLink.id)))\n    held=_held_by_link(db,links)\n    locations={loc.id:loc for loc in db.scalars(select(m.Location).where(m.Location.id.in_({link.location_id for link in links})))}\n    for link in links:")
s=s.replace('location = db.get(m.Location, link.location_id)','location = locations[link.location_id]').replace('shifts = held_shifts(db, location_ids=[link.location_id], external_ids={link.external_employee_id})','shifts = held[link.id]')
p.write_text(s,encoding='utf-8',newline='\n')
