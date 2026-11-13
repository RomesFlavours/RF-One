"""Menu Areas are shared across locations; preserve area IDs and menu entries."""
from alembic import op
import sqlalchemy as sa
revision='k9e120261112'
down_revision='k9d120261112'
branch_labels=None
depends_on=None
def upgrade():
    db=op.get_bind()
    duplicate=db.execute(sa.text("SELECT normalized_name FROM kitchen_configuration_items WHERE section='MENU_AREA' GROUP BY normalized_name HAVING count(*)>1")).first()
    if duplicate:raise RuntimeError('Resolve duplicate area names before sharing Menu Areas.')
    op.drop_constraint('ck_kitchen_menu_area_location','kitchen_configuration_items',type_='check')
    op.drop_index('uq_kitchen_menu_area_location_name',table_name='kitchen_configuration_items')
    db.execute(sa.text("UPDATE kitchen_configuration_items SET location_id=NULL WHERE section='MENU_AREA'"))
    op.create_index('uq_kitchen_menu_area_location_name','kitchen_configuration_items',['normalized_name'],unique=True,postgresql_where=sa.text("section = 'MENU_AREA'"))
def downgrade():
    raise RuntimeError('Preserve shared Menu Areas; restore explicit assignments before reverting.')
