"""add orders.business_date

Revision ID: aa3edadc9816
Revises: 2b29002fe5c5
Create Date: 2026-09-08 22:41:48.456561

Adds the canonical Business Date foundation (Product Owner decision) —
`orders.business_date`, a nullable `Date` column. Owned by Sales/Order
(`01 Domains/Business Domain/Restaurant/Sales/Restaurant Sales Model.md`
§6a), computed once via `rfone_data_store/business_date.py` and persisted
here — never recomputed at read time, never versioned. Nullable because
every existing Order predates this capability; no broad backfill is
performed by this migration (see the module docstring for why a value is
never invented when required inputs are unresolvable).

A plain nullable column with no constraint — SQLite supports
`ALTER TABLE ... ADD COLUMN` for this natively, no batch mode needed.

Autogenerate also detected pre-existing, unrelated drift on Selection tables
(`applications`, `in_person_interview_plans`, `phone_interview_plans`) —
those are intentionally NOT included here; this migration only adds
`orders.business_date`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa3edadc9816'
down_revision: Union[str, Sequence[str], None] = '2b29002fe5c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column('business_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orders', 'business_date')
