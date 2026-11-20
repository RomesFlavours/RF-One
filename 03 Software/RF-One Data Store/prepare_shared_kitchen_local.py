"""Apply the approved shared-catalog correction to empty local Kitchen tables."""
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from import_kitchen_excel import local_engine


def main():
    path = Path(__file__).parent/'migrations/versions/e5e620261110_shared_kitchen_catalog.py'
    spec = importlib.util.spec_from_file_location('shared_kitchen_migration',path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = local_engine()
    with engine.begin() as c:
        c.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions = c.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions == [migration.down_revision]:
            c.execute(sa.text('LOCK TABLE kitchen_recipes IN ACCESS EXCLUSIVE MODE'))
            if c.scalar(sa.text('SELECT count(*) FROM kitchen_recipes')) != 0:
                raise RuntimeError('Kitchen already contains recipes; review ownership before changing it')
            with Operations.context(MigrationContext.configure(c)):
                migration.upgrade()
            c.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),
                      dict(new=migration.revision,old=migration.down_revision))
        elif versions != [migration.revision]:
            raise RuntimeError(f'Unexpected revision: {versions}')
        assert 'restaurant_id' not in {x['name'] for x in sa.inspect(c).get_columns('kitchen_recipes')}
    engine.dispose()
    print('PASS: common Kitchen recipe catalog prepared in the existing local database')


if __name__ == '__main__':
    main()
