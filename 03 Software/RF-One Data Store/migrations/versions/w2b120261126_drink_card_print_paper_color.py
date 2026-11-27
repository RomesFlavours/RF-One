"""Wines > Drink card: print the paper colour or white (Product Owner 2026-11-27).

Additive only: one boolean on `restaurant_drink_cards`, true by default, so
every existing card keeps printing the background's paper colour.
"""
from alembic import op
import sqlalchemy as sa

revision = "w2b120261126"
down_revision = "w1c420261124"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "restaurant_drink_cards",
        sa.Column("print_paper_color", sa.Boolean, nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("restaurant_drink_cards", "print_paper_color")
