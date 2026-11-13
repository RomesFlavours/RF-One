#!/usr/bin/env python
"""Regression test for the startup-determinism fix (RF-ONE: "Remove DB
migration and Training seeding from application boot").

Proves the canonical rule the fix implements: importing the application
(`Tips/app.py`, `Training/db.py`, `Training/routes.py`) must never run
Alembic or write to the database — those are explicit, operator-invoked
steps (`run_migrations_to_head()`, then `initialize_training.py`), run
once, never repeated per Gunicorn worker.

Each check that needs to observe "did import touch the database" uses a
disposable SQLite path that is asserted absent beforehand and does not yet
have migrations applied — if any import path executed a migration or a
write, the file would come into existence (SQLite creates its backing file
lazily, on first real connection/statement, not merely from constructing an
Engine). A subprocess is used for every import check so each one gets a
genuinely fresh, uncached module state — exactly like a separate Gunicorn
worker process forking and importing the WSGI app for the first time.

Mirrors this repository's standalone-script test convention (`main()`
returning an exit code, no pytest) already used by `test_training_http.py`
and every other `test_*.py` in this repo.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
TIPS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Tips"))


def _fresh_db_path(label: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"startup_audit_{label}_")
    os.close(fd)
    os.remove(path)
    return path


def _run_import_subprocess(db_path: str, import_code: str) -> subprocess.CompletedProcess:
    """Runs `import_code` in a brand-new Python process (never a cached
    module from this test's own process) with RFONE_DATABASE_URL pointed at
    `db_path`, and PYTHONPATH set up exactly like the real app does."""
    env = dict(os.environ)
    env["RFONE_DATABASE_URL"] = f"sqlite:///{db_path.replace(os.sep, '/')}"
    return subprocess.run(
        [sys.executable, "-c", import_code],
        cwd=TIPS_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    # -------------------------------------------------------------------
    # A. Importing Tips/app.py does not run Alembic / touch the database.
    # -------------------------------------------------------------------
    db_a = _fresh_db_path("tips_import")
    result_a = _run_import_subprocess(db_a, "import app")
    check(
        "A: importing Tips/app.py succeeds without a schema", result_a.returncode == 0,
        result_a.stderr[-2000:],
    )
    check("A: importing Tips/app.py creates no database file (no migration ran)", not os.path.exists(db_a))

    # -------------------------------------------------------------------
    # B. Importing Training/db.py (standalone) does not run Alembic.
    # -------------------------------------------------------------------
    db_b = _fresh_db_path("training_db_import")
    import_db_code = (
        f"import sys; sys.path.insert(0, r'{DATA_STORE_DIR}'); sys.path.insert(0, r'{BASE_DIR}'); "
        "import db"
    )
    result_b = subprocess.run(
        [sys.executable, "-c", import_db_code],
        env={**os.environ, "RFONE_DATABASE_URL": f"sqlite:///{db_b.replace(os.sep, '/')}"},
        capture_output=True, text=True, timeout=30,
    )
    check(
        "B: importing Training/db.py standalone succeeds", result_b.returncode == 0, result_b.stderr[-2000:],
    )
    check("B: importing Training/db.py creates no database file (no migration ran)", not os.path.exists(db_b))

    # -------------------------------------------------------------------
    # C. Importing Training/routes.py does not seed data (nor migrate).
    # -------------------------------------------------------------------
    db_c = _fresh_db_path("training_routes_import")
    import_routes_code = (
        f"import sys; sys.path.insert(0, r'{DATA_STORE_DIR}'); sys.path.insert(0, r'{BASE_DIR}'); "
        "import routes"
    )
    result_c = subprocess.run(
        [sys.executable, "-c", import_routes_code],
        env={**os.environ, "RFONE_DATABASE_URL": f"sqlite:///{db_c.replace(os.sep, '/')}"},
        capture_output=True, text=True, timeout=30,
    )
    check(
        "C: importing Training/routes.py standalone succeeds", result_c.returncode == 0, result_c.stderr[-2000:],
    )
    check(
        "C: importing Training/routes.py creates no database file (no migration/seeding ran)",
        not os.path.exists(db_c),
    )

    # -------------------------------------------------------------------
    # D. initialize_training.py seeds the expected canonical content AFTER
    #    migrations have explicitly been applied.
    # -------------------------------------------------------------------
    db_d = _fresh_db_path("init_training")
    db_d_url = f"sqlite:///{db_d.replace(os.sep, '/')}"
    sys.path.insert(0, DATA_STORE_DIR)
    from rfone_data_store.database import run_migrations_to_head, create_configured_engine, create_session_factory
    run_migrations_to_head(db_d_url)
    check("D: database file exists after explicit migration", os.path.exists(db_d))

    sys.path.insert(0, BASE_DIR)
    os.environ["RFONE_DATABASE_URL"] = db_d_url
    import initialize_training  # noqa: E402

    first_run_code = initialize_training.main()
    check("D: initialize_training.py returns 0 (success) on first run", first_run_code == 0)

    engine_d = create_configured_engine(db_d_url)
    SessionD = create_session_factory(engine_d)
    from rfone_data_store import models as dm

    with SessionD() as s:
        pill_count_first = s.query(dm.TrainingPill).count()
        question_count_first = s.query(dm.TrainingQuestion).count()
    check("D: exactly 3 canonical pills seeded", pill_count_first == 3, f"got {pill_count_first}")
    check("D: exactly 27 canonical questions seeded", question_count_first == 27, f"got {question_count_first}")

    # -------------------------------------------------------------------
    # E. Running initialize_training.py a second time is safe/idempotent.
    # -------------------------------------------------------------------
    second_run_code = initialize_training.main()
    check("E: initialize_training.py returns 0 (success) on second run", second_run_code == 0)

    with SessionD() as s:
        pill_count_second = s.query(dm.TrainingPill).count()
        question_count_second = s.query(dm.TrainingQuestion).count()
    check(
        "E: pill count unchanged after second run (no duplicates)",
        pill_count_second == pill_count_first, f"first={pill_count_first} second={pill_count_second}",
    )
    check(
        "E: question count unchanged after second run (no duplicates)",
        question_count_second == question_count_first,
        f"first={question_count_first} second={question_count_second}",
    )
    engine_d.dispose()

    # -------------------------------------------------------------------
    # G. Simulated concurrent multi-worker startup performs ZERO migration
    #    and ZERO seeding — the exact scenario (Gunicorn --workers 2) that
    #    caused the original crash-loop.
    # -------------------------------------------------------------------
    db_g = _fresh_db_path("concurrent_workers")
    env_g = dict(os.environ)
    env_g["RFONE_DATABASE_URL"] = f"sqlite:///{db_g.replace(os.sep, '/')}"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", "import app"], cwd=TIPS_DIR, env=env_g,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    results_g = [p.communicate(timeout=30) for p in procs]
    returncodes_g = [p.returncode for p in procs]
    check("G: both simulated concurrent worker imports succeed", all(rc == 0 for rc in returncodes_g), str(results_g))
    check(
        "G: concurrent worker imports created no database file (zero migration, zero seeding)",
        not os.path.exists(db_g),
    )

    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------
    for path in (db_a, db_b, db_c, db_d, db_g):
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = path + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
