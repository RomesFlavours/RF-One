"""Training domain service — the only code that reads/writes `TrainingAccount`,
`TrainingPill`, `TrainingQuestion`, `TrainingNeed`, `TrainingAssignment`,
`TrainingAttempt` and `TrainingOverallAttempt` rows. The Flask web layer
(`03 Software/Training/`) never touches the ORM directly for Training data —
it calls only these functions, the same "service module operates on a
Session, web layer calls it" split already used by `rfone_data_store.tips`/
`rfone_data_store.selection`.

Password hashing uses Werkzeug's `generate_password_hash`/`check_password_
hash` — already a transitive Flask dependency, so this adds no new library.
The hash string is self-describing (Werkzeug picks and encodes its own
algorithm, currently scrypt; `check_password_hash` reads it back regardless
of which algorithm produced it), so this module never hard-codes one. A
plaintext password is never returned, logged or stored anywhere by this
module.
"""

from __future__ import annotations

import json
import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from .. import acting_identity_service
from .. import models as m
from .pills_content import PILL_DEFINITIONS, QUESTION_DEFINITIONS

UTC = timezone.utc

TRAINING_AUTH_PROVIDER = "training_local"

FAILED_LOGIN_LOCKOUT_THRESHOLD = 5
FAILED_LOGIN_LOCKOUT_MINUTES = 15

QUESTIONS_PER_QUIZ = 3
POINTS_PER_QUESTION = 1


# ---------------------------------------------------------------------------
# Pill / question seeding (idempotent — safe to call on every app start)
# ---------------------------------------------------------------------------


def ensure_pills_seeded(session: Session) -> None:
    """Creates the 3 pills + their question banks from `pills_content.py` if
    they do not already exist (matched by stable natural key: `slug` for
    pills, `(pill.slug, kind, position)` for questions). Never updates an
    already-existing row — there is no content editor in this version
    (spec §11); re-seeding only fills in what is missing."""
    pills_by_slug: dict[str, m.TrainingPill] = {}
    for defn in PILL_DEFINITIONS:
        existing = session.scalars(select(m.TrainingPill).where(m.TrainingPill.slug == defn["slug"])).first()
        if existing is None:
            existing = m.TrainingPill(
                slug=defn["slug"], title=defn["title"], learning_objectives=defn["learning_objectives"],
                content_version=defn["content_version"],
            )
            session.add(existing)
            session.flush()
        pills_by_slug[defn["slug"]] = existing

    for qdef in QUESTION_DEFINITIONS:
        pill = pills_by_slug[qdef["slug"]]
        existing_q = session.scalars(
            select(m.TrainingQuestion).where(
                m.TrainingQuestion.pill_id == pill.id,
                m.TrainingQuestion.kind == qdef["kind"],
                m.TrainingQuestion.position == qdef["position"],
            )
        ).first()
        if existing_q is None:
            session.add(m.TrainingQuestion(
                pill_id=pill.id, kind=qdef["kind"], category=qdef["category"], position=qdef["position"],
                version=qdef["version"], prompt=qdef["prompt"], options_json=json.dumps(qdef["options"]),
                correct_index=qdef["correct_index"], explanation=qdef["explanation"],
            ))
    session.flush()


# ---------------------------------------------------------------------------
# Accounts (login/authentication) — Training-local; see models.TrainingAccount
# module-level comment for why this is not RF-One's shared Authority engine.
# ---------------------------------------------------------------------------


class UsernameTakenError(ValueError):
    pass


def create_account(
    session: Session, *, display_name: str, username: str, password: str, role: str,
    created_by_account_id: int | None = None,
) -> m.TrainingAccount:
    if role not in ("trainer", "student"):
        raise ValueError(f"Invalid role {role!r}")
    normalized_username = username.strip().lower()
    if not normalized_username:
        raise ValueError("username is required")
    if not display_name.strip():
        raise ValueError("display_name is required")
    if not password:
        raise ValueError("password is required")

    existing = session.scalars(
        select(m.TrainingAccount).where(m.TrainingAccount.username == normalized_username)
    ).first()
    if existing is not None:
        raise UsernameTakenError(f"Username {normalized_username!r} is already in use.")

    identity = acting_identity_service.create_identity(
        session, kind=m.HUMAN_USER, display_name=display_name.strip(),
        authentication_provider=TRAINING_AUTH_PROVIDER, external_subject_id=normalized_username,
    )
    account = m.TrainingAccount(
        acting_identity_id=identity.id, username=normalized_username, role=role,
        password_hash=generate_password_hash(password), created_by_account_id=created_by_account_id,
    )
    session.add(account)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise UsernameTakenError(f"Username {normalized_username!r} is already in use.") from exc
    return account


