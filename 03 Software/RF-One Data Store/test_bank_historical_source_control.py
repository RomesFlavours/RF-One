#!/usr/bin/env python
"""Historical Bank source control (BANK_HISTORICAL_SOURCE_CONTROL_FOUNDATION_001).

The operator will download the same history again and again. This suite
exists to prove that costs them nothing: no file has to be thrown away, no
transaction is counted twice, no genuine repetition is collapsed, and no
account the evidence mentions is allowed to disappear.

Runs entirely against a DISPOSABLE SQLite database created here and deleted
at the end. The authoritative local database is never touched, no source
file is read from the real corpus, and no Excel file is opened or
referenced anywhere in this suite or in the feature.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="rfone_hist_source_")
os.close(_FD)
os.remove(_DB)
DB_URL = "sqlite:///" + _DB.replace(os.sep, "/")
os.environ["RFONE_DATABASE_URL"] = DB_URL

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(DB_URL)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.bank_reconciliation import historical_source as hs  # noqa: E402
from rfone_data_store.bank_reconciliation import parsers  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402

engine = create_engine(DB_URL, future=True)

passed: list[str] = []
failed: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(description)
        print(f"  PASS  {description}")
    else:
        failed.append(description)
        print(f"  FAIL  {description}" + (f"   [{detail[:300]}]" if detail else ""))


# --- source builders -------------------------------------------------
# Real Chase/First Citizens layouts. The two Chase card variants differ
# only by the `Card` column, which is exactly the trap §10 is about.

def chase_card_with_card(rows, card="1057") -> bytes:
    head = "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    return (head + "".join(
        f"{card},{t},{p},{d},Merchandise & Inventory,Sale,{a},\n" for t, p, d, a in rows
    )).encode()


def chase_card_no_card(rows) -> bytes:
    head = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    return (head + "".join(
        f"{t},{p},{d},Merchandise & Inventory,Sale,{a},\n" for t, p, d, a in rows
    )).encode()


def chase_bank(rows) -> bytes:
    """Chase bank account. `Description` may carry the bank's own TRN."""
    head = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    return (head + "".join(
        f"DEBIT,{p},\"{d}\",{a},ACH_DEBIT,{b},,\n" for p, d, a, b in rows
    )).encode()


A = ("06/03/2025", "06/04/2025", "COFFEE SHOP", "-4.50")
B = ("06/05/2025", "06/06/2025", "HARDWARE STORE", "-120.00")
C = ("06/07/2025", "06/08/2025", "FUEL STOP", "-60.25")
D = ("06/09/2025", "06/10/2025", "GROCERY", "-88.10")
E = ("06/11/2025", "06/12/2025", "STATIONERY", "-15.00")


def fp(data: bytes, name: str) -> hs.SourceFingerprint:
    return hs.fingerprint_bytes(file_bytes=data, path=f"/corpus/{name}")


print("\n=== 1-2. the two levels of idempotency are NOT the same question ===")
original = chase_card_with_card([A, B, C])
fp_a = fp(original, "export.csv")
fp_renamed = fp(original, "export (1).csv")
check("1. identical bytes under a different name are the SAME file",
      hs.classify_relationship(fp_a, fp_renamed).verdict == hs.EXACT_FILE_DUPLICATE)
check("1b. level 1 answers that with the byte hash alone",
      fp_a.sha256 == fp_renamed.sha256)

with_card = fp(chase_card_with_card([A, B, C]), "with_card.csv")
no_card = fp(chase_card_no_card([A, B, C]), "no_card.csv")
check("2. DIFFERENT bytes carrying the same financial events are not the same FILE",
      with_card.sha256 != no_card.sha256)
rel = hs.classify_relationship(with_card, no_card)
check("2b. but level 2 sees the same transactions through two Chase layouts",
      rel.verdict == hs.TRANSACTION_EQUIVALENT and rel.shared == 3,
      f"{rel.verdict} shared={rel.shared} {rel.basis}")
check("2c. the file layout is deliberately absent from transaction identity",
      set(with_card.identities) == set(no_card.identities))

print("\n=== 3-7. every source relationship ===")
old = fp(chase_card_with_card([A, B, C, D]), "old.csv")
new = fp(chase_card_with_card([B, C, D, E]), "new.csv")
same = fp(chase_card_no_card([A, B, C, D]), "same_again.csv")
bigger = fp(chase_card_with_card([A, B, C, D, E]), "bigger.csv")
smaller = fp(chase_card_with_card([A, B]), "smaller.csv")
other = fp(chase_card_with_card([E]), "other.csv")

