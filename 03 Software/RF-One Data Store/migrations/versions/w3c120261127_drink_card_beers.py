"""Wines > Drink card: beers (Product Owner 2026-11-27).

Additive only: one new table for the beers added by hand to a site's drink
card, like the mineral waters. No existing table or row changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "w3c120261127"
down_revision = "w2b120261126"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "restaurant_drink_card_beers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drink_card_id", sa.Integer, sa.ForeignKey("restaurant_drink_cards.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("beer_type", sa.String(60), nullable=True),
        sa.Column("size_label", sa.String(40), nullable=False),
        sa.Column("price_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.CheckConstraint("price_usd >= 0", name="ck_restaurant_drink_card_beers_price"),
    )
    op.create_index("ix_restaurant_drink_card_beers_drink_card_id", "restaurant_drink_card_beers", ["drink_card_id"])


def downgrade():
    op.drop_table("restaurant_drink_card_beers")
