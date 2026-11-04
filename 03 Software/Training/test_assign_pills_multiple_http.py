#!/usr/bin/env python
"""HTTP-level regression test for the trainer "Assign pills" modal
(multi-select pill assignment to one training need). Mirrors
`test_training_http.py`'s own convention exactly: a throwaway SQLite
database created BEFORE Tips's `app.py` is imported (Training is mounted
there, same as the existing test), Werkzeug's Flask test client, `main()`
returning an exit code. Never touches the real `RF-One Data Store/data/
rfone.db`.

This file focuses on what's NEW: the bulk-assign route
(`trainer_assign_pills_multiple`) and `rfone_data_store.training.service.
assign_pills_bulk` — CSRF/permissions, invalid ids blocking ALL writes,
already-assigned ids being skipped and counted (never duplicated), a
double submission not duplicating, a race between two concurrent callers
not duplicating, assigning the same pill under a DIFFERENT need still
working (never blocked), and that nothing about existing quiz/question
content or the single-assign route is disturbed. It does NOT attempt to
drive the modal's own client-side JS (filter/search/select-all/counter) —
that requires a real browser, not exercised here; see the chat report for
what was and was not verified.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="assign_pills_multiple_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

_TIPS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Tips"))
if _TIPS_DIR not in sys.path:
    sys.path.insert(0, _TIPS_DIR)

import app as tips_app  # noqa: E402

from db import SessionFactory as TrainingSessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.training import service as svc  # noqa: E402

with TrainingSessionFactory() as _init_session:
    svc.ensure_pills_seeded(_init_session)
    # ensure_pills_seeded only creates the original 3 pills — this test
    # needs several DISTINCT pills to exercise multi-select scenarios
    # independently, so it adds a few more directly (test-DB-only, no
    # change to real pill content/taxonomy).
    for i in range(6):
        slug = f"bulk-assign-test-pill-{i}"
        if _init_session.query(m.TrainingPill).filter(m.TrainingPill.slug == slug).first() is None:
            _init_session.add(m.TrainingPill(
                slug=slug, title=f"Bulk Assign Test Pill {i}",
                learning_objectives=f"Test scope/objective text for pill {i}.",
            ))
    _init_session.commit()

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


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
        # Fixture setup: one trainer, one student, a handful of distinct
        # pills, one need. Baseline counts of untouched content, captured
        # up front to prove they never change (checklist item: "storico e
        # quiz preesistenti invariati").
        # -----------------------------------------------------------------
        with TrainingSessionFactory() as s:
            trainer_account = svc.create_account(
                s, display_name="Bulk Assign Trainer", username="bulkassigntrainer",
                password="TrainerPass123!", role="trainer",
            )
            s.commit()
            trainer_account_id = trainer_account.id
            all_pills = svc.list_all_pills(s)
            pill_ids = [p.id for p in all_pills]
            check("fixture: at least 6 distinct pills available", len(pill_ids) >= 6, str(len(pill_ids)))
            p1, p2, p3, p4, p5, p6 = pill_ids[:6]
            question_count_before = s.query(m.TrainingQuestion).count()
            pill_count_before = s.query(m.TrainingPill).count()

        trainer_client = tips_app.app.test_client()
        anon_client = tips_app.app.test_client()

        resp = trainer_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            "/training/login", data={"username": "bulkassigntrainer", "password": "TrainerPass123!", "csrf_token": csrf},
        )
        check("trainer logs in", resp.status_code in (302, 303))

        resp = trainer_client.get("/training/trainer/students/new")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            "/training/trainer/students/new",
            data={"display_name": "Bulk Assign Student", "username": "bulkassignstudent", "password": "StudentPass123!", "csrf_token": csrf},
        )
        check("trainer creates a student", resp.status_code in (302, 303))

        with TrainingSessionFactory() as s:
            student = next(a for a in svc.list_all_students(s) if a.username == "bulkassignstudent")
            student_id = student.id

        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/students/{student_id}/needs",
            data={"text": "Bulk-assign need A", "origin": None, "csrf_token": csrf},
        )
        check("trainer creates a training need", resp.status_code in (302, 303))

        with TrainingSessionFactory() as s:
            need_a_id = svc.list_needs_for_student(s, student_id)[0].id

        assign_url = f"/training/trainer/needs/{need_a_id}/assign-multiple"

        # -----------------------------------------------------------------
        # Page renders the modal's data correctly: catalog + per-need
        # already-assigned ids (empty at this point).
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        check("student detail page 200s", resp.status_code == 200)
        check("assign-pills catalog script island present", b'id="assign-pills-catalog"' in resp.data)
        check("assign-pills trigger button present", b'assign-pills-trigger' in resp.data)
        check(
            "trigger button starts with an empty already-assigned list",
            f'data-assigned-pill-ids=""'.encode() in resp.data,
        )

        # -----------------------------------------------------------------
        # CSRF: rejected without a valid token, no writes.
        # -----------------------------------------------------------------
        resp = trainer_client.post(assign_url, data={"pill_ids": [str(p1)]})
        check("bulk-assign without CSRF token is rejected (400)", resp.status_code == 400)
        with TrainingSessionFactory() as s:
            check("no assignment created by the rejected CSRF-less request", len(svc.list_assignments_for_need(s, need_a_id)) == 0)

        # -----------------------------------------------------------------
        # Permissions: anonymous and non-trainer requests are rejected,
        # with no writes.
        # -----------------------------------------------------------------
        resp = anon_client.post(assign_url, data={"pill_ids": [str(p1)], "csrf_token": "irrelevant"})
        check("anonymous bulk-assign is rejected (redirect to login)", resp.status_code in (301, 302, 303, 308))

        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        student_client = tips_app.app.test_client()
        resp = student_client.get("/training/login")
        student_csrf = extract_csrf(resp.data)
        resp = student_client.post(
            "/training/login", data={"username": "bulkassignstudent", "password": "StudentPass123!", "csrf_token": student_csrf},
        )
        resp = student_client.post(assign_url, data={"pill_ids": [str(p1)], "csrf_token": student_csrf})
        check("a student (non-trainer) bulk-assign is rejected (403)", resp.status_code == 403)
        with TrainingSessionFactory() as s:
            check("no assignment created by the non-trainer request", len(svc.list_assignments_for_need(s, need_a_id)) == 0)

        # -----------------------------------------------------------------
        # Invalid pill id blocks ALL writes in the request, even the valid
        # ones submitted alongside it.
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            assign_url, data={"pill_ids": [str(p1), "999999999"], "csrf_token": csrf},
        )
        check("a request with one unknown pill id redirects (handled, not a crash)", resp.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            check(
                "the VALID pill in that same request was NOT partially written",
                len(svc.list_assignments_for_need(s, need_a_id)) == 0,
            )

        # -----------------------------------------------------------------
        # Real multi-assign: 3 distinct pills to the same need in one POST,
        # each an independent assignment (own status/quiz history).
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            assign_url, data={"pill_ids": [str(p1), str(p2), str(p3)], "csrf_token": csrf},
        )
        check("multi-assign of 3 pills redirects", resp.status_code in (302, 303))

        with TrainingSessionFactory() as s:
            assignments = svc.list_assignments_for_need(s, need_a_id)
            check("all 3 pills were assigned to the need", {a.pill_id for a in assignments} == {p1, p2, p3})
            check("each assignment is independent (own row, own id)", len({a.id for a in assignments}) == 3)
            for a in assignments:
                status = svc.assignment_status(s, a)
                check(f"assignment for pill {a.pill_id} starts not_started", status == svc.ASSIGNMENT_NOT_STARTED)
                check(f"assignment for pill {a.pill_id} has no attempts yet", svc.list_attempts_for_assignment(s, a.id) == [])

        # -----------------------------------------------------------------
        # Reopening the page: already-assigned ids now reflected on the
        # trigger button (what the modal uses to mark "Already assigned"
        # and disable re-selection).
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        body = resp.data.decode("utf-8")
        assigned_attr_match = re.search(r'data-assigned-pill-ids="([^"]*)"', body)
        check("assigned-pill-ids attribute present after assignment", assigned_attr_match is not None)
        if assigned_attr_match:
            assigned_ids = {int(x) for x in assigned_attr_match.group(1).split(",") if x}
            check("assigned-pill-ids reflects the 3 just-assigned pills", assigned_ids == {p1, p2, p3})

        # -----------------------------------------------------------------
        # Already-assigned pills are skipped (not duplicated) when
        # resubmitted alongside a genuinely new one; counted, not errored.
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            assign_url, data={"pill_ids": [str(p1), str(p4)], "csrf_token": csrf},
        )
        check("resubmitting an already-assigned pill alongside a new one redirects (no error)", resp.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            assignments = svc.list_assignments_for_need(s, need_a_id)
            check("no duplicate row for the already-assigned pill", len([a for a in assignments if a.pill_id == p1]) == 1)
            check("the genuinely new pill WAS added", any(a.pill_id == p4 for a in assignments))
            check("need now has exactly 4 distinct assigned pills", {a.pill_id for a in assignments} == {p1, p2, p3, p4})

        # -----------------------------------------------------------------
        # Double submission of the exact same new pill does not duplicate
        # (simulates a double click / resubmit).
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp1 = trainer_client.post(assign_url, data={"pill_ids": [str(p5)], "csrf_token": csrf})
        resp2 = trainer_client.post(assign_url, data={"pill_ids": [str(p5)], "csrf_token": csrf})
        check("first submission of pill 5 redirects", resp1.status_code in (302, 303))
        check("second (duplicate) submission of pill 5 also redirects, not an error", resp2.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            assignments = svc.list_assignments_for_need(s, need_a_id)
            check("double submit did not create two rows for pill 5", len([a for a in assignments if a.pill_id == p5]) == 1)

        # -----------------------------------------------------------------
        # The same pill CAN be assigned again under a DIFFERENT need for
        # the same student — never blocked just because it's used elsewhere
        # (existing rule, must remain unaffected by this task).
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/students/{student_id}/needs",
            data={"text": "Bulk-assign need B", "origin": None, "csrf_token": csrf},
        )
        with TrainingSessionFactory() as s:
            need_b_id = next(n.id for n in svc.list_needs_for_student(s, student_id) if n.text == "Bulk-assign need B")

        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/needs/{need_b_id}/assign-multiple", data={"pill_ids": [str(p1)], "csrf_token": csrf},
        )
        check("assigning pill 1 (already used under need A) to need B succeeds", resp.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            need_b_assignments = svc.list_assignments_for_need(s, need_b_id)
            check("pill 1 is now assigned under need B too (independent row)", any(a.pill_id == p1 for a in need_b_assignments))

        # -----------------------------------------------------------------
        # Empty selection is rejected client-side (button disabled) but if
        # somehow submitted anyway, the server must reject it too with no
        # writes — belt and suspenders, never trust the client alone.
        # -----------------------------------------------------------------
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(f"/training/trainer/needs/{need_b_id}/assign-multiple", data={"csrf_token": csrf})
        check("empty pill_ids submission redirects (handled, not a crash)", resp.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            check("empty submission created nothing new under need B", len(svc.list_assignments_for_need(s, need_b_id)) == 1)

        # -----------------------------------------------------------------
        # Concurrency: two overlapping bulk-assign calls against the SAME
        # need, run on two real threads with two separate DB sessions —
        # the final state must have no duplicate rows regardless of how
        # the race resolves. (Caveat: SQLite serializes writers at the
        # database-file level rather than giving true row-level MVCC the
        # way PostgreSQL/RDS does in production, so this mainly exercises
        # the nested-SAVEPOINT/IntegrityError code path under contention —
        # it is not a substitute for the same property holding under
        # PostgreSQL's real concurrent-transaction semantics.)
        # -----------------------------------------------------------------
        with TrainingSessionFactory() as s:
            need_c = svc.create_need(s, student_account_id=student_id, text="Concurrency need", origin=None, created_by_account_id=trainer_account_id)
            s.commit()
            need_c_id = need_c.id

        race_pill_ids = [p1, p2, p3, p4, p5, p6]
        errors: list[Exception] = []

        def _race_call():
            try:
                with TrainingSessionFactory() as s:
                    svc.assign_pills_bulk(s, need_id=need_c_id, pill_ids=race_pill_ids, assigned_by_account_id=trainer_account_id)
                    s.commit()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=_race_call)
        t2 = threading.Thread(target=_race_call)
        t1.start(); t2.start()
        t1.join(); t2.join()

        check("concurrent bulk-assign calls raised no unhandled exception", errors == [], str(errors))
        with TrainingSessionFactory() as s:
            race_assignments = svc.list_assignments_for_need(s, need_c_id)
            check(
                "concurrent calls produced exactly one row per pill (no duplicates)",
                sorted(a.pill_id for a in race_assignments) == sorted(race_pill_ids),
                str(sorted(a.pill_id for a in race_assignments)),
            )

        # -----------------------------------------------------------------
        # Existing quiz/question content and pill catalog are untouched by
        # any of the above.
        # -----------------------------------------------------------------
        with TrainingSessionFactory() as s:
            check("TrainingQuestion count unchanged", s.query(m.TrainingQuestion).count() == question_count_before)
            check("TrainingPill count unchanged", s.query(m.TrainingPill).count() == pill_count_before)

        # -----------------------------------------------------------------
        # Regression: the pre-existing single-pill "assign" route (still
        # present, not removed by this task) keeps working.
        # -----------------------------------------------------------------
        with TrainingSessionFactory() as s:
            need_d = svc.create_need(s, student_account_id=student_id, text="Single-assign need", origin=None, created_by_account_id=trainer_account_id)
            s.commit()
            need_d_id = need_d.id
        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/needs/{need_d_id}/assign", data={"pill_id": str(p6), "csrf_token": csrf},
        )
        check("pre-existing single-pill assign route still works", resp.status_code in (302, 303))
        with TrainingSessionFactory() as s:
            check("single-assign route created the expected row", any(a.pill_id == p6 for a in svc.list_assignments_for_need(s, need_d_id)))

        # -----------------------------------------------------------------
        # Regression: Tips home and /training/menu unaffected (same check
        # as test_training_http.py — Tips itself is not deployed by this
        # task, but its shared Training code path must stay intact).
        # -----------------------------------------------------------------
        resp = anon_client.get("/")
        check("Tips home page still returns 200", resp.status_code == 200)
        resp = anon_client.get("/training/menu")
        check("/training/menu still returns 200", resp.status_code == 200)

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
