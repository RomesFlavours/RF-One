#!/usr/bin/env python
"""Interactive local command to create the first (or an additional) RF-One
Web admin account. No credential is ever printed, logged, or otherwise
recorded by this script — only the operator who runs it (interactively, at
a real terminal) ever sees the password they just typed.

Usage:
    python create_admin.py --username RFone --display-name "Pino Miraglia"

`--username`/`--display-name` may be omitted and will be prompted for
instead. The password is always prompted for interactively via `getpass`
(hidden input, entered twice for confirmation) — it is never accepted as a
command-line argument (which would leak it into shell history/process
listings).

This script creates an ACTIVE account with `is_admin=True`. It does NOT
assign any Domain access — that is a separate, explicit step via
`/admin/accounts/<id>/access` once logged in, per the task's own "does NOT
automatically assign Domains unless explicitly requested in a future
task". It is never imported or auto-executed by `app.py`.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from db import SessionFactory  # noqa: E402  (local import — see db.py's sys.path setup)
from rfone_data_store import rfone_account_service as account_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an RF-One Web admin account.")
    parser.add_argument("--username", help="Login username (will be lowercased).")
    parser.add_argument("--display-name", dest="display_name", help="Name shown in the RF-One shell.")
    args = parser.parse_args()

    username = args.username or input("Admin username: ").strip()
    display_name = args.display_name or input("Admin display name: ").strip()
    if not username or not display_name:
        print("Username and display name are both required.", file=sys.stderr)
        return 1

    password = getpass.getpass("New admin password (hidden): ")
    password_confirm = getpass.getpass("Confirm password: ")
    if not password:
        print("Password is required.", file=sys.stderr)
        return 1
    if password != password_confirm:
        print("Passwords did not match — nothing was created.", file=sys.stderr)
        return 1

    with SessionFactory() as session:
        try:
            account = account_service.create_account(
                session, username=username, display_name=display_name, password=password,
                status="ACTIVE", is_admin=True,
            )
            session.commit()
        except account_service.UsernameTakenError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    print(f"Admin account created: username={account.username!r}, display name={display_name!r}.")
    print("Share the password with them directly (in person or by voice) — it is not stored anywhere in plain text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
