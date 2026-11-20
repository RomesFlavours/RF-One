"""RF-One Web ↔ Training single-login integration.

Mounts Training's EXISTING blueprint (`03 Software/Training/routes.py`)
onto this application unchanged — zero modifications to any Training file
— and adds the one thing Training's own code cannot know about itself:
that a request already carries a trusted RF-One identity, so Training must
never show its own login form for it.

How single sign-on works here (no second login):
  1. `install_training_blueprint()` loads Training's `routes.py` (and, via
     its own imports, `auth.py`/`db.py`/`dish_data.py`) from a brand-new
     module namespace, so it never collides with this application's OWN
     `auth`/`db` modules of the same plain names — Training's routes.py
     does `from auth import ...`/`from db import ...` and must resolve
     those to ITS OWN files, not this app's. Training's routes/decorators
     are otherwise used exactly as-is.
  2. `enforce_training_sso()`, called from an `app.before_request` hook
     scoped to the `training` blueprint, re-verifies on EVERY request
     (never cached in the session) that the CURRENT RF-One session belongs
     to an ACTIVE `RFOneAccount` with an enabled `TRAINING`
     `RFOneAccountDomainAccess` row and a valid `role_code`
     ('trainer'/'student' — the exact values Training's own
     `TrainingAccount.role` check constraint already accepts, so this is
     never a second, independently-maintained role vocabulary). Only then
     does it write Training's OWN session key
     (`training_account_id`, matching `Training/auth.py`'s
     `SESSION_ACCOUNT_KEY` exactly) — never by calling Training's `log_in()`
     (which clears the WHOLE shared session, including RF-One's own key).
     If anything is missing or invalid, any stray Training session key is
     removed and the request is redirected — a leftover/tampered Training
     session can never substitute for a real RF-One login.
  3. Because RF-One Web's own `/logout` clears the entire Flask session
     (`auth.log_out()` -> `flask_session.clear()`), it removes Training's
     session key too, for free — logging out of RF-One always logs out of
     Training in the same request.

`role_code` is authoritative for this integration: whenever it disagrees
with the linked `TrainingAccount.role`, this module overwrites the latter
to match, every time the gate runs — so there is exactly one place
(`RFOneAccountDomainAccess.role_code`, via `/admin/accounts/<id>/access`)
where a Training role is ever set for an RF-One-integrated account, never
two independently-editable roles.
"""

from __future__ import annotations

import importlib
import os
import secrets
import sys

from dataclasses import dataclass
from functools import wraps

from flask import abort, flash, redirect, request, session as flask_session, url_for

from rfone_data_store import models as m
from rfone_data_store import rfone_account_service as account_service
from rfone_data_store.training import service as training_service

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TRAINING_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Training"))

TRAINING_DOMAIN_CODE = "TRAINING"
# Must match Training/auth.py's own SESSION_ACCOUNT_KEY exactly — this is
# the ONE shared contract this integration relies on with Training's
# unmodified code.
TRAINING_SESSION_ACCOUNT_KEY = "training_account_id"
VALID_TRAINING_ROLE_CODES = ("trainer", "student")


def install_training_blueprint():
    """Loads Training's `routes.py` (hence its `auth`/`db`/`dish_data`)
    into fresh, uniquely-named modules so its internal
    `from auth import ...` / `from db import ...` resolve to ITS OWN files
    even though this application already has its own `auth`/`db` modules
    loaded under those exact plain names. Returns Training's unmodified
    `training_bp` Blueprint, ready to register.

    Training's view functions bind `auth.require_login`, `db.SessionFactory`
    etc. as plain names AT IMPORT TIME (`from auth import require_login`),
    so once this function returns, nothing later needs to keep juggling
    `sys.modules` — the blueprint's routes already hold direct references
    to the correct function/session-factory objects."""

    if _TRAINING_DIR not in sys.path:
        sys.path.insert(0, _TRAINING_DIR)

    # Save whatever this application's OWN 'auth'/'db' modules currently
    # occupy in sys.modules, so Training's fresh imports of those same
    # plain names don't see them (and so we can restore them afterward for
    # anything else that later does `import auth`/`import db` expecting
    # THIS app's own).
    saved_modules = {
        name: sys.modules.pop(name, None) for name in ("auth", "db", "dish_data", "routes")
    }

    try:
        training_routes_module = importlib.import_module("routes")
        training_bp = training_routes_module.training_bp
    finally:
        # Rename Training's freshly-loaded modules out of the generic
        # names so they don't linger there, then restore this
        # application's own.
        for name in ("auth", "db", "dish_data", "routes"):
            loaded = sys.modules.pop(name, None)
            if loaded is not None:
                sys.modules[f"_training_internal_{name}"] = loaded
        for name, previous in saved_modules.items():
            if previous is not None:
                sys.modules[name] = previous
        if _TRAINING_DIR in sys.path:
            sys.path.remove(_TRAINING_DIR)

    return training_bp


