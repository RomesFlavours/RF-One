#!/usr/bin/env python
"""Tests for `human_review.py` / `review_authority.py` / the `/review*` and
`/training*` Flask routes ("Purchased Human Review + Supplier Format
Training UI").

Always targets a disposable database (`RFONE_DATABASE_URL`) and an
isolated `supplier_format_training` store (`SUPPLIER_FORMAT_TRAINING_DB_PATH`)
for the whole run — same isolation convention `test_purchased_bridge.py`
established, extended here since every mutating route in this file calls
through to both stores.

Usage:
    python test_human_review.py
"""

from __future__ import annotations

import ast
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_DATA_STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RF-One Data Store"))
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

import human_review  # noqa: E402
import ocr_engine  # noqa: E402
import purchased_bridge  # noqa: E402
import review_authority  # noqa: E402
import supplier_format_training as sft  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def _open_session(url: str):
    engine = create_configured_engine(url)
    return create_session_factory(engine)()


# -- Fixtures -----------------------------------------------------------------

_COMPLETE_HEADER = {
    "supplier_name": "Test Foods Inc.",
    "document_number": "HR-1001",
    "document_type": "Invoice",
    "issue_date": "01/15/2026",
    "acquisition_method": "PDF-Text",
    "currency": "USD",
    "total_amount": "440.00",
}
_HUMAN_LINES = [
    {"description": "Tomatoes", "quantity": "3", "unit": "case", "unit_price": "100.00", "line_amount": "100.00", "line_type": "PRODUCT"},
    {"description": "Mozzarella", "quantity": "2", "unit": "case", "unit_price": "300.00", "line_amount": "300.00", "line_type": "PRODUCT"},
    {"description": "Delivery Fee", "quantity": "", "unit": "", "unit_price": "", "line_amount": "40.00", "line_type": "SURCHARGE"},
]


def _make_human_document(source_file: str = "hr-test.pdf", document_number: str = "HR-2001") -> int:
    """A document that lands HUMAN because issue_date is missing/blank —
    same real mechanism `_validate_extracted_fields` already uses."""

    header = dict(_COMPLETE_HEADER, document_number=document_number, issue_date="")
    return purchased_bridge.save_purchase_document(header, _HUMAN_LINES, source_file)


def _prime_line_page(number: str, date: str, total: str) -> str:
    return (
        "PRIME LINE DISTRIBUTORS INVOICE\n"
        f"ROME'S FLAVOURS Number: {number}\n"
        f"Date: {date}\n"
        "BM43 8 CASE SAN BENEDETTO NATURAL PET 1.5L 6/50.7 oz 8 7.99 63.92\n"
        f"TOTAL $ {total}\n"
    )


def _keith_page(number: str, page_in_invoice: int, total_line: str = "") -> str:
    return (
        "REMIT TO: BEN E KEITH FLORIDA FOODS\n"
        f"lnvoice No. Page Rep\n{number} {page_in_invoice} OT\n"
        "CHICKEN BREAST 8OZ BUTTER 2/10 LB 85.06 170.12\n" + total_line
    )


def _costco_direct_text() -> str:
    return (
        "COSTCO\n"
        "SUBTOTAL 149.44\nTAX 0.00\n**** TOTAL PD 44\n"
        "Tran ID#: 004200002942....\nMerchant ID: 990183\n"
        "EFT/Debit 149.44\nCHANGE 0.00\n02/11/2020 11:36\n"
    )


# -- 1/2/3/4/5: queue, multi-invoice visibility, page provenance --------------


def test_queue_lists_only_human_documents(result: Result) -> None:
    human_id = _make_human_document(source_file="hr-human.pdf", document_number="HR-QUEUE-HUMAN")
    normalized_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, document_number="HR-QUEUE-NORMALIZED"), _HUMAN_LINES, "hr-normalized.pdf"
    )
    rows = human_review.get_review_queue()
    ids_in_queue = {row["id"] for row in rows}
    result.check("a HUMAN document appears in the queue", human_id in ids_in_queue)
    result.check("a NORMALIZED document does not appear in the queue", normalized_id not in ids_in_queue)


def test_prime_line_batch_four_review_records(result: Result) -> None:
    pages = [
        _prime_line_page("7001001", "06/30/20", "100.00"),
        _prime_line_page("7001002", "05/26/20", "200.00"),
        _prime_line_page("7001003", "05/26/20", "300.00"),
        _prime_line_page("7001004", "05/26/20", "400.00"),
    ]
    document_ids = purchased_bridge.save_purchase_documents_from_batch(pages, "hr_primeline_batch.pdf", "OCR")
    result.check("4 PurchaseDocuments were created for the 4-invoice batch", len(document_ids) == 4)

    queue_ids = {row["id"] for row in human_review.get_review_queue()}
    result.check("all 4 batch invoices appear as separate review records in the queue", set(document_ids).issubset(queue_ids))

    view = human_review.get_review_detail(document_ids[0])
    sibling_ids = {sib.id for sib in view["siblings"]}
    result.check("multi-invoice visibility: viewing one shows all 3 others as siblings", sibling_ids == set(document_ids[1:]))
    result.check("this record is flagged multi-invoice in the queue", any(row["id"] == document_ids[0] and row["is_multi_invoice"] for row in human_review.get_review_queue()))


def test_keith_batch_two_review_records_multi_page(result: Result) -> None:
    pages = [
        _keith_page("8001001", 1, total_line="Total Invoice 170.12\n"),
        _keith_page("8001002", 1),
        _keith_page("8001002", 2, total_line="New Total 340.24\n"),
    ]
    document_ids = purchased_bridge.save_purchase_documents_from_batch(pages, "hr_keith_batch.pdf", "PDF-Text")
    result.check("exactly 2 PurchaseDocuments for 3 pages, 2 real invoices (no false split)", len(document_ids) == 2)

    single_page_view = human_review.get_review_detail(document_ids[0])
    multi_page_view = human_review.get_review_detail(document_ids[1])
    result.check("the single-page invoice's page_range is just p1", single_page_view["page_range"] == "p1")
    result.check(
        "the multi-page invoice's page_range correctly spans p2-3 (both pages represented, not lost)",
        multi_page_view["page_range"] == "p2-3",
    )


