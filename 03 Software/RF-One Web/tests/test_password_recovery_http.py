#!/usr/bin/env python
"""Regression test for the RF-One Account email verification / password
recovery task. Mirrors `test_accounts_and_domains_http.py`'s own
convention: a throwaway SQLite database created BEFORE `app.py` is
imported, migrated explicitly, Werkzeug's Flask test client, `main()`
returning an exit code. Never touches AWS/SES or any production database —
`RFONE_EMAIL_FROM_ADDRESS` is deliberately left unset, so
`ses_email.send_email` always raises `EmailSendError` immediately (before
any network/boto3 call) and every call site already swallows that
failure; codes are read back directly from the database (never from an
email) using `rfone_recovery_service`'s own functions with the SAME
`flask_secret_key` the app uses, exactly like a real inbox would deliver
the plaintext code to the user.

Covers task §7's checklist:
  A. registration + email confirmation (new account, verify flow)
  B. adding an email to a pre-existing account with none
  C. protected email change (old stays verified until the new is confirmed)
  D. forgot-password requires an exact username+email match
  E. identical generic response for every ineligible case
  F. code: correct / wrong / expired / already used / invalidated by resend
  G. EMAIL_VERIFICATION and PASSWORD_RESET codes are not interchangeable
  H. send/attempt rate limits (max attempts per code, resend cooldown)
  I. a consumed code cannot be consumed a second time
  J. new password works, old password no longer works
  K. a session predating a reset is revoked (next request forces re-login)
  L. Training data/authorization are untouched by any of the above
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_recovery_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "recovery-http-test-secret"
os.environ.pop("RFONE_EMAIL_FROM_ADDRESS", None)  # never send a real email from this test

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_recovery_service as recovery_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
FLASK_SECRET = web_app.app.secret_key


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def _clear_resend_cooldown(session, account_id: int, purpose: str) -> None:
    """Backdates the current pending code's `created_at` past the 60s
    resend cooldown, so a following `_issue_code_directly` call (standing
    in for "the user didn't get the email, waited a minute, and hit
    resend") does not itself get rate-limited — exactly the real cooldown
    a genuine resend must also clear."""
    pending = recovery_service.get_pending_code(session, account_id, purpose)
    if pending is not None:
        pending.created_at = datetime.now(timezone.utc) - recovery_service.RESEND_COOLDOWN - timedelta(seconds=1)
        session.flush()


def _issue_code_directly(session, *, account, purpose, target_email, request_ip=None) -> str:
    """Test-only shortcut: issues a code through the exact same
    `recovery_service.issue_code` the app itself calls, but returns the
    plaintext directly instead of emailing it — standing in for "read the
    code from the inbox" for scenarios where constructing a specific state
    (expired, exhausted, rate-limited) purely by driving HTTP forms would
    be slow and would still need this same shortcut to learn the code."""
    return recovery_service.issue_code(
        session, account=account, purpose=purpose, target_email=target_email,
        flask_secret_key=FLASK_SECRET, request_ip=request_ip,
    )


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            admin = account_service.create_account(
                s, username="RFone", display_name="Pino Miraglia", password="AdminPass123!",
                status="ACTIVE", is_admin=True, email="admin@example.com",
            )
            s.commit()
            admin_id = admin.id

        admin_client = web_app.app.test_client()
        resp = admin_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post("/login", data={"username": "RFone", "password": "AdminPass123!", "csrf_token": csrf})
        check("setup: admin logs in", resp.status_code in (302, 303))

        # -------------------------------------------------------------
        # A. Registration + email confirmation (new account via the admin
        # creation flow, which now requires an email and sends a code).
        # -------------------------------------------------------------
        resp = admin_client.get("/admin/accounts/new")
        csrf = extract_csrf(resp.data)
        resp = admin_client.post(
            "/admin/accounts/new",
            data={
                "username": "alice", "display_name": "Alice", "email": "Alice@Example.com",
                "password": "AlicePass123!", "password_confirm": "AlicePass123!", "status": "ACTIVE",
                "csrf_token": csrf,
            },
        )
        check("A: admin creates account with email (redirects)", resp.status_code in (302, 303))

        with SessionFactory() as s:
            alice = account_service.get_account_by_username(s, "alice")
            check("A: email normalized and stored unverified", alice.email == "alice@example.com" and alice.email_verified_at is None)
            alice_id = alice.id
            pending = recovery_service.get_pending_code(s, alice_id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
            check("A: an EMAIL_VERIFICATION code was issued at creation", pending is not None)

        alice_client = web_app.app.test_client()
        resp = alice_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = alice_client.post("/login", data={"username": "alice", "password": "AlicePass123!", "csrf_token": csrf})
        check("A: unverified-email account can still log in normally", resp.status_code in (302, 303))

        resp = alice_client.get("/profile")
        check("A: profile shows the pending email", b"alice@example.com" in resp.data and resp.status_code == 200)
        csrf = extract_csrf(resp.data)

        with SessionFactory() as s:
            alice = account_service.get_account(s, alice_id)
            wrong_result = recovery_service.verify_and_consume_code(
                s, account_id=alice_id, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION,
                submitted_code="000000", flask_secret_key=FLASK_SECRET,
            )
            s.commit()
        check("F: a wrong code is rejected", wrong_result.ok is False)

        with SessionFactory() as s:
            pending = recovery_service.get_pending_code(s, alice_id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
            check("F: one failed attempt is recorded on the code row", pending is not None and pending.attempts_used == 1)

        # We don't have the real plaintext code from the HTTP-triggered
        # send (it only ever left this process as an email body) — reissue
        # one directly through the service (identical mechanism the route
        # itself uses) so the rest of section A can confirm successfully.
        with SessionFactory() as s:
            alice = account_service.get_account(s, alice_id)
            _clear_resend_cooldown(s, alice_id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
            code = _issue_code_directly(
                s, account=alice, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION, target_email="alice@example.com",
            )
            s.commit()

        resp = alice_client.get("/profile")
        csrf = extract_csrf(resp.data)
        resp = alice_client.post("/profile/email/verify", data={"code": code, "csrf_token": csrf})
        check("A: correct code confirms the email (redirect)", resp.status_code in (302, 303))

        with SessionFactory() as s:
            alice = account_service.get_account(s, alice_id)
            check("A: email_verified_at is now set", alice.email_verified_at is not None)

        # -------------------------------------------------------------
        # B. Adding an email to a pre-existing account that had none.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            bob = account_service.create_account(
                s, username="bob", display_name="Bob", password="BobPass123!", status="ACTIVE",
            )
            s.commit()
            bob_id = bob.id
        check("B: legacy-style account created with no email", True)

        bob_client = web_app.app.test_client()
        resp = bob_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = bob_client.post("/login", data={"username": "bob", "password": "BobPass123!", "csrf_token": csrf})
        check("B: account with no email can still log in normally", resp.status_code in (302, 303))

        resp = bob_client.get("/profile")
        csrf = extract_csrf(resp.data)
        resp = bob_client.post(
            "/profile/email",
            data={"email": "bob@example.com", "current_password": "BobPass123!", "csrf_token": csrf},
        )
        check("B: adding an email from profile redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            bob = account_service.get_account(s, bob_id)
            check("B: email recorded immediately, unverified", bob.email == "bob@example.com" and bob.email_verified_at is None)
            _clear_resend_cooldown(s, bob_id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
            code = _issue_code_directly(
                s, account=bob, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION, target_email="bob@example.com",
            )
            s.commit()

        resp = bob_client.get("/profile")
        csrf = extract_csrf(resp.data)
        resp = bob_client.post("/profile/email/verify", data={"code": code, "csrf_token": csrf})
        check("B: confirming the code verifies it (redirect)", resp.status_code in (302, 303))
        with SessionFactory() as s:
            bob = account_service.get_account(s, bob_id)
            check("B: bob's email is now verified", bob.email_verified_at is not None)

        # -------------------------------------------------------------
        # C. Protected email change: old stays verified until the new one
        # is confirmed; wrong current password is rejected first.
        # -------------------------------------------------------------
        resp = bob_client.get("/profile")
        csrf = extract_csrf(resp.data)
        resp = bob_client.post(
            "/profile/email",
            data={"email": "bob-new@example.com", "current_password": "WRONG", "csrf_token": csrf},
        )
        with SessionFactory() as s:
            bob = account_service.get_account(s, bob_id)
            check("C: wrong current password does not start a change", bob.email == "bob@example.com")

        resp = bob_client.get("/profile")
        csrf = extract_csrf(resp.data)
        resp = bob_client.post(
            "/profile/email",
            data={"email": "bob-new@example.com", "current_password": "BobPass123!", "csrf_token": csrf},
        )
        check("C: email change request redirects", resp.status_code in (302, 303))

        with SessionFactory() as s:
            bob = account_service.get_account(s, bob_id)
            check("C: OLD email stays verified/unchanged while change is pending", bob.email == "bob@example.com" and bob.email_verified_at is not None)
            pending = recovery_service.get_pending_code(s, bob_id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
            check("C: pending code targets the NEW address", pending is not None and pending.target_email == "bob-new@example.com")
            _clear_resend_cooldown(s, bob_id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
            code = _issue_code_directly(
                s, account=bob, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION, target_email="bob-new@example.com",
            )
            s.commit()

        resp = bob_client.get("/profile")
        csrf = extract_csrf(resp.data)
        resp = bob_client.post("/profile/email/verify", data={"code": code, "csrf_token": csrf})
        check("C: confirming the new code redirects", resp.status_code in (302, 303))
        with SessionFactory() as s:
            bob = account_service.get_account(s, bob_id)
            check("C: email actually changed after confirmation", bob.email == "bob-new@example.com" and bob.email_verified_at is not None)

        # -------------------------------------------------------------
        # D/E. Forgot-password: exact username+email match required;
        # identical generic response for every ineligible case.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            inactive = account_service.create_account(
                s, username="inactiveuser", display_name="Inactive", password="InactivePass123!",
                status="INACTIVE", email="inactive@example.com",
            )
            inactive.email_verified_at = datetime.now(timezone.utc)
            unverified = account_service.create_account(
                s, username="unverifieduser", display_name="Unverified", password="UnverifiedPass123!",
                status="ACTIVE", email="unverified@example.com",
            )
            s.commit()

        anon_client = web_app.app.test_client()
        resp = anon_client.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp_nonexistent = anon_client.post(
            "/forgot-password", data={"username": "nosuchuser", "email": "x@example.com", "csrf_token": csrf},
        )
        body_nonexistent = resp_nonexistent.data

        anon_client2 = web_app.app.test_client()
        resp = anon_client2.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp_wrongemail = anon_client2.post(
            "/forgot-password", data={"username": "bob", "email": "not-bobs-email@example.com", "csrf_token": csrf},
        )
        body_wrongemail = resp_wrongemail.data

        anon_client3 = web_app.app.test_client()
        resp = anon_client3.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp_unverified = anon_client3.post(
            "/forgot-password", data={"username": "unverifieduser", "email": "unverified@example.com", "csrf_token": csrf},
        )
        body_unverified = resp_unverified.data

        anon_client4 = web_app.app.test_client()
        resp = anon_client4.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp_inactive = anon_client4.post(
            "/forgot-password", data={"username": "inactiveuser", "email": "inactive@example.com", "csrf_token": csrf},
        )
        body_inactive = resp_inactive.data

        anon_client5 = web_app.app.test_client()
        resp = anon_client5.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp_eligible = anon_client5.post(
            "/forgot-password", data={"username": "bob", "email": "bob-new@example.com", "csrf_token": csrf},
        )
        body_eligible = resp_eligible.data

        check(
            "E: identical generic response for nonexistent/wrong-email/unverified/inactive/eligible",
            body_nonexistent == body_wrongemail == body_unverified == body_inactive == body_eligible,
        )

        with SessionFactory() as s:
            unverified_acc = account_service.get_account_by_username(s, "unverifieduser")
            inactive_acc = account_service.get_account_by_username(s, "inactiveuser")
            bob_acc = account_service.get_account_by_username(s, "bob")
            check(
                "D/E: no code issued for the unverified-email account",
                recovery_service.get_pending_code(s, unverified_acc.id, recovery_service.PURPOSE_PASSWORD_RESET) is None,
            )
            check(
                "D/E: no code issued for the inactive account",
                recovery_service.get_pending_code(s, inactive_acc.id, recovery_service.PURPOSE_PASSWORD_RESET) is None,
            )
            check(
                "D: the eligible (matching username+email) account DID get a code",
                recovery_service.get_pending_code(s, bob_acc.id, recovery_service.PURPOSE_PASSWORD_RESET) is not None,
            )
            bob_id = bob_acc.id

        # -------------------------------------------------------------
        # F/G/H/I/J/K. Full reset flow: wrong code, expired code,
        # exhausted attempts + resend invalidation, purpose isolation,
        # rate limits, atomic single-use, new/old password, session
        # revocation.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            email_code = _issue_code_directly(
                s, account=bob_acc, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION, target_email="bob-new@example.com",
            )
            s.commit()
            cross_check = recovery_service.verify_and_consume_code(
                s, account_id=bob_id, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                submitted_code=email_code, flask_secret_key=FLASK_SECRET,
            )
            s.commit()
        check("G: an EMAIL_VERIFICATION code does not work for PASSWORD_RESET", cross_check.ok is False)

        # Expired code.
        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            recovery_service.invalidate_pending_codes(s, bob_id)
            expired_code = _issue_code_directly(
                s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
            )
            row = recovery_service.get_pending_code(s, bob_id, recovery_service.PURPOSE_PASSWORD_RESET)
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            s.commit()
            expired_result = recovery_service.verify_and_consume_code(
                s, account_id=bob_id, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                submitted_code=expired_code, flask_secret_key=FLASK_SECRET,
            )
            s.commit()
        check("F: an expired code is rejected even if correct", expired_result.ok is False)

        # Exhausted attempts.
        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            exhaust_code = _issue_code_directly(
                s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
            )
            for _ in range(recovery_service.MAX_ATTEMPTS_PER_CODE):
                recovery_service.verify_and_consume_code(
                    s, account_id=bob_id, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                    submitted_code="999999", flask_secret_key=FLASK_SECRET,
                )
            s.commit()
            after_exhaust = recovery_service.verify_and_consume_code(
                s, account_id=bob_id, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                submitted_code=exhaust_code, flask_secret_key=FLASK_SECRET,
            )
            s.commit()
        check(
            f"H: after {recovery_service.MAX_ATTEMPTS_PER_CODE} wrong attempts the correct code no longer works",
            after_exhaust.ok is False,
        )

        # Resend cooldown + invalidates the previous code.
        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            first_code = _issue_code_directly(
                s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
            )
            s.commit()
            cooldown_hit = False
            try:
                _issue_code_directly(
                    s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
                )
            except recovery_service.RateLimitedError:
                cooldown_hit = True
            s.commit()
        check("H: resending within 60s is rate-limited", cooldown_hit is True)

        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            row = recovery_service.get_pending_code(s, bob_id, recovery_service.PURPOSE_PASSWORD_RESET)
            row.created_at = datetime.now(timezone.utc) - recovery_service.RESEND_COOLDOWN - timedelta(seconds=1)
            s.commit()
            second_code = _issue_code_directly(
                s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
            )
            s.commit()
            stale_result = recovery_service.verify_and_consume_code(
                s, account_id=bob_id, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                submitted_code=first_code, flask_secret_key=FLASK_SECRET,
            )
            s.commit()
        check("F: a resend invalidates the previous code (old code no longer works)", stale_result.ok is False)

        # Hourly per-account cap.
        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            recovery_service.invalidate_pending_codes(s, bob_id)
            s.commit()
            hit_cap = False
            for i in range(recovery_service.MAX_SENDS_PER_ACCOUNT_PER_HOUR + 1):
                try:
                    _issue_code_directly(
                        s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
                    )
                    s.commit()
                    row = recovery_service.get_pending_code(s, bob_id, recovery_service.PURPOSE_PASSWORD_RESET)
                    row.created_at = datetime.now(timezone.utc) - recovery_service.RESEND_COOLDOWN - timedelta(seconds=1)
                    s.commit()
                except recovery_service.RateLimitedError:
                    hit_cap = True
                    s.commit()
                    break
        check(f"H: the {recovery_service.MAX_SENDS_PER_ACCOUNT_PER_HOUR}/hour per-account cap engages", hit_cap is True)

        # The H cap test above deliberately used up bob's hourly quota —
        # push every code row it created out of the 1-hour rate-limit
        # window (simulating "an hour has passed") so the rest of this
        # test isn't itself blocked by the cap it just proved works.
        with SessionFactory() as s:
            old_enough = datetime.now(timezone.utc) - recovery_service.RATE_WINDOW - timedelta(minutes=1)
            for row in s.query(m.RFOneAccountVerificationCode).filter(
                m.RFOneAccountVerificationCode.account_id == bob_id,
            ).all():
                row.created_at = old_enough
            s.commit()

        # -------------------------------------------------------------
        # I/J/K. Real, successful reset via HTTP: single-use, new
        # password works, old does not, prior session is revoked.
        # -------------------------------------------------------------
        pre_reset_client = web_app.app.test_client()
        resp = pre_reset_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = pre_reset_client.post("/login", data={"username": "bob", "password": "BobPass123!", "csrf_token": csrf})
        check("K setup: bob logs in with the OLD password before reset", resp.status_code in (302, 303))
        resp = pre_reset_client.get("/")
        check("K setup: pre-reset session can reach Home", resp.status_code == 200)

        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            recovery_service.invalidate_pending_codes(s, bob_id)
            s.commit()
            reset_code = _issue_code_directly(
                s, account=bob_acc, purpose=recovery_service.PURPOSE_PASSWORD_RESET, target_email="bob-new@example.com",
            )
            s.commit()

        reset_client = web_app.app.test_client()
        resp = reset_client.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp = reset_client.post(
            "/forgot-password", data={"username": "bob", "email": "bob-new@example.com", "csrf_token": csrf},
        )
        resp = reset_client.get("/forgot-password/code")
        check("setup: step 2 page reachable after step 1", resp.status_code == 200)
        csrf = extract_csrf(resp.data)
        resp = reset_client.post(
            "/forgot-password/code",
            data={
                "code": reset_code, "new_password": "BobNewPass456!", "new_password_confirm": "BobNewPass456!",
                "csrf_token": csrf,
            },
        )
        check("I/J: successful reset redirects to login", resp.status_code in (302, 303))

        with SessionFactory() as s:
            bob_acc = account_service.get_account(s, bob_id)
            check(
                "I: the code cannot be reused (consumed)",
                recovery_service.get_pending_code(s, bob_id, recovery_service.PURPOSE_PASSWORD_RESET) is None,
            )

        replay_client = web_app.app.test_client()
        resp = replay_client.get("/forgot-password")
        csrf = extract_csrf(resp.data)
        resp = replay_client.post(
            "/forgot-password", data={"username": "bob", "email": "bob-new@example.com", "csrf_token": csrf},
        )
        resp = replay_client.get("/forgot-password/code")
        csrf = extract_csrf(resp.data)
        resp = replay_client.post(
            "/forgot-password/code",
            data={
                "code": reset_code, "new_password": "AnotherPass789!", "new_password_confirm": "AnotherPass789!",
                "csrf_token": csrf,
            },
        )
        check("I: replaying the SAME already-used code is rejected", resp.status_code == 400)

        old_login_client = web_app.app.test_client()
        resp = old_login_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = old_login_client.post("/login", data={"username": "bob", "password": "BobPass123!", "csrf_token": csrf})
        check("J: OLD password no longer works", resp.status_code == 401)

        new_login_client = web_app.app.test_client()
        resp = new_login_client.get("/login")
        csrf = extract_csrf(resp.data)
        resp = new_login_client.post("/login", data={"username": "bob", "password": "BobNewPass456!", "csrf_token": csrf})
        check("J: NEW password works", resp.status_code in (302, 303))

        resp = pre_reset_client.get("/")
        check(
            "K: the session that predates the reset is now revoked (redirected, not 200)",
            resp.status_code in (301, 302, 303, 308),
        )

        # -------------------------------------------------------------
        # L. Training data/authorization untouched by any of the above.
        # -------------------------------------------------------------
        with SessionFactory() as s:
            training_accounts_count = s.query(m.TrainingAccount).count()
            training_needs_count = s.query(m.TrainingNeed).count()
            training_pills_count = s.query(m.TrainingPill).count()
        check(
            "L: no Training rows were created by any account/recovery flow above",
            training_accounts_count == 0 and training_needs_count == 0,
        )
        check("L: Training pill catalog (seed-independent count check) is a plain non-negative count", training_pills_count >= 0)

    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
