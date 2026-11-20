"""Focused tests on the real operational Bank, read-only (spec §5 acceptance).

Run (standard library only, nothing installed in the Bank environment):
  <Bank venv python> -I -m unittest discover -s "03 Software/C-Bank Prototype/tests" -v
Each test opens the Bank database read-only and an in-memory experimental store.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated  # noqa: E402,F401 — a copy of the Bank database, never the real one

from cbank import config, engine as eng_mod, legacy, matching, store  # noqa: E402

_ENV = {}


def env():
    if not _ENV:
        con = store.connect(":memory:")
        _ENV["e"], _ENV["con"] = eng_mod.Engine(legacy.session(), con), con
    return _ENV["e"], _ENV["con"]


class CBankTests(unittest.TestCase):
    def test_bank_database_is_read_only(self):
        from sqlalchemy import text
        db = legacy.session()
        with self.assertRaises(Exception):
            db.execute(text("create table cbank_should_fail(x integer)"))

    def test_engine_records_live_in_the_bank_database(self):
        """Phase 3A (supersedes the separate store): one database; the engine still READS it read-only."""
        self.assertEqual(config.STORE_DB, config.BANK_DB)
        self.assertNotIn("OneDrive", str(config.STORE_DB))

    def test_reference_extraction(self):
        self.assertEqual(matching.referenced_last_four("Online Transfer from CHK ...3376 transaction#: 1"), {"3376"})
        self.assertEqual(matching.referenced_last_four("Payment to Chase card ending in 1562 09/28"), {"1562"})

    def test_transfer_legs_are_paired_both_ways(self):
        e, _ = env()
        self.assertTrue(e.matches)
        for tid, mt in e.matches.items():
            self.assertEqual(e.matches[mt.counterpart_id].counterpart_id, tid)
            self.assertEqual(e.by_id[tid].amount_minor, -e.by_id[mt.counterpart_id].amount_minor)

    def test_human_bank_decision_is_never_replaced(self):
        e, _ = env()
        human = [t for t in e.txns if e.bank_decision(t)["source"] == "HUMAN" and e.bank_decision(t)["who_id"]][:60]
        self.assertTrue(human)
        for t in human:
            r = e.evaluate(t)
            self.assertEqual(r["protected"], eng_mod.HUMAN_BANK)
            self.assertEqual(legacy.clean(r["who_name"]), legacy.clean(r["bank"]["who"]))
            if r["bank"]["why_id"] is not None:
                self.assertEqual(r["why_id"], r["bank"]["why_id"], "a confirmed human WHY is never replaced")
            elif r["why_id"] is not None:
                # Only a MISSING WHY may be completed, from an approved source, with its provenance kept.
                self.assertIn("completing a human decision", r["why_method"])
                self.assertNotEqual(r["why_method"], eng_mod.HUMAN_BANK)

    def test_human_decision_from_cbank_is_a_bank_decision_and_wins(self):
        """Phase 3A: a person's decision goes through Bank's manual service and is protected as HUMAN (Bank)."""
        e, con = env()
        t = next(x for x in e.txns if not e.bank_decision(x)["who_id"])
        why = next(w for w, row in e.c.whys.items() if row.accounting_classification_id and w not in e.provisional)
        store.save_human_decision(con, t.id, who_name="TEST WHO", beneficiary_id=None, why_id=why,
                                  category_id=None, note="test")
        fresh = eng_mod.Engine(legacy.session(), con)
        r = fresh.evaluate(fresh.by_id[t.id])
        self.assertEqual(r["protected"], eng_mod.HUMAN_BANK)
        self.assertEqual((r["who_name"], r["why_id"]), ("TEST WHO", why))
        self.assertTrue(any(s["stage"] == "Protection" for s in r["trace"]))
        self.assertIn(t.id, store.human_decisions(con))

    def test_whom_always_comes_from_source(self):
        e, _ = env()
        for t in e.txns:
            r = e.evaluate(t)
            self.assertEqual(r["beneficiary_id"], r["payer_id"])

    def test_every_result_has_a_trace_and_valid_status(self):
        e, _ = env()
        for t in e.txns[:300]:
            r = e.evaluate(t)
            self.assertIn(r["status"], (eng_mod.RECONCILED, eng_mod.EXCEPTION))
            self.assertEqual(r["trace"][0]["stage"], "Source")
            if r["status"] == eng_mod.RECONCILED:
                self.assertTrue(all([r["who_name"], r["why_id"], r["category_id"], r["beneficiary_id"], r["operation_type"]]))
            else:
                self.assertTrue(r["exceptions"])


class DirectionAndKnowledgeTests(unittest.TestCase):
    """E1 (income vs cost), knowledge reuse provenance, independent AI fields."""

    def _automatic(self, e, pred):
        for t in e.txns:
            r = e.evaluate(t)
            if not r["protected"] and pred(t, r):
                yield t, r

    def test_income_on_personal_account_is_not_a_business_cost(self):
        e, _ = env()
        personal = e._personal_entity()
        rows = list(self._automatic(e, lambda t, r: r["payer_id"] == personal and t.amount_minor > 0
                                    and e._is_income(e.c.classes.get(r["category_id"]))))
        if not rows:
            self.skipTest("no automatic income on a personal account")
        for t, r in rows:
            self.assertNotIn("PERSONAL_SOURCE_BUSINESS_WHAT", [x["code"] for x in r["exceptions"]])
            self.assertEqual(r["subject_id"], personal)
            self.assertEqual(r["operation_type"], eng_mod.OPERATING_INCOME)

    def test_income_category_on_money_out_is_a_direction_conflict(self):
        e, _ = env()
        rows = list(self._automatic(e, lambda t, r: t.amount_minor < 0 and not r["match"]
                                    and e._is_income(e.c.classes.get(r["category_id"]))))
        if not rows:
            self.skipTest("no automatic income category on money out")
        for t, r in rows:
            self.assertIn("DIRECTION_CONFLICT", [x["code"] for x in r["exceptions"]])
            self.assertEqual(r["status"], eng_mod.EXCEPTION)

    def test_why_precedents_only_from_humans_or_approved_future_rules(self):
        e, _ = env()
        for t in e.txns:
            for p in e.memory.get(legacy.history_key(t.description_original), []):
                if p.get("rule"):
                    self.assertIn(p["txn_id"], e.approved_rule_decisions)
                    self.assertIn("apply to future", p["origin"])
                    self.assertIsNone(p["beneficiary_id"], "beneficiary precedents stay human-only")
                    self.assertFalse(e._is_codex(e.by_id[p["txn_id"]]), "Codex sessions are never precedents")
                else:
                    self.assertIn(p["origin"], (eng_mod.HUMAN_BANK, eng_mod.HUMAN_CBANK))

    def test_saved_ai_cannot_complete_an_automatic_decision(self):
        e, _ = env()
        t, before = next(self._automatic(e, lambda t, r: any(x["code"] == "WHO_SOURCE_CLASSIFICATION_MISSING" for x in r["exceptions"])
                                       and r["payer_id"] and not r["match"]))
        why = next(w for w, row in e.c.whys.items() if row.accounting_classification_id)
        saved = e.ai_answers.get(t.id)
        try:
            e.ai_answers[t.id] = dict(why_id=why, beneficiary_id=before["payer_id"], sufficient=True,
                                     confidence=1, investigation_id=0)
            self.assertEqual(before, e.evaluate(t))
            self.assertIsNone(before["why_id"])
        finally:
            if saved is None:
                e.ai_answers.pop(t.id, None)
            else:
                e.ai_answers[t.id] = saved


def _bank_copy_with_prior_classifications() -> Path:
    """An isolated Bank copy where the September MERCHANT BANKCD movements carry a previous, NON-human
    Bank classification — the situation Decision 59 recovers. The live Bank no longer has any (its WHYs
    were cleared when the USAR catalog replaced the old one, 2026-10-21), so the test builds it."""
    import sqlite3
    import tempfile
    path = Path(tempfile.mkdtemp(prefix="cbank_d59_")) / "bank.db"
    with sqlite3.connect(f"file:{config.BANK_DB.as_posix()}?mode=ro", uri=True) as a, sqlite3.connect(path) as b:
        a.backup(b)
    c = sqlite3.connect(path)
    why = dict(c.execute("select code, id from bank_transaction_reasons where status='ACTIVE'"))
    rows = c.execute("""select t.id, t.amount_minor, e.id from financial_transactions t
                        join bank_transaction_explanations e on e.id=t.explanation_id
                        where upper(t.description_original) like '%MERCHANT BANKCD%' and t.posting_date like '2026-09%'
                        and e.decision_source <> 'HUMAN' and e.occurrence_id is not null""").fetchall()
    for _tid, amount, eid in rows:
        code = "MERCHANT_CARD_SETTLEMENT" if amount > 0 else "MERCHANT_PROCESSING_FEE"
        c.execute("update bank_transaction_explanations set transaction_reason_id=? where id=?", (why[code], eid))
    c.commit()
    c.close()
    return path


class PriorApprovalTests(unittest.TestCase):
    """Decision 59 on an isolated in-memory store and an isolated Bank copy (never the real ones)."""

    def setUp(self):
        self._bank = config.BANK_DB
        config.BANK_DB = _bank_copy_with_prior_classifications()
        legacy._Session = None

    def tearDown(self):
        config.BANK_DB = self._bank
        legacy._Session = None

    def test_recover_group_approve_and_reevaluate(self):
        from cbank import prior, service
        con = store.connect(":memory:")
        e = eng_mod.Engine(legacy.session(), con)
        sample = [t for t in e.txns if "MERCHANT BANKCD" in (t.description_original or "").upper()
                  and str(t.posting_date).startswith("2026-09")]
        results = [e.evaluate(t) for t in sample]
        run_id = store.save_run(con, "test", {}, results, eng_mod.summarize(results))
        open_ids = [r["txn_id"] for r in results if r["status"] != eng_mod.RECONCILED]
        self.assertTrue(open_ids)
        priors = prior.recover(e.db, e.c, results, {})
        self.assertTrue(priors, "previous Bank classifications recovered")
        self.assertTrue(all(p["origin"] != "human" for p in priors.values()))
        groups = prior.groups(priors)
        keys = [g["key"] for g in groups]
        self.assertEqual(len(keys), len(set(keys)), "incompatible classifications in separate groups")
        g = max(groups, key=lambda x: len(x["txn_ids"]))
        chosen = g["txn_ids"][:2]
        by_id = {r["txn_id"]: r for r in results}
        corrected_why = next(w for w in e.c.whys if w != g["why_id"] and e.c.whys[w].accounting_classification_id)
        out = prior.approve(con, run_id, chosen[:1], priors=priors, results=by_id, catalog=e.c)
        out2 = prior.approve(con, run_id, chosen[1:] + chosen[:1], priors=priors, results=by_id,
                             corrections={"why_id": corrected_why}, catalog=e.c)
        self.assertEqual([s["id"] for s in out["saved"]], chosen[:1])
        self.assertIn(chosen[0], [s["id"] for s in out2["skipped"]], "an existing human decision is never overwritten")
        human = store.human_decisions(con)
        first = human[chosen[0]]
        self.assertIn("Decision 59", first["note"])
        self.assertIsNone(first["beneficiary_id"], "decision 86: no destination is stored with the decision")
        if len(chosen) > 1:
            self.assertEqual(human[chosen[1]]["why_id"], corrected_why)
        service.reevaluate(con, run_id, set(chosen))
        after = {r["txn_id"]: r for r in store.results(con, run_id)}
        for tid in chosen:
            self.assertEqual(after[tid]["protected"], eng_mod.HUMAN_BANK)
        untouched = [t for t in open_ids if t not in chosen]
        for tid in untouched:
            self.assertNotEqual(after[tid]["protected"], eng_mod.HUMAN_BANK, "unselected rows are not approved")
            self.assertEqual(after[tid]["status"], by_id[tid]["status"],
                             "an approval never spreads to other movements of the same WHO")


if __name__ == "__main__":
    unittest.main()
