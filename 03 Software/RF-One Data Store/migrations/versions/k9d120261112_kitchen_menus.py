"""Kitchen menus reference existing locations, menu areas and dish recipes."""
from alembic import op
import sqlalchemy as sa
revision='k9d120261112'
down_revision='k9c120261112'
branch_labels=None
depends_on=None
def upgrade():
    # Freeze this revision's original schema. Runtime metadata already includes
    # the active-menu fields introduced by k9f120261112 and must not be used here.
    op.create_table('kitchen_menus',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('draft_key',sa.String(32),nullable=False,unique=True),
        sa.Column('name',sa.String(255),nullable=False),
        sa.Column('location_id',sa.Integer,sa.ForeignKey('locations.id'),nullable=False),
        sa.Column('archived',sa.Boolean,nullable=False,server_default=sa.false()),
        sa.Column('revision',sa.Integer,nullable=False,server_default='1'))
    op.create_table('kitchen_menu_entries',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('menu_id',sa.Integer,sa.ForeignKey('kitchen_menus.id'),nullable=False),
        sa.Column('area_id',sa.Integer,sa.ForeignKey('kitchen_configuration_items.id'),nullable=False),
        sa.Column('recipe_id',sa.Integer,sa.ForeignKey('kitchen_recipes.id')),
        sa.Column('label',sa.String(255),nullable=False),
        sa.Column('position',sa.Integer,nullable=False),
        sa.CheckConstraint('position > 0',name='ck_kitchen_menu_position'),
        sa.UniqueConstraint('menu_id','position',name='uq_kitchen_menu_position'))
def downgrade():
    raise RuntimeError('Preserve saved menus and entries; roll back application code only.')
