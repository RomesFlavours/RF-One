"""RF-One Tips — Historical Backfill (Clover), Tip Distribution Rule
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
here, under "Historical Backfill", is only the UI trigger for an
operator-chosen date-range re-import/recovery — explicitly NOT the normal
operational data-acquisition mechanism, which is Live Sync (see
`clover_live_sync.py`), running independently of this web app.

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

import os
import sys
from dataclasses import asdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.database import (  # noqa: E402
    create_configured_engine, create_session_factory, get_database_url,
)
from rfone_data_store.technical.connectors.clover.acquisition import (  # noqa: E402
    ImportAlreadyRunningError, MODE_BACKFILL, get_order_settlement_time, import_clover_period,
)
from rfone_data_store.tips import distribution_engine as engine_svc  # noqa: E402
from rfone_data_store.tips import distribution_rule_service as rule_svc  # noqa: E402
from rfone_data_store.tips import payment_cycle_service as cycle_svc  # noqa: E402
from rfone_data_store.tips import payment_instruction as pi_svc  # noqa: E402
from rfone_data_store.tips import payment_readiness as payment_readiness_svc  # noqa: E402
from rfone_data_store.tips import payout_process as payout_svc  # noqa: E402
from rfone_data_store.tips import readiness as readiness_svc  # noqa: E402
from rfone_data_store.tips import schedule_service as sched_svc  # noqa: E402
from rfone_data_store.technical.connectors.mercury.client import (  # noqa: E402
    MercuryClient, MercuryConnectorError,
)
from rfone_data_store import restaurant_role_service as role_svc  # noqa: E402

UTC = timezone.utc

_DB_URL = get_database_url()
_engine = create_configured_engine(_DB_URL)
SessionFactory = create_session_factory(_engine)

app = Flask(__name__)
# Only used to flash the import summary across the POST -> redirect -> GET
# round trip below — never an Authentication mechanism (Tips has none; see
# GLOBAL_INTEGRITY_FIX_002's ActingIdentity work for that concern in
# Selection, not replicated here since this task does not touch identity).
app.secret_key = os.environ.get("RFONE_FLASK_SECRET_KEY") or os.urandom(24)


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
# not a new session mechanism, and Tips's own routes remain exactly as
# unauthenticated as before this addition.
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
        return {
            "brand_name": restaurant.name if restaurant is not None else "RF-One",
            "brand_logo_filename": _brand_logo_filename(),
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

        recent_runs = []
        payments_rows = []
        orders_rows = []
        shifts_rows = []
        if restaurant is not None:
            # Shows every Clover acquisition run touching this Restaurant's
            # Location, regardless of mode — a Historical Backfill triggered
            # here AND any Live Sync cycle running independently
            # (`clover_live_sync.py`) both write through the same Clover
            # Technical Connector (`technical.connectors.clover.acquisition`)
            # and the same "CLOVER_ACQUISITION..." notes prefix.
            recent_runs = list(
                session.scalars(
                    select(m.IngestionRun)
                    .where(m.IngestionRun.notes.isnot(None), m.IngestionRun.notes.like("CLOVER_ACQUISITION%"))
                    .order_by(m.IngestionRun.id.desc())
                    .limit(5)
                )
            )

            location_ids_subq = select(m.RestaurantLocation.location_id).where(
                m.RestaurantLocation.restaurant_id == restaurant.id
            )

            start = _parse_date(from_date)
            end = _parse_date(through_date)
            if start is not None and end is not None:
                payment_stmt = (
                    select(m.Payment)
                    .join(m.Order, m.Payment.order_id == m.Order.id)
                    .where(
                        m.Order.location_id.in_(location_ids_subq),
                        m.Payment.created_at >= start,
                        m.Payment.created_at <= end,
                    )
                    .order_by(m.Payment.created_at)
                )
                for payment in session.scalars(payment_stmt).all():
                    tip = session.get(m.PaymentTip, payment.id)
                    payments_rows.append(
                        {
                            "source_payment_id": payment.source_payment_id,
                            "employee_id": payment.source_employee_id,
                            "amount": payment.amount,
                            "tip_present": tip is not None,
                            "tip_amount": tip.amount if tip is not None else None,
                            "result": payment.result,
                            "created_at": payment.created_at,
                        }
                    )

                # Task §3/§12 — "Order is the business unit" / "inspect
                # imported Orders". One row per Order touched in the period,
                # with its Settlement Time (spec §5) and gratuity total —
                # never a per-Payment view of the same economic fact.
                order_stmt = (
                    select(m.Order)
                    .where(
                        m.Order.location_id.in_(location_ids_subq),
                        m.Order.created_at >= start,
                        m.Order.created_at <= end,
                    )
                    .order_by(m.Order.created_at)
                )
                for order in session.scalars(order_stmt).all():
                    fees = session.scalars(select(m.OrderFee).filter_by(order_id=order.id)).all()
                    num_payments = len(session.scalars(select(m.Payment).where(m.Payment.order_id == order.id)).all())
                    orders_rows.append(
                        {
                            "source_order_id": order.source_order_id,
                            "employee_id": order.source_employee_id,
                            "total": order.total,
                            "state": order.state,
                            "payment_state": order.payment_state,
                            "num_payments": num_payments,
                            "gratuity_total": sum(f.amount or 0 for f in fees),
                            "settlement_time": get_order_settlement_time(session, order.id),
                        }
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

        return render_template(
            "home.html", restaurant=restaurant, from_date=from_date, through_date=through_date,
            no_business_date_data=no_business_date_data,
            recent_runs=recent_runs, payments_rows=payments_rows, orders_rows=orders_rows, shifts_rows=shifts_rows,
            active_nav="historical-backfill",
        )


@app.route("/historical-backfill", methods=["POST"])
def run_historical_backfill():
    """CLOVER_DATA_ACQUISITION_ARCHITECTURE_001 §2 — this is historical
    backfill/recovery only (an operator-chosen date range, on demand), never
    the normal operational data-acquisition path. Live Sync
    (`clover_live_sync.py`) is what keeps RF-One's Clover data current
    second-to-second; this button exists for filling a known gap or
    re-importing a period after a data-quality concern, not for routine use."""
    from_date = request.form.get("from_date") or ""
    through_date = request.form.get("through_date") or ""
    start = _parse_date(from_date)
    end = _parse_date(through_date)

    if start is None or end is None:
        flash("Both From and Through dates are required.", "error")
        return redirect(url_for("home"))
    if end < start:
        flash("Through date must not be before From date.", "error")
        return redirect(url_for("home"))
    # Inclusive through the end of the selected Through day.
    end = end.replace(hour=23, minute=59, second=59)

    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet — nothing to import into.", "error")
            return redirect(url_for("home"))

        location_id = _resolve_clover_location_id(session, restaurant.id)
        if location_id is None:
            flash("No Clover-sourced Location is configured for this Restaurant — nothing to import.", "error")
            return redirect(url_for("home"))

        try:
            summary = import_clover_period(
                session, location_id=location_id, period_start=start, period_end=end, mode=MODE_BACKFILL,
            )
        except ImportAlreadyRunningError:
            # No second Clover fetch, no second write transaction:
            # `import_clover_period` never started either when this is
            # raised — whether the conflict is with another Backfill or
            # with a Live Sync cycle currently mid-flight makes no
            # difference, both share the same Location-scoped guard.
            # Clean, user-facing rejection instead of a stack trace or a
            # second concurrent SQLite writer.
            flash("An import is already in progress. Please wait for it to finish.", "error")
            return redirect(url_for("home", from_date=from_date, through_date=through_date))
        session.commit()

    flash(_summary_flash(summary), "summary")
    return redirect(url_for("home", from_date=from_date, through_date=through_date))


def _summary_flash(summary) -> dict:
    data = asdict(summary)
    data["period_start"] = summary.period_start.isoformat()
    data["period_end"] = summary.period_end.isoformat()
    return data


# ---------------------------------------------------------------------------
# Tip Distribution Engine — minimal Calculate/Review UI
# (TIP_DISTRIBUTION_ENGINE_001 §17-18). No manual adjustments, no
# Review/Approve/Lock workflow, no Payment Batch — see the task report.
# ---------------------------------------------------------------------------


def _calculation_period(from_date: str, through_date: str) -> tuple[datetime, datetime] | None:
    """From/Through -> `[period_start, period_end)` — inclusive through the
    end of the selected Through day. Unlike `/import`'s own
    `end.replace(hour=23, minute=59, second=59)` convention (an INCLUSIVE
    upper bound), `distribution_engine`'s Settlement-Time filter is
    EXCLUSIVE at `period_end` (task §9/§16), so the Through day's end is
    expressed as the following day's midnight instead. Returns `None` if
    either date is missing/unparseable."""
    start = _parse_date(from_date)
    end = _parse_date(through_date)
    if start is None or end is None:
        return None
    return start, end + timedelta(days=1)


@app.route("/calculate-tips")
def calculate_tips_home():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        from_date = request.args.get("from_date") or ""
        through_date = request.args.get("through_date") or ""

        run = None
        review_rows = []
        if restaurant is not None and from_date and through_date:
            period = _calculation_period(from_date, through_date)
            if period is not None:
                period_start, period_end = period
                run = engine_svc.get_latest_unsuperseded_run(
                    session, restaurant_id=restaurant.id, period_start=period_start, period_end=period_end,
                )
                if run is not None:
                    review_rows = engine_svc.build_employee_review(session, run)

        return render_template(
            "calculate_tips.html", restaurant=restaurant, from_date=from_date, through_date=through_date,
            run=run, review_rows=review_rows, active_nav="calculate-tips",
        )


@app.route("/calculate-tips/run", methods=["POST"])
def calculate_tips_run():
    from_date = request.form.get("from_date") or ""
    through_date = request.form.get("through_date") or ""
    period = _calculation_period(from_date, through_date)
    if period is None:
        flash("Both From and Through dates are required.", "error")
        return redirect(url_for("calculate_tips_home"))
    period_start, period_end = period
    if period_end <= period_start:
        flash("Through date must not be before From date.", "error")
        return redirect(url_for("calculate_tips_home"))

    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet — nothing to calculate.", "error")
            return redirect(url_for("calculate_tips_home"))

        run, summary = engine_svc.run_tip_distribution_calculation(
            session, restaurant_id=restaurant.id, period_start=period_start, period_end=period_end,
        )
        session.commit()

        if run.status == engine_svc.STATUS_FAILED:
            flash(run.notes or "Calculation failed.", "error")
        else:
            flash(
                f"Calculated {summary.orders_considered} Order(s): {summary.allocations_produced} "
                f"allocation(s) across {summary.rules_applied} rule application(s).",
                "summary",
            )

    return redirect(url_for("calculate_tips_home", from_date=from_date, through_date=through_date))


@app.route("/calculate-tips/order/<int:order_id>")
def calculate_tips_order_drilldown(order_id: int):
    from_date = request.args.get("from_date") or ""
    through_date = request.args.get("through_date") or ""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        period = _calculation_period(from_date, through_date)
        run = None
        drilldown = None
        if restaurant is not None and period is not None:
            period_start, period_end = period
            run = engine_svc.get_latest_unsuperseded_run(
                session, restaurant_id=restaurant.id, period_start=period_start, period_end=period_end,
            )
            if run is not None:
                drilldown = engine_svc.get_order_drilldown(session, run, order_id)

        if run is None or drilldown is None:
            flash("No calculated Order found for that period — recalculate first.", "error")
            return redirect(url_for("calculate_tips_home", from_date=from_date, through_date=through_date))

        return render_template(
            "order_drilldown.html", restaurant=restaurant, from_date=from_date, through_date=through_date,
            drilldown=drilldown, active_nav="calculate-tips",
        )


@app.route("/calculate-tips/history")
def calculate_tips_history():
    """Read-only list of past Tip Distribution Calculation runs — no new
    calculation logic, just a listing over the existing
    `TipDistributionCalculationRun` rows so a period already calculated can
    be found and re-opened (via the existing Employee Review page) without
    guessing dates. Mirrors `home()`'s own "recent runs" query style."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        run_rows = []
        if restaurant is not None:
            runs = session.scalars(
                select(m.TipDistributionCalculationRun)
                .where(m.TipDistributionCalculationRun.restaurant_id == restaurant.id)
                .order_by(m.TipDistributionCalculationRun.started_at.desc())
                .limit(50)
            )
            for run in runs:
                # Inverse of `_calculation_period`'s "Through day's end is the
                # following day's midnight" convention, for display/re-open only.
                run_rows.append(
                    {
                        "id": run.id,
                        "status": run.status,
                        "from_date": run.period_start.strftime("%Y-%m-%d"),
                        "through_date": (run.period_end - timedelta(days=1)).strftime("%Y-%m-%d"),
                        "started_at": run.started_at,
                        "completed_at": run.completed_at,
                        "superseded": run.superseded_by_calculation_run_id is not None,
                    }
                )
        return render_template(
            "calculate_tips_history.html", restaurant=restaurant, run_rows=run_rows,
            active_nav="calculate-tips-history",
        )


