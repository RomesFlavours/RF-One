"""relax source identity nullability on Order/OrderItem/OrderFee/Payment/Refund
(RFONE_OPERATIONAL_DATA_MODEL_001)

Revision ID: b6d3f8a1c4e7
Revises: e2c7b4a9f1d6
Create Date: 2026-09-06 00:00:00.000000

Applies the schema's own already-documented "modeling principle F" ("every
canonical entity should have an RF-One primary key and optional source
references" — `DATABASE_SCHEMA.md`) consistently. `Merchant`, `Location`,
`Employee`, and `Shift` already follow it (`source_system_id`/`source_*_id`
nullable); `Order`, `OrderItem`, `OrderFee`, `Payment`, and `Refund` did not
— they required a source system and external id, which structurally
prevented a canonical operational record from ever being created natively
(e.g. by a future RF-One POS) without inventing a fake external identity.

This migration ONLY relaxes NOT NULL to NULL-allowed on already-existing
columns — no column is added, removed, renamed, or retyped, and no existing
row's data changes (every currently-ingested row already has real,
non-null values in these columns; relaxing a NOT NULL constraint can never
invalidate data that already satisfies it). The paired
`UniqueConstraint(source_system_id, source_*_id)` on each of these tables is
left exactly as-is: SQL/SQLite already treats NULL as distinct from any
other value (including another NULL) in a UNIQUE constraint, so two future
natively-created rows (both NULL/NULL) can coexist without colliding, while
Clover-sourced rows keep their existing collision protection unchanged —
the same behavior this schema already relies on elsewhere (e.g.
`IngestionRun.lock_key`).

Downgrade re-tightens to NOT NULL — safe only if no row has a NULL value in
these columns at the time of downgrade (true today; would fail if a native,
sourceless row had since been created, which is the expected, accepted
trade-off of un-doing this forward-looking relaxation).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6d3f8a1c4e7'
down_revision: Union[str, Sequence[str], None] = 'e2c7b4a9f1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_order_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_line_item_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('order_fees', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_payment_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_refund_id', existing_type=sa.String(length=128), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.alter_column('source_refund_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.alter_column('source_payment_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('order_fees', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.alter_column('source_line_item_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.alter_column('source_order_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)