def set_password(session: Session, account: m.TrainingAccount, new_password: str) -> None:
    """Overwrites the password hash — the previous password is never
    recoverable (spec §2: "senza poter recuperare quella precedente").
    Also clears any active lockout, so a trainer resetting a locked-out
    student's password immediately restores access."""
    if not new_password:
        raise ValueError("password is required")
    account.password_hash = generate_password_hash(new_password)
    account.failed_login_attempts = 0
    account.locked_until = None
    session.flush()


@dataclass(frozen=True)
class LoginResult:
    account: m.TrainingAccount | None
    error: str | None  # None on success


def verify_login(session: Session, username: str, password: str, *, now: datetime | None = None) -> LoginResult:
    """Server-side login check with a simple, self-contained lockout (spec
    §"protezioni minime" — "limita i tentativi ripetuti di login"). Always
    returns a generic error for an unknown username or a wrong password
    (never reveals which); a locked account gets its own distinct message
    (a minor, standard information trade-off — never blocking work on a
    more elaborate scheme for this version)."""
    now = now or datetime.now(UTC)
    normalized_username = username.strip().lower()
    account = session.scalars(
        select(m.TrainingAccount).where(m.TrainingAccount.username == normalized_username)
    ).first()

    if account is None:
        return LoginResult(None, "Invalid username or password.")

    if account.locked_until is not None and _as_aware(account.locked_until) > now:
        return LoginResult(None, "Too many attempts. Try again in a few minutes.")

    if not check_password_hash(account.password_hash, password):
        account.failed_login_attempts += 1
        if account.failed_login_attempts >= FAILED_LOGIN_LOCKOUT_THRESHOLD:
            account.locked_until = now + timedelta(minutes=FAILED_LOGIN_LOCKOUT_MINUTES)
        session.flush()
        return LoginResult(None, "Invalid username or password.")

    account.failed_login_attempts = 0
    account.locked_until = None
    session.flush()
    return LoginResult(account, None)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_account(session: Session, account_id: int) -> m.TrainingAccount | None:
    return session.get(m.TrainingAccount, account_id)


def is_trainer(account: m.TrainingAccount | None) -> bool:
    return account is not None and account.role == "trainer"


# ---------------------------------------------------------------------------
# Needs / assignments (trainer actions + student's own path)
# ---------------------------------------------------------------------------


def create_need(
    session: Session, *, student_account_id: int, text: str, origin: str | None, created_by_account_id: int,
) -> m.TrainingNeed:
    text = text.strip()
    if not text:
        raise ValueError("text is required")
    if origin == "":
        origin = None
    need = m.TrainingNeed(
        student_account_id=student_account_id, text=text, origin=origin,
        created_by_account_id=created_by_account_id,
    )
    session.add(need)
    session.flush()
    return need


class DuplicateAssignmentError(ValueError):
    pass


def assign_pill(
    session: Session, *, need_id: int, pill_id: int, assigned_by_account_id: int,
) -> m.TrainingAssignment:
    """Creates one (need, pill) assignment. The proactive existence check
    below is purely a friendlier error message; the `uq_training_
    assignment_need_pill` UNIQUE constraint on the table itself is the
    actual, race-safe guarantee against an unintended duplicate (spec §2)."""
    existing = session.scalars(
        select(m.TrainingAssignment).where(
            m.TrainingAssignment.need_id == need_id, m.TrainingAssignment.pill_id == pill_id,
        )
    ).first()
    if existing is not None:
        raise DuplicateAssignmentError("This pill is already assigned to this need.")

    assignment = m.TrainingAssignment(need_id=need_id, pill_id=pill_id, assigned_by_account_id=assigned_by_account_id)
    session.add(assignment)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateAssignmentError("This pill is already assigned to this need.") from exc
    return assignment


@dataclass(frozen=True)
class BulkAssignResult:
    created_count: int
    already_assigned_count: int


