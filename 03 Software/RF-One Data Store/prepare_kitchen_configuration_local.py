"""Add Kitchen Configuration to the existing local database, without seeding data."""
import importlib.util
from pathlib import Path
import json
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from import_kitchen_excel import local_engine


def main():
    path=Path(__file__).parent/'migrations/versions/e6f720261110_kitchen_configuration.py'
    spec=importlib.util.spec_from_file_location('configuration_migration',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=local_engine()
    with engine.begin() as c:
        c.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions=c.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
        protected=('kitchen_recipes','kitchen_recipe_components','kitchen_recipe_steps','suppliers','restaurant_menu_cards')
        before={t:c.scalar(sa.text(f'SELECT count(*) FROM {t}')) for t in protected}
        if versions==[m.down_revision]:
            with Operations.context(MigrationContext.configure(c)):
                m.upgrade()
            c.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=m.revision,old=m.down_revision))
        elif versions!=[m.revision]:
            raise RuntimeError(f'Unexpected local revision: {versions}; no changes applied')
        after={t:c.scalar(sa.text(f'SELECT count(*) FROM {t}')) for t in protected}
        assert before==after
        counts=c.scalar(sa.text('SELECT count(*) FROM kitchen_configuration_items'))
    engine.dispose()
    print(json.dumps(dict(revision=m.revision,configuration_items=counts,preserved_counts=after)))


if __name__=='__main__':
    main()
