"""Where the Conoscenza register lives and who may use it.

Storage (first release, see README "Storage"): the URL comes from
`RFONE_CONOSCENZA_DATABASE_URL`; when unset, a project-relative SQLite file
`03 Software/RF-One Data Store/data/conoscenza.db` (Git-ignored) is used.
This keeps the register inside the authorized RF One folder; moving it into
the canonical PostgreSQL or AWS RDS is a URL change plus a migration and
needs a Product Owner decision.

Authentication: one random token per client (CLAUDE, CODEX, CHATGPT,
IMPORTER). Only the SHA-256 of a token is stored in the register; the token
itself is written once to `Secrets/conoscenza/<client>.token` (Git-ignored).
The recording AI is always the token's client — a caller cannot declare
another identity.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from .models import ALL_TABLES, CLIENTS, KnowledgeAccessRule, KnowledgeClient, KnowledgePerson

OWNER_NAME = "Pino"

ENV_URL = "RFONE_CONOSCENZA_DATABASE_URL"
ENV_TOKEN = "RFONE_CONOSCENZA_TOKEN"
REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_STORE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB = DATA_STORE_DIR / "data" / "conoscenza.db"
TOKEN_DIR = REPO_ROOT / "Secrets" / "conoscenza"
PENDING_DIR = REPO_ROOT / "output" / "conoscenza" / "pending"


class AuthenticationError(PermissionError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def database_url() -> str:
    return os.environ.get(ENV_URL) or f"sqlite:///{DEFAULT_DB.as_posix()}"


def make_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if url.startswith("sqlite:///"):
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, future=True, connect_args={"timeout": 30})

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection, _record):  # noqa: ANN001
            dbapi_connection.isolation_level = None
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            # OneDrive-synced folder: keep a single file, no -wal/-shm sidecars.
            cur.execute("PRAGMA journal_mode=DELETE")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        @event.listens_for(engine, "begin")
        def _begin(conn):  # noqa: ANN001
            conn.exec_driver_sql("BEGIN IMMEDIATE")

        return engine
    return create_engine(url, future=True, pool_pre_ping=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def ensure_schema(engine: Engine) -> None:
    from .models import ConoscenzaBase
    ConoscenzaBase.metadata.create_all(engine, tables=ALL_TABLES)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def ensure_owner(db: Session) -> KnowledgePerson:
    """The register owner (Pino). The only person with access in this release."""
    owner = db.scalar(select(KnowledgePerson).where(KnowledgePerson.is_owner.is_(True)))
    if owner is None:
        owner = KnowledgePerson(name=OWNER_NAME, is_owner=True, status="ACTIVE", created_at=utcnow())
        db.add(owner)
        db.flush()
    return owner


def issue_missing_tokens(db: Session, token_dir: Path = TOKEN_DIR) -> list[str]:
    """Create a token for every client that has none (file or row), owned by
    the owner. Never replaces an existing token. Returns the clients that
    received one."""
    token_dir.mkdir(parents=True, exist_ok=True)
    owner = ensure_owner(db)
    issued = []
    for client in CLIENTS:
        path = token_dir / f"{client.lower()}.token"
        if path.is_file():
            h = token_hash(path.read_text(encoding="ascii"))
            if not db.scalar(select(KnowledgeClient).where(KnowledgeClient.token_sha256 == h)):
                db.add(KnowledgeClient(client=client, person_id=owner.id, token_sha256=h, active=True,
                                       created_at=utcnow()))
            continue
        token = secrets.token_urlsafe(32)
        path.write_text(token, encoding="ascii")
        db.add(KnowledgeClient(client=client, person_id=owner.id, token_sha256=token_hash(token), active=True,
                               created_at=utcnow()))
        issued.append(client)
    db.commit()
    return issued


def read_token(client: str | None = None, token_dir: Path = TOKEN_DIR) -> str:
    """The caller's token: `RFONE_CONOSCENZA_TOKEN`, else the client's token file."""
    token = os.environ.get(ENV_TOKEN)
    if token:
        return token.strip()
    if not client:
        raise AuthenticationError("Token Conoscenza mancante: indicare il client o RFONE_CONOSCENZA_TOKEN.")
    path = token_dir / f"{client.lower()}.token"
    if not path.is_file():
        raise AuthenticationError(f"Token Conoscenza assente per {client}: eseguire 'conoscenza.py init'.")
    return path.read_text(encoding="ascii").strip()


def principal_for(db: Session, credential: KnowledgeClient):
    from .service import Principal
    person = db.get(KnowledgePerson, credential.person_id) if credential.person_id else None
    if person is None or person.status != "ACTIVE":
        raise AuthenticationError("La persona di questa credenziale non è attiva.")
    rules = [(r.permission, r.domain_pattern) for r in db.scalars(
        select(KnowledgeAccessRule).where(KnowledgeAccessRule.person_id == person.id,
                                          KnowledgeAccessRule.active.is_(True)))]
    return Principal(client=credential.client, credential_id=credential.id, person_id=person.id,
                     person_name=person.name, is_owner=person.is_owner, rules=rules)


def authenticate(db: Session, token: str):
    """The Principal (person + tool) of a credential token."""
    from .models import OAuthGrant
    h = token_hash(token)
    row = db.scalar(select(KnowledgeClient).where(KnowledgeClient.token_sha256 == h,
                                                  KnowledgeClient.active.is_(True)))
    if row is None:
        # An OAuth access token (ChatGPT) resolves to the credential that authorized it.
        grant = db.scalar(select(OAuthGrant).where(OAuthGrant.token_sha256 == h, OAuthGrant.kind == "ACCESS"))
        if grant is not None and _aware(grant.expires_at) > utcnow():
            row = db.get(KnowledgeClient, grant.credential_id)
            if row is not None and not row.active:
                row = None
    if row is None:
        raise AuthenticationError("Token Conoscenza non valido, scaduto o disattivato.")
    return principal_for(db, row)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
