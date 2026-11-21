"""RF-One Web — Tips period validation (TIPS_AWS_FINALIZATION_WORKFLOW_001).

WHY THIS LIVES IN RF-ONE WEB

TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §15 requires the person who
validates a Tips period to be identified by the ONE existing RF-One login.
That login is RF-One Web's own signed-cookie session, and a browser only
sends a cookie back to the host that set it. On AWS the Tips app runs as a
separate App Runner service on a different hostname, so the session never
reaches it: every Tips validation there is (correctly) refused as
unidentified, and CALCULATED periods cannot become FINAL.

This module is the smallest correction that keeps the approved control
model intact: the human validation step is offered HERE, on the host where
the person actually signed in, behind the same three server-side gates
every RF-One Web destination already uses —

  * `require_domain_access("TIPS")` — an ACTIVE account holding an enabled
    TIPS access row (BANK or any other Domain grants nothing here);
  * `require_csrf()` on the one state-changing POST;
  * the validator is the signed-in account, never a typed name.

No new login, no token in a URL, no cross-host cookie, no change to what
validation means. Every figure and every decision comes from
`rfone_data_store.tips.calculation_run_service` — its `validate_run` is the
one finalization rule; the Tips app has no validation route of its own and
links here instead — so this page cannot validate anything the service
would refuse (unbalanced control, already FINAL, overlapping FINAL
period), and it never recalculates: the report is read back from the saved
run exactly as the Tips app reads it.

The rest of Tips (calculation, rules, configuration, payment control) stays
in the Tips app, unchanged. Registered from `app.py` via
`register_tips_validation_routes(app, ...)`, following
`compensation_routes.py`'s "pass in collaborators explicitly" convention.
"""

from __future__ import annotations

import os

from flask import abort, flash, redirect, render_template, request, url_for
from flask import session as flask_session
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store import site_selection
from rfone_data_store.tips import calculation_run_service as run_svc
from rfone_data_store.tips import validation_mode_service as validation_mode_svc

TIPS_DOMAIN_CODE = "TIPS"
SITE_SESSION_KEY = "tips_validation_restaurant_id"


def register_tips_validation_routes(
    app, *, require_domain_access, SessionFactory, load_current_account, require_csrf,
) -> None:

    def _account_sites(db, account):
        """CLOVER_MULTISITE_001 — the restaurants this account may see and validate (central rule)."""
        return site_selection.sites_for_account(db, account, TIPS_DOMAIN_CODE)

    def _require_site_access(db, account, restaurant_id):
        if restaurant_id not in {site.restaurant_id for site in _account_sites(db, account)}:
            abort(403, description="This RF-One account may not use Tips for this restaurant.")

    @app.route("/tips/runs")
    @require_domain_access(TIPS_DOMAIN_CODE)
    def tips_validation_runs():
        """The saved Calculation Runs of the SELECTED restaurant (CLOVER_MULTISITE_001), newest
        first, final and non-final alike, as in the Tips app's own history."""
        with SessionFactory() as db:
            account = load_current_account(db)
            sites = _account_sites(db, account)
            site = site_selection.resolve_site(db, request.args.get("restaurant_id", type=int),
                                               flask_session.get(SITE_SESSION_KEY), sites=sites)
            sections = []
            if site is not None:
                flask_session[SITE_SESSION_KEY] = site.restaurant_id
                restaurant = db.get(m.Restaurant, site.restaurant_id)
                sections = [{
                    "restaurant": restaurant,
                    "runs": run_svc.list_runs(db, restaurant_id=restaurant.id),
                    "validation_mode": validation_mode_svc.get_validation_mode(db, restaurant_id=restaurant.id),
                }]
            return render_template("tips_validation_runs.html", sections=sections, sites=sites, site=site,
                                   ui_it=os.environ.get("RFONE_UI_LANGUAGE") == "it")

    @app.route("/tips/runs/<int:run_id>")
    @require_domain_access(TIPS_DOMAIN_CODE)
    def tips_validation_run(run_id: int):
        """The saved Calculation Run Report, read back — never recalculated."""
        with SessionFactory() as db:
            report = run_svc.get_run_report(db, run_id)
            if report is None:
                flash(f"No Calculation Run with id {run_id}.", "error")
                return redirect(url_for("tips_validation_runs"))
            account = load_current_account(db)
            run = report["run"]
            _require_site_access(db, account, run.restaurant_id)
            flask_session[SITE_SESSION_KEY] = run.restaurant_id  # the list reopens on this run's restaurant
            return render_template(
                "tips_validation_run.html", report=report, run=run,
                restaurant=db.get(m.Restaurant, run.restaurant_id),
                validation_mode=validation_mode_svc.get_validation_mode(
                    db, restaurant_id=run.restaurant_id,
                ),
                identified_as=shared_session.account_display_name(account),
                finalization_blockers=run_svc.finalization_blockers(db, run),
                site_active=site_selection.restaurant_is_operational(db, run.restaurant_id),
            )

    @app.route("/tips/runs/<int:run_id>/validate", methods=["POST"])
    @require_domain_access(TIPS_DOMAIN_CODE)
    def tips_validation_validate(run_id: int):
        """§14/§15 — the signed-in person validates the period, which makes
        it FINAL. `require_domain_access` has already established an ACTIVE
        account with TIPS access; the service re-checks every finalization
        rule and refuses rather than guessing."""
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            target = db.get(m.TipDistributionCalculationRun, run_id)
            if target is not None:
                # Server-side, whatever the page showed: the account must be allowed this
                # restaurant, and an inactive restaurant is never finalized.
                _require_site_access(db, account, target.restaurant_id)
                if not site_selection.restaurant_is_operational(db, target.restaurant_id):
                    flash("This restaurant is not active yet: its Tips periods cannot be validated.", "error")
                    return redirect(url_for("tips_validation_run", run_id=run_id))
            run, reason = run_svc.validate_run(
                db, run_id=run_id, account_id=account.id if account is not None else None,
            )
            if run is None:
                db.rollback()
                flash(reason, "error")
                return redirect(url_for("tips_validation_run", run_id=run_id))
            db.commit()
            flash(
                f"Calculation Run {run_id} validated by "
                f"{shared_session.account_display_name(account)} and is now FINAL. "
                "It can no longer be modified, and it is the Tips figure Payroll may use for "
                "this period.",
                "info",
            )
        return redirect(url_for("tips_validation_run", run_id=run_id))
