"""Development Journal rules (`10 System/Development Journal/README.md`).

Everything that decides what may be written lives here; RF-One Web's
`dev_journal_routes.py` only reads requests and renders. Every write also
records its `DevJournalEvent` in the same transaction, so the event log
future MyRF signals will read can never miss a change. Nothing here
delivers, sends or marks an event delivered.

Nothing changes a card on its own: a release entry — successful or failed —
never moves the phase or the status. Only a person editing the card does.
An entry can be corrected only by its author; every earlier version is kept.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from rfone_data_store import models as m
from rfone_data_store.dev_journal import models as dj

ACCESS_CODE = "DEV_JOURNAL"
GENERAL_DOMAIN_CODE = "SYSTEM"
GENERAL_DOMAIN_LABEL = "General / System"

PHASE_LABELS = {
    "STUDY": "Study", "SPECIFICATION": "Specification", "DEVELOPMENT": "Development",
    "LOCAL_TEST": "Local test", "READY_FOR_RELEASE": "Ready for release", "RELEASED": "Released",
}
STATUS_LABELS = {
    "IN_PROGRESS": "In progress", "WAITING": "Waiting", "BLOCKED": "Blocked",
    "COMPLETED": "Completed", "CANCELLED": "Cancelled",
}
CLOSED_STATUSES = frozenset({"COMPLETED", "CANCELLED"})
ENTRY_TYPE_LABELS = {
    "ANALYSIS": "Analysis", "DECISION": "Decision", "ACTIVITY": "Activity",
    "VERIFICATION": "Verification", "PROBLEM": "Problem", "RELEASE": "Release",
}
RELEASE_ENVIRONMENT_LABELS = {"TEST": "Test", "PRODUCTION": "Production"}
RELEASE_OUTCOME_LABELS = {"SUCCEEDED": "Succeeded", "FAILED": "Failed"}
EVENT_TYPE_LABELS = {
    "WORK_CREATED": "New work", "ENTRY_ADDED": "New entry", "ENTRY_EDITED": "Entry corrected",
    "DOCUMENT_UPLOADED": "Document uploaded", "PHASE_CHANGED": "Phase changed",
    "STATUS_CHANGED": "Status changed", "RELEASE_RECORDED": "Release recorded",
}

# Accepted documents: extension -> (served content type, signature check).
# The content type served back is always derived from the extension, never
# from what the browser declared.
_ZIP = (b"PK\x03\x04",)
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
ALLOWED_DOCUMENT_TYPES: dict[str, tuple[str, tuple[bytes, ...] | None]] = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", None),  # RIFF....WEBP, checked below
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", _ZIP),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", _ZIP),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", _ZIP),
    ".doc": ("application/msword", _OLE),
    ".xls": ("application/vnd.ms-excel", _OLE),
    ".ppt": ("application/vnd.ms-powerpoint", _OLE),
    ".txt": ("text/plain; charset=utf-8", None),
    ".md": ("text/markdown; charset=utf-8", None),
}
_TEXT_EXTENSIONS = frozenset({".txt", ".md"})
# Opened in the browser; everything else is downloaded.
INLINE_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".md"})
MAX_DOCUMENT_BYTES = int(float(os.environ.get("RFONE_DEV_JOURNAL_MAX_DOCUMENT_MB", "20")) * 1024 * 1024)
MAX_FILENAME_LENGTH = 200


class DevJournalError(ValueError):
    """A refused write, with a message meant for the person."""


class NotEntryAuthorError(DevJournalError):
    """Only the author of an entry may correct it."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def _clean(text: str | None, *, max_length: int | None = None, label: str = "") -> str | None:
    value = (text or "").strip()
    if max_length is not None and len(value) > max_length:
        raise DevJournalError(f"{label}: at most {max_length} characters.")
    return value or None


def _required(text: str | None, label: str, *, max_length: int | None = None) -> str:
    value = _clean(text, max_length=max_length, label=label)
    if not value:
        raise DevJournalError(f"{label} is required.")
    return value


