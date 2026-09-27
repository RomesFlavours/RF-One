"""RF-One Web — Clover Acquisition (CLOVER_ACQUISITION_IDENTITY_001).

Sync Now and Historical Backfill start real work on AWS (a Fargate task
writing to the operational database). They may be started ONLY by a person
signed in to RF-One — the one existing RF-One login, never a login, password,
typed name or URL token of Clover Acquisition's own — whose account holds the
CLOVER_ACQUISITION access (Product Owner decision, 2026-09-26: a dedicated
access entry, granted account by account through the existing access
screen; `domain_registry.CLOVER_ACQUISITION`).

WHY IT LIVES IN RF-ONE WEB: on AWS the standalone Tips app runs on another
hostname, where the RF-One session cookie never arrives, so it cannot know
who is asking. The same reason, and the same answer, as
`tips_validation_routes.py`. The Tips app keeps no acquisition action.

Every gate below runs BEFORE the central acquisition service
(`technical.connectors.clover.acquisition_jobs`) is called, so a refused
request has no effect at all: no job row, no Fargate task, no write.

  1. identity — a live RF-One session (`load_current_account`); otherwise
     the person is sent to the normal RF-One login, with `next` so they
     come back here, and a plain message;
  2. authorization — `account_may_enter_domain(..., "CLOVER_ACQUISITION")`,
     the ONE access rule every RF-One Web destination uses; otherwise 403;
  3. CSRF, on the two state-changing POSTs.

The job records the requesting account (`requested_by_account_id`). The
acquisition itself — windows, dates, engine, safety checks — is unchanged.

UI_NAVIGATION_AND_LOCAL_TIME_001: RF-One Web and Tips are now published on
ONE host (CloudFront: RF-One Web at `/`, Tips at `/tips/`), so the RF-One
session reaches Tips too. Tips's Clover Acquisition tab therefore offers Sync
Now itself — as a form posting to THIS route, never a second Sync Now: the
same gates, the same central service, the same one-job-per-location lock.
`return_to=tips` only chooses where the person lands afterwards (back on the
Tips tab); it can name nothing but that one known page.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, select

from domain_registry import TIPS_HOME_URL
from rfone_data_store import display_format
from rfone_data_store import local_calendar
from rfone_data_store import models as m
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.technical.connectors.clover import acquisition_jobs as clover_jobs
from rfone_data_store.technical.connectors.clover.acquisition import ImportAlreadyRunningError

CLOVER_ACQUISITION_ACCESS_CODE = "CLOVER_ACQUISITION"
UTC = timezone.utc

SIGN_IN_MESSAGE = "Please sign in to RF-One to use Clover Acquisition. You will come back here afterwards."

# The one page, besides this one, a Clover Acquisition POST may send the
# person back to (`return_to=tips`): the Tips Clover Acquisition tab.
RETURN_TIPS = "tips"


def _person(account) -> str:
    """An RF-One account as operational displays name people: "Surname I."
    (RF-One UI Rules §2)."""
    return display_format.employee_short_name(shared_session.account_display_name(account))


def _default_clover_location_id(db) -> int | None:
    """The Clover Location of RF-One's (currently only) Restaurant — the
    same resolution the Tips app has always used (lowest Restaurant id ->
    RestaurantLocation -> Clover-sourced Location)."""
    restaurant = db.scalars(select(m.Restaurant).order_by(m.Restaurant.id)).first()
    if restaurant is None:
        return None
    return db.scalars(
        select(m.Location.id)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id)
        .where(m.RestaurantLocation.restaurant_id == restaurant.id, m.SourceSystem.code == "CLOVER")
    ).first()




def register_clover_acquisition_routes(
    app, *, SessionFactory, load_current_account, require_csrf, log_out, get_launcher=lambda: None,
) -> None:
    """`get_launcher` returns the launcher to hand to the service (`None` =
    the deployment's configured one); tests replace it."""

    def _from_tips() -> bool:
        # `from=tips`: the full page was opened from the Tips tab (breadcrumb
        # RF-One > Tips > Clover Acquisition); `return_to=tips`: the Tips
        # tab's own Sync Now form.
        return RETURN_TIPS in (request.values.get("return_to"), request.values.get("from"))

    def _authorized_account(db):
        """(account, None) when the request may act; (None, response)
        otherwise. Nothing is created or started on the refusal paths."""
        account = load_current_account(db)
        if account is None:
            log_out()
            flash(SIGN_IN_MESSAGE, "error")
            come_back = url_for("clover_acquisition_home")
            if _from_tips() and TIPS_HOME_URL.startswith("/"):
                come_back = TIPS_HOME_URL
            return None, redirect(url_for("login", next=come_back))
        if not shared_session.account_may_enter_domain(db, account, CLOVER_ACQUISITION_ACCESS_CODE):
            abort(403, description=(
                "This RF-One account does not have the Clover Acquisition access. "
                "Ask an RF-One administrator to grant it."
            ))
        return account, None

    def _view(db, location_id: int | None) -> dict:
        view = {"location_id": location_id, "active_run": None, "sync_point": None, "live_sync": None,
                "runs": [], "stale_run_ids": set(), "requested_by": {}, "tz_name": None, "location_name": None}
        if location_id is None:
            return view
        # RF-One UI Rules §1: every time on this page is shown in the
        # Location's own local time (Winter Park -> America/New_York).
        location = db.get(m.Location, location_id)
        view["tz_name"] = location.timezone if location is not None else None
        view["location_name"] = location.name if location is not None else None
        # The existing stale-run recovery: a job whose process died is
        # shown FAILED, never as a phantom RUNNING. Creates nothing.
        clover_jobs.recover_stale_run(db, location_id=location_id)
        view["active_run"] = clover_jobs.get_active_run(db, location_id=location_id)
        view["sync_point"] = clover_jobs.get_last_successful_sync_point(db, location_id=location_id)
        view["live_sync"] = clover_jobs.describe_live_sync(db, location_id=location_id)
        view["runs"] = clover_jobs.list_acquisition_runs(db, location_id=location_id, limit=20)
        view["stale_run_ids"] = {r.id for r in view["runs"] if clover_jobs.run_is_stale(r)}
        account_ids = {r.requested_by_account_id for r in view["runs"] if r.requested_by_account_id}
        if view["active_run"] is not None and view["active_run"].requested_by_account_id:
            account_ids.add(view["active_run"].requested_by_account_id)
        view["requested_by"] = {
            account_id: _person(db.get(m.RFOneAccount, account_id)) for account_id in account_ids
        }
        return view

    @app.route("/clover-acquisition")
    def clover_acquisition_home():
        with SessionFactory() as db:
            account, refusal = _authorized_account(db)
            if refusal is not None:
                return refusal
            location_id = _default_clover_location_id(db)
            acquisition = _view(db, location_id)
            # Prefill From date with the latest operational Business Date on
            # file, as the Tips page did; an explicit value always wins.
            from_date = request.args.get("from_date")
            if from_date is None:
                latest = None
                if location_id is not None:
                    latest = db.scalar(select(func.max(m.Order.business_date)).where(m.Order.location_id == location_id))
                from_date = latest.isoformat() if latest else ""
            return render_template(
                "clover_acquisition.html", acquisition=acquisition, identified_as=_person(account),
                from_date=from_date, through_date=request.args.get("through_date") or "",
                from_tips=_from_tips(),
            )

    def _start(request_job) -> None:
        with SessionFactory() as db:
            account, refusal = _authorized_account(db)
            if refusal is not None:
                return refusal
            require_csrf()
            location_id = _default_clover_location_id(db)
            if location_id is None:
                flash("No Clover-sourced Location is configured for this Restaurant — nothing to acquire.", "error")
                return None
            try:
                run = request_job(db, location_id, account.id)
            except ImportAlreadyRunningError:
                flash("A Clover acquisition is already in progress for this location. A new one can start "
                      "once it is COMPLETE or FAILED — its progress is shown below.", "error")
                return None
            except local_calendar.LocationTimezoneMissingError as exc:
                flash(str(exc), "error")
                return None
            except clover_jobs.NoSyncStartingPointError as exc:
                flash(str(exc), "error")
                return None
            except clover_jobs.JobLaunchError as exc:
                flash(f"The acquisition was accepted but could not be started, and has been marked FAILED: {exc}",
                      "error")
                return None
            flash(f"Acquisition #{run.id} accepted and started, requested by "
                  f"{_person(account)}. You can leave this page — it continues on "
                  "its own.", "info")
            return None

    @app.route("/clover-acquisition/sync-now", methods=["POST"])
    def clover_acquisition_sync_now():
        """Last successful synchronization -> now; no dates."""
        refusal = _start(lambda db, location_id, account_id: clover_jobs.request_sync_now(
            db, location_id=location_id, launcher=get_launcher(), requested_by_account_id=account_id,
        ))
        if refusal:
            return refusal
        if request.form.get("return_to") == RETURN_TIPS:
            return redirect(TIPS_HOME_URL)
        return redirect(url_for("clover_acquisition_home", **({"from": RETURN_TIPS} if _from_tips() else {})))

    @app.route("/clover-acquisition/backfill", methods=["POST"])
    def clover_acquisition_backfill():
        """The chosen period as the Location's LOCAL civil days: From
        00:00:00 through 23:59:59 of the Through day, America/New_York for
        Winter Park (UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001), converted to
        UTC instants for the unchanged central service. Not the Tips
        Business Date: the operating-day cutoff plays no part here."""
        from_date = request.form.get("from_date") or ""
        through_date = request.form.get("through_date") or ""
        with SessionFactory() as db:
            _account, refusal = _authorized_account(db)
            if refusal is not None:
                return refusal
        first_day, last_day = local_calendar.parse_day(from_date), local_calendar.parse_day(through_date)
        back = redirect(url_for("clover_acquisition_home", from_date=from_date, through_date=through_date,
                                **({"from": RETURN_TIPS} if _from_tips() else {})))
        if first_day is None or last_day is None:
            require_csrf()
            flash("Both From and Through dates are required.", "error")
            return back
        if last_day < first_day:
            require_csrf()
            flash("Through date must not be before From date.", "error")
            return back
        def request_backfill(db, location_id, account_id):
            location = db.get(m.Location, location_id)
            start, end = local_calendar.local_days_to_utc(first_day, last_day, location.timezone)
            return clover_jobs.request_historical_backfill(
                db, location_id=location_id, period_start=start, period_end=end, launcher=get_launcher(),
                requested_by_account_id=account_id,
            )

        refusal = _start(request_backfill)
        return refusal or back

    @app.route("/clover-acquisition/status.json")
    def clover_acquisition_status():
        """Polled by the page while a job runs. Same gates, answered in JSON."""
        with SessionFactory() as db:
            account = load_current_account(db)
            if account is None:
                return jsonify({"error": "Sign in to RF-One."}), 401
            if not shared_session.account_may_enter_domain(db, account, CLOVER_ACQUISITION_ACCESS_CODE):
                return jsonify({"error": "No Clover Acquisition access."}), 403
            location_id = _default_clover_location_id(db)
            active = clover_jobs.get_active_run(db, location_id=location_id) if location_id else None
            return jsonify({
                "active_run_id": active.id if active is not None else None,
                "active_status": active.status if active is not None else None,
            })
