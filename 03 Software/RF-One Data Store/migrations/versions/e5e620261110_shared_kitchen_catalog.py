"""PO correction: one common Kitchen recipe catalog, restaurant-specific Menu links."""
from alembic import op
import sqlalchemy as sa

revision = 'e5e620261110'
down_revision = 'e4d520261110'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Only ownership constraints change; all content columns/rows are retained.
    for name in ['kitchen_recipe_components', 'kitchen_visual_menu_links']:
        for fk in inspector.get_foreign_keys(name):
            if fk['referred_table'] == 'kitchen_recipes':
                op.drop_constraint(fk['name'], name, type_='foreignkey')
    op.drop_constraint('uq_kitchen_restaurant_code', 'kitchen_recipes', type_='unique')
    op.drop_constraint('uq_kitchen_restaurant_recipe', 'kitchen_recipes', type_='unique')
    op.drop_column('kitchen_recipe_components', 'restaurant_id')
    op.drop_column('kitchen_recipes', 'restaurant_id')
    op.create_unique_constraint('uq_kitchen_recipe_code', 'kitchen_recipes', ['code'])
    op.create_foreign_key('fk_kitchen_component_recipe', 'kitchen_recipe_components', 'kitchen_recipes', ['recipe_id'], ['id'])
    op.create_foreign_key('fk_kitchen_component_preparation', 'kitchen_recipe_components', 'kitchen_recipes', ['preparation_id'], ['id'])
    op.create_foreign_key('fk_kitchen_menu_recipe', 'kitchen_visual_menu_links', 'kitchen_recipes', ['recipe_id'], ['id'])


def downgrade():
    raise RuntimeError('Shared recipes have no unique owning restaurant. Restore a backup rather than inventing ownership.')
