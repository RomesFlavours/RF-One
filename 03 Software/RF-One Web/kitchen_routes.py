"""Kitchen shell and editor registration using existing account Domain/item grants."""
from flask import abort, redirect, render_template, url_for
from sqlalchemy import inspect, text


TABS = (('DASHBOARD', 'Dashboard', 'kitchen_dashboard'),
        ('RECIPES', 'Recipes and Preparations', 'kitchen_recipes'),
        ('CONFIGURATION', 'Configuration', 'kitchen_configuration'))


def allowed_tabs(db, account):
    """Reuse ALL/SELECTED item access, including older pre-item schemas."""
    from rfone_data_store import rfone_web_session as shared
    items = shared.allowed_domain_items(db, account, 'KITCHEN', [tab[0] for tab in TABS])
    return [tab for tab in TABS if tab[0] in items]



def register_kitchen_routes(app, *, require_domain_access, SessionFactory, load_current_account, require_csrf=None):
    gate = require_domain_access('KITCHEN')
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

