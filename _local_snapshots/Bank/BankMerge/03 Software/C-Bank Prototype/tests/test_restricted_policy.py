"""Restricted reconciliation: real-data copy; poison forbidden evidence and require no effect."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated
from cbank import config, engine as E, legacy, service, store

class RestrictedPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = store.connect(":memory:")
        with patch.object(store, "investigation_answers", side_effect=AssertionError("AI history read")), \
             patch.object(legacy, "generate_json", side_effect=AssertionError("AI called")):
            cls.e = E.Engine(legacy.session(), cls.con)
        cls.t = next(t for t in cls.e.txns if t.id not in cls.e.matches
                     and cls.e.owner(t) and cls.e.bank_decision(t)["source"] != "HUMAN"
                     and not E.matching.is_card_payment_out(t, cls.e.c.instruments, cls.e.card_payment_out))

    def probe(self, outcome="FOUND", hits=None):
        e = copy.copy(self.e)
        e.photos, e.why_rules = [], []
        e.source_classifications = {}
        e.who_whys_approved, e.who_default_whys = {}, {}
        name = next(iter(e.c.whos.values()))
        recognition = NS(outcome=outcome, who=name, method="TEXT", evidence="controlled alias", legacy_hits=hits or [])
        e.recogniser = NS(recognise=lambda *a, **kw: recognition)
        return e

    def test_saved_ai_memory_and_history_never_decide(self):
        e = self.probe()
        before = e.evaluate(self.t)
        why = next(w for w, row in e.c.whys.items() if row.accounting_classification_id)
        evidence = dict(txn_id=-1, who="POISON", why_id=why, category_id=None,
                        beneficiary_id=next(iter(e.c.entities)), origin=E.HUMAN_BANK)
        key = legacy.history_key(self.t.description_original)
        e.memory = {key: [evidence, evidence]}
        e.who_memory = {key: [evidence, evidence]}
        e.who_whys_history = {i: [why] for i in e.c.whos}
        e.ai_answers = {self.t.id: dict(who="POISON", why_id=why, beneficiary_id=evidence["beneficiary_id"],
                      sufficient=True, confidence=1, investigation_id=999)}
        with patch.object(config, "WHO_EXTRA_RECOGNITION", True), patch.object(config, "WHO_WHY_KNOWLEDGE", True):
            after = e.evaluate(self.t)
            for key in ("who_name", "why_id", "category_id", "beneficiary_id", "status", "exceptions", "protected"):
                self.assertEqual(before[key], after[key], key)
        self.assertIsNone(before["why_id"])
        self.assertEqual(before["beneficiary_id"], before["payer_id"])

    def test_unknown_and_ambiguous_who_stay_open(self):
        for verdict in ("NONE", "TEXT_AMBIGUOUS", "RULES_DISAGREE"):
            with self.subTest(verdict=verdict):
                r = self.probe(verdict).evaluate(self.t)
                self.assertIsNone(r["who_name"])
                self.assertEqual(r["status"], E.EXCEPTION)
                self.assertEqual(r["beneficiary_id"], r["payer_id"])

    def test_exact_pair_sets_why_and_what_with_source_owner_whom(self):
        e=self.probe()
        who=next(iter(e.c.whos))
        why=next(w for w,row in e.c.whys.items() if row.accounting_classification_id and w not in e.provisional)
        e.source_classifications={(who,self.t.payment_instrument_id):why}
        r=e.evaluate(self.t)
        self.assertEqual(r['why_id'],why)
        self.assertEqual(r['category_id'],e.c.whys[why].accounting_classification_id)
        self.assertEqual(r['beneficiary_id'],r['payer_id'])

    def test_global_profile_cannot_supply_purpose_without_exact_pair(self):
        e=self.probe()
        e.photos=[(NS(id=999,user_title='old',title='old'),NS(id=999),dict(who=next(iter(e.c.whos.values())),branches=[dict(whom_id=999)]))]
        with patch.object(E.flow,'choose',side_effect=AssertionError('WHO-only profile used')):
            r=e.evaluate(self.t)
        self.assertIsNone(r['why_id'])
        self.assertEqual(r['beneficiary_id'],r['payer_id'])

    def test_all_matches_bypass_text_and_profiles(self):
        e = copy.copy(self.e)
        e.recogniser = NS(recognise=lambda *a, **kw: self.fail("text must not reclassify a matched transfer"))
        kinds = set()
        for tid, mt in e.matches.items():
            t = e.by_id[tid]
            if e.bank_decision(t)["source"] == "HUMAN":
                continue
            r = e.evaluate(t)
            kinds.add(mt.kind)
            self.assertEqual(r["who_method"], E.CONTEXT)
            self.assertEqual(r["beneficiary_id"], r["payer_id"])
            self.assertEqual(r["why_method"], E.CONTEXT if r["why_id"] else None)
        self.assertIn("CARD_SETTLEMENT", kinds)

    def test_policy_invalidates_old_run_and_signatures_agree(self):
        self.assertEqual(service.bank_signature(self.e), service.current_bank_signature())
        self.assertIn(service.RECONCILIATION_POLICY, service.bank_signature(self.e))

    def test_full_history_uses_only_allowed_methods_without_ai_calls(self):
        allowed = {None, E.HUMAN_BANK, E.CONTEXT, E.RULE, E.PROFILE, E.NAME_ALIAS, E.WHY_RULE,
                   E.ACCOUNT, E.WHO_CLASSIFICATION, "WHO + SOURCE (completing a human decision)", "PROFILE (completing a human decision)", "RULE (completing a human decision)",
                   "WHY RULE (completing a human decision)"}
        with patch.object(legacy, "generate_json", side_effect=AssertionError("AI called")):
            for t in self.e.txns:
                r = self.e.evaluate(t)
                for field in ("who_method", "why_method", "beneficiary_method"):
                    self.assertIn(r[field], allowed, (t.id, field))
                if r["bank"]["source"] == "HUMAN" and r["bank"]["who_id"]:
                    self.assertEqual(r["protected"], E.HUMAN_BANK)
                    if r["bank"]["why_id"]:
                        self.assertEqual(r["why_id"], r["bank"]["why_id"])

if __name__ == "__main__":
    unittest.main()
