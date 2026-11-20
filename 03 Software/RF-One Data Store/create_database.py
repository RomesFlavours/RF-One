#!/usr/bin/env python
"""Create the RF-One canonical Restaurant database schema and validate it.

Usage:
    python create_database.py

Configuration: set RFONE_DATABASE_URL (env var or a root .env file) to
target a different database (e.g. PostgreSQL). Defaults to a local SQLite
file at data/rfone.db.

Prints only: the (credential-redacted) database URL, the number of tables
created, and the validation outcome. Never prints raw data or secrets.
"""

from __future__ import annotations

from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
    run_migrations_to_head,
)
from rfone_data_store.models import Base
from rfone_data_store.schema_validation import run_validation


def main() -> None:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")

    # Schema creation goes through Alembic (not a direct create_all) so the
    # exact same path used here also works for an already-existing database
    # on a later schema revision — see migrations/README_MIGRATIONS.md.
    run_migrations_to_head(url)

    engine = create_configured_engine(url)
    table_count = len(Base.metadata.sorted_tables)
    print(f"Tables created: {table_count}")

    session_factory = create_session_factory(engine)
    result = run_validation(session_factory)

    if result.success:
        print(f"Validation: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
    else:
        print(
            "Validation: FAILURE "
            f"({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)"
        )
        for description in result.checks_failed:
            print(f"  FAILED: {description}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
