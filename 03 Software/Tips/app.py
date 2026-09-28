"""RF-One Tips — imported Clover data view, Tip Distribution Rule
configuration, and Tip Distribution Engine Calculate/Review UI.

TECHNICAL_CONNECTORS_STRUCTURE_001: Clover data acquisition is a Technical
cross-domain connector concern (`rfone_data_store.technical.connectors.
clover`), not owned by Tips or by Restaurant — the actual fetch/upsert logic
lives in `rfone_data_store.technical.connectors.clover.acquisition` (usable
by Tips, and in the future Server Copilot, Server Performance, Sales, and
other Domains) and `rfone_data_store.technical.connectors.clover.live_sync`
(the near-real-time operational path). The connector itself has no concept
of Restaurant — only Location/Merchant/SourceSystem — so this app resolves
its Restaurant's own Clover Location (`_resolve_clover_location_id` below,
via the existing `RestaurantLocation` join) before calling in. What remains
here is only a read-only view of imported Clover rows. Starting an
acquisition (Sync Now, Historical Backfill) and following its job history
happen in RF-One Web's Clover Acquisition page, behind the RF-One login and
the CLOVER_ACQUISITION access (CLOVER_ACQUISITION_IDENTITY_001).

TIP_DISTRIBUTION_ENGINE_001 added the "Calculate Tips" tab (Calculate/Review/
drill-down), reading `rfone_data_store.tips.distribution_engine` — the ONLY
active Tips calculation engine (TIPS_LEGACY_ENGINE_RETIREMENT_001 removed
the earlier, experimental Payment-level `calculate_tips.py`/
`rfone_data_store/tips/engine.py` path entirely).

Unlike `Selection/app.py` (which deliberately uses its OWN local demo
database), this app uses RF-One's SHARED operational database by default —
`get_database_url()`'s own default (`RF-One Data Store/data/rfone.db`) is
left untouched here, exactly like `calculate_tips.py` — because Tip source
facts genuinely belong in the same database Payroll/Sales/Purchasing already
share, not an isolated sandbox. Set `RFONE_DATABASE_URL` to point elsewhere
(e.g. a disposable test database) for local development.

Follows the same small-local-Flask-app convention `Selection/app.py` and
`InvoiceIntake/app.py` already established: server-rendered Jinja2
templates, no JS framework/build step.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, url_for  # noqa: E402
from flask import session as flask_session  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.database import (  # noqa: E402
    create_configured_engine, create_session_factory, get_database_url,
)
from rfone_data_store import display_format  # noqa: E402
from rfone_data_store import local_calendar  # noqa: E402
from rfone_data_store import public_entry  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.technical.connectors.clover import acquisition_jobs as clover_jobs  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips import distribution_engine as engine_svc  # noqa: E402
from rfone_data_store.tips import distribution_rule_service as rule_svc  # noqa: E402
from rfone_data_store.tips import host_audit_report as audit_svc  # noqa: E402
from rfone_data_store.tips import review_mode_service as review_mode_svc  # noqa: E402
from rfone_data_store.tips import payment_connector as connector_svc  # noqa: E402
from rfone_data_store.tips import payment_cycle_service as cycle_svc  # noqa: E402
from rfone_data_store.tips import payment_instruction as pi_svc  # noqa: E402
from rfone_data_store.tips import payment_readiness as payment_readiness_svc  # noqa: E402
from rfone_data_store.tips import payout_process as payout_svc  # noqa: E402
from rfone_data_store.tips import readiness as readiness_svc  # noqa: E402
from rfone_data_store.tips import rule_ai_authoring as rule_ai_svc  # noqa: E402
from rfone_data_store.tips import schedule_service as sched_svc  # noqa: E402
from rfone_data_store.tips import validation_mode_service as validation_mode_svc  # noqa: E402
# TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §15 — the ONE existing
# RF-One login, read (never issued) here. See `rfone_identity.py` for the
# whole of the integration and what it needs from the deployment.
import rfone_identity  # noqa: E402
import imported_data_view  # noqa: E402
# TIPS_AWS_FINALIZATION_WORKFLOW_001 — validation lives in RF-One Web only;
# Tips links there through `RFONE_WEB_BASE_URL`.
import rfone_web_link  # noqa: E402
from rfone_data_store import restaurant_role_service as role_svc  # noqa: E402

UTC = timezone.utc

_DB_URL = get_database_url()
_engine = create_configured_engine(_DB_URL)
SessionFactory = create_session_factory(_engine)

app = Flask(__name__)
# The SAME signing secret RF-One Web uses, so Tips can verify the RF-One
# session cookie it reads (`_require_rfone_login` below). Tips never issues
# a login of its own; it also signs its flash messages with it.
app.secret_key = os.environ.get("RFONE_FLASK_SECRET_KEY") or os.urandom(24)
# UI_NAVIGATION_AND_LOCAL_TIME_001 — Tips is published on the SAME host as
# RF-One Web, under `/tips/` (one CloudFront entry in front of both App
# Runner services), so the RF-One session cookie reaches Tips. The cookie is
# the one RF-One Web issues: whenever Tips writes to it (a flash message,
# the shared CSRF token) it must re-issue it with exactly RF-One Web's
# attributes, never weaker ones (see `RF-One Web/app.py`).
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_PATH="/",
)

# The public path Tips is mounted under on the shared host. A request that
# arrives as `/tips/...` is served as `/...` with `/tips` as its script
# root, so every `url_for` link carries the prefix; a request without it
# (the service's own App Runner hostname, local development) is untouched.
TIPS_PATH_PREFIX = "/tips"


class _TipsPathPrefix:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == TIPS_PATH_PREFIX or path.startswith(TIPS_PATH_PREFIX + "/"):
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + TIPS_PATH_PREFIX
            environ["PATH_INFO"] = path[len(TIPS_PATH_PREFIX):] or "/"
        return self.wsgi_app(environ, start_response)


app.wsgi_app = _TipsPathPrefix(app.wsgi_app)


@app.before_request
def _send_direct_visits_to_the_official_entry():
    """A person who reaches Tips's technical App Runner hostname is sent to
    the same page under `/tips/` on RF-One's official address
    (`rfone_data_store.public_entry`, UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001)."""
    target = public_entry.official_redirect(request.method, request.headers, request.full_path,
                                            prefix=TIPS_PATH_PREFIX)
    if target is not None:
        return redirect(target, code=301)
    return None


# TIPS_ACCESS_AND_DRILLDOWN_001 — every Tips page and action requires the
# RF-One login: the SAME shared session RF-One Web issues, checked with the
# SAME lookup its `require_login` uses (`rfone_identity.current_account` ->
# `rfone_web_session.account_for_session`, revocation included). Tips has no
# login of its own; a visitor without a session is sent to RF-One's login
# and comes back to the page asked for. This is the common minimum only —
# every existing, more specific check (e.g. RF-One Web's own TIPS/Clover
# gates) stays exactly as it is.
#
# Left public on purpose, and only these: the stylesheet/images a login
# redirect itself needs (`static`, `shared_brand_logo`), the public dish
# guide (`training_menu`), and the Training blueprint, which has its own
# login. App Runner's health check is TCP, and no job calls Tips over HTTP.
_PUBLIC_ENDPOINTS = frozenset({"static", "shared_brand_logo", "training_menu"})


@app.before_request
def _require_rfone_login():
    if request.endpoint is None or request.endpoint in _PUBLIC_ENDPOINTS or request.blueprint == "training":
        return None
    with SessionFactory() as db_session:
        if rfone_identity.current_account(db_session) is not None:
            return None
    # Back to the page asked for; after a refused POST, to Tips's first page
    # (the form's own URL cannot be reopened with a GET).
    if request.method in ("GET", "HEAD"):
        next_path = request.script_root + request.full_path.rstrip("?")
    else:
        next_path = request.script_root + "/"
    target = rfone_web_link.login_url(next_path)
    if target is None:
        abort(401)
    return redirect(target)

# RF-One UI Rules (`03 Software/Shared UI/UI Rules.md`): local times,
# "Surname I." — the same shared formatter RF-One Web registers.
app.jinja_env.filters["local_dt"] = display_format.local_datetime
app.jinja_env.filters["short_name"] = display_format.employee_short_name
app.jinja_env.globals["zone_label"] = display_format.zone_label
app.jinja_env.globals["rfone_web_home_url"] = rfone_web_link.home_url
app.jinja_env.globals["rfone_home_url"] = rfone_web_link.home_url
app.jinja_env.globals["rfone_web_base_url"] = rfone_web_link.base_url
app.jinja_env.globals["rfone_web_run_url"] = rfone_web_link.tips_run_url
app.jinja_env.globals["rfone_web_not_configured_message"] = rfone_web_link.NOT_CONFIGURED_MESSAGE


def _default_restaurant(session) -> "m.Restaurant | None":
    """Rome's Flavours is currently the only Restaurant RF-One tracks — this
    picks it deterministically (lowest id) rather than offering a selector,
    per task §11's "keep it simple" and "do not redesign the global UI".
    Never creates one: unlike Selection's own isolated demo database, this
    app runs against the shared operational store, where the real
    Restaurant/Location/Clover onboarding already exists."""
    return session.scalars(select(m.Restaurant).order_by(m.Restaurant.id)).first()


def _max_order_business_date(session, restaurant_id: int):
    """The latest operational Business Date (`Order.business_date` —
    the canonical operating-day attribution owned by Sales/Order, per
    `01 Domains/Business Domain/Restaurant/Sales/Restaurant Sales
    Model.md` §6a) already on file for this Restaurant's Clover
    Location(s) — deliberately NOT `Order.created_at`/`modified_at`
    (ingestion/sync timestamps), which say when RF-One recorded the row,
    not which operating day it belongs to. Returns `None` when this
    Restaurant has no Order with a resolved Business Date yet — never
    guessed/invented."""
    location_ids_subq = select(m.RestaurantLocation.location_id).where(
        m.RestaurantLocation.restaurant_id == restaurant_id
    )
    return session.scalars(
        select(func.max(m.Order.business_date)).where(m.Order.location_id.in_(location_ids_subq))
    ).first()


# RF-One branding is application-wide, not Tips-owned: the canonical asset
# location is the shared, module-independent `03 Software/Shared UI/brand/`
# area (branding-ownership correction task) — a sibling of Tips, never
# copied into `Tips/static/`. `SHARED_UI_DIR` intentionally mirrors
# `_DATA_STORE_DIR`'s own "sibling Software module" pattern above.
_SHARED_UI_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Shared UI"))
_SHARED_BRAND_LOGOS_DIR = os.path.join(_SHARED_UI_DIR, "brand", "logos")


def _brand_logo_filename() -> str | None:
    """The RF-One product logo — distinct from `Restaurant.name`/the Core
    `Brand` concept (`00 Core/Brand.md`), which is a tenant's OWN business
    identity (e.g. Rome's Flavours'), not RF-One-the-product's own mark.
    `03 Software/Shared UI/brand/logos/` is the one canonical location for
    it, owned by RF-One, not by Tips; this returns the first real file
    found there (`.gitkeep` aside), or `None` if no official asset has been
    placed yet — never a fabricated/placeholder logo."""
    if not os.path.isdir(_SHARED_BRAND_LOGOS_DIR):
        return None
    for name in sorted(os.listdir(_SHARED_BRAND_LOGOS_DIR)):
        if name == ".gitkeep":
            continue
        if os.path.isfile(os.path.join(_SHARED_BRAND_LOGOS_DIR, name)):
            return name
    return None


@app.route("/shared-brand/logos/<path:filename>")
def shared_brand_logo(filename: str):
    """Serves a file directly from the shared, Tips-independent
    `Shared UI/brand/logos/` directory — the smallest mechanism that lets
    Tips consume RF-One's branding without copying/duplicating the asset
    into `Tips/static/`. Only this one directory is exposed (never an
    arbitrary path), and only for reading an existing file — no upload/
    write capability is introduced."""
    return send_from_directory(_SHARED_BRAND_LOGOS_DIR, filename)


# The staff dish/wine training guide is a self-contained prototype with no
# Domain/business logic of its own. It lives in its own sibling Software
# module (`03 Software/Training/`), following the same "sibling module,
# served via send_from_directory" pattern as `_SHARED_BRAND_LOGOS_DIR`/
# `shared_brand_logo` above — this route only serves the existing static
# file; it introduces no new data model, API, or admin surface.
_TRAINING_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Training"))


@app.route("/training/menu")
def training_menu():
    return send_from_directory(_TRAINING_DIR, "RF-One-Training.html")


# Training's own operational area (login, student path, trainer area, pill
# quizzes — first version). `03 Software/Training/` is not a Python package
# (matching the "sibling module" placement above, not a Tips-owned concern),
# so its own directory is added to sys.path and its Blueprint imported like
# any other local module — the one and only place Tips references Training
# beyond the static-file route above. Everything the blueprint needs (its
# own database wiring, auth/session helpers, templates) lives in that
# directory; Training never imports anything from this file. It reuses this
# same Flask app's `secret_key` (already set above) for its session cookie —
# not a new session mechanism. Training keeps its own login; Tips's own
# routes require the RF-One login (`_require_rfone_login`).
if _TRAINING_DIR not in sys.path:
    sys.path.insert(0, _TRAINING_DIR)
from routes import training_bp  # noqa: E402

app.register_blueprint(training_bp)


@app.context_processor
def inject_brand_context() -> dict:
    """Page-header branding, sourced from RF-One's own canonical business
    identity — never a Tips-specific brand asset/config. `Restaurant.name`
    is the one canonical business-identity field that already exists
    (`Restaurant`'s own docstring: "canonical business identity/context");
    reusing it here (the same row `_default_restaurant()` resolves
    everywhere else in this app) is the smallest correct way to make the
    header data-driven instead of a hardcoded string.

    `brand_logo_filename` is the separate, static RF-One PRODUCT logo (see
    `_brand_logo_filename()`) — orthogonal to the Core `Brand` concept
    (tenant business identity), which still has no persisted model and is
    NOT what this renders. No Tips-local branding store is invented here:
    this only reads whatever file (if any) already exists at the one
    canonical static path.

    A `@app.context_processor` (rather than passing `restaurant=` from every
    `render_template` call) guarantees every Tips page gets the same brand
    name/logo even where a route does not otherwise need the Restaurant row
    (e.g. `distribution_rule_detail`)."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        # RF-One UI Rules §1: `tz` is the Restaurant's Clover Location's
        # own timezone, the zone every time on a Tips page is shown in
        # (`|local_dt(tz)`). None -> the formatter says "UTC" honestly.
        location_id = _resolve_clover_location_id(session, restaurant.id) if restaurant is not None else None
        location = session.get(m.Location, location_id) if location_id is not None else None
        return {
            "brand_name": restaurant.name if restaurant is not None else "RF-One",
            "brand_logo_filename": _brand_logo_filename(),
            "tz": location.timezone if location is not None else None,
        }


def _resolve_clover_location_id(session, restaurant_id: int) -> int | None:
    """Restaurant -> Clover Location, resolved HERE — a Restaurant-Domain
    join (`RestaurantLocation`) — never inside the Clover connector itself
    (TECHNICAL_CONNECTORS_STRUCTURE_001: the connector has no concept of
    Restaurant, only Location/Merchant/SourceSystem). Returns `None` if this
    Restaurant has no Clover-sourced Location configured."""
    return session.scalars(
        select(m.Location.id)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id)
        .where(m.RestaurantLocation.restaurant_id == restaurant_id, m.SourceSystem.code == "CLOVER")
    ).first()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


