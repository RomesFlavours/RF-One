"""Automated synthetic tests for the shared Identity / Authority /
Operational Signature foundation (RFONE_SHARED_IDENTITY_AUTHORITY_SIGNATURE_001).

Mirrors the established `*_validation.py` pattern (see
`clover_acquisition_validation.py`): synthetic fixture, disposable
database, always rolled back, never touches real data. Deliberately covers
only the essential behaviors the task calls out — this is a foundation
test, not an exhaustive suite, and no Domain is exercised here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt as pyjwt
from sqlalchemy.orm import Session, sessionmaker

from . import acting_identity_service as identity_svc
from . import authority_service as authority_svc
from . import models as m
from . import operational_signature_service as signature_svc
from .authority_service import AuthorityContextError, AuthorizationContext
from .technical.cognito_jwt import CognitoAuthConfig, CognitoTokenError, _validate_claims

UTC = timezone.utc


def _aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_valid_acting_identity(session, result)
            _test_authorization_allowed_denied_by_scope(session, result)
            _test_tenant_context_isolation(session, result)
            _test_operational_signature_captures_required_fields(session, result)
            _test_historical_signature_cannot_be_silently_overwritten(session, result)
            _test_cognito_jwt_local_verification(result)
        finally:
            session.rollback()
    return result


# ---------------------------------------------------------------------------
# 1. Valid Acting Identity
# ---------------------------------------------------------------------------


def _test_valid_acting_identity(session: Session, result: ValidationResult) -> None:
    identity = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Ada Lovelace")
    result.check(
        "a created Acting Identity has a permanent id and the requested kind/display_name",
        identity.id is not None and identity.kind == m.HUMAN_USER and identity.display_name == "Ada Lovelace"
        and identity.is_active,
    )

    # Core doc §2.1 — a label change must never change the identity itself.
    original_id = identity.id
    identity.display_name = "Ada, Countess of Lovelace"
    session.flush()
    reloaded = identity_svc.get_identity(session, original_id)
    result.check(
        "changing the display_name (a configurable Attribute) never changes the permanent identifier",
        reloaded is not None and reloaded.id == original_id,
    )

    # Just-in-time provisioning from an already-verified (provider, subject)
    # must be idempotent — a returning subject resolves to the SAME row.
    first = identity_svc.get_or_create_identity_for_verified_subject(
        session, provider="cognito", subject="sub-abc-123", display_name="Grace Hopper",
    )
    second = identity_svc.get_or_create_identity_for_verified_subject(
        session, provider="cognito", subject="sub-abc-123", display_name="Grace Hopper (different label)",
    )
    result.check(
        "resolving the same verified (provider, subject) twice returns the same permanent identity, "
        "never a duplicate",
        first.id == second.id,
    )

    result.check(
        "an invalid Acting Identity kind is rejected",
        _raises(ValueError, lambda: identity_svc.create_identity(session, kind="NOT_A_KIND", display_name="x")),
    )


# ---------------------------------------------------------------------------
# 2. Authorization allowed/denied by scope
# ---------------------------------------------------------------------------


def _test_authorization_allowed_denied_by_scope(session: Session, result: ValidationResult) -> None:
    actor = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Scoped User")
    authority_svc.grant_authority(
        session, actor=actor, domain="RESTAURANT", action="EDIT",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=101, module="PURCHASING",
    )

    in_scope = authority_svc.authorize(
        session, actor=actor, action="EDIT",
        context=AuthorizationContext(
            domain="RESTAURANT", module="PURCHASING", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=101,
        ),
    )
    result.check("a grant authorizes the EXACT action/domain/module/scope it was created for", in_scope.allowed)

    other_unit = authority_svc.authorize(
        session, actor=actor, action="EDIT",
        context=AuthorizationContext(
            domain="RESTAURANT", module="PURCHASING", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=202,
        ),
    )
    result.check(
        "the SAME action/domain/module is denied for a DIFFERENT Operational Unit scope_id — no "
        "hierarchical/global leakage from one grant",
        not other_unit.allowed,
    )

    other_action = authority_svc.authorize(
        session, actor=actor, action="APPROVE",
        context=AuthorizationContext(
            domain="RESTAURANT", module="PURCHASING", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=101,
        ),
    )
    result.check("an action the grant does not cover is denied, even in the exact same scope", not other_action.allowed)

    # Wildcard action + GLOBAL scope.
    admin = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Admin User")
    authority_svc.grant_authority(
        session, actor=admin, domain="RESTAURANT", action=m.AUTHORITY_WILDCARD,
        scope_type=m.SCOPE_GLOBAL, scope_id=None,
    )
    admin_decision = authority_svc.authorize(
        session, actor=admin, action="APPROVE",
        context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=999),
    )
    result.check(
        "a GLOBAL-scope wildcard-action grant authorizes any action in that domain, in any scope",
        admin_decision.allowed,
    )

    revoked_actor = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Revoked User")
    grant = authority_svc.grant_authority(
        session, actor=revoked_actor, domain="RESTAURANT", action="VIEW",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=101,
    )
    authority_svc.revoke_authority(session, grant_id=grant.id)
    revoked_decision = authority_svc.authorize(
        session, actor=revoked_actor, action="VIEW",
        context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=101),
    )
    result.check("a revoked grant no longer authorizes anything, but is never deleted", not revoked_decision.allowed)
    result.check(
        "the revoked grant row itself still exists (Historical Integrity — provable as having once existed)",
        session.get(m.AuthorityGrant, grant.id) is not None,
    )

    result.check(
        "authorize() with an invalid scope_type raises rather than silently denying/allowing",
        _raises(
            AuthorityContextError,
            lambda: authority_svc.authorize(
                session, actor=actor, action="EDIT",
                context=AuthorizationContext(domain="RESTAURANT", scope_type="NOT_A_SCOPE", scope_id=1),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# 3. Tenant / context isolation
# ---------------------------------------------------------------------------


def _test_tenant_context_isolation(session: Session, result: ValidationResult) -> None:
    tenant_a_user = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Tenant A User")
    tenant_b_user = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Tenant B User")

    authority_svc.grant_authority(
        session, actor=tenant_a_user, domain="RESTAURANT", action="VIEW",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=501,
    )
    authority_svc.grant_authority(
        session, actor=tenant_b_user, domain="RESTAURANT", action="VIEW",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=502,
    )

    a_in_own_scope = authority_svc.authorize(
        session, actor=tenant_a_user, action="VIEW",
        context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=501),
    )
    a_in_b_scope = authority_svc.authorize(
        session, actor=tenant_a_user, action="VIEW",
        context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=502),
    )
    b_in_a_scope = authority_svc.authorize(
        session, actor=tenant_b_user, action="VIEW",
        context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=501),
    )
    result.check("Tenant A's own grant authorizes Tenant A in Tenant A's own scope", a_in_own_scope.allowed)
    result.check(
        "Tenant A is NEVER authorized in Tenant B's scope merely by both sharing a domain/action",
        not a_in_b_scope.allowed,
    )
    result.check(
        "Tenant B's grant never leaks to Tenant A's identity, and vice versa — no cross-tenant bleed",
        not b_in_a_scope.allowed,
    )

    result.check(
        "a context with NO explicit scope_id (only a non-GLOBAL scope_type) is refused outright — "
        "the shared code can never silently fall back to a default/global tenant",
        _raises(
            AuthorityContextError,
            lambda: authority_svc.authorize(
                session, actor=tenant_a_user, action="VIEW",
                context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=None),
            ),
        ),
    )

    # Concurrent-safety-relevant: two isolated contexts evaluated back to
    # back against the SAME session produce independent, correct results —
    # no shared mutable module-level "current tenant" state leaks between
    # calls (there is none in this module by construction; this proves the
    # observable behavior matches that design).
    result.check(
        "re-evaluating both tenants' own scopes again yields the same correct, independent results",
        authority_svc.authorize(
            session, actor=tenant_b_user, action="VIEW",
            context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=502),
        ).allowed
        and not authority_svc.authorize(
            session, actor=tenant_a_user, action="VIEW",
            context=AuthorizationContext(domain="RESTAURANT", scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=502),
        ).allowed,
    )


# ---------------------------------------------------------------------------
# 4. Operational Signature captures actor/action/context/assurance
# ---------------------------------------------------------------------------


def _test_operational_signature_captures_required_fields(session: Session, result: ValidationResult) -> None:
    actor = identity_svc.create_identity(session, kind=m.AI_AGENT, display_name="RF-One Recommendation Engine")
    occurred_at = datetime(2026, 9, 5, 14, 32, 10, tzinfo=UTC)

    signature = signature_svc.record_operational_signature(
        session, actor=actor, action="CANDIDATE_OUTCOME_CHANGED", domain="SELECTION", module="CANDIDATE_DECISIONS",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=7,
        object_type="Candidate", object_id=42,
        before_state={"outcome": "STOP"}, after_state={"outcome": "HIRABLE"},
        applicable_version="rule-set-v4", authority_used="AuthorityGrant#does-not-matter-for-this-test",
        reason="Additional reference check completed", assurance_level=m.EXPLICIT_CONFIRMATION,
        occurred_at=occurred_at,
    )
    session.flush()
    reloaded = signature_svc.get_signature(session, signature.id)

    result.check(
        "the signature captures actor identity and its actor_kind at signing time",
        reloaded is not None and reloaded.acting_identity_id == actor.id and reloaded.actor_kind == m.AI_AGENT,
    )
    result.check(
        "the signature captures action + domain/module + explicit scope (the tenant/context)",
        reloaded.action == "CANDIDATE_OUTCOME_CHANGED" and reloaded.domain == "SELECTION"
        and reloaded.module == "CANDIDATE_DECISIONS"
        and reloaded.scope_type == m.SCOPE_OPERATIONAL_UNIT and reloaded.scope_id == 7,
    )
    result.check(
        "the signature captures object, before/after state, applicable version, authority used and reason",
        reloaded.object_type == "Candidate" and reloaded.object_id == "42"
        and reloaded.before_state == {"outcome": "STOP"} and reloaded.after_state == {"outcome": "HIRABLE"}
        and reloaded.applicable_version == "rule-set-v4"
        and reloaded.authority_used == "AuthorityGrant#does-not-matter-for-this-test"
        and reloaded.reason == "Additional reference check completed",
    )
    result.check(
        "the signature captures the exact requested assurance level and the exact occurred_at timestamp",
        reloaded.assurance_level == m.EXPLICIT_CONFIRMATION and reloaded.occurred_at == occurred_at,
    )
    result.check(
        "an invalid assurance level is rejected",
        _raises(
            ValueError,
            lambda: signature_svc.record_operational_signature(
                session, actor=actor, action="X", domain="SELECTION",
                scope_type=m.SCOPE_GLOBAL, scope_id=None, assurance_level="NOT_A_LEVEL",
            ),
        ),
    )
    result.check(
        "all three documented assurance levels are each independently recordable",
        all(
            signature_svc.record_operational_signature(
                session, actor=actor, action="X", domain="SELECTION",
                scope_type=m.SCOPE_GLOBAL, scope_id=None, assurance_level=level,
            ).assurance_level == level
            for level in m.OPERATIONAL_SIGNATURE_ASSURANCE_LEVELS
        ),
    )


# ---------------------------------------------------------------------------
# 5. Historical audit record cannot be silently overwritten
# ---------------------------------------------------------------------------


def _test_historical_signature_cannot_be_silently_overwritten(session: Session, result: ValidationResult) -> None:
    actor = identity_svc.create_identity(session, kind=m.HUMAN_USER, display_name="Pino Rossi")

    original = signature_svc.record_operational_signature(
        session, actor=actor, action="CANDIDATE_OUTCOME_CHANGED", domain="SELECTION",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=7,
        before_state={"outcome": "STOP"}, after_state={"outcome": "HIRABLE"},
        reason="Initial review", assurance_level=m.NORMAL_AUTHENTICATED_ACTION,
    )
    session.flush()
    snapshot = {
        "action": original.action, "before_state": original.before_state, "after_state": original.after_state,
        "reason": original.reason, "assurance_level": original.assurance_level,
        "occurred_at": original.occurred_at, "corrects_signature_id": original.corrects_signature_id,
    }

    correction = signature_svc.record_operational_signature(
        session, actor=actor, action="CANDIDATE_OUTCOME_CHANGED", domain="SELECTION",
        scope_type=m.SCOPE_OPERATIONAL_UNIT, scope_id=7,
        before_state={"outcome": "HIRABLE"}, after_state={"outcome": "STOP"},
        reason="Correction — reference check later failed", assurance_level=m.EXPLICIT_CONFIRMATION,
        corrects=original,
    )
    session.flush()
    session.expire_all()

    reloaded_original = signature_svc.get_signature(session, original.id)
    # SQLite round-trips `DateTime(timezone=True)` as offset-naive (same
    # quirk `acquisition.py`'s own `_aware_utc` works around) — normalize
    # before comparing rather than treating a driver detail as a real diff.
    reloaded_occurred_at = _aware_utc(reloaded_original.occurred_at)
    result.check(
        "the ORIGINAL row's every evidentiary field is byte-for-byte unchanged after a correction is recorded",
        reloaded_original.action == snapshot["action"]
        and reloaded_original.before_state == snapshot["before_state"]
        and reloaded_original.after_state == snapshot["after_state"]
        and reloaded_original.reason == snapshot["reason"]
        and reloaded_original.assurance_level == snapshot["assurance_level"]
        and reloaded_occurred_at == _aware_utc(snapshot["occurred_at"])
        and reloaded_original.corrects_signature_id == snapshot["corrects_signature_id"],
    )
    result.check(
        "a correction is a NEW, distinct row — never the same id as the original",
        correction.id != original.id,
    )
    result.check(
        "the correction points BACK at the original via corrects_signature_id — the original never points forward",
        correction.corrects_signature_id == original.id,
    )
    result.check(
        "operational_signature_service exposes no update/delete function for OperationalSignature at all",
        not hasattr(signature_svc, "update_operational_signature")
        and not hasattr(signature_svc, "delete_operational_signature"),
    )


# ---------------------------------------------------------------------------
# Bonus: local Cognito JWT verification (no network, no real User Pool)
# ---------------------------------------------------------------------------


def _test_cognito_jwt_local_verification(result: ValidationResult) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    config = CognitoAuthConfig(region="us-east-1", user_pool_id="us-east-1_TESTPOOL", app_client_id="test-client-id")

    now = datetime.now(UTC)
    valid_token = pyjwt.encode(
        {
            "sub": "cognito-sub-123", "email": "user@example.com", "token_use": "id",
            "aud": config.app_client_id, "iss": config.issuer,
            "iat": now, "exp": now + timedelta(hours=1),
        },
        private_key, algorithm="RS256",
    )
    claims = _validate_claims(valid_token, public_key, config)
    result.check(
        "a locally-signed, correctly-issued/audienced ID token verifies successfully with no network call",
        claims.subject == "cognito-sub-123" and claims.email == "user@example.com" and claims.token_use == "id",
    )

    expired_token = pyjwt.encode(
        {
            "sub": "cognito-sub-123", "token_use": "id", "aud": config.app_client_id, "iss": config.issuer,
            "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1),
        },
        private_key, algorithm="RS256",
    )
    result.check(
        "an expired token is rejected", _raises(CognitoTokenError, lambda: _validate_claims(expired_token, public_key, config)),
    )

    wrong_audience_token = pyjwt.encode(
        {
            "sub": "cognito-sub-123", "token_use": "id", "aud": "some-other-client-id", "iss": config.issuer,
            "iat": now, "exp": now + timedelta(hours=1),
        },
        private_key, algorithm="RS256",
    )
    result.check(
        "a token issued for a different App Client is rejected",
        _raises(CognitoTokenError, lambda: _validate_claims(wrong_audience_token, public_key, config)),
    )

    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged_token = pyjwt.encode(
        {
            "sub": "cognito-sub-123", "token_use": "id", "aud": config.app_client_id, "iss": config.issuer,
            "iat": now, "exp": now + timedelta(hours=1),
        },
        other_private_key, algorithm="RS256",
    )
    result.check(
        "a token signed by a DIFFERENT private key than the cached public key is rejected — proves real "
        "signature verification happens, not just claim inspection",
        _raises(CognitoTokenError, lambda: _validate_claims(forged_token, public_key, config)),
    )


def _raises(exc_type: type[Exception], fn) -> bool:
    try:
        fn()
    except exc_type:
        return True
    except Exception:
        return False
    return False
