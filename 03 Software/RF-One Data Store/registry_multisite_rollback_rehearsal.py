"""REGISTRY_MULTISITE_001 — local rehearsal of migration, rollback and roll-forward (disposable SQLite).

    python registry_multisite_rollback_rehearsal.py --old-tree <checkout of the live code, e.g. acd44b2>
                                                    [--extra-versions <dir with c4d520261121>] [--keep]

Every phase runs in its own Python process with the Data Store of either this tree (new code) or the
old tree (the code live before the switch), against one disposable SQLite database built by the real
migration chain. Phases:

 1. new  — chain to b2c320261121; seed WP with a legacy linked card (an Employee for the old code), a
           former pending Clover identity and a Training operator; snapshot "before".
 2. new  — alembic upgrade head (c7d820261122); compare: identical, EMPLOYEE added = exactly the list.
 3. new  — the new code writes: a Trainee (direct invitation → card + Training link), a POS ID for the
           Trainee and a POS ID correction of the legacy card; a held order is attributed.
 4. rollback data step — registry_multisite_rollback.py detach (Trainee links set aside), alembic
           downgrade b2c320261121; cards, assignments, POS IDs and Tips attributions unchanged.
 5. old  — the restored previous code reads the data: the Trainee is not an Employee, the legacy card is,
           POS IDs keep attributing work; what the former Registry queue would show is listed.
 6. old worker (proof only, on a throw-away copy) — the previous correction worker imports a new Clover
           name into Registry: this is why the workers are never rolled back to :12.
 7. new worker on the rolled-back database — a new Clover name creates nothing; work is attributed.
 8. roll-forward — reattach, alembic upgrade head; compare: identical, EMPLOYEE added = [] (the Trainee
           stays a Trainee).
 9. optional — with --extra-versions: c4d520261121 after c7d820261122 gives one head; up and down.
Prints one JSON result per phase and exits non-zero on the first failed expectation.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOW_ISO = "2026-11-22T20:00:00+00:00"


# ----------------------------------------------------------------------------------------- orchestration
def _run(tree: Path, phase: str, url: str, *extra: str) -> dict:
    env = dict(os.environ, PYTHONPATH=str(tree), PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--phase", phase, "--tree", str(tree),
                           "--db", url, *extra], cwd=str(tree), env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=1800)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    if proc.returncode or not lines:
        raise SystemExit(f"phase {phase} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
    return json.loads(lines[-1])


def _alembic(tree: Path, url: str, *args: str, extra_versions: str | None = None) -> str:
    env = dict(os.environ, ALEMBIC_DATABASE_URL_OVERRIDE=url, PYTHONIOENCODING="utf-8")
    cmd = [sys.executable, "-m", "alembic"]
    if extra_versions:
        ini = Path(tempfile.mkdtemp()) / "alembic.ini"
        text = (tree / "alembic.ini").read_text(encoding="utf-8")
        locations = os.pathsep.join([(tree / "migrations" / "versions").as_posix(), Path(extra_versions).as_posix()])
        text = text.replace("[alembic]", f"[alembic]\nversion_locations = {locations}", 1)
        text = text.replace("%(here)s", tree.as_posix())
        ini.write_text(text, encoding="utf-8")
        cmd += ["-c", str(ini)]
    proc = subprocess.run(cmd + list(args), cwd=str(tree), env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=1800)
    if proc.returncode:
        raise SystemExit(f"alembic {' '.join(args)} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return proc.stdout + proc.stderr


def _check(script: str, url: str, *args: str) -> dict:
    proc = subprocess.run([sys.executable, str(HERE / script), "--url", url, *args], cwd=str(HERE),
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    start = proc.stdout.find("{")
    if start < 0:
        raise SystemExit(f"{script} {' '.join(args)} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout[start:])


def _compare(before: Path, after: Path) -> dict:
    proc = subprocess.run([sys.executable, str(HERE / "registry_multisite_migration_check.py"), "compare",
                           str(before), str(after)], cwd=str(HERE), capture_output=True, text=True, encoding="utf-8")
    return json.loads(proc.stdout[proc.stdout.find("{"):])


def _expect(condition: bool, message: str, detail=None):
    if not condition:
        raise SystemExit(f"EXPECTATION FAILED: {message}\n{json.dumps(detail, indent=2, default=str)}")


def orchestrate(args):
    new_tree, old_tree = HERE, Path(args.old_tree) / "03 Software" / "RF-One Data Store"
    work = Path(tempfile.mkdtemp(prefix="registry_rollback_"))
    db = work / "rehearsal.db"
    url = f"sqlite:///{db.as_posix()}"
    results = {}
    try:
        _alembic(new_tree, url, "upgrade", "b2c320261121")
        results["1_seed"] = seed = _run(new_tree, "seed", url)
        _check("registry_multisite_migration_check.py", url, "snapshot", "--json", str(work / "before.json"))
        _alembic(new_tree, url, "upgrade", "head")
        _check("registry_multisite_migration_check.py", url, "snapshot", "--json", str(work / "after.json"))
        results["2_upgrade"] = cmp = _compare(work / "before.json", work / "after.json")
        _expect(cmp["identical"] and cmp["employee_status_added"] == [seed["veteran_person"]],
                "upgrade adds exactly the legacy Employee", cmp)
        results["3_new_code_writes"] = wrote = _run(new_tree, "write", url)
        _check("registry_multisite_migration_check.py", url, "snapshot", "--json", str(work / "written.json"))
        results["4_rollback_plan"] = rplan = _check("registry_multisite_rollback.py", url, "plan")
        _expect([l["person_id"] for l in rplan["trainee_links_to_set_aside"]] == [wrote["trainee_person"]],
                "the rollback sets aside exactly the Trainee link", rplan)
        hazard = work / "without_detach.db"
        shutil.copyfile(db, hazard)
        results["4_old_code_without_detach"] = h = _run(old_tree, "old_reads", f"sqlite:///{hazard.as_posix()}",
                                                        "--info", json.dumps({**seed, **wrote}))
        _expect(h["trainee_statuses"] == ["EMPLOYEE"], "without the detach the old code would show the Trainee "
                "as an Employee (why the rollback sets the link aside)", h)
        _check("registry_multisite_rollback.py", url, "detach", "--record", str(work / "links.json"), "--apply")
        _alembic(new_tree, url, "downgrade", "b2c320261121")
        _check("registry_multisite_migration_check.py", url, "snapshot", "--json", str(work / "rolled_back.json"))
        cmp = _compare(work / "written.json", work / "rolled_back.json")
        _expect(cmp["differences"] == ["person_employee_links"] and not cmp["employee_status_removed"],
                "rollback changes only the set-aside Trainee link", cmp)
        results["4_rollback_data"] = cmp
        results["5_old_code_reads"] = old = _run(old_tree, "old_reads", url, "--info", json.dumps({**seed, **wrote}))
        _expect(old["trainee_statuses"] == [] and old["veteran_statuses"] == ["EMPLOYEE"],
                "old code: Trainee is not an Employee, the legacy card is", old)
        _expect(old["resolved"].get("T1") == wrote["trainee_card"] and old["resolved"].get("V2") == seed["veteran_card"],
                "old code keeps attributing work through the POS IDs", old)
        copy = work / "old_worker_copy.db"
        shutil.copyfile(db, copy)
        results["6_old_worker_proof"] = proof = _run(old_tree, "old_worker", f"sqlite:///{copy.as_posix()}")
        _expect(proof["registry_changed"], "the previous worker would import Clover names (why :12 is never restored)",
                proof)
        results["7_new_worker_after_rollback"] = new_worker = _run(new_tree, "new_worker", url,
                                                                   "--info", json.dumps({**seed, **wrote}))
        _expect(not new_worker["registry_changed"] and new_worker["order_person"] == wrote["trainee_card"],
                "new worker on the rolled-back database: no Registry change, work attributed", new_worker)
        _check("registry_multisite_migration_check.py", url, "snapshot", "--json", str(work / "before_forward.json"))
        results["8_reattach"] = _check("registry_multisite_rollback.py", url, "reattach", "--record",
                                       str(work / "links.json"), "--apply")
        _alembic(new_tree, url, "upgrade", "head")
        _check("registry_multisite_migration_check.py", url, "snapshot", "--json", str(work / "forward.json"))
        cmp = _compare(work / "before_forward.json", work / "forward.json")
        _expect(cmp["differences"] == ["person_employee_links"] and cmp["employee_status_added"] == []
                and cmp["employee_status_exact"], "roll-forward restores the link and adds no EMPLOYEE status", cmp)
        results["8_roll_forward"] = cmp
        results["8_trainee_after"] = _run(new_tree, "trainee_state", url, "--info", json.dumps({**seed, **wrote}))
        _expect(results["8_trainee_after"]["statuses"] == [] and results["8_trainee_after"]["card"] == wrote["trainee_card"],
                "after the roll-forward the Trainee is still a Trainee on the same card", results["8_trainee_after"])
        if args.extra_versions:
            heads = _alembic(new_tree, url, "heads", extra_versions=args.extra_versions)
            _alembic(new_tree, url, "upgrade", "heads", extra_versions=args.extra_versions)
            current = _alembic(new_tree, url, "current", extra_versions=args.extra_versions)
            _alembic(new_tree, url, "downgrade", "c7d820261122", extra_versions=args.extra_versions)
            back = _alembic(new_tree, url, "current", extra_versions=args.extra_versions)
            revisions = lambda out: [l for l in out.splitlines() if l and not l.startswith("INFO")]
            results["9_with_c4d5"] = {"heads": revisions(heads), "current": revisions(current),
                                      "after_downgrade": revisions(back)}
            _expect(heads.count("(head)") == 1 and "c4d520261121" in heads and "c4d520261121" in current
                    and "c7d820261122" in back, "c4d520261121 follows c7d820261122 with one head", results["9_with_c4d5"])
        results["outcome"] = "ALL EXPECTATIONS MET"
        print(json.dumps(results, indent=2, default=str))
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


# ----------------------------------------------------------------------------------------- phases
def _session(url):
    from rfone_data_store.database import create_configured_engine, create_session_factory
    engine = create_configured_engine(url)
    return engine, create_session_factory(engine)()


def phase_seed(url):
    from datetime import time
    from rfone_data_store import models as m, people_registry as people
    from rfone_data_store import rfone_account_service as accounts
    engine, db = _session(url)
    # The Selection service creates its own tables (as on AWS); the Training invitation table refers to them.
    from rfone_data_store.selection import workspace_models  # noqa: F401
    from sqlalchemy import inspect
    have = set(inspect(engine).get_table_names())
    m.Base.metadata.create_all(engine, tables=[t for n, t in m.Base.metadata.tables.items()
                                               if n.startswith("selection_") and n not in have])
    source = m.SourceSystem(code="CLOVER", name="Clover", active=True); db.add(source); db.flush()
    merchant = m.Merchant(source_system_id=source.id, source_merchant_id="WPMERCHANT", name="WP", active=True)
    db.add(merchant); db.flush()
    location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id="WPMERCHANT",
                          name="WP", currency="USD", timezone="America/New_York", operating_day_cutoff_time=time(4, 0),
                          active=True)
    restaurant = m.Restaurant(name="Rome's Flavours - WP", default_currency="USD")
    db.add_all([location, restaurant]); db.flush()
    db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    area = m.OperationalArea(name="Restaurant Operations"); db.add(area); db.flush()
    cook = m.RestaurantRole(name="Cook", code="COOK"); db.add(cook); db.flush()
    db.add(m.OperationalAreaRole(operational_area_id=area.id, restaurant_role_id=cook.id))
    admin = accounts.create_account(db, username="admin", display_name="Admin A.", password="Admin-Pass-99",
                                    email="admin@example.invalid", is_admin=True)
    trainer = accounts.create_account(db, username="trainer", display_name="Trainer T.", password="Trainer-Pass-9",
                                      email="trainer@example.invalid")
    db.flush()
    accounts.set_domain_access(db, account_id=trainer.id, domain_code="TRAINING", enabled=True, role_code="trainer")
    from datetime import datetime, timezone
    veteran = m.Employee(display_name="Veteran V.", location_id=location.id); db.add(veteran); db.flush()
    db.add(m.EmployeeAssignment(employee_id=veteran.id, restaurant_id=restaurant.id, restaurant_role_id=cook.id,
                                operational_area_id=area.id, valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                assignment_source="CLOVER_ROLE_SYNC"))
    person = people.create_identity(db, full_name="Veteran V.", email="veteran@example.invalid",
                                    normalized_name="veteran v.")
    db.add(people.PersonEmployeeLink(employee_id=veteran.id, person_id=person.id, linked_by_id=admin.id,
                                     linked_at=datetime(2026, 1, 2, tzinfo=timezone.utc)))
    db.add(m.EmployeeCloverLink(employee_id=veteran.id, location_id=location.id, merchant_id="WPMERCHANT",
                                external_employee_id="V1", state="PRESENT"))
    db.add(m.EmployeeCloverLink(employee_id=None, location_id=location.id, merchant_id="WPMERCHANT",
                                external_employee_id="ANNA1", state="PENDING", snapshot={"name": "Anna Friend"}))
    db.commit()
    out = dict(veteran_card=veteran.id, veteran_person=person.id, location=location.id, restaurant=restaurant.id,
               role=cook.id, area=area.id, trainer=trainer.id, source=source.id)
    db.close(); engine.dispose()
    return out


def phase_write(url):
    from datetime import datetime, timezone
    from rfone_data_store import models as m, employee_directory as directory
    from rfone_data_store import rfone_account_service as accounts
    from rfone_data_store.training import enrollment as en
    engine, db = _session(url)
    restaurant = db.query(m.Restaurant).one(); location = db.query(m.Location).one()
    role = db.query(m.RestaurantRole).one(); area = db.query(m.OperationalArea).one()
    trainer = accounts.get_account_by_username(db, "trainer") if hasattr(accounts, "get_account_by_username") else \
        db.query(m.RFOneAccount).filter_by(username="trainer").one()
    invitation, _ = en.issue(db, actor=trainer, email="new.trainee@example.invalid", name="New Trainee",
                             restaurant_id=restaurant.id, role_id=role.id, area_id=area.id)
    db.commit()
    card = directory.card_for_person(db, invitation.person_id)
    order = m.Order(source_system_id=location.source_system_id, source_order_id="O-T1", location_id=location.id,
                    source_employee_id="T1", employee_id=None, created_at=datetime(2026, 11, 22, 18, tzinfo=timezone.utc))
    db.add(order); db.flush()
    directory.set_pos_id(db, employee_id=card.id, restaurant_id=restaurant.id, pos_id="T1")
    veteran = db.query(m.Employee).filter_by(display_name="Veteran V.").one()
    directory.set_pos_id(db, employee_id=veteran.id, restaurant_id=restaurant.id, pos_id="V2")
    db.commit()
    out = dict(trainee_person=invitation.person_id, trainee_card=card.id, order_person=order.employee_id)
    db.close(); engine.dispose()
    return out


def phase_old_reads(url, info):
    from rfone_data_store import models as m, people_registry as people
    from rfone_data_store.technical.connectors.clover import correction_sync
    engine, db = _session(url)
    resolved = correction_sync._employee_ids_for_location(db, info["location"])
    unlinked = [(l.external_employee_id, l.state) for l in db.query(m.EmployeeCloverLink).filter(
        m.EmployeeCloverLink.employee_id.is_(None)).order_by(m.EmployeeCloverLink.id)]
    out = dict(trainee_statuses=sorted(people.company_statuses(db, info["trainee_person"])),
               veteran_statuses=sorted(people.company_statuses(db, info["veteran_person"])),
               resolved={k: v for k, v in resolved.items()},
               previous_registry_queue_would_show=unlinked)
    db.close(); engine.dispose()
    return out


def _fake_cycle(db, location_id, now):
    from rfone_data_store.clover_correction_sync_validation import _CorrectionFakeCloverClient
    from rfone_data_store.technical.connectors.clover.correction_sync import run_correction_cycle
    from datetime import timedelta
    client = _CorrectionFakeCloverClient("WPMERCHANT")
    client.employees = [{"id": "NEWNAME", "name": "Brand New Clover Name"},
                        {"id": "T1", "name": "New Trainee RENAMED IN CLOVER"}]
    at = now - timedelta(hours=1)
    ms = lambda value: int(value.timestamp() * 1000)
    client.orders = [{"id": "O-T1", "employee": {"id": "T1"}, "createdTime": ms(at), "modifiedTime": ms(at),
                      "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 1500,
                      "lineItems": {"elements": []}}]
    run_correction_cycle(db, location_id=location_id, client=client, now=now)
    db.commit()
    return client


def _registry_state(db):
    from rfone_data_store import models as m
    return (db.query(m.Employee).count(), db.query(m.EmployeeCloverLink).count(),
            sorted((e.id, e.display_name) for e in db.query(m.Employee)))


def phase_old_worker(url):
    from datetime import datetime, timezone
    from rfone_data_store import models as m
    engine, db = _session(url)
    before = _registry_state(db)
    location = db.query(m.Location).one()
    try:
        _fake_cycle(db, location.id, datetime(2026, 11, 22, 21, tzinfo=timezone.utc))
        error = None
    except Exception as exc:  # noqa: BLE001 — the proof only needs to know whether Registry changed
        db.rollback(); error = repr(exc)[:300]
    after = _registry_state(db)
    out = dict(registry_changed=before != after, before=before, after=after, error=error)
    db.close(); engine.dispose()
    return out


def phase_new_worker(url, info):
    from datetime import datetime, timezone
    from rfone_data_store import models as m
    engine, db = _session(url)
    before = _registry_state(db)
    client = _fake_cycle(db, info["location"], datetime(2026, 11, 22, 21, tzinfo=timezone.utc))
    after = _registry_state(db)
    order = db.query(m.Order).filter_by(source_order_id="O-T1").one()
    out = dict(registry_changed=before != after, staff_list_read=any(p.endswith("/employees") for p, _ in client.calls),
               order_person=order.employee_id)
    db.close(); engine.dispose()
    return out


def phase_trainee_state(url, info):
    from rfone_data_store import people_registry as people, employee_directory as directory
    engine, db = _session(url)
    card = directory.card_for_person(db, info["trainee_person"])
    out = dict(statuses=sorted(people.company_statuses(db, info["trainee_person"])), card=card.id if card else None)
    db.close(); engine.dispose()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old-tree")
    parser.add_argument("--extra-versions")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--phase"); parser.add_argument("--tree"); parser.add_argument("--db"); parser.add_argument("--info")
    args = parser.parse_args(argv)
    if not args.phase:
        if not args.old_tree:
            parser.error("--old-tree is required")
        orchestrate(args)
        return 0
    sys.path.insert(0, args.tree)
    info = json.loads(args.info) if args.info else None
    phases = {"seed": lambda: phase_seed(args.db), "write": lambda: phase_write(args.db),
              "old_reads": lambda: phase_old_reads(args.db, info), "old_worker": lambda: phase_old_worker(args.db),
              "new_worker": lambda: phase_new_worker(args.db, info), "trainee_state": lambda: phase_trainee_state(args.db, info)}
    print(json.dumps(phases[args.phase](), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