# ---------------------------------------------------------------------------
# Tips Configuration (TASK_TIPS_COMPLETE_001 §3) — Calculation Schedule and
# Payment Schedule, Restaurant-scoped, deliberately independent of each
# other. "Run Calculation Now" (task §15) lives here too — the Clover-
# readiness-gated manual trigger, distinct from the existing "Calculate
# Tips" tab's own operator-chosen From/Through form (kept unchanged, for
# ad hoc/backfill periods).
# ---------------------------------------------------------------------------


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


@app.route("/tips-configuration")
def tips_configuration_home():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        calc_config = None
        payment_config = None
        readiness_state = None
        if restaurant is not None:
            calc_config = sched_svc.get_calculation_schedule_effective_at(session, restaurant_id=restaurant.id)
            payment_config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
            readiness_state = readiness_svc.describe_readiness(session, restaurant.id)
        return render_template(
            "tips_configuration.html", restaurant=restaurant, calc_config=calc_config,
            payment_config=payment_config, readiness_state=readiness_state,
            schedule_modes=m.TIPS_SCHEDULE_MODES, active_nav="tips-configuration",
        )


@app.route("/tips-configuration/calculation-schedule", methods=["POST"])
def tips_configuration_set_calculation_schedule():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("tips_configuration_home"))
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
    return redirect(url_for("tips_configuration_home"))


