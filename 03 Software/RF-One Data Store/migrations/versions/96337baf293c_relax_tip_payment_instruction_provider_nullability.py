"""relax tip_payment_instructions.provider nullability (baseline-closure)

Revision ID: 96337baf293c
Revises: 2b7d65e73c2e
Create Date: 2026-09-17 00:00:00.000000

STEP 12B/12C baseline-closure fix: `tip_payment_instructions.provider`
(`NOT NULL`, application-side `default="MERCURY"` in `models.py`, never a
DB-level `server_default`) previously meant every newly-created READY,
not-yet-submitted instruction was written with `provider='MERCURY'` even
when its Restaurant is configured for a different connector — misleading,
and inconsistent with `TipPaymentInstruction` staying provider-neutral
until a connector actually executes it (`01 Domains/Business Domain/
Restaurant/Tips/Tips Payment Execution.md`'s "Canonical payment-connector
decision").

This migration only relaxes the column to `NULL`-able. No existing row's
data is destructively altered — every already-submitted instruction keeps
whatever `provider` value it already has (in practice always `'MERCURY'`,
the only connector real payments have gone through to date); only NEW
instructions, created after this migration and this deployment's
`models.py` change, are inserted with `provider=NULL` until
`payment_instruction.submit_payment_instruction` sets it from the
resolved connector's own `connector_code` at actual submit time."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96337baf293c'
down_revision: Union[str, Sequence[str], None] = '2b7d65e73c2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tip_payment_instructions', schema=None) as batch_op:
        batch_op.alter_column('provider', existing_type=sa.String(length=16), nullable=True)


def downgrade() -> None:
    """Downgrade schema.

    Reverts the column to NOT NULL. Any row inserted as NULL while this
    migration was applied (a READY instruction that was never submitted)
    would violate the restored constraint — such a row must be resolved
    (submitted, so `provider` is set, or removed if it is genuinely
    abandoned) before downgrading, exactly like any other NOT-NULL
    tightening in this migration set.
    """
    with op.batch_alter_table('tip_payment_instructions', schema=None) as batch_op:
        batch_op.alter_column('provider', existing_type=sa.String(length=16), nullable=False)
