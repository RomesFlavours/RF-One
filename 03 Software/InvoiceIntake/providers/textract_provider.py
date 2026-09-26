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


# ---------------------------------------------------------------------------
# INVOICE_SCAN_ACQUISITION_001 — page-by-page reading with field provenance.
#
# The acquisition flow (`document_reader.py`) reads scanned PDFs and photos
# through the functions below. `AnalyzeExpense` (synchronous) accepts ONE
# page per call, so a multi-page PDF is split into single-page PDFs in
# memory (pypdfium2, already installed with pdfplumber — no rasterisation,
# no local OCR) and every page is sent on its own. A page that fails is
# never skipped silently: `analyze_pages()` raises `TextractPageError`
# naming every page that could not be read.
# ---------------------------------------------------------------------------

TEXTRACT_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
# Formats Textract does not accept directly: converted losslessly to PNG
# bytes in memory (a format conversion, not OCR).
CONVERTIBLE_IMAGE_TYPES = {".webp", ".bmp"}
# AnalyzeExpense synchronous limit for document bytes.
MAX_SYNC_BYTES = 10 * 1024 * 1024


class TextractPageError(RuntimeError):
    """One or more pages could not be read. `failed_pages` lists them
    (1-based) with the service's own reason; `pages_total` is the page
    count of the file."""

    def __init__(self, failed_pages: list[tuple[int, str]], pages_total: int):
        self.failed_pages = failed_pages
        self.pages_total = pages_total
        detail = "; ".join(f"page {p}: {reason}" for p, reason in failed_pages)
        super().__init__(f"{len(failed_pages)} of {pages_total} page(s) not read — {detail}")


