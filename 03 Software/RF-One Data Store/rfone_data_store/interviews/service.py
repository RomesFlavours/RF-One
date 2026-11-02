"""Persistent, revision-checked interview engine with explicit participants."""
from datetime import datetime, timezone
import json
import uuid

from sqlalchemy import inspect, select, update

from .. import models as m
from .. import rfone_web_session as permissions
from . import directory_bridge as people
from .models import InterviewSession
from .provider import ProviderError
from .specializations import get_specialization


class ConflictError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc)


# Columns added after the first release; until their migration runs the feature
# reports "not available yet" instead of failing on every query.
REQUIRED_COLUMNS = {"person_id", "consent_given", "consent_at"}


def available(db):
    inspector = inspect(db.connection())
    return (inspector.has_table(InterviewSession.__tablename__) and
        REQUIRED_COLUMNS <= {c["name"] for c in inspector.get_columns(InterviewSession.__tablename__)})


def active(account):
    if account is None or account.status != "ACTIVE":
        raise PermissionError("Account unavailable.")


def require_manager(db, account):
    active(account)
    if not permissions.account_may_use_domain_item(db, account, "ORGANIZATION", "interviews"):
        raise PermissionError("Interviews access required.")


def request_interview(db, requester, recipient_id, purpose, specialization="KNOW_HOW"):
    require_manager(db, requester)
    recipient = db.get(m.RFOneAccount, recipient_id)
    active(recipient)
    purpose = purpose.strip()
    if not purpose or len(purpose) > 4000:
        raise ValueError("Describe the purpose of the interview using up to 4000 characters.")
    get_specialization(specialization)
    person = people.person_for_account(db, recipient.id)
    if person is None:
        raise ValueError("Link this login to its person record in the existing RF-One directory first.")
    row = InterviewSession(id=str(uuid.uuid4()), requester_id=requester.id,
        recipient_id=recipient.id, person_id=person.id if person else None,
        purpose=purpose, specialization=specialization,
        status="REQUESTED", revision=0, transcript="[]", created_at=now())
    db.add(row)
    db.flush()
    return row


def request_for_person(db, requester, person_id, purpose):
    require_manager(db, requester)
    person = people.get_person(db, person_id)
    if person is None:
        raise ValueError("Select a person from the people directory.")
    recipient = people.delivery_account(db, person.id)
    if recipient is None:
        raise ValueError("Link an active RF-One account to this person before requesting an interview.")
    return request_interview(db, requester, recipient.id, purpose)


def interview_person(db, row):
    return people.get_person(db, row.person_id)


def pending(db, account):
    active(account)
    rows = list(db.scalars(select(InterviewSession).where(
        InterviewSession.recipient_id == account.id,
        InterviewSession.status != "COMPLETED").order_by(InterviewSession.created_at)))
    return [row for row in rows if recipient_matches(db, account, row)]


def recipient_matches(db, account, row):
    if row.recipient_id != account.id:
        return False
    try:
        current = people.person_for_account(db, account.id)
    except ValueError:
        return False
    subject = people.get_person(db, row.person_id)
    return bool(current and subject and current.id == subject.id)


def managed(db, account):
    """Every interview, for any account with the Interviews permission: the
    know-how belongs to the company, not to whoever happened to request it."""
    require_manager(db, account)
    return list(db.scalars(select(InterviewSession).order_by(InterviewSession.created_at.desc())))


def load(db, account, session_id, *, admin=False):
    active(account)
    row = db.get(InterviewSession, session_id)
    if admin:
        require_manager(db, account)
    if row is None or (not admin and not recipient_matches(db, account, row)):
        raise PermissionError("Interview unavailable.")
    return row


def delete_interview(db, account, session_id):
    """Remove one interview with its transcript and results (all held on the
    row). The person's append-only directory history keeps who deleted which
    interview and when, never its content."""
    require_manager(db, account)
    row = db.get(InterviewSession, session_id)
    if row is None:
        raise LookupError("Interview unavailable.")
    db.add(m.EmployeeDirectoryEvent(employee_id=row.person_id, account_id=account.id,
        action="INTERVIEW_DELETE", details=dict(interview_id=row.id, status=row.status,
            requester_id=row.requester_id, requested_at=row.created_at.isoformat())))
    db.delete(row)
    db.flush()


