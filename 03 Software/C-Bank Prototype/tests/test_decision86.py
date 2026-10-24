"""Decision 86 — the Source decides the accounting subject (real Bank, read-only; in-memory store).

Personal Source → personal accounting; RFWP / RFMD / RFCO Source → that LLC. WHO, WHY, Recognition Profile,
Label or AI may give a management destination, never another accounting subject. A destination is
signalled, never posted to another entity and never a balance by itself; balances come only from
documented transfers.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbank import engine as eng_mod, export, legacy, store  # noqa: E402

_ENV = {}


def env():
    if not _ENV:
        e = eng_mod.Engine(legacy.session(), store.connect(":memory:"))
        _ENV["e"], _ENV["results"] = e, [e.evaluate(t) for t in e.txns]
    return _ENV["e"], _ENV["results"]


class Decision86Tests(unittest.TestCase):
    def _entity(self, code):
        e, _ = env()
        return next((i for i, x in e.c.entities.items() if x.code == code), None)

    def test_every_movement_is_accounted_to_its_source_owner(self):
        _, results = env()
        for r in results:
            self.assertEqual(r["subject_id"], r["payer_id"])

    def _source_case(self, code):
        e, results = env()
        entity = self._entity(code) if code else e._personal_entity()
        rows = [r for r in results if r["payer_id"] == entity]
        if not rows:
            self.skipTest(f"no movement on a {code or 'personal'} Source")
        self.assertTrue(all(r["subject_id"] == entity for r in rows))
        other = [r for r in rows if r["beneficiary_id"] not in (None, entity)]
        for r in other:
            self.assertIsNotNone(r["management"], "another destination is recorded as management only")
            if r["ledger"]:
                self.assertEqual(r["ledger"]["kind"], "TRANSFER", "only documented transfers make a ledger entry")
        return rows

    def test_personal_source_is_personal_accounting(self):
        rows = self._source_case(None)
        for r in rows:
            if r["management"] and not r["protected"]:
                self.assertIn("PROMISCUOUS_USE", [a["code"] for a in r["anomalies"]], "signalled, not transferred")

    def test_rfwp_source_is_rfwp_accounting(self):
        self._source_case("RE_RFWP")

    def test_rfmd_source_is_rfmd_accounting(self):
        self._source_case("RE_RFMD_LLC")

    def test_rfco_source_is_rfco_accounting_including_amazon(self):
        rows = self._source_case("RE_RFCO")
        rfco = self._entity("RE_RFCO")
        amazon = [r for r in rows if "AMAZON" in r["description"].upper()]
        self.assertTrue(all(r["subject_id"] == rfco for r in amazon), "Amazon Business on RFCO stays in RFCO")

    def test_export_attributes_by_subject_and_destinations_make_no_balance(self):
        e, results = env()
        for entity_id in {r["subject_id"] for r in results if r["subject_id"]}:
            mine = [r for r in results if export.subject_id(r) == entity_id]
            self.assertTrue(all(r["payer_id"] == entity_id for r in mine))
        destinations_only = [r for r in results if r["management"] and not r["ledger"]]
        self.assertEqual(export.balances(destinations_only), {})

    def test_business_what_on_a_personal_source_is_never_moved_to_an_llc(self):
        e, results = env()
        personal = e._personal_entity()
        rows = [r for r in results if r["payer_id"] == personal
                and "PERSONAL_SOURCE_BUSINESS_WHAT" in [x["code"] for x in r["exceptions"] + r["anomalies"]]]
        for r in rows:
            self.assertEqual(r["subject_id"], personal)
            if not r["protected"]:
                self.assertEqual(r["status"], eng_mod.EXCEPTION)


if __name__ == "__main__":
    unittest.main()
