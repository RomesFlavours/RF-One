"""Kitchen final schema from the verified AWS head, without unrelated Training changes.

AWS is at t9a120261110. The local development chain interleaves the Student
registry and temporarily scopes Menu Areas to locations before sharing them
again. This explicit release branch applies only Kitchen's final additive
schema. It preserves shared areas, published recipes and all identity data.
"""
from alembic import op
import sqlalchemy as sa

revision='k9g120261112'
down_revision='t9a120261110'
branch_labels=('kitchen_aws_20261112',)
depends_on=None

def upgrade():
    op.add_column('kitchen_recipes',sa.Column('elapsed_preparation_minutes',sa.Numeric(14,4),nullable=True))
    op.add_column('kitchen_configuration_items',sa.Column('location_id',sa.Integer,nullable=True))
    op.create_foreign_key('fk_kitchen_configuration_location','kitchen_configuration_items','locations',['location_id'],['id'])
    op.drop_constraint('uq_kitchen_configuration_name','kitchen_configuration_items',type_='unique')
    op.create_index('uq_kitchen_configuration_shared_name','kitchen_configuration_items',['section','normalized_name'],unique=True,postgresql_where=sa.text("section <> 'MENU_AREA'"))
    op.create_index('uq_kitchen_menu_area_location_name','kitchen_configuration_items',['normalized_name'],unique=True,postgresql_where=sa.text("section = 'MENU_AREA'"))
    op.create_table('kitchen_menus',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('draft_key',sa.String(32),nullable=False,unique=True),
        sa.Column('name',sa.String(255),nullable=False),
        sa.Column('location_id',sa.Integer,sa.ForeignKey('locations.id'),nullable=False),
        sa.Column('archived',sa.Boolean,nullable=False,server_default=sa.false()),
        sa.Column('active',sa.Boolean,nullable=False,server_default=sa.false()),
        sa.Column('revision',sa.Integer,nullable=False,server_default='1'),
        sa.CheckConstraint('NOT (active AND archived)',name='ck_kitchen_menu_active_not_archived'))
    op.create_index('uq_kitchen_active_menu_location','kitchen_menus',['location_id'],unique=True,postgresql_where=sa.text('active'))
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
    raise RuntimeError('Preserve published Kitchen data; roll back the service image only.')
