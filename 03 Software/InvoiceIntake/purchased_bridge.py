"""Bridge from InvoiceIntake's OCR/review output to the canonical Purchased
persistence layer (originally TASK_PURCHASING_004; realigned by "Align
legacy Invoice Intake with Purchased").

Ownership (Align legacy Invoice Intake with Purchased): Invoice Intake is a
process that feeds Purchased (`01 Domains/Cross Domain/Purchased/README.md`)
— a Cross Domain, not owned by Restaurant or any other Business Domain.
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
`excel_store.py` itself is untouched and still importable as a standalone
debugging utility, but `app.py`'s `/upload` route no longer calls it
("Close Purchased Human Review Reliability Gaps" §2: manual upload now
saves through `save_purchase_documents_from_batch()` below, the same
entry point the mailbox pipeline uses, which never called `excel_store`
either) — see `03 Software/RF-One Data Store/PURCHASING.md`.

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
never stored as its own column.

Ownership realignment ("Purchased Invoice Intake — Improve Generic Parser
and Prepare Supplier Format Training"): the decision is now based
**entirely on the completeness/coherence of the extracted fields** —
supplier recognized, date recognized, total recognized, no conflicting
totals, line amounts (when any were extracted) arithmetically summing to
the total. *How* the text was acquired (OCR vs. a digital PDF's
embedded text vs., in the future, a trusted API/EDI feed) is deliberately
NOT a factor any more — "the document went through OCR" never by itself
implies HUMAN, and never by itself implies NORMALIZED either (Purchased/
README.md, "Source/format validation and training": SOURCE FORMAT
reliability and ITEM MAPPING/field-extraction reliability are two
different questions, and this module only ever answers the second one for
a single document). See `_validate_extracted_fields()` below. The real
per-Supplier/format trust-training mechanism (`supplier_format_training.py`)
remains a separate, purely observational foundation — nothing here reads
it back to influence a document's own result.

**Phase 1 ("Purchased Supplier+Format Training — Phase 1"):** before
resolving/validating anything, `header` is passed through
`supplier_format_rules.apply_supplier_specializations()` — a narrow,
second parsing stage (generic parser -> supplier-format specialization ->
validation) that corrects specific fields only for a Supplier+Format
combination whose raw text carries a real, verified recognition signature
(currently Prime Line Distributors and Costco Wholesale/direct — see that
module). It never invents a value its own targeted pattern does not find,
and every other Supplier's header passes through completely unchanged.

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
from dataclasses import dataclass
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

import invoice_splitter  # noqa: E402
import parser as invoice_parser  # noqa: E402
import supplier_format_rules  # noqa: E402
import supplier_format_training  # noqa: E402

UTC = timezone.utc

# 4-digit-year formats first, then 2-digit-year (Task requirement 2: "MM/DD/YY").
# %y follows Python's own POSIX-derived rule (00-68 -> 2000-2068, 69-99 ->
# 1969-1999) -- correct for this business's real invoice date range.
_DATE_FORMATS = (
    "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%m/%d/%y", "%d/%m/%y", "%m-%d-%y", "%d-%m-%y",
)
# A parsed date outside this window is treated as unparseable, not silently
# accepted -- catches an OCR-garbled year (e.g. "2620" misread from "2020")
# without guessing what the real year should have been ("NON introdurre
# inferenze arbitrarie" -- Task requirement 2, "se una data è ambigua -> HUMAN").
_PLAUSIBLE_YEAR_MIN = 2000

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
    now_year = datetime.now(UTC).year
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
        if not (_PLAUSIBLE_YEAR_MIN <= parsed.year <= now_year + 1):
            continue  # implausible year (e.g. an OCR-garbled digit) -- try another format, or give up
        return parsed
    return None  # unparsed/implausible -> Unknown, never guessed


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


def _resolve_supplier_name(session, restaurant_id: int, candidate: str, source_file: str | None) -> str | None:
    """Best-effort Supplier NAME resolution (Task requirement 5): prefers the
    document's own header text (`candidate`, already extracted by
    `parser.guess_supplier`), matched against Suppliers already known for
    this restaurant so the same real-world supplier is not fragmented into
    near-duplicate rows by a slightly different OCR read each time (e.g.
    "COSTCO WHOLESALE" one time, "Costco Wholesale #123" another). The
    source filename is consulted only as a SECONDARY signal, and only when
    the document's own text produced nothing plausible — never as the
    primary source of identity, and never to invent a Supplier that is not
    already known (Task: "NON inventare supplier identity").

    Returns `None` when nothing plausible could be resolved; the caller
    falls back to "Unknown Supplier" (unchanged from before this task) and
    the missing-supplier field counts against NORMALIZED in
    `_validate_extracted_fields()`.

    "Purchased Supplier Training Phase 2" (§9, "Supplier alias model"):
    also matches against known `SupplierAlias` rows — e.g. the pre-Phase-2
    dirty name "PRIME LINE DISTRIBUTORS INVOICE" now on file as an alias of
    the clean canonical "Prime Line Distributors" — always resolving to the
    Supplier's CURRENT canonical name, never the alias text itself.
    """

    from sqlalchemy import select

    # Only ever match against ALREADY-plausible known Suppliers -- a stray
    # "Unknown Supplier" or a short garbled name recorded before this task
    # (e.g. a bare "I") must never be propagated forward as if it were a
    # legitimate alias target, and a very short known name (<=3 chars) is
    # excluded from substring matching entirely: a 1-3 character string is
    # too likely to appear incidentally inside unrelated text/filenames to
    # be trustworthy evidence of identity either way.
    known_suppliers = [
        supplier
        for supplier in session.scalars(select(m.Supplier).where(m.Supplier.restaurant_id == restaurant_id)).all()
        if invoice_parser.looks_like_plausible_name(supplier.name) and len(supplier.name.strip()) > 3
    ]
    # (alias_name, canonical Supplier.name) pairs, same plausibility/length
    # filter as known_suppliers above -- an alias is only ever as
    # trustworthy as the Supplier it points to.
    known_supplier_ids = {supplier.id for supplier in known_suppliers}
    known_aliases = [
        (alias.alias_name, alias.supplier_id)
        for alias in session.scalars(
            select(m.SupplierAlias).where(m.SupplierAlias.supplier_id.in_(known_supplier_ids))
        ).all()
        if invoice_parser.looks_like_plausible_name(alias.alias_name) and len(alias.alias_name.strip()) > 3
    ] if known_supplier_ids else []
    supplier_by_id = {supplier.id: supplier for supplier in known_suppliers}

    candidate_plausible = invoice_parser.looks_like_plausible_name(candidate or "")
    if candidate_plausible:
        lowered_candidate = candidate.lower()
        for supplier in known_suppliers:
            lowered_known = supplier.name.lower()
            if lowered_known in lowered_candidate or lowered_candidate in lowered_known:
                return supplier.name  # reuse the canonical, already-known spelling
        for alias_name, supplier_id in known_aliases:
            lowered_alias = alias_name.lower()
            if lowered_alias in lowered_candidate or lowered_candidate in lowered_alias:
                return supplier_by_id[supplier_id].name  # the CURRENT canonical name, never the alias text
        return candidate  # a plausible new name the document itself states

    # The document's own text produced nothing plausible -- fall back to
    # checking whether a KNOWN Supplier's name appears in the source
    # filename (secondary evidence only; never used to fabricate a brand
    # new identity that isn't already on file).
    if source_file:
        lowered_filename = source_file.lower()
        for supplier in known_suppliers:
            if supplier.name.lower() in lowered_filename:
                return supplier.name
        for alias_name, supplier_id in known_aliases:
            if alias_name.lower() in lowered_filename:
                return supplier_by_id[supplier_id].name

    return None


@dataclass
class FieldValidationResult:
    is_normalized: bool
    reasons: list[str]


def _check_arithmetic_coherence(repository_lines: list[dict], total_amount_minor: int | None) -> bool | None:
    """True/False when checkable, `None` when not applicable (Task
    requirement 7, "arithmetic coherent where possible"). Not applicable
    when there is no total to check against, or no PRODUCT line carried a
    parsed amount at all (an empty/未-extracted line list must never count
    against a document — that is a known, separate line-parsing gap, not a
    coherence failure)."""

    if total_amount_minor is None:
        return None
    line_amounts = [line["source_amount_minor"] for line in repository_lines if line.get("source_amount_minor") is not None]
    if not line_amounts:
        return None
    lines_sum = sum(line_amounts)
    # Tolerance accounts for tax/fees/allocation not itemized as their own
    # PRODUCT line amount -- 5%, or at least $1.00 for small documents.
    tolerance = max(100, abs(total_amount_minor) // 20)
    return abs(lines_sum - total_amount_minor) <= tolerance


def _validate_extracted_fields(
    resolved_supplier_name: str | None, document_header: dict, repository_lines: list[dict], raw_text: str
) -> FieldValidationResult:
    """Replaces the old OCR-implies-HUMAN rule (Task requirement 6, "OCR ≠
    HUMAN automatico"): the decision depends only on the completeness and
    internal coherence of what was actually extracted, never on *how* the
    text was acquired. Deliberately simple, concrete checks (Task
    requirement 7, "NON creare un confidence score complesso") — every
    unmet check is recorded as its own plain-language reason, both for the
    Validation Log message and for this task's replay report."""

    reasons: list[str] = []

    if not resolved_supplier_name or not invoice_parser.looks_like_plausible_name(resolved_supplier_name):
        reasons.append("supplier not reliably recognized")
    if document_header.get("issue_date") is None:
        reasons.append("issue date not recognized (missing, unparseable, or an implausible year)")
    # A $0.00 read is treated the same as "not recognized" -- almost never a
    # genuine invoice total, far more often a mis-extraction (e.g. a
    # trailing "0.00" balance/change line mistaken for the total). Better a
    # false HUMAN here than a false NORMALIZED on a fabricated-looking zero
    # (Task requirement 11, "Meglio HUMAN corretto che NORMALIZED sbagliato").
    if document_header.get("total_amount_minor") is None or document_header.get("total_amount_minor") == 0:
        reasons.append("total amount not recognized (missing or an implausible $0.00 read)")
    if invoice_parser.has_conflicting_totals(raw_text):
        reasons.append("multiple conflicting total-like amounts found in the source text")

    arithmetic_ok = _check_arithmetic_coherence(repository_lines, document_header.get("total_amount_minor"))
    if arithmetic_ok is False:
        reasons.append("line amounts do not add up to the stated total")

    return FieldValidationResult(is_normalized=not reasons, reasons=reasons)


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


def save_purchase_document(
    header: dict, lines: list[dict], source_file: str, raw_text: str = "", batch_note: str | None = None
) -> int:
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
    `raw_text` is optional — the original OCR/extracted text, when the
    caller still has it (e.g. `mailbox_acquisition`'s direct pipeline call;
    `app.py`'s own manual-review form-post does not carry it across the
    redirect, so it is omitted there). Used only for the conflicting-totals
    check (`_validate_extracted_fields`) — never persisted, never required.
    `batch_note` (Task "Purchased Supplier Training Phase 2", multi-invoice
    splitting) is an optional free-text note appended to
    `source_provenance` — `save_purchase_documents_from_batch()` below uses
    it to record which invoice/page-range of a multi-invoice source file
    this one document came from (Task requirement 6: "page/range
    provenance"); a caller outside that function has no reason to pass it.
    """

    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    # Supplier + Format specialization (Task "Purchased Supplier+Format
    # Training — Phase 1"): a second, narrowly-scoped pass over the
    # generic parser's own header, applied only when the raw text carries a
    # real, verified Supplier+Format signature (see
    # `supplier_format_rules.py`'s module docstring for which ones and
    # why). Never touches `lines` — line-item extraction stays entirely the
    # generic parser's concern for this phase.
    header = supplier_format_rules.apply_supplier_specializations(raw_text, header)

    with session_factory() as session:
        restaurant_id = _get_or_create_default_restaurant(session)
        resolved_supplier_name = _resolve_supplier_name(session, restaurant_id, header.get("supplier_name") or "", source_file)
        supplier_name = resolved_supplier_name or "Unknown Supplier"
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
                (
                    f"InvoiceIntake upload; raw issue_date as read: {header.get('issue_date')!r}"
                    if header.get("issue_date") and _parse_date(header.get("issue_date")) is None
                    else "InvoiceIntake upload"
                )
                + (f"; {batch_note}" if batch_note else "")
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
        # Field completeness/coherence only -- acquisition method (OCR vs.
        # digital text) is never a factor (Task requirement 6, "OCR ≠ HUMAN
        # automatico"; see _validate_extracted_fields()'s own docstring).
        validation = _validate_extracted_fields(resolved_supplier_name, document_header, repository_lines, raw_text)
        if not validation.is_normalized:
            repo.add_validation_log_entry(
                session,
                purchase_document_id=document.id,
                severity="WARNING",
                message="Not reliable enough to trust automatically: " + "; ".join(validation.reasons) + ".",
                suggested_action="Verify the listed field(s) against the original document.",
            )

        # --- Supplier + Source Format training foundation (observation only) ---
        # Never reads its own history back to influence this document's
        # result -- see supplier_format_training.py's module docstring.
        try:
            training_store = supplier_format_training.SupplierFormatTrainingStore()
            try:
                signature = supplier_format_training.layout_signature(
                    supplier_found=bool(resolved_supplier_name),
                    date_found=document_header.get("issue_date") is not None,
                    number_found=bool(document_header.get("document_number")),
                    total_found=document_header.get("total_amount_minor") is not None,
                    line_count=len(repository_lines),
                )
                # Method (OCR/PDF-Text) + CHANNEL (Direct/Instacart) together
                # form the training unit's own "source_format" (Task
                # requirement 9): the same Supplier arriving through a
                # marketplace/delivery channel is never merged with its
                # direct-acquisition format just because the Supplier
                # identity is the same.
                channel = supplier_format_rules.detect_channel(raw_text, source_file)
                acquisition_method = header.get("acquisition_method") or "UNKNOWN"
                training_store.record_observation(
                    supplier_name=supplier.name,
                    source_format=f"{acquisition_method}/{channel}",
                    was_normalized=validation.is_normalized,
                    signature=signature,
                )
            finally:
                training_store.close()
        except Exception:  # noqa: BLE001 — a foundation/observation side effect must never block the canonical save
            pass

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


def save_purchase_documents_from_batch(pages: list[str], source_file: str, acquisition_method: str) -> list[int]:
    """"Purchased Supplier Training — Phase 2": one physical PDF can carry
    more than one real invoice (`invoice_splitter.py`'s own docstring has
    the real evidence/cases). This is the ONE call site
    `mailbox_acquisition`'s automated pipeline uses instead of building a
    header/lines pair once and calling `save_purchase_document()` directly
    — everything else about persistence, dedup, NORMALIZED/HUMAN
    validation and Supplier+Format training stays entirely inside that
    unchanged function, called once per real invoice found.

    `pages` is the source file's own per-page text
    (`ocr_engine.extract_pages_from_pdf`). When `invoice_splitter.split_into_invoices()`
    decides NOT to split (see its own "Uncertainty rule" — anywhere from
    "only one page" to "genuinely ambiguous"), this behaves exactly like
    Phase 1's single-call path: one `PurchaseDocument`, `source_reference`
    equal to `source_file` unchanged.

    When it DOES split, each resulting invoice is saved as its own
    document, with its own `source_reference` encoding which page range of
    the original file it came from (Task requirement 6: "page/range
    provenance") — `source_file` itself is never lost, only ever
    *extended* (e.g. `"batch.pdf#p2-3"`), so the original file is always
    recoverable by prefix. Returns every resulting PurchaseDocumentId, in
    page order — the caller decides what "the" id for this attachment
    means to it (see `mailbox_acquisition/acquisition_service.py`, which
    treats the first one as primary for its own single-id bookkeeping,
    same discipline `test_replay_does_not_persist_anything` already
    established: no new write path, just this module's own existing save
    function called more than once)."""

    def _build_and_save(text: str, segment_source_file: str, batch_note: str | None) -> int:
        header = invoice_parser.parse_header(text)
        header["acquisition_method"] = acquisition_method
        lines = invoice_parser.parse_lines(text)
        for line in lines:
            line["line_type"] = guess_line_type(line.get("description", ""))
        return save_purchase_document(header, lines, segment_source_file, raw_text=text, batch_note=batch_note)

    segments = invoice_splitter.split_into_invoices(pages)
    if segments is None:
        combined_text = "\n".join(pages).strip()
        return [_build_and_save(combined_text, source_file, batch_note=None)]

    document_ids = []
    for segment in segments:
        segment_source_file = f"{source_file}#{segment.page_range_label}"
        batch_note = (
            f"multi-invoice batch: invoice {segment.segment_index} of {segment.segment_count}, "
            f"page {segment.page_range_label} of {segment.total_pages} (source file: {source_file!r})"
        )
        document_ids.append(_build_and_save(segment.text, segment_source_file, batch_note))
    return document_ids


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


def get_saved_document_supplier_name(purchase_document_id: int) -> str | None:
    """The resolved Supplier name for an already-saved document, or `None`
    if the document no longer exists — a thin read-only helper for admin
    views (e.g. `mailbox/` acquisition's own view) that display which
    Supplier a delivered document was recognized as, without exposing the
    Purchasing repository/session machinery directly."""

    url = get_database_url()
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        document = session.get(m.PurchaseDocument, purchase_document_id)
        if document is None:
            return None
        supplier = session.get(m.Supplier, document.supplier_id)
        return supplier.name if supplier is not None else None
