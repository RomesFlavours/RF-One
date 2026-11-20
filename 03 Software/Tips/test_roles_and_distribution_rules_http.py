#!/usr/bin/env python
"""HTTP-level regression/verification test for the Tips app's Role
management (list/create/edit) and its effect on Tip Distribution Rule
creation.

Mirrors the throwaway-SQLite-database + Flask-test-client convention used
throughout this repo (e.g. `RF-One Web/tests/*_http.py`), adapted for
Tips's own lack of any authentication/CSRF mechanism (none exists here;
none is introduced by this test or by the change it verifies). Never
touches AWS or any production database.

Covers exactly what this task's own "VERIFICA" step asks for:
  - a newly created Role is selectable in the Distribution Rules create
    form (both Source Role and Recipient Role, since it is one shared list);
  - a Rule can then actually be saved;
  - before any Role exists, the create form shows a helpful message with a
    link to Role management, and the backend itself refuses to save a Rule
    referencing a nonexistent Role id (even calling the route directly).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_roles_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from rfone_data_store import models as m  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')  # not used by Tips - no CSRF here; kept for parity


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
        with tips_app.SessionFactory() as s:
            restaurant = m.Restaurant(name="Verification Restaurant", default_currency="USD")
            s.add(restaurant)
            s.commit()
            restaurant_id = restaurant.id

        client = tips_app.app.test_client()

        # -----------------------------------------------------------------
        # Before any Role exists: the create-rule form shows a helpful
        # message with a link to Role management, and the create select
        # boxes are disabled (never a silently empty, submittable select).
        # -----------------------------------------------------------------
        resp = client.get("/distribution-rules")
        check(
            "with zero Roles, the Distribution Rules page shows a helpful message linking to Role management",
            b"No Roles are defined yet" in resp.data and b'href="/roles/new"' in resp.data,
        )
        check(
            "the 'Manage Roles' link is present near the Create-a-new-Rule form",
            b"Manage Roles" in resp.data and b'href="/roles"' in resp.data,
        )

        # Even calling the backend route directly with a nonexistent Role
        # id (bypassing the disabled client-side select) must be refused.
        resp = client.post(
            "/distribution-rules/new",
            data={
                "source_role_id": "999999", "recipient_role_id": "999999",
                "calculation_base": "TOTAL_SALES", "rate": "5.0000", "effective_from": "2026-01-01",
            },
            follow_redirects=True,
        )
        check(
            "the backend refuses to save a Rule with a nonexistent Role id, even via a direct POST",
            resp.status_code == 200 and b"does not exist" in resp.data,
        )
        with tips_app.SessionFactory() as s:
            from sqlalchemy import select
            rule_count = len(list(s.scalars(select(m.TipDistributionRule)).all()))
            check("no Rule was persisted from the rejected direct POST", rule_count == 0)

        # -----------------------------------------------------------------
        # Role management: list (empty), create, list (shows it), edit.
        # -----------------------------------------------------------------
        resp = client.get("/roles")
        check("GET /roles opens (200)", resp.status_code == 200)
        check("with zero Roles, the Roles page shows the empty state", b"No Roles defined yet" in resp.data)

        resp = client.get("/roles/new")
        check("GET /roles/new opens (200)", resp.status_code == 200)

        resp = client.post(
            "/roles/new", data={"name": "Server", "code": "SRV", "description": "Front of house server", "active": "on"},
        )
        check("creating a Role redirects", resp.status_code in (302, 303))

        resp = client.post("/roles/new", data={"name": "Host", "active": "on"})
        check("creating a second Role redirects", resp.status_code in (302, 303))

        with tips_app.SessionFactory() as s:
            from rfone_data_store import restaurant_role_service as role_svc
            roles = role_svc.list_roles(s, restaurant_id)
            check("exactly two Roles persisted, correctly scoped to the Restaurant", len(roles) == 2)
            server_role = next(r for r in roles if r.name == "Server")
            host_role = next(r for r in roles if r.name == "Host")
            check(
                "the first Role's fields (name/code/description/active) persisted exactly as entered",
                server_role.code == "SRV" and server_role.description == "Front of house server" and server_role.active is True,
            )
            server_role_id, host_role_id = server_role.id, host_role.id

        resp = client.get("/roles")
        check("both Roles now appear in the Roles list", b"Server" in resp.data and b"Host" in resp.data)

        # Duplicate name is rejected.
        resp = client.post("/roles/new", data={"name": "Server", "active": "on"})
        check("creating a Role with a name already used for this Restaurant is rejected (400)", resp.status_code == 400)
        with tips_app.SessionFactory() as s:
            from rfone_data_store import restaurant_role_service as role_svc
            check("no duplicate Role row was created", len(role_svc.list_roles(s, restaurant_id)) == 2)

        # Edit.
        resp = client.get(f"/roles/{server_role_id}/edit")
        check("GET the edit form for an existing Role opens (200)", resp.status_code == 200)
        resp = client.post(
            f"/roles/{server_role_id}/edit",
            data={"name": "Server", "code": "SRV2", "description": "Updated", "active": "on"},
        )
        check("editing a Role redirects", resp.status_code in (302, 303))
        with tips_app.SessionFactory() as s:
            from rfone_data_store import restaurant_role_service as role_svc
            reloaded = role_svc.get_role(s, server_role_id)
            check("the edited Role's fields were updated correctly", reloaded.code == "SRV2" and reloaded.description == "Updated")

        # -----------------------------------------------------------------
        # Now that Roles exist: they are selectable (both as Source and
        # Recipient) on the Distribution Rules create form, and a valid
        # Rule can be saved.
        # -----------------------------------------------------------------
        resp = client.get("/distribution-rules")
        check(
            "with Roles defined, both role selects are populated (Server and Host each appear twice: "
            "once as a Source option, once as a Recipient option)",
            resp.data.count(b"<option value") >= 4 and b"Server" in resp.data and b"Host" in resp.data,
        )
        check(
            "the 'no Roles defined' warning is gone now that Roles exist",
            b"No Roles are defined yet" not in resp.data,
        )

        resp = client.post(
            "/distribution-rules/new",
            data={
                "source_role_id": str(server_role_id), "recipient_role_id": str(host_role_id),
                "calculation_base": "TOTAL_SALES", "rate": "10.0000", "effective_from": "2026-01-01",
                "created_by": "verification",
            },
        )
        check("creating a valid Rule redirects", resp.status_code in (302, 303))

        with tips_app.SessionFactory() as s:
            from sqlalchemy import select
            rules = list(s.scalars(select(m.TipDistributionRule)).all())
            check("exactly one Rule was persisted", len(rules) == 1)
            versions = list(s.scalars(
                select(m.TipDistributionRuleVersion).where(m.TipDistributionRuleVersion.rule_id == rules[0].id)
            ).all())
            check(
                "the Rule's version correctly references the Server (source) and Host (recipient) Roles just created",
                len(versions) == 1 and versions[0].source_role_id == server_role_id
                and versions[0].recipient_role_id == host_role_id,
            )

        resp = client.get("/distribution-rules")
        check(
            "the newly created Rule appears on the Distribution Rules page with the correct Role names",
            b"Server" in resp.data and b"Host" in resp.data and b"TOTAL_SALES" in resp.data,
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
