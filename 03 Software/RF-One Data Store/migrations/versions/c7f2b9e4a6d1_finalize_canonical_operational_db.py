"""finalize canonical operational DB — relax remaining source-identity
nullability + add missing detail-table unique constraints
(CANONICAL_OPERATIONAL_DB_FINALIZATION_001)

Revision ID: c7f2b9e4a6d1
Revises: b6d3f8a1c4e7
Create Date: 2026-09-06 00:00:00.000000

Completes the modeling principle F pass (RFONE_OPERATIONAL_DATA_MODEL_001
already applied it to Merchant/Location/Employee/Shift/Order/OrderItem/
OrderFee/Payment/Refund) on the remaining tables CANONICAL_OPERATIONAL_DB_
GAP_REVIEW_001 found still requiring an external source system for every
row: `Item`, `Category`, `ModifierGroup`, `Modifier`, `Tender`, `Device`,
`TaxRate`, `DiscountDefinition` (both `source_system_id` and their own
`source_*_id` relaxed to nullable), and `OrderItemModifier`,
`OrderItemTax`, `OrderDiscount`, `OrderItemDiscount` (`source_system_id`
only — their own `source_*_id` were already nullable). No column is added,
removed, renamed, or retyped, and no existing row's data changes — every
currently-ingested row already has real, non-null values in these columns.

Also adds the `UniqueConstraint`s CANONICAL_OPERATIONAL_DB_GAP_REVIEW_001
found missing entirely on `OrderItemModifier`, `OrderFee`, `OrderItemTax`,
`OrderDiscount`, `OrderItemDiscount` — previously these five tables relied
solely on `ingest.py`'s/`acquisition.py`'s own application-level SELECT-
then-write lookup for idempotency, with no database-level guarantee against
a true duplicate. Each new constraint matches the exact composite key the
existing ingestion lookup logic already uses (confirmed by inspection of
both `technical/connectors/clover/ingest.py` and `acquisition.py`), so no
ingestion behavior changes. A one-time duplicate spot-check against the
real `data/rfone.db` confirmed zero existing duplicate groups on any of the
five composite keys before this migration was written, so applying it is
expected to succeed against real data.

NULL-safety is unchanged from every prior migration in this family: SQL/
SQLite treats NULL as distinct from any other value (including another
NULL) in a UNIQUE constraint, so two future natively-created rows (both
NULL on the relevant source column) can coexist under any of these new
constraints without colliding, while a genuine duplicate external id pair
is still rejected exactly as before.

Downgrade re-tightens the relaxed columns to NOT NULL and drops the five
new unique constraints — safe only if no row has a NULL value in one of
the relaxed columns, or a real duplicate under one of the five new
constraints, at the time of downgrade (true today).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f2b9e4a6d1'
down_revision: Union[str, Sequence[str], None] = 'b6d3f8a1c4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('order_item_modifiers', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_unique_constraint(
            'uq_order_item_modifiers_order_item_id_source_modification_id',
            ['order_item_id', 'source_modification_id'],
        )

    with op.batch_alter_table('order_fees', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_order_fees_order_id_source_line_item_id', ['order_id', 'source_line_item_id'],
        )

    with op.batch_alter_table('order_item_taxes', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_unique_constraint(
            'uq_order_item_taxes_order_item_id_source_tax_reference',
            ['order_item_id', 'source_tax_reference'],
        )

    with op.batch_alter_table('order_discounts', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_unique_constraint(
            'uq_order_discounts_order_id_source_discount_id', ['order_id', 'source_discount_id'],
        )

    with op.batch_alter_table('order_item_discounts', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_unique_constraint(
            'uq_order_item_discounts_order_item_id_source_discount_id',
            ['order_item_id', 'source_discount_id'],
        )

    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_item_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_category_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('modifier_groups', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_modifier_group_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('modifiers', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_modifier_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('tenders', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_tender_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_device_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('tax_rates', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_tax_rate_id', existing_type=sa.String(length=128), nullable=True)

    with op.batch_alter_table('discount_definitions', schema=None) as batch_op:
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('source_discount_id', existing_type=sa.String(length=128), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('discount_definitions', schema=None) as batch_op:
        batch_op.alter_column('source_discount_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('tax_rates', schema=None) as batch_op:
        batch_op.alter_column('source_tax_rate_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.alter_column('source_device_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('tenders', schema=None) as batch_op:
        batch_op.alter_column('source_tender_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('modifiers', schema=None) as batch_op:
        batch_op.alter_column('source_modifier_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('modifier_groups', schema=None) as batch_op:
        batch_op.alter_column('source_modifier_group_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.alter_column('source_category_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.alter_column('source_item_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('order_item_discounts', schema=None) as batch_op:
        batch_op.drop_constraint(
            'uq_order_item_discounts_order_item_id_source_discount_id', type_='unique',
        )
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('order_discounts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_order_discounts_order_id_source_discount_id', type_='unique')
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('order_item_taxes', schema=None) as batch_op:
        batch_op.drop_constraint(
            'uq_order_item_taxes_order_item_id_source_tax_reference', type_='unique',
        )
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('order_fees', schema=None) as batch_op:
        batch_op.drop_constraint('uq_order_fees_order_id_source_line_item_id', type_='unique')

    with op.batch_alter_table('order_item_modifiers', schema=None) as batch_op:
        batch_op.drop_constraint(
            'uq_order_item_modifiers_order_item_id_source_modification_id', type_='unique',
        )
        batch_op.alter_column('source_system_id', existing_type=sa.Integer(), nullable=False)
