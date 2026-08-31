"""Automated Purchasing schema/repository validation (TASK_PURCHASING_004).

Same pattern as `schema_validation.py`/`payroll_validation.py`: builds a
synthetic fixture (never real Supplier data) inside one transaction and
always rolls it back, so running this never leaves rows in the target
database. Exercises the structural (CheckConstraint) and repository-level
historical-integrity guarantees directly — the full 7 canonical business
scenarios from TASK_PURCHASING_004, including the persistence-survives-
restart check, live in `test_purchasing_engine.py` instead, since that
check needs a real (non-rolled-back) commit and a second Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .purchasing import repository as repo

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def _now() -> datetime:
    return datetime.now(UTC)


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _build_fixture_and_assert(session, result)
        finally:
            session.rollback()
    return result


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    restaurant = m.Restaurant(name="Validation Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()

    supplier = repo.get_or_create_supplier(session, restaurant.id, "Fresh Food Inc.")
    supplier_again = repo.get_or_create_supplier(session, restaurant.id, "Fresh Food Inc.")
    result.check("get_or_create_supplier reuses an existing Supplier by name", supplier.id == supplier_again.id)

    # --- Supplier Product memory (Rule: known pair reuses the same row) ---
    sp1, created1 = repo.get_or_create_supplier_product(session, supplier.id, supplier_code="PARM24")
    sp2, created2 = repo.get_or_create_supplier_product(session, supplier.id, supplier_code="PARM24")
    result.check(
        "known (Supplier, Supplier Item Code) reuses the existing Supplier Product",
        created1 is True and created2 is False and sp1.id == sp2.id,
    )

    repo.update_supplier_product_classification(session, sp1.id, economic_classification="FOOD")
    document = repo.record_purchase_document(
        session,
        supplier.id,
        header={"document_number": "INV-1", "document_type": "Invoice", "issue_date": _now()},
        lines=[
            {
                "line_type": "PRODUCT",
                "raw_description": "Parmesan Cheese 24 Months",
                "supplier_product_id": sp1.id,
                "quantity": Decimal("10"),
                "purchase_unit": "kg",
                "unit_price_minor": 1200,
                "source_amount_minor": 12000,
            }
        ],
    )
    session.flush()
    recorded_line = document.lines[0]
    result.check(
        "a PRODUCT line snapshots the Supplier Product's current classification at insert time",
        recorded_line.economic_classification == "FOOD",
    )

    repo.update_supplier_product_classification(session, sp1.id, economic_classification="SUPPLIES")
    session.refresh(recorded_line)
    result.check(
        "a later Supplier Product correction never rewrites a historical Purchase Line's own classification",
        recorded_line.economic_classification == "FOOD",
    )

    # --- Rule 3, structural: SURCHARGE/DISCOUNT can never carry a Supplier
    # Product or a classification --------------------------------------
    rejected = False
    nested = session.begin_nested()
    try:
        session.add(
            m.PurchaseLine(
                purchase_document_id=document.id,
                line_type="SURCHARGE",
                raw_description="Fuel Surcharge",
                supplier_product_id=sp1.id,  # invalid for SURCHARGE
            )
        )
        session.flush()
    except IntegrityError:
        rejected = True
        nested.rollback()
    else:
        nested.rollback()
    result.check(
        "CheckConstraint rejects a SURCHARGE/DISCOUNT line with a Supplier Product (Rule 3, structural)", rejected
    )

    # --- Configured Expectation: prospective-only change, superseding ----
    expectation_1 = repo.set_configured_expectation(
        session, sp1.id, [{"pack_count": 20, "pack_size": "500 g"}], approved_by_employee_id=None
    )
    expectation_2 = repo.set_configured_expectation(
        session, sp1.id, [{"pack_count": 1, "pack_size": "5 kg"}], approved_by_employee_id=None
    )
    session.refresh(expectation_1)
    result.check(
        "changing a Configured Expectation supersedes the prior row rather than editing it",
        expectation_1.status == "SUPERSEDED"
        and expectation_2.status == "ACTIVE"
        and expectation_1.id != expectation_2.id,
    )

    # --- Configuration deviation Alert against the active expectation ---
    line_2 = repo.record_purchase_document(
        session,
        supplier.id,
        header={"document_number": "INV-2", "document_type": "Invoice", "issue_date": _now()},
        lines=[
            {
                "line_type": "PRODUCT",
                "raw_description": "Parmesan Cheese 24 Months",
                "supplier_product_id": sp1.id,
                "quantity": Decimal("5"),
                "pack_count": 20,
                "pack_size": "500 g",  # matches expectation_1, which is now SUPERSEDED
            }
        ],
    ).lines[0]
    alert = repo.detect_configuration_deviation(session, line_2.id)
    result.check(
        "a line matching only a SUPERSEDED expectation (not the ACTIVE one) raises a CONFIGURATION_DEVIATION Alert",
        alert is not None and alert.trigger == "CONFIGURATION_DEVIATION" and alert.comparison_basis == "CONFIGURED_EXPECTATION",
    )

    decided = repo.decide_configuration_alert(session, alert.id, "ACCEPT_THIS_PURCHASE_ONLY")
    active_after = repo.get_active_configured_expectation(session, sp1.id)
    result.check(
        "ACCEPT_THIS_PURCHASE_ONLY closes the Alert without changing the active Configured Expectation",
        decided.status == "CLOSED" and active_after.id == expectation_2.id,
    )

    # --- Receiving: Extra Item requires photo (structural) ---------------
    receiving = repo.start_receiving(
        session, supplier.id, receiving_timestamp=_now(), capture_method="MANUAL"
    )
    rejected_extra = False
    nested = session.begin_nested()
    try:
        session.add(
            m.ReceivingLine(
                receiving_record_id=receiving.id,
                raw_description="Zucchine",
                observed_quantity=Decimal("2"),
                photo_evidence=None,  # invalid: Extra Item with no photo
            )
        )
        session.flush()
    except IntegrityError:
        rejected_extra = True
        nested.rollback()
    else:
        nested.rollback()
    result.check(
        "CheckConstraint rejects an Extra/Unexpected Item Receiving Line with no photo (Rule 29, structural)",
        rejected_extra,
    )

    # --- Expected Supplier Credit: partial then full resolution ---------
    fake_alert = m.PurchasingAlert(
        trigger="RECEIVING_DISCREPANCY", purchase_document_id=document.id, purchase_line_id=recorded_line.id, status="DECIDED"
    )
    session.add(fake_alert)
    session.flush()
    credit = repo.create_expected_supplier_credit(
        session,
        alert_id=fake_alert.id,
        purchase_document_id=document.id,
        purchase_line_id=recorded_line.id,
        rejected_quantity=Decimal("2"),
        expected_amount_minor=2400,
    )
    repo.link_supplier_credit(session, credit.id, applied_amount_minor=1400, note="partial credit note")
    session.refresh(credit)
    recognized, outstanding = repo.get_expected_supplier_credit_amounts(session, credit.id)
    result.check(
        "a partial Supplier credit moves status to PARTIALLY_RESOLVED with the correct derived outstanding amount",
        credit.status == "PARTIALLY_RESOLVED" and recognized == 1400 and outstanding == 1000,
    )
    repo.link_supplier_credit(session, credit.id, applied_amount_minor=1000, note="remaining credit note")
    session.refresh(credit)
    recognized, outstanding = repo.get_expected_supplier_credit_amounts(session, credit.id)
    result.check(
        "a fully-recognized Supplier credit resolves the expectation with zero derived outstanding amount",
        credit.status == "RESOLVED" and outstanding == 0 and credit.resolved_at is not None,
    )

    # --- Referential integrity smoke test ---------------------------------
    fk_rejected = False
    nested = session.begin_nested()
    try:
        session.add(m.PurchaseLine(purchase_document_id=-1, line_type="PRODUCT", raw_description="INVALID-FK-CHECK"))
        session.flush()
    except IntegrityError:
        fk_rejected = True
        nested.rollback()
    else:
        nested.rollback()
    result.check("an invalid Purchase Line foreign key reference is rejected by the database", fk_rejected)
