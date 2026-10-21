"""Explicit demo setup and loopback server. Never loads .env or remote DBs."""
from pathlib import Path
import argparse
import os
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIR = ROOT / 'output' / 'ai-organization'
DATABASE = LOCAL_DIR / 'ai-organization-local.sqlite3'
# These assignments MUST precede imports of the shell database/auth modules.
os.environ['RFONE_DATABASE_URL'] = 'sqlite:///' + DATABASE.as_posix()
sys.path.insert(0, str(ROOT / '03 Software' / 'RF-One Data Store'))

from flask import Flask, redirect, url_for, abort
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from db import SessionFactory, _engine
from auth import get_csrf_token, require_csrf, log_in, log_out, require_login, load_current_account
from rfone_data_store import models as m
from rfone_data_store import ai_organization as svc
from rfone_data_store.rfone_web_session import account_may_enter_domain
from ai_organization_routes import register_ai_organization_routes


def initialize():
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    # Explicit isolated demo initialization only; never on import or normal boot.
    m.Base.metadata.create_all(_engine)
    with SessionFactory() as db:
        account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == 'demo'))
        if not account:
            account = m.RFOneAccount(username='demo', display_name='Responsabile demo',
                password_hash=generate_password_hash('Organization-demo-2026!'), status='ACTIVE', is_admin=False)
            db.add(account)
            db.flush()
            db.add(m.RFOneAccountDomainAccess(account_id=account.id, domain_code='AI_ORGANIZATION', enabled=True))
        entity = db.scalar(select(m.LegalEntity).where(m.LegalEntity.legal_name == 'Azienda dimostrativa · Mount Dora'))
        if not entity:
            entity = m.LegalEntity(legal_name='Azienda dimostrativa · Mount Dora', status='ACTIVE')
            db.add(entity)
            db.flush()
            position = svc.org.create_position(db, name='Presidio operativo demo', description='Responsabilità dimostrativa esistente; posizione ancora da coprire.')
            svc.org.add_position_scope(db, position=position, scope_type='LEGAL_ENTITY', scope_id=entity.id)
        if not db.get(svc.CompanyGrant, (account.id, entity.id)):
            db.add(svc.CompanyGrant(account_id=account.id, entity_id=entity.id, can_apply=True))
        db.commit()


def create_app(*, use_ai=False):
    if not DATABASE.exists():
        raise RuntimeError('Esegui prima: python ai_organization_local.py --init')
    app = Flask(__name__)
    key_path = LOCAL_DIR / 'session.key'
    if not key_path.exists():
        key_path.write_text(secrets.token_hex(32), encoding='ascii')
    app.secret_key = key_path.read_text(encoding='ascii')
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_NAME='rfone_ai_organization_local', MAX_CONTENT_LENGTH=150000,
        TRUSTED_HOSTS=['127.0.0.1', 'localhost'], TEMPLATES_AUTO_RELOAD=True)
    app.jinja_env.globals['csrf_token'] = get_csrf_token

    @app.before_request
    def local_demo_identity():
        # Explicit Product Owner instruction: no credential prompt in local demo.
        # This factory is loopback-only and forces the isolated synthetic DB.
        # The production shell/authentication is untouched.
        with SessionFactory() as db:
            account = load_current_account(db)
            if account is None:
                demo = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == 'demo', m.RFOneAccount.status == 'ACTIVE'))
                if demo is None:
                    abort(503, description='Inizializza prima il database dimostrativo locale.')
                log_in(demo.id, demo.session_version)
    if use_ai:
        from rfone_data_store.ai_organization_provider import existing_direct_provider
        if not os.environ.get('ANTHROPIC_API_KEY', '').strip():
            raise RuntimeError('Per --ai imposta ANTHROPIC_API_KEY nell’ambiente locale; AWS non è consentito.')
        app.config['AI_ORGANIZATION_PROVIDER'] = existing_direct_provider

    def require_domain_access(code):
        def decorate(view):
            from functools import wraps
            @wraps(view)
            @require_login
            def wrapped(*args, **kwargs):
                with SessionFactory() as db:
                    account = load_current_account(db)
                    if not account or not account_may_enter_domain(db, account, code):
                        abort(403)
                return view(*args, **kwargs)
            return wrapped
        return decorate

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        return redirect(url_for('ai_organization'))

    @app.get('/')
    def home():
        return redirect(url_for('ai_organization'))

    @app.post('/logout')
    def logout():
        require_csrf()
        log_out()
        return redirect(url_for('login'))

    register_ai_organization_routes(app, SessionFactory=SessionFactory,
        require_domain_access=require_domain_access, require_csrf=require_csrf)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--ai', action='store_true', help='Provider diretto esistente, solo con dati demo; mai AWS')
    args = parser.parse_args()
    if args.init:
        initialize()
        print('Database dimostrativo inizializzato:', DATABASE)
    else:
        create_app(use_ai=args.ai).run(host='127.0.0.1', port=5091, debug=False, use_reloader=False)
