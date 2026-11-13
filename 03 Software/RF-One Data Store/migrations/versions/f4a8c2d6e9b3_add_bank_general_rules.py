"""add Bank General (structural) WHO rules and the Chase ACH rule

Revision ID: f4a8c2d6e9b3
Revises: e2c6a9f4b7d1
Create Date: 2026-10-05

BANK_GENERAL_RULES_001 — Product Owner approved. ADDITIVE.

  * NEW `bank_general_rules`: a level-1 (structural) rule says WHERE a family
    of bank descriptions carries the WHO — the text between two markers —
    so one rule yields many WHO candidates. It is a separate concept from
    `bank_recognition_rules` (level 2: fixed phrase -> fixed WHO). A
    candidate becomes a WHO only through the existing canonical resolution;
    a General Rule never creates a WHO and never names a WHY.
  * Seeds the first rule, "Chase ACH — ORIG CO NAME": between "ORIG CO NAME:"
    and "ORIG ID:", ACTIVE. Idempotent (by name). Seeding configures future
    imports only; nothing already imported is touched by this revision.

Downgrade drops the table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a8c2d6e9b3'
down_revision: Union[str, Sequence[str], None] = 'e2c6a9f4b7d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "bank_general_rules"
CHASE_RULE = {"name": "Chase ACH — ORIG CO NAME", "source_field": "DESCRIPTION",
              "start_marker": "ORIG CO NAME:", "end_marker": "ORIG ID:", "status": "ACTIVE"}


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_field", sa.String(length=16), nullable=False),
        sa.Column("start_marker", sa.String(length=80), nullable=False),
        sa.Column("end_marker", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_bank_general_rule_name"),
        sa.CheckConstraint("source_field IN ('DESCRIPTION')", name="ck_bank_general_rule_source_field"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_general_rule_status"),
    )
    bind = op.get_bind()
    exists = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE name = :name"),
                          {"name": CHASE_RULE["name"]}).scalar()
    if not exists:
        bind.execute(sa.text(
            f"INSERT INTO {TABLE} (name, source_field, start_marker, end_marker, status) "
            "VALUES (:name, :source_field, :start_marker, :end_marker, :status)"
        ), CHASE_RULE)


def downgrade() -> None:
    op.drop_table(TABLE)
