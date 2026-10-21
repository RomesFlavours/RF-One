"""Development Journal: cards, phase/status history, journal entries with
their kept earlier versions, documents and the MyRF-ready event log.

Additive only: six new tables, no change to any existing table or row.
Access is the existing `rfone_account_domain_access` row with domain_code
DEV_JOURNAL — nothing to migrate for it. See
`rfone_data_store/dev_journal/models.py` and
`10 System/Development Journal/README.md`.

Revision ID: c4e820261021
Revises: c8e4b2a6f0d1
"""

from alembic import op
import sqlalchemy as sa

revision = "c4e820261021"
down_revision = "c8e4b2a6f0d1"
branch_labels = None
depends_on = None

_PHASES = "('STUDY', 'SPECIFICATION', 'DEVELOPMENT', 'LOCAL_TEST', 'READY_FOR_RELEASE', 'RELEASED')"
_ENTRY_TYPES = "('ANALYSIS', 'DECISION', 'ACTIVITY', 'VERIFICATION', 'PROBLEM', 'RELEASE')"
_RELEASE_FIELDS = (
    "(entry_type = 'RELEASE' AND release_environment IS NOT NULL AND release_outcome IS NOT NULL) OR "
    "(entry_type <> 'RELEASE' AND release_environment IS NULL AND release_outcome IS NULL "
    "AND release_aws_service IS NULL AND release_version IS NULL AND release_post_deploy_check IS NULL)"
)


def _account_fk(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=nullable)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _entry_content(table: str) -> list:
    return [
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("ref_link", sa.String(1000), nullable=True),
        sa.Column("ref_branch", sa.String(200), nullable=True),
        sa.Column("ref_commit", sa.String(100), nullable=True),
        sa.Column("ref_command", sa.Text(), nullable=True),
        sa.Column("release_environment", sa.String(16), nullable=True),
        sa.Column("release_aws_service", sa.String(200), nullable=True),
        sa.Column("release_version", sa.String(200), nullable=True),
        sa.Column("release_outcome", sa.String(16), nullable=True),
        sa.Column("release_post_deploy_check", sa.Text(), nullable=True),
        sa.CheckConstraint(f"phase IN {_PHASES}", name=f"ck_{table}_phase"),
        sa.CheckConstraint(f"entry_type IN {_ENTRY_TYPES}", name=f"ck_{table}_type"),
        sa.CheckConstraint(_RELEASE_FIELDS, name=f"ck_{table}_release_fields"),
        sa.CheckConstraint("release_environment IS NULL OR release_environment IN ('TEST', 'PRODUCTION')",
                           name=f"ck_{table}_release_environment"),
        sa.CheckConstraint("release_outcome IS NULL OR release_outcome IN ('SUCCEEDED', 'FAILED')",
                           name=f"ck_{table}_release_outcome"),
    ]


def upgrade():
    op.create_table(
        "dev_journal_works",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("domain_code", sa.String(40), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        _account_fk("responsible_account_id"),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=True),
        _account_fk("created_by_account_id"),
        _ts("created_at"),
        _account_fk("updated_by_account_id"),
        _ts("updated_at"),
        sa.CheckConstraint(f"phase IN {_PHASES}", name="ck_dev_journal_works_phase"),
        sa.CheckConstraint("status IN ('IN_PROGRESS', 'WAITING', 'BLOCKED', 'COMPLETED', 'CANCELLED')",
                           name="ck_dev_journal_works_status"),
    )
    op.create_index("ix_dev_journal_works_domain_code", "dev_journal_works", ["domain_code"])
    op.create_index("ix_dev_journal_works_responsible_account_id", "dev_journal_works", ["responsible_account_id"])
    op.create_index("ix_dev_journal_works_updated_at", "dev_journal_works", ["updated_at"])

    op.create_table(
        "dev_journal_work_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_id", sa.Integer(), sa.ForeignKey("dev_journal_works.id"), nullable=False),
        sa.Column("field", sa.String(16), nullable=False),
        sa.Column("old_value", sa.String(24), nullable=False),
        sa.Column("new_value", sa.String(24), nullable=False),
        _account_fk("changed_by_account_id"),
        _ts("changed_at"),
        sa.CheckConstraint("field IN ('PHASE', 'STATUS')", name="ck_dev_journal_work_changes_field"),
    )
    op.create_index("ix_dev_journal_work_changes_work_id", "dev_journal_work_changes", ["work_id"])

    op.create_table(
        "dev_journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_id", sa.Integer(), sa.ForeignKey("dev_journal_works.id"), nullable=False),
        _account_fk("author_account_id"),
        _ts("created_at"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _account_fk("edited_by_account_id", nullable=True),
        _ts("edited_at", nullable=True),
        *_entry_content("dev_journal_entries"),
        sa.CheckConstraint("version >= 1", name="ck_dev_journal_entries_version"),
    )
    op.create_index("ix_dev_journal_entries_work_id", "dev_journal_entries", ["work_id"])

    op.create_table(
        "dev_journal_entry_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("dev_journal_entries.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        _account_fk("written_by_account_id"),
        _ts("written_at"),
        _ts("superseded_at"),
        *_entry_content("dev_journal_entry_versions"),
        sa.UniqueConstraint("entry_id", "version", name="uq_dev_journal_entry_versions_entry_version"),
    )
    op.create_index("ix_dev_journal_entry_versions_entry_id", "dev_journal_entry_versions", ["entry_id"])

    op.create_table(
        "dev_journal_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_id", sa.Integer(), sa.ForeignKey("dev_journal_works.id"), nullable=False),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("dev_journal_entries.id"), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        _account_fk("uploaded_by_account_id"),
        _ts("uploaded_at"),
    )
    op.create_index("ix_dev_journal_documents_work_id", "dev_journal_documents", ["work_id"])
    op.create_index("ix_dev_journal_documents_entry_id", "dev_journal_documents", ["entry_id"])

    op.create_table(
        "dev_journal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_id", sa.Integer(), sa.ForeignKey("dev_journal_works.id"), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        _account_fk("actor_account_id"),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("dev_journal_entries.id"), nullable=True),
        sa.Column("entry_version_id", sa.Integer(), sa.ForeignKey("dev_journal_entry_versions.id"), nullable=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("dev_journal_documents.id"), nullable=True),
        sa.Column("change_id", sa.Integer(), sa.ForeignKey("dev_journal_work_changes.id"), nullable=True),
        sa.Column("summary", sa.String(500), nullable=False),
        _ts("occurred_at"),
        sa.CheckConstraint(
            "event_type IN ('WORK_CREATED', 'ENTRY_ADDED', 'ENTRY_EDITED', 'DOCUMENT_UPLOADED', 'PHASE_CHANGED', "
            "'STATUS_CHANGED', 'RELEASE_RECORDED')",
            name="ck_dev_journal_events_type",
        ),
    )
    op.create_index("ix_dev_journal_events_work_id", "dev_journal_events", ["work_id"])
    op.create_index("ix_dev_journal_events_occurred_at", "dev_journal_events", ["occurred_at"])


def downgrade():
    op.drop_table("dev_journal_events")
    op.drop_table("dev_journal_documents")
    op.drop_table("dev_journal_entry_versions")
    op.drop_table("dev_journal_entries")
    op.drop_table("dev_journal_work_changes")
    op.drop_table("dev_journal_works")
