"""BANK_WHO_WHY_MODE_001 on an isolated, migrated copy of the Bank database: UNIQUE / MULTIPLE WHO, WHO WHY rules,
open reasons, Amazon order evidence, dining by Source owner at the date, research with the WHO fixed, preservation.
Everything written here (modes, rules, Amazon artifacts, descriptions) is on the copy and removed afterwards."""
import dataclasses, json, sqlite3, sys, tempfile, unittest
from pathlib import Path
from sqlalchemy import delete, func, select
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated
from cbank import config, engine as E, legacy, three_stages as T
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules, who_why_rules as W


def snapshot(db):
    """What must be preserved: pairs and their WHY, movement decisions, allocations, WHO catalog."""
    return dict(
        pairs=sorted(db.execute(select(m.BankWhoSourceClassification.occurrence_id, m.BankWhoSourceClassification.payment_instrument_id,
                                       m.BankWhoSourceClassification.transaction_reason_id)).all()),
        explanations=db.scalar(select(func.count()).select_from(m.BankTransactionExplanation)),
        current=sorted(db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id)).all()),
        allocations=db.scalar(select(func.count()).select_from(m.BankTransactionAllocation)),
        whos=sorted(db.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name, m.BankOccurrence.status)).all()))


class WhoWhyModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = legacy._writer_session()
        cls.created_rules, cls.created_artifacts, cls.descriptions = [], [], {}
        cls.before = snapshot(cls.w)
        cls.e = cls.engine()
        e = cls.e
        cls.whys = [w for w in e.c.whys if w not in e.provisional and e._why_category(w) and e.c.whys[w].status == "ACTIVE"]
        cls.results = {t.id: e.evaluate(t) for t in e.txns}
        cls.by_code = staticmethod(lambda code: [r for r in cls.results.values()
                                                 if any(x["code"] == code for x in r["exceptions"])])
        # A movement decided by its WHO + Source pair, and the WHO it belongs to.
        cls.paired = next(r for r in cls.results.values() if r["why_method"] == W.METHOD_PAIR and r["who_id"]
                          and r["who_id"] != 121 and not r["protected"])
        cls.pair_who, cls.pair_why = cls.paired["who_id"], cls.paired["why_id"]
        cls.alt_why = next(w for w in cls.whys if w != cls.pair_why)
        cls.third_why = next(w for w in cls.whys if w not in (cls.pair_why, cls.alt_why))
        cls.direction = "money out" if cls.paired["amount_minor"] < 0 else "money in"

    @classmethod
    def tearDownClass(cls):
        w = cls.w
        w.rollback()
        for rid in cls.created_rules:
            w.execute(delete(m.BankAiRuleVersion).where(m.BankAiRuleVersion.rule_id == rid))
            w.execute(delete(m.BankAiRule).where(m.BankAiRule.id == rid))
        w.execute(delete(m.BankWhoWhyMode))
        for aid in cls.created_artifacts:
            w.execute(delete(m.BankFlowArtifact).where(m.BankFlowArtifact.id == aid))
        for tid, text in cls.descriptions.items():
            w.get(m.FinancialTransaction, tid).description_original = text
        w.commit()
        after = snapshot(w)
        w.close()
        assert after == cls.before, "the copy was not restored"

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def engine():
        return E.Engine(legacy.session(), None)

    def mode(self, who_id, mode):
        W.set_mode(self.w, who_id, mode, account_id=None)
        self.w.commit()

    def rule(self, who_ids, conditions, *, why_id=None, document=None, active=True):
        spec = dict(engine="BANK_WHY_PATTERN", scope="WHO", who_ids=who_ids, conditions=conditions)
        spec.update(dict(why_id=why_id) if why_id else dict(document=document))
        rule = W.save_rule(self.w, spec, account_id=None, active=active)
        self.w.commit()
        self.created_rules.append(rule.id)
        return rule.id

    def drop_rules(self):
        for rid in self.created_rules:
            self.w.get(m.BankAiRule, rid).status = "INACTIVE"
        self.w.commit()

    def evaluate(self, txn_id):
        e = self.engine()
        return e, e.evaluate(e.by_id[txn_id])

    def codes(self, r):
        return [x["code"] for x in r["exceptions"]]

    def tearDown(self):
        self.drop_rules()
        self.w.execute(delete(m.BankWhoWhyMode))
        self.w.commit()

    # -- UNIQUE ------------------------------------------------------------------

    def test_unique_with_and_without_pair(self):
        _e, r = self.evaluate(self.paired["txn_id"])
        self.assertEqual((r["why_id"], r["why_method"], r["why_mode"]), (self.pair_why, W.METHOD_PAIR, W.UNIQUE))
        missing = self.by_code(W.NEEDS_PAIR)[0]
        _e, r = self.evaluate(missing["txn_id"])
        x = next(x for x in r["exceptions"] if x["code"] == W.NEEDS_PAIR)
        self.assertEqual(x["label"], "Serve una classificazione WHO + Source")
        self.assertIsNone(r["why_id"])

    def test_different_whys_on_different_sources_stay_unique(self):
        # No automatic MULTIPLE: a WHO with different WHYs per Source is resolved by each pair.
        e = self.engine()
        per_who = {}
        for (who, _src), why in e.source_classifications.items():
            if why:
                per_who.setdefault(who, set()).add(why)
        several = [w for w, s in per_who.items() if len(s) > 1]
        self.assertTrue(several)
        self.assertEqual({e.why_resolver.mode(w) for w in several}, {W.UNIQUE})
        self.assertEqual(W.modes(self.w), {})

    # -- MULTIPLE ----------------------------------------------------------------

    def test_multiple_without_rule_ignores_the_registered_pair(self):
        self.mode(self.pair_who, W.MULTIPLE)
        _e, r = self.evaluate(self.paired["txn_id"])
        self.assertIsNone(r["why_id"])
        self.assertIn(W.NEEDS_RULE, self.codes(r))
        self.assertIn("PAIR_WHY_NOT_USED_FOR_MULTIPLE_WHO", [a["code"] for a in r["anomalies"]])
        # The pair itself is preserved.
        self.assertEqual(self.w.scalar(select(m.BankWhoSourceClassification.transaction_reason_id).where(
            m.BankWhoSourceClassification.occurrence_id == self.pair_who)) is not None, True)

    def test_multiple_with_resolving_rule(self):
        self.mode(self.pair_who, W.MULTIPLE)
        rid = self.rule([self.pair_who], [dict(field="direction", op="is", value=self.direction)], why_id=self.alt_why)
        e, r = self.evaluate(self.paired["txn_id"])
        self.assertEqual((r["why_id"], r["why_method"]), (self.alt_why, W.METHOD_RULE))
        self.assertEqual(r["category_id"], e._why_category(self.alt_why))          # WHAT from the WHY
        self.assertEqual(r["beneficiary_id"], r["payer_id"])                        # WHOM from the Source
        self.assertIn(f"rule #{rid}", next(s for s in r["trace"] if s["stage"] == "Classification")["evidence"])
        # Inactive rule: no longer applies.
        self.w.get(m.BankAiRule, rid).status = "INACTIVE"; self.w.commit()
        _e, r = self.evaluate(self.paired["txn_id"])
        self.assertIn(W.NEEDS_RULE, self.codes(r))

    def test_multiple_with_conflicting_rules(self):
        self.mode(self.pair_who, W.MULTIPLE)
        cond = [dict(field="direction", op="is", value=self.direction)]
        self.rule([self.pair_who], cond, why_id=self.alt_why)
        self.rule([self.pair_who], cond, why_id=self.third_why)
        _e, r = self.evaluate(self.paired["txn_id"])
        self.assertIsNone(r["why_id"])
        x = next(x for x in r["exceptions"] if x["code"] == W.CONFLICT)
        self.assertEqual(x["label"], "Regole in conflitto")

    def test_multiple_with_missing_information(self):
        self.mode(self.pair_who, W.MULTIPLE)
        self.rule([self.pair_who], [dict(field="extra:invoice_number", op="is", value="A-1")], why_id=self.alt_why)
        _e, r = self.evaluate(self.paired["txn_id"])
        x = next(x for x in r["exceptions"] if x["code"] == W.NEEDS_DOCUMENT)
        self.assertEqual(x["label"], "Serve un documento o un chiarimento")
        self.assertTrue(x["missing"])
        self.assertIsNone(r["why_id"])

    def test_rule_validation(self):
        with self.assertRaises(ValueError):   # no condition: a generic WHY in disguise
            W.validate(self.w, dict(engine="BANK_WHY_PATTERN", scope="WHO", who_ids=[self.pair_who], conditions=[],
                                    why_id=self.alt_why))
        with self.assertRaises(ValueError):   # both a WHY and a document
            W.validate(self.w, dict(engine="BANK_WHY_PATTERN", scope="WHO", who_ids=[self.pair_who],
                                    conditions=[dict(field="direction", op="is", value="money out")],
                                    why_id=self.alt_why, document="amazon_order"))
        with self.assertRaises(ValueError):   # unknown document
            W.validate(self.w, dict(engine="BANK_WHY_PATTERN", scope="WHO", who_ids=[self.pair_who],
                                    conditions=[dict(field="direction", op="is", value="money out")], document="invoice"))
        if self.e.provisional:
            with self.assertRaises(ValueError):
                W.validate(self.w, dict(engine="BANK_WHY_PATTERN", scope="WHO", who_ids=[self.pair_who],
                                        conditions=[dict(field="direction", op="is", value="money out")],
                                        why_id=next(iter(self.e.provisional))))
        # A WHO WHY rule is not a WHO identification rule nor a global WHY pattern.
        rid = self.rule([self.pair_who], [dict(field="direction", op="is", value="money out")], why_id=self.alt_why)
        e = self.engine()
        self.assertNotIn(rid, [r.id for r, _v, _s in e.c.rules])
        from rfone_data_store.bank_reconciliation import why_patterns
        self.assertNotIn(rid, [r.id for r, _v, _s in why_patterns.active_rules(self.w)])

    # -- dining by Source owner at the movement date ------------------------------

    def test_dining_personal_company_unknown_owner(self):
        e = self.engine()
        rows = {t.id: e.c.rule_row(t) for t in e.txns if t.amount_minor < 0}
        personal = next(t for t in e.txns if t.id in rows and rows[t.id].source_class == ai_rules.SOURCE_PERSONAL)
        company = next(t for t in e.txns if t.id in rows and rows[t.id].source_class == ai_rules.SOURCE_NOT_PERSONAL)
        whys = {r.name: r.id for r in e.c.whys.values()}
        restaurant, meals = whys["Owner Personal — Restaurant"], whys["Business Meals & Entertainment"]
        dining = self.pair_who
        self.mode(dining, W.MULTIPLE)
        self.rule([dining], [dict(field="subject", op="is", value="Personal")], why_id=restaurant)
        self.rule([dining], [dict(field="subject", op="is", value="Company")], why_id=meals)
        e = self.engine()
        det = lambda t, row: e.why_resolver.determine(t, who_id=dining, who="X", pair_why=None, row=row)
        self.assertEqual(det(personal, rows[personal.id]).why_id, restaurant)
        self.assertEqual(det(company, rows[company.id]).why_id, meals)
        unknown = det(company, dataclasses.replace(rows[company.id], source_class=None))
        self.assertEqual((unknown.why_id, unknown.code), (None, W.NEEDS_DOCUMENT))
        self.assertTrue(any("Accounting subject" in x for x in unknown.missing))

    # -- Amazon ------------------------------------------------------------------

    def test_amazon_matched_discordant_mixed(self):
        amazon = [r for r in self.results.values() if r["who_id"] == 121 and r["amount_minor"] < 0 and not r["protected"]]
        self.assertGreaterEqual(len(amazon), 4)
        ok, wrong_code, mixed, unclear = (r["txn_id"] for r in amazon[:4])
        codes = {ok: "TSTAMZOK1", wrong_code: "TSTAMZXX9", mixed: "TSTAMZMIX2", unclear: "TSTAMZQ3"}
        for tid, code in codes.items():
            t = self.w.get(m.FinancialTransaction, tid)
            self.descriptions[tid] = t.description_original
            t.description_original = (t.description_original or "") + " " + code
        consumables = self.e.why_by_code["DIRECT_CONSUMABLES"]
        other = self.e.why_by_code["OWNER_PERSONAL_OTHER"]
        # BANK_SPLIT_ALLOCATION_001: a certain link needs the code AND the order total and payment date of the movement.
        txn_of = {code: self.w.get(m.FinancialTransaction, tid) for tid, code in codes.items()}
        def product(title, code):
            t = txn_of.get(code)
            total, day = (f"{abs(t.amount_minor) / 100:.2f}", (t.transaction_date or t.posting_date).strftime("%m/%d/%Y")) if t \
                else ("1.00", "05/01/2026")
            return {"Order Date": day, "Order ID": f"111-{code}", "Charge Identifier": "", "Title": title, "ASIN": "B0",
                    "Order Net Total": total, "Payment Date": day, "Currency": "USD"}
        groups = {"TSTAMZOK1": [product("Nitrile gloves 100 pcs", "TSTAMZOK1"), product("Paper napkins", "TSTAMZOK1")],
                  "TSTAMZXX8": [product("Coffee filters", "TSTAMZXX8")],          # the report's code, not the movement's
                  "TSTAMZMIX2": [product("Food containers", "TSTAMZMIX2"), product("Phone case", "TSTAMZMIX2")],
                  "TSTAMZQ3": [product("Gift card", "TSTAMZQ3")]}
        rows = [dict(line=n, charge=code, fields=dict(p, **{"Charge Identifier": code}))
                for n, (code, p) in enumerate(((c, p) for c, ps in groups.items() for p in ps), 2)]
        report = m.BankFlowArtifact(kind=W.AMAZON_REPORT, account_id=None, payload=json.dumps(dict(
            file_name="test.csv", sha256="t", columns=list(rows[0]["fields"]), rows=rows, charges=4, without_code=0)))
        answers = {"TSTAMZOK1": [(consumables, "HIGH"), (consumables, "HIGH")], "TSTAMZXX8": [(consumables, "HIGH")],
                   "TSTAMZMIX2": [(consumables, "HIGH"), (other, "HIGH")], "TSTAMZQ3": [(None, "LOW")]}
        results = [dict(charge=c, status="PROPOSED",
                        items=[dict(item_id=f"{c}:{i}", product=dict(p, **{"Charge Identifier": c}),
                                    why_id=a[0], confidence=a[1], question="Uso?" if not a[0] else "")
                               for i, (p, a) in enumerate(zip(ps, answers[c]))])
                   for c, ps in groups.items()]
        run = m.BankFlowArtifact(kind=W.AMAZON_RUN, account_id=None, payload=json.dumps(dict(status="COMPLETED", results=results)))
        self.w.add_all([report, run]); self.w.commit()
        self.created_artifacts += [report.id, run.id]
        self.mode(121, W.MULTIPLE)
        self.rule([121], [dict(field="direction", op="is", value="money out")], document="amazon_order")
        e = self.engine()
        out = {tid: e.evaluate(e.by_id[tid]) for tid in codes}
        for tid in codes:
            self.assertEqual(out[tid]["who_id"], 121, "the added code changed WHO recognition")
        self.assertEqual((out[ok]["why_id"], out[ok]["why_method"]), (consumables, W.METHOD_RULE))
        for tid, word in ((wrong_code, "no Amazon order report"), (unclear, "HIGH confidence")):
            x = next(x for x in out[tid]["exceptions"] if x["code"] == W.NEEDS_DOCUMENT)
            self.assertIsNone(out[tid]["why_id"])
            self.assertIn(word, x["message"])
        # A mixed order is a split to complete, not a missing document (BANK_SPLIT_ALLOCATION_001).
        x = next(x for x in out[mixed]["exceptions"] if x["code"] == W.SPLIT_INCOMPLETE)
        self.assertIsNone(out[mixed]["why_id"])
        self.assertIn("Importi di dettaglio mancanti", x["missing"])
        # Never a blanket WHY: an Amazon movement without a report stays open too.
        rest = next(r["txn_id"] for r in amazon[4:]) if len(amazon) > 4 else None
        if rest:
            self.assertIn(W.NEEDS_DOCUMENT, self.codes(e.evaluate(e.by_id[rest])))

    # -- research with the WHO fixed ----------------------------------------------

    def test_known_who_without_why_goes_to_research_with_who_fixed(self):
        self.mode(self.pair_who, W.MULTIPLE)
        open_pair = self.by_code(W.NEEDS_PAIR)
        unique_open = next(r["txn_id"] for r in open_pair if r["who_method"] in ("RULE", "NAME/ALIAS"))
        multiple = self.paired["txn_id"]
        e = self.engine()
        sim = T.Simulation(e)
        self.assertTrue(T.recognise(sim, e.by_id[multiple])["resolved"])
        prompts = []

        def fake(prompt, *, web_research=False):
            payload = json.loads(prompt[prompt.index("\n{") + 1:])
            prompts.append(payload)
            out = []
            for mv in payload["movements"]:
                if mv["id"] == multiple:
                    out.append(dict(id=mv["id"], outcome="WHO_IDENTIFIED", who="SOMEONE ELSE ENTIRELY", who_certainty="CERTAIN",
                                    why_id=self.alt_why, why_confidence="HIGH", sources=[dict(title="s", url="https://example.org")]))
                else:
                    out.append(dict(id=mv["id"], outcome="UNRESOLVED", missing_information=["the invoice"]))
            return dict(movements=out)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sim.json"
            s = T.run(e, path, generate=fake, ids={multiple, unique_open}, log=lambda *_: None)
            data = {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["records"]}
        sent = {mv["id"]: mv for p in prompts for mv in p["movements"]}
        self.assertEqual(sent[multiple]["recognised_who"], data[multiple]["who"])
        r = data[multiple]
        self.assertEqual(r["stage3"]["who_id"], self.pair_who)                    # the WHO is never changed
        self.assertTrue(any("ignored" in n for n in r["stage3"]["notes"]))
        self.assertEqual((r["final"]["category"], r["final"]["why_basis"]), (T.COMPLETE, T.WHY_FROM_EVIDENCE))
        r = data[unique_open]
        self.assertEqual((r["final"]["category"], r["final"]["open_reason"]), (T.WHY_OPEN, W.NEEDS_PAIR))
        self.assertTrue(s["quadrature"].endswith("✓") and s["quadrature_final"].endswith("✓"), s)
        self.assertEqual(s["total"], 2)

    # -- preservation ------------------------------------------------------------

    def test_migration_preserves_existing_data(self):
        """The migrated copy keeps exactly the operational pairs, decisions and WHO catalog."""
        op = sqlite3.connect(f"file:{_isolated._source.as_posix()}?mode=ro", uri=True) if hasattr(_isolated, "_source") else None
        if op is None:
            self.skipTest("CBANK_BANK_DB given by the caller: no operational database to compare")
        try:
            pairs = sorted(op.execute("select occurrence_id, payment_instrument_id, transaction_reason_id "
                                      "from bank_who_source_classifications").fetchall())
            whos = sorted(op.execute("select id, canonical_name, status from bank_occurrences").fetchall())
        finally:
            op.close()
        # Other test modules sharing this copy may ADD rows; every operational row must be there, unchanged.
        copy_pairs = {(w, s): y for w, s, y in self.before["pairs"]}
        self.assertEqual({(w, s): y for w, s, y in pairs}, {k: copy_pairs.get(k) for k, _y in
                                                             ((p[:2], p[2]) for p in pairs)})
        copy_whos = {i: (n, s) for i, n, s in self.before["whos"]}
        self.assertEqual({i: (n, s) for i, n, s in whos}, {i: copy_whos.get(i) for i, _n, _s in whos})
        self.assertEqual(W.modes(self.w), {})        # no WHO marked MULTIPLE by the migration


if __name__ == "__main__":
    unittest.main()
