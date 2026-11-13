"""Offline HTTP and service checks on a disposable SQLite database.

Run this file directly so its isolated environment precedes shell imports.
No provider, speech service, shared DB or outgoing message is contacted.
"""
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import uuid

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(WEB.parent / "RF-One Data Store"))
TEMP = tempfile.TemporaryDirectory()
os.environ["RFONE_DATABASE_URL"] = "sqlite:///" + (Path(TEMP.name) / "interview-test.sqlite3").as_posix()
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "isolated-interview-test"

import app as web
import auth
from db import SessionFactory, _engine
from rfone_data_store import models as m
from rfone_data_store import people_registry as people
from rfone_data_store.interviews import service as svc
from rfone_data_store.interviews.models import InterviewSession
from rfone_data_store.interviews.provider import ProviderError
from sqlalchemy import inspect, select, update, func


def fake_provider(payload):
    if payload["operation"] == "question":
        return {"question": "What specific sign led you to choose that solution?"}
    index = next(i for i, msg in enumerate(payload["transcript"]) if msg["role"] == "user")
    answer = payload["transcript"][index]["text"]
    return {"summary": "An experience reported by the interviewee, pending verification.",
        "knowledge": [{"text": "A candidate method", "quote": answer, "message_index": index}],
        "open_questions": ["When would this method not apply?"]}


class InterviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m.Base.metadata.create_all(_engine)
        web.app.config.update(TESTING=True, INTERVIEW_PROVIDER=fake_provider)

    def setUp(self):
        self.db = SessionFactory()
        self.addCleanup(self.db.close)
        suffix = uuid.uuid4().hex
        self.admin = m.RFOneAccount(username="admin-" + suffix, display_name="Admin Uno",
            password_hash="unused", status="ACTIVE", is_admin=True)
        self.person = m.RFOneAccount(username="person-" + suffix, display_name="Persona Due",
            password_hash="unused", status="ACTIVE", is_admin=False)
        self.other = m.RFOneAccount(username="other-" + suffix, display_name="Altra Persona",
            password_hash="unused", status="ACTIVE", is_admin=False)
        self.admin2 = m.RFOneAccount(username="admin2-" + suffix, display_name="Altro Admin",
            password_hash="unused", status="ACTIVE", is_admin=True)
        self.db.add_all([self.admin, self.person, self.other, self.admin2]); self.db.commit()
        self.person_records = {}
        for account in [self.admin, self.person, self.other, self.admin2]:
            person = people.create_person(self.db, self.admin, account.display_name)
            people.link_source(self.db, self.admin, person.id, "account", account.id)
            self.person_records[account.id] = person
        self.person_record = self.person_records[self.person.id]
        self.db.commit()
        self.client = web.app.test_client()
        web.app.config["INTERVIEW_PROVIDER"] = fake_provider

    def tearDown(self):
        self.db.rollback(); self.db.close()

    def login(self, account):
        self.db.commit()  # Do not hold a fixture read lock during HTTP writes.
        with self.client.session_transaction() as session:
            session.clear()
            session[auth.SESSION_ACCOUNT_KEY] = account.id
            session[auth.SESSION_VERSION_KEY] = account.session_version
            session[auth.SESSION_CSRF_KEY] = "test-csrf"

    def create(self, purpose="Capire come risolvere un reclamo difficile"):
        row = svc.request_interview(self.db, self.admin, self.person.id, purpose)
        self.db.commit()
        return row

    def post(self, row, action, revision, **extra):
        self.db.commit()
        return self.client.post("/interviews/" + row.id,
            data=dict(csrf_token="test-csrf", action=action, revision=revision, **extra),
            headers={"Accept": "application/json"}, base_url="https://localhost")

    def test_admin_request_personal_home_and_complete_results(self):
        self.login(self.admin)
        response = self.client.post("/admin/interviews", data=dict(csrf_token="test-csrf",
            person_id=self.person_record.id, purpose="Conoscere la gestione dei reclami"), base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        row = self.db.scalar(select(InterviewSession).where(InterviewSession.requester_id == self.admin.id))
        result_url = response.location
        self.assertIn("Results will be available", self.client.get(result_url, base_url="https://localhost").text)
        self.login(self.person)
        home = self.client.get("/", base_url="https://localhost")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Interview requested", home.text)
        self.assertIn(row.id, home.text)
        self.assertNotIn("/admin/interviews", home.text)
        response = self.post(row, "start", 0)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("specific sign", response.json["messages"][-1]["text"])
        response = self.post(row, "answer", 1, message="Ho prima ascoltato il cliente.", channel="voice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["messages"][1]["channel"], "voice")
        # A new GET resumes without another provider call or reset.
        self.assertIn("Ho prima ascoltato", self.client.get("/interviews/" + row.id, base_url="https://localhost").text)
        response = self.post(row, "complete", 2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "COMPLETED")
        self.assertNotIn(row.id, self.client.get("/", base_url="https://localhost").text)
        self.login(self.admin)
        listing = self.client.get("/admin/interviews", base_url="https://localhost")
        self.assertIn("View results", listing.text)
        result = self.client.get(result_url, base_url="https://localhost")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Ho prima ascoltato", result.text)
        self.assertIn("do not constitute validated knowledge", result.text)
        self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_role_and_account_isolation(self):
        row = self.create()
        self.login(self.other)
        self.assertEqual(self.client.get("/admin/interviews", base_url="https://localhost").status_code, 403)
        self.assertEqual(self.client.get("/interviews/" + row.id, base_url="https://localhost").status_code, 404)
        self.assertNotIn(row.id, self.client.get("/", base_url="https://localhost").text)
        self.assertEqual(self.post(row, "start", 0).status_code, 404)
        self.login(self.admin2)
        self.assertEqual(self.client.get("/admin/interviews/" + row.id, base_url="https://localhost").status_code, 404)
        self.login(self.admin)
        self.assertEqual(self.post(row, "start", 0).status_code, 404)

    def test_csrf_and_session_revocation(self):
        row = self.create(); self.login(self.person)
        response = self.client.post("/interviews/" + row.id,
            data=dict(action="start", revision=0), base_url="https://localhost")
        self.assertEqual(response.status_code, 400)
        self.person.session_version += 1; self.db.commit()
        self.assertEqual(self.post(row, "start", 0).status_code, 302)

    def test_bad_provider_keeps_state_and_unsent_answer(self):
        row = self.create(); self.login(self.person)
        self.post(row, "start", 0)
        web.app.config["INTERVIEW_PROVIDER"] = lambda payload: {"question": ""}
        response = self.post(row, "answer", 1, message="Risposta da conservare")
        self.assertEqual(response.status_code, 503)
        self.db.refresh(row)
        self.assertEqual(row.revision, 1)
        self.assertEqual(len(json.loads(row.transcript)), 1)
        self.db.commit()
        response = self.client.post("/interviews/" + row.id, data=dict(
            csrf_token="test-csrf", action="answer", revision=1, message="Risposta da conservare"), base_url="https://localhost")
        self.assertIn("Risposta da conservare", response.text)

    def test_stale_turn_and_completed_session_are_immutable(self):
        row = self.create(); self.login(self.person)
        self.assertEqual(self.post(row, "start", 0).status_code, 200)
        self.assertEqual(self.post(row, "start", 0).status_code, 409)
        self.assertEqual(self.post(row, "answer", 1, message="Una risposta").status_code, 200)
        self.assertEqual(self.post(row, "complete", 1).status_code, 409)
        self.assertEqual(self.post(row, "complete", 2).status_code, 200)
        self.assertEqual(self.post(row, "answer", 3, message="Dopo la chiusura").status_code, 409)

    def test_competing_turn_during_provider_call_cannot_overwrite(self):
        row = self.create(); self.login(self.person)
        session_id = row.id

        def competing_provider(payload):
            with SessionFactory() as concurrent:
                concurrent.execute(update(InterviewSession).where(
                    InterviewSession.id == session_id).values(revision=1, status="IN_PROGRESS",
                    transcript=json.dumps([dict(role="assistant", text="Domanda già salvata")])) )
                concurrent.commit()
            return {"question": "Domanda concorrente da scartare"}

        web.app.config["INTERVIEW_PROVIDER"] = competing_provider
        response = self.post(row, "start", 0)
        self.assertEqual(response.status_code, 409, response.text)
        self.db.refresh(row)
        self.assertEqual("Domanda già salvata", json.loads(row.transcript)[0]["text"])
        self.assertNotIn("da scartare", row.transcript)

    def test_fabricated_evidence_prevents_completion(self):
        row = self.create(); self.login(self.person)
        self.post(row, "start", 0)
        self.post(row, "answer", 1, message="Un episodio reale")
        web.app.config["INTERVIEW_PROVIDER"] = lambda payload: dict(summary="Sintesi", knowledge=[
            dict(text="Inventato", quote="Mai detto", message_index=1)], open_questions=[])
        response = self.post(row, "complete", 2)
        self.assertEqual(response.status_code, 503)
        self.db.refresh(row)
        self.assertEqual(row.status, "IN_PROGRESS")
        self.assertIsNone(row.results)

    def test_validation_and_explicit_start(self):
        with self.assertRaises(PermissionError):
            svc.request_interview(self.db, self.person, self.other.id, "Scopo")
        with self.assertRaises(ValueError):
            svc.request_interview(self.db, self.admin, self.person.id, " ")
        self.other.status = "INACTIVE"; self.db.commit()
        with self.assertRaises(PermissionError):
            svc.request_interview(self.db, self.admin, self.other.id, "Scopo")
        row = self.create(); self.login(self.person)
        self.assertEqual(self.post(row, "answer", 0, message="Prima dell'avvio").status_code, 409)
        self.post(row, "start", 0)
        self.assertEqual(self.post(row, "complete", 1).status_code, 400)

    def employee(self, name):
        merchant = m.Merchant(name="Directory test merchant")
        self.db.add(merchant); self.db.flush()
        location = m.Location(merchant_id=merchant.id, name="Directory test location")
        self.db.add(location); self.db.flush()
        employee = m.Employee(location_id=location.id, display_name=name)
        self.db.add(employee); self.db.commit()
        return employee

    def test_one_directory_links_employee_and_external_without_new_registry(self):
        employee = self.employee(self.person_record.full_name)
        external = people.create_person(self.db, self.admin, "External specialist")
        self.db.commit()
        count = self.db.scalar(select(func.count()).select_from(m.CandidatePerson))
        self.login(self.admin)
        response = self.client.get("/people", base_url="https://localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("External specialist", response.text)
        self.assertIn("Records to connect", response.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(people.PersonEmployeeLink, employee.id), "GET must not match identical names")
        self.db.commit()
        data = dict(csrf_token="test-csrf", action="link", source="employee:" + str(employee.id), person_id=self.person_record.id)
        self.db.commit()
        response = self.client.post("/people", data=data, base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/people/" + str(self.person_record.id), response.location)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.CandidatePerson)), count)
        profile = self.client.get(response.location, base_url="https://localhost")
        self.assertIn("/employees/" + str(employee.id), profile.text)
        self.assertIn("Login settings", profile.text)
        self.assertIn("Request interview", profile.text)
        self.assertEqual(self.client.get("/employees", base_url="https://localhost").status_code, 302)
        self.assertIn("/people", self.client.get("/employees", base_url="https://localhost").location)

    def test_three_interview_pages_reference_same_person_not_account_alias(self):
        self.person.display_name = "Different login alias"; self.db.commit()
        self.login(self.admin)
        response = self.client.get("/admin/interviews?person_id=" + str(self.person_record.id), base_url="https://localhost")
        self.assertIn('name="person_id"', response.text)
        response = self.client.post("/admin/interviews", data=dict(csrf_token="test-csrf",
            person_id=self.person_record.id, purpose="A purpose about one identified person"), base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        row = self.db.scalar(select(InterviewSession).where(InterviewSession.requester_id == self.admin.id))
        self.assertEqual(row.person_id, self.person_record.id)
        self.assertEqual(row.recipient_id, self.person.id)
        self.login(self.person)
        page = self.client.get("/interviews/" + row.id, base_url="https://localhost")
        self.assertIn("Interview for " + self.person_record.full_name, page.text)
        self.post(row, "start", 0); self.post(row, "answer", 1, message="A specific experience")
        self.post(row, "complete", 2)
        self.login(self.admin)
        result = self.client.get("/admin/interviews/" + row.id, base_url="https://localhost")
        self.assertIn('/people/' + str(self.person_record.id), result.text)
        self.assertIn('id="results-conversation"', result.text)
        self.assertIn('data-open-transcript', result.text)
        person = self.client.get("/people/" + str(self.person_record.id), base_url="https://localhost")
        self.assertIn("/admin/interviews/" + row.id, person.text)
        account = self.client.get("/admin/accounts/" + str(self.person.id) + "/edit", base_url="https://localhost")
        self.assertIn('/people/' + str(self.person_record.id), account.text)

    def test_unlinked_person_needs_active_account_for_home_delivery(self):
        external = people.create_person(self.db, self.admin, "No login external person"); self.db.commit()
        self.login(self.admin)
        response = self.client.post("/admin/interviews", data=dict(csrf_token="test-csrf",
            person_id=external.id, purpose="Requested knowledge"), base_url="https://localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Link an active RF-One account", response.text)
        self.assertIsNone(self.db.scalar(select(InterviewSession).where(InterviewSession.person_id == external.id)))

    def test_person_link_conflicts_and_directory_access(self):
        self.login(self.other)
        self.assertEqual(self.client.get("/people", base_url="https://localhost").status_code, 403)
        self.assertEqual(self.client.get("/people/" + str(self.person_record.id), base_url="https://localhost").status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.post("/people", data=dict(action="create", full_name="No CSRF"), base_url="https://localhost").status_code, 400)
        with self.assertRaises(ValueError):
            people.link_source(self.db, self.admin, self.person_records[self.other.id].id, "account", self.person.id)
        self.assertEqual(self.db.get(people.PersonAccountLink, self.person.id).person_id, self.person_record.id)
        row = self.create()
        self.login(self.admin2)
        profile = self.client.get("/people/" + str(self.person_record.id), base_url="https://localhost")
        self.assertNotIn("/admin/interviews/" + row.id, profile.text)

    def test_identity_migration_preserves_legacy_interviews(self):
        from sqlalchemy import create_engine, text
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        def load(name):
            path = WEB.parents[1] / ("90 Archive/Superseded Migrations/interviews-prototype-20261101/" + name + ".py")
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            return module
        initial = load("f8d120261101_add_common_interview_sessions")
        identity = load("f9e220261101_link_people_and_interviews")
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            m.Base.metadata.create_all(connection, tables=[table for table in m.Base.metadata.tables.values()
                if table.name not in {"interview_sessions", "person_account_links", "person_employee_links"}])
            with Operations.context(MigrationContext.configure(connection)):
                initial.upgrade()
                connection.execute(text("INSERT INTO interview_sessions (id, requester_id, recipient_id, purpose, specialization, status, revision, transcript, created_at) VALUES ('legacy', 1, 2, 'Original purpose', 'KNOW_HOW', 'REQUESTED', 0, '[]', CURRENT_TIMESTAMP)"))
                identity.upgrade()
                legacy = connection.execute(text("SELECT purpose, person_id FROM interview_sessions WHERE id='legacy'")).one()
                self.assertEqual(tuple(legacy), ("Original purpose", None))
                identity.downgrade()
                self.assertEqual(connection.execute(text("SELECT purpose FROM interview_sessions WHERE id='legacy'")).scalar_one(), "Original purpose")
                self.assertFalse(inspect(connection).has_table("person_account_links"))
        engine.dispose()

    def test_missing_schema_does_not_break_existing_home(self):
        # Restore the table for subsequent tests; only this disposable DB is touched.
        InterviewSession.__table__.drop(_engine)
        try:
            self.login(self.admin)
            self.assertEqual(self.client.get("/", base_url="https://localhost").status_code, 200)
            self.assertEqual(self.client.get("/admin/interviews", base_url="https://localhost").status_code, 503)
        finally:
            InterviewSession.__table__.create(_engine)

    def test_additive_migration_on_empty_parent_and_downgrade(self):
        from sqlalchemy import create_engine
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path = WEB.parents[1] / "90 Archive/Superseded Migrations/interviews-prototype-20261101/f8d120261101_add_common_interview_sessions.py"
        spec = importlib.util.spec_from_file_location("interview_migration", path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            m.RFOneAccount.__table__.create(connection)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                self.assertTrue(inspect(connection).has_table("interview_sessions"))
                indexes = inspect(connection).get_indexes("interview_sessions")
                self.assertEqual(len(indexes), 2)
                migration.downgrade()
                self.assertFalse(inspect(connection).has_table("interview_sessions"))
                self.assertTrue(inspect(connection).has_table("rfone_accounts"))
        engine.dispose()


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False).result
    finally:
        _engine.dispose()
        TEMP.cleanup()
    sys.exit(0 if result.wasSuccessful() else 1)
