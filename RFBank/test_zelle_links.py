"""Tests for bank_zelle_links (Zelle payment -> bank movement links, 2026-11-20). In-memory SQLite only."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "03 Software" / "RF-One Web"), str(ROOT / "03 Software" / "RF-One Data Store")]

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import bank_zelle  # noqa: E402
import bank_zelle_links as zl  # noqa: E402


def setup():
    db = Session(create_engine("sqlite://"))
    db.execute(text("""CREATE TABLE financial_transactions (id INTEGER PRIMARY KEY, posting_date TEXT,
        amount_minor INTEGER, description_original TEXT, duplicate_status TEXT DEFAULT 'NONE')"""))
    for t in ("bank_flow_artifacts", "purchase_documents", "bank_transaction_allocations", "rfone_accounts"):
        db.execute(text(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)"))
    bank_zelle.ensure(db)
    db.execute(text("INSERT INTO bank_zelle_files (id,file_name,digest,content,status,uploaded_at) VALUES (1,'z.pdf','d',x'00','CONFIRMED','now')"))
    return db


def pay(db, pid, sent, recipient, amount, memo, status="Completed"):
    db.execute(text("""INSERT INTO bank_zelle_payments (id,file_id,sent_on,status,direction,who,recipient,memo,amount_minor,
        acquired_at,status_basis) VALUES (:i,1,:s,:st,'OUT',:w,:r,:m,:a,'now','CONSISTENT')"""),
               dict(i=pid, s=sent, st=status, w=bank_zelle.who_key(recipient), r=recipient, m=memo, a=amount))


def mov(db, tid, posted, name, amount, ref="JPM99abc"):
    db.execute(text("INSERT INTO financial_transactions (id,posting_date,amount_minor,description_original) VALUES (:i,:p,:a,:d)"),
               dict(i=tid, p=posted, a=-amount, d=f"Zelle payment to {name} {ref}"))


def links(db):
    return {(r[0], r[1]): (r[2], r[3]) for r in db.execute(text(
        """SELECT CAST(substr(d.source_key,21) AS INTEGER), l.financial_transaction_id, l.status, l.match_method
           FROM bank_transaction_document_links l JOIN bank_source_documents d ON d.id=l.source_document_id"""))}


def test_unique_typo_window_status():
    db = setup()
    pay(db, 1, "2026-09-28", "Tatiana Ceban", 266221, "26 Sep 21-27 Tip")
    mov(db, 10, "2026-09-29", "Tatiana Ceban", 266221)
    pay(db, 2, "2026-07-30", "Fosterr King", 9380, "26 Jul 06-19 Pay")          # typo in Zelle
    mov(db, 11, "2026-07-30", "Foster King", 9380)
    pay(db, 3, "2026-05-04", "Olivia Kosicki", 1530, "26 Apr 27-03 Tip", status="Rejected")
    mov(db, 12, "2026-05-04", "Olivia Kosicki", 1530)
    pay(db, 4, "2026-06-01", "Gaby Steinborn", 13966, "26 May 25-31 Tip")
    mov(db, 13, "2026-06-08", "Gaby Steinborn", 13966)                           # 7 days later: out of window
    pay(db, 5, "2026-11-17", "Giovanna Wine Rep", 300000, "Expences")             # no movement yet
    out = zl.match(db)
    got = links(db)
    assert got == {(1, 10): ("CONFIRMED", "AUTO"), (2, 11): ("CONFIRMED", "AUTO")}, got
    assert out["linked"] == 2 and out["proposed"] == 0 and out["no_movement"] == 2 and out["skipped"] == 1, out
    assert zl.memos(db)[10]["memo"] == "26 Sep 21-27 Tip"
    # idempotent
    again = zl.match(db)
    assert again["linked"] == 0 and links(db) == got, again


def test_same_date_is_certain():
    db = setup()
    # Olivia Kosicki 201.74 on Jul 6 and Jul 7, same memo; bank movements Jul 6 and Jul 7
    pay(db, 1, "2026-07-06", "Olivia Kosicki", 20174, "26 Jun 22-05 Pay")
    pay(db, 2, "2026-07-07", "Olivia Kosicki", 20174, "26 Jun 22-05 Pay")
    mov(db, 20, "2026-07-06", "Olivia Kosicki", 20174)
    mov(db, 21, "2026-07-07", "Olivia Kosicki", 20174)
    # BBC Wine 2,500 on Sep 11 and Sep 13; movements Sep 11 and Sep 14; name contained ("BBC" in "BBC Wine")
    pay(db, 3, "2026-09-11", "BBC", 250000, "Down")
    pay(db, 4, "2026-09-13", "BBC Wine", 250000, "Down")
    mov(db, 30, "2026-09-11", "BBC Wine", 250000)
    mov(db, 31, "2026-09-14", "BBC Wine", 250000)
    out = zl.match(db)
    got = links(db)
    assert {k: v for k, v in got.items() if v[0] == "CONFIRMED"} == {
        (1, 20): ("CONFIRMED", "AUTO"), (2, 21): ("CONFIRMED", "AUTO"),
        (3, 30): ("CONFIRMED", "AUTO"), (4, 31): ("CONFIRMED", "AUTO")}, got
    assert out["proposed"] == 0, out


def test_old_proposals_upgraded():
    db = setup()
    pay(db, 1, "2026-07-06", "Olivia Kosicki", 20174, "Pay")
    pay(db, 2, "2026-07-07", "Olivia Kosicki", 20174, "Pay")
    mov(db, 20, "2026-07-06", "Olivia Kosicki", 20174)
    mov(db, 21, "2026-07-07", "Olivia Kosicki", 20174)
    zl.ensure(db)
    doc = {}
    for pid in (1, 2):
        p = dict(db.execute(text("SELECT * FROM bank_zelle_payments WHERE id=:i"), {"i": pid}).mappings().first())
        doc[pid] = zl._document(db, p)
    for pid, tid in ((1, 20), (1, 21), (2, 21)):   # proposals left by the earlier version
        db.execute(text("""INSERT INTO bank_transaction_document_links (financial_transaction_id,source_document_id,role,
            status,match_method) VALUES (:t,:d,'PAYMENT_DETAIL','PROPOSED','AUTO')"""), dict(t=tid, d=doc[pid]))
    zl.match(db)
    got = links(db)
    assert got[(1, 20)][0] == "CONFIRMED" and got[(2, 21)][0] == "CONFIRMED" and got[(1, 21)][0] == "REJECTED", got


def test_identical_same_day_left_to_person():
    db = setup()
    pay(db, 1, "2026-03-17", "Sienna Silverstin", 15427, "Tips")
    pay(db, 2, "2026-03-17", "Sienna Silverstin", 15427, None)
    mov(db, 40, "2026-03-17", "Sienna Silverstin", 15427, ref="A1")
    mov(db, 41, "2026-03-17", "Sienna Silverstin", 15427, ref="A2")
    out = zl.match(db)
    got = links(db)
    assert out["linked"] == 0 and out["proposed"] == 4 and all(v == ("PROPOSED", "AUTO") for v in got.values()), (out, got)
    ov = zl.overview(db)
    assert ov["pending"][0]["zelle_amount_minor"] == 15427 and ov["pending"][0]["amount_minor"] == -15427
    link = db.execute(text("""SELECT l.id FROM bank_transaction_document_links l JOIN bank_source_documents d
        ON d.id=l.source_document_id WHERE d.source_key='bank_zelle_payments:1' AND l.financial_transaction_id=40""")).scalar()
    zl.decide(db, link, "CONFIRMED", account_id=None)
    zl.match(db)            # the remaining pair (2, 41) is now unique on both sides
    got = links(db)
    assert got[(1, 40)] == ("CONFIRMED", "HUMAN") and got[(1, 41)][0] == "REJECTED" and got[(2, 40)][0] == "REJECTED"
    assert got[(2, 41)][0] == "CONFIRMED", got
    try:
        zl.decide(db, link, "REJECTED", account_id=None)
    except ValueError:
        pass
    else:
        raise AssertionError("a decided link must not change")


def test_names():
    assert zl.bank_name("Zelle payment to Leo Windows Cleaning 30912033433") == "Leo Windows Cleaning"
    assert zl.same_recipient("Michael Costruction", "Michael Construction")
    assert zl.same_recipient("BBC", "BBC Wine")
    assert not zl.same_recipient("Andrew Muller", "Terry Muller")
    assert not zl.same_recipient("Alice Martini", "Allie Rokanas")


def test_page_break_row_is_joined():
    rows = [dict(page=1, line=15, sent_on="2026-11-16", recipient="Foster King", amount_minor=6252, memo=None,
                 doubt="Riga interrotta a fine pagina."),
            dict(page=2, line=1, sent_on=None, recipient="", amount_minor=None, memo="2026 Nov 09-15 Tip",
                 type="In moments", invalid=True, doubt="Continuazione"),
            dict(page=2, line=2, sent_on="2026-11-16", recipient="Bailey Roman", amount_minor=15036, memo="x")]
    out = bank_zelle.merge_continuations(rows)
    assert len(out) == 2 and out[0]["memo"] == "2026 Nov 09-15 Tip" and out[0]["doubt"] is None, out
    assert bank_zelle.merge_continuations(out) == out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
