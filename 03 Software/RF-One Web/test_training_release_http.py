"""Selection -> Training release endpoint (Product Owner 2026-11-21, OQ-7 completion). Disposable SQLite.

The signed server-to-server call Selection makes after a Hired decision now only releases the candidate
to a Training operator: no Student, no invitation e-mail, no Clover record."""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "RF-One Data Store"))
os.environ.setdefault("RFONE_WEB_TEST_SECRET_KEY", "test-only-secret")

from flask import Flask  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from rfone_data_store import models as m, people_registry as people, student_registry as registry  # noqa: E402
from rfone_data_store import access_profiles as profiles  # noqa: E402
from rfone_data_store import rfone_account_service as accounts  # noqa: E402
from rfone_data_store.database import create_configured_engine, create_session_factory  # noqa: E402
from rfone_data_store.selection import workspace_models as ps  # noqa: E402
from rfone_data_store.training import enrollment as en  # noqa: E402
import training_auto_invite as auto  # noqa: E402

SECRET = "test-only-secret"


class ReleaseEndpoint(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with self.factory() as db:
            hirer = accounts.create_account(db, username="hirer", display_name="Hirer", password="Hirer-Pass-9",
                                            email="hirer@example.invalid")
            trainer = accounts.create_account(db, username="trainer", display_name="Trainer T.",
                                              password="Trainer-Pass-9", email="trainer@example.invalid")
            db.flush()
            accounts.set_domain_access(db, account_id=hirer.id, domain_code="SELECTION", enabled=True, role_code="OWNER")
            requirements = m.RequirementSet(name="Server")
            db.add(requirements); db.flush()
            position = ps.WorkspacePosition(title="Server", role_code="SERVER", location_label="Winter Park",
                timezone="America/New_York", manager_account_id=hirer.id, created_by_account_id=hirer.id,
                requirement_set_id=requirements.id)
            db.add(position); db.flush()
            person = people.create_identity(db, full_name="Maria Rossi", email="maria@example.invalid",
                                            normalized_name="maria rossi")
            candidate = m.Candidate(full_name="Maria Rossi", email="maria@example.invalid", parsing_mode="DEMO")
            db.add(candidate); db.flush()
            application = m.Application(person_id=person.id, candidate_id=candidate.id)
            db.add(application); db.flush()
            pc = ps.WorkspacePositionCandidate(position_id=position.id, application_id=application.id,
                                               candidate_id=candidate.id, channel="MANUAL_UPLOAD")
            db.add(pc); db.flush()
            db.add(ps.WorkspaceDecision(position_candidate_id=pc.id, decision=ps.D_HIRED,
                                        actor_account_id=hirer.id, actor_name="Hirer"))
            db.commit()
            self.hirer_id, self.trainer_id, self.pc_id, self.person_id = hirer.id, trainer.id, pc.id, person.id
        app = Flask(__name__)
        app.config.update(TESTING=True)
        auto.install(app, SessionFactory=self.factory, secret=SECRET)
        self.client = app.test_client()

    def tearDown(self):
        self.engine.dispose()

    def call(self):
        body = json.dumps({"selection_id": self.pc_id, "actor_id": self.hirer_id, "ts": int(time.time())}).encode()
        return self.client.post("/training/manage/enrollment/auto", data=body,
                                headers={"X-RFOne-Signature": auto.sign(SECRET, body)})

    def test_release_only_hands_the_candidate_to_the_training_operator(self):
        sent = []
        with patch.object(auto, "_issuer", side_effect=lambda db, hirer, sid: db.get(m.RFOneAccount, self.trainer_id)), \
                patch("rfone_data_store.technical.account_email.send_email", side_effect=lambda **kw: sent.append(kw)):
            first = self.call()
            second = self.call()
        self.assertEqual((first.status_code, first.get_json()["status"]), (200, "released"))
        self.assertEqual(second.get_json()["status"], "already")
        self.assertEqual(sent, [])                                    # no invitation e-mail
        with self.factory() as db:
            self.assertIsNone(db.get(registry.PersonQualification, (self.person_id, "STUDENT")))
            self.assertEqual(db.scalar(select(func.count()).select_from(en.EnrollmentInvitation)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(m.EmployeeCloverLink)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(m.Employee)), 0)
            [event] = [e for e in db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == en.RELEASED))]
            self.assertEqual((event.details["selection_id"], event.details["operator_account_id"]),
                             (self.pc_id, self.trainer_id))

    def test_without_a_training_operator_nothing_is_released(self):
        with patch.object(auto, "_is_trainer", return_value=False):
            response = self.call()
        self.assertEqual((response.status_code, response.get_json()["status"]), (422, "skipped"))
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(profiles.ProfileEvent)), 0)

    def test_activation_of_a_link_without_arrival_confirmation_is_refused(self):
        # A pending link from the former automatic path, issued at release time without an arrival.
        import training_enrollment_routes as routes
        from datetime import timedelta
        from types import SimpleNamespace
        with self.factory() as db:
            hirer, trainer = db.get(m.RFOneAccount, self.hirer_id), db.get(m.RFOneAccount, self.trainer_id)
            en.release(db, selection_id=self.pc_id, released_by=hirer, operator=trainer)
            stamp = en.now()
            invitation = en.EnrollmentInvitation(token_digest="y" * 64, email="maria@example.invalid",
                name="Maria Rossi", phone="", person_id=self.person_id, selection_id=self.pc_id,
                created_by_id=self.trainer_id, created_at=stamp, expires_at=stamp + timedelta(hours=48), failed_attempts=0)
            db.add(invitation); db.flush()
            as_trainer = SimpleNamespace(training_account=SimpleNamespace(role="trainer"))
            form = {"first_name": "Maria", "last_name": "Rossi", "password": "Maria-Pass-99", "password_confirm": "Maria-Pass-99"}
            with patch.object(routes.integration, "check_training_authorization", return_value=as_trainer):
                with self.assertRaisesRegex(ValueError, "arrival has not been confirmed"):
                    routes.complete(db, invitation, form)
            self.assertIsNone(db.get(registry.PersonQualification, (self.person_id, "STUDENT")))
            db.rollback()

    def test_unsigned_call_is_refused(self):
        body = json.dumps({"selection_id": self.pc_id, "actor_id": self.hirer_id, "ts": int(time.time())}).encode()
        response = self.client.post("/training/manage/enrollment/auto", data=body, headers={"X-RFOne-Signature": "x"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
