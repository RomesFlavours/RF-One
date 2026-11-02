"""Apply only the reviewed additive interview consent migration; never expose a DSN."""
import importlib.util
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

PREVIOUS, REVISION = 'e0a120261101', 'e1b220261102'


def main():
    engine = create_engine(os.environ['RFONE_DATABASE_URL'], hide_parameters=True,
        connect_args={'connect_timeout': 15})
    try:
        with engine.begin() as connection:
            if connection.dialect.name != 'postgresql':
                raise ValueError('This operator entry point requires PostgreSQL.')
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('rf1-interviews-test-schema'))"))
            revisions = list(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
            if revisions == [REVISION]:
                print(json.dumps(dict(status='already_applied', revision=revisions[0])))
                return 0
            if revisions != [PREVIOUS]:
                print(json.dumps(dict(status='refused_unexpected_revision', revisions=revisions)))
                return 2
            if 'consent_given' in {c['name'] for c in inspect(connection).get_columns('interview_sessions')}:
                print('Refused: an unversioned consent column already exists.')
                return 2
            path = Path(__file__).resolve().parents[1] / 'migrations/versions/e1b220261102_add_interview_consent.py'
            spec = importlib.util.spec_from_file_location('interview_consent_migration', path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            updated = connection.execute(text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),
                dict(new=REVISION, old=PREVIOUS))
            if updated.rowcount != 1:
                raise ValueError('Migration version changed concurrently.')
            print(json.dumps(dict(status='applied', previous=PREVIOUS, revision=REVISION,
                added_columns=['interview_sessions.consent_given', 'interview_sessions.consent_at'], data_rows_created=0)))
        return 0
    except Exception as exc:
        print('Interview consent migration failed: ' + type(exc).__name__)
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