def test_page_provenance_correct(result: Result) -> None:
    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, document_number="HR-PROVENANCE"), _HUMAN_LINES, "plain_single.pdf"
    )
    view = human_review.get_review_detail(document_id)
    result.check("a non-split document's source_filename is the plain filename", view["source_filename"] == "plain_single.pdf")
    result.check("a non-split document has no page_range suffix", view["page_range"] is None)


# -- 6/7/8/9: field correction, original preserved, HUMAN/NORMALIZED ----------


def test_field_correction_persists_and_preserves_original(result: Result) -> None:
    document_id = _make_human_document(source_file="hr-correct.pdf", document_number="HR-CORRECT-1")
    before = human_review.get_review_detail(document_id)
    result.check("issue_date starts out missing (extracted, not yet corrected)", not before["header_effective"]["issue_date"])

    human_review.submit_field_review(
        document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026"
    )
    after = human_review.get_review_detail(document_id)
    result.check("the corrected value is now the EFFECTIVE value", after["header_effective"]["issue_date"] == "01/15/2026")
    result.check(
        "the ORIGINAL extracted value is still preserved (never overwritten) in header_original",
        after["header_original"]["issue_date"] in (None, ""),
    )
    session = _open_session(purchased_bridge.get_database_url())
    try:
        document = session.get(m.PurchaseDocument, document_id)
        result.check("PurchaseDocument.issue_date column itself was never mutated", document.issue_date is None)
    finally:
        session.close()


def test_correct_confirmation_after_prior_correction_does_not_revert(result: Result) -> None:
    """Bug fix ("Purchased Operator Review Test on Real Invoices" -- found
    by actually driving a real two-step review through the app on a real
    Ben E. Keith invoice): correcting a field (INCORRECT -> a real value),
    then LATER submitting a bare CORRECT confirmation on that SAME field
    (a realistic reviewer action -- re-opening a document and confirming a
    value someone already fixed) must CONFIRM the already-corrected value,
    never silently revert it back to the raw, wrong original."""

    document_id = _make_human_document(source_file="hr-confirm-after-correct.pdf", document_number="HR-CONFIRM-AFTER-CORRECT")
    before = human_review.get_review_detail(document_id)
    result.check("supplier starts out at its raw extracted value", before["header_effective"]["supplier"] == "Test Foods Inc.")

    human_review.submit_field_review(
        document_id, field_name="supplier", classification="INCORRECT", reviewed_by="alice", corrected_value="Corrected Supplier Name"
    )
    after_correction = human_review.get_review_detail(document_id)
    result.check(
        "the correction is effective immediately", after_correction["header_effective"]["supplier"] == "Corrected Supplier Name"
    )

    # A later CORRECT confirmation on the same field -- e.g. a second
    # reviewer re-checking the document and agreeing the correction stands.
    human_review.submit_field_review(document_id, field_name="supplier", classification="CORRECT", reviewed_by="bob")
    after_confirmation = human_review.get_review_detail(document_id)
    result.check(
        "a later CORRECT confirmation CONFIRMS the already-corrected value -- it must NOT revert to the raw original",
        after_confirmation["header_effective"]["supplier"] == "Corrected Supplier Name",
    )
    result.check(
        "the raw PurchaseDocument column itself is still untouched throughout (both records are additive)",
        after_confirmation["header_original"]["supplier"] == "Test Foods Inc.",
    )


def test_queue_shows_effective_header_values_not_raw(result: Result) -> None:
    """Task "Make Effective Purchased View canonical for all consumers",
    item 6/7/8: a document still HUMAN for one unresolved field must still
    show its OTHER, already-corrected header fields as effective in the
    review queue -- not the stale raw extraction. The queue is itself a
    Purchased consumer (Restaurant/Purchasing's own reviewers read it),
    not just `review_detail()`."""

    document_id = _make_human_document(source_file="hr-queue-effective.pdf", document_number="HR-QUEUE-EFFECTIVE")
    # Correct supplier, document number and total, but leave issue_date (the
    # actual blocker for this fixture, see _make_human_document) unresolved
    # -- the document stays HUMAN and in the queue.
    human_review.submit_field_review(
        document_id, field_name="supplier", classification="INCORRECT", reviewed_by="alice", corrected_value="Corrected Foods Inc."
    )
    human_review.submit_field_review(
        document_id, field_name="document_number", classification="INCORRECT", reviewed_by="alice", corrected_value="HR-QUEUE-FIXED"
    )
    human_review.submit_field_review(
        document_id, field_name="total_amount", classification="INCORRECT", reviewed_by="alice", corrected_value="999.00"
    )

    rows = {row["id"]: row for row in human_review.get_review_queue()}
    result.check("the corrected document is still in the queue (issue_date still unresolved)", document_id in rows)
    row = rows.get(document_id, {})
    result.check("the queue shows the CORRECTED supplier (supplier correction reflected), not the raw one", row.get("supplier_name") == "Corrected Foods Inc.")
    result.check("the queue shows the CORRECTED document number", row.get("document_number") == "HR-QUEUE-FIXED")
    result.check("the queue shows the CORRECTED total amount (total correction reflected)", row.get("total_amount") == "999.00")


def test_no_duplicate_merge_logic(result: Result) -> None:
    """Task requirement 17: "NON duplicare merge logic in più moduli" -- the
    "latest correction per field wins" reduction has exactly one
    implementation, in `purchasing/repository.py`
    (`resolve_latest_field_corrections`/`latest_field_corrections`/
    `effective_field_value`); `human_review.py` must call it, never keep its
    own private copy (it used to, as `_latest_corrections`/`_effective_value`,
    before "Make Effective Purchased View canonical for all consumers")."""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    source = open(os.path.join(base_dir, "human_review.py"), encoding="utf-8").read()
    tree = ast.parse(source, filename="human_review.py")
    defined_function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    result.check(
        "human_review.py no longer defines its own correction-merge helpers (moved to repository.py)",
        "_latest_corrections" not in defined_function_names and "_effective_value" not in defined_function_names,
    )
    result.check(
        "the single canonical merge implementation lives in the repository module",
        hasattr(repo, "resolve_latest_field_corrections")
        and hasattr(repo, "latest_field_corrections")
        and hasattr(repo, "effective_field_value"),
    )
    result.check(
        "human_review.py actually calls the shared repository merge functions, not a local equivalent",
        "repo.effective_field_value(" in source and "repo.latest_field_corrections(" in source,
    )