@app.route("/tips-configuration/payment-schedule", methods=["POST"])
def tips_configuration_set_payment_schedule():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("tips_configuration_home"))
        mode = request.form.get("mode") or ""
        interval_days = request.form.get("interval_days", type=int)
        execution_time = _parse_time(request.form.get("execution_time"))
        anchor_date_dt = _parse_date(request.form.get("anchor_date"))
        mercury_source_account_id = (request.form.get("mercury_source_account_id") or "").strip() or None
        auto_approval_mode = (request.form.get("auto_approval_mode") or "").strip() or None
        try:
            sched_svc.set_payment_schedule(
                session, restaurant_id=restaurant.id, mode=mode, interval_days=interval_days,
                execution_time=execution_time, anchor_date=anchor_date_dt.date() if anchor_date_dt else None,
                mercury_source_account_id=mercury_source_account_id, auto_approval_mode=auto_approval_mode,
                created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
            flash("Payment Schedule updated.", "summary")
        except sched_svc.ScheduleConfigError as exc:
            session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("tips_configuration_home"))


@app.route("/tips-configuration/run-calculation-now", methods=["POST"])
def tips_configuration_run_calculation_now():
    """Task §15 — "Run Calculation Now": always targets the latest
    Business Date via `readiness.describe_readiness`, gated by Clover
    readiness (task §5) exactly like the automatic scheduler would be —
    manual and automatic triggers share the exact same gated entry point,
    `payout_process.run_calculation_now`."""
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("tips_configuration_home"))
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
    return redirect(url_for("tips_configuration_home"))


