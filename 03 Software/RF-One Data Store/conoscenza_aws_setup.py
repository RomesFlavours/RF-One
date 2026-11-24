#!/usr/bin/env python
"""One-off Conoscenza setup on AWS RDS (`10 System/Conoscenza/README.md`).

Runs as an explicit ECS Fargate task inside the VPC — never at application
startup. Environment:

    CONOSCENZA_ADMIN_DATABASE_URL  existing RF-One administrative URL (secret rfone-tips/database-url)
    RFONE_CONOSCENZA_DATABASE_URL  URL of the dedicated role conoscenza_app (secret rfone-conoscenza/database-url)
    CONOSCENZA_IMPORT_S3_URI       optional s3://bucket/key of the export JSON to import
    CONOSCENZA_SETUP_MODE          "check" (default: everything in a rolled-back transaction where possible)
                                   or "apply"

Steps:
1. as administrator: create (or re-password) the role `conoscenza_app`, the
   schema `conoscenza` (usable and writable only by that role besides the
   administrator), and the role's search_path. Nothing outside the
   schema is granted; existing RF-One tables are not touched.
2. as `conoscenza_app`: create the Conoscenza tables in its schema.
3. if an export is given and the register is empty: import it with its ids.
4. print `MANIFEST {...}` (row counts + SHA-256 per table) for comparison.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, text  # noqa: E402

from rfone_data_store.conoscenza import migration  # noqa: E402
from rfone_data_store.conoscenza.store import ensure_schema, make_engine  # noqa: E402

ROLE = "conoscenza_app"
SCHEMA = "conoscenza"


def main() -> int:
    mode = os.environ.get("CONOSCENZA_SETUP_MODE", "check")
    admin_url = os.environ["CONOSCENZA_ADMIN_DATABASE_URL"]
    app_url = os.environ["RFONE_CONOSCENZA_DATABASE_URL"]
    parts = urlsplit(app_url)
    if unquote(parts.username or "") != ROLE:
        raise SystemExit(f"The application URL must use the role {ROLE}.")
    password = unquote(parts.password or "")
    database = parts.path.lstrip("/").split("?")[0]

    admin = create_engine(admin_url, future=True)
    with admin.connect() as conn:
        tx = conn.begin()
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).first()
        q = conn.dialect.identifier_preparer.quote
        literal = "'" + password.replace("'", "''") + "'"
        if exists:
            conn.execute(text(f"ALTER ROLE {q(ROLE)} WITH LOGIN PASSWORD {literal}"))
        else:
            conn.execute(text(f"CREATE ROLE {q(ROLE)} WITH LOGIN PASSWORD {literal} NOSUPERUSER NOCREATEDB "
                              f"NOCREATEROLE"))
        conn.execute(text(f"GRANT CONNECT ON DATABASE {q(database)} TO {q(ROLE)}"))
        # The schema belongs to the administrator; the role may only use it and create its own tables
        # (no role membership is needed, and nothing outside the schema is granted).
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {q(SCHEMA)}"))
        conn.execute(text(f"GRANT USAGE, CREATE ON SCHEMA {q(SCHEMA)} TO {q(ROLE)}"))
        conn.execute(text(f"ALTER ROLE {q(ROLE)} IN DATABASE {q(database)} SET search_path = {q(SCHEMA)}"))
        print(f"ADMIN role={'updated' if exists else 'created'} schema={SCHEMA} mode={mode}")
        if mode != "apply":
            tx.rollback()
            print("CHECK: administrative statements rolled back; nothing changed.")
            return 0
        tx.commit()
    admin.dispose()

    engine = make_engine(app_url)
    with engine.connect() as conn:
        path = conn.execute(text("SHOW search_path")).scalar_one()
        user = conn.execute(text("SELECT current_user")).scalar_one()
        print(f"APP user={user} search_path={path}")
        if SCHEMA not in path:
            raise SystemExit("search_path does not point at the conoscenza schema.")
    ensure_schema(engine)
    source = os.environ.get("CONOSCENZA_IMPORT_S3_URI")
    if source:
        import boto3
        bucket, key = source[5:].split("/", 1)
        payload = json.loads(boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"))
        current = migration.read_all(engine)
        if any(current[name] for name in migration.TABLE_ORDER):
            if migration.manifest(current) == migration.manifest(payload):
                print("IMPORT already done: destination equals the export.")
            else:
                raise SystemExit("Destination register is not empty and differs from the export: refusing.")
        else:
            migration.load(engine, payload)
            print("IMPORT done.")
    print("MANIFEST " + json.dumps(migration.manifest(migration.read_all(engine)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
