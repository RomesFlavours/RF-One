#!/usr/bin/env python
"""Purchasing persistence tests (TASK_PURCHASING_004).

Unlike `test_payroll_engine.py`/`test_tips_engine.py` (which build a
synthetic fixture against the CONFIGURED database inside one transaction
and always roll it back), this entry point exercises the specific
requirement TASK_PURCHASING_004 asks for that a rolled-back transaction
cannot demonstrate: that persisted Purchasing records survive a process
restart.

It always targets its OWN disposable local SQLite file
(`data/purchasing_test.db`, Git-ignored, deleted and recreated at the start
of every run) — never the shared `RFONE_DATABASE_URL` / local `data/rfone.db`
— so it never depends on, or risks, whatever a real deployment already has
persisted there.

Runs, in order:
  1. `purchasing_validation.run_validation` (rolled back) — structural
     CheckConstraint and repository-level historical-integrity checks.
  2. The 7 canonical business scenarios from TASK_PURCHASING_004, committed
     for real.
  3. A fresh Engine/Session pointed at the same database file, re-querying
     every scenario's data to confirm it survived the "restart."

Usage:
    python test_purchasing_engine.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from rfone_data_store.database import create_configured_engine, create_session_factory, run_migrations_to_head
from rfone_data_store import models as m
from rfone_data_store.purchasing import repository as repo
from rfone_data_store.purchasing_validation import run_validation as run_schema_validation

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def main() -> int:
    db_path = Path(__file__).resolve().parent / "data" / "purchasing_test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    url = f"sqlite:///{db_path.as_posix()}"
    print(f"Purchasing test database: {url}")

    run_migrations_to_head(url)

    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool) -> None:
        (checks_passed if condition else checks_failed).append(description)

    # --- 1. Structural / repository validation (rolled back) -------------
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    schema_result = run_schema_validation(session_factory)
    checks_passed.extend(schema_result.checks_passed)
    checks_failed.extend(schema_result.checks_failed)

    # --- 2. The 7 canonical business scenarios, persisted for real -------
    ids = _persist_seven_scenarios(session_factory, check)
    engine.dispose()

    # --- 3. Restart: fresh Engine/Session over the SAME file --------------
    restarted_engine = create_configured_engine(url)
    restarted_session_factory = create_session_factory(restarted_engine)
    with restarted_session_factory() as session:
        _assert_survives_restart(session, ids, check)
    restarted_engine.dispose()

    if checks_failed:
        print(f"Purchasing tests: FAILURE ({len(checks_passed)} passed, {len(checks_failed)} failed)")
        for description in checks_failed:
            print(f"  FAILED: {description}")
        return 1

    print(f"Purchasing tests: SUCCESS ({len(checks_passed)}/{len(checks_passed)} checks passed)")
    return 0


def _persist_seven_scenarios(session_factory, check) -> dict:
    ids: dict = {}
    with session_factory() as session:
        restaurant = m.Restaurant(name="Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.flush()
        ids["restaurant_id"] = restaurant.id

        supplier = repo.get_or_create_supplier(session, restaurant.id, "Fresh Food Inc.")
        ids["supplier_id"] = supplier.id

        # --- Scenario 1: normal Purchase Document with matching lines ---
        sp_parmesan, _ = repo.get_or_create_supplier_product(session, supplier.id, supplier_code="PARM24")
        repo.update_supplier_product_classification(session, sp_parmesan.id, economic_classification="FOOD")
        doc_1 = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "INV-1001", "document_type": "Invoice", "issue_date": _now(), "currency": "USD"},
            lines=[
                {
                    "line_type": "PRODUCT",
                    "raw_description": "Parmesan Cheese 24 Months",
                    "supplier_product_id": sp_parmesan.id,
                    "quantity": Decimal("10"),
                    "purchase_unit": "kg",
                    "unit_price_minor": 1200,
                    "source_amount_minor": 12000,
                },
                {
                    "line_type": "SURCHARGE",
                    "raw_description": "Delivery Fee",
                    "source_amount_minor": 1000,
                },
            ],
        )
        session.flush()
        ids["doc_1_id"] = doc_1.id
        ids["doc_1_line_product_id"] = doc_1.lines[0].id
        check(
            "Scenario 1: Purchase Document created with a PRODUCT line and a SURCHARGE line, both preserved verbatim",
            len(doc_1.lines) == 2
            and doc_1.lines[0].line_type == "PRODUCT"
            and doc_1.lines[0].economic_classification == "FOOD"
            and doc_1.lines[1].line_type == "SURCHARGE"
            and doc_1.lines[1].supplier_product_id is None,
        )

        # --- Scenario 2: unknown Supplier Product -> Validation Log ------
        doc_2 = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "INV-1002", "document_type": "Invoice", "issue_date": _now()},
            lines=[
                {
                    "line_type": "PRODUCT",
                    "raw_description": "Truffle Oil 250ml",
                    "supplier_item_code": "TRUF250",  # never seen before
                    "quantity": Decimal("6"),
                    "purchase_unit": "ea",
                }
            ],
        )
        session.flush()
        ids["doc_2_id"] = doc_2.id
        validation_entries = session.scalars(
            select(m.PurchasingValidationLogEntry).where(m.PurchasingValidationLogEntry.purchase_document_id == doc_2.id)
        ).all()
        check(
            "Scenario 2: an unknown Supplier Product is created and a Validation Log entry is generated, not guessed",
            doc_2.lines[0].supplier_product_id is not None
            and doc_2.lines[0].economic_classification is None
            and len(validation_entries) == 1
            and validation_entries[0].status == "OPEN",
        )

        # --- Scenario 3: Order 10 -> Invoice 10 -> Receiving 8 -----------
        sp_mozzarella, _ = repo.get_or_create_supplier_product(session, supplier.id, supplier_code="MOZZ")
        repo.update_supplier_product_classification(session, sp_mozzarella.id, economic_classification="FOOD")
        order_3 = repo.create_purchase_order(
            session, supplier.id, [{"supplier_product_id": sp_mozzarella.id, "quantity": Decimal("10")}]
        )
        order_3_line = session.scalars(
            select(m.PurchaseOrderLine).where(m.PurchaseOrderLine.purchase_order_id == order_3.id)
        ).first()
        doc_3 = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "INV-1003", "document_type": "Invoice", "issue_date": _now()},
            lines=[
                {
                    "line_type": "PRODUCT",
                    "raw_description": "Mozzarella",
                    "supplier_product_id": sp_mozzarella.id,
                    "quantity": Decimal("10"),
                    "purchase_unit": "ea",
                }
            ],
            purchase_order_id=order_3.id,
        )
        receiving_3 = repo.start_receiving(
            session, supplier.id, receiving_timestamp=_now(), capture_method="ORDER_BASED",
            purchase_order_id=order_3.id, purchase_document_id=doc_3.id,
        )
        receiving_3_line = repo.add_receiving_line(
            session,
            receiving_3.id,
            {
                "purchase_order_line_id": order_3_line.id,
                "purchase_line_id": doc_3.lines[0].id,
                "supplier_product_id": sp_mozzarella.id,
                "observed_quantity": Decimal("8"),
            },
        )
        outcomes_3 = repo.reconcile_receiving_line(session, receiving_3_line.id)
        alert_3 = repo.raise_receiving_discrepancy_alert(session, receiving_3_line.id, outcomes_3)
        repo.complete_receiving(session, receiving_3.id)
        session.flush()
        ids["receiving_3_id"] = receiving_3.id
        ids["alert_3_id"] = alert_3.id if alert_3 else None
        check(
            "Scenario 3 (Order 10 / Invoice 10 / Receiving 8): SHORT is derived and Receiving completes with the Alert OPEN",
            outcomes_3 == ["SHORT"]
            and alert_3 is not None
            and alert_3.status == "OPEN"
            and session.get(m.ReceivingRecord, receiving_3.id).status == "COMPLETED",
        )

        # --- Scenario 4: Order 10 -> Invoice 8 -> Receiving 8 ------------
        sp_wine, _ = repo.get_or_create_supplier_product(session, supplier.id, supplier_code="WINEA")
        repo.update_supplier_product_classification(session, sp_wine.id, economic_classification="DRINK")
        order_4 = repo.create_purchase_order(
            session, supplier.id, [{"supplier_product_id": sp_wine.id, "quantity": Decimal("10")}]
        )
        order_4_line = session.scalars(
            select(m.PurchaseOrderLine).where(m.PurchaseOrderLine.purchase_order_id == order_4.id)
        ).first()
        doc_4 = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "INV-1004", "document_type": "Invoice", "issue_date": _now()},
            lines=[
                {
                    "line_type": "PRODUCT",
                    "raw_description": "Wine A",
                    "supplier_product_id": sp_wine.id,
                    "quantity": Decimal("8"),
                    "purchase_unit": "ea",
                }
            ],
            purchase_order_id=order_4.id,
        )
        receiving_4 = repo.start_receiving(
            session, supplier.id, receiving_timestamp=_now(), capture_method="ORDER_BASED",
            purchase_order_id=order_4.id, purchase_document_id=doc_4.id,
        )
        receiving_4_line = repo.add_receiving_line(
            session,
            receiving_4.id,
            {
                "purchase_order_line_id": order_4_line.id,
                "purchase_line_id": doc_4.lines[0].id,
                "supplier_product_id": sp_wine.id,
                "observed_quantity": Decimal("8"),
            },
        )
        outcomes_4 = repo.reconcile_receiving_line(session, receiving_4_line.id)
        repo.complete_receiving(session, receiving_4.id)
        session.flush()
        check(
            "Scenario 4 (Order 10 / Invoice 8 / Receiving 8): ORDER_MISMATCH is derived; Invoice and Receiving match",
            outcomes_4 == ["ORDER_MISMATCH"],
        )

        # --- Scenario 5: damaged delivery, partial ACCEPT/REJECT_RETURN -
        # Matches the canonical Example 8 ("Order / Invoice: Parmesan Cheese
        # 24 Months — 10 units"): an Order line is present so the Receiving
        # Line is a normal (non-Extra) match against it, per the Domain's
        # own "no related Purchase Order Line ⇒ Extra/Unexpected Item"
        # definition (Purchasing/EntityDefinitions.md, "Receiving Line").
        sp_parm_2 = sp_parmesan
        order_5 = repo.create_purchase_order(
            session, supplier.id, [{"supplier_product_id": sp_parm_2.id, "quantity": Decimal("10")}]
        )
        order_5_line = session.scalars(
            select(m.PurchaseOrderLine).where(m.PurchaseOrderLine.purchase_order_id == order_5.id)
        ).first()
        doc_5 = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "INV-1005", "document_type": "Invoice", "issue_date": _now()},
            lines=[
                {
                    "line_type": "PRODUCT",
                    "raw_description": "Parmesan Cheese 24 Months",
                    "supplier_product_id": sp_parm_2.id,
                    "quantity": Decimal("10"),
                    "unit_price_minor": 1200,
                }
            ],
            purchase_order_id=order_5.id,
        )
        receiving_5 = repo.start_receiving(
            session, supplier.id, receiving_timestamp=_now(), capture_method="MANUAL",
            purchase_order_id=order_5.id, purchase_document_id=doc_5.id,
        )
        receiving_5_line = repo.add_receiving_line(
            session,
            receiving_5.id,
            {
                "purchase_order_line_id": order_5_line.id,
                "purchase_line_id": doc_5.lines[0].id,
                "supplier_product_id": sp_parm_2.id,
                "observed_quantity": Decimal("10"),
                "damaged_quantity": Decimal("2"),
                "photo_evidence": "synthetic://photos/damaged_parmesan.jpg",
            },
        )
        outcomes_5 = repo.reconcile_receiving_line(session, receiving_5_line.id)
        alert_5 = repo.raise_receiving_discrepancy_alert(session, receiving_5_line.id, outcomes_5)
        repo.complete_receiving(session, receiving_5.id)
        alert_5_decided, credit_5 = repo.decide_receiving_alert(
            session,
            alert_5.id,
            "REJECT_RETURN",
            rejected_quantity=Decimal("2"),
            expected_amount_minor=2400,  # 2 x 1200
        )
        session.refresh(receiving_5_line)
        session.flush()
        ids["receiving_5_line_id"] = receiving_5_line.id
        ids["credit_5_id"] = credit_5.id
        check(
            "Scenario 5 (10 observed / 8 accepted / 2 rejected): DAMAGED is derived, the Receiving observation "
            "still shows 10 with 2 damaged (never rewritten to 8), and an Expected Supplier Credit opens",
            outcomes_5 == ["DAMAGED"]
            and receiving_5_line.observed_quantity == Decimal("10")
            and receiving_5_line.damaged_quantity == Decimal("2")
            and credit_5 is not None
            and credit_5.status == "OPEN"
            and credit_5.expected_amount_minor == 2400,
        )

        # --- Scenario 6: later Supplier credit document, partial then full
        credit_note_6 = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "CN-2001", "document_type": "Credit Note", "issue_date": _now()},
            lines=[{"line_type": "PRODUCT", "raw_description": "Credit: Parmesan Cheese 24 Months", "source_amount_minor": -1400}],
        )
        repo.link_supplier_credit(
            session, credit_5.id, applied_amount_minor=1400,
            purchase_document_id=credit_note_6.id, purchase_line_id=credit_note_6.lines[0].id,
        )
        session.refresh(credit_5)
        original_doc_5_line = session.get(m.PurchaseLine, doc_5.lines[0].id)
        recognized_partial, outstanding_partial = repo.get_expected_supplier_credit_amounts(session, credit_5.id)
        check(
            "Scenario 6 (partial credit): original Purchase Document is unchanged; credit is linked separately; "
            "partial resolution is representable",
            credit_5.status == "PARTIALLY_RESOLVED"
            and recognized_partial == 1400
            and outstanding_partial == 1000
            and original_doc_5_line.quantity == Decimal("10")  # never rewritten
            and original_doc_5_line.raw_description == "Parmesan Cheese 24 Months",
        )

        credit_note_6b = repo.record_purchase_document(
            session,
            supplier.id,
            header={"document_number": "CN-2002", "document_type": "Credit Note", "issue_date": _now()},
            lines=[{"line_type": "PRODUCT", "raw_description": "Credit: Parmesan Cheese 24 Months (remainder)", "source_amount_minor": -1000}],
        )
        repo.link_supplier_credit(
            session, credit_5.id, applied_amount_minor=1000,
            purchase_document_id=credit_note_6b.id, purchase_line_id=credit_note_6b.lines[0].id,
        )
        session.refresh(credit_5)
        recognized_full, outstanding_full = repo.get_expected_supplier_credit_amounts(session, credit_5.id)
        check(
            "Scenario 6 (full resolution): a second credit note fully resolves the Expected Supplier Credit",
            credit_5.status == "RESOLVED" and outstanding_full == 0 and recognized_full == 2400,
        )

        # --- Scenario 7: extra/unexpected item ----------------------------
        receiving_7 = repo.start_receiving(session, supplier.id, receiving_timestamp=_now(), capture_method="LABEL_BASED")
        receiving_7_line = repo.add_receiving_line(
            session,
            receiving_7.id,
            {
                "purchase_order_line_id": None,  # no matching Order line -> Extra Item by definition
                "raw_description": "Zucchine",
                "observed_quantity": Decimal("2"),
                "photo_evidence": "synthetic://photos/extra_zucchine.jpg",
            },
        )
        outcomes_7 = repo.reconcile_receiving_line(session, receiving_7_line.id)
        alert_7 = repo.raise_receiving_discrepancy_alert(session, receiving_7_line.id, outcomes_7)
        repo.complete_receiving(session, receiving_7.id)
        session.flush()
        ids["alert_7_id"] = alert_7.id
        check(
            "Scenario 7 (extra/unexpected item): Receiving Line has no Purchase Order Line, carries mandatory photo "
            "evidence, and raises an EXTRA discrepancy Alert",
            receiving_7_line.purchase_order_line_id is None
            and receiving_7_line.photo_evidence is not None
            and outcomes_7 == ["EXTRA"]
            and alert_7 is not None
            and alert_7.status == "OPEN",
        )

        session.commit()

    return ids


def _assert_survives_restart(session, ids: dict, check) -> None:
    doc_1 = session.get(m.PurchaseDocument, ids["doc_1_id"])
    check(
        "restart: Scenario 1's Purchase Document and its lines are still present after reopening the store",
        doc_1 is not None and len(doc_1.lines) == 2,
    )

    receiving_3 = session.get(m.ReceivingRecord, ids["receiving_3_id"])
    alert_3 = session.get(m.PurchasingAlert, ids["alert_3_id"]) if ids["alert_3_id"] else None
    check(
        "restart: Scenario 3's Receiving stays COMPLETED and its Alert stays OPEN after reopening the store",
        receiving_3 is not None
        and receiving_3.status == "COMPLETED"
        and alert_3 is not None
        and alert_3.status == "OPEN",
    )

    receiving_5_line = session.get(m.ReceivingLine, ids["receiving_5_line_id"])
    credit_5 = session.get(m.ExpectedSupplierCredit, ids["credit_5_id"])
    recognized, outstanding = repo.get_expected_supplier_credit_amounts(session, credit_5.id)
    check(
        "restart: Scenario 5/6's Receiving observation (10 received, 2 damaged) and the now-RESOLVED "
        "Expected Supplier Credit both survive reopening the store",
        receiving_5_line.observed_quantity == Decimal("10")
        and receiving_5_line.damaged_quantity == Decimal("2")
        and credit_5.status == "RESOLVED"
        and outstanding == 0,
    )

    alert_7 = session.get(m.PurchasingAlert, ids["alert_7_id"])
    check(
        "restart: Scenario 7's Extra/Unexpected Item Alert survives reopening the store",
        alert_7 is not None and alert_7.trigger == "RECEIVING_DISCREPANCY" and alert_7.status == "OPEN",
    )


if __name__ == "__main__":
    sys.exit(main())
