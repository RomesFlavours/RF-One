"""REGISTRY_MULTISITE_001 — data step of the rollback (and of the roll-forward after it).

The previous code derives the EMPLOYEE status from every card link (`person_employee_links`). The new
Training entry links a Trainee to a card too (card event TRAINING_LINK). If the previous Registry, Training
or Tips images are restored, those Trainees would be shown as Employees. Before restoring them, the links
written by the Training entry for people who are not Employees are set aside (recorded in a JSON file and
removed); after the roll-forward they are put back. Nothing else is touched: cards, site assignments,
POS IDs (Clover links), Tips records and events stay as they are.

    python registry_multisite_rollback.py --url <db url> plan
    python registry_multisite_rollback.py --url <db url> detach --record links.json [--apply]
    python registry_multisite_rollback.py --url <db url> reattach --record links.json [--apply]

Without --apply nothing is written (dry run). `plan` also lists what a restored previous Registry page
would show in its former «Clover identities to confirm» queue (every Clover link without a person).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

TRAINEE_LINKS_SQL = """
    SELECT l.employee_id, l.person_id, l.linked_by_id, l.linked_at FROM person_employee_links l
    WHERE l.employee_id IN (SELECT employee_id FROM employee_directory_events
                            WHERE action = 'TRAINING_LINK' AND employee_id IS NOT NULL)
      AND l.person_id NOT IN (SELECT person_id FROM person_company_statuses WHERE code = 'EMPLOYEE')
    ORDER BY l.employee_id"""
UNLINKED_CLOVER_SQL = """
    SELECT id, merchant_id, external_employee_id, state FROM employee_clover_links
    WHERE employee_id IS NULL ORDER BY id"""


def _rows(conn, sql, **params):
    return [dict(row._mapping) for row in conn.execute(text(sql), params)]


def plan(conn):
    return {"trainee_links_to_set_aside": _rows(conn, TRAINEE_LINKS_SQL),
            "previous_registry_queue_would_show": _rows(conn, UNLINKED_CLOVER_SQL)}


def detach(conn, record: Path, apply: bool):
    links = _rows(conn, TRAINEE_LINKS_SQL)
    if apply:
        record.write_text(json.dumps(links, indent=2, default=str), encoding="utf-8")
        for link in links:
            conn.execute(text("DELETE FROM person_employee_links WHERE employee_id = :e AND person_id = :p"),
                         {"e": link["employee_id"], "p": link["person_id"]})
    return {"applied": apply, "set_aside": links, "record": str(record)}


def reattach(conn, record: Path, apply: bool):
    links = json.loads(record.read_text(encoding="utf-8"))
    restored, skipped = [], []
    for link in links:
        taken = conn.execute(text("SELECT person_id FROM person_employee_links WHERE employee_id = :e"),
                             {"e": link["employee_id"]}).scalar()
        if taken is not None:
            skipped.append({**link, "reason": "card already linked to person %s" % taken})
            continue
        restored.append(link)
        if apply:
            conn.execute(text("INSERT INTO person_employee_links (employee_id, person_id, linked_by_id, linked_at) "
                              "VALUES (:employee_id, :person_id, :linked_by_id, :linked_at)"), link)
    return {"applied": apply, "restored": restored, "skipped": skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("command", choices=("plan", "detach", "reattach"))
    parser.add_argument("--record")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.command != "plan" and not args.record:
        parser.error("--record is required")
    engine = create_engine(args.url)
    try:
        with engine.connect() as conn:
            if args.command == "plan":
                result = plan(conn)
            elif args.command == "detach":
                result = detach(conn, Path(args.record), args.apply)
            else:
                result = reattach(conn, Path(args.record), args.apply)
            conn.commit() if args.apply else conn.rollback()
    finally:
        engine.dispose()
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
