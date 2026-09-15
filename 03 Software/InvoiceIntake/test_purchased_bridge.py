#!/usr/bin/env python
"""Tests for `purchased_bridge.py` (renamed from `purchasing_bridge.py` by
"Align legacy Invoice Intake with Purchased").

Exercises, against a disposable SQLite database (never the shared
`data/rfone.db`): duplicate handling, supplier-side corrections, the
NORMALIZED/HUMAN functional-state heuristic, the single-scope-per-invoice
behavior, and — critically — that creating a Purchase Fact through this
bridge never depends on, or touches, any Restaurant/Purchasing decision or
receiving function (Purchase Order, Configured Expectation, Physical
Receiving, Alert).

Usage:
    python test_purchased_bridge.py
"""

from __future__ import annotations

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_DATA_STORE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RF-One Data Store")
)
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_disposable_test_database_url,
    create_session_factory,
)
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.purchasing import repository as repo  # noqa: E402

import purchased_bridge  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


_DIGITAL_HEADER = {
    "supplier_name": "US Foods",
    "document_number": "INV-1001",
    "document_type": "Invoice",
    "issue_date": "01/15/2026",
    "acquisition_method": "PDF text",
    "currency": "USD",
    "total_amount": "440.00",
}

_TWO_GOODS_LINES = [
    {"description": "Tomatoes", "quantity": "3", "unit": "case", "unit_price": "100.00", "line_amount": "100.00", "line_type": "PRODUCT"},
    {"description": "Mozzarella", "quantity": "2", "unit": "case", "unit_price": "300.00", "line_amount": "300.00", "line_type": "PRODUCT"},
    {"description": "Delivery Fee", "quantity": "", "unit": "", "unit_price": "", "line_amount": "40.00", "line_type": "SURCHARGE"},
]


def _open_session(url: str):
    engine = create_configured_engine(url)
    return create_session_factory(engine)()


def test_static_no_purchasing_decision_dependency(result: Result) -> None:
    """Static check: `purchased_bridge.py` never imports/calls a
    Restaurant/Purchasing *decision or receiving* function (Purchase Order,
    Configured Expectation, Physical Receiving, Alert, Expected Supplier
    Credit) — only Supplier/PurchaseDocument capture functions. Also
    confirms no Bank Reconciliation-shaped name was introduced (scenario
    17.15 of the alignment task)."""

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "purchased_bridge.py")
    source = open(path, encoding="utf-8").read()
    tree = ast.parse(source, filename="purchased_bridge.py")
    called_names = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}

    forbidden_repo_calls = {
        "create_purchase_order",
        "set_configured_expectation",
        "detect_configuration_deviation",
        "decide_configuration_alert",
        "start_receiving",
        "add_receiving_line",
        "complete_receiving",
        "reconcile_receiving_line",
        "raise_receiving_discrepancy_alert",
        "decide_receiving_alert",
        "create_expected_supplier_credit",
        "link_supplier_credit",
        "acknowledge_alert",
    }
    result.check(
        "purchased_bridge.py calls no Purchasing decision/receiving repository function",
        called_names.isdisjoint(forbidden_repo_calls),
    )

    forbidden_terms = ("bank", "reconcil", "payment_match", " pay ")
    lowered = source.lower()
    result.check(
        "purchased_bridge.py introduces no Bank Reconciliation logic (no bank/reconciliation/payment-matching terms)",
        not any(term in lowered for term in forbidden_terms),
    )


