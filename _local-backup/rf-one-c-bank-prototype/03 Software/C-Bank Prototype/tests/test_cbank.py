"""Focused tests on the real operational Bank, read-only (spec §5 acceptance).

Run (standard library only, nothing installed in the Bank environment):
  <Bank venv python> -I -m unittest discover -s "03 Software/C-Bank Prototype/tests" -v
Each test opens the Bank database read-only and an in-memory experimental store.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

    def test_store_is_separate_from_bank(self):
        self.assertNotEqual(config.STORE_DB.parent, config.BANK_DB.parent)
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
            self.assertEqual(r["why_id"], r["bank"]["why_id"])

    def test_cbank_human_decision_wins_and_is_traced(self):
        e, con = env()
        t = next(x for x in e.txns if not e.bank_decision(x)["who_id"])
        why = next(iter(e.c.whys))
        store.save_human_decision(con, t.id, who_name="TEST WHO", beneficiary_id=None, why_id=why,
                                  category_id=None, note="test")
        r = eng_mod.Engine(e.db, con, e.c).evaluate(t)
        self.assertEqual(r["protected"], eng_mod.HUMAN_CBANK)
        self.assertEqual((r["who_name"], r["why_id"]), ("TEST WHO", why))
        self.assertTrue(any(s["stage"] == "Protection" for s in r["trace"]))
        con.execute("update human_decisions set active=0")

    def test_beneficiary_comes_from_profile_branch_not_account(self):
        """TABLE TOP LINEN profile: the RF MOUNT DORA branch → RFMD, whatever account pays."""
        e, _ = env()
        rfmd = next(i for i, x in e.c.entities.items() if x.code == "RE_RFMD_LLC")
        rows = [t for t in e.txns if "TABLE TOP LINEN" in (t.description_original or "").upper()
                and "IND NAME:RF MOUNT DORA" in (t.description_original or "").upper()]
        checked = 0
        for t in rows:
            r = e.evaluate(t)
            if r["protected"]:
                continue
            self.assertEqual(r["beneficiary_id"], rfmd)
            self.assertEqual(r["beneficiary_method"], eng_mod.PROFILE)
            checked += 1
        if not checked:
            self.skipTest("no unprotected TABLE TOP LINEN RF MOUNT DORA movement")

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


class PriorApprovalTests(unittest.TestCase):
    """Decision 59 on an isolated in-memory store (never the real experimental store)."""

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
        self.assertTrue(first["note"].startswith("Decision 59"))
        if by_id[chosen[0]]["payer_id"] == priors[chosen[0]]["beneficiary_id"]:
            self.assertIsNone(first["beneficiary_id"], "account-owner beneficiary is not stored (no propagation)")
        if len(chosen) > 1:
            self.assertEqual(human[chosen[1]]["why_id"], corrected_why)
        service.reevaluate(con, run_id, set(chosen))
        after = {r["txn_id"]: r for r in store.results(con, run_id)}
        for tid in chosen:
            self.assertEqual(after[tid]["protected"], eng_mod.HUMAN_CBANK)
        untouched = [t for t in open_ids if t not in chosen]
        for tid in untouched:
            self.assertNotEqual(after[tid]["protected"], eng_mod.HUMAN_CBANK, "unselected rows are not approved")
            self.assertEqual(after[tid]["status"], by_id[tid]["status"],
                             "an approval never spreads to other movements of the same WHO")


if __name__ == "__main__":
    unittest.main()
