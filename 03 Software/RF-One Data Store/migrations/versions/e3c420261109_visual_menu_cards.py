"""Restaurant-scoped dish knowledge cards; no price or training results."""
from alembic import op
import sqlalchemy as sa

revision = 'e3c420261109'
down_revision = 'e2c320261109'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('restaurant_menu_cards',
        sa.Column('restaurant_id', sa.Integer(), sa.ForeignKey('restaurants.id'), nullable=False),
        sa.Column('dish_key', sa.String(64), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('content_version', sa.Integer(), nullable=False),
        sa.Column('validation_status', sa.String(24), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('restaurant_id', 'dish_key'),
        sa.CheckConstraint('content_version > 0'),
        sa.CheckConstraint("validation_status IN ('pending','validated')"))


def downgrade():
    op.drop_table('restaurant_menu_cards')
