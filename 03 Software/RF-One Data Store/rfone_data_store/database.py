"""Database configuration and engine/session management.

The database URL is configurable via the `RFONE_DATABASE_URL` environment
variable (or a local `.env` file at the repository root, consistent with the
convention already used by `03 Software/Clover Data Explorer/clover_explorer/config.py`).

If unset, it defaults to a local SQLite file at
`03 Software/RF-One Data Store/data/rfone.db` — convenient for local
development, Git-ignored, and never containing credentials.

The schema itself (see `models.py`) avoids SQLite-specific constructs so the
same models can later target PostgreSQL by changing only this URL.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "rfone.db"
ENV_VAR_NAME = "RFONE_DATABASE_URL"


def _find_dotenv(start: Path, max_levels: int = 8) -> Path | None:
    current = start
    for _ in range(max_levels):
        candidate = current / ".env"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def get_database_url() -> str:
    """Resolve the database URL: environment variable, then `.env`, then the
    local SQLite default. Never raises for the default case — a working
    local database is always available without configuration.
    """
    url = os.environ.get(ENV_VAR_NAME)
    if url:
        return url

    dotenv_path = _find_dotenv(Path(__file__).resolve().parent)
    if dotenv_path is not None:
        dotenv_values = _parse_dotenv(dotenv_path)
        url = dotenv_values.get(ENV_VAR_NAME)
        if url:
            return url

    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def redact_database_url(url: str) -> str:
    """Return `url` with any embedded password replaced by `***`.

    Never used to decide behavior — only to make a URL safe to print/log.
    """
    parts = urlsplit(url)
    if parts.password:
        redacted_netloc = re.sub(re.escape(parts.password), "***", parts.netloc, count=1)
        return parts._replace(netloc=redacted_netloc).geturl()
    return url


def create_configured_engine(url: str | None = None) -> Engine:
    """Create the SQLAlchemy Engine for `url` (or the resolved default).

    Enables SQLite foreign-key enforcement (off by default in SQLite) so
    that `schema_validation.py` exercises real FK behavior locally, matching
    what PostgreSQL enforces natively without any special configuration.
    """
    resolved_url = url or get_database_url()
    engine = create_engine(resolved_url, future=True)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


_MODULE_DIR = Path(__file__).resolve().parent.parent  # "03 Software/RF-One Data Store/"


def run_migrations_to_head(url: str) -> None:
    """Create/upgrade the schema at `url` to the latest Alembic revision.

    This is the single supported way to bring a database (the default local
    SQLite file, an ingestion staging DB, or a future PostgreSQL instance) up
    to the current canonical schema — including on an empty/non-existent
    database, which creates every table from the baseline migration onward.
    Future schema changes should be expressed as new Alembic revisions, not
    by deleting and recreating a populated database.
    """
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(_MODULE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_MODULE_DIR / "migrations"))
    # env.py reads ALEMBIC_DATABASE_URL_OVERRIDE if present; setting it here
    # (rather than only set_main_option) guarantees this exact `url` is used
    # even though env.py resolves its own default independently.
    previous_override = os.environ.get("ALEMBIC_DATABASE_URL_OVERRIDE")
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous_override is None:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = previous_override
