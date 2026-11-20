"""Isolated, synthetic-only Render trial. Never import from production launchers."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
SOFTWARE = ROOT / "03 Software"
if not SOFTWARE.is_dir():
    SOFTWARE = ROOT.parents[1]


def prepare_environment():
    if os.environ.get("RFONE_RENDER_TRIAL") != "1":
        raise RuntimeError("Explicit RFONE_RENDER_TRIAL=1 is required")
    url = os.environ.get("RFONE_DATABASE_URL", "")
    parsed = urlsplit(url)
    local_test = os.environ.get("RFONE_RENDER_TRIAL_LOCAL_TEST") == "1"
    if not (local_test and url.startswith("sqlite:///")):
        if (parsed.scheme not in ("postgres", "postgresql")
                or not (parsed.hostname or "").startswith("dpg-")
                or parsed.path != "/rfone_selection_free_trial"):
            raise RuntimeError("Only the isolated Render trial database is allowed")
    if parsed.scheme in ("postgres", "postgresql"):
        # SQLAlchemy 2.1 defaults to psycopg3; the shared app installs psycopg2.
        os.environ["RFONE_DATABASE_URL"] = "postgresql+psycopg2://" + url.split("://", 1)[1]
    for key in ("RFONE_FLASK_SECRET_KEY", "RFONE_TRIAL_ADMIN_PASSWORD"):
        if len(os.environ.get(key, "")) < 24:
            raise RuntimeError(f"Set a unique trial secret: {key} (24+ characters)")
    # No .env is packaged. Ignore any ambient AWS / mail / AI / bridge settings.
    for key in list(os.environ):
        if key.startswith(("AWS_", "ANTHROPIC_", "OPENAI_", "RFONE_SMTP_", "RFONE_SMS_")):
            os.environ.pop(key, None)
    for key in ("RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_SELECTION_ARUBA_KEY",
                "RFONE_PUBLIC_BASE_URL", "ALEMBIC_DATABASE_URL_OVERRIDE"):
        os.environ.pop(key, None)
    os.environ.update(RFONE_SELECTION_REQUIRE_RFONE_LOGIN="1",
        RFONE_SELECTION_AI="0", RFONE_SELECTION_AI_CV="0",
        RFONE_AI_PROVIDER="TRIAL_DISABLED", AWS_EC2_METADATA_DISABLED="true",
        RFONE_SELECTION_UPLOAD_DIR=str(ROOT / "trial-uploads"))
    base = os.environ.get("RENDER_EXTERNAL_URL", "https://localhost").rstrip("/")
    os.environ["RFONE_WEB_BASE_URL"] = base


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prepare_environment()
sys.path.insert(0, str(SOFTWARE / "RF-One Data Store"))
sys.path.insert(0, str(SOFTWARE / "Selection"))
selection = load("trial_selection", SOFTWARE / "Selection" / "app.py")
from workspace.schema import provision
provision(selection._engine)

from sqlalchemy import select, text
from rfone_data_store import models as m, rfone_account_service as accounts

with selection.SessionFactory() as db:
    account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == "render-trial"))
    if account is None:
        account = accounts.create_account(db, username="render-trial",
            display_name="Synthetic Render trial", password=os.environ["RFONE_TRIAL_ADMIN_PASSWORD"],
            is_admin=True)
        accounts.set_domain_access(db, account_id=account.id, domain_code="SELECTION",
                                  enabled=True, role_code="OWNER")
        db.commit()

sys.path.insert(0, str(SOFTWARE / "RF-One Web"))
web = load("trial_web", SOFTWARE / "RF-One Web" / "app.py")

from flask import Response, jsonify, request
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix


@web.app.get("/trial-health")
def health():
    with selection._engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return jsonify(status="ok", environment="synthetic-trial", ai=False, email=False,
                   document_persistence=False)


def trial_headers(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"
    if response.mimetype == "text/html" and not response.direct_passthrough:
        body = response.get_data(as_text=True)
        banner = ('<div role="status" style="padding:10px;background:#fff3cd;color:#392a00;'
                  'text-align:center">RENDER TEST — Synthetic data only. '
                  'AI and email disabled. Uploaded files are temporary.</div>')
        import re
        body = re.sub(r"(<body\b[^>]*>)", lambda match: match.group(1) + banner, body, count=1)
        response.set_data(body)
    return response


for app in (web.app, selection.app):
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=5 * 1024 * 1024)
    app.after_request(trial_headers)


@web.app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


application = ProxyFix(DispatcherMiddleware(web.app, {"/selection": selection.app}), x_proto=1)