def test_incomplete_review_remains_human(result: Result) -> None:
    document_id = _make_human_document(source_file="hr-incomplete.pdf", document_number="HR-INCOMPLETE")
    # Only confirm the supplier -- issue_date is still missing/blocking.
    human_review.submit_field_review(document_id, field_name="supplier", classification="CORRECT", reviewed_by="alice")
    result_dict = human_review.complete_review(document_id, reviewed_by="alice")
    result.check("a review with an unresolved blocking field stays HUMAN", result_dict["functional_status"] == "HUMAN")
    result.check("reasons still name the missing issue date", any("issue date" in r for r in result_dict["reasons"]))


def test_complete_review_normalizes(result: Result) -> None:
    document_id = _make_human_document(source_file="hr-complete.pdf", document_number="HR-COMPLETE-1")
    human_review.submit_field_review(
        document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026"
    )
    result_dict = human_review.complete_review(document_id, reviewed_by="alice")
    result.check("correcting the one blocking field and completing review -> NORMALIZED", result_dict["functional_status"] == "NORMALIZED")

    session = _open_session(purchased_bridge.get_database_url())
    try:
        result.check(
            "repository-level status also now reads NORMALIZED (OPEN entries were closed)",
            repo.get_document_functional_status(session, document_id) == "NORMALIZED",
        )
    finally:
        session.close()
    result.check("a HUMAN document no longer appears in the queue once NORMALIZED", document_id not in {row["id"] for row in human_review.get_review_queue()})


# -- 10/11: training store integration -----------------------------------------


def test_training_store_updated_automatically(result: Result) -> None:
    document_id = _make_human_document(source_file="hr-training.pdf", document_number="HR-TRAINING-1")
    human_review.submit_field_review(
        document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026"
    )
    human_review.complete_review(document_id, reviewed_by="alice")

    training_store = sft.SupplierFormatTrainingStore()
    try:
        observation = training_store.get("Test Foods Inc.", "PDF-Text/Direct")
        result.check("completing a review recorded a training observation with NO second manual step", observation is not None and observation.reviewed_count >= 1)
        reviews = training_store.list_field_reviews(supplier_name="Test Foods Inc.")
        result.check("the corrected field's review classification was also recorded", any(r.field_name == "issue_date" and r.classification == "INCORRECT" for r in reviews))
    finally:
        training_store.close()


def test_consecutive_correct_count_updated(result: Result) -> None:
    """All 3 documents are created (and thus their own SAVE-time HUMAN
    observations recorded) BEFORE any review happens, so the streak isn't
    reset partway through by a later document's own initial HUMAN save —
    only the 3 review completions below should build the streak."""

    training_store_name = "Streak Foods"
    document_ids = [
        purchased_bridge.save_purchase_document(
            dict(_COMPLETE_HEADER, supplier_name=training_store_name, document_number=f"HR-STREAK-{i}", issue_date=""),
            _HUMAN_LINES,
            f"hr-streak-{i}.pdf",
        )
        for i in range(3)
    ]
    for document_id in document_ids:
        human_review.submit_field_review(document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026")
        human_review.complete_review(document_id, reviewed_by="alice")
    training_store = sft.SupplierFormatTrainingStore()
    try:
        observation = training_store.get(training_store_name, "PDF-Text/Direct")
        result.check("3 consecutive NORMALIZED review completions increment consecutive_correct_count to 3", observation.consecutive_correct_count == 3)
    finally:
        training_store.close()


# -- 12/13/14: trust eligibility & VALIDATE FORMAT -----------------------------


def test_eligible_after_configured_threshold_and_validate_flow(result: Result) -> None:
    supplier_name = "Threshold Foods"
    training_store = sft.SupplierFormatTrainingStore()
    try:
        training_store.set_trust_threshold(2, supplier_name=supplier_name, source_format="PDF-Text/Direct")
    finally:
        training_store.close()

    for i in range(2):
        document_id = purchased_bridge.save_purchase_document(
            dict(_COMPLETE_HEADER, supplier_name=supplier_name, document_number=f"HR-ELIGIBLE-{i}"), _HUMAN_LINES, f"hr-eligible-{i}.pdf"
        )
        human_review.complete_review(document_id, reviewed_by="alice")

    training_store = sft.SupplierFormatTrainingStore()
    try:
        result.check(
            "still UNTRAINED (never explicitly moved to TRAINING) -- not eligible even with a met streak",
            not training_store.is_eligible_for_validation(supplier_name, "PDF-Text/Direct")[0],
        )
        training_store.set_trust_state(supplier_name, "PDF-Text/Direct", sft.TRUST_STATE_TRAINING)
    finally:
        training_store.close()

    # Test list requirement 13: VALIDATE FORMAT denied before eligibility
    # (reviewed_count/streak reset conceptually once moved to TRAINING --
    # re-run the 2 needed observations while already in TRAINING).
    for i in range(2, 4):
        document_id = purchased_bridge.save_purchase_document(
            dict(_COMPLETE_HEADER, supplier_name=supplier_name, document_number=f"HR-ELIGIBLE-{i}"), _HUMAN_LINES, f"hr-eligible-{i}.pdf"
        )
        human_review.complete_review(document_id, reviewed_by="alice")

    rows = {(r["supplier_name"], r["source_format"]): r for r in human_review.list_supplier_training_status()}
    row = rows[(supplier_name, "PDF-Text/Direct")]
    result.check("ELIGIBLE FOR VALIDATION is shown once threshold is met while TRAINING", row["eligible"] is True)

    # Test list requirement 14: VALIDATE FORMAT allowed after eligibility.
    outcome = human_review.validate_supplier_format(supplier_name, "PDF-Text/Direct")
    result.check("validate_supplier_format() promotes to VALIDATED once eligible", outcome["trust_state"] == sft.TRUST_STATE_VALIDATED)


def test_validate_format_denied_before_eligibility(result: Result) -> None:
    supplier_name = "Never Eligible Foods"
    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, supplier_name=supplier_name, document_number="HR-NOTYET"), _HUMAN_LINES, "hr-notyet.pdf"
    )
    human_review.complete_review(document_id, reviewed_by="alice")  # only 1 observation, still UNTRAINED
    raised = False
    try:
        human_review.validate_supplier_format(supplier_name, "PDF-Text/Direct")
    except ValueError:
        raised = True
    result.check("validate_supplier_format() refuses (raises) when not eligible -- never bypasses the service logic", raised)