@dataclass(frozen=True)
class TrainingAuthorizationResult:
    training_account: "m.TrainingAccount | None"
    error: str | None
    role_mismatch: bool = False


def check_training_authorization(session, rfone_account: "m.RFOneAccount") -> TrainingAuthorizationResult:
    """Re-verifies (every call — never cached) that `rfone_account` may
    enter Training right now. READ-ONLY: never writes to the database —
    a navigation check (GET or otherwise) must never have a side effect on
    `TrainingAccount.role`. If the linked `TrainingAccount.role` disagrees
    with `RFOneAccountDomainAccess.role_code`, this is reported as
    `role_mismatch=True` rather than silently corrected — only an explicit,
    authorized POST (see `sync_training_role_if_linked`,
    `link_existing_training_account`, `create_and_link_training_identity`)
    may ever write that column."""

    access_rows = account_service.list_domain_access_for_account(session, rfone_account.id)
    access = next((r for r in access_rows if r.domain_code == TRAINING_DOMAIN_CODE), None)
    if access is None or not access.enabled:
        return TrainingAuthorizationResult(None, "Il tuo account RF-One non ha accesso al Domain Training.")

    role_code = access.role_code
    if role_code not in VALID_TRAINING_ROLE_CODES:
        return TrainingAuthorizationResult(
            None, "Il tuo accesso a Training non ha un ruolo valido assegnato. Contatta un amministratore.",
        )

    link = session.query(m.RFOneTrainingIdentityLink).filter(
        m.RFOneTrainingIdentityLink.rfone_account_id == rfone_account.id
    ).first()
    if link is None:
        return TrainingAuthorizationResult(
            None, "Il tuo account non ha ancora un'identità Training collegata. Contatta un amministratore.",
        )

    training_account = session.get(m.TrainingAccount, link.training_account_id)
    if training_account is None:
        return TrainingAuthorizationResult(
            None, "L'identità Training collegata non è più valida. Contatta un amministratore.",
        )

    if training_account.role != role_code:
        return TrainingAuthorizationResult(
            None,
            "Il ruolo Training del tuo account non è coerente. Contatta un amministratore per correggerlo.",
            role_mismatch=True,
        )

    return TrainingAuthorizationResult(training_account, None)


def _role_mismatch_response(message: str):
    """A direct 403 body — never a redirect, so an incoherent-role account
    can never be caught in a redirect loop (task §3)."""
    return f"<h1>403 Forbidden</h1><p>{message}</p>", 403


def enforce_training_sso(app_auth_module, session_factory) -> "object | None":
    """Call from `app.before_request`. Returns a Flask response to
    short-circuit the request (redirect or 403), or `None` to let it
    proceed with `flask.session[TRAINING_SESSION_ACCOUNT_KEY]` already set
    correctly. Purely a read-only check — see
    `check_training_authorization`."""

    if request.blueprint != "training":
        return None

    with session_factory() as db:
        account = app_auth_module.load_current_account(db)
        if account is None or account.status != "ACTIVE":
            flask_session.pop(TRAINING_SESSION_ACCOUNT_KEY, None)
            flash("Effettua l'accesso a RF-One per continuare.", "error")
            return redirect(url_for("login", next=request.path))

        result = check_training_authorization(db, account)

        if result.role_mismatch:
            flask_session.pop(TRAINING_SESSION_ACCOUNT_KEY, None)
            return _role_mismatch_response(result.error)

        if result.training_account is None:
            flask_session.pop(TRAINING_SESSION_ACCOUNT_KEY, None)
            flash(result.error, "error")
            return redirect(url_for("home"))

        flask_session[TRAINING_SESSION_ACCOUNT_KEY] = result.training_account.id

    return None


