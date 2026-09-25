#!/usr/bin/env python
"""HTTP-level regression test for the Home layout (Product Owner,
2026-09-25): Domains, then Administration, then Settings, as one vertical
column of blocks.

  * Domains: operational first, Work in progress last, alphabetical within
    each group; Bank is not a Domain on Home.
  * Administration: Bank, for accounts with BANK access.
  * Settings: Accounts, Legal Entities, Organization (admins), Profile.
  * Profile is no longer a header button; Log out is a text link.

Throwaway SQLite database created before `app.py` is imported; never
touches AWS or any production database.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_home_layout_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "home-layout-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
import training_integration as ti  # noqa: E402
from domain_registry import DOMAINS_BY_CODE  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
HREF_RE = re.compile(r'href="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    resp = client.get("/login")
    csrf = extract_csrf(resp.data)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


def content_of(html: str) -> str:
    """The page body after the site header (the header links to Home and to
    the favicon/logo, which are not Home navigation)."""
    return html.split("</header>", 1)[1]


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
        with SessionFactory() as s:
            admin = account_service.create_account(
                s, username="admin1", display_name="Admin One", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            plain = account_service.create_account(
                s, username="plain1", display_name="Plain One", password="PlainPass123!", status="ACTIVE",
            )
            s.flush()
            for code in ("TRAINING", "TIPS", "COMPENSATION", "SELECTION", "BANK"):
                account_service.set_domain_access(
                    s, account_id=admin.id, domain_code=code, enabled=True,
                    role_code="trainer" if code == "TRAINING" else None,
                )
            ti.create_and_link_training_identity(s, rfone_account_id=admin.id, role_code="trainer")
            account_service.set_domain_access(s, account_id=plain.id, domain_code="TIPS", enabled=True, role_code=None)
            bank_only = account_service.create_account(
                s, username="bank1", display_name="Bank One", password="BankPass123!", status="ACTIVE",
            )
            s.flush()
            account_service.set_domain_access(s, account_id=bank_only.id, domain_code="BANK", enabled=True, role_code=None)
            s.commit()

        admin_client = web_app.app.test_client()
        login(admin_client, "admin1", "AdminPass123!")
        resp = admin_client.get("/")
        html = resp.data.decode("utf-8")
        body = content_of(html)
        check("admin Home renders (200)", resp.status_code == 200)

        # --- Header ---------------------------------------------------------
        header = html.split("</header>", 1)[0]
        check("viewport meta is in the rendered <head>",
              '<meta name="viewport" content="width=device-width, initial-scale=1">' in html.split("</head>", 1)[0])
        check("Log out is the first Home element after the header line",
              body.index('class="home-logout"') < body.index("<h1>"))
        check("Profile is not in the header", "/profile" not in header and "Profile" not in header)
        check("Log out is a text link below the header (link-button, POST with CSRF)",
              'class="home-logout"' in body and 'class="link-button">Log out</button>' in body
              and 'class="btn-secondary">Log out' not in html)

        # --- Domains --------------------------------------------------------
        domains_part = body.split("<h2>Your Domains</h2>", 1)[1].split('<div class="domain-name">Administration</div>', 1)[0]
        names = re.findall(r'<div class="domain-name">([^<]+)</div>', domains_part)
        expected = ["Compensation", "Tips", "Training", "Selection — Work in progress"]
        check("Domains ordered: operational alphabetical, then Work in progress", names == expected, f"{names}")
        check("Bank is not presented as a Domain",
              DOMAINS_BY_CODE["BANK"].display_name not in domains_part and 'href="/bank"' not in domains_part)
        check("no side-by-side domain grid remains on Home", 'class="domain-grid"' not in body)
        tips_block = domains_part.split(DOMAINS_BY_CODE["TIPS"].display_name, 1)[1].split('class="domain-card"', 1)[0]
        check("'Tips — validate saved periods' sits right under the Tips Domain",
              'href="/tips/runs"' in tips_block and "validate saved periods" in tips_block)

        # --- Administration and Settings -------------------------------------
        admin_part = body.split('<div class="domain-name">Administration</div>', 1)[1].split('<div class="domain-name">Settings</div>', 1)[0]
        settings_part = body.split('<div class="domain-name">Settings</div>', 1)[1]
        check("Administration contains exactly Bank",
              HREF_RE.findall(admin_part) == ["/bank"] and "<strong>Bank</strong>" in admin_part)
        rows = re.findall(r"<strong>([^<]+)</strong>", settings_part)
        check("Settings rows are Accounts, Legal Entities, Organization, Profile (alphabetical)",
              rows == ["Accounts", "Legal Entities", "Organization", "Profile"], f"{rows}")
        check("Settings links use the existing routes",
              HREF_RE.findall(settings_part) == ["/admin/accounts", "/admin/legal-entities", "/admin/organization", "/profile"])
        check("Administration and Settings are two distinct blocks",
              body.count('class="domain-card home-block"') == 2)
        check("old separate links are gone",
              "Manage Legal Entities" not in body and "Manage Organization" not in body)

        hrefs = HREF_RE.findall(body)
        check("no duplicated link on Home", len(hrefs) == len(set(hrefs)), f"{hrefs}")

        # --- Every destination still opens ------------------------------------
        for path in ("/compensation", "/training", "/selection", "/bank", "/tips/runs",
                     "/admin/accounts", "/admin/legal-entities", "/admin/organization", "/profile"):
            r = admin_client.get(path, follow_redirects=True)
            check(f"{path} opens (200)", r.status_code == 200, str(r.status_code))
        check("Tips Domain keeps its existing link",
              f'href="{DOMAINS_BY_CODE["TIPS"].link}"' in body)

        # --- Non-admin without BANK -------------------------------------------
        plain_client = web_app.app.test_client()
        login(plain_client, "plain1", "PlainPass123!")
        plain_body = content_of(plain_client.get("/").data.decode("utf-8"))
        plain_settings = plain_body.split('<div class="domain-name">Settings</div>', 1)[1]
        check("without BANK access there is no Administration block",
              "Administration" not in plain_body and 'href="/bank"' not in plain_body)
        check("a non-admin's Settings contain only Profile",
              re.findall(r"<strong>([^<]+)</strong>", plain_settings) == ["Profile"])

        # --- BANK-only account ----------------------------------------------------
        bank_client = web_app.app.test_client()
        login(bank_client, "bank1", "BankPass123!")
        bank_body = content_of(bank_client.get("/").data.decode("utf-8"))
        check("a BANK-only account sees 'No operational Domains are currently assigned to this account.'",
              "No operational Domains are currently assigned to this account." in bank_body
              and "No RF-One Domains" not in bank_body)
        check("a BANK-only account still has Bank under Administration",
              '<div class="domain-name">Administration</div>' in bank_body and 'href="/bank"' in bank_body)
        bank_hrefs = HREF_RE.findall(bank_body)
        check("BANK-only Home: Profile under Settings, no duplicate links",
              bank_hrefs == ["/bank", "/profile"], f"{bank_hrefs}")

        # --- Log out ------------------------------------------------------------
        csrf = extract_csrf(plain_client.get("/").data)
        out = plain_client.post("/logout", data={"csrf_token": csrf})
        after = plain_client.get("/")
        check("Log out works (redirect, then Home requires login again)",
              out.status_code in (302, 303) and after.status_code in (302, 303) and "/login" in after.headers.get("Location", ""))

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
