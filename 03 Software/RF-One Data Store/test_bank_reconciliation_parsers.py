#!/usr/bin/env python
"""Pure parser tests for Bank Reconciliation manual CSV import (spec §3).

No database — mirrors `test_payroll_engine.py`'s standalone `main()`
convention but needs no disposable database at all, since
`rfone_data_store.bank_reconciliation.parsers` never touches SQLAlchemy.

Usage:
    python test_bank_reconciliation_parsers.py
"""

from __future__ import annotations

import sys
from datetime import date

from rfone_data_store.bank_reconciliation import parsers

CHASE_BANK_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,04/05/2026,AMAZON MKTPLACE,-24.05,ACH_DEBIT,1523.10,\n"
    "CREDIT,04/06/2026,DEPOSIT,500.00,DEPOSIT,2023.10,\n"
)

CHASE_BANK_CSV_WITH_EMPTY_TRAILING_COLUMN = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,04/05/2026,AMAZON MKTPLACE,-24.05,ACH_DEBIT,1523.10,,\n"
)

CHASE_BANK_CSV_WITH_NONEMPTY_TRAILING_COLUMN = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,04/05/2026,AMAZON MKTPLACE,-24.05,ACH_DEBIT,1523.10,,UNEXPECTED\n"
)

CHASE_CARD_WITH_CARD_CSV = (
    "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "1057,07/29/2026,07/30/2026,UBER *TRIP,Travel,Sale,-3.00,\n"
    "1057,07/29/2026,07/30/2026,UBER *TRIP,Travel,Sale,-3.00,\n"
)

CHASE_CARD_NO_CARD_CSV = (
    "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "03/30/2026,03/31/2026,PY *WINE BY GEORGE,Shopping,Sale,-14.18,\n"
)

FIRST_CITIZENS_CSV = (
    "Account Number,Post Date,Check,Description,Debit,Credit,Status,Balance\n"
    "7470,08/01/2026,,PAYROLL DEPOSIT,,1200.00,Posted,4400.00\n"
    "7470,08/02/2026,101,CHECK PAYMENT,300.00,,Posted,4100.00\n"
)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    # -----------------------------------------------------------------
    # Layout 1: Chase bank account
    # -----------------------------------------------------------------
    parsed = parsers.parse_csv_bytes(CHASE_BANK_CSV.encode("utf-8"))
    check("Chase bank account: format detected", parsed.detected_format == parsers.CHASE_BANK_ACCOUNT)
    check("Chase bank account: 2 rows parsed", len(parsed.rows) == 2)
    row = parsed.rows[0]
    check("Chase bank account: PARSED status", row.parse_status == "PARSED", row.anomalies)
    check("Chase bank account: posting date", row.posting_date == date(2026, 4, 5))
    check("Chase bank account: signed amount preserved (-24.05 -> -2405)", row.amount_minor == -2405)
    check("Chase bank account: positive amount (500.00 -> 50000)", parsed.rows[1].amount_minor == 50000)
    check("Chase bank account: balance parsed", row.balance_minor == 152310)
    check("Chase bank account: no account hint in file", row.account_hint is None)
    check("Chase bank account: raw_fields preserves all original columns", set(row.raw_fields) == {
        "Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #",
    })

    # -----------------------------------------------------------------
    # Trailing undeclared column — empty must be ignored, non-empty flagged
    # -----------------------------------------------------------------
    parsed_empty_trailing = parsers.parse_csv_bytes(CHASE_BANK_CSV_WITH_EMPTY_TRAILING_COLUMN.encode("utf-8"))
    check(
        "Trailing column empty: not flagged, row still PARSED",
        not parsed_empty_trailing.extra_trailing_column_seen and parsed_empty_trailing.rows[0].parse_status == "PARSED",
    )
    parsed_nonempty_trailing = parsers.parse_csv_bytes(CHASE_BANK_CSV_WITH_NONEMPTY_TRAILING_COLUMN.encode("utf-8"))
    check(
        "Trailing column non-empty: flagged as an anomaly, never silently ignored",
        parsed_nonempty_trailing.extra_trailing_column_seen
        and any("trailing column" in a for a in parsed_nonempty_trailing.rows[0].anomalies),
    )

    # -----------------------------------------------------------------
    # Layout 2: Chase credit card, Variant A (with Card)
    # -----------------------------------------------------------------
    parsed = parsers.parse_csv_bytes(CHASE_CARD_WITH_CARD_CSV.encode("utf-8"))
    check("Chase card (with Card): format detected", parsed.detected_format == parsers.CHASE_CREDIT_CARD_WITH_CARD)
    check("Chase card (with Card): account_hint = Card value", parsed.rows[0].account_hint == "1057")
    check("Chase card (with Card): transaction_date distinct from posting_date",
          parsed.rows[0].transaction_date == date(2026, 7, 29) and parsed.rows[0].posting_date == date(2026, 7, 30))
    check("Chase card (with Card): both identical rows preserved (not collapsed by the parser)", len(parsed.rows) == 2)

    # -----------------------------------------------------------------
    # Layout 3: Chase credit card, Variant B (no Card)
    # -----------------------------------------------------------------
    parsed = parsers.parse_csv_bytes(CHASE_CARD_NO_CARD_CSV.encode("utf-8"))
    check("Chase card (no Card): format detected", parsed.detected_format == parsers.CHASE_CREDIT_CARD_NO_CARD)
    check("Chase card (no Card): no account hint available", parsed.rows[0].account_hint is None)
    check("Chase card (no Card): amount", parsed.rows[0].amount_minor == -1418)

    # -----------------------------------------------------------------
    # Layout 4: First Citizens — Amount = Credit - Debit
    # -----------------------------------------------------------------
    parsed = parsers.parse_csv_bytes(FIRST_CITIZENS_CSV.encode("utf-8"))
    check("First Citizens: format detected", parsed.detected_format == parsers.FIRST_CITIZENS)
    check("First Citizens: credit-only row -> positive amount (1200.00 -> 120000)", parsed.rows[0].amount_minor == 120000)
    check("First Citizens: debit-only row -> negative amount (300.00 -> -30000)", parsed.rows[1].amount_minor == -30000)
    check("First Citizens: account_hint = Account Number", parsed.rows[0].account_hint == "7470")
    check("First Citizens: Status column mapped to pending_status", parsed.rows[0].pending_status == "Posted")
    check("First Citizens: sign convention matches Chase (credit positive, debit negative)",
          parsed.rows[0].amount_minor > 0 and parsed.rows[1].amount_minor < 0)

    # -----------------------------------------------------------------
    # Unrecognized layout must raise, never be guessed
    # -----------------------------------------------------------------
    try:
        parsers.parse_csv_bytes(b"Foo,Bar\n1,2\n")
        check("Unrecognized header raises UnrecognizedFormatError", False, "no exception raised")
    except parsers.UnrecognizedFormatError:
        check("Unrecognized header raises UnrecognizedFormatError", True)

    # -----------------------------------------------------------------
    # Amount parsing edge cases
    # -----------------------------------------------------------------
    minor, err = parsers.to_minor_units("$1,234.56")
    check("Amount parsing: thousands separator + $ sign", minor == 123456 and err is None)
    minor, err = parsers.to_minor_units("(24.05)")
    check("Amount parsing: parenthesized negative", minor == -2405 and err is None)
    minor, err = parsers.to_minor_units("")
    check("Amount parsing: blank is an explicit error, never silently zero", minor is None and err is not None)

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
