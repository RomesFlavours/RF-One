"""Resolves a PostgreSQL SQLAlchemy URL from an AWS Secrets Manager secret.

Generic Technical infrastructure helper (not tied to any one connector or
Domain) — the counterpart to `database.get_database_url()` for a target
that lives in AWS RDS rather than a local SQLite file. Never logs, prints,
or returns the secret's raw contents; only ever returns the composed
SQLAlchemy URL, which callers must in turn pass through
`database.redact_database_url()` before printing.
"""

from __future__ import annotations

import json
from urllib.parse import quote_plus


def get_rds_postgres_url(*, secret_id: str, profile_name: str, region_name: str) -> str:
    """Builds a `postgresql+psycopg2://` URL from an AWS Secrets Manager
    secret shaped like the standard RDS "credentials for a database" template
    (`host`, `port`, `dbname`, `username`, `password`).

    Parses leniently from the first `{` to the last `}` in the returned
    `SecretString` — some secrets in this account carry a stray leading
    byte-order-mark that breaks strict `json.loads`.
    """
    import boto3  # imported lazily so modules that never touch RDS need no AWS credentials at import time

    session = boto3.Session(profile_name=profile_name, region_name=region_name)
    client = session.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    raw = response["SecretString"]
    secret = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])

    host = secret["host"]
    port = secret.get("port", 5432)
    dbname = secret["dbname"]
    username = quote_plus(secret["username"])
    password = quote_plus(secret["password"])

    return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{dbname}"
