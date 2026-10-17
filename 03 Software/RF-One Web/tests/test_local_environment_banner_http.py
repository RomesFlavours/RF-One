"""The local environment bar (Infrastructure/Bank Local Environment).

On a throwaway database, over HTTP:

* without RFONE_LOCAL_ENV_* (AWS, every other test) no bar is shown;
* started by "Avvia Bank" (work): PC, database, generation, code and AI mode;
* a test copy: the bar says TEST COPY, impossible to miss;
* the AI mode shown is the one in force: SESSION never names a provider.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_local_env_banner_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "local-env-banner-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402

ENV = {"RFONE_LOCAL_ENV_PC": "ASUS2026", "RFONE_LOCAL_ENV_DB": r"C:\Users\x\AppData\Local\RF-One\Bank\rfone.db",
       "RFONE_LOCAL_ENV_GENERATION": "7 (MINIPC-KSYR1, 2026-10-11T18:00:00-04:00)",
       "RFONE_LOCAL_ENV_CODE": "feature/x@abc1234 · code 0123456789", "RFONE_LOCAL_ENV_KIND": "WORK"}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    client = web_app.app.test_client()

    def login_page() -> str:
        return client.get("/login").data.decode()

    page = login_page()
    check("1. without the local environment no bar is shown", 'class="local-env' not in page)

    os.environ.update(ENV)
    os.environ["RFONE_BANK_AI_MODE"] = "SESSION"
    try:
        page = login_page()
        check("2. work environment: PC, database, generation, code and AI mode are shown",
              'class="local-env ' in page and "ASUS2026" in page and "Bank\\rfone.db" in page
              and "generation 7 (MINIPC-KSYR1" in page and "code 0123456789" in page
              and "SESSION Claude Code" in page and "TEST COPY" not in page)
        os.environ["RFONE_LOCAL_ENV_KIND"] = "TEST"
        page = login_page()
        check("3. a test copy is marked TEST COPY", "local-env-test" in page and "TEST COPY" in page)
        os.environ["RFONE_BANK_AI_MODE"] = "PROVIDER"
        page = login_page()
        check("4. PROVIDER mode names the provider in force", "PROVIDER " in page and "SESSION Claude Code" not in page)
    finally:
        for key in list(ENV) + ["RFONE_BANK_AI_MODE"]:
            os.environ.pop(key, None)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
