"""Category assignment and safe composition editing on existing Kitchen recipes."""
from alembic import op
import sqlalchemy as sa
revision='e8b920261110'
down_revision='e7a820261110'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('kitchen_recipes') as t:
        t.add_column(sa.Column('category_id',sa.Integer,nullable=True))
        t.add_column(sa.Column('revision',sa.Integer,nullable=False,server_default='1'))
        t.create_foreign_key('fk_kitchen_recipe_category','kitchen_configuration_items',['category_id'],['id'])
    with op.batch_alter_table('kitchen_recipe_components') as t:
        t.add_column(sa.Column('component_item_id',sa.Integer,nullable=True))
        t.create_foreign_key('fk_kitchen_component_item','kitchen_configuration_items',['component_item_id'],['id'])


def downgrade():
    with op.batch_alter_table('kitchen_recipe_components') as t:
        t.drop_constraint('fk_kitchen_component_item',type_='foreignkey');t.drop_column('component_item_id')
    with op.batch_alter_table('kitchen_recipes') as t:
        t.drop_constraint('fk_kitchen_recipe_category',type_='foreignkey');t.drop_column('category_id');t.drop_column('revision')
