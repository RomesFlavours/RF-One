#!/usr/bin/env python
"""Mercury transactions export in Bank (BANK_MERCURY_CSV_001).

Runs on a disposable SQLite database through the real services. Never touches
AWS, RDS or a production database. Optional: MERCURY_SAMPLE=<path to a real
Mercury export> also parses that file (read-only).

    python test_bank_mercury_csv.py
"""
from __future__ import annotations

import os
import sys

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import parsers
from rfone_data_store.bank_reconciliation import service as bank_service
from rfone_data_store.database import (
    create_configured_engine, create_session_factory, redact_database_url,
)

MERCURY_HEAD = ("Date (UTC),Description,Amount,Status,Source Account,Bank Description,Reference,Note,"
                "Last Four Digits,Name On Card,Merchant Type,Category,Source of Category,GL Code,"
                "Source of GL Code,Timestamp,Original Currency,Check Number,Cardholder Email,Tracking ID,"
                "Failure Reason\n")


def mercury_row(date, desc, amount, status="Sent", note="", reference="", tracking="", failure="", time="12:00:00"):
    return (f"{date},\"{desc}\",{amount},{status},Mercury Checking xx6667,,\"{reference}\",\"{note}\","
            f",,,,,,,{date} {time},,,,{tracking},\"{failure}\"\n")


SAMPLE = (MERCURY_HEAD
          + mercury_row("09-22-2026", "Chase - Checking xx3583", "2000.00", tracking="121145431780533")
          + mercury_row("10-01-2026", "Sysco Central Florida", "-1250.40", note="Produce invoice 4471",
                        tracking="900000000000001")
          + mercury_row("10-02-2026", "Jordan Example", "-180.00", reference="Tips week 39",
                        tracking="900000000000002")
          + mercury_row("10-03-2026", "Acme Linen", "-95.00", status="Failed", note="Linen",
                        tracking="900000000000003", failure="Account closed")
          + mercury_row("10-04-2026", "Office Depot", "-42.10")
          + mercury_row("10-05-2026", "Payroll Partner", "-300.00", status="Pending", tracking="900000000000005")
          # 02:30 UTC on 1 November is 10:30 pm on 31 October in Florida.
          + mercury_row("11-01-2026", "Late Supplier", "-75.00", tracking="900000000000006", time="02:30:00")).encode()


