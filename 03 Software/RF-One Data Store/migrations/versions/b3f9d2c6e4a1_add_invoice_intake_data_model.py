"""add Invoice Intake data model (line measures, sources, packaging, derived values)

Revision ID: b3f9d2c6e4a1
Revises: d8e2f5a9c3b7
Create Date: 2026-10-10 00:00:00.000000

"Invoice Intake data model" — see PURCHASING.md §13. Purely additive:

- `purchase_lines`: five nullable read-only measure columns (nominal piece
  content + unit, actual weight + unit, unit price basis). Existing rows
  keep NULL = "not read"; no existing value is touched.
- `purchasing_validation_log_entries`: three nullable columns for
  field-level uncertainty/conflict flags.
- new `purchase_document_sources`, `supplier_product_packagings`,
  `supplier_product_unit_conversions`, `purchased_line_derived_values`.

Charges are NOT a new table: they stay `purchase_lines` rows with
`line_type` SURCHARGE/DISCOUNT and a signed `source_amount_minor`, which
the existing non-goods allocation already reads.

Only `add_column` (no batch table rebuild) is used on existing tables, so
SQLite never recreates `purchase_lines` and its CheckConstraints.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f9d2c6e4a1'
down_revision: Union[str, Sequence[str], None] = 'd8e2f5a9c3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('purchase_lines', sa.Column('piece_content_value', sa.Numeric(12, 4), nullable=True))
    op.add_column('purchase_lines', sa.Column('piece_content_unit', sa.String(length=16), nullable=True))
    op.add_column('purchase_lines', sa.Column('actual_weight_value', sa.Numeric(12, 4), nullable=True))
    op.add_column('purchase_lines', sa.Column('actual_weight_unit', sa.String(length=16), nullable=True))
    op.add_column('purchase_lines', sa.Column('unit_price_basis', sa.String(length=16), nullable=True))

    op.add_column('purchasing_validation_log_entries', sa.Column('field_name', sa.String(length=64), nullable=True))
    op.add_column('purchasing_validation_log_entries', sa.Column('issue_type', sa.String(length=16), nullable=True))
    op.add_column('purchasing_validation_log_entries', sa.Column('observed_values', sa.JSON(), nullable=True))

    op.create_table(
        'purchase_document_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_document_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=True),
        sa.Column('storage_reference', sa.String(length=1024), nullable=True),
        sa.Column('channel', sa.String(length=32), nullable=True),
        sa.Column('acquisition_reference', sa.String(length=128), nullable=True),
        sa.Column('acquisition_status', sa.String(length=16), nullable=False),
        sa.Column('page_from', sa.Integer(), nullable=True),
        sa.Column('page_to', sa.Integer(), nullable=True),
        sa.Column('file_page_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(
            "acquisition_status IN ('RECEIVED', 'ACQUIRED', 'FAILED')",
            name='ck_purchase_document_sources_acquisition_status',
        ),
        sa.CheckConstraint(
            'page_from IS NULL OR page_to IS NULL OR page_from <= page_to',
            name='ck_purchase_document_sources_page_range',
        ),
        sa.ForeignKeyConstraint(['purchase_document_id'], ['purchase_documents.id'], name='fk_purchase_document_sources_purchase_document_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('purchase_document_id', 'sequence', name='uq_purchase_document_sources_document_sequence'),
    )
    op.create_index(op.f('ix_purchase_document_sources_purchase_document_id'), 'purchase_document_sources', ['purchase_document_id'], unique=False)
    op.create_index(op.f('ix_purchase_document_sources_content_hash'), 'purchase_document_sources', ['content_hash'], unique=False)

    op.create_table(
        'supplier_product_packagings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_product_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('package_unit', sa.String(length=16), nullable=True),
        sa.Column('pieces_per_package', sa.Integer(), nullable=True),
        sa.Column('piece_unit', sa.String(length=16), nullable=True),
        sa.Column('piece_content_value', sa.Numeric(12, 4), nullable=True),
        sa.Column('piece_content_unit', sa.String(length=16), nullable=True),
        sa.Column('sale_unit', sa.String(length=16), nullable=True),
        sa.Column('price_basis_unit', sa.String(length=16), nullable=True),
        sa.Column('is_variable_weight', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('origin', sa.String(length=16), nullable=False),
        sa.Column('source_purchase_line_id', sa.Integer(), nullable=True),
        sa.Column('confirmed_by', sa.String(length=255), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('superseded_by_packaging_id', sa.Integer(), nullable=True),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("status IN ('PROPOSED', 'ACTIVE', 'SUPERSEDED')", name='ck_supplier_product_packagings_status'),
        sa.CheckConstraint("origin IN ('INVOICE_READ', 'HUMAN')", name='ck_supplier_product_packagings_origin'),
        sa.CheckConstraint(
            "origin <> 'INVOICE_READ' OR source_purchase_line_id IS NOT NULL",
            name='ck_supplier_product_packagings_invoice_read_requires_line',
        ),
        sa.CheckConstraint(
            'pieces_per_package IS NULL OR pieces_per_package > 0',
            name='ck_supplier_product_packagings_pieces_positive',
        ),
        sa.ForeignKeyConstraint(['supplier_product_id'], ['supplier_products.id'], name='fk_supplier_product_packagings_supplier_product_id'),
        sa.ForeignKeyConstraint(['source_purchase_line_id'], ['purchase_lines.id'], name='fk_supplier_product_packagings_source_purchase_line_id'),
        sa.ForeignKeyConstraint(['superseded_by_packaging_id'], ['supplier_product_packagings.id'], name='fk_supplier_product_packagings_superseded_by_packaging_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_product_id', 'version', name='uq_supplier_product_packagings_product_version'),
    )
    op.create_index(op.f('ix_supplier_product_packagings_supplier_product_id'), 'supplier_product_packagings', ['supplier_product_id'], unique=False)

    op.create_table(
        'supplier_product_unit_conversions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('packaging_id', sa.Integer(), nullable=False),
        sa.Column('from_unit', sa.String(length=16), nullable=False),
        sa.Column('to_unit', sa.String(length=16), nullable=False),
        sa.Column('factor', sa.Numeric(18, 6), nullable=False),
        sa.Column('is_nominal', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('origin', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('factor > 0', name='ck_supplier_product_unit_conversions_factor_positive'),
        sa.CheckConstraint(
            "origin IN ('INVOICE_READ', 'HUMAN', 'CALCULATED')",
            name='ck_supplier_product_unit_conversions_origin',
        ),
        sa.ForeignKeyConstraint(['packaging_id'], ['supplier_product_packagings.id'], name='fk_supplier_product_unit_conversions_packaging_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('packaging_id', 'from_unit', 'to_unit', name='uq_supplier_product_unit_conversions_units'),
    )
    op.create_index(op.f('ix_supplier_product_unit_conversions_packaging_id'), 'supplier_product_unit_conversions', ['packaging_id'], unique=False)

    op.create_table(
        'purchased_line_derived_values',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_document_id', sa.Integer(), nullable=False),
        sa.Column('purchase_line_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.String(length=64), nullable=False),
        sa.Column('value_numeric', sa.Numeric(18, 6), nullable=True),
        sa.Column('value_text', sa.String(length=255), nullable=True),
        sa.Column('unit', sa.String(length=16), nullable=True),
        sa.Column('provenance', sa.String(length=16), nullable=False),
        sa.Column('packaging_id', sa.Integer(), nullable=True),
        sa.Column('calculation_formula', sa.Text(), nullable=True),
        sa.Column('calculation_inputs', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("provenance IN ('PRODUCT_CARD', 'CALCULATED')", name='ck_purchased_line_derived_values_provenance'),
        sa.CheckConstraint(
            "provenance <> 'PRODUCT_CARD' OR packaging_id IS NOT NULL",
            name='ck_purchased_line_derived_values_product_card_requires_packaging',
        ),
        sa.CheckConstraint(
            "provenance <> 'CALCULATED' OR (calculation_formula IS NOT NULL AND calculation_inputs IS NOT NULL)",
            name='ck_purchased_line_derived_values_calculated_requires_inputs',
        ),
        sa.CheckConstraint(
            "NOT (provenance = 'PRODUCT_CARD' AND field_name IN ('actual_weight', 'actual_weight_value'))",
            name='ck_purchased_line_derived_values_no_standard_actual_weight',
        ),
        sa.CheckConstraint(
            'value_numeric IS NOT NULL OR value_text IS NOT NULL',
            name='ck_purchased_line_derived_values_has_value',
        ),
        sa.ForeignKeyConstraint(['purchase_document_id'], ['purchase_documents.id'], name='fk_purchased_line_derived_values_purchase_document_id'),
        sa.ForeignKeyConstraint(['purchase_line_id'], ['purchase_lines.id'], name='fk_purchased_line_derived_values_purchase_line_id'),
        sa.ForeignKeyConstraint(['packaging_id'], ['supplier_product_packagings.id'], name='fk_purchased_line_derived_values_packaging_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_purchased_line_derived_values_purchase_document_id'), 'purchased_line_derived_values', ['purchase_document_id'], unique=False)
    op.create_index(op.f('ix_purchased_line_derived_values_purchase_line_id'), 'purchased_line_derived_values', ['purchase_line_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_purchased_line_derived_values_purchase_line_id'), table_name='purchased_line_derived_values')
    op.drop_index(op.f('ix_purchased_line_derived_values_purchase_document_id'), table_name='purchased_line_derived_values')
    op.drop_table('purchased_line_derived_values')
    op.drop_index(op.f('ix_supplier_product_unit_conversions_packaging_id'), table_name='supplier_product_unit_conversions')
    op.drop_table('supplier_product_unit_conversions')
    op.drop_index(op.f('ix_supplier_product_packagings_supplier_product_id'), table_name='supplier_product_packagings')
    op.drop_table('supplier_product_packagings')
    op.drop_index(op.f('ix_purchase_document_sources_content_hash'), table_name='purchase_document_sources')
    op.drop_index(op.f('ix_purchase_document_sources_purchase_document_id'), table_name='purchase_document_sources')
    op.drop_table('purchase_document_sources')

    with op.batch_alter_table('purchasing_validation_log_entries') as batch_op:
        batch_op.drop_column('observed_values')
        batch_op.drop_column('issue_type')
        batch_op.drop_column('field_name')
    with op.batch_alter_table('purchase_lines') as batch_op:
        batch_op.drop_column('unit_price_basis')
        batch_op.drop_column('actual_weight_unit')
        batch_op.drop_column('actual_weight_value')
        batch_op.drop_column('piece_content_unit')
        batch_op.drop_column('piece_content_value')
