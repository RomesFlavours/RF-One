"""add ingestion_runs.mode and Tips payment auto-approval mode
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001)

Revision ID: 1df5e09b3959
Revises: f5d11c7966be
Create Date: 2026-09-14 00:00:00.000000

Two small, additive, non-destructive schema changes for the same task:

1. `ingestion_runs.mode` (nullable String(16), CHECK IN ('BACKFILL',
   'LIVE_SYNC', 'RECONCILIATION') OR NULL) — a real, queryable column for
   the mode the free-text `notes` column already recorded as
   `"mode=..."`. This lets the new Correction/Reconciliation Poller
   (`technical/connectors/clover/reconciliation_poller.py`) find its own
   prior run (its Modification Cursor) without parsing free text and
   without conflating it with Live Sync's/Backfill's own `source_window_end`
   cursor lineage — CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §4's
   "two distinct cursors." Every pre-existing row gets `mode = NULL` (never
   guessed from its own `notes` text) — harmless, since only mode-specific
   cursor queries filter on this column, and older rows simply predate it.

2. `tips_payment_schedule_configs.auto_approval_mode` (nullable
   String(24), CHECK IN ('WITH_APPROVAL', 'WITHOUT_APPROVAL') OR NULL,
   plus a second CHECK that it is only ever set when `mode='AUTOMATIC'`) —
   completes the three Tips payment modes the Product Owner already decided
   (MANUAL; AUTOMATIC WITH human Approve & Pay approval; AUTOMATIC WITHOUT
   approval, i.e. RF-One itself Approves & Pays under explicit Delegated
   Authority). `NULL` on an AUTOMATIC row means WITH_APPROVAL — the
   already-existing, already-tested behavior (`tips/scheduler.py`'s
   `run_due_payment_cycle_starts`, which today only ever starts a cycle,
   never approves it) — so no existing AUTOMATIC configuration's behavior
   changes as a result of this migration; WITHOUT_APPROVAL must be chosen
   explicitly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1df5e09b3959'
down_revision: Union[str, Sequence[str], None] = 'f5d11c7966be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mode', sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            'ck_ingestion_run_mode',
            "mode IS NULL OR mode IN ('BACKFILL', 'LIVE_SYNC', 'RECONCILIATION')",
        )

    with op.batch_alter_table('tips_payment_schedule_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_approval_mode', sa.String(length=24), nullable=True))
        batch_op.create_check_constraint(
            'ck_tips_payment_schedule_auto_approval_mode',
            "auto_approval_mode IS NULL OR auto_approval_mode IN ('WITH_APPROVAL', 'WITHOUT_APPROVAL')",
        )
        batch_op.create_check_constraint(
            'ck_tips_payment_schedule_auto_approval_mode_requires_automatic',
            "mode = 'AUTOMATIC' OR auto_approval_mode IS NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tips_payment_schedule_configs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_tips_payment_schedule_auto_approval_mode_requires_automatic', type_='check')
        batch_op.drop_constraint('ck_tips_payment_schedule_auto_approval_mode', type_='check')
        batch_op.drop_column('auto_approval_mode')

    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_ingestion_run_mode', type_='check')
        batch_op.drop_column('mode')
