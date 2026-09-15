"""Purchased Human Review orchestration ("Purchased Human Review + Supplier
Format Training UI").

Implements the flow Purchased/README.md's own NORMALIZED/HUMAN diagram
already describes but never implemented until now:

    HUMAN -> review -> correction/confirmation -> NORMALIZED -> training observation

This module is Purchased's own concern (not Purchasing, not Accounting,
and not the separate cash/payment-matching domain out of this task's
scope) — it never calls a Restaurant/Purchasing decision/receiving
function, same discipline `purchased_bridge.py` already follows (see
`test_purchased_bridge.py`'s static AST check, now extended to cover this
file too).

**Never mutates `PurchaseDocument`/`PurchaseLine`** — both are "Immutable
by convention" (models.py, Rule 2/Rule 11: "the repository never updates a
row here" beyond `PurchaseDocument.status`). A human correction is
recorded as its own additive `PurchasedFieldCorrection` row
(`purchasing/repository.py`); `effective_document_view()` below is what
merges the latest correction per field on top of the original, immutable
columns for display and for re-validation. Nothing about the original
extraction is ever lost (Task requirement 5/17: "La source evidence resta
immutabile" / "NON cancellare la lettura originale").

Re-validation reuses `purchased_bridge._validate_extracted_fields()` —
the EXACT SAME function used at initial save — rather than a second,
parallel correctness check (Task: "NON aggiungere nuove euristiche
parser"). When the effective (corrected) values now pass it, every OPEN
WARNING/ERROR `PurchasingValidationLogEntry` referencing the document (or
a line) is closed, and `get_document_functional_status()` naturally
returns NORMALIZED again — no third functional state is introduced.

Every completed review also writes one observation to
`supplier_format_training.py` (Task requirement 8) — the same store
Phase 1/2 already built and the same API (`record_observation`,
`record_field_review`), so "Human Review" and "Supplier Format Training"
are the same act, not two.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from sqlalchemy import select  # noqa: E402

from rfone_data_store.database import (  # noqa: E402
    create_configured_engine,
    create_session_factory,
    get_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.purchasing import repository as repo  # noqa: E402

import purchased_bridge  # noqa: E402
import supplier_format_rules  # noqa: E402
import supplier_format_training as sft  # noqa: E402
from mailbox_acquisition.acquisition_store import AcquisitionStore  # noqa: E402
from mailbox_acquisition.acquisition_service import DEFAULT_DB_PATH as MAILBOX_DB_PATH  # noqa: E402

UTC = timezone.utc

HEADER_FIELDS = ("supplier", "document_number", "issue_date", "total_amount")
LINE_FIELDS = ("description", "normalized_item", "quantity", "unit_of_measure", "unit_price", "line_amount")
ALL_FIELDS = HEADER_FIELDS + LINE_FIELDS


def _session_factory():
    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    return create_session_factory(engine)


def _money_str(minor: int | None) -> str | None:
    return f"{minor / 100:.2f}" if minor is not None else None


def _date_str(value: datetime | None) -> str | None:
    return value.strftime("%m/%d/%Y") if value else None


def _latest_corrections(corrections: list) -> dict[tuple[int | None, str], "m.PurchasedFieldCorrection"]:
    """Latest correction per (purchase_line_id, field_name) — `corrections`
    must already be ordered oldest-first (`repo.list_field_corrections()`'s
    own contract), so a later dict write always wins."""

    latest: dict[tuple[int | None, str], "m.PurchasedFieldCorrection"] = {}
    for correction in corrections:
        latest[(correction.purchase_line_id, correction.field_name)] = correction
    return latest


def _effective_value(latest: dict, line_id: int | None, field_name: str, original: str | None) -> str | None:
    correction = latest.get((line_id, field_name))
    if correction is not None and correction.classification != "CORRECT" and correction.corrected_value is not None:
        return correction.corrected_value
    return original


def _lookup_mailbox_provenance(source_reference: str | None) -> dict | None:
    """Task requirement 4A: "email/message provenance dove disponibile" —
    a best-effort cross-reference into `mailbox_acquisition`'s own local
    store (a separate SQLite file, no foreign key — matched by filename
    only) since this document may have arrived by email. Returns `None`
    when nothing matches (e.g. a manually-uploaded document) rather than
    guessing."""

    if not source_reference:
        return None
    file_prefix = source_reference.split("#", 1)[0]
    store = AcquisitionStore(MAILBOX_DB_PATH)
    try:
        for record in store.list_recent(limit=500):
            if record.stored_path and os.path.basename(record.stored_path) == file_prefix:
                return {"sender": record.sender, "subject": record.subject, "received_at": record.received_at}
    finally:
        store.close()
    return None


def effective_document_view(session, purchase_document_id: int) -> dict | None:
    """The one function everything else in this module (and the review
    templates) builds on: original extracted values, the latest human
    correction per field (if any), and the resulting EFFECTIVE value —
    never a mutation, always a merge computed on read (Task requirement 5)."""

    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        return None
    supplier = session.get(m.Supplier, document.supplier_id)
    corrections = repo.list_field_corrections(session, purchase_document_id)
    latest = _latest_corrections(corrections)

    header_original = {
        "supplier": supplier.name if supplier else None,
        "document_number": document.document_number,
        "issue_date": _date_str(document.issue_date),
        "total_amount": _money_str(document.total_amount_minor),
    }
    header_effective = {field: _effective_value(latest, None, field, value) for field, value in header_original.items()}

    allocation_by_line_id = {row["purchase_line_id"]: row for row in repo.get_purchased_lines_with_allocation(session, document.id)}

    lines_view = []
    for line in sorted(document.lines, key=lambda entry: entry.id):
        original = {
            "description": line.raw_description,
            "normalized_item": None,
            "quantity": str(line.quantity) if line.quantity is not None else None,
            "unit_of_measure": line.purchase_unit,
            "unit_price": _money_str(line.unit_price_minor),
            "line_amount": _money_str(line.source_amount_minor),
        }
        effective = {field: _effective_value(latest, line.id, field, value) for field, value in original.items()}
        lines_view.append(
            {
                "id": line.id,
                "line_type": line.line_type,
                "original": original,
                "effective": effective,
                "allocation": allocation_by_line_id.get(line.id),
                "functional_status": repo.get_line_functional_status(session, line.id),
            }
        )

    open_entries = list(
        session.scalars(
            select(m.PurchasingValidationLogEntry).where(
                m.PurchasingValidationLogEntry.purchase_document_id == document.id,
                m.PurchasingValidationLogEntry.status == "OPEN",
            )
        ).all()
    )

    aliases = repo.list_supplier_aliases(session, document.supplier_id) if supplier else []
    mailbox_provenance = _lookup_mailbox_provenance(document.source_reference)
    source_reference = document.source_reference or ""
    source_filename, _, page_range = source_reference.partition("#")

    return {
        "document": document,
        "supplier": supplier,
        "aliases": aliases,
        "mailbox_provenance": mailbox_provenance,
        "source_filename": source_filename or None,
        "page_range": page_range or None,
        "header_original": header_original,
        "header_effective": header_effective,
        "lines": lines_view,
        "corrections": corrections,
        "open_validation_entries": open_entries,
        "functional_status": repo.get_document_functional_status(session, document.id),
        "siblings": repo.list_sibling_documents(session, document.id),
    }


def get_review_queue(restaurant_id: int | None = None) -> list[dict]:
    """Task requirement 2: every PurchaseDocument in HUMAN, most recent
    first, grouped by Supplier with a pending count (Task: "Ordina
    prioritariamente per: più recenti; supplier; eventuale numero di
    documenti pendenti")."""

    session_factory = _session_factory()
    with session_factory() as session:
        rid = restaurant_id if restaurant_id is not None else purchased_bridge._get_or_create_default_restaurant(session)
        documents = repo.list_human_review_queue(session, rid)
        rows = []
        for document in documents:
            supplier = session.get(m.Supplier, document.supplier_id)
            rows.append(
                {
                    "id": document.id,
                    "supplier_name": supplier.name if supplier else "Unknown Supplier",
                    "document_number": document.document_number,
                    "issue_date": _date_str(document.issue_date),
                    "total_amount": _money_str(document.total_amount_minor),
                    "created_at": document.created_at,
                    "source_reference": document.source_reference,
                    "is_multi_invoice": bool(document.source_reference and "#" in (document.source_reference or "")),
                }
            )
        pending_by_supplier: dict[str, int] = {}
        for row in rows:
            pending_by_supplier[row["supplier_name"]] = pending_by_supplier.get(row["supplier_name"], 0) + 1
        for row in rows:
            row["pending_for_supplier"] = pending_by_supplier[row["supplier_name"]]
        return rows


def get_review_detail(purchase_document_id: int) -> dict | None:
    session_factory = _session_factory()
    with session_factory() as session:
        return effective_document_view(session, purchase_document_id)


def submit_field_review(
    purchase_document_id: int,
    *,
    field_name: str,
    classification: str,
    reviewed_by: str,
    purchase_line_id: int | None = None,
    corrected_value: str | None = None,
) -> None:
    """Task requirement 6: one field, one review outcome — a confirmation
    (CORRECT, no corrected_value needed) or a correction (INCORRECT/UNREAD/
    AMBIGUOUS with a corrected_value). Always additive (see module
    docstring) — the CURRENT original value is captured automatically as
    `original_value`, from whichever is currently effective (so correcting
    the same field twice still preserves the full chain)."""

    if field_name not in ALL_FIELDS:
        raise ValueError(f"Unknown field_name {field_name!r}; must be one of {ALL_FIELDS}")
    session_factory = _session_factory()
    with session_factory() as session:
        view = effective_document_view(session, purchase_document_id)
        if view is None:
            raise ValueError(f"No PurchaseDocument with id={purchase_document_id!r}")
        if field_name in HEADER_FIELDS:
            original_value = view["header_effective"][field_name]
        else:
            line_view = next((line for line in view["lines"] if line["id"] == purchase_line_id), None)
            if line_view is None:
                raise ValueError(f"No line id={purchase_line_id!r} on document {purchase_document_id!r}")
            original_value = line_view["effective"][field_name]

        repo.record_field_correction(
            session,
            purchase_document_id=purchase_document_id,
            purchase_line_id=purchase_line_id,
            field_name=field_name,
            classification=classification,
            reviewed_by=reviewed_by,
            original_value=original_value,
            corrected_value=corrected_value if classification != "CORRECT" else None,
        )
        session.commit()


def complete_review(purchase_document_id: int, *, reviewed_by: str) -> dict:
    """Task requirement 7/8: re-validates the EFFECTIVE (post-correction)
    values with the SAME validation function used at initial save; if they
    now pass, closes every OPEN issue so the document becomes NORMALIZED
    (never a third state — README/requirement 7). Always records one
    Supplier+Format training observation, whatever the outcome (Task
    requirement 8: "NON deve richiedere un secondo inserimento manuale")."""

    session_factory = _session_factory()
    with session_factory() as session:
        view = effective_document_view(session, purchase_document_id)
        if view is None:
            raise ValueError(f"No PurchaseDocument with id={purchase_document_id!r}")
        document = view["document"]

        document_header = {
            "issue_date": purchased_bridge._parse_date(view["header_effective"]["issue_date"]),
            "total_amount_minor": purchased_bridge._parse_money_minor(view["header_effective"]["total_amount"]),
        }
        repository_lines = [
            {"source_amount_minor": purchased_bridge._parse_money_minor(line["effective"]["line_amount"])}
            for line in view["lines"]
        ]
        # raw_text is not persisted on PurchaseDocument (only used transiently
        # at initial save) -- the conflicting-totals check is a no-op here,
        # same degradation already documented for training replay scripts.
        validation = purchased_bridge._validate_extracted_fields(
            view["header_effective"]["supplier"], document_header, repository_lines, ""
        )

        if validation.is_normalized:
            for entry in view["open_validation_entries"]:
                if entry.severity in ("WARNING", "ERROR"):
                    repo.close_validation_log_entry(
                        session, entry.id, human_decision=f"Resolved by Purchased Human Review (reviewer: {reviewed_by})"
                    )

        # Supplier alias capture (Task requirement 12): if the review
        # corrected the supplier to a name that differs from what the
        # document originally resolved to, resolve/create that canonical
        # Supplier (alias-aware -- never a needless duplicate) and record
        # the original text as one of its known aliases for future
        # recognition. Never rewrites PurchaseDocument.supplier_id itself
        # (immutable by convention -- see module docstring).
        corrected_supplier_name = view["header_effective"]["supplier"]
        original_supplier_name = view["header_original"]["supplier"]
        if (
            corrected_supplier_name
            and original_supplier_name
            and corrected_supplier_name != original_supplier_name
        ):
            restaurant_id = view["supplier"].restaurant_id if view["supplier"] else purchased_bridge._get_or_create_default_restaurant(session)
            canonical_supplier = repo.get_or_create_supplier(session, restaurant_id, corrected_supplier_name)
            known_alias_names = {alias.alias_name for alias in repo.list_supplier_aliases(session, canonical_supplier.id)}
            if original_supplier_name not in known_alias_names and original_supplier_name != canonical_supplier.name:
                repo.add_supplier_alias(
                    session, canonical_supplier.id, original_supplier_name, source="Human Review correction"
                )

        session.commit()

        new_status = repo.get_document_functional_status(session, purchase_document_id)

        # -- Supplier+Format training observation (Task requirement 8) ------
        signature = sft.layout_signature(
            supplier_found=bool(view["header_effective"]["supplier"]),
            date_found=document_header["issue_date"] is not None,
            number_found=bool(view["header_effective"]["document_number"]),
            total_found=document_header["total_amount_minor"] is not None,
            line_count=len(repository_lines),
        )
        channel = supplier_format_rules.detect_channel("", document.source_reference)
        source_format = f"{document.acquisition_method or 'UNKNOWN'}/{channel}"
        training_store = sft.SupplierFormatTrainingStore()
        try:
            training_store.record_observation(
                supplier_name=corrected_supplier_name or original_supplier_name or "Unknown Supplier",
                source_format=source_format,
                was_normalized=(new_status == "NORMALIZED"),
                signature=signature,
            )
            for field_name in HEADER_FIELDS:
                correction = _latest_corrections(view["corrections"]).get((None, field_name))
                if correction is not None:
                    training_store.record_field_review(
                        supplier_name=corrected_supplier_name or original_supplier_name or "Unknown Supplier",
                        source_format=source_format,
                        document_reference=document.source_reference or str(document.id),
                        field_name=field_name,
                        classification=correction.classification,
                        extracted_value=correction.original_value,
                        expected_value=correction.corrected_value,
                    )
        finally:
            training_store.close()

        return {"functional_status": new_status, "reasons": validation.reasons}


def list_supplier_training_status() -> list[dict]:
    """Task requirement 9/10/11: every observed Supplier+Format pair, its
    trust_state, and whether it is eligible for promotion right now (never
    promoted automatically — see `validate_supplier_format()` below)."""

    training_store = sft.SupplierFormatTrainingStore()
    try:
        rows = []
        for observation in training_store.list_all():
            eligible, reason = training_store.is_eligible_for_validation(observation.supplier_name, observation.source_format)
            rows.append(
                {
                    "supplier_name": observation.supplier_name,
                    "source_format": observation.source_format,
                    "reviewed_count": observation.reviewed_count,
                    "normalized_count": observation.normalized_count,
                    "human_count": observation.human_count,
                    "consecutive_correct_count": observation.consecutive_correct_count,
                    "trust_state": observation.trust_state,
                    "threshold": training_store.get_trust_threshold(observation.supplier_name, observation.source_format),
                    "eligible": eligible,
                    "eligibility_reason": reason,
                }
            )
        return rows
    finally:
        training_store.close()


def validate_supplier_format(supplier_name: str, source_format: str) -> dict:
    """Task requirement 10: the ONE way a (Supplier, Format) pair actually
    becomes VALIDATED — always server-side re-checked against
    `is_eligible_for_validation()` (`supplier_format_training.promote_if_eligible()`
    itself raises if not eligible; this never bypasses that service logic,
    Task: "NON bypassare la service logic")."""

    training_store = sft.SupplierFormatTrainingStore()
    try:
        observation = training_store.promote_if_eligible(supplier_name, source_format)
        return {"trust_state": observation.trust_state}
    finally:
        training_store.close()
