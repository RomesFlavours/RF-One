"""add Restaurant Wines: wine types, catalog, pricing settings, Wine lists

Revision ID: b6e4d2a8c1f9
Revises: d8e2f5a9c3b7
Create Date: 2026-10-08 00:00:00.000000

RESTAURANT_WINES_FIRST_RELEASE_001 — first release of the Restaurant Wines
module (see the "Restaurant — Wines" section of `models.py`).

Only new tables are created; no existing table is altered. The one pricing
configuration row is inserted with the parameters of `Wine.xlsb`
(A = 1.3, B = 900, G = 3.5). Wine types are NOT inserted here: they are
loaded by the repeatable `seed_restaurant_wine_types.py`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e4d2a8c1f9'
down_revision: Union[str, Sequence[str], None] = 'd8e2f5a9c3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps(*, updated: bool = True) -> list[sa.Column]:
    columns = [sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]
    if updated:
        columns.append(sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    return columns


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'restaurant_wine_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('standard_name', sa.String(length=120), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'restaurant_wine_type_names',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wine_type_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('name_key', sa.String(length=120), nullable=False),
        sa.Column('is_standard', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['wine_type_id'], ['restaurant_wine_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name_key', name='uq_restaurant_wine_type_names_name_key'),
    )
    op.create_index('ix_restaurant_wine_type_names_wine_type_id', 'restaurant_wine_type_names', ['wine_type_id'])

    op.create_table(
        'restaurant_wines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wine_type_id', sa.Integer(), nullable=False),
        sa.Column('producer', sa.String(length=160), nullable=False),
        sa.Column('label_name', sa.String(length=200), nullable=True),
        sa.Column('vintage_year', sa.Integer(), nullable=True),
        sa.Column('non_vintage', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('category', sa.String(length=16), nullable=False),
        sa.Column('style', sa.String(length=16), nullable=False),
        sa.Column('denomination', sa.String(length=80), nullable=True),
        sa.Column('region', sa.String(length=80), nullable=True),
        sa.Column('bottle_size_ml', sa.Integer(), server_default=sa.text('750'), nullable=False),
        sa.Column('supplier_name', sa.String(length=160), nullable=True),
        sa.Column('cost_usd', sa.Numeric(10, 2), nullable=True),
        sa.Column('cost_date', sa.Date(), nullable=True),
        sa.Column('availability', sa.String(length=16), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('identity_key', sa.String(length=600), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("category IN ('RED', 'WHITE', 'ROSE')", name='ck_restaurant_wines_category'),
        sa.CheckConstraint("style IN ('STILL', 'FRIZZANTE', 'SPARKLING')", name='ck_restaurant_wines_style'),
        sa.CheckConstraint(
            "availability IN ('AVAILABLE', 'INCOMING', 'UNAVAILABLE')", name='ck_restaurant_wines_availability',
        ),
        sa.CheckConstraint(
            '(non_vintage AND vintage_year IS NULL) OR (NOT non_vintage AND vintage_year IS NOT NULL)',
            name='ck_restaurant_wines_vintage',
        ),
        sa.CheckConstraint('bottle_size_ml > 0', name='ck_restaurant_wines_bottle_size'),
        sa.CheckConstraint('cost_usd IS NULL OR cost_usd >= 0', name='ck_restaurant_wines_cost'),
        sa.ForeignKeyConstraint(['wine_type_id'], ['restaurant_wine_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('identity_key', name='uq_restaurant_wines_identity_key'),
    )
    op.create_index('ix_restaurant_wines_wine_type_id', 'restaurant_wines', ['wine_type_id'])

    settings = op.create_table(
        'restaurant_wine_pricing_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('coefficient_a', sa.Numeric(12, 4), nullable=False),
        sa.Column('log_base_b', sa.Numeric(12, 4), nullable=False),
        sa.Column('glass_divisor_g', sa.Numeric(12, 4), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('coefficient_a > 0', name='ck_restaurant_wine_pricing_a'),
        sa.CheckConstraint('log_base_b > 1', name='ck_restaurant_wine_pricing_b'),
        sa.CheckConstraint('glass_divisor_g > 0', name='ck_restaurant_wine_pricing_g'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(settings, [{'id': 1, 'coefficient_a': 1.3, 'log_base_b': 900, 'glass_divisor_g': 3.5}])

    op.create_table(
        'restaurant_wine_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('legal_entity_id', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('copied_from_wine_list_id', sa.Integer(), nullable=True),
        sa.Column('created_by_account_id', sa.Integer(), nullable=True),
        *_timestamps(updated=False),
        sa.ForeignKeyConstraint(['legal_entity_id'], ['legal_entities.id']),
        sa.ForeignKeyConstraint(['copied_from_wine_list_id'], ['restaurant_wine_lists.id']),
        sa.ForeignKeyConstraint(['created_by_account_id'], ['rfone_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('legal_entity_id', 'effective_from', name='uq_restaurant_wine_lists_entity_date'),
    )
    op.create_index('ix_restaurant_wine_lists_legal_entity_id', 'restaurant_wine_lists', ['legal_entity_id'])

    op.create_table(
        'restaurant_wine_list_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wine_list_id', sa.Integer(), nullable=False),
        sa.Column('wine_id', sa.Integer(), nullable=False),
        sa.Column('cost_used', sa.Numeric(10, 2), nullable=True),
        sa.Column('value_factor', sa.Numeric(8, 4), nullable=False),
        sa.Column('sells_by_glass', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('coefficient_a', sa.Numeric(12, 4), nullable=False),
        sa.Column('log_base_b', sa.Numeric(12, 4), nullable=False),
        sa.Column('glass_divisor_g', sa.Numeric(12, 4), nullable=False),
        sa.Column('calculated_bottle_price', sa.Integer(), nullable=True),
        sa.Column('calculated_glass_price', sa.Integer(), nullable=True),
        sa.Column('applied_bottle_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('applied_glass_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('bottle_price_manual', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('glass_price_manual', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        *_timestamps(),
        sa.CheckConstraint('value_factor > 0', name='ck_restaurant_wine_list_items_value'),
        sa.CheckConstraint('cost_used IS NULL OR cost_used >= 0', name='ck_restaurant_wine_list_items_cost'),
        sa.ForeignKeyConstraint(['wine_list_id'], ['restaurant_wine_lists.id']),
        sa.ForeignKeyConstraint(['wine_id'], ['restaurant_wines.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wine_list_id', 'wine_id', name='uq_restaurant_wine_list_items_list_wine'),
    )
    op.create_index('ix_restaurant_wine_list_items_wine_list_id', 'restaurant_wine_list_items', ['wine_list_id'])
    op.create_index('ix_restaurant_wine_list_items_wine_id', 'restaurant_wine_list_items', ['wine_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_restaurant_wine_list_items_wine_id', table_name='restaurant_wine_list_items')
    op.drop_index('ix_restaurant_wine_list_items_wine_list_id', table_name='restaurant_wine_list_items')
    op.drop_table('restaurant_wine_list_items')
    op.drop_index('ix_restaurant_wine_lists_legal_entity_id', table_name='restaurant_wine_lists')
    op.drop_table('restaurant_wine_lists')
    op.drop_table('restaurant_wine_pricing_settings')
    op.drop_index('ix_restaurant_wines_wine_type_id', table_name='restaurant_wines')
    op.drop_table('restaurant_wines')
    op.drop_index('ix_restaurant_wine_type_names_wine_type_id', table_name='restaurant_wine_type_names')
    op.drop_table('restaurant_wine_type_names')
    op.drop_table('restaurant_wine_types')
