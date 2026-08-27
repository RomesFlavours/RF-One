#!/usr/bin/env python
"""Post-promotion ingestion validation (task §48).

Confirms the configured database has non-zero row counts in every table a
successful Clover ingestion is expected to populate, and confirms the
tables this task deliberately leaves empty (Table Service / Physical Table
reconstruction is a separate task — §35-36) are, in fact, empty rather than
silently fabricated.

Usage:
    python validate_ingestion.py
"""

from __future__ import annotations

import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rfone_data_store.database import create_configured_engine, get_database_url, redact_database_url
from rfone_data_store.models import (
    Category,
    Device,
    DiscountDefinition,
    Employee,
    IngestionRun,
    Item,
    ItemCategory,
    ItemModifier,
    Location,
    Merchant,
    ModifierGroup,
    Modifier,
    Order,
    OrderDiscount,
    OrderFee,
    OrderItem,
    OrderItemModifier,
    OrderItemTax,
    OrderType,
    Payment,
    PaymentTip,
    PhysicalTable,
    Refund,
    Shift,
    SourceRecord,
    SourceSystem,
    TableService,
    TableServiceEmployee,
    TableServicePhysicalTable,
    TaxRate,
    Tender,
)

EXPECTED_NON_ZERO = [
    SourceSystem,
    IngestionRun,
    SourceRecord,
    Merchant,
    Location,
    Device,
    Employee,
    Shift,
    OrderType,
    Item,
    Category,
    ItemCategory,
    ModifierGroup,
    Modifier,
    ItemModifier,
    DiscountDefinition,
    TaxRate,
    Tender,
    Order,
    OrderItem,
    OrderItemModifier,
    OrderDiscount,
    OrderItemTax,
    OrderFee,
    Payment,
    PaymentTip,
    Refund,
]

EXPECTED_EMPTY = [
    PhysicalTable,
    TableService,
    TableServicePhysicalTable,
    TableServiceEmployee,
]


def main() -> int:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")
    engine = create_configured_engine(url)

    ok = True
    with Session(engine) as session:
        print("\nExpected non-zero:")
        for model in EXPECTED_NON_ZERO:
            count = session.scalar(select(func.count()).select_from(model)) or 0
            status = "OK" if count > 0 else "FAIL (zero rows)"
            if count == 0:
                ok = False
            print(f"  {model.__tablename__:35s} {count:8d}  {status}")

        print("\nExpected empty (deferred to a future Table Service reconstruction task):")
        for model in EXPECTED_EMPTY:
            count = session.scalar(select(func.count()).select_from(model)) or 0
            status = "OK" if count == 0 else "UNEXPECTED (should be empty)"
            if count != 0:
                ok = False
            print(f"  {model.__tablename__:35s} {count:8d}  {status}")

        latest_run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        if latest_run:
            print(f"\nLatest IngestionRun: id={latest_run.id} status={latest_run.status} started_at={latest_run.started_at}")
            if latest_run.status not in ("COMPLETE", "PARTIAL"):
                ok = False

    print(f"\nValidation: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
