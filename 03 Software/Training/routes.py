"""Training's Flask Blueprint — all routes for the first operational version
(spec: staff login, student personal path, trainer area, per-pill self-check
+ final quiz, whole-path quiz). Registered onto the existing Tips Flask app
by `Tips/app.py` (`app.register_blueprint(training_bp)`) — that one import +
one call is the *only* place Tips references Training; every other file in
this package is self-contained (own `db.py`, own templates, own auth).

Row-level access control: every route that loads a specific assignment/
attempt/student first verifies server-side that it belongs to the current
student (or, for trainer-only views, that the current account is a trainer)
before returning anything — never inferred from a client-supplied id alone.
A cross-student access attempt gets a 404 (never a 403 that would confirm
the id exists), matching the spec's "controlla lato server l'accesso ai
dati: ogni studente vede e modifica solo i propri"."""

from __future__ import annotations

import json

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from auth import (
    current_account_id, get_csrf_token, load_current_account, log_in, log_out,
    require_csrf, require_login, require_trainer,
)
from db import SessionFactory
from dish_data import get_dish
from rfone_data_store import models as m
from rfone_data_store.training import service as svc

training_bp = Blueprint("training", __name__, template_folder="templates", url_prefix="/training")

# Menu-area grouping for the trainer's pill-assignment picker (RF-ONE:
# importare le 51 nuove pillole, task §3 — "Mostra il raggruppamento...
# nella selezione delle pillole da assegnare"). Reuses the SAME `category`
# field already sourced from `RF-One-Training.html`'s dish-data via
# `dish_data.get_dish()` — no new column, no schema change. `_CATEGORY_
# DISPLAY_ALIASES` normalizes the preserved Caprese pill's existing
# singular "Appetizer" label for grouping purposes only — its own stored
# dish-data entry is never modified.
_AREA_ORDER = ["Appetizers", "Soups", "Bruschetta", "Salads", "Pasta", "Pizzas", "Meat & Fish", "Sides", "Desserts"]
_CATEGORY_DISPLAY_ALIASES = {"Appetizer": "Appetizers"}


def _pill_area(pill) -> str:
    dish = get_dish(pill.slug)
    raw_category = dish["category"] if dish else "Other"
    return _CATEGORY_DISPLAY_ALIASES.get(raw_category, raw_category)


def _group_pills_by_area(pills: list) -> list[tuple[str, list]]:
    grouped: dict[str, list] = {}
    for pill in pills:
        grouped.setdefault(_pill_area(pill), []).append(pill)
    ordered = [(area, grouped.pop(area)) for area in _AREA_ORDER if area in grouped]
    ordered.extend(grouped.items())  # any leftover area not in the fixed order, kept rather than dropped
    return ordered


@training_bp.context_processor
def _inject_csrf():
    return {"csrf_token": get_csrf_token}


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------


@training_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_account_id() is not None:
        return redirect(url_for("training.home"))

    if request.method == "POST":
        require_csrf()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        with SessionFactory() as db:
            result = svc.verify_login(db, username, password)
            db.commit()
        if result.account is None:
            flash(result.error or "Invalid username or password.", "error")
            return render_template("training/login.html"), 401
        log_in(result.account.id)
        next_url = request.args.get("next") or url_for("training.home")
        return redirect(next_url)

    return render_template("training/login.html")


@training_bp.route("/logout", methods=["POST"])
@require_login
def logout():
    require_csrf()
    log_out()
    return redirect(url_for("training.login"))


# ---------------------------------------------------------------------------
# Student home / personal path
# ---------------------------------------------------------------------------


