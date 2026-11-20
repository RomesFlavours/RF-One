#!/usr/bin/env python
"""Tests for `supplier_format_rules.py` ("Purchased Supplier+Format
Training — Phase 1"). Fixtures are synthetic text built to reproduce the
*specific* real patterns observed in real acquired documents (Task
requirement: synthetic input is only ever used for unit tests, never for
the actual training corpus) — except `PRIME_LINE_REAL_OCR_EXCERPT` below,
which is a real, frozen OCR excerpt (see its own comment), used as a
regression guard.

Usage:
    python test_supplier_format_rules.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parser as invoice_parser  # noqa: E402
from supplier_format_rules import (  # noqa: E402
    CANONICAL_COSTCO_NAME,
    CANONICAL_KEITH_NAME,
    CANONICAL_PRIME_LINE_NAME,
    apply_supplier_specializations,
    detect_channel,
)


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


# -- Prime Line Distributors -------------------------------------------------

_PRIME_LINE_SYNTHETIC = """PRIME LINE DISTRIBUTORS INVOICE
IMPORTERS OF SELECTED SPECIALTY FOODS
ROME'S FLAVOURS Number: 1107919
Date: 06/30/20
CASH CHECK # AMOUNT INVOICE #
Ootters Conte
SUBTOTAL $ 523.72
TAX $ 0.00
TOTAL $ 523.72
"""

# A real (frozen) excerpt of what pdfplumber/Tesseract actually produced for
# the real acquired document `PL20200630125750_001.pdf` (see the phase-1
# training report, section C) — kept verbatim (including its OCR noise) as
# a regression guard: if a future change to the regexes below stops
# extracting the verified-correct number/total from this exact real text,
# this test must fail.
PRIME_LINE_REAL_OCR_EXCERPT = """eof

� PLEASE REMIT
PRIME LINE DISTRIBUTORS  boxs05 veces INVOICE

PRIME LINE DISTRIBUTORS INC
Orlando (407) 812-1887 ne
IMPORTERS OF SELECTED SPECIALTY FOODS Toll-Free (800) 272 0254 PO Box 885310

| ROME'S FLAVOURS $| ROME'S FLAVOURS Number. 1107919
O} ANGEL! E DEMONI LLC H| 124 MORSE BLVD

CASH CHECK # AMOUNT . INVOICE #
Ootters Conte
Received in good condition rm an SUBTOTAL S$ 623.72
� ao TAX � 0.00
foo . TOTAL � 523.72
"""


def test_prime_line_recognized_and_specialized(result: Result) -> None:
    header = {"supplier_name": "IMPORTERS OF SELECTED SPECIALTY FOODS", "document_number": "", "issue_date": "", "currency": "USD", "total_amount": ""}
    out = apply_supplier_specializations(_PRIME_LINE_SYNTHETIC, header)
    result.check("supplier canonicalized to Prime Line Distributors", out["supplier_name"] == CANONICAL_PRIME_LINE_NAME)
    result.check("document_number read from bare 'Number:' label", out["document_number"] == "1107919")
    result.check("issue_date read from bare 'Date:' label", out["issue_date"] == "06/30/20")
    result.check("total_amount read from 'TOTAL $' line, not the blank INVOICE # stub", out["total_amount"] == "523.72")


def test_prime_line_generic_doc_number_bug_is_avoided(result: Result) -> None:
    """The generic parser's own `guess_document_number()` latches onto the
    blank "INVOICE #" remittance-stub field on a real Prime Line document
    (its garbled next-line token, e.g. "Ootters") -- confirms the
    specialization's own result is what actually gets used, not that
    generic bug's output."""

    generic_guess = invoice_parser.guess_document_number(_PRIME_LINE_SYNTHETIC)
    result.check("(sanity) the generic parser's own guess is indeed the wrong stub field", generic_guess.lower() in ("ootters", "conte"))
    header = {"supplier_name": "", "document_number": generic_guess, "issue_date": "", "currency": "", "total_amount": ""}
    out = apply_supplier_specializations(_PRIME_LINE_SYNTHETIC, header)
    result.check("specialization overrides the wrong generic guess", out["document_number"] == "1107919")


def test_prime_line_blanks_fields_it_cannot_confirm(result: Result) -> None:
    """Task requirement 12 discipline ("Meglio HUMAN corretto che
    NORMALIZED sbagliato") applied to Phase 1's own Prime Line rule: when
    its own Date pattern finds nothing, the field is left BLANK rather than
    whatever the (previously shown unreliable) generic guess produced --
    real sample `PL20200630125750_001.pdf` had no recoverable Date label at
    all after OCR, and would otherwise have kept the generic parser's wrong
    "Payment Due by" date."""

    text = "PRIME LINE DISTRIBUTORS INVOICE\nNumber: 1107919\nTOTAL $ 523.72\n*** Payment Due by 07/07/20 ***\n"
    header = {"supplier_name": "", "document_number": "", "issue_date": "07/07/20", "currency": "", "total_amount": ""}
    out = apply_supplier_specializations(text, header)
    result.check("issue_date is blanked, not left at the wrong generic guess", out["issue_date"] == "")


def test_prime_line_real_ocr_regression(result: Result) -> None:
    header = {"supplier_name": "", "document_number": "", "issue_date": "", "currency": "", "total_amount": ""}
    out = apply_supplier_specializations(PRIME_LINE_REAL_OCR_EXCERPT, header)
    result.check("real-sample regression: supplier", out["supplier_name"] == CANONICAL_PRIME_LINE_NAME)
    result.check("real-sample regression: document_number", out["document_number"] == "1107919")
    result.check("real-sample regression: total_amount (not the garbled SUBTOTAL 623.72)", out["total_amount"] == "523.72")