CLOVER_ACQUISITION_ACCESS_CODE = "CLOVER_ACQUISITION"


def _clover_acquisition_panel(session, restaurant) -> dict:
    """What the Tips "Clover Acquisition" tab shows (UI_NAVIGATION_AND_LOCAL_TIME_001):
    the last completed synchronization in the Location's local time, whether
    a job is running, and — for a signed-in account holding the
    CLOVER_ACQUISITION access — a Sync Now form that posts to RF-One Web's
    ONE Sync Now action. Read-only here: Tips never starts, recovers or
    records an acquisition itself."""
    location_id = _resolve_clover_location_id(session, restaurant.id) if restaurant is not None else None
    location = session.get(m.Location, location_id) if location_id is not None else None
    panel = {
        "location_id": location_id,
        "tz_name": location.timezone if location is not None else None,
        "sync_point": None, "active_run": None, "active_requested_by": None,
        "signed_in": False, "may_sync": False, "csrf_token": None,
        "sync_now_url": rfone_web_link.clover_sync_now_url(),
        "status_url": rfone_web_link.clover_status_url(),
        "full_page_url": rfone_web_link.clover_acquisition_url(),
        "login_url": rfone_web_link.login_url(url_for("home")),
    }
    if location_id is not None:
        panel["sync_point"] = clover_jobs.get_last_successful_sync_point(session, location_id=location_id)
        active = clover_jobs.get_active_run(session, location_id=location_id)
        # A job with no sign of life is not "in progress": RF-One Web's
        # Sync Now recovers it (FAILED) before starting the new one.
        if active is not None and not clover_jobs.run_is_stale(active):
            panel["active_run"] = active
            if active.requested_by_account_id:
                panel["active_requested_by"] = display_format.employee_short_name(
                    shared_session.account_display_name(session.get(m.RFOneAccount, active.requested_by_account_id))
                )
    account = rfone_identity.current_account(session)
    panel["signed_in"] = account is not None
    panel["may_sync"] = shared_session.account_may_enter_domain(session, account, CLOVER_ACQUISITION_ACCESS_CODE)
    if panel["may_sync"]:
        # The SAME per-session token RF-One Web checks on the POST.
        panel["csrf_token"] = shared_session.csrf_token(flask_session)
    return panel


def _employee_names(session, source_employee_ids) -> dict:
    """Clover employee id -> "Surname I." (RF-One UI Rules §2). The id stays
    in the database; it is never what a person reads."""
    ids = {i for i in source_employee_ids if i}
    if not ids:
        return {}
    employees = session.scalars(select(m.Employee).where(m.Employee.source_employee_id.in_(ids))).all()
    return {e.source_employee_id: display_format.employee_short_name(e.display_name) for e in employees}


