"""Record the participant's consent when an interview starts."""
from alembic import op
import sqlalchemy as sa

revision = 'e1b220261102'
down_revision = 'e0a120261101'
branch_labels = None
depends_on = None


def upgrade():
    # Additive. Existing rows read as "no consent recorded"; the previous image
    # keeps working because it never names these columns.
    op.add_column('interview_sessions', sa.Column('consent_given', sa.Boolean(),
        nullable=False, server_default=sa.false()))
    op.add_column('interview_sessions', sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('interview_sessions') as batch:
        batch.drop_column('consent_at')
        batch.drop_column('consent_given')
