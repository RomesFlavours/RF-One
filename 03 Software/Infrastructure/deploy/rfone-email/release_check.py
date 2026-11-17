"""Explicit ECS release step: isolated PostgreSQL checks or one planned migration.

Never prints URLs, credentials, recipients, message bodies or remote SMTP replies.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text, inspect, select
from rfone_data_store import email_service as e
from rfone_data_store.database import create_session_factory
from rfone_data_store.email_worker import run_once
from rfone_data_store.technical.aruba_smtp import load_secret, SendFailure

EXPECTED = 't9e120261113'
TARGET = 'e9a120261117'
PROTECTED = ('rfone_accounts', 'rfone_account_domain_access', 'selection_workspace_email_outbox',
             'training_accounts', 'employees')


def migration():
    path = Path('/app/RF-One Data Store/migrations/versions/e9a120261117_shared_email_service_aws.py')
    spec = importlib.util.spec_from_file_location('email_release_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def versions(db):
    return list(db.execute(text('select version_num from public.alembic_version')).scalars())


def protected_counts(db):
    existing = set(inspect(db).get_table_names(schema='public'))
    return {name: db.scalar(text(f'SELECT count(*) FROM public.{name}')) for name in PROTECTED if name in existing}


def smtp_check():
    settings = dict(host=os.environ['RFONE_SMTP_HOST'], port=os.environ['RFONE_SMTP_PORT'],
                    username=os.environ['RFONE_SMTP_USERNAME'], from_address=os.environ['RFONE_EMAIL_FROM_ADDRESS'])
    config = load_secret(os.environ['RFONE_EMAIL_SMTP_SECRET_ID'], os.environ['AWS_REGION'], smtp_settings=settings)
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with smtplib.SMTP_SSL(config['host'], int(config['port']), timeout=10, context=context) as client:
        client.ehlo()
        client.login(config['username'], config['password'])
        code, _ = client.noop()
        assert 200 <= code < 300
    print('ARUBA_TLS_AUTH_NOOP_OK no MAIL/RCPT/DATA issued', flush=True)


class Fake:
    def __init__(self, failure=None):
        self.sent, self.failure = [], failure

    def send(self, row):
        self.sent.append(row.id)
        if self.failure:
            raise self.failure


def postgres_checks(engine):
    schema = 'rfone_email_test_' + uuid.uuid4().hex
    assert re.fullmatch(r'rfone_email_test_[a-f0-9]{32}', schema)
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA {schema}'))
    isolated = create_engine(os.environ['RFONE_DATABASE_URL'],
        connect_args={'options': f'-csearch_path={schema},public', 'connect_timeout': 10})
    try:
        with isolated.begin() as db:
            with Operations.context(MigrationContext.configure(db)):
                migration().upgrade()
        factory = create_session_factory(isolated)

        def enqueue(domain='TRAINING', key='1'):
            with factory.begin() as db:
                row = e.enqueue(db, domain=domain, recipient='no-send@example.test', subject='Local check',
                                body='Isolated schema only', event='deployment-check', dedup_key=key)
                return row.id

        def status(rid):
            with factory() as db:
                return db.get(e.EmailRequest, rid).status

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: enqueue(), range(2)))
        assert ids[0] == ids[1]
        with factory() as db:
            assert e.get(db, 'SELECTION', ids[0]) is None
        transport = Fake()
        stamp = e.now() + timedelta(seconds=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run_once(factory, transport, clock=lambda: stamp), range(2)))
        assert results.count(True) == 1 and transport.sent == [ids[0]]
        assert status(ids[0]) == 'ACCEPTED'
        second = enqueue('SELECTION')
        stamp += timedelta(seconds=10)
        assert run_once(factory, Fake(SendFailure('SMTP_451', temporary=True)), clock=lambda: stamp)
        assert status(second) == 'RETRY'
        stamp += timedelta(seconds=40)
        assert run_once(factory, Fake(), clock=lambda: stamp)
        assert status(second) == 'ACCEPTED'
        third = enqueue(key='uncertain')
        stamp += timedelta(seconds=10)
        assert run_once(factory, Fake(SendFailure('SMTP_CONNECTION', uncertain=True)), clock=lambda: stamp)
        assert status(third) == 'UNCERTAIN'
        stamp += timedelta(seconds=400)
        assert not run_once(factory, Fake(), clock=lambda: stamp)
        print('POSTGRES_ISOLATED_OK dedup concurrent-workers domains retry uncertainty', flush=True)
    finally:
        isolated.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA {schema} CASCADE'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['preflight', 'migrate', 'verify'])
    args = parser.parse_args()
    engine = create_engine(os.environ['RFONE_DATABASE_URL'], connect_args={'connect_timeout': 10})
    try:
        with engine.connect() as db:
            current = versions(db)
            before = protected_counts(db)
        if args.mode == 'preflight':
            assert current == [EXPECTED], f'Unexpected database revision: {current}'
            postgres_checks(engine)
            smtp_check()
        elif args.mode == 'migrate':
            with engine.begin() as db:
                assert db.scalar(text('SELECT pg_try_advisory_xact_lock(7161172026)')), 'Another schema release is running'
                assert versions(db) == [EXPECTED], 'Database revision changed; migration refused'
                before = protected_counts(db)
                assert not any(inspect(db).has_table(t.name, schema='public') for t in e.TABLES), 'Email tables already exist'
                with Operations.context(MigrationContext.configure(db)):
                    migration().upgrade()
                result = db.execute(text('UPDATE public.alembic_version SET version_num=:target WHERE version_num=:expected'),
                                    dict(target=TARGET, expected=EXPECTED))
                assert result.rowcount == 1
                assert protected_counts(db) == before, 'Protected row counts changed'
            print('EMAIL_MIGRATION_OK ' + TARGET, flush=True)
        else:
            assert current == [TARGET], f'Unexpected database revision: {current}'
            with engine.connect() as db:
                assert all(inspect(db).has_table(t.name, schema='public') for t in e.TABLES)
                queued = db.scalar(select(e.EmailRequest.id).limit(1))
                state = db.get_execution_options()
                rows = db.execute(text('SELECT mode, heartbeat FROM email_worker_state WHERE id=1')).first()
                print('EMAIL_VERIFY', json.dumps(dict(revision=current, queue_empty=queued is None,
                      worker_mode=rows[0], heartbeat=str(rows[1]))), flush=True)
        with engine.connect() as db:
            assert protected_counts(db) == before, 'Protected row counts changed'
        print('PROTECTED_ROW_COUNTS_UNCHANGED', flush=True)
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        # CloudWatch must never receive an exception carrying a URL, SQL payload or SMTP reply.
        print('EMAIL_RELEASE_FAILED ' + type(exc).__name__, flush=True)
        raise SystemExit(1) from None
