#!/usr/bin/env python
"""HTTP-level regression test for Training's first operational version.

Mirrors `Selection/test_acting_identity_http.py`'s and `Selection/
test_batch_upload.py`'s own convention exactly: a throwaway SQLite database
created BEFORE `app.py` is imported (via `RFONE_DATABASE_URL`), Werkzeug's
Flask test client, `main()` returning an exit code. Never touches the real
`RF-One Data Store/data/rfone.db` — see the `UnsafeTestDatabaseError` guard
this repo's own `resolve_test_database_url()` would raise if it ever did.

This file complements (does not repeat) `RF-One Data Store/rfone_data_store/
training/service.py`'s own direct, non-HTTP smoke test already run during
development — it focuses on what only exists at the HTTP boundary: real
login/session cookies, CSRF enforcement, cross-student access control (IDOR)
through actual requests from separate "browsers", double-submit protection
over the wire, and the two required regression checks (Tips home, /training/
menu)."""

from __future__ import annotations

import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="training_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)  # let the explicit migration step below create it fresh
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

# App/Training import no longer migrates or seeds automatically (worker
# startup must never do either — see `db.py`/`initialize_training.py`), so
# this test's setup performs both explicitly, exactly like the real
# deployment procedure will: migrate, then initialize Training.
from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

_TIPS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Tips"))
if _TIPS_DIR not in sys.path:
    sys.path.insert(0, _TIPS_DIR)

import app as tips_app  # noqa: E402

from db import SessionFactory as TrainingSessionFactory  # noqa: E402
from rfone_data_store.training import service as svc  # noqa: E402

with TrainingSessionFactory() as _init_session:
    svc.ensure_pills_seeded(_init_session)
    _init_session.commit()

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="submission_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    m = CSRF_RE.search(html.decode("utf-8"))
    assert m, "csrf_token not found in response HTML"
    return m.group(1)


