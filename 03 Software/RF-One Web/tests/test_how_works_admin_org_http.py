#!/usr/bin/env python
"""HTTP-level test of the contextual help ("How … works" modal) on the
Settings/Administration pages and on the Organization Domain pages.

For every page it can reach it asserts: status 200, the layout's help link
for the page's own section (`data-how-works="<section>"`), the section's
content (`id="help-<section>"`), the right label ("How Organization works"
on the Domain's home, "How this page works" elsewhere) and exactly one help
dialog. It also checks that the parts of the help describing changes stay
hidden from an account that may only consult Organization, as the page's
own controls are.

Same convention as this app's other tests: throwaway SQLite database,
Werkzeug test client, GET requests only (no e-mail is sent, nothing is
written through the UI), `main()` returning an exit code.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_how_works_admin_org_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "how-works-admin-org-test-secret"
os.environ.pop("RFONE_EMAIL_FROM_ADDRESS", None)  # never send a real email from this test

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import training_integration  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import attention_service as att_svc  # noqa: E402
from rfone_data_store import legal_entity_service  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import organizational_responsibility_service as org_svc  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

UTC = timezone.utc
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
MODULE_LABEL = "How Organization works"
PAGE_LABEL = "How this page works"


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    resp = client.get("/login")
    csrf = extract_csrf(resp.data)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def check_help(client, who: str, path: str, section: str, label: str) -> str:
        resp = client.get(path)
        html = resp.get_data(as_text=True)
        check(f"{who} GET {path} renders (200)", resp.status_code == 200, f"got {resp.status_code}")
        check(f"{who} {path}: help link for '{section}'", f'data-how-works="{section}"' in html)
        check(f"{who} {path}: help content id=help-{section}", f'id="help-{section}"' in html)
        check(f"{who} {path}: label '{label}'", label in html)
        if label == PAGE_LABEL:
            check(f"{who} {path}: not labelled as a module home", MODULE_LABEL not in html)
        count = html.count('id="rf-help-dialog"')
        check(f"{who} {path}: exactly one help dialog", count == 1, f"found {count}")
        return html

    try:
        with SessionFactory() as s:
            admin = account_service.create_account(
                s, username="admin1", display_name="Admin One", password="AdminPass123!",
                status="ACTIVE", is_admin=True, email="admin1@example.com",
            )
            viewer = account_service.create_account(
                s, username="viewer1", display_name="Viewer One", password="ViewerPass123!",
                status="ACTIVE", is_admin=False,
            )
            linked = account_service.create_account(
                s, username="linked1", display_name="Linked One", password="LinkedPass123!",
                status="ACTIVE", is_admin=False,
            )
            s.commit()
            for account in (admin, viewer):
                account_service.set_domain_access(
                    s, account_id=account.id, domain_code="ORGANIZATION", enabled=True, role_code=None,
                )
            training_integration.create_and_link_training_identity(s, rfone_account_id=linked.id, role_code="student")
            entity = legal_entity_service.create_legal_entity(s, legal_name="TEST/DEMO Legal Entity LLC")
            s.add(m.Restaurant(name="TEST/DEMO Restaurant"))
            s.commit()

            parent = org_svc.create_position(s, name="TEST/DEMO Parent Position")
            child = org_svc.create_position(s, name="TEST/DEMO Child Position", parent=parent)
            occupant = m.ActingIdentity(kind=m.HUMAN_USER, display_name="TEST/DEMO Occupant")
            s.add(occupant)
            s.flush()
            org_svc.assign_occupant(s, position=parent, occupant=occupant, valid_from=datetime(2026, 1, 1, tzinfo=UTC))
            org_svc.set_process_ownership(s, domain="TESTHELP", process_name="TestHelpProcess", position=child)
            s.commit()
            item = att_svc.create_attention(
                s, source_domain="TESTHELP", source_process_name="TestHelpProcess",
                reason="TEST/DEMO help attention item", priority=m.ATTENTION_PRIORITY_HIGH,
            )
            s.commit()
            att_svc.route_attention(s, item=item)
            s.commit()
            ids = {
                "admin": admin.id, "viewer": viewer.id, "linked": linked.id, "entity": entity.id,
                "parent": parent.id, "item": item.id,
            }

        admin_client = web_app.app.test_client()
        login(admin_client, "admin1", "AdminPass123!")
        viewer_client = web_app.app.test_client()
        login(viewer_client, "viewer1", "ViewerPass123!")

        # -- Settings / Administration (RF-One administrators only) -------------
        settings_pages = (
            ("/admin/accounts", "settings-accounts"),
            ("/admin/accounts/new", "settings-account-form"),
            (f"/admin/accounts/{ids['viewer']}/edit", "settings-account-form"),
            (f"/admin/accounts/{ids['viewer']}/access", "settings-account-access"),
            (f"/admin/accounts/{ids['viewer']}/training-link", "settings-account-training-link"),
            (f"/admin/accounts/{ids['linked']}/training-link", "settings-account-training-link"),
            ("/admin/legal-entities", "settings-legal-entities"),
            ("/admin/legal-entities/new", "settings-legal-entity-form"),
            (f"/admin/legal-entities/{ids['entity']}/edit", "settings-legal-entity-form"),
            ("/admin/workweek", "settings-workweek"),
            ("/profile", "settings-profile"),
        )
        pages_html = {}
        for path, section in settings_pages:
            pages_html[path] = check_help(admin_client, "admin", path, section, PAGE_LABEL)

        check("create form help explains the Email field",
              "verification code is emailed" in pages_html["/admin/accounts/new"])
        edit_html = pages_html[f"/admin/accounts/{ids['viewer']}/edit"]
        check("edit form help explains Reset password", "every session where the person is signed in is ended" in edit_html)
        check("edit form help does not describe the create-only Email field",
              "verification code is emailed" not in edit_html)
        check("unlinked Training Identity help explains both options",
              "Link selected identity" in pages_html[f"/admin/accounts/{ids['viewer']}/training-link"])
        check("linked Training Identity help says the link cannot be changed",
              "already linked" in pages_html[f"/admin/accounts/{ids['linked']}/training-link"]
              and "Link selected identity</dt>" not in pages_html[f"/admin/accounts/{ids['linked']}/training-link"])

        # The Profile is every account's own page.
        check_help(viewer_client, "viewer", "/profile", "settings-profile", PAGE_LABEL)
        for path, _section in settings_pages[:-1]:
            check(f"viewer GET {path} stays forbidden (403)", viewer_client.get(path).status_code == 403)

        # -- Organization Domain -------------------------------------------------
        org_pages = (
            ("/admin/organization", "organization-home", MODULE_LABEL),
            ("/admin/org/positions", "organization-positions", PAGE_LABEL),
            ("/admin/org/positions/new", "organization-position-form", PAGE_LABEL),
            (f"/admin/org/positions/{ids['parent']}", "organization-position-detail", PAGE_LABEL),
            (f"/admin/org/positions/{ids['parent']}/interview", "organization-position-interview", PAGE_LABEL),
            ("/admin/org/process-ownerships", "organization-process-ownerships", PAGE_LABEL),
            ("/admin/org/fallback-policies", "organization-fallback-policies", PAGE_LABEL),
            ("/admin/org/coverage-check", "organization-coverage-check", PAGE_LABEL),
            ("/admin/org/attention", "organization-attention", PAGE_LABEL),
            ("/admin/org/attention?status=OPEN", "organization-attention", PAGE_LABEL),
            (f"/admin/org/attention/{ids['item']}", "organization-attention-detail", PAGE_LABEL),
            ("/admin/org/ai-review", "organization-ai-review", PAGE_LABEL),
        )
        admin_org = {}
        for path, section, label in org_pages:
            admin_org[path] = check_help(admin_client, "admin", path, section, label)

        # An account that may only consult Organization: same help sections,
        # without the parts that describe the change controls it cannot see.
        admin_only_pages = {"/admin/org/positions/new", f"/admin/org/positions/{ids['parent']}/interview"}
        viewer_org = {}
        for path, section, label in org_pages:
            if path in admin_only_pages:
                check(f"viewer GET {path} stays forbidden (403)", viewer_client.get(path).status_code == 403)
                continue
            viewer_org[path] = check_help(viewer_client, "viewer", path, section, label)

        home_admin, home_viewer = admin_org["/admin/organization"], viewer_org["/admin/organization"]
        check("Organization home help has the typical flow", "<h3>Typical flow</h3>" in home_admin)
        check("Organization home help: administrator is told they can change it",
              "you are an administrator of this Domain" in home_admin)
        check("Organization home help: viewer is told changes are reserved",
              "Changes are reserved to the administrators of this Domain" in home_viewer
              and "you are an administrator of this Domain" not in home_viewer)
        detail_path = f"/admin/org/positions/{ids['parent']}"
        check("Position help describes Assign Occupant to an administrator",
              "Assign Occupant</strong>" in admin_org[detail_path])
        check("Position help hides Assign Occupant from a viewer",
              "Assign Occupant</strong>" not in viewer_org[detail_path])
        check("Process Ownerships help hides the creation form from a viewer",
              "Create Process Ownership</dt>" in admin_org["/admin/org/process-ownerships"]
              and "Create Process Ownership</dt>" not in viewer_org["/admin/org/process-ownerships"])
        check("Fallback help hides Set Fallback Policy from a viewer",
              "Set Fallback Policy</dt>" in admin_org["/admin/org/fallback-policies"]
              and "Set Fallback Policy</dt>" not in viewer_org["/admin/org/fallback-policies"])
        item_path = f"/admin/org/attention/{ids['item']}"
        check("Attention Item help hides the actions from a viewer",
              "Re-evaluate routing now</dt>" in admin_org[item_path]
              and "Re-evaluate routing now</dt>" not in viewer_org[item_path])

        # The chart's Position window (a fragment) carries no help of its own:
        # the Organization home's help explains it.
        resp = admin_client.get(f"/admin/organization/positions/{ids['parent']}/fragment")
        check("chart window fragment renders (200)", resp.status_code == 200)
        check("chart window fragment has no help dialog of its own", b'id="rf-help-dialog"' not in resp.data)
        check("Organization home help explains the chart window", "Open full page" in home_admin)
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
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