def _choice(value: str | None, allowed, label: str) -> str:
    if value not in allowed:
        raise DevJournalError(f"{label} is not valid.")
    return value


# ---------------------------------------------------------------------------
# Who may use the journal / be responsible
# ---------------------------------------------------------------------------


def journal_accounts(db: Session) -> list[m.RFOneAccount]:
    """ACTIVE accounts holding the enabled DEV_JOURNAL access — the people
    who may be named responsible, and the future MyRF recipients."""
    return list(db.scalars(
        select(m.RFOneAccount)
        .join(m.RFOneAccountDomainAccess, m.RFOneAccountDomainAccess.account_id == m.RFOneAccount.id)
        .where(
            m.RFOneAccountDomainAccess.domain_code == ACCESS_CODE,
            m.RFOneAccountDomainAccess.enabled.is_(True),
            m.RFOneAccount.status == "ACTIVE",
        )
        .order_by(m.RFOneAccount.display_name)
    ))


def _check_responsible(db: Session, account_id: int | None, *, keep_current: int | None = None) -> int:
    if account_id is None:
        raise DevJournalError("Responsible is required.")
    if account_id == keep_current:
        return account_id  # unchanged: kept even if that person has since lost access
    if account_id not in {a.id for a in journal_accounts(db)}:
        raise DevJournalError("The responsible person must be a user with Development Journal access.")
    return account_id


def _event(db: Session, work: dj.DevJournalWork, event_type: str, actor_id: int, summary: str, *,
           entry_id=None, entry_version_id=None, document_id=None, change_id=None, at: datetime) -> None:
    db.add(dj.DevJournalEvent(
        work_id=work.id, event_type=event_type, actor_account_id=actor_id, entry_id=entry_id,
        entry_version_id=entry_version_id, document_id=document_id, change_id=change_id,
        summary=summary[:500], occurred_at=at,
    ))


def _touch(work: dj.DevJournalWork, actor_id: int, at: datetime) -> None:
    work.updated_at = at
    work.updated_by_account_id = actor_id


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


@dataclass
class WorkInput:
    title: str | None
    domain_code: str | None
    objective: str | None
    responsible_account_id: int | None
    phase: str | None
    status: str | None
    next_step: str | None


def _validated(db: Session, data: WorkInput, domain_codes, *, current: dj.DevJournalWork | None = None) -> dict:
    return {
        "title": _required(data.title, "Title", max_length=200),
        "domain_code": _choice(data.domain_code, domain_codes, "Domain"),
        "objective": _required(data.objective, "Objective"),
        "responsible_account_id": _check_responsible(
            db, data.responsible_account_id,
            keep_current=current.responsible_account_id if current is not None else None,
        ),
        "phase": _choice(data.phase, PHASE_LABELS, "Phase"),
        "status": _choice(data.status, STATUS_LABELS, "Status"),
        "next_step": _clean(data.next_step),
    }


def create_work(db: Session, data: WorkInput, *, actor_id: int, domain_codes) -> dj.DevJournalWork:
    values = _validated(db, data, domain_codes)
    now = utcnow()
    work = dj.DevJournalWork(**values, created_by_account_id=actor_id, created_at=now,
                             updated_by_account_id=actor_id, updated_at=now)
    db.add(work)
    db.flush()
    _event(db, work, "WORK_CREATED", actor_id, f"New work: {work.title}", at=now)
    return work


def _record_change(db, work, field: str, old: str, new: str, actor_id: int, at: datetime) -> None:
    change = dj.DevJournalWorkChange(work_id=work.id, field=field, old_value=old, new_value=new,
                                     changed_by_account_id=actor_id, changed_at=at)
    db.add(change)
    db.flush()
    labels = PHASE_LABELS if field == "PHASE" else STATUS_LABELS
    what = "Phase" if field == "PHASE" else "Status"
    _event(db, work, f"{field}_CHANGED", actor_id, f"{what}: {labels[old]} → {labels[new]}",
           change_id=change.id, at=at)


