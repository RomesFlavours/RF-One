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
from rfone_data_store.interviews import directory_bridge as people
from rfone_data_store import employee_directory as directory
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
            person = directory.create_person(self.db, display_name=account.display_name, account_id=self.admin.id)
            directory.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=account.id, account_id=self.admin.id)
            self.person_records[account.id] = people.get_person(self.db, person.id)
        self.person_record = self.person_records[self.person.id]
        self.db.add(m.RFOneAccountDomainAccess(account_id=self.admin.id, domain_code="EMPLOYEES", enabled=True, role_code="admin"))
        self.db.add(m.RFOneAccountDomainAccess(account_id=self.admin2.id, domain_code="EMPLOYEES", enabled=True, role_code="admin"))
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







    def test_missing_schema_does_not_break_existing_home(self):
        # Restore the table for subsequent tests; only this disposable DB is touched.
        InterviewSession.__table__.drop(_engine)
        try:
            self.login(self.admin)
            self.assertEqual(self.client.get("/", base_url="https://localhost").status_code, 200)
            self.assertEqual(self.client.get("/admin/interviews", base_url="https://localhost").status_code, 503)
        finally:
            InterviewSession.__table__.create(_engine)



    def test_canonical_directory_and_test_label(self):
        self.login(self.admin)
        page=self.client.get('/admin/interviews?person_id='+str(self.person_record.id),base_url='https://localhost')
        self.assertEqual(page.status_code,200)
        self.assertIn('TEST',page.text)
        self.assertEqual(page.headers['X-Robots-Tag'],'noindex, nofollow')
        self.assertIn(self.person_record.full_name,page.text)
        row=self.create()
        self.assertEqual(row.person_id,self.person_record.id)
        self.assertIsNotNone(self.db.get(m.Employee,row.person_id))
        self.assertFalse(inspect(_engine).has_table('person_account_links'))
        self.assertFalse(inspect(_engine).has_table('person_employee_links'))

    def test_removed_context_link_revokes_interview_access(self):
        row=self.create()
        self.login(self.person)
        self.assertEqual(self.client.get('/interviews/'+row.id,base_url='https://localhost').status_code,200)
        link=self.db.scalar(select(m.EmployeeContextLink).where(m.EmployeeContextLink.rfone_account_id==self.person.id))
        self.db.delete(link);self.db.commit()
        self.assertEqual(self.client.get('/interviews/'+row.id,base_url='https://localhost').status_code,404)
        self.assertNotIn(row.id,self.client.get('/',base_url='https://localhost').text)
        self.assertEqual(self.post(row,'start',0).status_code,404)

    def test_new_migration_is_additive_and_reversible(self):
        from sqlalchemy import create_engine
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path=WEB.parent/'RF-One Data Store/migrations/versions/e0a120261101_add_interviews_test.py'
        spec=importlib.util.spec_from_file_location('test_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as c:
            m.Base.metadata.create_all(c,tables=[t for t in m.Base.metadata.tables.values() if t.name!='interview_sessions'])
            with Operations.context(MigrationContext.configure(c)):
                migration.upgrade()
                self.assertTrue(inspect(c).has_table('interview_sessions'))
                self.assertEqual(len(inspect(c).get_indexes('interview_sessions')),3)
                foreign_keys=inspect(c).get_foreign_keys('interview_sessions')
                self.assertTrue(any(f['referred_table']=='employees' for f in foreign_keys))
                migration.downgrade()
                self.assertFalse(inspect(c).has_table('interview_sessions'))
                self.assertTrue(inspect(c).has_table('employees'))
        engine.dispose()


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False).result
    finally:
        _engine.dispose()
        TEMP.cleanup()
    sys.exit(0 if result.wasSuccessful() else 1)
