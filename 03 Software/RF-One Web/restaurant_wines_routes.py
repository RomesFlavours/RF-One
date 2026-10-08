"""RF-One Web — Restaurant > Wines (RESTAURANT_WINES_FIRST_RELEASE_001).

Three pages, gated by `require_domain_access("WINES")`:

  * Wine List   (`/restaurant/wines`)              — per Entity, versioned;
  * Availability (`/restaurant/wines/availability`) — the purchasable catalog;
  * Wine Types  (`/restaurant/wines/types`)         — the type registry.

All business rules live in `rfone_data_store.restaurant_wines`; this module
only reads requests and renders. Dialog saves are sent with `fetch` and
answer JSON, so a refused save keeps what was typed in the dialog; the
other actions are ordinary form posts. Either way the page shows the shared
busy indicator (`static/js/rf-one-busy.js`).

Registered from `app.py` via `register_restaurant_wines_routes(app, ...)`,
passing collaborators in explicitly like the other route modules here."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.restaurant_wines import catalog, wine_lists, wine_types
from rfone_data_store.restaurant_wines.pricing import PricingParameters, calculate_prices, cost_is_priceable

DOMAIN_CODE = "WINES"


class _BadInput(ValueError):
    pass


def _decimal(raw: str | None, label: str) -> Decimal | None:
    text = (raw or "").strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise _BadInput(f"{label} must be a number.") from None
    if not value.is_finite():
        raise _BadInput(f"{label} must be a number.")
    return value


def _int(raw: str | None, label: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise _BadInput(f"{label} must be a whole number.") from None


def _date(raw: str | None, label: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise _BadInput(f"{label} must be a date.") from None


def _local_today(db) -> date:
    """Today in the Restaurant Location's own timezone (RF-One UI Rules §1),
    the same Location the rest of RF-One Web shows times in."""
    tz_name = db.scalars(
        select(m.Location.timezone)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .order_by(m.RestaurantLocation.restaurant_id)
    ).first()
    try:
        return datetime.now(ZoneInfo(tz_name)).date() if tz_name else date.today()
    except Exception:  # an unknown zone name must not break the page
        return date.today()


def _money_text(value) -> str:
    if value is None:
        return ""
    value = Decimal(value)
    return str(int(value)) if value == value.to_integral_value() else f"{value:.2f}"


def _type_view(wine_type: m.WineType) -> dict:
    return {"id": wine_type.id, "name": wine_type.standard_name, "aliases": wine_type.aliases}


def _wine_view(wine: m.Wine) -> dict:
    return {
        "id": wine.id, "wine_type_id": wine.wine_type_id, "type_name": wine.wine_type.standard_name,
        "producer": wine.producer, "label_name": wine.label_name or "",
        "vintage_year": wine.vintage_year, "non_vintage": wine.non_vintage, "vintage_label": wine.vintage_label,
        "category": wine.category, "category_label": catalog.CATEGORY_LABELS[wine.category],
        "style": wine.style, "style_label": catalog.STYLE_LABELS[wine.style],
        "denomination": wine.denomination or "", "region": wine.region or "",
        "bottle_size_ml": wine.bottle_size_ml, "supplier_name": wine.supplier_name or "",
        "cost_usd": _money_text(wine.cost_usd), "cost_known": wine.cost_usd is not None,
        "cost_date": wine.cost_date.isoformat() if wine.cost_date else "",
        "availability": wine.availability, "availability_label": catalog.AVAILABILITY_LABELS[wine.availability],
        "notes": wine.notes or "", "display_name": catalog.display_name(wine),
    }


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def register_restaurant_wines_routes(app, *, require_domain_access, SessionFactory, load_current_account, require_csrf):
    gate = require_domain_access(DOMAIN_CODE)

    # -----------------------------------------------------------------
    # Wine Types
    # -----------------------------------------------------------------

    @app.route("/restaurant/wines/types")
    @gate
    def restaurant_wine_types():
        with SessionFactory() as db:
            types = [_type_view(t) for t in wine_types.list_wine_types(db)]
            counts: dict[int, int] = {}
            for wine_type_id in db.scalars(select(m.Wine.wine_type_id)).all():
                counts[wine_type_id] = counts.get(wine_type_id, 0) + 1
            for t in types:
                t["wine_count"] = counts.get(t["id"], 0)
            return render_template("restaurant_wine_types.html", types=types, active_tab="types")

    def _save_type(type_id: int | None):
        require_csrf()
        standard = request.form.get("standard_name", "")
        aliases = request.form.get("aliases", "").splitlines()
        with SessionFactory() as db:
            try:
                if type_id is None:
                    wine_type = wine_types.create_wine_type(db, standard_name=standard, aliases=aliases)
                else:
                    wine_type = db.get(m.WineType, type_id)
                    if wine_type is None:
                        abort(404)
                    wine_types.update_wine_type(db, wine_type, standard_name=standard, aliases=aliases)
                db.commit()
            except wine_types.WineTypeError as exc:
                db.rollback()
                return _json_error(str(exc))
            return jsonify({"ok": True, "type": _type_view(wine_type)})

    @app.route("/restaurant/wines/types/new", methods=["POST"])
    @gate
    def restaurant_wine_type_create():
        return _save_type(None)

    @app.route("/restaurant/wines/types/<int:type_id>", methods=["POST"])
    @gate
    def restaurant_wine_type_update(type_id: int):
        return _save_type(type_id)

    # -----------------------------------------------------------------
    # Availability (catalog)
    # -----------------------------------------------------------------

    @app.route("/restaurant/wines/availability")
    @gate
    def restaurant_wine_availability():
        query = request.args.get("q", "")
        with SessionFactory() as db:
            wines = [_wine_view(w) for w in catalog.list_wines(db, query)]
            return render_template(
                "restaurant_wine_availability.html", active_tab="availability", wines=wines, query=query,
                types=[_type_view(t) for t in wine_types.list_wine_types(db)],
                suppliers=catalog.known_supplier_names(db), today=_local_today(db).isoformat(),
                categories=catalog.CATEGORY_LABELS, styles=catalog.STYLE_LABELS,
                availabilities=catalog.AVAILABILITY_LABELS,
            )

    def _wine_input(form) -> catalog.WineInput:
        return catalog.WineInput(
            wine_type_id=_int(form.get("wine_type_id"), "Wine type"),
            producer=form.get("producer", ""),
            label_name=form.get("label_name"),
            vintage_year=_int(form.get("vintage_year"), "Vintage"),
            non_vintage=form.get("non_vintage") == "1",
            category=form.get("category", ""),
            style=form.get("style", ""),
            denomination=form.get("denomination"),
            region=form.get("region"),
            bottle_size_ml=_int(form.get("bottle_size_ml"), "Bottle format"),
            supplier_name=form.get("supplier_name"),
            cost_usd=_decimal(form.get("cost_usd"), "Cost"),
            cost_date=_date(form.get("cost_date"), "Cost date"),
            availability=form.get("availability", ""),
            notes=form.get("notes"),
        )

    def _save_wine(wine_id: int | None):
        require_csrf()
        with SessionFactory() as db:
            try:
                data = _wine_input(request.form)
                if wine_id is None:
                    wine = catalog.create_wine(db, data)
                else:
                    wine = db.get(m.Wine, wine_id)
                    if wine is None:
                        abort(404)
                    catalog.update_wine(db, wine, data)
                db.commit()
            except (_BadInput, catalog.WineCatalogError) as exc:
                db.rollback()
                return _json_error(str(exc))
            flash(f"{catalog.display_name(wine)} saved.", "info")
            return jsonify({"ok": True, "wine": _wine_view(wine)})

    @app.route("/restaurant/wines/availability/new", methods=["POST"])
    @gate
    def restaurant_wine_create():
        return _save_wine(None)

    @app.route("/restaurant/wines/availability/<int:wine_id>", methods=["POST"])
    @gate
    def restaurant_wine_update(wine_id: int):
        return _save_wine(wine_id)

    # -----------------------------------------------------------------
    # Wine List
    # -----------------------------------------------------------------

    def _item_view(item: m.WineListItem, current: PricingParameters) -> dict:
        wine = item.wine
        return {
            "id": item.id, "wine": _wine_view(wine),
            "cost_used": _money_text(item.cost_used), "cost_priceable": cost_is_priceable(item.cost_used),
            "value": f"{item.value_factor.normalize():f}", "sells_by_glass": item.sells_by_glass,
            "calculated_bottle": item.calculated_bottle_price, "calculated_glass": item.calculated_glass_price,
            "applied_bottle": _money_text(item.applied_bottle_price),
            "applied_glass": _money_text(item.applied_glass_price),
            "bottle_manual": item.bottle_price_manual, "glass_manual": item.glass_price_manual,
            "catalog_cost_changed": wine_lists.catalog_cost_changed(item),
            "parameters_changed": wine_lists.parameters_changed(item, current),
            "parameters": f"A {item.coefficient_a.normalize():f} · B {item.log_base_b.normalize():f} · "
                          f"G {item.glass_divisor_g.normalize():f}",
        }

    @app.route("/restaurant/wines")
    @gate
    def restaurant_wines_home():
        with SessionFactory() as db:
            today = _local_today(db)
            entities = wine_lists.list_entities(db)
            entity = None
            entity_id = request.args.get("entity", type=int)
            if entity_id is not None:
                entity = next((e for e in entities if e.id == entity_id), None)
            if entity is None and entities:
                entity = entities[0]

            versions, active, selected, items = [], None, None, []
            if entity is not None:
                versions = wine_lists.list_versions(db, entity.id)
                active = wine_lists.active_version(db, entity.id, today)
                list_id = request.args.get("list", type=int)
                selected = next((v for v in versions if v.id == list_id), None) or active
                if selected is None:
                    # No list in effect yet: show the nearest prepared one.
                    future = [v for v in versions if v.effective_from > today]
                    selected = future[-1] if future else None
            settings = wine_lists.get_settings(db)
            current = wine_lists.current_parameters(db)
            if selected is not None:
                items = [_item_view(i, current) for i in wine_lists.list_items(db, selected.id)]
            in_list = {i["wine"]["id"] for i in items}
            catalog_wines = [
                dict(_wine_view(w), in_list=w.id in in_list) for w in catalog.list_wines(db)
            ]
            version_views = [
                {"id": v.id, "effective_from": v.effective_from,
                 "status": wine_lists.version_status(v, active, today)}
                for v in versions
            ]
            selected_status = wine_lists.version_status(selected, active, today) if selected else None
            return render_template(
                "restaurant_wine_list.html", active_tab="list", entities=entities, entity=entity,
                versions=version_views, active=active, selected=selected, selected_status=selected_status,
                editable=selected is not None and selected_status != wine_lists.STATUS_PAST,
                items=items, catalog_wines=catalog_wines, today=today, settings=settings,
            )

    def _back_to_list(entity_id: int | None, list_id: int | None):
        return redirect(url_for("restaurant_wines_home", entity=entity_id, list=list_id))

    @app.route("/restaurant/wines/lists/new", methods=["POST"])
    @gate
    def restaurant_wine_list_create():
        require_csrf()
        entity_id = request.form.get("entity_id", type=int)
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                version = wine_lists.create_version(
                    db, legal_entity_id=entity_id, effective_from=_date(request.form.get("effective_from"), "Effective date"),
                    mode=request.form.get("mode", ""), today=_local_today(db),
                    account_id=account.id if account else None,
                )
                db.commit()
            except (_BadInput, wine_lists.WineListError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return _back_to_list(entity_id, None)
            flash(f"Wine list effective from {version.effective_from.isoformat()} created.", "info")
            return _back_to_list(entity_id, version.id)

    def _price_inputs(form):
        return {
            "cost_used": _decimal(form.get("cost_used"), "Cost used"),
            "value_factor": _decimal(form.get("value_factor"), "Value"),
            "sells_by_glass": form.get("sells_by_glass") == "1",
            "applied_bottle": _decimal(form.get("applied_bottle"), "Bottle price"),
            "applied_glass": _decimal(form.get("applied_glass"), "Glass price"),
        }

    @app.route("/restaurant/wines/lists/<int:list_id>/items/new", methods=["POST"])
    @gate
    def restaurant_wine_list_item_create(list_id: int):
        require_csrf()
        with SessionFactory() as db:
            version = db.get(m.WineList, list_id)
            if version is None:
                abort(404)
            try:
                item = wine_lists.add_item(
                    db, version, wine_id=_int(request.form.get("wine_id"), "Wine"), today=_local_today(db),
                    **_price_inputs(request.form),
                )
                db.commit()
            except (_BadInput, wine_lists.WineListError, ValueError) as exc:
                db.rollback()
                return _json_error(str(exc))
            flash(f"{catalog.display_name(item.wine)} added to the Wine list.", "info")
            return jsonify({"ok": True, "redirect": url_for(
                "restaurant_wines_home", entity=version.legal_entity_id, list=version.id)})

    def _load_item(db, item_id: int) -> m.WineListItem:
        item = db.get(m.WineListItem, item_id)
        if item is None:
            abort(404)
        return item

    @app.route("/restaurant/wines/items/<int:item_id>", methods=["POST"])
    @gate
    def restaurant_wine_list_item_update(item_id: int):
        require_csrf()
        with SessionFactory() as db:
            item = _load_item(db, item_id)
            version = item.wine_list
            try:
                wine_lists.update_item(db, item, today=_local_today(db), **_price_inputs(request.form))
                db.commit()
            except (_BadInput, wine_lists.WineListError, ValueError) as exc:
                db.rollback()
                return _json_error(str(exc))
            flash(f"{catalog.display_name(item.wine)} updated.", "info")
            return jsonify({"ok": True, "redirect": url_for(
                "restaurant_wines_home", entity=version.legal_entity_id, list=version.id)})

    def _item_action(item_id: int, action, done_message: str):
        require_csrf()
        with SessionFactory() as db:
            item = _load_item(db, item_id)
            version = item.wine_list
            name = catalog.display_name(item.wine)
            try:
                action(db, item, today=_local_today(db))
                db.commit()
            except wine_lists.WineListError as exc:
                db.rollback()
                flash(str(exc), "error")
            else:
                flash(done_message.format(name=name), "info")
            return _back_to_list(version.legal_entity_id, version.id)

    @app.route("/restaurant/wines/items/<int:item_id>/delete", methods=["POST"])
    @gate
    def restaurant_wine_list_item_delete(item_id: int):
        return _item_action(item_id, wine_lists.remove_item,
                            "{name} removed from this Wine list. It is still in the catalog.")

    @app.route("/restaurant/wines/items/<int:item_id>/adopt-catalog-cost", methods=["POST"])
    @gate
    def restaurant_wine_list_item_adopt_cost(item_id: int):
        return _item_action(item_id, wine_lists.adopt_catalog_cost,
                            "{name}: catalog cost adopted and prices recalculated (hand-set prices kept).")

    @app.route("/restaurant/wines/items/<int:item_id>/adopt-parameters", methods=["POST"])
    @gate
    def restaurant_wine_list_item_adopt_parameters(item_id: int):
        return _item_action(item_id, wine_lists.adopt_current_parameters,
                            "{name}: current pricing parameters adopted and prices recalculated (hand-set prices kept).")

    @app.route("/restaurant/wines/items/<int:item_id>/restore-calculated", methods=["POST"])
    @gate
    def restaurant_wine_list_item_restore(item_id: int):
        return _item_action(item_id, wine_lists.restore_calculated,
                            "{name}: applied prices restored to the calculated ones.")

    @app.route("/restaurant/wines/price-preview")
    @gate
    def restaurant_wine_price_preview():
        """The calculated prices a dialog shows while typing — the SAME
        formula the save uses, never a copy in the browser."""
        with SessionFactory() as db:
            try:
                cost = _decimal(request.args.get("cost"), "Cost")
                value = _decimal(request.args.get("value"), "Value")
                if value is None or value <= 0:
                    return _json_error("Value must be a positive number.")
                item_id = request.args.get("item", type=int)
                if item_id:
                    parameters = wine_lists.item_parameters(_load_item(db, item_id))
                else:
                    parameters = wine_lists.current_parameters(db)
                prices = calculate_prices(cost, value, parameters)
            except (_BadInput, ValueError) as exc:
                return _json_error(str(exc))
            return jsonify({"ok": True, "bottle": prices.bottle, "glass": prices.glass,
                            "priceable": cost_is_priceable(cost)})

    @app.route("/restaurant/wines/settings", methods=["POST"])
    @gate
    def restaurant_wine_settings_update():
        require_csrf()
        entity_id = request.form.get("entity_id", type=int)
        list_id = request.form.get("list_id", type=int)
        with SessionFactory() as db:
            try:
                parameters = PricingParameters(
                    _decimal(request.form.get("coefficient_a"), "Coefficient A"),
                    _decimal(request.form.get("log_base_b"), "Logarithm base B"),
                    _decimal(request.form.get("glass_divisor_g"), "Glass divisor G"),
                )
                wine_lists.update_settings(db, parameters)
                db.commit()
            except (_BadInput, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return _back_to_list(entity_id, list_id)
        flash("Pricing parameters saved. Prices already on Wine lists are unchanged until you adopt them row by row.", "info")
        return _back_to_list(entity_id, list_id)

    @app.route("/restaurant/wines/lists/<int:list_id>/export.csv")
    @gate
    def restaurant_wine_list_export(list_id: int):
        with SessionFactory() as db:
            version = db.get(m.WineList, list_id)
            if version is None:
                abort(404)
            body = wine_lists.export_csv(db, version)
            slug = "".join(ch if ch.isalnum() else "-" for ch in version.legal_entity.legal_name).strip("-")
            filename = f"wine-list-{slug}-{version.effective_from.isoformat()}.csv"
        return Response(
            "﻿" + body, mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