def test_standard_invoice_and_allocation(result: Result) -> None:
    """Scenarios 1-4: a standard multi-line invoice with a non-goods charge
    produces Purchased canonical lines, preserves original supplier text,
    and allocates the delivery fee proportionally."""

    url = create_disposable_test_database_url("purchased_bridge_standard")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        doc_id = purchased_bridge.save_purchase_document(_DIGITAL_HEADER, _TWO_GOODS_LINES, "invoice-1001.pdf")
        session = _open_session(url)
        try:
            document = session.get(m.PurchaseDocument, doc_id)
            result.check("a PurchaseDocument was created", document is not None)
            result.check("2 PRODUCT + 1 SURCHARGE line were persisted", len(document.lines) == 3)
            result.check(
                "original supplier description is preserved verbatim on the PRODUCT lines",
                {line.raw_description for line in document.lines if line.line_type == "PRODUCT"}
                == {"Tomatoes", "Mozzarella"},
            )

            allocation = repo.get_purchased_lines_with_allocation(session, doc_id)
            by_desc = {row["raw_description"]: row for row in allocation}
            result.check(
                "the delivery fee is allocated proportionally onto the goods lines (Tomatoes=110.00, Mozzarella=330.00)",
                by_desc["Tomatoes"]["allocated_amount_minor"] == 11000
                and by_desc["Mozzarella"]["allocated_amount_minor"] == 33000,
            )
            result.check(
                "the raw SURCHARGE (Delivery Fee) line is still present as source evidence",
                any(line.line_type == "SURCHARGE" and line.raw_description == "Delivery Fee" for line in document.lines),
            )
            result.check(
                "a cleanly-read digital-PDF invoice with a full header is NORMALIZED",
                purchased_bridge.get_saved_document_functional_status(doc_id) == "NORMALIZED",
            )
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_uncertain_read_is_human(result: Result) -> None:
    """Scenario 6/9/10 ("Improve Generic Parser..."): OCR is no longer, by
    itself, a reason for HUMAN — an OCR-sourced document with complete,
    coherent fields is NORMALIZED exactly like a digital-text one; a
    PRODUCT line with no description still surfaces as HUMAN regardless of
    acquisition method."""

    url = create_disposable_test_database_url("purchased_bridge_human")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        # _DIGITAL_HEADER's own total_amount (440.00) already matches
        # _TWO_GOODS_LINES' sum including its Delivery Fee surcharge (100 +
        # 300 + 40) -- arithmetically coherent -- so acquisition_method=
        # "OCR" is the only thing distinguishing this from a fully-
        # NORMALIZED digital read.
        ocr_header_coherent = dict(_DIGITAL_HEADER, document_number="INV-2000", acquisition_method="OCR")
        doc_id_coherent = purchased_bridge.save_purchase_document(ocr_header_coherent, _TWO_GOODS_LINES, "photo-good.jpg")
        result.check(
            "an OCR-sourced document with complete, coherent fields is NORMALIZED, not HUMAN merely for being OCR",
            purchased_bridge.get_saved_document_functional_status(doc_id_coherent) == "NORMALIZED",
        )

        # Same acquisition method, but a garbled/implausible supplier name
        # and no recognizable date -- a genuinely poor extraction, HUMAN.
        ocr_header_poor = dict(
            _DIGITAL_HEADER,
            document_number="INV-2001",
            acquisition_method="OCR",
            supplier_name="lilllilt]lilt ililililflIilil]t",
            issue_date="",
        )
        doc_id = purchased_bridge.save_purchase_document(ocr_header_poor, _TWO_GOODS_LINES, "photo.jpg")
        result.check(
            "an OCR-sourced document with a poor/garbled extraction is still HUMAN",
            purchased_bridge.get_saved_document_functional_status(doc_id) == "HUMAN",
        )

        missing_header = dict(_DIGITAL_HEADER, document_number="INV-2002", total_amount="")
        doc_id_2 = purchased_bridge.save_purchase_document(missing_header, _TWO_GOODS_LINES, "invoice-2002.pdf")
        result.check(
            "a digital document missing its total amount is HUMAN",
            purchased_bridge.get_saved_document_functional_status(doc_id_2) == "HUMAN",
        )

        blank_desc_lines = [
            {"description": "", "quantity": "1", "unit": "", "unit_price": "5.00", "line_amount": "5.00", "line_type": "PRODUCT"}
        ]
        doc_id_3 = purchased_bridge.save_purchase_document(
            dict(_DIGITAL_HEADER, document_number="INV-2003"), blank_desc_lines, "invoice-2003.pdf"
        )
        session = _open_session(url)
        try:
            line = session.get(m.PurchaseDocument, doc_id_3).lines[0]
            result.check(
                "a PRODUCT line with no description is flagged HUMAN at the line level",
                repo.get_line_functional_status(session, line.id) == "HUMAN",
            )
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_duplicate_returns_same_fact(result: Result) -> None:
    """Scenario 7: the same invoice submitted twice (e.g. two channels)
    produces exactly one Purchase Fact."""

    url = create_disposable_test_database_url("purchased_bridge_duplicate")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        header = dict(_DIGITAL_HEADER, document_number="INV-3001")
        first_id = purchased_bridge.save_purchase_document(header, _TWO_GOODS_LINES, "email-upload.pdf")
        second_id = purchased_bridge.save_purchase_document(dict(header), list(_TWO_GOODS_LINES), "portal-download.pdf")
        result.check(
            "re-submitting an equivalent invoice (same supplier/number/date/total) returns the same PurchaseDocumentId",
            first_id == second_id,
        )
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_conflicting_identity_is_human(result: Result) -> None:
    """Scenario 8: the same invoice identity (supplier + number) arriving
    with different content is never auto-resolved — a new row is inserted
    (nothing lost) and flagged HUMAN."""

    url = create_disposable_test_database_url("purchased_bridge_conflict")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        header = dict(_DIGITAL_HEADER, document_number="INV-4001")
        first_id = purchased_bridge.save_purchase_document(header, _TWO_GOODS_LINES, "invoice-4001-a.pdf")

        conflicting_header = dict(header, total_amount="999.00")
        second_id = purchased_bridge.save_purchase_document(conflicting_header, _TWO_GOODS_LINES, "invoice-4001-b.pdf")

        result.check("a same-identity, different-content submission is inserted as its own row", first_id != second_id)
        result.check(
            "the conflicting new row is flagged HUMAN (never silently chosen/auto-resolved)",
            purchased_bridge.get_saved_document_functional_status(second_id) == "HUMAN",
        )

        session = _open_session(url)
        try:
            result.check(
                "the original document/fact is untouched (never overwritten/deleted)",
                session.get(m.PurchaseDocument, first_id).total_amount_minor == 44000,
            )
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_credit_memo_is_compensating_fact(result: Result) -> None:
    """Scenario 9: a Credit Memo against a prior invoice is its own new,
    linked Purchase Fact — never a rewrite — and is not forced to HUMAN
    merely for being a correction."""

    url = create_disposable_test_database_url("purchased_bridge_credit_memo")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        invoice_header = dict(_DIGITAL_HEADER, document_number="INV-5001")
        invoice_id = purchased_bridge.save_purchase_document(invoice_header, _TWO_GOODS_LINES, "invoice-5001.pdf")

        credit_lines = [
            {"description": "Mozzarella (damaged, credited)", "quantity": "1", "unit": "case", "unit_price": "-30.00", "line_amount": "-30.00", "line_type": "PRODUCT"}
        ]
        credit_header = dict(
            _DIGITAL_HEADER,
            document_number="INV-5001",
            document_type="Credit Memo",
            total_amount="-30.00",
        )
        credit_id = purchased_bridge.save_purchase_document(credit_header, credit_lines, "credit-5001.pdf")

        result.check("the Credit Memo is a distinct new PurchaseDocumentId, not a rewrite of the invoice", credit_id != invoice_id)

        session = _open_session(url)
        try:
            original_still_intact = session.get(m.PurchaseDocument, invoice_id)
            credit_document = session.get(m.PurchaseDocument, credit_id)
            result.check(
                "the original invoice's own total is unchanged by the later credit",
                original_still_intact.total_amount_minor == 44000,
            )
            result.check("the credit memo carries its own negative economic effect", credit_document.total_amount_minor == -3000)
        finally:
            session.close()
        result.check(
            "a Credit Memo is not forced to HUMAN merely for being a correction",
            purchased_bridge.get_saved_document_functional_status(credit_id) == "NORMALIZED",
        )
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_single_scope_per_invoice(result: Result) -> None:
    """Scenario 10: every invoice this bridge saves resolves to exactly one
    economic/operational scope object (here: one Restaurant) — repeated
    calls reuse the same scope rather than creating a new one each time."""

    url = create_disposable_test_database_url("purchased_bridge_scope")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        purchased_bridge.save_purchase_document(dict(_DIGITAL_HEADER, document_number="INV-6001"), _TWO_GOODS_LINES, "a.pdf")
        purchased_bridge.save_purchase_document(dict(_DIGITAL_HEADER, document_number="INV-6002"), _TWO_GOODS_LINES, "b.pdf")

        session = _open_session(url)
        try:
            from sqlalchemy import select

            restaurants = session.scalars(select(m.Restaurant)).all()
            result.check(
                "two separate invoices resolve to the same single scope object, not two",
                len(restaurants) == 1,
            )
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_no_purchasing_side_effects_and_purchasing_can_consume(result: Result) -> None:
    """Scenarios 12-13: creating a Purchase Fact never creates a Purchase
    Order/Configured Expectation/Receiving/Alert row as a side effect (no
    dependency on Restaurant/Purchasing to create the fact) — and once
    created, ordinary Purchasing repository/read code can still consume it
    (Purchasing remains a working consumer, just not the owner)."""

    url = create_disposable_test_database_url("purchased_bridge_no_side_effects")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        doc_id = purchased_bridge.save_purchase_document(
            dict(_DIGITAL_HEADER, document_number="INV-7001"), _TWO_GOODS_LINES, "a.pdf"
        )

        session = _open_session(url)
        try:
            from sqlalchemy import func, select

            for model_cls in (m.PurchaseOrder, m.ConfiguredExpectation, m.ReceivingRecord, m.PurchasingAlert):
                count = session.scalar(select(func.count()).select_from(model_cls))
                result.check(f"no {model_cls.__name__} row was created as a side effect of saving the Purchase Fact", count == 0)

            # Purchasing can still consume the fact it did not create -- e.g.
            # its own configuration-deviation check runs without error.
            document = session.get(m.PurchaseDocument, doc_id)
            product_line = next(line for line in document.lines if line.line_type == "PRODUCT")
            alert = repo.detect_configuration_deviation(session, product_line.id)
            result.check(
                "Restaurant/Purchasing's own repository functions can read/consume the Purchase Fact (no expectation yet -> no Alert, no error)",
                alert is None,
            )
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_replay_does_not_persist_anything(result: Result) -> None:
    """Scenario 12 ("Improve Generic Parser..."): re-running OCR/parser and
    the field-validation/supplier-resolution logic against an
    already-acquired document (a "replay", as §10 of that task does across
    all 10 real documents) must never create a new PurchaseDocument or a
    new Supplier — these are read-only analysis functions, not a second
    write path."""

    url = create_disposable_test_database_url("purchased_bridge_replay")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        # A real document already saved once (the "original" acquisition).
        doc_id = purchased_bridge.save_purchase_document(
            dict(_DIGITAL_HEADER, document_number="INV-8001"), _TWO_GOODS_LINES, "invoice-8001.pdf"
        )

        session = _open_session(url)
        try:
            from sqlalchemy import func, select

            doc_count_before = session.scalar(select(func.count()).select_from(m.PurchaseDocument))
            supplier_count_before = session.scalar(select(func.count()).select_from(m.Supplier))

            # "Replay": re-run the read-only field-validation/supplier-
            # resolution functions against the same extracted text, exactly
            # as a reprocessing/report pass would -- never calling
            # save_purchase_document() again.
            restaurant_id = purchased_bridge._get_or_create_default_restaurant(session)
            resolved_supplier = purchased_bridge._resolve_supplier_name(
                session, restaurant_id, _DIGITAL_HEADER["supplier_name"], "invoice-8001.pdf"
            )
            document_header = {
                "issue_date": purchased_bridge._parse_date(_DIGITAL_HEADER["issue_date"]),
                "total_amount_minor": purchased_bridge._parse_money_minor(_DIGITAL_HEADER["total_amount"]),
            }
            purchased_bridge._validate_extracted_fields(resolved_supplier, document_header, [], "")
            session.rollback()

            doc_count_after = session.scalar(select(func.count()).select_from(m.PurchaseDocument))
            supplier_count_after = session.scalar(select(func.count()).select_from(m.Supplier))

            result.check("replaying field validation creates no new PurchaseDocument", doc_count_after == doc_count_before)
            result.check("replaying supplier resolution creates no new Supplier", supplier_count_after == supplier_count_before)
            result.check("the original document is untouched and still retrievable", session.get(m.PurchaseDocument, doc_id) is not None)
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


