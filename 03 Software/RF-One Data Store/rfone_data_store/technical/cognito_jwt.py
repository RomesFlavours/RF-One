"""Amazon Cognito JWT verification boundary
(RFONE_SHARED_IDENTITY_AUTHORITY_SIGNATURE_001).

Prepares the application authentication boundary for Cognito-issued JWTs
(Identity Authority and Security Architecture.md §7) — this module does
NOT create any AWS Cognito resource, and provider configuration (region,
User Pool id, App Client id) is read from the environment, never hardcoded,
never required to be present. Until a real User Pool exists, `load_cognito_
config_from_env()` simply returns `None` and nothing in this module is
reachable — the rest of RF-One keeps using `acting_identity_service`'s
existing pre-Authentication resolver exactly as before (no Domain is
touched by this module).

Verification happens LOCALLY, never against Cognito on every request:
Cognito's public signing keys (JWKS) are fetched over the network only the
first time a given key id is seen (or after the in-memory cache's lifespan
expires) — `jwt.PyJWKClient`'s own documented caching behavior, reused here
rather than re-implemented. A normal authenticated request never makes a
network call to Cognito; it only verifies an RS256 signature locally
against an already-cached public key.

RF-One never implements password/session storage of its own (Architecture
doc §7, §15) — this module only ever verifies a token Cognito already
issued; it has no login, password reset, or credential-storage code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient


class CognitoConfigurationError(RuntimeError):
    """Raised only if code calls `verify_cognito_jwt()` without first
    checking `load_cognito_config_from_env()` returned a config — never
    raised merely because Cognito is not yet provisioned in this
    environment (that case returns `None`, not an exception)."""


class CognitoTokenError(RuntimeError):
    """Raised for any local verification failure — bad signature, expired,
    wrong issuer/audience/token_use, or an unrecognized key id. Always
    means "treat this request as unauthenticated"; never leaks which
    specific check failed beyond a generic, non-sensitive reason."""


@dataclass(frozen=True)
class CognitoAuthConfig:
    """External provider configuration — read from the environment, never
    hardcoded and never committed (Architecture doc §15: "no API
    credentials committed in source code"). No AWS resource is implied by
    this object's mere existence; it only describes where to verify a
    token against, IF one is presented."""

    region: str
    user_pool_id: str
    app_client_id: str

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"


REGION_ENV_VAR = "RFONE_COGNITO_REGION"
USER_POOL_ID_ENV_VAR = "RFONE_COGNITO_USER_POOL_ID"
APP_CLIENT_ID_ENV_VAR = "RFONE_COGNITO_APP_CLIENT_ID"


def load_cognito_config_from_env() -> CognitoAuthConfig | None:
    """Returns `None` (never raises) when Cognito is not configured in this
    environment — the normal, expected state until a real User Pool exists
    and its identifiers are provided externally (task instruction: do not
    create Cognito resources yet; keep provider configuration external)."""
    region = os.environ.get(REGION_ENV_VAR)
    user_pool_id = os.environ.get(USER_POOL_ID_ENV_VAR)
    app_client_id = os.environ.get(APP_CLIENT_ID_ENV_VAR)
    if not (region and user_pool_id and app_client_id):
        return None
    return CognitoAuthConfig(region=region, user_pool_id=user_pool_id, app_client_id=app_client_id)


@dataclass(frozen=True)
class VerifiedTokenClaims:
    """The minimal, already-verified result `acting_identity_service` needs
    to resolve/just-in-time-provision an `ActingIdentity` — never the full
    raw token re-exposed as "trusted" beyond what was actually checked."""

    subject: str  # Cognito "sub" — the stable, permanent per-user identifier
    email: str | None
    token_use: str
    raw_claims: dict[str, Any]


# One cached `PyJWKClient` per JWKS URL for the life of the process —
# `PyJWKClient` itself performs the actual in-memory key caching
# (`cache_keys=True`) so a verification call only fetches over the network
# on a cache miss (an unrecognized `kid`) or after `lifespan` expires, never
# on every request.
_jwk_clients: dict[str, PyJWKClient] = {}
_JWKS_CACHE_LIFESPAN_SECONDS = 3600


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, cache_keys=True, lifespan=_JWKS_CACHE_LIFESPAN_SECONDS)
        _jwk_clients[jwks_url] = client
    return client


def _validate_claims(token: str, signing_key: Any, config: CognitoAuthConfig) -> VerifiedTokenClaims:
    """The pure verification/validation step, factored out from key
    retrieval so it can be exercised directly in tests with a locally
    generated keypair — no network call, no real Cognito User Pool needed
    to prove the RS256/issuer/audience/token_use logic itself is correct."""
    try:
        claims = jwt.decode(
            token, signing_key, algorithms=["RS256"], issuer=config.issuer,
            options={"require": ["exp", "iss", "sub", "token_use"], "verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise CognitoTokenError(f"JWT verification failed: {exc}") from None

    # Cognito ID tokens carry `aud`; Cognito ACCESS tokens carry `client_id`
    # instead and have no `aud` claim at all — both must still be checked
    # against the expected App Client, just via different claims.
    token_use = claims.get("token_use")
    if token_use == "id":
        if claims.get("aud") != config.app_client_id:
            raise CognitoTokenError("Unexpected audience claim.")
    elif token_use == "access":
        if claims.get("client_id") != config.app_client_id:
            raise CognitoTokenError("Unexpected client_id claim.")
    else:
        raise CognitoTokenError(f"Unexpected token_use claim: {token_use!r}")

    return VerifiedTokenClaims(
        subject=claims["sub"], email=claims.get("email"), token_use=token_use, raw_claims=claims,
    )


def verify_cognito_jwt(token: str, config: CognitoAuthConfig) -> VerifiedTokenClaims:
    """Verifies `token` LOCALLY against Cognito's cached public signing
    keys and returns its verified claims, or raises `CognitoTokenError`.
    This is the ONE function the web/API layer calls per incoming request
    once Cognito is configured — no Domain calls this directly; its result
    feeds `acting_identity_service`'s subject-based identity resolution."""
    jwk_client = _get_jwk_client(config.jwks_url)
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as exc:
        raise CognitoTokenError(f"Could not resolve a signing key for this token: {exc}") from None
    return _validate_claims(token, signing_key, config)
