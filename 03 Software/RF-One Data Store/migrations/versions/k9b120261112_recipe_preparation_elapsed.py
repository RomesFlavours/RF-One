"""Recipe preparation elapsed duration; existing person-minutes are retained."""
from alembic import op
import sqlalchemy as sa
revision='k9b120261112'
down_revision='t9a120261110'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('kitchen_recipes',sa.Column('elapsed_preparation_minutes',sa.Numeric(14,4),nullable=True))


def downgrade():
    op.drop_column('kitchen_recipes','elapsed_preparation_minutes')