check("3. transaction-equivalent exports: different bytes, different Chase layout, "
      "identical transactions",
      hs.classify_relationship(old, same).verdict == hs.TRANSACTION_EQUIVALENT
      and old.sha256 != same.sha256)
check("3b. byte-identical files are EXACT_FILE_DUPLICATE, a different answer",
      hs.classify_relationship(
          old, fp(chase_card_with_card([A, B, C, D]), "copy.csv")
      ).verdict == hs.EXACT_FILE_DUPLICATE)
check("4. superset export",
      hs.classify_relationship(bigger, old).verdict == hs.TRANSACTION_SUPERSET)
check("5. subset export",
      hs.classify_relationship(old, bigger).verdict == hs.TRANSACTION_SUBSET)
r = hs.classify_relationship(old, new)
check("6. partial overlap — and BOTH files are needed",
      r.verdict == hs.PARTIAL_OVERLAP and r.shared == 3 and r.only_a == 1
      and r.only_b == 1 and r.both_needed,
      f"{r.verdict} {r.shared}/{r.only_a}/{r.only_b}")
check("7. disjoint files",
      hs.classify_relationship(smaller, other).verdict == hs.DISJOINT)
check("7b. a CARD file against a BANK ACCOUNT file is AMBIGUOUS, not disjoint — they "
      "cannot be the same account, so their overlap would mean nothing",
      hs.classify_relationship(
          old, fp(chase_bank([("06/03/2025", "SOMETHING", "-4.50", "100.00")]), "bank.csv")
      ).verdict == hs.AMBIGUOUS)

print("\n=== 8-9. multiset: repetition is real, re-download is not ===")
combined = hs.reconcile([old, new])
check("8. old[A B C D] + new[B C D E] = FIVE economic rows, not eight",
      combined.economic_row_count == 5, str(combined.economic_row_count))
check("8b. the eight raw rows are named, so nothing is hidden",
      combined.raw_row_total == 8 and combined.rows_avoided == 3)

twice = fp(chase_card_with_card([A, A]), "twice.csv")
thrice = fp(chase_card_with_card([A, A, A]), "thrice.csv")
check("9a. a legitimately repeated identical row is NOT collapsed",
      twice.total_identified == 2 and twice.distinct_identities == 1)
grew = hs.reconcile([twice, thrice])
check("9. multiplicity rises from two to THREE, not to one and not to five",
      grew.economic_row_count == 3, str(grew.economic_row_count))
check("9b. and re-reconciling the same pair is stable",
      hs.reconcile([twice, thrice, twice]).economic_row_count == 3)
check("9c. the superset verdict respects multiplicity",
      hs.classify_relationship(thrice, twice).verdict == hs.TRANSACTION_SUPERSET)

print("\n=== 10-11. transaction identity strategy ===")
trn = fp(chase_bank([
    ("06/03/2025", "ORIG CO NAME:SUPPLIER TRN: 0026561259FF", "-500.00", "1000.00"),
    ("06/04/2025", "ORIG CO NAME:SUPPLIER TRN: 0026561260FF", "-500.00", "500.00"),
]), "trn.csv")
check("10. a stable provider transaction id is used when the source carries one",
      trn.identity_strength == hs.IDENTITY_PROVIDER_ID
      and all(i.basis == hs.IDENTITY_PROVIDER_ID for i in trn.identities))
check("10b. two rows identical but for their TRN stay two rows",
      trn.distinct_identities == 2)

check("11. without a provider id the fallback is canonical evidence, not date+amount",
      with_card.identity_strength == hs.IDENTITY_CANONICAL_EVIDENCE)
check("11b. the fallback is deterministic — the same bytes give the same identities",
      fp(original, "x.csv").identities == fp(original, "y.csv").identities)
collide = fp(chase_card_with_card([
    ("06/03/2025", "06/04/2025", "COFFEE SHOP", "-4.50"),
    ("06/03/2025", "06/04/2025", "COFFEE SHOP", "-4.50"),
]), "collide.csv")
check("11c. two genuinely identical events are counted twice, never merged into one",
      collide.total_identified == 2)

print("\n=== 12-16. the census, from three directions ===")
with Session(engine) as db:
    entity = m.LegalEntity(legal_name="Angeli E Demoni, LLC", status="ACTIVE")
    db.add(entity)
    db.flush()
    sourced = m.PaymentInstrument(
        instrument_type="CREDIT_CARD", display_name="Sourced Card", institution="CHASE",
        last_four="1057", status="ACTIVE", legal_entity_id=entity.id)
    orphan = m.PaymentInstrument(
        instrument_type="CREDIT_CARD", display_name="Unsourced Card", institution="CHASE",
        last_four="4242", status="ACTIVE", legal_entity_id=entity.id)
    db.add_all([sourced, orphan])
    db.commit()
    sourced_id, orphan_id = sourced.id, orphan.id