# -- 15: DEGRADED visibility ----------------------------------------------------


def test_degraded_format_visible(result: Result) -> None:
    training_store = sft.SupplierFormatTrainingStore()
    try:
        training_store.record_observation(supplier_name="Degrading Foods", source_format="OCR/Direct", was_normalized=True, signature="S1D1N1T1-L3")
        training_store.set_trust_state("Degrading Foods", "OCR/Direct", sft.TRUST_STATE_VALIDATED)
        training_store.record_observation(supplier_name="Degrading Foods", source_format="OCR/Direct", was_normalized=False, signature="S1D1N1T1-L3")
    finally:
        training_store.close()
    rows = {(r["supplier_name"], r["source_format"]): r for r in human_review.list_supplier_training_status()}
    result.check("a format that just degraded shows DEGRADED in the training status view", rows[("Degrading Foods", "OCR/Direct")]["trust_state"] == sft.TRUST_STATE_DEGRADED)


# -- 16/17: supplier alias preserved, no duplicate ------------------------------


def test_supplier_alias_preserved_no_duplicate(result: Result) -> None:
    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, supplier_name="ACME DISTRIBUTORS INVOICE", document_number="HR-ALIAS-1", issue_date=""),
        _HUMAN_LINES,
        "hr-alias.pdf",
    )
    human_review.submit_field_review(document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026")
    human_review.submit_field_review(document_id, field_name="supplier", classification="INCORRECT", reviewed_by="alice", corrected_value="ACME Distributors")
    human_review.complete_review(document_id, reviewed_by="alice")

    session = _open_session(purchased_bridge.get_database_url())
    try:
        from sqlalchemy import select

        suppliers = session.scalars(select(m.Supplier).where(m.Supplier.name.in_(["ACME DISTRIBUTORS INVOICE", "ACME Distributors"]))).all()
        canonical = next((s for s in suppliers if s.name == "ACME Distributors"), None)
        result.check("the corrected canonical Supplier was created", canonical is not None)
        if canonical is not None:
            aliases = repo.list_supplier_aliases(session, canonical.id)
            result.check("the original extracted name is preserved as a known alias", any(a.alias_name == "ACME DISTRIBUTORS INVOICE" for a in aliases))
        result.check("no duplicate 'ACME Distributors' Supplier row was created", len([s for s in suppliers if s.name == "ACME Distributors"]) <= 1)
    finally:
        session.close()


# -- 18: Costco Direct channel --------------------------------------------------


def test_costco_direct_channel_preserved(result: Result) -> None:
    document_id = purchased_bridge.save_purchase_document(
        {
            "supplier_name": "COSTCO",
            "document_number": "",
            "document_type": "Invoice",
            "issue_date": "",
            "acquisition_method": "OCR",
            "currency": "USD",
            "total_amount": "0.00",
        },
        [],
        "hr-costco.pdf",
        raw_text=_costco_direct_text(),
    )
    human_review.submit_field_review(document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="02/11/2020")
    human_review.complete_review(document_id, reviewed_by="alice")

    training_store = sft.SupplierFormatTrainingStore()
    try:
        observation = training_store.get("Costco Wholesale", "OCR/Direct")
        result.check("Costco receipt correctly trains under the OCR/Direct channel", observation is not None)
        instacart_observation = training_store.get("Costco Wholesale", "OCR/Instacart")
        result.check("never confused with an Instacart channel", instacart_observation is None)
    finally:
        training_store.close()


# -- 19/20/21: authority gating (Flask-level) -----------------------------------


def _client():
    import app as flask_app

    return flask_app.app.test_client()


def _login(client, role: str):
    with client.session_transaction() as sess:
        sess["reviewer_name"] = "tester"
        sess["reviewer_role"] = role


def test_source_file_access_protected(result: Result) -> None:
    client = _client()
    unauthenticated_response = client.get("/review/source/nonexistent.pdf")
    result.check("no session at all -> source file access is rejected (403)", unauthenticated_response.status_code == 403)

    _login(client, review_authority.ROLE_VIEWER)
    viewer_response = client.get("/review/source/nonexistent.pdf")
    result.check("a logged-in VIEWER may attempt access (falls through to 404 for a missing file, not 403)", viewer_response.status_code == 404)


def test_unauthorized_correction_rejected(result: Result) -> None:
    document_id = _make_human_document(source_file="hr-authz-correct.pdf", document_number="HR-AUTHZ-1")
    client = _client()
    _login(client, review_authority.ROLE_VIEWER)
    response = client.post(f"/review/{document_id}/field", data={"field_name": "issue_date", "classification": "CORRECT"})
    result.check("a VIEWER cannot submit a field correction (403)", response.status_code == 403)

    session = _open_session(purchased_bridge.get_database_url())
    try:
        result.check("no correction was actually recorded", repo.list_field_corrections(session, document_id) == [])
    finally:
        session.close()


def test_unauthorized_format_validation_rejected(result: Result) -> None:
    client = _client()
    _login(client, review_authority.ROLE_REVIEWER)
    response = client.post("/training/validate", data={"supplier_name": "Anyone", "source_format": "OCR/Direct"})
    result.check("a REVIEWER (not VALIDATOR) cannot validate a Supplier+Format (403)", response.status_code == 403)


def test_authorized_actions_succeed(result: Result) -> None:
    """The positive-path counterpart to the two tests above, so a bug that
    makes EVERYTHING 403 wouldn't silently pass those."""

    document_id = _make_human_document(source_file="hr-authz-positive.pdf", document_number="HR-AUTHZ-2")
    client = _client()
    _login(client, review_authority.ROLE_REVIEWER)
    response = client.post(f"/review/{document_id}/field", data={"field_name": "supplier", "classification": "CORRECT"})
    result.check("a REVIEWER CAN submit a field correction", response.status_code in (200, 302))

    _login(client, review_authority.ROLE_VALIDATOR)
    queue_response = client.get("/review")
    result.check("a VALIDATOR can also view the queue (cumulative roles)", queue_response.status_code == 200)


# -- 25: no Bank Reconciliation logic --------------------------------------------


def test_no_bank_reconciliation_logic(result: Result) -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    forbidden_terms = ("bank", "reconcil", "payment_match", " pay ")
    for filename in ("human_review.py", "review_authority.py"):
        source = open(os.path.join(base_dir, filename), encoding="utf-8").read().lower()
        result.check(f"{filename} introduces no Bank Reconciliation logic", not any(term in source for term in forbidden_terms))

    # Static check mirroring test_purchased_bridge.py's own: human_review.py
    # never calls a Restaurant/Purchasing decision/receiving function.
    tree = ast.parse(open(os.path.join(base_dir, "human_review.py"), encoding="utf-8").read(), filename="human_review.py")
    called_names = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    forbidden_repo_calls = {
        "create_purchase_order", "set_configured_expectation", "detect_configuration_deviation",
        "decide_configuration_alert", "start_receiving", "add_receiving_line", "complete_receiving",
        "reconcile_receiving_line", "raise_receiving_discrepancy_alert", "decide_receiving_alert",
        "create_expected_supplier_credit", "link_supplier_credit", "acknowledge_alert",
    }
    result.check("human_review.py calls no Purchasing decision/receiving repository function", called_names.isdisjoint(forbidden_repo_calls))


# ---------------------------------------------------------------------------
# "Close Purchased Human Review Reliability Gaps" -- manual upload
# multi-invoice split (task tests 1-4)
# ---------------------------------------------------------------------------


def test_manual_upload_uses_shared_split_no_duplicate_logic(result: Result) -> None:
    """Task §2 / §9 test: "NON duplicare la split logic" -- app.py's
    /upload route has no split algorithm of its own. It never imports
    `invoice_splitter` directly and calls the exact same
    `purchased_bridge.save_purchase_documents_from_batch()` the mailbox
    pipeline already calls (§9 test 3, "mailbox path invariato" -- both
    channels literally share one function, so neither can drift from the
    other)."""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_source = open(os.path.join(base_dir, "app.py"), encoding="utf-8").read()
    tree = ast.parse(app_source, filename="app.py")
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    result.check(
        "app.py does not import invoice_splitter directly (no duplicated split logic)",
        "invoice_splitter" not in imported_modules,
    )
    called_attrs = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    result.check(
        "app.py's /upload route calls the shared save_purchase_documents_from_batch (same path mailbox uses)",
        "save_purchase_documents_from_batch" in called_attrs,
    )
    result.check(
        "app.py no longer calls the old single-document save_purchase_document from /upload",
        "save_purchase_document" not in called_attrs,
    )


def _upload_with_fake_pages(client, pages: list[str], filename: str):
    """Monkeypatches `ocr_engine.extract_pages_from_pdf` (module-attribute
    access, so this reaches app.py's own `ocr_engine.extract_pages_from_pdf(...)`
    call too) so the manual /upload route can be exercised end-to-end with
    deterministic, real-evidence-shaped page text — the same fixtures
    `test_prime_line_batch_four_review_records`/`test_keith_batch_two_review_records_multi_page`
    already use directly against `save_purchase_documents_from_batch()` --
    without depending on an actual multi-page PDF file on disk (real
    acquired PDFs are untracked, environment-local artifacts, never a valid
    test dependency)."""

    original = ocr_engine.extract_pages_from_pdf
    ocr_engine.extract_pages_from_pdf = lambda path: (pages, "OCR")
    try:
        data = {"invoice_file": (io.BytesIO(b"%PDF-1.4 fake content for manual-upload split testing"), filename)}
        return client.post("/upload", data=data, content_type="multipart/form-data")
    finally:
        ocr_engine.extract_pages_from_pdf = original


def _documents_matching_filename(filename: str) -> list["m.PurchaseDocument"]:
    from sqlalchemy import select

    session = _open_session(purchased_bridge.get_database_url())
    try:
        return [
            d
            for d in session.scalars(select(m.PurchaseDocument)).all()
            if d.source_reference and filename in d.source_reference
        ]
    finally:
        session.close()


def test_manual_upload_prime_line_batch_creates_4_documents(result: Result) -> None:
    """Task §2/§9 test 1: a manually uploaded 4-page Prime Line batch (the
    exact real-world case the automated mailbox pipeline already handled)
    now produces 4 PurchaseDocuments through the manual /upload route too."""

    pages = [
        _prime_line_page("9101001", "07/01/26", "111.00"),
        _prime_line_page("9101002", "07/02/26", "222.00"),
        _prime_line_page("9101003", "07/02/26", "333.00"),
        _prime_line_page("9101004", "07/02/26", "444.00"),
    ]
    client = _client()
    filename = "manual_primeline_batch.pdf"
    response = _upload_with_fake_pages(client, pages, filename)
    result.check("upload of a 4-invoice batch succeeds", response.status_code == 200)

    documents = _documents_matching_filename(filename)
    result.check("exactly 4 PurchaseDocuments were created for the manually-uploaded 4-invoice batch", len(documents) == 4)
    result.check(
        "each resulting document's source_reference carries its own page-range suffix",
        all("#p" in (d.source_reference or "") for d in documents),
    )
    result.check(
        "each resulting document kept its own real invoice number",
        {d.document_number for d in documents} == {"9101001", "9101002", "9101003", "9101004"},
    )


def test_manual_upload_keith_batch_creates_2_documents_multipage_merged(result: Result) -> None:
    """Task §2/§9 test 2: a manually uploaded 3-page file bundling 2 real
    Ben E. Keith invoices (one of them spanning 2 pages) produces exactly 2
    PurchaseDocuments -- the multi-page invoice correctly merged into ONE
    document, never split by page."""

    pages = [
        _keith_page("9201001", 1, total_line="Total Invoice 170.12\n"),
        _keith_page("9201002", 1),
        _keith_page("9201002", 2, total_line="New Total 340.24\n"),
    ]
    client = _client()
    filename = "manual_keith_batch.pdf"
    response = _upload_with_fake_pages(client, pages, filename)
    result.check("upload of a 2-invoice/3-page batch succeeds", response.status_code == 200)

    documents = _documents_matching_filename(filename)
    result.check("exactly 2 PurchaseDocuments for 3 pages, 2 real invoices (no false split)", len(documents) == 2)
    multi_page_doc = next((d for d in documents if d.document_number == "9201002"), None)
    result.check(
        "the multi-page invoice's page_range correctly spans both its pages (p2-3), correctly merged",
        multi_page_doc is not None and (multi_page_doc.source_reference or "").endswith("#p2-3"),
    )


def test_manual_upload_ambiguous_split_stays_single_human_document(result: Result) -> None:
    """Task §2, "Se split incerto -> HUMAN, nessun confine inventato": a
    manually uploaded multi-page file with no real boundary evidence (no
    page ever shows a document_number) is never force-split --
    `invoice_splitter`'s own Uncertainty rule keeps it as ONE document,
    which then correctly lands HUMAN like any document with an
    unrecognized supplier/number (§9 test 4)."""

    pages = [
        "some invoice text with no recognizable number\nTOTAL $ 50.00\n",
        "more text, still no number anywhere\nsecond page\n",
    ]
    client = _client()
    filename = "manual_ambiguous_batch.pdf"
    response = _upload_with_fake_pages(client, pages, filename)
    result.check("upload of an ambiguous batch succeeds (never errors, never invents a boundary)", response.status_code == 200)

    documents = _documents_matching_filename(filename)
    result.check("no boundary evidence at all -> exactly ONE PurchaseDocument, never guessed as split", len(documents) == 1)
    if documents:
        session = _open_session(purchased_bridge.get_database_url())
        try:
            status = repo.get_document_functional_status(session, documents[0].id)
            result.check("the single un-splittable document lands HUMAN (no recognizable supplier)", status == "HUMAN")
        finally:
            session.close()


# ---------------------------------------------------------------------------
# "Close Purchased Human Review Reliability Gaps" -- add missing Purchase
# Line (task tests 5, 6, 7, 8, 9, 10, 15)
# ---------------------------------------------------------------------------


def test_add_missing_line_creates_visible_line_original_unchanged(result: Result) -> None:
    """Task §3/§4, tests 5/6/7/8: adds a Purchase Line the original
    extraction never created; the original line stays exactly as it was;
    the new line appears in the Effective Purchased View AND in
    `get_purchased_lines_with_allocation()` (the Restaurant/Purchasing
    consumer read), clearly flagged as human-added, never indistinguishable
    from source evidence."""

    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, document_number="HR-ADDLINE-1"),
        [{"description": "Tomatoes", "quantity": "3", "unit": "case", "unit_price": "100.00", "line_amount": "100.00", "line_type": "PRODUCT"}],
        "hr-addline.pdf",
    )
    before = human_review.get_review_detail(document_id)
    result.check("document starts with exactly the one originally-parsed line", len(before["lines"]) == 1)

    outcome = human_review.add_missing_line(
        document_id,
        added_by="alice",
        line_type="PRODUCT",
        description="Mozzarella di Bufala (missed by OCR)",
        normalized_item="Mozzarella",
        quantity="2",
        unit_of_measure="case",
        unit_price="50.00",
        line_amount="100.00",
    )
    result.check("add_missing_line reports created=True the first time", outcome["created"] is True)

    after = human_review.get_review_detail(document_id)
    result.check("the document now has 2 lines (original + added)", len(after["lines"]) == 2)
    original_line = next(l for l in after["lines"] if l["effective"]["description"] == "Tomatoes")
    added_line = next(l for l in after["lines"] if l["id"] == outcome["purchase_line_id"])

    result.check("the ORIGINAL line is untouched (original extraction unchanged)", original_line["effective"]["quantity"] == "3.0000")
    result.check("the original line is NOT flagged human_added (it IS source evidence)", original_line["human_added"] is False)
    result.check("the ADDED line is flagged human_added in the Effective Purchased View", added_line["human_added"] is True)
    result.check(
        "the added line's normalized_item correction is visible in the Effective View",
        added_line["effective"]["normalized_item"] == "Mozzarella",
    )
    result.check(
        "the added line is visible to the Restaurant/Purchasing consumer (get_purchased_lines_with_allocation), flagged human_added",
        added_line["allocation"] is not None and added_line["allocation"]["human_added"] is True,
    )

    session = _open_session(purchased_bridge.get_database_url())
    try:
        raw_added_line = session.get(m.PurchaseLine, outcome["purchase_line_id"])
        result.check(
            "the added line's own raw column holds exactly what the reviewer typed (its own source evidence)",
            raw_added_line.raw_description == "Mozzarella di Bufala (missed by OCR)" and raw_added_line.source_amount_minor == 10000,
        )
    finally:
        session.close()