# ---------------------------------------------------------------------------
# Tips Payment Control (TASK_TIPS_COMPLETE_001 §13/§14) — authorized visual
# control surface over the Payment Cycle: REVIEW (read-only) and
# APPROVE & PAY (gated by `authority_service.authorize()`, never `is_admin`).
# Not a workflow engine — every action here delegates entirely to
# `tips.payment_cycle_service`/`tips.payment_instruction`.
#
# SANDBOX ONLY: `MercuryClient()` defaults to the Mercury Sandbox base URL
# and reads `MERCURY_SANDBOX_API_TOKEN` from the environment. No production
# Mercury endpoint or token is referenced anywhere in this file.
# ---------------------------------------------------------------------------


# `_resolve_source_account_id` used to live here as a route-local helper;
# TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 (task §9, Channel
# Independence) moved it to `tips.payment_cycle_service.resolve_source_
# account_id` so the automatic scheduler's AUTO WITHOUT APPROVAL path can
# call the exact same resolution outside any Flask request — this module now
# just calls that shared function (`_resolve_source_account_id` kept as a
# thin local alias so every existing call site below reads unchanged).
_resolve_source_account_id = cycle_svc.resolve_source_account_id


@app.route("/payment-control")
def payment_control_home():
    return _render_payment_control(cycle_id=None)