@training_bp.route("", strict_slashes=False)
@require_login
def home():
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for("training.login"))
        if account.role == "trainer":
            return redirect(url_for("training.trainer_home"))

        needs = svc.list_needs_for_student(db, account.id)
        needs_view = []
        for need in needs:
            assignments = svc.list_assignments_for_need(db, need.id)
            assignments_view = []
            for a in assignments:
                status = svc.assignment_status(db, a)
                latest = svc.latest_attempt_for_assignment(db, a.id)
                assignments_view.append({
                    "assignment": a, "pill": a.pill, "status": status,
                    "status_label": svc.ASSIGNMENT_STATUS_LABELS[status],
                    "latest_attempt": latest,
                })
            needs_view.append({"need": need, "assignments": assignments_view})

        overall_available = svc.overall_quiz_available(db, account.id)
        has_assignments = len(svc.student_assignments(db, account.id)) > 0
        overall_history = svc.list_overall_attempts_for_student(db, account.id)

        return render_template(
            "training/student_home.html", account=account, needs_view=needs_view,
            overall_available=overall_available, has_assignments=has_assignments,
            overall_history=overall_history,
        )


def _load_own_assignment(db, account_id: int, assignment_id: int) -> "m.TrainingAssignment":
    assignment = db.get(m.TrainingAssignment, assignment_id)
    if assignment is None or assignment.need.student_account_id != account_id:
        abort(404)
    return assignment


@training_bp.route("/assignments/<int:assignment_id>")
@require_login
def assignment_detail(assignment_id: int):
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None or account.role != "student":
            abort(404)
        assignment = _load_own_assignment(db, account.id, assignment_id)
        svc.mark_assignment_opened(db, assignment)
        db.commit()

        pill = assignment.pill
        dish = get_dish(pill.slug)
        self_check_questions = svc.get_self_check_questions(db, pill.id)
        self_check_view = [
            {"id": q.id, "category": q.category, "prompt": q.prompt, "options": json.loads(q.options_json),
             "correct_index": q.correct_index, "explanation": q.explanation}
            for q in self_check_questions
        ]
        status = svc.assignment_status(db, assignment)
        attempts = svc.list_attempts_for_assignment(db, assignment.id)

        return render_template(
            "training/assignment_detail.html", assignment=assignment, pill=pill, dish=dish,
            self_check_questions=self_check_view, status=status,
            status_label=svc.ASSIGNMENT_STATUS_LABELS[status], attempts=attempts,
        )


@training_bp.route("/assignments/<int:assignment_id>/final-quiz", methods=["GET", "POST"])
@require_login
def final_quiz(assignment_id: int):
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None or account.role != "student":
            abort(404)
        assignment = _load_own_assignment(db, account.id, assignment_id)

        if request.method == "POST":
            require_csrf()
            questions = svc.get_final_quiz_view(db, assignment)
            answers: dict[int, int | None] = {}
            for q in questions:
                raw = request.form.get(f"answer_{q.id}")
                answers[q.id] = int(raw) if raw not in (None, "") else None
            token = request.form.get("submission_token", "")
            if not token:
                abort(400)
            try:
                attempt = svc.record_final_attempt(
                    db, assignment=assignment, answers=answers, submission_token=token,
                )
                db.commit()
                attempt_id = attempt.id
            except svc.DuplicateSubmissionError as exc:
                db.rollback()
                attempt_id = int(str(exc))
            return redirect(url_for("training.attempt_result", attempt_id=attempt_id))

        questions = svc.get_final_quiz_view(db, assignment)
        questions_view = [
            {"id": q.id, "category": q.category, "prompt": q.prompt, "options": json.loads(q.options_json)}
            for q in questions
        ]
        return render_template(
            "training/final_quiz.html", assignment=assignment, pill=assignment.pill,
            questions=questions_view, submission_token=svc.new_submission_token(),
        )


def _render_attempt_result(attempt: "m.TrainingAttempt", *, back_url: str):
    questions = json.loads(attempt.questions_json)
    answers = json.loads(attempt.answers_json)
    rows = []
    for q, given in zip(questions, answers):
        rows.append({
            "category": q["category"], "prompt": q["prompt"], "options": q["options"],
            "correct_index": q["correct_index"], "given_index": given,
            "is_correct": given is not None and given == q["correct_index"],
            "explanation": q["explanation"],
        })
    percentage = round(100 * attempt.points_earned / attempt.points_possible) if attempt.points_possible else 0
    return render_template(
        "training/attempt_result.html", attempt=attempt, rows=rows, percentage=percentage, back_url=back_url,
    )


