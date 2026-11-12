#!/usr/bin/env python
"""Regression test for the Training role-sync timing fix: navigation
checks (GET, and any read-only authorization check) must NEVER write
`TrainingAccount.role` — only explicit, authorized POSTs may. Mirrors this
repo's own standalone-script test convention. Uses a throwaway SQLite
database only — never AWS, never any production database.

Covers the task's own "VERIFICHE MIRATE" list:
  - GET Training con ruoli coerenti: accesso corretto, nessuna scrittura
  - GET Training con ruoli incoerenti: 403, ruoli invariati, sessione pulita
  - POST amministrativa di modifica ruolo: entrambi i ruoli aggiornati
  - POST che salva nuovamente lo stesso ruolo RF-One: incoerenza corretta
  - collegamento esplicito e creazione studente: ruoli coerenti
  - errore durante l'operazione: rollback, senza aggiornamenti parziali
  - studente non autorizzato a modificare ruoli, protezione CSRF mantenuta
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_role_sync_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "role-sync-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
import training_integration as ti  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.training import service as training_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
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
            account_service.create_account(s, username="admin", display_name="Admin", password="AdminPass123!", is_admin=True)

            trainer = account_service.create_account(s, username="trainer1", display_name="Trainer One", password="TrainerPass123!")
            account_service.set_domain_access(s, account_id=trainer.id, domain_code="TRAINING", enabled=True, role_code="trainer")
            ti.create_and_link_training_identity(s, rfone_account_id=trainer.id, role_code="trainer")

            coherent = account_service.create_account(s, username="coherent1", display_name="Coherent Student", password="Pass123!")
            account_service.set_domain_access(s, account_id=coherent.id, domain_code="TRAINING", enabled=True, role_code="student")
            ti.create_and_link_training_identity(s, rfone_account_id=coherent.id, role_code="student")

            incoherent = account_service.create_account(s, username="incoherent1", display_name="Incoherent Student", password="Pass123!")
            account_service.set_domain_access(s, account_id=incoherent.id, domain_code="TRAINING", enabled=True, role_code="student")
            ti.create_and_link_training_identity(s, rfone_account_id=incoherent.id, role_code="student")
            s.commit()

            coherent_id, incoherent_id, trainer_id = coherent.id, incoherent.id, trainer.id
            incoherent_link = ti.get_link_for_rfone_account(s, incoherent_id)
            incoherent_ta_id = incoherent_link.training_account_id

        # Force an incoherence directly (bypassing the app entirely) —
        # simulates a pre-existing bad state the fix must never "helpfully"
        # auto-correct during navigation.
        with SessionFactory() as s:
            ta = s.get(m.TrainingAccount, incoherent_ta_id)
            ta.role = "trainer"  # RFOneAccountDomainAccess.role_code stays 'student'
            s.commit()

        # -------------------------------------------------------------
        # GET with coherent roles: access granted, ZERO database write.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            before = s.get(m.TrainingAccount, ti.get_link_for_rfone_account(s, coherent_id).training_account_id)
            updated_at_before = before.updated_at

        coherent_client = web_app.app.test_client()
        login(coherent_client, "coherent1", "Pass123!")
        resp = coherent_client.get("/training", follow_redirects=True)
        check("coherent GET /training -> 200", resp.status_code == 200)

        with SessionFactory() as s:
            after = s.get(m.TrainingAccount, ti.get_link_for_rfone_account(s, coherent_id).training_account_id)
            check(
                "GET with coherent roles performs ZERO database write (updated_at unchanged)",
                after.updated_at == updated_at_before,
            )
            check("coherent role still 'student' (unchanged)", after.role == "student")

        # -------------------------------------------------------------
        # GET with incoherent roles: 403, roles left untouched, Training
        # session key removed, no redirect loop.
        # -------------------------------------------------------------
        incoherent_client = web_app.app.test_client()
        login(incoherent_client, "incoherent1", "Pass123!")
        resp = incoherent_client.get("/training")
        check("incoherent GET /training -> 403", resp.status_code == 403)
        check("403 response includes a human-readable message", "amministratore" in resp.data.decode().lower())
        check("403 response is a direct response, not a redirect (no Location header)", "Location" not in resp.headers)

        with incoherent_client.session_transaction() as sess:
            check(
                "stray Training session key removed after mismatch denial",
                ti.TRAINING_SESSION_ACCOUNT_KEY not in sess,
            )
            check("RF-One session itself remains intact (not logged out of RF-One)", "rfone_account_id" in sess)

        with SessionFactory() as s:
            access = next(
                r for r in account_service.list_domain_access_for_account(s, incoherent_id) if r.domain_code == "TRAINING"
            )
            ta = s.get(m.TrainingAccount, incoherent_ta_id)
            check("role_code left unchanged by the mismatch check", access.role_code == "student")
            check("TrainingAccount.role left unchanged by the mismatch check (still incoherent)", ta.role == "trainer")

        # -------------------------------------------------------------
        # Admin POST changing the TRAINING role: BOTH sides updated.
        # -------------------------------------------------------------
        admin_client = web_app.app.test_client()
        login(admin_client, "admin", "AdminPass123!")
        resp = admin_client.get(f"/admin/accounts/{incoherent_id}/access")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{incoherent_id}/access",
            data={"enabled_TRAINING": "on", "role_TRAINING": "student", "csrf_token": csrf},
        )
        check("admin role-fix POST redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            access = next(
                r for r in account_service.list_domain_access_for_account(s, incoherent_id) if r.domain_code == "TRAINING"
            )
            ta = s.get(m.TrainingAccount, incoherent_ta_id)
            check("POST admin: role_code is 'student'", access.role_code == "student")
            check("POST admin: TrainingAccount.role synced to 'student' (incoherence fixed)", ta.role == "student")

        resp = incoherent_client.get("/training", follow_redirects=True)
        check("after admin fix, the previously-blocked account can enter Training again", resp.status_code == 200)

        # -------------------------------------------------------------
        # POST re-saving the SAME RF-One value must still fix a
        # pre-existing incoherence (task §4) — force incoherence again
        # without changing role_code this time.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            ta = s.get(m.TrainingAccount, incoherent_ta_id)
            ta.role = "trainer"  # break it again, role_code stays 'student'
            s.commit()

        resp = admin_client.get(f"/admin/accounts/{incoherent_id}/access")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            # role_TRAINING is UNCHANGED ('student', same as already stored)
            f"/admin/accounts/{incoherent_id}/access",
            data={"enabled_TRAINING": "on", "role_TRAINING": "student", "csrf_token": csrf},
        )
        check("re-save-same-value POST redirects", resp.status_code in (302, 303))
        with SessionFactory() as s:
            ta = s.get(m.TrainingAccount, incoherent_ta_id)
            check(
                "saving the SAME RF-One role_code still corrects a pre-existing incoherence",
                ta.role == "student",
            )

        # -------------------------------------------------------------
        # Explicit linking and identity creation produce coherent roles.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            preexisting_ta = training_service.create_account(
                s, display_name="Old Trainer", username="oldtrainer", password="unused", role="student",
            )
            s.commit()
            preexisting_ta_id = preexisting_ta.id

            link_target = account_service.create_account(s, username="linktarget", display_name="Link Target", password="Pass123!")
            account_service.set_domain_access(s, account_id=link_target.id, domain_code="TRAINING", enabled=True, role_code="trainer")
            s.commit()
            link_target_id = link_target.id

            ti.link_existing_training_account(s, rfone_account_id=link_target_id, training_account_id=preexisting_ta_id)
            s.commit()

            ta_after_link = s.get(m.TrainingAccount, preexisting_ta_id)
            check(
                "explicit link syncs role to the account's existing role_code ('trainer')",
                ta_after_link.role == "trainer",
            )

            new_identity_account = account_service.create_account(s, username="newidentity", display_name="New Identity", password="Pass123!")
            s.commit()
            link2 = ti.create_and_link_training_identity(s, rfone_account_id=new_identity_account.id, role_code="student")
            s.commit()
            ta2 = s.get(m.TrainingAccount, link2.training_account_id)
            check("new identity created coherent from the start ('student')", ta2.role == "student")

        # -------------------------------------------------------------
        # Error during the operation -> rollback, no partial update.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            probe_account = account_service.create_account(s, username="rollbackprobe", display_name="Rollback Probe", password="Pass123!")
            account_service.set_domain_access(s, account_id=probe_account.id, domain_code="TRAINING", enabled=True, role_code="trainer")
            s.commit()
            probe_id = probe_account.id

        raised = False
        with SessionFactory() as s:
            try:
                ti.link_existing_training_account(s, rfone_account_id=probe_id, training_account_id=999999)
                s.commit()
            except Exception:
                s.rollback()
                raised = True
        check("linking a non-existent Training identity raises (no silent partial success)", raised)

        with SessionFactory() as s:
            check("rollback: no link row was created for the probe account", ti.get_link_for_rfone_account(s, probe_id) is None)

        # -------------------------------------------------------------
        # Non-admin cannot modify roles; CSRF protection still enforced.
        # -------------------------------------------------------------
        student_client = web_app.app.test_client()
        login(student_client, "coherent1", "Pass123!")
        resp = student_client.get(f"/admin/accounts/{incoherent_id}/access")
        check("non-admin cannot even VIEW the Domain Access page (403)", resp.status_code == 403)
        resp = student_client.post(
            f"/admin/accounts/{incoherent_id}/access",
            data={"enabled_TRAINING": "on", "role_TRAINING": "trainer", "csrf_token": "irrelevant"},
        )
        check("non-admin cannot POST to change TRAINING role (403)", resp.status_code == 403)

        with SessionFactory() as s:
            access = next(
                r for r in account_service.list_domain_access_for_account(s, incoherent_id) if r.domain_code == "TRAINING"
            )
            check("role_code unaffected by the non-admin's rejected attempt", access.role_code == "student")

        resp = admin_client.get(f"/admin/accounts/{incoherent_id}/access")
        real_csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{incoherent_id}/access",
            data={"enabled_TRAINING": "on", "role_TRAINING": "trainer", "csrf_token": "wrong-token-entirely"},
        )
        check("admin POST with an invalid CSRF token is rejected (400)", resp.status_code == 400)
        with SessionFactory() as s:
            access = next(
                r for r in account_service.list_domain_access_for_account(s, incoherent_id) if r.domain_code == "TRAINING"
            )
            check("CSRF-rejected POST made no change", access.role_code == "student")

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
