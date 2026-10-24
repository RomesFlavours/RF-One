"""Card payments between own instruments (CARD_SETTLEMENT_001), tests A–G and the 2500 test.

Always on ISOLATED COPIES: the Bank database is copied into a temporary folder (the
operational Bank is only read once, to make the copy) and the C-Bank store is in memory
or in that temporary folder. Cases D and E add movements to their own copy only.

Run:
  <Bank venv python> -I -m unittest discover -s "03 Software/C-Bank Prototype/tests" -p "test_card_settlement.py" -v
"""
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbank import config, engine as E, export, legacy, matching, service, store  # noqa: E402

_ORIGINAL_BANK = config.BANK_DB
_TMP = Path(tempfile.mkdtemp(prefix="cbank_card_test_"))


def _copy_bank(name: str) -> Path:
    dst = _TMP / name
    if dst.exists():
        dst.unlink()
    with sqlite3.connect(f"file:{_ORIGINAL_BANK.as_posix()}?mode=ro", uri=True) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    return dst


def _use_bank(path: Path):
    config.BANK_DB = path
    legacy._Session = None


def _add_movement(path: Path, like_id: int, *, instrument_id: int, amount_minor: int, days: int, description: str,
                  on=None) -> int:
    """A new imported movement in the COPY, cloned from an existing row, dated `on` + `days`."""
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    row = dict(c.execute("select * from financial_transactions where id=?", (like_id,)).fetchone())
    new_id = c.execute("select max(id)+1 from financial_transactions").fetchone()[0]
    from datetime import date
    day = date.fromisoformat(str(on or row["posting_date"])[:10]) + timedelta(days=days)
    row.update(id=new_id, payment_instrument_id=instrument_id, amount_minor=amount_minor, posting_date=str(day),
               transaction_date=str(day), transaction_datetime=None, description_original=description,
               description_normalized=description, external_transaction_id=f"cbank-test-{new_id}",
               explanation_id=None, fingerprint=f"cbank-test-{new_id}", duplicate_status=None,
               accounting_status="CANONICAL", accounting_canonical_transaction_id=None)
    cols = ",".join(row)
    c.execute(f"insert into financial_transactions ({cols}) values ({','.join('?' * len(row))})", list(row.values()))
    c.commit()
    c.close()
    return new_id


BASE = _copy_bank("bank_base.db")
_use_bank(BASE)
_ENV = {}


def env():
    if not _ENV:
        _ENV["e"] = E.Engine(legacy.session(), store.connect(":memory:"))
    return _ENV["e"]


def card_pairs(e, *, owners_same: bool, card_owner_type: str | None = None, card_name: str | None = None):
    """Bank-side legs of matched card settlements with the wanted owners."""
    out = []
    for tid, mt in e.matches.items():
        t = e.by_id[tid]
        if mt.kind != "CARD_SETTLEMENT" or t.amount_minor >= 0:
            continue
        payer, card_owner = e.owner(t), e.owner(e.by_id[mt.counterpart_id])
        card = e.c.instruments[mt.counterpart_instrument_id]
        if payer is None or card_owner is None or (payer.id == card_owner.id) != owners_same:
            continue
        if card_owner_type and card_owner.entity_type != card_owner_type:
            continue
        if card_name and card_name not in card.display_name:
            continue
        out.append(t)
    return out


class CardSettlementTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        _use_bank(_ORIGINAL_BANK)

    def assert_transfer_only(self, r):
        self.assertEqual(r["operation_type"], E.CARD_SETTLEMENT)
        self.assertEqual(r["why"], "Credit Card Statement Payment")
        self.assertIsNone(r["ledger"], "no receivable/payable may be created automatically")
        self.assertEqual(r["match"]["state"], "MATCHED")

    # A ---------------------------------------------------------------------------
    def test_A_own_card_is_matched_and_reconciled(self):
        e = env()
        legs = [t for t in card_pairs(e, owners_same=True, card_name="Ink RFWP")
                if "RFWP" in e.c.instruments[t.payment_instrument_id].display_name]
        self.assertTrue(legs, "no Checking RFWP -> Ink RFWP payment in the copy")
        for t in legs:
            r = e.evaluate(t)
            if r["protected"]:
                continue
            self.assert_transfer_only(r)
            self.assertEqual(r["match"]["relationship"], "SAME_OWNER")
            self.assertEqual(r["status"], E.RECONCILED)
            self.assertFalse(r["exceptions"])
            card = e.evaluate(e.by_id[r["match"]["counterpart_id"]])
            self.assert_transfer_only(card)
            self.assertEqual(card["match"]["posting"], "COUNTERPART")

    # B ---------------------------------------------------------------------------
    def test_B_personal_card_paid_by_llc_is_matched_relationship_open(self):
        e = env()
        legs = card_pairs(e, owners_same=False, card_owner_type="PERSONAL")
        self.assertTrue(legs, "no LLC -> personal card payment in the copy")
        for t in legs:
            r = e.evaluate(t)
            if r["protected"]:
                continue
            self.assert_transfer_only(r)
            self.assertEqual(r["match"]["relationship"], "TO_DECIDE")
            self.assertEqual([x["code"] for x in r["exceptions"]], ["RELATIONSHIP_TO_DECIDE"])
            self.assertIn("Rapporto economico da decidere", r["exceptions"][0]["message"])
            self.assertEqual(r["status"], E.EXCEPTION)   # not fully reconciled until the relationship is decided

    # C ---------------------------------------------------------------------------
    def test_C_llc_pays_other_llc_card_is_intercompany_flagged(self):
        e = env()
        legs = card_pairs(e, owners_same=False, card_name="Ink RFMD")
        self.assertTrue(legs, "no RFWP -> Ink RFMD payment in the copy")
        for t in legs:
            r = e.evaluate(t)
            if r["protected"]:
                continue
            self.assert_transfer_only(r)
            self.assertEqual(r["match"]["relationship"], "TO_DECIDE")
            self.assertIn("RFMD", r["exceptions"][0]["message"])

    # D ---------------------------------------------------------------------------
    def test_D_unmatched_payment_waits_then_matches_when_statement_arrives(self):
        e = env()
        waiting = [t for t in e.txns if t.id not in e.matches and "RFCO" in (e.c.instruments[t.payment_instrument_id].display_name or "")
                   and matching.is_card_payment_out(t, e.c.instruments, e.card_payment_out)]
        self.assertTrue(waiting, "no unmatched RFCO card payment in the copy")
        t = waiting[0]
        r = e.evaluate(t)
        self.assertEqual([x["code"] for x in r["exceptions"]], ["CARD_PAYMENT_UNMATCHED"])
        self.assertIsNone(r["why_id"], "never classified as an ordinary payment to the issuer")
        self.assertEqual(r["match"]["state"], "WAITING")
        # The missing statement arrives (in a copy): the next run matches it, with no manual relaunch.
        path = _copy_bank("bank_D.db")
        card = next(i for i in e.c.instruments.values() if i.display_name.startswith("Ink RFCO") and i.last_four == "3144")
        like = next(x.id for x in e.txns if x.payment_instrument_id == card.id)
        new_id = _add_movement(path, like, instrument_id=card.id, amount_minor=-t.amount_minor, days=1,
                               description="AUTOMATIC PAYMENT - THANK", on=t.posting_date)
        con = store.connect(":memory:")
        _use_bank(BASE)
        first = service.execute(con, "all")
        _use_bank(path)
        try:
            second = service.run_if_bank_changed(con)
            self.assertIsNotNone(second, "new Bank data must start a new run by itself")
            after = {r["txn_id"]: r for r in store.results(con, second)}
            self.assertEqual(after[t.id]["match"]["state"], "MATCHED")
            self.assertEqual(after[t.id]["match"]["counterpart_id"], new_id)
            summary = store.run(con, second)["summary"]
            self.assertGreaterEqual(summary["resumed_matches"], 1)
            self.assertEqual(summary["new_movements"], 1)
            self.assertIsNone(service.run_if_bank_changed(con), "no change, no new run")
        finally:
            _use_bank(BASE)
        self.assertTrue(first)

    # E ---------------------------------------------------------------------------
    def test_E_two_possible_credits_go_to_exceptions(self):
        e = env()
        legs = card_pairs(e, owners_same=True, card_name="Ink RFWP")
        t = legs[0]
        mt = e.matches[t.id]
        path = _copy_bank("bank_E.db")
        _add_movement(path, mt.counterpart_id, instrument_id=mt.counterpart_instrument_id, amount_minor=-t.amount_minor,
                      days=0, description=e.by_id[mt.counterpart_id].description_original)
        _use_bank(path)
        try:
            e2 = E.Engine(legacy.session(), store.connect(":memory:"))
            self.assertNotIn(t.id, e2.matches, "no arbitrary choice between two equal credits")
            r = e2.evaluate(e2.by_id[t.id])
            if not r["protected"]:
                self.assertEqual([x["code"] for x in r["exceptions"]], ["CARD_PAYMENT_AMBIGUOUS"])
                self.assertEqual(r["match"]["state"], "AMBIGUOUS")
                self.assertEqual(len(r["match"]["candidates"]), 2)
        finally:
            _use_bank(BASE)

    # F ---------------------------------------------------------------------------
    def test_F_repeated_runs_add_no_duplicate_matches(self):
        con = store.connect(":memory:")
        first = service.execute(con, "all")
        pairs = store.matched_pairs(con)
        second = service.execute(con, "all")
        self.assertEqual(store.matched_pairs(con) == [], False)
        self.assertEqual(len(store.matched_pairs(con)), len(pairs))
        self.assertEqual(store.run(con, second)["summary"]["new_matched_pairs"], 0)
        a = {r["txn_id"]: (r["status"], r["why_id"], (r["match"] or {}).get("counterpart_id")) for r in store.results(con, first)}
        b = {r["txn_id"]: (r["status"], r["why_id"], (r["match"] or {}).get("counterpart_id")) for r in store.results(con, second)}
        self.assertEqual(a, b)
        self.assertEqual(store.run(con, second)["summary"]["new_movements"], 0)

    # G ---------------------------------------------------------------------------
    def test_G_confirmed_human_decision_is_never_overwritten(self):
        e = env()
        t = card_pairs(e, owners_same=False, card_owner_type="PERSONAL")[0]
        con = store.connect(":memory:")
        why = next(w for w, r in e.c.whys.items() if r.code == "OWNER_PERSONAL_OTHER")
        store.save_human_decision(con, t.id, who_name="HUMAN WHO", beneficiary_id=None, why_id=why,
                                  category_id=None, note="test G")
        r = E.Engine(e.db, con, e.c).evaluate(t)
        self.assertEqual(r["protected"], E.HUMAN_CBANK)
        self.assertEqual((r["who_name"], r["why_id"]), ("HUMAN WHO", why))
        self.assertEqual(r["match"]["state"], "MATCHED", "the transfer is still identified")
        self.assertNotIn("RELATIONSHIP_TO_DECIDE", [x["code"] for x in r["exceptions"]])
        # Bank HUMAN decisions are protected too: no matched leg loses its person-made WHO/WHY.
        for tid, mt in e.matches.items():
            b = e.bank_decision(e.by_id[tid])
            if b["source"] == "HUMAN" and b["who_id"]:
                rr = e.evaluate(e.by_id[tid])
                self.assertEqual(rr["protected"], E.HUMAN_BANK)
                self.assertEqual(rr["why_id"], b["why_id"])

    # Personal expense paid by an LLC -------------------------------------------------
    def test_personal_expense_paid_by_llc_attributed_but_no_credit_created(self):
        flag = config.WHO_WHY_KNOWLEDGE
        config.WHO_WHY_KNOWLEDGE = True
        try:
            e = E.Engine(legacy.session(), store.connect(":memory:"))
            personal = e._personal_entity()
            cases = []
            for t in e.txns:
                if e.owner(t) is None or e.owner(t).id == personal:
                    continue
                r = e.evaluate(t)
                if r["ledger"] and r["ledger"]["kind"] == "PAID_FOR_OTHER" and r["beneficiary_id"] == personal:
                    cases.append(r)
                if len(cases) >= 5:
                    break
            if not cases:
                self.skipTest("no personal expense paid by an LLC in the copy")
            for r in cases:
                self.assertEqual(r["ledger"]["relationship"], "TO_DECIDE")
                self.assertEqual(r["beneficiary_id"], personal, "the economic attribution stays")
                if not r["protected"]:
                    self.assertIn("RELATIONSHIP_TO_DECIDE", [x["code"] for x in r["exceptions"]])
                    self.assertEqual(r["status"], E.EXCEPTION)
            self.assertEqual(export.balances(cases), {}, "no balance owed is created for an undecided relationship")
        finally:
            config.WHO_WHY_KNOWLEDGE = flag

    # 2500 ------------------------------------------------------------------------
    def test_2500_one_payment_is_posted_once(self):
        e = env()
        t = card_pairs(e, owners_same=True, card_name="Ink RFWP")[0]
        bank_leg = e.evaluate(t)
        card_leg = e.evaluate(e.by_id[bank_leg["match"]["counterpart_id"]])
        self.assertEqual(e.c.classes[bank_leg["category_id"]].code, "2500")
        self.assertEqual(e.c.classes[card_leg["category_id"]].code, "2500")
        self.assertEqual(e.c.classes[bank_leg["category_id"]].statement_type, "BALANCE_SHEET")  # never P&L
        # Both legs are listed (traceability) but only the bank leg is posted.
        self.assertEqual(export.posted_amount_minor(bank_leg), t.amount_minor)
        self.assertEqual(export.posted_amount_minor(card_leg), 0)
        posted_2500 = sum(export.posted_amount_minor(r) for r in (bank_leg, card_leg))
        listed_2500 = sum(r["amount_minor"] for r in (bank_leg, card_leg))
        self.assertEqual(posted_2500, t.amount_minor, "exactly one 2500 entry for one payment")
        self.assertEqual(listed_2500, 0, "listed legs cancel out: no hidden amount either")
        self.assertIsNone(bank_leg["ledger"])
        self.assertIsNone(card_leg["ledger"])
        # And in the real export file: the Posted amount column carries one entry, the counterpart 0.
        import io
        import zipfile
        from openpyxl import load_workbook
        data = export.build_zip([bank_leg, card_leg], e.c.entities, "test2500")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            owner = e.owner(t)
            name = next(n for n in z.namelist() if (e.c.entities[owner.id].code or "") in n)
            ws = load_workbook(io.BytesIO(z.read(name)))["Transactions"]
            header = [c.value for c in ws[2]]
            rows = [[c.value for c in row] for row in ws.iter_rows(min_row=3)]
        posted = [r[header.index("Posted amount")] for r in rows]
        self.assertEqual(sorted(posted), sorted([t.amount_minor / 100, 0]))
        self.assertEqual(sum(posted), t.amount_minor / 100)


if __name__ == "__main__":
    unittest.main()