@app.route("/")
def home():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        through_date = request.args.get("through_date") or ""

        # Prefill "From date" with the latest operational Business Date
        # already on file, so an operator does not have to guess where a
        # gap starts — but only on a fresh page load (no explicit
        # `from_date` in the URL, e.g. right after submitting a Backfill,
        # which redirects here with both dates set): an explicit value is
        # never overridden. Left as a normal, editable value — never
        # advanced by a day, never read-only.
        from_date_param = request.args.get("from_date")
        no_business_date_data = False
        if from_date_param is not None:
            from_date = from_date_param
        else:
            from_date = ""
            if restaurant is not None:
                max_business_date = _max_order_business_date(session, restaurant.id)
                if max_business_date is not None:
                    from_date = max_business_date.isoformat()
                else:
                    no_business_date_data = True

        imported = imported_data_view.empty()
        shifts_rows = []
        if restaurant is not None:
            location_ids_subq = select(m.RestaurantLocation.location_id).where(
                m.RestaurantLocation.restaurant_id == restaurant.id
            )

            # UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001: the chosen dates are the
            # Location's local civil days (00:00 -> 23:59:59), never UTC
            # days, and never the Tips Business Date. A read-only view.
            start = end = None
            first_day, last_day = local_calendar.parse_day(from_date), local_calendar.parse_day(through_date)
            clover_location_id = _resolve_clover_location_id(session, restaurant.id)
            clover_location = session.get(m.Location, clover_location_id) if clover_location_id else None
            if first_day is not None and last_day is not None:
                try:
                    start, end = local_calendar.local_days_to_utc(
                        first_day, last_day, clover_location.timezone if clover_location else None,
                    )
                except local_calendar.LocationTimezoneMissingError as exc:
                    flash(str(exc), "error")
            if start is not None and end is not None:
                # IMPORTED_CLOVER_DATA_CONTROL_001 — summaries first (to hold
                # next to Clover's Orders and Transactions reports), then the
                # Order and Payment listings. Read-only.
                imported = imported_data_view.build(
                    session, location_ids_subq=location_ids_subq, start=start, end=end,
                )

                shift_stmt = (
                    select(m.Shift)
                    .where(
                        m.Shift.location_id.in_(location_ids_subq) | m.Shift.location_id.is_(None),
                        m.Shift.clock_in >= start,
                        m.Shift.clock_in <= end,
                    )
                    .order_by(m.Shift.clock_in)
                )
                for shift in session.scalars(shift_stmt).all():
                    employee = session.get(m.Employee, shift.employee_id)
                    shifts_rows.append(
                        {
                            "employee_id": employee.source_employee_id if employee else None,
                            "clock_in": shift.clock_in,
                            "clock_out": shift.clock_out,
                            "source_shift_id": shift.source_shift_id,
                        }
                    )

        employee_names = _employee_names(
            session, [r["employee_id"] for r in imported["payments_rows"] + imported["orders_rows"] + shifts_rows],
        )
        clover = _clover_acquisition_panel(session, restaurant)
        return render_template(
            "home.html", restaurant=restaurant, from_date=from_date, through_date=through_date,
            no_business_date_data=no_business_date_data, clover=clover, tz=clover["tz_name"],
            employee_names=employee_names,
            **imported, shifts_rows=shifts_rows,
            active_nav="historical-backfill",
        )


# CLOVER_ACQUISITION_IDENTITY_001 — this app starts no Clover acquisition
# and keeps no job history. Sync Now and Historical Backfill start real work
# on AWS and may be started only by a signed-in RF-One account holding the
# CLOVER_ACQUISITION access; both, and the job history, live in RF-One Web
# (`/clover-acquisition`). Requests to the former action URLs
# (`/historical-backfill`, `/clover-acquisition/sync-now`) match no route
# here and are refused with no effect.
#
# UI_NAVIGATION_AND_LOCAL_TIME_001 — now that Tips shares RF-One Web's host
# and session, the Clover Acquisition tab shows the last update and a Sync
# Now button, but the button is a form posting to RF-One Web's ONE Sync Now
# action (`_clover_acquisition_panel`): no second Sync Now exists here.


# ---------------------------------------------------------------------------
# Tip Distribution Engine — minimal Calculate/Review UI
# (TIP_DISTRIBUTION_ENGINE_001 §17-18). No manual adjustments, no
# Review/Approve/Lock workflow, no Payment Batch — see the task report.
# ---------------------------------------------------------------------------


# TIPS_STATELESS_CALCULATION_001 — period selection is now a full
# START datetime / END datetime pair, expressed in the Restaurant's own
# local timezone, and every view recalculates on demand.

# TIPS_BRANCH_CONFIG_BUSINESS_DATE_AND_ELIGIBILITY_002 §2 — the UTC+02:00
# fallback that used to live here is GONE. RF-One never substitutes a
# timezone or an operating-day cutoff: a guessed cutoff attributes a whole
# night's takings to the wrong Business Date and nobody sees it happen. A
# Tips calculation on an unconfigured Location now refuses, naming the
# Location and the missing field(s).
_LOCAL_DT_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")


def _restaurant_period_config(session, restaurant):
    """The Branch's business-day boundary, read from the EXISTING
    `Location.timezone` / `Location.operating_day_cutoff_time`
    configuration — never from a Tips-local constant, so a different
    Restaurant or Corporate can choose a different boundary without
    touching Tips.

    §2 — NO FALLBACK. When either field is unset this returns
    `configured=False` with a reason naming the Location and the missing
    field(s), and the caller refuses to calculate. `tz`/`cutoff` come back
    `None` so no code downstream can accidentally compute with a guess."""
    if restaurant is None:
        return None, None, None, False, "No Restaurant selected."
    location_id = session.scalars(
        select(m.RestaurantLocation.location_id)
        .where(m.RestaurantLocation.restaurant_id == restaurant.id)
    ).first()
    location = session.get(m.Location, location_id) if location_id else None
    if location is None:
        return None, None, None, False, (
            f"Restaurant {restaurant.id} has no associated Location, so no Business Day "
            "configuration can be resolved."
        )
    missing = []
    if not location.timezone:
        missing.append("timezone")
    if location.operating_day_cutoff_time is None:
        missing.append("operating_day_cutoff_time")
    if missing:
        return None, None, None, False, (
            f"Location {location.id} ({location.name}) is missing its Business Day "
            f"configuration: {', '.join(missing)}. Tips cannot determine a Business Date "
            "without it, and RF-One never substitutes a default timezone or cutoff. "
            "Configure the Location, then recalculate."
        )
    try:
        tz = ZoneInfo(location.timezone)
    except Exception:
        return None, None, None, False, (
            f"Location {location.id} ({location.name}) has timezone "
            f"{location.timezone!r}, which is not a valid IANA identifier."
        )
    return location.timezone, tz, location.operating_day_cutoff_time, True, ""


def _default_period_local(session, restaurant):
    """Default Business Day window: the latest Business Date with Orders,
    from its cutoff time to the SAME time the following day (e.g. 04:00 to
    04:00 for Winter Park). Returned as local-datetime strings for the
    form inputs."""
    _, tz, cutoff, configured, _ = _restaurant_period_config(session, restaurant)
    if not configured:
        return "", ""
    business_date = None
    if restaurant is not None:
        business_date = readiness_svc.get_latest_business_date_with_orders(session, restaurant.id)
    if business_date is None:
        business_date = datetime.now(tz).date()
    start_local = datetime.combine(business_date, cutoff)
    end_local = start_local + timedelta(days=1)
    return start_local.strftime("%Y-%m-%dT%H:%M"), end_local.strftime("%Y-%m-%dT%H:%M")


def _parse_local_dt(value: str, tz):
    for fmt in _LOCAL_DT_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def _calculation_period_dt(start_at: str, end_at: str, tz) -> tuple[datetime, datetime] | None:
    """START/END local datetimes -> `[period_start, period_end)` in UTC.

    Both bounds are explicit instants chosen by the operator, so any
    interval works — a few hours, a business day, a week, or a window that
    overlaps one calculated a moment ago. `period_end` stays EXCLUSIVE,
    matching the engine's Settlement-Time filter."""
    if not start_at or not end_at:
        return None
    start = _parse_local_dt(start_at, tz)
    end = _parse_local_dt(end_at, tz)
    if start is None or end is None:
        return None
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _result_fingerprint(voluntary: int, gratuity: int, control_difference: int, payable_by_employee) -> str:
    """CALCULATE_AND_CONSOLIDATE_001 — identifies ONE result: its totals and
    what each employee is owed. The page carries it into Consolidate, and a
    saved run with the same fingerprint for the same Business Dates is that
    same result already consolidated."""
    pairs = ",".join(f"{e}:{a}" for e, a in sorted(payable_by_employee))
    return f"{voluntary}|{gratuity}|{control_difference}|{pairs}"


def _fingerprint_of_calculation(totals, review_rows) -> str:
    return _result_fingerprint(
        totals.voluntary_minor, totals.gratuity_minor, totals.control_difference_minor,
        [(row.employee_id, row.final_entitlement_minor) for row in review_rows],
    )


def _fingerprint_of_run(session, run) -> str:
    entitlements = session.scalars(
        select(m.TipEntitlement).where(m.TipEntitlement.calculation_run_id == run.id)
    ).all()
    return _result_fingerprint(
        run.voluntary_total_minor or 0, run.gratuity_total_minor or 0, run.control_difference_minor or 0,
        [(e.employee_id, e.payable_amount_minor) for e in entitlements],
    )


