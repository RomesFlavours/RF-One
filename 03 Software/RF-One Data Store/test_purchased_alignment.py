#!/usr/bin/env python
"""Tests for the "Purchased output" repository functions added by "Align
legacy Invoice Intake with Purchased" (`rfone_data_store/purchasing/
repository.py`, §10 of `PURCHASING.md`): `get_document_functional_status`,
`get_line_functional_status`, `get_purchased_lines_with_allocation`, and
`find_purchase_documents_by_number`. Also covers the Effective Purchased
View merge added by "Make Effective Purchased View canonical for all
consumers" (`resolve_latest_field_corrections`/`latest_field_corrections`/
`effective_field_value`) as consumed directly by the repository layer —
non-goods allocation and Physical Receiving three-way reconciliation —
which is Restaurant/Purchasing's own remaining scope and has no dedicated
runtime module of its own to test against; see `03 Software/InvoiceIntake/
test_human_review.py` for the same merge as consumed by Human
Review/Invoice Intake's own views.

These are repository-level tests (no InvoiceIntake/Flask involved) — see
`03 Software/InvoiceIntake/test_purchased_bridge.py` for the bridge-level
duplicate/correction/functional-state integration tests.

Always targets its own disposable, self-provisioned SQLite database (never
`RFONE_DATABASE_URL`/the shared local `data/rfone.db`) — same convention as
`test_purchasing_engine.py`.

Usage:
    python test_purchased_alignment.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_disposable_test_database_url,
    create_session_factory,
)
from rfone_data_store import models as m
from rfone_data_store.purchasing import repository as repo

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def main() -> int:
    url = create_disposable_test_database_url("purchased_alignment")
    result = Result()
    try:
        engine = create_configured_engine(url)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            restaurant = m.Restaurant(name="Purchased Alignment Test Restaurant", default_currency="USD")
            session.add(restaurant)
            session.flush()
            supplier = repo.get_or_create_supplier(session, restaurant.id, "Test Foods Inc.")

            # --- Non-goods cost allocation (Purchased/README.md example) ---
            # Goods A = 100, Goods B = 300, Delivery = 40 -> A=110, B=330.
            document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "ALLOC-1", "document_type": "Invoice", "issue_date": _now()},
                lines=[
                    {"line_type": "PRODUCT", "raw_description": "Goods A", "source_amount_minor": 10000},
                    {"line_type": "PRODUCT", "raw_description": "Goods B", "source_amount_minor": 30000},
                    {"line_type": "SURCHARGE", "raw_description": "Delivery", "source_amount_minor": 4000},
                ],
            )
            session.commit()
            allocated = repo.get_purchased_lines_with_allocation(session, document.id)
            by_desc = {row["raw_description"]: row for row in allocated}
            result.check(
                "non-goods allocation matches the README worked example (A=110, B=330)",
                allocated is not None
                and len(allocated) == 2
                and by_desc["Goods A"]["allocated_amount_minor"] == 11000
                and by_desc["Goods B"]["allocated_amount_minor"] == 33000,
            )
            result.check(
                "the raw SURCHARGE line remains in the database as source evidence (never dropped)",
                any(line.line_type == "SURCHARGE" and line.raw_description == "Delivery" for line in document.lines),
            )
            result.check(
                "allocation only touches PRODUCT lines' output rows (2, not 3)",
                {row["raw_description"] for row in allocated} == {"Goods A", "Goods B"},
            )

            # --- Allocation rounding: last line absorbs the remainder -----
            rounding_document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "ALLOC-2", "document_type": "Invoice", "issue_date": _now()},
                lines=[
                    {"line_type": "PRODUCT", "raw_description": "Item 1", "source_amount_minor": 100},
                    {"line_type": "PRODUCT", "raw_description": "Item 2", "source_amount_minor": 100},
                    {"line_type": "PRODUCT", "raw_description": "Item 3", "source_amount_minor": 100},
                    {"line_type": "SURCHARGE", "raw_description": "Fee", "source_amount_minor": 10},
                ],
            )
            session.commit()
            rounding_rows = repo.get_purchased_lines_with_allocation(session, rounding_document.id)
            result.check(
                "allocated shares always sum exactly back to the non-goods total (rounding absorbed, not lost)",
                sum(row["allocated_non_goods_minor"] for row in rounding_rows) == 10,
            )

            # --- No PRODUCT lines: non-goods amount left unallocated -------
            no_goods_document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "ALLOC-3", "document_type": "Invoice", "issue_date": _now()},
                lines=[{"line_type": "SURCHARGE", "raw_description": "Fee only", "source_amount_minor": 500}],
            )
            session.commit()
            no_goods_rows = repo.get_purchased_lines_with_allocation(session, no_goods_document.id)
            result.check(
                "a document with no PRODUCT lines produces an empty allocated-lines view (documented open edge case)",
                no_goods_rows == [],
            )

            # --- NORMALIZED / HUMAN, derived from PurchasingValidationLogEntry ---
            clean_document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "STATUS-1", "document_type": "Invoice", "issue_date": _now()},
                lines=[{"line_type": "PRODUCT", "raw_description": "Clean Item", "source_amount_minor": 1000}],
            )
            session.commit()
            result.check(
                "a document with no OPEN WARNING/ERROR validation log entry is NORMALIZED",
                repo.get_document_functional_status(session, clean_document.id) == "NORMALIZED",
            )

            repo.add_validation_log_entry(
                session,
                purchase_document_id=clean_document.id,
                severity="WARNING",
                message="Simulated low-confidence read",
                suggested_action="Verify manually",
            )
            session.commit()
            result.check(
                "a document with an OPEN WARNING validation log entry becomes HUMAN",
                repo.get_document_functional_status(session, clean_document.id) == "HUMAN",
            )

            info_only_document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "STATUS-2", "document_type": "Credit Memo", "issue_date": _now()},
                lines=[{"line_type": "PRODUCT", "raw_description": "Credit Item", "source_amount_minor": -500}],
            )
            repo.add_validation_log_entry(
                session,
                purchase_document_id=info_only_document.id,
                severity="INFORMATION",
                message="Correction of STATUS-1",
            )
            session.commit()
            result.check(
                "an OPEN INFORMATION-only entry (e.g. a correction note) does not force HUMAN by itself",
                repo.get_document_functional_status(session, info_only_document.id) == "NORMALIZED",
            )

            line = clean_document.lines[0]
            result.check(
                "get_line_functional_status is NORMALIZED for a line with no issue",
                repo.get_line_functional_status(session, line.id) == "NORMALIZED",
            )
            repo.add_validation_log_entry(
                session,
                purchase_document_id=clean_document.id,
                purchase_line_id=line.id,
                severity="ERROR",
                message="Simulated line-level problem",
            )
            session.commit()
            result.check(
                "get_line_functional_status becomes HUMAN once an OPEN ERROR entry references that specific line",
                repo.get_line_functional_status(session, line.id) == "HUMAN",
            )

            # --- Duplicate-identity lookup ----------------------------------
            matches = repo.find_purchase_documents_by_number(session, supplier.id, "ALLOC-1")
            result.check(
                "find_purchase_documents_by_number finds the existing (supplier, document_number) row",
                len(matches) == 1 and matches[0].id == document.id,
            )
            result.check(
                "find_purchase_documents_by_number returns nothing for a blank document_number",
                repo.find_purchase_documents_by_number(session, supplier.id, "") == [],
            )

            # --- Supplier alias model / canonical cleanup ("Purchased
            # Supplier Training Phase 2", §8-10) --------------------------
            dirty_supplier = repo.get_or_create_supplier(session, restaurant.id, "PRIME LINE DISTRIBUTORS INVOICE")
            linked_document = repo.record_purchase_document(
                session,
                dirty_supplier.id,
                header={"document_number": "PL-0001", "document_type": "Invoice", "issue_date": _now(), "total_amount_minor": 12345},
                lines=[{"line_type": "PRODUCT", "raw_description": "Some Item", "source_amount_minor": 12345}],
            )
            session.commit()
            supplier_id_before_rename = dirty_supplier.id

            renamed = repo.rename_supplier_canonical(session, dirty_supplier.id, "Prime Line Distributors")
            session.commit()
            result.check(
                "rename_supplier_canonical renames in place (same id)",
                renamed.id == supplier_id_before_rename and renamed.name == "Prime Line Distributors",
            )
            result.check(
                "the old dirty name is preserved as an alias, not deleted",
                any(a.alias_name == "PRIME LINE DISTRIBUTORS INVOICE" for a in repo.list_supplier_aliases(session, renamed.id)),
            )
            result.check(
                "the pre-existing PurchaseDocument's FK/data is untouched by the rename",
                session.get(m.PurchaseDocument, linked_document.id).supplier_id == supplier_id_before_rename
                and session.get(m.PurchaseDocument, linked_document.id).total_amount_minor == 12345,
            )
            result.check(
                "renaming to the same name again is a no-op (idempotent, no duplicate alias)",
                repo.rename_supplier_canonical(session, renamed.id, "Prime Line Distributors").id == renamed.id
                and len(repo.list_supplier_aliases(session, renamed.id)) == 1,
            )

            resolved_via_alias = repo.get_or_create_supplier(session, restaurant.id, "PRIME LINE DISTRIBUTORS INVOICE")
            result.check(
                "get_or_create_supplier resolves a known ALIAS to the current canonical Supplier, never a duplicate",
                resolved_via_alias.id == renamed.id,
            )

            add_alias_again = repo.add_supplier_alias(session, renamed.id, "PRIME LINE DISTRIBUTORS INVOICE", source="dup-call")
            result.check(
                "add_supplier_alias is idempotent for an already-recorded alias",
                add_alias_again.id == next(a.id for a in repo.list_supplier_aliases(session, renamed.id) if a.alias_name == "PRIME LINE DISTRIBUTORS INVOICE"),
            )

            # --- Effective Purchased View: non-goods allocation must use
            # effective (corrected) amounts, not raw ones ("Make Effective
            # Purchased View canonical for all consumers") -----------------
            eff_document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "EFFECTIVE-1", "document_type": "Invoice", "issue_date": _now()},
                lines=[
                    {"line_type": "PRODUCT", "raw_description": "Goods A", "source_amount_minor": 10000},
                    {"line_type": "PRODUCT", "raw_description": "Goods B", "source_amount_minor": 30000},
                    {"line_type": "SURCHARGE", "raw_description": "Delivery", "source_amount_minor": 4000},
                ],
            )
            session.commit()
            goods_a = next(line for line in eff_document.lines if line.raw_description == "Goods A")
            delivery = next(line for line in eff_document.lines if line.raw_description == "Delivery")

            baseline = {row["raw_description"]: row for row in repo.get_purchased_lines_with_allocation(session, eff_document.id)}
            result.check(
                "no correction yet: effective_amount_minor equals the raw source_amount_minor (Effective View = original)",
                baseline["Goods A"]["effective_amount_minor"] == 10000
                and baseline["Goods A"]["source_amount_minor"] == 10000,
            )

            repo.record_field_correction(
                session, purchase_document_id=eff_document.id, purchase_line_id=goods_a.id,
                field_name="line_amount", classification="INCORRECT", reviewed_by="alice",
                original_value="100.00", corrected_value="200.00",
            )
            session.commit()
            corrected = {row["raw_description"]: row for row in repo.get_purchased_lines_with_allocation(session, eff_document.id)}
            result.check(
                "a line_amount correction changes the effective amount used as the allocation base (Goods A: 100 -> 200)",
                corrected["Goods A"]["effective_amount_minor"] == 20000,
            )
            result.check(
                "the raw source_amount_minor column stays untouched by the correction (source evidence immutable)",
                session.get(m.PurchaseLine, goods_a.id).source_amount_minor == 10000,
            )
            result.check(
                "non-goods allocation recomputes proportionally against the NEW effective goods total "
                "(goods 200+300=500; delivery 40 -> A gets 16.00, B gets 24.00)",
                corrected["Goods A"]["allocated_non_goods_minor"] == 1600
                and corrected["Goods B"]["allocated_non_goods_minor"] == 2400,
            )
            result.check(
                "allocated shares still sum exactly to the non-goods total after a correction (rounding still absorbed)",
                corrected["Goods A"]["allocated_non_goods_minor"] + corrected["Goods B"]["allocated_non_goods_minor"] == 4000,
            )

            # A later CORRECT confirmation on the SAME field is not a value
            # override (record_field_correction never stores a
            # corrected_value for CORRECT) -- the LATEST correction still
            # wins, and it reverts the effective value back to the original.
            repo.record_field_correction(
                session, purchase_document_id=eff_document.id, purchase_line_id=goods_a.id,
                field_name="line_amount", classification="CORRECT", reviewed_by="alice", original_value="200.00",
            )
            session.commit()
            reverted = {row["raw_description"]: row for row in repo.get_purchased_lines_with_allocation(session, eff_document.id)}
            result.check(
                "multiple corrections: the LATEST one wins -- a later CORRECT confirmation reverts to the original value",
                reverted["Goods A"]["effective_amount_minor"] == 10000,
            )

            # Correcting the non-goods (SURCHARGE) line's own amount changes
            # the allocation base too -- not just PRODUCT lines.
            repo.record_field_correction(
                session, purchase_document_id=eff_document.id, purchase_line_id=delivery.id,
                field_name="line_amount", classification="INCORRECT", reviewed_by="alice",
                original_value="40.00", corrected_value="80.00",
            )
            session.commit()
            surcharge_corrected = {row["raw_description"]: row for row in repo.get_purchased_lines_with_allocation(session, eff_document.id)}
            result.check(
                "correcting the SURCHARGE line's own amount changes the total allocated across the goods lines",
                surcharge_corrected["Goods A"]["allocated_non_goods_minor"]
                + surcharge_corrected["Goods B"]["allocated_non_goods_minor"] == 8000,
            )
            result.check(
                "the SURCHARGE line's raw source_amount_minor stays untouched by its own correction",
                session.get(m.PurchaseLine, delivery.id).source_amount_minor == 4000,
            )

            # --- Effective Purchased View: Physical Receiving's own
            # three-way reconciliation must compare against the effective
            # (corrected) invoice quantity, not the raw OCR-read one -------
            qty_order = repo.create_purchase_order(
                session, supplier.id, [{"item_description": "Chicken Breast", "quantity": Decimal("8")}]
            )
            qty_order_line = session.scalars(
                select(m.PurchaseOrderLine).where(m.PurchaseOrderLine.purchase_order_id == qty_order.id)
            ).first()
            qty_document = repo.record_purchase_document(
                session,
                supplier.id,
                header={"document_number": "QTY-1", "document_type": "Invoice", "issue_date": _now()},
                lines=[
                    {
                        "line_type": "PRODUCT",
                        "raw_description": "Chicken Breast",
                        "quantity": Decimal("10"),  # an OCR misread -- the order and the physical delivery both say 8
                        "purchase_unit": "case",
                    }
                ],
                purchase_order_id=qty_order.id,
            )
            session.commit()
            qty_line = qty_document.lines[0]
            qty_receiving = repo.start_receiving(
                session, supplier.id, receiving_timestamp=_now(), capture_method="ORDER_BASED",
                purchase_order_id=qty_order.id, purchase_document_id=qty_document.id,
            )
            qty_receiving_line = repo.add_receiving_line(
                session, qty_receiving.id,
                {"purchase_order_line_id": qty_order_line.id, "purchase_line_id": qty_line.id, "observed_quantity": Decimal("8")},
            )
            session.commit()

            outcomes_before = repo.reconcile_receiving_line(session, qty_receiving_line.id)
            result.check(
                "before correction: reconciliation compares received (8) against the RAW misread invoice quantity (10) "
                "-> a false ORDER_MISMATCH/SHORT",
                set(outcomes_before) == {"ORDER_MISMATCH", "SHORT"},
            )

            repo.record_field_correction(
                session, purchase_document_id=qty_document.id, purchase_line_id=qty_line.id,
                field_name="quantity", classification="INCORRECT", reviewed_by="alice",
                original_value="10", corrected_value="8",
            )
            session.commit()
            outcomes_after = repo.reconcile_receiving_line(session, qty_receiving_line.id)
            result.check(
                "after correcting the invoice quantity to the true value (8), reconciliation now reports a clean MATCH",
                outcomes_after == ["MATCH"],
            )
            result.check(
                "the raw PurchaseLine.quantity column itself is never mutated by the correction",
                session.get(m.PurchaseLine, qty_line.id).quantity == Decimal("10"),
            )

            outcomes_alert = repo.raise_receiving_discrepancy_alert(session, qty_receiving_line.id, outcomes_after)
            result.check(
                "raise_receiving_discrepancy_alert also resolves the effective quantity (MATCH -> no Alert raised)",
                outcomes_alert is None,
            )
    finally:
        cleanup_disposable_test_database_url(url)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Purchased alignment repository tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Purchased alignment repository tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
