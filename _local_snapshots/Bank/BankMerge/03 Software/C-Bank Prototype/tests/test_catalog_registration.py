"""New WHO identities and explicit manual classification; isolated Bank copy only."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated
from cbank import config, engine as E, legacy, service, store
from rfone_data_store.bank_reconciliation import who_registration as W, who_recognition as wr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sqlengine = create_engine("sqlite:///" + config.BANK_DB.as_posix())

    def setUp(self):
        self.db = Session(self.sqlengine)

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_new_name_is_created_once_without_any_movement_decision(self):
        before = self.db.query(legacy.m.BankTransactionExplanation).count()
        a = W.register_candidates(self.db, ["XYLOPHONE ZENITH SERVICES", "xylophone zenith services"])
        self.assertEqual(len(a["created"]), 1)
        self.assertFalse(a["held"])
        b = W.register_candidates(self.db, ["XYLOPHONE ZENITH SERVICES"])
        self.assertFalse(b["created"])
        self.assertEqual(b["reused"], a["created"])
        self.assertEqual(before, self.db.query(legacy.m.BankTransactionExplanation).count())

    def test_added_words_and_typo_are_held_not_merged_or_created(self):
        W.register_candidates(self.db, ["XYLOPHONE ZENITH SERVICES"])
        for name in ("XYLOPHONE ZENITH SERVICES LLC", "XYLOPHONE ZENITH SERVICE"):
            outcome = W.register_candidates(self.db, [name])
            self.assertFalse(outcome["created"])
            self.assertIn(wr.who_key(name), outcome["held"])

    def test_alias_is_reused_and_similar_alias_is_held(self):
        created = W.register_candidates(self.db, ["XYLOPHONE ZENITH SERVICES"])["created"][0]
        self.db.add(legacy.m.BankOccurrenceAlias(occurrence_id=created, alias_text="XYLOPHONIC BRAND",
                    alias_key=wr.who_key("XYLOPHONIC BRAND"), source_family="TEST", source="HUMAN"))
        self.db.flush()
        self.assertEqual(W.register_candidates(self.db, ["XYLOPHONIC BRAND"])["reused"], [created])
        self.assertTrue(W.register_candidates(self.db, ["XYLOPHONIC BRAND LLC"])["held"])

    def test_similar_names_from_same_run_are_both_held(self):
        result = W.register_candidates(self.db, ["XYLOPHONE ZENITH SERVICES", "XYLOPHONE ZENITH SERVICES LLC"])
        self.assertFalse(result["created"])
        self.assertEqual(len(result["held"]), 2)

    def test_inactive_name_and_invalid_name_are_not_created(self):
        oid = W.register_candidates(self.db, ["XYLOPHONE ZENITH SERVICES"])["created"][0]
        self.db.get(legacy.m.BankOccurrence, oid).status = "INACTIVE"
        self.db.flush()
        for name in ("XYLOPHONE ZENITH SERVICES", "123456", "A" * 256):
            result = W.register_candidates(self.db, [name])
            self.assertFalse(result["created"])
            self.assertTrue(result["held"])

class ConfigurationActionTests(unittest.TestCase):
    def setUp(self):
        from flask import Flask, request, abort
        from bank_configuration_routes import register_bank_configuration_routes
        self.app = Flask(__name__)
        self.app.secret_key = "isolated-test-only"
        def csrf():
            if request.form.get("csrf_token") != "test-token":
                abort(400)
        def gate(fn):
            from functools import wraps
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if request.headers.get("X-Test-Bank-Access") != "yes":
                    abort(403)
                return fn(*args, **kwargs)
            return wrapped
        from sqlalchemy.orm import sessionmaker
        # The completeness gate reads the isolated copy of the Bank database (never the operational one).
        self.Session = sessionmaker(create_engine("sqlite:///" + config.BANK_DB.as_posix()))
        register_bank_configuration_routes(self.app, gate=gate, SessionFactory=self.Session,
                load_current_account=None, require_csrf=csrf)
        self.app.add_url_rule("/bank/work", "bank_work", lambda: "work")
        self.client = self.app.test_client()

    def test_action_requires_bank_access_and_csrf_and_refreshes_only_on_post(self):
        import bank_guided_reconciliation as guided
        route = "/bank/configuration/recalculate"
        with patch.object(guided, "recalculate_classification", return_value=(17, {"RECONCILED": 3, "EXCEPTION": 4})) as call:
            self.assertEqual(self.client.get(route).status_code, 405)
            self.assertEqual(self.client.post(route).status_code, 403)
            self.assertEqual(self.client.post(route, headers={"X-Test-Bank-Access":"yes"}).status_code, 400)
            call.assert_not_called()
            from rfone_data_store.bank_reconciliation import intake
            # Incomplete data: the gate refuses, sends the person to the completeness check and recalculates nothing.
            with patch.object(intake, "require_ready", side_effect=intake.NotReady("6 thing(s) to settle")):
                response = self.client.post(route, headers={"X-Test-Bank-Access":"yes"}, data={"csrf_token":"test-token"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/bank/work#check"))
            call.assert_not_called()
            # Complete data: the recalculation runs once and returns to Configuration.
            with patch.object(intake, "require_ready", return_value=None):
                response = self.client.post(route, headers={"X-Test-Bank-Access":"yes"}, data={"csrf_token":"test-token"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/bank/configuration#cp-who"))
            call.assert_called_once()

    def test_gate_reads_the_real_state_of_the_isolated_copy(self):
        """No patch of the check: whatever the copy's completeness, the route follows it."""
        import bank_guided_reconciliation as guided, bank_work_gate
        with patch.object(guided, "recalculate_classification", return_value=(1, {})) as call:
            refused = bank_work_gate.refusal(self.Session, "Recalculate classification")
            response = self.client.post("/bank/configuration/recalculate", headers={"X-Test-Bank-Access":"yes"}, data={"csrf_token":"test-token"})
        self.assertEqual(response.status_code, 302)
        if refused:
            self.assertTrue(response.headers["Location"].endswith("/bank/work#check"))
            call.assert_not_called()
        else:
            call.assert_called_once()

if __name__ == "__main__":
    unittest.main()
