"""Pending Training invitations; no identity backfill or startup migration."""
from alembic import op
from rfone_data_store.training.enrollment import EnrollmentInvitation

revision = 't9d120261113'
down_revision = 't9c120261112'
branch_labels = None
depends_on = None


def upgrade():
    EnrollmentInvitation.__table__.create(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError('Retain invitation audit history; roll back application code only.')
