#!/usr/bin/env python
"""HTTP-level trust-boundary regression test for GLOBAL_INTEGRITY_FIX_002 /
C-1 (task §23).

Mirrors `test_batch_upload.py`'s convention exactly (throwaway SQLite
database created before `app.py` is imported, Werkzeug's Flask test client,
main()-returns-exit-code). This file does NOT test login — RF-One has no
Authentication yet and this fix does not add one (see
`rfone_data_store.acting_identity_service`'s module docstring). What it
proves, at the actual HTTP layer (not just the service layer), is the
trust-boundary claim GLOBAL_INTEGRITY_FIX_002 makes: a route never accepts
a client-submitted name/id as proof of "who is acting" for a consequential
Application-ownership action — the actor is always resolved server-side
from a signed session cookie set only by `/identity/switch` /
`/identity/register` after validating an id against a real, active
`ActingIdentity` row.
"""

from __future__ import annotations

import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_identity_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)  # let app.py's migration runner create it fresh
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

import app as selection_app  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.selection import import_pipeline  # noqa: E402
from rfone_data_store.selection.core.resume_source import LOCAL_UPLOAD  # noqa: E402
from rfone_data_store.selection.parsing.dedup import compute_content_hash  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _identity_by_name(session, display_name: str) -> "m.ActingIdentity":
    return session.scalars(
        select(m.ActingIdentity).where(m.ActingIdentity.display_name == display_name)
    ).one()


