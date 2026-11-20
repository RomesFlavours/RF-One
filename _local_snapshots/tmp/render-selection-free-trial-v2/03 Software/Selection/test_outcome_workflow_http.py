#!/usr/bin/env python
"""HTTP-level regression test for GLOBAL_INTEGRITY_FIX_003 / C-2 (task §21).

Mirrors `test_acting_identity_http.py`'s convention exactly (throwaway
SQLite database created before `app.py` is imported, Werkzeug's Flask test
client, main()-returns-exit-code). What it proves, at the actual HTTP
layer, is C-2's trust/governance-parity claim for the legacy
`/applications/<id>/workflow-status` control (`workflow_projection_
service.apply_legacy_workflow_action`):

- the legacy form cannot bypass the authoritative Outcome Engine (it always
  creates a real `SelectionOutcomeDecision`, never a direct scalar write,
  for a restaurant with a configured Outcome);
- the actor cannot be spoofed — a non-owner, non-superior identity is
  blocked by the SAME ownership/authority guard the modern routes use;
- the mandatory-reason-on-change rule applies identically through this
  route;
- the SAME Candidate Communication consequence fires as the modern route;
- the retired `/applications/<id>/outcome` route (the OTHER split-brain
  path — a direct, ungoverned `Application.outcome` overwrite) no longer
  exists at all.
"""

from __future__ import annotations

