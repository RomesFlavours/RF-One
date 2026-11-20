#!/usr/bin/env python
"""Concise schema inventory: table name, row count, column count.

Usage:
    python inspect_database.py

Not a database admin UI — read-only inspection only, using the same
configurable database URL as create_database.py.
"""

from __future__ import annotations

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from rfone_data_store.database import create_configured_engine, get_database_url, redact_database_url
from rfone_data_store.models import Base


def main() -> None:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")

    engine = create_configured_engine(url)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    print(f"{'table':40s} {'columns':>7s} {'rows':>10s}")
    print("-" * 60)

    with Session(engine) as session:
        for table in Base.metadata.sorted_tables:
            column_count = len(table.columns)
            if table.name in existing_tables:
                row_count = session.scalar(select(func.count()).select_from(table))
            else:
                row_count = "n/a"
            print(f"{table.name:40s} {column_count:7d} {str(row_count):>10s}")


if __name__ == "__main__":
    main()
