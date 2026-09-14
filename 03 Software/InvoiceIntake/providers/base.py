"""Invoice Source Contract + NormalizedInvoice — the provider-agnostic
extraction boundary, per `01 Domains/Cross Domain/Administration/Invoice
Intake/CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001.md` §3/§4/§5/§6/§7.

Every provider (`tesseract_provider.py`, `textract_provider.py`) implements
`ExtractionProvider.extract()` against this exact contract, so the rest of
Invoice Intake — and, later, whatever consumes its output — never depends
on which provider actually ran. Nothing here calls Purchasing or any other
Business Domain; this module has no import of `rfone_data_store` or
`purchased_bridge` (renamed from `purchasing_bridge`) at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

UTC = timezone.utc


@dataclass
class SourceFile:
    """One file that is part of a submission. `path` points to the file's
    ALREADY-preserved location on disk (§5) — nothing in this contract
    re-saves, re-encodes, or mutates the original."""

    path: str
    original_filename: str
    content_type: str | None = None


@dataclass
class InvoiceSourceSubmission:
    """§3 — the Invoice Source Contract's unstructured-document path: one
    logical invoice, one or more source files (multi-file/multi-image
    support, §8 of the foundation task — grouping is explicit: the caller
    assembles `source_files` itself, nothing here infers that separate
    uploads belong together).

    `invoking_domain_reference` is opaque and carried through unread — this
    contract does not implement invocation/return (§10 of the spec); it
    exists here only so the field is part of the shape from the start."""

    source_files: list[SourceFile]
    invoking_domain_reference: str | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class NormalizedHeader:
    """§7 Header. Every field is `None` unless the source actually provided
    it — nothing here is ever defaulted or guessed. `extra` is not named in
    the spec's own Header field list, but is added here for consistency
    with Lines/Totals (both of which the spec explicitly gives an "any
    other materially present" catch-all) — required by §7's own general
    rule: "Do not discard invoice information merely because a later
    Domain may not use it." A provider that exposes a header-level fact
    with no named field to hold it (e.g. Textract's `RECEIVER_NAME`) must
    have somewhere faithful to put it."""

    supplier_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    reference_numbers: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedLine:
    """§7 Lines. `confidence` is populated only by a provider that actually
    exposes it (Textract does; the wrapped local OCR path does not — see
    `tesseract_provider.py`). `extra` preserves any materially present
    field that does not fit the named ones, per §7's "do not discard
    invoice information merely because a later Domain may not use it"."""

    description: str | None = None
    supplier_product_code: str | None = None
    quantity: str | None = None
    unit: str | None = None
    unit_price: str | None = None
    discount: str | None = None
    tax: str | None = None
    fees: str | None = None
    line_total: str | None = None
    confidence: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedTotals:
    """§7 Totals."""

    subtotal: str | None = None
    discounts: str | None = None
    tax: str | None = None
    fees: str | None = None
    total: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedMetadata:
    """§7 Metadata. `review_status` is recorded here as a plain string, not
    an implementation of the full RECEIVED/EXTRACTED/READY/NEEDS_REVIEW/
    APPROVED lifecycle (§8) — that lifecycle (and the trusted-supplier/
    confidence gate that decides READY vs. NEEDS_REVIEW) is out of scope
    for this foundation task; every draft this task produces is left at
    `"EXTRACTED"`, the one lifecycle state that requires no supplier-trust
    or coherence decision."""

    source_files: list[str] = field(default_factory=list)
    language: str | None = None
    extraction_confidence: float | None = None
    review_status: str = "EXTRACTED"
    version: int = 1
    provider_name: str = ""
    acquired_at: datetime | None = None


@dataclass
class NormalizedInvoice:
    """§7 — the provider-agnostic normalized draft every provider produces,
    regardless of which one ran."""

    header: NormalizedHeader
    lines: list[NormalizedLine]
    totals: NormalizedTotals
    metadata: NormalizedMetadata

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict view for tests/inspection/preservation — never used
        as a substitute for the raw provider response (§6)."""
        return {
            "header": vars(self.header) | {"reference_numbers": list(self.header.reference_numbers)},
            "lines": [vars(line) | {"extra": dict(line.extra)} for line in self.lines],
            "totals": vars(self.totals) | {"extra": dict(self.totals.extra)},
            "metadata": {
                **vars(self.metadata),
                "acquired_at": self.metadata.acquired_at.isoformat() if self.metadata.acquired_at else None,
            },
        }


@dataclass
class RawExtractionResult:
    """§5/§6 — the Provider Mirror: the raw provider response preserved
    verbatim, alongside which provider produced it and when it was
    retrieved. Never read by anything outside the provider that produced
    it or `source_preservation.py`'s own persistence helper — no consuming
    Domain may depend on this shape directly (§6)."""

    provider_name: str
    raw_response: Any
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ExtractionProvider(Protocol):
    """§4 — the provider-agnostic extraction boundary. Every provider
    implements exactly this method; nothing outside a provider module may
    depend on provider-specific request/response shapes."""

    name: str

    def extract(self, submission: InvoiceSourceSubmission) -> tuple[NormalizedInvoice, RawExtractionResult]: ...
