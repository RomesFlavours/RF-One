#!/usr/bin/env python
"""Historical dataset audit repair (BANK_HISTORICAL_DATASET_AUDIT_REPAIR_001).

Pins the four audit/control defects found after the historical clean
import, without touching canonical money:

  A. accounts the evidence names but the registry lacks must be PERSISTED
     as unresolved candidates, discovered generically and idempotently;
  B. a raw row from a multi-instrument export counts for the instrument it
     actually belongs to, not for the batch header (which has none);
  C. the current `a9e6d3c71f24` migration produces the schema the golden
     database carries;
  D. the ··3376 overlap is counted as a MULTISET of full identities, and a
     coarse distinct (date, amount, description) count under-states it;
  E. `record_candidate` itself is idempotent: candidate identity + evidence
     set -> deterministic state (BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_
     IDEMPOTENCY_001).

Writes only to DISPOSABLE SQLite databases created here and deleted at the
end. The golden database and the original corpus are opened read-only, and
only when present; nothing in them is modified. Never touches AWS.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def _disposable_url(prefix: str) -> tuple[str, str]:
    fd, path = tempfile.mkstemp(suffix=".db", prefix=prefix)
    os.close(fd)
    os.remove(path)
    return path, "sqlite:///" + path.replace(os.sep, "/")


_DB, DB_URL = _disposable_url("rfone_audit_repair_")
_MIG_DB, MIG_URL = _disposable_url("rfone_audit_repair_mig_")
os.environ["RFONE_DATABASE_URL"] = DB_URL

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(DB_URL)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.bank_reconciliation import historical_source as hs  # noqa: E402
from rfone_data_store.bank_reconciliation import parsers  # noqa: E402
import generate_historical_dataset_manifest as gen  # noqa: E402

GOLDEN = os.path.join(BASE_DIR, "data", "rfone.db")
BANK_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "Bank"))
MIGRATION = "a9e6d3c71f24"
PREVIOUS = "f7c4a21e98b3"

engine = create_engine(DB_URL, future=True)
passed: list[str] = []
failed: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(description)
        print(f"  PASS  {description}")
    else:
        failed.append(description)
        print(f"  FAIL  {description}" + (f"   [{str(detail)[:300]}]" if detail else ""))


def _normalized(sql: str | None) -> str:
    return " ".join((sql or "").split())


def _ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.replace(os.sep, '/')}?mode=ro&immutable=1", uri=True)


# --- fixture: a small ledger shaped exactly like the promoted history -----

_fingerprints = iter(range(1, 10_000))


def add_event(db, *, instrument, batch, day, amount, description, raw_copies=1, extra_batch=None):
    """One canonical transaction plus its raw evidence rows, linked the way
    `promote_historical_staging` links them: duplicate evidence points at
    the SAME transaction."""
    fp = f"{next(_fingerprints):032x}:0"
    tx = m.FinancialTransaction(
        payment_instrument_id=instrument.id, bank_source="CANONICAL_SOURCE_EVIDENCE",
        posting_date=day, transaction_date=day, description_original=description,
        amount_minor=amount, status="COMPLETED", import_batch_id=batch.id,
        fingerprint=fp, accounting_status="CANONICAL", accounting_dedup_key=fp,
        classification="UNKNOWN",
    )
    db.add(tx)
    db.flush()
    for copy in range(raw_copies):
        owner = batch if copy == 0 or extra_batch is None else extra_batch
        db.add(m.RawBankTransaction(
            import_batch_id=owner.id, row_number=next(_fingerprints),
            raw_fields={"description": description, "memo": None,
                        "account_hint": instrument.last_four,
                        "payment_instrument_id": instrument.id},
            row_fingerprint=f"{fp}#{copy}", parse_status="PARSED",
            normalized_transaction_id=tx.id,
        ))
    db.flush()
    return tx


def add_batch(db, name, instrument=None, fmt="CHASE_BANK_ACCOUNT"):
    batch = m.BankImportBatch(
        detected_format=fmt, payment_instrument_id=instrument.id if instrument else None,
        original_file_name=name, raw_file_bytes=name.encode(), sha256=f"{name:0<64}"[:64],
        row_count=0, status="NORMALIZED",
    )
    db.add(batch)
    db.flush()
    return batch


def snapshot(db) -> tuple:
    """Every column of every canonical and raw row — the money must not move."""
    fts = [tuple(getattr(t, c.key) for c in m.FinancialTransaction.__table__.columns)
           for t in db.scalars(select(m.FinancialTransaction).order_by(m.FinancialTransaction.id))]
    raws = [tuple(getattr(r, c.key) for c in m.RawBankTransaction.__table__.columns)
            for r in db.scalars(select(m.RawBankTransaction).order_by(m.RawBankTransaction.id))]
    return json.dumps(fts, default=str), json.dumps(raws, default=str)


with Session(engine) as db:
    entity = m.LegalEntity(legal_name="Test Entity, LLC", status="ACTIVE")
    db.add(entity)
    db.flush()
    operating = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Operating",
                                    institution="CHASE", last_four="3000", status="ACTIVE",
                                    legal_entity_id=entity.id)
    card_a = m.PaymentInstrument(instrument_type="CREDIT_CARD", display_name="Card A",
                                 institution="CHASE", last_four="1111", status="ACTIVE",
                                 legal_entity_id=entity.id)
    card_b = m.PaymentInstrument(instrument_type="CREDIT_CARD", display_name="Card B",
                                 institution="CHASE", last_four="2222", status="ACTIVE",
                                 legal_entity_id=entity.id)
    known = m.PaymentInstrument(instrument_type="CREDIT_CARD", display_name="Known Card",
                                institution="CHASE", last_four="1057", status="ACTIVE",
                                legal_entity_id=entity.id)
    no_digits = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="No Digits",
                                    institution="CHASE", status="INACTIVE")
    db.add_all([operating, card_a, card_b, known, no_digits])
    db.flush()

    bank_old = add_batch(db, "Chase3000_old.csv", operating)
    bank_new = add_batch(db, "Chase3000_new.csv", operating)
    multi = add_batch(db, "Chase_multi_card.csv", None, "CHASE_CREDIT_CARD_WITH_CARD")

    # Real-style Chase bank descriptions. ··4321 is paid twice (two genuine
    # payments) and one of them was downloaded twice (duplicate evidence).
    add_event(db, instrument=operating, batch=bank_old, day=date(2025, 6, 15), amount=-50000,
              description="Payment to Chase card ending in 4321 06/15", raw_copies=2,
              extra_batch=bank_new)
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 8, 15), amount=-42000,
              description="Payment to Chase card ending in 4321 08/15")
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 7, 3), amount=-1000,
              description="Online Transfer to account xxxx8765 transaction#: 23456")
    # A registered card: evidence, but not a candidate.
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 7, 20), amount=-30000,
              description="Payment to Chase card ending in 1057 07/20")
    # Noise: trace numbers, order references and balances containing digits.
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 7, 21), amount=-777,
              description="ORIG CO NAME:SUPPLIER TRACE#:063116509283336 EED:260224")
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 7, 22), amount=-2500,
              description="AMAZON MKTPL*133361JG3 Amzn.com/bill WA")
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 7, 23), amount=-900,
              description="CHECK 5871 PAID ORDER 0246-8321")
    # One multi-card export: rows for BOTH cards, header naming neither.
    add_event(db, instrument=card_a, batch=multi, day=date(2025, 7, 1), amount=-450,
              description="COFFEE SHOP")
    add_event(db, instrument=card_a, batch=multi, day=date(2025, 7, 2), amount=-1200,
              description="HARDWARE STORE")
    add_event(db, instrument=card_b, batch=multi, day=date(2025, 7, 1), amount=-6025,
              description="FUEL STOP", raw_copies=2)
    add_event(db, instrument=card_b, batch=multi, day=date(2025, 7, 5), amount=-8810,
              description="GROCERY")
    db.commit()
    ids = {"operating": operating.id, "card_a": card_a.id, "card_b": card_b.id,
           "known": known.id, "no_digits": no_digits.id}
    instrument_count = db.query(m.PaymentInstrument).count()


print("\n=== A1-A2. generic reference extraction from real-style descriptions ===")
check("A1. a Chase card payment names the card it pays",
      hs.extract_instrument_references("Payment to Chase card ending in 4321 06/15") == {"4321"})
check("A1b. a masked transfer destination is recognised",
      hs.extract_instrument_references("Online Transfer to account xxxx8765 transaction#: 23456")
      == {"8765"})
refs = hs.instrument_reference_evidence("Payment to Chase card ending in 4321 06/15",
                                        known_institutions={"CHASE"})
check("A1c. the evidence records its kind and the institution the text itself names",
      [(r.last_four, r.kind, r.institution) for r in refs]
      == [("4321", "CARD_OR_ACCOUNT_ENDING_IN", "CHASE")], str(refs))
check("A1d. an unknown word before 'card' is not promoted to an institution",
      [r.institution for r in hs.instrument_reference_evidence(
          "Payment to Mystery card ending in 4321", known_institutions={"CHASE"})] == [None])
check("A2. a trace number is NOT an instrument reference",
      hs.extract_instrument_references("TRACE#:063116509283336 EED:260224") == set())
check("A2b. nor an order reference, nor a bare check/order number",
      hs.extract_instrument_references("AMAZON MKTPL*133361JG3") == set()
      and hs.extract_instrument_references("CHECK 5871 PAID ORDER 0246-8321") == set())

print("\n=== A3-A8. candidate discovery over the raw evidence ===")
with Session(engine) as db:
    before = snapshot(db)
    result = hs.discover_indirect_reference_candidates(db)
    db.commit()
    candidates = {c.last_four: c for c in hs.list_candidates(db)}
    check("A3. every credible unregistered reference became a persisted candidate",
          set(candidates) == {"4321", "8765"}, str(sorted(candidates)))
    check("A3b. a reference to a REGISTERED card is not a candidate",
          "1057" not in candidates and "1057" in result.registered_references)
    check("A3c. noise digits (trace, order, check numbers) produced no candidate",
          not ({"3336", "1336", "5871", "0246", "8321"} & set(candidates)))
    c4321 = candidates.get("4321")
    check("A4. the candidate counts distinct canonical transactions, not raw copies",
          c4321 is not None and c4321.occurrence_count == 2, getattr(c4321, "occurrence_count", None))
    check("A4b. its evidence names the reference kind, and keeps 3 raw rows for 2 transactions",
          c4321 is not None and "CARD_OR_ACCOUNT_ENDING_IN" in c4321.evidence
          and c4321.raw_evidence_count == 3 and c4321.canonical_transaction_count == 2,
          getattr(c4321, "evidence", ""))
    check("A4c. first/last observed dates are the evidence span",
          c4321 is not None and c4321.first_seen_date == date(2025, 6, 15)
          and c4321.last_seen_date == date(2025, 8, 15))
    check("A4d. the institution comes only from what the text names",
          c4321 is not None and c4321.institution == "CHASE"
          and candidates["8765"].institution is None)
    check("A4e. discovery is INDIRECT_REFERENCE", all(
        c.discovery == m.CANDIDATE_INDIRECT_REFERENCE for c in candidates.values()))
    check("A5. every candidate stays unresolved and undecided", all(
        c.resolution is None and c.resolution_effective_date is None
        and c.resolved_payment_instrument_id is None
        and hs.candidate_state(c) == hs.REFERENCED_WITHOUT_REGISTERED_INSTRUMENT
        for c in candidates.values()))
    check("A5b. no Payment Instrument was created, and none was changed",
          db.query(m.PaymentInstrument).count() == instrument_count
          and db.query(m.PaymentInstrument).filter(
              m.PaymentInstrument.last_four.in_(["4321", "8765"])).count() == 0)
    check("A6. discovery did not change a single FinancialTransaction or raw row",
          snapshot(db) == before)
    check("A6b. the registered instrument with no last four was left as it is",
          db.get(m.PaymentInstrument, ids["no_digits"]).last_four is None
          and db.get(m.PaymentInstrument, ids["no_digits"]).status == "INACTIVE")
    first_state = {k: (c.evidence, c.occurrence_count, c.first_seen_date, c.last_seen_date,
                       c.updated_at) for k, c in candidates.items()}

with Session(engine) as db:
    again = hs.discover_indirect_reference_candidates(db)
    db.commit()
    candidates = {c.last_four: c for c in hs.list_candidates(db)}
    second_state = {k: (c.evidence, c.occurrence_count, c.first_seen_date, c.last_seen_date,
                        c.updated_at) for k, c in candidates.items()}
    check("A7. a repeated scan creates nothing and changes nothing",
          again.created == [] and again.updated == [] and first_state == second_state,
          f"created={again.created} updated={again.updated}")

    hs.resolve_candidate(db, candidate=candidates["8765"], resolution=m.CANDIDATE_NOT_OURS,
                         note="test: supplier's own account")
    db.commit()
    hs.discover_indirect_reference_candidates(db)
    db.commit()
    check("A8. a later scan never overwrites a human's resolution",
          db.scalars(select(m.BankHistoricalInstrumentCandidate).where(
              m.BankHistoricalInstrumentCandidate.last_four == "8765")).one().resolution
          == m.CANDIDATE_NOT_OURS)

print("\n=== B. multi-instrument source raw attribution and manifest counting ===")
with Session(engine) as db:
    raw = gen.raw_rows_by_instrument(db)
    check("B1. rows of a multi-instrument export count for the card they belong to",
          raw.get(ids["card_a"]) == 2 and raw.get(ids["card_b"]) == 3, str(raw))
    by_header = {
        i: db.query(m.RawBankTransaction).join(
            m.BankImportBatch, m.BankImportBatch.id == m.RawBankTransaction.import_batch_id
        ).filter(m.BankImportBatch.payment_instrument_id == i).count()
        for i in (ids["card_a"], ids["card_b"])
    }
    check("B1b. whereas the batch header — the old method — counts them for nobody",
          by_header == {ids["card_a"]: 0, ids["card_b"]: 0}, str(by_header))
    check("B2. per-instrument raw rows add up to every raw row",
          sum(raw.values()) == db.query(m.RawBankTransaction).count())
    split = gen.batch_instrument_split(db)
    check("B3. the multi-instrument file is split across both cards",
          split["Chase_multi_card.csv"] == {ids["card_a"]: 2, ids["card_b"]: 3}, str(split))

    def controls_from_db() -> dict:
        out = {}
        for instrument in db.scalars(select(m.PaymentInstrument)):
            txs = db.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.payment_instrument_id == instrument.id)).all()
            if not txs:
                continue
            out[str(instrument.id)] = {
                "raw_rows": raw.get(instrument.id, 0), "clean_events": len(txs),
                "duplicate_evidence_rows": raw.get(instrument.id, 0) - len(txs),
                "debit_minor": sum(t.amount_minor for t in txs if t.amount_minor < 0),
                "credit_minor": sum(t.amount_minor for t in txs if t.amount_minor >= 0),
                "month_count": 1, "month_gaps": [],
            }
        return out

    controls = controls_from_db()
    rows = gen.instrument_rows(db, controls)
    by_id = {r["id"]: r for r in rows}
    check("B4. the manifest's per-instrument row reports the attributed raw count",
          by_id[ids["card_b"]]["raw_rows"] == 3 and by_id[ids["card_b"]]["duplicate_evidence"] == 1
          and by_id[ids["card_b"]]["canonical"] == 2)
    check("B4b. every registered instrument appears, the unsourced one as REGISTERED_NO_SOURCE",
          by_id[ids["no_digits"]]["census_state"] == hs.REGISTERED_NO_SOURCE
          and by_id[ids["no_digits"]]["raw_rows"] == 0 and len(rows) == instrument_count)
    wrong = dict(controls)
    wrong[str(ids["card_a"])] = dict(wrong[str(ids["card_a"])], raw_rows=0)
    try:
        gen.instrument_rows(db, wrong)
        refused = False
    except gen.ManifestMismatch:
        refused = True
    check("B5. a manifest whose raw count disagrees with staging is refused, not written",
          refused)

print("\n=== C. migration a9e6d3c71f24 — current file vs applied schema ===")
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def _alembic(url: str) -> Config:
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = url
    return Config(os.path.join(BASE_DIR, "alembic.ini"))


run_migrations_to_head(MIG_URL)
with _ro(_MIG_DB) as con:
    head_ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='bank_import_batches'").fetchone()[0]
    head_version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
check("C1. a fresh database at head carries the widened format vocabulary",
      all(v in head_ddl for v in ("'AMEX_QBO'", "'AMEX_XLSX'", "'AMEX_CSV'", "'FIRST_CITIZENS'")))
check("C1b. and every default, width and constraint the rebuild must preserve",
      all(s in _normalized(head_ddl) for s in (
          "detected_format VARCHAR(48) NOT NULL",
          "uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
          "row_count INTEGER DEFAULT '0' NOT NULL",
          "status VARCHAR(24) DEFAULT 'RECEIVED' NOT NULL",
          "CONSTRAINT uq_bank_import_batches_sha256 UNIQUE (sha256)",
          "FOREIGN KEY(payment_instrument_id) REFERENCES payment_instruments (id)",
      )))
cfg = _alembic(MIG_URL)
command.downgrade(cfg, PREVIOUS)
with _ro(_MIG_DB) as con:
    down_ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='bank_import_batches'").fetchone()[0]
command.upgrade(cfg, MIGRATION)
with _ro(_MIG_DB) as con:
    cycled_ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='bank_import_batches'").fetchone()[0]
command.upgrade(cfg, "head")
os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
check("C2. downgrade restores the original four-format CHECK",
      "'AMEX_QBO'" not in down_ddl and "'FIRST_CITIZENS'" in down_ddl)
check("C2b. downgrade → upgrade returns to exactly the same DDL",
      _normalized(cycled_ddl) == _normalized(head_ddl))
if os.path.exists(GOLDEN):
    with _ro(GOLDEN) as con:
        golden_ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='bank_import_batches'").fetchone()[0]
        golden_version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    check("C3. the golden database is at the same revision the current files end at",
          golden_version == head_version, f"{golden_version} vs {head_version}")
    check("C3b. and the schema the CURRENT migration produces is the one the golden DB carries",
          _normalized(golden_ddl) == _normalized(head_ddl))
else:
    print("  SKIP  C3. golden database not present on this machine")

print("\n=== D. the ··3376 comparison method ===")


def chase_bank(rows) -> bytes:
    head = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    return (head + "".join(
        f"DEBIT,{p},\"{d}\",{a},FEE_TRANSACTION,{b},,\n" for p, d, a, b in rows)).encode()


# Two genuine $10 fees on the same day with the same text: only the running
# balance tells them apart. Both exports contain both.
pair = [("01/26/2026", "OFFICIAL CHECKS CHARGE", "-10.00", "1343.43"),
        ("01/26/2026", "OFFICIAL CHECKS CHARGE", "-10.00", "1343.53"),
        ("01/27/2026", "WIRE FEE", "-15.00", "1328.43")]
fa = hs.fingerprint_bytes(file_bytes=chase_bank(pair), path="/x/old.csv")
fb = hs.fingerprint_bytes(file_bytes=chase_bank(pair + [("01/28/2026", "FEE", "-1.00", "1327.43")]),
                          path="/x/new.csv")
rel = hs.classify_relationship(fa, fb)
check("D1. the certified multiset identity counts BOTH same-day fees as shared",
      rel.verdict == hs.TRANSACTION_SUBSET and rel.shared == 3 and rel.only_b == 1,
      f"{rel.verdict} {rel.shared}/{rel.only_a}/{rel.only_b}")


def review(path, rows):
    parsed = parsers.parse_csv_bytes(chase_bank(rows)).rows
    out = []
    for r in parsed:
        ident = hs.row_identity(parsers.CHASE_BANK_ACCOUNT, r)
        out.append({"payment_instrument_id": 6, "source_path": path,
                    "posting_date": r.posting_date.isoformat(), "amount_minor": r.amount_minor,
                    "description": r.description, "identity_basis": ident.basis,
                    "identity_key": list(ident.key)})
    return out


cmp_ = gen.coarse_vs_multiset_overlap(review("old.csv", pair) + review("new.csv", pair), 6)
check("D2. a DISTINCT (date, amount, description) count collapses them into one",
      cmp_["coarse_distinct_shared"] == 2 and cmp_["multiset_shared"] == 3, str(cmp_))
check("D2b. and names the collapsed key, so the difference is explainable",
      cmp_["collapsed_keys"] == [{"posting_date": "2026-01-26", "amount_minor": -1000,
                                  "rows_in_each_file": 2}], str(cmp_["collapsed_keys"]))

old_3376 = os.path.join(BANK_DIR, "Download", "Chase3376_Activity_20260915.csv")
new_3376 = os.path.join(BANK_DIR, "Historic Data", "Chase3376_Activity_20260922.csv")
if os.path.exists(old_3376) and os.path.exists(new_3376):
    real = hs.classify_relationship(hs.fingerprint_path(old_3376), hs.fingerprint_path(new_3376))
    rows_old = [r for r in parsers.parse_csv_bytes(open(old_3376, "rb").read()).rows]
    rows_new = [r for r in parsers.parse_csv_bytes(open(new_3376, "rb").read()).rows]
    coarse = lambda r: (r.posting_date, r.amount_minor, r.description)
    distinct_shared = len({coarse(r) for r in rows_old} & {coarse(r) for r in rows_new})
    check("D3. real ··3376: the certified multiset shares 1,376 rows (read-only)",
          real.verdict == hs.TRANSACTION_SUBSET and real.shared == 1376 and real.only_a == 0,
          f"{real.verdict} {real.shared}")
    check("D3b. real ··3376: the earlier coarse distinct count reproduces as 1,370",
          distinct_shared == 1370, str(distinct_shared))
else:
    print("  SKIP  D3. original ··3376 exports not present on this machine")

print("\n=== E. record_candidate: identity + evidence set -> deterministic state ===")


def state(c) -> tuple:
    return (c.occurrence_count, c.first_seen_date, c.last_seen_date, c.raw_evidence_count,
            c.canonical_transaction_count, len(c.evidence_items), c.evidence, c.resolution,
            c.updated_at)


def candidate(db, last_four):
    return db.scalars(select(m.BankHistoricalInstrumentCandidate).where(
        m.BankHistoricalInstrumentCandidate.last_four == last_four)).one()


with Session(engine) as db:
    ft_before = snapshot(db)[0]
    first = hs.record_candidate(
        db, last_four="6060", institution="CHASE", discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence="unit: generic API", evidence_items=[
            hs.CandidateEvidence(key="raw:900001", kind="ENDING_IN", first_observed=date(2025, 3, 1),
                                 last_observed=date(2025, 3, 1), financial_transaction_id=None),
        ])
    db.commit()
    check("E1. the first recording creates the candidate with its evidence",
          first.occurrence_count == 1 and len(first.evidence_items) == 1)
    s1 = state(first)
    hs.record_candidate(
        db, last_four="6060", institution="CHASE", discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence="unit: generic API", evidence_items=[
            hs.CandidateEvidence(key="raw:900001", kind="ENDING_IN", first_observed=date(2025, 3, 1),
                                 last_observed=date(2025, 3, 1)),
        ])
    db.commit()
    check("E3. the SAME evidence key recorded again cannot increment anything",
          state(candidate(db, "6060")) == s1, f"{s1} vs {state(candidate(db, '6060'))}")

    legacy = dict(last_four="7070", institution="CHASE", discovery=m.CANDIDATE_DIRECT_SOURCE,
                  evidence="Chase7070_Activity.csv — its own export", first_seen=date(2025, 1, 2),
                  last_seen=date(2025, 6, 30), occurrences=200)
    hs.record_candidate(db, **legacy)
    db.commit()
    s_legacy = state(candidate(db, "7070"))
    hs.record_candidate(db, **legacy)
    hs.record_candidate(db, **legacy)
    db.commit()
    check("E3b. a summary-only caller repeating itself is also a no-op (was: 200 -> 600)",
          state(candidate(db, "7070")) == s_legacy and s_legacy[0] == 200, str(s_legacy[:3]))
    hs.record_candidate(db, **dict(legacy, evidence="Chase7070_Activity (2).csv — July export",
                                   first_seen=date(2025, 7, 1), last_seen=date(2025, 7, 31),
                                   occurrences=31))
    db.commit()
    c7070 = candidate(db, "7070")
    check("E3c. and a genuinely different summary adds exactly what it declares",
          c7070.occurrence_count == 231 and c7070.last_seen_date == date(2025, 7, 31)
          and c7070.first_seen_date == date(2025, 1, 2))
    check("E12b. the generic API wrote no FinancialTransaction", snapshot(db)[0] == ft_before)

with Session(engine) as db:
    operating = db.get(m.PaymentInstrument, ids["operating"])
    bank_new = db.scalars(select(m.BankImportBatch).where(
        m.BankImportBatch.original_file_name == "Chase3000_new.csv")).one()
    c4321 = candidate(db, "4321")
    before_4321 = state(c4321)

    # E4 — a NEW raw copy of an ALREADY-counted canonical transaction.
    tx = db.scalars(select(m.FinancialTransaction).where(
        m.FinancialTransaction.description_original.like("%ending in 4321 08/15%"))).one()
    db.add(m.RawBankTransaction(
        import_batch_id=bank_new.id, row_number=990001,
        raw_fields={"description": tx.description_original, "memo": None},
        row_fingerprint="late-redownload", parse_status="PARSED", normalized_transaction_id=tx.id))
    db.commit()
    hs.discover_indirect_reference_candidates(db)
    db.commit()
    c4321 = candidate(db, "4321")
    check("E4. new raw evidence adds ONE raw evidence row",
          c4321.raw_evidence_count == before_4321[3] + 1, f"{before_4321[3]} -> {c4321.raw_evidence_count}")
    check("E4b. but the same canonical transaction is still counted once",
          c4321.occurrence_count == before_4321[0] and c4321.canonical_transaction_count == 2)

    # E5-E7 — genuinely new canonical transactions, one later and one earlier.
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 9, 30), amount=-61000,
              description="Payment to Chase card ending in 4321 09/30")
    add_event(db, instrument=operating, batch=bank_new, day=date(2025, 5, 2), amount=-12000,
              description="Payment to Chase card ending in 4321 05/02")
    db.commit()
    hs.discover_indirect_reference_candidates(db)
    db.commit()
    c4321 = candidate(db, "4321")
    check("E5. two new canonical transactions increment the count by exactly two",
          c4321.occurrence_count == before_4321[0] + 2, str(c4321.occurrence_count))
    check("E6. first observed stays the MINIMUM of the evidence", c4321.first_seen_date == date(2025, 5, 2))
    check("E7. last observed stays the MAXIMUM of the evidence", c4321.last_seen_date == date(2025, 9, 30))
    after_growth = state(c4321)
    hs.discover_indirect_reference_candidates(db)
    db.commit()
    check("E2. rerunning identical discovery after growth changes nothing",
          state(candidate(db, "4321")) == after_growth)
    check("E8. the human resolution recorded earlier is still intact",
          candidate(db, "8765").resolution == m.CANDIDATE_NOT_OURS)

# E9-E12 on a fresh ledger shaped like the real one: four real-style references.
_E_DB, E_URL = _disposable_url("rfone_audit_repair_four_")
run_migrations_to_head(E_URL)
e_engine = create_engine(E_URL, future=True)
with Session(e_engine) as db:
    entity = m.LegalEntity(legal_name="Four Entity, LLC", status="ACTIVE")
    db.add(entity)
    db.flush()
    payer = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Payer",
                                institution="CHASE", last_four="3376", status="ACTIVE",
                                legal_entity_id=entity.id)
    freedom = m.PaymentInstrument(instrument_type="CREDIT_CARD", display_name="Freedom",
                                  institution="CHASE", last_four="2915", status="ACTIVE")
    lookalike = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Chase-2915",
                                    status="INACTIVE")
    db.add_all([payer, freedom, lookalike])
    db.flush()
    lookalike_id = lookalike.id
    batch = add_batch(db, "Chase3376_real_style.csv", payer)
    plan = {"0246": 4, "2813": 6, "5871": 6, "8321": 3}
    day = date(2025, 8, 1)
    for last_four, n in plan.items():
        for k in range(n):
            add_event(db, instrument=payer, batch=batch, day=date(2025, 8, 1 + k), amount=-1000 * (k + 1),
                      description=f"Payment to Chase card ending in {last_four} 08/{1 + k:02d}",
                      raw_copies=2)
    add_event(db, instrument=payer, batch=batch, day=day, amount=-5,
              description="Payment to Chase card ending in 2915 08/01")
    add_event(db, instrument=payer, batch=batch, day=day, amount=-6,
              description="ORIG CO NAME:VENDOR TRACE#:021000029283336 EED:260301 ORDER 5871-0246")
    db.commit()
    e_before = snapshot(db)
    runs = []
    for _ in range(3):
        hs.discover_indirect_reference_candidates(db)
        db.commit()
        runs.append({c.last_four: state(c) for c in hs.list_candidates(db)})
    check("E9. a registered card (Freedom ··2915) never becomes a candidate",
          "2915" not in runs[-1])
    check("E10. trace/order-number digits never become candidates",
          set(runs[-1]) == set(plan), str(sorted(runs[-1])))
    check("E11. four real-style candidates are identical across three scans",
          runs[0] == runs[1] == runs[2]
          and {k: v[0] for k, v in runs[-1].items()} == plan
          and all(v[3] == 2 * plan[k] for k, v in runs[-1].items())
          and all(v[7] is None for v in runs[-1].values()), str({k: v[:4] for k, v in runs[-1].items()}))
    check("E11b. the registered Chase-2915 look-alike is untouched: no last four, no merge",
          db.get(m.PaymentInstrument, lookalike_id).last_four is None
          and db.query(m.PaymentInstrument).count() == 3)
    check("E12. canonical FinancialTransaction and raw rows are unchanged by every scan",
          snapshot(db) == e_before)
e_engine.dispose()

engine.dispose()
for path in (_DB, _MIG_DB, _E_DB):
    try:
        os.remove(path)
    except OSError:
        pass

print(f"\n{len(passed)} passed, {len(failed)} failed.")
if failed:
    print("FAILURES:")
    for f in failed:
        print(f"  - {f}")
sys.exit(1 if failed else 0)
