#!/usr/bin/env python
"""HTTP-level regression test for RF-One Web V1 (accounts + Domain access
shell). Mirrors `Training/test_training_http.py`'s own convention exactly:
a throwaway SQLite database created BEFORE `app.py` is imported (via
`RFONE_DATABASE_URL`), migrated explicitly (app import never migrates —
see `test_startup_no_migration_no_write.py`), Werkzeug's Flask test client,
`main()` returning an exit code. Never touches AWS or any production
database.

Covers task items A-L and N:
  A. first admin can be created explicitly (`create_admin`-equivalent path)
  B. valid ACTIVE account can log in
  C. invalid password fails
  D. INACTIVE account cannot log in
  E. non-admin cannot access /admin/accounts
  F. admin can create another account
  G. duplicate username is rejected
  H. admin can assign Training access
  I. admin can assign multiple Domains
  J. Home displays ONLY authorized Domains
  K. role_code is persisted correctly
  L. disabling a Domain removes it from Home
  N. password hashes are stored, never the plain password
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)  # let the explicit migration step below create it fresh
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

# app.py no longer migrates automatically (worker startup must never do so)
# — this test's setup performs it explicitly, exactly like the real
# deployment procedure will.
from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        # -----------------------------------------------------------------
        # A. First admin can be created explicitly (the same service call
        # create_admin.py itself makes — its own argparse/getpass shell is
        # exercised separately, not over HTTP).
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            admin = account_service.create_account(
                s, username="RFone", display_name="Pino Miraglia", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            s.commit()
            admin_id = admin.id
        check("A: first admin account created", admin_id is not None)
        check("A: admin username normalized/stored", admin.username == "rfone")
        check("A: admin is_admin flag set", admin.is_admin is True)

        # -----------------------------------------------------------------
        # N. Password hash stored, never the plain password.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            reloaded = s.get(m.RFOneAccount, admin_id)
            check("N: password_hash does not contain the plain password", "AdminPass123!" not in reloaded.password_hash)
            check("N: password_hash is a non-trivial hash string", len(reloaded.password_hash) > 20)

        admin_client = web_app.app.test_client()
        anon_client = web_app.app.test_client()

        # -----------------------------------------------------------------
        # B. Valid ACTIVE account can log in.
        # -----------------------------------------------------------------
        resp = admin_client.get("/login")
        check("GET /login returns 200", resp.status_code == 200)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post("/login", data={"username": "RFone", "password": "AdminPass123!", "csrf_token": csrf})
        check("B: valid login redirects to home", resp.status_code in (302, 303))

        resp = admin_client.get("/")
        check("B: home page shows admin's display name after login", b"Pino Miraglia" in resp.data)

        # -----------------------------------------------------------------
        # C. Invalid password fails.
        # -----------------------------------------------------------------
        wrong_client = web_app.app.test_client()
        resp = wrong_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = wrong_client.post("/login", data={"username": "RFone", "password": "WRONG", "csrf_token": csrf})
        check("C: wrong password login rejected (401)", resp.status_code == 401)

        # -----------------------------------------------------------------
        # D. INACTIVE account cannot log in.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            account_service.create_account(
                s, username="inactive_user", display_name="Inactive Person", password="Whatever123!",
                status="INACTIVE",
            )
            s.commit()
        inactive_client = web_app.app.test_client()
        resp = inactive_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = inactive_client.post(
            "/login", data={"username": "inactive_user", "password": "Whatever123!", "csrf_token": csrf},
        )
        check("D: INACTIVE account login rejected (401)", resp.status_code == 401)

        # -----------------------------------------------------------------
        # E. Non-admin cannot access /admin/accounts.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            account_service.create_account(
                s, username="plain_user", display_name="Plain User", password="PlainPass123!",
                status="ACTIVE", is_admin=False,
            )
            s.commit()
        plain_client = web_app.app.test_client()
        resp = plain_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = plain_client.post(
            "/login", data={"username": "plain_user", "password": "PlainPass123!", "csrf_token": csrf},
        )
        check("plain user login redirects", resp.status_code in (302, 303))

        resp = plain_client.get("/")
        check("E: non-admin home page does NOT show Administration section", b"Administration" not in resp.data)

        resp = plain_client.get("/admin/accounts")
        check("E: non-admin GET /admin/accounts is forbidden (403)", resp.status_code == 403)

        resp = anon_client.get("/admin/accounts")
        check(
            "unauthenticated GET /admin/accounts redirects to login",
            resp.status_code in (301, 302, 303, 308),
        )

        # -----------------------------------------------------------------
        # F. Admin can create another account.
        # -----------------------------------------------------------------
        resp = admin_client.get("/admin/accounts")
        check("admin can open /admin/accounts (200)", resp.status_code == 200)

        resp = admin_client.get("/admin/accounts/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/accounts/new",
            data={
                "username": "jamie", "display_name": "Jamie Rossi", "email": "Jamie@Example.com",
                "password": "JamiePass123!", "password_confirm": "JamiePass123!", "status": "ACTIVE",
                "csrf_token": csrf,
            },
        )
        check("F: admin creates another account (redirects)", resp.status_code in (302, 303))

        with SessionFactory() as s:
            jamie = account_service.get_account_by_username(s, "jamie")
            check("F: new account persisted", jamie is not None)
            jamie_id = jamie.id
            check("F: email normalized (trimmed/lowercased) and stored", jamie.email == "jamie@example.com")
            check("F: new account's email starts unverified", jamie.email_verified_at is None)

        # -----------------------------------------------------------------
        # G. Duplicate username is rejected.
        # -----------------------------------------------------------------
        resp = admin_client.get("/admin/accounts/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/accounts/new",
            data={
                "username": "jamie", "display_name": "Jamie Duplicate", "password": "AnotherPass123!",
                "password_confirm": "AnotherPass123!", "status": "ACTIVE", "csrf_token": csrf,
            },
        )
        check("G: duplicate username rejected (400)", resp.status_code == 400)
        with SessionFactory() as s:
            count = s.query(m.RFOneAccount).filter(m.RFOneAccount.username == "jamie").count()
            check("G: duplicate username did not create a second row", count == 1)

        # -----------------------------------------------------------------
        # H. Admin can assign Training access. K. role_code persisted.
        # -----------------------------------------------------------------
        resp = admin_client.get(f"/admin/accounts/{jamie_id}/access")
        check("GET domain access page succeeds", resp.status_code == 200)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{jamie_id}/access",
            data={"enabled_TRAINING": "on", "role_TRAINING": "TRAINER", "csrf_token": csrf},
        )
        check("H: assigning Training access redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            rows = account_service.list_domain_access_for_account(s, jamie_id)
            training_row = next((r for r in rows if r.domain_code == "TRAINING"), None)
            check("H: Training access row created and enabled", training_row is not None and training_row.enabled)
            check("K: role_code persisted correctly ('TRAINER')", training_row.role_code == "TRAINER")

        # -----------------------------------------------------------------
        # I. Admin can assign multiple Domains. J. Home shows ONLY
        # authorized Domains.
        # -----------------------------------------------------------------
        resp = admin_client.get(f"/admin/accounts/{jamie_id}/access")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{jamie_id}/access",
            data={
                "enabled_TRAINING": "on", "role_TRAINING": "TRAINER",
                "enabled_TIPS": "on", "role_TIPS": "MANAGER",
                "csrf_token": csrf,
            },
        )
        check("I: assigning multiple Domains redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            rows = account_service.list_domain_access_for_account(s, jamie_id)
            enabled_codes = {r.domain_code for r in rows if r.enabled}
            check("I: both TRAINING and TIPS enabled", enabled_codes == {"TRAINING", "TIPS"})

        jamie_client = web_app.app.test_client()
        resp = jamie_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = jamie_client.post(
            "/login", data={"username": "jamie", "password": "JamiePass123!", "csrf_token": csrf},
        )
        check("jamie login redirects", resp.status_code in (302, 303))

        resp = jamie_client.get("/")
        check("J: home shows Training domain card", b"Training" in resp.data)
        check("J: home shows Tips domain card", b"Tips" in resp.data)
        check("J: home does NOT show Compensation (not assigned)", b"Compensation" not in resp.data)
        check("J: home does NOT show Selection (not assigned)", b"Selection" not in resp.data)
        check("J: home does NOT show Administration for non-admin", b"Administration" not in resp.data)

        # -----------------------------------------------------------------
        # L. Disabling a Domain removes it from Home.
        # -----------------------------------------------------------------
        resp = admin_client.get(f"/admin/accounts/{jamie_id}/access")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{jamie_id}/access",
            data={"enabled_TIPS": "on", "role_TIPS": "MANAGER", "csrf_token": csrf},  # TRAINING omitted -> disabled
        )
        check("disabling Training redirects", resp.status_code in (302, 303))

        resp = jamie_client.get("/")
        check("L: Training removed from Home after being disabled", b"Training" not in resp.data)
        check("L: Tips still present after Training disabled", b"Tips" in resp.data)

        with SessionFactory() as s:
            rows = account_service.list_domain_access_for_account(s, jamie_id)
            training_row = next((r for r in rows if r.domain_code == "TRAINING"), None)
            check("L: Training access row persists as disabled (not deleted)", training_row is not None and training_row.enabled is False)

        # -----------------------------------------------------------------
        # No Domain assigned -> explicit empty-state message.
        # -----------------------------------------------------------------
        no_domain_client = web_app.app.test_client()
        resp = no_domain_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = no_domain_client.post(
            "/login", data={"username": "plain_user", "password": "PlainPass123!", "csrf_token": csrf},
        )
        resp = no_domain_client.get("/")
        check(
            "account with no Domain access sees the explicit empty-state message",
            b"No operational Domains are currently assigned to this account." in resp.data,
        )

    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
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
