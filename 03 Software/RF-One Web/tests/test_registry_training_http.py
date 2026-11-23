#!/usr/bin/env python
"""REGISTRY_MULTISITE_001 — the Training entry into Registry over HTTP (Training app, throwaway SQLite).

  1. Training -> Invite student asks no site (the invitation belongs to the person, Product Owner 2026-11-22)
     and offers the optional role trained for from Registry's catalog; a direct invitation creates the Trainee's
     Registry card with no site, with or without a role.
  2. Confirm hire turns the same card into Employee and records who and when on the card's history; the
     owner exception without a signed course still needs a reason.
  3. Codex review: without a card Confirm hire saves nothing and shows no success; «Resolve card and site»
     gives a legacy Trainee card and site first; an uncertain card identity is asked before anything is saved.
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
        self.assertNotIn('name="site_role"', page)
        self.assertIn('name="training_role"', page)
        self.assertIn(f'value="{self.cook_id}:{self.area_id}"', page)
        # no site and no role: accepted, card without a site
        bare = self.client.post("/training/manage/enrollment", data={"csrf_token": self.csrf("/training/manage/enrollment"),
                                "mode": "direct", "email": "nosite@example.invalid", "name": "No Site"})
        self.assertEqual(bare.status_code, 200, bare.get_data(as_text=True)[:400])
        with self.factory() as db:
            invitation = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == "nosite@example.invalid"))
            self.assertEqual(directory.employee_site_ids(db, directory.card_for_person(db, invitation.person_id).id), set())
        done = self.client.post("/training/manage/enrollment", data={"csrf_token": self.csrf("/training/manage/enrollment"),
                                "mode": "direct", "email": "new.cook@example.invalid", "name": "New Cook",
                                "training_role": f"{self.cook_id}:{self.area_id}"})
        self.assertEqual(done.status_code, 200, done.get_data(as_text=True)[:400])
        with self.factory() as db:
            invitation = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == "new.cook@example.invalid"))
            card = directory.card_for_person(db, invitation.person_id)
            self.assertEqual(directory.employee_site_ids(db, card.id), set())
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

    # Codex review 3 — no card, no hire
    def _as_student(self, person_id):
        import training_hire_confirm as hire
        from sqlalchemy.orm import Session
        original_get = Session.get

        def get(session, entity, ident, *args, **kwargs):
            if entity is m.TrainingAccount and ident == 77:
                return SimpleNamespace(id=77, role="student")
            return original_get(session, entity, ident, *args, **kwargs)
        student = SimpleNamespace(id=self.trainer_id)
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(Session, "get", get))
        stack.enter_context(patch("rfone_data_store.training.workspace.linked_account", return_value=student))
        stack.enter_context(patch.object(hire, "person_for", return_value=person_id))
        stack.enter_context(patch.object(hire, "course_status", return_value={self.trainer_id: {"signed": True}}))
        return stack

    def _flashes(self):
        with self.client.session_transaction() as session:
            return list(session.pop("_flashes", []))

    def _legacy_trainee(self, phone=None):
        with self.factory() as db:
            person = people.create_identity(db, full_name="Terry Legacy", email="terry@example.invalid", phone=phone,
                                            normalized_name="terry legacy")
            db.add(registry.PersonQualification(person_id=person.id, code="STUDENT"))
            db.commit()
            return person.id

    def test_confirm_hire_without_a_card_saves_nothing_and_shows_no_success(self):
        person_id = self._legacy_trainee()
        token = self.csrf("/training/manage/enrollment")
        with self._as_student(person_id):
            response = self.client.post("/training/manage/students/77/confirm-hire", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        flashes = self._flashes()
        self.assertTrue(any(category == "error" and "no Registry card" in text for category, text in flashes), flashes)
        self.assertFalse(any("Hire confirmed" in text for _, text in flashes))
        with self.factory() as db:
            self.assertNotIn("EMPLOYEE", people.company_statuses(db, person_id))
            self.assertIsNone(db.scalar(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == "registry.hire_confirmed")))
            self.assertIsNone(db.scalar(select(m.EmployeeDirectoryEvent).where(m.EmployeeDirectoryEvent.action == "HIRE_CONFIRMED")))

    def test_legacy_trainee_gets_card_and_site_then_the_hire_is_confirmed(self):
        person_id = self._legacy_trainee()
        with self._as_student(person_id):
            page = self.client.get("/training/manage/students/77/registry-card").get_data(as_text=True)
            self.assertIn("Resolve card and site", page)
            self.assertIn("How this page works", page)
            token = CSRF_RE.search(page).group(1)
            saved = self.client.post("/training/manage/students/77/registry-card", data={
                "csrf_token": token, "site_role": f"{self.md_id}:{self.cook_id}:{self.area_id}"})
            self.assertEqual(saved.status_code, 302, saved.get_data(as_text=True)[:300])
            self._flashes()
            with self.factory() as db:
                card = directory.card_for_person(db, person_id)
                self.assertEqual(directory.employee_site_ids(db, card.id), {self.md_id})
                self.assertEqual(db.scalar(select(en.EnrollmentInvitation.id)), None)        # no invitation
                card_id = card.id
            done = self.client.post("/training/manage/students/77/confirm-hire",
                                    data={"csrf_token": self.csrf("/training/manage/enrollment")})
        self.assertEqual(done.status_code, 302)
        self.assertTrue(any("Hire confirmed" in text for _, text in self._flashes()))
        with self.factory() as db:
            self.assertIn("EMPLOYEE", people.company_statuses(db, person_id))
            self.assertIsNotNone(db.scalar(select(m.EmployeeDirectoryEvent).where(
                m.EmployeeDirectoryEvent.employee_id == card_id, m.EmployeeDirectoryEvent.action == "HIRE_CONFIRMED")))

    def test_uncertain_card_identity_is_asked_on_the_pages_before_anything_is_saved(self):
        with self.factory() as db:
            wp_card = directory.create_person(db, display_name="Luca Bianchi", phone="407-555-0101",
                                              restaurant_id=self.wp_id, role_id=self.cook_id, area_id=self.area_id)
            db.commit(); wp_card_id = wp_card.id
        data = {"mode": "direct", "email": "luca@example.invalid", "name": "Luca Bianchi", "phone": "(407) 555 0101",
                "training_role": f"{self.cook_id}:{self.area_id}"}
        asked = self.client.post("/training/manage/enrollment",
                                 data={**data, "csrf_token": self.csrf("/training/manage/enrollment")})
        self.assertEqual(asked.status_code, 400)
        self.assertIn("Is this the same person as an existing Registry card?", asked.get_data(as_text=True))
        with self.factory() as db:
            self.assertEqual((db.scalar(select(en.EnrollmentInvitation.id)), db.scalar(select(m.CandidatePerson.id))),
                             (None, None))
        import re
        options = lambda page: re.findall(r'name="card_confirmation" value="([^"]+)"', page.get_data(as_text=True))
        seen = options(asked)
        self.assertEqual([v.split("@")[0] for v in seen], [f"card:{wp_card_id}", "card:new"])
        # Codex review 3: meanwhile another card with the same US number (+1) is entered; the stale choice is
        # not accepted, the page shows the updated options and nothing is saved.
        with self.factory() as db:
            other = directory.create_person(db, display_name="Luca B.", phone="+1 407 555 0101",
                                            restaurant_id=self.wp_id, role_id=self.cook_id, area_id=self.area_id)
            db.commit(); other_id = other.id
        stale = self.client.post("/training/manage/enrollment", data={**data, "card_confirmation": seen[0],
                                 "csrf_token": self.csrf("/training/manage/enrollment")})
        self.assertEqual(stale.status_code, 400)
        self.assertIn("The Registry match changed", stale.get_data(as_text=True))
        updated = options(stale)
        self.assertEqual(sorted(v.split("@")[0] for v in updated),
                         sorted([f"card:{wp_card_id}", f"card:{other_id}", "card:new"]))
        with self.factory() as db:
            self.assertEqual((db.scalar(select(en.EnrollmentInvitation.id)), db.scalar(select(m.CandidatePerson.id))),
                             (None, None))
        choice = next(v for v in updated if v.startswith(f"card:{wp_card_id}@"))
        done = self.client.post("/training/manage/enrollment", data={**data, "card_confirmation": choice,
                                "csrf_token": self.csrf("/training/manage/enrollment")})
        self.assertEqual(done.status_code, 200, done.get_data(as_text=True)[:400])
        with self.factory() as db:
            invitation = db.scalar(select(en.EnrollmentInvitation))
            self.assertEqual(directory.card_for_person(db, invitation.person_id).id, wp_card_id)
            self.assertEqual(directory.employee_site_ids(db, wp_card_id), {self.wp_id})   # no site added


if __name__ == "__main__":
    unittest.main()
