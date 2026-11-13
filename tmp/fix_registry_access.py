from pathlib import Path
base=Path(r'C:\Users\servi\.codex\worktrees\edee\RF One\tmp\git-anagrafica-release\03 Software')
def edit(file,old,new):
 p=base/file;s=p.read_text(encoding='utf-8');assert old in s,(file,old[:70]);p.write_text(s.replace(old,new),encoding='utf-8',newline='\n')
(base/'RF-One Data Store/rfone_data_store/web_access.py').write_text('''"""Flask adapters for the shared Registry policy; no cached grants in cookies."""
from flask import g, session as browser_session
from . import access_profiles as profiles, rfone_web_session as shared


def install_access_context(app, session_factory, account_loader=None):
    """Resolve the validated company before every domain/blueprint gate."""
    if app.extensions.get("registry_access_context"):
        return
    app.extensions["registry_access_context"] = True
    def resolve_company():
        with session_factory() as db:
            account = account_loader(db) if account_loader else shared.account_for_session(
                db, account_id=browser_session.get(shared.SESSION_ACCOUNT_KEY),
                session_version=browser_session.get(shared.SESSION_VERSION_KEY))
            allowed = profiles.company_ids_for_account(db, account.id) if account else set()
            chosen = browser_session.get("rfone_company_context")
            if chosen not in allowed:
                chosen = min(allowed) if allowed else None
            g.registry_company_token = profiles.company_context.set(chosen)
    app.before_request_funcs.setdefault(None, []).insert(0, resolve_company)
    @app.teardown_request
    def release_company(error):
        token = g.pop("registry_company_token", None)
        if token is not None:
            profiles.company_context.reset(token)


class AuthorizedTrainingAccount:
    """Request-only role view. The domain identity/history is never rewritten."""
    def __init__(self, account, role):
        self._account, self.role = account, role
    def __getattr__(self, name):
        return getattr(self._account, name)


def training_account_for_rf1(db, account):
    from . import models as m, rfone_account_service as accounts
    if account is None:
        return None
    grants = accounts.list_domain_access_for_account(db, account.id)
    grant = next((r for r in grants if r.domain_code == "TRAINING" and r.enabled), None)
    role = accounts.normalize_role_code(grant.role_code) if grant else None
    if role == accounts.DOMAIN_ADMIN_ROLE:
        role = "trainer"
    if role not in ("trainer", "student"):
        return None
    link = db.query(m.RFOneTrainingIdentityLink).filter_by(rfone_account_id=account.id).first()
    identity = db.get(m.TrainingAccount, link.training_account_id) if link else None
    return AuthorizedTrainingAccount(identity, role) if identity else None
''',encoding='utf-8')
p=base/'RF-One Web/role_profile_routes.py';s=p.read_text();start=s.index('    @app.before_request');end=s.index('    @app.context_processor',start);s=s[:start]+'''    from rfone_data_store.web_access import install_access_context
    install_access_context(app, SessionFactory, load_current_account)

'''+s[end:];p.write_text(s,encoding='utf-8',newline='\n')
edit(Path('RF-One Web/templates/home.html'),'or can_manage_profiles %}','or can_manage_profiles or employees_available %}')
edit(Path('RF-One Web/templates/home.html'),'''      {% endif %}
      {% if bank_available %}''','''      {% elif employees_available %}
      <a class="home-row" href="{{ url_for('employee_directory_home') }}"><strong>Registry</strong> &mdash; People directory.</a>
      {% endif %}
      {% if bank_available %}''')
p=base/'RF-One Web/training_integration.py';s=p.read_text();start=s.index('    if training_account.role != role_code:');end=s.index('\n\n\ndef _role_mismatch_response',start);s=s[:start]+'''    from rfone_data_store.web_access import AuthorizedTrainingAccount
    return TrainingAuthorizationResult(AuthorizedTrainingAccount(training_account, role_code), None)'''+s[end:];start=s.index('    candidates = session.query(m.RFOneAccount).join(',s.index('def list_training_students'));end=s.index('    return [a for a in candidates',start);s=s[:start]+'''    candidates = session.query(m.RFOneAccount).filter(
        m.RFOneAccount.status == "ACTIVE"
    ).order_by(m.RFOneAccount.display_name).all()
'''+s[end:];s=s.replace('        flask_session[TRAINING_SESSION_ACCOUNT_KEY] = result.training_account.id','''        from flask import g
        g.rfone_training_account = result.training_account
        flask_session[TRAINING_SESSION_ACCOUNT_KEY] = result.training_account.id''');p.write_text(s,encoding='utf-8',newline='\n')
edit(Path('Training/auth.py'),'from flask import abort, redirect, request, session as flask_session, url_for','from flask import abort, redirect, request, session as flask_session, url_for, g, current_app')
edit(Path('Training/auth.py'),'''    account_id = current_account_id()
    if account_id is None:''','''    if current_app.extensions.get("rfone_managed_training"):
        from rfone_data_store import rfone_web_session as shared
        from rfone_data_store.web_access import training_account_for_rf1
        account = shared.account_for_session(db_session,
            account_id=flask_session.get(shared.SESSION_ACCOUNT_KEY),
            session_version=flask_session.get(shared.SESSION_VERSION_KEY))
        return training_account_for_rf1(db_session, account)
    effective = getattr(g, "rfone_training_account", None)
    if effective is not None:
        return effective
    account_id = current_account_id()
    if account_id is None:''')
edit(Path('Training/auth.py'),'''        if current_account_id() is None:
            return redirect''','''        if current_app.extensions.get("rfone_managed_training"):
            with SessionFactory() as db:
                if load_current_account(db) is None:
                    abort(403)
        elif current_account_id() is None:
            return redirect''')
edit(Path('Tips/app.py'),'''        if rfone_identity.current_account(db_session) is not None:
            return None''','''        account = rfone_identity.current_account(db_session)
        if account is not None:
            if not shared_session.account_may_enter_domain(db_session, account, "TIPS"):
                abort(403)
            return None''')
edit(Path('Tips/app.py'),'app = Flask(__name__)','''app = Flask(__name__)
from rfone_data_store.web_access import install_access_context
install_access_context(app, SessionFactory)
app.extensions["rfone_managed_training"] = True''')
edit(Path('Selection/app.py'),'run_migrations_to_head(_DB_URL)','# Schema migrations are an explicit release operation, never an import side effect.')
edit(Path('Selection/app.py'),'app = Flask(__name__)','''app = Flask(__name__)
from rfone_data_store.web_access import install_access_context
install_access_context(app, SessionFactory)''')
print('Patched shared company context, Tips/Selection and Training effective roles.')
