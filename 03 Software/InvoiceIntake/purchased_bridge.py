"""Bridge from InvoiceIntake's OCR/review output to the canonical Purchased
persistence layer (originally TASK_PURCHASING_004; realigned by "Align
legacy Invoice Intake with Purchased").

Ownership (Align legacy Invoice Intake with Purchased): Invoice Intake is a
process that feeds Purchased (`01 Domains/Shared Domains/Purchased/README.md`)
— a Shared Domain, not owned by Restaurant or any other Business Domain.
Purchased owns the Purchase Fact: capture + normalize + publish. This module
is that capture-and-normalize step for InvoiceIntake's reviewed header/lines:
it maps them onto the existing `PurchaseDocument`/`PurchaseLine` model
(`03 Software/RF-One Data Store/rfone_data_store/purchasing/`, unchanged —
see PURCHASING.md's ownership note) and writes them through
`rfone_data_store.purchasing.repository`, the same persistence module
Restaurant/Purchasing's own Physical Receiving uses. Restaurant/Purchasing is
a *consumer* of the resulting Purchase Fact, never a prerequisite for
creating one — nothing in this module calls a Purchasing decision/receiving
function (Purchase Order, Configured Expectation, Physical Receiving, Alert).
`excel_store.py` itself is untouched and still available as a secondary
export/debugging capability (`app.py` calls both, but only this module's
result is the canonical PurchaseDocumentId shown to the user) — see
`03 Software/RF-One Data Store/PURCHASING.md`.

This module deliberately does NOT invent facts the OCR/parser did not
extract: an unparsed date or amount is passed through as `None` (Unknown),
never defaulted, matching Purchasing/EntityDefinitions.md's "extract what
the source knows; do not invent what the source does not know."

Functional state (Purchased/README.md, "NORMALIZED / HUMAN"): this module
computes a best-effort NORMALIZED/HUMAN signal for what it just saved and
records it as a `PurchasingValidationLogEntry` (WARNING, OPEN) when the
document or a line looks unreliable — the same mechanism the repository
already used for an unclassified Supplier Product. The actual functional
state is always derived on demand from these entries
(`repository.get_document_functional_status`/`get_line_functional_status`),
never stored as its own column. The specific heuristic here (OCR/photo
acquisition defaults to HUMAN; a fully-parsed digital-PDF-text header
defaults to NORMALIZED) is InvoiceIntake's own provisional rule for this
prototype's parser — not a universal threshold; Purchased/README.md's
"Source/format validation and training" explicitly leaves the real
per-Supplier/format training criteria (N, accuracy threshold) as a future,
configurable concern.

Duplicate/correction handling (Purchased/README.md, "Duplicate handling" and
"Supplier-side corrections"): before inserting, this module looks up any
existing Purchase Document sharing the same (Supplier, Document Number)
identity.
  - Same identity, same `document_type`, equivalent content (same total and
    issue date) -> a re-submission of the same source document through a
    different channel: the existing PurchaseDocumentId is returned, nothing
    new is inserted ("exactly one purchase fact per actual source document").
  - Same identity, same `document_type`, different content -> ambiguous
    (could be a corrected resend, could be a data problem): a new row is
    still inserted (never overwrite/lose the prior fact), but flagged HUMAN
    via a WARNING validation log entry cross-referencing the earlier
    PurchaseDocumentId.
  - Same identity, different `document_type` (e.g. a "Credit Memo" against a
    prior "Invoice") -> a deliberate supplier-side correction: inserted as
    its own new row (a compensating economic fact, never a retroactive
    rewrite), linked to the original via an INFORMATION validation log entry
    that does not by itself force HUMAN.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    create_configured_engine,
    create_session_factory,
    get_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.purchasing import repository as repo  # noqa: E402

UTC = timezone.utc

_DATE_FORMATS = ("%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y-%m-%d")

_SURCHARGE_KEYWORDS = ("surcharge", "delivery fee", "fuel", "service fee", "environmental fee")
_DISCOUNT_KEYWORDS = ("discount", "credit", "rebate", "bonus")

# Document types InvoiceIntake treats as a supplier-side correction of a
# prior document rather than a first-time invoice (Purchased/README.md,
# "Supplier-side corrections" — illustrative, non-exhaustive; the field
# itself stays free text, matching PurchaseDocument.document_type).
CORRECTION_DOCUMENT_TYPES = {"credit memo", "credit note", "corrected invoice", "return credit", "adjustment"}


def guess_line_type(description: str) -> str:
    """Best-effort default only — the review screen lets the user correct
    it before anything is saved, consistent with "human validation always
    prevails" (`01 Domains/Business Domain/Restaurant/Purchasing/BusinessRules.md`,
    Design Principles)."""

    lowered = (description or "").lower()
    if any(keyword in lowered for keyword in _SURCHARGE_KEYWORDS):
        return "SURCHARGE"
    if any(keyword in lowered for keyword in _DISCOUNT_KEYWORDS):
        return "DISCOUNT"
    return "PRODUCT"


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None  # unparsed -> Unknown, never guessed


def _parse_money_minor(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in ("", "-", "."):
        return None
    try:
        return int((Decimal(cleaned) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in ("", "-", "."):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _get_or_create_default_restaurant(session) -> int:
    """The single economic/operational scope object this invoice belongs to
    (Purchased/README.md, "Scope — one invoice, one economic object").
    InvoiceIntake has no restaurant-selection UI yet (out of scope for this
    task — see PURCHASING.md, "Remaining gaps"). Reuses the single existing
    `Restaurant` row when there is exactly one (the normal case for this
    repository's current single-restaurant data), otherwise creates a
    clearly-labeled placeholder row rather than guessing which one applies.
    A genuinely multi-scope source (more than one candidate scope for one
    invoice) is not handled here — Purchased/README.md routes that anomaly to
    HUMAN rather than designing a standard allocation model, and this
    prototype has no such case to detect yet.
    """

    from sqlalchemy import select

    restaurants = session.scalars(select(m.Restaurant)).all()
    if len(restaurants) == 1:
        return restaurants[0].id
    for restaurant in restaurants:
        if restaurant.name == "InvoiceIntake Default Restaurant":
            return restaurant.id
    placeholder = m.Restaurant(name="InvoiceIntake Default Restaurant")
    session.add(placeholder)
    session.flush()
    return placeholder.id


def _looks_reliably_read(header: dict, document_header: dict) -> bool:
    """InvoiceIntake's own provisional NORMALIZED/HUMAN heuristic (see module
    docstring): a digital-PDF-text extraction with every key header field
    successfully parsed is NORMALIZED; a photo/OCR-sourced document, or one
    missing a key field, is HUMAN. This directly operationalizes this
    prototype's own documented reality (README.md: digital PDF text reads
    "almost perfectly"; phone photos "read only partially and require manual
    corrections") — it is not the future per-Supplier/format trust-training
    mechanism Purchased/README.md leaves as an open, configurable concern."""

    if (header.get("acquisition_method") or "").upper() == "OCR":
        return False
    return bool(
        header.get("supplier_name")
        and document_header.get("issue_date") is not None
        and document_header.get("total_amount_minor") is not None
    )


def _record_conflict_or_correction(
    session,
    new_document: "m.PurchaseDocument",
    existing: "m.PurchaseDocument",
    is_correction: bool,
) -> None:
    if is_correction:
        repo.add_validation_log_entry(
            session,
            purchase_document_id=new_document.id,
            severity="INFORMATION",
            message=(
                f"Supplier-side correction ({new_document.document_type!r}) of "
                f"PurchaseDocumentId={existing.id} (document_number={existing.document_number!r})."
            ),
            suggested_action=None,
        )
    else:
        repo.add_validation_log_entry(
            session,
            purchase_document_id=new_document.id,
            severity="WARNING",
            message=(
                f"Same invoice identity (supplier_id={existing.supplier_id}, "
                f"document_number={existing.document_number!r}) as PurchaseDocumentId={existing.id}, "
                "but with different content (total/issue date differ) — not auto-resolved as a duplicate."
            ),
            suggested_action="Confirm whether this is a corrected resend of the same invoice or two distinct documents.",
        )


def save_purchase_document(header: dict, lines: list[dict], source_file: str) -> int:
    """Maps InvoiceIntake's reviewed header/lines onto the canonical
    Purchased Purchase Fact and persists them. Returns the resulting
    `PurchaseDocumentId` — either a newly inserted document, or a pre-existing
    one when this submission is recognized as a duplicate of it (see module
    docstring, "Duplicate/correction handling").

    `header` keys (from `app.py`'s `/save` route): supplier_name,
    document_number, document_type, issue_date, acquisition_method,
    currency, total_amount.
    `lines` items: description, quantity, unit, unit_price, line_amount,
    line_type (added by the review form; defaults to PRODUCT if absent).
    """

    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        restaurant_id = _get_or_create_default_restaurant(session)
        supplier_name = header.get("supplier_name") or "Unknown Supplier"
        supplier = repo.get_or_create_supplier(session, restaurant_id, supplier_name)

        document_type = header.get("document_type") or "Invoice"
        document_number = (header.get("document_number") or "").strip()

        document_header = {
            "document_number": document_number or None,
            "document_type": document_type,
            "issue_date": _parse_date(header.get("issue_date")),
            "acquisition_method": header.get("acquisition_method") or None,
            "currency": header.get("currency") or None,
            "total_amount_minor": _parse_money_minor(header.get("total_amount")),
            "status": "RECORDED",
            "source_reference": source_file or None,
            "source_provenance": (
                f"InvoiceIntake upload; raw issue_date as read: {header.get('issue_date')!r}"
                if header.get("issue_date") and _parse_date(header.get("issue_date")) is None
                else "InvoiceIntake upload"
            ),
        }

        # --- Duplicate handling (Purchased/README.md, "Duplicate handling") ---
        existing_matches = repo.find_purchase_documents_by_number(session, supplier.id, document_number)
        is_correction = document_type.strip().lower() in CORRECTION_DOCUMENT_TYPES
        duplicate_of: "m.PurchaseDocument | None" = None
        conflict_with: "m.PurchaseDocument | None" = None
        if existing_matches and not is_correction:
            new_issue_date = document_header["issue_date"]
            # SQLite has no real timestamptz storage, so a `DateTime(timezone=True)`
            # value read back from the database comes back naive; compare
            # tzinfo-insensitively rather than risk every re-fetch looking
            # like a content conflict.
            new_issue_date_naive = new_issue_date.replace(tzinfo=None) if new_issue_date is not None else None
            for candidate in existing_matches:
                if candidate.document_type.strip().lower() != document_type.strip().lower():
                    continue  # a differently-typed existing row is handled as a correction target, not a duplicate/conflict
                candidate_issue_date_naive = (
                    candidate.issue_date.replace(tzinfo=None) if candidate.issue_date is not None else None
                )
                same_content = (
                    candidate.total_amount_minor == document_header["total_amount_minor"]
                    and candidate_issue_date_naive == new_issue_date_naive
                )
                if same_content:
                    duplicate_of = candidate
                    break
                conflict_with = candidate
        if duplicate_of is not None:
            # Same source document, arrived again through a different
            # channel: exactly one purchase fact, nothing new inserted.
            return duplicate_of.id

        repository_lines = []
        for line in lines:
            description = (line.get("description") or "").strip()
            quantity = _parse_decimal(line.get("quantity"))
            unit_price_minor = _parse_money_minor(line.get("unit_price"))
            line_amount_minor = _parse_money_minor(line.get("line_amount"))
            if not description and quantity is None and unit_price_minor is None and line_amount_minor is None:
                continue  # a fully blank review row, never persisted

            line_type = line.get("line_type") or guess_line_type(description)
            repository_lines.append(
                {
                    "line_type": line_type,
                    "raw_description": description or "(no description)",
                    "source_amount_minor": line_amount_minor,
                    "quantity": quantity if line_type == "PRODUCT" else None,
                    "purchase_unit": (line.get("unit") or None) if line_type == "PRODUCT" else None,
                    "unit_price_minor": unit_price_minor if line_type == "PRODUCT" else None,
                    "_unreliable": line_type == "PRODUCT" and not description,
                }
            )

        unreliable_line_flags = [entry.pop("_unreliable") for entry in repository_lines]
        document = repo.record_purchase_document(session, supplier.id, document_header, repository_lines)
        session.commit()

        # --- Functional state (Purchased/README.md, "NORMALIZED / HUMAN") ---
        if not _looks_reliably_read(header, document_header):
            repo.add_validation_log_entry(
                session,
                purchase_document_id=document.id,
                severity="WARNING",
                message=(
                    "Document read via OCR and/or missing a key header field "
                    "(supplier, issue date, or total) — not reliable enough to trust automatically."
                ),
                suggested_action="Verify supplier, issue date and total against the original document.",
            )
        ordered_lines = sorted(document.lines, key=lambda line: line.id)
        for persisted_line, was_unreliable in zip(ordered_lines, unreliable_line_flags):
            if was_unreliable:
                repo.add_validation_log_entry(
                    session,
                    purchase_document_id=document.id,
                    purchase_line_id=persisted_line.id,
                    severity="WARNING",
                    message="Product line has no description — likely an unreliable OCR/parser read.",
                    suggested_action="Confirm or correct this line's description.",
                )

        if duplicate_of is None and conflict_with is not None:
            _record_conflict_or_correction(session, document, conflict_with, is_correction=False)
        elif is_correction and existing_matches:
            # Link to the most recent same-identity document of a different
            # type — a deliberate correction, never routed to HUMAN by itself.
            _record_conflict_or_correction(session, document, existing_matches[-1], is_correction=True)

        session.commit()
        return document.id


def get_saved_document_functional_status(purchase_document_id: int) -> str:
    """NORMALIZED / HUMAN for an already-saved document (Purchased/README.md,
    "NORMALIZED / HUMAN") — a thin read-only wrapper around
    `repository.get_document_functional_status` for `app.py`'s confirmation
    screen."""

    url = get_database_url()
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        return repo.get_document_functional_status(session, purchase_document_id)
