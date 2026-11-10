"""Flask adapters for the shared Registry policy; no cached grants in cookies."""
from flask import g, session as browser_session
from . import access_profiles as profiles, rfone_web_session as shared


def install_access_context(app, session_factory, account_loader=None):
    """Resolve the validated company before every domain/blueprint gate."""
    if app.extensions.get("registry_access_context"):
        return
    app.extensions["registry_access_context"] = True
    @app.after_request
    def protect_authorized_response(response):
        # A permission-dependent page must be rechecked after a Registry change.
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

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
