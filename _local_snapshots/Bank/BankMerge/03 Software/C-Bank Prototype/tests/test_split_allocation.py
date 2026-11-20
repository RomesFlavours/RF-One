"""BANK_SPLIT_ALLOCATION_001 on an isolated, migrated copy of the Bank database: one bank movement, several
classification lines (QuickBooks Online Split), Amazon order evidence, QBO preview, data preservation.
Everything written here (Amazon artifacts, rules, modes, allocations, QBO maps/exports, descriptions) is on the
copy and removed afterwards."""
import json, re, sys, unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import delete, func, select
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated
from cbank import engine as E, legacy
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import qbo_export as Q, split_allocation as S, who_why_rules as W

AMAZON = 121
REAL_CSV = Path(r"C:\Users\servi\Downloads\orders_from_20260101_to_20261026_20261026_1345 (1).csv")


def snapshot(db):
    """What must be preserved: movements, decisions, rules, WHO + Source classifications, allocations."""
    return dict(
        movements=sorted(db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.amount_minor,
                                           m.FinancialTransaction.explanation_id)).all()),
        explanations=db.scalar(select(func.count()).select_from(m.BankTransactionExplanation)),
        rules=sorted(db.execute(select(m.BankAiRule.id, m.BankAiRule.status)).all()),
        pairs=sorted(db.execute(select(m.BankWhoSourceClassification.occurrence_id, m.BankWhoSourceClassification.payment_instrument_id,
                                       m.BankWhoSourceClassification.transaction_reason_id)).all()),
        allocations=sorted(db.execute(select(m.BankTransactionAllocation.financial_transaction_id, m.BankTransactionAllocation.amount_minor,
                                             m.BankTransactionAllocation.transaction_reason_id)).all()))


def row(code, order, total, pay, title, n, **extra):
    fields = {"Order Date": pay, "Order ID": order, "Currency": "USD", "Order Net Total": total, "Payment Date": pay,
              "Charge Identifier": code, "ASIN": f"B0{n:04d}", "Title": title, "Family": extra.get("family", "Family"),
              "Class": "Class", "Commodity": "Commodity", "Amazon-Internal Product Category": "Kitchen", "Item Quantity": "1"}
    return dict(line=n, charge=code, fields=fields)


def fake(tid, desc, amount, day):
    return SimpleNamespace(id=tid, description_original=desc, amount_minor=amount, transaction_date=day, posting_date=day,
                           payment_instrument_id=None, accounting_status="CANONICAL", duplicate_status=None)


