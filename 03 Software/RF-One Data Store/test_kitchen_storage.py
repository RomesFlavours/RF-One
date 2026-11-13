"""Migration and ownership checks using an ephemeral in-memory database."""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


def load_migration():
    path = Path(__file__).parent / 'migrations/versions/e4d520261110_kitchen_recipe_storage.py'
    spec = importlib.util.spec_from_file_location('kitchen_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    m = load_migration()
    e = sa.create_engine('sqlite:///:memory:')
    with e.begin() as c:
        c.exec_driver_sql('PRAGMA foreign_keys=ON')
        for name in ['restaurants', 'acting_identities', 'restaurant_menu_cards']:
            m.metadata.tables[name].create(c)
        c.execute(m.metadata.tables['restaurants'].insert(), [{'id': 1}, {'id': 2}])
        c.execute(m.metadata.tables['restaurant_menu_cards'].insert(),
                  [{'restaurant_id': 1, 'dish_key': 'dish'}, {'restaurant_id': 2, 'dish_key': 'dish'}])
        with Operations.context(MigrationContext.configure(c)):
            m.upgrade()
        assert all(c.scalar(sa.select(sa.func.count()).select_from(t)) == 0 for t in m.TABLES)
        c.execute(m.recipes.insert(), [dict(id=1, restaurant_id=1, code='D001', name='Dish', kind='dish'),
                                     dict(id=2, restaurant_id=2, code='D001', name='Other', kind='dish')])
        assert c.scalar(sa.select(m.recipes.c.dietary_class).where(m.recipes.c.id == 1)) is None
        c.execute(m.photos.insert(), dict(id=1, recipe_id=1, asset_uri='assets/plating.jpg'))
        c.execute(m.menu_links.insert(), dict(restaurant_id=1, dish_key='dish', recipe_id=1, standard_photo_id=1))
        bad = [
            m.recipes.insert().values(restaurant_id=1, code='D001', name='Duplicate', kind='dish'),
            m.recipes.update().where(m.recipes.c.id == 1).values(dietary_class='unknown'),
            m.menu_links.update().values(recipe_id=2),
            m.components.insert().values(restaurant_id=1, recipe_id=1, position=1, preparation_id=2),
            m.photos.insert().values(id=2, recipe_id=2, asset_uri='other.jpg'),
        ]
        # Insert a second recipe's photo, then verify it cannot be selected for the first.
        c.execute(bad.pop())
        bad.append(m.menu_links.update().values(standard_photo_id=2))
        for statement in bad:
            try:
                with c.begin_nested():
                    c.execute(statement)
            except IntegrityError:
                pass
            else:
                raise AssertionError('Invalid relationship/classification accepted')
        for value in ['vegan', 'vegetarian', 'standard']:
            c.execute(m.recipes.update().where(m.recipes.c.id == 1).values(dietary_class=value))
        with Operations.context(MigrationContext.configure(c)):
            m.downgrade()
        assert not set(t.name for t in m.TABLES) & set(sa.inspect(c).get_table_names())
    e.dispose()
    print('PASS: upgrade/downgrade, empty storage, unknown diet, three classes, duplicate codes, restaurant/photo ownership')


if __name__ == '__main__':
    main()