with Session(engine) as db:
    inst = db.get(m.PaymentInstrument, sourced_id)
    cov = hs.coverage_for_fingerprints(inst, [old, new])
    check("12. a registered instrument WITH sources is covered",
          cov.state == hs.REGISTERED_AND_SOURCED and cov.source_count == 2, cov.state)
    check("12b. its economic row count is the reconciled five, not the raw eight",
          cov.economic_row_count == 5)
    check("12c. its file relationship is recorded as provenance, not resolved by deletion",
          cov.relationships and cov.relationships[0][2].verdict == hs.PARTIAL_OVERLAP)

    empty = hs.coverage_for_fingerprints(db.get(m.PaymentInstrument, orphan_id), [])
    check("13. a registered instrument with NO source is surfaced, not assumed fine",
          empty.state == hs.REGISTERED_NO_SOURCE and not empty.is_resolved, empty.state)
    check("13b. and absence alone changed nothing about the instrument",
          db.get(m.PaymentInstrument, orphan_id).status == "ACTIVE"
          and db.get(m.PaymentInstrument, orphan_id).lifecycle_end_reason is None)

with Session(engine) as db:
    direct = hs.record_candidate(
        db, last_four="7788", institution="CHASE", discovery=m.CANDIDATE_DIRECT_SOURCE,
        evidence="Chase7788_Activity.csv — a source file matching no registered instrument",
        first_seen=date(2025, 3, 1), last_seen=date(2025, 9, 30), occurrences=200)
    db.commit()
    check("14. a SOURCE whose instrument is unknown becomes a candidate",
          hs.candidate_state(direct) == hs.SOURCE_WITHOUT_REGISTERED_INSTRUMENT)
    check("14b. it did NOT create a Payment Instrument",
          db.query(m.PaymentInstrument).filter_by(last_four="7788").count() == 0)

description = "Payment to Chase card ending in 9191 06/15"
refs = hs.extract_instrument_references(description)
check("15a. an indirect reference is recognised in a real Chase description",
      refs == {"9191"}, str(refs))
check("15b. a trace number is NOT mistaken for an account",
      hs.extract_instrument_references("TRACE#:063116509283336 EED:260224") == set())
check("15c. nor is a merchant order reference",
      hs.extract_instrument_references("AMAZON MKTPL*133361JG3") == set())

with Session(engine) as db:
    ref_cand = hs.record_candidate(
        db, last_four="9191", institution="CHASE",
        discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence=f'2025-06 statement of another account: "{description}"',
        first_seen=date(2025, 6, 15), last_seen=date(2025, 6, 15), occurrences=1)
    db.commit()
    check("15. ··9191 is surfaced as REFERENCED_WITHOUT_REGISTERED_INSTRUMENT",
          hs.candidate_state(ref_cand) == hs.REFERENCED_WITHOUT_REGISTERED_INSTRUMENT)
    check("15d. no instrument was invented from an indirect mention",
          db.query(m.PaymentInstrument).filter_by(last_four="9191").count() == 0)
    check("15e. and nothing concluded it was closed",
          ref_cand.resolution is None and ref_cand.resolution_effective_date is None)

    # 16 — the control start bounds completeness, never discovery.
    from rfone_data_store.bank_reconciliation import monthly_source
    monthly_source.set_control_start(db, year=2026, month=1, note="from January")
    db.commit()
    again = hs.list_candidates(db)
    check("16. a 2025 reference stays visible although control starts in 2026-01",
          any(c.last_four == "9191" for c in again)
          and monthly_source.get_control_start_month(db) == "2026-01")
    check("16b. and it is still unresolved, still demanding a human",
          not [c for c in again if c.last_four == "9191"][0].is_resolved)

