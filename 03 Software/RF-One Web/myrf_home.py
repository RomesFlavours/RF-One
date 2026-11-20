"""Local navigation parity with the verified published RF-One shell.

Installed explicitly by loopback launchers. No migrations, seed data or network
calls run here. Existing grants and company memberships remain authoritative.
"""
from flask import abort, g, redirect, render_template, request, url_for

from domain_registry import DOMAINS, DOMAINS_BY_CODE, SELECTION_OLD_LINK
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store import rfone_web_session as shared

DOMAIN_LABELS = {
    'COMPENSATION': ('Compensi', 'Prepara, verifica e approva i compensi; comunica i risultati al servizio paghe e riconcilia gli esiti.'),
    'KITCHEN': ('Cucina', 'Ricette, preparazioni, componenti e impiattamento standard.'),
    'ORGANIZATION': ('Organizzazione', 'Posizioni, titolari e sostituti, responsabilità dei processi e gestione delle segnalazioni.'),
    'PROJECTS': ('Gestione progetti', 'Progetti con capitoli, attività, sottoattività, prerequisiti e diagramma di Gantt stampabile.'),
    'SELECTION': ('Selezione', 'Valutazione dei candidati, interviste e decisioni di assunzione.'),
    'TIPS': ('Mance', 'Configurazione delle regole di distribuzione e calcolo delle mance.'),
    'TRAINING': ('Formazione', 'Conoscenza di piatti e vini, verifiche e percorsi di apprendimento assegnati.'),
    'WINES': ('Vini', 'Tipi di vino, catalogo dei vini acquistabili e carte dei vini con i prezzi di ogni entità.'),
}


def install(app, *, SessionFactory, auth, require_domain_access):
    if app.extensions.get('myrf_local_home'):
        return
    app.extensions['myrf_local_home'] = True
    from role_profile_routes import register_role_profile_routes
    from employee_directory_routes import register_employee_directory_routes
    from projects_routes import register_projects_routes
    from dev_journal_routes import register_dev_journal_routes
    from interview_routes import home_state

    register_role_profile_routes(app, SessionFactory=SessionFactory,
        require_admin=auth.require_admin, load_current_account=auth.load_current_account,
        require_csrf=auth.require_csrf, domains=DOMAINS)
    register_employee_directory_routes(app, SessionFactory=SessionFactory,
        require_domain_access=require_domain_access, load_current_account=auth.load_current_account,
        require_csrf=auth.require_csrf)
    register_projects_routes(app, SessionFactory=SessionFactory,
        require_domain_access=require_domain_access, require_csrf=auth.require_csrf)
    register_dev_journal_routes(app, SessionFactory=SessionFactory,
        require_domain_access=require_domain_access, load_current_account=auth.load_current_account,
        require_csrf=auth.require_csrf)

    def allowed_items(code):
        cache = g.setdefault('rfone_allowed_items', {})
        if code not in cache:
            domain = DOMAINS_BY_CODE[code]
            with SessionFactory() as db:
                allowed = shared.allowed_domain_items(db, auth.load_current_account(db),
                    code, [item.code for item in domain.items])
            cache[code] = [item for item in domain.items if item.code in allowed]
        return cache[code]

    def domain_entry(code):
        domain = DOMAINS_BY_CODE[code]
        if not domain.items:
            return domain.link
        items = allowed_items(code)
        return url_for(items[0].endpoint) if items else None

    app.jinja_env.globals.update(
        home_domain_name=lambda code, default: DOMAIN_LABELS.get(code, (default, ''))[0],
        home_domain_description=lambda code, default: DOMAIN_LABELS.get(code, ('', default))[1],
        domain_entry=domain_entry, selection_old_link=SELECTION_OLD_LINK,
        domain_nav=lambda code: [(i.code, i.label, url_for(i.endpoint)) for i in allowed_items(code)],
        may_use_item=lambda code, item: any(i.code == item for i in allowed_items(code)),
    )

    @auth.require_login
    def home():
        with SessionFactory() as db:
            account = auth.load_current_account(db)
            if account is None:
                auth.log_out()
                return redirect(url_for('login'))
            enabled = {row.domain_code for row in accounts.list_domain_access_for_account(db, account.id)
                       if row.enabled}
            separate = {'BANK', 'CLOVER_ACQUISITION', 'EMPLOYEES', 'DEV_JOURNAL',
                        'MYRF', 'AI_ORGANIZATION'}
            domains = sorted((d for d in DOMAINS if d.code in enabled and d.code not in separate),
                             key=lambda d: d.display_name.casefold())
            return render_template('home_local.html', account=account, domains_view=domains,
                work_in_progress_codes=frozenset(), bank_available='BANK' in enabled,
                clover_acquisition_available='CLOVER_ACQUISITION' in enabled,
                employees_available='EMPLOYEES' in enabled,
                dev_journal_available='DEV_JOURNAL' in enabled, **home_state(db, account))

    app.view_functions['home'] = home

    # Enforce the same selected-item restrictions that choose Home destinations.
    @app.before_request
    def local_item_access():
        for domain in DOMAINS:
            item = domain.item_for_path(request.path)
            if item is not None:
                with SessionFactory() as db:
                    account = auth.load_current_account(db)
                    if account is not None and not shared.account_may_use_domain_item(db, account, domain.code, item.code):
                        abort(403)
                break
