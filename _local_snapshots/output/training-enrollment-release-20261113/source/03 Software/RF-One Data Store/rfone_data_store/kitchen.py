"""Kitchen storage in the canonical RF-One database; no inferred recipe facts."""
import sqlalchemy as sa
from .models import Base
from . import kitchen_configuration  # register shared configuration FK targets

metadata = Base.metadata

# Existing Visual Menu identity, created by revision e3c420261109.
menu_cards = sa.Table(
    'restaurant_menu_cards', metadata,
    sa.Column('restaurant_id', sa.Integer, sa.ForeignKey('restaurants.id'), primary_key=True),
    sa.Column('dish_key', sa.String(64), primary_key=True),
    sa.Column('title', sa.String(255), nullable=False),
    sa.Column('content_version', sa.Integer, nullable=False),
    sa.Column('validation_status', sa.String(24), nullable=False),
    sa.Column('content_json', sa.Text, nullable=False),
    sa.CheckConstraint('content_version > 0'),
    sa.CheckConstraint("validation_status IN ('pending','validated')"),
    extend_existing=True,
)

recipes = sa.Table(
    'kitchen_recipes', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('code', sa.String(64), nullable=False),
    sa.Column('name', sa.Text, nullable=False),
    sa.Column('kind', sa.String(24), nullable=False),
    sa.Column('category_id', sa.Integer, sa.ForeignKey('kitchen_configuration_items.id')),
    sa.Column('revision', sa.Integer, nullable=False, server_default='1'),
    sa.Column('description', sa.Text),
    sa.Column('dietary_class', sa.String(24)),
    sa.Column('dietary_evidence', sa.Text),
    sa.Column('appearance', sa.Text),
    sa.Column('aroma', sa.Text),
    sa.Column('taste', sa.Text),
    sa.Column('texture', sa.Text),
    sa.Column('serving_temperature', sa.Text),
    sa.Column('organoleptic_notes', sa.Text),
    sa.Column('plating_instructions', sa.Text),
    sa.Column('portion_count', sa.Numeric(14, 4)),
    sa.Column('portion_weight_g', sa.Numeric(14, 4)),
    sa.Column('ingredient_weight_g', sa.Numeric(14, 4)),
    sa.Column('cooked_yield_g', sa.Numeric(14, 4)),
    sa.Column('actual_work_minutes', sa.Numeric(14, 4)),
    sa.Column('elapsed_preparation_minutes', sa.Numeric(14, 4)),
    sa.Column('total_cost', sa.Numeric(18, 6)),
    sa.Column('cost_per_kg', sa.Numeric(18, 6)),
    sa.Column('currency', sa.String(3)),
    sa.Column('kcal', sa.Numeric(18, 6)),
    sa.Column('protein_g', sa.Numeric(18, 6)),
    sa.Column('carbohydrate_g', sa.Numeric(18, 6)),
    sa.Column('fat_g', sa.Numeric(18, 6)),
    sa.Column('cholesterol_mg', sa.Numeric(18, 6)),
    sa.Column('nutrition_basis', sa.Text),
    sa.Column('source_file', sa.Text),
    sa.Column('source_sha256', sa.String(64)),
    sa.Column('source_sheet', sa.Text),
    sa.Column('source_row', sa.Integer),
    sa.Column('source_payload', sa.JSON),
    sa.Column('validation_status', sa.String(24), nullable=False, server_default='pending'),
    sa.Column('validated_by_id', sa.Integer, sa.ForeignKey('acting_identities.id')),
    sa.Column('validated_at', sa.DateTime(timezone=True)),
    sa.UniqueConstraint('code', name='uq_kitchen_recipe_code'),
    sa.CheckConstraint("kind IN ('dish','preparation')", name='ck_kitchen_kind'),
    sa.CheckConstraint("dietary_class IN ('vegan','vegetarian','standard')", name='ck_kitchen_diet'),
    sa.CheckConstraint("validation_status IN ('pending','validated')", name='ck_kitchen_validation'),
)

components = sa.Table(
    'kitchen_recipe_components', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('recipe_id', sa.Integer, sa.ForeignKey('kitchen_recipes.id'), nullable=False),
    sa.Column('position', sa.Integer, nullable=False),
    sa.Column('source_line_key', sa.String(128)),
    sa.Column('ingredient_reference', sa.Text),
    sa.Column('preparation_reference', sa.Text),
    sa.Column('preparation_id', sa.Integer, sa.ForeignKey('kitchen_recipes.id')),
    sa.Column('component_item_id', sa.Integer, sa.ForeignKey('kitchen_configuration_items.id')),
    sa.Column('quantity', sa.Numeric(18, 6)),
    sa.Column('unit', sa.String(32)),
    sa.Column('notes', sa.Text),
    sa.Column('cost', sa.Numeric(18, 6)),
    sa.Column('cost_per_kg', sa.Numeric(18, 6)),
    sa.Column('kcal', sa.Numeric(18, 6)),
    sa.Column('protein_g', sa.Numeric(18, 6)),
    sa.Column('carbohydrate_g', sa.Numeric(18, 6)),
    sa.Column('fat_g', sa.Numeric(18, 6)),
    sa.Column('cholesterol_mg', sa.Numeric(18, 6)),
    sa.Column('source_row', sa.Integer),
    sa.Column('source_payload', sa.JSON),
    sa.UniqueConstraint('recipe_id', 'position', name='uq_kitchen_component_position'),
    sa.CheckConstraint('position > 0', name='ck_kitchen_component_position'),
    sa.CheckConstraint('preparation_id IS NULL OR preparation_id <> recipe_id', name='ck_kitchen_no_self_component'),
)

steps = sa.Table(
    'kitchen_recipe_steps', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('recipe_id', sa.Integer, sa.ForeignKey('kitchen_recipes.id'), nullable=False),
    sa.Column('position', sa.Integer, nullable=False),
    sa.Column('instruction', sa.Text, nullable=False),
    sa.Column('source_row', sa.Integer),
    sa.UniqueConstraint('recipe_id', 'position', name='uq_kitchen_step_position'),
    sa.CheckConstraint('position > 0', name='ck_kitchen_step_position'),
)

photos = sa.Table(
    'kitchen_recipe_photos', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('recipe_id', sa.Integer, sa.ForeignKey('kitchen_recipes.id'), nullable=False),
    sa.Column('asset_uri', sa.Text, nullable=False),
    sa.Column('sha256', sa.String(64)),
    sa.Column('mime_type', sa.String(128)),
    sa.Column('caption', sa.Text),
    sa.Column('alt_text', sa.Text),
    sa.Column('source', sa.Text),
    sa.Column('captured_at', sa.DateTime(timezone=True)),
    sa.UniqueConstraint('recipe_id', 'id', name='uq_kitchen_recipe_photo'),
)

menu_links = sa.Table(
    'kitchen_visual_menu_links', metadata,
    sa.Column('restaurant_id', sa.Integer, primary_key=True),
    sa.Column('dish_key', sa.String(64), primary_key=True),
    sa.Column('recipe_id', sa.Integer, sa.ForeignKey('kitchen_recipes.id'), nullable=False),
    sa.Column('standard_photo_id', sa.Integer),
    sa.ForeignKeyConstraint(['restaurant_id', 'dish_key'], ['restaurant_menu_cards.restaurant_id', 'restaurant_menu_cards.dish_key']),
    sa.ForeignKeyConstraint(['recipe_id', 'standard_photo_id'], ['kitchen_recipe_photos.recipe_id', 'kitchen_recipe_photos.id']),
)

KITCHEN_TABLES = [recipes, components, steps, photos, menu_links]
