"""Validation/test fixtures only — never imported by production code (REGISTRY_MULTISITE_001).

Since Clover's staff list no longer creates Registry cards, validation suites that need known people create
the cards and the POS IDs the way an operator would have recorded them: one card per record and a confirmed
POS link at the record's site.
"""
from __future__ import annotations

from sqlalchemy import select

from . import models as m


def cards_with_pos_ids(session, *, location_id: int, merchant_id: str, records) -> dict[str, int]:
    """{Clover employee id: card id}; existing POS links are reused, so repeating it changes nothing."""
    result = {}
    for raw in records:
        external_id = raw["id"]
        link = session.scalar(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.merchant_id == merchant_id, m.EmployeeCloverLink.external_employee_id == external_id))
        if link is None or link.employee_id is None:
            card = m.Employee(display_name=raw.get("name"), custom_id=raw.get("customId"))
            session.add(card)
            session.flush()
            if link is None:
                link = m.EmployeeCloverLink(location_id=location_id, merchant_id=merchant_id,
                                            external_employee_id=external_id, state="MANUAL")
                session.add(link)
            link.employee_id, link.state = card.id, "MANUAL"
            session.flush()
        result[external_id] = link.employee_id
    return result