def test_added_line_participates_in_non_goods_allocation(result: Result) -> None:
    """Task §5, test 9: a manually added line participates in the SAME
    non-goods allocation formula as any other line -- no duplicated
    formula, no special-casing."""

    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, document_number="HR-ADDLINE-ALLOC"),
        [{"description": "Goods A", "quantity": "1", "unit": "case", "unit_price": "100.00", "line_amount": "100.00", "line_type": "PRODUCT"}],
        "hr-addline-alloc.pdf",
    )
    added_goods_b = human_review.add_missing_line(
        document_id, added_by="alice", line_type="PRODUCT", description="Goods B (missed by OCR)",
        quantity="1", unit_of_measure="case", unit_price="300.00", line_amount="300.00",
    )
    added_delivery = human_review.add_missing_line(
        document_id, added_by="alice", line_type="SURCHARGE", description="Delivery Fee (missed by OCR)", line_amount="40.00",
    )

    view = human_review.get_review_detail(document_id)
    by_id = {l["id"]: l for l in view["lines"]}
    goods_a = next(l for l in view["lines"] if l["effective"]["description"] == "Goods A")
    goods_b = by_id[added_goods_b["purchase_line_id"]]

    result.check(
        "the added SURCHARGE line itself carries no allocation (only PRODUCT lines do -- same as original lines)",
        by_id[added_delivery["purchase_line_id"]]["allocation"] is None,
    )
    result.check(
        "the added PRODUCT line's allocation reflects the added SURCHARGE amount (A=100,B=300,Delivery=40 -> A=10.00,B=30.00)",
        goods_a["allocation"]["allocated_non_goods_minor"] == 1000 and goods_b["allocation"]["allocated_non_goods_minor"] == 3000,
    )
    result.check(
        "allocated shares still sum exactly to the non-goods total with an added line in the mix",
        goods_a["allocation"]["allocated_non_goods_minor"] + goods_b["allocation"]["allocated_non_goods_minor"] == 4000,
    )


