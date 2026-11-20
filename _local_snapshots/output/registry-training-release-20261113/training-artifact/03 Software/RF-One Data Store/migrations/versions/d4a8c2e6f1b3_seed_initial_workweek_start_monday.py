"""seed the initial Workweek start (Monday) (COMPENSATION_PERIOD_SUMMARY_001)

Revision ID: d4a8c2e6f1b3
Revises: c9e5a3b7d2f1
Create Date: 2026-09-28 12:00:00.000000

Data-only, additive. `workweek_definitions` has existed since the payroll
schema (Rome's Flavours' configuration was documented as Monday -> Sunday on
`WorkweekDefinition`) but no row was ever written, so the setting had no
value. The Product Owner set the initial value to Monday: every Restaurant
that has NO Workweek definition yet receives one, Monday, valid from
2000-01-01 (so it covers all history already acquired). A Restaurant that
already has any definition is left exactly as it is. Later changes are made
in RF-One Settings > Workweek, effective-dated, never by editing this row.

Downgrade removes only the rows this migration created (identified by
their note), never a definition a person recorded afterwards.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a8c2e6f1b3'
down_revision: Union[str, Sequence[str], None] = 'c9e5a3b7d2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_NOTE = "Initial value: Monday (COMPENSATION_PERIOD_SUMMARY_001, Product Owner 2026-09-28)"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO workweek_definitions (restaurant_id, start_weekday, valid_from, valid_to, notes) "
            "SELECT r.id, 0, :valid_from, NULL, :note FROM restaurants r "
            "WHERE NOT EXISTS (SELECT 1 FROM workweek_definitions w WHERE w.restaurant_id = r.id)"
        ).bindparams(
            sa.bindparam(
                "valid_from", datetime(2000, 1, 1, tzinfo=timezone.utc), type_=sa.DateTime(timezone=True),
            ),
            sa.bindparam("note", SEED_NOTE),
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text("DELETE FROM workweek_definitions WHERE notes = :note").bindparams(
            sa.bindparam("note", SEED_NOTE)
        )
    )
