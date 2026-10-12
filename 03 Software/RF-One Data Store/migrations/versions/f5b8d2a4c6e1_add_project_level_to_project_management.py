"""MyRF Project Management: the Project level above Chapters

Revision ID: f5b8d2a4c6e1
Revises: c3d9e1f5a7b2
Create Date: 2026-10-12

Project → Chapter → Task → child activity
(`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`):

  * project                     — new: id, name (required), sort_order, timestamps.
  * project_chapter.project_id  — new, required, → project. A Task's Project is its Chapter's Project: nothing is
                                  added to project_task.

Existing data is kept. If any Chapter exists, one initial Project named "Progetto da rinominare" is created and every
Chapter is linked to it; Tasks, child activities and prerequisites are untouched, so they all fall within that
Project. If no Chapter exists, no Project is created.

Chained after the current head of this worktree (c3d9e1f5a7b2, Bank AI Rules "Solo WHO").
Downgrade drops project_chapter.project_id and the project table (Projects are lost, Chapters are kept).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f5b8d2a4c6e1'
down_revision: Union[str, Sequence[str], None] = 'c3d9e1f5a7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INITIAL_PROJECT_NAME = "Progetto da rinominare"


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_project_name_not_blank"),
    )
    with op.batch_alter_table("project_chapter") as batch:
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM project_chapter")).scalar():
        bind.execute(sa.text("INSERT INTO project (name, sort_order) VALUES (:name, 1)"), {"name": INITIAL_PROJECT_NAME})
        project_id = bind.execute(sa.text("SELECT id FROM project WHERE name = :name"),
                                  {"name": INITIAL_PROJECT_NAME}).scalar()
        bind.execute(sa.text("UPDATE project_chapter SET project_id = :project_id"), {"project_id": project_id})

    with op.batch_alter_table("project_chapter") as batch:
        batch.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_project_chapter_project_id", "project", ["project_id"], ["id"])
        batch.create_index("ix_project_chapter_project_id", ["project_id"])


def downgrade() -> None:
    with op.batch_alter_table("project_chapter") as batch:
        batch.drop_index("ix_project_chapter_project_id")
        batch.drop_constraint("fk_project_chapter_project_id", type_="foreignkey")
        batch.drop_column("project_id")
    op.drop_table("project")