def test_add_line_audit_records_reviewer_and_timestamp(result: Result) -> None:
    """Task §3, test 10: "Preserva audit: reviewer, timestamp, action =
    ADD_LINE, source document, valori inseriti" -- every addition is
    traceable back to who did it and when."""

    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, document_number="HR-ADDLINE-AUDIT"), [], "hr-addline-audit.pdf"
    )
    human_review.add_missing_line(document_id, added_by="alice", description="Missed Item", line_amount="10.00")

    view = human_review.get_review_detail(document_id)
    result.check("exactly one ADD_LINE audit record exists", len(view["line_additions"]) == 1)
    addition = view["line_additions"][0]
    result.check("the audit record names the reviewer (action = ADD_LINE is this table's own existence)", addition.added_by == "alice")
    result.check("the audit record has a timestamp", addition.added_at is not None)
    result.check(
        "the audit record references the new line, on this same source document",
        addition.purchase_line_id == view["lines"][0]["id"] and addition.purchase_document_id == document_id,
    )


def test_add_missing_line_no_duplicate_on_repeated_submit(result: Result) -> None:
    """Task §9, test 15: "no duplicate lines on repeated submit" -- e.g. a
    reviewer's browser double-submitting the same Add Line form must not
    create two lines."""

    document_id = purchased_bridge.save_purchase_document(
        dict(_COMPLETE_HEADER, document_number="HR-ADDLINE-DUP"), [], "hr-addline-dup.pdf"
    )
    first = human_review.add_missing_line(document_id, added_by="alice", description="Repeated Item", line_amount="25.00")
    second = human_review.add_missing_line(document_id, added_by="alice", description="Repeated Item", line_amount="25.00")

    result.check("the first submission creates a new line", first["created"] is True)
    result.check("a second, identical submission does not create a duplicate", second["created"] is False)
    result.check("both calls resolve to the SAME purchase_line_id", first["purchase_line_id"] == second["purchase_line_id"])
    view = human_review.get_review_detail(document_id)
    result.check("the document still has exactly one line after the repeated submit", len(view["lines"]) == 1)


