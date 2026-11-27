#!/usr/bin/env python
"""Checks for Restaurant > Wines > Drink card (WINES_DRINK_CARD_001).

Same convention as `test_restaurant_wines_http.py`: throwaway SQLite
database created before `app.py` is imported, migrated explicitly, Flask
test client, `main()` returning an exit code. The AI call is replaced by a
local stand-in; nothing leaves this computer and no shared database is
touched. PDF text is read with pypdfium2."""

from __future__ import annotations

import json

import io
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
for path in (APP_DIR, BASE_DIR, os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))):
    if path not in sys.path:
        sys.path.insert(0, path)

_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_wine_card_test_")
os.close(_FD)
os.remove(_DB)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "wine-card-test-secret"
os.environ.pop("RFONE_UI_LANGUAGE", None)

import _wine_card_fixture as fixture  # noqa: E402

fixture.install_enrollment_stub()
fixture.install_sqlite_migration_shims()
from rfone_data_store.database import run_migrations_to_head  # noqa: E402

run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import pypdfium2 as pdfium  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.restaurant_wines import catalog, drink_card as dc, drink_card_ai  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    csrf = extract_csrf(client.get("/login").data)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201e5273de90000000049454e44ae426082"
)


def pdf_pages(data: bytes) -> list[str]:
    doc = pdfium.PdfDocument(data)
    return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]


