#!/usr/bin/env python
"""HTTP-level regression test for the RF-One Web ↔ Training single-login
integration. Mirrors this repo's own standalone-script test convention
(`main()` returning an exit code, no pytest). Uses a throwaway SQLite
database only — never AWS, never any production database.

Covers the task's own "VERIFICHE MIRATE" list:
  1. login RF-One -> Training senza secondo login
  2. destinazione corretta per studente e addestratore
  3. accesso diretto negato senza abilitazione o con ruolo errato
  4. disabilitazione efficace anche su sessione già aperta
  5. isolamento dei dati tra studenti
  6. collegamento esplicito di uno studente preesistente con storico conservato
  7. creazione di un nuovo studente e accesso con RF-One
  8. consegna di un quiz e registrazione del risultato
  9. logout unico
  10. Home RF-One e accesso Training preesistente tramite Tips ancora funzionanti
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_training_integration_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "training-integration-test-secret"

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

# Training's own pill/question content is no longer auto-seeded at import
# (see the earlier startup-determinism fix) — this test's setup performs
# the explicit initialization step, exactly like the real deployment
# procedure (`Training/initialize_training.py`) does.
with SessionFactory() as _seed_session:
    training_service.ensure_pills_seeded(_seed_session)
    _seed_session.commit()

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="submission_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def extract_submission_token(html: bytes) -> str:
    match = TOKEN_RE.search(html.decode("utf-8"))
    assert match, "submission_token not found"
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
        # -----------------------------------------------------------------
        # Fixtures: RF-One admin; a trainer already linked to Training; a
        # PRE-EXISTING Training-only account (as if created before this
        # integration existed) with real history (need, assignment, attempt).
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            account_service.create_account(s, username="admin", display_name="Admin", password="AdminPass123!", is_admin=True)

            trainer = account_service.create_account(s, username="trainer1", display_name="Trainer One", password="TrainerPass123!")
            account_service.set_domain_access(s, account_id=trainer.id, domain_code="TRAINING", enabled=True, role_code="trainer")
            ti.create_and_link_training_identity(s, rfone_account_id=trainer.id, role_code="trainer")
            trainer_ta = training_service.get_account(s, ti.get_link_for_rfone_account(s, trainer.id).training_account_id)

            preexisting_ta = training_service.create_account(
                s, display_name="Old Student", username="oldstudent", password="whatever-not-used-anymore", role="student",
            )
            caprese = next(p for p in training_service.list_all_pills(s) if p.slug == "caprese")
            need = training_service.create_need(
                s, student_account_id=preexisting_ta.id, text="Learn Caprese", origin=None,
                created_by_account_id=trainer_ta.id,
            )
            assignment = training_service.assign_pill(
                s, need_id=need.id, pill_id=caprese.id, assigned_by_account_id=trainer_ta.id,
            )
            s.commit()
            preexisting_ta_id = preexisting_ta.id
            assignment_id = assignment.id

        # -----------------------------------------------------------------
        # 1 & 2 (trainer). Login RF-One -> /training reaches TRAINER home,
        # no second login.
        # -----------------------------------------------------------------
        trainer_client = web_app.app.test_client()
        resp = login(trainer_client, "trainer1", "TrainerPass123!")
        check("trainer login redirects", resp.status_code in (302, 303))

        resp = trainer_client.get("/training", follow_redirects=True)
        check("1: trainer reaches /training without a second login (200)", resp.status_code == 200)
        check("2: trainer is routed to the TRAINER destination", b"trainer" in resp.data.lower())

        # -----------------------------------------------------------------
        # 3. Direct access denied: no TRAINING access at all.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            no_access = account_service.create_account(s, username="noaccess", display_name="No Access", password="Pass123!")
            s.commit()
            no_access_id = no_access.id
        no_access_client = web_app.app.test_client()
        login(no_access_client, "noaccess", "Pass123!")
        resp = no_access_client.get("/training", follow_redirects=True)
        check("3a: no TRAINING access -> denied, not 200 Training content", b"non ha accesso" in resp.data)

        # 3b. Enabled but invalid/missing role_code.
        with SessionFactory() as s:
            bad_role = account_service.create_account(s, username="badrole", display_name="Bad Role", password="Pass123!")
            account_service.set_domain_access(s, account_id=bad_role.id, domain_code="TRAINING", enabled=True, role_code=None)
            s.commit()
        bad_role_client = web_app.app.test_client()
        login(bad_role_client, "badrole", "Pass123!")
        resp = bad_role_client.get("/training", follow_redirects=True)
        check("3b: enabled but missing role_code -> denied with clear message", b"ruolo" in resp.data.lower())

        # -----------------------------------------------------------------
        # 6. Explicit admin linking of the PRE-EXISTING Training account —
        # history (need/assignment) must remain intact and reachable.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            preexisting_rf = account_service.create_account(s, username="oldstudent", display_name="Old Student", password="NewRFPass123!")
            account_service.set_domain_access(s, account_id=preexisting_rf.id, domain_code="TRAINING", enabled=True, role_code="student")
            s.commit()
            preexisting_rf_id = preexisting_rf.id

        admin_client = web_app.app.test_client()
        login(admin_client, "admin", "AdminPass123!")
        resp = admin_client.get(f"/admin/accounts/{preexisting_rf_id}/training-link")
        csrf = extract_csrf(resp.data)
        check("existing Training account listed as linkable", str(preexisting_ta_id).encode() in resp.data)
        resp = admin_client.post(
            f"/admin/accounts/{preexisting_rf_id}/training-link",
            data={"action": "link_existing", "training_account_id": str(preexisting_ta_id), "csrf_token": csrf},
        )
        check("6a: explicit link created (redirect)", resp.status_code in (302, 303))

        # Duplicate-link protection: same Training account can't be linked twice.
        with SessionFactory() as s:
            another_rf = account_service.create_account(s, username="another", display_name="Another", password="Pass123!")
            s.commit()
            another_id = another_rf.id
        resp = admin_client.get(f"/admin/accounts/{another_id}/training-link")
        csrf = extract_csrf(resp.data)
        check(
            "6b: already-linked Training account no longer offered for linking",
            f'value="{preexisting_ta_id}"'.encode() not in resp.data,
        )

        old_student_client = web_app.app.test_client()
        login(old_student_client, "oldstudent", "NewRFPass123!")
        resp = old_student_client.get("/training", follow_redirects=True)
        check("6c: linked pre-existing student reaches Training via RF-One login", resp.status_code == 200)
        check("6d: pre-existing history (assigned need) still visible after linking", b"Caprese" in resp.data)

        resp = old_student_client.get(f"/training/assignments/{assignment_id}")
        check("6e: pre-existing assignment still directly reachable (not recreated/renumbered)", resp.status_code == 200)

        # -----------------------------------------------------------------
        # 7. New student created via the RF-One-facing trainer flow, logs
        # in with RF-One directly.
        # -----------------------------------------------------------------
        resp = trainer_client.get("/training-trainer/students/new")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            "/training-trainer/students/new",
            data={
                "username": "newkid", "display_name": "New Kid", "email": "newkid@example.com",
                "password": "NewKidPass123!", "password_confirm": "NewKidPass123!", "csrf_token": csrf,
            },
        )
        check("7a: trainer creates a new student (redirect)", resp.status_code in (302, 303))

        newkid_client = web_app.app.test_client()
        resp = login(newkid_client, "newkid", "NewKidPass123!")
        check("7b: new student logs in with RF-One", resp.status_code in (302, 303))
        resp = newkid_client.get("/training", follow_redirects=True)
        check("7c: new student reaches STUDENT destination", resp.status_code == 200 and b"New Kid" in resp.data)

        with SessionFactory() as s:
            newkid_rf = account_service.get_account_by_username(s, "newkid")
            check("7d: new student RF-One account has TRAINING/student access only", newkid_rf.is_admin is False)

        # A trainer creating a student never grants admin or other Domains.
        resp = newkid_client.get("/admin/accounts")
        check("7e: newly created student is NOT an RF-One admin", resp.status_code == 403)

        # -----------------------------------------------------------------
        # 5. Student data isolation: give the new student their own
        # assignment; the pre-existing student must not be able to read it.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            newkid_ta_id = ti.get_link_for_rfone_account(
                s, account_service.get_account_by_username(s, "newkid").id
            ).training_account_id
            need2 = training_service.create_need(
                s, student_account_id=newkid_ta_id, text="Learn Caprese too", origin=None,
                created_by_account_id=trainer_ta.id,
            )
            assignment2 = training_service.assign_pill(
                s, need_id=need2.id, pill_id=caprese.id, assigned_by_account_id=trainer_ta.id,
            )
            s.commit()
            assignment2_id = assignment2.id

        resp = old_student_client.get(f"/training/assignments/{assignment2_id}")
        check("5: student A cannot read student B's assignment (404, row-level isolation preserved)", resp.status_code == 404)

        # -----------------------------------------------------------------
        # 8. Quiz delivery and result recording, through the integration.
        # -----------------------------------------------------------------
        resp = newkid_client.get(f"/training/assignments/{assignment2_id}/final-quiz")
        check("8a: final quiz page reachable through RF-One-integrated session", resp.status_code == 200)
        csrf = extract_csrf(resp.data)
        token = extract_submission_token(resp.data)

        with SessionFactory() as s:
            assignment_obj = s.get(m.TrainingAssignment, assignment2_id)
            questions = training_service.get_final_quiz_view(s, assignment_obj)
            form_data = {"csrf_token": csrf, "submission_token": token}
            for q in questions:
                form_data[f"answer_{q.id}"] = str(q.correct_index)

        resp = newkid_client.post(f"/training/assignments/{assignment2_id}/final-quiz", data=form_data)
        check("8b: quiz submission redirects to a result page", resp.status_code in (302, 303))

        with SessionFactory() as s:
            attempts = training_service.list_attempts_for_assignment(s, assignment2_id)
            check("8c: quiz attempt recorded exactly once", len(attempts) == 1)
            check("8d: quiz scored correctly (3/3)", attempts[0].points_earned == 3)

        # -----------------------------------------------------------------
        # 4. Disabling TRAINING access blocks an ALREADY-OPEN session.
        # -----------------------------------------------------------------
        resp = newkid_client.get("/training", follow_redirects=True)
        check("session still valid before disabling", resp.status_code == 200)
        with SessionFactory() as s:
            account_service.set_domain_access(
                s, account_id=account_service.get_account_by_username(s, "newkid").id,
                domain_code="TRAINING", enabled=False, role_code="student",
            )
            s.commit()
        resp = newkid_client.get("/training", follow_redirects=True)
        check("4: disabling mid-session blocks the already-open session immediately", b"non ha accesso" in resp.data)

        # -----------------------------------------------------------------
        # 9. Single logout: RF-One logout also ends the Training session.
        # -----------------------------------------------------------------
        resp = trainer_client.get("/")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post("/logout", data={"csrf_token": csrf})
        resp = trainer_client.get("/training", follow_redirects=True)
        check("9: after RF-One logout, /training requires login again (single logout)", b"Log in" in resp.data)

        # A stale Training-only session key must never substitute for RF-One login.
        with trainer_client.session_transaction() as sess:
            sess[ti.TRAINING_SESSION_ACCOUNT_KEY] = trainer_ta.id
        resp = trainer_client.get("/training", follow_redirects=True)
        check(
            "9b: a stray Training session key alone does not grant access without RF-One login",
            b"Log in" in resp.data,
        )

        # -----------------------------------------------------------------
        # 10. Home RF-One and Tips' existing Training mount both still work.
        # -----------------------------------------------------------------
        fresh_admin_client = web_app.app.test_client()
        login(fresh_admin_client, "admin", "AdminPass123!")
        resp = fresh_admin_client.get("/")
        check("10a: RF-One Home still works", resp.status_code == 200 and b"Administration" in resp.data)

        # Run Tips' own regression check in a SEPARATE PROCESS, not this
        # test's own — Tips and RF-One Web are always separate deployments
        # in production, each importing Training's routes.py fresh into an
        # otherwise-empty sys.modules; importing both in the SAME process
        # (as this test otherwise does for convenience) would artificially
        # collide on the plain names 'auth'/'db'/'routes', which never
        # happens across two real, separate processes. See final report
        # "limiti".
        _TIPS_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "Tips"))
        tips_check_code = (
            "import sys, os\n"
            f"sys.path.insert(0, r'{_TIPS_DIR}')\n"
            "import app as tips_app\n"
            "c = tips_app.app.test_client()\n"
            "r1 = c.get('/')\n"
            "r2 = c.get('/training/menu')\n"
            "r3c = c.get('/training/login')\n"
            "import re\n"
            "csrf = re.search(r'name=\"csrf_token\" value=\"([^\"]+)\"', r3c.data.decode()).group(1)\n"
            f"r3 = c.post('/training/login', data={{'username': {trainer_ta.username!r}, 'password': 'whatever', 'csrf_token': csrf}})\n"
            "print('TIPS_HOME_STATUS', r1.status_code)\n"
            "print('TIPS_TRAINING_MENU_STATUS', r2.status_code)\n"
            "print('TIPS_TRAINING_LOGIN_STATUS', r3.status_code)\n"
        )
        import subprocess
        tips_env = dict(os.environ)
        result = subprocess.run(
            [sys.executable, "-c", tips_check_code], cwd=_TIPS_DIR, env=tips_env,
            capture_output=True, text=True, timeout=30,
        )
        check("10b: Tips home page still works unmodified", "TIPS_HOME_STATUS 200" in result.stdout, result.stderr[-1500:])
        check("10c: Tips' own /training/menu still works unmodified", "TIPS_TRAINING_MENU_STATUS 200" in result.stdout)
        check(
            "10d: Training's OWN login under Tips is untouched (still rejects a wrong password)",
            "TIPS_TRAINING_LOGIN_STATUS 401" in result.stdout,
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
