"""Test data for Wines > Drink card: a Winter Park site with the wines and
prices of the approved Winter Park card and a small active Kitchen menu.

Also provides `install_enrollment_stub()`: this live-code checkout carries
the AWS migration `t9e120261113`, which imports a Training module the live
web image does not ship. A throwaway test database only needs the table to
exist, so the stub defines just that table. Used by tests only."""

from __future__ import annotations

import sys
import types
from datetime import date
from decimal import Decimal

WINES = [
    # category, type, label, producer, vintage, cost, by_glass, bottle, glass
    ("RED", "Amarone della Valpolicella", None, "Cantina del Castello", 2018, "48", False, "122", None),
    ("RED", "Barolo", "Az.", "Az. Grimaldi Giacomo", 2021, "42", True, "110", "30"),
    ("RED", "Cabernet Sauvignon", "Fuga", "Tararo", 2024, "28", True, "85", "24"),
    ("RED", "Montepulciano d'Abruzzo", None, "Selva la Canonica", 2024, "14", True, "48", "14"),
    ("RED", "Nebbiolo", "Langhe", "Carlo Alberto", 2021, "31", True, "100", "29"),
    ("WHITE", "Gavi", "Fornaci", "Castellari", 2023, "18", True, "60", "17"),
    ("WHITE", "Pinot Grigio", "Colli Orientali", "Lis Neris", 2023, "25", True, "80", "23"),
    ("ROSE", "Frappato", "Per Mari", "Casa di Grazia", 2024, "17", True, "58", "17"),
]

DISHES = [
    ("WP-001", "Brasato al Barolo", "Beef braised in red wine", ["beef cheek", "Barolo wine", "carrot", "celery"]),
    ("WP-002", "Spaghetti alle Vongole", "Clams, garlic, parsley", ["spaghetti", "clams", "garlic", "parsley"]),
    ("WP-003", "Tagliata di Manzo", "Sliced grilled steak", ["ribeye", "arugula", "parmigiano"]),
]


def install_enrollment_stub() -> None:
    try:
        import rfone_data_store.training.enrollment  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    from sqlalchemy import Column, Integer
    from rfone_data_store import models as m

    module = types.ModuleType("rfone_data_store.training.enrollment")

    class EnrollmentInvitation(m.Base):
        __tablename__ = "training_enrollment_invitations"
        id = Column(Integer, primary_key=True)

    module.EnrollmentInvitation = EnrollmentInvitation
    sys.modules["rfone_data_store.training.enrollment"] = module


def install_sqlite_migration_shims() -> None:
    """The live AWS migration chain adds and drops constraints with ALTER,
    which SQLite cannot do. A throwaway SQLite test database skips those
    constraint changes; every table and column is still created."""
    from alembic.ddl.sqlite import SQLiteImpl

    SQLiteImpl.add_constraint = lambda self, const: None
    SQLiteImpl.drop_constraint = lambda self, const: None


def _type_id(s, wine_types, name):
    found = wine_types.find_type_by_name(s, name)
    if found is None:
        found = wine_types.create_wine_type(s, standard_name=name, aliases=[])
    return found.id


def seed(s, *, with_menu: bool = True) -> dict:
    """Create the Winter Park site, its Entity, Wine list and menu."""
    from sqlalchemy import text
    from rfone_data_store import legal_entity_service
    from rfone_data_store import models as m
    from rfone_data_store.restaurant_wines import catalog, wine_lists, wine_types

    entity = legal_entity_service.create_legal_entity(s, legal_name="RFWP")
    merchant = m.Merchant(name="Rome's Flavours WP")
    s.add(merchant)
    s.flush()
    location = m.Location(merchant_id=merchant.id, name="Winter Park", timezone="America/New_York")
    s.add(location)
    s.flush()
    restaurant = m.Restaurant(name="Rome's Flavours", legal_entity_id=entity.id)
    s.add(restaurant)
    s.flush()
    s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    wine_types.seed_reference_wine_types(s)
    s.flush()

    version = wine_lists.create_version(
        s, legal_entity_id=entity.id, effective_from=date(2026, 11, 1), mode=wine_lists.MODE_EMPTY,
        today=date(2026, 11, 1), account_id=None,
    )
    wines = {}
    for category, type_name, label, producer, vintage, cost, by_glass, bottle, glass in WINES:
        wine = catalog.create_wine(s, catalog.WineInput(
            wine_type_id=_type_id(s, wine_types, type_name), producer=producer, label_name=label,
            vintage_year=vintage, non_vintage=False, category=category, style="STILL", denomination=None,
            region=None, bottle_size_ml=750, supplier_name=None, cost_usd=Decimal(cost), cost_date=None,
            availability="AVAILABLE", notes=None,
        ))
        wine_lists.add_item(
            s, version, wine_id=wine.id, today=date(2026, 11, 1), cost_used=Decimal(cost), value_factor=Decimal("1"),
            sells_by_glass=by_glass, applied_bottle=Decimal(bottle), applied_glass=Decimal(glass) if glass else None,
        )
        wines[producer] = wine.id
    s.flush()

    recipes = {}
    if with_menu:
        s.execute(text("INSERT INTO kitchen_configuration_items (section, name, normalized_name) "
                       "VALUES ('MENU_AREA', 'Secondi', 'secondi')"))
        area_id = s.execute(text("SELECT id FROM kitchen_configuration_items WHERE normalized_name='secondi'")).scalar()
        s.execute(text("INSERT INTO kitchen_menus (draft_key, name, location_id, archived, active, revision) "
                       "VALUES ('wp-menu', 'Winter Park Fall', :loc, 0, 1, 1)"), {"loc": location.id})
        menu_id = s.execute(text("SELECT id FROM kitchen_menus WHERE draft_key='wp-menu'")).scalar()
        for position, (code, name, description, ingredients) in enumerate(DISHES, start=1):
            s.execute(text("INSERT INTO kitchen_recipes (code, name, kind, revision, description, validation_status) "
                           "VALUES (:c, :n, 'dish', 1, :d, 'validated')"), {"c": code, "n": name, "d": description})
            rid = s.execute(text("SELECT id FROM kitchen_recipes WHERE code=:c"), {"c": code}).scalar()
            for pos, ingredient in enumerate(ingredients, start=1):
                s.execute(text("INSERT INTO kitchen_recipe_components (recipe_id, position, ingredient_reference) "
                               "VALUES (:r, :p, :i)"), {"r": rid, "p": pos, "i": ingredient})
            s.execute(text("INSERT INTO kitchen_menu_entries (menu_id, area_id, recipe_id, label, position) "
                           "VALUES (:m, :a, :r, :l, :p)"), {"m": menu_id, "a": area_id, "r": rid, "l": name, "p": position})
            recipes[code] = rid
    s.flush()
    return {"entity_id": entity.id, "location_id": location.id, "list_id": version.id, "wines": wines,
            "recipes": recipes}
