"""Keep source profile availability separate from employment status."""
from alembic import op
import sqlalchemy as sa
revision = 'd120261019ee'
down_revision = 'b9e620261019'
branch_labels = None
depends_on = None

def upgrade():
    columns={c['name'] for c in sa.inspect(op.get_bind()).get_columns('employees')}
    if 'source_available' not in columns:
        op.add_column('employees',sa.Column('source_available',sa.Boolean(),nullable=True))
    if 'source_checked_at' not in columns:
        op.add_column('employees',sa.Column('source_checked_at',sa.DateTime(timezone=True),nullable=True))

def downgrade():
    op.drop_column('employees','source_checked_at')
    op.drop_column('employees','source_available')
