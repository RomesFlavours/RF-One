"""Shared Clover acquisition engine (CLOVER_ACQUISITION_ENGINE_001, Product Owner 2026-11-22).

Additive only — prepared locally, NOT applied on AWS:
- `operational_acquisition_schedules`: the ONE daily download time for every active Clover site,
  editable in Settings > Clover download. One row is seeded with the Product Owner's initial value:
  00:00, America/New_York.
- `operational_acquisition_requests`: one row per download of one site — SCHEDULED (the ordinary daily
  download, unique per site and date) and LIVE (only when an authorized RF-One function asks). Each row
  keeps its own outcome and, only when it ended COMPLETE, the period it covered; a running download
  carries its engine instance and lease (`claimed_by`, `lease_until`).
No existing row is changed or removed.

Release order: a1c220261121 (AWS) -> this revision (released before CLOVER_MULTISITE_001, which is re-parented after it). Independent of
REGISTRY_MULTISITE_001 (c7d820261122), which will be re-parented after this revision when it is released.
"""
from datetime import time

from alembic import op
import sqlalchemy as sa

revision = 'd2a120261122'
down_revision = 'a1c220261121'
branch_labels = None
depends_on = None


def upgrade() -> None:
    schedules = op.create_table(
        'operational_acquisition_schedules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_time', sa.Time(), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False),
        sa.Column('updated_by_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.bulk_insert(schedules, [{'id': 1, 'run_time': time(0, 0), 'timezone': 'America/New_York'}])
    op.create_table(
        'operational_acquisition_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('requested_by_application', sa.String(length=32), nullable=True),
        sa.Column('requested_by_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scheduled_local_date', sa.Date(), nullable=True),
        sa.Column('resources', sa.String(length=64), nullable=True),
        sa.Column('live_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('claimed_by', sa.String(length=64), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.Text(), nullable=True),
        sa.Column('coverage_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('coverage_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingestion_run_id', sa.Integer(), sa.ForeignKey('ingestion_runs.id'), nullable=True),
        sa.UniqueConstraint('location_id', 'kind', 'scheduled_local_date',
                            name='uq_operational_acquisition_request_schedule'),
        sa.CheckConstraint("kind IN ('SCHEDULED','LIVE')", name='ck_operational_acquisition_request_kind'),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETE','FAILED','ACTIVE','ENDED')",
                           name='ck_operational_acquisition_request_status'),
    )
    op.create_index('ix_operational_acquisition_request_location_status',
                    'operational_acquisition_requests', ['location_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_operational_acquisition_request_location_status',
                  table_name='operational_acquisition_requests')
    op.drop_table('operational_acquisition_requests')
    op.drop_table('operational_acquisition_schedules')
