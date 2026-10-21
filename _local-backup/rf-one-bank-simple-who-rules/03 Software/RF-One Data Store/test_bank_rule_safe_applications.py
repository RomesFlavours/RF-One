"""Synthetic-only regression tests for modes, preview binding and guarded undo."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules as rules
from rfone_data_store.bank_reconciliation import ai_rule_operations as operations
from rfone_data_store.bank_reconciliation import recognition, economic_allocation
from rfone_data_store.bank_reconciliation import rule_application_safety as safety


class SafeApplications(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rfone_test_safe_rules_")
        self.engine = create_engine("sqlite:///" + (Path(self.tmp.name) / "test.db").as_posix())
        m.Base.metadata.create_all(self.engine)
        self.s = Session(self.engine)
        typ = m.BankOccurrenceType(code="COUNTERPARTY", name="Counterparty", status="ACTIVE")
        inst = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Test", institution="CHASE", last_four="1234", currency="USD", status="ACTIVE")
        self.s.add_all([typ, inst]); self.s.flush()
        self.oldwho = m.BankOccurrence(canonical_name="OLD WHO", occurrence_type_id=typ.id, status="ACTIVE")
        self.newwho = m.BankOccurrence(canonical_name="NEW WHO", occurrence_type_id=typ.id, status="ACTIVE")
        self.why = m.BankTransactionReason(code="OLD_REASON", name="Old reason", status="ACTIVE")
        self.newwhy = m.BankTransactionReason(code="NEW_REASON", name="New reason", status="ACTIVE")
        self.entity = m.ReportingEntity(code="E1", name="Entity One", entity_type="PERSONAL", status="ACTIVE")
        self.entity2 = m.ReportingEntity(code="E2", name="Entity Two", entity_type="PERSONAL", status="ACTIVE")
        self.s.add_all([self.oldwho, self.newwho, self.why, self.newwhy, self.entity, self.entity2]); self.s.flush()
        self.txns = []
        for i in range(3):
            t = m.FinancialTransaction(payment_instrument_id=inst.id, posting_date=date(2026, 1, 2), amount_minor=-1000-i,
                description_original="SYNTHETIC RULE TEST", description_normalized="SYNTHETIC RULE TEST",
                status="COMPLETED", classification="UNKNOWN", duplicate_status="NONE", accounting_status="CANONICAL")
            self.s.add(t); self.s.flush(); self.txns.append(t)
        self.decide(self.txns[0], self.oldwho.id, self.why.id)
        self.decide(self.txns[1], self.oldwho.id, None)
        self.text = 'If description contains "SYNTHETIC RULE TEST", WHO is "NEW WHO" and WHY is "New reason".'
        def generate(_):
            return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "SYNTHETIC RULE TEST"}],
                    "who": {"mode": "fixed", "name": "NEW WHO"}, "why": {"mode": "fixed", "name": "New reason"},
                    "coverage": [{"instruction": "whole rule", "represented_by": "conditions, WHO and WHY"}]}
        self.generate = generate
        saved = operations.save_rule(self.s, rule_id=None, rule_text=self.text, create_missing_who=False,
            apply_future=False, origin_transaction_id=self.txns[0].id, account_id=None, generate=generate)
        self.rule = saved.rule
        self.s.commit()

    def tearDown(self):
        self.s.close(); self.engine.dispose(); self.tmp.cleanup()

    def decide(self, txn, who, why):
        return recognition._create_decision_row(self.s, txn, occurrence_id=who, transaction_reason_id=why,
            decision_source="HUMAN", decision_status="HUMAN_CONFIRMED", confidence="HIGH", explanation_notes="Test human choice")

    def preview(self, mode):
        preview = rules.preview_rule(self.s, rule_text=self.text, origin_transaction_id=self.txns[0].id,
            date_from=None, date_to=None, scope=rules.SCOPE_ALL, ai_rule_id=self.rule.id,
            application_mode=mode, generate=self.generate)
        self.s.commit()
        self.assertEqual(preview.status, "COMPLETED", preview.error_message)
        return preview

    def apply(self, preview, mode):
        a = operations.apply_rule(self.s, rule=self.rule, scope=rules.SCOPE_ALL, selected_ids=[],
            preview_id=preview.id, account_id=None, application_mode=mode)
        self.s.commit(); return a

    def current(self, t):
        return self.s.get(m.BankTransactionExplanation, t.explanation_id)

    def test_fill_preserves_populated_manual_fields_and_rollback(self):
        p = self.preview(safety.FILL_MISSING)
        self.assertEqual(p.planned_updates, 2)
        a = self.apply(p, safety.FILL_MISSING)
        self.assertEqual(self.current(self.txns[0]).transaction_reason_id, self.why.id)
        self.assertEqual(self.current(self.txns[1]).occurrence_id, self.oldwho.id)
        self.assertEqual(self.current(self.txns[1]).transaction_reason_id, self.newwhy.id)
        self.assertEqual(self.current(self.txns[2]).occurrence_id, self.newwho.id)
        out = safety.rollback_application(self.s, a.id); self.s.commit()
        self.assertEqual(out["restored"], 2)
        self.assertIsNone(self.current(self.txns[1]).transaction_reason_id)
        self.assertIsNone(self.current(self.txns[2]).occurrence_id)
        self.assertIsNone(recognition.get_current_explanation(self.s, financial_transaction_id=self.txns[2].id).occurrence_id)
        again = safety.rollback_application(self.s, a.id)
        self.assertTrue(again["already_rolled_back"])

    def test_update_overrides_manual_and_skips_subsequent_decision(self):
        p = self.preview(safety.UPDATE_ASSIGNED); a = self.apply(p, safety.UPDATE_ASSIGNED)
        self.assertEqual(a.updated, 3)
        self.decide(self.txns[1], self.oldwho.id, self.why.id); self.s.commit()
        result = safety.rollback_application(self.s, a.id); self.s.commit()
        self.assertEqual(result["restored"], 2)
        self.assertEqual([x["id"] for x in result["skipped"]], [self.txns[1].id])
        self.assertEqual(self.current(self.txns[1]).transaction_reason_id, self.why.id)
        self.assertEqual(self.current(self.txns[0]).transaction_reason_id, self.why.id)

    def test_missing_stale_changed_mode_and_consumed_preview_rejected(self):
        with self.assertRaises(operations.NeedsPreview): self.apply(type("P", (), {"id": None})(), safety.UPDATE_ASSIGNED)
        self.s.rollback()
        p = self.preview(safety.FILL_MISSING)
        with self.assertRaises(operations.NeedsPreview): self.apply(p, safety.UPDATE_ASSIGNED)
        self.s.rollback()
        p = self.preview(safety.UPDATE_ASSIGNED)
        self.txns[0].description_original = "Later source edit"; self.s.commit()
        with self.assertRaises(operations.NeedsPreview): self.apply(p, safety.UPDATE_ASSIGNED)
        self.s.rollback()
        p = self.preview(safety.UPDATE_ASSIGNED); self.apply(p, safety.UPDATE_ASSIGNED)
        with self.assertRaises(operations.NeedsPreview): self.apply(p, safety.UPDATE_ASSIGNED)

    def test_rollback_preserves_later_for_whom_and_source_change(self):
        p = self.preview(safety.UPDATE_ASSIGNED); a = self.apply(p, safety.UPDATE_ASSIGNED)
        economic_allocation.set_allocations(self.s, financial_transaction_id=self.txns[0].id,
            specs=[economic_allocation.AllocationSpec(amount_minor=self.txns[0].amount_minor,
                reporting_entity_id=self.entity.id, status=economic_allocation.NEEDS_OPERATOR)])
        self.txns[1].amount_minor -= 1; self.s.commit()
        out = safety.rollback_application(self.s, a.id); self.s.commit()
        self.assertEqual(out["restored"], 1); self.assertEqual(len(out["skipped"]), 2)

    def test_update_for_whom_and_undo_without_touching_source(self):
        t = self.txns[0]
        economic_allocation.set_allocations(self.s, financial_transaction_id=t.id,
            specs=[economic_allocation.AllocationSpec(amount_minor=t.amount_minor,
                reporting_entity_id=self.entity.id, status=economic_allocation.NEEDS_OPERATOR)])
        self.s.commit()
        planner = rules.Planner(self.s, other_rules=False)
        row = rules.row_for(self.s, t.id)
        target = rules.Target(application_mode=safety.UPDATE_ASSIGNED, why_set=True, why_id=self.newwhy.id,
            why_name=self.newwhy.name, for_whom_set=True, for_whom_id=self.entity2.id, for_whom_name=self.entity2.name)
        from datetime import datetime, timezone
        a = m.BankAiRuleApplication(rule_id=self.rule.id, version_id=operations.current_version(self.rule).id,
            mode="EXISTING_ALL", status="COMPLETED", started_at=datetime.now(timezone.utc))
        self.s.add(a)
        outcome = operations._apply_one(self.s, planner, row, target, create_missing_who=False,
            maker=operations._WhoMaker(self.s), application=a, note="Test update")
        self.s.commit(); self.assertEqual(outcome, rules.UPDATED)
        out = safety.rollback_application(self.s, a.id); self.s.commit()
        self.assertEqual(out["restored"], 1)
        alloc = economic_allocation.get_allocations(self.s, financial_transaction_id=t.id)[0]
        self.assertEqual(alloc.reporting_entity_id, self.entity.id)
        self.assertEqual(t.amount_minor, -1000)

    def test_http_preview_required_history_and_rollback(self):
        from functools import wraps
        from flask import Flask, abort, request
        from jinja2 import ChoiceLoader, DictLoader
        from sqlalchemy.orm import sessionmaker
        web = Path(__file__).parent.parent / "RF-One Web"
        sys.path.insert(0, str(web))
        from bank_ai_rule_routes import register_bank_ai_rule_routes
        app = Flask(__name__, template_folder=str(web / "templates"))
        app.secret_key = "synthetic-test-secret"
        app.jinja_loader = ChoiceLoader([DictLoader({
            "base.html": "{% block content %}{% endblock %}",
            "_bank_macros.html": "{% macro module_nav(active) %}Bank{% endmacro %}",
        }), app.jinja_loader])
        app.jinja_env.globals["csrf_token"] = lambda: "test-csrf"
        def gate(fn):
            @wraps(fn)
            def protected(*args, **kwargs):
                if request.headers.get("X-Test-Auth") != "yes": abort(401)
                return fn(*args, **kwargs)
            return protected
        def csrf():
            if request.form.get("csrf_token") != "test-csrf": abort(400)
        register_bank_ai_rule_routes(app, gate=gate, SessionFactory=sessionmaker(self.engine),
                                    load_current_account=lambda _: None, require_csrf=csrf)
        client = app.test_client(); headers = {"X-Test-Auth": "yes"}
        prefix = f"/bank/ai-rules/rules/{self.rule.id}"
        data = {"csrf_token": "test-csrf", "application_mode": safety.UPDATE_ASSIGNED}
        self.assertEqual(client.get("/bank/ai-rules/applications").status_code, 401)
        self.assertEqual(client.post(prefix + "/application-preview", headers=headers).status_code, 400)
        self.assertEqual(client.post(prefix + "/apply-preview", data=data, headers=headers).status_code, 409)
        with patch.object(rules, "default_generate", return_value=self.generate):
            response = client.post(prefix + "/application-preview", data=data, headers=headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        data["preview_id"] = response.get_json()["preview_id"]
        applied = client.post(prefix + "/apply-preview", data=data, headers=headers)
        self.assertEqual(applied.status_code, 200, applied.get_json())
        self.assertEqual(applied.get_json()["updated"], 3)
        self.assertEqual(client.get("/bank/ai-rules/applications", headers=headers).status_code, 200)
        aid = applied.get_json()["application_id"]
        out = client.post(f"/bank/ai-rules/applications/{aid}/rollback", data=data, headers=headers)
        self.assertEqual(out.status_code, 200, out.get_json())
        self.assertEqual(out.get_json()["restored"], 3)

    def test_selected_rule_replaces_previous_rule_without_changing_future_policy(self):
        other_text = 'If description contains "SYNTHETIC RULE TEST", WHO is "OLD WHO".'
        def other_generate(_):
            result = self.generate("")
            result["who"] = {"mode": "fixed", "name": "OLD WHO"}
            result["why"] = None
            return result
        operations.save_rule(self.s, rule_id=None, rule_text=other_text, create_missing_who=False,
            apply_future=True, origin_transaction_id=self.txns[0].id, account_id=None, generate=other_generate)
        self.s.commit()
        planner = rules.Planner(self.s, rule_id=self.rule.id)
        row = rules.row_for(self.s, self.txns[2].id)
        target = rules.Target(who_set=True, who_id=self.newwho.id, who_name=self.newwho.canonical_name)
        self.assertEqual(planner.plan_full(row, target, create_missing_who=False).outcome, rules.CONFLICT)
        target.application_mode = safety.UPDATE_ASSIGNED
        self.assertEqual(planner.plan_full(row, target, create_missing_who=False).outcome, rules.UPDATED)

    def test_split_allocations_and_explicit_conditions_stay_protected(self):
        t = self.txns[0]
        economic_allocation.set_allocations(self.s, financial_transaction_id=t.id, specs=[
            economic_allocation.AllocationSpec(amount_minor=-500, reporting_entity_id=self.entity.id,
                                              status=economic_allocation.NEEDS_OPERATOR),
            economic_allocation.AllocationSpec(amount_minor=-500, reporting_entity_id=self.entity2.id,
                                              status=economic_allocation.NEEDS_OPERATOR),
        ])
        self.s.commit()
        planner = rules.Planner(self.s, other_rules=False)
        row = rules.row_for(self.s, t.id)
        target = rules.Target(application_mode=safety.UPDATE_ASSIGNED, for_whom_set=True,
            for_whom_id=self.entity2.id, for_whom_name=self.entity2.name)
        self.assertEqual(planner.plan_full(row, target, create_missing_who=False).outcome, rules.PROTECTED)
        target = rules.Target(application_mode=safety.UPDATE_ASSIGNED, who_set=True,
            who_id=self.oldwho.id, who_name=self.oldwho.canonical_name,
            only_if_who_differs=True, why_set=True, why_id=self.newwhy.id, why_name=self.newwhy.name)
        self.assertEqual(planner.plan_full(row, target, create_missing_who=False).outcome, rules.UNCHANGED)


if __name__ == "__main__":
    unittest.main()
