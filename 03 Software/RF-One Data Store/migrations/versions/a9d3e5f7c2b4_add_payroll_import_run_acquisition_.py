"""add payroll_import_runs.acquisition_method (TASK_PAYROLL_003)

Revision ID: a9d3e5f7c2b4
Revises: f2c8b6d4e1a7
Create Date: 2026-08-30 00:00:00.000001

One additive, non-destructive change: a nullable `acquisition_method`
column on `payroll_import_runs`, recording how each import's bytes actually
reached RF-One (`ADP_XLSX_FILE`, `ADP_SFTP_AES`, etc — free string,
`01 Domains/Administration/Payroll/Payroll Result Acquisition.md`).

No existing row is modified by this migration — every existing
`payroll_import_runs` row gets `acquisition_method = NULL` (unknown), which
is correct: RF-One never guesses how a historical import actually arrived.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9d3e5f7c2b4'
down_revision: Union[str, Sequence[str], None] = 'f2c8b6d4e1a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('payroll_import_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('acquisition_method', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payroll_import_runs', schema=None) as batch_op:
        batch_op.drop_column('acquisition_method')