def _consolidated_run_for(session, restaurant_id, first, last, fingerprint):
    """The saved run that already holds exactly this result for exactly
    these Business Dates, newest first; `None` when there is none."""
    runs = session.scalars(
        select(m.TipDistributionCalculationRun)
        .where(
            m.TipDistributionCalculationRun.restaurant_id == restaurant_id,
            m.TipDistributionCalculationRun.first_business_date == first,
            m.TipDistributionCalculationRun.last_business_date == last,
        )
        .order_by(m.TipDistributionCalculationRun.id.desc())
    ).all()
    return next((r for r in runs if _fingerprint_of_run(session, r) == fingerprint), None)


def _business_dates_of_window(start_at: str, end_at: str, tz, cutoff):
    """CALCULATE_LOCAL_WINDOW_001 — the inclusive Business Date range a local
    window covers EXACTLY (it starts and ends at the Location's cutoff), or
    `None`. A Saved Period is a Business Date range, so only such a window
    can be consolidated as the very result on screen."""
    start, end = _parse_local_dt(start_at, tz), _parse_local_dt(end_at, tz)
    if start is None or end is None or start.time() != cutoff or end.time() != cutoff or end <= start:
        return None
    return start.date(), end.date() - timedelta(days=1)


def _window_of_business_dates(first, last, cutoff) -> tuple[str, str]:
    """The local window of an inclusive Business Date range (cutoff to
    cutoff), as form values — how a link that names Business Dates opens."""
    start_local = datetime.combine(first, cutoff)
    end_local = datetime.combine(last + timedelta(days=1), cutoff)
    return start_local.strftime("%Y-%m-%dT%H:%M"), end_local.strftime("%Y-%m-%dT%H:%M")


def _parse_business_date(value: str | None):
    """A Business Date as the operator typed it (YYYY-MM-DD), or `None`.

    Deliberately a DATE, never a datetime: a Business Date is not an
    instant, and the Location's own cutoff is what turns it into one
    (`distribution_engine.business_date_window_utc`)."""
    parsed = _parse_date(value)
    return parsed.date() if parsed else None


@app.route("/calculate-tips")
def calculate_tips_home():
    """Two actions (CALCULATE_AND_CONSOLIDATE_001), on the exact local window
    the person chooses (CALCULATE_LOCAL_WINDOW_001).

    CALCULATE: FROM date+time -> THROUGH date+time in the Location's local
    time, end exclusive, through the engine's own `calculate_tips` — exactly
    what this page computed before. Opens on the latest Business Date,
    cutoff to cutoff. Writes nothing; repeat it as often as you like.

    CONSOLIDATE: a Saved Period is a Business Date range, so the result on
    screen can be consolidated as-is when the window is whole Business Days
    (cutoff to cutoff); for any other window the page says so. No dates are
    asked again, and the same period with the same result is saved once."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        tz_name, tz, cutoff, tz_configured, config_error = _restaurant_period_config(session, restaurant)

        start_at = request.args.get("start_at") or ""
        end_at = request.args.get("end_at") or ""
        named_first = _parse_business_date(request.args.get("from_date"))
        named_last = _parse_business_date(request.args.get("through_date"))
        if (not start_at or not end_at) and named_first and named_last and cutoff:
            # A link that names Business Dates (e.g. back from Consolidate).
            start_at, end_at = _window_of_business_dates(named_first, named_last, cutoff)
        if not start_at or not end_at:
            start_at, end_at = _default_period_local(session, restaurant)

        result = None
        review_rows = []
        period_error = None
        # §2 — refuse before computing anything when the Branch has no
        # Business Day configuration. No guessed timezone, no guessed cutoff.
        period = _calculation_period_dt(start_at, end_at, tz) if tz else None
        if restaurant is None:
            period_error = "No Restaurant exists in this database yet."
        elif not tz_configured:
            period_error = config_error
        elif period is None:
            period_error = "Enter a valid From and Through date and time."
        elif period[1] <= period[0]:
            period_error = "Through must be after From."
        else:
            result = engine_svc.calculate_tips(
                session, restaurant_id=restaurant.id, period_start=period[0], period_end=period[1],
            )
            if result.blocked_reason:
                period_error = result.blocked_reason
                result = None
            else:
                review_rows = engine_svc.build_employee_review(session, result)

        review_mode = (
            review_mode_svc.get_review_mode(session, restaurant_id=restaurant.id)
            if restaurant is not None else None
        )
        # §4 — the payment header, derived from the same rows the table
        # pays from so the two can never disagree.
        totals = (
            engine_svc.build_operational_totals(result, review_rows)
            if result is not None else None
        )
        business_dates = (
            _business_dates_of_window(start_at, end_at, tz, cutoff) if result is not None else None
        )
        first, last = business_dates or (None, None)
        fingerprint = _fingerprint_of_calculation(totals, review_rows) if totals is not None else ""
        consolidated_run = (
            _consolidated_run_for(session, restaurant.id, first, last, fingerprint)
            if business_dates else None
        )

        def shown(value):
            parsed = _parse_local_dt(value, tz) if tz else None
            return parsed.strftime("%m/%d/%Y %H:%M") if parsed else value

        return render_template(
            "calculate_tips.html", restaurant=restaurant,
            start_at=start_at, end_at=end_at,
            window_label=f"{shown(start_at)} → {shown(end_at)}",
            from_date=first.isoformat() if first else "", through_date=last.isoformat() if last else "",
            first_business_date=first, last_business_date=last,
            result=result, review_rows=review_rows, period_error=period_error, totals=totals,
            fingerprint=fingerprint, consolidated_run=consolidated_run,
            tz_name=tz_name, tz_configured=tz_configured,
            cutoff=cutoff.strftime("%H:%M") if cutoff else None,
            config_error=config_error, review_mode=review_mode,
            audit_mode=(review_mode == m.TIPS_REVIEW_MODE_AUDIT),
            active_nav="calculate-tips",
        )


@app.route("/calculate-tips/run", methods=["POST"])
def calculate_tips_run():
    """CALCULATE — carries the chosen local window onto the Calculate Tips
    URL; the calculation itself happens on render and writes nothing."""
    return redirect(url_for(
        "calculate_tips_home",
        start_at=request.form.get("start_at") or "", end_at=request.form.get("end_at") or "",
    ))


@app.route("/calculate-tips/consolidate", methods=["POST"])
def calculate_tips_consolidate():
    """CONSOLIDATE the result the page is showing, for the period it shows.

    Saved through the existing `run_svc.save_calculation_run` (a Saved
    Period, validated and paid exactly as before). That service calculates
    the period itself; the saved result is then compared with the one the
    person was looking at, and nothing is kept unless they are identical —
    a Clover sync in between would otherwise consolidate figures nobody saw.
    The same period with the same result already saved is not saved again."""
    first = _parse_business_date(request.form.get("from_date"))
    last = _parse_business_date(request.form.get("through_date"))
    shown = request.form.get("fingerprint") or ""
    back = url_for("calculate_tips_home", from_date=request.form.get("from_date") or "",
                   through_date=request.form.get("through_date") or "")
    if first is None or last is None or last < first or not shown:
        flash("Calculate a period first, then consolidate it.", "error")
        return redirect(back)

    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(back)
        if _consolidated_run_for(session, restaurant.id, first, last, shown) is not None:
            flash("This result is already consolidated.", "info")
            return redirect(back)
        run, reason = run_svc.save_calculation_run(
            session, restaurant_id=restaurant.id,
            first_business_date=first, last_business_date=last,
        )
        if run is None:
            session.rollback()
            flash(reason, "error")
            return redirect(back)
        if _fingerprint_of_run(session, run) != shown:
            session.rollback()
            flash("The data for this period changed after you calculated it. Nothing was consolidated: "
                  "check the new result below, then consolidate again.", "error")
            return redirect(back)
        session.commit()
    flash(f"Period consolidated: {first:%m/%d/%Y} → {last:%m/%d/%Y}.", "info")
    return redirect(back)


@app.route("/tips-runs")
def tips_run_history():
    """§19 — every saved Calculation Run for this Restaurant, newest first.

    Non-final runs are listed too. A history showing only what was approved
    would hide the recalculations that led there, which is precisely the
    part an auditor asks about."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        runs = (
            run_svc.list_runs(session, restaurant_id=restaurant.id)
            if restaurant is not None else []
        )
        validation_mode = (
            validation_mode_svc.get_validation_mode(session, restaurant_id=restaurant.id)
            if restaurant is not None else m.TIPS_VALIDATION_MODE_MANUAL
        )
        return render_template(
            "tips_run_history.html", restaurant=restaurant, runs=runs,
            validation_mode=validation_mode, active_nav="tips-runs",
        )


@app.route("/tips-runs/<int:run_id>")
def tips_run_report(run_id: int):
    """§18 — the Calculation Run Report, read back from what was saved.

    This route does NOT recalculate. `run_svc.get_run_report` has no access
    to the engine at all, so reopening a final report next year shows the
    figures it was approved on even if a rule, a shift or an order has been
    edited since.

    Read-only for finalization (TIPS_AWS_FINALIZATION_WORKFLOW_001): the
    page shows why a period cannot yet be final and links to RF-One Web's
    `/tips/runs/<run_id>`, the one place a person validates it. Tips has no
    validation route of its own."""
    with SessionFactory() as session:
        report = run_svc.get_run_report(session, run_id)
        if report is None:
            flash(f"No Calculation Run with id {run_id}.", "error")
            return redirect(url_for("tips_run_history"))
        blockers = run_svc.finalization_blockers(session, report["run"])
        return render_template(
            "tips_run_report.html", report=report, run=report["run"],
            validation_mode=validation_mode_svc.get_validation_mode(
                session, restaurant_id=report["run"].restaurant_id,
            ),
            finalization_blockers=blockers,
            active_nav="tips-runs",
        )


