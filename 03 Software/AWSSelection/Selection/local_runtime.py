"""One existing database and account; explicitly initialized, loopback-only."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
STORE = HERE.parent / 'RF-One Data Store'
PRIVATE = Path(os.environ['LOCALAPPDATA']) / 'RF-One'
DATABASE = PRIVATE / 'RFBank/rfone.db'
DATA = HERE.parents[2] / 'output/selection-local'
sys.path.insert(0, str(STORE))
sys.path.insert(0, str(HERE))


def existing_database():
    root = HERE.parents[2]
    configs = [root / 'RFBank/local-database.json', root.parent / 'RFBank/local-database.json']
    config = next((p for p in configs if p.is_file()), None)
    if config is None:
        raise RuntimeError('Il database locale condiviso non è stato identificato: nessun database creato.')
    configured = Path(json.loads(config.read_text(encoding='utf-8'))['database'])
    expected = (configured if configured.is_absolute() else config.parent / configured).resolve()
    permitted = {(config.parent / 'rfone.db').resolve(), DATABASE.resolve()}
    if expected not in permitted:
        raise RuntimeError('Percorso del database locale non previsto: nessun database creato.')
    if not expected.is_file():
        raise RuntimeError('Il database locale condiviso non esiste: nessun database creato.')
    return expected


def operator(username='admin', require_access=True):
    with closing(sqlite3.connect(existing_database().as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT id,username,status,session_version FROM rfone_accounts WHERE username=?', (username,)).fetchone()
        if row is None or row[2] != 'ACTIVE':
            raise RuntimeError('Operatore locale esistente non disponibile. Nessun account creato.')
        access = db.execute("SELECT enabled FROM rfone_account_domain_access WHERE account_id=? AND domain_code='SELECTION'", (row[0],)).fetchone()
        if require_access and (not access or not access[0]):
            raise RuntimeError('Selezione non è abilitata per questo operatore. I permessi non sono modificati all’avvio.')
        return row


def configure(port, ai=False, ai_cv=False):
    path = existing_database()
    DATA.mkdir(parents=True, exist_ok=True)
    key = DATA / 'secret.key'
    if not key.exists():
        key.write_text(secrets.token_hex(32), encoding='ascii')
    os.environ.update(RFONE_DATABASE_URL='sqlite:///' + path.as_posix(),
        RFONE_FLASK_SECRET_KEY=key.read_text(encoding='ascii').strip(),
        RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1', RFONE_WEB_BASE_URL=f'http://127.0.0.1:{port}',
        RFONE_SELECTION_UPLOAD_DIR=str(DATA / 'documents'), RFONE_UI_LANGUAGE='it',
        RFONE_SELECTION_ENGINE='conversation', RFONE_SELECTION_AI='1' if ai or ai_cv else '0',
        RFONE_SELECTION_AI_CV='1' if ai_cv else '0', AWS_EC2_METADATA_DISABLED='true')
    for name in ('RFONE_SELECTION_DOCUMENT_BUCKET','RFONE_PUBLIC_BASE_URL','ALEMBIC_DATABASE_URL_OVERRIDE'):
        os.environ.pop(name, None)
    return path


def initialize(enable_selection=False):
    """Explicit additive compatibility step, never the automatic startup path."""
    from sqlalchemy import create_engine, inspect, text
    from workspace.schema import required_tables, verify
    who = operator(require_access=False)
    path = existing_database()
    backups = DATA / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / ('selection-before-local-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sqlite-backup')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(backup)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup del database non valido.')
    engine = create_engine('sqlite:///' + path.as_posix())
    added = []
    with engine.begin() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        inspector = inspect(connection)
        existing = set(inspector.get_table_names())
        for table in required_tables():
            if table.name not in existing:
                table.create(connection)
                existing.add(table.name)
                added.append(table.name)
                continue
            old = {c['name'] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in old:
                    continue
                # Only nullable additions or the non-privileged owner default.
                if not column.nullable and (table.name, column.name) != ('rfone_accounts', 'is_owner'):
                    raise RuntimeError(f'Adeguamento non previsto: {table.name}.{column.name}')
                default = ' NOT NULL DEFAULT 0' if column.name == 'is_owner' else ''
                sql_type = column.type.compile(dialect=engine.dialect)
                connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {sql_type}{default}')
                added.append(table.name + '.' + column.name)
        if enable_selection:
            # Explicit PO authorization on 2026-11-14; no other grant changes.
            result = connection.execute(text("UPDATE rfone_account_domain_access SET enabled=1 WHERE account_id=:id AND domain_code='SELECTION'"), {'id': who[0]})
            if result.rowcount != 1:
                raise RuntimeError('Il permesso esistente Selezione non è stato trovato.')
    verify(str(engine.url))
    engine.dispose()
    print(json.dumps({'backup': str(backup), 'additions': added, 'account_created': False}, ensure_ascii=False), flush=True)


def create_application(port=5096, username='admin', ai=False, ai_cv=False):
    # An environment problem must never be reported as an unreadable CV.
    from rfone_data_store.selection.parsing.text_extraction import require_readers
    require_readers()
    configure(port, ai, ai_cv)
    operator(username)
    spec = importlib.util.spec_from_file_location('selection_app', HERE / 'app.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    app = module.app
    app.config.update(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_NAME='rfone_selection_local',
        RFONE_LOCAL_OPERATOR=username, TRUSTED_HOSTS=['127.0.0.1','localhost'])
    from flask import abort, redirect, request, session, send_file
    from rfone_data_store import rfone_web_session as shared

    def local_operator():
        if request.remote_addr not in ('127.0.0.1','::1') or request.host not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            abort(403)
        try:
            row = operator(username)
        except RuntimeError:
            abort(403)
        session[shared.SESSION_ACCOUNT_KEY] = row[0]
        session[shared.SESSION_VERSION_KEY] = row[3]
        if request.path == '/' and not request.script_root:
            return redirect('/selection/')
    app.before_request_funcs.setdefault(None, []).insert(0, local_operator)
    app.add_url_rule('/shared-brand/logos/rf-one.png', 'local_brand',
        lambda: send_file(HERE / 'static/brand/rf-one.png'))
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--enable-selection-for-admin', action='store_true')
    parser.add_argument('--port', type=int, default=5096)
    parser.add_argument('--operator', default='admin')
    parser.add_argument('--ai', action='store_true')
    parser.add_argument('--ai-cv', action='store_true')
    args = parser.parse_args()
    if args.enable_selection_for_admin and not args.initialize:
        parser.error('Il permesso può cambiare solo con --initialize.')
    if args.initialize:
        initialize(args.enable_selection_for_admin)
        return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            print(f'La porta {args.port} è già in uso. Selezione locale: http://127.0.0.1:{args.port}/selection/', flush=True)
            return
    app = create_application(args.port, args.operator, args.ai, args.ai_cv)
    print(f'Selezione: http://127.0.0.1:{args.port}/selection/ · database condiviso · operatore esistente {args.operator}', flush=True)
    from werkzeug.serving import run_simple
    run_simple('127.0.0.1', args.port, app, use_reloader=False, use_debugger=False, threaded=True)