def test_add_line_route_requires_correct_permission(result: Result) -> None:
    """Adding a missing line is gated behind the same ACTION_CORRECT
    permission as any other field correction."""

    document_id = _make_human_document(source_file="hr-addline-route.pdf", document_number="HR-ADDLINE-ROUTE")
    client = _client()
    _login(client, review_authority.ROLE_VIEWER)
    response = client.post(f"/review/{document_id}/line/add", data={"description": "New Item", "line_amount": "10.00"})
    result.check("a VIEWER cannot add a missing line (403)", response.status_code == 403)

    _login(client, review_authority.ROLE_REVIEWER)
    response = client.post(f"/review/{document_id}/line/add", data={"description": "New Item", "line_amount": "10.00"})
    result.check("a REVIEWER can add a missing line", response.status_code in (200, 302))
    view = human_review.get_review_detail(document_id)
    result.check("the line was actually added via the real route", any(l["effective"]["description"] == "New Item" for l in view["lines"]))


# ---------------------------------------------------------------------------
# "Close Purchased Human Review Reliability Gaps" -- AMBIGUOUS/UNREAD are
# blocking, INCORRECT requires a value (task tests 11, 12, 13, 14; §7)
# ---------------------------------------------------------------------------


def test_ambiguous_raw_value_does_not_satisfy_validation(result: Result) -> None:
    """Task §6, test 11 -- the exact real bug found on a Ben E. Keith
    invoice during Operator Review Testing: a required field (total_amount)
    already has a present, parseable raw value (so
    `_validate_extracted_fields()` alone would accept it), but a reviewer
    has marked it AMBIGUOUS with no corrected_value -- the document must
    stay HUMAN, never silently pass just because the untouched raw value
    "looks" fine."""

    document_id = _make_human_document(source_file="hr-ambiguous-total.pdf", document_number="HR-AMBIGUOUS-TOTAL")
    # Resolve the ACTUAL blocker (missing issue_date) so total_amount's own
    # AMBIGUOUS marker is the only thing left that could still block.
    human_review.submit_field_review(
        document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026"
    )
    human_review.submit_field_review(document_id, field_name="total_amount", classification="AMBIGUOUS", reviewed_by="alice")

    result_dict = human_review.complete_review(document_id, reviewed_by="alice")
    result.check(
        "an AMBIGUOUS required field with no correction keeps the document HUMAN, even though the raw value is present",
        result_dict["functional_status"] == "HUMAN",
    )
    result.check(
        "the reasons explain WHY (not just a generic 'not recognized')",
        any("total_amount" in r and "AMBIGUOUS" in r for r in result_dict["reasons"]),
    )
    session = _open_session(purchased_bridge.get_database_url())
    try:
        result.check(
            "repository-level status also reads HUMAN for every consumer (a new WARNING entry was opened)",
            repo.get_document_functional_status(session, document_id) == "HUMAN",
        )
    finally:
        session.close()