def update_work(db: Session, work: dj.DevJournalWork, data: WorkInput, *, actor_id: int, domain_codes) -> None:
    values = _validated(db, data, domain_codes, current=work)
    now = utcnow()
    if values["phase"] != work.phase:
        _record_change(db, work, "PHASE", work.phase, values["phase"], actor_id, now)
    if values["status"] != work.status:
        _record_change(db, work, "STATUS", work.status, values["status"], actor_id, now)
    for key, value in values.items():
        setattr(work, key, value)
    _touch(work, actor_id, now)


def reopen_work(db: Session, work: dj.DevJournalWork, *, actor_id: int) -> None:
    if work.status not in CLOSED_STATUSES:
        raise DevJournalError("This work is already open.")
    now = utcnow()
    _record_change(db, work, "STATUS", work.status, "IN_PROGRESS", actor_id, now)
    work.status = "IN_PROGRESS"
    _touch(work, actor_id, now)


@dataclass
class WorkFilters:
    domain_code: str | None = None
    phase: str | None = None
    status: str | None = None
    responsible_account_id: int | None = None


def list_works(db: Session, filters: WorkFilters) -> list[dj.DevJournalWork]:
    query = select(dj.DevJournalWork)
    if filters.domain_code:
        query = query.where(dj.DevJournalWork.domain_code == filters.domain_code)
    if filters.phase:
        query = query.where(dj.DevJournalWork.phase == filters.phase)
    if filters.status:
        query = query.where(dj.DevJournalWork.status == filters.status)
    if filters.responsible_account_id:
        query = query.where(dj.DevJournalWork.responsible_account_id == filters.responsible_account_id)
    return list(db.scalars(query.order_by(dj.DevJournalWork.updated_at.desc(), dj.DevJournalWork.id.desc())))


def get_work(db: Session, work_id: int) -> dj.DevJournalWork | None:
    return db.get(dj.DevJournalWork, work_id)


def list_changes(db: Session, work_id: int) -> list[dj.DevJournalWorkChange]:
    return list(db.scalars(select(dj.DevJournalWorkChange).where(dj.DevJournalWorkChange.work_id == work_id)
                           .order_by(dj.DevJournalWorkChange.changed_at, dj.DevJournalWorkChange.id)))


def list_entries(db: Session, work_id: int) -> list[dj.DevJournalEntry]:
    """Chronological: oldest first, as a journal is read."""
    return list(db.scalars(select(dj.DevJournalEntry).where(dj.DevJournalEntry.work_id == work_id)
                           .order_by(dj.DevJournalEntry.created_at, dj.DevJournalEntry.id)))


def get_entry(db: Session, work_id: int, entry_id: int) -> dj.DevJournalEntry | None:
    entry = db.get(dj.DevJournalEntry, entry_id)
    return entry if entry is not None and entry.work_id == work_id else None


def list_entry_versions(db: Session, entry_id: int) -> list[dj.DevJournalEntryVersion]:
    """Earlier versions, oldest first (the current one is the entry itself)."""
    return list(db.scalars(select(dj.DevJournalEntryVersion).where(dj.DevJournalEntryVersion.entry_id == entry_id)
                           .order_by(dj.DevJournalEntryVersion.version)))


def list_documents(db: Session, work_id: int) -> list[dj.DevJournalDocument]:
    return list(db.scalars(select(dj.DevJournalDocument).where(dj.DevJournalDocument.work_id == work_id)
                           .order_by(dj.DevJournalDocument.uploaded_at, dj.DevJournalDocument.id)))


def list_events(db: Session, work_id: int | None = None) -> list[dj.DevJournalEvent]:
    query = select(dj.DevJournalEvent)
    if work_id is not None:
        query = query.where(dj.DevJournalEvent.work_id == work_id)
    return list(db.scalars(query.order_by(dj.DevJournalEvent.occurred_at, dj.DevJournalEvent.id)))


