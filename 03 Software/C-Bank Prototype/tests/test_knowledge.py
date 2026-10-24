"""Bank unification Phase 2 — knowledge in the one engine (real Bank, read-only; in-memory store).

Labels are CONTEXT: read from Bank's own catalog and links, shown, given to the AI and summarised as
a hint, never a classification and never above a Recognition Profile or an approved WHO -> WHY
association. Recognition Profiles and approved associations keep their precedence; human decisions
stay protected.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated  # noqa: E402,F401 — a copy of the Bank database, never the real one

from cbank import ai, config, engine as eng_mod, legacy, store  # noqa: E402

_ENV = {}
DECISION = ("status", "who_name", "why_id", "category_id", "beneficiary_id", "operation_type", "protected")


def env():
    if not _ENV:
        con = store.connect(":memory:")
        _ENV["e"], _ENV["con"] = eng_mod.Engine(legacy.session(), con), con
    return _ENV["e"], _ENV["con"]


def labelled(e, limit=200):
    """Movements whose automatic WHO is a known WHO that has Labels."""
    out = []
    for t in e.txns:
        r = e.evaluate(t)
        if r["who_id"] and r["who_labels"]:
            out.append((t, r))
            if len(out) >= limit:
                break
    return out


class KnowledgeTests(unittest.TestCase):
    def test_labels_are_read_from_bank_without_a_copy(self):
        e, _ = env()
        self.assertTrue(e.who_labels, "the Bank has labelled WHOs")
        self.assertEqual(e.who_labels, legacy.who_identification.labels_of(e.db, e.c.whos.keys()))
        for names in e.who_labels.values():
            self.assertTrue(all(n in e.label_definitions for n in names))

    def test_labels_are_shown_as_context_on_the_movement(self):
        e, _ = env()
        rows = labelled(e, 30)
        self.assertTrue(rows)
        for _, r in rows:
            step = next(s for s in r["trace"] if s["stage"] == "Labels")
            self.assertEqual(step["method"], eng_mod.CONTEXT)
            self.assertIn("never a classification", step["evidence"])

    def test_labels_never_change_a_decision(self):
        e, con = env()
        rows = labelled(e, 150)
        bare = eng_mod.Engine(e.db, con, e.c)
        bare.who_labels, bare.label_members = {}, {}
        for t, r in rows:
            plain = bare.evaluate(t)
            self.assertEqual({k: r[k] for k in DECISION}, {k: plain[k] for k in DECISION})
            self.assertEqual([x["code"] for x in r["exceptions"]], [x["code"] for x in plain["exceptions"]])

    def test_label_hint_excludes_the_who_itself_and_never_decides(self):
        e, _ = env()
        hinted = []
        for t in e.txns:
            r = e.evaluate(t)
            if r["label_hints"] and any(x["code"] == "NO_PROFILE" for x in r["exceptions"]):
                hinted.append(r)
                if len(hinted) >= 10:
                    break
        self.assertTrue(hinted, "some open movements carry a Label hint")
        for r in hinted:
            self.assertIsNone(r["why_id"], "a hint never fills the WHY")
            self.assertEqual(r["status"], eng_mod.EXCEPTION)
            for h in r["label_hints"]:
                members = e.label_members[h["label"]] - {r["who_id"]}
                self.assertLessEqual(h["of"], len(members))

    def test_ai_investigation_receives_the_labels(self):
        e, _ = env()
        _, r = labelled(e, 1)[0]
        evidence = ai._evidence(e, [r])
        item = next(x for x in evidence if x["kind"].startswith("WHO Labels"))
        self.assertEqual([x["name"] for x in item["labels"]], r["who_labels"])
        self.assertIn("WHO Labels are evidence, not proof", ai.INSTRUCTIONS)

    def test_profile_prevails_over_an_approved_association(self):
        e, con = env()
        t, r = next((t, r) for t in e.txns for r in [e.evaluate(t)]
                    if r["why_method"] == eng_mod.PROFILE and r["who_id"] and not r["protected"])
        other = next(w for w in e.c.whys if w != r["why_id"] and e.c.whys[w].accounting_classification_id)
        with mock.patch.object(config, "WHO_WHY_KNOWLEDGE", True):
            probe = eng_mod.Engine(e.db, con, e.c)
            probe.who_whys_approved[r["who_id"]] = [other]
            again = probe.evaluate(t)
        self.assertEqual(again["why_id"], r["why_id"], "the Recognition Profile keeps its WHY")
        self.assertIn("PROFILE_VS_APPROVED_WHY", [a["code"] for a in again["anomalies"]])

    def test_approved_association_decides_only_without_profile(self):
        e, con = env()
        with mock.patch.object(config, "WHO_WHY_KNOWLEDGE", True):
            probe = eng_mod.Engine(e.db, con, e.c)
            decided = [r for t in probe.txns[:1500] for r in [probe.evaluate(t)]
                       if r["why_method"] == eng_mod.RULE and any(
                           "approved WHO→WHY association" in (s["evidence"] or "") for s in r["trace"])]
        self.assertTrue(decided, "approved associations classify some movements")
        for r in decided:
            self.assertIn(r["why_id"], probe.who_whys_approved[r["who_id"]])
            self.assertFalse(any(s["stage"] == "Profile" and s["method"] == eng_mod.PROFILE for s in r["trace"]))

    def test_provisional_why_is_kept_and_never_reconciled(self):
        """Decisions 74-76, 79: a provisional WHY keeps the movement an Exception, and stays visible."""
        e, con = env()
        t, r = next((t, r) for t in e.txns for r in [e.evaluate(t)]
                    if r["status"] == eng_mod.RECONCILED and r["why_id"] and not r["protected"])
        probe = eng_mod.Engine(e.db, con, e.c)
        probe.provisional = {r["why_id"]}
        again = probe.evaluate(t)
        self.assertEqual(again["why_id"], r["why_id"], "the provisional WHY is not lost")
        self.assertEqual(again["status"], eng_mod.EXCEPTION)
        self.assertIn("PROVISIONAL_WHY", [x["code"] for x in again["exceptions"]])
        for w in e.provisional:   # the real provisional WHYs, when the Bank has them
            self.assertIsNone(e.c.whys[w].accounting_classification_id)

    def test_human_decisions_stay_protected_with_labels(self):
        e, _ = env()
        human = [t for t in e.txns if e.bank_decision(t)["source"] == "HUMAN" and e.bank_decision(t)["who_id"]][:80]
        for t in human:
            r = e.evaluate(t)
            self.assertEqual(r["protected"], eng_mod.HUMAN_BANK)
            if r["bank"]["why_id"] is not None:
                self.assertEqual(r["why_id"], r["bank"]["why_id"])


if __name__ == "__main__":
    unittest.main()
