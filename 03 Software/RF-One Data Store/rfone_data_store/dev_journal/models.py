"""Development Journal tables (`10 System/Development Journal/README.md`).

Kept in their own module, on the shared `Base`, rather than growing
`models.py` further.

- `DevJournalWork`         — one card: a change with a verifiable result.
- `DevJournalWorkChange`   — every phase or status change of a card (history).
- `DevJournalEntry`        — the chronological journal inside a card, in its
  CURRENT version; a RELEASE entry carries its own release fields.
- `DevJournalEntryVersion` — every earlier version of an entry, kept whole
  when its author corrects it, with who wrote that version and when.
- `DevJournalDocument`     — an uploaded file, attached to a card and,
  optionally, to one of its entries. Only metadata lives here; the bytes are
  in the persistent document store (`document_store.py`).
- `DevJournalEvent`        — the persistent event log future MyRF signals will
  read. Deliberately NO delivery column: delivery belongs to each recipient
  and will be modelled by MyRF itself; nothing here marks an event delivered.

Phase, status, entry type and release values are codes; the labels shown to
people live in `service.py`. Timestamps are written explicitly in UTC
(SQLite hands them back naive; RF-One treats naive as UTC).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rfone_data_store.models import Base

PHASES = ("STUDY", "SPECIFICATION", "DEVELOPMENT", "LOCAL_TEST", "READY_FOR_RELEASE", "RELEASED")
STATUSES = ("IN_PROGRESS", "WAITING", "BLOCKED", "COMPLETED", "CANCELLED")
ENTRY_TYPES = ("ANALYSIS", "DECISION", "ACTIVITY", "VERIFICATION", "PROBLEM", "RELEASE")
RELEASE_ENVIRONMENTS = ("TEST", "PRODUCTION")
RELEASE_OUTCOMES = ("SUCCEEDED", "FAILED")
CHANGE_FIELDS = ("PHASE", "STATUS")
EVENT_TYPES = (
    "WORK_CREATED", "ENTRY_ADDED", "ENTRY_EDITED", "DOCUMENT_UPLOADED", "PHASE_CHANGED", "STATUS_CHANGED",
    "RELEASE_RECORDED",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


# Shared by the current entry and its versions: the release fields exist
# exactly on RELEASE entries.
RELEASE_FIELDS_RULE = (
    "(entry_type = 'RELEASE' AND release_environment IS NOT NULL AND release_outcome IS NOT NULL) OR "
    "(entry_type <> 'RELEASE' AND release_environment IS NULL AND release_outcome IS NULL "
    "AND release_aws_service IS NULL AND release_version IS NULL AND release_post_deploy_check IS NULL)"
)


class DevJournalWork(Base):
    __tablename__ = "dev_journal_works"
    __table_args__ = (
        CheckConstraint(_in("phase", PHASES), name="ck_dev_journal_works_phase"),
        CheckConstraint(_in("status", STATUSES), name="ck_dev_journal_works_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # A Domain access code from RF-One Web's `domain_registry`, or SYSTEM for
    # "General / System". Validated by the service, not the database — the
    # same choice `RFOneAccountDomainAccess.domain_code` makes.
    domain_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class DevJournalWorkChange(Base):
    __tablename__ = "dev_journal_work_changes"
    __table_args__ = (CheckConstraint(_in("field", CHANGE_FIELDS), name="ck_dev_journal_work_changes_field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("dev_journal_works.id"), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(16), nullable=False)
    old_value: Mapped[str] = mapped_column(String(24), nullable=False)
    new_value: Mapped[str] = mapped_column(String(24), nullable=False)
    changed_by_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class _EntryContent:
    """The editable content of an entry — the same columns on the current
    entry and on each kept version."""

    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    ref_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ref_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ref_commit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ref_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_environment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    release_aws_service: Mapped[str | None] = mapped_column(String(200), nullable=True)
    release_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    release_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    release_post_deploy_check: Mapped[str | None] = mapped_column(Text, nullable=True)


ENTRY_CONTENT_FIELDS = (
    "phase", "entry_type", "body", "ref_link", "ref_branch", "ref_commit", "ref_command",
    "release_environment", "release_aws_service", "release_version", "release_outcome", "release_post_deploy_check",
)


def _content_checks(table: str) -> tuple:
    return (
        CheckConstraint(_in("phase", PHASES), name=f"ck_{table}_phase"),
        CheckConstraint(_in("entry_type", ENTRY_TYPES), name=f"ck_{table}_type"),
        CheckConstraint(RELEASE_FIELDS_RULE, name=f"ck_{table}_release_fields"),
        CheckConstraint("release_environment IS NULL OR " + _in("release_environment", RELEASE_ENVIRONMENTS),
                        name=f"ck_{table}_release_environment"),
        CheckConstraint("release_outcome IS NULL OR " + _in("release_outcome", RELEASE_OUTCOMES),
                        name=f"ck_{table}_release_outcome"),
    )


class DevJournalEntry(_EntryContent, Base):
    __tablename__ = "dev_journal_entries"
    __table_args__ = _content_checks("dev_journal_entries") + (
        CheckConstraint("version >= 1", name="ck_dev_journal_entries_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("dev_journal_works.id"), nullable=False, index=True)
    author_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The current version: 1 until the author corrects the entry. Earlier
    # versions are in `dev_journal_entry_versions`.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    edited_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DevJournalEntryVersion(_EntryContent, Base):
    """An earlier version of an entry, exactly as it read before a
    correction. `written_by`/`written_at` are who wrote THAT version and
    when (the original author and creation time for version 1, the editor
    and edit time afterwards); `superseded_at` is when it was replaced."""

    __tablename__ = "dev_journal_entry_versions"
    __table_args__ = _content_checks("dev_journal_entry_versions") + (
        UniqueConstraint("entry_id", "version", name="uq_dev_journal_entry_versions_entry_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("dev_journal_entries.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    written_by_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    written_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DevJournalDocument(Base):
    __tablename__ = "dev_journal_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("dev_journal_works.id"), nullable=False, index=True)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("dev_journal_entries.id"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DevJournalEvent(Base):
    __tablename__ = "dev_journal_events"
    __table_args__ = (CheckConstraint(_in("event_type", EVENT_TYPES), name="ck_dev_journal_events_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("dev_journal_works.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("dev_journal_entries.id"), nullable=True)
    # For ENTRY_EDITED: the earlier version that the edit replaced.
    entry_version_id: Mapped[int | None] = mapped_column(ForeignKey("dev_journal_entry_versions.id"), nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("dev_journal_documents.id"), nullable=True)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("dev_journal_work_changes.id"), nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
