#!/usr/bin/env python
"""Tests for the "Purchased output" repository functions added by "Align
legacy Invoice Intake with Purchased" (`rfone_data_store/purchasing/
repository.py`, §10 of `PURCHASING.md`): `get_document_functional_status`,
`get_line_functional_status`, `get_purchased_lines_with_allocation`, and
`find_purchase_documents_by_number`.

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
