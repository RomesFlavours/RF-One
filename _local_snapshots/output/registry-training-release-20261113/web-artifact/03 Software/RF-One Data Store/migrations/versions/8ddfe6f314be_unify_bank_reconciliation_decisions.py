"""unify bank reconciliation decisions

Revision ID: 8ddfe6f314be
Revises: 00e6783b630f
Create Date: 2026-09-16 16:34:59.111984

Canonical Financial Model Convergence — Phase 4B only (FINANCIAL_MODEL_
CONVERGENCE_001). Eliminates the dual-decision architecture confirmed by
the Phase 4B read-only analysis: `BankTransactionExplanation` becomes the
ONE canonical reconciliation decision/audit row per Product Owner
Decision 1.

- Creates `bank_transaction_reason_export_mappings` (Decision 4) — the
  Kermali accounting/export attributes (`food_cost`/`operative`/
  `deductible`/`what_label`) as a Reason-scoped mapping, never on Reason
  itself (Decision 3) and never a live field a decision row re-reads.
- Adds five immutable decision-snapshot columns to
  `bank_transaction_explanations` (Decision 8).
- Migrates existing legacy-generation rows deterministically ONLY
  (Decision 9): `name` is matched to an EXISTING `BankOccurrence` by
  exact `canonical_name` — never fabricated, since `BankOccurrenceType`
  is required and no type can be inferred from legacy data. No Reason is
  ever invented (the legacy generation never recorded one); every
  migrated decision is left `NEEDS_HUMAN_REVIEW` with every known legacy
  value preserved as a snapshot, never silently discarded.
- Backfills `financial_transactions.explanation_id` for any transaction
  that already had an Expert System decision row but no pointer yet
  (wiring only — no data invented).
- Retires the legacy catalog columns (`name`/`category`/`food_cost`/
  `operative`/`deductible`/`what_label`/`active`) and their unique
  constraint from `bank_transaction_explanations` only after every
  legacy-referenced value has been preserved as a snapshot (Decisions 1,
  2, 4, 5, 17). `category` (write-only, read nowhere per the Phase 4B
  analysis) is retired without migration, per Decision 5.

Does NOT touch `financial_accounts`, `normalized_financial_transactions`,
`payment_instrument_transactions`, `payment_instrument_transaction_
matches`, or any PayPal/matching schema.

Cross-dialect fix (AWS_RDS_ALEMBIC_RECONCILIATION_001): the Boolean column
defaults in `bank_transaction_reason_export_mappings` (upgrade) and in the
legacy-catalog-column recreation (downgrade) originally used SQLite-only
integer literals (`sa.text('0')`/`sa.text('1')`) — PostgreSQL rejects an
integer literal as the default for a `boolean` column outright (empirically
confirmed against the real RDS target). Changed to the `false`/`true` SQL
keyword form accepted by both SQLite and PostgreSQL, with no change to the
resulting stored value.

The data-migration steps use SQLite's `lastrowid` to correlate each newly
inserted canonical decision row back to its source transaction — the
same dialect assumption every Bank Reconciliation migration in this
phase chain has made; this migration is not portable to another dialect
without adaptation. It was tested only against disposable SQLite
databases and is not applied to any real/production database by this
task.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ddfe6f314be'
down_revision: Union[str, Sequence[str], None] = '00e6783b630f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    op.create_table(
        'bank_transaction_reason_export_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_transaction_reason_id', sa.Integer(), nullable=False),
        sa.Column('food_cost', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('operative', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deductible', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('what_label', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['bank_transaction_reason_id'], ['bank_transaction_reasons.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_transaction_reason_id', name='uq_btrem_reason_id'),
    )

    with op.batch_alter_table('bank_transaction_explanations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('occurrence_name_snapshot', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('food_cost_snapshot', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('operative_snapshot', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('deductible_snapshot', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('what_label_snapshot', sa.String(length=128), nullable=True))

    _migrate_legacy_explanations(conn)
    _backfill_missing_current_pointers(conn)

    with op.batch_alter_table('bank_transaction_explanations', schema=None) as batch_op:
        batch_op.drop_constraint('uq_bank_transaction_explanation_name', type_='unique')
        batch_op.drop_column('active')
        batch_op.drop_column('what_label')
        batch_op.drop_column('deductible')
        batch_op.drop_column('operative')
        batch_op.drop_column('food_cost')
        batch_op.drop_column('category')
        batch_op.drop_column('name')


def _migrate_legacy_explanations(conn) -> None:
    """Decisions 1/2/4/5/9/15: every FinancialTransaction whose
    `explanation_id` still points at a legacy catalog-generation row
    (`financial_transaction_id IS NULL`) gets ONE new canonical per-
    transaction decision row. `name` is matched to an EXISTING
    `BankOccurrence` by exact `canonical_name` only; if none matches,
    `occurrence_id` is left NULL rather than fabricating one (occurrence
    type cannot be inferred). No Reason is ever invented — the legacy
    generation never recorded one, so `transaction_reason_id` is always
    NULL here. `decision_source` is left NULL (neither an automated RULE
    match nor an actual HUMAN confirmation produced this row — it is a
    migration artifact) and `decision_status` is always
    `NEEDS_HUMAN_REVIEW`, so Kermali export continues to correctly
    require human completion of the Reason. Every known legacy value
    (`food_cost`/`operative`/`deductible`/`what_label`/`name`) is
    preserved verbatim as a snapshot — nothing already classified is
    silently lost."""
    rows = conn.execute(sa.text("""
        SELECT ft.id AS transaction_id, le.id AS legacy_id, le.name AS legacy_name,
               le.food_cost AS legacy_food_cost, le.operative AS legacy_operative,
               le.deductible AS legacy_deductible, le.what_label AS legacy_what_label
        FROM financial_transactions ft
        JOIN bank_transaction_explanations le ON le.id = ft.explanation_id
        WHERE le.financial_transaction_id IS NULL AND le.name IS NOT NULL
    """)).fetchall()

    for row in rows:
        occurrence_id = conn.execute(
            sa.text("SELECT id FROM bank_occurrences WHERE canonical_name = :name"),
            {"name": row.legacy_name},
        ).scalar()

        notes = (
            f"Migrated during Phase 4B canonical convergence from legacy Kermali "
            f"explanation id={row.legacy_id} (name={row.legacy_name!r}). "
            + ("Occurrence matched by exact canonical_name. "
               if occurrence_id is not None else
               "No matching BankOccurrence found by canonical_name — occurrence left "
               "for HUMAN review, never fabricated. ")
            + "No Reason could be determined from legacy data (none was ever recorded) "
            "— left for HUMAN review; legacy Food $/Oper/Deduct/What preserved as snapshot."
        )

        result = conn.execute(
            sa.text("""
                INSERT INTO bank_transaction_explanations (
                    financial_transaction_id, occurrence_id, transaction_reason_id,
                    recognition_rule_id, decision_source, decision_status, confidence,
                    explanation_notes, confirmed_by_account_id, confirmed_at,
                    occurrence_name_snapshot, food_cost_snapshot, operative_snapshot,
                    deductible_snapshot, what_label_snapshot, created_at, updated_at
                ) VALUES (
                    :financial_transaction_id, :occurrence_id, NULL,
                    NULL, NULL, 'NEEDS_HUMAN_REVIEW', NULL,
                    :notes, NULL, NULL,
                    :occurrence_name_snapshot, :food_cost_snapshot, :operative_snapshot,
                    :deductible_snapshot, :what_label_snapshot, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "financial_transaction_id": row.transaction_id,
                "occurrence_id": occurrence_id,
                "notes": notes,
                "occurrence_name_snapshot": row.legacy_name,
                "food_cost_snapshot": row.legacy_food_cost,
                "operative_snapshot": row.legacy_operative,
                "deductible_snapshot": row.legacy_deductible,
                "what_label_snapshot": row.legacy_what_label,
            },
        )
        new_id = result.lastrowid
        conn.execute(
            sa.text("UPDATE financial_transactions SET explanation_id = :new_id WHERE id = :txn_id"),
            {"new_id": new_id, "txn_id": row.transaction_id},
        )


