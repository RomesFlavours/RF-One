"""add supplier aliases table

Revision ID: baf1fe9ef53a
Revises: 09ed62634a09
Create Date: 2026-09-15 08:37:08.904882

Rechained from its original source-branch down_revision (f7174fa37e93) to
main's actual current head (09ed62634a09) — main gained the Organizational
Responsibility/Attention Runtime and Tips Payment Execution migrations
(merged at 09ed62634a09) after this branch diverged; keeping the original
down_revision would have created a second Alembic head instead of
extending the existing one linearly.

"Purchased Supplier Training — Phase 2" (canonical Supplier cleanup, §8/§9):
adds `supplier_aliases`, the minimum needed to represent "canonical
Supplier + known source aliases" (Purchased/README.md, "Supplier identity" —
"The original text/code as it appeared in the source must always remain
available as source provenance, even after resolution to a canonical
Supplier"). Purely additive — a brand new table, no existing column
changed, no existing row touched. `Supplier.name` itself is left mutable
(unchanged by this migration); correcting an existing dirty canonical name
in place and recording its prior spelling here as an alias is a data-level
operation performed by `rename_supplier_canonical()` in
`purchasing/repository.py`, not by this migration.

Autogenerate also detected pre-existing, unrelated drift on Selection
tables (`applications`, `in_person_interview_plans`,
`phone_interview_plans`) — those are intentionally NOT included here (same
convention as `2747004fc651_add_legal_entities_table_and_.py`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'baf1fe9ef53a'
down_revision: Union[str, Sequence[str], None] = '09ed62634a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'supplier_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('alias_name', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name='fk_supplier_aliases_supplier_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_id', 'alias_name', name='uq_supplier_aliases_supplier_id_alias_name'),
    )
    op.create_index(op.f('ix_supplier_aliases_supplier_id'), 'supplier_aliases', ['supplier_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_supplier_aliases_supplier_id'), table_name='supplier_aliases')
    op.drop_table('supplier_aliases')
