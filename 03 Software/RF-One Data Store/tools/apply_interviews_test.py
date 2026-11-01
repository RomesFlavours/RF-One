"""Apply only the reviewed additive interview migration; never expose a DSN."""
import importlib.util
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


def main():
    engine = create_engine(os.environ['RFONE_DATABASE_URL'], hide_parameters=True,
        connect_args={'connect_timeout': 15})
    try:
        with engine.begin() as connection:
            if connection.dialect.name != 'postgresql':
                raise ValueError('This operator entry point requires PostgreSQL.')
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('rf1-interviews-test-schema'))"))
            revisions = list(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
            if revisions == ['e0a120261101']:
                print(json.dumps(dict(status='already_applied', revision=revisions[0])))
                return 0
            if revisions != ['d9e220261029']:
                print(json.dumps(dict(status='refused_unexpected_revision', revisions=revisions)))
                return 2
            if inspect(connection).has_table('interview_sessions'):
                print('Refused: an unversioned interview table already exists.')
                return 2
            path = Path(__file__).resolve().parents[1] / 'migrations/versions/e0a120261101_add_interviews_test.py'
            spec = importlib.util.spec_from_file_location('interviews_test_migration', path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            updated = connection.execute(text("UPDATE alembic_version SET version_num='e0a120261101' WHERE version_num='d9e220261029'"))
            if updated.rowcount != 1:
                raise ValueError('Migration version changed concurrently.')
            print(json.dumps(dict(status='applied', previous='d9e220261029', revision='e0a120261101',
                added_table='interview_sessions', data_rows_created=0)))
        return 0
    except Exception as exc:
        print('Interview migration failed: ' + type(exc).__name__)
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
