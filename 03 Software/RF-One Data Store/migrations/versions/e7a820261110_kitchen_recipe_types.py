"""Add Recipe Type to the existing Kitchen configuration lists."""
from alembic import op
import sqlalchemy as sa

revision='e7a820261110'
down_revision='e6f720261110'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('kitchen_configuration_items') as table:
        table.drop_constraint('ck_kitchen_configuration_section',type_='check')
        table.create_check_constraint('ck_kitchen_configuration_section',
            "section IN ('MENU_TYPE','MENU_AREA','CATEGORY','COMPONENT','RECIPE_TYPE')")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM kitchen_configuration_items WHERE section='RECIPE_TYPE'")):
        raise RuntimeError('Recipe types exist; refusing to discard them during downgrade.')
    with op.batch_alter_table('kitchen_configuration_items') as table:
        table.drop_constraint('ck_kitchen_configuration_section',type_='check')
        table.create_check_constraint('ck_kitchen_configuration_section',
            "section IN ('MENU_TYPE','MENU_AREA','CATEGORY','COMPONENT')")