@app.route("/calculate-tips/order/<int:order_id>")
def calculate_tips_order_drilldown(order_id: int):
    """Recalculates the selected window and explains one Order from that
    fresh result — no stored allocation rows are read."""
    start_at = request.args.get("start_at") or ""
    end_at = request.args.get("end_at") or ""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        _, tz, _, _, _ = _restaurant_period_config(session, restaurant)
        period = _calculation_period_dt(start_at, end_at, tz)
        drilldown = None
        if restaurant is not None and period is not None and period[1] > period[0]:
            result = engine_svc.calculate_tips(
                session, restaurant_id=restaurant.id, period_start=period[0], period_end=period[1],
            )
            drilldown = engine_svc.get_order_drilldown(session, result, order_id)

        if drilldown is None:
            flash("That Order is not within the selected period.", "error")
            return redirect(url_for("calculate_tips_home", start_at=start_at, end_at=end_at))

        # `get_order_drilldown` returns a dict (the template reads it with
        # Jinja's attribute syntax, which falls back to keys; Python does not).
        # RF-One UI Rules §2: people as "Surname I.", never an id.
        recipient_ids = {a.recipient_employee_id for a in drilldown["allocations"] if a.recipient_employee_id}
        recipient_names = {
            e.id: display_format.employee_short_name(e.display_name)
            for e in (session.scalars(select(m.Employee).where(m.Employee.id.in_(recipient_ids))).all()
                      if recipient_ids else [])
        }
        order = drilldown["order"]
        order_employee_name = _employee_names(session, [order.source_employee_id]).get(order.source_employee_id)
        return render_template(
            "order_drilldown.html", restaurant=restaurant, start_at=start_at, end_at=end_at,
            drilldown=drilldown, recipient_names=recipient_names, order_employee_name=order_employee_name,
            active_nav="calculate-tips",
        )


def _general_configuration_context(session, restaurant) -> dict:
    """The General Configuration section (formerly the Tips Configuration
    tab): Review Mode, Validation Mode, Calculation and Payment Schedules."""
    calc_config = None
    payment_config = None
    readiness_state = None
    review_mode = m.TIPS_REVIEW_MODE_AUDIT
    if restaurant is not None:
        calc_config = sched_svc.get_calculation_schedule_effective_at(session, restaurant_id=restaurant.id)
        payment_config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
        readiness_state = readiness_svc.describe_readiness(session, restaurant.id)
        review_mode = review_mode_svc.get_review_mode(session, restaurant_id=restaurant.id)
    # §16 — a SEPARATE setting from Review Mode above, deliberately. One
    # decides which report the UI emphasises; this one decides whether a
    # human has to approve money.
    validation_mode = (
        validation_mode_svc.get_validation_mode(session, restaurant_id=restaurant.id)
        if restaurant is not None else m.TIPS_VALIDATION_MODE_MANUAL
    )
    return {
        "calc_config": calc_config, "payment_config": payment_config, "readiness_state": readiness_state,
        "review_mode": review_mode, "validation_mode": validation_mode,
        "validation_modes": m.TIPS_VALIDATION_MODES, "schedule_modes": m.TIPS_SCHEDULE_MODES,
        "connector_codes": connector_svc.KNOWN_CONNECTOR_CODES,
    }


@app.route("/configuration")
def configuration_home():
    """CONFIGURATION_TAB_001 — the one Tips Configuration page: Distribution
    Rules, then General Configuration. Nothing here changes what either
    section did on its former tab."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        return render_template("configuration.html", **_distribution_rules_base_context(session, restaurant))


@app.route("/tips-configuration")
def tips_configuration_home():
    """Former tab URL, kept so saved links still work."""
    return redirect(url_for("configuration_home", _anchor="general-configuration"))


@app.route("/tips-configuration/validation-mode", methods=["POST"])
def tips_configuration_set_validation_mode():
    """§16 — set the Restaurant's Tips Validation Mode.

    Choosing AUTOMATIC means deciding that nobody will sign off this
    Restaurant's Tips periods, so the change itself records WHO made it
    (§15) when an RF-One identity is available. The setting is still
    changeable without one — it is a configuration, not an approval — but
    an unattributed switch to AUTOMATIC is called out rather than accepted
    silently."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="general-configuration"))
        account = rfone_identity.current_account(session)
        validation_mode = request.form.get("validation_mode") or ""
        try:
            validation_mode_svc.set_validation_mode(
                session, restaurant_id=restaurant.id, validation_mode=validation_mode,
                updated_by_account_id=account.id if account else None,
            )
            session.commit()
            if validation_mode == m.TIPS_VALIDATION_MODE_AUTOMATIC and account is None:
                flash(
                    "Validation Mode set to AUTOMATIC, but no RF-One user was identified for "
                    "this change, so the decision is recorded without a name. Tips periods "
                    "will now finalize themselves whenever the period balances.",
                    "error",
                )
            else:
                flash(f"Tips Validation Mode set to {validation_mode}.", "summary")
        except ValueError as exc:
            session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("configuration_home", _anchor="general-configuration"))


@app.route("/tips-configuration/review-mode", methods=["POST"])
def tips_configuration_set_review_mode():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="general-configuration"))
        review_mode = request.form.get("review_mode") or ""
        try:
            review_mode_svc.set_review_mode(session, restaurant_id=restaurant.id, review_mode=review_mode)
            session.commit()
            flash(f"Review Mode set to {review_mode}.", "summary")
        except ValueError as exc:
            session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("configuration_home", _anchor="general-configuration"))


@app.route("/tips-configuration/calculation-schedule", methods=["POST"])
def tips_configuration_set_calculation_schedule():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="general-configuration"))
        mode = request.form.get("mode") or ""
        interval_days = request.form.get("interval_days", type=int)
        execution_time = _parse_time(request.form.get("execution_time"))
        anchor_date_dt = _parse_date(request.form.get("anchor_date"))
        try:
            sched_svc.set_calculation_schedule(
                session, restaurant_id=restaurant.id, mode=mode, interval_days=interval_days,
                execution_time=execution_time, anchor_date=anchor_date_dt.date() if anchor_date_dt else None,
                created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
            flash("Calculation Schedule updated.", "summary")
        except sched_svc.ScheduleConfigError as exc:
            session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("configuration_home", _anchor="general-configuration"))


@app.route("/tips-configuration/payment-schedule", methods=["POST"])
def tips_configuration_set_payment_schedule():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="general-configuration"))
        mode = request.form.get("mode") or ""
        interval_days = request.form.get("interval_days", type=int)
        execution_time = _parse_time(request.form.get("execution_time"))
        anchor_date_dt = _parse_date(request.form.get("anchor_date"))
        connector_code = (request.form.get("connector_code") or "").strip() or None
        mercury_source_account_id = (request.form.get("mercury_source_account_id") or "").strip() or None
        auto_approval_mode = (request.form.get("auto_approval_mode") or "").strip() or None
        try:
            sched_svc.set_payment_schedule(
                session, restaurant_id=restaurant.id, mode=mode, interval_days=interval_days,
                execution_time=execution_time, anchor_date=anchor_date_dt.date() if anchor_date_dt else None,
                connector_code=connector_code, mercury_source_account_id=mercury_source_account_id,
                auto_approval_mode=auto_approval_mode,
                created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
            flash("Payment Schedule updated.", "summary")
        except sched_svc.ScheduleConfigError as exc:
            session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("configuration_home", _anchor="general-configuration"))


