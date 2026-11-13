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
from unittest import mock
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
from rfone_data_store import employee_applicability as applicability
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
        self.db.add(m.RFOneAccountDomainAccess(account_id=self.admin.id, domain_code="ORGANIZATION", enabled=True, role_code="admin"))
        self.db.add(m.RFOneAccountDomainAccess(account_id=self.admin2.id, domain_code="ORGANIZATION", enabled=True, role_code="admin"))
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

    def make_restaurants(self, *names):
        restaurants = [m.Restaurant(name=name + "-" + uuid.uuid4().hex[:6]) for name in names]
        self.db.add_all(restaurants); self.db.flush()
        return restaurants

    def scope(self, account_or_person_id, kind, *restaurants):
        """Set applicability the only way RF-One allows: the Employee Directory service."""
        person_id = (self.person_records[account_or_person_id.id].id
                     if isinstance(account_or_person_id, m.RFOneAccount) else account_or_person_id)
        applicability.set_applicability(self.db, person_id, kind=kind, restaurant_ids=[r.id for r in restaurants])
        self.db.commit()

    def create(self, purpose="Capire come risolvere un reclamo difficile"):
        row = svc.request_interview(self.db, self.admin, self.person.id, purpose)
        self.db.commit()
        return row

    def post(self, row, action, revision, **extra):
        if action == "start":
            extra.setdefault("consent", "yes")
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
        self.assertEqual(self.client.get("/admin/interviews/" + row.id, base_url="https://localhost").status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.post(row, "start", 0).status_code, 404)
        self.login(self.admin2)
        self.assertEqual(self.post(row, "start", 0).status_code, 404)

    def test_organization_interviews_checkbox_without_global_admin(self):
        from rfone_data_store import rfone_account_service as accounts
        accounts.set_domain_access(self.db, account_id=self.other.id,
            domain_code="ORGANIZATION", enabled=True, role_code=None,
            scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, item_codes=["interviews"])
        self.db.commit()
        self.login(self.other)
        self.assertEqual(self.client.get('/admin/interviews').status_code, 200)
        self.assertEqual(self.client.get('/administration/employees').status_code, 403)
        self.assertEqual(self.client.get('/admin/accounts').status_code, 403)
        response = self.client.post('/admin/interviews', data=dict(csrf_token='test-csrf',
            person_id=self.person_record.id, purpose='Learn from a service experience'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(response.location).status_code, 200)
        self.assertIn(b'/admin/interviews', self.client.get('/').data)
        accounts.set_domain_access(self.db, account_id=self.other.id,
            domain_code="ORGANIZATION", enabled=True, role_code=None,
            scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, item_codes=["positions"])
        self.db.commit()
        self.assertEqual(self.client.get('/admin/interviews').status_code, 403)
        self.assertEqual(self.client.get(response.location).status_code, 403)
        self.assertNotIn(b'/admin/interviews', self.client.get('/').data)

    def test_any_interviews_admin_sees_results(self):
        row = self.create(); self.login(self.person)
        self.post(row, "start", 0)
        self.post(row, "answer", 1, message="Ho chiamato il fornitore.")
        self.assertEqual(self.post(row, "complete", 2).status_code, 200)
        self.login(self.admin2)
        result = self.client.get("/admin/interviews/" + row.id, base_url="https://localhost")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Ho chiamato il fornitore", result.text)
        self.assertIn("Admin Uno", result.text)
        listing = self.client.get("/admin/interviews", base_url="https://localhost")
        self.assertIn(row.id, listing.text)
        self.assertIn("Admin Uno", listing.text)
        self.assertIn(row, svc.managed(self.db, self.admin2))
        with self.assertRaises(PermissionError):
            svc.managed(self.db, self.other)

    def test_admin_delete_is_permissioned_csrf_checked_and_audited(self):
        row = self.create(); self.login(self.person)
        self.post(row, "start", 0)
        self.post(row, "answer", 1, message="Risposta da eliminare")
        session_id, url = row.id, "/admin/interviews/" + row.id + "/delete"
        def delete(**data):
            self.db.commit()
            return self.client.post(url, data=data, base_url="https://localhost")
        def exists():
            self.db.commit()
            return self.db.scalar(select(func.count()).select_from(InterviewSession).where(InterviewSession.id == session_id)) == 1
        self.assertEqual(delete(csrf_token="test-csrf", confirm="yes").status_code, 403)  # participant
        self.login(self.other)
        self.assertEqual(delete(csrf_token="test-csrf", confirm="yes").status_code, 403)
        self.login(self.admin2)
        page = self.client.get("/admin/interviews/" + session_id, base_url="https://localhost")
        self.assertIn('action="/admin/interviews/' + session_id + '/delete"', page.text)
        self.assertIn('name="confirm" value="yes" required', page.text)
        self.assertEqual(delete(confirm="yes").status_code, 400)
        self.assertEqual(self.client.get(url, base_url="https://localhost").status_code, 405)
        response = delete(csrf_token="test-csrf")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/admin/interviews/" + session_id))
        self.assertTrue(exists())
        response = delete(csrf_token="test-csrf", confirm="yes")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(exists())
        event = self.db.scalar(select(m.EmployeeDirectoryEvent).where(m.EmployeeDirectoryEvent.action == "INTERVIEW_DELETE")
            .order_by(m.EmployeeDirectoryEvent.id.desc()))
        self.assertEqual((event.employee_id, event.account_id, event.details["interview_id"]),
            (self.person_record.id, self.admin2.id, session_id))
        self.assertNotIn("Risposta", json.dumps(event.details))
        self.assertEqual(delete(csrf_token="test-csrf", confirm="yes").status_code, 404)
        self.assertNotIn(session_id, self.client.get("/admin/interviews", base_url="https://localhost").text)
        self.login(self.person)
        self.assertEqual(self.client.get("/interviews/" + session_id, base_url="https://localhost").status_code, 404)

    def test_delete_during_ai_turn_is_not_a_server_error(self):
        row = self.create(); self.login(self.person)
        session_id = row.id
        def deleting_provider(payload):
            with SessionFactory() as concurrent:
                svc.delete_interview(concurrent, concurrent.get(m.RFOneAccount, self.admin.id), session_id)
                concurrent.commit()
            return {"question": "Domanda per un'intervista eliminata"}
        web.app.config["INTERVIEW_PROVIDER"] = deleting_provider
        response = self.post(row, "start", 0)
        self.assertEqual(response.status_code, 404)
        self.assertIn("no longer available", response.json["error"])

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

    def test_start_requires_consent_on_the_server(self):
        row = self.create(); self.login(self.person)
        page = self.client.get("/interviews/" + row.id, base_url="https://localhost")
        self.assertIn('name="consent" value="yes" required', page.text)
        self.assertIn("Administrators can delete them", page.text)
        calls = []
        web.app.config["INTERVIEW_PROVIDER"] = lambda payload: calls.append(payload) or {"question": "Domanda"}
        for refused in ("", "no"):
            response = self.post(row, "start", 0, consent=refused)
            self.assertEqual(response.status_code, 400)
            self.assertIn("I agree", response.json["error"])
        self.db.commit()
        response = self.client.post("/interviews/" + row.id, data=dict(csrf_token="test-csrf",
            action="start", revision=0), base_url="https://localhost")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(calls, [])
        self.db.refresh(row)
        self.assertEqual((row.status, row.consent_given, row.consent_at), ("REQUESTED", False, None))
        self.assertEqual(self.post(row, "start", 0).status_code, 200)
        self.db.refresh(row)
        self.assertTrue(row.consent_given)
        self.assertIsNotNone(row.consent_at)
        with self.assertRaises(ValueError):
            svc.advance(self.db, self.person, self.create(), 0, "start", "", fake_provider)

    def test_ai_timeout_is_a_clean_try_again(self):
        row = self.create(); self.login(self.person)
        self.post(row, "start", 0)
        def timed_out(payload):
            raise ProviderError("The AI took too long to answer. Please try again; the saved conversation has not changed.")
        web.app.config["INTERVIEW_PROVIDER"] = timed_out
        response = self.post(row, "answer", 1, message="Risposta lenta")
        self.assertEqual(response.status_code, 503)
        self.assertIn("try again", response.json["error"])
        self.db.refresh(row)
        self.assertEqual((row.revision, len(json.loads(row.transcript))), (1, 1))

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

    def test_fabricated_evidence_is_dropped_not_kept(self):
        row = self.create(); self.login(self.person)
        self.post(row, "start", 0)
        self.post(row, "answer", 1, message="Un episodio reale accaduto ieri")
        web.app.config["INTERVIEW_PROVIDER"] = lambda payload: dict(summary="Sintesi", knowledge=[
            dict(text="Inventato", quote="Mai detto", message_index=1),
            dict(text="Supportato", quote="episodio reale accaduto", message_index=1)], open_questions=[])
        response = self.post(row, "complete", 2)
        self.assertEqual(response.status_code, 200)
        self.db.refresh(row)
        self.assertEqual(row.status, "COMPLETED")
        results = json.loads(row.results)
        self.assertEqual([item["text"] for item in results["knowledge"]], ["Supportato"])
        self.assertEqual(results["dropped_unsupported"], 1)
        self.login(self.admin)
        page = self.client.get("/admin/interviews/" + row.id, base_url="https://localhost").text
        self.assertIn("1 AI proposal was left out", page)
        self.assertNotIn("Inventato", page)

    def test_quotation_matches_despite_typography(self):
        # Curly apostrophe/quotes, an em dash, a one-character ellipsis, double
        # spaces and a line break in the answer; plain ASCII in the quotations.
        answer = "L\u2019ho detto al cliente: \u201cnon \u00e8 colpa sua\u201d \u2014 poi  ho aspettato\u2026\nE ha funzionato."
        messages = [dict(role="assistant", text="Domanda"), dict(role="user", text=answer)]
        raw = dict(summary="Sintesi", open_questions=[], knowledge=[
            dict(text="Apostrophe and case", quote="l'HO DETTO al cliente", message_index=1),
            dict(text="Quotes and dash", quote='"Non \u00e8 colpa sua" - poi ho aspettato...', message_index=1),
            dict(text="Line break and end mark", quote="\u201cho aspettato... e ha funzionato.\u201d", message_index=1),
            dict(text="Wrong index, right answer", quote="non \u00e8 colpa sua", message_index=0),
            dict(text="Not said", quote="ho chiamato il direttore", message_index=1),
            dict(text="Only punctuation", quote="\u2026", message_index=1)])
        result = svc._complete_output(raw, messages)
        self.assertEqual([item["text"] for item in result["knowledge"]],
            ["Apostrophe and case", "Quotes and dash", "Line break and end mark", "Wrong index, right answer"])
        self.assertEqual({item["message_index"] for item in result["knowledge"]}, {1})
        # Stored as the participant wrote it, not as the AI copied it.
        self.assertEqual([item["quote"] for item in result["knowledge"]], [
            "L\u2019ho detto al cliente",
            "non \u00e8 colpa sua\u201d \u2014 poi  ho aspettato",
            "ho aspettato\u2026\nE ha funzionato",
            "non \u00e8 colpa sua"])
        self.assertEqual(result["dropped_unsupported"], 2)

    def test_short_quotations_are_dropped(self):
        answer = "S\u00ec, il fornitore. Poi ho chiamato il direttore per la riorganizzazione della sala."
        messages = [dict(role="assistant", text="Domanda"), dict(role="user", text=answer)]
        quotes = {"two short words": "il fornitore", "one word": "S\u00ec",
            "three words": "ho chiamato il", "fifteen characters": "riorganizzazione",
            "decomposed accent": "Si\u0300, il fornitore"}
        raw = dict(summary="Sintesi", open_questions=[], knowledge=[
            dict(text=name, quote=quote, message_index=1) for name, quote in quotes.items()])
        result = svc._complete_output(raw, messages)
        self.assertEqual({item["text"]: item["quote"] for item in result["knowledge"]}, {
            "three words": "ho chiamato il", "fifteen characters": "riorganizzazione",
            "decomposed accent": "S\u00ec, il fornitore"})
        self.assertEqual(result["dropped_unsupported"], 2)

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







    def legacy_in_progress(self, requester=None):
        """An interview started before consent was asked (pre-migration row)."""
        row = svc.request_interview(self.db, requester or self.admin, self.person.id, "Interview from before consent")
        self.db.commit()
        self.login(self.person)
        self.assertEqual(self.post(row, "start", 0).status_code, 200)
        self.assertEqual(self.post(row, "answer", 1, message="Risposta data prima del consenso").status_code, 200)
        self.db.execute(update(InterviewSession).where(InterviewSession.id == row.id).values(
            consent_given=False, consent_at=None))
        self.db.commit()
        return row

    def test_legacy_interview_needs_consent_before_any_ai_call(self):
        row = self.legacy_in_progress()
        page = self.client.get("/interviews/" + row.id, base_url="https://localhost")
        self.assertIn('id="interview-consent-answer" type="checkbox" name="consent" value="yes" required', page.text)
        self.assertIn('id="interview-consent-complete"', page.text)
        calls = []
        web.app.config["INTERVIEW_PROVIDER"] = lambda payload: calls.append(payload) or fake_provider(payload)
        for action in ("answer", "complete"):
            response = self.post(row, action, 2, message="Seconda risposta")
            self.assertEqual(response.status_code, 400)
            self.assertIn("I agree", response.json["error"])
        self.assertEqual(calls, [])
        self.db.refresh(row)
        self.assertEqual((row.revision, row.consent_given), (2, False))
        response = self.post(row, "answer", 2, message="Seconda risposta", consent="yes")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json["consent_given"])
        self.db.refresh(row)
        self.assertTrue(row.consent_given)
        self.assertIsNotNone(row.consent_at)
        self.assertNotIn('interview-consent-answer', self.client.get("/interviews/" + row.id, base_url="https://localhost").text)
        # Once recorded, later turns do not ask again.
        self.assertEqual(self.post(row, "complete", 3).status_code, 200)

    def test_legacy_completion_records_consent(self):
        row = self.legacy_in_progress()
        self.assertEqual(self.post(row, "complete", 2).status_code, 400)
        self.assertEqual(self.post(row, "complete", 2, consent="yes").status_code, 200)
        self.db.refresh(row)
        self.assertEqual((row.status, row.consent_given), ("COMPLETED", True))

    def test_results_without_consent_are_for_the_requester_only(self):
        row = self.legacy_in_progress()
        self.db.execute(update(InterviewSession).where(InterviewSession.id == row.id).values(
            status="COMPLETED", results=json.dumps(dict(summary="Sintesi riservata", knowledge=[],
                dropped_unsupported=0, open_questions=[], validation="CANDIDATE"))))
        self.db.commit()
        url = "/admin/interviews/" + row.id
        self.login(self.admin)
        page = self.client.get(url, base_url="https://localhost").text
        self.assertIn("Consent not recorded", page)
        self.assertIn("Sintesi riservata", page)
        self.assertIn("Risposta data prima del consenso", page)
        self.login(self.admin2)
        page = self.client.get(url, base_url="https://localhost")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Consent not recorded", page.text)
        self.assertNotIn("Sintesi riservata", page.text)
        self.assertNotIn("Risposta data prima del consenso", page.text)
        self.assertIn("Consent not recorded", self.client.get("/admin/interviews", base_url="https://localhost").text)

    def test_interviews_item_without_domain_admin_sees_only_own_requests(self):
        from rfone_data_store import rfone_account_service as accounts
        accounts.set_domain_access(self.db, account_id=self.other.id,
            domain_code="ORGANIZATION", enabled=True, role_code=None,
            scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, item_codes=["interviews"])
        self.db.commit()
        theirs = self.create("Interview requested by an Organization administrator")
        mine = svc.request_interview(self.db, self.other, self.person.id, "Interview requested by a manager")
        self.db.commit()
        mine_id, theirs_id = mine.id, theirs.id
        self.assertFalse(svc.is_domain_admin(self.db, self.other))
        self.assertEqual([row.id for row in svc.managed(self.db, self.other)], [mine_id])
        self.assertLessEqual({mine_id, theirs_id}, {row.id for row in svc.managed(self.db, self.admin2)})
        self.login(self.other)
        listing = self.client.get("/admin/interviews", base_url="https://localhost").text
        self.assertIn(mine_id, listing)
        self.assertNotIn(theirs_id, listing)
        self.assertEqual(self.client.get("/admin/interviews/" + theirs_id, base_url="https://localhost").status_code, 404)
        own = self.client.get("/admin/interviews/" + mine_id, base_url="https://localhost")
        self.assertEqual(own.status_code, 200)
        self.assertNotIn("/delete", own.text)
        for session_id in (mine_id, theirs_id):
            self.db.commit()
            response = self.client.post("/admin/interviews/" + session_id + "/delete",
                data=dict(csrf_token="test-csrf", confirm="yes"), base_url="https://localhost")
            self.assertEqual(response.status_code, 403)
        with self.assertRaises(PermissionError):
            svc.delete_interview(self.db, self.other, mine_id)
        self.db.rollback()
        self.assertIsNotNone(self.db.get(InterviewSession, mine_id))
        # The Domain administrator role on ORGANIZATION, without global admin, sees and deletes all.
        accounts.set_domain_access(self.db, account_id=self.other.id,
            domain_code="ORGANIZATION", enabled=True, role_code="admin",
            scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, item_codes=["interviews"])
        self.db.commit()
        self.assertTrue(svc.is_domain_admin(self.db, self.other))
        self.assertIn(theirs_id, self.client.get("/admin/interviews", base_url="https://localhost").text)
        page = self.client.get("/admin/interviews/" + theirs_id, base_url="https://localhost")
        self.assertIn("/admin/interviews/" + theirs_id + "/delete", page.text)
        self.db.commit()
        response = self.client.post("/admin/interviews/" + theirs_id + "/delete",
            data=dict(csrf_token="test-csrf", confirm="yes"), base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        self.db.commit()
        self.assertIsNone(self.db.get(InterviewSession, theirs_id))

    def test_html_error_after_deletion_is_not_found(self):
        row = self.create(); self.login(self.person)
        session_id = row.id
        def deleting_then_failing(payload):
            with SessionFactory() as concurrent:
                svc.delete_interview(concurrent, concurrent.get(m.RFOneAccount, self.admin.id), session_id)
                concurrent.commit()
            raise ProviderError("The AI is unavailable. Please try again; the saved conversation has not changed.")
        web.app.config["INTERVIEW_PROVIDER"] = deleting_then_failing
        self.db.commit()
        response = self.client.post("/interviews/" + session_id, data=dict(csrf_token="test-csrf",
            action="start", revision=0, consent="yes"), base_url="https://localhost")
        self.assertEqual(response.status_code, 404)
        row = self.create(); self.login(self.person)
        web.app.config["INTERVIEW_PROVIDER"] = lambda payload: (_ for _ in ()).throw(ProviderError("The AI is unavailable."))
        self.db.commit()
        response = self.client.post("/interviews/" + row.id, data=dict(csrf_token="test-csrf",
            action="start", revision=0, consent="yes"), base_url="https://localhost")
        self.assertEqual(response.status_code, 503)
        self.assertIn("The AI is unavailable.", response.text)

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

    def test_consent_migration_extends_the_single_chain(self):
        import ast
        from sqlalchemy import create_engine
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        versions = WEB.parent/'RF-One Data Store/migrations/versions'
        parents = {}
        for path in versions.glob('*.py'):
            # Same reading as check_migration_chain.py: plain and annotated assignments.
            declared = {t.id: ast.literal_eval(n.value) for n in ast.parse(path.read_text(encoding='utf-8')).body
                if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                if isinstance(t, ast.Name) and t.id in ('revision', 'down_revision')}
            if 'revision' in declared:
                down = declared.get('down_revision')
                parents[declared['revision']] = tuple(down) if isinstance(down, (list, tuple)) else ((down,) if down else ())
        children = {p for ups in parents.values() for p in ups}
        heads = sorted(r for r in parents if r not in children)
        self.assertEqual(len(heads), 1)
        # Later revisions (the Employee Directory lifecycle) build on the consent revision.
        ancestry, todo = set(), list(heads)
        while todo:
            current = todo.pop()
            ancestry.add(current); todo.extend(parents.get(current, ()))
        self.assertIn('e1b220261102', ancestry)
        self.assertEqual(parents['e1b220261102'], ('e0a120261101',))
        loaded = []
        for name in ('e0a120261101_add_interviews_test.py', 'e1b220261102_add_interview_consent.py'):
            spec = importlib.util.spec_from_file_location('migration_' + name[:12], versions/name)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); loaded.append(module)
        engine = create_engine('sqlite://')
        with engine.begin() as c:
            m.Base.metadata.create_all(c, tables=[t for t in m.Base.metadata.tables.values() if t.name != 'interview_sessions'])
            with Operations.context(MigrationContext.configure(c)):
                loaded[0].upgrade()
                c.exec_driver_sql("INSERT INTO interview_sessions (id, requester_id, recipient_id, person_id, purpose, "
                    "specialization, status, revision, transcript, created_at) VALUES ('old', 1, 1, 1, 'p', 'KNOW_HOW', "
                    "'REQUESTED', 0, '[]', '2026-11-01')")
                loaded[1].upgrade()
                columns = {col['name'] for col in inspect(c).get_columns('interview_sessions')}
                self.assertLessEqual({'consent_given', 'consent_at'}, columns)
                self.assertEqual(tuple(c.exec_driver_sql("SELECT consent_given, consent_at FROM interview_sessions").one()), (0, None))
                loaded[1].downgrade()
                self.assertNotIn('consent_given', {col['name'] for col in inspect(c).get_columns('interview_sessions')})
                self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM interview_sessions").scalar(), 1)
        engine.dispose()

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


