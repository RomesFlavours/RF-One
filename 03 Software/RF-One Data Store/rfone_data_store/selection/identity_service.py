"""Selection identity-resolution service (Task 3C-FIX §1/§2). Decides
whether a newly-imported résumé's `Candidate` row belongs to an already-
known `CandidatePerson`, using confidence-based matching
(`core/identity_model.py`). Only a VERY_STRONG match (identical normalized
email or phone) resolves automatically — the same rule the original Task 3C
`get_or_create_person_for_candidate` already applied for email, extended
here to phone. STRONG/POSSIBLE matches (name-based, no exact contact match)
are surfaced as a `PersonMatchCandidate` for the Selezionatore to confirm or
reject — never auto-merged ("Prefer false separation over an incorrect
merge.").

Reassignment (confirming a suggestion, or a direct manual correction) only
ever changes `Application.person_id`. Every other record — the CV snapshot
(`Candidate`), Fit Assessment, Signal Observations, evidence, notes — hangs
off `application_id`/`candidate_id`, never off `person_id` directly, so
none of it needs to move or can be lost by a reassignment. A placeholder
`CandidatePerson` left with zero Applications after a reassignment is kept,
never deleted — it may still be referenced by `PersonMatchCandidate` rows
as part of the audit trail, and the task only requires the Application to
move, never the person record to be destroyed. Never a merge of two real
person records either way.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import identity_model as idm


def _find_by_contact(
    session: Session, *, restaurant_id: int | None, normalized_email: str | None, normalized_phone: str | None,
) -> tuple[m.CandidatePerson | None, str | None, str | None]:
    if normalized_email:
        stmt = select(m.CandidatePerson).where(
            m.CandidatePerson.restaurant_id == restaurant_id, m.CandidatePerson.primary_email == normalized_email,
        )
        found = session.scalars(stmt).first()
        if found is not None:
            return found, idm.VERY_STRONG, f"Same email ({normalized_email})."
    if normalized_phone:
        stmt = select(m.CandidatePerson).where(
            m.CandidatePerson.restaurant_id == restaurant_id,
            m.CandidatePerson.primary_phone_normalized == normalized_phone,
        )
        found = session.scalars(stmt).first()
        if found is not None:
            return found, idm.VERY_STRONG, "Same phone number."
    return None, None, None


def _find_name_based_candidates(
    session: Session, *, restaurant_id: int | None, normalized_name: str | None, exclude_person_id: int,
) -> list[tuple[m.CandidatePerson, str, str]]:
    if not normalized_name:
        return []
    stmt = select(m.CandidatePerson).where(
        m.CandidatePerson.restaurant_id == restaurant_id,
        m.CandidatePerson.id != exclude_person_id,
        m.CandidatePerson.normalized_name.is_not(None),
    )
    matches: list[tuple[m.CandidatePerson, str, str]] = []
    for person in session.scalars(stmt).all():
        if person.normalized_name == normalized_name:
            matches.append((person, idm.STRONG, f"Same full name ({person.full_name})."))
        elif idm.names_share_surname_and_initial(normalized_name, person.normalized_name):
            matches.append((person, idm.POSSIBLE, f"Similar name ({person.full_name})."))
    return matches


def resolve_or_create_person(
    session: Session, *, restaurant_id: int | None, full_name: str | None, email: str | None, phone: str | None,
) -> tuple[m.CandidatePerson, bool]:
    """Returns `(person, is_new)`. A VERY_STRONG contact match (identical
    normalized email or phone) resolves directly to the existing person —
    the only case resolved automatically. Otherwise a brand-new
    `CandidatePerson` is created and returned with `is_new=True`; the
    caller (`application_service.create_application`) is responsible for
    calling `create_pending_suggestions_for_application` once the
    Application itself has an id, so any STRONG/POSSIBLE name-based
    suggestions can be recorded against it."""

    normalized_email = idm.normalize_email(email)
    normalized_phone = idm.normalize_phone(phone)
    normalized_name = idm.normalize_name(full_name)

    existing, _confidence, _basis = _find_by_contact(
        session, restaurant_id=restaurant_id, normalized_email=normalized_email, normalized_phone=normalized_phone,
    )
    if existing is not None:
        # Fill in previously-unknown display fields only — never overwrite
        # an already-known value (same rule Task 3C's original resolver used).
        if not existing.full_name and full_name:
            existing.full_name = full_name
            existing.normalized_name = normalized_name
        if not existing.primary_phone and phone:
            existing.primary_phone = phone
            existing.primary_phone_normalized = normalized_phone
        return existing, False

    person = m.CandidatePerson(
        restaurant_id=restaurant_id, full_name=full_name, primary_email=normalized_email,
        primary_phone=phone, primary_phone_normalized=normalized_phone, normalized_name=normalized_name,
    )
    session.add(person)
    session.flush()
    return person, True


def create_pending_suggestions_for_application(
    session: Session, *, application_id: int, new_person: m.CandidatePerson,
) -> list[m.PersonMatchCandidate]:
    """Records a `PersonMatchCandidate` suggestion for every STRONG/POSSIBLE
    name-based match found against OTHER existing persons at this
    restaurant. The new person and its Application remain fully usable and
    fully separate in the meantime — nothing here blocks or delays
    anything, it only surfaces a question for later confirmation."""

    candidates = _find_name_based_candidates(
        session, restaurant_id=new_person.restaurant_id, normalized_name=new_person.normalized_name,
        exclude_person_id=new_person.id,
    )
    created = [
        m.PersonMatchCandidate(
            application_id=application_id, source_person_id=new_person.id, suggested_person_id=suggested.id,
            confidence=confidence, match_basis=basis,
        )
        for suggested, confidence, basis in candidates
    ]
    if created:
        session.add_all(created)
        session.flush()
    return created


def list_pending_matches(session: Session, *, restaurant_id: int | None = None) -> list[m.PersonMatchCandidate]:
    stmt = (
        select(m.PersonMatchCandidate)
        .where(m.PersonMatchCandidate.status == idm.PENDING)
        .order_by(m.PersonMatchCandidate.id)
    )
    matches = list(session.scalars(stmt).all())
    if restaurant_id is not None:
        matches = [x for x in matches if x.source_person.restaurant_id == restaurant_id]
    return matches


def get_match(session: Session, match_id: int) -> m.PersonMatchCandidate | None:
    return session.get(m.PersonMatchCandidate, match_id)


def _close_out_orphaned_pending_matches(session: Session, person_id: int) -> None:
    """After a reassignment leaves `person_id` with zero Applications, any
    OTHER still-pending suggestion naming it as the source can no longer
    ever be confirmed against a real Application — close it out rather than
    leave a dangling row. The now-empty `CandidatePerson` row itself is
    deliberately NOT deleted: `PersonMatchCandidate` rows (this one
    included, now CONFIRMED/REJECTED) keep referencing it as part of the
    audit trail, and the task's own instruction is only that the
    Application move, never that the placeholder person be destroyed."""

    still_has_applications = session.scalars(
        select(m.Application).where(m.Application.person_id == person_id)
    ).first()
    if still_has_applications is not None:
        return

    other_pending = session.scalars(
        select(m.PersonMatchCandidate).where(
            m.PersonMatchCandidate.source_person_id == person_id, m.PersonMatchCandidate.status == idm.PENDING,
        )
    ).all()
    for pending in other_pending:
        pending.status = idm.REJECTED
        pending.reviewed_at = datetime.utcnow()
        pending.review_note = "Auto-closed: source person had no remaining Applications."


def confirm_match(session: Session, match_id: int, *, note: str | None = None) -> m.PersonMatchCandidate:
    """Selezionatore confirms this suggestion is the same person — safely
    reassigns the Application to the confirmed `CandidatePerson`. Every
    already-recorded CV/Fit Assessment/Signal Observation/note tied to this
    Application is untouched (none of it is keyed off `person_id`)."""

    match = session.get(m.PersonMatchCandidate, match_id)
    if match is None:
        raise ValueError(f"No PersonMatchCandidate with id {match_id}")
    if match.status != idm.PENDING:
        return match

    application = session.get(m.Application, match.application_id)
    if application is None:
        raise ValueError(f"No Application with id {match.application_id}")

    previous_person_id = application.person_id
    application.person_id = match.suggested_person_id
    application.identity_origin = idm.HUMAN_CONFIRMED
    application.identity_confirmed_at = datetime.utcnow()

    match.status = idm.CONFIRMED
    match.reviewed_at = datetime.utcnow()
    match.review_note = note
    session.flush()

    if previous_person_id != match.suggested_person_id:
        _close_out_orphaned_pending_matches(session, previous_person_id)
    session.flush()
    return match


def reject_match(session: Session, match_id: int, *, note: str | None = None) -> m.PersonMatchCandidate:
    """Selezionatore rejects this suggestion — the Application stays
    exactly where it is (on its own, separate `CandidatePerson`); both
    people remain intact."""

    match = session.get(m.PersonMatchCandidate, match_id)
    if match is None:
        raise ValueError(f"No PersonMatchCandidate with id {match_id}")
    if match.status != idm.PENDING:
        return match
    match.status = idm.REJECTED
    match.reviewed_at = datetime.utcnow()
    match.review_note = note
    session.flush()
    return match


def reassign_application(
    session: Session, application_id: int, *, target_person_id: int, note: str | None = None,
) -> m.Application:
    """Direct manual reassignment (task §2's general case) — used when a
    Selezionatore recognizes the correct person outside of a system-
    generated suggestion. Same safety guarantee as `confirm_match`: only
    `Application.person_id` changes."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    target = session.get(m.CandidatePerson, target_person_id)
    if target is None:
        raise ValueError(f"No CandidatePerson with id {target_person_id}")

    previous_person_id = application.person_id
    application.person_id = target_person_id
    application.identity_origin = idm.HUMAN_CONFIRMED
    application.identity_confirmed_at = datetime.utcnow()
    session.flush()

    if note:
        session.add(m.ApplicationNote(application_id=application.id, note_text=f"Identity reassignment: {note}"))

    if previous_person_id != target_person_id:
        _close_out_orphaned_pending_matches(session, previous_person_id)
    session.flush()
    return application


def list_persons(session: Session, *, restaurant_id: int | None = None) -> list[m.CandidatePerson]:
    """For the manual-reassignment UI's "target person" picker."""

    stmt = select(m.CandidatePerson).order_by(m.CandidatePerson.full_name)
    if restaurant_id is not None:
        stmt = stmt.where(m.CandidatePerson.restaurant_id == restaurant_id)
    return list(session.scalars(stmt).all())
