#!/usr/bin/env python
"""Regression test for the 51-new-pill menu import (RF-ONE: "importare le
51 nuove pillole e completare il menu Training, raggruppato nelle 9
aree"). Mirrors this repo's own standalone-script test convention. Uses a
throwaway SQLite database and a throwaway Flask test client only — never
AWS, never any production database.

Covers the task's own "VERIFICHE MIRATE" list.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="menu_import_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)
from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.training import service as svc  # noqa: E402
import import_menu_pills  # noqa: E402
import dish_data  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="submission_token" value="([^"]+)"')
PRESERVE_IDS = ["caprese", "carbonara", "shrimp-pistachio"]
AREA_COUNTS = {
    "Appetizers": 5, "Soups": 2, "Bruschetta": 5, "Salads": 4, "Pasta": 11,
    "Pizzas": 11, "Meat & Fish": 8, "Sides": 4, "Desserts": 4,
}


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def extract_submission_token(html: bytes) -> str:
    match = TOKEN_RE.search(html.decode("utf-8"))
    assert match, "submission_token not found"
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
        # Fixtures: seed the original 3 pills, then attach real history
        # (account, need, assignment, attempt) to one of them BEFORE
        # running the import — proving the import never disturbs it.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            svc.ensure_pills_seeded(s)
            s.commit()

            trainer = svc.create_account(s, display_name="Trainer", username="trainer1", password="pass", role="trainer")
            student = svc.create_account(s, display_name="Student One", username="student1", password="pass", role="student")
            s.commit()

            caprese = next(p for p in svc.list_all_pills(s) if p.slug == "caprese")
            need = svc.create_need(s, student_account_id=student.id, text="Learn Caprese", origin=None, created_by_account_id=trainer.id)
            assignment = svc.assign_pill(s, need_id=need.id, pill_id=caprese.id, assigned_by_account_id=trainer.id)
            svc.mark_assignment_opened(s, assignment)
            questions = svc.get_final_quiz_view(s, assignment)
            answers = {q.id: q.correct_index for q in questions}
            attempt = svc.record_final_attempt(s, assignment=assignment, answers=answers, submission_token="pre-import-token")
            s.commit()
            pre_import_attempt_id = attempt.id
            pre_import_assignment_id = assignment.id
            pre_import_caprese_id = caprese.id
            pre_import_caprese_title = caprese.title
            pre_import_caprese_objectives = caprese.learning_objectives
            trainer_id, student_id = trainer.id, student.id

        # -----------------------------------------------------------------
        # Run the import.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            with open(import_menu_pills.DEFAULT_SOURCE, encoding="utf-8") as f:
                package = json.load(f)
            to_create_pills, to_create_questions, skipped, conflicts = import_menu_pills.plan_import(s, package["new_pills"])
            check("no conflicts on first import", conflicts == [])
            pill_count, question_count = import_menu_pills.apply_import(s, to_create_pills, to_create_questions)
            s.commit()
        check("51 new pills created", pill_count == 51, str(pill_count))
        check("459 new questions created", question_count == 459, str(question_count))

        # -----------------------------------------------------------------
        # Final pill/question counts.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            total_pills = s.query(m.TrainingPill).count()
            check("54 pills total (3 preserved + 51 new)", total_pills == 54, str(total_pills))

            for slug in PRESERVE_IDS:
                p = s.query(m.TrainingPill).filter(m.TrainingPill.slug == slug).first()
                check(f"preserved pill '{slug}' still present", p is not None)

            caprese_after = s.get(m.TrainingPill, pre_import_caprese_id)
            check("caprese id unchanged", caprese_after.id == pre_import_caprese_id)
            check("caprese title unchanged", caprese_after.title == pre_import_caprese_title)
            check("caprese learning_objectives unchanged", caprese_after.learning_objectives == pre_import_caprese_objectives)

            attempt_after = s.get(m.TrainingAttempt, pre_import_attempt_id)
            check("pre-existing attempt still present with same id", attempt_after is not None)
            check("pre-existing attempt still scored correctly", attempt_after.points_earned == attempt_after.points_possible)
            assignment_after = s.get(m.TrainingAssignment, pre_import_assignment_id)
            check("pre-existing assignment still present with same id", assignment_after is not None)

            kind_counts = Counter(q.kind for q in s.query(m.TrainingQuestion).all())
            check("459 self_check+final_quiz+overall_quiz questions from new pills (162 each, 27 pre-existing)",
                  kind_counts["self_check"] == 162 and kind_counts["final_quiz"] == 162 and kind_counts["overall_quiz"] == 162,
                  str(dict(kind_counts)))

        # -----------------------------------------------------------------
        # Area counts (via dish_data — the same source /training/menu uses).
        # -----------------------------------------------------------------
        dishes = dish_data.load_dishes()
        check("54 dishes in dish-data", len(dishes) == 54, str(len(dishes)))
        area_counter = Counter(
            ("Appetizers" if d["category"] == "Appetizer" else d["category"]) for d in dishes.values()
        )
        for area, expected in AREA_COUNTS.items():
            check(f"area '{area}' has {expected} dishes", area_counter.get(area, 0) == expected, str(area_counter.get(area, 0)))
        check("area counts sum to 54", sum(area_counter.values()) == 54)

        # -----------------------------------------------------------------
        # Idempotent second run: no duplicates.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            to_create_pills2, to_create_questions2, skipped2, conflicts2 = import_menu_pills.plan_import(s, package["new_pills"])
            check("second run: no conflicts", conflicts2 == [])
            check("second run: nothing new to create", len(to_create_pills2) == 0 and len(to_create_questions2) == 0)
            check("second run: all 51 pills reported as skipped/already present", len(skipped2) == 51)
            pill_count2, question_count2 = import_menu_pills.apply_import(s, to_create_pills2, to_create_questions2)
            s.commit()
        with SessionFactory() as s:
            check("pill count unchanged after second run", s.query(m.TrainingPill).count() == 54)
            check("question count unchanged after second run", s.query(m.TrainingQuestion).count() == 486)

        # -----------------------------------------------------------------
        # Conflict detection: tamper with one new pill, verify abort + no
        # partial writes.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            colosseo = s.query(m.TrainingPill).filter(m.TrainingPill.slug == "colosseo").first()
            colosseo.title = "Tampered"
            s.commit()
        with SessionFactory() as s:
            _, _, _, conflicts3 = import_menu_pills.plan_import(s, package["new_pills"])
            check("tampered pill produces a reported conflict", any("colosseo" in c for c in conflicts3))
        with SessionFactory() as s:
            # restore for the rest of the test
            colosseo = s.query(m.TrainingPill).filter(m.TrainingPill.slug == "colosseo").first()
            colosseo.title = "Colosseo"
            s.commit()
            check("pill/question counts unaffected by the conflict-detection pass", s.query(m.TrainingPill).count() == 54)

        # -----------------------------------------------------------------
        # Missing-photo placeholders.
        # -----------------------------------------------------------------
        for dish_id in ["vegetal-festival", "vegetable-festival", "lemon-butter-asparagus"]:
            check(f"'{dish_id}' has no image (image is None)", dishes[dish_id]["image"] is None)

        html = open(os.path.join(BASE_DIR, "RF-One-Training.html"), encoding="utf-8").read()
        check("menu page JS has explicit placeholder markup for missing photos", "Photo not available" in html)

        # -----------------------------------------------------------------
        # Formal answer keys never appear in the public menu HTML.
        # -----------------------------------------------------------------
        check("public menu HTML contains no 'correct_option_id' (formal answer key)", "correct_option_id" not in html)
        check("public menu HTML contains no embedded 'questions' quiz data at all", '"questions"' not in html)

        # -----------------------------------------------------------------
        # HTTP-level: menu reachable, dish detail reachable via app.py
        # (Tips-mounted, matching how /training/menu is actually served),
        # assignment of a NEW pill, self-check (no write), final quiz
        # (scored + recorded), overall quiz (scoped to assigned pills only).
        # -----------------------------------------------------------------
        _TIPS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Tips"))
        if _TIPS_DIR not in sys.path:
            sys.path.insert(0, _TIPS_DIR)
        import app as tips_app  # noqa: E402

        anon_client = tips_app.app.test_client()
        resp = anon_client.get("/training/menu")
        check("public /training/menu reachable", resp.status_code == 200)
        check("public /training/menu contains a new dish name", b"Colosseo" in resp.data)
        check("public /training/menu does not leak formal answer keys", b"correct_option_id" not in resp.data)

        trainer_client = tips_app.app.test_client()
        resp = trainer_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post("/training/login", data={"username": "trainer1", "password": "pass", "csrf_token": csrf})
        check("trainer login ok", resp.status_code in (302, 303))

        with SessionFactory() as s:
            colosseo_pill = s.query(m.TrainingPill).filter(m.TrainingPill.slug == "colosseo").first()
            colosseo_id = colosseo_pill.id

        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        # The single-select <optgroup> picker was replaced by the "Assign
        # pills" modal (multi-select assignment task) — area grouping now
        # reaches the trainer via the modal's JSON catalog island instead
        # of server-rendered <optgroup> markup; same underlying area data
        # (_group_pills_by_area/_pill_area), different transport.
        check(
            "trainer's assign-pills catalog includes the new pill's area",
            b'"Pizzas"' in resp.data and str(colosseo_id).encode() in resp.data,
        )
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/students/{student_id}/needs",
            data={"text": "Learn a pizza", "origin": None, "csrf_token": csrf},
        )
        with SessionFactory() as s:
            new_need = [n for n in svc.list_needs_for_student(s, student_id) if n.text == "Learn a pizza"][0]
            new_need_id = new_need.id

        resp = trainer_client.get(f"/training/trainer/students/{student_id}")
        csrf = extract_csrf(resp.data)
        resp = trainer_client.post(
            f"/training/trainer/needs/{new_need_id}/assign", data={"pill_id": str(colosseo_id), "csrf_token": csrf},
        )
        check("new-pill assignment to student succeeds", resp.status_code in (302, 303))

        with SessionFactory() as s:
            assignments = svc.list_assignments_for_need(s, new_need_id)
            check("assignment of the new pill was created", len(assignments) == 1)
            colosseo_assignment_id = assignments[0].id

        student_client = tips_app.app.test_client()
        resp = student_client.get("/training/login")
        csrf = extract_csrf(resp.data)
        resp = student_client.post("/training/login", data={"username": "student1", "password": "pass", "csrf_token": csrf})
        check("student login ok", resp.status_code in (302, 303))

        with SessionFactory() as s:
            attempt_count_before = s.query(m.TrainingAttempt).count()

        resp = student_client.get(f"/training/assignments/{colosseo_assignment_id}")
        check("student can open the new pill's assignment page (200)", resp.status_code == 200)
        check("assignment page shows dish content for the new pill", b"Colosseo" in resp.data)
        check("assignment page shows the practice-check disclaimer (not a formal assessment)", b"not a formal assessment" in resp.data)
        check(
            "self-check data on the page carries no formal-quiz leakage beyond its own 3 practice questions",
            resp.data.count(b'"prompt"') == 3,
        )

        with SessionFactory() as s:
            attempt_count_after_view = s.query(m.TrainingAttempt).count()
        check("viewing the assignment (incl. its self-check) writes ZERO TrainingAttempt rows", attempt_count_after_view == attempt_count_before)

        resp = student_client.get(f"/training/assignments/{colosseo_assignment_id}/final-quiz")
        check("final quiz page for new pill reachable", resp.status_code == 200)
        csrf = extract_csrf(resp.data)
        token = extract_submission_token(resp.data)
        with SessionFactory() as s:
            assignment_obj = s.get(m.TrainingAssignment, colosseo_assignment_id)
            quiz_questions = svc.get_final_quiz_view(s, assignment_obj)
            form_data = {"csrf_token": csrf, "submission_token": token}
            for q in quiz_questions:
                form_data[f"answer_{q.id}"] = str(q.correct_index)
        resp = student_client.post(f"/training/assignments/{colosseo_assignment_id}/final-quiz", data=form_data)
        check("final quiz submission for new pill redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            attempts = svc.list_attempts_for_assignment(s, colosseo_assignment_id)
            check("final quiz attempt recorded exactly once for the new pill", len(attempts) == 1)
            check("final quiz scored 3/3 for all-correct answers", attempts[0].points_earned == 3)

        # -----------------------------------------------------------------
        # Overall quiz: limited to the student's DISTINCT assigned pills
        # only (caprese + colosseo here), never all 54.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            available = svc.overall_quiz_available(s, student_id)
        check("overall quiz becomes available once all assignments are completed", available is True)

        resp = student_client.get("/training/overall-quiz")
        check("overall quiz page reachable", resp.status_code == 200)
        with SessionFactory() as s:
            overall_questions = svc.get_overall_quiz_view(s, student_id, shuffle=False)
            pill_ids_in_overall = {q.pill_id for q in overall_questions}
        check("overall quiz has exactly 6 questions (2 distinct assigned pills x 3)", len(overall_questions) == 6, str(len(overall_questions)))
        check("overall quiz covers exactly the 2 assigned pills, no others", pill_ids_in_overall == {pre_import_caprese_id, colosseo_id})
        check("overall quiz has no duplicate question ids", len({q.id for q in overall_questions}) == len(overall_questions))

        csrf = extract_csrf(resp.data)
        token = extract_submission_token(resp.data)
        with SessionFactory() as s:
            overall_questions2 = svc.get_overall_quiz_view(s, student_id, shuffle=False)
            form_data = {"csrf_token": csrf, "submission_token": token}
            for q in overall_questions2:
                form_data[f"answer_{q.id}"] = str(q.correct_index)
        resp = student_client.post("/training/overall-quiz", data=form_data)
        check("overall quiz submission succeeds", resp.status_code in (302, 303))
        with SessionFactory() as s:
            overall_attempts = svc.list_overall_attempts_for_student(s, student_id)
            check("exactly one overall attempt recorded", len(overall_attempts) == 1)
            check("overall attempt scored 6/6", overall_attempts[0].points_earned == 6)

        # -----------------------------------------------------------------
        # Formal answers never present in the pre-submission page payload.
        # -----------------------------------------------------------------
        resp = student_client.get(f"/training/assignments/{colosseo_assignment_id}/final-quiz")
        check("final quiz GET page never includes the correct answer key", b"correct_index" not in resp.data)

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
