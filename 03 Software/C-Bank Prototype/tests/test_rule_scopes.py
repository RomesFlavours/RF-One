"""Review > rules of every scope, WHO category and contextual declarations (BANK_RULE_SCOPE_AND_WHO_CATEGORY_001),
on an isolated COPY of the Bank database (`_isolated`), through the real C-Bank routes and the one engine.

Only the internet research of the category is simulated (scripted answer). The UBER declaration and the WHYs used
(Owner Personal Travel / Owner Personal — Other) are the test's choices on the copy, not decisions on real data.
The tests run in order (test_1 ... test_9) on the same copy."""
import json, re, sqlite3, sys, unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated  # noqa: F401
from cbank import config, engine as engine_mod, legacy, service, store
from cbank.web import create_app
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import who_categories as wc, who_why_rules as wr

EXC, GROUP = "WHO_SOURCE_CLASSIFICATION_MISSING", "UBER"
DECLARATION = "Io uso UBER soltanto per trasporto"


def human_decisions():
    con = sqlite3.connect(f"file:{Path(config.BANK_DB).as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("select t.id, e.occurrence_id, e.transaction_reason_id from financial_transactions t join "
                           "bank_transaction_explanations e on e.id = t.explanation_id where e.decision_source = 'HUMAN' order by t.id").fetchall()
    finally:
        con.close()