def _upload_application(session, restaurant, email: str, name: str) -> "m.Application":
    text = f"{name}\n{email}\n555-010-0000\n\nEXPERIENCE\nServer, Test Bistro\nJan 2022 - Present\nServed guests.\n"
    imported = import_pipeline.import_one_resume(
        session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}.txt",
        storage_path=None, raw_text=text, content_hash=compute_content_hash(text, email),
    )
    application = selection_app.app_svc.create_application(
        session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
    )
    session.commit()
    return application


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool) -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)

    try:
        # ---------------------------------------------------------------
        # Fixture setup: two registered Acting Identities (via the real
        # HTTP registration route, one per independent test-client "browser"),
        # one Selection Session with a confirmed Rule Set, and one Application
        # linked to it and taken in charge by Alex.
        # ---------------------------------------------------------------
        client_alex = selection_app.app.test_client()
        client_jordan = selection_app.app.test_client()

        resp = client_alex.post("/identity/register", data={"display_name": "HTTP-Test Alex"})
        check("setup: registering an Acting Identity redirects (no error)", resp.status_code in (302, 303))
        resp = client_jordan.post("/identity/register", data={"display_name": "HTTP-Test Jordan"})
        check("setup: registering a second Acting Identity redirects (no error)", resp.status_code in (302, 303))

        with selection_app.SessionFactory() as session:
            restaurant = selection_app._bootstrap_restaurant(session)
            alex = _identity_by_name(session, "HTTP-Test Alex")
            jordan = _identity_by_name(session, "HTTP-Test Jordan")
            alex_id, jordan_id = alex.id, jordan.id

            selection_session = selection_app.sess_svc.create_session(
                session, restaurant_id=restaurant.id, name="HTTP Trust Boundary Test Session", target_role="SERVER",
            )
            session.commit()
            selection_app.rs_svc.confirm_rule_set_version(session, selection_session.id, acting_identity_id=alex_id)
            session.commit()

            application = _upload_application(session, restaurant, "http.trust.boundary@example.com", "Robin HttpTest")
            selection_app.sess_svc.link_application_to_session(session, application.id, selection_session.id)
            session.commit()
            application_id = application.id

        # ---------------------------------------------------------------
        # Check 1 — "route does not trust typed actor name": Take In Charge
        # POSTs a legacy `owner_name` field forged to a third-party name;
        # the route no longer reads it at all, so the recorded owner must be
        # the server-resolved current identity (Alex), never the forged text.
        # ---------------------------------------------------------------
        resp = client_alex.post(
            f"/applications/{application_id}/take-in-charge",
            data={"owner_name": "Totally Someone Else", "next": "/"},
        )
        check("1: Take In Charge redirects (no error)", resp.status_code in (302, 303))

        with selection_app.SessionFactory() as session:
            ownership = selection_app.own_svc.get_current_owner(session, application_id)
            check(
                "1: the owner recorded is the server-resolved current identity, NOT the forged 'owner_name' field",
                ownership is not None and ownership.owner_name == "HTTP-Test Alex" and ownership.owner_name != "Totally Someone Else",
            )
            check(
                "1: server-side resolved identity is the actor recorded (acting_identity_id/assigned_by_identity_id)",
                ownership.acting_identity_id == alex_id and ownership.assigned_by_identity_id == alex_id,
            )

        # ---------------------------------------------------------------
        # Check 2 — "changing a form field cannot impersonate another
        # owner": Jordan (a peer of Alex — no configured authority) attempts
        # to reassign Alex's Application to himself, forging
        # `performed_by_identity_id` to Alex's own id in the POST body. The
        # route must ignore that field entirely and resolve the REAL actor
        # (Jordan) from his own session cookie — so the peer-authority
        # rejection must still apply and ownership must NOT change.
        # ---------------------------------------------------------------
        resp = client_jordan.post(
            f"/applications/{application_id}/reassign",
            data={
                "new_owner_identity_id": str(jordan_id),
                "performed_by_identity_id": str(alex_id),  # forged — must be ignored
                "reason": "Attempting to impersonate Alex",
                "next": "/",
            },
        )
        check("2: forged reassignment attempt redirects (no 500)", resp.status_code in (302, 303))

        with selection_app.SessionFactory() as session:
            ownership = selection_app.own_svc.get_current_owner(session, application_id)
            check(
                "2: a forged 'performed_by_identity_id' cannot impersonate another (superior/owner) identity — "
                "ownership is unchanged (still Alex)",
                ownership is not None and ownership.acting_identity_id == alex_id,
            )

        # ---------------------------------------------------------------
        # Check 3 — "target identity selection still works where required":
        # Alex (the real current owner, resolved from his own cookie) may
        # legitimately reassign to Jordan by selecting Jordan's stable id.
        # ---------------------------------------------------------------
        resp = client_alex.post(
            f"/applications/{application_id}/reassign",
            data={"new_owner_identity_id": str(jordan_id), "reason": "Legitimate handoff", "next": "/"},
        )
        check("3: a legitimate owner-performed reassignment redirects (no error)", resp.status_code in (302, 303))

        with selection_app.SessionFactory() as session:
            ownership = selection_app.own_svc.get_current_owner(session, application_id)
            check(
                "3: target identity selection (new_owner_identity_id) works — ownership now belongs to Jordan",
                ownership is not None and ownership.acting_identity_id == jordan_id and ownership.owner_name == "HTTP-Test Jordan",
            )
            check(
                "3: the performer recorded for the legitimate reassignment is Alex (server-resolved), not a form field",
                ownership.assigned_by_identity_id == alex_id,
            )

        # ---------------------------------------------------------------
        # Check 4 — a non-owner, non-superior identity (Alex, now that
        # Jordan owns it and neither has configured authority over the
        # other) has read-only access enforced by `assert_can_operate`
        # through the real HTTP route (Stage change), not just the service
        # layer directly.
        # ---------------------------------------------------------------
        with selection_app.SessionFactory() as session:
            before_stage = selection_app.app_svc.get_application(session, application_id).current_stage
        resp = client_alex.post(
            f"/applications/{application_id}/stage",
            data={"new_stage": "PHONE_INTERVIEW", "next": "/"},
        )
        check("4: a blocked Stage-change attempt still redirects (no 500)", resp.status_code in (302, 303))
        with selection_app.SessionFactory() as session:
            after_stage = selection_app.app_svc.get_application(session, application_id).current_stage
        check(
            "4: a non-owner, non-superior identity cannot change Stage via the real HTTP route (read-only enforced)",
            after_stage == before_stage,
        )

    finally:
        selection_app._engine.dispose()
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = _TEST_DB_PATH + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    if not checks_failed:
        print(f"Acting Identity HTTP trust-boundary tests (GLOBAL_INTEGRITY_FIX_002): SUCCESS ({len(checks_passed)}/{len(checks_passed)} checks passed)")
        return 0

    print(
        "Acting Identity HTTP trust-boundary tests (GLOBAL_INTEGRITY_FIX_002): FAILURE "
        f"({len(checks_passed)} passed, {len(checks_failed)} failed)"
    )
    for description in checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
