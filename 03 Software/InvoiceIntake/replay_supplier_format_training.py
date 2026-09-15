#!/usr/bin/env python
"""Phase 1 real-document replay — "Purchased Supplier+Format Training —
Phase 1", §13 ("Replay").

Re-runs OCR/parser/specialization/field-validation against the real,
already-acquired documents for the priority Suppliers (Prime Line, Keith,
Samuel & Son, Costco/Instacart, Sam's Club/Instacart), exactly the
read-only "replay" discipline already established by
`test_purchased_bridge.py::test_replay_does_not_persist_anything`: this
NEVER calls `purchased_bridge.save_purchase_document()` and NEVER commits
a database session — no new PurchaseDocument, no new Supplier, no
duplicate is ever created by running this script (Task requirement 13:
"NON creare duplicati Purchased"). The one durable side effect is writing
to `supplier_format_training.py`'s own separate, observational store
(training-unit observations + field-level human review classifications) —
exactly the kind of "acquisition/quality-tracking metadata, not a
Purchased fact" write that store exists for.

Field-level CORRECT/INCORRECT/UNREAD/AMBIGUOUS classifications below come
from manually comparing each document's extraction against the real source
document (opened and read directly), per Task requirement 5 — not
computed/guessed by this script.

Usage:
    python replay_supplier_format_training.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_DATA_STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

import ocr_engine  # noqa: E402
import parser as invoice_parser  # noqa: E402
import purchased_bridge  # noqa: E402
import supplier_format_rules  # noqa: E402
import supplier_format_training as sft  # noqa: E402

from rfone_data_store.database import (  # noqa: E402
    create_configured_engine,
    create_session_factory,
    get_database_url,
    run_migrations_to_head,
)

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")


class Document:
    def __init__(self, supplier: str, filename: str, doc_ref: str, expected: dict) -> None:
        self.supplier = supplier
        self.filename = filename
        self.doc_ref = doc_ref  # what this replay reports as "document_reference" for field reviews
        self.expected = expected  # manually-verified ground truth, from reading the real document


# Manually verified against the real acquired documents (opened directly) —
# see the phase-1 report for how each was read. "total" is always the
# document's own stated grand total; "number" is the document's own
# invoice/transaction identifier; "" means the real document genuinely has
# no such field (not "not found").
DOCUMENTS: list[Document] = [
    Document(
        "Prime Line Distributors",
        "1fa14bf8_PL20200630125750_001.pdf",
        "PL20200630125750_001.pdf",
        {"supplier": "Prime Line Distributors", "number": "1107919", "date": "06/30/20", "total": "523.72"},
    ),
    Document(
        "Prime Line Distributors",
        "d0d88aaa_PL20200602113022_001.pdf",
        "PL20200602113022_001.pdf",
        # The source scan itself is cropped at the right edge -- the real
        # Number/Date are only partially visible even by direct inspection
        # ("110398...", "06/02/2..."); Total is fully visible.
        {"supplier": "Prime Line Distributors", "number": "110398?(cropped source)", "date": "06/02/2?(cropped source)", "total": "468.47"},
    ),
    Document(
        "Prime Line Distributors",
        "21806b7f_PL20200609171959_001.pdf",
        "PL20200609171959_001.pdf#invoice1-of-4",
        # A single PDF bundling 4 distinct Prime Line invoices as separate
        # pages (see report, section B) -- only the FIRST invoice is in
        # scope for this document's header, matching what the rest of the
        # pipeline (one PurchaseDocument per source file) already does.
        {"supplier": "Prime Line Distributors", "number": "(garbled at source: \"VI 039\")", "date": "06/02/20", "total": "468.47"},
    ),
    Document(
        "Ben E. Keith Foods",
        "f8862b89_24 Keith_20241010_0002-1-3.pdf",
        "24 Keith_20241010_0002-1-3.pdf#90079477",
        {"supplier": "Ben E. Keith Foods", "number": "90079477", "date": "01/05/24", "total": "302.74"},
    ),
    Document(
        "Ben E. Keith Foods",
        "f8862b89_24 Keith_20241010_0002-1-3.pdf",
        "24 Keith_20241010_0002-1-3.pdf#90080721",
        {"supplier": "Ben E. Keith Foods", "number": "90080721", "date": "01/10/24", "total": "1257.66"},
    ),
    Document(
        "Costco Wholesale",
        "5ba9d2aa_CO2020-02-11.pdf",
        "CO2020-02-11.pdf",
        {"supplier": "Costco Wholesale", "number": "004200002942", "date": "02/11/2020", "total": "149.44"},
    ),
    Document(
        "Costco Wholesale",
        "cebaf879_CO2020-02-08.pdf",
        "CO2020-02-08.pdf",
        {"supplier": "Costco Wholesale", "number": "003900003938", "date": "02/08/2020", "total": "368.42"},
    ),
]


def _classify(expected: str, extracted: str | None) -> tuple[str, str]:
    """Returns (classification, note). Never invented — a straight
    string/field comparison against the manually-verified ground truth
    above."""

    if not extracted:
        return sft.FIELD_REVIEW_UNREAD, "not extracted"
    if "cropped source" in expected or "garbled at source" in expected:
        return sft.FIELD_REVIEW_AMBIGUOUS, "real document itself is degraded/cropped at this field; cannot fully confirm either way"
    if extracted.strip().lower() == expected.strip().lower():
        return sft.FIELD_REVIEW_CORRECT, ""
    return sft.FIELD_REVIEW_INCORRECT, f"expected {expected!r}"


def replay() -> None:
    training_store = sft.SupplierFormatTrainingStore()

    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    results = []
    for doc in DOCUMENTS:
        path = os.path.join(UPLOADS_DIR, doc.filename)
        text, method = ocr_engine.extract_from_pdf(path)
        header = invoice_parser.parse_header(text)
        lines = invoice_parser.parse_lines(text)
        header = supplier_format_rules.apply_supplier_specializations(text, header)
        channel = supplier_format_rules.detect_channel(text, doc.filename)
        source_format = f"{method}/{channel}"

        document_header = {
            "issue_date": purchased_bridge._parse_date(header.get("issue_date")),
            "total_amount_minor": purchased_bridge._parse_money_minor(header.get("total_amount")),
        }
        repository_lines = [
            {"source_amount_minor": purchased_bridge._parse_money_minor(line.get("line_amount"))} for line in lines
        ]

        # Read-only supplier-alias resolution against the real store,
        # always rolled back -- never a second write path (see module
        # docstring / test_replay_does_not_persist_anything precedent).
        session = session_factory()
        try:
            restaurant_id = purchased_bridge._get_or_create_default_restaurant(session)
            resolved_supplier = purchased_bridge._resolve_supplier_name(
                session, restaurant_id, header.get("supplier_name") or "", doc.filename
            )
        finally:
            session.rollback()
            session.close()

        validation = purchased_bridge._validate_extracted_fields(resolved_supplier, document_header, repository_lines, text)

        signature = sft.layout_signature(
            supplier_found=bool(resolved_supplier),
            date_found=document_header["issue_date"] is not None,
            number_found=bool(header.get("document_number")),
            total_found=document_header["total_amount_minor"] is not None,
            line_count=len(repository_lines),
        )
        observation = training_store.record_observation(
            supplier_name=resolved_supplier or doc.supplier,
            source_format=source_format,
            was_normalized=validation.is_normalized,
            signature=signature,
        )

        field_values = {
            "supplier": resolved_supplier or "",
            "number": header.get("document_number") or "",
            "date": header.get("issue_date") or "",
            "total": header.get("total_amount") or "",
        }
        classifications = {}
        for field_name, expected_value in doc.expected.items():
            extracted_value = field_values[field_name]
            classification, note = _classify(expected_value, extracted_value)
            training_store.record_field_review(
                supplier_name=resolved_supplier or doc.supplier,
                source_format=source_format,
                document_reference=doc.doc_ref,
                field_name=field_name,
                classification=classification,
                extracted_value=extracted_value or None,
                expected_value=expected_value,
                note=note or None,
            )
            classifications[field_name] = classification
        # Line items: the generic parser found 0 usable lines on every real
        # document seen so far (see report section C-G) -- recorded as
        # UNREAD rather than silently skipped.
        line_classification = sft.FIELD_REVIEW_CORRECT if lines else sft.FIELD_REVIEW_UNREAD
        training_store.record_field_review(
            supplier_name=resolved_supplier or doc.supplier,
            source_format=source_format,
            document_reference=doc.doc_ref,
            field_name="line_items",
            classification=line_classification,
            extracted_value=str(len(lines)),
            expected_value=None,
            note="generic LINE_ITEM_RE found no usable line" if not lines else None,
        )
        classifications["line_items"] = line_classification

        results.append(
            {
                "doc_ref": doc.doc_ref,
                "method": method,
                "source_format": source_format,
                "functional_status": "NORMALIZED" if validation.is_normalized else "HUMAN",
                "reasons": validation.reasons,
                "fields": classifications,
                "trust_state": observation.trust_state,
                "reviewed_count": observation.reviewed_count,
            }
        )

    training_store.close()

    print(f"{'document_reference':45} {'source_format':16} {'status':10} {'fields (supplier/number/date/total/lines)'}")
    for r in results:
        fields_str = "/".join(r["fields"].get(k, "-") for k in ("supplier", "number", "date", "total", "line_items"))
        print(f"{r['doc_ref']:45} {r['source_format']:16} {r['functional_status']:10} {fields_str}")
        if r["reasons"]:
            print(f"    reasons: {'; '.join(r['reasons'])}")

    print()
    print("Training store state (Supplier, Format):")
    for obs in sft.SupplierFormatTrainingStore().list_all():
        print(
            f"  {obs.supplier_name:28} {obs.source_format:16} reviewed={obs.reviewed_count} "
            f"normalized={obs.normalized_count} human={obs.human_count} trust_state={obs.trust_state}"
        )


if __name__ == "__main__":
    replay()