class RuleScopes(unittest.TestCase):
    S = {}

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True, BANK_CHAT_PROVIDER_CONTEXT_APPROVED=True)
        cls.c = cls.app.test_client()
        cls.token = re.search(r'name="cbank-token" content="([^"]+)"', cls.c.get("/").get_data(as_text=True)).group(1)
        cls.con = cls.app.config["CON"]
        cls.run_id = store.runs(cls.con)[0]["id"]
        db = legacy.session()
        cls.who = next(i for i, n in legacy.Catalog.load(db).whos.items() if n == "UBER")
        whys = {r.name: r.id for r in db.query(m.BankTransactionReason)}
        cls.travel, cls.other = whys["Owner Personal Travel"], whys["Owner Personal — Other"]
        cls.human = human_decisions()
        ctx = cls.get(f"/api/who/{cls.who}/rules?run_id={cls.run_id}")
        cls.personal = [s["id"] for s in ctx["sources"] if s["subject"] == "Personal"]
        cls.company = [s["id"] for s in ctx["sources"] if s["subject"] == "Company"]

    @classmethod
    def get(cls, path):
        r = cls.c.get(path, headers={"X-CBank-Token": cls.token})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()

    def post(self, path, **data):
        return self.c.post(path, headers={"X-CBank-Token": self.token}, data=data)

    def rule(self, path, spec, **extra):
        data = dict(exc=EXC, group=GROUP, spec=json.dumps(spec), replace=json.dumps(extra.pop("replace", [])),
                    keep=json.dumps(extra.pop("keep", [])), **extra)
        return self.post(f"/api/runs/{self.run_id}/rules/{path}", **data)

    def simulate(self, spec, **extra):
        r = self.rule("simulate", spec, **extra)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def open_group(self):
        r = self.c.get(f"/api/runs/{self.run_id}/results?exc={EXC}&group={GROUP}").get_json()
        return {x["txn_id"] for x in r["rows"] if x["status"] != engine_mod.RECONCILED}

    def status(self, rule_id):
        return legacy.session().get(m.BankAiRule, rule_id).status

    def who_rule(self, why):
        return dict(scope="WHO", who_ids=[self.who], why_id=why, conditions=[dict(field="subject", op="is", value="Personal")])

    def category_rule(self, why, exceptions=()):
        spec = dict(scope="CATEGORY", categories=["PASSENGER_TRANSPORT"], why_id=why,
                    conditions=[dict(field="subject", op="is", value="Personal")])
        if exceptions:
            spec["exceptions"] = [{"conditions": [dict(field="description", op="contains", value=t)]} for t in exceptions]
        return spec

    # ------------------------------------------------------------------ category and declaration

    def test_1_category_is_proposed_with_evidence_and_used_only_once_confirmed(self):
        self.app.config["CBANK_GENERATE_WEB"] = lambda prompt: dict(
            category="PASSENGER_TRANSPORT", certainty="high", evidence="Ride-hailing platform (scripted research).",
            sources=[dict(title="Official site", url="https://www.uber.com/")])
        try:
            self.app.config["BANK_CHAT_PROVIDER_CONTEXT_APPROVED"] = False
            r = self.post(f"/api/who/{self.who}/category", action="propose")
            self.assertEqual(r.status_code, 409, "no consent: nothing may be sent")
            self.app.config["BANK_CHAT_PROVIDER_CONTEXT_APPROVED"] = True
            v = self.post(f"/api/who/{self.who}/category", action="propose").get_json()
        finally:
            self.app.config.pop("CBANK_GENERATE_WEB")
        p = v["proposed"]
        self.assertEqual((p["category"], p["status"], p["certainty"], p["origin"]), ("PASSENGER_TRANSPORT", "PROPOSED", "high", "AI"))
        self.assertEqual(p["sources"][0]["url"], "https://www.uber.com/")
        self.assertNotIn(self.who, wc.confirmed(legacy.session()), "a proposal authorises nothing")
        self.assertEqual(self.post(f"/api/who/{self.who}/category", action="reject").status_code, 200)
        self.assertEqual(wc.current(legacy.session())[self.who]["status"], "REJECTED")
        self.assertEqual(len(wc.history(legacy.session(), self.who)), 2, "proposal and decision both kept")

    def test_2_declaration_holds_only_on_its_sources(self):
        self.assertTrue(self.personal, "the copy has UBER movements on a personal Source")
        r = self.post(f"/api/who/{self.who}/declaration", text=DECLARATION, category="PASSENGER_TRANSPORT",
                      source_ids=json.dumps(self.personal))
        self.assertEqual(r.status_code, 200, r.get_json())
        cats = wc.Categories(legacy.session())
        self.assertEqual(cats.category_for(self.who, self.personal[0]), ("PASSENGER_TRANSPORT", f"declaration «{DECLARATION}»"))
        for source in self.company:
            self.assertEqual(cats.category_for(self.who, source), (None, None), "not extended beyond the declared Sources")

    # ------------------------------------------------------------------ one lifecycle, three scopes

    def test_3_who_rule_draft_then_apply_once(self):
        before_open = self.open_group()
        sim = self.simulate(self.who_rule(self.travel))
        self.assertGreater(sim["group_resolved"], 0)
        self.assertEqual(sim["open_conflicts"], 0)
        draft = self.rule("save", self.who_rule(self.travel), mode="DRAFT", token=sim["token"]).get_json()
        self.assertEqual(draft["status"], "INACTIVE")
        self.assertEqual(self.open_group(), before_open, "a draft changes no movement")
        # the draft changed the rules: the simulation shown before it is no longer valid
        stale = self.rule("save", self.who_rule(self.travel), mode="APPLY", token=sim["token"])
        self.assertEqual(stale.status_code, 409, stale.get_json())
        sim = self.simulate(self.who_rule(self.travel))
        changed = self.rule("save", self.who_rule(self.other), mode="APPLY", token=sim["token"])
        self.assertEqual(changed.status_code, 409, "a different rule than the one simulated is refused")
        v = self.rule("save", self.who_rule(self.travel), mode="APPLY", token=sim["token"]).get_json()
        self.assertTrue(v["ok"], v)
        self.assertEqual(self.status(v["rule_id"]), "ACTIVE")
        after_open = self.open_group()
        self.assertEqual(len(before_open) - len(after_open), sim["group_resolved"])
        again = self.rule("save", self.who_rule(self.travel), mode="APPLY", token=sim["token"])
        self.assertEqual(again.status_code, 409, "the same confirmation is not applied twice")
        RuleScopes.S.update(who_rule=v["rule_id"], resolved=before_open - after_open)
        print(f"\n  WHO rule #{v['rule_id']}: group {len(before_open)} -> {len(after_open)} open")

    def test_4_category_rule_equivalent_on_data_then_on_conditions_replace_and_restore(self):
        old = RuleScopes.S["who_rule"]
        sim = self.simulate(self.category_rule(self.travel))
        mine = next(r for r in sim["rules"] if r["rule_id"] == old)
        self.assertEqual((mine["kind"], mine["replaceable"], mine["future"]), ("EQUIVALENT", True, False),
                         "a declaration is limited to its Sources: equivalent on the data only")
        # confirming the category changes the context: the earlier simulation is refused, a new one shows the
        # equivalence also on the conditions
        self.assertEqual(self.post(f"/api/who/{self.who}/category", action="choose", category="PASSENGER_TRANSPORT").status_code, 200)
        stale = self.rule("save", self.category_rule(self.travel), mode="APPLY", replace=[old], token=sim["token"])
        self.assertEqual(stale.status_code, 409)
        sim = self.simulate(self.category_rule(self.travel), replace=[old])
        mine = next(r for r in sim["rules"] if r["rule_id"] == old)
        self.assertEqual((mine["kind"], mine["future"], mine["replace"]), ("EQUIVALENT", True, True))
        self.assertEqual(sim["summary"]["changed_why"] + sim["summary"]["lost_why"], 0)
        open_before = self.open_group()
        v = self.rule("save", self.category_rule(self.travel), mode="APPLY", replace=[old], token=sim["token"]).get_json()
        self.assertTrue(v["ok"], v)
        self.assertEqual((self.status(v["rule_id"]), self.status(old)), ("ACTIVE", "INACTIVE"))
        self.assertEqual(self.open_group(), open_before, "an equivalent replacement changes no outcome")
        record = v["replaced"]
        self.assertEqual([x["rule_id"] for x in record["replaced"]], [old])
        self.assertIsNotNone(legacy.session().get(m.BankAiRule, old), "never deleted")
        r = self.post(f"/api/rules/replacements/{record['record_id']}/restore", run_id=self.run_id)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual((self.status(old), self.status(v["rule_id"])), ("ACTIVE", "INACTIVE"))
        RuleScopes.S["category_rule"] = v["rule_id"]

    def test_5_conflict_is_shown_blocks_apply_and_can_be_kept_as_exception(self):
        old = RuleScopes.S["who_rule"]
        spec = self.category_rule(self.other)
        sim = self.simulate(spec)
        mine = next(r for r in sim["rules"] if r["rule_id"] == old)
        self.assertEqual(mine["kind"], "CONFLICT")
        self.assertTrue(mine["movements"])
        blocked = self.rule("save", spec, mode="APPLY", token=sim["token"])
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("conflicts", blocked.get_json()["error"])
        kept = self.simulate(spec, keep=[old])
        mine = next(r for r in kept["rules"] if r["rule_id"] == old)
        self.assertEqual(mine["kind"], "KEPT")
        self.assertIn({"field": "who", "op": "in", "value": ["UBER"]}, kept["spec"]["exceptions"][0]["conditions"])
        self.assertEqual(kept["open_conflicts"], 0)

    def test_6_exceptions_general_and_heterogeneous_scopes(self):
        sim = self.simulate(self.category_rule(self.travel, exceptions=["EATS"]))
        self.assertTrue(all("EATS" not in x["description"].upper() for x in sim["rows"] if x["effect"] in ("new_why", "changed_why")))
        bad = self.rule("simulate", dict(scope="GENERAL", why_id=self.travel, conditions=[dict(field="subject", op="is", value="Personal")]))
        self.assertEqual(bad.status_code, 400, "a general rule on the Source subject alone is a generic WHY")
        bad = self.rule("simulate", dict(scope="CATEGORY", categories=["MARKETPLACE"], why_id=self.travel,
                                         conditions=[dict(field="subject", op="is", value="Personal")]))
        self.assertEqual(bad.status_code, 400, "a heterogeneous category cannot determine one WHY")
        general = self.simulate(dict(scope="GENERAL", why_id=self.travel, conditions=[
            dict(field="subject", op="is", value="Personal"), dict(field="description", op="contains", value="UBER")]))
        self.assertTrue(any(r["rule_id"] == RuleScopes.S["who_rule"] for r in general["rules"]))

    def test_7_new_movement_is_resolved_by_the_active_rule(self):
        db = legacy._writer_session()
        try:
            model = db.get(m.FinancialTransaction, sorted(RuleScopes.S["resolved"])[0])
            clone = m.FinancialTransaction(**{c.name: getattr(model, c.name) for c in m.FinancialTransaction.__table__.columns
                                              if c.name not in ("id", "explanation_id", "import_batch_id") and not c.primary_key})
            for attr in ("external_id", "source_row_hash", "dedup_key", "fingerprint"):
                if getattr(clone, attr, None):
                    setattr(clone, attr, f"{getattr(clone, attr)}-scope-new")
            clone.posting_date = model.posting_date + timedelta(days=400)
            if getattr(clone, "transaction_date", None):
                clone.transaction_date = clone.posting_date
            db.add(clone)
            db.commit()
            new_id = clone.id
        finally:
            db.close()
        eng = service.new_engine(self.con)
        try:
            r = eng.evaluate(eng.by_id[new_id])
        finally:
            eng.db.close()
        self.assertEqual((r["who_id"], r["why_id"]), (self.who, self.travel))
        self.assertIn(f"rule #{RuleScopes.S['who_rule']}", next(s["evidence"] for s in r["trace"] if s["stage"] == "Classification"))
        print(f"  new movement #{new_id}: WHY from rule #{RuleScopes.S['who_rule']}, status {r['status']}")

    def test_8_human_decisions_unchanged(self):
        self.assertEqual(human_decisions(), self.human)

    def test_9_context_lists_every_scope(self):
        ctx = self.get(f"/api/who/{self.who}/rules?run_id={self.run_id}")
        scopes = {r["scope"] for r in ctx["rules"]}
        self.assertTrue({"WHO", "CATEGORY"} <= scopes)
        self.assertEqual(ctx["category"]["status"], "CONFIRMED")
        self.assertEqual(ctx["declarations"][0]["text"], DECLARATION)
        self.assertTrue(ctx["replacements"][0]["restored"])


if __name__ == "__main__":
    unittest.main()
