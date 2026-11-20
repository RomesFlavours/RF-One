#!/usr/bin/env python
"""Invoice evidence for Bank Assessment —
BANK_INVOICE_EVIDENCE_COLLABORATION_001.

Proves, on a throwaway database, that invoices are EVIDENCE and Bank
Assessment remains the accounting control point:

* Bank <-> Invoice matching that is genuinely many-to-many, with amounts,
  with both over-allocation controls, and with ambiguity reported rather
  than guessed;
* a MULTI_CATEGORY_CAPABLE counterparty whose invoice must be read before
  its transaction can be classified — and whose missing invoice leaves the
  movement financially reconciled but accounting pending;
* supplier item learning after exactly two consistent confirmations, with
  contradictions preserved instead of overwritten;
* ancillary costs apportioned by Purchasing's own existing implementation;
* FOR WHOM taken from document evidence or from the operator, and never
  from the payer;
* a month that is fully reconciled financially and still accounting
  incomplete.

Never touches AWS, RDS, the operational database, or a real bank file. No
historical data is imported.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import card_configuration
from rfone_data_store.bank_reconciliation import economic_allocation as alloc
from rfone_data_store.bank_reconciliation import economic_reporting as reporting
from rfone_data_store.bank_reconciliation import invoice_allocation_bridge as bridge
from rfone_data_store.bank_reconciliation import invoice_evidence as evidence
from rfone_data_store.bank_reconciliation import invoice_matching as matching
from rfone_data_store.bank_reconciliation import reporting_entity as entities
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store.purchasing import repository as purchasing

POSTING_DATE = date(2026, 3, 15)
PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def raises(description: str, fn, fragment: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — the point is that something refused
            check(description, fragment.lower() in str(exc).lower(), detail=str(exc))
        else:
            check(description, False, detail="nothing was raised")

    url = resolve_test_database_url("bank_invoice_evidence")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            fx = _build_fixture(s, check)

            _test_matching(s, fx, check, raises)
            _test_multi_category(s, fx, check, raises)
            _test_item_learning(s, fx, check)
            _test_ancillary(s, fx, check)
            _test_economic_owner(s, fx, check)
            _test_period_completeness(s, fx, check)

            s.rollback()
    finally:
        engine.dispose()

    print()
    print(f"Checks passed: {len(passed)}")
    print(f"Checks failed: {len(failed)}")
    if failed:
        print()
        for description in failed:
            print(f"  FAILED  {description}")
        return 1
    for description in passed:
        print(f"  ok  {description}")
    return 0


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


class Fixture:
    pass


def _build_fixture(s, check) -> Fixture:
    fx = Fixture()

    fx.restaurant = m.Restaurant(name="Test Restaurant")
    s.add(fx.restaurant)
    s.flush()

    fx.wp = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
    fx.md = m.LegalEntity(legal_name="RF Mount Dora, LLC", status="ACTIVE")
    fx.gelati = m.LegalEntity(legal_name="RF Gelati, LLC", status="ACTIVE")
    s.add_all([fx.wp, fx.md, fx.gelati])
    s.flush()
    fx.legal_entity_count = s.scalar(select(func.count(m.LegalEntity.id)))

    fx.bank_wp = m.PaymentInstrument(
        instrument_type="BANK_ACCOUNT", display_name="WP Checking",
        legal_entity_id=fx.wp.id, status="ACTIVE",
    )
    fx.bank_gelati = m.PaymentInstrument(
        instrument_type="BANK_ACCOUNT", display_name="Gelati Checking",
        legal_entity_id=fx.gelati.id, status="ACTIVE",
    )
    fx.bank_personal = m.PaymentInstrument(
        instrument_type="BANK_ACCOUNT", display_name="Owner Personal Checking",
        legal_entity_id=None, status="ACTIVE",
    )
    s.add_all([fx.bank_wp, fx.bank_gelati, fx.bank_personal])
    s.flush()

    fx.card_personal = m.PaymentInstrument(
        instrument_type="CREDIT_CARD", display_name="Personal Card",
        legal_entity_id=None, last_four="2222", status="ACTIVE",
    )
    s.add(fx.card_personal)
    s.flush()
    card_configuration.assign_settlement_account(
        s, credit_card_payment_instrument_id=fx.card_personal.id,
        settlement_bank_account_id=fx.bank_personal.id, valid_from=date(2026, 1, 1),
    )

    # The canonical catalog and WHY vocabulary arrive with the migrations.
    fx.why_food = _why(s, "FOOD_PURCHASES")
    fx.why_togo = _why(s, "TO_GO_PACKAGING")
    fx.why_supplies = _why(s, "RESTAURANT_OPERATING_SUPPLIES")
    fx.why_office = _why(s, "OFFICE_SUPPLIES")

    fx.group = entities.create_reporting_group(s, code="RF_GROUP", name="RF Perimeter")
    fx.re_wp = entities.create_legal_entity_reporting_entity(
        s, code="RE_WP", name="RF Winter Park", legal_entity_id=fx.wp.id,
        reporting_group_id=fx.group.id,
    )
    fx.re_md = entities.create_legal_entity_reporting_entity(
        s, code="RE_MD", name="RF Mount Dora", legal_entity_id=fx.md.id,
        reporting_group_id=fx.group.id,
    )
    fx.re_gelati = entities.create_legal_entity_reporting_entity(
        s, code="RE_GELATI", name="RF Gelati", legal_entity_id=fx.gelati.id,
        reporting_group_id=fx.group.id,
    )

    supplier_type = s.scalar(select(m.BankOccurrenceType).limit(1))
    if supplier_type is None:
        supplier_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier", status="ACTIVE")
        s.add(supplier_type)
        s.flush()
    fx.occurrence_type = supplier_type

    fx.who_cheney = _occurrence(s, "Cheney Brothers", supplier_type.id)
    fx.who_gordon = _occurrence(s, "Gordon Food Service", supplier_type.id)
    fx.who_amazon = _occurrence(s, "Amazon", supplier_type.id)
    fx.who_unknown = _occurrence(s, "New Vendor", supplier_type.id)

    fx.sup_cheney = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Cheney Brothers")
    fx.sup_gordon = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Gordon Food Service")
    fx.sup_amazon = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Amazon")
    fx.sup_other = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Other Distributor")
    fx.sup_new = purchasing.get_or_create_supplier(s, fx.restaurant.id, "New Vendor")

    for occurrence, supplier in (
        (fx.who_cheney, fx.sup_cheney),
        (fx.who_gordon, fx.sup_gordon),
        (fx.who_amazon, fx.sup_amazon),
        (fx.who_unknown, fx.sup_new),
    ):
        evidence.link_occurrence_supplier(
            s, occurrence_id=occurrence.id, supplier_id=supplier.id,
        )

    evidence.set_who_capability(
        s, occurrence_id=fx.who_cheney.id, capability=m.WHO_MULTI_CATEGORY_CAPABLE,
        evidence="Operator: Cheney invoices carry food, packaging, cleaning and services.",
    )
    evidence.set_who_capability(
        s, occurrence_id=fx.who_gordon.id, capability=m.WHO_SINGLE_CATEGORY,
        evidence="Operator: this distributor only ever invoices food.",
    )
    evidence.set_who_capability(
        s, occurrence_id=fx.who_amazon.id, capability=m.WHO_MULTI_CATEGORY_CAPABLE,
        evidence="Operator: one Amazon order mixes toner, pans and shelving.",
    )

    check(
        "a counterparty starts UNKNOWN rather than being assumed single-category",
        fx.who_unknown.category_capability == m.WHO_CATEGORY_UNKNOWN,
    )
    check(
        "MULTI_CATEGORY_CAPABLE is what makes invoice examination mandatory",
        fx.who_cheney.requires_invoice_line_examination
        and not fx.who_gordon.requires_invoice_line_examination
        and not fx.who_unknown.requires_invoice_line_examination,
    )
    return fx


def _why(s, code: str) -> "m.BankTransactionReason":
    row = s.scalar(select(m.BankTransactionReason).where(m.BankTransactionReason.code == code))
    if row is None:
        raise AssertionError(f"Canonical WHY {code} is missing from the seeded vocabulary.")
    return row


def _occurrence(s, name: str, type_id: int) -> "m.BankOccurrence":
    row = m.BankOccurrence(canonical_name=name, occurrence_type_id=type_id, status="ACTIVE")
    s.add(row)
    s.flush()
    return row


def _transaction(
    s, instrument, amount_minor: int, description: str,
    occurrence=None, reference: str | None = None, posting: date | None = None,
) -> "m.FinancialTransaction":
    """A bank movement in the canonical sign convention — money out
    negative — optionally carrying a current WHO decision."""
    transaction = m.FinancialTransaction(
        payment_instrument_id=instrument.id,
        posting_date=posting or POSTING_DATE,
        transaction_date=posting or POSTING_DATE,
        description_original=description,
        reference=reference,
        amount_minor=amount_minor,
        status="COMPLETED",
        classification="UNKNOWN",
        accounting_status="CANONICAL",
    )
    s.add(transaction)
    s.flush()
    if occurrence is not None:
        explanation = m.BankTransactionExplanation(
            financial_transaction_id=transaction.id,
            occurrence_id=occurrence.id,
            decision_source="HUMAN",
            decision_status="HUMAN_CONFIRMED",
            occurrence_name_snapshot=occurrence.canonical_name,
        )
        s.add(explanation)
        s.flush()
        transaction.explanation_id = explanation.id
        s.flush()
    return transaction


def _document(
    s, supplier, *, number: str, total_minor: int | None, lines: list[dict],
    destination: str | None = None, issue: date | None = None,
) -> "m.PurchaseDocument":
    return purchasing.record_purchase_document(
        s,
        supplier_id=supplier.id,
        header={
            "document_number": number,
            "document_type": "Invoice",
            "issue_date": datetime.combine(issue or POSTING_DATE, datetime.min.time()),
            "total_amount_minor": total_minor,
            "destination_location": destination,
            "currency": "USD",
        },
        lines=lines,
    )


def _product(description: str, amount: int, code: str | None = None, number: int = 1) -> dict:
    line = {
        "line_type": "PRODUCT",
        "raw_description": description,
        "source_amount_minor": amount,
        "source_line_number": number,
    }
    if code is not None:
        line["supplier_item_code"] = code
    return line


# ---------------------------------------------------------------------------
# §25 — Bank <-> Invoice matching
# ---------------------------------------------------------------------------


def _test_matching(s, fx, check, raises) -> None:
    # [1] one Bank -> one Invoice, exact
    txn1 = _transaction(s, fx.bank_wp, -100_000, "GORDON FOOD", occurrence=fx.who_gordon)
    doc1 = _document(
        s, fx.sup_gordon, number="G-1001", total_minor=100_000,
        lines=[_product("CASE CHICKEN", 100_000, code="CHK-1")],
    )
    written = matching.auto_match(s, financial_transaction_id=txn1.id)
    check(
        "[1] one bank payment matches one invoice exactly, automatically",
        len(written) == 1
        and written[0].purchase_document_id == doc1.id
        and written[0].matched_amount_minor == -100_000
        and written[0].is_confirmed,
        detail=str(written),
    )
    check(
        "[1] the exact match records that nothing differs",
        written[0].difference_kind == m.DIFFERENCE_NONE and not written[0].difference_minor,
    )

    # [2] one Bank -> two Invoices
    txn2 = _transaction(s, fx.bank_wp, -30_000, "GORDON FOOD COMBINED", occurrence=fx.who_gordon)
    doc_a = _document(
        s, fx.sup_gordon, number="G-1002", total_minor=10_000,
        lines=[_product("PRODUCE", 10_000, code="PRD-1")],
    )
    doc_b = _document(
        s, fx.sup_gordon, number="G-1003", total_minor=20_000,
        lines=[_product("DAIRY", 20_000, code="DRY-1")],
    )
    combo = matching.auto_match(s, financial_transaction_id=txn2.id)
    check(
        "[2] one payment settling two invoices is matched as a combination",
        len(combo) == 2
        and {mm.purchase_document_id for mm in combo} == {doc_a.id, doc_b.id}
        and sum(mm.matched_amount_minor for mm in combo) == -30_000,
        detail=str([(mm.purchase_document_id, mm.matched_amount_minor) for mm in combo]),
    )

    # [3] two Bank payments -> one Invoice, [4] partial payment
    doc_big = _document(
        s, fx.sup_gordon, number="G-2001", total_minor=50_000,
        lines=[_product("BULK ORDER", 50_000, code="BLK-1")],
    )
    txn3a = _transaction(s, fx.bank_wp, -30_000, "GORDON PART 1", occurrence=fx.who_gordon)
    txn3b = _transaction(s, fx.bank_wp, -20_000, "GORDON PART 2", occurrence=fx.who_gordon)
    first = matching.create_match(
        s, financial_transaction_id=txn3a.id, purchase_document_id=doc_big.id,
        matched_amount_minor=-30_000, difference_kind=m.DIFFERENCE_PARTIAL_PAYMENT,
    )
    check(
        "[4] a partial payment is matched for what it actually paid",
        first.matched_amount_minor == -30_000
        and first.difference_kind == m.DIFFERENCE_PARTIAL_PAYMENT,
    )
    check(
        "[8] an invoice's already-matched amount is not available again",
        matching.document_remaining_minor(s, purchase_document_id=doc_big.id) == 20_000,
    )
    second = matching.create_match(
        s, financial_transaction_id=txn3b.id, purchase_document_id=doc_big.id,
        matched_amount_minor=-20_000,
    )
    check(
        "[3] two bank payments settle one invoice between them",
        second.is_confirmed
        and matching.document_remaining_minor(s, purchase_document_id=doc_big.id) == 0
        and matching.matched_total_for_document(s, purchase_document_id=doc_big.id) == 50_000,
    )

    # [9] over-allocation rejected, on both sides
    txn_over = _transaction(s, fx.bank_wp, -10_000, "GORDON OVER", occurrence=fx.who_gordon)
    doc_small = _document(
        s, fx.sup_gordon, number="G-2002", total_minor=5_000,
        lines=[_product("SMALL", 5_000, code="SML-1")],
    )
    raises(
        "[9] matching more than the invoice is payable for is refused",
        lambda: matching.create_match(
            s, financial_transaction_id=txn_over.id, purchase_document_id=doc_small.id,
            matched_amount_minor=-9_000,
        ),
        "payable amount",
    )
    doc_huge = _document(
        s, fx.sup_gordon, number="G-2003", total_minor=99_000,
        lines=[_product("HUGE", 99_000, code="HUG-1")],
    )
    raises(
        "[9] matching more than the transaction is worth is refused",
        lambda: matching.create_match(
            s, financial_transaction_id=txn_over.id, purchase_document_id=doc_huge.id,
            matched_amount_minor=-99_000,
        ),
        "more than the",
    )
    check(
        "[9] a refused match left both sides untouched",
        matching.matched_total_for_transaction(s, financial_transaction_id=txn_over.id) == 0
        and matching.document_remaining_minor(s, purchase_document_id=doc_small.id) == 5_000,
    )

    # [8] a fully matched invoice cannot be matched again
    txn_again = _transaction(s, fx.bank_wp, -50_000, "GORDON AGAIN", occurrence=fx.who_gordon)
    raises(
        "[8] a fully paid invoice cannot absorb another payment",
        lambda: matching.create_match(
            s, financial_transaction_id=txn_again.id, purchase_document_id=doc_big.id,
            matched_amount_minor=-50_000,
        ),
        "payable amount",
    )

    # [6] explainable ancillary difference
    txn_tax = _transaction(s, fx.bank_wp, -11_000, "GORDON PLUS TAX", occurrence=fx.who_gordon)
    doc_tax = _document(
        s, fx.sup_gordon, number="G-3001", total_minor=10_000,
        lines=[_product("GOODS", 10_000, code="GDS-1")],
    )
    tax_match = matching.create_match(
        s, financial_transaction_id=txn_tax.id, purchase_document_id=doc_tax.id,
        matched_amount_minor=-10_000, difference_kind=m.DIFFERENCE_NONE,
    )
    difference = matching.unmatched_difference(s, financial_transaction_id=txn_tax.id)
    check(
        "[6] a payment larger than its invoice leaves a stated difference",
        difference.remaining_minor == -1_000 and not difference.is_fully_matched,
        detail=str(difference),
    )
    check(
        "[10] the unresolved difference is reported in words, not absorbed",
        "not accounted for" in difference.explanation and tax_match.is_confirmed,
    )

    # [7] ambiguous equal-total candidates are never auto-matched
    txn_amb = _transaction(s, fx.bank_wp, -25_000, "AMBIGUOUS", occurrence=fx.who_unknown)
    _document(
        s, fx.sup_new, number="N-1", total_minor=25_000,
        lines=[_product("THING A", 25_000, code="A-1")],
    )
    _document(
        s, fx.sup_new, number="N-2", total_minor=25_000,
        lines=[_product("THING B", 25_000, code="B-1")],
    )
    report = matching.generate_candidates(s, financial_transaction_id=txn_amb.id)
    check(
        "[7] two invoices matching the same payment are reported as ambiguous",
        report.ambiguity_note is not None and report.auto_confirmable is None,
        detail=str(report.ambiguity_note),
    )
    check(
        "[7] an ambiguous report writes no match at all",
        matching.auto_match(s, financial_transaction_id=txn_amb.id) == []
        and matching.propose_candidates(s, financial_transaction_id=txn_amb.id) == []
        and matching.matched_total_for_transaction(
            s, financial_transaction_id=txn_amb.id
        ) == 0,
    )

    # [5] combination candidate generation is deterministic
    check(
        "[5] combination matching is available and deterministic",
        all(
            matching.generate_candidates(
                s, financial_transaction_id=txn_amb.id
            ).ambiguity_note
            == report.ambiguity_note
            for _ in range(3)
        ),
    )

    fx.txn_gordon_exact = txn1
    fx.doc_gordon_exact = doc1


# ---------------------------------------------------------------------------
# §26 — multi-category enforcement
# ---------------------------------------------------------------------------


def _test_multi_category(s, fx, check, raises) -> None:
    # [11] a SINGLE_CATEGORY counterparty needs no invoice decomposition
    requirement = bridge.evidence_requirement(
        s, financial_transaction_id=fx.txn_gordon_exact.id
    )
    check(
        "[11] a SINGLE_CATEGORY counterparty does not require invoice examination",
        not requirement.requires_invoice and requirement.may_complete,
    )
    single = alloc.set_allocations(
        s,
        financial_transaction_id=fx.txn_gordon_exact.id,
        specs=[
            alloc.AllocationSpec(
                amount_minor=-100_000, reporting_entity_id=fx.re_wp.id,
                transaction_reason_id=fx.why_food.id,
            )
        ],
    )
    check("[11] a SINGLE_CATEGORY counterparty produces one allocation", len(single) == 1)

    # [14] MULTI_CATEGORY_CAPABLE with no invoice -> PENDING_EVIDENCE
    txn_no_doc = _transaction(s, fx.bank_wp, -200_000, "CHENEY NO INVOICE", occurrence=fx.who_cheney)
    requirement = bridge.evidence_requirement(s, financial_transaction_id=txn_no_doc.id)
    check(
        "[14] a multi-category counterparty with no invoice is blocked from completion",
        requirement.requires_invoice
        and not requirement.may_complete
        and requirement.blocking_reason is not None,
        detail=str(requirement.blocking_reason),
    )
    pending = bridge.mark_pending_evidence(s, financial_transaction_id=txn_no_doc.id)
    check(
        "[14] the movement is recorded as PENDING_EVIDENCE, not guessed",
        len(pending) == 1
        and pending[0].status == alloc.PENDING_EVIDENCE
        and pending[0].amount_minor == -200_000,
    )
    # [15] no guessed WHY
    check(
        "[15] no WHY is invented when the required invoice is absent",
        pending[0].transaction_reason_id is None
        and pending[0].accounting_classification_code_snapshot is None
        and pending[0].reporting_entity_id is None,
    )
    check(
        "[15] the counterparty's usual meaning is explicitly not used as evidence",
        "not evidence" in (requirement.blocking_reason or ""),
    )
    raises(
        "[15] applying invoice evidence is refused while the document is missing",
        lambda: bridge.apply_invoice_evidence(s, financial_transaction_id=txn_no_doc.id),
        "PENDING_EVIDENCE",
    )
    # [48] the financial fact survives untouched
    check(
        "[48] a missing invoice does not make the financial transaction disappear",
        s.get(m.FinancialTransaction, txn_no_doc.id) is not None
        and s.get(m.FinancialTransaction, txn_no_doc.id).accounting_status == "CANONICAL"
        and s.get(m.FinancialTransaction, txn_no_doc.id).amount_minor == -200_000,
    )
    fx.txn_pending = txn_no_doc

    # [12] MULTI_CATEGORY_CAPABLE + single-category invoice -> ONE allocation
    txn_one_cat = _transaction(s, fx.bank_wp, -80_000, "CHENEY ALL FOOD", occurrence=fx.who_cheney)
    doc_one_cat = _document(
        s, fx.sup_cheney, number="C-100", total_minor=80_000,
        destination="RF Winter Park",
        lines=[
            _product("CHICKEN", 50_000, code="C-CHK", number=1),
            _product("BEEF", 30_000, code="C-BEF", number=2),
        ],
    )
    matching.create_match(
        s, financial_transaction_id=txn_one_cat.id, purchase_document_id=doc_one_cat.id,
        matched_amount_minor=-80_000,
    )
    for line in evidence.product_lines(s, purchase_document_id=doc_one_cat.id):
        evidence.classify_line(
            s, purchase_line_id=line.id, transaction_reason_id=fx.why_food.id,
            reporting_entity_id=fx.re_wp.id,
        )
    one_cat = bridge.apply_invoice_evidence(s, financial_transaction_id=txn_one_cat.id)
    check(
        "[12] a multi-category supplier's single-category invoice gives ONE allocation",
        len(one_cat) == 1
        and one_cat[0].amount_minor == -80_000
        and one_cat[0].accounting_classification_code_snapshot == "5100",
        detail=str([(a.amount_minor, a.accounting_classification_code_snapshot) for a in one_cat]),
    )

    # [13] three categories -> three allocations
    txn_three = _transaction(s, fx.bank_wp, -200_000, "CHENEY MIXED", occurrence=fx.who_cheney)
    doc_three = _document(
        s, fx.sup_cheney, number="C-200", total_minor=200_000,
        destination="RF Winter Park",
        lines=[
            _product("CHICKEN CASE", 150_000, code="C-CHK", number=1),
            _product("TOGO BOXES", 30_000, code="C-BOX", number=2),
            _product("CLEANING SUPPLIES", 20_000, code="C-CLN", number=3),
        ],
    )
    matching.create_match(
        s, financial_transaction_id=txn_three.id, purchase_document_id=doc_three.id,
        matched_amount_minor=-200_000,
    )
    lines_three = evidence.product_lines(s, purchase_document_id=doc_three.id)
    for line, why in zip(lines_three, (fx.why_food, fx.why_togo, fx.why_supplies)):
        evidence.classify_line(
            s, purchase_line_id=line.id, transaction_reason_id=why.id,
            reporting_entity_id=fx.re_wp.id,
        )
    three = bridge.apply_invoice_evidence(s, financial_transaction_id=txn_three.id)
    check(
        "[13] a three-category invoice produces three allocations",
        len(three) == 3
        and sorted(a.amount_minor for a in three) == [-150_000, -30_000, -20_000],
        detail=str(sorted(a.amount_minor for a in three)),
    )
    check(
        "[13] each allocation carries the account derived from its own line's WHY",
        {a.accounting_classification_code_snapshot for a in three} == {"5100", "5300", "7830"},
    )
    check(
        "[13] the parent is still exactly one bank transaction",
        s.scalar(
            select(func.count(m.FinancialTransaction.id)).where(
                m.FinancialTransaction.id == txn_three.id
            )
        ) == 1,
    )
    check(
        "[32] the resulting allocations sum exactly to the bank parent",
        sum(a.amount_minor for a in three) == txn_three.amount_minor == -200_000,
    )
    fx.txn_three = txn_three
    fx.doc_three = doc_three
    fx.txn_one_cat = txn_one_cat

    # [16] explicit operator bypass
    txn_bypass = _transaction(s, fx.bank_wp, -45_000, "CHENEY LOST INVOICE", occurrence=fx.who_cheney)
    authorization, allocations = bridge.complete_with_bypass(
        s,
        financial_transaction_id=txn_bypass.id,
        specs=[
            alloc.AllocationSpec(
                amount_minor=-45_000, reporting_entity_id=fx.re_wp.id,
                transaction_reason_id=fx.why_food.id,
            )
        ],
        reason="Invoice destroyed in a kitchen flood; delivery confirmed by the chef.",
        missing_document_note="Cheney cannot reissue before month end.",
        authorized_by_name="Operator",
    )
    check(
        "[16] an explicit bypass allows completion despite the missing document",
        len(allocations) == 1
        and allocations[0].status == alloc.COMPLETE
        and allocations[0].accounting_classification_code_snapshot == "5100",
    )
    check(
        "[16] the bypass records who, when, why, and that the document was unavailable",
        authorization.reason.startswith("Invoice destroyed")
        and authorization.authorized_at is not None
        and authorization.missing_document_note is not None
        and authorization.capability_snapshot == m.WHO_MULTI_CATEGORY_CAPABLE
        and authorization.occurrence_name_snapshot == "Cheney Brothers",
    )
    check(
        "[16] every allocation made under a bypass says so in its own evidence",
        allocations[0].evidence_kind == "OPERATOR_BYPASS"
        and f"bypass:{authorization.id}" == allocations[0].evidence_reference,
    )
    # The audit must outlive a restatement of the split.
    alloc.set_allocations(
        s,
        financial_transaction_id=txn_bypass.id,
        specs=[
            alloc.AllocationSpec(
                amount_minor=-45_000, reporting_entity_id=fx.re_wp.id,
                transaction_reason_id=fx.why_supplies.id,
            )
        ],
    )
    check(
        "[16] the bypass audit survives a later restatement of the allocations",
        len(bridge.bypass_history(s, financial_transaction_id=txn_bypass.id)) == 1
        and bridge.bypass_for(s, financial_transaction_id=txn_bypass.id).id == authorization.id,
    )
    fx.txn_bypass = txn_bypass

    # [17] an UNKNOWN counterparty's invoice reveals multiple categories
    txn_discover = _transaction(s, fx.bank_wp, -60_000, "NEW VENDOR", occurrence=fx.who_unknown)
    doc_discover = _document(
        s, fx.sup_new, number="N-500", total_minor=60_000, destination="RF Winter Park",
        lines=[
            _product("FOOD ITEM", 40_000, code="NV-F", number=1),
            _product("PAPER GOODS", 20_000, code="NV-P", number=2),
        ],
    )
    matching.create_match(
        s, financial_transaction_id=txn_discover.id, purchase_document_id=doc_discover.id,
        matched_amount_minor=-60_000,
    )
    disc_lines = evidence.product_lines(s, purchase_document_id=doc_discover.id)
    for line, why in zip(disc_lines, (fx.why_food, fx.why_togo)):
        evidence.classify_line(
            s, purchase_line_id=line.id, transaction_reason_id=why.id,
            reporting_entity_id=fx.re_wp.id,
        )
    evidence.discover_capability_from_document(
        s, occurrence_id=fx.who_unknown.id, purchase_document_id=doc_discover.id,
    )
    check(
        "[17] an invoice showing several categories establishes the capability by itself",
        fx.who_unknown.category_capability == m.WHO_MULTI_CATEGORY_CAPABLE
        and fx.who_unknown.capability_source == m.CAPABILITY_SOURCE_INVOICE_EVIDENCE,
        detail=fx.who_unknown.category_capability,
    )
    check(
        "[17] no prior configuration was needed for RF-One to discover it",
        "distinct canonical accounts" in (fx.who_unknown.capability_evidence or ""),
    )

    # [18] a later single-category invoice does not erase the capability
    doc_single_later = _document(
        s, fx.sup_new, number="N-501", total_minor=10_000, destination="RF Winter Park",
        lines=[_product("FOOD ONLY", 10_000, code="NV-F2")],
    )
    later_line = evidence.product_lines(s, purchase_document_id=doc_single_later.id)[0]
    evidence.classify_line(
        s, purchase_line_id=later_line.id, transaction_reason_id=fx.why_food.id,
        reporting_entity_id=fx.re_wp.id,
    )
    evidence.discover_capability_from_document(
        s, occurrence_id=fx.who_unknown.id, purchase_document_id=doc_single_later.id,
    )
    check(
        "[18] a later single-category invoice does not downgrade the capability",
        fx.who_unknown.category_capability == m.WHO_MULTI_CATEGORY_CAPABLE,
    )
    raises(
        "[18] an automatic downgrade is refused outright",
        lambda: evidence.set_who_capability(
            s, occurrence_id=fx.who_unknown.id, capability=m.WHO_SINGLE_CATEGORY,
            source=m.CAPABILITY_SOURCE_INVOICE_EVIDENCE,
        ),
        "never downgraded automatically",
    )


# ---------------------------------------------------------------------------
# §27 — supplier item learning
# ---------------------------------------------------------------------------


def _test_item_learning(s, fx, check) -> None:
    def classify(document_number: str, code: str, why, description="SALMON FILLET") -> None:
        doc = _document(
            s, fx.sup_cheney, number=document_number, total_minor=10_000,
            destination="RF Winter Park",
            lines=[_product(description, 10_000, code=code)],
        )
        line = evidence.product_lines(s, purchase_document_id=doc.id)[0]
        evidence.classify_line(
            s, purchase_line_id=line.id, transaction_reason_id=why.id,
            reporting_entity_id=fx.re_wp.id,
        )
        return doc, line

    # [19] one confirmation teaches nothing
    doc1, line1 = classify("L-1", "SALMON-1", fx.why_food)
    identity = evidence.resolve_item_identity(s, purchase_line=line1)
    learned = evidence.learned_mapping_for(
        s, supplier_id=fx.sup_cheney.id, identity=identity,
    )
    check(
        "[19] one human confirmation does not create a learned mapping",
        learned is None,
    )
    rows = s.scalars(
        select(m.SupplierItemCategoryLearning).where(
            m.SupplierItemCategoryLearning.identity_value == identity.value,
            m.SupplierItemCategoryLearning.supplier_id == fx.sup_cheney.id,
        )
    ).all()
    check(
        "[19] the single confirmation is recorded as OBSERVED, proposing nothing",
        len(rows) == 1
        and rows[0].confirmation_count == 1
        and rows[0].status == m.LEARNING_OBSERVED
        and not rows[0].may_propose,
    )

    # [24] a stable supplier identifier is preferred over a description
    check(
        "[24] an item with a supplier code is identified by that code, not its description",
        identity.kind == m.ITEM_IDENTITY_SUPPLIER_PRODUCT and identity.is_strong,
        detail=identity.kind,
    )

    # [20] the second consistent confirmation promotes it
    classify("L-2", "SALMON-1", fx.why_food)
    learned = evidence.learned_mapping_for(
        s, supplier_id=fx.sup_cheney.id, identity=identity,
    )
    check(
        "[20] two consistent confirmations produce a learned mapping",
        learned is not None
        and learned.status == m.LEARNING_LEARNED
        and learned.confirmation_count == 2
        and learned.transaction_reason_id == fx.why_food.id,
        detail=str(learned and learned.status),
    )

    # [21] the third occurrence is proposed automatically
    doc3 = _document(
        s, fx.sup_cheney, number="L-3", total_minor=10_000, destination="RF Winter Park",
        lines=[_product("SALMON FILLET", 10_000, code="SALMON-1")],
    )
    proposals = evidence.propose_line_classifications(s, purchase_document_id=doc3.id)
    check(
        "[21] the next invoice line is proposed automatically from what was learned",
        len(proposals) == 1
        and proposals[0].transaction_reason_id == fx.why_food.id
        and proposals[0].decision_source == m.LINE_DECISION_LEARNED
        and proposals[0].status == m.LINE_CLASSIFICATION_PROPOSED,
        detail=str(proposals),
    )
    check(
        "[21] the proposal is traceable back to the confirmations that produced it",
        proposals[0].learning_id == learned.id
        and "consistent human confirmations" in (proposals[0].evidence or ""),
    )
    check(
        "[21] an automatic proposal does not teach itself a third confirmation",
        learned.confirmation_count == 2,
    )

    # [22] a per-line human override is supported
    override = evidence.classify_line(
        s, purchase_line_id=proposals[0].purchase_line_id,
        transaction_reason_id=fx.why_supplies.id, reporting_entity_id=fx.re_wp.id,
    )
    current = evidence.current_classification(
        s, purchase_line_id=proposals[0].purchase_line_id,
    )
    check(
        "[22] a human may override the proposal on one invoice line",
        current.id == override.id
        and current.transaction_reason_id == fx.why_supplies.id
        and current.is_override,
    )
    check(
        "[22] the overridden proposal is preserved as history, not erased",
        len(evidence.classification_history(
            s, purchase_line_id=proposals[0].purchase_line_id,
        )) == 2,
    )

    # [23] the contradiction is preserved and audited, and does not silently win
    still_learned = evidence.learned_mapping_for(
        s, supplier_id=fx.sup_cheney.id, identity=identity,
    )
    check(
        "[23] one override does not overturn a mapping confirmed twice",
        still_learned is not None and still_learned.id == learned.id,
    )
    check(
        "[23] the disagreement is recorded on the learned mapping rather than hidden",
        "also classified this item" in (learned.contradiction_note or ""),
        detail=str(learned.contradiction_note),
    )
    # A second confirmation of the competing WHY makes it a real contradiction.
    classify("L-4", "SALMON-1", fx.why_supplies)
    contradicted = evidence.learned_mapping_for(
        s, supplier_id=fx.sup_cheney.id, identity=identity,
    )
    all_rows = s.scalars(
        select(m.SupplierItemCategoryLearning).where(
            m.SupplierItemCategoryLearning.supplier_id == fx.sup_cheney.id,
            m.SupplierItemCategoryLearning.identity_value == identity.value,
        )
    ).all()
    check(
        "[23] two twice-confirmed mappings contradict, and automatic proposal stops",
        contradicted is None
        and all(r.status == m.LEARNING_CONTRADICTED for r in all_rows if r.confirmation_count >= 2),
        detail=str([(r.transaction_reason_id, r.confirmation_count, r.status) for r in all_rows]),
    )
    check(
        "[23] neither side of the contradiction is deleted or overwritten",
        len(all_rows) == 2 and all(r.confirmation_count >= 2 for r in all_rows),
    )

    # [25] description fallback when no code exists
    doc_nocode = _document(
        s, fx.sup_amazon, number="A-1", total_minor=5_000, destination="RF Winter Park",
        lines=[{
            "line_type": "PRODUCT",
            "raw_description": "Printer  Toner, Black!",
            "source_amount_minor": 5_000,
            "source_line_number": 1,
        }],
    )
    nocode_line = evidence.product_lines(s, purchase_document_id=doc_nocode.id)[0]
    nocode_identity = evidence.resolve_item_identity(s, purchase_line=nocode_line)
    check(
        "[25] an item with no code falls back to a normalized description",
        nocode_identity.kind == m.ITEM_IDENTITY_NORMALIZED_DESCRIPTION
        and nocode_identity.value == "PRINTER TONER BLACK"
        and not nocode_identity.is_strong,
        detail=str(nocode_identity),
    )

    # A raw supplier item code with no resolved SupplierProduct still
    # outranks the description.
    raw_line = m.PurchaseLine(
        purchase_document_id=doc_nocode.id, line_type="PRODUCT",
        raw_description="Shelving Unit", source_amount_minor=0,
        supplier_item_code="shelf-9",
    )
    s.add(raw_line)
    s.flush()
    raw_identity = evidence.resolve_item_identity(s, purchase_line=raw_line)
    check(
        "[24] a bare supplier item code still outranks the description",
        raw_identity.kind == m.ITEM_IDENTITY_SUPPLIER_ITEM_CODE
        and raw_identity.value == "SHELF-9",
    )

    # [26] the same description from a different supplier is a different item
    evidence.record_item_confirmation(
        s, supplier_id=fx.sup_amazon.id, identity=nocode_identity,
        transaction_reason_id=fx.why_office.id,
    )
    evidence.record_item_confirmation(
        s, supplier_id=fx.sup_amazon.id, identity=nocode_identity,
        transaction_reason_id=fx.why_office.id,
    )
    amazon_learned = evidence.learned_mapping_for(
        s, supplier_id=fx.sup_amazon.id, identity=nocode_identity,
    )
    other_supplier = evidence.learned_mapping_for(
        s, supplier_id=fx.sup_other.id, identity=nocode_identity,
    )
    check(
        "[26] identical descriptions from two suppliers never share a learned mapping",
        amazon_learned is not None and other_supplier is None,
    )


# ---------------------------------------------------------------------------
# §28 — ancillary costs
# ---------------------------------------------------------------------------


def _test_ancillary(s, fx, check) -> None:
    # [27] proportional tax allocation, the task's own worked example
    doc_tax = _document(
        s, fx.sup_cheney, number="ANC-1", total_minor=110_000, destination="RF Winter Park",
        lines=[
            _product("FOOD", 70_000, code="ANC-FOOD", number=1),
            _product("PACKAGING", 30_000, code="ANC-PKG", number=2),
            {
                "line_type": "SURCHARGE",
                "raw_description": "Sales tax",
                "source_amount_minor": 10_000,
                "source_line_number": 3,
            },
        ],
    )
    allocated = purchasing.get_purchased_lines_with_allocation(s, doc_tax.id)
    shares = {row["raw_description"]: row["allocated_amount_minor"] for row in allocated}
    check(
        "[27] ancillary tax is apportioned in proportion to item value",
        shares["FOOD"] == 77_000 and shares["PACKAGING"] == 33_000,
        detail=str(shares),
    )
    check(
        "[31] the allocated line values sum exactly to the invoice total",
        sum(row["allocated_amount_minor"] for row in allocated) == 110_000,
    )

    # [28] freight behaves identically — the rule is about non-goods cost,
    # not about the word used for it.
    doc_freight = _document(
        s, fx.sup_cheney, number="ANC-2", total_minor=110_000, destination="RF Winter Park",
        lines=[
            _product("FOOD", 70_000, code="ANC-FOOD", number=1),
            _product("PACKAGING", 30_000, code="ANC-PKG", number=2),
            {
                "line_type": "SURCHARGE",
                "raw_description": "Freight",
                "source_amount_minor": 10_000,
                "source_line_number": 3,
            },
        ],
    )
    freight_shares = {
        row["raw_description"]: row["allocated_amount_minor"]
        for row in purchasing.get_purchased_lines_with_allocation(s, doc_freight.id)
    }
    check(
        "[28] freight is apportioned by the same proportional rule",
        freight_shares["FOOD"] == 77_000 and freight_shares["PACKAGING"] == 33_000,
    )

    # [29] several ancillary costs together
    doc_combined = _document(
        s, fx.sup_cheney, number="ANC-3", total_minor=112_000, destination="RF Winter Park",
        lines=[
            _product("FOOD", 70_000, code="ANC-FOOD", number=1),
            _product("PACKAGING", 30_000, code="ANC-PKG", number=2),
            {
                "line_type": "SURCHARGE", "raw_description": "Sales tax",
                "source_amount_minor": 6_000, "source_line_number": 3,
            },
            {
                "line_type": "SURCHARGE", "raw_description": "Fuel surcharge",
                "source_amount_minor": 6_000, "source_line_number": 4,
            },
        ],
    )
    combined = purchasing.get_purchased_lines_with_allocation(s, doc_combined.id)
    combined_shares = {row["raw_description"]: row["allocated_amount_minor"] for row in combined}
    check(
        "[29] several ancillary costs are apportioned together, once",
        combined_shares["FOOD"] == 78_400 and combined_shares["PACKAGING"] == 33_600,
        detail=str(combined_shares),
    )
    check(
        "[31] the combined allocation still reconciles to the invoice total",
        sum(row["allocated_amount_minor"] for row in combined) == 112_000,
    )

    # [30] the odd cent lands deterministically and never disappears
    doc_odd = _document(
        s, fx.sup_cheney, number="ANC-4", total_minor=10_001, destination="RF Winter Park",
        lines=[
            _product("A", 3_333, code="ODD-A", number=1),
            _product("B", 3_333, code="ODD-B", number=2),
            _product("C", 3_334, code="ODD-C", number=3),
            {
                "line_type": "SURCHARGE", "raw_description": "Odd cents",
                "source_amount_minor": 1, "source_line_number": 4,
            },
        ],
    )
    odd = purchasing.get_purchased_lines_with_allocation(s, doc_odd.id)
    check(
        "[30] an odd cent is assigned deterministically, never dropped",
        sum(row["allocated_non_goods_minor"] for row in odd) == 1
        and sum(row["allocated_amount_minor"] for row in odd) == 10_001,
        detail=str([row["allocated_non_goods_minor"] for row in odd]),
    )
    first_run = [row["allocated_amount_minor"] for row in odd]
    second_run = [
        row["allocated_amount_minor"]
        for row in purchasing.get_purchased_lines_with_allocation(s, doc_odd.id)
    ]
    check("[30] the same document allocates identically every time", first_run == second_run)

    # The same deterministic rule, one level up: splitting a payment across
    # category totals.
    split = bridge.proportional_split(100, [70, 30])
    check(
        "[30] the category-level split follows the same proportional rule",
        split == [70, 30] and sum(bridge.proportional_split(101, [1, 1, 1])) == 101,
        detail=str(split),
    )

    # [32] ancillary costs flow through into bank allocations that balance
    txn_anc = _transaction(s, fx.bank_wp, -110_000, "CHENEY WITH TAX", occurrence=fx.who_cheney)
    matching.create_match(
        s, financial_transaction_id=txn_anc.id, purchase_document_id=doc_tax.id,
        matched_amount_minor=-110_000,
    )
    tax_lines = evidence.product_lines(s, purchase_document_id=doc_tax.id)
    for line, why in zip(tax_lines, (fx.why_food, fx.why_togo)):
        evidence.classify_line(
            s, purchase_line_id=line.id, transaction_reason_id=why.id,
            reporting_entity_id=fx.re_wp.id,
        )
    anc_allocations = bridge.apply_invoice_evidence(s, financial_transaction_id=txn_anc.id)
    amounts = sorted(a.amount_minor for a in anc_allocations)
    check(
        "[32] bank allocations carry the ancillary-inclusive line values",
        amounts == [-77_000, -33_000],
        detail=str(amounts),
    )
    check(
        "[32] and sum exactly to the bank parent amount",
        sum(a.amount_minor for a in anc_allocations) == txn_anc.amount_minor == -110_000,
    )
    fx.txn_ancillary = txn_anc


# ---------------------------------------------------------------------------
# §29 — economic owner
# ---------------------------------------------------------------------------


def _test_economic_owner(s, fx, check) -> None:
    # [33] the document itself establishes the beneficiary
    doc_delivered = _document(
        s, fx.sup_cheney, number="D-1", total_minor=20_000, destination="RF Mount Dora",
        lines=[_product("DELIVERED GOODS", 20_000, code="DEL-1")],
    )
    resolved = evidence.resolve_owner_from_document_evidence(
        s, purchase_document_id=doc_delivered.id,
    )
    check(
        "[33] delivery evidence on the document establishes the beneficiary",
        resolved is not None and resolved.id == fx.re_md.id,
        detail=str(resolved and resolved.name),
    )

    # [34]/[35] no beneficiary on the document -> operator, never the payer
    txn_amazon = _transaction(s, fx.bank_gelati, -30_000, "AMAZON ORDER", occurrence=fx.who_amazon)
    doc_amazon = _document(
        s, fx.sup_amazon, number="AMZ-900", total_minor=30_000, destination=None,
        lines=[
            _product("PRINTER TONER", 10_000, code="AMZ-TONER", number=1),
            _product("PANS", 12_000, code="AMZ-PANS", number=2),
            _product("SHELVING", 8_000, code="AMZ-SHELF", number=3),
        ],
    )
    matching.create_match(
        s, financial_transaction_id=txn_amazon.id, purchase_document_id=doc_amazon.id,
        matched_amount_minor=-30_000,
    )
    check(
        "[35] a document with no delivery evidence establishes no beneficiary",
        evidence.resolve_owner_from_document_evidence(
            s, purchase_document_id=doc_amazon.id,
        ) is None,
    )

    amazon_lines = evidence.product_lines(s, purchase_document_id=doc_amazon.id)
    for line, why in zip(amazon_lines, (fx.why_office, fx.why_supplies, fx.why_supplies)):
        evidence.classify_line(
            s, purchase_line_id=line.id, transaction_reason_id=why.id,
        )
    state = evidence.document_evidence_state(s, purchase_document_id=doc_amazon.id)
    check(
        "[34] lines with a WHY but no beneficiary leave the document not ready",
        not state.is_ready and len(state.lines_without_owner) == 3,
        detail=str(state.lines_without_owner),
    )
    needing = evidence.lines_needing_owner(s, purchase_document_id=doc_amazon.id)
    check(
        "[34] RF-One asks the operational question at the line level",
        len(needing) == 3 and {line.id for line in needing} == set(state.lines_without_owner),
    )
    requirement = bridge.evidence_requirement(s, financial_transaction_id=txn_amazon.id)
    check(
        "[34] the transaction is blocked until the beneficiary is answered",
        not requirement.may_complete and "no beneficiary" in (requirement.blocking_reason or ""),
        detail=str(requirement.blocking_reason),
    )
    check(
        "[35] the payer's entity is never used as a beneficiary fallback",
        all(
            evidence.current_classification(
                s, purchase_line_id=line.id,
            ).reporting_entity_id is None
            for line in amazon_lines
        ),
    )

    # [36]/[37] the operator answers, in bulk where the answer is shared
    evidence.assign_economic_owner(
        s, purchase_line_ids=[amazon_lines[0].id], reporting_entity_id=fx.re_wp.id,
        evidence="Operator: toner was for the Winter Park office.",
    )
    evidence.assign_economic_owner(
        s, purchase_line_ids=[amazon_lines[1].id, amazon_lines[2].id],
        reporting_entity_id=fx.re_md.id,
        evidence="Operator: pans and shelving went to Mount Dora.",
    )
    check(
        "[36] the operator assigns one Amazon line to Winter Park",
        evidence.current_classification(
            s, purchase_line_id=amazon_lines[0].id,
        ).reporting_entity_id == fx.re_wp.id,
    )
    check(
        "[37] the operator assigns the other Amazon lines to Mount Dora, in one answer",
        evidence.current_classification(
            s, purchase_line_id=amazon_lines[1].id,
        ).reporting_entity_id == fx.re_md.id
        and evidence.current_classification(
            s, purchase_line_id=amazon_lines[2].id,
        ).reporting_entity_id == fx.re_md.id,
    )
    check(
        "[36] answering FOR WHOM does not count as a category confirmation",
        evidence.current_classification(
            s, purchase_line_id=amazon_lines[0].id,
        ).transaction_reason_id == fx.why_office.id,
    )

    # [38] one invoice, allocations for two entities
    amazon_allocations = bridge.apply_invoice_evidence(
        s, financial_transaction_id=txn_amazon.id,
    )
    by_entity = {}
    for allocation in amazon_allocations:
        by_entity.setdefault(allocation.reporting_entity_id, 0)
        by_entity[allocation.reporting_entity_id] += allocation.amount_minor
    check(
        "[38] one invoice produces allocations for two different entities",
        by_entity == {fx.re_wp.id: -10_000, fx.re_md.id: -20_000},
        detail=str(by_entity),
    )
    check(
        "[38] the multi-entity allocations still sum to the one bank parent",
        sum(a.amount_minor for a in amazon_allocations) == -30_000,
    )

    # [39] the intercompany consequence is derived
    cross = [a for a in amazon_allocations if a.is_cross_entity]
    check(
        "[39] cross-entity allocations derive Due From / Due To automatically",
        # Two allocations, not three lines: the two Mount Dora lines share
        # a beneficiary AND a WHY, so they aggregate into one economic
        # meaning. Three invoice lines do not imply three allocations.
        len(cross) == 2
        and {a.reporting_entity_id for a in cross} == {fx.re_wp.id, fx.re_md.id}
        and all(a.payer_legal_entity_id == fx.gelati.id for a in cross)
        and all(a.intercompany_due_from_code_snapshot == "1610" for a in cross)
        and all(a.intercompany_due_to_code_snapshot == "2710" for a in cross),
        detail=str([(a.reporting_entity_id, a.intercompany_outcome) for a in cross]),
    )

    # [40] the payer's P&L does not receive the other entity's expense
    gelati_pl = reporting.profit_and_loss_for_entity(
        s, reporting_entity_id=fx.re_gelati.id, date_from=PERIOD_START, date_to=PERIOD_END,
    )
    md_pl = reporting.profit_and_loss_for_entity(
        s, reporting_entity_id=fx.re_md.id, date_from=PERIOD_START, date_to=PERIOD_END,
    )
    check(
        "[40] the paying entity's P&L carries none of the other entity's expense",
        gelati_pl.total_minor == 0,
        detail=str(gelati_pl.total_minor),
    )
    check(
        "[40] the economic owner's P&L carries it instead",
        md_pl.total_minor == -20_000,
        detail=str(md_pl.total_minor),
    )

    # [41] a personal payer's business expense defaults to 2710
    txn_personal = _transaction(
        s, fx.card_personal, -15_000, "PERSONAL CARD BUYS SUPPLIES", occurrence=fx.who_gordon,
    )
    personal = alloc.set_allocations(
        s,
        financial_transaction_id=txn_personal.id,
        specs=[
            alloc.AllocationSpec(
                amount_minor=-15_000, reporting_entity_id=fx.re_wp.id,
                transaction_reason_id=fx.why_supplies.id,
            )
        ],
    )[0]
    check(
        "[41] a personal payer's business expense defaults to 2710 Due To Related Parties",
        personal.intercompany_outcome == m.INTERCOMPANY_PERSONAL_PAYER_DUE_TO
        and personal.intercompany_due_to_code_snapshot == "2710"
        and personal.payer_kind == m.PAYER_KIND_PERSONAL,
        detail=str(personal.intercompany_outcome),
    )
    check(
        "[41] it is never silently treated as a Member Contribution",
        "never silently treated as a Member Contribution" in (personal.intercompany_notes or ""),
    )

    # [42] an explicit Member Contribution goes to 3300 instead
    txn_contribution = _transaction(
        s, fx.card_personal, -25_000, "OWNER FUNDS SUPPLIES", occurrence=fx.who_gordon,
    )
    contribution = alloc.set_allocations(
        s,
        financial_transaction_id=txn_contribution.id,
        specs=[
            alloc.AllocationSpec(
                amount_minor=-25_000, reporting_entity_id=fx.re_wp.id,
                transaction_reason_id=fx.why_supplies.id,
                personal_funding_treatment=m.PERSONAL_FUNDING_MEMBER_CONTRIBUTION,
            )
        ],
    )[0]
    check(
        "[42] an explicit operator choice books the funding to 3300 instead",
        contribution.intercompany_outcome == m.INTERCOMPANY_PERSONAL_PAYER_CONTRIBUTION
        and contribution.intercompany_due_to_code_snapshot == "3300",
        detail=str(contribution.intercompany_outcome),
    )
    check(
        "[42] the expense itself is unaffected by how the funding was classified",
        contribution.accounting_classification_code_snapshot
        == personal.accounting_classification_code_snapshot
        == "7830",
    )

    # [43] no fake LegalEntity is ever created for the individual
    check(
        "[43] no LegalEntity was invented to represent the personal payer",
        s.scalar(select(func.count(m.LegalEntity.id))) == fx.legal_entity_count
        and personal.payer_legal_entity_id is None
        and contribution.payer_legal_entity_id is None,
    )
    fx.txn_personal = txn_personal
    fx.txn_contribution = txn_contribution


# ---------------------------------------------------------------------------
# §30 — period completeness
# ---------------------------------------------------------------------------


def _test_period_completeness(s, fx, check) -> None:
    completeness = reporting.evaluate_period_completeness(
        s, period_month="2026-03", period_start=PERIOD_START, period_end=PERIOD_END,
    )

    # [44] a fully settled transaction is accounting complete
    complete_state = alloc.allocation_state(s, financial_transaction_id=fx.txn_three.id)
    check(
        "[44] a financially reconciled movement with settled evidence is accounting complete",
        complete_state.is_accounting_closed
        and s.get(m.FinancialTransaction, fx.txn_three.id).accounting_status == "CANONICAL",
    )

    # [45] financially reconciled, accounting pending
    pending_state = alloc.allocation_state(s, financial_transaction_id=fx.txn_pending.id)
    check(
        "[45] a movement can be financially reconciled and accounting pending at once",
        s.get(m.FinancialTransaction, fx.txn_pending.id).accounting_status == "CANONICAL"
        and pending_state.status == alloc.PENDING_EVIDENCE
        and not pending_state.is_accounting_closed,
    )

    # [46] that pending movement blocks the month's accounting completion
    check(
        "[46] the month is financially reconciled",
        completeness.financially_reconciled,
        detail=(
            f"{completeness.financially_resolved_count}/{completeness.transaction_count}"
        ),
    )
    check(
        "[46] but is NOT accounting complete while an invoice is missing",
        not completeness.accounting_complete
        and fx.txn_pending.id in completeness.blocking_transaction_ids
        and completeness.pending_evidence_count >= 1,
        detail=completeness.summary,
    )
    check(
        "[46] the two completeness states are reported separately, never as one",
        "financially reconciled" in completeness.summary
        and "ACCOUNTING INCOMPLETE" in completeness.summary,
        detail=completeness.summary,
    )

    # [47] an authorized bypass lets a blocked movement complete
    bypassed_state = alloc.allocation_state(s, financial_transaction_id=fx.txn_bypass.id)
    check(
        "[47] an authorized bypass allows a movement with no invoice to be accounting complete",
        bypassed_state.is_accounting_closed
        and bridge.bypass_for(s, financial_transaction_id=fx.txn_bypass.id) is not None,
    )
    check(
        "[47] and it is still on record that the document was never seen",
        bridge.bypass_for(
            s, financial_transaction_id=fx.txn_bypass.id,
        ).missing_document_note is not None,
    )

    # Resolving the last pending movement closes the month's accounting.
    doc_late = _document(
        s, fx.sup_cheney, number="C-LATE", total_minor=200_000, destination="RF Winter Park",
        lines=[_product("LATE DELIVERY", 200_000, code="C-LATE-1")],
    )
    matching.create_match(
        s, financial_transaction_id=fx.txn_pending.id, purchase_document_id=doc_late.id,
        matched_amount_minor=-200_000,
    )
    late_line = evidence.product_lines(s, purchase_document_id=doc_late.id)[0]
    evidence.classify_line(
        s, purchase_line_id=late_line.id, transaction_reason_id=fx.why_food.id,
        reporting_entity_id=fx.re_wp.id,
    )
    bridge.apply_invoice_evidence(s, financial_transaction_id=fx.txn_pending.id)
    check(
        "[45] the late invoice resolves the pending movement without touching its money",
        alloc.allocation_state(
            s, financial_transaction_id=fx.txn_pending.id,
        ).is_accounting_closed
        and s.get(m.FinancialTransaction, fx.txn_pending.id).amount_minor == -200_000,
    )

    after = reporting.evaluate_period_completeness(
        s, period_month="2026-03", period_start=PERIOD_START, period_end=PERIOD_END,
    )
    check(
        "[48] every financial transaction still exists after the evidence work",
        after.transaction_count == completeness.transaction_count,
        detail=f"{after.transaction_count} vs {completeness.transaction_count}",
    )
    check(
        "[46] resolving the evidence reduces what blocks the month",
        len(after.blocking_transaction_ids) < len(completeness.blocking_transaction_ids),
        detail=(
            f"{len(after.blocking_transaction_ids)} vs "
            f"{len(completeness.blocking_transaction_ids)}"
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
