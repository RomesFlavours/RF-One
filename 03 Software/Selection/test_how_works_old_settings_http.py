#!/usr/bin/env python
"""Contextual help ("How this page works" modal) on the Selection Old
configuration and interview pages (part B).

Mirrors `test_outcome_workflow_http.py`'s convention: a throwaway SQLite
database created before `app.py` is imported, Werkzeug's Flask test client,
main() returning the exit code. All data is synthetic. The AI client is
isolated (`isolated_ai_client`): no real provider can be reached, and the
test asserts that none was attempted. No SMS/e-mail provider is configured
(the Selection communication providers are in-process mocks).

For every page of the area it GETs the page and asserts: HTTP 200, the
modal link for the page's own help section, the section itself, the label
"How this page works", and exactly one help dialog.
"""

from __future__ import annotations

import os
import sys
import tempfile

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_how_works_old_settings_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)  # let app.py's migration runner create it fresh
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
for _name in ("RFONE_SELECTION_REQUIRE_RFONE_LOGIN", "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD"):
    os.environ.pop(_name, None)

import app as selection_app  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.selection import import_pipeline  # noqa: E402
from rfone_data_store.selection.core import compliance_model as cpm  # noqa: E402
from rfone_data_store.selection.core.resume_source import LOCAL_UPLOAD  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from rfone_data_store.selection.parsing.dedup import compute_content_hash  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _upload_application(session, restaurant, email: str, name: str) -> "m.Application":
    text = f"{name}\n{email}\n555-030-0000\n\nEXPERIENCE\nServer, Test Bistro\nJan 2022 - Present\nServed guests.\n"
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
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool) -> None:
        (passed if condition else failed).append(description)

    with isolated_ai_client() as guard:
        try:
            client = selection_app.app.test_client()
            resp = client.post("/identity/register", data={"display_name": "HowWorks Old Tester"})
            check("setup: registering an acting identity redirects", resp.status_code in (302, 303))

            # Pages that seed their own starter configuration on first open.
            for path in ("/requirements", "/signals", "/priority-policies", "/phone-interview-questions",
                         "/in-person-interview-sections", "/primary-screening-criteria", "/selection-outcomes"):
                check(f"setup: {path} opens", client.get(path).status_code == 200)

            with selection_app.SessionFactory() as session:
                restaurant = selection_app._bootstrap_restaurant(session)
                identity = session.scalars(
                    select(m.ActingIdentity).where(m.ActingIdentity.display_name == "HowWorks Old Tester")
                ).one()

                requirement_set = selection_app.req_svc.create_requirement_set(
                    session, restaurant_id=restaurant.id, name="HowWorks Server Set", target_role="SERVER",
                )
                selection_app.req_svc.add_requirement(
                    session, requirement_set.id, name="Serving experience", criticality=selection_app.rm.MUST_HAVE,
                    trainability=selection_app.rm.PARTIALLY_TRAINABLE,
                    assessment_stages=[selection_app.rm.RESUME, selection_app.rm.PHONE_INTERVIEW],
                )
                snapshot = selection_app.req_svc.create_requirement_set_snapshot(session, requirement_set.id)
                session.commit()

                application = _upload_application(session, restaurant, "howworks.old@example.test", "Robin HowWorks")
                selection_app.fa_svc.create_fit_assessment(
                    session, candidate_id=application.candidate_id, requirement_set_id=requirement_set.id,
                )
                session.commit()
                phone_plan = selection_app.pi_svc.create_plan(session, application.id)
                session.commit()
                in_person_plan = selection_app.ip_svc.create_plan(session, application.id)
                session.commit()
                run = selection_app.ps_svc.create_screening_run(session, application.id)
                session.commit()

                draft_session = selection_app.sess_svc.create_session(
                    session, restaurant_id=restaurant.id, name="HowWorks Draft Session", target_role="SERVER",
                )
                active_session = selection_app.sess_svc.create_session(
                    session, restaurant_id=restaurant.id, name="HowWorks Active Session", target_role="BARTENDER",
                )
                session.commit()
                selection_app.rs_svc.confirm_rule_set_version(session, active_session.id, acting_identity_id=identity.id)
                session.commit()

                policy = selection_app.sig_svc.list_policies(session, restaurant_id=restaurant.id)[0]
                criterion = selection_app.ps_svc.list_criteria(session, restaurant_id=restaurant.id, active_only=False)[0]
                ids = {
                    "requirement_set": requirement_set.id, "snapshot": snapshot.id, "phone_plan": phone_plan.id,
                    "in_person_plan": in_person_plan.id, "run": run.id, "draft_session": draft_session.id,
                    "active_session": active_session.id, "policy": policy.id, "criterion": criterion.id,
                }

            resp = client.post("/compliance/review", data={
                "object_type": cpm.PRIMARY_SCREENING_CRITERION, "object_id": ids["criterion"],
                "next": "/compliance-reviews",
            })
            check("setup: running a Compliance Review redirects", resp.status_code in (302, 303))

            pages = [
                ("/acquisition-sources", "selection-old-acquisition-sources"),
                ("/alerts", "selection-old-alerts"),
                ("/application-questions", "selection-old-application-questions"),
                ("/channel-analytics", "selection-old-channel-analytics"),
                ("/channels", "selection-old-channels"),
                ("/communication-templates", "selection-old-communication-templates"),
                ("/compliance-reviews", "selection-old-compliance-reviews"),
                (f"/in-person-interviews/{ids['in_person_plan']}", "selection-old-in-person-interview"),
                ("/in-person-interview-sections", "selection-old-in-person-sections"),
                (f"/phone-interviews/{ids['phone_plan']}", "selection-old-phone-interview"),
                ("/phone-interview-questions", "selection-old-phone-questions"),
                ("/primary-screening-criteria", "selection-old-screening-criteria"),
                (f"/primary-screening/{ids['run']}", "selection-old-screening-detail"),
                ("/primary-screening-queue", "selection-old-screening-queue"),
                ("/priority-policies", "selection-old-priority-policies"),
                (f"/priority-policies/{ids['policy']}", "selection-old-priority-policy"),
                ("/reminder-policies", "selection-old-reminder-policies"),
                (f"/requirements/{ids['requirement_set']}", "selection-old-requirement-set"),
                (f"/requirements/{ids['requirement_set']}/snapshots/{ids['snapshot']}",
                 "selection-old-requirement-snapshot"),
                ("/requirements", "selection-old-requirements"),
                ("/selection-outcomes", "selection-old-outcomes"),
                ("/selection-queues", "selection-old-queues"),
                (f"/sessions/{ids['draft_session']}", "selection-old-session"),
                (f"/sessions/{ids['active_session']}", "selection-old-session"),
                ("/sessions", "selection-old-sessions"),
                ("/signals", "selection-old-signals"),
            ]
            bodies: dict[str, str] = {}
            for path, section in pages:
                resp = client.get(path)
                body = resp.get_data(as_text=True)
                bodies[path] = body
                check(f"{path}: HTTP 200", resp.status_code == 200)
                check(f"{path}: link opens help section {section}", f'data-how-works="{section}"' in body)
                check(f"{path}: help section {section} rendered", f'id="help-{section}"' in body)
                check(f"{path}: label 'How this page works'", "How this page works" in body)
                check(f"{path}: exactly one help dialog", body.count('id="rf-help-dialog"') == 1)

            # The Rule Change paragraph follows the page's own ACTIVE-only condition.
            check("session help: Rule Change explained on an ACTIVE Session",
                  "Propose a Rule Change</h3>" in bodies[f"/sessions/{ids['active_session']}"])
            check("session help: Rule Change not explained on a DRAFT Session",
                  "Propose a Rule Change</h3>" not in bodies[f"/sessions/{ids['draft_session']}"])
        except Exception as exc:  # noqa: BLE001 — report, never hide
            import traceback
            traceback.print_exc()
            failed.append(f"unexpected exception: {exc!r}")

        check("no real AI provider call was attempted", not guard.attempts)

    for line in passed:
        print(f"PASS  {line}")
    for line in failed:
        print(f"FAIL  {line}")
    print(f"\n{len(passed)} passed, {len(failed)} failed")
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
    if failed:
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
