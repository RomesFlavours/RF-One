"""MyRF Project Management: projects, chapters, tasks, prerequisites

Revision ID: d2f6b9a3e7c1
Revises: b6e4d2a8c1f9
Create Date: 2026-10-12

Project → Chapter → Task → child activity
(`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md` §7):

  * project                  — id, name (required), sort_order, timestamps.
  * project_chapter          — belongs to one project (project_id required).
  * project_task             — belongs to one chapter; a child activity has parent_task_id; manual percentage 0–100,
                               planned start, planned days ≥ 1, actual days NULL or ≥ 0. Its project is its chapter's.
  * project_task_dependency  — prerequisite links (finish-to-start, informational), never self.

The same schema was first built on the Bank line of work by e3a7c5f9b1d4 and f5b8d2a4c6e1. Those revisions are
applied to the local working database and are not rewritten; their parents are not on main. This revision therefore
creates only what is missing:

  * no table yet (production, a new database)  → creates the four tables;
  * tables present through both Bank-line revisions → changes nothing;
  * chapters present without project_id (e3a7c5f9b1d4 only) → adds projects as f5b8d2a4c6e1 does: one initial
    project "Progetto da rinominare" holding every existing chapter, created only when chapters exist.

No existing row is changed or removed. Downgrade drops the four tables.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2f6b9a3e7c1'
down_revision: Union[str, Sequence[str], None] = 'b6e4d2a8c1f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INITIAL_PROJECT_NAME = "Progetto da rinominare"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "project" not in existing:
        op.create_table(
            "project",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            *_timestamps(),
            sa.CheckConstraint("length(trim(name)) > 0", name="ck_project_name_not_blank"),
        )

    if "project_chapter" not in existing:
        op.create_table(
            "project_chapter",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", name="fk_project_chapter_project_id"),
                      nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            *_timestamps(),
            sa.CheckConstraint("length(trim(title)) > 0", name="ck_project_chapter_title_not_blank"),
        )
        op.create_index("ix_project_chapter_project_id", "project_chapter", ["project_id"])
    elif "project_id" not in {c["name"] for c in inspector.get_columns("project_chapter")}:
        # Chapters from e3a7c5f9b1d4 without f5b8d2a4c6e1: link them to one initial project, keeping every row.
        with op.batch_alter_table("project_chapter") as batch:
            batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        if bind.execute(sa.text("SELECT COUNT(*) FROM project_chapter")).scalar():
            bind.execute(sa.text("INSERT INTO project (name, sort_order) VALUES (:name, 1)"),
                         {"name": INITIAL_PROJECT_NAME})
            project_id = bind.execute(sa.text("SELECT MIN(id) FROM project WHERE name = :name"),
                                      {"name": INITIAL_PROJECT_NAME}).scalar()
            bind.execute(sa.text("UPDATE project_chapter SET project_id = :project_id"), {"project_id": project_id})
        with op.batch_alter_table("project_chapter") as batch:
            batch.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key("fk_project_chapter_project_id", "project", ["project_id"], ["id"])
            batch.create_index("ix_project_chapter_project_id", ["project_id"])

    if "project_task" not in existing:
        op.create_table(
            "project_task",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("project_chapter.id"), nullable=False),
            sa.Column("parent_task_id", sa.Integer(), sa.ForeignKey("project_task.id"), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("percent_complete", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("planned_start_date", sa.Date(), nullable=False),
            sa.Column("planned_duration_days", sa.Integer(), nullable=False),
            sa.Column("actual_duration_days", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            *_timestamps(),
            sa.CheckConstraint("length(trim(title)) > 0", name="ck_project_task_title_not_blank"),
            sa.CheckConstraint("percent_complete BETWEEN 0 AND 100", name="ck_project_task_percent_range"),
            sa.CheckConstraint("planned_duration_days >= 1", name="ck_project_task_planned_days_positive"),
            sa.CheckConstraint("actual_duration_days IS NULL OR actual_duration_days >= 0",
                               name="ck_project_task_actual_days_not_negative"),
            sa.CheckConstraint("parent_task_id IS NULL OR parent_task_id <> id",
                               name="ck_project_task_not_own_parent"),
        )
        op.create_index("ix_project_task_chapter_id", "project_task", ["chapter_id"])
        op.create_index("ix_project_task_parent_task_id", "project_task", ["parent_task_id"])

    if "project_task_dependency" not in existing:
        op.create_table(
            "project_task_dependency",
            sa.Column("predecessor_task_id", sa.Integer(), sa.ForeignKey("project_task.id"), primary_key=True),
            sa.Column("successor_task_id", sa.Integer(), sa.ForeignKey("project_task.id"), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("predecessor_task_id <> successor_task_id",
                               name="ck_project_task_dependency_not_self"),
        )
        op.create_index("ix_project_task_dependency_successor", "project_task_dependency", ["successor_task_id"])


def downgrade() -> None:
    op.drop_index("ix_project_task_dependency_successor", table_name="project_task_dependency")
    op.drop_table("project_task_dependency")
    op.drop_index("ix_project_task_parent_task_id", table_name="project_task")
    op.drop_index("ix_project_task_chapter_id", table_name="project_task")
    op.drop_table("project_task")
    op.drop_index("ix_project_chapter_project_id", table_name="project_chapter")
    op.drop_table("project_chapter")
    op.drop_table("project")