def require_training_trainer(app_auth_module, session_factory):
    """Decorator factory for RF-One Web's OWN routes (not Training's) that
    need "this account currently has the Training trainer role" — e.g. the
    RF-One-side student-creation flow. Deliberately independent of
    `auth.require_admin` (task: "Essere amministratore RF-One NON assegna
    automaticamente accesso o ruolo addestratore in Training"). Read-only,
    same as `enforce_training_sso` — see `check_training_authorization`."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if app_auth_module.current_account_id() is None:
                return redirect(url_for("login", next=request.path))
            with session_factory() as db:
                account = app_auth_module.load_current_account(db)
                if account is None or account.status != "ACTIVE":
                    app_auth_module.log_out()
                    return redirect(url_for("login", next=request.path))
                result = check_training_authorization(db, account)
                if result.role_mismatch:
                    flask_session.pop(TRAINING_SESSION_ACCOUNT_KEY, None)
                    return _role_mismatch_response(result.error)
                if result.training_account is None or result.training_account.role != "trainer":
                    abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Admin: linking an existing Training identity, or creating a new one
# ---------------------------------------------------------------------------


def get_link_for_rfone_account(session, rfone_account_id: int) -> "m.RFOneTrainingIdentityLink | None":
    return session.query(m.RFOneTrainingIdentityLink).filter(
        m.RFOneTrainingIdentityLink.rfone_account_id == rfone_account_id
    ).first()


def list_unlinked_training_accounts(session) -> list["m.TrainingAccount"]:
    """Existing `TrainingAccount` rows not yet linked to any `RFOneAccount`
    — the explicit selection list an admin picks from (task: "impedendo
    collegamenti duplicati o sostituzioni silenziose")."""
    linked_ids = {
        row.training_account_id
        for row in session.query(m.RFOneTrainingIdentityLink.training_account_id).all()
    }
    # Training's own service module only exposes list_all_students() (no
    # trainer-listing helper), so this reads the model directly — read-only,
    # no new Training behavior introduced.
    accounts = session.query(m.TrainingAccount).order_by(m.TrainingAccount.username).all()
    return [a for a in accounts if a.id not in linked_ids]


class AlreadyLinkedError(ValueError):
    pass


def sync_training_role_if_linked(session, rfone_account_id: int, role_code: str | None) -> None:
    """The ONLY place `TrainingAccount.role` is written outside account/
    identity creation — call exclusively from an explicit, authorized POST
    that assigns/changes an already-linked account's TRAINING `role_code`
    (task §2, first bullet). Does nothing (no error, no write) if the
    account has no linked `TrainingAccount` yet — never creates one as a
    side effect — and does nothing for an invalid/missing `role_code`.
    Runs unconditionally whenever called with a valid `role_code`, even if
    it equals the value already stored (task §4: fixing a pre-existing
    incoherence must not depend on the RF-One value actually changing)."""
    if role_code not in VALID_TRAINING_ROLE_CODES:
        return
    link = get_link_for_rfone_account(session, rfone_account_id)
    if link is None:
        return
    training_account = session.get(m.TrainingAccount, link.training_account_id)
    if training_account is not None:
        training_account.role = role_code
        session.flush()


def link_existing_training_account(session, *, rfone_account_id: int, training_account_id: int) -> "m.RFOneTrainingIdentityLink":
    """Explicit admin action — never automatic, never by matching
    display_name/username. If the RF-One account already has a valid
    TRAINING `role_code` at link time, syncs the newly-linked
    `TrainingAccount.role` to match, in the SAME flush/transaction (task
    §2, second bullet) — never touches any OTHER, unlinked account."""
    if get_link_for_rfone_account(session, rfone_account_id) is not None:
        raise AlreadyLinkedError("Questo account RF-One è già collegato a un'identità Training.")
    existing_for_training = session.query(m.RFOneTrainingIdentityLink).filter(
        m.RFOneTrainingIdentityLink.training_account_id == training_account_id
    ).first()
    if existing_for_training is not None:
        raise AlreadyLinkedError("Questa identità Training è già collegata a un altro account RF-One.")

    link = m.RFOneTrainingIdentityLink(rfone_account_id=rfone_account_id, training_account_id=training_account_id)
    session.add(link)

    access_rows = account_service.list_domain_access_for_account(session, rfone_account_id)
    training_access = next((r for r in access_rows if r.domain_code == TRAINING_DOMAIN_CODE), None)
    if training_access is not None and training_access.role_code in VALID_TRAINING_ROLE_CODES:
        training_account = session.get(m.TrainingAccount, training_account_id)
        training_account.role = training_access.role_code

    session.flush()
    return link


def create_and_link_training_identity(
    session, *, rfone_account_id: int, role_code: str,
) -> "m.RFOneTrainingIdentityLink":
    """The "enablement" flow (task §2): for an `RFOneAccount` with no
    Training identity yet, creates one — WITHOUT a second password. The
    `TrainingAccount.password_hash` column is structurally required
    (existing, FROZEN schema) but is never used for authentication in this
    integration (Training is only ever entered via RF-One SSO here), so a
    random, unknown, immediately-discarded value satisfies it."""
    if role_code not in VALID_TRAINING_ROLE_CODES:
        raise ValueError(f"Invalid role_code {role_code!r} — must be one of {VALID_TRAINING_ROLE_CODES}")
    if get_link_for_rfone_account(session, rfone_account_id) is not None:
        raise AlreadyLinkedError("Questo account RF-One è già collegato a un'identità Training.")

    rfone_account = session.get(m.RFOneAccount, rfone_account_id)
    if rfone_account is None:
        raise ValueError("RFOneAccount not found")

    training_account = training_service.create_account(
        session, display_name=rfone_account.display_name, username=rfone_account.username,
        password=secrets.token_urlsafe(32), role=role_code,
    )
    link = m.RFOneTrainingIdentityLink(rfone_account_id=rfone_account_id, training_account_id=training_account.id)
    session.add(link)
    session.flush()
    return link


# ---------------------------------------------------------------------------
# Trainer-facing: creating a brand-new student from within RF-One Web
# ---------------------------------------------------------------------------


class StudentCreationError(ValueError):
    pass


def is_pure_training_student(session, rfone_account: "m.RFOneAccount") -> bool:
    """True only for an RF-One account that is NOT an admin and has NO
    Domain access other than an enabled TRAINING/'student' row — the exact
    population a Training trainer may reset the RF-One password of (task:
    "Non consentire all'addestratore di resettare credenziali di
    amministratori o account con privilegi in altri Domain")."""
    if rfone_account.is_admin:
        return False
    access_rows = account_service.list_domain_access_for_account(session, rfone_account.id)
    enabled_rows = [r for r in access_rows if r.enabled]
    if len(enabled_rows) != 1:
        return False
    row = enabled_rows[0]
    return row.domain_code == TRAINING_DOMAIN_CODE and row.role_code == "student"


def list_training_students(session) -> list["m.RFOneAccount"]:
    """All RF-One accounts a Training trainer may see/manage in this
    integration — pure Training students only (see
    `is_pure_training_student`)."""
    candidates = session.query(m.RFOneAccount).join(
        m.RFOneAccountDomainAccess, m.RFOneAccountDomainAccess.account_id == m.RFOneAccount.id,
    ).filter(
        m.RFOneAccountDomainAccess.domain_code == TRAINING_DOMAIN_CODE,
        m.RFOneAccountDomainAccess.role_code == "student",
        m.RFOneAccountDomainAccess.enabled.is_(True),
    ).order_by(m.RFOneAccount.display_name).all()
    return [a for a in candidates if is_pure_training_student(session, a)]


def create_student_via_rf_one(
    session, *, username: str, display_name: str, password: str, email: str,
) -> tuple["m.RFOneAccount", "m.TrainingAccount"]:
    """Atomically provisions an RF-One-loginable student: an `RFOneAccount`
    (never admin, never any Domain but TRAINING), its `TRAINING`
    `RFOneAccountDomainAccess` (role_code='student'), a linked
    `TrainingAccount` (Training's own required password column filled with
    a random, unused placeholder — the account only ever logs in via
    RF-One), and the identity link. `password` here becomes the account's
    real, sole (RF-One) password. `email` is required (task: "richiedi
    l'email nei flussi di creazione, compreso quello degli studenti
    Training") and recorded unverified — the caller is responsible for
    sending the verification code (`app.py`'s
    `training_trainer_new_student` route), never this module, which knows
    nothing about email delivery."""
    try:
        rfone_account = account_service.create_account(
            session, username=username, display_name=display_name, password=password,
            status="ACTIVE", is_admin=False, email=email,
        )
    except account_service.UsernameTakenError as exc:
        raise StudentCreationError(str(exc)) from exc

    account_service.set_domain_access(
        session, account_id=rfone_account.id, domain_code=TRAINING_DOMAIN_CODE, enabled=True, role_code="student",
    )

    try:
        training_account = training_service.create_account(
            session, display_name=display_name, username=username,
            password=secrets.token_urlsafe(32), role="student",
        )
    except training_service.UsernameTakenError as exc:
        raise StudentCreationError(
            f"Username {username!r} is already taken in Training's own roster."
        ) from exc

    link = m.RFOneTrainingIdentityLink(rfone_account_id=rfone_account.id, training_account_id=training_account.id)
    session.add(link)
    session.flush()
    return rfone_account, training_account