# ---------------------------------------------------------------------------
# Journal entries
# ---------------------------------------------------------------------------


@dataclass
class EntryInput:
    phase: str | None
    entry_type: str | None
    body: str | None
    ref_link: str | None = None
    ref_branch: str | None = None
    ref_commit: str | None = None
    ref_command: str | None = None
    release_environment: str | None = None
    release_aws_service: str | None = None
    release_version: str | None = None
    release_outcome: str | None = None
    release_post_deploy_check: str | None = None


def _validated_entry(data: EntryInput) -> dict:
    entry_type = _choice(data.entry_type, ENTRY_TYPE_LABELS, "Type")
    link = _clean(data.ref_link, max_length=1000, label="Link")
    if link and not (link.startswith("https://") or link.startswith("http://")):
        raise DevJournalError("The link must start with https:// or http://.")
    values = {
        "phase": _choice(data.phase, PHASE_LABELS, "Phase"),
        "entry_type": entry_type,
        "body": _required(data.body, "Text"),
        "ref_link": link,
        "ref_branch": _clean(data.ref_branch, max_length=200, label="Branch"),
        "ref_commit": _clean(data.ref_commit, max_length=100, label="Commit"),
        "ref_command": _clean(data.ref_command),
        "release_environment": None, "release_aws_service": None, "release_version": None,
        "release_outcome": None, "release_post_deploy_check": None,
    }
    if entry_type == "RELEASE":
        values.update(
            release_environment=_choice(data.release_environment, RELEASE_ENVIRONMENT_LABELS, "Environment"),
            release_aws_service=_required(data.release_aws_service, "AWS service", max_length=200),
            release_version=_required(data.release_version, "Version or commit", max_length=200),
            release_outcome=_choice(data.release_outcome, RELEASE_OUTCOME_LABELS, "Outcome"),
            release_post_deploy_check=_clean(data.release_post_deploy_check),
        )
    return values


def validate_entry(data: EntryInput) -> None:
    """Check an entry before any of its files is stored."""
    _validated_entry(data)


def _release_summary(entry) -> str:
    return (f"Release {RELEASE_ENVIRONMENT_LABELS[entry.release_environment]} "
            f"{entry.release_aws_service} {entry.release_version}: "
            f"{RELEASE_OUTCOME_LABELS[entry.release_outcome]}")


def add_entry(db: Session, work: dj.DevJournalWork, data: EntryInput, *, actor_id: int) -> dj.DevJournalEntry:
    values = _validated_entry(data)
    now = utcnow()
    entry = dj.DevJournalEntry(work_id=work.id, author_account_id=actor_id, created_at=now, version=1, **values)
    db.add(entry)
    db.flush()
    if entry.entry_type == "RELEASE":
        # One event, the specific one: a release is announced as a release.
        _event(db, work, "RELEASE_RECORDED", actor_id, _release_summary(entry), entry_id=entry.id, at=now)
    else:
        _event(db, work, "ENTRY_ADDED", actor_id,
               f"{ENTRY_TYPE_LABELS[entry.entry_type]}: {entry.body.splitlines()[0][:200]}",
               entry_id=entry.id, at=now)
    _touch(work, actor_id, now)
    return entry


