#!/usr/bin/env python
"""Tests for `invoice_splitter.py` ("Purchased Supplier Training — Phase
2", multi-invoice PDF splitting).

Real-case regression tests (§14/§15 of the test list) run against the
actual acquired files under `uploads/` via `ocr_engine.extract_pages_from_pdf`
— both are "PDF-Text" documents (a real, embedded text layer read through
pdfplumber), so unlike an OCR-fallback test these need no external
Tesseract/Poppler installation to run. Every other test uses synthetic
per-page text built to reproduce the specific real patterns already
verified against those files (Task: synthetic input is only ever used for
unit tests, never the training corpus itself).

Usage:
    python test_invoice_splitter.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ocr_engine  # noqa: E402
from invoice_splitter import split_into_invoices  # noqa: E402

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def _prime_line_page(number: str, date: str, total: str) -> str:
    return (
        "PRIME LINE DISTRIBUTORS INVOICE\n"
        f"ROME'S FLAVOURS Number: {number}\n"
        f"Date: {date}\n"
        "BM43 8 CASE SAN BENEDETTO NATURAL PET 1.5L 6/50.7 oz 8 7.99 63.92\n"
        f"TOTAL $ {total}\n"
    )


def _keith_page(number: str, page_in_invoice: int) -> str:
    return (
        "REMIT TO: BEN E KEITH FLORIDA FOODS\n"
        f"lnvoice No. Page Rep\n{number} {page_in_invoice} OT\n"
        "CHICKEN BREAST 8OZ BUTTER 2/10 LB 85.06 170.12\n"
    )


# -- Synthetic: Prime Line-shaped 4-invoice batch (Task real case A) --------


def test_four_invoice_batch_becomes_four_segments(result: Result) -> None:
    pages = [
        _prime_line_page("1107919", "06/30/20", "523.72"),
        _prime_line_page("1103031", "05/26/20", "87.50"),
        _prime_line_page("1103028", "05/26/20", "265.38"),
        _prime_line_page("1103053", "05/26/20", "42.00"),
    ]
    segments = split_into_invoices(pages)
    result.check("a 4-page batch where every page has its own distinct number becomes 4 segments", segments is not None and len(segments) == 4)
    result.check("each segment is exactly one page (no false multi-page grouping)", all(not s.is_multi_page for s in segments))
    result.check("segment document_numbers match each page's own number, in order", [s.document_number for s in segments] == ["1107919", "1103031", "1103028", "1103053"])
    result.check("segment_index/segment_count are consistent", [s.segment_index for s in segments] == [1, 2, 3, 4] and all(s.segment_count == 4 for s in segments))


# -- Synthetic: Ben E. Keith-shaped 2-invoice batch, one multi-page (Task real case B) --


def test_two_invoice_batch_with_one_multi_page(result: Result) -> None:
    pages = [
        _keith_page("90079477", 1),  # invoice A, page 1 of 1
        _keith_page("90080721", 1),  # invoice B, page 1 of 2
        _keith_page("90080721", 2),  # invoice B, page 2 of 2 -- same number, must stay merged
    ]
    segments = split_into_invoices(pages)
    result.check("3 pages, 2 real invoices -> exactly 2 segments", segments is not None and len(segments) == 2)
    result.check("the first invoice is a single page", segments[0].page_start == 1 and segments[0].page_end == 1)
    result.check("the second invoice correctly stays ONE document across its 2 pages (not split further)", segments[1].page_start == 2 and segments[1].page_end == 3 and segments[1].is_multi_page)
    result.check("document_numbers are correct per segment", segments[0].document_number == "90079477" and segments[1].document_number == "90080721")


def test_page_provenance_preserved(result: Result) -> None:
    """Task requirement 6 / test list requirement 5: "page provenance
    preserved"."""

    pages = [_keith_page("111111", 1), _keith_page("222222", 1), _keith_page("222222", 2)]
    segments = split_into_invoices(pages)
    result.check("total_pages is recorded on every segment", all(s.total_pages == 3 for s in segments))
    result.check("page_range_label reflects a single page correctly", segments[0].page_range_label == "p1")
    result.check("page_range_label reflects a multi-page range correctly", segments[1].page_range_label == "p2-3")


# -- Uncertainty rule (Task requirement 4) -----------------------------------


def test_single_page_is_never_split(result: Result) -> None:
    result.check("a 1-page document is never split (nothing to split)", split_into_invoices([_prime_line_page("1", "01/01/24", "1.00")]) is None)
    result.check("an empty page list is never split", split_into_invoices([]) is None)