class PureSplitTests(unittest.TestCase):
    """The split rules, without the database."""

    def test_three_identical_fans_are_three_rows_and_one_total(self):
        rows = [row("FAN1", "111-7130700-7696250", "286.23", "06/27/2026", "62 Inch Ceiling Fan", n) for n in (2, 3, 4)]
        charges = S.charges_from_groups({"FAN1": rows})
        self.assertEqual(len(charges["FAN1"].rows), 3)                 # identical rows are not de-duplicated
        self.assertEqual(charges["FAN1"].expected_minor, 28623)        # the order total, read once — not 3 × 286.23
        ev = S.AmazonEvidence(charges, [fake(1, "AMAZON MKTPL*FAN1", -28623, date(2026, 6, 27))], item_whys={"FAN1": [(7, "t")] * 3})
        p = ev.proposal(ev.txns[1])
        self.assertTrue(p.complete)
        self.assertEqual([(ln.amount_minor, len(ln.items)) for ln in p.lines], [(-28623, 3)])
        self.assertEqual(p.difference_minor, 0)

    @unittest.skipUnless(REAL_CSV.exists(), "real Amazon report not on this PC")
    def test_real_report_fans_and_order_totals(self):
        sys.path.insert(0, str(Path(_isolated._bank_code) / "03 Software" / "RF-One Web"))
        import bank_amazon
        report = bank_amazon.parse_report(REAL_CSV.read_bytes())
        self.assertEqual(len(report["rows"]), 118)
        charges = S.charges_from_groups(S.groups_from_report(report, file_name=REAL_CSV.name))
        fans = charges["3819W4QQ3"]
        self.assertEqual((len(fans.rows), fans.expected_minor), (3, 28623))
        self.assertFalse([c for c in charges.values() if c.problems])  # Order Net Total constant within each order
        self.assertEqual(sum(len(c.rows) for c in charges.values()) + report["without_code"], 118)

    def test_same_classification_one_line(self):
        p = S.build(-3000, [S.Item({"title": "Gloves"}, 5), S.Item({"title": "Napkins"}, 5)])
        self.assertTrue(p.complete)
        self.assertEqual([(ln.amount_minor, ln.why_id, len(ln.items)) for ln in p.lines], [(-3000, 5, 2)])

    def test_mixed_with_amounts_and_tax_is_exact(self):
        items = [S.Item({"title": "Containers"}, 1, amount_minor=1000), S.Item({"title": "Lids"}, 1, amount_minor=333),
                 S.Item({"title": "Phone case"}, 2, amount_minor=1800)]
        p = S.build(-3330, items, ancillary=dict(kind="TAX", amount_minor=197))
        self.assertTrue(p.complete, p.reasons)
        self.assertEqual(len(p.lines), 2)
        self.assertEqual(sum(ln.amount_minor for ln in p.lines), -3330)
        self.assertEqual(sum(ln.ancillary_minor for ln in p.lines), -197)   # tax apportioned, last line takes the cent
        self.assertEqual([ln.amount_minor - ln.ancillary_minor for ln in p.lines], [-1333, -1800])

    def test_mixed_without_detail_prices_stays_incomplete(self):
        p = S.build(-3000, [S.Item({"title": "Containers"}, 1), S.Item({"title": "Phone case"}, 2)])
        self.assertFalse(p.complete)
        self.assertEqual([r["label"] for r in p.reasons], ["Importi di dettaglio mancanti"])
        self.assertEqual([ln.amount_minor for ln in p.lines], [None, None])   # never equal parts, never the majority

    def test_unexplained_difference_and_rounding(self):
        items = [S.Item({"title": "a"}, 1, amount_minor=1000), S.Item({"title": "b"}, 2, amount_minor=1000)]
        p = S.build(-2001, items)
        self.assertEqual([r["code"] for r in p.reasons], [S.DIFFERENCE_UNEXPLAINED])
        self.assertEqual(p.difference_minor, -1)                       # shown, not absorbed
        self.assertEqual(S.money_minor("0.10") + S.money_minor("0.20"), 30)
        with self.assertRaises(ValueError):
            S.money_minor("1.005")

    def test_discordant_code_refund_partial_and_aggregated_charges(self):
        rows = [row("AAA1", "O-1", "10.00", "05/01/2026", "Gloves", 2), row("BBB2", "O-2", "20.00", "05/01/2026", "Lids", 3),
                row("CCC3", "O-3", "15.00", "05/01/2026", "Mixed A", 4), row("CCC3", "O-3", "15.00", "05/01/2026", "Mixed B", 5),
                row("DDD4", "O-4", "30.00", "05/01/2026", "Split order", 6), row("EEE5", "O-4", "30.00", "05/02/2026", "Split order 2", 7),
                row("FFF6", "O-6", "12.00", "05/01/2026", "Late", 8), row("GGG7", "O-7", "10.00", "05/01/2026", "Gloves 2", 9)]
        groups = {}
        for r in rows:
            groups.setdefault(r["charge"], []).append(r)
        txns = [fake(1, "AMAZON MKTPL*ZZZ9", -1000, date(2026, 5, 1)),          # amount/date of GGG7, other code
                fake(2, "AMAZON MKTPL*AAA1 BBB2", -3000, date(2026, 5, 2)),     # two charges in one movement
                fake(3, "AMAZON REFUND CCC3", 700, date(2026, 5, 3)),           # partial refund of a mixed order
                fake(4, "AMAZON MKTPL*DDD4", -3000, date(2026, 5, 1)),          # order spread over two charges
                fake(5, "AMAZON MKTPL*FFF6", -1200, date(2026, 6, 30))]         # right code, date far away
        ev = S.AmazonEvidence(S.charges_from_groups(groups), txns, item_whys={"CCC3": [(1, "t"), (2, "t")]})
        self.assertEqual(ev.links[1].state, S.CANDIDATE)              # a candidate is never certain
        self.assertEqual((ev.links[2].state, sorted(ev.links[2].codes)), (S.CERTAIN, ["AAA1", "BBB2"]))
        self.assertEqual(ev.links[3].state, S.CERTAIN)
        self.assertIn(S.REFUND_PARTIAL, [r["code"] for r in ev.proposal(txns[2]).reasons])
        self.assertEqual(ev.links[4].state, S.CODE_ONLY)
        self.assertIn(S.PARTIAL_CHARGE, [r["code"] for r in ev.links[4].reasons])
        self.assertEqual(ev.links[5].state, S.CODE_ONLY)
        self.assertIn(S.DATE_MISMATCH, [r["code"] for r in ev.links[5].reasons])
        # A full refund of a one-WHY order: one line, money in.
        ev2 = S.AmazonEvidence(S.charges_from_groups({"AAA1": [rows[0]]}), [fake(9, "AMAZON AAA1", 1000, date(2026, 5, 4))],
                               item_whys={"AAA1": [(1, "t")]})
        p = ev2.proposal(ev2.txns[9])
        self.assertTrue(p.complete)
        self.assertEqual([ln.amount_minor for ln in p.lines], [1000])


