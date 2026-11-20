#!/usr/bin/env python
"""Interactive local command to create the first (or an additional) Training
trainer account. This is the ONLY way a trainer account is created in this
version — spec §2: "non creare una pagina pubblica per registrare
addestratori". There is no default/seeded trainer and no credential is ever
printed, logged, or otherwise recorded by this script — only the operator
who runs it (interactively, at a real terminal) ever sees the password they
just typed.

Usage:
    python create_trainer.py --username jamie --display-name "Jamie Rossi"

`--username`/`--display-name` may be omitted and will be prompted for
instead. The password is always prompted for interactively via `getpass`
(hidden input, entered twice for confirmation) — it is never accepted as a
command-line argument (which would leak it into shell history/process
listings).
"""

from __future__ import annotations

import argparse
import getpass
import sys

from db import SessionFactory  # noqa: E402  (local import — see db.py's sys.path setup)
from rfone_data_store.training import service as svc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Training trainer account.")
    parser.add_argument("--username", help="Login username (will be lowercased).")
    parser.add_argument("--display-name", dest="display_name", help="Name shown to students/other trainers.")
    args = parser.parse_args()

    username = args.username or input("Trainer username: ").strip()
    display_name = args.display_name or input("Trainer display name: ").strip()
    if not username or not display_name:
        print("Username and display name are both required.", file=sys.stderr)
        return 1

    password = getpass.getpass("New trainer password (hidden): ")
    password_confirm = getpass.getpass("Confirm password: ")
    if not password:
        print("Password is required.", file=sys.stderr)
        return 1
    if password != password_confirm:
        print("Passwords did not match — nothing was created.", file=sys.stderr)
        return 1

    with SessionFactory() as session:
        try:
            account = svc.create_account(
                session, display_name=display_name, username=username, password=password, role="trainer",
            )
            session.commit()
        except svc.UsernameTakenError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    print(f"Trainer account created: username={account.username!r}, display name={display_name!r}.")
    print("Share the password with them directly (in person or by voice) — it is not stored anywhere in plain text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
