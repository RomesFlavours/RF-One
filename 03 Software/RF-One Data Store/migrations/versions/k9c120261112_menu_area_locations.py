"""Scope Kitchen menu areas to the canonical Location registry."""
from alembic import op
import sqlalchemy as sa

revision='k9c120261112'
down_revision='t9b120261112'
branch_labels=None
depends_on=None

def upgrade():
    db=op.get_bind()
    locations=db.execute(sa.text('SELECT id FROM locations')).scalars().all()
    count=db.scalar(sa.text("SELECT count(*) FROM kitchen_configuration_items WHERE section='MENU_AREA'"))
    if count and len(locations)!=1:
        raise RuntimeError('Existing menu areas need explicit location assignments before migration.')
    op.add_column('kitchen_configuration_items',sa.Column('location_id',sa.Integer(),nullable=True))
    op.create_foreign_key('fk_kitchen_configuration_location','kitchen_configuration_items','locations',['location_id'],['id'])
    if count:
        db.execute(sa.text("UPDATE kitchen_configuration_items SET location_id=:location WHERE section='MENU_AREA'"),{'location':locations[0]})
    op.drop_constraint('uq_kitchen_configuration_name','kitchen_configuration_items',type_='unique')
    op.create_index('uq_kitchen_configuration_shared_name','kitchen_configuration_items',['section','normalized_name'],unique=True,postgresql_where=sa.text("section <> 'MENU_AREA'"))
    op.create_index('uq_kitchen_menu_area_location_name','kitchen_configuration_items',['location_id','normalized_name'],unique=True,postgresql_where=sa.text("section = 'MENU_AREA'"))
    op.create_check_constraint('ck_kitchen_menu_area_location','kitchen_configuration_items',"section <> 'MENU_AREA' OR location_id IS NOT NULL")

def downgrade():
    raise RuntimeError('Preserve location-scoped menu areas; roll back application code only.')
