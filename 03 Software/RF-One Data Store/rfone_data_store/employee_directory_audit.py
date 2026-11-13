"""Read-only, pre-migration employee/account compatibility inventory.

Run with RFONE_DATABASE_URL set:  python -m rfone_data_store.employee_directory_audit
Never prints credentials or personal contacts, only internal IDs and counts.
Works against the previous d9e220261029 schema as well as the new revision.
`blocking` lists what migration e3f120261103 refuses before any change.
"""
import json
import os
from sqlalchemy import create_engine, text


def audit(connection):
    rows = []
    for row in connection.execute(text("""
        SELECT e.id, e.source_employee_id IS NOT NULL AS source_backed, e.active,
          (SELECT count(*) FROM employee_context_links c WHERE c.employee_id=e.id AND c.rfone_account_id IS NOT NULL) AS accounts,
          (SELECT count(*) FROM employee_clover_links l WHERE l.employee_id=e.id) AS clover_links,
          (SELECT count(*) FROM shifts s WHERE s.employee_id=e.id AND (s.clock_in IS NOT NULL OR s.clock_out IS NOT NULL)) AS shifts,
          (SELECT count(*) FROM shifts s WHERE s.employee_id=e.id AND s.location_id IS NULL AND (s.clock_in IS NOT NULL OR s.clock_out IS NOT NULL)) AS unscoped_shifts
        FROM employees e WHERE e.id NOT IN (SELECT employee_id FROM employee_identity_aliases)
        ORDER BY e.id
    """)).mappings():
        rows.append(dict(row))
    from .employee_directory import CONFIRMED_ACCOUNT_PAIRS_SQL
    by_person, by_account = {}, {}
    for employee, account in connection.execute(text(CONFIRMED_ACCOUNT_PAIRS_SQL)):
        by_person.setdefault(employee, set()).add(account)
        by_account.setdefault(account, set()).add(employee)
    owners = set(connection.scalars(text("SELECT id FROM rfone_accounts WHERE is_owner")))
    multiple = sorted(identity for identity, accounts in by_person.items() if len(accounts) > 1)
    shared = sorted(identity for identity, people in by_account.items() if len(people) > 1)
    return {
        "blocking": {"employees_with_multiple_confirmed_accounts": multiple,
                     "accounts_confirmed_for_several_employees": shared},
        "employees": len(rows),
        "accounts_reused_from_confirmed_links": sorted(r["id"] for r in rows if r["accounts"] == 0 and r["id"] in by_person),
        "accounts_to_provision": sorted(r["id"] for r in rows if r["accounts"] == 0 and r["id"] not in by_person
                                        and (not r["source_backed"] or r["shifts"] > 0)),
        # No account until a complete Clover clock scan (or explicit link) shows they worked.
        "accounts_deferred_without_clock_evidence": sorted(r["id"] for r in rows if r["accounts"] == 0
            and r["id"] not in by_person and r["source_backed"] and r["shifts"] == 0),
        "no_local_clock_evidence_ids": [r["id"] for r in rows if r["shifts"] == 0],
        "unscoped_clock_evidence_ids": [r["id"] for r in rows if r["unscoped_shifts"] > 0],
        # Previously an RF1 archive flag; complete synchronization now governs these.
        "clover_linked_with_explicit_inactive_flag": [r["id"] for r in rows if r["clover_links"] and r["active"] is False],
        "owner_accounts_linked_to_employees": sorted(identity for identity, accounts in by_person.items() if accounts & owners),
        "source_verification_required": True,
    }


def main():
    engine = create_engine(os.environ["RFONE_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            elif engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")
            print(json.dumps(audit(connection), indent=2, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
