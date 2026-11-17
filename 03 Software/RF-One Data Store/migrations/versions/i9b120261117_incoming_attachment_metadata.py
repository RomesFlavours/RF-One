"""Attachment descriptors only; no payloads, AI or provider message modifications."""
from alembic import op
import sqlalchemy as sa

revision = 'i9b120261117'
down_revision = 'i9a120261117'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('email_arrivals', sa.Column('attachments', sa.JSON(), nullable=True))
    op.add_column('email_arrivals', sa.Column('attachment_error', sa.String(30), nullable=True))
    op.add_column('email_arrivals', sa.Column('attachments_checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('email_arrivals') as batch:
        batch.drop_column('attachments_checked_at')
        batch.drop_column('attachment_error')
        batch.drop_column('attachments')
