"""Document reading for invoice acquisition (INVOICE_SCAN_ACQUISITION_001).

One entry point, `read_document(path)`, used by manual upload and by the
mailbox channel alike. It decides HOW a file is read and returns one or more
`ReadInvoice` (one per invoice found in the file) — or raises
`DocumentReadError`. A read that fails is never turned into an invoice:
before this module, a missing OCR engine produced a document whose supplier
was literally "(Nessun motore disponibile per leggere questo PDF)".

How a file is read:

- PDF with a usable digital text layer (the generic parser finds at least a
  supplier and a labelled total in it): read from the text layer, exactly as
  before (`ocr_engine.extract_pages_from_pdf` text + `parser`), split into
  invoices by `invoice_splitter` when it is confident.
- Every other PDF (scanned, or a scanner text layer the parser cannot make
  sense of) and every image: AWS Textract `AnalyzeExpense`, page by page
  (`providers/textract_provider.py`). Local OCR (Tesseract) is no longer part
  of this flow.

Nothing here invents a value: empty readings stay absent, values that are
not what their field needs are listed as `unreadable`, and two different
readings of the same amount are listed as `conflicts`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import invoice_splitter
import parser as invoice_parser
from providers import textract_provider

IMAGE_TYPES = textract_provider.TEXTRACT_IMAGE_TYPES | textract_provider.CONVERTIBLE_IMAGE_TYPES
METHOD_DIGITAL = "PDF-Text"
METHOD_TEXTRACT = "Textract-AnalyzeExpense"


class DocumentReadError(RuntimeError):
    """The file could not be read. The acquisition stays an ERROR that can
    be retried; no invoice is created."""


@dataclass
class ReadInvoice:
    header: dict[str, Any]
    lines: list[dict[str, Any]]
    amounts: dict[str, Any]
    pages: list[int]
    raw_text: str
    provenance: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    unreadable: list[dict[str, Any]] = field(default_factory=list)
    page_range_label: str | None = None  # "p2-3" when the file holds several invoices

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": self.header, "lines": self.lines, "amounts": self.amounts, "pages": self.pages,
            "provenance": self.provenance, "conflicts": self.conflicts, "unreadable": self.unreadable,
            "page_range_label": self.page_range_label,
        }


@dataclass
class ReadResult:
    method: str
    pages_total: int
    pages_read: list[int]
    invoices: list[ReadInvoice]
    raw: Any


def _digital_invoice(text: str, pages: list[int], label: str | None) -> ReadInvoice:
    header = invoice_parser.parse_header(text)
    extracted = invoice_parser.extract_amounts(text)
    conflicts = list(extracted["conflicts"])
    if invoice_parser.has_conflicting_totals(text):
        conflicts.append("total: different values read under equally authoritative total labels")
    lines = invoice_parser.parse_lines(text)
    return ReadInvoice(
        header={
            "supplier_name": header.get("supplier_name") or None,
            "document_number": header.get("document_number") or None,
            "issue_date": header.get("issue_date") or None,
            "currency": header.get("currency") or None,
            **invoice_parser.extract_terms_and_due_date(text),
        },
        lines=[{**line, "page": None} for line in lines],
        amounts=extracted["amounts"],
        pages=pages,
        raw_text=text,
        conflicts=conflicts,
        page_range_label=label,
    )


def _digital_text_is_usable(pages_text: list[str]) -> bool:
    text = "\n".join(pages_text)
    if len(text.strip()) <= 40:
        return False
    header = invoice_parser.parse_header(text)
    # A scanner's own text layer often yields a name and a number but no
    # usable line (Ben E. Keith scans): such a PDF is read by Textract.
    return bool(header.get("supplier_name")) and invoice_parser.looks_like_plausible_name(header["supplier_name"]) \
        and bool(invoice_parser.guess_total(text)) and bool(invoice_parser.parse_lines(text))


def _read_digital(pages_text: list[str]) -> ReadResult:
    segments = invoice_splitter.split_into_invoices(pages_text)
    all_pages = list(range(1, len(pages_text) + 1))
    if segments is None:
        invoices = [_digital_invoice("\n".join(pages_text).strip(), all_pages, None)]
    else:
        invoices = []
        for segment in segments:
            invoices.append(_digital_invoice(segment.text, _pages_from_label(segment.page_range_label), segment.page_range_label))
    return ReadResult(METHOD_DIGITAL, len(pages_text), all_pages, invoices, {"pages_text": pages_text})


def _pages_from_label(label: str) -> list[int]:
    body = label.lstrip("p")
    if "-" in body:
        a, b = body.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(body)]


def _read_textract(path: str, client_factory) -> ReadResult:
    try:
        page_results = textract_provider.analyze_pages(path, client_factory)
    except textract_provider.TextractPageError as exc:
        raise DocumentReadError(f"AWS Textract could not read the document — {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — e.g. credentials, network, unreadable file
        raise DocumentReadError(f"AWS Textract could not be used — {type(exc).__name__}: {exc}"[:500]) from exc
    mapped = textract_provider.map_pages_to_invoices(page_results)
    several = len(mapped) > 1
    invoices = []
    for inv in mapped:
        header = dict(inv["header"])
        header.setdefault("supplier_name", None)
        label = None
        if several:
            label = f"p{inv['pages'][0]}" + (f"-{inv['pages'][-1]}" if len(inv["pages"]) > 1 else "")
        invoices.append(ReadInvoice(
            header=header, lines=inv["lines"], amounts=inv["amounts"], pages=inv["pages"], raw_text=inv["text"],
            provenance=inv["provenance"], conflicts=inv["conflicts"], unreadable=inv["unreadable"],
            page_range_label=label,
        ))
    if not invoices:
        raise DocumentReadError("AWS Textract read the file but found no invoice content on any page.")
    pages = [r["page"] for r in page_results]
    return ReadResult(METHOD_TEXTRACT, len(pages), pages, invoices, {"textract_pages": page_results})


def read_document(path: str, *, textract_client_factory=None) -> ReadResult:
    """See module docstring. Raises `DocumentReadError` on any failure."""
    factory = textract_client_factory or textract_provider._client_factory_default
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                pages_text = [p.extract_text() or "" for p in pdf.pages]
        except Exception as exc:  # noqa: BLE001 — a damaged/unsupported PDF is an acquisition error
            raise DocumentReadError(f"The PDF could not be opened — {type(exc).__name__}: {exc}"[:500]) from exc
        if not pages_text:
            raise DocumentReadError("The PDF has no pages.")
        if _digital_text_is_usable(pages_text):
            return _read_digital(pages_text)
        return _read_textract(path, factory)
    if ext in IMAGE_TYPES:
        return _read_textract(path, factory)
    raise DocumentReadError(f"Unsupported file type {ext!r}.")
