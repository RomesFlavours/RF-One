"""Local-only Email Control, without login; private sandbox DB and DPAPI vault.

Starts the independent incoming monitor by default. No SMTP worker is started.
Run from any directory: python run_email_control_local.py --port 8769
"""
import argparse
from datetime import datetime, timedelta, timezone
from contextlib import closing
import importlib.util
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys

WEB = Path(__file__).resolve().parent
STORE = WEB.parent / 'RF-One Data Store'
sys.path[:0] = [str(WEB), str(STORE)]

from flask import Flask, abort, redirect, request, session, url_for
from sqlalchemy import inspect, select, text
from rfone_data_store import models as m, email_service as outgoing, incoming_email as incoming, display_format
from rfone_data_store.database import create_configured_engine, create_session_factory, DEFAULT_SQLITE_PATH
from rfone_data_store.technical.mailbox_credentials import LocalMailboxVault
from email_routes import register_email_routes
from incoming_email_routes import register_incoming_email_routes


def _apply_local_migration(db, filename):
    spec = importlib.util.spec_from_file_location('incoming_local_migration', STORE / 'migrations/versions' / filename)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    with Operations.context(MigrationContext.configure(db)):
        migration.upgrade()


# Ordered local sandbox schema steps: (from revision, to revision, migration file).
SANDBOX_STEPS = [
    ('i9a120261117', 'i9b120261117', 'i9b120261117_incoming_attachment_metadata.py'),
    ('i9b120261117', 'i9c120261117', 'i9c120261117_incoming_attachment_rules.py'),
]
SANDBOX_VERSION = SANDBOX_STEPS[-1][1]


def upgrade_database(path):
    """Explicit upgrade of a recognized private sandbox, after a consistent backup."""
    path = path.resolve()
    if path == DEFAULT_SQLITE_PATH.resolve() or path.suffix.lower() != '.db':
        raise RuntimeError('Choose a dedicated local Email Control sandbox .db file.')
    if not path.exists():
        return None
    engine = create_configured_engine('sqlite:///' + path.as_posix(), sqlite_immediate=True)
    try:
        with engine.connect() as db:
            if '_email_control_sandbox' not in inspect(db).get_table_names():
                raise RuntimeError('This is not an Email Control sandbox. No tables were changed.')
            version = db.scalar(text('SELECT version FROM _email_control_sandbox'))
        if version == SANDBOX_VERSION:
            return None
        known = [step[0] for step in SANDBOX_STEPS]
        if version not in known:
            raise RuntimeError('Unexpected sandbox revision. No tables were changed.')
        backup = path.with_name(path.stem + '.pre-' + SANDBOX_VERSION + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
        with closing(sqlite3.connect('file:' + path.as_posix() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(str(backup))) as target:
                source.backup(target)
        with engine.begin() as db:
            if db.scalar(text('SELECT version FROM _email_control_sandbox')) != version:
                raise RuntimeError('Sandbox revision changed. Upgrade refused.')
            for source_rev, target_rev, filename in SANDBOX_STEPS[known.index(version):]:
                _apply_local_migration(db, filename)
                db.execute(text('UPDATE _email_control_sandbox SET version=:target WHERE version=:source'),
                           dict(target=target_rev, source=source_rev))
        return backup
    finally:
        engine.dispose()


def prepare_database(path):
    path = path.resolve()
    if path == DEFAULT_SQLITE_PATH.resolve() or path.suffix.lower() != '.db':
        raise RuntimeError('Choose a dedicated local Email Control sandbox .db file.')
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_configured_engine('sqlite:///' + path.as_posix(), sqlite_immediate=True)
    try:
        with engine.begin() as db:
            names = inspect(db).get_table_names()
            if names:
                if '_email_control_sandbox' not in names:
                    raise RuntimeError('This is not an Email Control sandbox. No tables were changed.')
                version = db.scalar(text('SELECT version FROM _email_control_sandbox'))
                if version != SANDBOX_VERSION:
                    raise RuntimeError('The sandbox needs an explicit schema upgrade: run this launcher with --upgrade.')
                return engine
            m.Base.metadata.create_all(db, tables=[m.RFOneAccount.__table__] + outgoing.TABLES)
            _apply_local_migration(db, 'i9a120261117_incoming_email_monitoring.py')
            for _, _, filename in SANDBOX_STEPS:
                _apply_local_migration(db, filename)
            db.execute(text('CREATE TABLE _email_control_sandbox (version VARCHAR(30) NOT NULL)'))
            db.execute(text('INSERT INTO _email_control_sandbox VALUES (:version)'), dict(version=SANDBOX_VERSION))
            db.execute(m.RFOneAccount.__table__.insert().values(id=1, username='local-email-control',
                display_name='Local user', password_hash='local-sandbox-no-login', is_admin=True, is_owner=True))
            db.execute(outgoing.EmailWorkerState.__table__.insert().values(id=1, mode='STOPPED',
                lease_until=outgoing.now(), next_send_at=outgoing.now()))
    except BaseException:
        engine.dispose()
        raise
    return engine


def make_app(engine, timezone_name=None):
    factory = create_session_factory(engine)
    app = Flask(__name__, template_folder=str(WEB / 'templates'), static_folder=str(WEB / 'static'))
    app.secret_key = secrets.token_urlsafe(32)
    app.jinja_env.auto_reload = True
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      TRUSTED_HOSTS=['127.0.0.1', 'localhost'])
    app.jinja_env.filters['local_dt'] = display_format.local_datetime
    app.context_processor(lambda: {'csrf_token': lambda: csrf_token()})

    def csrf_token():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    def csrf():
        expected, supplied = session.get('csrf', ''), request.form.get('csrf_token', '')
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400)

    # The loopback sandbox has one explicit local principal. This does not
    # modify authentication in RF-One Web or any production service.
    def current(db):
        return db.get(m.RFOneAccount, 1)

    kwargs = dict(SessionFactory=factory, load_current_account=current, require_csrf=csrf,
                  get_timezone=lambda: timezone_name)
    register_email_routes(app, **kwargs)
    register_incoming_email_routes(app, **kwargs)

    @app.get('/')
    def home():
        return redirect(url_for('email_mailboxes'))

    return app


