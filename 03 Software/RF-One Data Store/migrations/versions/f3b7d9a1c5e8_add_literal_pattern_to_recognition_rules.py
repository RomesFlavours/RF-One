"""add the literal text of a WHO Rule made in the Rule modal

Revision ID: f3b7d9a1c5e8
Revises: e7a1c4b9d2f6
Create Date: 2026-10-08

BANK_WHO_RULE_CONDITIONS_001 (Product Owner authorization, 2026-10-08,
limited to `bank_recognition_rules`). ADDITIVE, no data change.

  * `bank_recognition_rules.literal_pattern` (TEXT, NULL): the text to match
    exactly as typed in the Rule modal. A rule that has it is matched
    literally (case and outer spaces ignored, nothing else); every existing
    rule keeps NULL and its normalized matching — none is converted.

Downgrade drops the column (natively, without rebuilding the table).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f3b7d9a1c5e8'
down_revision: Union[str, Sequence[str], None] = 'e7a1c4b9d2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Native ADD / DROP COLUMN on both dialects — never a batch rebuild (see
# e7a1c4b9d2f6): the table's DDL, constraints and data stay as they are.


def upgrade() -> None:
    op.add_column("bank_recognition_rules", sa.Column("literal_pattern", sa.Text(), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE bank_recognition_rules DROP COLUMN literal_pattern")
    else:
        op.drop_column("bank_recognition_rules", "literal_pattern")
