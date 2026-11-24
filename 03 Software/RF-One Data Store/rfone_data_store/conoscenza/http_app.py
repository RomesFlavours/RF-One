"""Conoscenza HTTPS service (AWS App Runner): MCP over Streamable HTTP + OAuth.

Endpoints
- `GET  /health`                                   liveness (no database access)
- `POST /mcp`                                      MCP JSON-RPC (initialize, tools/list, tools/call, ping)
- `GET  /.well-known/oauth-protected-resource[/mcp]`   RFC 9728 metadata
- `GET  /.well-known/oauth-authorization-server`  RFC 8414 metadata
- `POST /oauth/register`                           RFC 7591 dynamic client registration (ChatGPT)
- `GET|POST /oauth/authorize`                      authorization code + PKCE (S256)
- `POST /oauth/token`                              code / refresh-token exchange

Authentication on `/mcp`: `Authorization: Bearer <token>`, where the token
is either a tool credential (Claude Code, Codex: one token per person+tool)
or an OAuth access token issued to ChatGPT. An OAuth authorization is
granted only by entering the ChatGPT credential key of the person on the
authorization page, so the grant is bound to that person and to the tool
CHATGPT. Every operation is attributed to person + tool by `service.py`.

The database is reached only from inside the VPC; this service is the only
public entry point. The schema is never migrated at startup.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import time
import uuid
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from flask import Flask, Response, jsonify, request
from sqlalchemy import select

from . import models as k
from .api import Conoscenza, dispatch
from .mcp_server import PROTOCOL_VERSION, TOOLS
from .store import (AuthenticationError, authenticate, database_url, make_engine, session_factory, token_hash,
                    utcnow)

CODE_TTL = timedelta(minutes=10)
ACCESS_TTL = timedelta(hours=8)
REFRESH_TTL = timedelta(days=90)
SCOPE = "conoscenza"
SERVER_INSTRUCTIONS = (
    "Registro Conoscenza di RF-One (decisioni di Pino, correzioni motivate, stato dei lavori). All'inizio "
    "chiamare conoscenza_contesto; prima di ogni proposta conoscenza_cerca (anche più volte con parole diverse); "
    "registrare subito decisioni e correzioni esplicite con conoscenza_registra e gli esiti del lavoro con "
    "conoscenza_lavoro. Alla domanda 'A che punto siamo?' usare conoscenza_contesto e conoscenza_cerca sullo "
    "stato dei lavori.")

app = Flask(__name__)
_factory = None


def _db():
    global _factory
    if _factory is None:
        _factory = session_factory(make_engine(database_url()))
    return _factory()


def _base_url() -> str:
    configured = os.environ.get("RFONE_CONOSCENZA_PUBLIC_URL")
    if configured:
        return configured.rstrip("/")
    return request.host_url.rstrip("/").replace("http://", "https://")


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


def _unauthorized(message: str = "authentication required") -> Response:
    response = jsonify({"error": "invalid_token", "error_description": message})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = (
        f'Bearer resource_metadata="{_base_url()}/.well-known/oauth-protected-resource", scope="{SCOPE}"')
    return response


@app.after_request
def _security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "rf-one-conoscenza",
                    "revision": os.environ.get("RFONE_RELEASE_REVISION", "local")})


# ---------------------------------------------------------------------------
# MCP (Streamable HTTP, JSON responses)
# ---------------------------------------------------------------------------


@app.route("/mcp", methods=["GET", "DELETE"])
def mcp_other():
    return Response(status=405, headers={"Allow": "POST"})


@app.post("/mcp")
def mcp():
    token = _bearer()
    if not token:
        return _unauthorized()
    with _db() as db:
        try:
            who = authenticate(db, token)
        except AuthenticationError as exc:
            return _unauthorized(str(exc))
    try:
        message = request.get_json(force=True)
    except Exception:
        return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), 400
    if isinstance(message, list):
        return jsonify({"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32600, "message": "Batch requests are not supported"}}), 400
    method, mid = message.get("method"), message.get("id")
    session_id = request.headers.get("Mcp-Session-Id") or uuid.uuid4().hex
    headers = {"Mcp-Session-Id": session_id}
    if mid is None:  # notification
        return Response(status=202, headers=headers)
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
        result = {"protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "rf-one-conoscenza", "version": "1.0.0"},
                  "instructions": SERVER_INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        args = dict(params.get("arguments") or {})
        args.setdefault("session_ref", f"{who.client.lower()}-http-{session_id[:16]}")
        api = Conoscenza(token, url=database_url())
        api._factory = _factory  # reuse the service's connection pool
        try:
            payload = dispatch(api, params.get("name"), args)
        except Exception as exc:  # never return a stack trace to the client
            app.logger.exception("tool call failed")
            payload = {"ok": False, "errore": f"Errore interno del servizio: {type(exc).__name__}"}
        result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=1,
                                                                  default=str)}],
                  "isError": not payload.get("ok", False)}
    else:
        return jsonify({"jsonrpc": "2.0", "id": mid,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}}), 200, headers
    return jsonify({"jsonrpc": "2.0", "id": mid, "result": result}), 200, headers


# ---------------------------------------------------------------------------
# OAuth 2.1 (for ChatGPT)
# ---------------------------------------------------------------------------


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource():
    base = _base_url()
    return jsonify({"resource": f"{base}/mcp", "authorization_servers": [base], "scopes_supported": [SCOPE],
                    "bearer_methods_supported": ["header"], "resource_name": "RF-One Conoscenza"})


@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/openid-configuration")
def authorization_server():
    base = _base_url()
    return jsonify({"issuer": base, "authorization_endpoint": f"{base}/oauth/authorize",
                    "token_endpoint": f"{base}/oauth/token", "registration_endpoint": f"{base}/oauth/register",
                    "response_types_supported": ["code"], "grant_types_supported": ["authorization_code",
                                                                                    "refresh_token"],
                    "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"],
                    "scopes_supported": [SCOPE]})


def _oauth_error(error: str, description: str, status: int = 400):
    return jsonify({"error": error, "error_description": description}), status


@app.post("/oauth/register")
def register():
    body = request.get_json(silent=True) or {}
    uris = body.get("redirect_uris") or []
    if not isinstance(uris, list) or not uris or not all(
            isinstance(u, str) and urlsplit(u).scheme == "https" and urlsplit(u).netloc for u in uris):
        return _oauth_error("invalid_redirect_uri", "redirect_uris must be a non-empty list of https URLs")
    client_id = "cnz-" + secrets.token_urlsafe(18)
    with _db() as db:
        db.add(k.OAuthClient(client_id=client_id, client_name=str(body.get("client_name") or "")[:200] or None,
                             redirect_uris=json.dumps(uris), created_at=utcnow()))
        db.commit()
    return jsonify({"client_id": client_id, "client_id_issued_at": int(time.time()), "redirect_uris": uris,
                    "client_name": body.get("client_name"), "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                    "scope": SCOPE}), 201


def _client_and_redirect(db, client_id: str | None, redirect_uri: str | None):
    client = db.scalar(select(k.OAuthClient).where(k.OAuthClient.client_id == (client_id or "")))
    if client is None or redirect_uri not in json.loads(client.redirect_uris):
        return None
    return client


AUTHORIZE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RF-One Conoscenza</title>
<style>
:root{{--bg:#f6f6f4;--fg:#1c1c1a;--muted:#5d5d58;--line:#d9d9d4;--card:#fff;--accent:#2f5d50}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ececea;--muted:#a8a8a2;--line:#33332f;--card:#1e1e1c;--accent:#7fb8a6}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:480px;margin:8vh auto;padding:0 16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:24px}}
h1{{font-size:1.3rem;margin:0 0 12px}} hr{{border:0;border-top:1px solid var(--line);margin:0}}
.help{{text-align:right;margin:6px 0 16px}} .help a{{color:var(--accent);font-size:.9rem}}
label{{display:block;font-weight:600;margin:12px 0 6px}}
input[type=password]{{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}}
button{{margin-top:16px;padding:10px 16px;border:0;border-radius:6px;background:var(--accent);color:#fff;font-weight:600;cursor:pointer}}
.err{{color:#b3261e;margin-top:10px}} p{{color:var(--muted)}}
dialog{{max-width:440px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--fg)}}
dialog .x{{position:sticky;top:0;float:right;background:none;color:var(--fg);margin:0;padding:0 4px;font-size:1.3rem}}
</style></head><body><main><div class="card">
<h1>Connect ChatGPT to RF-One Conoscenza</h1><hr>
<div class="help"><a href="#" onclick="document.getElementById('hw').showModal();return false">How this page works</a></div>
<p>{client_name} is asking to read and write the RF-One Conoscenza register on your behalf.</p>
<form method="post">{hidden}
<label for="k">ChatGPT access key</label>
<input id="k" name="access_key" type="password" autocomplete="off" required autofocus>
{error}<button type="submit">Authorize</button></form></div>
<dialog id="hw"><button class="x" aria-label="Close" onclick="this.closest('dialog').close()">&times;</button>
<h2>How this page works</h2><p>This page links the ChatGPT connector to the RF-One Conoscenza register.
Enter the ChatGPT access key you were given for Conoscenza and press Authorize. ChatGPT then receives a
token that lets it search and record decisions, corrections and work status in the register, always
attributed to you and to the tool ChatGPT. Nothing else in RF-One becomes accessible. A wrong key grants
nothing.</p></dialog></main></body></html>"""