class SplitOnCopyTests(unittest.TestCase):
    """Engine, confirmation, QBO preview and preservation on the isolated copy."""

    @classmethod
    def setUpClass(cls):
        cls.w = legacy._writer_session()
        cls.before = snapshot(cls.w)
        cls.created_artifacts, cls.created_rules, cls.descriptions, cls.split_txns = [], [], {}, []
        e = E.Engine(legacy.session(), None)
        cls.whys = [w for w in e.c.whys if w not in e.provisional and e._why_category(w) and e.c.whys[w].status == "ACTIVE"]
        amazon = [t for t in e.txns if t.amount_minor < 0 and re.search("AMAZON|AMZN", t.description_original or "", re.I)]
        out = {t.id: e.evaluate(t) for t in amazon}
        cls.amazon = [out[t.id] for t in amazon if out[t.id]["who_id"] == AMAZON and not out[t.id]["protected"]
                      and not e.bank_decision(t)["split"]]
        cls.consumables, cls.personal = e.why_by_code["DIRECT_CONSUMABLES"], e.why_by_code["OWNER_PERSONAL_OTHER"]
        e.db.close()
        assert len(cls.amazon) >= 4, "the copy needs four Amazon movements"

    @classmethod
    def tearDownClass(cls):
        w = cls.w
        w.rollback()
        for tid in cls.split_txns:
            w.execute(delete(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id == tid))
        w.execute(delete(m.BankQboExport))
        w.execute(delete(m.BankQboAccountMap))
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

    def add_report(self, charges):
        """charges: code → (movement result, [(title, why_id)]); report and analysis on the copy."""
        rows, results, n = [], [], 2
        for code, (mv, products) in charges.items():
            t = self.w.get(m.FinancialTransaction, mv["txn_id"])
            if t.id not in self.descriptions:
                self.descriptions[t.id] = t.description_original
            t.description_original = (self.descriptions[t.id] or "") + " " + code
            day = (t.transaction_date or t.posting_date).strftime("%m/%d/%Y")
            total = f"{abs(t.amount_minor) / 100:.2f}"
            mine = []
            for title, _why in products:
                mine.append(row(code, f"T-{code}", total, day, title, n)); n += 1
            rows += mine
            results.append(dict(charge=code, status="PROPOSED", items=[
                dict(item_id=f"{code}:{i}", product=r["fields"], why_id=why, confidence="HIGH" if why else "LOW")
                for i, (r, (_t, why)) in enumerate(zip(mine, products))]))
        report = m.BankFlowArtifact(kind=W.AMAZON_REPORT, account_id=None, payload=json.dumps(dict(
            file_name="split-test.csv", sha256="split-test", columns=list(rows[0]["fields"]), rows=rows,
            charges=len(charges), without_code=0)))
        run = m.BankFlowArtifact(kind=W.AMAZON_RUN, account_id=None, payload=json.dumps(dict(status="COMPLETED", results=results)))
        self.w.add_all([report, run]); self.w.commit()
        self.created_artifacts += [report.id, run.id]

    def amazon_rule(self):
        W.set_mode(self.w, AMAZON, W.MULTIPLE, account_id=None)
        rule = W.save_rule(self.w, dict(engine="BANK_WHY_PATTERN", scope="WHO", who_ids=[AMAZON], document="amazon_order",
                                        conditions=[dict(field="direction", op="is", value="money out")]), account_id=None, active=True)
        self.w.commit()
        self.created_rules.append(rule.id)

    def test_engine_split_paths_confirmation_qbo_and_preservation(self):
        same, mixed, priced, bad = (r for r in self.amazon[:4])
        self.add_report({"TSTSPSAME1": (same, [("Nitrile gloves", self.consumables), ("Paper napkins", self.consumables)]),
                         "TSTSPMIX2": (mixed, [("Food containers", self.consumables), ("Phone case", self.personal)]),
                         "TSTSPPRC3": (priced, [("Food containers", self.consumables), ("Phone case", self.personal)])})
        self.amazon_rule()
        e = E.Engine(legacy.session(), None)
        res = e.why_resolver
        # Detail amounts from another document (the order report never has them) for the third order.
        t3 = e.by_id[priced["txn_id"]]
        part = abs(t3.amount_minor) // 3
        res.amazon.evidence.item_amounts["TSTSPPRC3"] = [part, abs(t3.amount_minor) - part]
        out = {r["txn_id"]: e.evaluate(e.by_id[r["txn_id"]]) for r in (same, mixed, priced, bad)}
        # 2. same classification: one WHY, one line.
        self.assertEqual((out[same["txn_id"]]["why_id"], out[same["txn_id"]]["why_method"]), (self.consumables, W.METHOD_RULE))
        # 4. mixed without detail prices: "Ripartizione incompleta" — "Importi di dettaglio mancanti".
        r = out[mixed["txn_id"]]
        x = next(x for x in r["exceptions"] if x["code"] == W.SPLIT_INCOMPLETE)
        self.assertIn("Importi di dettaglio mancanti", x["missing"])
        self.assertIsNone(r["why_id"])
        self.assertEqual([ln["amount_minor"] for ln in r["split"]["lines"]], [None, None])
        self.assertEqual(r["who_id"], AMAZON)                          # WHO recognised, classification incomplete
        # 3. mixed with detail amounts: resolved by the split, exact.
        r = out[priced["txn_id"]]
        self.assertTrue(r["split"]["complete"], r["split"]["reasons"])
        self.assertEqual(r["why_method"], W.METHOD_SPLIT)
        self.assertEqual(sum(ln["amount_minor"] for ln in r["split"]["lines"]), t3.amount_minor)
        self.assertFalse([x for x in r["exceptions"] if x["code"] in W.OPEN_REASONS])
        self.assertEqual(r["why"], "Ripartizione: 2 righe")
        # An Amazon movement without a report stays open: never a blanket WHY.
        self.assertIn(W.NEEDS_DOCUMENT, [x["code"] for x in out[bad["txn_id"]]["exceptions"]])
        e.db.close()

        # Confirmation by a person writes the lines as the movement's allocations, exactly.
        lines = [dict(amount_minor=ln["amount_minor"], why_id=ln["why_id"], description=ln["description"], items=ln["items"])
                 for ln in r["split"]["lines"]]
        with self.assertRaises(ValueError):                            # not balanced: refused, nothing written
            S.confirm_split(self.w, t3.id, [dict(lines[0], amount_minor=lines[0]["amount_minor"] + 1), lines[1]], account_id=None)
        self.w.rollback()
        self.assertFalse(S.existing_split(self.w, t3.id))
        self.split_txns.append(t3.id)
        written = S.confirm_split(self.w, t3.id, lines, account_id=None, evidence_kind=S.EVIDENCE_AMAZON,
                                  evidence_reference="TSTSPPRC3")
        self.w.commit()
        self.assertEqual(sum(a.amount_minor for a in written), t3.amount_minor)
        self.assertEqual(len(written), 2)
        self.assertEqual(json.loads(written[1].evidence_detail)[0]["title"], "Phone case")
        e = E.Engine(legacy.session(), None)
        r = e.evaluate(e.by_id[t3.id])
        self.assertEqual((r["split"]["origin"], r["split"]["complete"]), ("BANK", True))
        e.db.close()

        # 6. QBO preview: one Purchase, two lines, no double count; blocked until mapped; duplicate protection.
        item = Q.preview(self.w, [t3.id])["purchases"][0]
        self.assertEqual((item["line_count"], item["lines_minor"]), (2, t3.amount_minor))
        self.assertEqual({b["code"] for b in item["blockers"]}, {Q.CATEGORY_NOT_MAPPED, Q.PAYMENT_ACCOUNT_NOT_MAPPED})
        self.assertEqual(round(sum(ln["Amount"] for ln in item["payload"]["Line"]) * 100), abs(t3.amount_minor))
        self.assertEqual(round(item["payload"]["TotalAmt"] * 100), abs(t3.amount_minor))
        for a in written:
            Q.set_map(self.w, Q.CATEGORY, a.accounting_classification_id, f"Q{a.accounting_classification_id}", "Expense")
        Q.set_map(self.w, Q.PAYMENT_ACCOUNT, t3.payment_instrument_id, "Q-CARD", "Card")
        item = Q.preview(self.w, [t3.id])["purchases"][0]
        self.assertTrue(item["ready"], item["blockers"])
        self.assertEqual(item["payload"]["DocNumber"], "TSTSPPRC3")
        Q.record_export(self.w, item)
        self.w.commit()
        again = Q.preview(self.w, [t3.id])["purchases"][0]
        self.assertEqual([b["code"] for b in again["blockers"]], [Q.ALREADY_EXPORTED])
        with self.assertRaises(ValueError):
            Q.record_export(self.w, item)
        self.w.rollback()


if __name__ == "__main__":
    unittest.main()