def _backfill_missing_current_pointers(conn) -> None:
    """Decision 6: a transaction whose `explanation_id` is still NULL but
    which already has at least one Expert System decision row (created
    automatically by Phase 4's `deduce_for_transaction`, before this
    phase existed to keep the pointer in sync) gets `explanation_id`
    backfilled to the CURRENT such row (highest id) — purely wiring up
    the pointer this phase introduces; no data is invented."""
    conn.execute(sa.text("""
        UPDATE financial_transactions
        SET explanation_id = (
            SELECT bte.id FROM bank_transaction_explanations bte
            WHERE bte.financial_transaction_id = financial_transactions.id
            ORDER BY bte.id DESC LIMIT 1
        )
        WHERE explanation_id IS NULL
        AND EXISTS (
            SELECT 1 FROM bank_transaction_explanations bte2
            WHERE bte2.financial_transaction_id = financial_transactions.id
        )
    """))


def downgrade() -> None:
    """Downgrade schema.

    Structural reversal only — recreates the legacy catalog columns and
    drops the snapshot columns/export-mapping table. Does NOT attempt to
    reconstruct original standalone legacy catalog rows from snapshot
    data (which decision rows originated from a legacy migration vs. a
    genuine new decision is not recoverable), matching this migration
    chain's existing "no general historical versioning" scope."""
    with op.batch_alter_table('bank_transaction_explanations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('category', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('food_cost', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('operative', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('deductible', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('what_label', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
        batch_op.create_unique_constraint('uq_bank_transaction_explanation_name', ['name'])

        batch_op.drop_column('what_label_snapshot')
        batch_op.drop_column('deductible_snapshot')
        batch_op.drop_column('operative_snapshot')
        batch_op.drop_column('food_cost_snapshot')
        batch_op.drop_column('occurrence_name_snapshot')

    op.drop_table('bank_transaction_reason_export_mappings')
