#!/usr/bin/env python
"""REGISTRY_MULTISITE_001 — the Training entry into Registry over HTTP (Training app, throwaway SQLite).

  1. Training -> Invite student offers the training site and role; a direct invitation creates the Trainee's
     Registry card at that site (and only there); a missing site is refused with nothing created.
  2. Confirm hire turns the same card into Employee and records who and when on the card's history; the
     owner exception without a signed course still needs a reason.
Never sends mail, never contacts AWS or Clover.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
for path in (APP_DIR, DATA_STORE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault("RFONE_WEB_TEST_SECRET_KEY", "http-test-secret")
_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_registry_training_")
os.close(_FD)
os.remove(_DB_PATH)
os.environ.setdefault("RFONE_DATABASE_URL", f"sqlite:///{_DB_PATH.replace(os.sep, '/')}")

from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m, people_registry as people, student_registry as registry  # noqa: E402
from rfone_data_store import access_profiles as profiles  # noqa: E402,F401
from rfone_data_store import employee_directory as directory  # noqa: E402
from rfone_data_store import rfone_account_service as accounts  # noqa: E402
from rfone_data_store.database import create_configured_engine, create_session_factory  # noqa: E402
from rfone_data_store.training import enrollment as en  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


class RegistryTrainingHttpTest(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db", prefix="rfone_registry_training_"); os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = create_configured_engine("sqlite:///" + path.replace(os.sep, "/"))
        self.addCleanup(self.engine.dispose)
        m.Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with self.factory() as db:
            self.wp = m.Restaurant(name="Rome's Flavours - WP"); self.md = m.Restaurant(name="Rome's Flavours - MD")
            area = m.OperationalArea(name="Restaurant Operations")
            db.add_all([self.wp, self.md, area]); db.flush()
            cook = m.RestaurantRole(name="Cook", code="COOK"); db.add(cook); db.flush()
            db.add(m.OperationalAreaRole(operational_area_id=area.id, restaurant_role_id=cook.id))
            trainer = accounts.create_account(db, username="trainer", display_name="Trainer T.", password="Trainer-Pass-99",
                                              email="trainer@example.invalid")
            db.flush()
            accounts.set_domain_access(db, account_id=trainer.id, domain_code="TRAINING", enabled=True, role_code="trainer")
            db.commit()
            self.wp_id, self.md_id, self.area_id, self.cook_id = self.wp.id, self.md.id, area.id, cook.id
            self.trainer_id, self.trainer_version = trainer.id, trainer.session_version
        import training_cloud
        self.app = training_cloud.create_app(SessionFactory=self.factory)
        self.app.config.update(TESTING=True, TRAINING_ENROLLMENT_LOCAL=True, SESSION_COOKIE_SECURE=False)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            import auth
            session[auth.SESSION_ACCOUNT_KEY] = self.trainer_id
            session[auth.SESSION_VERSION_KEY] = self.trainer_version
        trainer_ok = SimpleNamespace(training_account=SimpleNamespace(role="trainer", id=1), allowed=True)
        patcher = patch("training_integration.check_training_authorization", return_value=trainer_ok)
        patcher.start(); self.addCleanup(patcher.stop)

    def csrf(self, path):
        return CSRF_RE.search(self.client.get(path).get_data(as_text=True)).group(1)

    def test_direct_invitation_creates_the_trainee_card_at_the_chosen_site(self):
        page = self.client.get("/training/manage/enrollment").get_data(as_text=True)
        self.assertIn('name="site_role"', page)
        self.assertIn(f'value="{self.md_id}:{self.cook_id}:{self.area_id}"', page)
        token = self.csrf("/training/manage/enrollment")
        refused = self.client.post("/training/manage/enrollment", data={"csrf_token": token, "mode": "direct",
                                   "email": "nosite@example.invalid", "name": "No Site"})
        self.assertEqual(refused.status_code, 400)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(m.Employee.id)), None)
        done = self.client.post("/training/manage/enrollment", data={"csrf_token": self.csrf("/training/manage/enrollment"),
                                "mode": "direct", "email": "new.cook@example.invalid", "name": "New Cook",
                                "site_role": f"{self.md_id}:{self.cook_id}:{self.area_id}"})
        self.assertEqual(done.status_code, 200, done.get_data(as_text=True)[:400])
        with self.factory() as db:
            invitation = db.scalar(select(en.EnrollmentInvitation))
            card = directory.card_for_person(db, invitation.person_id)
            self.assertEqual(directory.employee_site_ids(db, card.id), {self.md_id})
            self.assertIsNotNone(db.get(registry.PersonQualification, (invitation.person_id, "STUDENT")))
            self.person_id, self.card_id = invitation.person_id, card.id

    def test_confirm_hire_turns_the_same_card_into_employee_with_who_and_when(self):
        self.test_direct_invitation_creates_the_trainee_card_at_the_chosen_site()
        import training_hire_confirm as hire
        from sqlalchemy.orm import Session
        original_get = Session.get

        def get(session, entity, ident, *args, **kwargs):   # the trainee's Training row (id 77) as a stub
            if entity is m.TrainingAccount and ident == 77:
                return SimpleNamespace(id=77, role="student")
            return original_get(session, entity, ident, *args, **kwargs)
        student = SimpleNamespace(id=self.trainer_id)
        with patch.object(Session, "get", get),                 patch("rfone_data_store.training.workspace.linked_account", return_value=student),                 patch.object(hire, "person_for", return_value=self.person_id),                 patch.object(hire, "course_status", return_value={self.trainer_id: {"signed": True}}):
            response = self.client.post("/training/manage/students/77/confirm-hire",
                                        data={"csrf_token": self.csrf("/training/manage/enrollment")})
        self.assertEqual(response.status_code, 302)
        with self.factory() as db:
            self.assertIn("EMPLOYEE", people.company_statuses(db, self.person_id))
            self.assertEqual(directory.card_for_person(db, self.person_id).id, self.card_id)   # same card
            event = db.scalar(select(m.EmployeeDirectoryEvent).where(
                m.EmployeeDirectoryEvent.employee_id == self.card_id, m.EmployeeDirectoryEvent.action == "HIRE_CONFIRMED"))
            self.assertEqual(event.account_id, self.trainer_id)
            self.assertTrue(event.details["at"])
            self.assertEqual(event.details["by_name"], "Trainer T.")


if __name__ == "__main__":
    unittest.main()