class ActiveRecipientTests(unittest.TestCase):
    """New recipients come from the shared Employee Directory; never a live database."""

    setUpClass = classmethod(InterviewTests.setUpClass.__func__)
    setUp = InterviewTests.setUp
    tearDown = InterviewTests.tearDown
    login = InterviewTests.login
    create = InterviewTests.create
    make_restaurants = InterviewTests.make_restaurants
    scope = InterviewTests.scope

    def dropdown(self, person_id=None, account=None):
        self.login(account or self.admin)
        url = "/admin/interviews" + ("?person_id=" + str(person_id) if person_id else "")
        response = self.client.get(url, base_url="https://localhost")
        self.assertEqual(response.status_code, 200)
        return response.text.split('<select id="person_id"', 1)[1].split('</select>', 1)[0]

    def count(self):
        return self.db.scalar(select(func.count()).select_from(InterviewSession))

    def manager(self):
        from rfone_data_store import rfone_account_service as accounts
        accounts.set_domain_access(self.db, account_id=self.other.id,
            domain_code="ORGANIZATION", enabled=True, role_code=None,
            scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, item_codes=["interviews"])
        self.db.commit()
        return self.other

    def test_active_only_and_no_retained_dismissed_selection(self):
        person = self.db.get(m.Employee, self.person_record.id)
        self.assertIn('value="' + str(person.id) + '"', self.dropdown())
        person.active = False
        self.db.commit()
        # Keep the login active: an active account is not employment evidence.
        self.assertEqual(self.person.status, "ACTIVE")
        self.assertNotIn('value="' + str(person.id) + '"', self.dropdown(person.id))
        page = self.client.get("/admin/interviews?person_id=" + str(person.id), base_url="https://localhost")
        self.assertIn("is not a current employee", page.text)

    def test_ineligible_technical_person_is_not_a_recipient(self):
        person = self.db.get(m.Employee, self.person_record.id)
        person.directory_eligible = False
        self.db.commit()
        self.assertNotIn('value="' + str(person.id) + '"', self.dropdown())
        with self.assertRaises(ValueError):
            svc.request_for_person(self.db, self.admin, person.id, "Purpose")

    def test_stale_form_and_direct_account_creation_rejected_after_dismissal(self):
        self.dropdown()  # The page is rendered while the person is still employed.
        person = self.db.get(m.Employee, self.person_record.id)
        person.dismissed_at = func.now(); person.active = False
        self.db.commit()
        before = self.count()
        response = self.client.post("/admin/interviews", data={
            "csrf_token": "test-csrf", "person_id": person.id, "purpose": "Purpose"},
            base_url="https://localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("dismissed or outside", response.text)
        with self.assertRaises(ValueError):
            svc.request_interview(self.db, self.admin, self.person.id, "Purpose")
        self.db.rollback()
        self.assertEqual(self.count(), before)

    def test_external_account_is_not_a_recipient(self):
        external = m.RFOneAccount(username="external-" + uuid.uuid4().hex,
            display_name="External reviewer", password_hash="unused", status="ACTIVE")
        self.db.add(external)
        self.db.commit()
        with self.assertRaises(ValueError):
            svc.request_interview(self.db, self.admin, external.id, "Purpose")
        self.assertNotIn("External reviewer", self.dropdown())

    def test_retired_ids_resolve_without_bypassing_active_check(self):
        alias = m.Employee(display_name="Retired identity")
        self.db.add(alias); self.db.flush()
        self.db.add(m.EmployeeIdentityAlias(employee_id=alias.id,
            canonical_employee_id=self.person_record.id))
        self.db.flush()
        row = svc.request_for_person(self.db, self.admin, alias.id, "Purpose")
        self.assertEqual(row.person_id, self.person_record.id)
        self.db.get(m.Employee, self.person_record.id).active = False
        self.db.flush()
        with self.assertRaises(ValueError):
            svc.request_for_person(self.db, self.admin, alias.id, "Purpose")
        # A manipulated form carrying the retired ID is refused the same way.
        self.db.commit()
        before = self.count()
        self.login(self.admin)
        response = self.client.post("/admin/interviews", data={
            "csrf_token": "test-csrf", "person_id": alias.id, "purpose": "Purpose"},
            base_url="https://localhost")
        self.assertIn("dismissed or outside", response.text)
        self.assertEqual(self.count(), before)

    def test_dismissal_preserves_existing_interview_and_manager_history(self):
        row = self.create()
        row.status = "COMPLETED"
        row.transcript = json.dumps([{"role": "user", "text": "Original testimony"}])
        row.results = json.dumps({"summary": "Saved summary", "knowledge": [], "open_questions": []})
        row.consent_given = True
        self.db.get(m.Employee, self.person_record.id).active = False
        self.db.commit()
        self.login(self.admin)
        response = self.client.get("/admin/interviews/" + row.id, base_url="https://localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Original testimony", response.text)
        self.assertIn("Saved summary", response.text)
        self.assertEqual(svc.interview_person(self.db, row).id, self.person_record.id)
        self.assertIn(row.id, self.client.get("/admin/interviews", base_url="https://localhost").text)
        self.assertIn(row.id, self.client.get("/admin/interviews?person_id=" + str(self.person_record.id),
                                              base_url="https://localhost").text)
        self.assertIsNotNone(self.db.get(InterviewSession, row.id).results)

    def people_with_scopes(self):
        """A server on one restaurant, one on two, one elsewhere, a group director, one not configured."""
        wp, md, dt = self.make_restaurants("WP", "MD", "DT")
        made = {}
        for label, kind, places in (("wp", "RESTAURANT", (wp,)), ("wpmd", "RESTAURANTS", (wp, md)),
                                    ("dt", "RESTAURANT", (dt,)), ("group", "GROUP", ()), ("unset", None, ())):
            person = directory.create_person(self.db, display_name="Person " + label, account_id=self.admin.id)
            if kind:
                self.scope(person.id, kind, *places)
            made[label] = person.id
        self.db.commit()
        return (wp, md, dt), made

    def test_requester_applicability_does_not_limit_recipients(self):
        (wp, md, dt), people_ids = self.people_with_scopes()
        manager = self.manager()
        for requester_scope in ((None,), ("RESTAURANT", wp), ("RESTAURANTS", md, dt), ("GROUP",)):
            if requester_scope[0]:
                self.scope(manager, *requester_scope)
            options = self.dropdown(account=manager)
            for label in people_ids:  # every current employee, whatever either applicability
                self.assertIn('value="' + str(people_ids[label]) + '"', options, (requester_scope[0], label))
            self.assertNotIn("pplicability", options)
        page = self.client.get("/admin/interviews", base_url="https://localhost").text
        self.assertNotIn("organizational applicability", page)

    def test_both_creation_paths_ignore_applicability_and_recheck_active(self):
        wp, md = self.make_restaurants("WP", "MD")
        manager = self.manager()
        self.scope(manager, "RESTAURANT", wp)
        self.scope(self.person, "RESTAURANT", md)  # a different restaurant: still selectable
        self.assertEqual(svc.request_for_person(self.db, manager, self.person_record.id, "Purpose").person_id,
                         self.person_record.id)
        self.assertEqual(svc.request_interview(self.db, manager, self.person.id, "Purpose").person_id,
                         self.person_record.id)
        self.db.commit()
        # Scope fields smuggled into the request change nothing.
        self.login(manager)
        response = self.client.post("/admin/interviews?scope_kind=RESTAURANT", data={
            "csrf_token": "test-csrf", "person_id": self.person_record.id, "purpose": "Purpose",
            "scope_kind": "RESTAURANT", "restaurant_id": str(wp.id), "location_ids": "1"}, base_url="https://localhost")
        self.assertEqual(response.status_code, 302)
        # The active-state recheck still applies to both paths.
        self.db.get(m.Employee, self.person_record.id).active = False
        self.db.commit()
        before = self.count()
        with self.assertRaises(ValueError):
            svc.request_for_person(self.db, manager, self.person_record.id, "Purpose")
        with self.assertRaises(ValueError):
            svc.request_interview(self.db, manager, self.person.id, "Purpose")
        self.db.rollback()
        self.assertEqual(self.count(), before)

    def test_requester_not_configured_is_neither_a_block_nor_the_whole_group(self):
        manager = self.manager()
        manager_person = self.person_records[manager.id].id
        self.assertEqual(applicability.get_applicability(self.db, manager_person), applicability.UNCONFIGURED)
        self.assertIn('value="' + str(self.person_record.id) + '"', self.dropdown(account=manager))
        row = svc.request_for_person(self.db, manager, self.person_record.id, "Purpose")
        self.db.commit()
        self.assertEqual(row.person_id, self.person_record.id)
        # Nothing is assigned automatically to either person.
        for person_id in (manager_person, self.person_record.id):
            self.assertEqual(applicability.get_applicability(self.db, person_id), applicability.UNCONFIGURED)
            self.assertNotEqual(applicability.get_applicability(self.db, person_id).kind, applicability.GROUP)
        # A dismissed manager loses Interviews access altogether (unchanged lifecycle rule).
        self.db.get(m.Employee, manager_person).active = False
        self.db.commit()
        self.assertIn(self.client.get("/admin/interviews", base_url="https://localhost").status_code, (302, 403))

    def test_applicability_never_grants_interviews_access(self):
        self.scope(self.other, "GROUP")  # whole group, but no Interviews item
        self.login(self.other)
        self.assertEqual(self.client.get("/admin/interviews", base_url="https://localhost").status_code, 403)
        with self.assertRaises(PermissionError):
            svc.request_for_person(self.db, self.other, self.person_record.id, "Purpose")

    def test_dismissed_owner_keeps_access_but_is_never_a_recipient(self):
        owner = self.admin2
        self.assertIsNone(self.db.scalar(select(m.RFOneAccount.id).where(m.RFOneAccount.is_owner.is_(True))))
        owner.is_owner = True
        record = self.db.get(m.Employee, self.person_records[owner.id].id)
        record.dismissed_at = func.now(); record.active = False
        self.db.commit()

        owner_id = owner.id

        def restore():  # runs after tearDown closed the fixture session
            with SessionFactory() as db:
                db.get(m.RFOneAccount, owner_id).is_owner = False
                db.commit()
        self.addCleanup(restore)
        self.assertEqual(owner.status, "ACTIVE")
        self.assertTrue(directory.account_employee_allows_access(self.db, owner.id))
        # The owner still administers Interviews...
        options = self.dropdown(account=owner)
        self.assertIn('value="' + str(self.person_record.id) + '"', options)
        # ...but the owner's dismissed person is not offered and cannot be requested.
        self.assertNotIn('value="' + str(record.id) + '"', options)
        self.assertNotIn('value="' + str(record.id) + '"', self.dropdown())
        before = self.count()
        for requester in (self.admin, owner):
            with self.assertRaises(ValueError):
                svc.request_for_person(self.db, requester, record.id, "Purpose")
            with self.assertRaises(ValueError):
                svc.request_interview(self.db, requester, owner.id, "Purpose")
            self.db.rollback()
        self.assertEqual(self.count(), before)

    def test_permissions_and_csrf_unchanged(self):
        before = self.count()
        self.login(self.other)  # no Interviews access
        self.assertEqual(self.client.get("/admin/interviews", base_url="https://localhost").status_code, 403)
        self.assertEqual(self.client.post("/admin/interviews", data={"csrf_token": "test-csrf",
            "person_id": self.person_record.id, "purpose": "Purpose"}, base_url="https://localhost").status_code, 403)
        with self.assertRaises(PermissionError):
            svc.request_for_person(self.db, self.other, self.person_record.id, "Purpose")
        self.login(self.admin)
        response = self.client.post("/admin/interviews", data={
            "person_id": self.person_record.id, "purpose": "Purpose"}, base_url="https://localhost")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.count(), before)

    def test_how_works_links_open_their_own_section(self):
        row = self.create()
        guide = self.client.get("/interviews/how-it-works", base_url="https://localhost")
        self.assertEqual(guide.status_code, 302)  # sign-in required
        self.login(self.admin)
        guide = self.client.get("/interviews/how-it-works", base_url="https://localhost").text
        for section in ("request", "results", "session"):
            self.assertIn('id="' + section + '"', guide)
        self.assertNotIn("applicability", guide)  # recipients are not limited by it
        self.assertIn("/interviews/how-it-works#request",
                      self.client.get("/admin/interviews", base_url="https://localhost").text)
        self.assertIn("/interviews/how-it-works#results",
                      self.client.get("/admin/interviews/" + row.id, base_url="https://localhost").text)
        self.login(self.person)
        self.assertIn("/interviews/how-it-works#session",
                      self.client.get("/interviews/" + row.id, base_url="https://localhost").text)


