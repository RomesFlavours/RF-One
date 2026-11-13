"""Apply only the Kitchen migration to the existing canonical local PostgreSQL."""
import json
import os
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import URL
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_kitchen_storage import load_migration


def main():
    config = Path(os.environ['LOCALAPPDATA']) / 'RF-One/AWS-Copy/20261025T130037Z/local-connection.json'
    d = json.loads(config.read_text())
    if d['host'] != '127.0.0.1' or d['port'] != 55436:
        raise RuntimeError('Expected the established canonical local PostgreSQL connection')
    engine = sa.create_engine(URL.create('postgresql+psycopg2', username=d['user'],
        password=d['password'], host=d['host'], port=d['port'], database=d['database']))
    m = load_migration()
    with engine.begin() as c:
        c.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions = c.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions == [m.down_revision]:
            with Operations.context(MigrationContext.configure(c)):
                m.upgrade()
            c.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),
                      dict(new=m.revision, old=m.down_revision))
        elif versions != [m.revision]:
            raise RuntimeError(f'Unexpected local revision: {versions}; no change applied')
        inspector = sa.inspect(c)
        for table in m.TABLES:
            assert set(col.name for col in table.columns) == {col['name'] for col in inspector.get_columns(table.name)}
        counts = {t.name: c.scalar(sa.select(sa.func.count()).select_from(t)) for t in m.TABLES}
    engine.dispose()
    print(json.dumps({'database': 'canonical local PostgreSQL', 'revision': m.revision, 'row_counts': counts}))


if __name__ == '__main__':
    main()
