"""add Clover acquisition job tracking to ingestion_runs (CLOVER_ACQUISITION_JOBS_001)

Revision ID: b8d4e2f7a1c9
Revises: e7b2c94d0f18
Create Date: 2026-09-26 00:00:00.000000

Additive, non-destructive. CLOVER_ACQUISITION_JOBS_001 moves every manual
Clover acquisition (Sync Now, Historical Backfill) out of the web request
into a separate process. `ingestion_runs` stays the ONE history of those
jobs — no second job table — and gains only what that history needs to be
readable and safe:

- `acquisition_mode`: BACKFILL / SYNC_NOW / LIVE_SYNC / CORRECTION as a
  column, instead of being parsed out of free-text `notes`. It is what
  "last successful synchronization" is computed from, so it must not
  depend on the wording of a note. Existing rows are filled from their
  `notes` ("... mode=<X> ..."); a row whose note carries no mode stays NULL.
- `queued_at`: when the job was accepted (status QUEUED). `started_at`
  then records when the separate process actually began running it.
- `heartbeat_at`: last sign of life from the process running the job. A
  long Historical Backfill is no longer bounded by a request timeout, so
  "RUNNING for more than N minutes" can no longer mean "dead" by itself.
- `orders_processed` / `payments_processed` / `shifts_processed`: the
  counts the job history shows. NULL for rows recorded before this change
  (their counts only ever existed inside `notes`, left untouched).
- `error_summary`: the safe error text of a FAILED run (or the per-record
  anomalies of a PARTIAL one), shown in the history.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4e2f7a1c9'
down_revision: Union[str, Sequence[str], None] = 'e7b2c94d0f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('acquisition_mode', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('orders_processed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('payments_processed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('shifts_processed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('error_summary', sa.Text(), nullable=True))

    # Deterministic fill of `acquisition_mode` from the notes every Clover
    # run has always carried ("CLOVER_ACQUISITION mode=BACKFILL location_id=
    # 1; ..."). Nothing else about an existing row changes.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, notes FROM ingestion_runs WHERE notes LIKE '%mode=%'")
    ).fetchall()
    for row_id, notes in rows:
        token = notes.split("mode=", 1)[1].split(" ", 1)[0].split(";", 1)[0].strip()
        if token:
            conn.execute(
                sa.text("UPDATE ingestion_runs SET acquisition_mode = :mode WHERE id = :id"),
                {"mode": token[:32], "id": row_id},
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.drop_column('error_summary')
        batch_op.drop_column('shifts_processed')
        batch_op.drop_column('payments_processed')
        batch_op.drop_column('orders_processed')
        batch_op.drop_column('heartbeat_at')
        batch_op.drop_column('queued_at')
        batch_op.drop_column('acquisition_mode')
