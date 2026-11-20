"""drop the hypothetical "would have been distributed" amount

AWS deploy task §6/§10.

The Product Owner's ruling: an amount describing what a rule WOULD have
moved, had an eligible recipient existed when none did, has no functional
use. When no Host was on shift at Order Open Time, no distribution
obligation arose at all — nothing was withheld, nothing is unresolved, and
the Service Owner simply earned 100% of that Order. The figure must be
absent from the operational result, from the report, and from storage.

Carrying it "for audit" invited exactly the reading it was meant to
prevent: that some amount is still owed to somebody.

Two columns go:

  * `tip_distribution_calculation_runs.retained_no_eligible_host_minor`
  * `tip_entitlements.retained_no_eligible_host_minor`

Both were introduced by `e8b3d74f02a1`, which is deliberately left exactly
as it was rather than edited. That revision has already been applied to a
local QA database holding real Rule Version configuration, and rewriting an
applied revision would mean a downgrade/upgrade cycle that rebuilds
`tip_distribution_rule_versions` and resets every version's status to
ACTIVE — silently discarding which versions are OLD and which are
CANCELLED. Dropping the columns in their own forward revision costs one
extra step in the history and risks nothing.

Nothing else is touched, and no row is deleted: only two columns that no
code reads any more.

Revision ID: f3c92a5e81d7
Revises: e8b3d74f02a1
Create Date: 2026-09-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3c92a5e81d7"
down_revision = "e8b3d74f02a1"
branch_labels = None
depends_on = None

COLUMN = "retained_no_eligible_host_minor"
TABLES = ("tip_distribution_calculation_runs", "tip_entitlements")


def upgrade() -> None:
    for table in TABLES:
        # SQLite cannot drop a column in place, so batch mode rebuilds the
        # table; on PostgreSQL this issues a plain ALTER ... DROP COLUMN.
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column(COLUMN)


def downgrade() -> None:
    # Restores the columns as nullable and EMPTY. The values are not
    # recovered, because they were never a source fact: each one was
    # derived from the allocation lines of a calculation, and a calculation
    # can always be re-derived. Inventing figures on the way back would be
    # worse than an honest NULL.
    for table in TABLES:
        op.add_column(table, sa.Column(COLUMN, sa.Integer(), nullable=True))