def seed_demo(engine):
    """Explicit, fictional preview data. Demo mailboxes are paused."""
    factory = create_session_factory(engine)
    with factory.begin() as db:
        if db.scalar(select(incoming.Mailbox.id).limit(1)):
            return
        for label, address in [('Applications', 'applications@example.test'), ('Administration', 'office@example.test')]:
            box = incoming.configure(db, owner=1, credential_ref='local:' + '0' * 32,
                label=label, address=address, host='mail.example.test', username=address,
                folder='INBOX', interval_seconds=60)
            box.enabled = False
            box.last_success_at, box.last_checked_at = outgoing.now(), outgoing.now()
            box.uidvalidity, box.last_uid = '100', 12
            for i in (11, 12):
                db.add(incoming.Arrival(mailbox_id=box.id, generation=1, uidvalidity='100', uid=i,
                    sender='Alex Morgan <alex@example.test>', recipient=address,
                    subject='CV for the restaurant team' if i == 11 else 'Availability for next week',
                    message_date=outgoing.now() - timedelta(minutes=15), size_bytes=2450,
                    attachments=[dict(part='2', name='CV_Alex_Morgan.pdf' if i == 11 else 'availability.xlsx',
                        content_type='application/pdf' if i == 11 else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        size_bytes=124000 if i == 11 else 8200, encoding='BASE64', disposition='attachment')],
                    attachments_checked_at=outgoing.now()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'RF-One' / 'email-control-local.db')
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--timezone', default=None, help='Location timezone; unset displays explicitly labelled UTC')
    parser.add_argument('--no-monitor', action='store_true')
    parser.add_argument('--upgrade', action='store_true', help='Back up and upgrade a recognized local sandbox explicitly')
    parser.add_argument('--demo', action='store_true', help='Seed fictional paused mailboxes in this sandbox only')
    args = parser.parse_args()
    if args.demo and args.database.resolve() == (Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'RF-One' / 'email-control-local.db').resolve():
        parser.error('--demo requires a separate --database path')
    if args.upgrade:
        backup = upgrade_database(args.database)
        if backup:
            print('Local database backup: ' + str(backup), flush=True)
    engine = prepare_database(args.database)
    if args.demo:
        seed_demo(engine)
    app = make_app(engine, args.timezone)
    monitor = None
    if not args.no_monitor:
        monitor = subprocess.Popen([sys.executable, '-B', '-m', 'rfone_data_store.incoming_email_worker',
            '--database-url', str(engine.url), '--run'], cwd=str(STORE),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    # Request query strings may contain private sender/subject searches.
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    from werkzeug.serving import make_server
    print(f'Email Control: http://127.0.0.1:{args.port}/administration/email/mailboxes', flush=True)
    print('Incoming monitor started.' if monitor else 'Incoming monitor not started.', flush=True)
    try:
        make_server('127.0.0.1', args.port, app).serve_forever()
    finally:
        if monitor:
            monitor.terminate()
            try:
                monitor.wait(timeout=5)
            except subprocess.TimeoutExpired:
                monitor.kill()
        engine.dispose()


if __name__ == '__main__':
    main()