_PRIME_LINE_RAW_TEXT = """PRIME LINE DISTRIBUTORS INVOICE
IMPORTERS OF SELECTED SPECIALTY FOODS
ROME'S FLAVOURS Number: 1107919
Date: 06/30/20
CASH CHECK # AMOUNT INVOICE #
Ootters Conte
SUBTOTAL $ 523.72
TAX $ 0.00
TOTAL $ 523.72
"""

# What the GENERIC parser alone actually produces for `_PRIME_LINE_RAW_TEXT`
# (wrong document_number, from the blank "INVOICE #" stub -- see
# `test_supplier_format_rules.py` for the same finding against real OCR
# text) -- used here to prove `save_purchase_document()` itself applies the
# Phase 1 specialization, not just the pure function in isolation.
_PRIME_LINE_GENERIC_HEADER = {
    "supplier_name": "IMPORTERS OF SELECTED SPECIALTY FOODS",
    "document_number": "Ootters",
    "document_type": "Invoice",
    "issue_date": "06/30/20",
    "acquisition_method": "OCR",
    "currency": "USD",
    "total_amount": "523.72",
}


def test_supplier_format_specialization_applied_end_to_end(result: Result) -> None:
    """"Purchased Supplier+Format Training — Phase 1": `save_purchase_document`
    itself (not just `supplier_format_rules.py` in isolation) must run the
    Prime Line specialization over the generic parser's header before
    resolving/validating it -- correcting the wrong document_number and
    canonicalizing the supplier name -- resulting in NORMALIZED for an
    otherwise-complete real-pattern read."""

    url = create_disposable_test_database_url("purchased_bridge_specialization")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        lines = [{"description": "San Benedetto Water", "quantity": "8", "unit": "case", "unit_price": "7.99", "line_amount": "523.72", "line_type": "PRODUCT"}]
        doc_id = purchased_bridge.save_purchase_document(
            _PRIME_LINE_GENERIC_HEADER, lines, "PL20200630125750_001.pdf", raw_text=_PRIME_LINE_RAW_TEXT
        )
        session = _open_session(url)
        try:
            document = session.get(m.PurchaseDocument, doc_id)
            supplier = session.get(m.Supplier, document.supplier_id)
            result.check("supplier name was canonicalized by the specialization, not left as the generic guess", supplier.name == "Prime Line Distributors")
            result.check("document_number was corrected by the specialization, not left as the wrong generic stub value", document.document_number == "1107919")
            result.check(
                "a fully specialized, coherent Prime Line read is NORMALIZED",
                purchased_bridge.get_saved_document_functional_status(doc_id) == "NORMALIZED",
            )
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_specialization_does_not_break_duplicate_detection(result: Result) -> None:
    """Task requirement 13 ("NON creare duplicati Purchased"): resubmitting
    the exact same real-pattern document a second time (e.g. arriving again
    through a different channel) must still be recognized as the same
    Purchase Fact now that the specialization changes what document_number/
    supplier actually get persisted."""

    url = create_disposable_test_database_url("purchased_bridge_specialization_dup")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        lines = [{"description": "San Benedetto Water", "quantity": "8", "unit": "case", "unit_price": "7.99", "line_amount": "523.72", "line_type": "PRODUCT"}]
        first_id = purchased_bridge.save_purchase_document(
            _PRIME_LINE_GENERIC_HEADER, lines, "PL20200630125750_001.pdf", raw_text=_PRIME_LINE_RAW_TEXT
        )
        second_id = purchased_bridge.save_purchase_document(
            _PRIME_LINE_GENERIC_HEADER, lines, "PL20200630125750_001.pdf (resent)", raw_text=_PRIME_LINE_RAW_TEXT
        )
        result.check("resubmitting the same specialized document returns the same PurchaseDocumentId", first_id == second_id)

        session = _open_session(url)
        try:
            from sqlalchemy import func, select

            doc_count = session.scalar(select(func.count()).select_from(m.PurchaseDocument))
            result.check("exactly one PurchaseDocument was persisted, not two", doc_count == 1)
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_costco_specialization_applied_end_to_end(result: Result) -> None:
    """Same Phase 1 wiring check for Costco: Merchant-ID-only recognition
    (no "COSTCO" wordmark in this raw text, matching the real
    `CO2020-02-08.pdf` sample) and the EFT/Debit total, both applied by
    `save_purchase_document` itself."""

    costco_raw_text = (
        "Altamonte Springs #183\n"
        "SUBTOTAL 364.36\nTAX 4.06\nwoe TOTAL PSO 42 |\n"
        "Tran ID#: 063900003938....\nMerchant ID: 990183\n"
        "EFT/Debit 368.42\nCHANGE 0.00\n02/08/2020 11:45\n"
    )
    generic_header = {
        "supplier_name": "Altamonte Springs #183",
        "document_number": "",
        "document_type": "Invoice",
        "issue_date": "02/08/2020",
        "acquisition_method": "OCR",
        "currency": "USD",
        "total_amount": "0.00",
    }
    url = create_disposable_test_database_url("purchased_bridge_costco_specialization")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        doc_id = purchased_bridge.save_purchase_document(generic_header, [], "CO2020-02-08.pdf", raw_text=costco_raw_text)
        session = _open_session(url)
        try:
            document = session.get(m.PurchaseDocument, doc_id)
            supplier = session.get(m.Supplier, document.supplier_id)
            result.check("Costco recognized via Merchant ID even without the wordmark", supplier.name == "Costco Wholesale")
            result.check("document_number taken from Tran ID#, not left blank", document.document_number == "063900003938")
            result.check("total_amount taken from EFT/Debit, not the garbled/zero-read TOTAL line", document.total_amount_minor == 36842)
        finally:
            session.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def main() -> int:
    # `save_purchase_document()` always writes to
    # `supplier_format_training.py`'s own observation store as a side
    # effect; every test in this file that calls it must never pollute the
    # real, persistent training data with synthetic test suppliers (Task
    # "Purchased Supplier+Format Training — Phase 1" finding — see
    # `supplier_format_training.py`'s `_ENV_DB_PATH_OVERRIDE`).
    import shutil
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="supplier_format_training_isolation_")
    os.environ["SUPPLIER_FORMAT_TRAINING_DB_PATH"] = os.path.join(tmp_dir, "isolated_training.db")

    result = Result()
    try:
        for test_fn in (
            test_static_no_purchasing_decision_dependency,
            test_standard_invoice_and_allocation,
            test_uncertain_read_is_human,
            test_duplicate_returns_same_fact,
            test_conflicting_identity_is_human,
            test_credit_memo_is_compensating_fact,
            test_single_scope_per_invoice,
            test_no_purchasing_side_effects_and_purchasing_can_consume,
            test_replay_does_not_persist_anything,
            test_supplier_format_specialization_applied_end_to_end,
            test_specialization_does_not_break_duplicate_detection,
            test_costco_specialization_applied_end_to_end,
        ):
            test_fn(result)
    finally:
        os.environ.pop("SUPPLIER_FORMAT_TRAINING_DB_PATH", None)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"purchased_bridge tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"purchased_bridge tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