@app.route("/tips-configuration/run-calculation-now", methods=["POST"])
def tips_configuration_run_calculation_now():
    """"Run Calculation Now": always targets the latest Business Date via
    `readiness.describe_readiness`, gated by Clover readiness exactly like
    the automatic scheduler would be — manual and automatic triggers share
    the exact same gated entry point, `payout_process.run_calculation_now`."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="general-configuration"))
        result = payout_svc.run_calculation_now(session, restaurant_id=restaurant.id)
        session.commit()
        if result.ran:
            flash(
                f"Business Date {result.business_date}: calculated, {result.entitlements_created} "
                "Tip Entitlement(s) persisted.",
                "summary",
            )
        else:
            flash(result.blocked_reason or "Nothing to calculate.", "error")
    return redirect(url_for("configuration_home", _anchor="general-configuration"))


# ---------------------------------------------------------------------------
# Tips Payment Control (TASK_TIPS_COMPLETE_001 §13/§14) — authorized visual
# control surface over the Payment Cycle: REVIEW (read-only) and
# APPROVE & PAY (gated by `authority_service.authorize()`, never `is_admin`).
# Not a workflow engine — every action here delegates entirely to
# `tips.payment_cycle_service`/`tips.payment_instruction`.
#
# Connector-neutral (STEP 12B Product Owner decision): every route below
# resolves the connector to invoke from THIS Restaurant's own configured
# `TipsPaymentScheduleConfig.connector_code`
# (`tips.payment_connector.resolve_connector`) — never constructs a Mercury
# client directly. Missing/unknown configuration surfaces as
# `connector_error`/a flashed message, never a silent Mercury fallback.
# ---------------------------------------------------------------------------


def _resolve_restaurant_connector(session, restaurant_id: int) -> "connector_svc.PaymentConnector":
    """Fails closed (`connector_svc.ConnectorConfigurationError`) when this
    Restaurant has no/an unknown connector configured — callers below
    always let this propagate to their own `except` clause, never catch it
    here and substitute a default."""
    payment_config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant_id)
    connector_code = payment_config.connector_code if payment_config is not None else None
    return connector_svc.resolve_connector(connector_code)


@app.route("/payment-control")
def payment_control_home():
    return _render_payment_control(cycle_id=None)


@app.route("/payment-control/cycle/<int:cycle_id>")
def payment_control_cycle(cycle_id: int):
    """Cognito deep-link target: a stable, resolvable URL for ONE specific
    Payment Cycle, independent of whichever Restaurant `_default_restaurant()`
    would otherwise pick. No Cognito capability is implemented by this
    route — it only makes a future one's "open Payment Control on the
    correct Payment Cycle" possible, by existing as a real, addressable
    route now. Works for a Cycle in ANY status (OPEN for action, APPROVED
    for after-the-fact review), not only an actionable one."""
    return _render_payment_control(cycle_id=cycle_id)


def _render_payment_control(*, cycle_id: int | None):
    with SessionFactory() as session:
        restaurant = None
        deep_link_cycle: "m.TipPaymentCycle | None" = None
        if cycle_id is not None:
            deep_link_cycle = session.get(m.TipPaymentCycle, cycle_id)
            if deep_link_cycle is None:
                flash(f"Payment Cycle {cycle_id} not found.", "error")
                return redirect(url_for("payment_control_home"))
            restaurant = session.get(m.Restaurant, deep_link_cycle.restaurant_id)
        else:
            restaurant = _default_restaurant(session)

        calc_state = None
        cycle_readiness = None
        payment_readiness = None
        open_cycle = None
        instructions = []
        employees_by_id = {}
        references_by_employee = {}
        attention_items_by_instruction = {}
        entitlements_by_instruction = {}
        connector_balance = None
        connector_error = None
        identities = []

        if restaurant is not None:
            # Only Acting Identities actually authorized to Approve & Pay
            # THIS Restaurant are offered — never a global list a user could
            # pick from and then be rejected server-side (the server-side
            # gate in `approve_and_pay_cycle` remains authoritative either
            # way; this is a UI convenience, not a second/divergent check).
            identities = [
                identity
                for identity in session.scalars(select(m.ActingIdentity).order_by(m.ActingIdentity.display_name))
                if cycle_svc.can_approve_and_pay(session, acting_identity=identity, restaurant_id=restaurant.id)
            ]
            calc_state = readiness_svc.describe_readiness(session, restaurant.id)
            cycle_readiness = cycle_svc.describe_payment_cycle_readiness(session, restaurant.id)
            # The SAME `payment_readiness.describe_payment_readiness` gate
            # `approve_and_pay_cycle` itself enforces server-side; shown here
            # for the READY/NOT READY summary and to enable/disable
            # Approve & Pay — never a second, divergent readiness definition.
            payment_readiness = payment_readiness_svc.describe_payment_readiness(session, restaurant.id)
            open_cycle = deep_link_cycle if deep_link_cycle is not None else cycle_readiness.open_cycle
            if open_cycle is not None:
                instructions = list(
                    session.scalars(
                        select(m.TipPaymentInstruction)
                        .where(m.TipPaymentInstruction.payment_cycle_id == open_cycle.id)
                        .order_by(m.TipPaymentInstruction.employee_id)
                    )
                )
                employee_ids = [i.employee_id for i in instructions]
                if employee_ids:
                    employees_by_id = {
                        e.id: e for e in session.scalars(select(m.Employee).where(m.Employee.id.in_(employee_ids))).all()
                    }
                    references_by_employee = {
                        r.employee_id: r
                        for r in session.scalars(
                            select(m.EmployeeExternalPaymentAccount).where(
                                m.EmployeeExternalPaymentAccount.employee_id.in_(employee_ids),
                                m.EmployeeExternalPaymentAccount.is_active.is_(True),
                            )
                        )
                    }
                attention_items_by_instruction = {
                    i.id: session.get(m.AttentionItem, i.attention_item_id)
                    for i in instructions if i.attention_item_id is not None
                }
                # Per-payee Detail view: Business Dates included,
                # gross/source tips, distributions transferred in/out, final
                # payable — all already persisted per TipEntitlement, never
                # re-derived here.
                instruction_ids = [i.id for i in instructions]
                entitlements_by_instruction: dict[int, list] = {i: [] for i in instruction_ids}
                for entitlement in session.scalars(
                    select(m.TipEntitlement)
                    .where(m.TipEntitlement.tip_payment_instruction_id.in_(instruction_ids))
                    .order_by(m.TipEntitlement.business_date)
                ):
                    entitlements_by_instruction[entitlement.tip_payment_instruction_id].append(entitlement)
            try:
                connector = _resolve_restaurant_connector(session, restaurant.id)
                account_id = cycle_svc.resolve_source_account_id(session, restaurant.id, connector)
                if account_id is not None:
                    accounts = {a.id: a for a in connector.get_accounts()}
                    account = accounts.get(account_id)
                    # Never the full account object ("NON mostrare dati
                    # bancari completi") — only the one figure this control
                    # surface needs.
                    connector_balance = account.available_balance if account is not None else None
            except connector_svc.PaymentConnectorError as exc:
                connector_error = str(exc)

        return render_template(
            "payment_control.html", restaurant=restaurant, calc_state=calc_state, cycle_readiness=cycle_readiness,
            payment_readiness=payment_readiness, open_cycle=open_cycle, instructions=instructions,
            employees_by_id=employees_by_id, references_by_employee=references_by_employee,
            attention_items_by_instruction=attention_items_by_instruction,
            entitlements_by_instruction=entitlements_by_instruction,
            connector_balance=connector_balance, connector_error=connector_error, identities=identities,
            is_deep_link=cycle_id is not None, active_nav="payment-control",
        )


@app.route("/payment-control/start-cycle", methods=["POST"])
def payment_control_start_cycle():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("payment_control_home"))
        cycle = cycle_svc.start_payment_cycle(
            session, restaurant_id=restaurant.id, triggered_by=m.TIP_PAYMENT_CYCLE_TRIGGER_MANUAL,
        )
        session.commit()
        if cycle is None:
            flash("Nothing unpaid to aggregate into a Payment Cycle.", "error")
        else:
            flash(f"Payment Cycle {cycle.id} opened — review below before Approve & Pay.", "summary")
    return redirect(url_for("payment_control_home"))


@app.route("/payment-control/approve-and-pay", methods=["POST"])
def payment_control_approve_and_pay():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        cycle = cycle_svc.get_open_cycle(session, restaurant.id) if restaurant is not None else None
        if cycle is None:
            flash("No open Payment Cycle to approve.", "error")
            return redirect(url_for("payment_control_home"))

        acting_identity_id = request.form.get("acting_identity_id", type=int)
        acting_identity = session.get(m.ActingIdentity, acting_identity_id) if acting_identity_id else None
        if acting_identity is None:
            flash("Select the Acting Identity approving this payout.", "error")
            return redirect(url_for("payment_control_home"))

        try:
            connector = _resolve_restaurant_connector(session, restaurant.id)
            source_account_id = cycle_svc.resolve_source_account_id(session, restaurant.id, connector)
            if source_account_id is None:
                flash(f"No {connector.connector_code} source account configured or available.", "error")
                return redirect(url_for("payment_control_home"))
            result = cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle, acting_identity=acting_identity, connector=connector,
                source_account_id=source_account_id,
            )
            session.commit()
        except cycle_svc.PaymentNotReadyError as exc:
            # NOT READY is a normal, expected wait, never a financial
            # error: a calm "info" message, not the red "error" styling
            # below (still no connector call, still no state change).
            session.rollback()
            flash(str(exc), "info")
            return redirect(url_for("payment_control_home"))
        except cycle_svc.ApproveAndPayError as exc:
            session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("payment_control_home"))
        except connector_svc.PaymentConnectorError as exc:
            session.rollback()
            flash(f"Payment connector error: {exc}", "error")
            return redirect(url_for("payment_control_home"))

        flash(
            f"Payment Cycle {cycle.id} approved: {result.submitted_count} instruction(s) submitted, "
            f"{result.needs_attention_count} needing attention.",
            "summary",
        )
    return redirect(url_for("payment_control_home"))


@app.route("/payment-control/instruction/<int:instruction_id>/retry", methods=["POST"])
def payment_control_retry_instruction(instruction_id: int):
    with SessionFactory() as session:
        instruction = session.get(m.TipPaymentInstruction, instruction_id)
        if instruction is None:
            flash("Payment Instruction not found.", "error")
            return redirect(url_for("payment_control_home"))
        cycle = session.get(m.TipPaymentCycle, instruction.payment_cycle_id)
        try:
            connector = _resolve_restaurant_connector(session, cycle.restaurant_id) if cycle is not None else None
            source_account_id = instruction.provider_account_id or (
                cycle_svc.resolve_source_account_id(session, cycle.restaurant_id, connector)
                if cycle is not None and connector is not None else None
            )
            if source_account_id is None or connector is None:
                flash("No payment connector source account available for retry.", "error")
                return redirect(url_for("payment_control_home"))
            cycle_svc.retry_instruction(session, instruction, connector, source_account_id=source_account_id)
            session.commit()
        except connector_svc.PaymentConnectorError as exc:
            session.rollback()
            flash(f"Payment connector error: {exc}", "error")
            return redirect(url_for("payment_control_home"))
        flash(f"Payment Instruction {instruction.id} retried — status is now {instruction.status}.", "summary")
    return redirect(url_for("payment_control_home"))


@app.route("/payment-control/employee/<int:employee_id>/link-recipient", methods=["POST"])
def payment_control_link_recipient(employee_id: int):
    """Links an Employee to an EXISTING connector recipient by exact name
    (never creates one). Deactivates any prior active reference for this
    Employee/connector rather than deleting it (Historical Integrity)."""
    recipient_name = (request.form.get("recipient_name") or "").strip()
    if not recipient_name:
        flash("Recipient name is required.", "error")
        return redirect(url_for("payment_control_home"))
    with SessionFactory() as session:
        employee = session.get(m.Employee, employee_id)
        if employee is None:
            flash("Employee not found.", "error")
            return redirect(url_for("payment_control_home"))
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("payment_control_home"))
        try:
            connector = _resolve_restaurant_connector(session, restaurant.id)
            recipient = connector.find_recipient_by_name(recipient_name)
        except connector_svc.PaymentConnectorError as exc:
            flash(f"Payment connector error: {exc}", "error")
            return redirect(url_for("payment_control_home"))
        if recipient is None:
            flash(f"No {connector.connector_code} recipient named {recipient_name!r} was found.", "error")
            return redirect(url_for("payment_control_home"))

        existing = session.scalars(
            select(m.EmployeeExternalPaymentAccount).where(
                m.EmployeeExternalPaymentAccount.employee_id == employee_id,
                m.EmployeeExternalPaymentAccount.provider == connector.connector_code,
                m.EmployeeExternalPaymentAccount.is_active.is_(True),
            )
        ).all()
        for row in existing:
            row.is_active = False
        session.add(
            m.EmployeeExternalPaymentAccount(
                employee_id=employee_id, provider=connector.connector_code, provider_recipient_id=recipient.id,
                is_active=True,
            )
        )
        session.commit()
        flash(f"Employee {employee_id} linked to {connector.connector_code} recipient {recipient.name!r}.", "summary")
    return redirect(url_for("payment_control_home"))


# ---------------------------------------------------------------------------
# Tip Distribution Rule — minimal UI (TIPS_DISTRIBUTION_RULES_001 §12).
# List / create / edit-through-versioning / activate-deactivate / view
# history only — no distribution-results UI (explicitly out of scope).
# ---------------------------------------------------------------------------

def _parse_rate(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _distribution_rules_base_context(session, restaurant) -> dict:
    """Shared by the plain GET and the AI-authoring POST handlers below —
    the existing structured Rules list / roles / Advanced form no longer
    lives in its own isolated view, so every render (whichever route
    produced it) shows the same up-to-date Rules list."""
    rules_rows = []
    roles = []
    if restaurant is not None:
        roles = list(
            session.scalars(
                select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == restaurant.id).order_by(m.RestaurantRole.name)
            )
        )
        for rule in rule_svc.list_rules(session, restaurant.id):
            versions = rule_svc.list_versions(session, rule.id)
            current = versions[-1] if versions else None
            rules_rows.append(
                {
                    "id": rule.id,
                    "is_active": rule.is_active,
                    "version_count": len(versions),
                    "current": current,
                    "source_role_name": (
                        current.source_role.name if current and current.source_role
                        else ("Service Owner (Order owner)" if current else "-")
                    ),
                    "recipient_role_name": current.recipient_role.name if current else "-",
                }
            )
    return {
        "restaurant": restaurant, "rules_rows": rules_rows, "roles": roles,
        "calculation_bases": m.TIP_DISTRIBUTION_CALCULATION_BASES, "active_nav": "configuration",
        # CONFIGURATION_TAB_001 — one page: the General Configuration
        # section renders with every Distribution Rules response too.
        **_general_configuration_context(session, restaurant),
    }


def _ai_history_from_json(raw: str | None) -> list["rule_ai_svc.ConversationTurn"]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    turns = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("role"), str) and isinstance(item.get("content"), str):
            turns.append(rule_ai_svc.ConversationTurn(role=item["role"], content=item["content"]))
    return turns


def _ai_history_to_json(turns: list["rule_ai_svc.ConversationTurn"]) -> str:
    return json.dumps([asdict(t) for t in turns])


@app.route("/distribution-rules")
def distribution_rules_home():
    """Former tab URL, kept so saved links still work."""
    return redirect(url_for("configuration_home", _anchor="distribution-rules"))


@app.route("/distribution-rules/ai/interpret", methods=["POST"])
def distribution_rule_ai_interpret():
    """Natural-language Rule authoring — the PRIMARY way to create/change a
    Tip Distribution Rule (AI_GOVERNED_RULE_AUTHORING_001 §12, applied to
    Tips). Stateless: the entire conversation round-trips through hidden
    form fields (`history_json`), never a server-side session — so the same
    `rule_ai_authoring.interpret_rule_statement` call underneath this route
    could equally be driven by a future chat/voice interface (task §10)."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        base_ctx = _distribution_rules_base_context(session, restaurant)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))

        statement = (request.form.get("statement") or "").strip()
        history = _ai_history_from_json(request.form.get("history_json"))
        rule_id = request.form.get("rule_id", type=int)

        try:
            result = rule_ai_svc.interpret_rule_statement(
                session, restaurant_id=restaurant.id, statement=statement, history=history, rule_id=rule_id,
            )
        except rule_ai_svc.AIRuleAuthoringUnavailable as exc:
            flash(f"AI rule interpretation is currently unavailable ({exc}). Use the Advanced form below.", "error")
            return render_template("configuration.html", **base_ctx)

        new_history = list(history) + [rule_ai_svc.ConversationTurn(role="user", content=statement)]

        if result.outcome == rule_ai_svc.OUTCOME_CLARIFICATION_NEEDED:
            new_history.append(rule_ai_svc.ConversationTurn(role="assistant", content=result.clarification.question))
            return render_template(
                "configuration.html", **base_ctx,
                ai_mode="CLARIFICATION", ai_question=result.clarification.question,
                ai_history_json=_ai_history_to_json(new_history), ai_rule_id=rule_id,
            )

        if result.outcome == rule_ai_svc.OUTCOME_UNSUPPORTED:
            new_history.append(
                rule_ai_svc.ConversationTurn(role="assistant", content=result.unsupported.unsupported_summary)
            )
            return render_template(
                "configuration.html", **base_ctx,
                ai_mode="UNSUPPORTED", ai_unsupported=result.unsupported,
                ai_history_json=_ai_history_to_json(new_history), ai_rule_id=rule_id,
            )

        # OUTCOME_PROPOSED
        proposal = result.proposal
        new_history.append(rule_ai_svc.ConversationTurn(role="assistant", content=proposal.human_readable_summary))
        return render_template(
            "configuration.html", **base_ctx,
            ai_mode="PROPOSED", ai_proposal=proposal, ai_proposal_json=json.dumps(asdict(proposal)),
            ai_history_json=_ai_history_to_json(new_history), ai_rule_id=rule_id,
        )