@app.route("/oauth/authorize", methods=["GET", "POST"])
def authorize():
    source = request.values
    fields = {name: source.get(name) for name in ("response_type", "client_id", "redirect_uri", "code_challenge",
                                                  "code_challenge_method", "state", "scope", "resource")}
    with _db() as db:
        client = _client_and_redirect(db, fields["client_id"], fields["redirect_uri"])
        if client is None:
            return _oauth_error("invalid_client", "Unknown client or redirect_uri")
        if fields["response_type"] != "code" or fields["code_challenge_method"] != "S256" or \
                not fields["code_challenge"]:
            return _oauth_error("invalid_request", "response_type=code with PKCE S256 is required")
        error = ""
        if request.method == "POST":
            key = (request.form.get("access_key") or "").strip()
            credential = db.scalar(select(k.KnowledgeClient).where(
                k.KnowledgeClient.token_sha256 == token_hash(key), k.KnowledgeClient.client == "CHATGPT",
                k.KnowledgeClient.active.is_(True))) if key else None
            if credential is None:
                time.sleep(1.0)
                error = '<div class="err">This key is not valid.</div>'
            else:
                code = secrets.token_urlsafe(32)
                db.add(k.OAuthGrant(kind="CODE", token_sha256=token_hash(code), oauth_client_id=client.client_id,
                                    credential_id=credential.id, redirect_uri=fields["redirect_uri"],
                                    code_challenge=fields["code_challenge"], expires_at=utcnow() + CODE_TTL,
                                    created_at=utcnow()))
                db.add(k.KnowledgeAccess(client="CHATGPT", person_id=credential.person_id, operation="AUTH",
                                         outcome="OK", detail=f"OAuth autorizzato per {client.client_name or client.client_id}",
                                         occurred_at=utcnow()))
                db.commit()
                query = {"code": code}
                if fields["state"]:
                    query["state"] = fields["state"]
                sep = "&" if "?" in fields["redirect_uri"] else "?"
                return Response(status=302, headers={"Location": fields["redirect_uri"] + sep + urlencode(query)})
        hidden = "".join(f'<input type="hidden" name="{n}" value="{html.escape(v or "", quote=True)}">'
                         for n, v in fields.items() if v)
        page = AUTHORIZE_PAGE.format(client_name=html.escape(client.client_name or "ChatGPT"), hidden=hidden,
                                     error=error)
        response = Response(page, mimetype="text/html")
        response.headers["Content-Security-Policy"] = ("default-src 'none'; style-src 'unsafe-inline'; "
                                                       "script-src 'unsafe-inline'; form-action 'self' https:; "
                                                       "frame-ancestors 'none'")
        return response


