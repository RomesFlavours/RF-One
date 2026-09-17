#!/usr/bin/env python
"""Tests for `parser.py`'s generic field recognition, and for
`purchased_bridge._parse_date`'s date-format handling (Purchased Invoice
Intake — Improve Generic Parser and Prepare Supplier Format Training).

Fast, isolated unit tests — no database, no OCR, no mailbox.

Usage:
    python test_parser.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_DATA_STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

import parser as invoice_parser  # noqa: E402
import purchased_bridge  # noqa: E402

UTC = timezone.utc


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


# ---------------------------------------------------------------------------
# §10 scenarios 1-4: date formats
# ---------------------------------------------------------------------------


def test_date_mm_dd_yy(result: Result) -> None:
    result.check("MM/DD/YY (07/07/20) is parsed as 2020-07-07", purchased_bridge._parse_date("07/07/20") == datetime(2020, 7, 7, tzinfo=UTC))
    result.check("MM-DD-YY (07-07-20) is parsed as 2020-07-07", purchased_bridge._parse_date("07-07-20") == datetime(2020, 7, 7, tzinfo=UTC))


def test_date_mm_dd_yyyy(result: Result) -> None:
    result.check("MM/DD/YYYY (01/31/2020) is parsed as 2020-01-31", purchased_bridge._parse_date("01/31/2020") == datetime(2020, 1, 31, tzinfo=UTC))


def test_date_yyyy_mm_dd(result: Result) -> None:
    result.check("YYYY-MM-DD (2020-01-31) is parsed as 2020-01-31", purchased_bridge._parse_date("2020-01-31") == datetime(2020, 1, 31, tzinfo=UTC))


def test_missing_or_implausible_date_is_none(result: Result) -> None:
    result.check("an empty date string is Unknown (None)", purchased_bridge._parse_date("") is None)
    result.check("None is Unknown (None)", purchased_bridge._parse_date(None) is None)
    result.check("unrecognizable text is Unknown (None)", purchased_bridge._parse_date("not a date") is None)
    result.check(
        "an OCR-garbled/implausible year (02/08/2620) is Unknown, never silently accepted -- 'NON introdurre inferenze arbitrarie'",
        purchased_bridge._parse_date("02/08/2620") is None,
    )


# ---------------------------------------------------------------------------
# §3: invoice/receipt/transaction number recognition
# ---------------------------------------------------------------------------


def test_invoice_number_labels_recognized(result: Result) -> None:
    cases = {
        "Invoice #: ABC123": "ABC123",
        "Invoice No. 456": "456",
        "Invoice Number: INV-789": "INV-789",
        "Receipt # 55521": "55521",
        "Receipt No: R-9001": "R-9001",
        "Transaction Number: T99": "T99",
        "Trans #: 4471": "4471",
        "Order No. O-1234": "O-1234",
    }
    for text, expected in cases.items():
        got = invoice_parser.guess_document_number(text)
        result.check(f"{text!r} -> document number {expected!r} (got {got!r})", got == expected)


def test_no_invented_document_number(result: Result) -> None:
    result.check(
        "text with no recognizable number label produces an empty string, never a guess",
        invoice_parser.guess_document_number("Just some regular text about a delivery.") == "",
    )


# ---------------------------------------------------------------------------
# §4: total recognition, avoiding subtotal/tax/tip/payment confusion
# ---------------------------------------------------------------------------


def test_total_keyword_priority(result: Result) -> None:
    text = "Subtotal: $100.00\nTax: $8.00\nGrand Total: $108.00\n"
    result.check("Grand Total is preferred over a Subtotal/Tax line", invoice_parser.guess_total(text) == "108.00")


def test_total_never_confused_with_subtotal(result: Result) -> None:
    text = "Item A  1  50.00  50.00\nSubtotal $50.00\nTotal $54.00\n"
    result.check("the bare 'Total' line is used, never the Subtotal line it contains as a substring", invoice_parser.guess_total(text) == "54.00")


def test_total_avoids_tip_and_payment_lines(result: Result) -> None:
    text = "Amount Due: $75.50\nTip: $10.00\nAmount Tendered: $85.50\nChange Due: $0.00\n"
    result.check(
        "Amount Due is recognized without being confused by nearby Tip/Payment/Change lines",
        invoice_parser.guess_total(text) == "75.50",
    )


def test_conflicting_totals_detected(result: Result) -> None:
    text = "Amount Due: $100.00\n...\nBalance Due: $120.00\n"
    result.check(
        "two different amounts under equally-authoritative total labels -> conflict detected",
        invoice_parser.has_conflicting_totals(text) is True,
    )


def test_no_conflict_for_ordinary_subtotal_plus_total(result: Result) -> None:
    text = "Subtotal: $100.00\nTax: $8.00\nGrand Total: $108.00\n"
    result.check(
        "an ordinary Subtotal+Tax+Grand Total combination is not a conflict",
        invoice_parser.has_conflicting_totals(text) is False,
    )


def test_no_conflict_when_same_total_repeated(result: Result) -> None:
    text = "Total Due: $50.00\nThank you! Total Due: $50.00\n"
    result.check(
        "the same amount repeated under a total label is not a conflict",
        invoice_parser.has_conflicting_totals(text) is False,
    )


# ---------------------------------------------------------------------------
# §5: supplier plausibility
# ---------------------------------------------------------------------------


def test_plausible_supplier_names_accepted(result: Result) -> None:
    for name in ("US Foods", "COSTCO WHOLESALE", "Trader Joe's", "Prime Line Distributors"):
        result.check(f"{name!r} is a plausible name", invoice_parser.looks_like_plausible_name(name))


def test_implausible_supplier_text_rejected(result: Result) -> None:
    for bad in ("", "I", "12345", "###???", "  "):
        result.check(f"{bad!r} is rejected as an implausible name", not invoice_parser.looks_like_plausible_name(bad))


def test_guess_supplier_prefers_plausible_line(result: Result) -> None:
    lines = ["eof", "COSTCO WHOLESALE #183", "123 Main St"]
    result.check(
        "guess_supplier skips an implausible first line in favor of a plausible one",
        invoice_parser.guess_supplier(lines) == "COSTCO WHOLESALE #183",
    )


def main() -> int:
    result = Result()
    for test_fn in (
        test_date_mm_dd_yy,
        test_date_mm_dd_yyyy,
        test_date_yyyy_mm_dd,
        test_missing_or_implausible_date_is_none,
        test_invoice_number_labels_recognized,
        test_no_invented_document_number,
        test_total_keyword_priority,
        test_total_never_confused_with_subtotal,
        test_total_avoids_tip_and_payment_lines,
        test_conflicting_totals_detected,
        test_no_conflict_for_ordinary_subtotal_plus_total,
        test_no_conflict_when_same_total_repeated,
        test_plausible_supplier_names_accepted,
        test_implausible_supplier_text_rejected,
        test_guess_supplier_prefers_plausible_line,
    ):
        test_fn(result)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Parser tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Parser tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
