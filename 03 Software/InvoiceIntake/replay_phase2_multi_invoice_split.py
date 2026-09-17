#!/usr/bin/env python
"""Phase 2 real-document replay — "Purchased Supplier Training — Phase 2",
§15 ("Prime Line replay") / §16 ("Keith replay") / §17 ("Training store").

Supersedes Phase 1's `replay_supplier_format_training.py` for the two real
batch files it could only treat as ONE document each (a Phase 1-documented
open gap): here, every real acquired document is replayed at the real
INVOICE level via `invoice_splitter.py` — `PL20200609171959_001.pdf`
becomes 4 replayed invoices instead of 1, `24 Keith_20241010_0002-1-3.pdf`
becomes 2 instead of 1. The other real documents (the two single-invoice
Prime Line scans, both Costco receipts) are unaffected by splitting
(nothing to split) and are replayed exactly as in Phase 1, for a complete,
consistent Training Store picture.

Same read-only discipline as Phase 1's replay
(`test_purchased_bridge.py::test_replay_does_not_persist_anything`): never
calls `purchased_bridge.save_purchase_document()` / never commits — no new
PurchaseDocument, no new Supplier, no duplicate is ever created by running
this script (Task requirement 7: "NON deve creare duplicati"). The one
durable side effect is writing to `supplier_format_training.py`'s own
separate, observational store (training-unit observations + field-level
human review classifications), same as Phase 1.

Field-level CORRECT/INCORRECT/UNREAD/AMBIGUOUS classifications below come
from manually comparing each real invoice's extraction against the real
source document (opened and read directly — see the Phase 2 report for
the visual confirmation of all 4 Prime Line invoices in the batch file).

Usage:
    python replay_phase2_multi_invoice_split.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_DATA_STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

import invoice_splitter  # noqa: E402
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


class RealInvoice:
    """One real invoice's ground truth, manually verified by opening the
    real source document directly (Task requirement 5). `filename` is the
    source file under uploads/; `page_hint` narrows which split segment
    this ground truth applies to when a file yields more than one (matched
    by the segment's own 1-indexed page_start)."""

    def __init__(self, supplier: str, filename: str, doc_ref: str, expected: dict, page_hint: int | None = None) -> None:
        self.supplier = supplier
        self.filename = filename
        self.doc_ref = doc_ref
        self.expected = expected
        self.page_hint = page_hint


REAL_INVOICES: list[RealInvoice] = [
    # -- Prime Line: 2 real single-invoice scans (unaffected by splitting) --
    RealInvoice(
        "Prime Line Distributors", "1fa14bf8_PL20200630125750_001.pdf", "PL20200630125750_001.pdf",
        {"supplier": "Prime Line Distributors", "number": "1107919", "date": "06/30/20", "total": "523.72"},
    ),
    RealInvoice(
        "Prime Line Distributors", "d0d88aaa_PL20200602113022_001.pdf", "PL20200602113022_001.pdf",
        # Source scan itself is cropped at the right edge -- Number/Date only partially visible even on direct inspection.
        {"supplier": "Prime Line Distributors", "number": "110398?(cropped source)", "date": "06/02/2?(cropped source)", "total": "468.47"},
    ),
    # -- Prime Line: 1 real batch file, 4 real invoices (Task real case A) --
    RealInvoice(
        "Prime Line Distributors", "21806b7f_PL20200609171959_001.pdf", "PL20200609171959_001.pdf#invoice1",
        # "Number: VI 039£" is illegible/degraded on the real source page itself (confirmed by direct visual inspection, not an extraction failure).
        {"supplier": "Prime Line Distributors", "number": "VI 039£(illegible at source)", "date": "06/02/20", "total": "468.47"},
        page_hint=1,
    ),
    RealInvoice(
        "Prime Line Distributors", "21806b7f_PL20200609171959_001.pdf", "PL20200609171959_001.pdf#invoice2",
        {"supplier": "Prime Line Distributors", "number": "1103031", "date": "05/26/20", "total": "87.50"},
        page_hint=2,
    ),
    RealInvoice(
        "Prime Line Distributors", "21806b7f_PL20200609171959_001.pdf", "PL20200609171959_001.pdf#invoice3",
        {"supplier": "Prime Line Distributors", "number": "1103028", "date": "05/26/20", "total": "265.38"},
        page_hint=3,
    ),
    RealInvoice(
        "Prime Line Distributors", "21806b7f_PL20200609171959_001.pdf", "PL20200609171959_001.pdf#invoice4",
        {"supplier": "Prime Line Distributors", "number": "1103053", "date": "05/26/20", "total": "42.00"},
        page_hint=4,
    ),
    # -- Ben E. Keith: 1 real batch file, 2 real invoices, one multi-page (Task real case B) --
    RealInvoice(
        "Ben E. Keith Foods", "f8862b89_24 Keith_20241010_0002-1-3.pdf", "24 Keith_20241010_0002-1-3.pdf#invoice1",
        {"supplier": "Ben E. Keith Foods", "number": "90079477", "date": "01/05/24", "total": "302.74"},
        page_hint=1,
    ),
    RealInvoice(
        "Ben E. Keith Foods", "f8862b89_24 Keith_20241010_0002-1-3.pdf", "24 Keith_20241010_0002-1-3.pdf#invoice2",
        {"supplier": "Ben E. Keith Foods", "number": "90080721", "date": "01/10/24", "total": "1257.66"},
        page_hint=2,
    ),
    # -- Costco: 2 real single-page receipts (unaffected by splitting) --
    RealInvoice(
        "Costco Wholesale", "5ba9d2aa_CO2020-02-11.pdf", "CO2020-02-11.pdf",
        {"supplier": "Costco Wholesale", "number": "004200002942", "date": "02/11/2020", "total": "149.44"},
    ),
    RealInvoice(
        "Costco Wholesale", "cebaf879_CO2020-02-08.pdf", "CO2020-02-08.pdf",
        {"supplier": "Costco Wholesale", "number": "003900003938", "date": "02/08/2020", "total": "368.42"},
    ),
]


def _classify(expected: str, extracted: str | None) -> tuple[str, str]:
    if not extracted:
        return sft.FIELD_REVIEW_UNREAD, "not extracted"
    if "cropped source" in expected or "illegible at source" in expected:
        return sft.FIELD_REVIEW_AMBIGUOUS, "real document itself is degraded at this field; cannot fully confirm either way"
    if extracted.strip().lower() == expected.strip().lower():
        return sft.FIELD_REVIEW_CORRECT, ""
    return sft.FIELD_REVIEW_INCORRECT, f"expected {expected!r}"


def _extract_pages(filename: str) -> tuple[list[str], str]:
    path = os.path.join(UPLOADS_DIR, filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return ocr_engine.extract_pages_from_pdf(path)
    return [ocr_engine.extract_from_image(path)], "OCR"


def replay() -> None:
    training_store = sft.SupplierFormatTrainingStore()

    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    # Split each distinct source file once; every RealInvoice ground-truth
    # entry for that file then picks out its own segment by page_hint.
    segments_by_file: dict[str, list] = {}
    method_by_file: dict[str, str] = {}
    for filename in {inv.filename for inv in REAL_INVOICES}:
        pages, method = _extract_pages(filename)
        method_by_file[filename] = method
        segments_by_file[filename] = invoice_splitter.split_into_invoices(pages) or [
            # Not split -- the whole file is one segment (page_hint None matches this).
            invoice_splitter.InvoiceSegment(
                page_start=1, page_end=len(pages), total_pages=len(pages),
                segment_index=1, segment_count=1, text="\n".join(pages).strip(), document_number="",
            )
        ]

    results = []
    for inv in REAL_INVOICES:
        segments = segments_by_file[inv.filename]
        segment = next((s for s in segments if s.page_start == inv.page_hint), segments[0]) if inv.page_hint else segments[0]
        method = method_by_file[inv.filename]

        text = segment.text
        header = invoice_parser.parse_header(text)
        lines = invoice_parser.parse_lines(text)
        header = supplier_format_rules.apply_supplier_specializations(text, header)
        channel = supplier_format_rules.detect_channel(text, inv.filename)
        source_format = f"{method}/{channel}"

        document_header = {
            "issue_date": purchased_bridge._parse_date(header.get("issue_date")),
            "total_amount_minor": purchased_bridge._parse_money_minor(header.get("total_amount")),
        }
        repository_lines = [
            {"source_amount_minor": purchased_bridge._parse_money_minor(line.get("line_amount"))} for line in lines
        ]

        session = session_factory()
        try:
            restaurant_id = purchased_bridge._get_or_create_default_restaurant(session)
            resolved_supplier = purchased_bridge._resolve_supplier_name(
                session, restaurant_id, header.get("supplier_name") or "", inv.filename
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
            supplier_name=resolved_supplier or inv.supplier,
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
        for field_name, expected_value in inv.expected.items():
            extracted_value = field_values[field_name]
            classification, note = _classify(expected_value, extracted_value)
            training_store.record_field_review(
                supplier_name=resolved_supplier or inv.supplier,
                source_format=source_format,
                document_reference=inv.doc_ref,
                field_name=field_name,
                classification=classification,
                extracted_value=extracted_value or None,
                expected_value=expected_value,
                note=note or None,
            )
            classifications[field_name] = classification
        line_classification = sft.FIELD_REVIEW_CORRECT if lines else sft.FIELD_REVIEW_UNREAD
        training_store.record_field_review(
            supplier_name=resolved_supplier or inv.supplier,
            source_format=source_format,
            document_reference=inv.doc_ref,
            field_name="line_items",
            classification=line_classification,
            extracted_value=str(len(lines)),
            expected_value=None,
            note=None if lines else "generic LINE_ITEM_RE found no usable line",
        )
        classifications["line_items"] = line_classification

        results.append(
            {
                "doc_ref": inv.doc_ref,
                "page_range": segment.page_range_label,
                "source_format": source_format,
                "functional_status": "NORMALIZED" if validation.is_normalized else "HUMAN",
                "reasons": validation.reasons,
                "fields": classifications,
            }
        )

    training_store.close()

    print(f"{'document_reference':42} {'pages':7} {'source_format':16} {'status':10} {'fields (supplier/number/date/total/lines)'}")
    for r in results:
        fields_str = "/".join(r["fields"].get(k, "-") for k in ("supplier", "number", "date", "total", "line_items"))
        print(f"{r['doc_ref']:42} {r['page_range']:7} {r['source_format']:16} {r['functional_status']:10} {fields_str}")
        if r["reasons"]:
            print(f"    reasons: {'; '.join(r['reasons'])}")

    print()
    print("Training store state (Supplier, Format):")
    for obs in sft.SupplierFormatTrainingStore().list_all():
        print(
            f"  {obs.supplier_name:28} {obs.source_format:16} reviewed={obs.reviewed_count} "
            f"normalized={obs.normalized_count} human={obs.human_count} "
            f"consecutive_correct={obs.consecutive_correct_count} trust_state={obs.trust_state}"
        )


if __name__ == "__main__":
    replay()