def main() -> int:
    passed, failed = [], []

    def check(label, ok, detail=""):
        (passed if ok else failed).append(label)
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok or not detail else f" ({detail})"))

    # --- Parser ---------------------------------------------------------------
    parsed = parsers.parse_csv_bytes(SAMPLE)
    rows = parsed.rows
    check("Mercury export recognized as MERCURY", parsed.detected_format == parsers.MERCURY, parsed.detected_format)
    check("7 rows read, none unreadable", len(rows) == 7 and not [r for r in rows if r.parse_status == "UNREADABLE"],
          [(r.row_number, r.parse_status, r.anomalies) for r in rows])
    r0, r1, r2, r3, r4, r5, r6 = rows
    check("pending payment kept but flagged: not settled yet",
          r5.parse_status == "ANOMALOUS" and any("not settled" in a for a in r5.anomalies), (r5.parse_status, r5.anomalies))
    check("a sent payment is not flagged", r1.parse_status == "PARSED" and not r1.anomalies, r1.anomalies)
    check("dates are Florida time: 02:30 UTC on 1 Nov is 31 Oct", str(r6.posting_date) == "2026-10-31", r6.posting_date)
    check("midday UTC keeps its own day", str(r1.posting_date) == "2026-10-01", r1.posting_date)
    no_stamp = dict(r1.raw_fields, Timestamp="")
    check("no Timestamp: falls back to Date (UTC)",
          str(parsers.parse_row_fields(parsers.MERCURY, 2, no_stamp).posting_date) == "2026-10-01")
    check("date 09-22-2026 and +2000.00 read as 2026-09-22 and 200000 cents",
          str(r0.posting_date) == "2026-09-22" and r0.amount_minor == 200000, (r0.posting_date, r0.amount_minor))
    check("money out stays negative", r1.amount_minor == -125040, r1.amount_minor)
    check("the payment's Note is the reason (purpose)",
          r1.source_memo == "Produce invoice 4471" and r1.source_memo_field == "Note", (r1.source_memo, r1.source_memo_field))
    check("no Note: the Reference sent with the payment is the reason",
          r2.source_memo == "Tips week 39" and r2.source_memo_field == "Reference", (r2.source_memo, r2.source_memo_field))
    check("no Note and no Reference: no reason invented", r4.source_memo is None and r4.source_memo_field is None)
    check("Tracking ID kept as the transaction's identifier", r1.reference == "900000000000001", r1.reference)
    check("account read from Source Account on every row, last four 6667",
          all(bank_service.extract_last_four(r.account_hint) == "6667" for r in rows))
    check("failed payment kept but flagged: the money did not move",
          r3.parse_status == "ANOMALOUS" and any("did not move" in a for a in r3.anomalies), (r3.parse_status, r3.anomalies))
    check("re-reading a stored row gives the same result",
          parsers.parse_row_fields(parsers.MERCURY, r1.row_number, r1.raw_fields).source_memo == "Produce invoice 4471")

    extra = SAMPLE.replace(b"Failure Reason\n", b"Failure Reason,Tags\n", 1)
    check("a Mercury export with an extra column is still recognized",
          parsers.parse_csv_bytes(extra).detected_format == parsers.MERCURY)

    chase = b"Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\nDEBIT,09/02/2026,\"X\",-1.00,ACH_DEBIT,10.00,,\n"
    fc = b"Account Number,Post Date,Check,Description,Debit,Credit,Status,Balance\n123,09/02/2026,,X,1.00,,Posted,10.00\n"
    check("Chase and First Citizens files are recognized exactly as before",
          parsers.parse_csv_bytes(chase).detected_format == parsers.CHASE_BANK_ACCOUNT
          and parsers.parse_csv_bytes(fc).detected_format == parsers.FIRST_CITIZENS)
    try:
        parsers.parse_csv_bytes(b"Date,Amount\n09-22-2026,1.00\n")
        check("an unknown file is still refused", False)
    except parsers.UnrecognizedFormatError:
        check("an unknown file is still refused", True)

    sample_path = os.environ.get("MERCURY_SAMPLE")
    if sample_path:
        real = parsers.parse_csv_bytes(open(sample_path, "rb").read())
        check("the real Mercury export parses with no unreadable rows",
              real.detected_format == parsers.MERCURY and all(r.parse_status != "UNREADABLE" for r in real.rows),
              (real.detected_format, len(real.rows)))

    # --- Upload page: which account the file belongs to -----------------------
    from rfone_data_store.bank_reconciliation import import_session
    ident = import_session.identify_file("rf-one-transactions-to-2026-nov-20.csv", SAMPLE)
    check("upload page takes the account from inside the file (6667), not the date in the name (2026)",
          ident.account_digits == "6667" and ident.institution == "Mercury", (ident.account_digits, ident.institution))
    prefill = import_session.source_prefill(ident.kind, ident.institution, ident.instrument_type, ident.account_digits)
    check("new-source suggestion reads Mercury ..6667", "6667" in prefill.get("display_name", "") and "2026" not in prefill.get("display_name", ""),
          prefill)
    chase_ident = import_session.identify_file("Chase3583_Activity_20261120.CSV",
        b"Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\nDEBIT,09/02/2026,\"X\",-1.00,ACH_DEBIT,10.00,,\n")
    check("Chase file names still give their account digits (3583)", chase_ident.account_digits == "3583", chase_ident.account_digits)
    two = SAMPLE.replace(b"Office Depot\",-42.10,Sent,Mercury Checking xx6667", b"Office Depot\",-42.10,Sent,Mercury Savings xx1234", 1)
    check("a file covering two Mercury accounts suggests no single account",
          import_session.identify_file("x.csv", two).account_digits is None)

    # --- Import through the real service on a disposable database -------------
    import tempfile, pathlib
    url = "sqlite:///" + pathlib.Path(tempfile.mkdtemp(prefix="bank-mercury-"), "t.db").as_posix()
    print(f"Database URL: {redact_database_url(url)}")
    # The AWS-era migrations are PostgreSQL-only, so the disposable SQLite schema
    # comes from the models (which carry the widened MERCURY check). The migration
    # itself is checked separately as offline PostgreSQL SQL.
    engine = create_configured_engine(url)
    m.Base.metadata.create_all(engine)
    with create_session_factory(engine)() as s:
        le = m.LegalEntity(legal_name="Angeli e Demoni LLC", status="ACTIVE")
        s.add(le); s.flush()
        inst = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Mercury Checking",
                                   institution="Mercury", last_four="6667", legal_entity_id=le.id, status="ACTIVE")
        s.add(inst); s.commit()
        result = bank_service.import_csv(s, file_bytes=SAMPLE, original_file_name="rf-one-transactions-to-2026-nov-20.csv",
                                         uploaded_by_account_id=None, payment_instrument_id=inst.id)
        s.commit()
        batch = result.batch
        check("the import batch is stored with format MERCURY (database allows it)",
              batch.detected_format == parsers.MERCURY, batch.detected_format)
        txns = s.query(m.FinancialTransaction).filter_by(import_batch_id=batch.id).all()
        check("transactions are stored on the Mercury account", txns and all(t.payment_instrument_id == inst.id for t in txns),
              len(txns))
        sysco = [t for t in txns if (t.description_original or "").startswith("Sysco")]
        check("the reason is saved on the transaction (Note)",
              len(sysco) == 1 and sysco[0].source_memo == "Produce invoice 4471" and sysco[0].source_memo_field == "Note",
              [(t.description_original, t.source_memo, t.source_memo_field) for t in sysco])
        tips = [t for t in txns if (t.description_original or "").startswith("Jordan")]
        check("the reason is saved on the transaction (Reference)",
              len(tips) == 1 and tips[0].source_memo == "Tips week 39" and tips[0].source_memo_field == "Reference")
        late = [t for t in txns if (t.description_original or "").startswith("Late Supplier")]
        check("the late-evening payment is stored on 31 October",
              len(late) == 1 and str(late[0].posting_date) == "2026-10-31", [str(t.posting_date) for t in late])
        matches = import_session.matching_sources(s, ident)
        check("upload page finds the configured Mercury account for the file",
              [i.id for i in matches] == [inst.id], [i.id for i in matches])
        again = bank_service.import_csv(s, file_bytes=SAMPLE, original_file_name="copy.csv",
                                        uploaded_by_account_id=None, payment_instrument_id=inst.id)
        check("importing the same file again creates nothing new", again.batch.id == batch.id)
        resolved = bank_service.resolve_instrument_for_file(s, parsers.MERCURY, "rf-one-transactions-to-2026-nov-20.csv", parsed) \
            if hasattr(bank_service, "resolve_instrument_for_file") else None
        if resolved is not None:
            print("  info  automatic account match:", getattr(resolved, "detail", resolved))
    engine.dispose()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
