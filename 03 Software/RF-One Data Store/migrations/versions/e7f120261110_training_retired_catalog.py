"""Retain withdrawn Training catalog entries and their historical references."""
from alembic import op
import sqlalchemy as sa

revision='e7f120261110'
down_revision='e8b920261110'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('training_retired_pills',
        sa.Column('pill_id',sa.Integer(),sa.ForeignKey('training_pills.id'),primary_key=True),
        sa.Column('retired_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))


def downgrade():
    op.drop_table('training_retired_pills')
