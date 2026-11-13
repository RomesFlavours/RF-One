"""add rfone_training_identity_links

Revision ID: 6a4816849735
Revises: 4674ce4a75c3
Create Date: 2026-09-11 09:00:00.000000

Adds the one persistent, univocal bridge between a general `RFOneAccount`
(RF-One Web's own login) and an existing `TrainingAccount` — the RF-One
Web ↔ Training single-login integration task. Both foreign keys are UNIQUE,
so an `RFOneAccount` can link to at most one `TrainingAccount` and vice
versa — no duplicate or silently-replaced link is representable.

Purely additive — no existing table (`rfone_accounts`,
`rfone_account_domain_access`, or any Training/Tips/Compensation table) is
altered, and no existing Training account, need, assignment, attempt, or
snapshot is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a4816849735'
down_revision: Union[str, Sequence[str], None] = '4674ce4a75c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rfone_training_identity_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('rfone_account_id', sa.Integer(), nullable=False),
        sa.Column('training_account_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['rfone_account_id'], ['rfone_accounts.id'], ),
        sa.ForeignKeyConstraint(['training_account_id'], ['training_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rfone_account_id'),
        sa.UniqueConstraint('training_account_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('rfone_training_identity_links')