import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_outcome_workflow_http_test_")
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
    text = f"{name}\n{email}\n555-020-0000\n\nEXPERIENCE\nServer, Test Bistro\nJan 2022 - Present\nServed guests.\n"
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
        # Fixture setup: two registered Acting Identities, a Selection
        # Session with a confirmed Rule Set, an Application linked to it
        # and taken in charge by Alex, a restaurant-configured "Stop"/
        # "Hold" Outcome, and one Communication Template per Outcome so
        # the "same communication consequence" claim is actually exercised.
        # ---------------------------------------------------------------
        client_alex = selection_app.app.test_client()
        client_jordan = selection_app.app.test_client()

        resp = client_alex.post("/identity/register", data={"display_name": "HTTP-Test Fix003 Alex"})
        check("setup: registering Alex redirects (no error)", resp.status_code in (302, 303))
        resp = client_jordan.post("/identity/register", data={"display_name": "HTTP-Test Fix003 Jordan"})
        check("setup: registering Jordan redirects (no error)", resp.status_code in (302, 303))

        with selection_app.SessionFactory() as session:
            restaurant = selection_app._bootstrap_restaurant(session)
            alex = _identity_by_name(session, "HTTP-Test Fix003 Alex")
            jordan = _identity_by_name(session, "HTTP-Test Fix003 Jordan")
            alex_id, jordan_id = alex.id, jordan.id

            selection_session = selection_app.sess_svc.create_session(
                session, restaurant_id=restaurant.id, name="HTTP Fix003 Outcome/Workflow Test Session",
                target_role="SERVER",
            )
            session.commit()
            selection_app.rs_svc.confirm_rule_set_version(session, selection_session.id, acting_identity_id=alex_id)
            session.commit()

            stop_def = selection_app.outcome_svc.create_outcome_definition(
                session, restaurant_id=restaurant.id, name="HTTP Fix003 Stop", lifecycle_effect=selection_app.om.CLOSED,
                requires_reason=False,
            )
            hold_def = selection_app.outcome_svc.create_outcome_definition(
                session, restaurant_id=restaurant.id, name="HTTP Fix003 Hold", lifecycle_effect=selection_app.om.SUSPENDED,
                requires_reason=False,
            )
            selection_app.tmpl_svc.create_template(
                session, restaurant_id=restaurant.id, trigger_event=selection_app.cm.TRIGGER_PRIMARY_SCREENING_STOP,
                outcome_definition_id=stop_def.id, sms_text="Thanks for your interest.",
            )
            session.commit()

            application = _upload_application(session, restaurant, "http.fix003.outcome@example.com", "Robin HttpFix003")
            selection_app.sess_svc.link_application_to_session(session, application.id, selection_session.id)
            session.commit()
            selection_app.own_svc.take_in_charge(session, application.id, acting_identity_id=alex_id)
            session.commit()
            application_id = application.id

        # ---------------------------------------------------------------
        # Check 1 — "actor cannot be spoofed": Jordan (a peer of Alex, the
        # real owner — no configured authority) attempts to change the
        # legacy Workflow Status control to STOP. The route resolves
        # Jordan's REAL identity server-side (never a form field); since
        # Jordan is neither the owner nor a configured superior, the SAME
        # `assert_can_operate` guard the modern routes use must block this,
        # exactly as it would on the modern Outcome route.
        # ---------------------------------------------------------------
        resp = client_jordan.post(
            f"/applications/{application_id}/workflow-status", data={"new_status": "STOP", "reason": ""},
        )
        check("1: blocked workflow-status attempt still redirects (no 500)", resp.status_code in (302, 303))
        with selection_app.SessionFactory() as session:
            decision = selection_app.outcome_svc.get_current_outcome_decision(session, application_id)
            check(
                "1: a non-owner, non-superior identity cannot change the legacy Workflow Status control — "
                "no Outcome decision was created",
                decision is None,
            )

        # ---------------------------------------------------------------
        # Check 2 — "legacy form cannot bypass the authoritative Outcome
        # Engine" / "governed Decision row is created": Alex (the real
        # owner) submits the SAME legacy control; it must create a real,
        # governed SelectionOutcomeDecision (never a direct scalar write),
        # carry Alex's stable ActingIdentity, and fire the SAME Candidate
        # Communication the modern Outcome route would fire.
        # ---------------------------------------------------------------
        resp = client_alex.post(
            f"/applications/{application_id}/workflow-status", data={"new_status": "STOP", "reason": ""},
        )
        check("2: the owner's workflow-status change redirects (no error)", resp.status_code in (302, 303))
        with selection_app.SessionFactory() as session:
            decision = selection_app.outcome_svc.get_current_outcome_decision(session, application_id)
            check(
                "2: the legacy Workflow Status control created a real, governed SelectionOutcomeDecision "
                "(the authoritative Outcome Engine), naming the restaurant's own 'Stop' Outcome Definition",
                decision is not None and decision.outcome_definition_snapshot.definition_id == stop_def.id,
            )
            check(
                "2: the governed decision carries the server-resolved ActingIdentity (Alex), never a typed name",
                decision.performed_by_identity_id == alex_id,
            )
            comms = selection_app.comm_svc.list_communications_for_application(session, application_id)
            check(
                "2: the legacy control fired the SAME Candidate Communication consequence a modern Outcome "
                "route would fire for this Outcome",
                len(comms) == 1 and comms[0].trigger_event == selection_app.cm.TRIGGER_PRIMARY_SCREENING_STOP,
            )

        # ---------------------------------------------------------------
        # Check 3 — "the reason requirement works": changing the NOW-
        # EXISTING governed decision (Stop -> Hold) via the SAME legacy
        # control without a reason must be rejected, exactly like the
        # modern Outcome route would reject it — the rule lives once, in
        # `outcome_service.apply_outcome`, reached by both routes.
        # ---------------------------------------------------------------
        resp = client_alex.post(
            f"/applications/{application_id}/workflow-status", data={"new_status": "HOLD", "reason": ""},
        )
        check("3: a rejected change-without-reason attempt still redirects (no 500)", resp.status_code in (302, 303))
        with selection_app.SessionFactory() as session:
            decision = selection_app.outcome_svc.get_current_outcome_decision(session, application_id)
            check(
                "3: changing an existing governed decision via the legacy control without a reason is "
                "rejected — the Outcome remains 'Stop'",
                decision is not None and decision.outcome_definition_snapshot.definition_id == stop_def.id,
            )

        resp = client_alex.post(
            f"/applications/{application_id}/workflow-status",
            data={"new_status": "HOLD", "reason": "Reconsidering after new information."},
        )
        check("3b: the same change succeeds once a reason is supplied", resp.status_code in (302, 303))
        with selection_app.SessionFactory() as session:
            decision = selection_app.outcome_svc.get_current_outcome_decision(session, application_id)
            check(
                "3b: with a reason supplied, the legacy control's change is applied through the authoritative "
                "Outcome Engine — the Outcome is now 'Hold'",
                decision is not None and decision.outcome_definition_snapshot.definition_id == hold_def.id,
            )

        # ---------------------------------------------------------------
        # Check 4 — the OTHER split-brain path named by task §4 (the
        # direct, ungoverned `Application.outcome` scalar mutation route)
        # has been retired entirely; it must no longer be a routable URL.
        # ---------------------------------------------------------------
        resp = client_alex.post(f"/applications/{application_id}/outcome", data={"outcome": "HIRED"})
        check(
            "4: the retired /applications/<id>/outcome mutation route no longer exists (404) — the ungoverned "
            "legacy Application.outcome write path is gone",
            resp.status_code == 404,
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
        print(f"Outcome/Workflow unification HTTP tests (GLOBAL_INTEGRITY_FIX_003): SUCCESS ({len(checks_passed)}/{len(checks_passed)} checks passed)")
        return 0

    print(
        "Outcome/Workflow unification HTTP tests (GLOBAL_INTEGRITY_FIX_003): FAILURE "
        f"({len(checks_passed)} passed, {len(checks_failed)} failed)"
    )
    for description in checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
