"""RF-One Web — Restaurant > Wines > Drink card (WINES_DRINK_CARD_001).

One page, `/restaurant/wines/card`, gated like the other Wines pages by
`require_domain_access("WINES")`. The person chooses the site, reviews the
descriptions and pairings, adds mineral waters, sets the print layout and
downloads the PDF. The preview on the page IS the PDF the export downloads
(`rfone_data_store.restaurant_wines.drink_card.build_card`).

Business rules live in `rfone_data_store.restaurant_wines.drink_card`; this
module reads requests, translates messages and renders. Local development
shows Italian (`RFONE_UI_LANGUAGE=it`), shared installations English.
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for

from rfone_data_store import models as m
from rfone_data_store.restaurant_wines import drink_card as dc
from rfone_data_store.restaurant_wines import drink_card_ai

_IT = {
    # shared How Works component
    "How this page works": "Come funziona questa pagina", "Close": "Chiudi",
    # service messages
    "Number of pages must be a whole number.": "Il numero di pagine deve essere un numero intero.",
    "Number of pages must be between 1 and 24.": "Il numero di pagine deve essere fra 1 e 24.",
    "Sheet width must be a number.": "La larghezza del foglio deve essere un numero.",
    "Sheet height must be a number.": "L'altezza del foglio deve essere un numero.",
    "Sheet width and height must be between 3 and 20 inches.": "Larghezza e altezza del foglio devono essere fra 3 e 20 pollici.",
    "Choose portrait or landscape.": "Scegli verticale oppure orizzontale.",
    "Corner side must be a number.": "Il lato dell'angolo deve essere un numero.",
    "Corner side cannot be negative.": "Il lato dell'angolo non può essere negativo.",
    "With free corners on, the corner side must be greater than zero.": "Con gli angoli liberi attivi, il lato deve essere maggiore di zero.",
    "The free corners are too large for this sheet.": "Gli angoli liberi sono troppo grandi per questo foglio.",
    "Text colour must be a colour such as #2E3A1C.": "Il colore del testo deve essere un colore come #2E3A1C.",
    "Price colour must be a colour such as #2E3A1C.": "Il colore dei prezzi deve essere un colore come #2E3A1C.",
    "Line colour must be a colour such as #2E3A1C.": "Il colore delle linee deve essere un colore come #2E3A1C.",
    "The card title cannot be empty.": "Il titolo della carta non può essere vuoto.",
    "This wine is no longer in the catalog.": "Questo vino non è più nel catalogo.",
    "A chosen dish is not on the site's active menu.": "Un piatto scelto non è nel menu attivo della sede.",
    "Choose at most two dishes.": "Scegli al massimo due piatti.",
    f"The description can be at most {dc.MAX_DESCRIPTION_LENGTH} characters.":
        f"La descrizione può avere al massimo {dc.MAX_DESCRIPTION_LENGTH} caratteri.",
    "Enter the name of the water.": "Scrivi il nome dell'acqua.",
    "Enter the format, for example 750 mL.": "Scrivi il formato, per esempio 750 mL.",
    "Price must be a number.": "Il prezzo deve essere un numero.",
    "The price cannot be negative.": "Il prezzo non può essere negativo.",
    "This water is no longer on the card.": "Questa acqua non è più nella carta.",
    "Unknown image position.": "Posizione dell'immagine sconosciuta.",
    "Choose an image file.": "Scegli un file immagine.",
    "The image is larger than 4 MB.": "L'immagine supera 4 MB.",
    "Use a PNG or JPEG image.": "Usa un'immagine PNG o JPEG.",
    "The AI is not configured on this installation: write the descriptions by hand.":
        "L'AI non è configurata in questa installazione: scrivi le descrizioni a mano.",
    "The AI could not be reached. Nothing was changed.": "L'AI non è raggiungibile. Non è stato cambiato nulla.",
    "The AI answer was incomplete. Nothing was changed.": "La risposta dell'AI era incompleta. Non è stato cambiato nulla.",
}


def _ui_it() -> bool:
    return os.environ.get("RFONE_UI_LANGUAGE") == "it"


def _t(en: str, it: str | None = None) -> str:
    if not _ui_it():
        return en
    if it is not None:
        return it
    if en.startswith("The AI request failed (HTTP"):
        return en.replace("The AI request failed", "Richiesta AI non riuscita").replace(
            "Nothing was changed.", "Non è stato cambiato nulla.")
    return _IT.get(en, en)


IMAGE_SLOT_LABELS = {
    "REFERENCE": ("Graphic example (reference only, not printed)", "Esempio grafico (solo riferimento, non stampato)"),
    "LOGO": ("Logo, replaces the heading", "Logo, al posto dell'intestazione"),
    "HEADER_LEFT": ("Decoration top left", "Decoro in alto a sinistra"),
    "HEADER_RIGHT": ("Decoration top right", "Decoro in alto a destra"),
    "FOOTER_LEFT": ("Decoration bottom left", "Decoro in basso a sinistra"),
    "FOOTER_CENTER": ("Decoration bottom centre", "Decoro in basso al centro"),
    "FOOTER_RIGHT": ("Decoration bottom right", "Decoro in basso a destra"),
}


def _site_today(site: dc.Site):
    try:
        return datetime.now(ZoneInfo(site.location.timezone)).date() if site.location.timezone else datetime.now().date()
    except Exception:  # an unknown zone name must not break the page
        return datetime.now().date()


def _money(value) -> str:
    if value is None:
        return ""
    return str(int(value)) if value == int(value) else f"{value:.2f}"


def register_restaurant_wine_card_routes(app, *, gate, SessionFactory, require_csrf):

    @app.context_processor
    def _wines_card_language():
        # The Wines tab label follows the same language selection as this page.
        return {"wines_card_ui_it": _ui_it()}

    def _load(db, location_id: int):
        site = next((s for s in dc.list_sites(db) if s.location.id == location_id), None)
        if site is None:
            abort(404)
        return site, dc.get_card(db, site)

    def _back(location_id: int, anchor: str | None = None):
        return redirect(url_for("restaurant_wine_card", site=location_id) + (f"#{anchor}" if anchor else ""))

    @app.route("/restaurant/wines/card")
    @gate
    def restaurant_wine_card():
        with SessionFactory() as db:
            sites = dc.list_sites(db)
            site = dc.get_site(db, request.args.get("site", type=int))
            context = {"sites": sites, "site": site, "ui_it": _ui_it(), "page_ui": _t, "t": _t,
                       "active_tab": "card", "slot_labels": IMAGE_SLOT_LABELS, "paper_presets": dc.PAPER_PRESETS,
                       "ai_configured": drink_card_ai.is_configured()}
            if site is not None:
                card = dc.get_card(db, site)
                db.commit()
                today = _site_today(site)
                version = dc.wine_list_in_effect(db, site, today)
                wines = dc.card_wines(db, site, today)
                dishes = dc.menu_dishes(db, site.location.id)
                result = dc.build_card(db, site, card, today)
                images = dc.card_images(db, card)
                context.update(
                    card=card, version=version, menu_name=dc.active_menu_name(db, site.location.id),
                    dishes=[{"id": d.recipe_id, "name": d.name} for d in dishes],
                    rows=[{
                        "wine_id": w.wine.id, "name": w.name, "producer": w.producer, "vintage": w.vintage,
                        "bottle": _money(w.bottle_price), "glass": _money(dc.printed_glass_price(card, w)),
                        "description": w.description, "description_approved": w.description_approved,
                        "pairing_ids": [d.recipe_id for d in w.pairings], "pairing_names": [d.name for d in w.pairings],
                        "pairings_reviewed": w.pairings_reviewed, "removed": w.removed_dishes,
                        "printed": w.printed_description(),
                    } for w in wines],
                    waters=[{"id": w.id, "name": w.name, "sparkling": w.sparkling, "size_label": w.size_label,
                             "price": _money(w.price_usd)} for w in dc.list_waters(db, card)],
                    images={slot: img.filename for slot, img in images.items()},
                    result=result, today=today,
                    pending=sum(1 for w in wines if (w.description and not w.description_approved) or not w.pairings_reviewed),
                    to_review=sum(1 for w in wines if w.removed_dishes),
                )
            return render_template("restaurant_wine_card.html", **context)

    @app.route("/restaurant/wines/card/<int:location_id>/card.pdf")
    @gate
    def restaurant_wine_card_pdf(location_id: int):
        download = request.args.get("download") == "1"
        with SessionFactory() as db:
            site, card = _load(db, location_id)
            db.commit()
            result = dc.build_card(db, site, card, _site_today(site))
        if download and not result.exportable:
            flash(_t("The card does not fit the chosen pages: fix it before exporting.",
                     "La carta non entra nelle pagine scelte: correggi prima di esportare."), "error")
            return _back(location_id, "preview")
        slug = "".join(ch if ch.isalnum() else "-" for ch in site.location.name).strip("-") or "site"
        disposition = "attachment" if download else "inline"
        return Response(result.pdf, mimetype="application/pdf", headers={
            "Content-Disposition": f'{disposition}; filename="drink-card-{slug}.pdf"',
            "Cache-Control": "no-store",
        })

    @app.route("/restaurant/wines/card/<int:location_id>/settings", methods=["POST"])
    @gate
    def restaurant_wine_card_settings(location_id: int):
        require_csrf()
        with SessionFactory() as db:
            site, card = _load(db, location_id)
            try:
                dc.update_settings(db, card, request.form)
                db.commit()
            except dc.DrinkCardError as exc:
                db.rollback()
                flash(_t(str(exc)), "error")
                return _back(location_id, "print")
        flash(_t("Print settings saved: the preview is updated.", "Impostazioni di stampa salvate: l'anteprima è aggiornata."), "info")
        return _back(location_id, "print")

    @app.route("/restaurant/wines/card/<int:location_id>/glass", methods=["POST"])
    @gate
    def restaurant_wine_card_glass(location_id: int):
        require_csrf()
        with SessionFactory() as db:
            _, card = _load(db, location_id)
            dc.set_glass_price_visible(db, card, request.form.get("show_glass_price") == "1")
            db.commit()
        return jsonify({"ok": True})

    @app.route("/restaurant/wines/card/<int:location_id>/propose", methods=["POST"])
    @gate
    def restaurant_wine_card_propose(location_id: int):
        require_csrf()
        with SessionFactory() as db:
            site, card = _load(db, location_id)
            today = _site_today(site)
            wines = dc.card_wines(db, site, today)
            dishes = dc.menu_dishes(db, site.location.id)
            todo = [w for w in wines if not w.description_approved or not w.pairings_reviewed]
            if not todo:
                flash(_t("Every wine is already approved: nothing to propose.",
                         "Tutti i vini sono già approvati: niente da proporre."), "info")
                return _back(location_id, "texts")
            try:
                proposals = drink_card_ai.propose(todo, dishes)
                count = dc.apply_proposals(db, site, proposals, card)
                db.commit()
            except drink_card_ai.DrinkCardAIError as exc:
                db.rollback()
                flash(_t(str(exc)), "error")
                return _back(location_id, "texts")
        flash(_t(f"New proposals for {count} wines. Approved texts were kept.",
                 f"Nuove proposte per {count} vini. I testi approvati sono rimasti invariati."), "info")
        return _back(location_id, "texts")

    @app.route("/restaurant/wines/card/<int:location_id>/approve-all", methods=["POST"])
    @gate
    def restaurant_wine_card_approve_all(location_id: int):
        require_csrf()
        with SessionFactory() as db:
            site, _ = _load(db, location_id)
            count = dc.approve_all(db, site, _site_today(site))
            db.commit()
        flash(_t(f"{count} wines approved.", f"{count} vini approvati."), "info")
        return _back(location_id, "texts")

    @app.route("/restaurant/wines/card/<int:location_id>/wines/<int:wine_id>", methods=["POST"])
    @gate
    def restaurant_wine_card_review(location_id: int, wine_id: int):
        require_csrf()
        recipe_ids = []
        for raw in request.form.getlist("recipe_id"):
            if raw.strip():
                try:
                    recipe_ids.append(int(raw))
                except ValueError:
                    return jsonify({"ok": False, "error": _t("A chosen dish is not on the site's active menu.")}), 400
        with SessionFactory() as db:
            site, _ = _load(db, location_id)
            try:
                dc.save_review(db, site, wine_id, request.form.get("description", ""), recipe_ids)
                db.commit()
            except dc.DrinkCardError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": _t(str(exc))}), 400
        flash(_t("Description and pairings approved.", "Descrizione e abbinamenti approvati."), "info")
        return jsonify({"ok": True, "redirect": url_for("restaurant_wine_card", site=location_id)})

    def _save_water(location_id: int, water_id: int | None):
        require_csrf()
        with SessionFactory() as db:
            _, card = _load(db, location_id)
            try:
                dc.save_water(db, card, water_id, request.form)
                db.commit()
            except dc.DrinkCardError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": _t(str(exc))}), 400
        flash(_t("Water saved.", "Acqua salvata."), "info")
        return jsonify({"ok": True, "redirect": url_for("restaurant_wine_card", site=location_id)})

    @app.route("/restaurant/wines/card/<int:location_id>/waters/new", methods=["POST"])
    @gate
    def restaurant_wine_card_water_create(location_id: int):
        return _save_water(location_id, None)

    @app.route("/restaurant/wines/card/<int:location_id>/waters/<int:water_id>", methods=["POST"])
    @gate
    def restaurant_wine_card_water_update(location_id: int, water_id: int):
        return _save_water(location_id, water_id)

    @app.route("/restaurant/wines/card/<int:location_id>/waters/<int:water_id>/delete", methods=["POST"])
    @gate
    def restaurant_wine_card_water_delete(location_id: int, water_id: int):
        require_csrf()
        with SessionFactory() as db:
            _, card = _load(db, location_id)
            dc.delete_water(db, card, water_id)
            db.commit()
        flash(_t("Water removed from the card.", "Acqua tolta dalla carta."), "info")
        return _back(location_id, "waters")

    @app.route("/restaurant/wines/card/<int:location_id>/images/<slot>", methods=["POST"])
    @gate
    def restaurant_wine_card_image(location_id: int, slot: str):
        require_csrf()
        upload = request.files.get("image")
        with SessionFactory() as db:
            _, card = _load(db, location_id)
            try:
                if request.form.get("remove") == "1":
                    dc.delete_image(db, card, slot)
                else:
                    dc.set_image(db, card, slot, upload.filename if upload else "", upload.read() if upload else b"")
                db.commit()
            except dc.DrinkCardError as exc:
                db.rollback()
                flash(_t(str(exc)), "error")
                return _back(location_id, "print")
        flash(_t("Image updated: the preview is updated.", "Immagine aggiornata: l'anteprima è aggiornata."), "info")
        return _back(location_id, "print")

    @app.route("/restaurant/wines/card/<int:location_id>/images/<slot>")
    @gate
    def restaurant_wine_card_image_view(location_id: int, slot: str):
        with SessionFactory() as db:
            _, card = _load(db, location_id)
            image = dc.card_images(db, card).get(slot)
            if image is None:
                abort(404)
            return Response(image.data, mimetype=image.content_type, headers={"Cache-Control": "no-store"})
