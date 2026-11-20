"""RF-One Web — Settings > Workweek (COMPENSATION_PERIOD_SUMMARY_001).

The Workweek start is a general, shared Restaurant setting
(`WorkweekDefinition`), not a parameter of any one report: every reader
(the Compensation Period Summary first) resolves it through
`payroll_calculation.workweek`. This page shows each Restaurant's current
value and its history, and records a new start day effective from a chosen
Business Date — never rewriting a week that is already history.

Registered from `app.py` via `register_workweek_settings_routes(app, ...)`,
passing collaborators in explicitly like the other route modules here."""

from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.payroll_calculation import workweek as workweek_service
from rfone_data_store.tips.distribution_engine import business_date_window_utc


def register_workweek_settings_routes(app, *, require_admin, SessionFactory, require_csrf, load_current_account):

    @app.route("/admin/workweek")
    @require_admin
    def admin_workweek():
        with SessionFactory() as db:
            restaurants = db.scalars(select(m.Restaurant).order_by(m.Restaurant.name)).all()
            now = datetime.now(workweek_service.UTC)
            rows = [
                {
                    "restaurant": restaurant,
                    "current": workweek_service.effective_workweek_definition(db, restaurant.id, now),
                    "history": workweek_service.workweek_definitions_for(db, restaurant.id),
                }
                for restaurant in restaurants
            ]
            return render_template(
                "admin_workweek.html", rows=rows, weekday_names=workweek_service.WEEKDAY_NAMES,
            )

    @app.route("/admin/workweek/<int:restaurant_id>", methods=["POST"])
    @require_admin
    def admin_workweek_set(restaurant_id: int):
        require_csrf()
        start_weekday = request.form.get("start_weekday", type=int)
        effective_raw = request.form.get("effective_business_date", "")
        with SessionFactory() as db:
            restaurant = db.get(m.Restaurant, restaurant_id)
            if restaurant is None or start_weekday is None:
                flash("Restaurant and start day are required.", "error")
                return redirect(url_for("admin_workweek"))
            try:
                effective_date = datetime.strptime(effective_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("An effective Business Date is required.", "error")
                return redirect(url_for("admin_workweek"))
            if effective_date.weekday() != start_weekday:
                flash("The effective Business Date must fall on the new start day, so no week is cut in two.", "error")
                return redirect(url_for("admin_workweek"))

            # The new week begins at that Business Date's cutoff, in the
            # Location's own timezone — the same instant every Business Date
            # starts at. Without a configured Location nothing is assumed.
            location = db.scalars(
                select(m.Location).join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
                .where(m.RestaurantLocation.restaurant_id == restaurant.id)
            ).first()
            if location is None or not location.timezone or location.operating_day_cutoff_time is None:
                flash("The Restaurant's Location has no timezone/cutoff configured; the week start instant cannot be set.", "error")
                return redirect(url_for("admin_workweek"))
            effective_from, _ = business_date_window_utc(location, effective_date, effective_date)

            account = load_current_account(db)
            who = (account.display_name or account.username) if account else "unknown"
            try:
                workweek_service.set_workweek_start(
                    db, restaurant_id=restaurant.id, start_weekday=start_weekday,
                    effective_from=effective_from,
                    notes=f"Set in Settings > Workweek by {who}",
                )
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("admin_workweek"))
            flash(
                f"Workweek for {restaurant.name} starts on {workweek_service.WEEKDAY_NAMES[start_weekday]} "
                f"from Business Date {effective_date}.", "info",
            )
            return redirect(url_for("admin_workweek"))