@training_bp.route("/attempts/<int:attempt_id>")
@require_login
def attempt_result(attempt_id: int):
    with SessionFactory() as db:
        account = load_current_account(db)
        attempt = svc.get_attempt(db, attempt_id)
        if account is None or attempt is None or attempt.student_account_id != account.id:
            abort(404)
        back_url = url_for("training.assignment_detail", assignment_id=attempt.assignment_id)
        return _render_attempt_result(attempt, back_url=back_url)


# ---------------------------------------------------------------------------
# Overall (whole-path) quiz
# ---------------------------------------------------------------------------


@training_bp.route("/overall-quiz", methods=["GET", "POST"])
@require_login
def overall_quiz():
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None or account.role != "student":
            abort(404)

        if request.method == "POST":
            require_csrf()
            questions = svc.get_overall_quiz_view(db, account.id, shuffle=False)
            answers: dict[int, int | None] = {}
            for q in questions:
                raw = request.form.get(f"answer_{q.id}")
                answers[q.id] = int(raw) if raw not in (None, "") else None
            token = request.form.get("submission_token", "")
            if not token:
                abort(400)
            try:
                attempt = svc.record_overall_attempt(
                    db, student_account_id=account.id, answers=answers, submission_token=token,
                )
                db.commit()
                attempt_id = attempt.id
            except svc.DuplicateSubmissionError as exc:
                db.rollback()
                attempt_id = int(str(exc))
            return redirect(url_for("training.overall_attempt_result", attempt_id=attempt_id))

        if not svc.overall_quiz_available(db, account.id):
            flash(
                "The whole-path quiz becomes available once every pill assigned to you has been "
                "completed at least once.", "error",
            )
            return redirect(url_for("training.home"))

        questions = svc.get_overall_quiz_view(db, account.id, shuffle=True)
        questions_view = [
            {"id": q.id, "category": q.category, "prompt": q.prompt, "options": json.loads(q.options_json)}
            for q in questions
        ]
        return render_template(
            "training/overall_quiz.html", questions=questions_view, submission_token=svc.new_submission_token(),
        )


@training_bp.route("/overall-attempts/<int:attempt_id>")
@require_login
def overall_attempt_result(attempt_id: int):
    with SessionFactory() as db:
        account = load_current_account(db)
        attempt = svc.get_overall_attempt(db, attempt_id)
        if account is None or attempt is None or attempt.student_account_id != account.id:
            abort(404)
        return _render_overall_attempt_result(db, account.id, attempt, back_url=url_for("training.home"))


def _render_overall_attempt_result(db, student_account_id: int, attempt: "m.TrainingOverallAttempt", *, back_url: str):
    questions = json.loads(attempt.questions_json)
    answers = json.loads(attempt.answers_json)
    pills = json.loads(attempt.pills_json)
    pills_by_id = {p["pill_id"]: p for p in pills}

    missed_pill_ids: set[int] = set()
    rows = []
    for q, given in zip(questions, answers):
        is_correct = given is not None and given == q["correct_index"]
        if not is_correct:
            missed_pill_ids.add(q["pill_id"])
        rows.append({
            "pill_title": pills_by_id.get(q["pill_id"], {}).get("title", "?"), "category": q["category"],
            "prompt": q["prompt"], "options": q["options"], "correct_index": q["correct_index"],
            "given_index": given, "is_correct": is_correct, "explanation": q["explanation"],
        })

    review_links = []
    for pid in missed_pill_ids:
        assignment = svc.find_latest_assignment_for_pill(db, student_account_id=student_account_id, pill_id=pid)
        if assignment is not None:
            review_links.append({
                "title": pills_by_id.get(pid, {}).get("title", "?"),
                "url": url_for("training.assignment_detail", assignment_id=assignment.id),
            })

    percentage = round(100 * attempt.points_earned / attempt.points_possible) if attempt.points_possible else 0
    return render_template(
        "training/overall_attempt_result.html", attempt=attempt, rows=rows, percentage=percentage,
        review_links=review_links, pills=pills, back_url=back_url,
    )


