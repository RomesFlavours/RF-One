#!/usr/bin/env python
"""Focused tests for the Invoice Intake provider-agnostic extraction
boundary (CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001_FOUNDATION_V1).

Covers: provider adapter contract, normalized draft creation, multi-file
document handling, raw-response preservation, and the absence of any
Purchasing dependency. Uses only the small real samples already under
`01 Domains/Shared Domains/Administration/Invoice Intake/Invoices/Raw/` — no
large or production AWS calls are made; the Textract provider is validated
against `botocore.stub.Stubber` with a canned, schema-accurate response,
never a real network call.

Usage:
    python test_invoice_intake_providers.py
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from providers.base import InvoiceSourceSubmission, NormalizedInvoice, RawExtractionResult, SourceFile  # noqa: E402
from providers.tesseract_provider import TesseractProvider  # noqa: E402
from providers.textract_provider import TextractProvider  # noqa: E402
from providers import source_preservation  # noqa: E402

# The local OCR path needs the actual Tesseract *binary* on PATH, not just
# the `pytesseract` Python wrapper — a real, pre-existing, documented
# environment prerequisite (see this tool's own README) that this
# provider-boundary task does not install. Digital-PDF extraction (via
# pdfplumber) never needs it; only image/scanned-photo extraction does.
TESSERACT_BINARY_AVAILABLE = shutil.which("tesseract") is not None

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_RAW_SAMPLES_DIR = os.path.join(
    _REPO_ROOT, "01 Domains", "Shared Domains", "Administration", "Invoice Intake", "Invoices", "Raw",
)


class Result:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.skipped: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)

    def skip(self, description: str) -> None:
        self.skipped.append(description)


def _real_pdf_sample() -> str:
    """Targets `Invoice 6855.pdf` specifically — the one digital-text PDF
    this tool's own README documents as reading "almost perfectly" — rather
    than an arbitrary `glob` match. Other PDF files have since appeared
    alongside it in `Invoices/Raw/` (added independently of this task); a
    non-deterministic pick would make this test's outcome depend on
    whichever happens to sort first."""
    path = os.path.join(_RAW_SAMPLES_DIR, "Invoice 6855.pdf")
    assert os.path.isfile(path), f"Expected real PDF sample not found: {path}"
    return path


def _real_jpg_samples(n: int) -> list[str]:
    matches = sorted(glob.glob(os.path.join(_RAW_SAMPLES_DIR, "*.jpg")))
    assert len(matches) >= n, f"Expected at least {n} real jpg samples under {_RAW_SAMPLES_DIR}, found {len(matches)}"
    return matches[:n]


def _make_submission(paths: list[str]) -> InvoiceSourceSubmission:
    return InvoiceSourceSubmission(
        source_files=[SourceFile(path=p, original_filename=os.path.basename(p)) for p in paths],
        invoking_domain_reference="TEST-REF-001",
    )


def test_provider_adapter_contract(result: Result) -> None:
    """Both providers expose the same `.name` + `.extract()` shape, and
    `.extract()` returns exactly a (NormalizedInvoice, RawExtractionResult)
    pair for both — the contract `base.ExtractionProvider` defines."""
    tesseract = TesseractProvider()
    textract = TextractProvider(client_factory=lambda: _StubTextractClient())

    result.check("TesseractProvider has a name", isinstance(tesseract.name, str) and bool(tesseract.name))
    result.check("TextractProvider has a name", isinstance(textract.name, str) and bool(textract.name))
    result.check("provider names are distinct", tesseract.name != textract.name)

    submission = _make_submission([_real_pdf_sample()])
    for provider in (tesseract, textract):
        normalized, raw = provider.extract(submission)
        result.check(
            f"{provider.name}.extract() returns (NormalizedInvoice, RawExtractionResult)",
            isinstance(normalized, NormalizedInvoice) and isinstance(raw, RawExtractionResult),
        )
        result.check(f"{provider.name} raw result records its own provider_name", raw.provider_name == provider.name)


def test_normalized_draft_creation_from_real_digital_pdf(result: Result) -> None:
    """The real digital-PDF sample produces a NormalizedInvoice with at
    least a supplier name and a total via the local Tesseract/PDF-text
    provider (mirrors the existing README's own claim that this file reads
    almost perfectly)."""
    submission = _make_submission([_real_pdf_sample()])
    normalized, raw = TesseractProvider().extract(submission)

    result.check("header is a NormalizedHeader with a supplier_name extracted", bool(normalized.header.supplier_name))
    result.check("totals.total was extracted from the real digital PDF", bool(normalized.totals.total))
    result.check("metadata.provider_name records which provider ran", normalized.metadata.provider_name == "tesseract-local")
    result.check("metadata.source_files lists exactly the one real file", normalized.metadata.source_files == [os.path.basename(_real_pdf_sample())])
    result.check("raw response preserves the acquisition method used", "acquisition_methods" in raw.raw_response)
    result.check("to_dict() round-trips without error", isinstance(normalized.to_dict(), dict))


def test_multi_file_document_handling(result: Result) -> None:
    """Two of the real phone-photo samples, submitted together as one
    explicitly-grouped InvoiceSourceSubmission, merge into ONE
    NormalizedInvoice — not two — with lines drawn from both files."""
    photo_paths = _real_jpg_samples(2)
    submission = _make_submission(photo_paths)

    if TESSERACT_BINARY_AVAILABLE:
        normalized, raw = TesseractProvider().extract(submission)
        result.check(
            "metadata.source_files lists both grouped files, in submission order",
            normalized.metadata.source_files == [os.path.basename(p) for p in photo_paths],
        )
        result.check(
            "raw response preserves a per-file entry for each grouped file",
            set(raw.raw_response["per_file"].keys()) == {os.path.basename(p) for p in photo_paths},
        )
        result.check("exactly one NormalizedInvoice is produced for the group (not two)", isinstance(normalized, NormalizedInvoice))
    else:
        result.skip(
            "local Tesseract-provider multi-file JPG checks — tesseract binary not installed in this "
            "environment (pre-existing, documented prerequisite; not installed by this task)"
        )

    # Same multi-file grouping through the Textract provider (stubbed) —
    # confirms the merge logic is provider-agnostic, not Tesseract-specific.
    textract_normalized, textract_raw = TextractProvider(client_factory=lambda: _StubTextractClient()).extract(submission)
    result.check(
        "Textract provider also merges the same multi-file group into one NormalizedInvoice",
        textract_normalized.metadata.source_files == [os.path.basename(p) for p in photo_paths],
    )
    result.check(
        "Textract provider preserves a per-file raw response for each grouped file",
        set(textract_raw.raw_response["per_file"].keys()) == {os.path.basename(p) for p in photo_paths},
    )
    result.check(
        "Textract-mapped header/line fields from the stub are present in the merged draft",
        textract_normalized.header.supplier_name == "Acme Foods (stub)"
        and len(textract_normalized.lines) == 2 * len(photo_paths),
    )
    result.check(
        "Textract provider exposes line-level confidence (unlike the local OCR path)",
        all(line.confidence is not None for line in textract_normalized.lines),
    )
    result.check(
        "an unmapped Textract summary field type is preserved in header.extra, never discarded",
        "RECEIVER_NAME" in textract_normalized.header.extra,
    )


def test_raw_response_preservation(result: Result) -> None:
    """`source_preservation.py` writes the original file, the raw provider
    response, and acquisition metadata to disk — append-only, one new
    directory per submission, nothing overwritten."""
    tmp_dir = tempfile.mkdtemp(prefix="invoice_intake_test_")
    try:
        original_pdf = _real_pdf_sample()
        preserved = source_preservation.preserve_source_file(original_pdf, os.path.basename(original_pdf))
        result.check("preserve_source_file() copies into uploads/, original untouched", os.path.isfile(preserved.path) and os.path.isfile(original_pdf))
        result.check("preserved file content matches the original byte-for-byte", open(preserved.path, "rb").read() == open(original_pdf, "rb").read())

        submission = _make_submission([preserved.path])
        normalized, raw = TesseractProvider().extract(submission)
        submission_dir_1 = source_preservation.preserve_extraction_result(submission, normalized, raw)
        submission_dir_2 = source_preservation.preserve_extraction_result(submission, normalized, raw)

        result.check("each preservation call gets its own, distinct directory (append-only)", submission_dir_1 != submission_dir_2)
        for d in (submission_dir_1, submission_dir_2):
            result.check(
                f"acquisition_metadata.json exists in {os.path.basename(d)}",
                os.path.isfile(os.path.join(d, "acquisition_metadata.json")),
            )
            result.check(
                f"raw_provider_response.json exists in {os.path.basename(d)}",
                os.path.isfile(os.path.join(d, "raw_provider_response.json")),
            )
            result.check(
                f"normalized_draft.json exists in {os.path.basename(d)}",
                os.path.isfile(os.path.join(d, "normalized_draft.json")),
            )
    finally:
        # Clean up only what THIS test created under uploads/ — never touch
        # any pre-existing real upload.
        try:
            os.remove(preserved.path)
        except OSError:
            pass
        for d in (submission_dir_1, submission_dir_2):
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_no_purchasing_dependency(result: Result) -> None:
    """None of the new provider-boundary modules import Purchased's bridge/
    rfone_data_store — the foundation task must not connect Invoice Intake
    to Purchased/Purchasing directly."""
    import ast

    providers_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "providers")
    forbidden = ("purchasing_bridge", "purchased_bridge", "rfone_data_store")
    offending: list[str] = []
    for filename in os.listdir(providers_dir):
        if not filename.endswith(".py"):
            continue
        path = os.path.join(providers_dir, filename)
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=filename)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(f in name for name in names for f in forbidden):
                offending.append(f"{filename}: {names}")

    result.check("no providers/*.py file imports purchased_bridge/purchasing_bridge or rfone_data_store", not offending)


class _StubTextractClient:
    """A `botocore.stub.Stubber`-wrapped Textract client returning one
    fixed, schema-accurate `AnalyzeExpense` response — never a real AWS
    call, never real credentials. Built once per instantiation so each
    call in a multi-file submission gets a fresh stubbed response."""

    def analyze_expense(self, Document):
        import boto3
        from botocore.stub import Stubber

        client = boto3.client("textract", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
        stubber = Stubber(client)
        canned_response = {
            "DocumentMetadata": {"Pages": 1},
            "ExpenseDocuments": [
                {
                    "ExpenseIndex": 1,
                    "SummaryFields": [
                        {"Type": {"Text": "VENDOR_NAME", "Confidence": 99.0}, "ValueDetection": {"Text": "Acme Foods (stub)", "Confidence": 98.5}},
                        {"Type": {"Text": "INVOICE_RECEIPT_ID", "Confidence": 99.0}, "ValueDetection": {"Text": "INV-STUB-1", "Confidence": 97.0}},
                        {"Type": {"Text": "TOTAL", "Confidence": 99.0}, "ValueDetection": {"Text": "123.45", "Confidence": 96.0}},
                        {"Type": {"Text": "RECEIVER_NAME", "Confidence": 90.0}, "ValueDetection": {"Text": "Rome's Flavours", "Confidence": 88.0}},
                    ],
                    "LineItemGroups": [
                        {
                            "LineItemGroupIndex": 1,
                            "LineItems": [
                                {
                                    "LineItemExpenseFields": [
                                        {"Type": {"Text": "ITEM", "Confidence": 90.0}, "ValueDetection": {"Text": "Tomatoes", "Confidence": 91.0}},
                                        {"Type": {"Text": "PRICE", "Confidence": 90.0}, "ValueDetection": {"Text": "10.00", "Confidence": 88.0}},
                                    ]
                                },
                                {
                                    "LineItemExpenseFields": [
                                        {"Type": {"Text": "ITEM", "Confidence": 90.0}, "ValueDetection": {"Text": "Onions", "Confidence": 92.0}},
                                        {"Type": {"Text": "PRICE", "Confidence": 90.0}, "ValueDetection": {"Text": "5.00", "Confidence": 89.0}},
                                    ]
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        stubber.add_response("analyze_expense", canned_response, {"Document": Document})
        stubber.activate()
        return client.analyze_expense(Document=Document)


def main() -> int:
    result = Result()
    for test_fn in (
        test_provider_adapter_contract,
        test_normalized_draft_creation_from_real_digital_pdf,
        test_multi_file_document_handling,
        test_raw_response_preservation,
        test_no_purchasing_dependency,
    ):
        test_fn(result)

    total = len(result.passed) + len(result.failed)
    skip_note = f", {len(result.skipped)} skipped" if result.skipped else ""
    if not result.failed:
        print(f"Invoice Intake provider boundary tests: SUCCESS ({len(result.passed)}/{total} checks passed{skip_note})")
        for description in result.skipped:
            print(f"  SKIPPED: {description}")
        return 0
    print(f"Invoice Intake provider boundary tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed{skip_note})")
    for description in result.failed:
        print(f"  FAILED: {description}")
    for description in result.skipped:
        print(f"  SKIPPED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
