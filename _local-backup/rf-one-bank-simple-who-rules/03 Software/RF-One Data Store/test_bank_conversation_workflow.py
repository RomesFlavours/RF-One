"""Synthetic tests: discuss, save/future/past, transaction entry and safe undo."""
import sys
import json
import unittest
from pathlib import Path
from functools import wraps
from unittest.mock import patch

from flask import Flask, abort, request
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import test_bank_rule_safe_applications as fixtures
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules, ai_rule_operations as operations


class ConversationWorkflow(unittest.TestCase):
    decide = fixtures.SafeApplications.decide
    tearDown = fixtures.SafeApplications.tearDown

    def setUp(self):
        fixtures.SafeApplications.setUp(self)
        web = Path(__file__).parent.parent / "RF-One Web"
        sys.path.insert(0, str(web))
        from bank_ai_rule_routes import register_bank_ai_rule_routes
        self.app = Flask(__name__, template_folder=str(web / "templates"))
        self.app.secret_key = "conversation-test-secret"
        self.app.config["BANK_CHAT_PROVIDER_CONTEXT_APPROVED"] = True
        self.app.jinja_loader = ChoiceLoader([DictLoader({
            "base.html": "{% block content %}{% endblock %}",
            "_bank_macros.html": "{% macro module_nav(active) %}Bank{% endmacro %}",
        }), self.app.jinja_loader])
        self.app.jinja_env.globals["csrf_token"] = lambda: "test-csrf"
        def gate(fn):
            @wraps(fn)
            def protected(*args, **kwargs):
                if request.headers.get("X-Test-Auth") != "yes": abort(401)
                return fn(*args, **kwargs)
            return protected
        def csrf():
            if request.form.get("csrf_token") != "test-csrf": abort(400)
        register_bank_ai_rule_routes(self.app, gate=gate, SessionFactory=sessionmaker(self.engine),
                                    load_current_account=lambda _: None, require_csrf=csrf)
        self.client = self.app.test_client(); self.headers = {"X-Test-Auth": "yes"}

    def context(self, **kwargs):
        response = self.client.get('/bank/ai-rules/context', query_string=kwargs, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def post(self, path, **kwargs):
        return self.client.post(path, data={"csrf_token": "test-csrf", **kwargs}, headers=self.headers)

    def state(self):
        self.s.expire_all()
        return [(t.id, t.explanation_id, t.amount_minor, t.description_original)
                for t in self.s.scalars(select(m.FinancialTransaction).order_by(m.FinancialTransaction.id))]

    def test_all_saved_rules_and_transaction_without_who_have_context(self):
        c = self.context(transaction_id=self.txns[0].id)
        self.assertEqual(c['rule_id'], self.rule.id)
        self.assertTrue(c['confirmation_token'])
        c = self.context(transaction_id=self.txns[2].id)
        self.assertIsNone(c['who_id'])
        snapshot = self.client.get('/bank/ai-rules/snapshot', headers=self.headers).get_json()
        self.assertIn(self.rule.id, [r['id'] for r in snapshot['learned_rules']])
        self.assertTrue(any(r['who_id'] is None for r in snapshot['cases']))

    def test_save_without_scope_is_refused(self):
        c = self.context(rule_id=self.rule.id); before = self.state()
        response = self.post('/bank/ai-rules/chat/decision', confirmation_token=c['confirmation_token'], action='SAVE_ONLY')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.state(), before)

    def test_future_only_and_stale_prior_choice(self):
        c = self.context(rule_id=self.rule.id); before = self.state()
        response = self.post('/bank/ai-rules/chat/decision', confirmation_token=c['confirmation_token'], action='FUTURE')
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()['apply_future']); self.assertEqual(self.state(), before)
        stale = self.post('/bank/ai-rules/chat/decision', confirmation_token=c['confirmation_token'], action='SAVE_ONLY')
        self.assertEqual(stale.status_code, 409)

    def test_past_preview_is_read_only_then_apply_and_rollback_in_context(self):
        c = self.context(rule_id=self.rule.id); before = self.state()
        response = self.post('/bank/ai-rules/chat/decision', confirmation_token=c['confirmation_token'], action='PAST_AND_FUTURE')
        self.assertEqual(response.status_code, 200, response.get_json())
        preview = response.get_json(); self.assertEqual(preview['planned_updates'], 3)
        self.assertEqual(self.state(), before); self.s.refresh(self.rule); self.assertFalse(self.rule.apply_future)
        applied = self.post('/bank/ai-rules/chat/apply', confirmation_token=c['confirmation_token'], preview_id=preview['preview_id'])
        self.assertEqual(applied.status_code, 200, applied.get_json())
        data = applied.get_json(); self.assertEqual(data['application']['updated'], 3)
        aid = data['application']['application_id']
        history = self.client.get(f'/bank/ai-rules/rules/{self.rule.id}/applications', headers=self.headers).get_json()
        self.assertTrue(history['applications'][0]['can_rollback'])
        self.s.expire_all(); self.decide(self.txns[1], self.oldwho.id, self.why.id); self.s.commit()
        undone = self.post(f'/bank/ai-rules/applications/{aid}/rollback').get_json()
        self.assertEqual(undone['restored'], 2); self.assertEqual(len(undone['skipped']), 1)

    def test_past_refuses_changed_data_and_missing_preview_without_saving_future(self):
        c = self.context(rule_id=self.rule.id)
        missing = self.post('/bank/ai-rules/chat/apply', confirmation_token=c['confirmation_token'])
        self.assertEqual(missing.status_code, 409)
        preview = self.post('/bank/ai-rules/chat/decision', confirmation_token=c['confirmation_token'], action='PAST_AND_FUTURE').get_json()
        self.txns[0].amount_minor -= 5; self.s.commit(); before = self.state()
        bad = self.post('/bank/ai-rules/chat/apply', confirmation_token=c['confirmation_token'], preview_id=preview['preview_id'])
        self.assertEqual(bad.status_code, 409); self.assertEqual(self.state(), before)
        self.s.refresh(self.rule); self.assertFalse(self.rule.apply_future)

    def test_multiple_compatible_rules_require_a_choice(self):
        text = 'If description contains "SYNTHETIC RULE TEST", WHO is "OLD WHO".'
        def generate(_):
            raw = self.generate(''); raw['who'] = {'mode':'fixed', 'name':'OLD WHO'}; raw['why'] = None
            return raw
        operations.save_rule(self.s, rule_id=None, rule_text=text, create_missing_who=False,
            apply_future=False, origin_transaction_id=self.txns[0].id, account_id=None, generate=generate)
        self.s.commit()
        context = self.context(transaction_id=self.txns[0].id)
        self.assertEqual(len(context['related_rules']), 2); self.assertIsNone(context['rule_id'])

    def test_discuss_new_rule_from_transaction_without_who(self):
        self.txns[2].description_original = 'UNKNOWN TEST'; self.s.commit()
        text = 'If description contains "UNKNOWN TEST", WHO is "NEW WHO" and WHY is "New reason".'
        raw = self.generate(''); raw['conditions'][0]['value'] = 'UNKNOWN TEST'
        with patch('bank_chatgpt.generate_json', return_value={'ready':True,'reply':'Ecco il criterio.',
                'rule_text':text,'interpretation':raw}):
            response = self.post('/bank/ai-rules/chat', transaction_id=self.txns[2].id,
                messages=json.dumps([{'role':'user','text':'Per UNKNOWN TEST usa NEW WHO e New reason.'}]), general_rules='[]')
        self.assertEqual(response.status_code, 200, response.get_json())
        draft = response.get_json(); self.assertTrue(draft['ready'])
        before = self.state()
        saved = self.post('/bank/ai-rules/chat/decision', confirmation_token=draft['confirmation_token'], action='FUTURE')
        self.assertEqual(saved.status_code, 200, saved.get_json()); self.assertEqual(self.state(), before)
        rule_id = saved.get_json()['saved_rule_id']
        self.assertNotEqual(rule_id, self.rule.id)
        reopened = self.context(rule_id=rule_id); self.assertEqual(reopened['rule_text'], text)

    def test_auth_csrf_tamper_and_history_only_page(self):
        self.assertEqual(self.client.get('/bank/ai-rules/context').status_code, 401)
        self.assertEqual(self.client.post('/bank/ai-rules/chat/decision', headers=self.headers).status_code, 400)
        self.assertEqual(self.post('/bank/ai-rules/chat/decision', confirmation_token='tampered', action='FUTURE').status_code, 409)
        page = self.client.get('/bank/ai-rules/applications', headers=self.headers)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('rule-application-form', page.data.decode())


if __name__ == '__main__':
    unittest.main()
