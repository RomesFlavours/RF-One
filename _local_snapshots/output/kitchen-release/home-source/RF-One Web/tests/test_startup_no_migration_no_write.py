#!/usr/bin/env python
"""Regression test (task item M): importing RF-One Web's `app.py` must
execute ZERO Alembic migrations and ZERO database writes.

Mirrors `Training/test_startup_no_migration_no_seed.py`'s own convention
exactly: a disposable SQLite path that is asserted absent beforehand and
never migrated, imported in a brand-new subprocess (never a module cached
from this test's own process) — if import touched the database at all, the
SQLite file would come into existence (SQLite creates its backing file
lazily, on first real connection/statement, not merely from constructing an
Engine). Two imports are run truly concurrently to simulate Gunicorn
`--workers 2`, the exact scenario the Training incident this rule responds
to involved.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))


def _fresh_db_path(label: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"rfoneweb_startup_audit_{label}_")
    os.close(fd)
    os.remove(path)
    return path


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
    # A single import of app.py must migrate/write nothing.
    # -------------------------------------------------------------------
    db_single = _fresh_db_path("single_import")
    env_single = dict(os.environ)
    env_single["RFONE_DATABASE_URL"] = f"sqlite:///{db_single.replace(os.sep, '/')}"
    env_single["RFONE_WEB_TEST_SECRET_KEY"] = "startup-audit-secret"
    result_single = subprocess.run(
        [sys.executable, "-c", "import app"], cwd=APP_DIR, env=env_single,
        capture_output=True, text=True, timeout=30,
    )
    check("single import of app.py succeeds", result_single.returncode == 0, result_single.stderr[-2000:])
    check("single import of app.py creates no database file (zero migration, zero write)", not os.path.exists(db_single))

    # -------------------------------------------------------------------
    # M: simulated concurrent multi-worker startup performs ZERO migration
    # and ZERO writes.
    # -------------------------------------------------------------------
    db_concurrent = _fresh_db_path("concurrent_workers")
    env_concurrent = dict(os.environ)
    env_concurrent["RFONE_DATABASE_URL"] = f"sqlite:///{db_concurrent.replace(os.sep, '/')}"
    env_concurrent["RFONE_WEB_TEST_SECRET_KEY"] = "startup-audit-secret"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", "import app"], cwd=APP_DIR, env=env_concurrent,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    results = [p.communicate(timeout=30) for p in procs]
    returncodes = [p.returncode for p in procs]
    check("M: both simulated concurrent worker imports succeed", all(rc == 0 for rc in returncodes), str(results))
    check(
        "M: concurrent worker imports created no database file (zero migration, zero write)",
        not os.path.exists(db_concurrent),
    )

    for path in (db_single, db_concurrent):
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
