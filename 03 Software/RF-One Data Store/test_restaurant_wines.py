#!/usr/bin/env python
"""Restaurant Wines — service-level checks (RESTAURANT_WINES_FIRST_RELEASE_001).

Runs on a disposable SQLite database (never the shared one):

    python test_restaurant_wines.py

Covers: the price formula against every distinct case computed by
`Wine.xlsb` (Price Calculator sheet), missing/invalid costs, the type
registry (aliases, no duplicates, repeatable initial load), the catalog
duplicate check, Wine list versions per Entity (active / future / copy /
duplicate date), applied vs calculated prices, and the export.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal as D

from rfone_data_store import legal_entity_service
from rfone_data_store import models as m
from rfone_data_store.database import (
    cleanup_disposable_test_database_url, create_configured_engine, create_session_factory,
    resolve_test_database_url,
)
from rfone_data_store.restaurant_wines import catalog, wine_lists, wine_types
from rfone_data_store.restaurant_wines.pricing import PricingParameters, calculate_prices

# (cost, Value, bottle price, glass price) — every distinct row the workbook
# computed in its Price Calculator sheet (Wine.xlsb of 2026-02-14).
XLSB_CASES = (
    ("4.5", "1.2", 38, 11),
    ("5", "1.5", 62, 18),
    ("6", "1", 30, 8),
    ("6", "1.2", 43, 12),
    ("6", "1.4", 58, 17),
    ("7", "1.23", 48, 14),
    ("7", "1.5", 72, 20),
    ("8", "1", 34, 10),
    ("8", "1.1", 41, 12),
    ("9", "1", 36, 10),
    ("9", "1.05", 40, 11),
    ("10", "1", 38, 11),
    ("10", "1.05", 42, 12),
    ("10", "1.1", 46, 13),
    ("11", "1", 41, 12),
    ("11", "1.1", 49, 14),
    ("12", "1", 43, 12),
    ("12", "1.02", 44, 13),
    ("12", "1.05", 47, 13),
    ("12", "1.08", 50, 14),
    ("12", "1.14", 55, 16),
    ("12", "1.35", 78, 22),
    ("12.5", "1.25", 68, 20),
    ("13", "1", 45, 13),
    ("14", "1", 47, 13),
    ("15", "1", 49, 14),
    ("15", "1.08", 57, 16),
    ("15", "1.1", 59, 17),
    ("15", "1.15", 65, 19),
    ("15.5", "1.1", 61, 17),
    ("16", "1", 51, 15),
    ("16", "1.08", 60, 17),
    ("16.5", "1", 52, 15),
    ("17", "1.02", 55, 16),
    ("18", "1", 55, 16),
    ("18", "1.12", 69, 20),
    ("19", "1", 57, 16),
    ("19.5", "1.05", 64, 18),
    ("20", "1.1", 71, 20),
    ("20", "1.17", 81, 23),
    ("21", "1", 61, 17),
    ("22", "1", 63, 18),
    ("22", "1.05", 69, 20),
    ("22", "1.1", 76, 22),
    ("23", "1", 65, 19),
    ("23", "1.05", 72, 20),
    ("24", "1", 67, 19),
    ("24.1", "1.05", 74, 21),
    ("25", "1.05", 76, 22),
    ("25.6666666666667", "1", 70, 20),
    ("26", "1", 71, 20),
    ("26", "1.05", 78, 22),
    ("28", "1", 74, 21),
    ("29", "1", 76, 22),
    ("29", "1.04", 82, 24),
    ("29", "1.05", 84, 24),
    ("30.4", "0.95", 71, 20),
    ("31", "0.9", 65, 18),
    ("32", "0.982", 79, 22),
    ("32", "1", 82, 23),
    ("32", "1.05", 90, 26),
    ("33", "1.045", 91, 26),
    ("34", "0.96", 79, 22),
    ("34", "1", 85, 24),
    ("35", "1", 87, 25),
    ("38", "1", 92, 26),
    ("42", "1", 99, 28),
    ("42", "1.04", 107, 31),
    ("42", "1.05", 110, 31),
    ("44", "1", 103, 29),
    ("45", "1.005", 106, 30),
    ("47", "1.05", 119, 34),
    ("50", "1", 113, 32),
    ("55", "1", 121, 35),
    ("65", "1", 138, 39),
    ("73", "1", 150, 43),
)

PARAMS = PricingParameters(D("1.3"), D("900"), D("3.5"))
TODAY = date(2026, 10, 8)


def wine_input(type_id, producer, label=None, vintage=2021, nv=False, size=750, cost=None, category="RED"):
    return catalog.WineInput(
        wine_type_id=type_id, producer=producer, label_name=label, vintage_year=None if nv else vintage,
        non_vintage=nv, category=category, style="STILL", denomination="DOCG", region=None,
        bottle_size_ml=size, supplier_name="BBC", cost_usd=cost, cost_date=TODAY if cost is not None else None,
        availability="AVAILABLE", notes="internal note",
    )


def main() -> int:
    failures: list[str] = []
    passed = 0

    def check(description: str, condition: bool, detail: str = "") -> None:
        nonlocal passed
        if condition:
            passed += 1
        else:
            failures.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    # ---- Pricing: exact reproduction of the workbook -------------------
    mismatches = []
    for cost, value, bottle, glass in XLSB_CASES:
        got = calculate_prices(D(cost), D(value), PARAMS)
        if (got.bottle, got.glass) != (bottle, glass):
            mismatches.append((cost, value, (got.bottle, got.glass), (bottle, glass)))
    check(f"all {len(XLSB_CASES)} Wine.xlsb price cases reproduced exactly", not mismatches, str(mismatches[:3]))
    got = calculate_prices(D("42"), D("1.05"), PARAMS)
    check("mandatory example: $42, Value 1.05 -> bottle $110, glass $31", (got.bottle, got.glass) == (110, 31), str(got))
    v1 = calculate_prices(D("42"), D("1"), PARAMS)
    check("Value is applied squared: Value 1 -> $99 (99.35), Value 1.05 -> 99.35 x 1.1025 = 109.53 -> $110", v1.bottle == 99 and got.bottle == 110, str(v1))
    for bad in (None, D("0"), D("1"), D("0.5")):
        r = calculate_prices(bad, D("1"), PARAMS)
        check(f"cost {bad} gives no price (not 0, not negative, no error)", r.bottle is None and r.glass is None)
    check("not sold by the glass -> no glass price",
          calculate_prices(D("42"), D("1.05"), PARAMS, sells_by_glass=False).glass is None)
    try:
        calculate_prices(D("42"), D("0"), PARAMS)
        check("Value 0 is refused", False)
    except ValueError:
        check("Value 0 is refused", True)

    url = resolve_test_database_url("restaurant_wines")
    try:
        factory = create_session_factory(create_configured_engine(url))
        with factory() as s:
            # ---- Types ---------------------------------------------------
            first = wine_types.seed_reference_wine_types(s)
            second = wine_types.seed_reference_wine_types(s)
            s.commit()
            total = s.query(m.WineType).count()
            check("initial load creates the 67 types of the Base sheet", len(first.created) == 67 and total == 67, str(total))
            check("initial load is repeatable (second run creates nothing)", not second.created and not second.names_added and total == 67)
            check("misspelling kept as alternative name: 'Malbech' -> Malbec",
                  wine_types.find_type_by_name(s, "Malbech").standard_name == "Malbec")
            pinot = wine_types.find_type_by_name(s, "pinot gris")
            check("'Pinot Gris' resolves to Pinot Grigio", pinot is not None and pinot.standard_name == "Pinot Grigio")
            for duplicate in ("Pinot Gris", "  pinot   GRIGIO ", "Gewurztraminer"):
                try:
                    wine_types.create_wine_type(s, standard_name=duplicate)
                    check(f"{duplicate!r} cannot become a new type", False)
                except wine_types.WineTypeError:
                    s.rollback()
                    check(f"{duplicate!r} cannot become a new type", True)
            amarone = wine_types.find_type_by_name(s, "Amarone")
            try:
                wine_types.update_wine_type(s, amarone, standard_name="Amarone", aliases=["Pinot Gris"])
                check("an alias already used by another type is refused", False)
            except wine_types.WineTypeError:
                s.rollback()
                check("an alias already used by another type is refused", True)
            new_type = wine_types.create_wine_type(s, standard_name="Etna Rosso", aliases=["Etna Rosso DOC", "etna rosso"])
            check("repeated alias collapsed, distinct alias kept", new_type.aliases == ["Etna Rosso DOC"], str(new_type.aliases))
            s.commit()

            # ---- Catalog -------------------------------------------------
            amarone = wine_types.find_type_by_name(s, "Amarone")
            w1 = catalog.create_wine(s, wine_input(amarone.id, "Domini Veneti", cost=D("42")))
            w2 = catalog.create_wine(s, wine_input(amarone.id, "Venturini", cost=D("47"), vintage=2019))
            w3 = catalog.create_wine(s, wine_input(amarone.id, "Domini Veneti", label="Riserva", cost=None))
            s.commit()
            check("two labels of the same type are both catalogued", w1.id != w2.id and w1.wine_type_id == w2.wine_type_id)
            check("unknown cost is stored as NULL, not 0", w3.cost_usd is None)
            try:
                catalog.create_wine(s, wine_input(amarone.id, " domini  veneti ", cost=D("40")))
                check("same type/producer/label/vintage/format is refused as a duplicate", False)
            except catalog.DuplicateWineError as exc:
                s.rollback()
                check("same type/producer/label/vintage/format is refused as a duplicate", exc.existing_wine_id == w1.id)
            w_magnum = catalog.create_wine(s, wine_input(amarone.id, "Domini Veneti", size=1500, cost=D("90")))
            w_zero = catalog.create_wine(s, wine_input(wine_types.find_type_by_name(s, "Soave").id, "Pieropan",
                                                       nv=True, cost=D("0"), category="WHITE"))
            s.commit()
            check("same wine in another format is a different wine", w_magnum.id != w1.id)
            check("cost 0 is kept distinct from unknown", w_zero.cost_usd == D("0") and w_zero.vintage_label == "NV")

            # ---- Wine lists ----------------------------------------------
            rfwp = legal_entity_service.create_legal_entity(s, legal_name="RFWP")
            rfmd = legal_entity_service.create_legal_entity(s, legal_name="RFMD LLC")
            s.commit()
            v_now = wine_lists.create_version(s, legal_entity_id=rfwp.id, effective_from=date(2026, 10, 1),
                                              mode=wine_lists.MODE_EMPTY, today=TODAY)
            item = wine_lists.add_item(s, v_now, wine_id=w1.id, cost_used=w1.cost_usd, value_factor=D("1.05"),
                                       sells_by_glass=True, today=TODAY)
            s.commit()
            check("added row: calculated = applied = $110 / $31",
                  (item.calculated_bottle_price, item.calculated_glass_price) == (110, 31)
                  and (item.applied_bottle_price, item.applied_glass_price) == (D("110"), D("31"))
                  and not item.bottle_price_manual and not item.glass_price_manual)
            try:
                wine_lists.add_item(s, v_now, wine_id=w1.id, cost_used=D("42"), value_factor=D("1"),
                                    sells_by_glass=False, today=TODAY)
                check("the same wine cannot appear twice on one list", False)
            except wine_lists.WineListError:
                s.rollback()
                check("the same wine cannot appear twice on one list", True)
            unknown = wine_lists.add_item(s, v_now, wine_id=w3.id, cost_used=None, value_factor=D("1"),
                                          sells_by_glass=True, today=TODAY)
            check("unknown cost: row saved, prices left to complete (None)",
                  unknown.calculated_bottle_price is None and unknown.applied_bottle_price is None)
            wine_lists.add_item(s, v_now, wine_id=w2.id, cost_used=w2.cost_usd, value_factor=D("1"),
                                sells_by_glass=False, applied_bottle=D("125"), today=TODAY)
            s.commit()
            manual = s.query(m.WineListItem).filter_by(wine_list_id=v_now.id, wine_id=w2.id).one()
            check("an applied price typed by hand is marked manual",
                  manual.bottle_price_manual and manual.applied_bottle_price == D("125"))

            # Separation between Entities
            md = wine_lists.create_version(s, legal_entity_id=rfmd.id, effective_from=date(2026, 10, 1),
                                           mode=wine_lists.MODE_EMPTY, today=TODAY)
            s.commit()
            check("same effective date allowed for another Entity", md.id != v_now.id)
            check("Entities keep separate lists", len(wine_lists.list_items(s, md.id)) == 0
                  and len(wine_lists.list_items(s, v_now.id)) == 3)
            try:
                wine_lists.create_version(s, legal_entity_id=rfwp.id, effective_from=date(2026, 10, 1),
                                          mode=wine_lists.MODE_EMPTY, today=TODAY)
                check("duplicate effective date for one Entity is refused", False)
            except wine_lists.WineListError:
                s.rollback()
                check("duplicate effective date for one Entity is refused", True)

            # Catalog cost change: saved prices do not move
            w1 = s.get(m.Wine, w1.id)
            catalog.update_wine(s, w1, wine_input(amarone.id, "Domini Veneti", cost=D("50")))
            w2 = s.get(m.Wine, w2.id)
            catalog.update_wine(s, w2, wine_input(amarone.id, "Venturini", cost=D("52"), vintage=2019))
            s.commit()
            item = s.get(m.WineListItem, item.id)
            check("catalog cost update does not alter saved prices",
                  item.cost_used == D("42") and item.applied_bottle_price == D("110"))
            check("catalog cost update is signalled", wine_lists.catalog_cost_changed(item))

            # Future version, copy
            future = wine_lists.create_version(s, legal_entity_id=rfwp.id, effective_from=date(2026, 11, 1),
                                               mode=wine_lists.MODE_COPY_ACTIVE, today=TODAY)
            s.commit()
            check("the active list is still the current one while a future one is prepared",
                  wine_lists.active_version(s, rfwp.id, TODAY).id == v_now.id)
            check("future list becomes active on its date",
                  wine_lists.active_version(s, rfwp.id, date(2026, 11, 1)).id == future.id)
            copied = {i.wine_id: i for i in wine_lists.list_items(s, future.id)}
            check("copy keeps rows, costs, Value and prices (manual ones stay manual)",
                  len(copied) == 3 and copied[w1.id].applied_bottle_price == D("110")
                  and copied[w2.id].bottle_price_manual and copied[w1.id].value_factor == D("1.05"))

            # Adopt catalog cost on the future version: manual price kept
            wine_lists.adopt_catalog_cost(s, copied[w1.id], today=TODAY)
            wine_lists.adopt_catalog_cost(s, copied[w2.id], today=TODAY)
            s.commit()
            check("adopting the catalog cost recalculates an automatic price",
                  copied[w1.id].cost_used == D("50") and copied[w1.id].applied_bottle_price
                  == D(calculate_prices(D("50"), D("1.05"), PARAMS).bottle))
            check("adopting the catalog cost keeps a hand-set price",
                  copied[w2.id].applied_bottle_price == D("125") and copied[w2.id].bottle_price_manual
                  and copied[w2.id].calculated_bottle_price == calculate_prices(D("52"), D("1"), PARAMS).bottle)
            check("the previous version is untouched", s.get(m.WineListItem, item.id).cost_used == D("42"))
            wine_lists.restore_calculated(s, copied[w2.id], today=TODAY)
            s.commit()
            check("explicit restore puts the calculated price back",
                  not copied[w2.id].bottle_price_manual
                  and copied[w2.id].applied_bottle_price == D(copied[w2.id].calculated_bottle_price))

            # Edit: untouched applied price follows; Value change recalculates
            edited = wine_lists.update_item(s, copied[w1.id], cost_used=D("50"), value_factor=D("1"),
                                            sells_by_glass=False, applied_bottle=copied[w1.id].applied_bottle_price,
                                            applied_glass=None, today=TODAY)
            s.commit()
            check("edit with an untouched applied price follows the recalculation",
                  edited.applied_bottle_price == D(calculate_prices(D("50"), D("1"), PARAMS).bottle)
                  and not edited.bottle_price_manual)
            check("glass sale turned off -> no glass price", edited.applied_glass_price is None and edited.calculated_glass_price is None)

            # Parameters: stored per row
            wine_lists.update_settings(s, PricingParameters(D("1.4"), D("900"), D("3.5")))
            s.commit()
            item = s.get(m.WineListItem, item.id)
            check("changing the configuration does not alter saved rows",
                  item.applied_bottle_price == D("110") and item.coefficient_a == D("1.3"))
            check("changed configuration is signalled", wine_lists.parameters_changed(item, wine_lists.current_parameters(s)))
            wine_lists.update_settings(s, PARAMS)
            s.commit()

            # Remove from list only
            wine_lists.remove_item(s, copied[w1.id], today=TODAY)
            s.commit()
            check("removing a row keeps the wine in the catalog",
                  s.get(m.Wine, w1.id) is not None and len(wine_lists.list_items(s, future.id)) == 2
                  and len(wine_lists.list_items(s, v_now.id)) == 3)

            # Past versions are read only
            later_today = date(2026, 11, 2)
            try:
                wine_lists.remove_item(s, s.get(m.WineListItem, item.id), today=later_today)
                check("a previous version cannot be changed", False)
            except wine_lists.WineListError:
                s.rollback()
                check("a previous version cannot be changed", True)

            # Export
            text = wine_lists.export_csv(s, v_now)
            lines = text.strip().splitlines()
            check("export header", lines[0] == ",".join(wine_lists.EXPORT_HEADER), lines[0])
            check("export has prices but no cost, Value or notes",
                  "RFWP,2026-10-01,Red,Amarone,,Domini Veneti,2021,750,110,31" in lines
                  and "42" not in text.replace("2021", "") and "1.05" not in text and "internal note" not in text,
                  text)
            check("export leaves the glass price empty when not sold by the glass",
                  "RFWP,2026-10-01,Red,Amarone,,Venturini,2019,750,125," in lines, text)
    finally:
        cleanup_disposable_test_database_url(url)

    print(f"{passed} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
