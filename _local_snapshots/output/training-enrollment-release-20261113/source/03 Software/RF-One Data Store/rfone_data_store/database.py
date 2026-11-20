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

        # Python's stdlib `sqlite3` driver runs its own legacy implicit-
        # transaction handling by default, which is well known to conflict
        # with SQLAlchemy's own transaction demarcation — most visibly
        # breaking SAVEPOINT/nested-transaction and rollback correctness
        # (see SQLAlchemy's pysqlite dialect notes, "Serializable isolation
        # / Savepoints / Transactional DDL"). Every "always rolls back, never
        # leaves synthetic rows" validation suite in this codebase
        # (`*_validation.py`) depends on rollback actually working —
        # including `selection_validation.py`'s use of `Session.begin_nested()`
        # (TASK_SELECTION_002) — so this is the officially documented fix,
        # applied here once for every caller of this engine factory.
        @event.listens_for(engine, "connect")
        def _sqlite_disable_pysqlite_implicit_transactions(dbapi_connection, connection_record):  # noqa: ANN001
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def _sqlite_emit_explicit_begin(conn):  # noqa: ANN001
            conn.exec_driver_sql("BEGIN")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


_MODULE_DIR = Path(__file__).resolve().parent.parent  # "03 Software/RF-One Data Store/"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when a test/validation entry point would target the normal
    shared/operational database instead of a disposable/test-only one."""


def is_default_operational_database(url: str) -> bool:
    """True if `url` resolves to the same shared SQLite file normal runtime
    uses (`data/rfone.db`) — compared by resolved filesystem path so a
    differently-spelled (relative/absolute) URL pointing at the same file
    can't bypass the check.
    """
    if not url.startswith("sqlite:///"):
        return False
    raw_path = url[len("sqlite:///") :]
    if not raw_path:
        return False
    try:
        return Path(raw_path).resolve() == DEFAULT_SQLITE_PATH.resolve()
    except OSError:
        return False


_DISPOSABLE_TEST_DB_PREFIX = "rfone_test_"


def create_disposable_test_database_url(label: str) -> str:
    """Create a brand-new throwaway SQLite file for a test/validation entry
    point named `label`, migrated to the current schema head, and return its
    URL.

    The file lives under the OS temp directory (never under this project's
    `data/` directory), so it can never collide with or resemble the shared
    operational database. Pair with `cleanup_disposable_test_database_url`
    in a `finally` block once the caller is done with it.
    """
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"{_DISPOSABLE_TEST_DB_PREFIX}{label}_")
    os.close(fd)
    os.remove(path)  # let run_migrations_to_head create it fresh
    url = f"sqlite:///{Path(path).as_posix()}"
    run_migrations_to_head(url)
    return url


def cleanup_disposable_test_database_url(url: str) -> None:
    """Best-effort removal of a SQLite file previously returned by
    `create_disposable_test_database_url` (plus its `-wal`/`-shm`/`-journal`
    siblings, if any).

    Only ever deletes a file whose name carries the disposable-test-DB
    prefix this module itself generates — never a caller-supplied
    `RFONE_DATABASE_URL`, so this is safe to call unconditionally after
    `resolve_test_database_url()`, whether or not it actually provisioned a
    disposable file.
    """
    if not url.startswith("sqlite:///"):
        return
    path = url[len("sqlite:///") :]
    if not os.path.basename(path).startswith(_DISPOSABLE_TEST_DB_PREFIX):
        return
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = path + suffix
        if os.path.exists(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass


def resolve_test_database_url(label: str) -> str:
    """Resolve the database URL a test/validation entry point should use
    (GLOBAL_INTEGRITY_FIX_001 / C-4).

    - If `RFONE_DATABASE_URL` is explicitly set in the environment, it is
      used — unless it resolves to the shared operational default
      (`data/rfone.db`), in which case this raises `UnsafeTestDatabaseError`
      rather than silently running against real data.
    - If unset, a fresh disposable SQLite database is self-provisioned (see
      `create_disposable_test_database_url`), so simply omitting the
      variable is always safe and can never fall through to the shared
      default the way `get_database_url()` does for normal runtime.

    Deliberately does not consult a `.env` file's `RFONE_DATABASE_URL` (only
    `get_database_url()`, used by normal runtime, does that) — a test entry
    point should default to self-isolation, not to whatever a developer's
    local `.env` happens to point at.
    """
    explicit_url = os.environ.get(ENV_VAR_NAME)
    if explicit_url:
        if is_default_operational_database(explicit_url):
            raise UnsafeTestDatabaseError(
                f"{ENV_VAR_NAME} points at the shared operational database "
                f"({redact_database_url(explicit_url)}). Refusing to run a test/validation "
                "entry point against it - point it at a disposable database instead, or unset "
                f"{ENV_VAR_NAME} to use an auto-provisioned disposable one."
            )
        return explicit_url
    return create_disposable_test_database_url(label)


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