@app.route("/distribution-rules/ai/confirm", methods=["POST"])
def distribution_rule_ai_confirm():
    """The ONLY route that turns an AI-produced proposal into a persisted
    `TipDistributionRuleVersion` — reachable only via explicit human CONFIRM
    (task §6). Re-validates the proposal from scratch (`confirm_rule_
    proposal` never trusts the round-tripped hidden field blindly)."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        try:
            data = json.loads(request.form.get("proposal_json") or "{}")
            proposal = rule_ai_svc.RuleProposal(**data)
        except (TypeError, ValueError, json.JSONDecodeError):
            flash("The proposed Rule could not be read back — please describe the Rule again.", "error")
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))

        created_by = (request.form.get("created_by") or "").strip() or None
        try:
            rule_ai_svc.confirm_rule_proposal(session, proposal, created_by=created_by)
            session.commit()
        except ValueError as exc:
            session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))

        flash(f"Rule confirmed: {proposal.human_readable_summary}", "summary")
        return redirect(url_for("configuration_home", _anchor="distribution-rules"))


@app.route("/distribution-rules/ai/cancel", methods=["POST"])
def distribution_rule_ai_cancel():
    """Explicit CANCEL (task §6) — nothing was ever written for a proposal
    that only exists in a round-tripped hidden field, so this route's only
    job is to discard it and return to a clean state."""
    flash("Cancelled — nothing was created.", "summary")
    return redirect(url_for("configuration_home", _anchor="distribution-rules"))


@app.route("/distribution-rules/new", methods=["POST"])
def distribution_rule_create():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))

        source_role_id = request.form.get("source_role_id", type=int)
        recipient_role_id = request.form.get("recipient_role_id", type=int)
        calculation_base = request.form.get("calculation_base") or ""
        rate = _parse_rate(request.form.get("rate"))
        effective_from = _parse_date(request.form.get("effective_from"))
        created_by = (request.form.get("created_by") or "").strip() or None

        if not source_role_id or not recipient_role_id or rate is None or effective_from is None:
            flash("Source Role, Recipient Role, Rate, and Effective From are all required.", "error")
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))

        try:
            rule_svc.create_rule(
                session, restaurant_id=restaurant.id, source_role_id=source_role_id,
                recipient_role_id=recipient_role_id, calculation_base=calculation_base, rate=rate,
                effective_from=effective_from, created_by=created_by,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("configuration_home", _anchor="distribution-rules"))


@app.route("/distribution-rules/<int:rule_id>")
def distribution_rule_detail(rule_id: int):
    with SessionFactory() as session:
        rule = rule_svc.get_rule(session, rule_id)
        if rule is None:
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))
        versions = rule_svc.list_versions(session, rule_id)
        roles = list(
            session.scalars(
                select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == rule.restaurant_id).order_by(m.RestaurantRole.name)
            )
        )
        return render_template(
            "distribution_rule_detail.html", rule=rule, versions=versions, roles=roles,
            calculation_bases=m.TIP_DISTRIBUTION_CALCULATION_BASES, active_nav="configuration",
        )


@app.route("/distribution-rules/<int:rule_id>/versions", methods=["POST"])
def distribution_rule_new_version(rule_id: int):
    with SessionFactory() as session:
        rule = rule_svc.get_rule(session, rule_id)
        if rule is None:
            return redirect(url_for("configuration_home", _anchor="distribution-rules"))

        source_role_id = request.form.get("source_role_id", type=int)
        recipient_role_id = request.form.get("recipient_role_id", type=int)
        calculation_base = request.form.get("calculation_base") or ""
        rate = _parse_rate(request.form.get("rate"))
        effective_from = _parse_date(request.form.get("effective_from"))
        created_by = (request.form.get("created_by") or "").strip() or None

        if not source_role_id or not recipient_role_id or rate is None or effective_from is None:
            flash("Source Role, Recipient Role, Rate, and Effective From are all required.", "error")
            return redirect(url_for("distribution_rule_detail", rule_id=rule_id))

        try:
            new_version = rule_svc.create_new_version(
                session, rule_id, source_role_id=source_role_id, recipient_role_id=recipient_role_id,
                calculation_base=calculation_base, rate=rate, effective_from=effective_from, created_by=created_by,
            )
            # TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §7 — say out
            # loud what entering this version did to the others. Silently
            # re-statusing a rule somebody scheduled for next month is how a
            # configuration change becomes a surprise on a payslip.
            replaced = getattr(new_version, "replaced_versions", {"old": [], "cancelled": []})
            session.commit()
            parts = [f"Version {new_version.version_number} is now in force."]
            if replaced["old"]:
                parts.append(
                    f"Version(s) {', '.join(str(i) for i in replaced['old'])} became OLD and "
                    "stop at this version's start; their own past is unchanged."
                )
            if replaced["cancelled"]:
                parts.append(
                    f"Version(s) {', '.join(str(i) for i in replaced['cancelled'])} fell inside "
                    "this version's coverage and were CANCELLED — they now govern nothing."
                )
            flash(" ".join(parts), "summary")
        except ValueError as exc:
            session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("distribution_rule_detail", rule_id=rule_id))


@app.route("/distribution-rules/<int:rule_id>/toggle-active", methods=["POST"])
def distribution_rule_toggle_active(rule_id: int):
    with SessionFactory() as session:
        rule = rule_svc.get_rule(session, rule_id)
        if rule is not None:
            rule_svc.set_active(session, rule_id, not rule.is_active)
            session.commit()
        return redirect(request.form.get("next") or url_for("configuration_home", _anchor="distribution-rules"))


# ---------------------------------------------------------------------------
# Host Tip Audit / Explain (HOST_TIP_AUDIT_001) — explains the EXISTING Tip
# Distribution Engine's own already-persisted output (`tips.host_audit_
# report`); never a second calculation path. Read-only throughout.
# ---------------------------------------------------------------------------

def _host_audit_filters(session, restaurant):
    employees = []
    if restaurant is not None:
        location_ids = list(
            session.scalars(
                select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant.id)
            )
        )
        if location_ids:
            employees = list(
                session.scalars(
                    select(m.Employee).where(m.Employee.location_id.in_(location_ids)).order_by(m.Employee.display_name)
                )
            )
    return employees


def _host_audit_report_from_request(session, restaurant):
    """Shared by the HTML view and the CSV export — same filters, same
    report, so the export is always an exact mirror of what is displayed."""
    employee_id = request.args.get("employee_id", type=int)
    start_at = request.args.get("start_at") or ""
    end_at = request.args.get("end_at") or ""
    if restaurant is None or not employee_id or not start_at or not end_at:
        return None
    _, tz, _, _, _ = _restaurant_period_config(session, restaurant)
    period = _calculation_period_dt(start_at, end_at, tz)
    if period is None or period[1] <= period[0]:
        return None
    period_start, period_end = period
    # Calculated fresh here; the CSV export calls this same helper, so the
    # download always mirrors exactly what the page showed.
    return audit_svc.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=employee_id,
        period_start=period_start, period_end=period_end,
    )


@app.route("/host-audit")
def host_audit_home():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        employees = _host_audit_filters(session, restaurant)
        report = _host_audit_report_from_request(session, restaurant)
        return render_template(
            "host_audit.html", restaurant=restaurant, employees=employees, report=report,
            employee_id=request.args.get("employee_id", type=int),
            start_at=request.args.get("start_at") or "",
            end_at=request.args.get("end_at") or "", active_nav="host-audit",
        )


@app.route("/host-audit/export.csv")
def host_audit_export_csv():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        report = _host_audit_report_from_request(session, restaurant)
        if report is None:
            flash("Select a Restaurant, Host Employee, and a start/end date and time first.", "error")
            return redirect(url_for("host_audit_home", **request.args))

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=audit_svc.CSV_FIELDNAMES)
        writer.writeheader()
        # RF-One UI Rules: the export mirrors the screen — local times,
        # "Surname I." — in the Restaurant's Clover Location timezone.
        location_id = _resolve_clover_location_id(session, restaurant.id)
        location = session.get(m.Location, location_id) if location_id else None
        for row in audit_svc.report_to_csv_rows(report, tz_name=location.timezone if location else None):
            writer.writerow(row)

        filename = (
            f"host-tip-audit-{display_format.employee_short_name(report.host_employee_name)}-"
            f"{request.args.get('start_at')}_{request.args.get('end_at')}.csv"
        ).replace(":", "")
        return Response(
            buffer.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


# ---------------------------------------------------------------------------
# Restaurant Roles — the role DEFINITION registry (`rfone_data_store.
# restaurant_role_service`), standalone from Tip Distribution Rules and
# reusable elsewhere. Distribution Rules only ever READS this list (for
# both "Source Role" and "Recipient Role" — one registry, two uses); this
# is the one place roles are created/edited. Deliberately never touches
# `EmployeeAssignment` (which Employee holds a role, when) — that stays a
# separate concern.
# ---------------------------------------------------------------------------


@app.route("/roles")
def restaurant_roles_home():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        roles = role_svc.list_roles(session, restaurant.id) if restaurant is not None else []
        return render_template(
            "restaurant_roles_home.html", restaurant=restaurant, roles=roles, active_nav="configuration",
        )


@app.route("/roles/new", methods=["GET", "POST"])
def restaurant_role_new():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("restaurant_roles_home"))

        if request.method == "POST":
            name = request.form.get("name", "")
            code = request.form.get("code", "")
            description = request.form.get("description", "")
            active = request.form.get("active") == "on"
            try:
                role_svc.create_role(
                    session, restaurant_id=restaurant.id, name=name, code=code,
                    description=description, active=active,
                )
                session.commit()
            except ValueError as exc:
                session.rollback()
                flash(str(exc), "error")
                return render_template("restaurant_role_form.html", mode="create", role=None, restaurant=restaurant), 400
            flash(f"Role {name!r} created.", "info")
            return redirect(url_for("restaurant_roles_home"))

        return render_template("restaurant_role_form.html", mode="create", role=None, restaurant=restaurant)


@app.route("/roles/<int:role_id>/edit", methods=["GET", "POST"])
def restaurant_role_edit(role_id: int):
    with SessionFactory() as session:
        role = role_svc.get_role(session, role_id)
        if role is None:
            flash("Role not found.", "error")
            return redirect(url_for("restaurant_roles_home"))

        if request.method == "POST":
            name = request.form.get("name", "")
            code = request.form.get("code", "")
            description = request.form.get("description", "")
            active = request.form.get("active") == "on"
            try:
                role_svc.update_role(session, role, name=name, code=code, description=description, active=active)
                session.commit()
            except ValueError as exc:
                session.rollback()
                flash(str(exc), "error")
                return render_template("restaurant_role_form.html", mode="edit", role=role, restaurant=None), 400
            flash("Role updated.", "info")
            return redirect(url_for("restaurant_roles_home"))

        return render_template("restaurant_role_form.html", mode="edit", role=role, restaurant=None)


if __name__ == "__main__":
    app.run(debug=True, port=5057)