def assign_pills_bulk(
    session: Session, *, need_id: int, pill_ids: list[int], assigned_by_account_id: int,
) -> BulkAssignResult:
    """The multi-select counterpart to `assign_pill` (trainer "Assign pills"
    modal). Two different failure modes, deliberately NOT symmetric:

    - An unknown pill id is a request-integrity problem (a tampered form, a
      pill deleted between page load and submit) — this raises `ValueError`
      and creates NOTHING at all, even for the other, valid ids in the same
      submission ("identificativi non validi... devono impedire scritture
      parziali").
    - A pill already assigned to THIS need is an entirely normal outcome
      (the trainer re-submitted, or another trainer/tab assigned it a
      moment ago) — it is silently skipped and counted, never an error
      ("quelle già presenti vanno saltate e conteggiate"). A pill already
      assigned to a DIFFERENT need is not a duplicate at all (spec:
      `TrainingAssignment`'s own docstring — the same pill can be assigned
      under different needs) and is created normally.

    Each insert runs in its own SAVEPOINT (`session.begin_nested()`): a
    unique-constraint race against a truly concurrent request/double
    submit is caught per-row and folded into `already_assigned_count`,
    without poisoning the surrounding transaction for the rows that DID
    succeed — one commit by the caller persists everything atomically."""
    need = session.get(m.TrainingNeed, need_id)
    if need is None:
        raise ValueError("Training need not found.")

    unique_ids = sorted(set(pill_ids))
    if not unique_ids:
        raise ValueError("At least one pill must be selected.")

    existing_pill_ids = set(
        session.scalars(select(m.TrainingPill.id).where(m.TrainingPill.id.in_(unique_ids)))
    )
    missing = set(unique_ids) - existing_pill_ids
    if missing:
        raise ValueError(f"Unknown pill id(s): {sorted(missing)}")

    already_assigned_ids = set(
        session.scalars(
            select(m.TrainingAssignment.pill_id).where(
                m.TrainingAssignment.need_id == need_id, m.TrainingAssignment.pill_id.in_(unique_ids),
            )
        )
    )

    created_count = 0
    already_assigned_count = len(already_assigned_ids)

    for pill_id in unique_ids:
        if pill_id in already_assigned_ids:
            continue
        try:
            with session.begin_nested():
                session.add(m.TrainingAssignment(
                    need_id=need_id, pill_id=pill_id, assigned_by_account_id=assigned_by_account_id,
                ))
                session.flush()
            created_count += 1
        except IntegrityError:
            already_assigned_count += 1

    return BulkAssignResult(created_count=created_count, already_assigned_count=already_assigned_count)


def mark_assignment_opened(session: Session, assignment: m.TrainingAssignment, *, now: datetime | None = None) -> None:
    if assignment.first_opened_at is None:
        assignment.first_opened_at = now or datetime.now(UTC)
        session.flush()


ASSIGNMENT_NOT_STARTED = "not_started"
ASSIGNMENT_IN_PROGRESS = "in_progress"
ASSIGNMENT_COMPLETED = "completed"

ASSIGNMENT_STATUS_LABELS = {
    ASSIGNMENT_NOT_STARTED: "Not started",
    ASSIGNMENT_IN_PROGRESS: "In progress",
    ASSIGNMENT_COMPLETED: "Completed",
}


def assignment_status(session: Session, assignment: m.TrainingAssignment) -> str:
    """Spec §4's three states, computed live from what actually happened on
    THIS assignment row — never stored/cached, so it can never drift from
    the facts (`first_opened_at`, and whether at least one `TrainingAttempt`
    exists for this assignment). "Completed" means the activity was
    completed at least once, never a claim of proven competence (spec §4)."""
    if assignment.first_opened_at is None:
        return ASSIGNMENT_NOT_STARTED
    has_attempt = session.scalars(
        select(m.TrainingAttempt.id).where(m.TrainingAttempt.assignment_id == assignment.id).limit(1)
    ).first()
    return ASSIGNMENT_COMPLETED if has_attempt is not None else ASSIGNMENT_IN_PROGRESS


def list_needs_for_student(session: Session, student_account_id: int) -> list[m.TrainingNeed]:
    return list(
        session.scalars(
            select(m.TrainingNeed)
            .where(m.TrainingNeed.student_account_id == student_account_id)
            .order_by(m.TrainingNeed.created_at)
        ).all()
    )


def list_assignments_for_need(session: Session, need_id: int) -> list[m.TrainingAssignment]:
    return list(
        session.scalars(
            select(m.TrainingAssignment)
            .where(m.TrainingAssignment.need_id == need_id)
            .order_by(m.TrainingAssignment.assigned_at)
        ).all()
    )


def latest_attempt_for_assignment(session: Session, assignment_id: int) -> m.TrainingAttempt | None:
    return session.scalars(
        select(m.TrainingAttempt)
        .where(m.TrainingAttempt.assignment_id == assignment_id)
        .order_by(m.TrainingAttempt.submitted_at.desc())
        .limit(1)
    ).first()


def list_attempts_for_assignment(session: Session, assignment_id: int) -> list[m.TrainingAttempt]:
    return list(
        session.scalars(
            select(m.TrainingAttempt)
            .where(m.TrainingAttempt.assignment_id == assignment_id)
            .order_by(m.TrainingAttempt.submitted_at.desc())
        ).all()
    )