# ---------------------------------------------------------------------------
# Trainer area
# ---------------------------------------------------------------------------


@training_bp.route("/trainer")
@require_trainer
def trainer_home():
    with SessionFactory() as db:
        account = load_current_account(db)
        students = svc.list_all_students(db)
        students_view = [
            {"account": s, "need_count": len(svc.list_needs_for_student(db, s.id))} for s in students
        ]
        return render_template("training/trainer_home.html", account=account, students=students_view)


@training_bp.route("/trainer/students/new", methods=["GET", "POST"])
@require_trainer
def trainer_new_student():
    with SessionFactory() as db:
        account = load_current_account(db)
        if request.method == "POST":
            require_csrf()
            display_name = request.form.get("display_name", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            try:
                student = svc.create_account(
                    db, display_name=display_name, username=username, password=password, role="student",
                    created_by_account_id=account.id,
                )
                db.commit()
                flash(f"Student '{display_name}' created.", "info")
                return redirect(url_for("training.trainer_student_detail", account_id=student.id))
            except (svc.UsernameTakenError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
        return render_template("training/trainer_new_student.html", account=account)


def _load_student_or_404(db, account_id: int) -> "m.TrainingAccount":
    student = svc.get_account(db, account_id)
    if student is None or student.role != "student":
        abort(404)
    return student


@training_bp.route("/trainer/students/<int:account_id>")
@require_trainer
def trainer_student_detail(account_id: int):
    with SessionFactory() as db:
        account = load_current_account(db)
        student = _load_student_or_404(db, account_id)
        needs = svc.list_needs_for_student(db, student.id)
        needs_view = []
        for need in needs:
            assignments = svc.list_assignments_for_need(db, need.id)
            assignments_view = []
            for a in assignments:
                status = svc.assignment_status(db, a)
                attempts = svc.list_attempts_for_assignment(db, a.id)
                assignments_view.append({
                    "assignment": a, "pill": a.pill, "status": status,
                    "status_label": svc.ASSIGNMENT_STATUS_LABELS[status], "attempts": attempts,
                })
            needs_view.append({
                "need": need, "assignments": assignments_view,
                # Already-assigned pills for THIS need only — never pills
                # assigned to a different need (spec: assigning the same
                # pill under a different need is not a duplicate at all).
                "assigned_pill_ids": [row["pill"].id for row in assignments_view],
            })

        overall_history = svc.list_overall_attempts_for_student(db, student.id)
        all_pills = svc.list_all_pills(db)
        pills_by_area = _group_pills_by_area(all_pills)
        # Flat, JSON-serializable catalog for the "Assign pills" modal
        # (assign-pills-catalog script island in the template) — area and
        # scope come from the SAME existing sources as the rest of this
        # page (dish-data category, `learning_objectives`), never a new
        # taxonomy or generated content.
        all_pills_data = [
            {"id": pill.id, "title": pill.title, "area": _pill_area(pill), "scope": pill.learning_objectives}
            for pill in all_pills
        ]
        areas_order = [area for area, _pills in pills_by_area]
        return render_template(
            "training/trainer_student_detail.html", account=account, student=student, needs_view=needs_view,
            all_pills=all_pills, pills_by_area=pills_by_area, overall_history=overall_history,
            all_pills_data=all_pills_data, areas_order=areas_order,
        )


@training_bp.route("/trainer/students/<int:account_id>/reset-password", methods=["POST"])
@require_trainer
def trainer_reset_password(account_id: int):
    require_csrf()
    with SessionFactory() as db:
        student = _load_student_or_404(db, account_id)
        new_password = request.form.get("password", "")
        try:
            svc.set_password(db, student, new_password)
            db.commit()
            flash("Password updated.", "info")
        except ValueError as exc:
            db.rollback()
            flash(str(exc), "error")
    return redirect(url_for("training.trainer_student_detail", account_id=account_id))


@training_bp.route("/trainer/students/<int:account_id>/needs", methods=["POST"])
@require_trainer
def trainer_create_need(account_id: int):
    require_csrf()
    with SessionFactory() as db:
        account = load_current_account(db)
        student = _load_student_or_404(db, account_id)
        text = request.form.get("text", "")
        origin = request.form.get("origin") or None
        try:
            svc.create_need(db, student_account_id=student.id, text=text, origin=origin, created_by_account_id=account.id)
            db.commit()
        except ValueError as exc:
            db.rollback()
            flash(str(exc), "error")
    return redirect(url_for("training.trainer_student_detail", account_id=account_id))


@training_bp.route("/trainer/needs/<int:need_id>/assign", methods=["POST"])
@require_trainer
def trainer_assign_pill(need_id: int):
    require_csrf()
    with SessionFactory() as db:
        account = load_current_account(db)
        need = db.get(m.TrainingNeed, need_id)
        if need is None:
            abort(404)
        pill_id = request.form.get("pill_id", type=int)
        if pill_id is None:
            abort(400)
        try:
            svc.assign_pill(db, need_id=need_id, pill_id=pill_id, assigned_by_account_id=account.id)
            db.commit()
        except svc.DuplicateAssignmentError as exc:
            db.rollback()
            flash(str(exc), "error")
        student_account_id = need.student_account_id
    return redirect(url_for("training.trainer_student_detail", account_id=student_account_id))


@training_bp.route("/trainer/needs/<int:need_id>/assign-multiple", methods=["POST"])
@require_trainer
def trainer_assign_pills_multiple(need_id: int):
    """The "Assign pills" modal's target — one POST, many pills, one
    transaction (task §3). CSRF, need existence, and trainer authorization
    are checked exactly like every other trainer route here; pill id
    validity/dedup and the actual writes are `assign_pills_bulk`'s job
    (see its own docstring for the two different failure modes)."""
    require_csrf()
    with SessionFactory() as db:
        account = load_current_account(db)
        need = db.get(m.TrainingNeed, need_id)
        if need is None:
            abort(404)
        student_account_id = need.student_account_id

        raw_ids = request.form.getlist("pill_ids")
        try:
            pill_ids = [int(v) for v in raw_ids]
        except ValueError:
            abort(400, description="Invalid pill selection.")

        if not pill_ids:
            flash("Select at least one pill to assign.", "error")
            return redirect(url_for("training.trainer_student_detail", account_id=student_account_id))

        try:
            result = svc.assign_pills_bulk(
                db, need_id=need_id, pill_ids=pill_ids, assigned_by_account_id=account.id,
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            flash(str(exc), "error")
            return redirect(url_for("training.trainer_student_detail", account_id=student_account_id))

    if result.already_assigned_count:
        flash(
            f"{result.created_count} pill(s) assigned "
            f"({result.already_assigned_count} were already assigned to this need).",
            "info",
        )
    else:
        flash(f"{result.created_count} pill(s) assigned.", "info")
    return redirect(url_for("training.trainer_student_detail", account_id=student_account_id))


@training_bp.route("/trainer/attempts/<int:attempt_id>")
@require_trainer
def trainer_view_attempt(attempt_id: int):
    with SessionFactory() as db:
        attempt = svc.get_attempt(db, attempt_id)
        if attempt is None:
            abort(404)
        back_url = url_for("training.trainer_student_detail", account_id=attempt.student_account_id)
        return _render_attempt_result(attempt, back_url=back_url)


@training_bp.route("/trainer/overall-attempts/<int:attempt_id>")
@require_trainer
def trainer_view_overall_attempt(attempt_id: int):
    with SessionFactory() as db:
        attempt = svc.get_overall_attempt(db, attempt_id)
        if attempt is None:
            abort(404)
        back_url = url_for("training.trainer_student_detail", account_id=attempt.student_account_id)
        return _render_overall_attempt_result(db, attempt.student_account_id, attempt, back_url=back_url)
