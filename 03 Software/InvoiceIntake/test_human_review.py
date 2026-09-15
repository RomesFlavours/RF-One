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