@app.route("/payment-control/cycle/<int:cycle_id>")
def payment_control_cycle(cycle_id: int):
    """TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 §8 — Cognito deep-
    link target: a stable, resolvable URL for ONE specific Payment Cycle,
    independent of whichever Restaurant `_default_restaurant()` would
    otherwise pick. No Cognito capability is implemented by this route — it
    only makes a future one's "open Payment Control on the correct Payment
    Cycle" possible, by existing as a real, addressable route now. Works for
    a Cycle in ANY status (OPEN for action, APPROVED for after-the-fact
    review), not only an actionable one."""
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
        mercury_balance = None
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
            # TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 §6 — the SAME
            # payment_readiness.describe_payment_readiness gate approve_and_
            # pay_cycle itself enforces server-side; shown here for the
            # READY/NOT READY summary and to enable/disable Approve & Pay —
            # never a second, divergent readiness definition.
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
                # Task §7's per-payee Detail view: Business Dates included,
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
                client = MercuryClient()
                account_id = _resolve_source_account_id(session, restaurant.id, client)
                if account_id is not None:
                    accounts = {a.id: a for a in client.get_accounts()}
                    account = accounts.get(account_id)
                    # Never the full account object (task §13 "NON mostrare
                    # dati bancari completi") — only the one figure this
                    # control surface needs.
                    mercury_balance = account.available_balance if account is not None else None
            except MercuryConnectorError as exc:
                connector_error = str(exc)

        return render_template(
            "payment_control.html", restaurant=restaurant, calc_state=calc_state, cycle_readiness=cycle_readiness,
            payment_readiness=payment_readiness, open_cycle=open_cycle, instructions=instructions,
            employees_by_id=employees_by_id, references_by_employee=references_by_employee,
            attention_items_by_instruction=attention_items_by_instruction,
            entitlements_by_instruction=entitlements_by_instruction,
            mercury_balance=mercury_balance, connector_error=connector_error, identities=identities,
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
            client = MercuryClient()
            source_account_id = _resolve_source_account_id(session, restaurant.id, client)
            if source_account_id is None:
                flash("No Mercury sandbox source account configured or available.", "error")
                return redirect(url_for("payment_control_home"))
            result = cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle, acting_identity=acting_identity, client=client,
                source_account_id=source_account_id,
            )
            session.commit()
        except cycle_svc.PaymentNotReadyError as exc:
            # Task §3/§11 — NOT READY is a normal, expected wait, never a
            # financial error: a calm "info" message, not the red "error"
            # styling below (still no Mercury call, still no state change).
            session.rollback()
            flash(str(exc), "info")
            return redirect(url_for("payment_control_home"))
        except cycle_svc.ApproveAndPayError as exc:
            session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("payment_control_home"))
        except MercuryConnectorError as exc:
            session.rollback()
            flash(f"Mercury sandbox connector error: {exc}", "error")
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
            client = MercuryClient()
            source_account_id = instruction.provider_account_id or (
                _resolve_source_account_id(session, cycle.restaurant_id, client) if cycle is not None else None
            )
            if source_account_id is None:
                flash("No Mercury sandbox source account available for retry.", "error")
                return redirect(url_for("payment_control_home"))
            cycle_svc.retry_instruction(session, instruction, client, source_account_id=source_account_id)
            session.commit()
        except MercuryConnectorError as exc:
            session.rollback()
            flash(f"Mercury sandbox connector error: {exc}", "error")
            return redirect(url_for("payment_control_home"))
        flash(f"Payment Instruction {instruction.id} retried — status is now {instruction.status}.", "summary")
    return redirect(url_for("payment_control_home"))


