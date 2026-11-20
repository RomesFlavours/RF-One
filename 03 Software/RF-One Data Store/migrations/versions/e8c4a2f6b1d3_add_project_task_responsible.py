"""MyRF Project Management: a Responsible per Task, from the Project's list

Revision ID: e8c4a2f6b1d3
Revises: d2f6b9a3e7c1
Create Date: 2026-10-12

(`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md` §3, §7):

  * project_responsible          — id, project_id (required), name, name_key (trimmed, case-folded),
                                   unique (project_id, name_key), timestamps.
  * project_task.responsible_id  — nullable → project_responsible.id, indexed.

Additive only: no existing row is changed, every existing Task starts without a Responsible. Downgrade removes
the column and the table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e8c4a2f6b1d3'
down_revision: Union[str, Sequence[str], None] = 'd2f6b9a3e7c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_responsible",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", name="fk_project_responsible_project_id"),
                  nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_project_responsible_name_not_blank"),
        sa.UniqueConstraint("project_id", "name_key", name="uq_project_responsible_project_name_key"),
    )
    if op.get_bind().dialect.name == "sqlite":
        # A plain ADD COLUMN with its reference: rebuilding project_task (batch mode) could drop its CHECKs.
        op.execute("ALTER TABLE project_task ADD COLUMN responsible_id INTEGER "
                   "CONSTRAINT fk_project_task_responsible_id REFERENCES project_responsible (id)")
    else:
        op.add_column("project_task", sa.Column("responsible_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_project_task_responsible_id", "project_task", "project_responsible",
                              ["responsible_id"], ["id"])
    op.create_index("ix_project_task_responsible_id", "project_task", ["responsible_id"])


def downgrade() -> None:
    op.drop_index("ix_project_task_responsible_id", table_name="project_task")
    with op.batch_alter_table("project_task") as batch:
        if op.get_bind().dialect.name != "sqlite":
            batch.drop_constraint("fk_project_task_responsible_id", type_="foreignkey")
        batch.drop_column("responsible_id")
    op.drop_table("project_responsible")
