"""Review > Define rule, end to end on an isolated COPY of the Bank database (`_isolated`), with the real routes:
the Bank recognition-profile editor (conversation, choices, Preview, Save and apply) and C-Bank (refresh of the
run, the group reopened). Only the AI provider is simulated: online research and the reading of the person's
instruction return fixed answers. The WHYs used are the test's choice on the copy, not a classification of the
real movements.

Verified: Preview writes no movement data; a changed conversation invalidates the Preview; the same Preview cannot
be saved twice; a profile has no draft; confirmed human decisions are untouched. Kept as assertions, two FINDINGS
on the UBER group ("WHO recognised, WHY to determine"): its open movements are not in the profile's application
queue (Save and apply to existing finds nothing to apply), and a new UBER movement is not classified by the profile
on import because no extraction rule reads its WHO. The group is resolved by the WHY rules of every scope
(test_rule_scopes), which the engine reads directly."""
import hashlib, json, re, sys, unittest
from functools import wraps
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated  # noqa: F401
from cbank import config, engine as engine_mod, legacy, service, store
from cbank.web import create_app

WEB = config.BANK_CODE_ROOT / "03 Software" / "RF-One Web"
sys.path.insert(0, str(WEB))
from flask import Flask, abort, request  # noqa: E402
from jinja2 import ChoiceLoader, DictLoader  # noqa: E402
from sqlalchemy import create_engine, select, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.bank_reconciliation import flow, ai_rules  # noqa: E402

PERSONAL_WHY, COMPANY_WHY = "Owner Personal Travel", "Business Travel - Transportation"


def db_hash():
    """The movement data and the rules: decisions, allocations, movement review states, rules and versions.
    (Conversations and Previews are records of the editor itself, not movement data.)"""
    import sqlite3
    con = sqlite3.connect(f"file:{Path(config.BANK_DB).as_posix()}?mode=ro", uri=True)
    try:
        parts = [con.execute(q).fetchall() for q in (
            "select id, explanation_id, review_status from financial_transactions order by id",
            "select * from bank_transaction_explanations order by id",
            "select * from bank_transaction_allocations order by id",
            "select id, status, apply_future, deleted_at from bank_ai_rules order by id",
            "select id, rule_id, version_no from bank_ai_rule_versions order by id")]
    finally:
        con.close()
    return hashlib.sha256(repr(parts).encode()).hexdigest()


class DefineRuleEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cbank = create_app()
        cls.cbank.config.update(TESTING=True)
        cls.cc = cls.cbank.test_client()
        cls.ctoken = re.search(r'name="cbank-token" content="([^"]+)"', cls.cc.get("/").get_data(as_text=True)).group(1)
        cls.con = cls.cbank.config["CON"]
        cls.run_id = store.runs(cls.con)[0]["id"]
        cls.engine = create_engine(f"sqlite:///{Path(config.BANK_DB).as_posix()}", connect_args={"timeout": 30})
        cls.Session = sessionmaker(cls.engine)
        app = Flask("bank-e2e", template_folder=str(WEB / "templates"))
        app.secret_key = "e2e"
        app.config["BANK_CHAT_PROVIDER_CONTEXT_APPROVED"] = True
        app.jinja_loader = ChoiceLoader([DictLoader({"base.html": "{% block content %}{% endblock %}",
                                                     "_bank_macros.html": "{% macro module_nav(active) %}Bank{% endmacro %}"}),
                                         app.jinja_loader])
        app.jinja_env.globals["csrf_token"] = lambda: "e2e-csrf"

        def gate(fn):
            @wraps(fn)
            def protected(*a, **k):
                if request.headers.get("X-Test-Auth") != "yes":
                    abort(401)
                return fn(*a, **k)
            return protected

        def csrf():
            if request.form.get("csrf_token") != "e2e-csrf":
                abort(400)
        from bank_ai_rule_routes import register_bank_ai_rule_routes
        register_bank_ai_rule_routes(app, gate=gate, SessionFactory=cls.Session, load_current_account=lambda _: None,
                                     require_csrf=csrf)
        cls.bank = app.test_client()
        with cls.Session() as db:
            cls.who = db.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "UBER"))
            whys = {r.name: r for r in db.scalars(select(m.BankTransactionReason))}
            cls.personal, cls.company = whys[PERSONAL_WHY], whys[COMPANY_WHY]
            # WHAT derives from WHY: the P&L WHATs of the two WHYs (a balance-sheet destination is no WHAT)
            cls.what_ids = [x for x in (cls.personal.accounting_classification_id, cls.company.accounting_classification_id)
                            if x and db.get(m.BankAccountingClassification, x).is_what]

    def bpost(self, path, **data):
        return self.bank.post(path, data=dict(data, csrf_token="e2e-csrf"), headers={"X-Test-Auth": "yes"})

    def group_open(self):
        r = self.cc.get(f"/api/runs/{self.run_id}/results?exc=WHO_SOURCE_CLASSIFICATION_MISSING&group=UBER").get_json()
        return [x for x in r["rows"] if x["status"] != engine_mod.RECONCILED]

    def human(self):
        with self.Session() as db:
            q = select(m.FinancialTransaction.id, m.BankTransactionExplanation.occurrence_id, m.BankTransactionExplanation.transaction_reason_id) \
                .join(m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id) \
                .where(m.BankTransactionExplanation.decision_source == "HUMAN", m.BankTransactionExplanation.occurrence_id == self.who.id)
            return sorted(db.execute(q).all())

    def spec(self):
        return dict(engine=flow.ENGINE, kind="PHOTO", who="UBER", aliases=[], whom_mode="SOURCE", review_before_confirm=True,
                    allowed_why_ids=[self.personal.id, self.company.id], allowed_whom_ids=[], requirements=[], unresolved=[],
                    branches=[dict(conditions=[dict(field="source_class", op="is", value=ai_rules.SOURCE_PERSONAL)], why_id=self.personal.id,
                                   destination_id=self.personal.accounting_classification_id, mode="CODE"),
                              dict(conditions=[dict(field="source_class", op="is", value=ai_rules.SOURCE_NOT_PERSONAL)], why_id=self.company.id,
                                   destination_id=self.company.accounting_classification_id, mode="CODE")])

    def say(self, chat, text, spec):
        with patch("bank_chatgpt.generate_json", return_value=dict(ready=True, title="UBER", reply=text, spec=spec)):
            r = self.bpost(f"/bank/flow/conversation/{chat}", message=text)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertTrue(r.get_json()["ready"], r.get_json()["messages"][-1])
        return r.get_json()

    def test_profile_editor_on_the_group_and_reuse_on_new_imports(self):
        open_before = self.group_open()
        self.assertGreater(len(open_before), 6, "the UBER group of the copy is open")
        human_before = self.human()
        # 1. Define rule: the editor for the group's WHO, research (simulated provider) and WHY choices.
        chat = self.bpost("/bank/flow/conversation", kind="PHOTO", who_id=self.who.id).get_json()["id"]
        with patch("bank_profile_research.research", return_value=dict(probable_who="UBER", summary="Ride service (simulated)", sources=[], proposals=[])):
            self.assertEqual(self.bpost(f"/bank/flow/conversation/{chat}/research", mode="who").status_code, 200)
        r = self.bpost(f"/bank/flow/conversation/{chat}/research/choices", who="UBER",
                       why_ids=json.dumps([self.personal.id, self.company.id]), what_ids=json.dumps(self.what_ids))
        self.assertEqual(r.status_code, 200, r.get_json())
        self.say(chat, "Personal card: owner travel. Company account: business transportation. WHOM is the Source owner.", self.spec())
        # 2. The profile editor keeps no draft of a profile (drafts exist for AI extraction rules and for the WHY
        #    rules of every scope, see test_rule_scopes): the request is refused and nothing is written.
        before = db_hash()
        draft = self.bpost(f"/bank/flow/conversation/{chat}/draft", pending_message="")
        self.assertEqual(draft.status_code, 409, draft.get_json())
        self.assertEqual(db_hash(), before)
        # 3. Simulate (Preview) on every movement still to reconcile: read-only. FINDING kept as an assertion: the
        #    open movements of this group already have their WHO, so they are not in the profile's application queue
        #    ("To Reconcile"): the profile can be saved for future imports but applies to none of them now.
        state = db_hash()
        p = self.bpost(f"/bank/flow/conversation/{chat}/preview", scope="ALL").get_json()
        self.assertEqual(db_hash(), state, "Preview wrote to the database")
        with self.Session() as db:
            from rfone_data_store.bank_reconciliation import reconciliation_runner as runner
            pending = {t.id for t in runner.pending(db)}
        in_queue = {x["txn_id"] for x in open_before} & pending
        self.assertEqual(in_queue, set())
        self.assertFalse(p["can_apply"])
        print(f"\n  profile Preview ALL: examined {p['examined']}, matched {p['matched']}; group movements in the profile queue: "
              f"{len(in_queue)} of {len(open_before)} -> {p['blocking_reason']}")
        refused = self.bpost(f"/bank/flow/conversation/{chat}/save", preview_id=p["id"], action="ALL")
        self.assertEqual(refused.status_code, 409, refused.get_json())
        self.assertEqual(db_hash(), state)
        # 4. Save for future imports: a changed conversation invalidates the Preview first.
        p = self.bpost(f"/bank/flow/conversation/{chat}/preview").get_json()
        self.say(chat, "Same rule, restated.", self.spec())
        stale = self.bpost(f"/bank/flow/conversation/{chat}/save", preview_id=p["id"], action="FUTURE")
        self.assertEqual(stale.status_code, 409, stale.get_json())
        self.assertEqual(db_hash(), state)
        p = self.bpost(f"/bank/flow/conversation/{chat}/preview").get_json()
        saved = self.bpost(f"/bank/flow/conversation/{chat}/save", preview_id=p["id"], action="FUTURE")
        self.assertEqual(saved.status_code, 200, saved.get_json())
        v = saved.get_json()
        self.assertEqual(v["updated"], 0)
        with self.Session() as db:
            rule = db.get(m.BankAiRule, v["rule_id"])
            self.assertEqual((rule.status, rule.apply_future), ("ACTIVE", True))
        # 5. No double application: the same Preview is refused.
        after_save = db_hash()
        again = self.bpost(f"/bank/flow/conversation/{chat}/save", preview_id=p["id"], action="FUTURE")
        self.assertEqual(again.status_code, 409, again.get_json())
        self.assertEqual(db_hash(), after_save)
        # 6. Human decisions protected; the group reopened after the refresh is unchanged (nothing applied now).
        self.assertEqual(self.human(), human_before)
        rf = self.cc.post(f"/api/runs/{self.run_id}/refresh", headers={"X-CBank-Token": self.ctoken}, data=dict(exc="WHO_SOURCE_CLASSIFICATION_MISSING", group="UBER"))
        self.assertEqual(rf.status_code, 200)
        self.assertEqual(len(self.group_open()), len(open_before))
        # 7. Reuse on a NEW movement of the same WHO, as a new import brings it: the saved profile classifies it.
        with self.Session() as db:
            model = db.get(m.FinancialTransaction, open_before[0]["txn_id"])
            clone = m.FinancialTransaction(**{c.name: getattr(model, c.name) for c in m.FinancialTransaction.__table__.columns
                                              if c.name not in ("id", "explanation_id", "import_batch_id") and not c.primary_key})
            for attr in ("external_id", "source_row_hash", "dedup_key", "fingerprint"):
                if hasattr(clone, attr) and getattr(clone, attr):
                    setattr(clone, attr, f"{getattr(clone, attr)}-e2e-new")
            from datetime import timedelta
            clone.posting_date = model.posting_date + timedelta(days=400)
            if getattr(clone, "transaction_date", None):
                clone.transaction_date = clone.posting_date
            db.add(clone)
            db.flush()
            source_class = flow.facts(db, clone, "UBER").get("source_class")
            expected_why = self.personal.id if source_class == ai_rules.SOURCE_PERSONAL else self.company.id
            from rfone_data_store.bank_reconciliation import reconciliation_runner as runner
            plan = runner.plan(db, clone)
            print(f"  new movement plan: extracted WHO {plan.get('extracted_who')!r}, choice {bool(plan.get('choice'))}, note {plan.get('note')!r}")
            applied = flow.import_new(db, clone)
            db.commit()
            new_id = clone.id
            # FINDING: no extraction rule reads UBER (the engine recognises it by name), so the import planner never
            # reaches the profile: the new movement is not classified by it.
            self.assertIsNone(plan.get("extracted_who"))
            self.assertFalse(applied)
        eng = service.new_engine(self.con)
        try:
            res = eng.evaluate(eng.by_id[new_id])
        finally:
            eng.db.close()
        self.assertEqual(res["who_id"], self.who.id)
        self.assertIn("WHO_SOURCE_CLASSIFICATION_MISSING", [x["code"] for x in res["exceptions"]])
        print(f"  new movement #{new_id}: the engine recognises UBER but the profile gives no WHY (still open)")


if __name__ == "__main__":
    unittest.main()
