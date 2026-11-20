#!/usr/bin/env python
"""HTTP-level smoke test for the Organizational Responsibility + Attention
Management ADMIN/CONFIGURATION/TEST HARNESS screens (TASK_ATTENTION_ORG_
RUNTIME §12). Confirms the routes are admin-gated and every template
renders without error against real data produced through the service
layer — the actual business behavior (scope matching, routing, lifecycle)
is already covered by `test_attention_org_runtime.py` in `RF-One Data
Store`; this test only exercises the HTTP/template layer on top of it.

Mirrors this app's own test convention exactly (throwaway SQLite database,
Werkzeug test client, `main()` returning an exit code).
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_org_attention_admin_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "org-attention-admin-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import attention_service as att_svc  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import organizational_responsibility_service as org_svc  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


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

    try:
        with SessionFactory() as s:
            account_service.create_account(
                s, username="admin1", display_name="Admin One", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            account_service.create_account(
                s, username="plain1", display_name="Plain One", password="PlainPass123!",
                status="ACTIVE", is_admin=False,
            )
            s.commit()

            position = org_svc.create_position(s, name="TEST/DEMO HTTP Position")
            occupant = m.ActingIdentity(kind=m.HUMAN_USER, display_name="TEST/DEMO HTTP Occupant")
            s.add(occupant)
            s.flush()
            org_svc.assign_occupant(s, position=position, occupant=occupant, valid_from=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc))
            org_svc.set_process_ownership(s, domain="TESTHTTP", process_name="TestHttpProcess", position=position)
            s.commit()
            position_id = position.id

            item = att_svc.create_attention(
                s, source_domain="TESTHTTP", source_process_name="TestHttpProcess",
                reason="TEST/DEMO HTTP attention item", priority=m.ATTENTION_PRIORITY_HIGH,
            )
            s.commit()
            att_svc.route_attention(s, item=item)
            s.commit()
            item_id = item.id

        admin_client = web_app.app.test_client()
        login(admin_client, "admin1", "AdminPass123!")
        plain_client = web_app.app.test_client()
        login(plain_client, "plain1", "PlainPass123!")
        anon_client = web_app.app.test_client()

        check(
            # Relabeled to "Manage Organization" by TASK_ORG_CHART_ADMIN_PAGE,
            # pointing at /admin/organization instead of the plain Positions
            # list — see test_organization_chart_http.py for full coverage
            # of that page.
            "admin sees the 'Manage Organization' link on Home",
            b"Manage Organization" in admin_client.get("/").data,
        )

        for path in (
            "/admin/org/positions", "/admin/org/positions/new", f"/admin/org/positions/{position_id}",
            "/admin/org/process-ownerships", "/admin/org/attention", f"/admin/org/attention/{item_id}",
        ):
            resp = admin_client.get(path)
            check(f"admin GET {path} renders (200)", resp.status_code == 200, f"got {resp.status_code}")

        resp = plain_client.get("/admin/org/positions")
        check("non-admin GET /admin/org/positions is forbidden (403)", resp.status_code == 403)
        resp = anon_client.get("/admin/org/positions")
        check(
            "unauthenticated GET /admin/org/positions redirects to login",
            resp.status_code in (302, 303) and "/login" in resp.headers.get("Location", ""),
        )

        # Create a Position via the form.
        resp = admin_client.get("/admin/org/positions/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/org/positions/new", data={"name": "TEST/DEMO HTTP Position 2", "csrf_token": csrf},
        )
        check("admin creates a Position via the form (redirects)", resp.status_code in (302, 303))

        # Add a scope to the existing position.
        resp = admin_client.get(f"/admin/org/positions/{position_id}")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{position_id}/scopes/new",
            data={"scope_type": "RESTAURANT", "scope_id": "7", "csrf_token": csrf},
        )
        check("admin adds a Scope via the form (redirects)", resp.status_code in (302, 303))
        resp = admin_client.get(f"/admin/org/positions/{position_id}")
        check("the new Scope now appears on the Position detail page", b"RESTAURANT" in resp.data)

        # OPERATIONAL_UNIT scope (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §1): its
        # own dropdown/UI presents it against `Location`, independently from
        # RESTAURANT — never sharing RESTAURANT's id space or a raw numeric field.
        resp = admin_client.get(f"/admin/org/positions/{position_id}")
        check("Position editor exposes a dedicated OPERATIONAL_UNIT scope field", b'data-scope-value-for="OPERATIONAL_UNIT"' in resp.data)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{position_id}/scopes/new",
            data={"scope_type": "OPERATIONAL_UNIT", "scope_id": "3", "csrf_token": csrf},
        )
        check("admin adds an OPERATIONAL_UNIT Scope via the form (redirects)", resp.status_code in (302, 303))
        resp = admin_client.get(f"/admin/org/positions/{position_id}")
        check("the new OPERATIONAL_UNIT Scope now appears on the Position detail page", b"OPERATIONAL_UNIT" in resp.data)

        # Routing audit trail (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §5): the
        # detail page shows the history table, and "Re-evaluate routing now"
        # appends a new row rather than replacing the existing one.
        resp = admin_client.get(f"/admin/org/attention/{item_id}")
        check("Attention Item detail page shows the routing history table", b"Routing history" in resp.data)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/attention/{item_id}/route", data={"csrf_token": csrf},
        )
        check("admin re-evaluates routing via the form (redirects)", resp.status_code in (302, 303))
        with SessionFactory() as s:
            item_after_reroute = s.get(m.AttentionItem, item_id)
            history = att_svc.list_routing_history(s, item=item_after_reroute)
        check(
            "Re-evaluating routing appends a new audit-trail row rather than replacing the original one",
            len(history) == 2,
        )

        # Acknowledge then resolve the Attention Item.
        resp = admin_client.get(f"/admin/org/attention/{item_id}")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/attention/{item_id}/acknowledge",
            data={"by_acting_identity_id": str(occupant.id), "csrf_token": csrf},
        )
        check("admin acknowledges an Attention Item (redirects)", resp.status_code in (302, 303))
        resp = admin_client.get(f"/admin/org/attention/{item_id}")
        check("Attention Item now shows ACKNOWLEDGED", b"ACKNOWLEDGED" in resp.data)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/attention/{item_id}/resolve",
            data={"by_acting_identity_id": str(occupant.id), "csrf_token": csrf},
        )
        check("admin resolves an Attention Item (redirects)", resp.status_code in (302, 303))

    except Exception as exc:  # noqa: BLE001
        print(f"EXCEPTION: {exc}")
        checks_failed.append(f"unhandled exception: {exc}")

    print(f"\n{len(checks_passed)} passed, {len(checks_failed)} failed")
    return 0 if not checks_failed else 1


if __name__ == "__main__":
    try:
        exit_code = main()
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass
    sys.exit(exit_code)
