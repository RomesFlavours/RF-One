#!/usr/bin/env python
"""HTTP-level checks for Restaurant > Wines (RESTAURANT_WINES_FIRST_RELEASE_001).

Mirrors this app's own test convention: throwaway SQLite database created
before `app.py` is imported, migrated explicitly, Werkzeug's Flask test
client, `main()` returning an exit code. Never touches AWS or any shared
database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_restaurant_wines_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "restaurant-wines-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import legal_entity_service  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.restaurant_wines import wine_types  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    resp = client.get("/login")
    csrf = extract_csrf(resp.data)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


def wine_form(csrf, type_id, producer, label="", vintage="2021", cost="", **extra):
    form = {
        "csrf_token": csrf, "wine_type_id": str(type_id), "producer": producer, "label_name": label,
        "vintage_year": vintage, "category": "RED", "style": "STILL", "denomination": "DOCG",
        "region": "Veneto", "bottle_size_ml": "750", "supplier_name": "BBC", "cost_usd": cost,
        "cost_date": "2026-10-01" if cost else "", "availability": "AVAILABLE", "notes": "internal note",
    }
    form.update(extra)
    return form


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            wine_user = account_service.create_account(
                s, username="wines1", display_name="Wine Manager", password="WinesPass123!", status="ACTIVE",
            )
            account_service.set_domain_access(s, account_id=wine_user.id, domain_code="WINES", enabled=True, role_code=None)
            account_service.create_account(
                s, username="plain1", display_name="Plain One", password="PlainPass123!", status="ACTIVE",
            )
            rfwp = legal_entity_service.create_legal_entity(s, legal_name="RFWP")
            rfmd = legal_entity_service.create_legal_entity(s, legal_name="RFMD LLC")
            wine_types.seed_reference_wine_types(s)
            s.commit()
            rfwp_id, rfmd_id = rfwp.id, rfmd.id
            amarone_id = wine_types.find_type_by_name(s, "Amarone").id

        # ---- Access ------------------------------------------------------
        plain = web_app.app.test_client()
        login(plain, "plain1", "PlainPass123!")
        check("an account without WINES access gets 403", plain.get("/restaurant/wines").status_code == 403)
        check("Home does not show Wines without access", b'href="/restaurant/wines"' not in plain.get("/").data)

        c = web_app.app.test_client()
        login(c, "wines1", "WinesPass123!")
        check("Home shows the Wines card with access", b'href="/restaurant/wines"' in c.get("/").data)
        for path in ("/restaurant/wines", "/restaurant/wines/availability", "/restaurant/wines/types"):
            resp = c.get(path)
            check(f"{path} renders", resp.status_code == 200, str(resp.status_code))
        page = c.get("/restaurant/wines/types").data.decode()
        check("breadcrumb RF-One > Wines > Wine Types", 'href="/restaurant/wines">Wines</a>' in page and "Wine Types</span>" in page)
        check("pages load the shared busy indicator", "js/rf-one-busy.js" in page)
        csrf = extract_csrf(c.get("/restaurant/wines/availability").data)

        avail = c.get("/restaurant/wines/availability").data.decode()
        check("'Upload file' is shown disabled with its reason",
              re.search(r"<button[^>]*disabled[^>]*>Upload file</button>", avail) is not None
              and "waiting for a sample file" in avail)

        # ---- Types -------------------------------------------------------
        resp = c.post("/restaurant/wines/types/new", data={"csrf_token": csrf, "standard_name": "pinot gris", "aliases": ""})
        check("a new type under an existing alias is refused (Pinot Gris)", resp.status_code == 400 and not resp.json["ok"])
        resp = c.post("/restaurant/wines/types/new", data={"csrf_token": csrf, "standard_name": "Etna Rosso", "aliases": "Etna Rosso DOC"})
        check("a new type is created from the dialog and returned for immediate selection",
              resp.status_code == 200 and resp.json["ok"] and resp.json["type"]["name"] == "Etna Rosso"
              and resp.json["type"]["aliases"] == ["Etna Rosso DOC"])
        etna_id = resp.json["type"]["id"]
        resp = c.post("/restaurant/wines/types/new", data={"csrf_token": "wrong", "standard_name": "Xyz"})
        check("type save without a valid CSRF token is refused", resp.status_code == 400)

        # ---- Catalog -----------------------------------------------------
        r1 = c.post("/restaurant/wines/availability/new", data=wine_form(csrf, amarone_id, "Domini Veneti", cost="42"))
        r2 = c.post("/restaurant/wines/availability/new", data=wine_form(csrf, amarone_id, "Venturini", vintage="2019", cost="47"))
        check("two labels of the same type are both saved", r1.json["ok"] and r2.json["ok"], f"{r1.json} {r2.json}")
        w1, w2 = r1.json["wine"]["id"], r2.json["wine"]["id"]
        dup = c.post("/restaurant/wines/availability/new", data=wine_form(csrf, amarone_id, "domini veneti", cost="40"))
        check("a duplicate wine is refused with a readable message",
              dup.status_code == 400 and "already in the catalog" in dup.json["error"])
        r3 = c.post("/restaurant/wines/availability/new", data=wine_form(csrf, etna_id, "Benanti", vintage="", non_vintage="1"))
        check("unknown cost + non-vintage wine is saved", r3.json["ok"] and r3.json["wine"]["vintage_label"] == "NV"
              and r3.json["wine"]["cost_known"] is False)
        w3 = r3.json["wine"]["id"]
        bad = c.post("/restaurant/wines/availability/new", data=wine_form(csrf, amarone_id, "Allegrini", vintage=""))
        check("vintage is required unless non-vintage", bad.status_code == 400)
        c.get("/restaurant/wines/types")  # shows (and clears) the confirmations flashed by the saves above
        search = c.get("/restaurant/wines/availability?q=venturini").data.decode()
        check("catalog search filters", "Venturini" in search and "Domini Veneti" not in search)

        # ---- Wine lists --------------------------------------------------
        resp = c.post("/restaurant/wines/lists/new", data={
            "csrf_token": csrf, "entity_id": rfwp_id, "effective_from": "2026-01-01", "mode": "EMPTY"})
        check("a Wine list is created", resp.status_code == 302)
        with SessionFactory() as s:
            wp_list = s.query(m.WineList).filter_by(legal_entity_id=rfwp_id).one()
            wp_list_id = wp_list.id
        resp = c.post(f"/restaurant/wines/lists/{wp_list_id}/items/new", data={
            "csrf_token": csrf, "wine_id": w1, "cost_used": "42", "value_factor": "1.05", "sells_by_glass": "1",
            "applied_bottle": "110", "applied_glass": "31"})
        check("wine added to the list", resp.status_code == 200 and resp.json["ok"], str(resp.json))
        resp = c.post(f"/restaurant/wines/lists/{wp_list_id}/items/new", data={
            "csrf_token": csrf, "wine_id": w1, "cost_used": "42", "value_factor": "1"})
        check("the same wine cannot be added twice to one list", resp.status_code == 400)
        c.post(f"/restaurant/wines/lists/{wp_list_id}/items/new", data={
            "csrf_token": csrf, "wine_id": w2, "cost_used": "47", "value_factor": "1", "applied_bottle": "125"})
        c.post(f"/restaurant/wines/lists/{wp_list_id}/items/new", data={
            "csrf_token": csrf, "wine_id": w3, "cost_used": "", "value_factor": "1", "sells_by_glass": "1"})

        page = c.get(f"/restaurant/wines?entity={rfwp_id}").data.decode()
        check("Wine list shows $110 bottle and $31 glass for $42 / Value 1.05", "$110" in page and "$31" in page)
        check("a row without a valid cost shows prices to complete", "To complete" in page)
        preview = c.get("/restaurant/wines/price-preview?cost=42&value=1.05").json
        check("price preview uses the same formula", (preview["bottle"], preview["glass"]) == (110, 31), str(preview))
        preview = c.get("/restaurant/wines/price-preview?cost=1&value=1").json
        check("price preview: cost 1 has no price", preview["bottle"] is None and preview["ok"])

        c.get("/restaurant/wines/types")  # clears pending confirmations
        other = c.get(f"/restaurant/wines?entity={rfmd_id}").data.decode()
        check("another Entity does not see RFWP's list", "<tbody>" not in other and "RFMD LLC has no Wine list yet" in other)
        resp = c.post("/restaurant/wines/lists/new", data={
            "csrf_token": csrf, "entity_id": rfwp_id, "effective_from": "2026-01-01", "mode": "EMPTY"}, follow_redirects=True)
        check("duplicate effective date for the same Entity is refused", b"already has a Wine list effective from" in resp.data)

        # Catalog cost change -> signalled, prices kept
        c.post(f"/restaurant/wines/availability/{w1}", data=wine_form(csrf, amarone_id, "Domini Veneti", cost="50"))
        page = c.get(f"/restaurant/wines?entity={rfwp_id}").data.decode()
        check("after a catalog cost change the saved prices stay and the change is signalled",
              "$110" in page and "Catalog now $50" in page and "Adopt and recalculate" in page)

        # Future version as a copy of the current one
        resp = c.post("/restaurant/wines/lists/new", data={
            "csrf_token": csrf, "entity_id": rfwp_id, "effective_from": "2099-01-01", "mode": "COPY_ACTIVE"})
        with SessionFactory() as s:
            future = s.query(m.WineList).filter_by(legal_entity_id=rfwp_id, effective_from=date(2099, 1, 1)).one()
            future_id = future.id
            copied = {i.wine_id: i.id for i in future.items}
        check("a future copy keeps all rows", len(copied) == 3)
        page = c.get(f"/restaurant/wines?entity={rfwp_id}").data.decode()
        check("without a list selected, the one in effect is shown (not the future one)",
              "Wine list from 2026-01-01" in page and "Prepared (future)" in page)

        resp = c.post(f"/restaurant/wines/items/{copied[w1]}/adopt-catalog-cost", data={"csrf_token": csrf})
        resp = c.post(f"/restaurant/wines/items/{copied[w2]}/delete", data={"csrf_token": csrf})
        with SessionFactory() as s:
            adopted = s.get(m.WineListItem, copied[w1])
            check("adopting the catalog cost recalculates the future row",
                  adopted.cost_used == 50 and adopted.calculated_bottle_price != 110)
            check("the current list is untouched",
                  s.query(m.WineListItem).filter_by(wine_list_id=wp_list_id).count() == 3)
            check("deleting a row keeps the wine in the catalog",
                  s.get(m.WineListItem, copied[w2]) is None and s.get(m.Wine, w2) is not None)
            manual_row = s.query(m.WineListItem).filter_by(wine_list_id=wp_list_id, wine_id=w2).one()
            manual_id = manual_row.id
        resp = c.post(f"/restaurant/wines/items/{manual_id}", data={
            "csrf_token": csrf, "cost_used": "47", "value_factor": "1.1", "applied_bottle": "125"})
        with SessionFactory() as s:
            row = s.get(m.WineListItem, manual_id)
            check("editing Value keeps a hand-set applied price", row.applied_bottle_price == 125 and row.bottle_price_manual)
        c.post(f"/restaurant/wines/items/{manual_id}/restore-calculated", data={"csrf_token": csrf})
        with SessionFactory() as s:
            row = s.get(m.WineListItem, manual_id)
            check("restore puts the calculated price back", not row.bottle_price_manual
                  and row.applied_bottle_price == row.calculated_bottle_price)

        # Export
        resp = c.get(f"/restaurant/wines/lists/{wp_list_id}/export.csv")
        text = resp.data.decode("utf-8-sig")
        check("export is a CSV download", resp.status_code == 200 and resp.mimetype == "text/csv"
              and "attachment" in resp.headers.get("Content-Disposition", ""))
        check("export has the menu columns and prices",
              text.splitlines()[0].startswith("Entity,Effective from,Category,Type,Label,Producer,Vintage")
              and "RFWP,2026-01-01,Red,Amarone,,Domini Veneti,2021,750,110,31" in text, text)
        check("export carries no cost, Value or notes", "internal note" not in text and "1.05" not in text and ",42," not in text)
        resp = c.get(f"/restaurant/wines/lists/{future_id}/export.csv")
        check("a future version can be exported too", resp.status_code == 200)
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
