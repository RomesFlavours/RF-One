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
from sqlalchemy import select  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.database import (  # noqa: E402
    create_configured_engine, create_session_factory, get_database_url, run_migrations_to_head,
)
from rfone_data_store.technical.connectors.clover.acquisition import (  # noqa: E402
    ImportAlreadyRunningError, MODE_BACKFILL, get_order_settlement_time, import_clover_period,
)
from rfone_data_store.tips import distribution_engine as engine_svc  # noqa: E402
from rfone_data_store.tips import distribution_rule_service as rule_svc  # noqa: E402

UTC = timezone.utc

_DB_URL = get_database_url()
run_migrations_to_head(_DB_URL)
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
        from_date = request.args.get("from_date") or ""
        through_date = request.args.get("through_date") or ""

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


if __name__ == "__main__":
    app.run(debug=True, port=5057)
