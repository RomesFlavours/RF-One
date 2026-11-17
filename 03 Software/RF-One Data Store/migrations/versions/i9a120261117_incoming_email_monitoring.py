"""Local-first incoming email monitoring, metadata only. Not applied to AWS."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
revision = 'i9a120261117'
down_revision = 'e9a120261117'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('email_mailboxes',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('owner_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('label', sa.String(120), nullable=False),
        sa.Column('address', sa.String(254), nullable=False),
        sa.Column('host', sa.String(253), nullable=False),
        sa.Column('username', sa.String(254), nullable=False),
        sa.Column('folder', sa.String(120), nullable=False),
        sa.Column('credential_ref', sa.String(80), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column('config_version', sa.Integer(), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('uidvalidity', sa.String(20), nullable=True),
        sa.Column('last_uid', sa.BigInteger(), nullable=False),
        sa.Column('next_check_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(40), nullable=True),
        sa.Column('lease_owner', sa.String(36), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('owner_account_id', 'host', 'username', 'folder'),
        sa.CheckConstraint('interval_seconds >= 60 AND interval_seconds <= 3600'))
    op.create_index('ix_email_mailboxes_next_check_at', 'email_mailboxes', ['next_check_at'])
    op.create_index('ix_email_mailboxes_owner_account_id', 'email_mailboxes', ['owner_account_id'])
    op.create_table('email_arrivals',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('mailbox_id', sa.String(36), sa.ForeignKey('email_mailboxes.id'), nullable=False),
        sa.Column('uidvalidity', sa.String(20), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('uid', sa.BigInteger(), nullable=False),
        sa.Column('sender', sa.String(1000), nullable=False),
        sa.Column('recipient', sa.String(1000), nullable=False),
        sa.Column('subject', sa.String(1000), nullable=False),
        sa.Column('message_id', sa.String(1000), nullable=True),
        sa.Column('message_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('mailbox_id', 'generation', 'uidvalidity', 'uid'))
    op.create_index('ix_email_arrivals_detected_at', 'email_arrivals', ['detected_at'])
    op.create_index('ix_email_arrivals_mailbox_id', 'email_arrivals', ['mailbox_id'])
    op.create_table('email_mailbox_checks',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('mailbox_id', sa.String(36), sa.ForeignKey('email_mailboxes.id'), nullable=False),
        sa.Column('lease_owner', sa.String(36), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(24), nullable=False),
        sa.Column('found', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(40), nullable=True))
    op.create_index('ix_email_mailbox_checks_mailbox_id', 'email_mailbox_checks', ['mailbox_id'])
    op.create_table('email_mailbox_audit',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('mailbox_id', sa.String(36), sa.ForeignKey('email_mailboxes.id'), nullable=False),
        sa.Column('actor_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_email_mailbox_audit_mailbox_id', 'email_mailbox_audit', ['mailbox_id'])
    stamp = datetime.now(timezone.utc)
    op.bulk_insert(sa.table('email_worker_state', sa.column('id', sa.Integer()),
        sa.column('lease_until', sa.DateTime(timezone=True)), sa.column('next_send_at', sa.DateTime(timezone=True)),
        sa.column('mode', sa.String(20))), [dict(id=2, lease_until=stamp, next_send_at=stamp, mode='STOPPED')])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM email_mailboxes')):
        raise RuntimeError('Preserve configured mailboxes and history; roll back the application only.')
    for name in ('email_mailbox_audit', 'email_mailbox_checks', 'email_arrivals', 'email_mailboxes'):
        op.drop_table(name)
    op.execute(sa.text('DELETE FROM email_worker_state WHERE id=2'))
