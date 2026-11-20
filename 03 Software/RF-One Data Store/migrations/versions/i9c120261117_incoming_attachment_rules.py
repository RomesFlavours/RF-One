"""Per-mailbox attachment rules: configuration only, PDF-only, always inactive. Local only; not applied to AWS."""
from alembic import op
import sqlalchemy as sa

revision = 'i9c120261117'
down_revision = 'i9b120261117'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('email_attachment_rules',
        sa.Column('mailbox_id', sa.String(36), sa.ForeignKey('email_mailboxes.id'), primary_key=True, nullable=False),
        sa.Column('file_type', sa.String(10), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('selection', sa.Text(), nullable=False),
        sa.Column('conditions', sa.Text(), nullable=False),
        sa.Column('actions', sa.Text(), nullable=False),
        sa.Column('missing', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_by_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("file_type = 'PDF'", name='ck_email_attachment_rules_pdf_only'),
        sa.CheckConstraint('NOT active', name='ck_email_attachment_rules_inactive'))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM email_attachment_rules')):
        raise RuntimeError('Preserve saved attachment rules; roll back the application only.')
    op.drop_table('email_attachment_rules')
