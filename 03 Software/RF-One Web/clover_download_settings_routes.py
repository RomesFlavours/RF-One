"""RF-One Web — Settings > Clover download (CLOVER_ACQUISITION_ENGINE_001,
Product Owner 2026-11-22).

The one common daily time at which the shared Clover acquisition engine
(`rfone_data_store.operational_acquisition`) downloads new records and updates
for every active Clover site. Initial value 00:00, America/New_York. The page
also shows, per site, the outcome of the last ordinary download, the last
successful one and the period covered. It starts no download itself.

Registered from `app.py`; administrators only, like Settings > Workweek.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, url_for

from rfone_data_store import operational_acquisition as acquisition_engine

UTC = timezone.utc


def register_clover_download_settings_routes(app, *, require_admin, SessionFactory, require_csrf, load_current_account):

    def _ui_it() -> bool:
        return os.environ.get("RFONE_UI_LANGUAGE") == "it"

    _IT = {"How this page works": "Come funziona questa pagina", "Close": "Chiudi"}

    def _page_ui(value: str) -> str:
        """Labels of the shared How Works modal in the page's language."""
        return _IT.get(value, value) if _ui_it() else value

    @app.context_processor
    def _clover_download_language():
        # The Home link of this page follows the same language selection as the page.
        return {"clover_download_ui_it": _ui_it()}

    @app.route("/admin/clover-download")
    @require_admin
    def admin_clover_download():
        with SessionFactory() as db:
            schedule = acquisition_engine.get_schedule(db)
            now = datetime.now(UTC)
            sites = [acquisition_engine.describe_site_status(db, location_id)
                     for location_id in acquisition_engine.clover_site_location_ids(db)]
            return render_template(
                "admin_clover_download.html", schedule=schedule, next_run=schedule.next_run(now),
                sites=sites, tz=schedule.timezone, ui_it=_ui_it(), page_ui=_page_ui,
            )

    @app.route("/admin/clover-download", methods=["POST"])
    @require_admin
    def admin_clover_download_set():
        require_csrf()
        it = _ui_it()
        raw = (request.form.get("run_time") or "").strip()
        try:
            run_time = datetime.strptime(raw, "%H:%M").time()
        except ValueError:
            flash("Indica un orario valido (HH:MM)." if it else "Enter a valid time (HH:MM).", "error")
            return redirect(url_for("admin_clover_download"))
        with SessionFactory() as db:
            account = load_current_account(db)
            schedule = acquisition_engine.set_schedule(db, run_time=run_time, account_id=account.id if account else None)
            db.commit()
        label = schedule.run_time.strftime("%H:%M")
        flash((f"Scarico ordinario impostato alle {label} ({schedule.timezone}) per tutte le sedi."
               if it else f"Ordinary download set to {label} ({schedule.timezone}) for every site."), "info")
        return redirect(url_for("admin_clover_download"))
