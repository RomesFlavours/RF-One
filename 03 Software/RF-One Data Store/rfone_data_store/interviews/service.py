"""Persistent, revision-checked interview engine with explicit participants."""
from datetime import datetime, timezone
import json
import unicodedata
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


def is_domain_admin(db, account):
    """Domain administrators of ORGANIZATION see and delete every interview;
    other accounts with the Interviews item only the ones they requested."""
    return permissions.account_is_domain_admin(db, account, "ORGANIZATION")


def may_manage(db, account, row):
    return row.requester_id == account.id or is_domain_admin(db, account)


def content_visible(account, row):
    """Answers and results of an interview without recorded consent (started
    before consent was asked) stay with the person who requested it until the
    participant agrees on their next answer."""
    return bool(row.consent_given) or row.requester_id == account.id


def consent_missing(row):
    return row.status != "REQUESTED" and not row.consent_given


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
    # The owner's login stays active after a dismissal; the person still may not be chosen.
    person = people.require_recipient(db, person.id)
    row = InterviewSession(id=str(uuid.uuid4()), requester_id=requester.id,
        recipient_id=recipient.id, person_id=person.id if person else None,
        purpose=purpose, specialization=specialization,
        status="REQUESTED", revision=0, transcript="[]", created_at=now())
    db.add(row)
    db.flush()
    return row


def request_for_person(db, requester, person_id, purpose):
    require_manager(db, requester)
    person = people.require_recipient(db, person_id)
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
    """Every interview for a Domain administrator of ORGANIZATION (the
    know-how belongs to the company); for any other account with the
    Interviews item, only the interviews it requested."""
    require_manager(db, account)
    query = select(InterviewSession).order_by(InterviewSession.created_at.desc())
    if not is_domain_admin(db, account):
        query = query.where(InterviewSession.requester_id == account.id)
    return list(db.scalars(query))


def load(db, account, session_id, *, admin=False):
    active(account)
    row = db.get(InterviewSession, session_id)
    if admin:
        require_manager(db, account)
        if row is None or not may_manage(db, account, row):
            raise PermissionError("Interview unavailable.")
    elif row is None or not recipient_matches(db, account, row):
        raise PermissionError("Interview unavailable.")
    return row


def delete_interview(db, account, session_id):
    """Remove one interview with its transcript and results (all held on the
    row). The person's append-only directory history keeps who deleted which
    interview and when, never its content. Domain administrators of
    ORGANIZATION only."""
    require_manager(db, account)
    if not is_domain_admin(db, account):
        raise PermissionError("Only Domain administrators of ORGANIZATION can delete interviews.")
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


# Typography the AI may change when it copies a quotation: curly and straight
# quotes and apostrophes, dash variants, the one-character ellipsis.
_QUOTE_FOLD = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'", "`": "'", "\u00b4": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"', "\u00ab": '"', "\u00bb": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u2026": "...",
})


# Shorter quotations ("yes", "the supplier") prove nothing about a claim.
MIN_QUOTE_WORDS, MIN_QUOTE_CHARACTERS = 3, 15


def _comparable_map(text):
    """Text as compared for quotations (same words, any typography, case or
    spacing) and, for each of its characters, the (start, end) of the
    original characters it came from. A base character and its combining
    marks are normalised together, so composed and decomposed accents match."""
    clusters, start = [], 0
    for position in range(1, len(text) + 1):
        if position == len(text) or not unicodedata.combining(text[position]):
            clusters.append((start, position))
            start = position
    chars, origin = [], []
    for begin, end in clusters:
        for char in unicodedata.normalize("NFKC", text[begin:end]).translate(_QUOTE_FOLD).casefold():
            if char.isspace():
                if not chars or chars[-1] == " ":
                    continue
                char = " "
            chars.append(char)
            origin.append((begin, end))
    while chars and chars[-1] == " ":
        chars.pop()
        origin.pop()
    return "".join(chars), origin


def _comparable(text):
    return _comparable_map(text)[0]


def _quote_source(quote, index, messages):
    """(index of the user answer containing `quote`, the matching words as the
    participant wrote them), or None. The AI's own message_index is tried
    first; any other answer is accepted when that index is wrong. Surrounding
    quote marks and end punctuation are ignored. A quotation needs at least
    MIN_QUOTE_WORDS words or MIN_QUOTE_CHARACTERS characters."""
    wanted = _comparable(quote).strip(" \"'.,;:!?")
    if not wanted or (len(wanted.split()) < MIN_QUOTE_WORDS and len(wanted) < MIN_QUOTE_CHARACTERS):
        return None
    candidates = ([index] if type(index) is int and 0 <= index < len(messages) else []) + list(range(len(messages)))
    for position in candidates:
        if messages[position]["role"] != "user":
            continue
        answer = messages[position]["text"]
        comparable, origin = _comparable_map(answer)
        found = comparable.find(wanted)
        if found >= 0:
            return position, answer[origin[found][0]:origin[found + len(wanted) - 1][1]]
    return None


def _complete_output(raw, messages):
    if not isinstance(raw, dict):
        raise ProviderError("Invalid AI results. Please try again.")
    summary = _string(raw.get("summary"), 16000)
    knowledge, questions = raw.get("knowledge"), raw.get("open_questions")
    if not isinstance(knowledge, list) or len(knowledge) > 50 or not isinstance(questions, list) or len(questions) > 30:
        raise ProviderError("Invalid AI results. Please try again.")
    verified, dropped = [], 0
    for item in knowledge:
        if not isinstance(item, dict):
            raise ProviderError("Invalid AI results. Please try again.")
        text, quote = _string(item.get("text"), 4000), _string(item.get("quote"), 8000)
        source = _quote_source(quote, item.get("message_index"), messages)
        if source is None:
            # Unsupported by the answers: left out, the rest of the results stand.
            dropped += 1
            continue
        # Kept in the participant's own words, not the AI's copy of them.
        index, quote = source
        verified.append(dict(text=text, quote=quote, message_index=index))
    return dict(summary=summary, knowledge=verified, dropped_unsupported=dropped,
        open_questions=[_string(q, 2000) for q in questions], validation="CANDIDATE")


def advance(db, account, row, expected_revision, action, text, provider, *, channel="text", consent=False):
    """Only an assigned active account can mutate; CAS protects concurrent tabs.

    Build/validate the entire turn before writing. No provider/tool can approve
    knowledge or create an operational side effect through this interface.
    Starting requires the participant's explicit consent, checked here so a
    request that skips the page's checkbox is still refused. An interview
    started before consent was asked needs the same consent on its next
    answer or completion, before anything reaches the AI.
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
    record_consent = not row.consent_given
    if record_consent and consent is not True:
        raise ValueError("Tick \"I agree\" to continue the interview.")
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
    if record_consent:
        values.update(consent_given=True, consent_at=now())
    changed = db.execute(update(InterviewSession).where(
        InterviewSession.id == session_id, InterviewSession.revision == expected_revision,
        InterviewSession.status == previous_status).values(**values).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise ConflictError("Another request updated this interview. Reload the page.")
    db.expire(row)