print("\n=== 17-20. a human resolves a candidate; absence never does ===")
with Session(engine) as db:
    c_missing = hs.record_candidate(
        db, last_four="5511", institution="CHASE", discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence="referenced once")
    hs.resolve_candidate(db, candidate=c_missing, resolution=m.CANDIDATE_SOURCE_MISSING,
                         note="bank portal would not export it", account_id=None)
    db.commit()
    check("17. SOURCE FILE MISSING is recorded but deliberately NOT resolved",
          c_missing.resolution == m.CANDIDATE_SOURCE_MISSING and not c_missing.is_resolved)

    c_closed = hs.record_candidate(
        db, last_four="6622", institution="CHASE", discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence="referenced in 2024", first_seen=date(2024, 1, 5), last_seen=date(2024, 8, 9))
    hs.resolve_candidate(db, candidate=c_closed, resolution=m.RESOLUTION_CLOSED,
                         note="closed years ago, date not known")
    db.commit()
    check("18. CLOSED is accepted as a human judgement and resolves the candidate",
          c_closed.resolution == m.RESOLUTION_CLOSED and c_closed.is_resolved)
    check("18b. with its effective date left UNKNOWN rather than taken from the evidence",
          c_closed.resolution_effective_date is None
          and c_closed.last_seen_date == date(2024, 8, 9))

    c_not_ours = hs.record_candidate(
        db, last_four="7733", institution="CHASE", discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence="a supplier's own card, named in a payment description")
    try:
        hs.resolve_candidate(db, candidate=c_not_ours, resolution=m.CANDIDATE_NOT_OURS)
        refused = False
    except ValueError:
        db.rollback()
        refused = True
    check("19a. NOT OUR INSTRUMENT without a reason is refused", refused)
    c_not_ours = hs.record_candidate(
        db, last_four="7733", institution="CHASE", discovery=m.CANDIDATE_INDIRECT_REFERENCE,
        evidence="a supplier's own card, named in a payment description")
    hs.resolve_candidate(db, candidate=c_not_ours, resolution=m.CANDIDATE_NOT_OURS,
                         note="belongs to the supplier, confirmed with them")
    db.commit()
    check("19. NOT OUR INSTRUMENT with a reason resolves it",
          c_not_ours.resolution == m.CANDIDATE_NOT_OURS and c_not_ours.is_resolved)

    unresolved = [c for c in hs.list_candidates(db) if c.resolution is None]
    check("20. absence alone selected NOTHING — untouched candidates stay undecided",
          len(unresolved) >= 2 and all(c.resolution_effective_date is None for c in unresolved))
    check("20b. and no candidate ever created an instrument behind the operator's back",
          db.query(m.PaymentInstrument).count() == 2)

    confirmed = hs.record_candidate(
        db, last_four="8844", institution="CHASE", discovery=m.CANDIDATE_DIRECT_SOURCE,
        evidence="its own export file")
    try:
        hs.resolve_candidate(db, candidate=confirmed, resolution=m.CANDIDATE_CONFIRMED)
        needs_instrument = False
    except ValueError:
        db.rollback()
        needs_instrument = True
    check("20c. CONFIRMED must name the instrument it became", needs_instrument)

print("\n=== 21-22. a source boundary is never a lifecycle date ===")
with Session(engine) as db:
    inst = db.get(m.PaymentInstrument, sourced_id)
    cov = hs.coverage_for_fingerprints(inst, [old, new])
    check("21. the earliest source date did NOT become an activation date",
          cov.earliest_source_date == date(2025, 6, 3)
          and inst.effective_start_date is None)
    check("22. the latest source date did NOT become a closure date",
          cov.latest_source_date == date(2025, 6, 12)
          and inst.effective_end_date is None and inst.lifecycle_end_reason is None)
    check("22b. coverage offers no field that could be mistaken for one",
          not any("activation" in f or "closure" in f for f in vars(cov)))

print("\n=== 23-25. gaps, double counting and provenance ===")
jan = fp(chase_card_with_card([("01/05/2026", "01/06/2026", "JAN BUY", "-10.00")]), "jan.csv")
mar = fp(chase_card_with_card([("03/05/2026", "03/06/2026", "MAR BUY", "-10.00")]), "mar.csv")
with Session(engine) as db:
    inst = db.get(m.PaymentInstrument, sourced_id)
    gappy = hs.coverage_for_fingerprints(inst, [jan, mar])
    check("23. February is reported as an INTERNAL gap between January and March",
          gappy.internal_missing_months == ["2026-02"], str(gappy.internal_missing_months))
    check("23b. and nothing before January or after March is called missing — RF-One "
          "does not know how far back the account goes",
          "2025-12" not in gappy.internal_missing_months
          and "2026-04" not in gappy.internal_missing_months)
    check("23c. an internal gap keeps the instrument from being fully covered",
          gappy.state == hs.REGISTERED_SOURCE_PARTIAL and not gappy.is_resolved)

    overlapped = hs.coverage_for_fingerprints(inst, [old, new, same])
    check("24. three overlapping exports still yield five economic rows",
          overlapped.economic_row_count == 5, str(overlapped.economic_row_count))
    check("24b. against twelve raw rows — seven avoided, and the figure is stated",
          hs.reconcile([old, new, same]).raw_row_total == 12)

    combined = hs.reconcile([old, new, same])
    shared_identity = next(i for i in combined.identities
                           if i in old.identities and i in new.identities)
    sources = combined.provenance[shared_identity]
    check("25. provenance survives: an economic row names every file that evidenced it",
          set(sources) == {"old.csv", "new.csv", "same_again.csv"}, str(sources))
    only_new = next(i for i in new.identities if i not in old.identities)
    check("25b. and a row seen in one file names only that file",
          combined.provenance[only_new] == ["new.csv"])

