"""Read-only Registry queue over the existing Clover identity hold service."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from rfone_data_store import models as m, employee_directory as directory
from rfone_data_store.technical.connectors.clover.identity_holds import held_shifts


def pending_identities(db):
    rows = []
    for link in db.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.employee_id.is_(None)).order_by(m.EmployeeCloverLink.id)):
        location = db.get(m.Location, link.location_id)
        shifts = held_shifts(db, location_ids=[link.location_id], external_ids={link.external_employee_id})
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
