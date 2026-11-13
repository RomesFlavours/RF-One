"""Kitchen access and template checks; isolated in-memory database only."""
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
import sys

from flask import Flask, abort, send_from_directory
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent / 'RF-One Data Store'))
from kitchen_routes import register_kitchen_routes, allowed_tabs


def make_app(require_csrf=None):
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.exec_driver_sql('CREATE TABLE rfone_account_domain_access (account_id INTEGER, domain_code TEXT, enabled BOOLEAN, scope TEXT)')
        c.exec_driver_sql('CREATE TABLE rfone_account_domain_item_access (account_id INTEGER, domain_code TEXT, item_code TEXT)')
        c.exec_driver_sql("INSERT INTO rfone_account_domain_access VALUES (1,'KITCHEN',1,'ALL')")
    sessions = sessionmaker(engine)
    app = Flask(__name__, template_folder=str(APP_DIR/'templates'), static_folder=str(APP_DIR/'static'))
    app.config['ACCOUNT_ID'] = 1

    def account(db):
        return SimpleNamespace(id=app.config['ACCOUNT_ID'])

    def gate(code):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                with sessions() as db:
                    if not allowed_tabs(db, account(db)):
                        abort(403)
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    @app.get('/')
    def home():
        return 'Kitchen preview'

    @app.get('/shared-brand/logos/<path:filename>')
    def shared_brand_logo(filename):
        return send_from_directory(APP_DIR.parent/'Shared UI/brand/logos', filename)

    app.context_processor(lambda: {'brand_logo_filename': 'rf-one.png'})
    register_kitchen_routes(app, require_domain_access=gate, SessionFactory=sessions, load_current_account=account, require_csrf=require_csrf)
    return app, engine


def main():
    app, engine = make_app()
    from rfone_data_store.kitchen_configuration import items
    from rfone_data_store.kitchen import recipes,photos,components
    items.create(engine)
    recipes.create(engine)
    photos.create(engine)
    components.create(engine)
    app.context_processor(lambda:{'csrf_token':lambda:'test-csrf'})
    c = app.test_client()
    assert c.get('/kitchen').location.endswith('/kitchen/dashboard')
    dashboard = c.get('/kitchen/dashboard').text
    assert 'Dashboard' in dashboard and 'Recipes' in dashboard and 'How Kitchen works' in dashboard
    assert '<dialog' in dashboard and 'data-how-works' in dashboard
    assert '<main' in dashboard and '<h1>' not in dashboard
    recipes = c.get('/kitchen/recipes').text
    assert '<h1>Recipes and Preparations</h1>' in recipes and 'kitchen-recipes' in recipes
    with engine.begin() as db:
        db.exec_driver_sql("UPDATE rfone_account_domain_access SET scope='SELECTED'")
        db.exec_driver_sql("INSERT INTO rfone_account_domain_item_access VALUES (1,'KITCHEN','DASHBOARD')")
    assert 'href="/kitchen/recipes"' not in c.get('/kitchen/dashboard').text
    assert c.get('/kitchen/recipes').status_code == 403
    with engine.begin() as db:
        db.exec_driver_sql("UPDATE rfone_account_domain_item_access SET item_code='RECIPES'")
    assert c.get('/kitchen').location.endswith('/kitchen/recipes')
    assert c.get('/kitchen/dashboard').status_code == 403
    assert c.get('/kitchen/recipes').status_code == 200
    app.config['ACCOUNT_ID'] = 2
    assert all(c.get(path).status_code == 403 for path in ['/kitchen','/kitchen/dashboard','/kitchen/recipes'])
    engine.dispose()
    shared = APP_DIR.parent/'Shared UI/help/_how_works.html'
    assert shared.read_bytes() == (APP_DIR/'templates/_how_works.html').read_bytes()
    print('PASS: default tab, both templates/help, ALL/SELECTED grants, hidden tabs, direct access denial, no grants, identical shared help')


if __name__ == '__main__':
    main()
