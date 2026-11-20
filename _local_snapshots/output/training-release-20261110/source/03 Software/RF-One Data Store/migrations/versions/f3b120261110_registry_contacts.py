"""Registry contact details for external RF1 accounts, not recovery channels."""
from alembic import op
import sqlalchemy as sa
revision='f3b120261110'
down_revision='k9a020261110'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('rfone_accounts',sa.Column('contact_email',sa.String(255),nullable=True))
    op.add_column('rfone_accounts',sa.Column('contact_phone',sa.String(64),nullable=True))

def downgrade():
    raise RuntimeError('Preserve Registry contacts; use the verified backup for recovery.')