def test_no_boundary_evidence_is_not_split(result: Result) -> None:
    """A genuine multi-page SINGLE invoice (every page shows the same
    number, or Continuation pages with no number of their own) must stay
    exactly one document -- `split_into_invoices()` returning `None` here
    means "let the legacy single-document path handle it", which already
    behaves correctly for this case."""

    pages = [_keith_page("500500", 1), _keith_page("500500", 2), _keith_page("500500", 3)]
    result.check("every page agreeing on the same number -> not split (stays one document)", split_into_invoices(pages) is None)


def test_ambiguous_boundary_is_not_split(result: Result) -> None:
    """Task requirement 4 / test list requirement 3: "ambiguous boundary ->
    HUMAN". A page with NO identity evidence at all, sitting where a
    boundary was tentatively detected, makes the whole split untrustworthy
    -- `split_into_invoices()` returns `None` (never guesses which side the
    blank page belongs to), so the whole file falls back to being treated
    as a single document, which normal NORMALIZED/HUMAN validation then
    correctly routes to HUMAN (missing/incoherent fields)."""

    ambiguous_page = "some illegible scan noise with no recognizable label at all\n***\n"
    pages = [_prime_line_page("1107919", "06/30/20", "523.72"), ambiguous_page, _prime_line_page("1103031", "05/26/20", "87.50")]
    result.check(
        "a page with zero identity evidence between two differently-numbered segments aborts the split entirely",
        split_into_invoices(pages) is None,
    )


# -- Real-case regressions (Task requirement 14/15) --------------------------


def test_prime_line_real_batch_regression(result: Result) -> None:
    path = os.path.join(UPLOADS_DIR, "21806b7f_PL20200609171959_001.pdf")
    if not os.path.exists(path):
        result.check("SKIPPED (real fixture file not present in this environment): Prime Line real 4-invoice batch", True)
        return
    pages, method = ocr_engine.extract_pages_from_pdf(path)
    result.check("real file is read via the digital PDF-Text path (pdfplumber only, no OCR needed)", method == "PDF-Text")
    result.check("real file has 4 pages", len(pages) == 4)
    segments = split_into_invoices(pages)
    result.check("the real 4-invoice Prime Line batch splits into exactly 4 segments", segments is not None and len(segments) == 4)
    if segments is not None:
        result.check("each real invoice is a single page (verified real layout)", all(not s.is_multi_page for s in segments))
        result.check(
            "real document_numbers match the verified ground truth (1103031/1103028/1103053; the first page's own number is itself garbled at the OCR/text-layer source, see supplier_format_rules.py)",
            [s.document_number for s in segments[1:]] == ["1103031", "1103028", "1103053"],
        )


def test_keith_real_batch_regression(result: Result) -> None:
    path = os.path.join(UPLOADS_DIR, "f8862b89_24 Keith_20241010_0002-1-3.pdf")
    if not os.path.exists(path):
        result.check("SKIPPED (real fixture file not present in this environment): Ben E. Keith real 2-invoice batch", True)
        return
    pages, method = ocr_engine.extract_pages_from_pdf(path)
    result.check("real file is read via the digital PDF-Text path (pdfplumber only, no OCR needed)", method == "PDF-Text")
    result.check("real file has 3 pages", len(pages) == 3)
    segments = split_into_invoices(pages)
    result.check("the real 2-invoice Keith batch (one multi-page) splits into exactly 2 segments", segments is not None and len(segments) == 2)
    if segments is not None:
        result.check("the first real invoice is page 1 only", segments[0].page_start == 1 and segments[0].page_end == 1)
        result.check(
            "the second real invoice correctly stays merged across its real pages 2-3 (no false split)",
            segments[1].page_start == 2 and segments[1].page_end == 3,
        )
        result.check("real document_number for the second (multi-page) invoice is 90080721", segments[1].document_number == "90080721")


def main() -> int:
    result = Result()
    for test_fn in (
        test_four_invoice_batch_becomes_four_segments,
        test_two_invoice_batch_with_one_multi_page,
        test_page_provenance_preserved,
        test_single_page_is_never_split,
        test_no_boundary_evidence_is_not_split,
        test_ambiguous_boundary_is_not_split,
        test_prime_line_real_batch_regression,
        test_keith_real_batch_regression,
    ):
        test_fn(result)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Invoice Splitter tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Invoice Splitter tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
