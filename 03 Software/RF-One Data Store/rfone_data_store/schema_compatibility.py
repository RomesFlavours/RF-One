"""Read-only schema compatibility for services that share one database.

Rule (see `MIGRATIONS.md`): no service applies migrations to the shared
database while it starts. Instead, a service names the tables its code maps
and checks, without writing, that each exists with every mapped column.

The Alembic revision is reported but never decides on its own: another
Domain may already have applied a newer, additive migration that this
service's code does not contain yet. An unknown revision with a compatible
schema is a warning; a missing table or column is a refusal.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import Engine, Table, create_engine, inspect, text
from sqlalchemy.engine import make_url

LOG = logging.getLogger(__name__)
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class IncompatibleSchemaError(RuntimeError):
    """The database lacks tables or columns the service's code maps."""


@dataclass(frozen=True)
class SchemaReport:
    revisions: tuple[str, ...]
    unknown_revisions: tuple[str, ...]
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...]

    @property
    def compatible(self) -> bool:
        return not self.missing_tables and not self.missing_columns

    def describe(self) -> str:
        parts = [f"revision {', '.join(self.revisions) or 'none'}"
                 + (" (not in this code's migration chain)" if self.unknown_revisions or not self.revisions else "")]
        if self.missing_tables:
            parts.append("missing tables: " + ", ".join(self.missing_tables))
        if self.missing_columns:
            parts.append("missing columns: " + ", ".join(self.missing_columns))
        return "; ".join(parts)


def known_revisions() -> frozenset[str]:
    """Every revision in this code's migration chain."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(_MIGRATIONS_DIR))
    return frozenset(s.revision for s in script.walk_revisions("base", "heads"))


def read_only_engine(url: str) -> Engine:
    """An engine that cannot write: SQLite opened `mode=ro`, PostgreSQL in a
    read-only transaction mode. Dispose it after use."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        if not parsed.database or parsed.database == ":memory:":
            raise ValueError("a read-only check needs a database file, not an in-memory SQLite database")
        uri = f"file:{Path(parsed.database).as_posix()}?mode=ro"
        return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    if parsed.get_backend_name() == "postgresql":
        return create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
    return create_engine(url)


def inspect_schema(engine: Engine, tables: Iterable[Table]) -> SchemaReport:
    missing_tables, missing_columns = [], []
    with engine.connect() as connection:
        inspector = inspect(connection)
        existing = set(inspector.get_table_names())
        revisions = ()
        if "alembic_version" in existing:
            revisions = tuple(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        for table in sorted(set(tables), key=lambda t: t.name):
            if table.name not in existing:
                missing_tables.append(table.name)
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            missing_columns += [f"{table.name}.{c.name}" for c in table.columns if c.name not in present]
    known = known_revisions()
    return SchemaReport(revisions=revisions, unknown_revisions=tuple(r for r in revisions if r not in known),
                        missing_tables=tuple(missing_tables), missing_columns=tuple(missing_columns))


def require_compatible_schema(engine: Engine, tables: Iterable[Table], *, service: str) -> SchemaReport:
    """Raise IncompatibleSchemaError if a mapped table or column is missing;
    warn, without refusing, when the revision is unknown to this code."""
    report = inspect_schema(engine, tables)
    if not report.compatible:
        raise IncompatibleSchemaError(f"{service}: the database schema is not compatible with this release "
                                      f"({report.describe()}). No migration was applied; see MIGRATIONS.md.")
    if report.unknown_revisions or not report.revisions:
        LOG.warning("%s: %s. The required tables and columns are present, so the service starts.",
                    service, report.describe())
    return report