def pdf_size(data: bytes) -> tuple[float, float]:
    doc = pdfium.PdfDocument(data)
    return doc[0].get_size()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            user = account_service.create_account(s, username="wines1", display_name="Wine Manager",
                                                  password="WinesPass123!", status="ACTIVE")
            account_service.set_domain_access(s, account_id=user.id, domain_code="WINES", enabled=True, role_code=None)
            account_service.create_account(s, username="plain1", display_name="Plain One",
                                           password="PlainPass123!", status="ACTIVE")
            ids = fixture.seed(s)
            # A second site of another Entity, without a Kitchen menu.
            from rfone_data_store import legal_entity_service
            other_entity = legal_entity_service.create_legal_entity(s, legal_name="RFMD LLC")
            merchant = m.Merchant(name="Mount Dora")
            s.add(merchant)
            s.flush()
            md = m.Location(merchant_id=merchant.id, name="Mount Dora", timezone="America/New_York")
            s.add(md)
            s.flush()
            md_restaurant = m.Restaurant(name="Rome's Flavours MD", legal_entity_id=other_entity.id)
            s.add(md_restaurant)
            s.flush()
            s.add(m.RestaurantLocation(restaurant_id=md_restaurant.id, location_id=md.id, is_primary=True))
            s.commit()
            md_id = md.id
        wp = ids["location_id"]
        brasato, vongole, tagliata = (ids["recipes"][k] for k in ("WP-001", "WP-002", "WP-003"))
        amarone, barolo, nebbiolo, gavi = (ids["wines"][k] for k in
                                           ("Cantina del Castello", "Az. Grimaldi Giacomo", "Carlo Alberto", "Castellari"))

        # ---- Access and page -----------------------------------------------
        plain = web_app.app.test_client()
        login(plain, "plain1", "PlainPass123!")
        check("an account without WINES access gets 403", plain.get("/restaurant/wines/card").status_code == 403)
        c = web_app.app.test_client()
        login(c, "wines1", "WinesPass123!")
        resp = c.get(f"/restaurant/wines/card?site={wp}")
        page = resp.data.decode()
        check("the Drink card page renders", resp.status_code == 200, str(resp.status_code))
        check("the page has its How Works link and help", "data-how-works" in page and 'id="wine-card"' in page)
        check("every window has its ? help", 'data-help-dialog="rf-help-review"' in page and 'data-help-dialog="rf-help-water"' in page
              and 'data-help-dialog="rf-help-beer"' in page and 'id="wine-card-beer"' in page
              and 'id="wine-card-review"' in page and 'id="wine-card-water"' in page)
        check("the Drink card tab is in the Wines header", 'href="/restaurant/wines/card"' in c.get("/restaurant/wines").data.decode())
        check("the site's active menu is named", "Winter Park Fall" in page and "3 dishes" in page)
        check("every wine of the Wine list is listed", page.count('data-review="') == len(fixture.WINES))
        csrf = extract_csrf(resp.data)

        # ---- Site change: wines and dishes of that site only ----------------
        md_page = c.get(f"/restaurant/wines/card?site={md_id}").data.decode()
        check("another site shows its own (empty) Wine list", "There is no Wine list in effect today for RFMD LLC" in md_page)
        check("a site without an active menu is warned", "automatic pairings are unavailable" in md_page)
        with SessionFactory() as s:
            check("dishes come only from the site's active menu",
                  [d.recipe_id for d in dc.menu_dishes(s, wp)] == [brasato, vongole, tagliata]
                  and dc.menu_dishes(s, md_id) == [])

        # ---- AI proposals and approval ---------------------------------------
        calls = []

        def fake_call(prompt):
            calls.append(prompt)
            return {"wines": [
                {"id": amarone, "description": "A rich Amarone with dried cherry and spice.", "dish_ids": [brasato]},
                {"id": barolo, "description": "A structured Nebbiolo with red cherry", "dish_ids": [brasato, 999999]},
                {"id": gavi, "description": "A crisp Cortese with citrus and green apple", "dish_ids": [vongole]},
            ]}

        original_call, original_configured = drink_card_ai._call, drink_card_ai.is_configured
        drink_card_ai._call = fake_call
        drink_card_ai.is_configured = lambda: True
        try:
            resp = c.post(f"/restaurant/wines/card/{wp}/propose", data={"csrf_token": csrf})
            check("Propose with AI redirects back", resp.status_code == 302)
            check("prices and suppliers are not sent to the AI", calls and "122" not in calls[0] and "cost" not in calls[0])
            check("the menu sent to the AI carries ingredients", calls and "clams" in calls[0])
            with SessionFactory() as s:
                site = dc.get_site(s, wp)
                rows = {w.wine.id: w for w in dc.card_wines(s, site, date(2026, 11, 24))}
            check("the proposal is stored (without its final period), not approved", rows[amarone].description == "A rich Amarone with dried cherry and spice"
                  and not rows[amarone].description_approved and not rows[amarone].pairings_reviewed)
            check("pairings are printed inside the description (Winter Park)",
                  rows[amarone].printed_description() == "A rich Amarone with dried cherry and spice, ideal with Brasato al Barolo.")
            check("a dish id outside the menu is dropped", [d.recipe_id for d in rows[barolo].pairings] == [brasato])

            # A person approves Gavi with no dish and a new text.
            resp = c.post(f"/restaurant/wines/card/{wp}/wines/{gavi}", data={
                "csrf_token": csrf, "description": "A crisp Gavi with citrus notes", "recipe_id": ["", ""]})
            check("the review window saves and approves", resp.status_code == 200 and resp.json["ok"], str(resp.data[:200]))
            resp = c.post(f"/restaurant/wines/card/{wp}/wines/{gavi}", data={
                "csrf_token": csrf, "description": "x" * 161, "recipe_id": [""]})
            check("a description over 160 characters is refused in the window", resp.status_code == 400 and "160" in resp.json["error"])
            resp = c.post(f"/restaurant/wines/card/{wp}/wines/{gavi}", data={
                "csrf_token": csrf, "description": "ok", "recipe_id": [str(brasato), str(vongole), str(tagliata)]})
            check("more than two dishes is refused", resp.status_code == 400)

            # Regenerating keeps what was approved.
            def fake_call_2(prompt):
                return {"wines": [
                    {"id": gavi, "description": "SHOULD NOT REPLACE", "dish_ids": [tagliata]},
                    {"id": amarone, "description": "A second proposal", "dish_ids": [tagliata]},
                    {"id": barolo, "description": "A Barolo proposal", "dish_ids": []},
                ]}
            drink_card_ai._call = fake_call_2
            c.post(f"/restaurant/wines/card/{wp}/propose", data={"csrf_token": csrf})
            with SessionFactory() as s:
                rows = {w.wine.id: w for w in dc.card_wines(s, dc.get_site(s, wp), date(2026, 11, 24))}
            check("regeneration keeps the approved description and the reviewed 'no dish' choice",
                  rows[gavi].description == "A crisp Gavi with citrus notes" and rows[gavi].pairings == [])
            check("regeneration updates a proposal not yet approved",
                  rows[amarone].description == "A second proposal" and [d.recipe_id for d in rows[amarone].pairings] == [tagliata])

            resp = c.post(f"/restaurant/wines/card/{wp}/approve-all", data={"csrf_token": csrf})
            with SessionFactory() as s:
                rows = {w.wine.id: w for w in dc.card_wines(s, dc.get_site(s, wp), date(2026, 11, 24))}
            check("Approve all approves the proposals", rows[amarone].description_approved and rows[amarone].pairings_reviewed)
            check("Approve all leaves a wine without dishes waiting for a proposal",
                  rows[barolo].description_approved and rows[barolo].pairings == [] and not rows[barolo].pairings_reviewed)

            # Proposing the missing pairings keeps the approved description and
            # takes the dishes from the site's active menu only.
            sent = []
            def fake_call_3(prompt):
                sent.append(json.loads(prompt))
                return {"wines": [{"id": barolo, "description": "SHOULD NOT REPLACE", "dish_ids": [brasato, 999999]}]}
            drink_card_ai._call = fake_call_3
            c.post(f"/restaurant/wines/card/{wp}/propose", data={"csrf_token": csrf})
            with SessionFactory() as s:
                site = dc.get_site(s, wp)
                rows = {w.wine.id: w for w in dc.card_wines(s, site, date(2026, 11, 24))}
                menu_ids = [d.recipe_id for d in dc.menu_dishes(s, site.location.id)]
            check("Propose keeps the approved description of a wine missing its pairings",
                  rows[barolo].description == "A Barolo proposal" and rows[barolo].description_approved)
            check("Propose fills the missing pairings from the active menu, left to review",
                  [d.recipe_id for d in rows[barolo].pairings] == [brasato] and not rows[barolo].pairings_reviewed)
            check("only the site's active menu is sent to the AI",
                  sent and sorted(x["id"] for x in sent[0]["menu"]) == sorted(menu_ids))
            check("wines already fully approved are not sent again",
                  sent and {x["id"] for x in sent[0]["wines"]} == {w for w, r in rows.items() if not (r.description_approved and r.pairings_reviewed)})
        finally:
            drink_card_ai._call, drink_card_ai.is_configured = original_call, original_configured

        def answer_error(prompt):
            raise drink_card_ai.DrinkCardAIError("The AI could not be reached. Nothing was changed.")
        drink_card_ai.is_configured = lambda: True
        drink_card_ai._call = answer_error
        with SessionFactory() as s:  # make one wine pending again
            s.execute(text("UPDATE restaurant_wine_card_descriptions SET approved = 0 WHERE wine_id = :w"), {"w": barolo})
            s.commit()
        resp = c.post(f"/restaurant/wines/card/{wp}/propose", data={"csrf_token": csrf}, follow_redirects=True)
        check("an AI failure is reported and changes nothing", "could not be reached" in resp.data.decode())
        drink_card_ai._call, drink_card_ai.is_configured = original_call, original_configured

        # ---- Kitchen changes -------------------------------------------------
        with SessionFactory() as s:
            s.execute(text("UPDATE kitchen_menu_entries SET label = 'Brasato della Casa' WHERE recipe_id = :r"), {"r": brasato})
            s.commit()
        pdf = c.get(f"/restaurant/wines/card/{wp}/card.pdf")
        text_all = " ".join(pdf_pages(pdf.data))
        check("the preview is an inline PDF", pdf.status_code == 200 and pdf.mimetype == "application/pdf"
              and pdf.headers["Content-Disposition"].startswith("inline"))
        check("a renamed dish shows its new name on the card", "Brasato della Casa" in text_all and "Brasato al Barolo" not in text_all)
        with SessionFactory() as s:
            s.execute(text("DELETE FROM kitchen_menu_entries WHERE recipe_id = :r"), {"r": tagliata})
            s.commit()
        page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
        check("a paired dish removed from the menu is flagged for review",
              "Left the active menu: Tagliata di Manzo" in page and "paired dish that left the active menu" in page)
        text_all = " ".join(pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data))
        check("a dish no longer on the menu is not printed", "Tagliata" not in text_all)

        # ---- Glass prices (Winter Park rule) ---------------------------------
        with SessionFactory() as s:
            site = dc.get_site(s, wp)
            card = dc.get_card(s, site)
            rows = {w.wine.id: w for w in dc.card_wines(s, site, date(2026, 11, 24))}
            check("a bottle above $100 shows no glass price", dc.printed_glass_price(card, rows[barolo]) is None)
            check("a $100 bottle keeps its glass price", dc.printed_glass_price(card, rows[nebbiolo]) == 29)
            s.commit()
        first = pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)[0]
        check("with the checkbox on, the G column is printed", " G" in first or "G\r\nB" in first or "G B" in first.replace("\r\n", " "))
        resp = c.post(f"/restaurant/wines/card/{wp}/glass", data={"csrf_token": csrf, "show_glass_price": "0"})
        check("the checkbox saves at once", resp.status_code == 200 and resp.json["ok"])
        first = pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)[0]
        check("with the checkbox off, heading and glass prices disappear",
              "G B" not in first.replace("\r\n", " ") and " 24" not in first and "\n24" not in first)
        c.post(f"/restaurant/wines/card/{wp}/glass", data={"csrf_token": csrf, "show_glass_price": "1"})

        # ---- Waters ----------------------------------------------------------
        check("no water section without waters", "MINERAL WATER" not in " ".join(pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)))
        resp = c.post(f"/restaurant/wines/card/{wp}/waters/new", data={"csrf_token": csrf, "name": "", "size_label": "750 mL", "price_usd": "8"})
        check("a water without a name is refused in the window", resp.status_code == 400 and "name" in resp.json["error"])
        resp = c.post(f"/restaurant/wines/card/{wp}/waters/new", data={"csrf_token": csrf, "name": "San Pellegrino",
                                                                     "sparkling": "1", "size_label": "750 mL", "price_usd": "8"})
        check("a water is added", resp.status_code == 200 and resp.json["ok"])
        text_all = " ".join(pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data))
        check("the water section appears with its entry", "MINERAL WATER" in text_all and "San Pellegrino" in text_all
              and "Sparkling · 750 mL" in text_all)

        # ---- Beers -----------------------------------------------------------
        check("no beer section without beers", "BEERS" not in " ".join(pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)))
        resp = c.post(f"/restaurant/wines/card/{wp}/beers/new", data={"csrf_token": csrf, "name": "", "size_label": "12 oz bottle", "price_usd": "8"})
        check("a beer without a name is refused in the window", resp.status_code == 400 and "name" in resp.json["error"])
        resp = c.post(f"/restaurant/wines/card/{wp}/beers/new", data={"csrf_token": csrf, "name": "Peroni Nastro Azzurro", "beer_type": "Lager", "size_label": "", "price_usd": "8"})
        check("a beer without a format is refused in the window", resp.status_code == 400 and "format" in resp.json["error"])
        resp = c.post(f"/restaurant/wines/card/{wp}/beers/new", data={"csrf_token": csrf, "name": "Peroni Nastro Azzurro",
                                                                    "beer_type": "Lager", "size_label": "12 oz bottle", "price_usd": "8"})
        check("a beer is added", resp.status_code == 200 and resp.json["ok"])
        pdf_text = pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)
        text_all = " ".join(pdf_text)
        check("the beer section appears with name, type · format and price", "BEERS" in text_all and "Peroni Nastro Azzurro" in text_all
              and "Lager · 12 oz bottle" in text_all)
        check("beers are printed after the wines and before the mineral waters",
              text_all.index("BEERS") > text_all.index("WINES") and text_all.index("BEERS") < text_all.index("MINERAL WATER"))
        with SessionFactory() as s:
            card = dc.get_card(s, dc.get_site(s, wp))
            beer_id = dc.list_beers(s, card)[0].id
            check("the beer is saved for the site", [b.name for b in dc.list_beers(s, card)] == ["Peroni Nastro Azzurro"])
        page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
        check("the page lists the beer with Edit and Delete", 'data-beer="%d"' % beer_id in page and "Peroni Nastro Azzurro" in page
              and "1 beers" in page)
        resp = c.post(f"/restaurant/wines/card/{wp}/beers/{beer_id}", data={"csrf_token": csrf, "name": "Moretti",
                                                                           "beer_type": "", "size_label": "Draft 16 oz", "price_usd": "7"})
        text_all = " ".join(pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data))
        check("a beer is edited; an empty type prints only the format", resp.status_code == 200 and "Moretti" in text_all
              and "Draft 16 oz" in text_all and "Peroni" not in text_all)
        resp = c.post(f"/restaurant/wines/card/{wp}/beers/{beer_id}/delete", data={"csrf_token": csrf})
        check("a beer is removed and the section disappears", resp.status_code == 302
              and "BEERS" not in " ".join(pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)))
        c.post(f"/restaurant/wines/card/{wp}/beers/new", data={"csrf_token": csrf, "name": "Peroni Nastro Azzurro",
                                                             "beer_type": "Lager", "size_label": "12 oz bottle", "price_usd": "8"})

        # ---- Print settings and overflow --------------------------------------
        settings = {"csrf_token": csrf, "page_count": "2", "page_width_in": "8.5", "page_height_in": "11",
                    "orientation": "LANDSCAPE", "corners_enabled": "1", "corner_leg_in": "1", "show_glass_price": "1",
                    "title": "Wine List", "heading": "Rome's Flavours", "subheading": "Winter Park",
                    "footer_note": "Glass of 6 fl oz · Bottles 750 mL", "ink_color": "#2E3A1C",
                    "accent_color": "#A0401C", "line_color": "#B08A5A"}
        resp = c.post(f"/restaurant/wines/card/{wp}/settings", data=settings)
        pdf = c.get(f"/restaurant/wines/card/{wp}/card.pdf").data
        width, height = pdf_size(pdf)
        check("pages, size and orientation update the preview", len(pdf_pages(pdf)) == 2 and round(width) == 792 and round(height) == 612)
        bad = dict(settings, corner_leg_in="5")
        resp = c.post(f"/restaurant/wines/card/{wp}/settings", data=bad, follow_redirects=True)
        check("corners too large for the sheet are refused", "too large" in resp.data.decode())
        tiny = dict(settings, page_count="1", page_width_in="4", page_height_in="5", orientation="PORTRAIT", corner_leg_in="0.5")
        c.post(f"/restaurant/wines/card/{wp}/settings", data=tiny)
        page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
        check("content that does not fit is reported before export", "The card does not fit" in page and "Export is disabled" in page)
        resp = c.get(f"/restaurant/wines/card/{wp}/card.pdf?download=1")
        check("the export is refused while the card does not fit", resp.status_code == 302)
        c.post(f"/restaurant/wines/card/{wp}/settings", data=dict(settings, page_count="4", page_width_in="5.5",
                                                                  page_height_in="8.5", orientation="PORTRAIT"))
        preview = c.get(f"/restaurant/wines/card/{wp}/card.pdf").data
        export = c.get(f"/restaurant/wines/card/{wp}/card.pdf?download=1")
        check("the exported PDF is the preview's PDF", export.status_code == 200
              and export.headers["Content-Disposition"].startswith("attachment") and pdf_pages(export.data) == pdf_pages(preview))
        check("the Winter Park layout: 4 half-Letter pages", len(pdf_pages(preview)) == 4
              and tuple(round(v) for v in pdf_size(preview)) == (396, 612))

        # ---- Images -----------------------------------------------------------
        resp = c.post(f"/restaurant/wines/card/{wp}/images/HEADER_LEFT",
                      data={"csrf_token": csrf, "image": (io.BytesIO(b"not an image"), "x.png")},
                      content_type="multipart/form-data", follow_redirects=True)
        check("a non-image upload is refused", "PNG or JPEG" in resp.data.decode())
        PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
        resp = c.post(f"/restaurant/wines/card/{wp}/images/HEADER_LEFT",
                      data={"csrf_token": csrf, "image": (io.BytesIO(PDF), "sample.pdf")},
                      content_type="multipart/form-data", follow_redirects=True)
        check("a PDF is refused as a printed decoration", "only as the graphic example" in resp.data.decode())
        resp = c.post(f"/restaurant/wines/card/{wp}/images/REFERENCE",
                      data={"csrf_token": csrf, "image": (io.BytesIO(PDF), "graphic sample.pdf")}, content_type="multipart/form-data")
        shown = c.get(f"/restaurant/wines/card/{wp}/images/REFERENCE")
        page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
        check("a PDF graphic example is uploaded and shown next to the preview", resp.status_code == 302
              and shown.data == PDF and shown.mimetype == "application/pdf" and "card-reference-pdf" in page)
        resp = c.post(f"/restaurant/wines/card/{wp}/images/HEADER_LEFT",
                      data={"csrf_token": csrf, "image": (io.BytesIO(PNG), "olive.png")}, content_type="multipart/form-data")
        check("a decoration is uploaded", resp.status_code == 302
              and c.get(f"/restaurant/wines/card/{wp}/images/HEADER_LEFT").data == PNG)
        check("the card still renders with the decoration", c.get(f"/restaurant/wines/card/{wp}/card.pdf").status_code == 200)
        resp = c.post(f"/restaurant/wines/card/{wp}/images/BACKGROUND",
                      data={"csrf_token": csrf, "image": (io.BytesIO(PNG), "background.png")}, content_type="multipart/form-data")
        with_background = c.get(f"/restaurant/wines/card/{wp}/card.pdf")
        check("a background is uploaded and the card renders on it", resp.status_code == 302
              and c.get(f"/restaurant/wines/card/{wp}/images/BACKGROUND").data == PNG
              and with_background.status_code == 200 and len(pdf_pages(with_background.data)) == 4)
        page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
        check("with a background, the 'Print the paper colour' checkbox is shown ticked",
              'id="paper-color-toggle" checked' in page)
        from PIL import Image
        from rfone_data_store.restaurant_wines import drink_card_pdf as card_pdf
        sample = Image.new("RGB", (200, 300), (250, 243, 225))          # cream paper
        sample.paste((90, 110, 40), (60, 100, 140, 200))                  # a green leaf
        raw = io.BytesIO(); sample.save(raw, "PNG")
        c.post(f"/restaurant/wines/card/{wp}/images/BACKGROUND",
               data={"csrf_token": csrf, "image": (io.BytesIO(raw.getvalue()), "cream.png")}, content_type="multipart/form-data")
        with_background = c.get(f"/restaurant/wines/card/{wp}/card.pdf")
        resp = c.post(f"/restaurant/wines/card/{wp}/paper-color", data={"csrf_token": csrf, "print_paper_color": "0"})
        white_card = c.get(f"/restaurant/wines/card/{wp}/card.pdf")
        def first_page_pixels(data):
            return pdfium.PdfDocument(data)[0].render(scale=0.5).to_pil().convert("RGB").tobytes()
        check("the checkbox saves at once and the printed page changes", resp.status_code == 200 and resp.json["ok"]
              and white_card.status_code == 200 and first_page_pixels(white_card.data) != first_page_pixels(with_background.data))
        check("unticked, the layout stays the same", pdf_pages(white_card.data) == pdf_pages(with_background.data))
        whitened = Image.open(io.BytesIO(card_pdf.white_paper(raw.getvalue()))).convert("RGB")
        paper_px, leaf_px = whitened.getpixel((10, 10)), whitened.getpixel((100, 150))
        check("unticked, the paper colour becomes white", min(paper_px) >= 250, str(paper_px))
        check("unticked, the drawings keep their colour", all(abs(a - b) <= 6 for a, b in zip(leaf_px, (90, 110, 40))), str(leaf_px))
        with SessionFactory() as s:
            card = dc.get_card(s, dc.get_site(s, wp))
            check("the uploaded background is not modified", dc.card_images(s, card)["BACKGROUND"].data == raw.getvalue()
                  and card.print_paper_color is False)
        page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
        check("the page and the print settings form keep the choice", 'name="print_paper_color" value="0"' in page
              and 'id="paper-color-toggle"' in page and 'id="paper-color-toggle" checked' not in page)
        c.post(f"/restaurant/wines/card/{wp}/paper-color", data={"csrf_token": csrf, "print_paper_color": "1"})
        check("ticked again, the paper colour is printed",
              first_page_pixels(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data) == first_page_pixels(with_background.data))

        # ---- Two pages per sheet, for printing and cutting -------------------------
        single = pdf_pages(c.get(f"/restaurant/wines/card/{wp}/card.pdf").data)
        resp = c.get(f"/restaurant/wines/card/{wp}/card.pdf?download=1&two_up=1")
        sheets = pdf_pages(resp.data)
        check("2 pages per sheet: 4 pages on 2 landscape Letter sheets",
              resp.status_code == 200 and len(single) == 4 and len(sheets) == 2
              and tuple(round(v) for v in pdf_size(resp.data)) == (792, 612), str(pdf_size(resp.data)))
        check("2 pages per sheet keeps the content of pages 1-2 and 3-4",
              all(sorted(sheets[k].split()) == sorted((single[2 * k] + " " + single[2 * k + 1]).split()) for k in range(2)))
        check("2 pages per sheet is a download with its own name", resp.headers["Content-Disposition"].startswith("attachment")
              and "2-per-sheet" in resp.headers["Content-Disposition"])

        # ---- Deleting a wine removes its card texts -----------------------------
        with SessionFactory() as s:
            catalog.delete_wine(s, s.get(m.Wine, amarone))
            s.commit()
            left = s.execute(text("SELECT COUNT(*) FROM restaurant_wine_card_pairings WHERE wine_id = :w"), {"w": amarone}).scalar()
            left += s.execute(text("SELECT COUNT(*) FROM restaurant_wine_card_descriptions WHERE wine_id = :w"), {"w": amarone}).scalar()
        check("deleting a wine from Availability removes its card texts", left == 0)

        # ---- Italian local interface ---------------------------------------------
        os.environ["RFONE_UI_LANGUAGE"] = "it"
        try:
            page = c.get(f"/restaurant/wines/card?site={wp}").data.decode()
            check("the local interface is Italian", "Carta bevande" in page and "Mostra prezzo al calice" in page
                  and "Come funziona questa pagina" in page and "Proponi con AI" in page)
        finally:
            os.environ.pop("RFONE_UI_LANGUAGE", None)
    except Exception:
        import traceback
        traceback.print_exc()
        failed.append("unexpected exception")

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
