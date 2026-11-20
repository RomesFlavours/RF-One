"""Kitchen configuration vocabularies; Suppliers reuse the existing registry."""
from alembic import op
import sqlalchemy as sa

revision = 'e6f720261110'
down_revision = 'e6f120261109'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('kitchen_configuration_items',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('section',sa.String(24),nullable=False),
        sa.Column('name',sa.String(255),nullable=False),
        sa.Column('normalized_name',sa.String(255),nullable=False),
        sa.Column('archived',sa.Boolean,nullable=False,server_default=sa.false()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint('section','normalized_name',name='uq_kitchen_configuration_name'),
        sa.CheckConstraint("section IN ('MENU_TYPE','MENU_AREA','CATEGORY','COMPONENT')",name='ck_kitchen_configuration_section'),
        sa.CheckConstraint('length(trim(name)) > 0',name='ck_kitchen_configuration_name'))


def downgrade():
    op.drop_table('kitchen_configuration_items')
