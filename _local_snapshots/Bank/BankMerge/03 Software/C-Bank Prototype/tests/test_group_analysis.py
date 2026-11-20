"""Review > Analyse the group, on an isolated copy of the Bank database (`_isolated`), with a scripted AI.

The analysis reads EVERY movement of a group (never a 6-movement cap), proposes WHO WHY rules with subgroups and
exceptions, simulates them, reports only the limitations that concern the group, and writes nothing. The Bank
wrapper keeps its general completeness gate for full runs and AI investigations, never for this analysis."""
import hashlib, json, re, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated  # noqa: F401  — CBANK_BANK_DB is a temporary copy
from cbank import config, group_analysis as G, legacy, store
from cbank.web import create_app
from rfone_data_store.bank_reconciliation import intake, why_patterns as wp


def db_hash():
    return hashlib.sha256(Path(config.BANK_DB).read_bytes()).hexdigest()


class ScriptedAI:
    """Reads each format: 'EATS' or ACH formats are meals, the others travel; PAYPAL / HELP formats it cannot tell.
    Scripted for the test (subgroups and an unclear format), not a statement about the real movements."""
    def __init__(self, meal, travel, unclear=("HELP", "PAYPAL")):
        self.meal, self.travel, self.unclear, self.calls, self.formats = meal, travel, unclear, 0, []

    def __call__(self, prompt):
        self.calls += 1
        batch = json.loads(prompt[prompt.index('{"catalog"'):])["formats"]
        assert len(batch) <= wp.AI_BATCH
        assert all(len(f["examples"]) <= wp.MAX_AI_DESCRIPTIONS for f in batch)
        out = []
        for f in batch:
            self.formats.append(f["format"])
            text = " ".join(f["examples"]).upper()
            why = None if any(u in text for u in self.unclear) else self.meal if ("EATS" in text or "ACH" in f["format"]) else self.travel
            out.append(dict(id=f["id"], why=why, conditions=[], confidence="certain" if why else "unclear", reason="scripted"))
        return {"formats": out}


class GroupAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True, BANK_CHAT_PROVIDER_CONTEXT_APPROVED=True)
        cls.c = cls.app.test_client()
        page = cls.c.get("/").get_data(as_text=True)
        cls.token = re.search(r'name="cbank-token" content="([^"]+)"', page).group(1)
        con = cls.app.config["CON"]
        cls.run_id = store.runs(con)[0]["id"]
        results = [r for r in store.results(con, cls.run_id) if r["status"] != "RECONCILED"]
        groups = {}
        for r in results:
            for e in r["exceptions"]:
                groups.setdefault((e["code"], r["group_key"] or "—"), []).append(r)
        # The largest group with one recognised WHO and more than 6 movements (UBER on the PO's data).
        cls.exc, cls.group = max(((k, v) for k, v in groups.items()
                                  if len(v) > 6 and len({r.get("who_id") for r in v}) == 1 and v[0].get("who_id")),
                                 key=lambda kv: len(kv[1]))[0]
        cls.rows = groups[(cls.exc, cls.group)]
        whys = [w for w in legacy.Catalog.load(legacy.session()).whys.values() if w.status == "ACTIVE"]
        cls.meal = next(w.name for w in whys if "meal" in w.name.lower())
        cls.travel = next(w.name for w in whys if "travel" in w.name.lower())

    def analyze(self, **form):
        return self.c.post(f"/api/runs/{self.run_id}/analyze", headers={"X-CBank-Token": self.token},
                           data=dict(exc=self.exc, group=self.group, **form))

    def test_whole_group_subgroups_simulated_and_nothing_written(self):
        ai = ScriptedAI(self.meal, self.travel)
        before = db_hash()
        with patch.dict(self.app.config, CBANK_GENERATE=ai):
            r = self.analyze()
        v = r.get_json()
        self.assertEqual(r.status_code, 200, v)
        self.assertEqual(db_hash(), before, "the analysis wrote to the database")
        self.assertEqual(v["movements"], len(self.rows))
        self.assertGreater(v["movements"], 6)
        # Every format of the WHO's history was read, in batches: no 6-movement limit.
        self.assertEqual(sum(f["movements"] for f in v["formats"]), len(self.rows))
        self.assertGreaterEqual(len(ai.formats), len(v["formats"]))
        self.assertEqual(ai.calls, -(-len(ai.formats) // wp.AI_BATCH))
        self.assertIn(v["state"], (G.PROPOSAL, G.NO_RULE))
        for p in v["proposals"]:
            self.assertEqual(p["spec"]["scope"], "WHO")
            self.assertTrue(p["spec"]["conditions"], "a rule on the WHO name alone was proposed")
            self.assertTrue(all(c["field"] != "who" for c in p["spec"]["conditions"]))
            self.assertEqual(p["resolves"], len(p["resolved"]))
            self.assertTrue(p["what"] or p["why"])
        resolved = {x["id"] for p in v["proposals"] for x in p["resolved"]}
        excluded = {x["id"] for x in v["excluded"]}
        self.assertFalse(resolved & excluded)
        self.assertTrue(all(x["reason"] in ("CONFLICT", "PROTECTED", "NOT_READ", "UNCLEAR", "NOT_SUPPORTED") for x in v["excluded"]))
        self.assertFalse(v["applied"])
        print(f"\n  group {self.exc}|{self.group}: {v['movements']} movements, {len(v['formats'])} formats, "
              f"{ai.calls} AI calls, state {v['state']}, proposals {[(p["why"], p["resolves"], p["conditions"], p["exceptions"]) for p in v["proposals"]]}, "
              f"excluded {len(v['excluded'])}, sources {v['sources']}")

    def test_ai_payload_has_no_amounts_or_dates(self):
        prompts = []
        ai = ScriptedAI(self.meal, self.travel)
        with patch.dict(self.app.config, CBANK_GENERATE=lambda p: (prompts.append(p), ai(p))[1]):
            self.analyze()
        payload = "".join(prompts)
        for r in self.rows:
            self.assertNotIn(f"{abs(r['amount_minor']) / 100:.2f}", payload)
            self.assertNotIn(r["date"], payload)

    def test_missing_data_of_other_sources_does_not_block_and_own_gaps_are_reported(self):
        e = legacy.Catalog.load(legacy.session())
        own = next(t.payment_instrument_id for t in legacy.session().query(legacy.m.FinancialTransaction)
                   .filter(legacy.m.FinancialTransaction.id == self.rows[0]["txn_id"]))
        other = next(i for i in e.instruments if i != own)
        from datetime import date
        gaps = [intake.Gap(intake.GAP_MISSING_STATEMENT, own, "OWN SOURCE", date(2026, 3, 1), date(2026, 3, 31), "missing statement"),
                intake.Gap(intake.GAP_MISSING_STATEMENT, other, "OTHER SOURCE", date(2026, 3, 1), date(2026, 3, 31), "missing statement")]
        with patch.object(intake, "completeness", return_value=type("C", (), {"gaps": gaps})()), \
                patch.dict(self.app.config, CBANK_GENERATE=ScriptedAI(self.meal, self.travel)):
            v = self.analyze().get_json()
        cov = [l for l in v["limits"] if l["kind"] == "COVERAGE"]
        self.assertEqual([l["source"] for l in cov], ["OWN SOURCE"])
        self.assertIn(v["state"], (G.PROPOSAL, G.NO_RULE))          # analysed anyway, on the available movements

    def test_consent_missing_is_limited_and_sends_nothing(self):
        ai = ScriptedAI(self.meal, self.travel)
        with patch.dict(self.app.config, BANK_CHAT_PROVIDER_CONTEXT_APPROVED=False, CBANK_GENERATE=ai), \
                patch("bank_assistant_preview_routes._provider_context_approved", return_value=False, create=True):
            v = self.analyze().get_json()
        self.assertEqual(v["state"], G.LIMITED)
        self.assertEqual(v["limits"][0]["kind"], "CONSENT")
        self.assertEqual(ai.calls, 0)

    def test_provider_error_is_retriable_error(self):
        def down(_prompt):
            raise RuntimeError("provider down")
        with patch.dict(self.app.config, CBANK_GENERATE=down):
            r = self.analyze()
        self.assertEqual(r.get_json()["state"], G.ERROR)

    def test_group_without_who_is_limited_without_ai(self):
        con = self.app.config["CON"]
        rows = [r for r in store.results(con, self.run_id) if r["status"] != "RECONCILED" and not r.get("who_id")]
        if not rows:
            self.skipTest("no open movement without WHO in this copy")
        code = rows[0]["exceptions"][0]["code"]
        ai = ScriptedAI(self.meal, self.travel)
        with patch.dict(self.app.config, CBANK_GENERATE=ai):
            v = self.c.post(f"/api/runs/{self.run_id}/analyze", headers={"X-CBank-Token": self.token},
                            data=dict(exc=code, group=rows[0]["group_key"] or "—")).get_json()
        self.assertEqual(v["state"], G.LIMITED)
        self.assertEqual(ai.calls, 0)
        self.assertEqual(v["limits"][0]["kind"], "WHO_MISSING")

    def test_bank_gate_blocks_runs_and_investigation_not_group_analysis(self):
        """The Bank wrapper, with a refusing completeness check ('6 things to settle')."""
        import flask
        sys.path.insert(0, str(config.BANK_CODE_ROOT / "03 Software" / "RF-One Web"))
        import bank_guided_reconciliation as bg
        import bank_work_gate
        outer = flask.Flask("bank")
        with patch.object(bg, "available", return_value=True), patch.object(bg, "_cbank_app", return_value=self.app), \
                patch.object(bank_work_gate, "refusal", return_value="Automatic reconciliation is not available until the data are complete: 6 thing(s) to settle."), \
                patch.object(bg, "_session_factory", return_value=None):
            bg.register(outer, require_domain_access=lambda _d: (lambda f: f))
            client = outer.test_client()
            h = {"X-CBank-Token": self.token}
            with patch.dict(self.app.config, CBANK_GENERATE=ScriptedAI(self.meal, self.travel)):
                ok = client.post(f"{bg.PREFIX}/api/runs/{self.run_id}/analyze", headers=h, data=dict(exc=self.exc, group=self.group))
            self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True)[:300])
            self.assertIn(ok.get_json()["state"], (G.PROPOSAL, G.NO_RULE))
            self.assertEqual(client.post(f"{bg.PREFIX}/api/runs/{self.run_id}/investigate", headers=h, data=dict(txn_ids="1")).status_code, 409)
            self.assertEqual(client.post(f"{bg.PREFIX}/api/runs", headers=h, data=dict(kind="all")).status_code, 409)


if __name__ == "__main__":
    unittest.main()
