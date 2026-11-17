"""Centralized persistent email queue, attempts, audit and worker lease."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = 'c7e5a3b9d201'
down_revision = 'b6e4d2a8c1f9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('email_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('domain', sa.String(80), nullable=False),
        sa.Column('recipient', sa.String(254), nullable=False),
        sa.Column('subject', sa.String(250), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('event', sa.String(200), nullable=False),
        sa.Column('dedup_key', sa.String(200), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error', sa.String(80)),
        sa.UniqueConstraint('domain', 'dedup_key'),
        sa.CheckConstraint("status in ('QUEUED','SENDING','RETRY','ACCEPTED','FAILED','UNCERTAIN','CANCELLED')"))
    for column in ('domain', 'status', 'available_at'):
        op.create_index('ix_email_requests_' + column, 'email_requests', [column])
    op.create_table('email_attempts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.String(36), sa.ForeignKey('email_requests.id'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('outcome', sa.String(20), nullable=False),
        sa.Column('error', sa.String(80)),
        sa.UniqueConstraint('request_id', 'number'))
    op.create_index('ix_email_attempts_request_id', 'email_attempts', ['request_id'])
    op.create_table('email_audit',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.String(36), sa.ForeignKey('email_requests.id'), nullable=False),
        sa.Column('actor_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_email_audit_request_id', 'email_audit', ['request_id'])
    op.create_table('email_worker_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('owner', sa.String(36)),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('heartbeat', sa.DateTime(timezone=True)),
        sa.Column('next_send_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('mode', sa.String(20), nullable=False))
    stamp = datetime.now(timezone.utc)
    op.bulk_insert(sa.table('email_worker_state', sa.column('id', sa.Integer()),
        sa.column('lease_until', sa.DateTime(timezone=True)), sa.column('next_send_at', sa.DateTime(timezone=True)),
        sa.column('mode', sa.String(20))), [dict(id=1, lease_until=stamp, next_send_at=stamp, mode='STOPPED')])


def downgrade():
    for table in ('email_audit', 'email_attempts', 'email_requests', 'email_worker_state'):
        op.drop_table(table)