class AIClientLimitTests(unittest.TestCase):
    """Both providers are replaced by stand-ins; nothing leaves the machine."""

    def setUp(self):
        from rfone_data_store.selection.parsing import ai_client
        self.ai = ai_client
        self.calls = calls = []

        class Messages:
            def create(self, **kwargs):
                calls.append(("anthropic", kwargs))
                return type("Response", (), {"content": [type("Block", (), {"type": "text", "text": "{}"})()]})()

        class Anthropic:
            def __init__(self, **kwargs):
                calls.append(("anthropic-client", kwargs))
                self.messages = Messages()

        class Bedrock:
            def converse(self, **kwargs):
                calls.append(("bedrock", kwargs))
                return {"output": {"message": {"content": [{"text": "{}"}]}}}

        def client(name, **kwargs):
            calls.append(("bedrock-client", kwargs))
            return Bedrock()

        fake_anthropic, fake_boto3 = type(sys)("anthropic"), type(sys)("boto3")
        fake_anthropic.Anthropic, fake_boto3.client = Anthropic, client
        for patch in (mock.patch.dict(sys.modules, anthropic=fake_anthropic, boto3=fake_boto3),
                mock.patch.dict(os.environ, ANTHROPIC_API_KEY="unused-test-key", RFONE_BEDROCK_MODEL_ID="unused-test-model",
                    RFONE_AI_TIMEOUT_SECONDS=""),
                # The process environment only, never a local .env.
                mock.patch.object(ai_client, "_read_env_or_dotenv", lambda name: os.environ.get(name) or None)):
            patch.start()
            self.addCleanup(patch.stop)

    def sent(self):
        return dict((kind, kwargs) for kind, kwargs in self.calls)

    def test_both_providers_use_the_shared_output_ceiling(self):
        self.assertEqual(self.ai.MAX_OUTPUT_TOKENS, 16000)
        self.assertEqual(self.ai._generate_json_anthropic("{}"), {})
        self.assertEqual(self.ai._generate_json_bedrock("{}"), {})
        self.assertEqual(self.sent()["anthropic"]["max_tokens"], self.ai.MAX_OUTPUT_TOKENS)
        self.assertEqual(self.sent()["bedrock"]["inferenceConfig"]["maxTokens"], self.ai.MAX_OUTPUT_TOKENS)

    def test_every_call_is_bounded_and_explicit_timeout_is_one_attempt(self):
        self.ai.generate_json("{}")
        with mock.patch.dict(os.environ, RFONE_AI_PROVIDER="BEDROCK"):
            self.ai.generate_json("{}")
        self.assertEqual((self.sent()["anthropic-client"]["timeout"], self.sent()["anthropic-client"]["max_retries"]), (100, 1))
        config = self.sent()["bedrock-client"]["config"]
        self.assertEqual((config.read_timeout, config.connect_timeout, config.retries), (100, 10, {"total_max_attempts": 2, "mode": "standard"}))
        self.calls.clear()
        with mock.patch.dict(os.environ, RFONE_AI_TIMEOUT_SECONDS="45"):
            self.ai._generate_json_anthropic("{}")
            self.ai._generate_json_bedrock("{}")
        self.assertEqual((self.sent()["anthropic-client"]["timeout"], self.sent()["anthropic-client"]["max_retries"]), (45, 0))
        config = self.sent()["bedrock-client"]["config"]
        self.assertEqual((config.read_timeout, config.retries["total_max_attempts"]), (45, 1))
        self.calls.clear()
        with mock.patch.dict(os.environ, RFONE_AI_TIMEOUT_SECONDS="not a number"):
            self.ai._generate_json_anthropic("{}")
        self.assertEqual(self.sent()["anthropic-client"]["timeout"], 100)
        self.calls.clear()
        with mock.patch.dict(os.environ, RFONE_AI_TIMEOUT_SECONDS="45"):
            self.ai._generate_json_anthropic("{}", timeout=30)
            self.ai._generate_json_bedrock("{}", timeout=30)
        self.assertEqual(self.sent()["anthropic-client"]["timeout"], 30)
        self.assertEqual(self.sent()["anthropic-client"]["max_retries"], 0)
        config = self.sent()["bedrock-client"]["config"]
        self.assertEqual((config.read_timeout, config.connect_timeout), (30, 10))
        self.assertEqual(config.retries["total_max_attempts"], 1)
        with self.assertRaises(TypeError):
            self.ai.generate_json("{}", 30)  # `timeout` stays keyword-only

    def test_bedrock_client_is_created_once_per_configuration_across_threads(self):
        import threading
        import time
        created = []
        boto3 = sys.modules["boto3"]
        def slow_client(name, **kwargs):
            time.sleep(0.05)  # widen the window two threads could both create in
            created.append((name, kwargs["config"].read_timeout))
            return type("Bedrock", (), {"converse": lambda self, **kw: {"output": {"message": {"content": [{"text": "{}"}]}}}})()
        boto3.client = slow_client
        threads = [threading.Thread(target=self.ai._generate_json_bedrock, args=("{}",), kwargs=dict(timeout=45)) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.ai._generate_json_bedrock("{}", timeout=45)
        self.assertEqual(created, [("bedrock-runtime", 45)])
        self.ai._generate_json_bedrock("{}", timeout=30)
        self.ai._generate_json_bedrock("{}")
        self.assertEqual(created, [("bedrock-runtime", 45), ("bedrock-runtime", 30), ("bedrock-runtime", 100)])
        # A replaced factory (a test stand-in or isolation guard) is always asked again.
        replacement = []
        boto3.client = lambda name, **kwargs: replacement.append(name) or slow_client(name, **kwargs)
        self.ai._generate_json_bedrock("{}", timeout=45)
        self.assertEqual(replacement, ["bedrock-runtime"])

    def test_bedrock_timeout_becomes_try_again(self):
        from botocore.exceptions import ReadTimeoutError
        from rfone_data_store.interviews import provider as interview_provider

        def slow(name, **kwargs):
            self.calls.append(("bedrock-client", kwargs))
            class Slow:
                def converse(self, **kwargs):
                    raise ReadTimeoutError(endpoint_url="https://bedrock.invalid")
            return Slow()

        sys.modules["boto3"].client = slow
        with mock.patch.dict(os.environ, RFONE_AI_PROVIDER="BEDROCK"):
            with self.assertRaises(self.ai.AIProviderTimeout):
                self.ai.generate_json("{}", timeout=75)
            with self.assertRaises(ProviderError) as caught:
                interview_provider.generate(dict(operation="question", transcript=[]))
        self.assertIn("took too long", str(caught.exception))
        self.assertIn("try again", str(caught.exception))
        self.assertEqual(self.sent()["bedrock-client"]["config"].read_timeout, interview_provider.AI_TIMEOUT_SECONDS)

    def test_web_image_limits_fit_inside_cloudfront(self):
        from rfone_data_store.interviews.provider import AI_TIMEOUT_SECONDS
        infrastructure = WEB.parent / "Infrastructure/deploy"
        dockerfile = (infrastructure / "rfone-web/Dockerfile").read_text(encoding="utf-8")
        command = json.loads(next(line for line in dockerfile.splitlines() if line.startswith("CMD "))[4:])
        options = dict(zip(command[1::2], command[2::2]))
        self.assertEqual((options["--workers"], options["--threads"], options["--worker-class"]), ("2", "4", "gthread"))
        self.assertIn("ENV RFONE_AI_TIMEOUT_SECONDS=45", dockerfile.splitlines())
        distribution = json.loads((infrastructure / "rfone-cloudfront/distribution-config.json").read_text(encoding="utf-8"))
        timeouts = {origin["CustomOriginConfig"]["OriginReadTimeout"] for origin in distribution["Origins"]["Items"]}
        self.assertEqual(AI_TIMEOUT_SECONDS, 45)
        self.assertLessEqual(AI_TIMEOUT_SECONDS + 10, min(timeouts))

    def test_server_database_pool_checks_connections_and_fails_fast(self):
        from rfone_data_store import database
        engine = mock.MagicMock()
        engine.dialect.name = "postgresql"
        with mock.patch.object(database, "create_engine", return_value=engine) as create:
            database.create_configured_engine("postgresql://user:secret@db.invalid/rfone")
            database.create_configured_engine("sqlite:///unused.sqlite3")
        self.assertEqual(create.call_args_list[0].kwargs, dict(future=True, pool_pre_ping=True, pool_timeout=10))
        self.assertEqual(create.call_args_list[1].kwargs, dict(future=True))


class RealSDKRetryConfigurationTests(unittest.TestCase):
    def test_attempt_budget_is_the_total_seen_by_the_real_sdk(self):
        # Unlike the stand-ins above, the SDK normalizes max_attempts to total_max_attempts.
        # Synthetic static credentials and localhost prevent credential/metadata/network lookup.
        import boto3
        from types import SimpleNamespace
        from rfone_data_store.selection.parsing import ai_client
        session=boto3.Session(aws_access_key_id="synthetic",aws_secret_access_key="synthetic",region_name="us-east-1")
        factory=SimpleNamespace(client=lambda name,**kw:session.client(name,endpoint_url="http://127.0.0.1:1",**kw))
        for total in (1,2):
            client=ai_client._bedrock_client(factory,"us-east-1",45,total)
            self.addCleanup(client.close)
            self.assertEqual(client.meta.config.retries["total_max_attempts"],total)


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False).result
    finally:
        _engine.dispose()
        TEMP.cleanup()
    sys.exit(0 if result.wasSuccessful() else 1)
