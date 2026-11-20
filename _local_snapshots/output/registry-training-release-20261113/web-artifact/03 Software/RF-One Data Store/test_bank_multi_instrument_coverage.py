#!/usr/bin/env python
"""Multi-instrument source coverage — BANK_MULTI_INSTRUMENT_SOURCE_COVERAGE_001.

Proves, on a throwaway database, the approved received-source rule:

    SOURCE RECEIVED = a batch assigned to the instrument covers the month
                      OR (only when there is none) a batch with no single
                      instrument contains a raw row, linked to a transaction
                      of that instrument whose posting_date is in the month.

* direct evidence always wins and is never replaced;
* the fallback is proven through RAW-ROW lineage, not through
  `FinancialTransaction.import_batch_id`;
* a duplicate/suppressed transaction still proves the source, and its
  accounting fields are not touched;
* a NULL posting date proves no month; a file without a row for the
  instrument proves nothing for it;
* several qualifying files → the lowest batch id, the existing convention.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import monthly_source as ms
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

MARCH = date(2026, 3, 10)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    url = resolve_test_database_url("bank_multi_instrument_coverage")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            le = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
            s.add(le)
            s.flush()

            def card(name, last_four):
                inst = m.PaymentInstrument(instrument_type="CREDIT_CARD", display_name=name,
                                           institution="Chase", last_four=last_four,
                                           legal_entity_id=le.id, status="ACTIVE")
                s.add(inst)
                s.flush()
                return inst

            direct_card, multi_card, absent_card, dup_card, undated_card = (
                card("Direct Card", "1111"), card("Multi Card", "2222"), card("Absent Card", "3333"),
                card("Dup Card", "4444"), card("Undated Card", "5555"))

            def batch(n, instrument, start, end):
                b = m.BankImportBatch(detected_format="CHASE_CREDIT_CARD_WITH_CARD",
                                      original_file_name=f"f{n}.csv", raw_file_bytes=b"x",
                                      sha256=f"{n:064d}", status="NORMALIZED",
                                      payment_instrument_id=instrument.id if instrument else None,
                                      date_range_start=start, date_range_end=end)
                s.add(b)
                s.flush()
                return b

            direct = batch(1, direct_card, date(2026, 3, 1), date(2026, 3, 31))
            multi_1 = batch(2, None, date(2026, 3, 1), date(2026, 4, 30))
            multi_2 = batch(3, None, date(2026, 3, 1), date(2026, 5, 31))

            row_numbers = {}

            def raw(b, txn):
                row_numbers[b.id] = row_numbers.get(b.id, 0) + 1
                s.add(m.RawBankTransaction(import_batch_id=b.id, row_number=row_numbers[b.id],
                                           raw_fields={}, row_fingerprint=f"{b.id}-{row_numbers[b.id]}",
                                           parse_status="PARSED", normalized_transaction_id=txn.id))

            def txn(instrument, created_by, posting, fp, **extra):
                t = m.FinancialTransaction(payment_instrument_id=instrument.id, posting_date=posting,
                                           transaction_date=MARCH, description_original="x",
                                           amount_minor=-100, status="COMPLETED",
                                           classification="UNKNOWN", import_batch_id=created_by.id,
                                           fingerprint=fp, **extra)
                s.add(t)
                s.flush()
                return t

            # 1 — direct card: direct batch AND a multi-card row in March.
            t_direct = txn(direct_card, direct, MARCH, "d:0")
            raw(direct, t_direct)
            raw(multi_1, t_direct)
            # 2/5/8 — multi card: one transaction FIRST CREATED by multi_2, also
            # present in multi_1 (overlap); a May-only row exists only in multi_2.
            t_multi = txn(multi_card, multi_2, MARCH, "m:0")
            raw(multi_2, t_multi)
            raw(multi_1, t_multi)
            t_may = txn(multi_card, multi_2, date(2026, 5, 3), "m:1")
            raw(multi_2, t_may)
            # 6 — a real source row whose transaction is a suppressed duplicate.
            t_dup = txn(dup_card, multi_1, MARCH, "u:0", accounting_status="DUPLICATE_SUPPRESSED",
                        duplicate_status="CONFIRMED_DUPLICATE")
            raw(multi_1, t_dup)
            # 7 — a row whose transaction has no posting date.
            t_undated = txn(undated_card, multi_1, None, "n:0")
            raw(multi_1, t_undated)
            s.commit()
            dup_before = (t_dup.accounting_status, t_dup.duplicate_status, t_dup.status)
            txn_count = s.scalar(select(func.count(m.FinancialTransaction.id)))

            def coverage(period, instrument):
                return next(c for c in ms.coverages(s, period) if c.payment_instrument_id == instrument.id)

            march = ms.get_or_create_period(s, 2026, 3)
            ms.refresh_coverage(s, march)
            s.commit()

            c = coverage(march, direct_card)
            check("1. direct evidence remains credited", c.source_received and c.import_batch_id == direct.id,
                  str(c.import_batch_id))
            check("1b. multi-card evidence does not replace it",
                  c.import_batch_id != multi_1.id)

            c = coverage(march, multi_card)
            check("2. no direct batch, rows in a multi-card file → source received", c.source_received)
            check("8. several qualifying multi-card files → the lowest batch id (existing convention)",
                  c.import_batch_id == multi_1.id, str(c.import_batch_id))
            check("5. raw-row lineage finds the file even though the transaction was first created by "
                  "another batch", t_multi.import_batch_id == multi_2.id and c.import_batch_id == multi_1.id)
            check("5b. the overlapping copies are one transaction, not two",
                  s.scalar(select(func.count(m.FinancialTransaction.id))
                           .where(m.FinancialTransaction.payment_instrument_id == multi_card.id)) == 2)

            c = coverage(march, absent_card)
            check("4. a multi-card file with no row for the instrument proves nothing for it",
                  not c.source_received and c.import_batch_id is None)

            c = coverage(march, dup_card)
            s.refresh(t_dup)
            check("6. a row whose transaction is a suppressed duplicate still proves the source",
                  c.source_received and c.import_batch_id == multi_1.id)
            check("6b. and its accounting / duplicate / status fields are untouched",
                  (t_dup.accounting_status, t_dup.duplicate_status, t_dup.status) == dup_before)

            c = coverage(march, undated_card)
            check("7. a transaction with no posting date proves no month (no fallback date)",
                  not c.source_received)

            april = ms.get_or_create_period(s, 2026, 4)
            ms.refresh_coverage(s, april)
            may = ms.get_or_create_period(s, 2026, 5)
            ms.refresh_coverage(s, may)
            s.commit()
            check("8b. a month with rows only in the second file credits that file",
                  coverage(may, multi_card).import_batch_id == multi_2.id)
            check("2b. a month in a multi-card file's range with no row for the instrument is not credited",
                  not coverage(april, multi_card).source_received)

            report = ms.evaluate(s, march)
            check("evaluate: the credited instruments are no longer blockers",
                  not any(("Multi Card" in b or "Dup Card" in b or "Direct Card" in b) for b in report.blockers)
                  and any("Absent Card" in b for b in report.blockers), str(report.blockers))

            before = [(x.id, x.import_batch_id) for x in ms.coverages(s, march)]
            ms.refresh_coverage(s, march)
            s.commit()
            check("refresh is idempotent", [(x.id, x.import_batch_id) for x in ms.coverages(s, march)] == before)
            check("no transaction was created or removed",
                  s.scalar(select(func.count(m.FinancialTransaction.id))) == txn_count)
    finally:
        engine.dispose()

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
