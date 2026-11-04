#!/usr/bin/env python
"""HTTP-level test for the Organizational Chart Admin Page
(TASK_ORG_CHART_ADMIN_PAGE §21): interactive graph data, click-to-edit
fragment, Backup Position, Organizational Fallback Policy, Organizational
Coverage Check, Scope Interview harness, AI review boundary, Home Page
link, and admin authorization on every new route.

Mirrors this app's own test convention exactly (throwaway SQLite database,
Werkzeug test client, `main()` returning an exit code). No AI provider is
called by this test.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_org_chart_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "org-chart-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import organizational_responsibility_service as org_svc  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

UTC = timezone.utc
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

            parent = org_svc.create_position(s, name="TEST/DEMO Parent Position")
            child = org_svc.create_position(s, name="TEST/DEMO Child Position", parent=parent)
            occupant = m.ActingIdentity(kind=m.HUMAN_USER, display_name="TEST/DEMO Occupant")
            s.add(occupant)
            s.flush()
            org_svc.assign_occupant(s, position=parent, occupant=occupant, valid_from=datetime(2026, 1, 1, tzinfo=UTC))
            org_svc.set_process_ownership(s, domain="TESTHTTPCHART", process_name="TestProcess", position=child)
            s.commit()
            parent_id, child_id = parent.id, child.id

        admin_client = web_app.app.test_client()
        login(admin_client, "admin1", "AdminPass123!")
        plain_client = web_app.app.test_client()
        login(plain_client, "plain1", "PlainPass123!")
        anon_client = web_app.app.test_client()

        # -- Home Page link authorization --------------------------------------------
        check("admin sees 'Organization' under Settings on Home", b'href="/admin/organization"' in admin_client.get("/").data)
        check("non-admin does NOT see 'Organization' on Home", b'href="/admin/organization"' not in plain_client.get("/").data)

        # -- New pages render, admin-gated --------------------------------------------
        for path in (
            "/admin/organization", "/admin/organization/graph-data.json",
            f"/admin/organization/positions/{parent_id}/fragment",
            "/admin/org/fallback-policies", "/admin/org/coverage-check",
            f"/admin/org/positions/{parent_id}/interview", "/admin/org/ai-review",
        ):
            resp = admin_client.get(path)
            check(f"admin GET {path} renders (200)", resp.status_code == 200, f"got {resp.status_code}")
            resp = plain_client.get(path)
            check(f"non-admin GET {path} is forbidden (403)", resp.status_code == 403)
            resp = anon_client.get(path)
            check(
                f"unauthenticated GET {path} redirects to login",
                resp.status_code in (302, 303) and "/login" in resp.headers.get("Location", ""),
            )

        # -- /admin/org/chart redirects to /admin/organization ------------------------
        resp = admin_client.get("/admin/org/chart")
        check("old /admin/org/chart redirects to /admin/organization", resp.status_code in (301, 302, 303))

        # -- Graph data reflects DB hierarchy -----------------------------------------
        graph = admin_client.get("/admin/organization/graph-data.json").get_json()
        by_id = {p["id"]: p for p in graph["positions"]}
        check("graph data includes the parent Position", parent_id in by_id)
        check("graph data includes the child Position with the correct parent_id", by_id[child_id]["parent_id"] == parent_id)
        check("graph data shows the parent's real Occupant, not VACANT", by_id[parent_id]["vacant"] is False and by_id[parent_id]["occupant_name"] == "TEST/DEMO Occupant")
        check("graph data flags the child (owns a Process, vacant, no backup/fallback) as a coverage gap", by_id[child_id]["gap_warning"] is True)

        # -- Parent change reflected in graph ------------------------------------------
        with SessionFactory() as s:
            grandparent = org_svc.create_position(s, name="TEST/DEMO Grandparent Position")
            s.commit()
            grandparent_id = grandparent.id
            child_row = s.get(m.Position, child_id)
            child_row.parent_position_id = grandparent_id
            s.commit()
        graph2 = admin_client.get("/admin/organization/graph-data.json").get_json()
        by_id2 = {p["id"]: p for p in graph2["positions"]}
        check("graph reflects a parent Position change immediately (derived from DB, never static)", by_id2[child_id]["parent_id"] == grandparent_id)

        # -- create/edit Position, parent change via UI, Occupant assignment ---------
        resp = admin_client.get("/admin/org/positions/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post("/admin/org/positions/new", data={"name": "TEST/DEMO New Position", "csrf_token": csrf})
        check("admin creates a Position via the form", resp.status_code in (302, 303))

        resp = admin_client.get(f"/admin/org/positions/{child_id}")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{child_id}/assignments/new",
            data={"acting_identity_id": str(occupant.id), "csrf_token": csrf},
        )
        check("Occupant assignment via the full detail page works", resp.status_code in (302, 303))

        # -- structured Scope (never free text) ---------------------------------------
        resp = admin_client.get(f"/admin/org/positions/{child_id}")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{child_id}/scopes/new",
            data={"scope_type": "RESTAURANT", "scope_id": "1", "csrf_token": csrf},
        )
        check("structured Scope creation accepted (dropdown-driven, not free text)", resp.status_code in (302, 303))

        # -- Process Ownership from the position page -------------------------------
        resp = admin_client.get("/admin/org/process-ownerships")
        check("Process Ownership list page renders", resp.status_code == 200)

        # -- Backup Position -----------------------------------------------------------
        resp = admin_client.get(f"/admin/org/positions/{child_id}")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{child_id}/backups/new",
            data={"backup_position_id": str(parent_id), "csrf_token": csrf},
        )
        check("Backup Position creation via the form works", resp.status_code in (302, 303))
        resp = admin_client.get(f"/admin/org/positions/{child_id}")
        check("the new Backup Position appears on the Position detail page", b"TEST/DEMO Parent Position" in resp.data)

        # -- badge fix (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §4): a Process
        # actually routable via its owner's Backup Position must NOT be
        # shown as a "Coverage gap" — it is delivered, via Backup. Uses
        # fresh Positions (the shared child_id above already has a direct
        # Occupant by this point in the test, from the earlier assignment
        # step, so it would no longer exercise the Backup path at all). ----
        with SessionFactory() as s:
            badge_owner = org_svc.create_position(s, name="TEST/DEMO Badge Owner (vacant, has Backup)")
            badge_backup = org_svc.create_position(s, name="TEST/DEMO Badge Backup (occupied)")
            badge_backup_occupant = m.ActingIdentity(kind=m.HUMAN_USER, display_name="TEST/DEMO Badge Backup Occupant")
            s.add(badge_backup_occupant)
            s.flush()
            org_svc.assign_occupant(s, position=badge_backup, occupant=badge_backup_occupant, valid_from=datetime(2026, 1, 1, tzinfo=UTC))
            org_svc.set_process_ownership(s, domain="TESTHTTPCHART", process_name="BadgeProcess", position=badge_owner)
            org_svc.add_position_backup(s, covered_position=badge_owner, backup_position=badge_backup)
            s.commit()
            badge_owner_id = badge_owner.id
        graph_after_backup = admin_client.get("/admin/organization/graph-data.json").get_json()
        by_id_after_backup = {p["id"]: p for p in graph_after_backup["positions"]}
        check(
            "graph data does NOT flag a Position as a coverage gap once its Backup Position resolves the Process",
            by_id_after_backup[badge_owner_id]["gap_warning"] is False,
        )
        check(
            "graph data instead flags that Position as covered via Backup",
            by_id_after_backup[badge_owner_id]["covered_via_backup"] is True,
        )

        # -- Temporary Coverage ----------------------------------------------------------
        resp = admin_client.get(f"/admin/org/positions/{child_id}")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{child_id}/coverages/new",
            data={"delegate_acting_identity_id": str(occupant.id), "csrf_token": csrf},
        )
        check("Temporary Coverage creation via the form works", resp.status_code in (302, 303))

        # -- vacant Position visible in graph -------------------------------------------
        with SessionFactory() as s:
            vacant_position = org_svc.create_position(s, name="TEST/DEMO Vacant For Graph")
            s.commit()
            vacant_id = vacant_position.id
        graph3 = admin_client.get("/admin/organization/graph-data.json").get_json()
        by_id3 = {p["id"]: p for p in graph3["positions"]}
        check("a vacant Position is correctly marked vacant in the graph", by_id3[vacant_id]["vacant"] is True)

        # -- coverage gap detection / fallback resolution -------------------------------
        resp = admin_client.get("/admin/org/coverage-check")
        check("Coverage Check page renders with per-process detail", b"TestProcess" in resp.data)

        resp = admin_client.get("/admin/org/fallback-policies")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/org/fallback-policies/new",
            data={"fallback_position_id": str(parent_id), "scope_type": "GLOBAL", "csrf_token": csrf},
        )
        check("Organizational Fallback Policy creation via the form works", resp.status_code in (302, 303))
        resp = admin_client.get("/admin/org/fallback-policies")
        check("the new Fallback Policy appears on its own admin page", b"TEST/DEMO Parent Position" in resp.data)

        # -- badge fix (TASK_ORG_RUNTIME_CONSISTENCY_FIXES §4): a Process
        # with a vacant owner and NO Backup, now resolved only via the
        # freshly-configured GLOBAL Organizational Fallback Policy, must be
        # shown as "covered via Fallback", never as a generic "gap". -------
        with SessionFactory() as s:
            fallback_owner = org_svc.create_position(s, name="TEST/DEMO Fallback-badge Owner (vacant, no backup)")
            org_svc.set_process_ownership(s, domain="TESTHTTPCHART", process_name="FallbackBadgeProcess", position=fallback_owner)
            s.commit()
            fallback_owner_id = fallback_owner.id
        graph_after_fallback = admin_client.get("/admin/organization/graph-data.json").get_json()
        by_id_after_fallback = {p["id"]: p for p in graph_after_fallback["positions"]}
        check(
            "graph data does NOT flag a Position as a coverage gap once the GLOBAL Fallback Policy resolves the Process",
            by_id_after_fallback[fallback_owner_id]["gap_warning"] is False,
        )
        check(
            "graph data instead flags that Position as covered via Organizational Fallback",
            by_id_after_fallback[fallback_owner_id]["covered_via_fallback"] is True,
        )

        # -- trigger/process without owner: an Attention Item on a truly unowned
        # process still appears somewhere in the coverage/attention picture ----------
        with SessionFactory() as s:
            from rfone_data_store import attention_service as att_svc
            item = att_svc.create_attention(
                s, source_domain="TESTHTTPCHART", source_process_name="NeverOwnedProcess",
                reason="TEST/DEMO unowned", priority=m.ATTENTION_PRIORITY_HIGH,
            )
            s.commit()
            att_svc.route_attention(s, item=item)
            s.commit()
        resp = admin_client.get("/admin/org/coverage-check")
        check("a Process with no owner appears in the Coverage Check report", b"NeverOwnedProcess" in resp.data)

        # -- Scope Interview harness (ADMIN/TEST ONLY, saves structured data) --------
        resp = admin_client.get(f"/admin/org/positions/{parent_id}/interview")
        check("Interview harness page is labeled ADMIN / TEST ONLY", b"ADMIN / TEST ONLY" in resp.data)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/org/positions/{parent_id}/interview",
            data={"domain": "TESTINTERVIEW", "process_name": "InterviewProcess", "csrf_token": csrf},
        )
        check("Interview submission saves structured Process Ownership (redirects)", resp.status_code in (302, 303))
        with SessionFactory() as s:
            found = list(
                s.query(m.ProcessOwnership).filter_by(domain="TESTINTERVIEW", process_name="InterviewProcess")
            )
            check("Interview answer was persisted as a real, structured ProcessOwnership row", len(found) == 1)

        # -- AI Consistency Review boundary — never a real AI call --------------------
        resp = admin_client.get("/admin/org/ai-review")
        check("AI Review page states NOT YET IMPLEMENTED", b"NOT YET IMPLEMENTED" in resp.data)

    except Exception as exc:  # noqa: BLE001
        print(f"EXCEPTION: {exc}")
        import traceback
        traceback.print_exc()
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
