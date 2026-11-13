#!/usr/bin/env python
"""Contextual help ("How … works" modal) on every Training page.

Training's templates extend the HOST application's layout, which renders
the link (``data-how-works="<section>"``) and ONE help dialog
(``id="rf-help-dialog"``) with the page's own section
(``id="help-<section>"``, file ``Training/templates/help/<section>.html``).
The student's Training home says "How Training works"; every other page
says "How this page works".

Two hosts, each on its own throwaway SQLite database:
  * RF-One Web (single sign-on, the published mount) — every page, student
    and trainer; this process.
  * Tips (Training's own login) — the same pages except the trainer home,
    which Tips cannot render (it links to an RF-One Web-only page); a child
    process of this script, because both applications are named ``app``.

Never touches AWS or any real database.

Usage:
    python test_how_works_training_http.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("TRAINING_HOW_WORKS_HOST", "web")
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix=f"training_how_works_{HOST}_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "training-how-works-test-secret"
os.environ["RFONE_FLASK_SECRET_KEY"] = "training-how-works-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

APP_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Web" if HOST == "web" else "Tips"))
# The host mounts Training itself; this script's own folder must not shadow
# the host's modules (both have an `auth`/`db`).
sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) != os.path.normcase(BASE_DIR)]
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import app as host_app  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.training import service as svc  # noqa: E402

if HOST == "web":
    from db import SessionFactory  # noqa: E402  (RF-One Web's own)
    import training_integration as ti  # noqa: E402
else:
    from db import SessionFactory  # noqa: E402  (Training's own, imported by Tips)

with SessionFactory() as _seed:
    svc.ensure_pills_seeded(_seed)
    _seed.commit()

HOME_LABEL = "How Training works"
PAGE_LABEL = "How this page works"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def visible_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def build_history(s, *, student_ta_id: int, trainer_ta_id: int) -> dict:
    """One need, one pill, one final attempt and one whole-path attempt."""
    caprese = next(p for p in svc.list_all_pills(s) if p.slug == "caprese")
    need = svc.create_need(s, student_account_id=student_ta_id, text="Learn Caprese", origin="observation",
                           created_by_account_id=trainer_ta_id)
    assignment = svc.assign_pill(s, need_id=need.id, pill_id=caprese.id, assigned_by_account_id=trainer_ta_id)
    svc.mark_assignment_opened(s, assignment)
    attempt = svc.record_final_attempt(s, assignment=assignment, answers={}, submission_token="hw-final-1")
    overall = svc.record_overall_attempt(s, student_account_id=student_ta_id, answers={},
                                         submission_token="hw-overall-1")
    s.commit()
    return {"assignment": assignment.id, "attempt": attempt.id, "overall": overall.id, "student": student_ta_id}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  [{HOST}] {description}"
              + ("" if condition or not detail else f" ({detail})"))

    student = host_app.app.test_client()
    trainer = host_app.app.test_client()
    with SessionFactory() as s:
        if HOST == "web":
            accounts = {}
            for username, role in (("hw-trainer", "trainer"), ("hw-student", "student")):
                acc = account_service.create_account(s, username=username, display_name=f"HW {role.title()}",
                                                     password="a-long-enough-test-password")
                account_service.set_domain_access(s, account_id=acc.id, domain_code="TRAINING", enabled=True,
                                                  role_code=role)
                ti.create_and_link_training_identity(s, rfone_account_id=acc.id, role_code=role)
                accounts[role] = (acc.id, acc.session_version,
                                  ti.get_link_for_rfone_account(s, acc.id).training_account_id)
            s.commit()
            ids = build_history(s, student_ta_id=accounts["student"][2], trainer_ta_id=accounts["trainer"][2])
            for client, role in ((student, "student"), (trainer, "trainer")):
                with client.session_transaction() as sess:
                    sess[shared_session.SESSION_ACCOUNT_KEY] = accounts[role][0]
                    sess[shared_session.SESSION_VERSION_KEY] = accounts[role][1]
        else:
            t = svc.create_account(s, display_name="HW Trainer", username="hwtrainer",
                                   password="TrainerPass123!", role="trainer")
            st = svc.create_account(s, display_name="HW Student", username="hwstudent",
                                    password="StudentPass123!", role="student")
            s.commit()
            ids = build_history(s, student_ta_id=st.id, trainer_ta_id=t.id)
    if HOST == "tips":
        for client, username, password in ((student, "hwstudent", "StudentPass123!"),
                                           (trainer, "hwtrainer", "TrainerPass123!")):
            csrf = CSRF_RE.search(client.get("/training/login").get_data(as_text=True)).group(1)
            resp = client.post("/training/login", data={"username": username, "password": password, "csrf_token": csrf})
            check(f"{username} signs in to Training", resp.status_code in (302, 303), str(resp.status_code))

    pages = [
        (student, "/training", "training-home", HOME_LABEL),
        (student, f"/training/assignments/{ids['assignment']}", "training-assignment", PAGE_LABEL),
        (student, f"/training/assignments/{ids['assignment']}/final-quiz", "training-final-quiz", PAGE_LABEL),
        (student, f"/training/attempts/{ids['attempt']}", "training-attempt-result", PAGE_LABEL),
        (student, "/training/overall-quiz", "training-overall-quiz", PAGE_LABEL),
        (student, f"/training/overall-attempts/{ids['overall']}", "training-overall-result", PAGE_LABEL),
        (trainer, "/training/trainer/students/new", "training-trainer-create-student", PAGE_LABEL),
        (trainer, f"/training/trainer/students/{ids['student']}", "training-trainer-student", PAGE_LABEL),
        (trainer, f"/training/trainer/attempts/{ids['attempt']}", "training-attempt-result", PAGE_LABEL),
        (trainer, f"/training/trainer/overall-attempts/{ids['overall']}", "training-overall-result", PAGE_LABEL),
    ]
    if HOST == "web":
        pages.append((trainer, "/training/trainer", "training-trainer-home", PAGE_LABEL))
    for client, path, section, label in pages:
        resp = client.get(path)
        html = resp.get_data(as_text=True)
        check(f"{path}: 200", resp.status_code == 200, f"{resp.status_code} {resp.headers.get('Location', '')}")
        check(f"{path}: link opens section {section}", f'data-how-works="{section}"' in html)
        check(f"{path}: the page's own section is in the dialog", f'id="help-{section}"' in html)
        check(f"{path}: label '{label}'", f">{label}</button>" in html)
        check(f"{path}: exactly one help dialog", html.count('id="rf-help-dialog"') == 1,
              str(html.count('id="rf-help-dialog"')))
        start = html.find(f'id="help-{section}"')
        body = html[start:html.find("</section>", start)] if start >= 0 else ""
        check(f"{path}: the section explains the page (>= 300 visible characters)",
              len(visible_text(body)) >= 300, str(len(visible_text(body))))

    # The same result page explains itself to the student or to the trainer.
    own = student.get(f"/training/attempts/{ids['attempt']}").get_data(as_text=True)
    seen = trainer.get(f"/training/trainer/attempts/{ids['attempt']}").get_data(as_text=True)
    check("attempt result: the student's help speaks of their own attempt", "one of your final-quiz attempts" in own)
    check("attempt result: the trainer's help speaks of the student's attempt", "made by your student" in seen)

    # Signed out: Training pages (and their help) are not served.
    anon = host_app.app.test_client().get("/training")
    check("signed out: no help is served", anon.status_code in (301, 302, 303)
          and 'id="rf-help-dialog"' not in anon.get_data(as_text=True), str(anon.status_code))

    print(f"Training How Works HTTP tests [{HOST}]: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    code = main()
    if HOST == "web":
        child = subprocess.run([sys.executable, os.path.abspath(__file__)],
                               env={**os.environ, "TRAINING_HOW_WORKS_HOST": "tips"})
        code = code or child.returncode
        print("ALL CHECKS PASSED" if code == 0 else "SOME CHECKS FAILED")
    sys.exit(code)
