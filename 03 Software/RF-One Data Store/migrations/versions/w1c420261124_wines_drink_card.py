"""Wines > Drink card (WINES_DRINK_CARD_001, Product Owner 2026-11-24).

Additive only: six new tables for the printable drink card of a site —
wine descriptions, pairings with Kitchen recipes, pairing reviews, print
settings, mineral waters and images. No existing table or row changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "w1c420261124"
down_revision = "d2a120261122"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "restaurant_wine_card_descriptions",
        sa.Column("wine_id", sa.Integer, sa.ForeignKey("restaurant_wines.id"), primary_key=True),
        sa.Column("sentence", sa.String(300), nullable=False),
        sa.Column("approved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "restaurant_wine_card_pairings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("wine_id", sa.Integer, sa.ForeignKey("restaurant_wines.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("recipe_id", sa.Integer, sa.ForeignKey("kitchen_recipes.id"), nullable=False),
        sa.Column("approved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("location_id", "wine_id", "position", name="uq_restaurant_wine_card_pairings_slot"),
        sa.CheckConstraint("position IN (1, 2)", name="ck_restaurant_wine_card_pairings_position"),
    )
    op.create_index("ix_restaurant_wine_card_pairings_location_id", "restaurant_wine_card_pairings", ["location_id"])
    op.create_index("ix_restaurant_wine_card_pairings_wine_id", "restaurant_wine_card_pairings", ["wine_id"])
    op.create_table(
        "restaurant_wine_card_pairing_reviews",
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), primary_key=True),
        sa.Column("wine_id", sa.Integer, sa.ForeignKey("restaurant_wines.id"), primary_key=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "restaurant_drink_cards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("heading", sa.String(80), nullable=True),
        sa.Column("subheading", sa.String(80), nullable=True),
        sa.Column("footer_note", sa.String(160), nullable=True),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("page_width_in", sa.Numeric(6, 2), nullable=False),
        sa.Column("page_height_in", sa.Numeric(6, 2), nullable=False),
        sa.Column("orientation", sa.String(16), nullable=False),
        sa.Column("corners_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("corner_leg_in", sa.Numeric(6, 2), nullable=False),
        sa.Column("show_glass_price", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("ink_color", sa.String(7), nullable=False),
        sa.Column("accent_color", sa.String(7), nullable=False),
        sa.Column("line_color", sa.String(7), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("location_id", name="uq_restaurant_drink_cards_location"),
        sa.CheckConstraint("page_count BETWEEN 1 AND 24", name="ck_restaurant_drink_cards_pages"),
        sa.CheckConstraint("page_width_in > 0 AND page_height_in > 0", name="ck_restaurant_drink_cards_size"),
        sa.CheckConstraint("orientation IN ('PORTRAIT', 'LANDSCAPE')", name="ck_restaurant_drink_cards_orientation"),
        sa.CheckConstraint("corner_leg_in >= 0", name="ck_restaurant_drink_cards_corner"),
    )
    op.create_table(
        "restaurant_drink_card_waters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drink_card_id", sa.Integer, sa.ForeignKey("restaurant_drink_cards.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sparkling", sa.Boolean, nullable=False),
        sa.Column("size_label", sa.String(40), nullable=False),
        sa.Column("price_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.CheckConstraint("price_usd >= 0", name="ck_restaurant_drink_card_waters_price"),
    )
    op.create_index("ix_restaurant_drink_card_waters_drink_card_id", "restaurant_drink_card_waters", ["drink_card_id"])
    op.create_table(
        "restaurant_drink_card_images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drink_card_id", sa.Integer, sa.ForeignKey("restaurant_drink_cards.id"), nullable=False),
        sa.Column("slot", sa.String(24), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("drink_card_id", "slot", name="uq_restaurant_drink_card_images_slot"),
    )
    op.create_index("ix_restaurant_drink_card_images_drink_card_id", "restaurant_drink_card_images", ["drink_card_id"])


def downgrade():
    for table in (
        "restaurant_drink_card_images", "restaurant_drink_card_waters", "restaurant_drink_cards",
        "restaurant_wine_card_pairing_reviews", "restaurant_wine_card_pairings", "restaurant_wine_card_descriptions",
    ):
        op.drop_table(table)