def test_ambiguous_corrected_resolves_to_normalized(result: Result) -> None:
    """Task §6, test 12: once the AMBIGUOUS field is corrected with a real
    value, the document can become NORMALIZED again -- AMBIGUOUS is
    blocking, not permanent."""

    document_id = _make_human_document(source_file="hr-ambiguous-resolved.pdf", document_number="HR-AMBIGUOUS-RESOLVED")
    human_review.submit_field_review(
        document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026"
    )
    human_review.submit_field_review(document_id, field_name="total_amount", classification="AMBIGUOUS", reviewed_by="alice")
    still_human = human_review.complete_review(document_id, reviewed_by="alice")
    result.check("still HUMAN before the AMBIGUOUS field is resolved", still_human["functional_status"] == "HUMAN")

    human_review.submit_field_review(
        document_id, field_name="total_amount", classification="INCORRECT", reviewed_by="alice", corrected_value="440.00"
    )
    resolved = human_review.complete_review(document_id, reviewed_by="alice")
    result.check("resolving the AMBIGUOUS field with a real value allows NORMALIZED", resolved["functional_status"] == "NORMALIZED")


def test_unread_blocking_behavior(result: Result) -> None:
    """Task §6/§7, test 13: UNREAD behaves exactly like AMBIGUOUS -- blocks
    while unresolved, resolves once corrected."""

    document_id = _make_human_document(source_file="hr-unread.pdf", document_number="HR-UNREAD")
    human_review.submit_field_review(document_id, field_name="issue_date", classification="UNREAD", reviewed_by="alice")
    human_review.submit_field_review(
        document_id, field_name="total_amount", classification="INCORRECT", reviewed_by="alice", corrected_value="440.00"
    )
    still_human = human_review.complete_review(document_id, reviewed_by="alice")
    result.check(
        "UNREAD issue_date (no corrected_value) keeps the document HUMAN even though total_amount was fixed",
        still_human["functional_status"] == "HUMAN",
    )

    human_review.submit_field_review(
        document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice", corrected_value="01/15/2026"
    )
    resolved = human_review.complete_review(document_id, reviewed_by="alice")
    result.check("resolving the UNREAD field allows NORMALIZED", resolved["functional_status"] == "NORMALIZED")


def test_incorrect_requires_corrected_value(result: Result) -> None:
    """Task §7, Field Review Semantics: "INCORRECT -> richiede corrected
    value" -- unlike AMBIGUOUS/UNREAD (which may legitimately stay
    unresolved), asserting INCORRECT without saying what the right value
    IS is a malformed review action, rejected outright."""

    document_id = _make_human_document(source_file="hr-incorrect-no-value.pdf", document_number="HR-INCORRECT-NOVALUE")
    raised = False
    try:
        human_review.submit_field_review(document_id, field_name="issue_date", classification="INCORRECT", reviewed_by="alice")
    except ValueError:
        raised = True
    result.check("INCORRECT without a corrected_value is rejected", raised)

    client = _client()
    _login(client, review_authority.ROLE_REVIEWER)
    response = client.post(f"/review/{document_id}/field", data={"field_name": "issue_date", "classification": "INCORRECT"})
    result.check("the Flask route surfaces this as a redirect+error, never a 500", response.status_code in (302, 303))


def main() -> int:
    url = create_disposable_test_database_url("human_review")
    os.environ["RFONE_DATABASE_URL"] = url
    tmp_dir = tempfile.mkdtemp(prefix="human_review_training_isolation_")
    os.environ["SUPPLIER_FORMAT_TRAINING_DB_PATH"] = os.path.join(tmp_dir, "isolated_training.db")

    result = Result()
    try:
        for test_fn in (
            test_queue_lists_only_human_documents,
            test_prime_line_batch_four_review_records,
            test_keith_batch_two_review_records_multi_page,
            test_page_provenance_correct,
            test_field_correction_persists_and_preserves_original,
            test_correct_confirmation_after_prior_correction_does_not_revert,
            test_queue_shows_effective_header_values_not_raw,
            test_no_duplicate_merge_logic,
            test_incomplete_review_remains_human,
            test_complete_review_normalizes,
            test_training_store_updated_automatically,
            test_consecutive_correct_count_updated,
            test_eligible_after_configured_threshold_and_validate_flow,
            test_validate_format_denied_before_eligibility,
            test_degraded_format_visible,
            test_supplier_alias_preserved_no_duplicate,
            test_costco_direct_channel_preserved,
            test_source_file_access_protected,
            test_unauthorized_correction_rejected,
            test_unauthorized_format_validation_rejected,
            test_authorized_actions_succeed,
            test_no_bank_reconciliation_logic,
            test_manual_upload_uses_shared_split_no_duplicate_logic,
            test_manual_upload_prime_line_batch_creates_4_documents,
            test_manual_upload_keith_batch_creates_2_documents_multipage_merged,
            test_manual_upload_ambiguous_split_stays_single_human_document,
            test_add_missing_line_creates_visible_line_original_unchanged,
            test_added_line_participates_in_non_goods_allocation,
            test_add_line_audit_records_reviewer_and_timestamp,
            test_add_missing_line_no_duplicate_on_repeated_submit,
            test_add_line_route_requires_correct_permission,
            test_ambiguous_raw_value_does_not_satisfy_validation,
            test_ambiguous_corrected_resolves_to_normalized,
            test_unread_blocking_behavior,
            test_incorrect_requires_corrected_value,
        ):
            test_fn(result)
    finally:
        os.environ.pop("RFONE_DATABASE_URL", None)
        os.environ.pop("SUPPLIER_FORMAT_TRAINING_DB_PATH", None)
        cleanup_disposable_test_database_url(url)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Human Review tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Human Review tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
