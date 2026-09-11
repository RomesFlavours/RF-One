#!/usr/bin/env python
"""HTTP-level regression test for the Home link relocation ("Manage
Training students" moved from the general Home to Training's own trainer
home; "Manage Legal Entities" takes its former place on the general Home)
and the new minimal Legal Entity management (list/create/edit).

Mirrors this app's own test convention: throwaway SQLite database created
before `app.py` is imported, migrated explicitly, Werkzeug's Flask test
client, `main()` returning an exit code. Never touches AWS or any
production database.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_links_legal_entities_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "links-legal-entities-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
import training_integration as ti  # noqa: E402
from rfone_data_store import legal_entity_service  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
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
            admin = account_service.create_account(
                s, username="admin1", display_name="Admin One", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            plain = account_service.create_account(
                s, username="plain1", display_name="Plain One", password="PlainPass123!", status="ACTIVE",
            )
            trainer = account_service.create_account(
                s, username="trainer1", display_name="Trainer One", password="TrainerPass123!", status="ACTIVE",
            )
            account_service.set_domain_access(s, account_id=trainer.id, domain_code="TRAINING", enabled=True, role_code="trainer")
            ti.create_and_link_training_identity(s, rfone_account_id=trainer.id, role_code="trainer")
            s.commit()

        # -----------------------------------------------------------------
        # Home: admin sees "Manage Legal Entities"; plain user does not.
        # -----------------------------------------------------------------
        admin_client = web_app.app.test_client()
        login(admin_client, "admin1", "AdminPass123!")
        resp = admin_client.get("/")
        check(
            "admin sees 'Manage Legal Entities' on the general Home, linking to /admin/legal-entities",
            b"Manage Legal Entities" in resp.data and b'href="/admin/legal-entities"' in resp.data,
        )
        check(
            "'Manage Training students' no longer appears on the general Home (even for an admin)",
            b"Manage Training students" not in resp.data,
        )

        plain_client = web_app.app.test_client()
        login(plain_client, "plain1", "PlainPass123!")
        resp = plain_client.get("/")
        check(
            "a non-admin does NOT see 'Manage Legal Entities' on the general Home",
            b"Manage Legal Entities" not in resp.data,
        )

        # -----------------------------------------------------------------
        # Training trainer home: "Manage Training students" now lives here,
        # same destination/authorization as before (require_training_trainer).
        # -----------------------------------------------------------------
        trainer_client = web_app.app.test_client()
        login(trainer_client, "trainer1", "TrainerPass123!")
        resp = trainer_client.get("/training", follow_redirects=True)
        check("trainer reaches the Training trainer home (200)", resp.status_code == 200)
        check(
            "'Manage Training students' now appears on the Training trainer home, "
            "linking to the same /training-trainer/students destination",
            b"Manage Training students" in resp.data and b'href="/training-trainer/students"' in resp.data,
        )

        resp = trainer_client.get("/training-trainer/students")
        check(
            "following that link still opens the same, unchanged trainer-facing student list (200)",
            resp.status_code == 200,
        )

        # -----------------------------------------------------------------
        # /admin/legal-entities is admin-gated, same as /admin/accounts.
        # -----------------------------------------------------------------
        resp = plain_client.get("/admin/legal-entities")
        check("non-admin GET /admin/legal-entities is forbidden (403)", resp.status_code == 403)

        anon_client = web_app.app.test_client()
        resp = anon_client.get("/admin/legal-entities")
        check(
            "unauthenticated GET /admin/legal-entities redirects to login",
            resp.status_code in (301, 302, 303, 308),
        )

        resp = admin_client.get("/admin/legal-entities")
        check("admin can open /admin/legal-entities (200)", resp.status_code == 200)

        # -----------------------------------------------------------------
        # Minimal Legal Entity management: create, then edit.
        # -----------------------------------------------------------------
        resp = admin_client.get("/admin/legal-entities/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/legal-entities/new",
            data={"legal_name": "Rome's Flavours Winter Park LLC", "status": "ACTIVE", "csrf_token": csrf},
        )
        check("F: admin creates a Legal Entity (redirects)", resp.status_code in (302, 303))

        with SessionFactory() as s:
            entities = legal_entity_service.list_legal_entities(s)
            check("F: exactly one Legal Entity persisted", len(entities) == 1)
            entity_id = entities[0].id
            check(
                "F: name and default ACTIVE status persisted correctly",
                entities[0].legal_name == "Rome's Flavours Winter Park LLC" and entities[0].status == "ACTIVE",
            )

        resp = admin_client.get("/admin/legal-entities/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/legal-entities/new", data={"legal_name": "  ", "status": "ACTIVE", "csrf_token": csrf},
        )
        check("G: an empty Legal Entity name is rejected (400)", resp.status_code == 400)
        with SessionFactory() as s:
            check("G: no second row was created", len(legal_entity_service.list_legal_entities(s)) == 1)

        resp = admin_client.get(f"/admin/legal-entities/{entity_id}/edit")
        check("H: edit form opens (200)", resp.status_code == 200)
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/legal-entities/{entity_id}/edit",
            data={"legal_name": "Rome's Flavours Mount Dora LLC", "status": "INACTIVE", "csrf_token": csrf},
        )
        check("H: editing a Legal Entity redirects", resp.status_code in (302, 303))
        with SessionFactory() as s:
            reloaded = legal_entity_service.get_legal_entity(s, entity_id)
            check(
                "H: name and status updated correctly",
                reloaded.legal_name == "Rome's Flavours Mount Dora LLC" and reloaded.status == "INACTIVE",
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
