"""Local Selection integrated in RF-One (SELECTION_AI_INTEGRATION_001).

Serves RF-One Web at "/" and Selection at "/selection" in ONE local process
on one port — the same address layout CloudFront gives the two services in
production — so the RF-One login, its session cookie and the Selection
Domain card work exactly as deployed:

    http://127.0.0.1:5096/           RF-One (login, Home)
    http://127.0.0.1:5096/selection/ Selection (positions)
    http://127.0.0.1:5096/selection/jobs/<token>  public candidate pages

Data lives outside OneDrive and Git, in %LOCALAPPDATA%\\RF-One\\Selection:
`rfone.db` (SQLite, the full RF-One schema via Alembic), `documents\\`
(résumés), `secret.key` (session secret, generated once). It never touches
AWS databases: RFONE_DATABASE_URL is forced to that file.

On an empty database it creates one local administrator (username `admin`)
with a random password written to `first-login.txt` in the data folder —
change it from RF-One's Profile page after the first login.

    python local_server.py [--port 5096] [--ai] [--ai-cv]

`--ai` lets AI draft positions and messages; `--ai-cv` also lets it read
résumés and interview answers (AWS Bedrock through Selection's AI client:
needs a valid `aws login` for the profile in AWS_PROFILE). Candidate
verification emails go through the Aruba SMTP mailbox configured once with
`python configure_smtp.py local` (password protected with Windows DPAPI in
the data folder, read here into the RFONE_SMTP_* variables); text messages
need RFONE_SMS_ORIGINATION_IDENTITY (a registered AWS number). Without them
the candidate page shows an explicit error or "not available".
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOFTWARE = HERE.parent
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Selection"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _prepare_environment(port: int, ai: bool, ai_cv: bool) -> None:
    (DATA / "documents").mkdir(parents=True, exist_ok=True)
    secret_file = DATA / "secret.key"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
    os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{(DATA / 'rfone.db').as_posix()}"  # forced: never another database
    os.environ["RFONE_FLASK_SECRET_KEY"] = secret_file.read_text(encoding="utf-8").strip()
    os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
    os.environ["RFONE_WEB_BASE_URL"] = f"http://127.0.0.1:{port}"
    os.environ["RFONE_SELECTION_UPLOAD_DIR"] = str(DATA / "documents")
    os.environ["RFONE_SELECTION_AI"] = "1" if (ai or ai_cv) else "0"
    os.environ["RFONE_SELECTION_AI_CV"] = "1" if ai_cv else "0"
    for name in ("RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_PUBLIC_BASE_URL", "ALEMBIC_DATABASE_URL_OVERRIDE"):
        os.environ.pop(name, None)
    os.environ.setdefault("AWS_PROFILE", "rfone-dev-login")
    ai_file = DATA / "ai.json"
    if ai_file.exists():
        ai_settings = json.loads(ai_file.read_text(encoding="utf-8"))
        for key in ("RFONE_AI_PROVIDER", "RFONE_BEDROCK_MODEL_ID", "AWS_REGION"):
            if ai_settings.get(key):
                os.environ[key] = str(ai_settings[key])
    import smtp_local_config  # sets RFONE_SMTP_* from the DPAPI-protected file, if configured

    if not smtp_local_config.apply_to_environment():
        print("Candidate email is NOT configured; run `python configure_smtp.py local`.")


def _ensure_administrator(selection_app) -> None:
    from sqlalchemy import func, select

    from rfone_data_store import models as m
    from rfone_data_store import rfone_account_service as account_svc

    with selection_app.SessionFactory() as db:
        if db.scalar(select(func.count()).select_from(m.RFOneAccount)):
            return
        password = secrets.token_urlsafe(12)
        account = account_svc.create_account(db, username="admin", display_name="Local administrator",
                                             password=password, is_admin=True)
        account_svc.set_domain_access(db, account_id=account.id, domain_code="SELECTION", enabled=True,
                                      role_code="OWNER")
        db.commit()
    (DATA / "first-login.txt").write_text(
        "Local RF-One (Selection) - first login\n\nUsername: admin\nPassword: " + password +
        "\n\nChange it in Profile after your first login. This file applies only to the local database "
        "in this folder.\n", encoding="utf-8")
    print(f"Local administrator created; credentials in {DATA / 'first-login.txt'}")


def _install_auto_login(selection_app, *flask_apps) -> None:
    """Local environment only (127.0.0.1): a request without an RF-One session is signed in as the local
    administrator, so no login page is shown. Never used by the AWS deployment, which does not run this file."""
    from flask import session
    from rfone_data_store import rfone_account_service as account_svc
    from rfone_data_store import rfone_web_session as shared_session

    def sign_in():
        if session.get(shared_session.SESSION_ACCOUNT_KEY):
            return
        with selection_app.SessionFactory() as db:
            admin = next((a for a in account_svc.list_accounts(db) if a.username == "admin"), None)
            if admin is not None:
                session[shared_session.SESSION_ACCOUNT_KEY] = admin.id
                session[shared_session.SESSION_VERSION_KEY] = admin.session_version

    for flask_app in flask_apps:
        flask_app.before_request_funcs.setdefault(None, []).insert(0, sign_in)


def main() -> None:
    parser = argparse.ArgumentParser(description="RF-One + Selection, local environment")
    parser.add_argument("--port", type=int, default=5096)
    parser.add_argument("--ai", action="store_true", help="AI drafts positions and messages")
    parser.add_argument("--ai-cv", action="store_true", help="AI may also read résumés and answers")
    parser.add_argument("--auto-login", action="store_true",
                        help="local only: enter as the local administrator without typing credentials")
    args = parser.parse_args()
    _prepare_environment(args.port, args.ai, args.ai_cv)

    sys.path.insert(0, str(HERE))
    selection_app = _load("selection_app", HERE / "app.py")  # runs the Alembic migrations to head
    from workspace.schema import provision
    provision(selection_app._engine)
    _ensure_administrator(selection_app)
    web_dir = SOFTWARE / "RF-One Web"
    sys.path.insert(0, str(web_dir))
    rfone_web = _load("rfone_web_app", web_dir / "app.py")

    # Plain HTTP on 127.0.0.1 only: the session cookie cannot be HTTPS-only here.
    for flask_app in (rfone_web.app, selection_app.app):
        flask_app.config["SESSION_COOKIE_SECURE"] = False

    if args.auto_login:
        _install_auto_login(selection_app, rfone_web.app, selection_app.app)

    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.serving import run_simple

    application = DispatcherMiddleware(rfone_web.app, {"/selection": selection_app.app})
    print(f"RF-One: http://127.0.0.1:{args.port}/  ·  Selection: http://127.0.0.1:{args.port}/selection/")
    print(f"Local data: {DATA}")
    print("AI position/message drafting:", "ENABLED" if (args.ai or args.ai_cv) else "disabled",
          "· AI résumé and answer processing:", "ENABLED" if args.ai_cv else "disabled")
    # Threaded: one stalled browser connection must not block every other page (single-thread server hung).
    run_simple("127.0.0.1", args.port, application, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