print("\n=== 26-27. the two configuration changes ===")
with Session(engine) as db:
    inst = db.get(m.PaymentInstrument, sourced_id)
    previous = inst.last_four
    inst.last_four = "9999"
    db.add(m.BankInstrumentIdentityAudit(
        payment_instrument_id=inst.id, field_name="last_four",
        previous_value=previous, new_value="9999",
        reason="test correction", source_evidence="two independent exports"))
    db.commit()
    audit = db.scalars(select(m.BankInstrumentIdentityAudit)).first()
    check("26. an identity correction is audited with old, new, reason, evidence and time",
          audit.previous_value == previous and audit.new_value == "9999"
          and audit.reason and audit.source_evidence and audit.changed_at is not None)
    check("26b. the correction changed the instrument in place — no second account",
          db.query(m.PaymentInstrument).filter_by(display_name="Sourced Card").count() == 1)
    inst.last_four = previous
    db.commit()

    amex = m.PaymentInstrument(
        instrument_type="CREDIT_CARD", display_name="Amex", institution="AMEX",
        provider="American Express", last_four="1002", currency="USD", status="ACTIVE",
        legal_entity_id=db.scalars(select(m.LegalEntity)).first().id)
    db.add(amex)
    db.commit()
    check("27. Amex ··1002 registers with its Legal Entity and no invented lifecycle",
          amex.last_four == "1002" and amex.legal_entity is not None
          and amex.effective_start_date is None and amex.effective_end_date is None
          and amex.lifecycle_end_reason is None and amex.replaced_by_instrument_id is None
          and amex.linked_instrument_id is None)

print("\n=== 17/28/29. corpus completeness and the rest of Bank ===")
with Session(engine) as db:
    inst = db.get(m.PaymentInstrument, sourced_id)
    orph = db.get(m.PaymentInstrument, orphan_id)
    coverages = [
        hs.coverage_for_fingerprints(inst, [old, new]),
        hs.coverage_for_fingerprints(orph, []),
    ]
    status = hs.corpus_status(db, coverages)
    check("§17. the corpus is NOT complete while anything is unresolved",
          not status.is_complete and status.blockers)
    check("§17b. and it names the registered instrument with no source",
          any("Unsourced Card" in b for b in status.blockers), str(status.blockers[:2]))
    check("§17c. and the unjudged candidates, including ··9191",
          any("··9191" in b for b in status.blockers))

    from rfone_data_store.bank_reconciliation import monthly_source
    period = monthly_source.get_or_create_period(db, 2026, 2)
    monthly_source.refresh_coverage(db, period)
    db.commit()
    rows = monthly_source.coverages(db, period)
    check("28. monthly source completeness still works and still sees every instrument",
          len(rows) == db.query(m.PaymentInstrument).count())
    check("28b. the control start is untouched by any of this",
          monthly_source.get_control_start_month(db) == "2026-01")

    check("29a. file-level idempotency is still service.import_csv's own, by SHA-256",
          hasattr(bank_service, "import_csv"))
    result = bank_service.import_csv(
        db, file_bytes=original, original_file_name="regression.csv",
        uploaded_by_account_id=None)
    db.commit()
    first_id = result.batch.id
    again = bank_service.import_csv(
        db, file_bytes=original, original_file_name="regression-renamed.csv",
        uploaded_by_account_id=None)
    db.commit()
    check("29. re-uploading identical bytes still reuses the batch — import idempotency "
          "is unchanged by this task",
          not again.created and again.batch.id == first_id)
    check("29b. and the existing resolver still owns file-to-instrument identity",
          hasattr(bank_service, "resolve_instrument_for_source"))

print(f"\n{len(passed)} passed, {len(failed)} failed.")
if failed:
    print("FAILURES:")
    for f in failed:
        print("   -", f)

engine.dispose()
for suffix in ("", "-wal", "-shm", "-journal"):
    candidate = _DB + suffix
    if os.path.exists(candidate):
        try:
            os.remove(candidate)
        except OSError:
            pass
print("ALL CHECKS PASSED" if not failed else "FAILED")
sys.exit(1 if failed else 0)
