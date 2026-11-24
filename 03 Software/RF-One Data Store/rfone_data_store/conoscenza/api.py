"""Access paths to the register, all exposing the same `call_tool(name, args)`.

- `Conoscenza` — direct database access (the AWS service itself, tests,
  local fallback). Every call authenticates the credential token and runs
  one service operation.
- `RemoteConoscenza` — the client side used on Pino's PC by Claude Code and
  Codex (through the local stdio MCP proxy) and by the command line: every
  call goes to the AWS service over HTTPS with the tool's own token.

Writes are never lost silently. A remote write gets its request key BEFORE
the first attempt; if the service cannot be reached, the request is saved
to `output/conoscenza/pending/` and the caller is told the write did NOT
happen. Pending writes are replayed automatically before the next
successful call (and by `riprova`); because the key is unchanged and the
service treats a repeated key as the same write, each one reaches the
register exactly once.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from . import service
from .store import (PENDING_DIR, REPO_ROOT, AuthenticationError, authenticate, database_url, ensure_schema,
                    make_engine, read_token, session_factory, utcnow)

WRITE_TOOLS = {"conoscenza_registra", "conoscenza_lavoro", "conoscenza_cambia", "conoscenza_collega",
               "conoscenza_approva"}
REMOTE_CONFIG = REPO_ROOT / "Secrets" / "conoscenza" / "remote.json"
ENV_REMOTE_URL = "RFONE_CONOSCENZA_URL"


def remote_url() -> str | None:
    """The AWS service URL when this PC is pointed at it, else None (local register)."""
    url = os.environ.get(ENV_REMOTE_URL)
    if url is not None:
        return url.strip() or None
    if REMOTE_CONFIG.is_file():
        return (json.loads(REMOTE_CONFIG.read_text(encoding="utf-8")).get("url") or "").strip() or None
    return None


def dispatch(api, name: str, args: dict, default_session: str | None = None) -> dict:
    """Map an MCP tool call onto the operations of a backend with the
    `Conoscenza` method names (shared by the stdio server and the HTTP service)."""
    args = dict(args or {})
    if default_session:
        args.setdefault("session_ref", default_session)
    s = args.get("session_ref")
    if name == "conoscenza_contesto":
        return api.brief(domain=args.get("domain"), session_ref=s)
    if name == "conoscenza_cerca":
        return api.search(args.get("query", ""), domain=args.get("domain"), kind=args.get("kind"),
                          include_history=bool(args.get("include_history")), limit=args.get("limit") or 8,
                          session_ref=s)
    if name == "conoscenza_leggi":
        return api.read(args.get("id"), session_ref=s)
    if name == "conoscenza_registra":
        if args.get("kind") not in ("DECISION", "CORRECTION"):
            return {"ok": False, "errore": "kind deve essere DECISION o CORRECTION."}
        return api.record(**args)
    if name == "conoscenza_lavoro":
        args.pop("kind", None)
        return api.record(kind="WORK_UPDATE", **args)
    if name == "conoscenza_cambia":
        old_id = args.pop("old_id", None)
        return api.supersede(old_id, **args)
    if name == "conoscenza_collega":
        return api.link(args.get("from_id"), args.get("to_id"), args.get("relation"), args.get("note"), s)
    if name == "conoscenza_approva":
        return api.approve(args.get("id"), args.get("note"), s)
    if name == "conoscenza_storico":
        return api.access_log(session_ref=args.get("filter_session"), client=args.get("client"),
                              limit=args.get("limit") or 50)
    return {"ok": False, "errore": f"Strumento sconosciuto: {name}"}


class Conoscenza:
    """Direct database backend."""

    def __init__(self, token: str | None = None, *, client: str | None = None, url: str | None = None,
                 pending_dir: Path = PENDING_DIR):
        self.token = token or read_token(client)
        self.url = url or database_url()
        self.pending_dir = pending_dir
        self._factory = None
        self.who = None

    # -- plumbing ---------------------------------------------------------
    def _session(self):
        if self._factory is None:
            engine = make_engine(self.url)
            ensure_schema(engine)
            self._factory = session_factory(engine)
        return self._factory()

    def close(self) -> None:
        """Release the database connections (needed on Windows before deleting a SQLite file)."""
        if self._factory is not None:
            self._factory.kw["bind"].dispose()
            self._factory = None

    def _run(self, operation: str, fn, *, params: dict, session_ref: str | None = None):
        try:
            with self._session() as db:
                self.who = authenticate(db, self.token)
                return {"ok": True, **fn(db, self.who)}
        except AuthenticationError as exc:
            return {"ok": False, "errore": str(exc), "tipo_errore": "AUTENTICAZIONE"}
        except service.ConoscenzaError as exc:
            if self.who:
                service.log_failure(self._factory, self.who, _LOG_OP.get(operation, "WRITE"), str(exc),
                                    session_ref=session_ref)
            return {"ok": False, "errore": str(exc), "tipo_errore": "RIFIUTATA"}
        except (OperationalError, SQLAlchemyError, OSError) as exc:
            out = {"ok": False, "tipo_errore": "REGISTRO_IRRAGGIUNGIBILE",
                   "errore": f"REGISTRO CONOSCENZA IRRAGGIUNGIBILE: {type(exc).__name__}: {str(exc)[:300]}"}
            if operation in ("record", "supersede", "link", "approve"):
                out["in_coda"] = str(_queue(self.pending_dir, operation, params))
                out["errore"] += (" — SCRITTURA NON AVVENUTA. Richiesta salvata in coda; verrà ripetuta "
                                  "(una sola volta) quando il registro torna disponibile.")
            return out

    def pending(self) -> list[str]:
        return _pending(self.pending_dir)

    def call_tool(self, name: str, args: dict) -> dict:
        return dispatch(self, name, args)

    # -- operations ---------------------------------------------------------
    def brief(self, domain=None, session_ref=None):
        out = self._run("brief", lambda db, w: service.brief(db, w, session_ref=session_ref, domain=domain),
                        params={}, session_ref=session_ref)
        out["scritture_in_coda"] = self.pending()
        return out

    def search(self, query, domain=None, kind=None, include_history=False, limit=8, session_ref=None):
        return self._run("search", lambda db, w: service.search(
            db, w, query, session_ref=session_ref, domain=domain, kind=kind, include_history=include_history,
            limit=limit), params={}, session_ref=session_ref)

    def read(self, item_id, session_ref=None):
        return self._run("read", lambda db, w: {"item": service.read(db, w, int(item_id), session_ref)},
                         params={}, session_ref=session_ref)

    def record(self, **fields):
        return self._run("record", lambda db, w: service.record(db, w, fields), params=fields,
                         session_ref=fields.get("session_ref"))

    def supersede(self, old_id, **fields):
        return self._run("supersede", lambda db, w: service.supersede(db, w, int(old_id), fields),
                         params={"old_id": old_id, **fields}, session_ref=fields.get("session_ref"))

    def link(self, from_id, to_id, relation, note=None, session_ref=None):
        return self._run("link", lambda db, w: service.link(db, w, from_id, to_id, relation, note, session_ref),
                         params={"from_id": from_id, "to_id": to_id, "relation": relation, "note": note,
                                 "session_ref": session_ref}, session_ref=session_ref)

    def approve(self, item_id, note=None, session_ref=None):
        return self._run("approve", lambda db, w: service.approve(db, w, int(item_id), note, session_ref),
                         params={"id": item_id, "note": note, "session_ref": session_ref}, session_ref=session_ref)

    def access_log(self, session_ref=None, client=None, limit=50):
        return self._run("log", lambda db, w: {"accessi": service.access_log(
            db, w, session_ref=session_ref, client=client, limit=limit)}, params={})

    def retry_pending(self) -> dict:
        return _retry(self.pending_dir, self.call_tool)


class RemoteConoscenza:
    """HTTPS client of the AWS service (Bearer = the tool's own token)."""

    def __init__(self, url: str, token: str | None = None, *, client: str | None = None,
                 pending_dir: Path = PENDING_DIR, timeout: float = 30):
        self.url = url.rstrip("/")
        self.endpoint = self.url if self.url.endswith("/mcp") else self.url + "/mcp"
        self.token = token or read_token(client)
        self.pending_dir = pending_dir
        self.timeout = timeout

    def _post(self, name: str, args: dict) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": args}}).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream", "User-Agent": "rf-one-conoscenza-proxy/1.0"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            reply = json.loads(response.read().decode("utf-8"))
        if "error" in reply:
            return {"ok": False, "errore": reply["error"].get("message")}
        return json.loads(reply["result"]["content"][0]["text"])

    def call_tool(self, name: str, args: dict, *, replay: bool = True) -> dict:
        args = dict(args or {})
        if name in WRITE_TOOLS and name != "conoscenza_cambia" and not args.get("request_key"):
            args["request_key"] = f"{name}-{uuid.uuid4().hex}"
        try:
            if replay and self.pending():
                self.retry_pending()
            out = self._post(name, args)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return {"ok": False, "tipo_errore": "AUTENTICAZIONE",
                        "errore": f"Credenziale Conoscenza rifiutata dal servizio AWS (HTTP {exc.code})."}
            return self._unreachable(name, args, f"HTTP {exc.code}")
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            return self._unreachable(name, args, f"{type(exc).__name__}: {str(exc)[:200]}")
        if name == "conoscenza_contesto":
            out["scritture_in_coda"] = self.pending()
            out["servizio"] = self.url
        return out

    def _unreachable(self, name: str, args: dict, detail: str) -> dict:
        out = {"ok": False, "tipo_errore": "REGISTRO_IRRAGGIUNGIBILE",
               "errore": f"REGISTRO CONOSCENZA (AWS) IRRAGGIUNGIBILE: {detail}"}
        if name in WRITE_TOOLS:
            out["in_coda"] = str(_queue_tool(self.pending_dir, name, args))
            out["errore"] += (" — SCRITTURA NON AVVENUTA. Salvata in coda: arriverà al registro AWS una sola "
                              "volta al ripristino della connessione.")
        return out

    def pending(self) -> list[str]:
        return _pending(self.pending_dir)

    def retry_pending(self) -> dict:
        return _retry(self.pending_dir, lambda n, a: self.call_tool(n, a, replay=False))


# -- pending queue (shared) ------------------------------------------------

def _pending(pending_dir: Path) -> list[str]:
    return sorted(p.name for p in pending_dir.glob("*.json")) if pending_dir.is_dir() else []


def _queue_tool(pending_dir: Path, name: str, args: dict) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{utcnow():%Y%m%dT%H%M%S%f}-{name}.json"
    path.write_text(json.dumps({"tool": name, "arguments": args}, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    return path


_OP_TOOL = {"record": None, "supersede": "conoscenza_cambia", "link": "conoscenza_collega",
            "approve": "conoscenza_approva"}


def _queue(pending_dir: Path, operation: str, params: dict) -> Path:
    args = dict(params)
    if operation == "record":
        name = "conoscenza_lavoro" if args.get("kind") == "WORK_UPDATE" else "conoscenza_registra"
        args.setdefault("request_key", f"{name}-{uuid.uuid4().hex}")
    else:
        name = _OP_TOOL[operation]
    return _queue_tool(pending_dir, name, args)


def _retry(pending_dir: Path, call) -> dict:
    done, failed = [], []
    for file_name in _pending(pending_dir):
        path = pending_dir / file_name
        request = json.loads(path.read_text(encoding="utf-8"))
        out = call(request["tool"], request["arguments"])
        if out.get("ok"):
            path.unlink()
            done.append({"file": file_name, "esito": out.get("esito"), "id": out.get("item", {}).get("id")})
        else:
            failed.append({"file": file_name, "errore": out.get("errore")})
            if out.get("tipo_errore") == "REGISTRO_IRRAGGIUNGIBILE":
                # still down: a replayed write was re-queued by the failed call; drop the duplicate file
                for extra in set(_pending(pending_dir)) - {file_name} - {d["file"] for d in done}:
                    data = json.loads((pending_dir / extra).read_text(encoding="utf-8"))
                    if data.get("arguments", {}).get("request_key") == request["arguments"].get("request_key"):
                        (pending_dir / extra).unlink()
                break
    return {"ok": not failed, "ripetute": done, "ancora_in_coda": failed}


def backend(client: str | None = None):
    """The backend this PC should use: the AWS service when configured, else the local register."""
    url = remote_url()
    return RemoteConoscenza(url, client=client) if url else Conoscenza(client=client)


_LOG_OP = {"record": "WRITE", "supersede": "SUPERSEDE", "link": "LINK", "approve": "APPROVE", "search": "SEARCH",
           "read": "READ", "brief": "BRIEF", "log": "READ"}