# -- Costco Wholesale ---------------------------------------------------------

_COSTCO_WITH_WORDMARK = """COSTCO
Altamonte Springs #183
E 36070 GORGONZOLA 7.88
SUBTOTAL 149.44
TAX 0.00
**** TOTAL PD 44
Tran ID#: 004200002942....
Merchant ID: 990183
EFT/Debit 149.44
CHANGE 0.00
"""

# The real second Costco receipt's OCR never recovered the "COSTCO"
# wordmark at all (the logo did not OCR) -- only Merchant ID/Tran ID survive.
_COSTCO_WITHOUT_WORDMARK = """Altamonte Springs #183
741 Orange Ave.
SUBTOTAL 364.36
TAX 4.06
woe TOTAL PSO 42 |
Tran ID#: 063900003938....
Merchant ID: 990183
EFT/Debit 368.42
CHANGE 0.00
"""


def test_costco_recognized_by_wordmark(result: Result) -> None:
    header = {"supplier_name": "COSTCO", "document_number": "", "issue_date": "02/11/2020", "currency": "USD", "total_amount": "0.00"}
    out = apply_supplier_specializations(_COSTCO_WITH_WORDMARK, header)
    result.check("supplier canonicalized to Costco Wholesale", out["supplier_name"] == CANONICAL_COSTCO_NAME)
    result.check("document_number read from Tran ID#", out["document_number"] == "004200002942")
    result.check("total_amount read from EFT/Debit, not the garbled TOTAL line", out["total_amount"] == "149.44")


def test_costco_recognized_via_merchant_id_when_wordmark_missing(result: Result) -> None:
    """Task requirement 3 ("NON assumere Supplier = one format") applies to
    recognition evidence too -- a real Costco receipt whose OCR dropped the
    logo entirely is still recognized, via the stable Merchant ID."""

    header = {"supplier_name": "Altamonte Springs #183", "document_number": "", "issue_date": "", "currency": "", "total_amount": "0.00"}
    out = apply_supplier_specializations(_COSTCO_WITHOUT_WORDMARK, header)
    result.check("supplier still canonicalized without the wordmark", out["supplier_name"] == CANONICAL_COSTCO_NAME)
    result.check("total_amount read from EFT/Debit", out["total_amount"] == "368.42")


# -- Ben E. Keith Foods (supplier name only) ---------------------------------

_KEITH_SYNTHETIC = """lilllilt]lilt ililililflIilil]t
REMIT TO:
BEN E KEITH FLORIDA FOODS
PO BOX 309
TOTAL WEIGHT 19.10# 15.85 302.74
"""


def test_keith_recognized_name_only(result: Result) -> None:
    header = {"supplier_name": "lilllilt]lilt ililililflIilil]t", "document_number": "", "issue_date": "", "currency": "", "total_amount": ""}
    out = apply_supplier_specializations(_KEITH_SYNTHETIC, header)
    result.check("supplier canonicalized to Ben E. Keith Foods", out["supplier_name"] == CANONICAL_KEITH_NAME)
    result.check("document_number is left to the generic parser (no Keith-specific rule yet)", out["document_number"] == "")


# -- Generic fallback ---------------------------------------------------------

def test_unrecognized_supplier_left_untouched(result: Result) -> None:
    """Task requirement 6: the generic parser's own result is always the
    fallback for a Supplier+Format this module has no real-evidence rule
    for -- specialization must never invent one."""

    header = {"supplier_name": "Some Other Supplier Inc.", "document_number": "INV-42", "issue_date": "01/01/24", "currency": "USD", "total_amount": "10.00"}
    out = apply_supplier_specializations("SOME OTHER SUPPLIER INC.\nInvoice No: INV-42\nTotal: $10.00\n", dict(header))
    result.check("header is returned unchanged for an unrecognized Supplier+Format", out == header)


def test_empty_raw_text_is_a_no_op(result: Result) -> None:
    header = {"supplier_name": "X", "document_number": "1", "issue_date": "", "currency": "", "total_amount": ""}
    out = apply_supplier_specializations("", dict(header))
    result.check("no raw text -> header unchanged", out == header)


# -- Acquisition channel (Task requirement 9) --------------------------------

def test_channel_detection(result: Result) -> None:
    result.check("no Instacart evidence -> Direct", detect_channel(_COSTCO_WITH_WORDMARK, "CO2020-02-11.pdf") == "Direct")
    result.check("Instacart mentioned in the document text -> Instacart", detect_channel("Your Instacart order from Costco\n" + _COSTCO_WITH_WORDMARK, "receipt.pdf") == "Instacart")
    result.check("Instacart mentioned only in the source filename -> Instacart", detect_channel(_COSTCO_WITH_WORDMARK, "instacart_costco_receipt.pdf") == "Instacart")
    result.check("channel detection is supplier-agnostic (works without any known-supplier signature)", detect_channel("Some Other Supplier via Instacart", None) == "Instacart")


def main() -> int:
    result = Result()
    for test_fn in (
        test_prime_line_recognized_and_specialized,
        test_prime_line_generic_doc_number_bug_is_avoided,
        test_prime_line_blanks_fields_it_cannot_confirm,
        test_prime_line_real_ocr_regression,
        test_costco_recognized_by_wordmark,
        test_costco_recognized_via_merchant_id_when_wordmark_missing,
        test_keith_recognized_name_only,
        test_unrecognized_supplier_left_untouched,
        test_empty_raw_text_is_a_no_op,
        test_channel_detection,
    ):
        test_fn(result)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Supplier Format Rules tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Supplier Format Rules tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