def _string(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ProviderError("The AI response is invalid. No changes were saved.")
    return value.strip()


def _complete_output(raw, messages):
    if not isinstance(raw, dict):
        raise ProviderError("Invalid AI results. Please try again.")
    summary = _string(raw.get("summary"), 16000)
    knowledge, questions = raw.get("knowledge"), raw.get("open_questions")
    if not isinstance(knowledge, list) or len(knowledge) > 50 or not isinstance(questions, list) or len(questions) > 30:
        raise ProviderError("Invalid AI results. Please try again.")
    verified = []
    for item in knowledge:
        if not isinstance(item, dict):
            raise ProviderError("Invalid AI results. Please try again.")
        text, quote = _string(item.get("text"), 4000), _string(item.get("quote"), 8000)
        index = item.get("message_index")
        if type(index) is not int or not 0 <= index < len(messages) or messages[index]["role"] != "user" or quote not in messages[index]["text"]:
            raise ProviderError("An AI quotation does not match the answers. Please try completing the interview again.")
        verified.append(dict(text=text, quote=quote, message_index=index))
    return dict(summary=summary, knowledge=verified,
        open_questions=[_string(q, 2000) for q in questions], validation="CANDIDATE")


def advance(db, account, row, expected_revision, action, text, provider, *, channel="text", consent=False):
    """Only an assigned active account can mutate; CAS protects concurrent tabs.

    Build/validate the entire turn before writing. No provider/tool can approve
    knowledge or create an operational side effect through this interface.
    Starting requires the participant's explicit consent, checked here so a
    request that skips the page's checkbox is still refused.
    """
    active(account)
    if not recipient_matches(db, account, row):
        raise PermissionError("Interview unavailable.")
    if row.revision != expected_revision or row.status == "COMPLETED":
        raise ConflictError("The interview has changed. Reload the page before continuing.")
    if action not in {"start", "answer", "complete"}:
        raise ValueError("Invalid operation.")
    if channel not in {"text", "voice"}:
        raise ValueError("Invalid channel.")
    if (action == "start") != (row.status == "REQUESTED"):
        raise ConflictError("This action is unavailable in the current state.")
    if action == "start" and consent is not True:
        raise ValueError("Tick \"I agree\" to start the interview.")
    messages = json.loads(row.transcript)
    if action == "answer":
        text = text.strip()
        if not text or len(text) > 8000:
            raise ValueError("Enter an answer using up to 8000 characters.")
        messages.append(dict(role="user", text=text, at=now().isoformat(), channel=channel))
    if action == "complete" and not any(msg["role"] == "user" for msg in messages):
        raise ValueError("Answer at least one question before completing the interview.")
    payload = dict(operation="complete" if action == "complete" else "question",
        purpose=row.purpose, specialization=get_specialization(row.specialization), transcript=messages)
    session_id, previous_status = row.id, row.status
    try:
        raw = provider(payload)
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError("The AI is unavailable. No changes were saved.") from exc
    values = dict(revision=expected_revision + 1)
    if action == "complete":
        values.update(status="COMPLETED", completed_at=now(),
            results=json.dumps(_complete_output(raw, messages), ensure_ascii=False))
    else:
        if not isinstance(raw, dict):
            raise ProviderError("Invalid AI response. Please try again.")
        question = _string(raw.get("question"), 4000)
        messages.append(dict(role="assistant", text=question, at=now().isoformat(), channel="ai"))
        values.update(status="IN_PROGRESS", transcript=json.dumps(messages, ensure_ascii=False))
        if action == "start":
            values.update(consent_given=True, consent_at=now())
    changed = db.execute(update(InterviewSession).where(
        InterviewSession.id == session_id, InterviewSession.revision == expected_revision,
        InterviewSession.status == previous_status).values(**values).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise ConflictError("Another request updated this interview. Reload the page.")
    db.expire(row)
