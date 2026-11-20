"""AWS Textract `AnalyzeExpense` extraction provider — the initial V1
document-extraction provider named in `CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001.md`
§4. Implements `ExtractionProvider` (`base.py`) so nothing outside this
module ever depends on Textract's own response shape.

Credentials are never hardcoded here. `boto3` resolves credentials through
its own standard chain (environment variables, shared config/credentials
file, IAM role) — this module only reads a region from configuration/
environment (`AWS_REGION`/`AWS_DEFAULT_REGION`, or an explicit constructor
argument), which is a configuration hook, not a credential. This is
deliberately compatible with a later move to AWS Secrets Manager/IAM: this
module never needs to change for that, only how the *caller* configures
`boto3`'s environment does.

Multi-file handling is the minimum needed for an explicitly grouped
submission (§8 of the foundation task): `AnalyzeExpense` is a single-
document synchronous API with no native "combine these files" input, so
each file in the submission is sent as its own `AnalyzeExpense` call, and
the resulting per-file `NormalizedInvoice` drafts are merged exactly like
`tesseract_provider.py` does (header/totals: first non-empty value wins;
lines: concatenated in submission order) — no image-stitching or
preprocessing is introduced.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .base import (
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

# Real AWS Textract AnalyzeExpense SummaryField `Type.Text` values this
# provider recognizes and maps to a named NormalizedHeader/NormalizedTotals
# field. Anything Textract returns that is NOT in these maps is preserved
# verbatim in `header.extra`/`totals.extra` (§7) — never silently dropped.
_HEADER_FIELD_MAP = {
    "VENDOR_NAME": "supplier_name",
    "INVOICE_RECEIPT_ID": "invoice_number",
    "INVOICE_RECEIPT_DATE": "invoice_date",
    "DUE_DATE": "due_date",
}
_HEADER_REFERENCE_TYPES = {"PO_NUMBER", "ORDER_DATE"}
_TOTALS_FIELD_MAP = {
    "SUBTOTAL": "subtotal",
    "TAX": "tax",
    "TOTAL": "total",
    "DISCOUNT": "discounts",
    "SERVICE_CHARGE": "fees",
    "GRATUITY": "fees",
}
# Real AnalyzeExpense LineItem `Type.Text` values.
_LINE_FIELD_MAP = {
    "ITEM": "description",
    "PRODUCT_CODE": "supplier_product_code",
    "QUANTITY": "quantity",
    "UNIT_PRICE": "unit_price",
    "PRICE": "line_total",
}


def _client_factory_default():
    """Lazily imports boto3 so importing this module never requires boto3
    to be installed in an environment that only uses the local Tesseract
    provider — mirrors `ocr_engine.py`'s own optional-import pattern for
    `pdfplumber`/`pdf2image`."""
    import boto3

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    return boto3.client("textract", region_name=region) if region else boto3.client("textract")


def _field_text(expense_field: dict[str, Any], key: str) -> tuple[str | None, float | None]:
    detection = expense_field.get(key) or {}
    text = detection.get("Text")
    confidence = detection.get("Confidence")
    return (text or None), (float(confidence) if confidence is not None else None)


def _map_summary_fields(summary_fields: list[dict[str, Any]]) -> tuple[NormalizedHeader, NormalizedTotals]:
    header = NormalizedHeader()
    totals = NormalizedTotals()
    for expense_field in summary_fields:
        type_text = (expense_field.get("Type") or {}).get("Text")
        value_text, confidence = _field_text(expense_field, "ValueDetection")
        if value_text is None:
            continue

        if type_text in _HEADER_FIELD_MAP:
            setattr(header, _HEADER_FIELD_MAP[type_text], value_text)
        elif type_text in _HEADER_REFERENCE_TYPES:
            header.reference_numbers.append(value_text)
        elif type_text in _TOTALS_FIELD_MAP:
            existing = getattr(totals, _TOTALS_FIELD_MAP[type_text])
            # SERVICE_CHARGE/GRATUITY both map to `fees` — never overwrite a
            # value already found under the other type, combine instead.
            if existing and _TOTALS_FIELD_MAP[type_text] == "fees":
                setattr(totals, "fees", f"{existing}, {value_text}")
            else:
                setattr(totals, _TOTALS_FIELD_MAP[type_text], value_text)
        elif type_text == "CURRENCY" or expense_field.get("Currency"):
            currency_code = (expense_field.get("Currency") or {}).get("Code")
            if currency_code:
                header.currency = currency_code
        elif type_text:
            # A real, materially present summary field with no named home —
            # preserved verbatim (§7), never discarded.
            header.extra[type_text] = value_text
    return header, totals


def _map_line_items(line_item_groups: list[dict[str, Any]]) -> list[NormalizedLine]:
    lines: list[NormalizedLine] = []
    for group in line_item_groups:
        for line_item in group.get("LineItems", []):
            normalized_line = NormalizedLine()
            line_confidences: list[float] = []
            for expense_field in line_item.get("LineItemExpenseFields", []):
                type_text = (expense_field.get("Type") or {}).get("Text")
                value_text, confidence = _field_text(expense_field, "ValueDetection")
                if confidence is not None:
                    line_confidences.append(confidence)
                if value_text is None:
                    continue
                if type_text in _LINE_FIELD_MAP:
                    setattr(normalized_line, _LINE_FIELD_MAP[type_text], value_text)
                elif type_text:
                    normalized_line.extra[type_text] = value_text
            # Line-level confidence: the mean of this line's own field
            # confidences, when Textract provided at least one — never
            # invented when Textract reported none.
            if line_confidences:
                normalized_line.confidence = sum(line_confidences) / len(line_confidences)
            lines.append(normalized_line)
    return lines


def _first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


class TextractProvider:
    """`ExtractionProvider` implementation calling AWS Textract's
    `AnalyzeExpense` operation. `client_factory` is injectable so tests can
    supply a `botocore.stub.Stubber`-wrapped client instead of a real one —
    see `test_invoice_intake_providers.py`."""

    name = "aws-textract-analyze-expense"

    def __init__(self, client_factory=_client_factory_default):
        self._client_factory = client_factory

    def _analyze_one_file(self, path: str) -> dict[str, Any]:
        client = self._client_factory()
        with open(path, "rb") as fh:
            document_bytes = fh.read()
        return client.analyze_expense(Document={"Bytes": document_bytes})

    def extract(self, submission: InvoiceSourceSubmission) -> tuple[NormalizedInvoice, RawExtractionResult]:
        per_file_raw: dict[str, Any] = {}
        headers: list[NormalizedHeader] = []
        totals: list[NormalizedTotals] = []
        all_lines: list[NormalizedLine] = []
        all_confidences: list[float] = []

        for source_file in submission.source_files:
            response = self._analyze_one_file(source_file.path)
            per_file_raw[source_file.original_filename] = response

            for expense_document in response.get("ExpenseDocuments", []):
                header, doc_totals = _map_summary_fields(expense_document.get("SummaryFields", []))
                headers.append(header)
                totals.append(doc_totals)
                doc_lines = _map_line_items(expense_document.get("LineItemGroups", []))
                all_lines.extend(doc_lines)
                all_confidences.extend(
                    line.confidence for line in doc_lines if line.confidence is not None
                )

        merged_header = NormalizedHeader(
            supplier_name=_first_non_empty([h.supplier_name for h in headers]),
            invoice_number=_first_non_empty([h.invoice_number for h in headers]),
            invoice_date=_first_non_empty([h.invoice_date for h in headers]),
            due_date=_first_non_empty([h.due_date for h in headers]),
            currency=_first_non_empty([h.currency for h in headers]),
            reference_numbers=[ref for h in headers for ref in h.reference_numbers],
            extra={k: v for h in headers for k, v in h.extra.items()},
        )
        merged_totals = NormalizedTotals(
            subtotal=_first_non_empty([t.subtotal for t in totals]),
            discounts=_first_non_empty([t.discounts for t in totals]),
            tax=_first_non_empty([t.tax for t in totals]),
            fees=_first_non_empty([t.fees for t in totals]),
            total=_first_non_empty([t.total for t in totals]),
            extra={k: v for t in totals for k, v in t.extra.items()},
        )

        normalized = NormalizedInvoice(
            header=merged_header,
            lines=all_lines,
            totals=merged_totals,
            metadata=NormalizedMetadata(
                source_files=[sf.original_filename for sf in submission.source_files],
                language=None,  # AnalyzeExpense does not report a detected language
                extraction_confidence=(
                    sum(all_confidences) / len(all_confidences) if all_confidences else None
                ),
                provider_name=self.name,
                acquired_at=datetime.now(UTC),
            ),
        )
        raw = RawExtractionResult(provider_name=self.name, raw_response={"per_file": per_file_raw})
        return normalized, raw
