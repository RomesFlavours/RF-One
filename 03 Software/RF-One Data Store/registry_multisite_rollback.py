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

The record file is the only copy of the links set aside (Codex review 3):
- `detach --apply` writes it (atomically) BEFORE removing any link; when the file already exists — e.g. a
  repeated detach on the same path — the links it holds are kept and only links not yet recorded are added,
  so a second detach (which finds nothing left to set aside) never empties it; an unreadable file stops the
  detach without touching the database;
- `reattach` fails explicitly (exit code 2, nothing written) when the record is missing, empty or
  unreadable, or when any recorded link would not be back exactly (card linked to another person); after the
  inserts every recorded link is read back and the transaction is rolled back if one is not there.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
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


class RecordError(RuntimeError):
    """The record file cannot be used safely: nothing was written to the database."""


class NotRestored(RuntimeError):
    """Some recorded links are not back after reattach: the transaction is rolled back."""

    def __init__(self, missing):
        super().__init__("%d recorded link(s) not restored; nothing was written" % len(missing))
        self.missing = missing


def _key(link):
    return int(link["employee_id"]), int(link["person_id"])


def read_record(record: Path):
    if not record.exists():
        raise RecordError("record file not found: %s" % record)
    try:
        links = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordError("record file unreadable: %s (%s)" % (record, exc)) from exc
    if not isinstance(links, list) or any(not isinstance(l, dict) or "employee_id" not in l or "person_id" not in l
                                          for l in links):
        raise RecordError("record file is not a list of links: %s" % record)
    return links


def _write_atomically(record: Path, links):
    record.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=record.name + ".", suffix=".tmp", dir=str(record.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(links, out, indent=2, default=str)
            out.flush(); os.fsync(out.fileno())
        os.replace(temp, record)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


def detach(conn, record: Path, apply: bool):
    links = _rows(conn, TRAINEE_LINKS_SQL)
    kept = read_record(record) if record.exists() else []
    recorded = {_key(l) for l in kept}
    added = [l for l in links if _key(l) not in recorded]
    if apply:
        if added or not record.exists():
            _write_atomically(record, kept + added)       # the file holds every link before any is removed
        if {_key(l) for l in read_record(record)} != recorded | {_key(l) for l in links}:
            raise RecordError("record file does not hold every link to set aside: %s" % record)
        for link in links:
            conn.execute(text("DELETE FROM person_employee_links WHERE employee_id = :e AND person_id = :p"),
                         {"e": link["employee_id"], "p": link["person_id"]})
    return {"applied": apply, "set_aside_now": links, "already_recorded": kept,
            "record_holds": len(kept) + len(added), "record": str(record)}


def reattach(conn, record: Path, apply: bool):
    links = read_record(record)
    if not links:
        raise RecordError("record file holds no link: %s" % record)
    restored, already, conflicts = [], [], []
    for link in links:
        owner = conn.execute(text("SELECT person_id FROM person_employee_links WHERE employee_id = :e"),
                             {"e": link["employee_id"]}).scalar()
        if owner is None:
            restored.append(link)
        elif int(owner) == int(link["person_id"]):
            already.append(link)
        else:
            conflicts.append({**link, "reason": "card already linked to person %s" % owner})
    if conflicts:
        raise NotRestored(conflicts)
    if apply:
        for link in restored:
            conn.execute(text("INSERT INTO person_employee_links (employee_id, person_id, linked_by_id, linked_at) "
                              "VALUES (:employee_id, :person_id, :linked_by_id, :linked_at)"), link)
        present = {(int(e), int(p)) for e, p in conn.execute(text(
            "SELECT employee_id, person_id FROM person_employee_links"))}
        missing = [link for link in links if _key(link) not in present]
        if missing:
            raise NotRestored(missing)
    return {"applied": apply, "restored": restored, "already_present": already, "verified": apply,
            "expected": len(links)}


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
            try:
                if args.command == "plan":
                    result = plan(conn)
                elif args.command == "detach":
                    result = detach(conn, Path(args.record), args.apply)
                else:
                    result = reattach(conn, Path(args.record), args.apply)
            except (RecordError, NotRestored) as exc:
                conn.rollback()
                print(json.dumps({"failed": str(exc), "missing": getattr(exc, "missing", None)},
                                 indent=2, default=str, ensure_ascii=False))
                return 2
            conn.commit() if args.apply else conn.rollback()
    finally:
        engine.dispose()
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