def split_into_page_documents(path: str) -> list[bytes]:
    """The document bytes to send to AnalyzeExpense, one entry per page."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        import io

        import pypdfium2 as pdfium

        source = pdfium.PdfDocument(path)
        pages = []
        for index in range(len(source)):
            single = pdfium.PdfDocument.new()
            single.import_pages(source, [index])
            buffer = io.BytesIO()
            single.save(buffer)
            pages.append(buffer.getvalue())
        return pages
    if ext in CONVERTIBLE_IMAGE_TYPES:
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.open(path).save(buffer, format="PNG")
        return [buffer.getvalue()]
    with open(path, "rb") as fh:
        return [fh.read()]


def analyze_pages(path: str, client_factory=_client_factory_default) -> list[dict[str, Any]]:
    """Calls AnalyzeExpense once per page; returns `[{"page": n, "response": ...}]`.
    Raises `TextractPageError` if ANY page fails (the whole file is then an
    acquisition error to retry — never a partial invoice built from the
    pages that happened to succeed)."""
    documents = split_into_page_documents(path)
    client = client_factory()
    results, failed = [], []
    for page_number, document_bytes in enumerate(documents, start=1):
        if len(document_bytes) > MAX_SYNC_BYTES:
            failed.append((page_number, f"page is {len(document_bytes) // 1024} KB, above the 10 MB synchronous limit"))
            continue
        try:
            response = client.analyze_expense(Document={"Bytes": document_bytes})
        except Exception as exc:  # noqa: BLE001 — every failure is reported per page
            failed.append((page_number, f"{type(exc).__name__}: {exc}"[:300]))
            continue
        results.append({"page": page_number, "response": response})
    if failed:
        raise TextractPageError(failed, len(documents))
    return results


_MONEY_TEXT_RE = __import__("re").compile(
    r"^\(?-?\$?\s*-?(?:\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)\)?$"
)
_AMOUNT_TYPES = {
    "TOTAL": "total", "SUBTOTAL": "subtotal", "TAX": "tax", "DISCOUNT": "discount",
    "SHIPPING_HANDLING_CHARGE": "shipping", "AMOUNT_PAID": "amount_paid", "AMOUNT_DUE": "balance_due",
    "PRIOR_BALANCE": "prior_balance",
}
_FEE_TYPES = {"SERVICE_CHARGE", "GRATUITY"}
_FEE_LABEL_WORDS = ("charge", "fee", "freight", "fuel", "delivery", "surcharge", "shipping", "handling")
_UNIT_LABELS = {"unit", "uom", "u/m", "um", "units"}
_ITEM_CODE_LABELS = ("item no", "item #", "item code", "item number", "product code", "sku", "code", "item")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def normalize_money_text(value: str | None) -> tuple[str | None, bool]:
    """(`"1234.56"`-style string, readable?) from what Textract read. An
    empty value is absent (None, True); a value that is not an amount is
    kept as unreadable (None, False) — never coerced into a number."""
    text = _clean_text(value)
    if text is None:
        return None, True
    compact = text.replace(" ", "")
    if not _MONEY_TEXT_RE.match(compact):
        return None, False
    negative = compact.startswith("(") or "-" in compact
    digits = compact.replace("(", "").replace(")", "").replace("$", "").replace("-", "").replace(",", "")
    if digits.startswith("."):
        digits = "0" + digits
    return (f"-{digits}" if negative else digits), True


def _provenance(expense_field: dict[str, Any], page: int) -> dict[str, Any]:
    value = expense_field.get("ValueDetection") or {}
    box = (value.get("Geometry") or {}).get("BoundingBox")
    return {
        # Each page is sent to Textract as its own one-page document, so
        # Textract's PageNumber is always 1: the page of the ORIGINAL file is used.
        "page": page,
        "label": _clean_text((expense_field.get("LabelDetection") or {}).get("Text")),
        "type": (expense_field.get("Type") or {}).get("Text"),
        "confidence": round(value["Confidence"], 1) if value.get("Confidence") is not None else None,
        "bbox": {k: round(v, 4) for k, v in box.items()} if box else None,
        "raw": value.get("Text"),
    }


def _page_line_text(response: dict[str, Any]) -> str:
    return "\n".join(b.get("Text", "") for b in response.get("Blocks", []) if b.get("BlockType") == "LINE")


def _map_page(page: int, response: dict[str, Any]) -> dict[str, Any]:
    """Header fields, amounts, lines, provenance and unreadable values for
    one page, with nothing invented: empty values are absent; values that
    are not what their field needs are reported as unreadable."""
    out: dict[str, Any] = {"page": page, "header": {}, "amounts": {}, "fees": [], "lines": [], "provenance": {},
                           "unreadable": [], "amount_values": {}, "text": _page_line_text(response),
                           "supplier_readings": []}
    for document in response.get("ExpenseDocuments", []):
        for f in document.get("SummaryFields", []):
            ftype = (f.get("Type") or {}).get("Text")
            label = (_clean_text((f.get("LabelDetection") or {}).get("Text")) or "").lower()
            raw_value = (f.get("ValueDetection") or {}).get("Text")
            value = _clean_text(raw_value)
            if value is None:
                continue
            prov = _provenance(f, page)
            currency = (f.get("Currency") or {}).get("Code")
            if currency and "currency" not in out["header"]:
                out["header"]["currency"] = currency
                out["provenance"]["currency"] = prov
            header_key = {"VENDOR_NAME": "supplier_name", "INVOICE_RECEIPT_ID": "document_number",
                          "INVOICE_RECEIPT_DATE": "issue_date", "DUE_DATE": "due_date",
                          "RECEIVER_NAME": "receiver_name", "RECEIVER_ADDRESS": "receiver_address",
                          "PAYMENT_TERMS": "payment_terms", "PO_NUMBER": "po_number"}.get(ftype)
            if ftype == "OTHER" and label in ("terms", "payment terms"):
                header_key = "payment_terms"
            if header_key == "supplier_name" and value not in out["supplier_readings"]:
                out["supplier_readings"].append(value)
            if header_key:
                if header_key not in out["header"]:
                    out["header"][header_key] = value
                    out["provenance"][header_key] = prov
                continue
            amount_key = _AMOUNT_TYPES.get(ftype)
            is_fee = ftype in _FEE_TYPES or (ftype == "OTHER" and any(w in label for w in _FEE_LABEL_WORDS))
            if amount_key or is_fee:
                money, readable = normalize_money_text(raw_value)
                if not readable and not amount_key:
                    # A label that merely mentions a charge ("Shipping info")
                    # but carries no amount: kept as information, not flagged.
                    out["header"].setdefault("other_fields", {})[label or ftype] = value
                    continue
                if not readable:
                    out["unreadable"].append({"field": amount_key, "raw": value, **prov})
                    continue
                if money is None:
                    continue
                if is_fee and not amount_key:
                    out["fees"].append({"label": _clean_text((f.get("LabelDetection") or {}).get("Text")) or ftype,
                                        "amount": money, **prov})
                    continue
                out["amount_values"].setdefault(amount_key, []).append({"amount": money, **prov})
        for group in document.get("LineItemGroups", []):
            for item in group.get("LineItems", []):
                line: dict[str, Any] = {"page": page, "extra": {}, "provenance": {}}
                for f in item.get("LineItemExpenseFields", []):
                    ftype = (f.get("Type") or {}).get("Text")
                    label = (_clean_text((f.get("LabelDetection") or {}).get("Text")) or "").lower()
                    value = _clean_text((f.get("ValueDetection") or {}).get("Text"))
                    prov = _provenance(f, page)
                    if ftype == "EXPENSE_ROW":
                        line["row_text"] = value
                        line["provenance"]["row"] = prov
                        continue
                    if value is None:
                        continue
                    key = {"ITEM": "description", "QUANTITY": "quantity", "UNIT_PRICE": "unit_price",
                           "PRICE": "line_amount"}.get(ftype)
                    if key is None:
                        if "mfg" in label or "manufacturer" in label:
                            key = "manufacturer_code"
                        elif "pack" in label and "size" in label:
                            key = "pack_size"
                        elif label == "brand":
                            key = "brand"
                        elif label in _UNIT_LABELS:
                            key = "unit"
                        elif label == "line":
                            key = "source_line_number"
                        elif ftype == "PRODUCT_CODE" and (not label or any(label.startswith(w) for w in _ITEM_CODE_LABELS)):
                            key = "supplier_item_code"
                        elif ftype == "OTHER" and any(label.startswith(w) for w in _ITEM_CODE_LABELS):
                            key = "supplier_item_code"
                    if key is None:
                        line["extra"][label or ftype] = value
                        continue
                    if key in line:  # never overwrite a first reading; keep the second as extra
                        line["extra"][f"{key} (also read)"] = value
                        continue
                    if key in ("quantity", "unit_price", "line_amount"):
                        money, readable = normalize_money_text(value)
                        if not readable:
                            line.setdefault("unreadable", []).append(f"{key}: {value!r}")
                            continue
                        value = money
                    line[key] = value
                    line["provenance"][key] = prov
                out["lines"].append(line)
    return out


def map_pages_to_invoices(page_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups pages into invoices by the invoice number Textract read on
    each page: a page carrying a different number starts a new invoice; a
    page without one continues the current invoice. Within an invoice the
    first value read for each header field is kept (with its page/position);
    each amount keeps EVERY distinct value read, so two different totals
    are a visible conflict, never a silent choice."""
    invoices: list[dict[str, Any]] = []
    current = None
    for result in page_results:
        page = _map_page(result["page"], result["response"])
        number = page["header"].get("document_number")
        if current is None or (number and current["header"].get("document_number") and number != current["header"]["document_number"]):
            current = {"pages": [], "header": {}, "provenance": {}, "amount_values": {}, "fees": [], "lines": [],
                       "unreadable": [], "text": [], "supplier_readings": []}
            invoices.append(current)
        current["pages"].append(page["page"])
        current["text"].append(page["text"])
        for key, value in page["header"].items():
            if key not in current["header"]:
                current["header"][key] = value
                if key in page["provenance"]:
                    current["provenance"][key] = page["provenance"][key]
        for name in page["supplier_readings"]:
            if name not in current["supplier_readings"]:
                current["supplier_readings"].append(name)
        for key, values in page["amount_values"].items():
            current["amount_values"].setdefault(key, []).extend(values)
        current["fees"].extend(page["fees"])
        current["lines"].extend(page["lines"])
        current["unreadable"].extend(page["unreadable"])
    for invoice in invoices:
        invoice["text"] = "\n".join(invoice["text"])
        invoice["amounts"], invoice["conflicts"] = {}, []
        for key, values in invoice["amount_values"].items():
            distinct = sorted({v["amount"] for v in values})
            if len(distinct) == 1:
                invoice["amounts"][key] = distinct[0]
                invoice["provenance"][key] = values[0]
            else:
                invoice["conflicts"].append(f"{key}: different values read {', '.join(distinct)}")
        if invoice["fees"]:
            invoice["amounts"]["fees"] = [{"label": f["label"], "amount": f["amount"]} for f in invoice["fees"]]
        if len(invoice["supplier_readings"]) > 1:
            # Several different supplier names were read (logo, remit-to
            # block...): the first is kept, all are shown for review.
            invoice["header"]["supplier_name_readings"] = invoice["supplier_readings"]
    return invoices


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
