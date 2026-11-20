#!/usr/bin/env python
"""Run RF-One Web on this PC — the stable local launcher (used, among
others, to try the Development Journal).

    python local_server.py                 # migrate the local database, then serve
    python local_server.py --create-admin  # create a local admin account (interactive)
    python local_server.py --port 5096     # another port

Everything local lives OUTSIDE OneDrive and outside the repository, in
`%LOCALAPPDATA%\\RF-One\\RF-One Web\\` (or `RFONE_WEB_LOCAL_HOME`):

    rfone_web_local.db         the local SQLite database
    flask_secret_key           this PC's session secret, created once
    dev_journal_documents\\    Development Journal uploads

Safety rules (enforced here, not just documented):
  * only a SQLite database is accepted — the launcher refuses any other
    `RFONE_DATABASE_URL`, so it can never migrate or serve an AWS database;
  * the S3 document bucket and the official public address are cleared, so
    nothing local is written to AWS and no request is redirected there;
  * no account or password is created automatically: `--create-admin`
    prompts for them (via `create_admin.py`), and they stay in the local
    database only.

Migrations run explicitly here, once per start, on the local database only
— never from `app.py` (see `db.py`). Not used on AWS: the deployed service
runs `gunicorn app:app` (`Infrastructure/deploy/rfone-web/Dockerfile`).
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
DATA_STORE_DIR = WEB_DIR.parent / "RF-One Data Store"
DEFAULT_PORT = 5095


def local_home() -> Path:
    override = (os.environ.get("RFONE_WEB_LOCAL_HOME") or "").strip()
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "RF-One" / "RF-One Web"


def prepare_environment(home: Path) -> str:
    home.mkdir(parents=True, exist_ok=True)
    url = (os.environ.get("RFONE_DATABASE_URL") or "").strip()
    if not url:
        url = f"sqlite:///{(home / 'rfone_web_local.db').as_posix()}"
    if not url.startswith("sqlite:///"):
        raise SystemExit("Refused: the local launcher only runs on a local SQLite database "
                         "(RFONE_DATABASE_URL must start with sqlite:///).")
    os.environ["RFONE_DATABASE_URL"] = url

    secret_file = home / "flask_secret_key"
    if not secret_file.is_file():
        secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    os.environ["RFONE_FLASK_SECRET_KEY"] = secret_file.read_text(encoding="utf-8").strip()

    os.environ["RFONE_DEV_JOURNAL_DOCUMENT_DIR"] = str(home / "dev_journal_documents")
    for name in ("RFONE_DEV_JOURNAL_DOCUMENT_BUCKET", "RFONE_PUBLIC_BASE_URL"):
        os.environ.pop(name, None)
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RF-One Web locally.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("RFONE_WEB_LOCAL_PORT", DEFAULT_PORT)))
    parser.add_argument("--create-admin", action="store_true", help="Create a local admin account, then exit.")
    args = parser.parse_args()

    home = local_home()
    url = prepare_environment(home)
    for path in (str(WEB_DIR), str(DATA_STORE_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.chdir(WEB_DIR)

    from rfone_data_store.database import run_migrations_to_head
    print(f"Local data: {home}")
    print("Bringing the local database to the latest schema...")
    run_migrations_to_head(url)

    if args.create_admin:
        import create_admin
        sys.argv = [sys.argv[0]]
        return create_admin.main()

    import app as web_app
    from db import SessionFactory
    from rfone_data_store import rfone_account_service as account_service
    with SessionFactory() as db:
        if not account_service.list_accounts(db):
            print("No local account yet: run  python local_server.py --create-admin  first.")
    print(f"RF-One Web: http://localhost:{args.port}/   (Development Journal: http://localhost:{args.port}/dev-journal)")
    web_app.app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