def _issue_tokens(db, oauth_client_id: str, credential_id: int):
    access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    now = utcnow()
    db.add(k.OAuthGrant(kind="ACCESS", token_sha256=token_hash(access), oauth_client_id=oauth_client_id,
                        credential_id=credential_id, expires_at=now + ACCESS_TTL, created_at=now))
    db.add(k.OAuthGrant(kind="REFRESH", token_sha256=token_hash(refresh), oauth_client_id=oauth_client_id,
                        credential_id=credential_id, expires_at=now + REFRESH_TTL, created_at=now))
    db.commit()
    return jsonify({"access_token": access, "token_type": "Bearer", "expires_in": int(ACCESS_TTL.total_seconds()),
                    "refresh_token": refresh, "scope": SCOPE})


def _aware(moment):
    from datetime import UTC
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


@app.post("/oauth/token")
def token():
    form = request.form
    grant_type = form.get("grant_type")
    with _db() as db:
        if grant_type == "authorization_code":
            grant = db.scalar(select(k.OAuthGrant).where(k.OAuthGrant.token_sha256 == token_hash(form.get("code") or ""),
                                                         k.OAuthGrant.kind == "CODE"))
            if grant is None or grant.used or _aware(grant.expires_at) <= utcnow():
                return _oauth_error("invalid_grant", "Unknown, used or expired code")
            if form.get("client_id") and form.get("client_id") != grant.oauth_client_id:
                return _oauth_error("invalid_grant", "Code issued to another client")
            if form.get("redirect_uri") and form.get("redirect_uri") != grant.redirect_uri:
                return _oauth_error("invalid_grant", "redirect_uri mismatch")
            verifier = form.get("code_verifier") or ""
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            if not verifier or not secrets.compare_digest(challenge, grant.code_challenge or ""):
                return _oauth_error("invalid_grant", "PKCE verification failed")
            grant.used = True
            return _issue_tokens(db, grant.oauth_client_id, grant.credential_id)
        if grant_type == "refresh_token":
            grant = db.scalar(select(k.OAuthGrant).where(
                k.OAuthGrant.token_sha256 == token_hash(form.get("refresh_token") or ""),
                k.OAuthGrant.kind == "REFRESH"))
            if grant is None or grant.used or _aware(grant.expires_at) <= utcnow():
                return _oauth_error("invalid_grant", "Unknown, used or expired refresh token")
            credential = db.get(k.KnowledgeClient, grant.credential_id)
            if credential is None or not credential.active:
                return _oauth_error("invalid_grant", "Credential disabled")
            grant.used = True  # rotation
            return _issue_tokens(db, grant.oauth_client_id, grant.credential_id)
    return _oauth_error("unsupported_grant_type", "Use authorization_code or refresh_token")
