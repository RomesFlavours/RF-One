"""Read the existing RF-One person directory; never create another registry."""
from dataclasses import dataclass
from sqlalchemy import inspect, select

from .. import models as m
from .. import employee_directory as directory


@dataclass(frozen=True)
class PersonView:
    id: int
    full_name: str


def available(db):
    return inspect(db.connection()).has_table('employee_context_links')


def get_person(db, person_id):
    canonical_id = directory.resolve_employee_id(db, person_id)
    person = db.get(m.Employee, canonical_id)
    return PersonView(person.id, person.display_name or 'Name not available') if person else None


def list_people(db):
    """Recipients of NEW interviews: current employees, from the shared
    Employee Directory selector. History keeps using get_person, unfiltered.

    Unrestricted scope is explicit: the Product Owner decided on 2026-11-04
    that Interviews has no requester perimeter (neither site nor
    applicability)."""
    return [PersonView(p.id, p.display_name or 'Name not available')
            for p in directory.interview_employee_options(db, location_ids=None)]


def require_recipient(db, person_id):
    """Re-check at submission: refuses dismissed people; retired IDs count as their record."""
    person = directory.require_active_employee(db, person_id)
    return PersonView(person.id, person.display_name or 'Name not available')


def person_for_account(db, account_id):
    person_id = directory.context_person_id(db, 'RFONE_ACCOUNT', account_id)
    return get_person(db, person_id) if person_id is not None else None


def delivery_account(db, person_id):
    """Require one unambiguous active login; links confer no Domain rights."""
    canonical = directory.resolve_employee_id(db, person_id)
    return delivery_accounts(db).get(canonical)


def delivery_accounts(db):
    matches = {}
    for account in db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.status == 'ACTIVE')):
        try:
            person = person_for_account(db, account.id)
        except ValueError:
            continue  # A conflicting identity chain is not a delivery address.
        if person:
            matches.setdefault(person.id, []).append(account)
    return {person_id: accounts[0] for person_id, accounts in matches.items() if len(accounts) == 1}