def extract_submission_token(html: bytes) -> str:
    m = TOKEN_RE.search(html.decode("utf-8"))
    assert m, "submission_token not found in response HTML"
    return m.group(1)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool) -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}")

    try:
        # -----------------------------------------------------------------
        # Fixture setup — bootstrap one trainer and pull the pill id we'll
        # use, directly via the service layer (equivalent to what
        # create_trainer.py's CLI does under the hood; the CLI's own
        # argument-parsing/prompt flow is exercised separately, not over
        # HTTP).
        # -----------------------------------------------------------------
        with TrainingSessionFactory() as s:
            trainer = svc.create_account(
                s, display_name="HTTP Test Trainer", username="httptesttrainer",
                password="TrainerPass123!", role="trainer",
            )
            s.commit()
            caprese = next(p for p in svc.list_all_pills(s) if p.slug == "caprese")
            caprese_id = caprese.id

        trainer_client = tips_app.app.test_client()
        student_a_client = tips_app.app.test_client()
        student_b_client = tips_app.app.test_client()
        anon_client = tips_app.app.test_client()

        # -----------------------------------------------------------------
        # Regression: Tips home and /training/menu unaffected.
        # -----------------------------------------------------------------
        resp = anon_client.get("/")
        check("Tips home page still returns 200", resp.status_code == 200)
        resp = anon_client.get("/training/menu")
        check("/training/menu still returns 200", resp.status_code == 200)
        check("/training/menu body still contains the dish guide data", b'"id": "caprese"' in resp.data)

        # -----------------------------------------------------------------
        # Login: wrong credentials rejected; unknown route access blocked
        # pre-login.
        # -----------------------------------------------------------------
        resp = anon_client.get("/training")
        check("unauthenticated GET /training redirects to login", resp.status_code in (301, 302, 303, 308))

        resp = trainer_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            "/training/login", data={"username": "httptesttrainer", "password": "WRONG", "csrf_token": csrf},
        )
        check("wrong password login rejected (401)", resp.status_code == 401)

        resp = trainer_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            "/training/login",
            data={"username": "httptesttrainer", "password": "TrainerPass123!", "csrf_token": csrf},
        )
        check("correct trainer login redirects", resp.status_code in (302, 303))

        resp = trainer_client.get("/training/trainer")
        check("trainer can open the trainer area", resp.status_code == 200)

        # -----------------------------------------------------------------
        # CSRF enforcement: creating a student without a valid token is
        # rejected (400), even while authenticated as trainer.
        # -----------------------------------------------------------------
        resp = trainer_client.post(
            "/training/trainer/students/new",
            data={"display_name": "No CSRF", "username": "nocsrf", "password": "whatever12345"},
        )
        check("create-student POST without CSRF token is rejected (400)", resp.status_code == 400)

        # -----------------------------------------------------------------
        # Trainer creates two students.
        # -----------------------------------------------------------------
        def create_student(username: str, display_name: str, password: str) -> None:
            resp = trainer_client.get("/training/trainer/students/new")
            csrf = extract_csrf(resp.data)
            resp = trainer_client.post(
                "/training/trainer/students/new",
                data={"display_name": display_name, "username": username, "password": password, "csrf_token": csrf},
            )
            check(f"trainer creates student {username!r}", resp.status_code in (302, 303))

        create_student("httpteststudenta", "HTTP Test Student A", "StudentAPass123!")
        create_student("httpteststudentb", "HTTP Test Student B", "StudentBPass123!")

        with TrainingSessionFactory() as s:
            student_a = next(a for a in svc.list_all_students(s) if a.username == "httpteststudenta")
            student_b = next(a for a in svc.list_all_students(s) if a.username == "httpteststudentb")
            student_a_id, student_b_id = student_a.id, student_b.id

        # -----------------------------------------------------------------
        # Trainer records a need for Student A and assigns the Caprese pill.
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_a_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/students/{student_a_id}/needs",
            data={"text": "Learn the Caprese", "origin": "observation", "csrf_token": csrf},
        )
        check("trainer adds a need for student A", resp.status_code in (302, 303))

        with TrainingSessionFactory() as s:
            need = svc.list_needs_for_student(s, student_a_id)[0]
            need_id = need.id

        resp = trainer_client.get(f"/training/trainer/students/{student_a_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/needs/{need_id}/assign", data={"pill_id": str(caprese_id), "csrf_token": csrf},
        )
        check("trainer assigns Caprese to the need", resp.status_code in (302, 303))

        # Duplicate assignment of the same pill to the same need is rejected
        # with a friendly redirect (flash), not a crash / not a duplicate row.
        resp = trainer_client.get(f"/training/trainer/students/{student_a_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/needs/{need_id}/assign", data={"pill_id": str(caprese_id), "csrf_token": csrf},
        )
        check("duplicate pill assignment to the same need does not error", resp.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            assignments = svc.list_assignments_for_need(s, need_id)
            check("duplicate assignment attempt did not create a second row", len(assignments) == 1)
            assignment_id = assignments[0].id

        # -----------------------------------------------------------------
        # A student cannot reach the trainer area.
        # -----------------------------------------------------------------
        resp = student_a_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = student_a_client.post(
            "/training/login",
            data={"username": "httpteststudenta", "password": "StudentAPass123!", "csrf_token": csrf},
        )
        check("student A login redirects", resp.status_code in (302, 303))

        resp = student_a_client.get("/training/trainer")
        check("student cannot open the trainer area (403)", resp.status_code == 403)

        # -----------------------------------------------------------------
        # Student A opens the assignment (marks it in_progress) and sees
        # their own name.
        # -----------------------------------------------------------------
        resp = student_a_client.get("/training")
        check("student home shows the student's own display name", b"HTTP Test Student A" in resp.data)

        resp = student_a_client.get(f"/training/assignments/{assignment_id}")
        check("student A can open their own assignment", resp.status_code == 200)

        # -----------------------------------------------------------------
        # Row-level security: Student B must NOT be able to read Student A's
        # assignment, even by guessing/changing the id in the URL.
        # -----------------------------------------------------------------
        resp = student_b_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = student_b_client.post(
            "/training/login",
            data={"username": "httpteststudentb", "password": "StudentBPass123!", "csrf_token": csrf},
        )
        check("student B login redirects", resp.status_code in (302, 303))

        resp = student_b_client.get(f"/training/assignments/{assignment_id}")
        check("student B cannot read student A's assignment (404)", resp.status_code == 404)

        # -----------------------------------------------------------------
        # Student A submits the final quiz (all correct) and double-submits
        # the identical form — must not create two attempts.
        # -----------------------------------------------------------------
        resp = student_a_client.get(f"/training/assignments/{assignment_id}/final-quiz")
        csrf = extract_csrf(resp.data)
        token = extract_submission_token(resp.data)

        with TrainingSessionFactory() as s:
            from rfone_data_store import models as m
            assignment_obj = s.get(m.TrainingAssignment, assignment_id)
            questions = svc.get_final_quiz_view(s, assignment_obj)
            form_data = {"csrf_token": csrf, "submission_token": token}
            for q in questions:
                form_data[f"answer_{q.id}"] = str(q.correct_index)

        resp = student_a_client.post(f"/training/assignments/{assignment_id}/final-quiz", data=form_data)
        check("final quiz submission redirects to a result page", resp.status_code in (302, 303))
        first_location = resp.headers.get("Location", "")

        resp2 = student_a_client.post(f"/training/assignments/{assignment_id}/final-quiz", data=form_data)
        check(
            "resubmitting the identical form (same token) redirects to the SAME result",
            resp2.status_code in (302, 303) and resp2.headers.get("Location", "") == first_location,
        )

        with TrainingSessionFactory() as s:
            attempts = svc.list_attempts_for_assignment(s, assignment_id)
            check("double form submission created exactly one attempt", len(attempts) == 1)
            check("final quiz scored 3/3 for all-correct answers", attempts[0].points_earned == 3)

        resp = student_a_client.get(first_location)
        check("student A can view their own attempt result", resp.status_code == 200)
        check("attempt result page shows the score", b"3 / 3" in resp.data)

        resp = student_b_client.get(first_location)
        check("student B cannot view student A's attempt result (404)", resp.status_code == 404)

        with TrainingSessionFactory() as s:
            from rfone_data_store import models as m
            assignment_obj = s.get(m.TrainingAssignment, assignment_id)
            status_after = svc.assignment_status(s, assignment_obj)
            check("assignment status is 'completed' after the final quiz", status_after == svc.ASSIGNMENT_COMPLETED)

        # -----------------------------------------------------------------
        # Login lockout over HTTP.
        # -----------------------------------------------------------------
        lockout_client = tips_app.app.test_client()
        for _ in range(svc.FAILED_LOGIN_LOCKOUT_THRESHOLD):
            resp = lockout_client.get("/training/login")
            csrf = extract_csrf(resp.data)
            lockout_client.post(
                "/training/login", data={"username": "httpteststudentb", "password": "WRONG", "csrf_token": csrf},
            )
        resp = lockout_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = lockout_client.post(
            "/training/login",
            data={"username": "httpteststudentb", "password": "StudentBPass123!", "csrf_token": csrf},
        )
        check(
            "account is locked after repeated failed HTTP login attempts (correct password now also rejected)",
            resp.status_code == 401 and b"Too many attempts" in resp.data,
        )

        # -----------------------------------------------------------------
        # Persistence across a fresh process-level connection (simulates a
        # restart: a brand-new engine/session against the same DB file).
        # -----------------------------------------------------------------
        from rfone_data_store.database import create_configured_engine, create_session_factory, get_database_url
        fresh_engine = create_configured_engine(get_database_url())
        FreshSessionFactory = create_session_factory(fresh_engine)
        with FreshSessionFactory() as s2:
            reloaded = svc.list_all_students(s2)
            check(
                "students persisted and are readable from a brand-new DB connection (restart simulation)",
                len(reloaded) == 2,
            )
            reloaded_attempts = svc.list_attempts_for_assignment(s2, assignment_id)
            check("quiz attempt persisted across a fresh connection", len(reloaded_attempts) == 1)
        fresh_engine.dispose()

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
