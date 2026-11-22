"""REGISTRY_MULTISITE_001 — read-only migration check for the new multi-site Registry.

Never writes. Every statement runs in a READ ONLY transaction (PostgreSQL) and is rolled back.

    python registry_multisite_migration_check.py --url <db url> report   [--json out.json]
    python registry_multisite_migration_check.py --url <db url> snapshot --json before.json
    python registry_multisite_migration_check.py compare before.json after.json

report    — people per site (explicit assignments only) and the doubtful cases to verify before the
            switch-over: active cards without a site, dismissed cards with an open assignment, Clover or
            company evidence of MD without an MD assignment, Trainees without a card, former pending Clover
            identities (history only), cards whose person would need the explicit EMPLOYEE status.
snapshot  — fingerprints of what the migration must preserve: identities, POS links, assignments, Tips
            history attributions (shifts, orders, payments, refunds, tip entitlements and payment lines).
compare   — exit status 0 only when every fingerprint is identical and the EMPLOYEE statuses added are
            exactly the list the "before" snapshot expected (`employee_status_expected`, same SQL as
            c7d820261122); a re-run after a rollback/re-upgrade expects and adds nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

HERE = Path(__file__).resolve().parent


def _rows(conn, sql, **params):
    return [dict(row._mapping) for row in conn.execute(text(sql), params)]


def _tables(conn):
    return set(inspect(conn).get_table_names())


def _connect(url):
    engine = create_engine(url)
    conn = engine.connect()
    if engine.dialect.name == "postgresql":
        conn.execute(text("SET TRANSACTION READ ONLY"))
    return engine, conn


CURRENT = "a.valid_from <= CURRENT_TIMESTAMP AND (a.valid_to IS NULL OR a.valid_to > CURRENT_TIMESTAMP)"
SITE_OF = "COALESCE(a.restaurant_id, rl.restaurant_id)"


def report(conn):
    tables = _tables(conn)
    sites = _rows(conn, "SELECT id, name FROM restaurants ORDER BY id")
    assigned = _rows(conn, f"""
        SELECT {SITE_OF} AS site_id, a.employee_id, e.display_name, e.active, a.assignment_source
        FROM employee_assignments a JOIN employees e ON e.id = a.employee_id
        LEFT JOIN restaurant_locations rl ON rl.location_id = a.location_id AND a.restaurant_id IS NULL
        WHERE {CURRENT}""")
    by_site = {site["id"]: sorted({row["employee_id"] for row in assigned if row["site_id"] == site["id"]})
               for site in sites}
    aliases = {row["employee_id"] for row in _rows(conn, "SELECT employee_id FROM employee_identity_aliases")}
    employees = [row for row in _rows(conn, "SELECT id, display_name, active FROM employees ORDER BY id")
                 if row["id"] not in aliases]
    with_site = {row["employee_id"] for row in assigned}
    md = next((site for site in sites if site["name"].rstrip().upper().endswith("MD")), None)
    result = {
        "sites": [{"id": site["id"], "name": site["name"], "people": len(by_site[site["id"]]),
                   "employee_ids": by_site[site["id"]]} for site in sites],
        "doubtful": {
            "active_without_site": [dict(id=row["id"], name=row["display_name"]) for row in employees
                                    if row["active"] is not False and row["id"] not in with_site],
            "dismissed_with_open_assignment": sorted({(row["employee_id"], row["display_name"]) for row in assigned
                                                      if row["active"] is False}),
            "assignments_from_former_clover_sync": sum(1 for row in assigned
                                                       if row["assignment_source"] == "CLOVER_ROLE_SYNC"),
        },
    }
    if md is not None:
        md_links = _rows(conn, """
            SELECT l.employee_id, l.external_employee_id, l.state FROM employee_clover_links l
            JOIN restaurant_locations rl ON rl.location_id = l.location_id
            WHERE rl.restaurant_id = :site AND l.employee_id IS NOT NULL""", site=md["id"])
        result["doubtful"]["md_clover_link_without_md_assignment"] = [
            row for row in md_links if row["employee_id"] not in set(by_site[md["id"]])]
        if "rfone_person_company_memberships" in tables and "rfone_company_contexts" in tables:
            members = _rows(conn, """
                SELECT m.employee_id, m.account_id FROM rfone_person_company_memberships m
                JOIN rfone_company_contexts c ON c.id = m.company_id
                WHERE upper(c.name) = 'MD' AND m.valid_to IS NULL""")
            result["doubtful"]["md_company_member_without_md_assignment"] = [
                row for row in members if row["employee_id"] is None or row["employee_id"] not in set(by_site[md["id"]])]
    pending = _rows(conn, """SELECT id, merchant_id, external_employee_id, state, snapshot
                             FROM employee_clover_links WHERE employee_id IS NULL ORDER BY id""")
    result["doubtful"]["former_pending_clover_identities_history_only"] = [
        dict(id=row["id"], merchant_id=row["merchant_id"], pos_id=row["external_employee_id"], state=row["state"],
             name=(json.loads(row["snapshot"]) if isinstance(row["snapshot"], str) else (row["snapshot"] or {})).get("name"))
        for row in pending]
    if {"person_qualifications", "person_employee_links"} <= tables:
        result["doubtful"]["trainees_without_card"] = _rows(conn, """
            SELECT q.person_id, p.full_name FROM person_qualifications q JOIN candidate_persons p ON p.id = q.person_id
            WHERE q.code = 'STUDENT' AND q.person_id NOT IN (SELECT person_id FROM person_employee_links)""")
        if "person_company_statuses" in tables:
            result["employee_status_to_record"] = _employee_status_to_record(conn)
    return result


def _employee_status_to_record(conn):
    """The exact persons c7d820261122 gives the EMPLOYEE status (same SQL as the migration)."""
    import importlib.util
    path = HERE / "migrations" / "versions" / "c7d820261122_registry_multisite.py"
    spec = importlib.util.spec_from_file_location("c7d8_registry_multisite", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [row["person_id"] for row in _rows(conn, module.EMPLOYEE_STATUS_TO_RECORD_SQL)]


def _digest(rows):
    return {"count": len(rows),
            "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()}


def snapshot(conn):
    tables = _tables(conn)
    queries = {
        "employees": "SELECT id, display_name, email, phone, active, location_id FROM employees ORDER BY id",
        "aliases": "SELECT employee_id, canonical_employee_id FROM employee_identity_aliases ORDER BY employee_id",
        "clover_links": "SELECT id, employee_id, merchant_id, external_employee_id, state FROM employee_clover_links ORDER BY id",
        "assignments": "SELECT id, employee_id, restaurant_id, location_id, restaurant_role_id, operational_area_id, "
                       "valid_from, valid_to, assignment_source FROM employee_assignments ORDER BY id",
        "shifts": "SELECT id, employee_id, location_id, override_in_employee_id, override_out_employee_id FROM shifts ORDER BY id",
        "orders": "SELECT id, employee_id, source_employee_id FROM orders ORDER BY id",
        "payments": "SELECT id, employee_id, source_employee_id FROM payments ORDER BY id",
        "refunds": "SELECT id, employee_id FROM refunds ORDER BY id",
        "context_links": "SELECT id, employee_id FROM employee_context_links ORDER BY id",
        "person_employee_links": "SELECT employee_id, person_id FROM person_employee_links ORDER BY employee_id",
        "person_qualifications": "SELECT person_id, code FROM person_qualifications ORDER BY person_id, code",
        "company_memberships": "SELECT id, employee_id, account_id, company_id, valid_to FROM rfone_person_company_memberships ORDER BY id",
    }
    for name in ("tip_entitlements", "tip_payment_instructions"):
        if name in tables:
            columns = {c["name"] for c in inspect(conn).get_columns(name)}
            if "employee_id" in columns:
                queries[name] = f"SELECT id, employee_id FROM {name} ORDER BY id"
    out = {}
    for name, sql in queries.items():
        table = sql.split(" FROM ")[1].split()[0]
        if table in tables:
            out[name] = _digest(_rows(conn, sql))
    if "person_company_statuses" in tables:
        out["employee_statuses"] = sorted(row["person_id"] for row in _rows(
            conn, "SELECT person_id FROM person_company_statuses WHERE code = 'EMPLOYEE'"))
        if "person_employee_links" in tables and "employee_directory_events" in tables:
            out["employee_status_expected"] = _employee_status_to_record(conn)
    out["alembic"] = [row["version_num"] for row in _rows(conn, "SELECT version_num FROM alembic_version")]
    return out


def compare(before, after):
    differences = [name for name in sorted(set(before) | set(after))
                   if name not in ("alembic", "employee_statuses", "employee_status_expected")
                   and before.get(name) != after.get(name)]
    added_status = sorted(set(after.get("employee_statuses", [])) - set(before.get("employee_statuses", [])))
    removed_status = sorted(set(before.get("employee_statuses", [])) - set(after.get("employee_statuses", [])))
    expected = sorted(before.get("employee_status_expected", []))
    exact = added_status == expected
    return {"identical": not differences and not removed_status and exact, "differences": differences,
            "employee_status_added": added_status, "employee_status_expected": expected,
            "employee_status_exact": exact, "employee_status_removed": removed_status,
            "alembic": [before.get("alembic"), after.get("alembic")]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url")
    parser.add_argument("command", choices=("report", "snapshot", "compare"))
    parser.add_argument("files", nargs="*")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    if args.command == "compare":
        result = compare(*(json.loads(Path(p).read_text(encoding="utf-8")) for p in args.files[:2]))
    else:
        engine, conn = _connect(args.url)
        try:
            result = report(conn) if args.command == "report" else snapshot(conn)
        finally:
            conn.rollback(); conn.close(); engine.dispose()
    payload = json.dumps(result, indent=2, default=str, ensure_ascii=False)
    if args.json:
        Path(args.json).write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if args.command != "compare" or result["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
