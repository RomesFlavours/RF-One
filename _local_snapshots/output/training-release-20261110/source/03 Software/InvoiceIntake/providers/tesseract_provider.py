"""Local OCR/Tesseract extraction provider — the existing `ocr_engine.py`/
`parser.py` pipeline, wrapped behind the new provider-agnostic
`ExtractionProvider` boundary (`base.py`). Not deleted, not modified: this
module only calls into the existing, already-working functions and maps
their existing output shape onto `NormalizedInvoice`.

Retained explicitly as the local fallback/reference provider — the
foundation task instructs against deleting the existing local OCR path.
Multi-file handling here is the minimum needed for an explicitly grouped
submission: each file is extracted independently with the existing
per-file logic, and the resulting per-file drafts are merged (header/
totals: first non-empty value wins; lines: concatenated in submission
order) — no image-stitching, deskew, or auto-grouping is introduced.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

_INVOICE_INTAKE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _INVOICE_INTAKE_DIR not in sys.path:
    sys.path.insert(0, _INVOICE_INTAKE_DIR)

import ocr_engine  # noqa: E402
import parser as invoice_parser  # noqa: E402

from .base import (  # noqa: E402
    ExtractionProvider,
    InvoiceSourceSubmission,
    NormalizedHeader,
    NormalizedInvoice,
    NormalizedLine,
    NormalizedMetadata,
    NormalizedTotals,
    RawExtractionResult,
)

UTC = timezone.utc


def _extract_one_file(path: str) -> tuple[str, str]:
    """Returns (text, acquisition_method) using the exact existing
    `ocr_engine.extract_text` dispatch — no new extraction logic."""
    return ocr_engine.extract_text(path)


def _header_from_parsed(parsed: dict) -> NormalizedHeader:
    return NormalizedHeader(
        supplier_name=parsed.get("supplier_name") or None,
        invoice_number=parsed.get("document_number") or None,
        invoice_date=parsed.get("issue_date") or None,
        due_date=None,  # the existing parser.py never extracts a due date — not invented here
        currency=parsed.get("currency") or None,
        reference_numbers=[],  # the existing parser.py never extracts PO/reference numbers
    )


def _lines_from_parsed(parsed_lines: list[dict]) -> list[NormalizedLine]:
    lines: list[NormalizedLine] = []
    for raw_line in parsed_lines:
        lines.append(
            NormalizedLine(
                description=raw_line.get("description") or None,
                supplier_product_code=None,  # the existing parser.py never extracts a product code
                quantity=raw_line.get("quantity") or None,
                unit=None,
                unit_price=raw_line.get("unit_price") or None,
                discount=None,
                tax=None,
                fees=None,
                line_total=raw_line.get("line_amount") or None,
                confidence=None,  # the existing local OCR path exposes no per-field confidence at all
            )
        )
    return lines


def _totals_from_parsed(parsed: dict) -> NormalizedTotals:
    return NormalizedTotals(total=parsed.get("total_amount") or None)


def _first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


class TesseractProvider:
    """`ExtractionProvider` implementation wrapping the existing local
    OCR/Tesseract + regex-parser pipeline."""

    name = "tesseract-local"

    def extract(self, submission: InvoiceSourceSubmission) -> tuple[NormalizedInvoice, RawExtractionResult]:
        per_file_raw: dict[str, dict] = {}
        headers: list[NormalizedHeader] = []
        totals: list[NormalizedTotals] = []
        all_lines: list[NormalizedLine] = []
        methods: list[str] = []

        for source_file in submission.source_files:
            text, method = _extract_one_file(source_file.path)
            methods.append(method)
            parsed_header = invoice_parser.parse_header(text)
            parsed_lines = invoice_parser.parse_lines(text)
            per_file_raw[source_file.original_filename] = {
                "acquisition_method": method,
                "raw_text": text,
                "parsed_header": parsed_header,
                "parsed_lines": parsed_lines,
            }
            headers.append(_header_from_parsed(parsed_header))
            totals.append(_totals_from_parsed(parsed_header))
            all_lines.extend(_lines_from_parsed(parsed_lines))

        merged_header = NormalizedHeader(
            supplier_name=_first_non_empty([h.supplier_name for h in headers]),
            invoice_number=_first_non_empty([h.invoice_number for h in headers]),
            invoice_date=_first_non_empty([h.invoice_date for h in headers]),
            due_date=_first_non_empty([h.due_date for h in headers]),
            currency=_first_non_empty([h.currency for h in headers]),
            reference_numbers=[],
        )
        merged_totals = NormalizedTotals(total=_first_non_empty([t.total for t in totals]))

        normalized = NormalizedInvoice(
            header=merged_header,
            lines=all_lines,
            totals=merged_totals,
            metadata=NormalizedMetadata(
                source_files=[sf.original_filename for sf in submission.source_files],
                language=None,  # the existing local path never detects a language
                extraction_confidence=None,  # no document-level confidence score is exposed by pytesseract.image_to_string
                provider_name=self.name,
                acquired_at=datetime.now(UTC),
            ),
        )
        raw = RawExtractionResult(
            provider_name=self.name,
            raw_response={"acquisition_methods": methods, "per_file": per_file_raw},
        )
        return normalized, raw
