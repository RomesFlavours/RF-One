#!/usr/bin/env python
"""Tests for the "Invoice Intake data model" (PURCHASING.md §13; migration
`b3f9d2c6e4a1`).

1. Migration safety: a database at the previous head (`d8e2f5a9c3b7`)
   holding Purchased data is upgraded; every pre-existing row and value is
   unchanged and the new columns read NULL. Downgrade and re-upgrade keep
   the data too.
2. Representation, with isolated test data: a sale by the bottle, a sale by
   the case and a catch-weight sale — invoice-read values, product card
   (versioned packaging + conversions), calculated values with their inputs,
   human confirmations, uncertainty/conflict flags, charges.
3. Structural guarantees: a standard weight cannot be stored as an actual
   weight; a calculated value needs its inputs; an automatic packaging
   needs the invoice line it came from; a packaging change leaves earlier
   invoices untouched.

Always targets its own disposable SQLite database (never
`RFONE_DATABASE_URL`/the shared local `data/rfone.db`).

Usage:
    python test_invoice_intake_data_model.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m
from rfone_data_store.database import (
    _DISPOSABLE_TEST_DB_PREFIX,
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
)
from rfone_data_store.purchasing import repository as repo

UTC = timezone.utc
MODULE_DIR = Path(__file__).resolve().parent
PREVIOUS_HEAD = "d8e2f5a9c3b7"
NEW_LINE_COLUMNS = (
    "piece_content_value", "piece_content_unit", "actual_weight_value", "actual_weight_unit", "unit_price_basis",
)
NEW_LOG_COLUMNS = ("field_name", "issue_type", "observed_values")
PRESERVED_TABLES = (
    "restaurants", "suppliers", "supplier_products", "purchase_documents", "purchase_lines",
    "purchasing_validation_log_entries", "purchased_field_corrections",
)


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def _alembic(url: str, action: str, revision: str) -> None:
    cfg = Config(str(MODULE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(MODULE_DIR / "migrations"))
    previous = os.environ.get("ALEMBIC_DATABASE_URL_OVERRIDE")
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = url
    try:
        getattr(command, action)(cfg, revision)
    finally:
        if previous is None:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = previous


def _snapshot(url: str) -> dict[str, list[dict]]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {
                table: [dict(row._mapping) for row in conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))]
                for table in PRESERVED_TABLES
            }
    finally:
        engine.dispose()


def _seed_previous_schema(url: str) -> None:
    """Existing Purchased data, written with plain SQL against the previous
    schema (the current ORM models already carry the new columns)."""
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO restaurants (id, name) VALUES (1, 'Legacy Restaurant')"))
            conn.execute(text("INSERT INTO suppliers (id, restaurant_id, name) VALUES (1, 1, 'Legacy Foods')"))
            conn.execute(text(
                "INSERT INTO supplier_products (id, supplier_id, supplier_code, supplier_name, packaging)"
                " VALUES (1, 1, 'OIL-1', 'OLIVE OIL', '4/1 GAL')"
            ))
            conn.execute(text(
                "INSERT INTO purchase_documents (id, supplier_id, document_number, document_type, issue_date,"
                " total_amount_minor, status, source_reference)"
                " VALUES (1, 1, 'L-100', 'Invoice', '2026-08-19 00:00:00', 49052, 'RECORDED', 'legacy.pdf#p1')"
            ))
            conn.execute(text(
                "INSERT INTO purchase_lines (id, purchase_document_id, line_type, raw_description, source_amount_minor,"
                " supplier_product_id, supplier_item_code, quantity, purchase_unit, pack_count, pack_size,"
                " unit_price_minor) VALUES (1, 1, 'PRODUCT', 'OLIVE OIL 4/1 GAL', 48352, 1, 'OIL-1', 4, 'CS', 4,"
                " '1 GAL', 12088)"
            ))
            conn.execute(text(
                "INSERT INTO purchase_lines (id, purchase_document_id, line_type, raw_description, source_amount_minor)"
                " VALUES (2, 1, 'SURCHARGE', 'FUEL SURCHARGE', 700)"
            ))
            conn.execute(text(
                "INSERT INTO purchasing_validation_log_entries (id, purchase_document_id, severity, message, status)"
                " VALUES (1, 1, 'WARNING', 'Unknown or unclassified Supplier Product', 'OPEN')"
            ))
            conn.execute(text(
                "INSERT INTO purchased_field_corrections (id, purchase_document_id, purchase_line_id, field_name,"
                " classification, original_value, corrected_value, reviewed_by)"
                " VALUES (1, 1, 1, 'quantity', 'CORRECT', '4', NULL, 'Legacy Reviewer')"
            ))
    finally:
        engine.dispose()


def _rows_preserved(before: dict, after: dict) -> bool:
    for table, rows in before.items():
        if len(rows) != len(after[table]):
            return False
        for old, new in zip(rows, after[table]):
            if any(new.get(column) != value for column, value in old.items()):
                return False
    return True


def test_migration_preserves_data(result: Result) -> None:
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"{_DISPOSABLE_TEST_DB_PREFIX}intake_migration_")
    os.close(fd)
    os.remove(path)
    url = f"sqlite:///{Path(path).as_posix()}"
    try:
        _alembic(url, "upgrade", PREVIOUS_HEAD)
        _seed_previous_schema(url)
        before = _snapshot(url)

        _alembic(url, "upgrade", "head")
        after = _snapshot(url)
        result.check("migration: every pre-existing row and value unchanged", _rows_preserved(before, after))
        result.check(
            "migration: new purchase_lines columns are NULL on existing rows (not zero)",
            all(row[col] is None for row in after["purchase_lines"] for col in NEW_LINE_COLUMNS),
        )
        result.check(
            "migration: new validation-log columns are NULL on existing rows",
            all(row[col] is None for row in after["purchasing_validation_log_entries"] for col in NEW_LOG_COLUMNS),
        )
        engine = create_engine(url)
        tables = set(inspect(engine).get_table_names())
        engine.dispose()
        result.check(
            "migration: four new tables exist",
            {"purchase_document_sources", "supplier_product_packagings", "supplier_product_unit_conversions",
             "purchased_line_derived_values"} <= tables,
        )

        _alembic(url, "downgrade", PREVIOUS_HEAD)
        result.check("downgrade: existing data still intact", _rows_preserved(before, _snapshot(url)))
        _alembic(url, "upgrade", "head")
        result.check("re-upgrade: existing data still intact", _rows_preserved(before, _snapshot(url)))
    finally:
        cleanup_disposable_test_database_url(url)


def _expect_integrity_error(session, build) -> bool:
    savepoint = session.begin_nested()
    try:
        session.add(build())
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        return True
    savepoint.rollback()
    return False


def _packaging(session, supplier_product_id: int, version: int, **fields) -> m.SupplierProductPackaging:
    packaging = m.SupplierProductPackaging(supplier_product_id=supplier_product_id, version=version, **fields)
    session.add(packaging)
    session.flush()
    return packaging


def _conversion(session, packaging_id: int, from_unit: str, to_unit: str, factor: str, origin: str,
                is_nominal: bool = False) -> None:
    session.add(m.SupplierProductUnitConversion(
        packaging_id=packaging_id, from_unit=from_unit, to_unit=to_unit, factor=Decimal(factor),
        origin=origin, is_nominal=is_nominal,
    ))


def test_representation(result: Result) -> None:
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"{_DISPOSABLE_TEST_DB_PREFIX}intake_model_")
    os.close(fd)
    os.remove(path)
    url = f"sqlite:///{Path(path).as_posix()}"
    try:
        _alembic(url, "upgrade", "head")
        engine = create_configured_engine(url)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            restaurant = m.Restaurant(name="Intake Data Model Test Restaurant", default_currency="USD")
            session.add(restaurant)
            session.flush()
            supplier = repo.get_or_create_supplier(session, restaurant.id, "Test Beverage & Deli Co.")

            document = repo.record_purchase_document(
                session,
                supplier.id,
                header={
                    "document_number": "T-001", "document_type": "Invoice",
                    "issue_date": datetime(2026, 10, 1, tzinfo=UTC), "total_amount_minor": 32640,
                },
                lines=[
                    # 1. Sold by the bottle: 6 bottles of 750 ML at 12.00 per bottle.
                    {"line_type": "PRODUCT", "raw_description": "CHIANTI DOCG 750ML", "supplier_item_code": "WINE-01",
                     "quantity": "6", "purchase_unit": "BOTTLE", "piece_content_value": "750",
                     "piece_content_unit": "ML", "unit_price_minor": 1200, "unit_price_basis": "BOTTLE",
                     "source_amount_minor": 7200},
                    # 2. Sold by the case: Qty 2 CASE, 6 per case printed, price basis not printed.
                    {"line_type": "PRODUCT", "raw_description": "SPARKLING WATER 6/1 L", "supplier_item_code": "WATER-06",
                     "quantity": "2", "purchase_unit": "CASE", "pack_count": 6, "pack_size": "6/1 L",
                     "unit_price_minor": 900, "source_amount_minor": 1800},
                    # 3. Catch weight: 2 cases, 3 pieces of 2.5 # avg, 16.08 delivered (unit not printed), 8.98 per #.
                    {"line_type": "PRODUCT", "raw_description": "SALAME 3/2.5 # AVG", "supplier_item_code": "SAL-03",
                     "quantity": "2", "purchase_unit": "CASE", "pack_count": 3, "pack_size": "3/2.5 # AVG",
                     "actual_weight_value": "16.08", "unit_price_minor": 898, "unit_price_basis": "#",
                     "source_amount_minor": 14440},
                    # 4. Same water, but the quantity unit is not printed.
                    {"line_type": "PRODUCT", "raw_description": "SPARKLING WATER", "supplier_item_code": "WATER-06",
                     "quantity": "2", "unit_price_minor": 900, "source_amount_minor": 1800},
                    # Charges: name + signed amount, linked to the invoice.
                    {"line_type": "SURCHARGE", "raw_description": "FUEL SURCHARGE", "source_amount_minor": 700},
                    {"line_type": "DISCOUNT", "raw_description": "PROMO CREDIT", "source_amount_minor": -500},
                ],
            )
            bottle, case, catch, case_no_unit, fuel, promo = sorted(document.lines, key=lambda line: line.id)

            # --- Invoice data: supplier link, number/date, source files and pages ---
            session.add_all([
                m.PurchaseDocumentSource(purchase_document_id=document.id, sequence=1, content_hash="a" * 64,
                                         original_filename="T-001 page1.jpg", storage_reference="uploads/a.jpg",
                                         channel="MANUAL_UPLOAD", acquisition_status="ACQUIRED", page_from=1,
                                         page_to=1, file_page_count=1),
                m.PurchaseDocumentSource(purchase_document_id=document.id, sequence=2, content_hash="b" * 64,
                                         original_filename="T-001 page2.jpg", storage_reference="uploads/b.jpg",
                                         channel="MANUAL_UPLOAD", acquisition_status="FAILED", page_from=1,
                                         page_to=1, file_page_count=1),
            ])
            session.flush()
            sources = session.scalars(select(m.PurchaseDocumentSource).where(
                m.PurchaseDocumentSource.purchase_document_id == document.id).order_by(m.PurchaseDocumentSource.sequence)).all()
            result.check("invoice: supplier linked to the existing supplier registry",
                         session.get(m.Supplier, document.supplier_id).name == "Test Beverage & Deli Co.")
            result.check("invoice: number and date stored", document.document_number == "T-001" and document.issue_date is not None)
            result.check("invoice: two source files with pages and per-file acquisition status",
                         [(s.sequence, s.page_from, s.acquisition_status) for s in sources]
                         == [(1, 1, "ACQUIRED"), (2, 1, "FAILED")])
            result.check("invoice: verification status derived (NORMALIZED/HUMAN), not a new column",
                         repo.get_document_functional_status(session, document.id) in ("NORMALIZED", "HUMAN"))
            result.check("invoice: inverted page range rejected", _expect_integrity_error(session, lambda: m.PurchaseDocumentSource(
                purchase_document_id=document.id, sequence=3, content_hash="c" * 64, acquisition_status="ACQUIRED",
                page_from=2, page_to=1)))

            # --- Lines: product card link and read values ---
            products = {p.supplier_code: p for p in session.scalars(select(m.SupplierProduct)).all()}
            result.check("lines: linked to the supplier product card by supplier code",
                         bottle.supplier_product_id == products["WINE-01"].id
                         and case.supplier_product_id == case_no_unit.supplier_product_id == products["WATER-06"].id)
            result.check("bottle sale: quantity 6 BOTTLE, 750 ML per piece, price per BOTTLE",
                         (bottle.quantity, bottle.purchase_unit, bottle.piece_content_value, bottle.piece_content_unit,
                          bottle.unit_price_basis) == (Decimal("6"), "BOTTLE", Decimal("750"), "ML", "BOTTLE"))
            result.check("case sale: quantity 2 CASE and 6 per case kept distinct (12 not stored on the line)",
                         (case.quantity, case.purchase_unit, case.pack_count) == (Decimal("2"), "CASE", 6))
            result.check("case sale: price basis not printed stays NULL", case.unit_price_basis is None)
            result.check("catch weight: actual weight 16.08 read, unit not printed stays NULL",
                         catch.actual_weight_value == Decimal("16.08") and catch.actual_weight_unit is None)
            result.check("missing values stay NULL, never zero",
                         case.piece_content_value is None and bottle.actual_weight_value is None
                         and case_no_unit.purchase_unit is None)

            # --- Charges: separate rows, signed, compatible with existing allocation ---
            result.check("charges: name and signed amount kept, linked to the invoice",
                         (fuel.line_type, fuel.raw_description, fuel.source_amount_minor) == ("SURCHARGE", "FUEL SURCHARGE", 700)
                         and promo.source_amount_minor == -500 and fuel.purchase_document_id == document.id)
            allocation = repo.get_purchased_lines_with_allocation(session, document.id)
            result.check("charges: existing allocation still distributes the net 2.00 over goods lines",
                         sum(row["allocated_non_goods_minor"] for row in allocation) == 200)

            # --- Product card: packaging versions and conversions ---
            wine_v1 = _packaging(session, products["WINE-01"].id, 1, status="ACTIVE", package_unit="CASE",
                                 pieces_per_package=12, piece_unit="BOTTLE", piece_content_value=Decimal("750"),
                                 piece_content_unit="ML", sale_unit="BOTTLE", price_basis_unit="BOTTLE",
                                 origin="INVOICE_READ", source_purchase_line_id=bottle.id)
            _conversion(session, wine_v1.id, "BOTTLE", "ML", "750", "INVOICE_READ")
            _conversion(session, wine_v1.id, "CASE", "BOTTLE", "12", "HUMAN")
            water_v1 = _packaging(session, products["WATER-06"].id, 1, status="ACTIVE", package_unit="CASE",
                                  pieces_per_package=6, piece_unit="BOTTLE", piece_content_value=Decimal("1"),
                                  piece_content_unit="L", sale_unit="CASE", price_basis_unit="CASE", origin="HUMAN",
                                  confirmed_by="Test Reviewer", confirmed_at=datetime.now(UTC))
            _conversion(session, water_v1.id, "CASE", "BOTTLE", "6", "HUMAN")
            salame_v1 = _packaging(session, products["SAL-03"].id, 1, status="ACTIVE", package_unit="CASE",
                                   pieces_per_package=3, piece_unit="PIECE", piece_content_value=Decimal("2.5"),
                                   piece_content_unit="LB", sale_unit="CASE", price_basis_unit="LB",
                                   is_variable_weight=True, origin="HUMAN", confirmed_by="Test Reviewer")
            _conversion(session, salame_v1.id, "CASE", "LB", "7.5", "CALCULATED", is_nominal=True)
            session.flush()
            result.check("product card: automatic packaging records the invoice line it came from",
                         wine_v1.source_purchase_line_id == bottle.id and len(wine_v1.conversions) == 2)
            result.check("product card: automatic packaging without its invoice line rejected",
                         _expect_integrity_error(session, lambda: m.SupplierProductPackaging(
                             supplier_product_id=products["WINE-01"].id, version=9, status="PROPOSED",
                             origin="INVOICE_READ")))
            result.check("product card: catch-weight equivalence marked nominal",
                         salame_v1.is_variable_weight and salame_v1.conversions[0].is_nominal)

            # --- Derived values with provenance ---
            session.add(m.PurchasedLineDerivedValue(
                purchase_document_id=document.id, purchase_line_id=case.id, field_name="piece_content_value",
                value_numeric=Decimal("1"), unit="L", provenance="PRODUCT_CARD", packaging_id=water_v1.id,
                created_by="test"))
            session.add(m.PurchasedLineDerivedValue(
                purchase_document_id=document.id, purchase_line_id=case.id, field_name="total_pieces",
                value_numeric=Decimal("12"), unit="BOTTLE", provenance="CALCULATED",
                calculation_formula="quantity * pack_count (purchase_unit = CASE = package unit)",
                calculation_inputs=[
                    {"field": "quantity", "provenance": "INVOICE_READ", "purchase_line_id": case.id, "value": "2"},
                    {"field": "purchase_unit", "provenance": "INVOICE_READ", "purchase_line_id": case.id, "value": "CASE"},
                    {"field": "pack_count", "provenance": "INVOICE_READ", "purchase_line_id": case.id, "value": "6"},
                ], created_by="test"))
            session.add(m.PurchasedLineDerivedValue(
                purchase_document_id=document.id, purchase_line_id=catch.id, field_name="nominal_weight",
                value_numeric=Decimal("15"), unit="LB", provenance="PRODUCT_CARD", packaging_id=salame_v1.id,
                created_by="test"))
            session.flush()
            derived = session.scalars(select(m.PurchasedLineDerivedValue).order_by(m.PurchasedLineDerivedValue.id)).all()
            result.check("provenance: product-card value points at the exact packaging version",
                         derived[0].provenance == "PRODUCT_CARD" and derived[0].packaging_id == water_v1.id)
            result.check("provenance: calculated total keeps formula and inputs (each with its provenance)",
                         derived[1].value_numeric == Decimal("12")
                         and {i["provenance"] for i in derived[1].calculation_inputs} == {"INVOICE_READ"})
            result.check("provenance: invoice line column untouched by derived values",
                         session.get(m.PurchaseLine, case.id).piece_content_value is None)
            result.check("guarantee: standard weight cannot be stored as actual weight",
                         _expect_integrity_error(session, lambda: m.PurchasedLineDerivedValue(
                             purchase_document_id=document.id, purchase_line_id=catch.id, field_name="actual_weight",
                             value_numeric=Decimal("15"), unit="LB", provenance="PRODUCT_CARD", packaging_id=salame_v1.id)))
            result.check("guarantee: calculated value without inputs rejected",
                         _expect_integrity_error(session, lambda: m.PurchasedLineDerivedValue(
                             purchase_document_id=document.id, purchase_line_id=case_no_unit.id,
                             field_name="total_pieces", value_numeric=Decimal("12"), provenance="CALCULATED")))
            result.check("guarantee: product-card value without packaging version rejected",
                         _expect_integrity_error(session, lambda: m.PurchasedLineDerivedValue(
                             purchase_document_id=document.id, purchase_line_id=case.id,
                             field_name="piece_content_value", value_numeric=Decimal("1"), provenance="PRODUCT_CARD")))
            result.check("guarantee: a derived value with no value at all rejected (missing is not zero)",
                         _expect_integrity_error(session, lambda: m.PurchasedLineDerivedValue(
                             purchase_document_id=document.id, purchase_line_id=case.id, field_name="total_pieces",
                             provenance="CALCULATED", calculation_formula="x", calculation_inputs=[])))

            # --- Human: confirmation/entry keeps the original extracted value ---
            session.add(m.PurchasedFieldCorrection(
                purchase_document_id=document.id, purchase_line_id=catch.id, field_name="actual_weight_unit",
                classification="UNREAD", original_value=None, corrected_value="LB", reviewed_by="Test Reviewer"))
            session.add(m.PurchasedFieldCorrection(
                purchase_document_id=document.id, purchase_line_id=bottle.id, field_name="quantity",
                classification="INCORRECT", original_value="6", corrected_value="5", reviewed_by="Test Reviewer"))
            session.flush()
            corrections = repo.resolve_latest_field_corrections(session, document.id)
            result.check("human: corrected value effective, original extracted value preserved",
                         repo.effective_field_value(corrections, bottle.id, "quantity", "6") == "5"
                         and session.get(m.PurchaseLine, bottle.id).quantity == Decimal("6"))

            # --- Uncertain / conflicting data flags ---
            flag = repo.add_validation_log_entry(session, purchase_document_id=document.id, severity="WARNING",
                                                 message="Quantity unit not printed: total pieces not derivable",
                                                 purchase_line_id=case_no_unit.id)
            flag.field_name, flag.issue_type = "purchase_unit", "UNCERTAIN"
            session.add(m.PurchasingValidationLogEntry(
                purchase_document_id=document.id, purchase_line_id=catch.id, severity="WARNING",
                message="Two different actual weights read", field_name="actual_weight_value", issue_type="CONFLICT",
                observed_values=[{"value": "16.08", "page": 1}, {"value": "16.80", "page": 1}], status="OPEN"))
            session.flush()
            flags = session.scalars(select(m.PurchasingValidationLogEntry).where(
                m.PurchasingValidationLogEntry.issue_type.is_not(None))).all()
            result.check("flags: uncertain and conflicting fields recorded with competing values",
                         {(f.field_name, f.issue_type) for f in flags}
                         == {("purchase_unit", "UNCERTAIN"), ("actual_weight_value", "CONFLICT")}
                         and any(f.observed_values and len(f.observed_values) == 2 for f in flags))
            result.check("flags: no total pieces derived for the line with an unprinted unit",
                         not any(d.purchase_line_id == case_no_unit.id for d in session.scalars(
                             select(m.PurchasedLineDerivedValue)).all()))

            # --- Packaging change: new version, earlier invoice unchanged ---
            water_v2 = _packaging(session, products["WATER-06"].id, 2, status="ACTIVE", package_unit="CASE",
                                  pieces_per_package=4, piece_unit="BOTTLE", piece_content_value=Decimal("1.5"),
                                  piece_content_unit="L", sale_unit="CASE", price_basis_unit="CASE", origin="HUMAN",
                                  confirmed_by="Test Reviewer")
            water_v1.status, water_v1.superseded_by_packaging_id = "SUPERSEDED", water_v2.id
            water_v1.superseded_at = datetime.now(UTC)
            session.flush()
            old_value = session.scalars(select(m.PurchasedLineDerivedValue).where(
                m.PurchasedLineDerivedValue.purchase_line_id == case.id,
                m.PurchasedLineDerivedValue.field_name == "piece_content_value")).one()
            result.check("packaging change: old invoice still points at version 1 (1 L), line unchanged",
                         old_value.packaging_id == water_v1.id and old_value.value_numeric == Decimal("1")
                         and session.get(m.PurchaseLine, case.id).pack_count == 6)
            result.check("packaging change: version 1 superseded by version 2, both kept",
                         water_v1.status == "SUPERSEDED" and water_v1.superseded_by_packaging_id == water_v2.id
                         and len(session.scalars(select(m.SupplierProductPackaging).where(
                             m.SupplierProductPackaging.supplier_product_id == products["WATER-06"].id)).all()) == 2)
            result.check("packaging change: duplicate version number rejected",
                         _expect_integrity_error(session, lambda: m.SupplierProductPackaging(
                             supplier_product_id=products["WATER-06"].id, version=2, status="PROPOSED", origin="HUMAN")))
            session.commit()
        engine.dispose()
    finally:
        cleanup_disposable_test_database_url(url)


def main() -> int:
    result = Result()
    test_migration_preserves_data(result)
    test_representation(result)
    for description in result.passed:
        print(f"PASS  {description}")
    for description in result.failed:
        print(f"FAIL  {description}")
    print(f"\n{len(result.passed)} passed, {len(result.failed)} failed")
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