def list_all_students(session: Session) -> list[m.TrainingAccount]:
    return list(
        session.scalars(
            select(m.TrainingAccount).where(m.TrainingAccount.role == "student").order_by(m.TrainingAccount.username)
        ).all()
    )


def list_all_pills(session: Session) -> list[m.TrainingPill]:
    return list(session.scalars(select(m.TrainingPill).order_by(m.TrainingPill.title)).all())


# ---------------------------------------------------------------------------
# Final (per-pill) quiz
# ---------------------------------------------------------------------------


def get_self_check_questions(session: Session, pill_id: int) -> list[m.TrainingQuestion]:
    return list(
        session.scalars(
            select(m.TrainingQuestion)
            .where(m.TrainingQuestion.pill_id == pill_id, m.TrainingQuestion.kind == "self_check")
            .order_by(m.TrainingQuestion.position)
        ).all()
    )


def find_latest_assignment_for_pill(
    session: Session, *, student_account_id: int, pill_id: int,
) -> m.TrainingAssignment | None:
    return session.scalars(
        select(m.TrainingAssignment)
        .join(m.TrainingNeed, m.TrainingAssignment.need_id == m.TrainingNeed.id)
        .where(m.TrainingNeed.student_account_id == student_account_id, m.TrainingAssignment.pill_id == pill_id)
        .order_by(m.TrainingAssignment.assigned_at.desc())
        .limit(1)
    ).first()


def _canonical_final_quiz_questions(session: Session, pill_id: int) -> list[m.TrainingQuestion]:
    return list(
        session.scalars(
            select(m.TrainingQuestion)
            .where(m.TrainingQuestion.pill_id == pill_id, m.TrainingQuestion.kind == "final_quiz")
            .order_by(m.TrainingQuestion.position)
        ).all()
    )


def get_final_quiz_view(session: Session, assignment: m.TrainingAssignment) -> list[m.TrainingQuestion]:
    """Questions for GET-rendering only — the caller (web layer) must strip
    `correct_index`/`explanation` before it ever reaches a template context
    used for the pre-submission page (spec §6 — never send the solution to
    the client before submission)."""
    return _canonical_final_quiz_questions(session, assignment.pill_id)


class DuplicateSubmissionError(ValueError):
    """Raised when a `submission_token` has already been used — the caller
    should treat this as "already recorded", not as an error to surface."""


def record_final_attempt(
    session: Session, *, assignment: m.TrainingAssignment, answers: dict[int, int | None],
    submission_token: str, now: datetime | None = None,
) -> m.TrainingAttempt:
    """Scores and records one final-quiz submission. `answers` maps
    `TrainingQuestion.id -> selected option index or None`; the set of
    questions actually graded is always re-derived here from the pill's
    live `final_quiz` bank (never trusted from client-submitted question
    ids), so a tampered question list cannot change what is graded.
    `submission_token`'s UNIQUE constraint is the actual guard against a
    double click creating two attempt rows (see `models.TrainingAttempt`)."""
    questions = _canonical_final_quiz_questions(session, assignment.pill_id)
    snapshot_questions = []
    snapshot_answers = []
    points_earned = 0
    for q in questions:
        given = answers.get(q.id)
        is_correct = given is not None and given == q.correct_index
        if is_correct:
            points_earned += POINTS_PER_QUESTION
        snapshot_questions.append({
            "question_id": q.id, "category": q.category, "prompt": q.prompt,
            "options": json.loads(q.options_json), "correct_index": q.correct_index,
            "explanation": q.explanation,
        })
        snapshot_answers.append(given)

    attempt = m.TrainingAttempt(
        assignment_id=assignment.id, student_account_id=assignment.need.student_account_id,
        pill_id=assignment.pill_id, pill_content_version=assignment.pill.content_version,
        quiz_version=questions[0].version if questions else 1,
        questions_json=json.dumps(snapshot_questions), answers_json=json.dumps(snapshot_answers),
        points_earned=points_earned, points_possible=len(questions) * POINTS_PER_QUESTION,
        submission_token=submission_token, submitted_at=now or datetime.now(UTC),
    )
    session.add(attempt)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalars(
            select(m.TrainingAttempt).where(m.TrainingAttempt.submission_token == submission_token)
        ).first()
        if existing is not None:
            raise DuplicateSubmissionError(str(existing.id)) from exc
        raise
    return attempt


def get_attempt(session: Session, attempt_id: int) -> m.TrainingAttempt | None:
    return session.get(m.TrainingAttempt, attempt_id)


