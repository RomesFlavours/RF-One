"""Add only enrollment invitations after the actual deployed Registry revision."""
from alembic import op
from rfone_data_store.training.enrollment import EnrollmentInvitation
revision = 't9e120261113'
down_revision = 'r9a120261113'
branch_labels = None
depends_on = None
def upgrade():
    EnrollmentInvitation.__table__.create(op.get_bind(), checkfirst=False)
def downgrade():
    raise RuntimeError('Retain invitation history; restore the prior application image.')
