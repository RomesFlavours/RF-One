"""At most one explicitly active Kitchen menu per location."""
from alembic import op
import sqlalchemy as sa
revision='k9f120261112'
down_revision='k9e120261112'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('kitchen_menus',sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_check_constraint('ck_kitchen_menu_active_not_archived','kitchen_menus','NOT (active AND archived)')
    op.create_index('uq_kitchen_active_menu_location','kitchen_menus',['location_id'],unique=True,postgresql_where=sa.text('active'))
def downgrade():
    raise RuntimeError('Preserve explicit active menu selection; roll back application code only.')