# ---------------------------------------------------------------------------
# Overall (whole-path) quiz
# ---------------------------------------------------------------------------


def distinct_assigned_pills(session: Session, student_account_id: int) -> list[m.TrainingPill]:
    """Pill spec §7 — "considera una sola volta ciascuna pillola distinta
    assegnata alla persona" — deduplicated by pill id across every need."""
    assignments = list(
        session.scalars(
            select(m.TrainingAssignment)
            .join(m.TrainingNeed, m.TrainingAssignment.need_id == m.TrainingNeed.id)
            .where(m.TrainingNeed.student_account_id == student_account_id)
        ).all()
    )
    seen: dict[int, m.TrainingPill] = {}
    for a in assignments:
        if a.pill_id not in seen:
            seen[a.pill_id] = a.pill
    return list(seen.values())


def student_assignments(session: Session, student_account_id: int) -> list[m.TrainingAssignment]:
    return list(
        session.scalars(
            select(m.TrainingAssignment)
            .join(m.TrainingNeed, m.TrainingAssignment.need_id == m.TrainingNeed.id)
            .where(m.TrainingNeed.student_account_id == student_account_id)
        ).all()
    )


def overall_quiz_available(session: Session, student_account_id: int) -> bool:
    assignments = student_assignments(session, student_account_id)
    if not assignments:
        return False
    return all(assignment_status(session, a) == ASSIGNMENT_COMPLETED for a in assignments)


def _canonical_overall_quiz_questions(session: Session, pill_ids: list[int]) -> list[m.TrainingQuestion]:
    if not pill_ids:
        return []
    return list(
        session.scalars(
            select(m.TrainingQuestion)
            .where(m.TrainingQuestion.pill_id.in_(pill_ids), m.TrainingQuestion.kind == "overall_quiz")
            .order_by(m.TrainingQuestion.pill_id, m.TrainingQuestion.position)
        ).all()
    )


def get_overall_quiz_view(session: Session, student_account_id: int, *, shuffle: bool = True) -> list[m.TrainingQuestion]:
    pills = distinct_assigned_pills(session, student_account_id)
    questions = _canonical_overall_quiz_questions(session, [p.id for p in pills])
    if shuffle:
        questions = list(questions)
        random.shuffle(questions)
    return questions


def record_overall_attempt(
    session: Session, *, student_account_id: int, answers: dict[int, int | None],
    submission_token: str, now: datetime | None = None,
) -> m.TrainingOverallAttempt:
    pills = distinct_assigned_pills(session, student_account_id)
    questions = _canonical_overall_quiz_questions(session, [p.id for p in pills])

    snapshot_questions = []
    snapshot_answers = []
    points_earned = 0
    for q in questions:
        given = answers.get(q.id)
        is_correct = given is not None and given == q.correct_index
        if is_correct:
            points_earned += POINTS_PER_QUESTION
        snapshot_questions.append({
            "question_id": q.id, "pill_id": q.pill_id, "category": q.category, "prompt": q.prompt,
            "options": json.loads(q.options_json), "correct_index": q.correct_index,
            "explanation": q.explanation,
        })
        snapshot_answers.append(given)

    pills_snapshot = [{"pill_id": p.id, "slug": p.slug, "title": p.title, "content_version": p.content_version}
                       for p in pills]

    attempt = m.TrainingOverallAttempt(
        student_account_id=student_account_id, pills_json=json.dumps(pills_snapshot),
        questions_json=json.dumps(snapshot_questions), answers_json=json.dumps(snapshot_answers),
        points_earned=points_earned, points_possible=len(questions) * POINTS_PER_QUESTION,
        submission_token=submission_token, submitted_at=now or datetime.now(UTC),
    )
    session.add(attempt)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalars(
            select(m.TrainingOverallAttempt).where(m.TrainingOverallAttempt.submission_token == submission_token)
        ).first()
        if existing is not None:
            raise DuplicateSubmissionError(str(existing.id)) from exc
        raise
    return attempt


def get_overall_attempt(session: Session, attempt_id: int) -> m.TrainingOverallAttempt | None:
    return session.get(m.TrainingOverallAttempt, attempt_id)


def list_overall_attempts_for_student(session: Session, student_account_id: int) -> list[m.TrainingOverallAttempt]:
    return list(
        session.scalars(
            select(m.TrainingOverallAttempt)
            .where(m.TrainingOverallAttempt.student_account_id == student_account_id)
            .order_by(m.TrainingOverallAttempt.submitted_at.desc())
        ).all()
    )


def new_submission_token() -> str:
    return secrets.token_urlsafe(32)
