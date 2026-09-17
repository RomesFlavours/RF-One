"""converge bank recognition and export

Revision ID: 00e6783b630f
Revises: 5d199e89c719
Create Date: 2026-09-16 15:58:22.680841

Canonical Financial Model Convergence — Phase 4 only
(FINANCIAL_MODEL_CONVERGENCE_001). Ports the preserved in-progress Bank
Recognition Expert System (BANK_RECONCILIATION_EXPERT_SYSTEM_001) from
`feature/bank-reconciliation-mvp`: four new, additive tables
(`bank_occurrence_types`, `bank_occurrences`, `bank_transaction_reasons`,
`bank_recognition_rules`) plus the new `bank_transaction_explanations`
table (both the legacy V1 catalog-style shape and the Expert System's
per-decision shape, in one additive table exactly as on the source
branch). `financial_transactions.explanation_id` (omitted in Phase 2,
since this table did not yet exist) is added as a proper FK now that
`bank_transaction_explanations` exists.

Canonical adaptation only: `BankRecognitionRule.financial_account_id` ->
`payment_instrument_id`; `BankTransactionExplanation.normalized_
financial_transaction_id` -> `financial_transaction_id`, retargeted to
`financial_transactions.id`. No `financial_accounts`, `normalized_
financial_transactions`, `payment_instrument_transactions`, or
`payment_instrument_transaction_matches` table is created here. No data
is migrated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00e6783b630f'
down_revision: Union[str, Sequence[str], None] = '5d199e89c719'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bank_occurrence_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_bank_occurrence_type_code'),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_occurrence_type_status'),
    )

    op.create_table(
        'bank_transaction_reasons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_bank_transaction_reason_code'),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_transaction_reason_status'),
    )

    op.create_table(
        'bank_occurrences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('canonical_name', sa.String(length=255), nullable=False),
        sa.Column('occurrence_type_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('optional_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['occurrence_type_id'], ['bank_occurrence_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_name', name='uq_bank_occurrence_canonical_name'),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_occurrence_status'),
    )
    op.create_index('ix_bank_occurrences_occurrence_type_id', 'bank_occurrences', ['occurrence_type_id'])

    op.create_table(
        'bank_recognition_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_type', sa.String(length=32), nullable=False),
        sa.Column('normalized_pattern', sa.Text(), nullable=False),
        sa.Column('payment_instrument_id', sa.Integer(), nullable=True),
        sa.Column('direction', sa.String(length=8), nullable=True),
        sa.Column('occurrence_id', sa.Integer(), nullable=False),
        sa.Column('transaction_reason_id', sa.Integer(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('auto_apply_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('human_confirmations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('human_contradictions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_from_transaction_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['payment_instrument_id'], ['payment_instruments.id']),
        sa.ForeignKeyConstraint(['occurrence_id'], ['bank_occurrences.id']),
        sa.ForeignKeyConstraint(['transaction_reason_id'], ['bank_transaction_reasons.id']),
        sa.ForeignKeyConstraint(['created_from_transaction_id'], ['financial_transactions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "match_type IN ('EXACT_NORMALIZED_DESCRIPTION', 'CONTAINS_TEXT', 'PREFIX')",
            name='ck_bank_recognition_rule_match_type',
        ),
        sa.CheckConstraint("direction IS NULL OR direction IN ('DEBIT', 'CREDIT')", name='ck_bank_recognition_rule_direction'),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'NEEDS_REVIEW')", name='ck_bank_recognition_rule_status'),
    )
    op.create_index('ix_bank_recognition_rule_pattern', 'bank_recognition_rules', ['normalized_pattern'])
    op.create_index('ix_bank_recognition_rules_occurrence_id', 'bank_recognition_rules', ['occurrence_id'])

    op.create_table(
        'bank_transaction_explanations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=128), nullable=True),
        sa.Column('food_cost', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('operative', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('deductible', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('what_label', sa.String(length=128), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
        sa.Column('occurrence_id', sa.Integer(), nullable=True),
        sa.Column('transaction_reason_id', sa.Integer(), nullable=True),
        sa.Column('recognition_rule_id', sa.Integer(), nullable=True),
        sa.Column('decision_source', sa.String(length=8), nullable=True),
        sa.Column('decision_status', sa.String(length=24), nullable=True),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('explanation_notes', sa.Text(), nullable=True),
        sa.Column('confirmed_by_account_id', sa.Integer(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['financial_transaction_id'], ['financial_transactions.id']),
        sa.ForeignKeyConstraint(['occurrence_id'], ['bank_occurrences.id']),
        sa.ForeignKeyConstraint(['transaction_reason_id'], ['bank_transaction_reasons.id']),
        sa.ForeignKeyConstraint(['recognition_rule_id'], ['bank_recognition_rules.id']),
        sa.ForeignKeyConstraint(['confirmed_by_account_id'], ['rfone_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_bank_transaction_explanation_name'),
        sa.CheckConstraint(
            "decision_source IS NULL OR decision_source IN ('HUMAN', 'RULE')",
            name='ck_bank_transaction_explanation_decision_source',
        ),
        sa.CheckConstraint(
            "decision_status IS NULL OR decision_status IN "
            "('SUGGESTED', 'AUTO_APPLIED', 'HUMAN_CONFIRMED', 'HUMAN_OVERRIDDEN', 'NEEDS_HUMAN_REVIEW')",
            name='ck_bank_transaction_explanation_decision_status',
        ),
    )
    op.create_index(
        'ix_bank_transaction_explanations_financial_transaction_id',
        'bank_transaction_explanations', ['financial_transaction_id'],
    )

    with op.batch_alter_table('financial_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('explanation_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_financial_transactions_explanation', 'bank_transaction_explanations', ['explanation_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('financial_transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_financial_transactions_explanation', type_='foreignkey')
        batch_op.drop_column('explanation_id')

    op.drop_index(
        'ix_bank_transaction_explanations_financial_transaction_id', table_name='bank_transaction_explanations',
    )
    op.drop_table('bank_transaction_explanations')

    op.drop_index('ix_bank_recognition_rules_occurrence_id', table_name='bank_recognition_rules')
    op.drop_index('ix_bank_recognition_rule_pattern', table_name='bank_recognition_rules')
    op.drop_table('bank_recognition_rules')

    op.drop_index('ix_bank_occurrences_occurrence_type_id', table_name='bank_occurrences')
    op.drop_table('bank_occurrences')

    op.drop_table('bank_transaction_reasons')
    op.drop_table('bank_occurrence_types')
