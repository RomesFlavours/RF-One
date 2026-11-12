"""Kitchen shell and editor registration using existing account Domain/item grants."""
from flask import abort, redirect, render_template, url_for
from sqlalchemy import inspect, text


TABS = (('DASHBOARD', 'Dashboard', 'kitchen_dashboard'),
        ('MENU', 'Menu', 'kitchen_menus'),
        ('RECIPES', 'Recipes and Preparations', 'kitchen_recipes'),
        ('CONFIGURATION', 'Configuration', 'kitchen_configuration'))


def allowed_tabs(db, account):
    """Reuse ALL/SELECTED item access, including older pre-item schemas."""
    from flask import current_app,has_request_context
    if has_request_context() and current_app.config.get('RFONE_LOCAL_OPERATOR'):
        from local_operator_session import local_admin_preview
        if local_admin_preview(account):return list(TABS)
    columns = {c['name'] for c in inspect(db.get_bind()).get_columns('rfone_account_domain_access')}
    scope_column = 'scope' if 'scope' in columns else "'ALL' AS scope"
    grant = db.execute(text(f'SELECT enabled, {scope_column} FROM rfone_account_domain_access '
                            'WHERE account_id=:account AND domain_code=:domain'),
                       {'account': account.id, 'domain': 'KITCHEN'}).mappings().first()
    if not grant or not grant['enabled']:
        return []
    if grant['scope'] == 'ALL':
        return list(TABS)
    if grant['scope'] != 'SELECTED':
        return []
    items = set(db.execute(text('SELECT item_code FROM rfone_account_domain_item_access '
                               'WHERE account_id=:account AND domain_code=:domain'),
                           {'account': account.id, 'domain': 'KITCHEN'}).scalars())
    return [tab for tab in TABS if tab[0] in items]


def register_kitchen_routes(app, *, require_domain_access, SessionFactory, load_current_account, require_csrf=None):
    gate = require_domain_access('KITCHEN')
    from kitchen_menu_routes import register_menu_routes
    register_menu_routes(app,gate=gate,SessionFactory=SessionFactory,
        load_current_account=load_current_account,allowed_tabs=allowed_tabs,require_csrf=require_csrf)
    from kitchen_recipe_routes import register_recipe_routes
    register_recipe_routes(app,gate=gate,SessionFactory=SessionFactory,
        load_current_account=load_current_account,allowed_tabs=allowed_tabs,require_csrf=require_csrf)
    from kitchen_configuration_routes import register_configuration_routes
    register_configuration_routes(app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, allowed_tabs=allowed_tabs, require_csrf=require_csrf)

    def page(code):
        with SessionFactory() as db:
            account = load_current_account(db)
            if account is None:
                abort(403)
            tabs = allowed_tabs(db, account)
        if not any(tab[0] == code for tab in tabs):
            abort(403)
        return render_template('kitchen_dashboard.html' if code == 'DASHBOARD' else 'kitchen_recipes.html',
                               kitchen_tabs=tabs, active_tab=code, ui=lambda value: value)

    @app.get('/kitchen')
    @gate
    def kitchen_home():
        with SessionFactory() as db:
            account = load_current_account(db)
            tabs = allowed_tabs(db, account) if account else []
        if not tabs:
            abort(403)
        return redirect(url_for(tabs[0][2]))

    @app.get('/kitchen/dashboard')
    @gate
    def kitchen_dashboard():
        return page('DASHBOARD')

