"""MyRF Project Management v1: chapters, tasks, task dependencies

Revision ID: e3a7c5f9b1d4
Revises: a1b5c3d7e9f2
Create Date: 2026-10-12

MyRF / Project Management v1 — additive, three new tables only
(`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`):

  * project_chapter          — Chapter (title, description, order).
  * project_task             — Task or child activity (parent_task_id), manual percentage 0–100, planned start,
                               planned days ≥ 1, actual days NULL or ≥ 0.
  * project_task_dependency  — prerequisite links (finish-to-start, informational), never self.

Chained after the head of this line of work (a1b5c3d7e9f2, Bank AI Rules). The Invoice Intake revision
(b3f9d2c6e4a1) exists only in the main worktree, uncommitted, on d8e2f5a9c3b7: it is neither modified nor required
here. When the two lines are merged, one merge revision joins their heads.

No existing table or row is changed. Downgrade drops the three tables.

Integration with main (BANK_AWS_001, 2026-10-12): on `main` the same schema is created by d2f6b9a3e7c1 (after the
Restaurant Wines revision), so a database that comes from `main` - production included - already holds these
tables when it reaches this revision. This revision therefore creates only what does not exist yet; on a database
where it ran first (the local working database) nothing changes. Never rerun on such a database: downgrade below
this revision drops the Project Management tables whoever created them.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e3a7c5f9b1d4'
down_revision: Union[str, Sequence[str], None] = 'a1b5c3d7e9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "project_chapter" in sa.inspect(op.get_bind()).get_table_names():
        return                     # created on main by d2f6b9a3e7c1 (see the docstring)
    op.create_table(
        "project_chapter",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_project_chapter_title_not_blank"),
    )
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_project_task_title_not_blank"),
        sa.CheckConstraint("percent_complete BETWEEN 0 AND 100", name="ck_project_task_percent_range"),
        sa.CheckConstraint("planned_duration_days >= 1", name="ck_project_task_planned_days_positive"),
        sa.CheckConstraint("actual_duration_days IS NULL OR actual_duration_days >= 0",
                           name="ck_project_task_actual_days_not_negative"),
        sa.CheckConstraint("parent_task_id IS NULL OR parent_task_id <> id", name="ck_project_task_not_own_parent"),
    )
    op.create_index("ix_project_task_chapter_id", "project_task", ["chapter_id"])
    op.create_index("ix_project_task_parent_task_id", "project_task", ["parent_task_id"])
    op.create_table(
        "project_task_dependency",
        sa.Column("predecessor_task_id", sa.Integer(), sa.ForeignKey("project_task.id"), primary_key=True),
        sa.Column("successor_task_id", sa.Integer(), sa.ForeignKey("project_task.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("predecessor_task_id <> successor_task_id", name="ck_project_task_dependency_not_self"),
    )
    op.create_index("ix_project_task_dependency_successor", "project_task_dependency", ["successor_task_id"])


def downgrade() -> None:
    op.drop_index("ix_project_task_dependency_successor", table_name="project_task_dependency")
    op.drop_table("project_task_dependency")
    op.drop_index("ix_project_task_parent_task_id", table_name="project_task")
    op.drop_index("ix_project_task_chapter_id", table_name="project_task")
    op.drop_table("project_task")
    op.drop_table("project_chapter")
