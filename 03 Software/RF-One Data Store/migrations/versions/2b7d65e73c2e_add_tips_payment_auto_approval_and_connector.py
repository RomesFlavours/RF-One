"""add Tips payment auto-approval mode and connector selection (STEP 12B integration)

Revision ID: 2b7d65e73c2e
Revises: f5d11c7966be
Create Date: 2026-09-17 00:00:00.000000

STEP 12B integration note: the source branch's `1df5e09b3959` ("add
ingestion_runs.mode and Tips payment auto-approval mode",
TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001) bundled TWO unrelated
schema effects. This migration intentionally ports only the first, still
required, effect, and adds one further additive column authorized by the
STEP 12B Product Owner decision:

1. `tips_payment_schedule_configs.auto_approval_mode` (nullable String(24),
   CHECK IN ('WITH_APPROVAL', 'WITHOUT_APPROVAL') OR NULL, plus a second
   CHECK that it is only ever set when `mode='AUTOMATIC'`) — completes the
   three Tips payment modes the Product Owner already decided (MANUAL;
   AUTOMATIC WITH human Approve & Pay approval; AUTOMATIC WITHOUT approval,
   i.e. RF-One itself Approves & Pays under explicit Delegated Authority).
   `NULL` on an AUTOMATIC row means WITH_APPROVAL — the already-existing,
   already-tested behavior — so no existing AUTOMATIC configuration's
   behavior changes as a result of this migration; WITHOUT_APPROVAL must
   be chosen explicitly. Unchanged from the source revision.

2. `tips_payment_schedule_configs.connector_code` (nullable String(16), no
   CHECK) — NEW: which technical connector executes this Restaurant's Tips
   payments (`tips/payment_connector.py`'s registry). The Product Owner
   decision requires payment mode to be configurable and to identify the
   connector to invoke, with NO silent Mercury-only default — this column
   is that setting. `NULL` means "not configured," which `payment_
   connector.resolve_connector` treats as a fail-closed condition, never a
   Mercury fallback. Deliberately NO CHECK constraint whitelisting known
   codes here (unlike `ck_authority_grant_scope_type`'s bounded Core
   organizational vocabulary, widened by `f5d11c7966be`): the whole point
   of a connector REGISTRY (`payment_connector._CONNECTOR_FACTORIES`) is
   that a new connector is registered in code, not by a schema migration —
   coupling this column to a hardcoded DB whitelist would force a migration
   on every future connector addition/removal, exactly the rigidity the
   registry pattern exists to avoid. Validity is enforced at the two
   places that actually matter: `schedule_service.set_payment_schedule`
   (rejects a code not in the CURRENT, live registry when a config is
   written) and `resolve_connector` (fails closed at execution time,
   regardless of what is already persisted) — never a third, DB-level
   opinion that could drift from either.

EXCLUDED, deliberately, from this migration: `ingestion_runs.mode` and its
`ck_ingestion_run_mode` CHECK constraint. That effect existed only to
support `technical.connectors.clover.reconciliation_poller.py`'s own
Modification Cursor lookup — an independently-developed Correction/
Reconciliation mechanism that was NEVER integrated into main. Main's own
canonical mechanism (`technical.connectors.clover.correction_sync.py`,
`IngestionRun.resource_type`, `aa48187f696b`) already supersedes it
end-to-end (STEP 12A; see `PROJECT_STATE.md`'s own supersession note) — a
`mode` column serving only the superseded poller would be dead schema on
main from the moment this migration applied, and `reconciliation_poller.py`
itself is intentionally not ported by this integration (STEP 12B §7/§16).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b7d65e73c2e'
down_revision: Union[str, Sequence[str], None] = 'f5d11c7966be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tips_payment_schedule_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_approval_mode', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('connector_code', sa.String(length=16), nullable=True))
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
        batch_op.drop_column('connector_code')
        batch_op.drop_column('auto_approval_mode')