@app.route("/payment-control/employee/<int:employee_id>/link-recipient", methods=["POST"])
def payment_control_link_recipient(employee_id: int):
    """Links an Employee to an EXISTING Mercury sandbox recipient by exact
    name (task §7/§11: never creates one). Deactivates any prior active
    reference for this Employee rather than deleting it (Historical
    Integrity)."""
    recipient_name = (request.form.get("recipient_name") or "").strip()
    if not recipient_name:
        flash("Recipient name is required.", "error")
        return redirect(url_for("payment_control_home"))
    with SessionFactory() as session:
        employee = session.get(m.Employee, employee_id)
        if employee is None:
            flash("Employee not found.", "error")
            return redirect(url_for("payment_control_home"))
        try:
            client = MercuryClient()
            recipient = client.find_recipient_by_name(recipient_name)
        except MercuryConnectorError as exc:
            flash(f"Mercury sandbox connector error: {exc}", "error")
            return redirect(url_for("payment_control_home"))
        if recipient is None:
            flash(f"No Mercury sandbox recipient named {recipient_name!r} was found.", "error")
            return redirect(url_for("payment_control_home"))

        existing = session.scalars(
            select(m.EmployeeExternalPaymentAccount).where(
                m.EmployeeExternalPaymentAccount.employee_id == employee_id,
                m.EmployeeExternalPaymentAccount.provider == "MERCURY",
                m.EmployeeExternalPaymentAccount.is_active.is_(True),
            )
        ).all()
        for row in existing:
            row.is_active = False
        session.add(
            m.EmployeeExternalPaymentAccount(
                employee_id=employee_id, provider="MERCURY", provider_recipient_id=recipient.id, is_active=True,
            )
        )
        session.commit()
        flash(f"Employee {employee_id} linked to Mercury sandbox recipient {recipient.name!r}.", "summary")
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


@app.route("/distribution-rules")
def distribution_rules_home():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
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
                        "source_role_name": current.source_role.name if current else "-",
                        "recipient_role_name": current.recipient_role.name if current else "-",
                    }
                )
        return render_template(
            "distribution_rules_home.html", restaurant=restaurant, rules_rows=rules_rows, roles=roles,
            calculation_bases=m.TIP_DISTRIBUTION_CALCULATION_BASES, active_nav="distribution-rules",
        )


@app.route("/distribution-rules/new", methods=["POST"])
def distribution_rule_create():
    with SessionFactory() as session:
        restaurant = _default_restaurant(session)
        if restaurant is None:
            flash("No Restaurant exists in this database yet.", "error")
            return redirect(url_for("distribution_rules_home"))

        source_role_id = request.form.get("source_role_id", type=int)
        recipient_role_id = request.form.get("recipient_role_id", type=int)
        calculation_base = request.form.get("calculation_base") or ""
        rate = _parse_rate(request.form.get("rate"))
        effective_from = _parse_date(request.form.get("effective_from"))
        created_by = (request.form.get("created_by") or "").strip() or None

        if not source_role_id or not recipient_role_id or rate is None or effective_from is None:
            flash("Source Role, Recipient Role, Rate, and Effective From are all required.", "error")
            return redirect(url_for("distribution_rules_home"))

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
        return redirect(url_for("distribution_rules_home"))


@app.route("/distribution-rules/<int:rule_id>")
def distribution_rule_detail(rule_id: int):
    with SessionFactory() as session:
        rule = rule_svc.get_rule(session, rule_id)
        if rule is None:
            return redirect(url_for("distribution_rules_home"))
        versions = rule_svc.list_versions(session, rule_id)
        roles = list(
            session.scalars(
                select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == rule.restaurant_id).order_by(m.RestaurantRole.name)
            )
        )
        return render_template(
            "distribution_rule_detail.html", rule=rule, versions=versions, roles=roles,
            calculation_bases=m.TIP_DISTRIBUTION_CALCULATION_BASES, active_nav="distribution-rules",
        )


@app.route("/distribution-rules/<int:rule_id>/versions", methods=["POST"])
def distribution_rule_new_version(rule_id: int):
    with SessionFactory() as session:
        rule = rule_svc.get_rule(session, rule_id)
        if rule is None:
            return redirect(url_for("distribution_rules_home"))

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
            rule_svc.create_new_version(
                session, rule_id, source_role_id=source_role_id, recipient_role_id=recipient_role_id,
                calculation_base=calculation_base, rate=rate, effective_from=effective_from, created_by=created_by,
            )
            session.commit()
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
        return redirect(request.form.get("next") or url_for("distribution_rules_home"))


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
            "restaurant_roles_home.html", restaurant=restaurant, roles=roles, active_nav="distribution-rules",
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