def edit_entry(db: Session, work: dj.DevJournalWork, entry: dj.DevJournalEntry, data: EntryInput, *,
               actor_id: int) -> dj.DevJournalEntryVersion | None:
    """Correct an entry. Only its author may; the version being replaced is
    kept whole. Returns that kept version, or None when nothing changed."""
    if entry.work_id != work.id:
        raise DevJournalError("This entry does not belong to this work.")
    if entry.author_account_id != actor_id:
        raise NotEntryAuthorError("Only the author of an entry can correct it.")
    values = _validated_entry(data)
    if all(getattr(entry, name) == values[name] for name in dj.ENTRY_CONTENT_FIELDS):
        return None
    now = utcnow()
    kept = dj.DevJournalEntryVersion(
        entry_id=entry.id, version=entry.version,
        written_by_account_id=entry.edited_by_account_id or entry.author_account_id,
        written_at=entry.edited_at or entry.created_at, superseded_at=now,
        **{name: getattr(entry, name) for name in dj.ENTRY_CONTENT_FIELDS},
    )
    db.add(kept)
    db.flush()
    for name, value in values.items():
        setattr(entry, name, value)
    entry.version += 1
    entry.edited_by_account_id = actor_id
    entry.edited_at = now
    _event(db, work, "ENTRY_EDITED", actor_id,
           f"Entry #{entry.id} corrected (version {entry.version}): "
           f"{ENTRY_TYPE_LABELS[entry.entry_type]}: {entry.body.splitlines()[0][:150]}",
           entry_id=entry.id, entry_version_id=kept.id, at=now)
    _touch(work, actor_id, now)
    return kept


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@dataclass
class CheckedDocument:
    original_filename: str
    extension: str
    content_type: str
    data: bytes


def _display_filename(raw: str | None) -> str:
    """The original name shown back to people: only its last path part,
    without control characters, length-bounded. Never used as a path."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>|*?:').strip().strip(".")
    if not name:
        raise DevJournalError("The file name is not valid.")
    if len(name) > MAX_FILENAME_LENGTH:
        stem, ext = os.path.splitext(name)
        name = stem[: MAX_FILENAME_LENGTH - len(ext)] + ext
    return name


def check_document(raw_filename: str | None, data: bytes) -> CheckedDocument:
    name = _display_filename(raw_filename)
    extension = os.path.splitext(name)[1].lower()
    if extension not in ALLOWED_DOCUMENT_TYPES:
        raise DevJournalError(
            f"“{name}”: file type not allowed. Allowed: PDF, images (PNG, JPG, GIF, WEBP), "
            "Office (DOC, DOCX, XLS, XLSX, PPT, PPTX), TXT and Markdown."
        )
    if not data:
        raise DevJournalError(f"“{name}”: the file is empty.")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DevJournalError(f"“{name}”: larger than the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB limit.")
    content_type, signatures = ALLOWED_DOCUMENT_TYPES[extension]
    if extension == ".webp":
        valid = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    elif extension in _TEXT_EXTENSIONS:
        try:
            data.decode("utf-8")
            valid = b"\x00" not in data
        except UnicodeDecodeError:
            valid = False
    else:
        valid = any(data.startswith(sig) for sig in signatures)
    if not valid:
        raise DevJournalError(f"“{name}”: the content does not match the file type.")
    return CheckedDocument(original_filename=name, extension=extension, content_type=content_type, data=data)


def add_document(db: Session, work: dj.DevJournalWork, document: CheckedDocument, store, *, actor_id: int,
                 entry: dj.DevJournalEntry | None = None) -> dj.DevJournalDocument:
    if entry is not None and entry.work_id != work.id:
        raise DevJournalError("This entry does not belong to this work.")
    storage_path = store.put(document.data)
    now = utcnow()
    row = dj.DevJournalDocument(
        work_id=work.id, entry_id=entry.id if entry is not None else None,
        original_filename=document.original_filename, content_type=document.content_type,
        size_bytes=len(document.data), sha256=hashlib.sha256(document.data).hexdigest(),
        storage_path=storage_path, uploaded_by_account_id=actor_id, uploaded_at=now,
    )
    db.add(row)
    db.flush()
    where = f" (entry #{entry.id})" if entry is not None else ""
    _event(db, work, "DOCUMENT_UPLOADED", actor_id, f"Document uploaded: {row.original_filename}{where}",
           entry_id=row.entry_id, document_id=row.id, at=now)
    _touch(work, actor_id, now)
    return row


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
