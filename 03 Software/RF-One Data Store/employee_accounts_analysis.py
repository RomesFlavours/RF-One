"""EMPLOYEE_ACCOUNTS_001 — read-only analysis of existing data before migration.

Lists every record incompatible with the approved rules and what the release
would change, without changing anything:

    python employee_accounts_analysis.py <database-url> [--rehearse]

The connection is opened read-only. `--rehearse` (only for a disposable copy,
never for AWS) also applies the cessation access rule inside a transaction that
is rolled back, to show the exact account changes. Output is JSON with ids and
names only (no emails, phones or credentials).
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from rfone_data_store import models as m
from rfone_data_store import employee_directory as directory


def analyse(db: Session) -> dict:
    states = directory.employment_states(db)
    people = {p.id: p for p in db.scalars(directory.canonical_employees())}
    accounts = {a.id: a for a in db.scalars(select(m.RFOneAccount))}
    account_links = list(db.execute(select(m.EmployeeContextLink.employee_id, m.EmployeeContextLink.rfone_account_id)
                                    .where(m.EmployeeContextLink.rfone_account_id.is_not(None))))
    per_person = Counter(person for person, _ in account_links)
    by_person = {}
    for person, account_id in account_links:
        by_person.setdefault(person, []).append(account_id)
    links = list(db.scalars(select(m.EmployeeCloverLink)))
    locations = {loc.id: loc.name for loc in db.scalars(select(m.Location))}

    def who(person_id):
        person = people.get(person_id)
        return {"id": person_id, "name": person.display_name if person else None}

    def account_view(account_id):
        a = accounts[account_id]
        return {"id": a.id, "username": a.username, "status": a.status, "is_admin": a.is_admin, "is_owner": a.is_owner}

    ceased_with_active_account, ceased_kept = [], []
    other_admins = lambda account_id: sum(1 for a in accounts.values()
                                          if a.is_admin and a.status == "ACTIVE" and a.id != account_id)
    for person_id, state in states.items():
        if state.status != directory.STATUS_CEASED:
            continue
        for account_id in by_person.get(person_id, []):
            if accounts[account_id].status != "ACTIVE":
                continue
            row = {**who(person_id), "ceased_at": str(state.ceased_at), "account": account_view(account_id)}
            if accounts[account_id].is_owner or (accounts[account_id].is_admin and not other_admins(account_id)):
                ceased_kept.append(row)
            else:
                ceased_with_active_account.append(row)

    # Accounts reaching a person only through the Training/ActingIdentity chain.
    indirect = []
    for account_id in accounts:
        if any(a == account_id for _, a in account_links):
            continue
        try:
            person_id = directory.context_person_id(db, "RFONE_ACCOUNT", account_id)
        except ValueError as exc:
            indirect.append({"account": account_view(account_id), "conflict": str(exc)})
            continue
        if person_id is not None:
            indirect.append({"account": account_view(account_id), "person": who(person_id)})

    waiting = [l for l in links if directory.pending_requires_review(db, l)]
    punches = directory.held_punch_counts(db, waiting)
    status_counts = Counter(state.status for state in states.values())
    return {
        "summary": {
            "people": len(people), "by_status": dict(status_counts),
            "accounts": len(accounts), "account_links": len(account_links),
            "external_accounts": len(set(accounts) - {a for _, a in account_links}),
            "clover_links": len(links), "roster_sites": sorted(locations.get(s, s) for s in directory.roster_location_ids(db)),
        },
        "blocking_migration_people_with_several_accounts": [
            {**who(person), "accounts": [account_view(a) for a in by_person[person]]}
            for person, count in per_person.items() if count > 1],
        "would_disable_ceased_accounts": ceased_with_active_account,
        "would_keep_owner_or_last_admin": ceased_kept,
        "active_employees_without_account": [
            {**who(person_id), "sites": [locations.get(p.location_id) for p in state.positions
                                         if p.status == directory.POSITION_ACTIVE]}
            for person_id, state in states.items()
            if state.status == directory.STATUS_ACTIVE and person_id not in by_person],
        "ceased_without_account": [who(pid) for pid, s in states.items()
                                   if s.status == directory.STATUS_CEASED and pid not in by_person],
        "ceased": [{**who(pid), "ceased_at": str(s.ceased_at),
                    "positions": [{"site": locations.get(p.location_id), "last_clock_in": str(p.last_clock_in)}
                                  for p in s.positions]}
                   for pid, s in states.items() if s.status == directory.STATUS_CEASED],
        "partially_ended": [{**who(pid), "ended_sites": [locations.get(p.location_id) for p in s.positions
                                                         if p.status == directory.POSITION_ENDED]}
                            for pid, s in states.items() if s.status == directory.STATUS_ACTIVE
                            and any(p.status == directory.POSITION_ENDED for p in s.positions)],
        "manually_archived": [{**who(pid), "has_punches": s.is_employee,
                               "active_positions": [locations.get(p.location_id) for p in s.positions
                                                    if p.status == directory.POSITION_ACTIVE]}
                              for pid, s in states.items() if s.status == directory.STATUS_ARCHIVED],
        "confirmed_people_without_punches": [
            {**who(pid), "clover_sites": [locations.get(p.location_id) for p in s.positions],
             "account": account_view(by_person[pid][0]) if pid in by_person else None}
            for pid, s in states.items() if s.status == directory.STATUS_NOT_EMPLOYEE and s.positions],
        "rf1_people_without_clover_or_punches": len([1 for s in states.values()
                                                     if s.status == directory.STATUS_NOT_EMPLOYEE and not s.positions]),
        "pending_with_punches": [{"link_id": l.id, "site": locations.get(l.location_id),
                                  "name": (l.snapshot or {}).get("name"), "punches": punches[l.id]}
                                 for l in waiting if punches.get(l.id)],
        "pending_without_punches": [{"link_id": l.id, "site": locations.get(l.location_id),
                                     "name": (l.snapshot or {}).get("name"), "state": l.state}
                                    for l in waiting if not punches.get(l.id)],
        "accounts_reaching_a_person_only_indirectly": indirect,
    }


def rehearse(db: Session) -> dict:
    """Disposable copies only: apply the access rule, report it, roll back."""
    changed = directory.enforce_cessation_access(db, run_id=None)
    events = list(db.scalars(select(m.EmployeeDirectoryEvent).where(
        m.EmployeeDirectoryEvent.action.in_(("ACCESS_DISABLED", "ACCESS_KEPT")))))
    result = {"disabled_account_ids": changed,
              "events": [{"action": e.action, "employee_id": e.employee_id, **e.details} for e in events]}
    db.rollback()
    return result


def main(argv):
    url = argv[1]
    connect_args = {"options": "-c default_transaction_read_only=on"} if url.startswith("postgresql") and "--rehearse" not in argv else {}
    engine = create_engine(url, connect_args=connect_args)
    try:
        with Session(engine) as db:
            out = analyse(db)
            db.rollback()
            if "--rehearse" in argv:
                out["rehearsal"] = rehearse(db)
    finally:
        engine.dispose()
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv)
