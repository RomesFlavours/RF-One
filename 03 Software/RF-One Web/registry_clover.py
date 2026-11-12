"""Read-only Registry queue over the existing Clover identity hold service."""
from datetime import datetime, timezone
from collections import defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy import select, cast, String, or_
from rfone_data_store import models as m, employee_directory as directory
from rfone_data_store.technical.connectors.clover.identity_holds import _shift_employee_refs


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


def pending_identities(db):
    rows = []
    links=list(db.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.employee_id.is_(None)).order_by(m.EmployeeCloverLink.id)))
    held=_held_by_link(db,links)
    locations={loc.id:loc for loc in db.scalars(select(m.Location).where(m.Location.id.in_({link.location_id for link in links})))}
    for link in links:
        location = locations[link.location_id]
        shifts = held[link.id]
        if not shifts and not directory.pending_requires_review(db, link):
            continue
        zone = ZoneInfo(location.timezone) if location.timezone else timezone.utc
        dates = []
        for source_id, raw in shifts.items():
            value = raw.get('inTime')
            start = datetime.fromtimestamp(value / 1000, timezone.utc).astimezone(zone) if isinstance(value, int) else None
            dates.append({'id': source_id, 'start': start.strftime('%Y-%m-%d %H:%M %Z') if start else '—'})
        rows.append({'link': link, 'location': location, 'shifts': sorted(dates, key=lambda row: row['start']),
                     'candidates': directory.candidates(db, link.snapshot or {})})
    return rows
