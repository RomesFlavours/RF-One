"""RF-One Web — Bank Reconciliation: the module's pages and their routes.

The Bank tabs, in the Product Owner's order:

  Import and Review    `/bank`: upload staged and reviewed before anything is
                       imported (Confirm / Cancel), Check Sources (source
                       completeness for the month), Automatic WHO, Review
                       Missing (BANK_SOURCE_AND_IMPORT_REVIEW_001);
  Review Transactions  `/bank/review`: To Reconcile / Reconciled
                       (BANK_TWO_STAGE_REVIEW_001); WHO + WHY decided by a
                       person (`bank_manual_reconciliation_routes`), the WHO
                       Rule (`bank_who_rule_routes`);
  Monthly Export       `/bank/export`;
  Source               `/bank/sources`: the expected financial sources —
                       accounts, cards, PayPal — create / edit / active
                       (canonical `PaymentInstrument`); card settings;
  Classification       `/bank/classification`: Classification Learning
                       (`bank_learning_routes`), General Rules
                       (`bank_general_rule_routes`), WHO Classification;
  Instructions         `/bank/instructions`.

`/bank/instruments` and `/bank/monthly` are retired pages kept only as
redirects for bookmarks. WHAT / WHY / WHO vocabulary is maintained on
Bank Configuration (`bank_configuration_routes`).

Every mutating route is behind `require_domain_access("BANK")` and
`require_csrf()`, and calls straight into `rfone_data_store.bank_reconciliation`
— no business logic lives here. Registered from `app.py` via
`register_bank_routes(app, ...)`; this module never imports `app.py`."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from flask import Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from rfone_data_store import display_format
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import card_configuration
from rfone_data_store.bank_reconciliation import configuration as configuration_service
from rfone_data_store.bank_reconciliation import export as export_service
from rfone_data_store.bank_reconciliation import import_preview
from rfone_data_store.bank_reconciliation import matching as matching_service
from rfone_data_store.bank_reconciliation import monthly_source
from rfone_data_store.bank_reconciliation import parsers
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import service as bank_service
from rfone_data_store.bank_reconciliation import review_queues
from rfone_data_store.bank_reconciliation import row_reconciliation as reconciliation_rows
from rfone_data_store.bank_reconciliation import who_rules

import bank_import_staging
from bank_who_rule_routes import pop_manual_only_result, pop_rule_result, register_bank_who_rule_routes


def _parse_optional_date(value: str | None) -> date | None:
    """An empty or unparseable date stays UNKNOWN (None).

    BANK_MONTHLY_SOURCE_COMPLETENESS_001 §13B — an operator who does not
    know a date must be able to say so, and RF-One must keep that as
    UNKNOWN rather than substituting today or the period end.

    Used only by the resolutions that end no life. A lifecycle-ending
    resolution is dated from the instrument's own transactions and never
    from this field.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _months_spanned(batch) -> set[tuple[int, int]]:
    """The calendar months a source file's own covered range touches.

    Uses the range the parser already recorded on the batch — the same
    fact `monthly_source.batches_covering` matches a month against — so a
    file is never attributed to a month by its name or upload date. A
    batch RF-One could not date covers nothing: an unreadable file is not
    evidence about any month.
    """
    return monthly_source.months_spanned(batch.date_range_start, batch.date_range_end)


def _flash_control_outcome(outcome) -> None:
    """Say what bringing months under control found, in the operator's words.

    Missing accounts become visible and have to be explained in Check
    Sources on Import and Review; nothing is closed, deactivated or resolved
    here."""
    for control in outcome.blocked:
        report = control.report
        flash(
            f"MISSING ACCOUNTS — {control.period.period_month}: "
            f"{len(report.blockers)} expected account(s) not represented by the data "
            "received. Each needs a decision: the file/data is still missing, or the "
            "account is closed. " + " ".join(report.blockers),
            "error",
        )
    historical = outcome.historical_months
    if historical:
        flash(
            f"HISTORICAL DATA — {len(historical)} month(s) before the control start "
            f"{outcome.control_start_month} ({historical[0]} to {historical[-1]}): the "
            "transactions were imported and kept, but these months are not placed under "
            "completeness control and are not certified complete. Nothing existing was changed.",
            "info",
        )
    if outcome.blocked:
        flash(
            "Resolve them in Check Sources on Import and Review — nothing was closed or "
            "deactivated by this import.",
            "info",
        )


def _report_missing_accounts(db, covered_months: set[tuple[int, int]]) -> None:
    """Put the CONTROLLED months this import touched under completeness
    control, and leave the historical ones alone.

    The Reconciliation Control Start divides the two. A month on or after
    it is opened if it does not exist, reused if it does, refreshed and
    evaluated — so an expected account no file represented becomes visible
    and has to be explained. A month BEFORE it is skipped entirely: its
    data is imported and kept, but data being available is not the same
    claim as a period being proven complete, and importing a file is not a
    reason to start demanding history nobody promised.

    Skipped means untouched. A pre-threshold period an operator created on
    purpose keeps its coverage, its resolutions and its status exactly as
    they are. The division and the per-month work are
    `monthly_source.bring_months_under_control` — the same
    `get_or_create_period`, `refresh_coverage`, `evaluate` the monthly
    screen runs, shared with the activation of the control start over
    already-imported batches. No second completeness system.
    """
    if monthly_source.get_control_start_month(db) is None:
        if covered_months:
            flash(
                "NO RECONCILIATION CONTROL START is configured, so no month was placed under "
                "completeness control. The transactions were imported and kept; RF-One simply "
                "has not been told from which month it is responsible for proving a month "
                "complete. Set it in Check Sources on Import and Review.",
                "error",
            )
        return
    outcome = monthly_source.bring_months_under_control(db, covered_months)
    db.commit()
    _flash_control_outcome(outcome)


# ---------------------------------------------------------------------------
# Import and Review (BANK_IMPORT_AND_REVIEW_001) — presentation helpers.
#
# `/bank` is the monthly operational page: Import, Check Sources, Automatic
# WHO, Review Missing, for ONE selected month. Nothing here is a process
# state: every figure is read from the facts the specialist pages already
# use, through the same functions.
# ---------------------------------------------------------------------------

# The only values a POST may carry in `return_to`. Anything else is ignored
# and the route redirects exactly as it did before, so no caller can turn a
# Bank form into a redirect to an address of its choosing.
RETURN_IMPORT_REVIEW = "import_review"
# "instruments" is the value forms sent before the Source page replaced
# Instruments; both lead to Source.
RETURN_INSTRUMENTS = "instruments"
RETURN_SOURCES = "sources"

_MIN_YEAR, _MAX_YEAR = 2000, 2100


def _valid_month(year: int | None, month: int | None) -> tuple[int, int] | None:
    if year is None or month is None:
        return None
    if not (_MIN_YEAR <= year <= _MAX_YEAR and 1 <= month <= 12):
        return None
    return year, month


def _previous_local_month(tz_name: str | None) -> tuple[int, int]:
    """The calendar month before today, today being the Location's local
    date (RF-One UI Rules §1). With no usable zone the UTC date is used, as
    `display_format` does everywhere: a zone is never guessed."""
    today = display_format.to_local(datetime.now(timezone.utc), tz_name).date()
    last_of_previous = today.replace(day=1) - timedelta(days=1)
    return last_of_previous.year, last_of_previous.month


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _monthly_sources_view(db, period) -> dict:
    """The selected-month source-completeness facts shown by Check Sources
    on `/bank` (BANK_SOURCE_AND_IMPORT_REVIEW_001 retired the separate
    Monthly Sources page; its logic lives here, unchanged).

    An OPEN month re-evaluates on every view, so the screen is never stale;
    a COMPLETE one is history and is read as-is (`refresh_coverage` leaves
    it untouched). Commits the refreshed coverage, exactly as the Monthly
    Sources page always has."""
    rows, report, extra_batches, still_active_ids = [], None, {}, set()
    if period is not None:
        monthly_source.refresh_coverage(db, period)
        db.commit()
        rows = monthly_source.coverages(db, period)
        report = monthly_source.evaluate(db, period)
        for coverage in rows:
            covering = monthly_source.batches_covering(
                db, period=period, instrument_id=coverage.payment_instrument_id,
            )
            if len(covering) > 1:
                extra_batches[coverage.id] = covering[1:]
        # STILL ACTIVE is offered only where the service would accept it;
        # the service re-checks on submit either way.
        still_active_ids = {
            c.payment_instrument_id for c in rows
            if monthly_source.still_active_refusal(db, c.payment_instrument) is None
        }
    control_config = monthly_source.get_control_config(db)
    return {
        "control_config": control_config,
        "period_is_controlled": (
            period is not None and control_config is not None
            and period.period_month >= control_config.control_start_month
        ),
        "period": period,
        "coverages": rows,
        "report": report,
        "extra_batches": extra_batches,
        "still_active_ids": still_active_ids,
        "EXPECTED": m.COVERAGE_EXPECTED,
        "NOT_EXPECTED": m.COVERAGE_NOT_EXPECTED,
        "NEEDS_CONFIRMATION": m.COVERAGE_NEEDS_CONFIRMATION,
        "RESOLUTIONS": m.COVERAGE_RESOLUTIONS,
    }


def _source_attention(coverages) -> list[dict]:
    """The month's accounts/cards that still need a person, in a few words.

    Exactly the rows `monthly_source.evaluate` turns into blockers: no
    source file received and no human resolution. Accounts and cards that
    are already covered or resolved are not listed — the full table is the
    Check Sources detail on the same page."""
    items = []
    for coverage in coverages:
        if coverage.source_received or coverage.is_resolved:
            continue
        instrument = coverage.payment_instrument
        last_four = instrument.last_four or (
            instrument.external_account_identifier[-4:]
            if instrument.external_account_identifier else None
        )
        if coverage.resolution == m.RESOLUTION_SOURCE_FILE_MISSING:
            issue = "source file still owed"
        elif coverage.expectation == m.COVERAGE_NEEDS_CONFIRMATION:
            issue = "needs confirmation"
        else:
            issue = "source missing"
        items.append({
            "label": instrument.display_name + (f" ··{last_four}" if last_four else ""),
            "institution": coverage.institution_snapshot or instrument.institution,
            "issue": issue,
        })
    return items


# The WHO status of a month's transactions, read from their CURRENT
# decision and nothing else. Only the WHO is looked at: never the Why, the
# What or the decision status, which also speaks about purpose.
WHO_FROM_LEARNED_RULE = "learned_rule"
WHO_FROM_HUMAN = "human"
WHO_FROM_OTHER_AUTOMATIC = "other_automatic"
WHO_MISSING = "missing"


def _who_source(explanation) -> str:
    if explanation is None or explanation.occurrence_id is None:
        return WHO_MISSING
    if explanation.decision_source == "HUMAN":
        return WHO_FROM_HUMAN
    if explanation.decision_source == "RULE" and explanation.recognition_rule_id is not None:
        return WHO_FROM_LEARNED_RULE
    return WHO_FROM_OTHER_AUTOMATIC


def _who_status_counts(db, transactions) -> dict[str, int]:
    """How many of `transactions` have a WHO, and where it came from."""
    counts = dict.fromkeys(
        (WHO_FROM_LEARNED_RULE, WHO_FROM_HUMAN, WHO_FROM_OTHER_AUTOMATIC, WHO_MISSING), 0,
    )
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    explanations = {
        e.id: e for e in db.scalars(
            select(m.BankTransactionExplanation)
            .where(m.BankTransactionExplanation.id.in_(explanation_ids))
        ).all()
    } if explanation_ids else {}
    for txn in transactions:
        counts[_who_source(explanations.get(txn.explanation_id))] += 1
    return counts


def register_bank_routes(
    app, *, require_domain_access, SessionFactory, load_current_account, require_csrf,
):
    gate = require_domain_access("BANK")

    def _current_account(db):
        account = load_current_account(db)
        if account is None:
            abort(403)
        return account

    # -----------------------------------------------------------------
    # Home — upload, batch list/status, PaymentInstrument configuration.
    # -----------------------------------------------------------------

    def _instruments(db):
        return db.scalars(
            select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)
        ).all()

    def _active_legal_entities(db):
        return db.scalars(
            select(m.LegalEntity).where(m.LegalEntity.status == "ACTIVE")
            .order_by(m.LegalEntity.legal_name)
        ).all()

    def _return_redirect(default, *, year: int | None = None, month: int | None = None):
        """Where a Bank POST goes when it is done.

        `return_to` may name one of two Bank pages and nothing else: Import
        and Review (for the month given, when it is a real month) or
        Source. Without it — or with any other value — the route's own
        `default` redirect is returned unchanged."""
        target = request.form.get("return_to")
        if target == RETURN_IMPORT_REVIEW:
            selected = _valid_month(year, month)
            if selected is None:
                return redirect(url_for("bank_home"))
            return redirect(url_for("bank_home", year=selected[0], month=selected[1]))
        if target in (RETURN_INSTRUMENTS, RETURN_SOURCES):
            return redirect(url_for("bank_sources"))
        return default

    def _form_month() -> dict:
        """The month an Import and Review form was rendered for, as sent back
        with the form — used only to choose which month to return to."""
        return {"year": request.form.get("year", type=int),
                "month": request.form.get("month", type=int)}

    def _site_timezone() -> str | None:
        """The zone RF-One Web shows every time in — the `tz` its context
        processor already provides to templates, read here rather than
        looked up a second way."""
        context: dict = {}
        current_app.update_template_context(context)
        return context.get("tz")

    @app.route("/bank")
    @gate
    def bank_home():
        """Import and Review — the monthly Bank work for one month."""
        selected = _valid_month(
            request.args.get("year", type=int), request.args.get("month", type=int),
        )
        year, month = selected or _previous_local_month(_site_timezone())
        month_start, month_end = monthly_source.period_bounds(year, month)
        show_all_batches = request.args.get("batches") == "all"

        with SessionFactory() as db:
            # The Import Set Review of a file set waiting for Confirm or
            # Cancel — only the uploader's own, and only while undecided.
            staged = bank_import_staging.load(
                _staging_root(), request.args.get("staged"), account_id=_current_account(db).id,
            )
            instruments = _instruments(db)
            instruments_by_id = {i.id: i for i in instruments}

            # --- 1 Import: this month's source files, plus any file of any
            # month that still waits for an action — pending work is never
            # hidden by the month selector.
            batches = db.scalars(
                select(m.BankImportBatch).order_by(m.BankImportBatch.uploaded_at.desc())
            ).all()
            batch_states = {
                batch.id: bank_service.compute_batch_review_state(db, batch) for batch in batches
            }
            month_key = (year, month)
            month_batches, pending_batches, undated_count = [], [], 0
            for batch in batches:
                spanned = _months_spanned(batch)
                if not spanned:
                    undated_count += 1
                state = batch_states.get(batch.id)
                if show_all_batches or month_key in spanned:
                    month_batches.append(batch)
                elif state is not None and state.action is not None:
                    pending_batches.append(batch)

            # --- 2 Check Sources: the month's source completeness (the
            # former Monthly Sources page, now only here).
            period = monthly_source.get_period(db, year, month)
            monthly = _monthly_sources_view(db, period)
            source_attention = _source_attention(monthly["coverages"])

            # --- 3 Automatic WHO and 4 Review Missing: the month's
            # transactions as the monthly export sees them.
            transactions = export_service.in_scope_transactions(db, year, month)
            who_counts = _who_status_counts(db, transactions)
            unresolved_count = len(
                export_service.unresolved_transactions(db, year=year, month=month)
            )

            previous_year, previous_month = _shift_month(year, month, -1)
            next_year, next_month = _shift_month(year, month, 1)
            return render_template(
                "bank_home.html",
                year=year, month=month,
                month_label=date(year, month, 1).strftime("%B %Y"),
                month_start=month_start, month_end=month_end,
                previous_year=previous_year, previous_month=previous_month,
                next_year=next_year, next_month=next_month,
                is_controlled=monthly_source.is_controlled_month(db, year, month),
                is_provisional=monthly_source.is_provisional_month(db, year, month),
                instruments=instruments, instruments_by_id=instruments_by_id,
                batches=month_batches, pending_batches=pending_batches,
                month_action_count=sum(
                    1 for b in month_batches
                    if batch_states.get(b.id) is not None and batch_states[b.id].action is not None
                ),
                batch_states=batch_states, undated_batch_count=undated_count,
                show_all_batches=show_all_batches, total_batch_count=len(batches),
                transaction_count=len(transactions), who_counts=who_counts,
                unresolved_count=unresolved_count,
                source_attention=source_attention,
                RETURN_IMPORT_REVIEW=RETURN_IMPORT_REVIEW,
                monthly_return_to=RETURN_IMPORT_REVIEW,
                staged_token=staged.token if staged else None,
                import_review=staged.manifest.get("review") if staged else None,
                **monthly,
            )

    @app.route("/bank/instructions")
    @gate
    def bank_instructions():
        """How the monthly Bank work is done — explanation only, no data."""
        return render_template("bank_instructions.html")

    @app.route("/bank/instruments")
    @gate
    def bank_instruments():
        """Retired page (BANK_SOURCE_AND_IMPORT_REVIEW_001): Instruments is
        now Source. Kept so bookmarks and old links land on Source."""
        return redirect(url_for("bank_sources"))

    @app.route("/bank/sources")
    @gate
    def bank_sources():
        """Source — the stable setup list of every source RF-One expects
        financial data from (bank accounts, cards, PayPal, ...). One row per
        canonical `PaymentInstrument`; the page says Source, the model keeps
        its name. Create and edit happen in one modal on this page; the
        file-recognition rules, the assignment history and the accounting
        deduplication summary stay available, collapsed, below the list."""
        with SessionFactory() as db:
            instruments = _instruments(db)
            legal_entities = _active_legal_entities(db)
            instrument_warnings = {
                i.id: bank_service.instrument_export_warning(i) for i in instruments
            }

            # BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001. Resolved
            # server-side so the template states facts instead of deriving
            # them: for a card, the Company comes through its settlement
            # account, never from the card's own value and never from its
            # holder.
            settlement_accounts = {}
            cardholders = {}
            derived_companies = {}
            card_warnings = {}
            for instrument in instruments:
                derived_companies[instrument.id] = card_configuration.legal_entity_for(
                    db, instrument=instrument, on_date=date.today(),
                )
                if instrument.instrument_type == "CREDIT_CARD":
                    settlement_accounts[instrument.id] = (
                        card_configuration.current_settlement_account(db, instrument.id)
                    )
                    cardholders[instrument.id] = card_configuration.current_cardholder(
                        db, instrument.id,
                    )
                    card_warnings[instrument.id] = card_configuration.configuration_warning(
                        db, instrument,
                    )
            dedup = accounting_dedup.summarize(db)

            source_profiles = db.scalars(
                select(m.BankSourceInstrumentProfile)
                .order_by(m.BankSourceInstrumentProfile.detected_format,
                          m.BankSourceInstrumentProfile.id)
            ).all()
            assignment_audits = db.scalars(
                select(m.BankInstrumentAssignmentAudit)
                .order_by(m.BankInstrumentAssignmentAudit.id.desc())
                .limit(25)
            ).all()

            return render_template(
                "bank_sources.html", instruments=instruments,
                instruments_by_id={i.id: i for i in instruments},
                legal_entities=legal_entities, instrument_warnings=instrument_warnings,
                source_profiles=source_profiles, assignment_audits=assignment_audits,
                settlement_accounts=settlement_accounts, cardholders=cardholders,
                derived_companies=derived_companies, card_warnings=card_warnings,
                dedup=dedup,
            )

    # -----------------------------------------------------------------
    # Payment Instrument configuration — create and edit.
    # -----------------------------------------------------------------

    def _cardholder_candidates(db):
        """Real people this database can link a cardholder to — HUMAN_USER
        identities and employees, each person once. The one implementation
        lives in the Bank configuration service, shared with the Bank
        Configuration page."""
        return configuration_service.cardholder_candidates(db)

    def _instrument_form_values(form):
        """The one place the instrument form's fields are read, so the
        create and edit paths can never diverge on what a field means."""
        return {
            "institution": (form.get("institution") or "").strip() or None,
            "display_name": (form.get("display_name") or "").strip(),
            "instrument_type": form.get("instrument_type"),
            "last_four": (form.get("last_four") or "").strip() or None,
            "external_account_identifier": (form.get("external_account_identifier") or "").strip() or None,
            "legal_entity_id": form.get("legal_entity_id", type=int) or None,
            "currency": (form.get("currency") or "").strip() or None,
            "linked_instrument_id": form.get("linked_instrument_id", type=int) or None,
            "status": form.get("status") or "ACTIVE",
        }

    def _wants_json() -> bool:
        """The Source modal saves with fetch and stays open on an error;
        a plain form post keeps the redirect behaviour it always had."""
        return request.headers.get("X-Requested-With") == "fetch"

    @app.route("/bank/instruments/new", methods=["POST"])
    @gate
    def bank_instrument_new():
        """Create a Source — the one creation path, used by the New Source
        modal. A card's settlement account is NOT taken here: it is a
        historized fact with an effective date, recorded from the card's
        settings once the card exists."""
        require_csrf()
        values = _instrument_form_values(request.form)
        if values["instrument_type"] == "CREDIT_CARD":
            values["linked_instrument_id"] = None
        with SessionFactory() as db:
            try:
                instrument = bank_service.create_payment_instrument(db, **values)
                warning = bank_service.instrument_export_warning(instrument)
                display_name = instrument.display_name
                db.commit()
                instrument_id = instrument.id
            except ValueError as exc:
                db.rollback()
                if _wants_json():
                    return jsonify({"ok": False, "error": str(exc)}), 400
                flash(str(exc), "error")
                return _return_redirect(redirect(url_for("bank_home")))
        flash(f"Source {display_name!r} created.", "info")
        if warning:
            flash(f"{display_name}: {warning}", "error")
        if _wants_json():
            return jsonify({"ok": True, "id": instrument_id})
        return _return_redirect(redirect(url_for("bank_home")))

    @app.route("/bank/instruments/<int:instrument_id>/edit", methods=["GET", "POST"])
    @gate
    def bank_instrument_edit(instrument_id: int):
        with SessionFactory() as db:
            instrument = db.get(m.PaymentInstrument, instrument_id)
            if instrument is None:
                abort(404)

            if request.method == "POST":
                require_csrf()
                values = _instrument_form_values(request.form)

                # BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001: for a CREDIT_CARD,
                # `linked_instrument_id` is a PROJECTION of the historized
                # settlement assignment, never an independent input. The page
                # no longer offers the legacy control for a card, but a stale
                # tab or a scripted post still can — so any value arriving
                # here is routed through the canonical service, which writes
                # the historized row, closes the previous period and keeps
                # the projection in step. Writing the column directly is what
                # produced the split configuration this task repairs.
                legacy_link = values.pop("linked_instrument_id", None)
                if instrument.instrument_type == "CREDIT_CARD":
                    current = card_configuration.current_settlement_account(db, instrument_id)
                    if legacy_link is not None and (current is None or current.id != legacy_link):
                        try:
                            card_configuration.assign_settlement_account(
                                db, credit_card_payment_instrument_id=instrument_id,
                                settlement_bank_account_id=legacy_link,
                                valid_from=date.today(),
                                notes="Set from the instrument form (routed through the canonical service).",
                                created_by_account_id=_current_account(db).id,
                            )
                            bank_service.recompute_accounting_deduplication(db)
                        except ValueError as exc:
                            db.rollback()
                            if _wants_json():
                                return jsonify({"ok": False, "error": str(exc)}), 400
                            flash(str(exc), "error")
                            return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))
                else:
                    values["linked_instrument_id"] = legacy_link

                # Active / Inactive (BANK_FINAL_RELEASE_BLOCKERS_002): only
                # when the form actually carries it — the Source modal does,
                # the Card settings form does not — and always through the
                # lifecycle service, never as a plain column edit.
                values.pop("status", None)
                requested_status = request.form.get("status") if "status" in request.form else None
                if requested_status not in (None, "ACTIVE", "INACTIVE"):
                    requested_status = None
                if requested_status is not None and requested_status != instrument.status:
                    monthly_source.set_source_active(
                        db, instrument=instrument, active=requested_status == "ACTIVE",
                    )
                # The Source modal never receives the stored identifier, so
                # an untouched field means "keep it", not "clear it".
                if request.form.get("keep_external_account_identifier"):
                    values.pop("external_account_identifier", None)
                try:
                    bank_service.update_payment_instrument(db, instrument_id=instrument_id, **values)
                    warning = bank_service.instrument_export_warning(instrument)
                    display_name = instrument.display_name
                    db.commit()
                except ValueError as exc:
                    db.rollback()
                    if _wants_json():
                        return jsonify({"ok": False, "error": str(exc)}), 400
                    flash(str(exc), "error")
                    return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))
                flash(f"Source {display_name!r} updated.", "info")
                if warning:
                    flash(f"{display_name}: {warning}", "error")
                if _wants_json():
                    return jsonify({"ok": True, "id": instrument_id})
                return _return_redirect(redirect(url_for("bank_home")))

            all_instruments = _instruments(db)
            return render_template(
                "bank_instrument_edit.html",
                instrument=instrument,
                legal_entities=_active_legal_entities(db),
                instruments=[i for i in all_instruments if i.id != instrument_id],
                instruments_by_id={i.id: i for i in all_instruments},
                # A card settles to a BANK_ACCOUNT and never to another card,
                # so only bank accounts are offered — the UI never proposes a
                # choice the service layer would then refuse.
                bank_accounts=[
                    i for i in all_instruments
                    if i.instrument_type == "BANK_ACCOUNT" and i.id != instrument_id
                ],
                current_settlement=card_configuration.current_settlement_account(db, instrument_id),
                settlement_history=card_configuration.settlement_history(db, instrument_id),
                settlement_warning=card_configuration.configuration_warning(db, instrument),
                current_cardholder=card_configuration.current_cardholder(db, instrument_id),
                cardholder_history=card_configuration.cardholder_history(db, instrument_id),
                # BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001: only HUMAN_USER
                # identities are offered. A card is held by a person, and
                # listing SYSTEM / AI_AGENT / EXTERNAL_SERVICE identities —
                # which is what an unfiltered list showed in QA, where the
                # only identity is "RF-One System" — offers a choice that is
                # never correct.
                cardholder_candidates=_cardholder_candidates(db),
                today=date.today().isoformat(),
                export_warning=bank_service.instrument_export_warning(instrument),
                transaction_count=db.scalar(
                    select(func.count(m.FinancialTransaction.id))
                    .where(m.FinancialTransaction.payment_instrument_id == instrument_id)
                ) or 0,
            )

    # -----------------------------------------------------------------
    # Card configuration — settlement account and cardholder
    # (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).
    #
    # Two separate sets of routes because the two facts have entirely
    # different consequences: changing the settlement account changes the
    # Company and the accounting identity of the card's transactions, so it
    # triggers a deduplication recompute; changing the cardholder changes
    # nothing but who is accountable, so it triggers nothing.
    # -----------------------------------------------------------------

    def _form_date(field_name: str, *, required: bool = True) -> date | None:
        raw = (request.form.get(field_name) or "").strip()
        if not raw:
            if required:
                raise ValueError("Provide an effective date.")
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"{raw!r} is not a valid date (expected YYYY-MM-DD).") from None

    @app.route("/bank/instruments/<int:instrument_id>/settlement", methods=["POST"])
    @gate
    def bank_instrument_settlement_assign(instrument_id: int):
        """Assign or re-assign the bank account a card settles to.

        A re-assignment closes the previous period rather than overwriting
        it, and the deduplication recompute that follows is what turns the
        card's previously un-deduplicable transactions into resolvable
        ones."""
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                card_configuration.assign_settlement_account(
                    db,
                    credit_card_payment_instrument_id=instrument_id,
                    settlement_bank_account_id=request.form.get(
                        "settlement_bank_account_id", type=int,
                    ),
                    valid_from=_form_date("valid_from"),
                    notes=request.form.get("notes"),
                    created_by_account_id=account.id,
                )
                outcome = bank_service.recompute_accounting_deduplication(db)
                db.commit()
                flash(
                    "Settlement account saved. Accounting deduplication recomputed: "
                    f"{outcome.canonical_transactions} canonical, "
                    f"{outcome.suppressed_transactions} excluded, "
                    f"{outcome.unresolved_transactions} still without a settlement account.",
                    "info",
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))

    @app.route(
        "/bank/instruments/<int:instrument_id>/settlement/<int:assignment_id>",
        methods=["POST"],
    )
    @gate
    def bank_instrument_settlement_correct(instrument_id: int, assignment_id: int):
        """Correct a settlement assignment recorded wrongly. The row is
        edited and kept — never deleted — and the recompute re-derives every
        affected accounting identity."""
        require_csrf()
        with SessionFactory() as db:
            try:
                card_configuration.correct_settlement_assignment(
                    db,
                    assignment_id=assignment_id,
                    settlement_bank_account_id=request.form.get(
                        "settlement_bank_account_id", type=int,
                    ),
                    valid_from=_form_date("valid_from"),
                    notes=request.form.get("notes"),
                )
                bank_service.recompute_accounting_deduplication(db)
                db.commit()
                flash("Settlement assignment corrected and deduplication recomputed.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))

    @app.route("/bank/instruments/<int:instrument_id>/cardholder", methods=["POST"])
    @gate
    def bank_instrument_cardholder_assign(instrument_id: int):
        """Record who holds this card from a given date. Deliberately does
        NOT recompute deduplication: the holder has no accounting
        consequence whatsoever."""
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                card_configuration.assign_cardholder(
                    db,
                    credit_card_payment_instrument_id=instrument_id,
                    holder_kind=request.form.get("holder_kind", ""),
                    holder_acting_identity_id=request.form.get(
                        "holder_acting_identity_id", type=int,
                    ) or None,
                    holder_employee_id=request.form.get("holder_employee_id", type=int) or None,
                    holder_display_name=request.form.get("holder_display_name"),
                    valid_from=_form_date("valid_from"),
                    notes=request.form.get("notes"),
                    created_by_account_id=account.id,
                )
                db.commit()
                flash("Cardholder recorded.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))

    @app.route(
        "/bank/instruments/<int:instrument_id>/cardholder/<int:assignment_id>",
        methods=["POST"],
    )
    @gate
    def bank_instrument_cardholder_correct(instrument_id: int, assignment_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                card_configuration.correct_cardholder_assignment(
                    db,
                    assignment_id=assignment_id,
                    holder_kind=request.form.get("holder_kind", ""),
                    holder_acting_identity_id=request.form.get(
                        "holder_acting_identity_id", type=int,
                    ) or None,
                    holder_employee_id=request.form.get("holder_employee_id", type=int) or None,
                    holder_display_name=request.form.get("holder_display_name"),
                    valid_from=_form_date("valid_from"),
                    notes=request.form.get("notes"),
                )
                db.commit()
                flash("Cardholder assignment corrected.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))

    @app.route("/bank/accounting-dedup/recompute", methods=["POST"])
    @gate
    def bank_recompute_accounting_dedup():
        """Re-run accounting deduplication over the whole ledger.

        Idempotent: it re-derives everything from the current transactions
        and the current card configuration and writes only the
        accounting-dedup columns. No raw row, amount, date, description,
        human duplicate decision or reconciliation decision is touched."""
        require_csrf()
        with SessionFactory() as db:
            try:
                outcome = bank_service.recompute_accounting_deduplication(db)
                db.commit()
                flash(
                    f"Accounting deduplication recomputed: {outcome.canonical_transactions} "
                    f"canonical, {outcome.duplicate_groups} duplicate group(s), "
                    f"{outcome.suppressed_transactions} excluded from accounting, "
                    f"{outcome.unresolved_transactions} without a settlement account. "
                    f"{outcome.raw_rows_preserved} raw rows preserved.",
                    "info",
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _return_redirect(redirect(url_for("bank_home")))

    # -----------------------------------------------------------------
    # Import Set Review (BANK_SOURCE_AND_IMPORT_REVIEW_001). The upload is
    # two steps with a human decision between them:
    #
    #   /bank/upload                 stage the files (outside the database),
    #                                run them through the real import inside
    #                                a transaction that is rolled back, and
    #                                show the result in one modal;
    #   /bank/upload/<token>/confirm import the staged set — once, in one
    #                                transaction;
    #   /bank/upload/<token>/cancel  discard it. Nothing was ever written.
    # -----------------------------------------------------------------

    def _staging_root() -> str:
        return bank_import_staging.staging_root(current_app.config.get("BANK_IMPORT_STAGING_DIR"))

    def _staged_redirect(options: dict, **extra):
        """Back to Import and Review, to the month the upload came from when
        it came from that page — the same rule `_return_redirect` applies."""
        if options.get("return_to") == RETURN_IMPORT_REVIEW:
            selected = _valid_month(options.get("year"), options.get("month"))
            if selected is not None:
                return redirect(url_for("bank_home", year=selected[0], month=selected[1], **extra))
        return redirect(url_for("bank_home", **extra))

    @app.route("/bank/upload", methods=["POST"])
    @gate
    def bank_upload():
        """Stage the selected files and review them. Writes NOTHING to the
        Bank data: the import is only rehearsed, and rolled back."""
        require_csrf()
        uploaded_files = [f for f in request.files.getlist("files") if f and f.filename]
        if not uploaded_files:
            flash("Select at least one CSV file to upload.", "error")
            return _return_redirect(redirect(url_for("bank_home")), **_form_month())
        options = {
            "payment_instrument_id": request.form.get("payment_instrument_id", type=int) or None,
            "return_to": request.form.get("return_to"),
            **_form_month(),
        }
        files = [(f.filename, f.read()) for f in uploaded_files]
        root = _staging_root()
        with SessionFactory() as db:
            account_id = _current_account(db).id
        token = bank_import_staging.stage(root, account_id=account_id, files=files, options=options)
        staged = bank_import_staging.load(root, token, account_id=account_id)
        try:
            with SessionFactory() as db:
                review = import_preview.preview_import(
                    db,
                    files=[import_preview.StagedFile(name, content) for name, content in files],
                    uploaded_by_account_id=account_id,
                    payment_instrument_id=options["payment_instrument_id"],
                )
        except Exception as exc:  # noqa: BLE001 — the set is discarded, nothing was written
            bank_import_staging.discard(staged)
            current_app.logger.exception("Import Set Review failed")
            flash(f"The selected files could not be reviewed, so nothing was imported: {exc}", "error")
            return _staged_redirect(options)
        bank_import_staging.save_review(staged, review)
        return _staged_redirect(options, staged=token)

    def _import_staged_files(db, *, account_id: int, files, payment_instrument_id):
        """Import a confirmed set. The per-file messages are the ones the
        upload has always given; nothing is committed here — the caller
        commits the whole set, or nothing."""
        notes: list[tuple[str, str]] = []
        covered_months: set[tuple[int, int]] = set()
        created_batch_ids: set[int] = set()
        for file_name, data in files:
            try:
                parsers.parse_csv_bytes(data)
            except parsers.UnrecognizedFormatError as exc:
                notes.append((f"{file_name}: rejected — {exc}", "error"))
                continue
            result = bank_service.import_csv(
                db, file_bytes=data, original_file_name=file_name,
                uploaded_by_account_id=account_id, payment_instrument_id=payment_instrument_id,
            )
            if not result.created:
                existing = result.batch
                if existing.id in created_batch_ids:
                    notes.append((
                        f"{file_name}: same content as {existing.original_file_name} in this "
                        "set — imported once.", "info",
                    ))
                    continue
                # BANK_MONTHLY_SOURCE_COMPLETENESS_001 §10 — the same
                # bytes were already imported, so the normal duplicate
                # import STOPS here: no second batch, no duplicate
                # transactions. Identity is content, not file name: a
                # renamed identical file lands here too, and a same-named
                # file with different bytes does not.
                instrument = existing.payment_instrument
                covered = (
                    f"{existing.date_range_start} to {existing.date_range_end}"
                    if existing.date_range_start and existing.date_range_end
                    else "date range unknown"
                )
                period_note = ""
                if existing.date_range_start is not None:
                    period_note = f", month {existing.date_range_start.strftime('%Y-%m')}"
                notes.append((
                    f"SOURCE FILE ALREADY IMPORTED — {file_name}: "
                    f"instrument {instrument.display_name if instrument else 'NOT RESOLVED'}"
                    f"{period_note}, original batch #{existing.id} "
                    f"({existing.original_file_name}, {covered}), "
                    f"imported {existing.uploaded_at:%Y-%m-%d %H:%M}. "
                    "Nothing was imported again.",
                    "info",
                ))
                continue

            created_batch_ids.add(result.batch.id)
            note = f"{file_name}: {result.batch.detected_format}, {result.parsed_row_count} row(s)"
            if result.batch.date_range_start and result.batch.date_range_end:
                note += f", {result.batch.date_range_start} to {result.batch.date_range_end}"
            if result.unreadable_row_count:
                note += f", {result.unreadable_row_count} unreadable row(s)"
            if result.candidate_duplicate_count:
                note += f", {result.candidate_duplicate_count} candidate duplicate(s)"
            category = "info"
            if result.unresolved_row_count:
                # The file names an account/card RF-One has never been
                # told about. Say WHICH one: "not resolved" on its own
                # leaves the operator hunting through the file.
                note += (
                    f" — {result.unresolved_row_count} row(s) reference an account/card "
                    f"with NO REGISTERED SOURCE ({result.resolution_detail}). "
                    "Those rows are kept as evidence and attributed to nothing; register "
                    "the Source, or assign the batch below"
                )
                category = "error"
            if result.batch.payment_instrument_id is None:
                note += " — INSTRUMENT NOT RESOLVED, requires manual resolution below"
                category = "error"
            elif result.unreadable_row_count or result.candidate_duplicate_count:
                category = "error"
            if result.batch.overlap_warning:
                note += f" — {result.batch.overlap_warning}"
            notes.append((note, category))
            covered_months |= _months_spanned(result.batch)
        return notes, covered_months

    @app.route("/bank/upload/<token>/confirm", methods=["POST"])
    @gate
    def bank_upload_confirm(token: str):
        """The human's Confirm: import the reviewed set, exactly once.

        The set is claimed before anything is imported, so a second Confirm
        of the same set finds nothing. Every file is imported in ONE
        transaction: if any of them fails, nothing of the set is kept."""
        require_csrf()
        root = _staging_root()
        with SessionFactory() as db:
            account_id = _current_account(db).id
        staged = bank_import_staging.claim(root, token, account_id=account_id)
        if staged is None:
            flash("This file set was already imported or cancelled, or it has expired. "
                  "Nothing was imported.", "error")
            return redirect(url_for("bank_home"))
        options = staged.manifest.get("options") or {}
        try:
            with SessionFactory() as db:
                try:
                    notes, covered_months = _import_staged_files(
                        db, account_id=account_id, files=staged.files(),
                        payment_instrument_id=options.get("payment_instrument_id"),
                    )
                    db.commit()
                except Exception as exc:  # noqa: BLE001 — reported, and rolled back whole
                    db.rollback()
                    current_app.logger.exception("Confirmed Bank import failed")
                    flash(f"IMPORT FAILED — nothing of this file set was imported: {exc}", "error")
                    return _staged_redirect(options)
                for note, category in notes:
                    flash(note, category)
                _report_missing_accounts(db, covered_months)
        finally:
            bank_import_staging.discard(staged)
        return _staged_redirect(options)

    @app.route("/bank/upload/<token>/cancel", methods=["POST"])
    @gate
    def bank_upload_cancel(token: str):
        """The human's Cancel: the staged set is deleted. Nothing had been
        written to the Bank data, so there is nothing to undo."""
        require_csrf()
        root = _staging_root()
        with SessionFactory() as db:
            account_id = _current_account(db).id
        staged = bank_import_staging.load(root, token, account_id=account_id)
        options = (staged.manifest.get("options") if staged else None) or {}
        bank_import_staging.discard(staged)
        flash("Import cancelled. Nothing was imported; select the files again to start over.", "info")
        return _staged_redirect(options)

    # -----------------------------------------------------------------
    # Batch actions after import.
    # -----------------------------------------------------------------

    @app.route("/bank/batches/<int:batch_id>/resolve-instrument", methods=["POST"])
    @gate
    def bank_batch_resolve_instrument(batch_id: int):
        """One endpoint for both the FIRST resolution of a batch and a
        later CORRECTION of it — they are the same operation on the same
        canonical field. `service.assign_batch_instrument` is what
        enforces the difference that matters: a correction must state a
        reason, and it moves the existing transactions instead of
        creating new ones."""
        require_csrf()
        payment_instrument_id = request.form.get("payment_instrument_id", type=int)
        reason = (request.form.get("reason") or "").strip() or None
        save_profile = bool(request.form.get("save_as_source_profile"))
        if not payment_instrument_id:
            flash("Select a Source to resolve this batch.", "error")
            return _return_redirect(redirect(url_for("bank_home")), **_form_month())
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                result = bank_service.assign_batch_instrument(
                    db, batch_id=batch_id, payment_instrument_id=payment_instrument_id,
                    reason=reason, changed_by_account_id=account.id,
                    save_as_source_profile=save_profile,
                )
                note = (
                    f"Batch #{batch_id}: {result.normalized_row_count} transaction(s) now assigned to "
                    f"{result.batch.payment_instrument.display_name!r}"
                )
                if result.candidate_duplicate_count:
                    note += f", {result.candidate_duplicate_count} candidate duplicate(s) to review"
                db.commit()
                flash(note + ".", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _return_redirect(redirect(url_for("bank_home")), **_form_month())

    @app.route("/bank/batches/<int:batch_id>/normalize-pending", methods=["POST"])
    @gate
    def bank_batch_normalize_pending(batch_id: int):
        """Normalize the rows still waiting for an instrument, re-running
        source resolution against the CURRENT instrument configuration —
        the correct action for a file that mixes several cards, where
        assigning the batch as a whole would be wrong."""
        require_csrf()
        with SessionFactory() as db:
            try:
                normalized, candidates = bank_service.normalize_pending_rows(db, batch_id=batch_id)
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _return_redirect(redirect(url_for("bank_home")), **_form_month())
        if normalized:
            note = f"Batch #{batch_id}: {normalized} pending row(s) normalized"
            if candidates:
                note += f", {candidates} candidate duplicate(s) to review"
            flash(note + ".", "info")
        else:
            flash(
                f"Batch #{batch_id}: no pending row could be resolved — the in-file identifier "
                "still matches no configured Source.",
                "error",
            )
        return _return_redirect(redirect(url_for("bank_home")), **_form_month())

    @app.route("/bank/batches/<int:batch_id>/reprocess", methods=["POST"])
    @gate
    def bank_batch_reprocess(batch_id: int):
        """Re-derive fingerprints, duplicate state, Recognition and
        matching for an already-normalized batch. Creates and deletes
        nothing; running it twice changes nothing the second time."""
        require_csrf()
        with SessionFactory() as db:
            try:
                state = bank_service.reprocess_batch(db, batch_id=batch_id)
                summary = f"Batch #{batch_id} reprocessed — status {state.status}"
                if state.reasons:
                    summary += f": {state.reasons[0]}"
                db.commit()
                flash(summary, "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _return_redirect(redirect(url_for("bank_home")), **_form_month())

    @app.route("/bank/source-profiles/<int:profile_id>", methods=["POST"])
    @gate
    def bank_source_profile_update(profile_id: int):
        """Change or disable a saved source rule. Disabling never deletes
        it — the evidence that a human taught this mapping is kept."""
        require_csrf()
        status = request.form.get("status")
        payment_instrument_id = request.form.get("payment_instrument_id", type=int)
        with SessionFactory() as db:
            try:
                if payment_instrument_id:
                    bank_service.update_source_profile_instrument(
                        db, profile_id=profile_id, payment_instrument_id=payment_instrument_id,
                    )
                if status:
                    bank_service.set_source_profile_status(db, profile_id=profile_id, status=status)
                db.commit()
                flash(f"Source rule #{profile_id} updated.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _return_redirect(redirect(url_for("bank_home")))

    # -----------------------------------------------------------------
    # Review — two queues (BANK_TWO_STAGE_REVIEW_001):
    #
    #   To Reconcile  the WHO is not yet resolved: Select Who, Rule,
    #                 duplicate decisions. A row leaves as soon as its
    #                 current decision names a WHO — or at once when it is
    #                 an own-account movement, which has no WHO by design.
    #   Reconciled    the WHO is resolved: the Reconciliation rows (WHY,
    #                 WHAT, For Whom, Confirm, Automatic / Confirmed).
    #
    # Both are views over persisted facts (`review_queues`); only the
    # selected queue's rows are loaded. Month, instrument and batch filters
    # apply to both; the former status filter is gone, because the two tabs
    # ARE the status split.
    # -----------------------------------------------------------------

    @app.route("/bank/review")
    @gate
    def bank_review():
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if not (year and month and 1 <= month <= 12):
            year = month = None
        payment_instrument_id = request.args.get("payment_instrument_id", type=int)
        # Deep link target for a batch's "Review issues" action, so a
        # concrete batch reason leads straight to the rows it is about.
        batch_id = request.args.get("batch_id", type=int)
        view = request.args.get("view")
        if view not in review_queues.VIEWS:
            view = review_queues.TO_RECONCILE
        filters = review_queues.ReviewFilters(
            year=year, month=month, payment_instrument_id=payment_instrument_id, batch_id=batch_id,
        )
        tab_args = {"year": year, "month": month, "payment_instrument_id": payment_instrument_id,
                    "batch_id": batch_id}

        with SessionFactory() as db:
            queue_counts = review_queues.counts(db, filters)
            transactions = review_queues.queue(db, view, filters)
            instruments = db.scalars(select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)).all()
            filter_batch = db.get(m.BankImportBatch, batch_id) if batch_id else None
            if view == review_queues.RECONCILED:
                # The Reconciliation page's own rows and editor, for exactly
                # this queue: one definition of status, WHY, WHAT, For Whom.
                return render_template(
                    "bank_reconciliation.html",
                    view=reconciliation_rows.rows_view(db, transactions),
                    review_mode=True, review_view=view, queue_counts=queue_counts, tab_args=tab_args,
                    instruments=instruments, filter_year=year, filter_month=month,
                    filter_payment_instrument_id=payment_instrument_id, filter_batch_id=batch_id,
                    filter_batch=filter_batch, row_limit=review_queues.ROW_LIMIT,
                    return_to=request.full_path.rstrip("?"),
                    period_label=(f"{calendar.month_name[month]} {year}" if year and month else "all months"),
                    who_rule_result=pop_rule_result(),
                )
            instruments_by_id = {i.id: i for i in instruments}

            # Canonical Financial Model Convergence — Phase 4B: the current
            # canonical decision for each transaction (Occurrence/Reason/
            # status), resolved via FinancialTransaction.explanation_id —
            # kept current by every RULE/HUMAN decision (Decision 6).
            explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
            explanations_by_id = {
                e.id: e for e in db.scalars(
                    select(m.BankTransactionExplanation).where(m.BankTransactionExplanation.id.in_(explanation_ids))
                ).all()
            } if explanation_ids else {}
            # BANK_MANUAL_WHO_WHY_001 — the "Select WHO / WHY" popup loads its
            # WHO list and each WHO's WHY on demand
            # (bank_manual_reconciliation_routes); the page itself only needs
            # the ids of the ACTIVE WHO (the Rule button's preselection, and
            # whether any WHO exists at all).
            active_who_ids = set(db.scalars(
                select(m.BankOccurrence.id).where(m.BankOccurrence.status == "ACTIVE")
            ).all())

            # Canonical Financial Model Convergence — Phase 6: cross-ledger
            # internal-transfer match state for each in-scope transaction —
            # the confirmed counterpart if already matched, or candidates a
            # HUMAN could confirm otherwise (matching.py's AUTO engine is
            # never invoked to create anything HERE — this is read-only
            # display + HUMAN-candidate listing for the confirm form below,
            # unrelated to the AUTO match this page's own transactions
            # already went through automatically at acquisition time — see
            # Phase 6B, `matching.on_financial_transaction_acquired`, called
            # from `bank_reconciliation/service.py` and the PayPal
            # connector's `ingest.py`, never from this route).
            transaction_ids = [t.id for t in transactions]
            matches = db.scalars(
                select(m.FinancialTransactionMatch).where(
                    or_(
                        m.FinancialTransactionMatch.transaction_a_id.in_(transaction_ids),
                        m.FinancialTransactionMatch.transaction_b_id.in_(transaction_ids),
                    )
                )
            ).all() if transaction_ids else []
            counterpart_by_transaction_id: dict[int, m.FinancialTransaction] = {}
            for match in matches:
                counterpart_by_transaction_id[match.transaction_a_id] = match.transaction_b
                counterpart_by_transaction_id[match.transaction_b_id] = match.transaction_a
            # BANK_TWO_STAGE_REVIEW_001 — the same candidates, asked for every
            # row at once (it was two queries per row: ~4 s for one month).
            match_candidates_by_transaction_id = matching_service.find_cross_ledger_candidates_for_many(
                db, [t for t in transactions if t.id not in counterpart_by_transaction_id],
                require_linked_instrument=False,
            )

            # Instrument-assignment history for the rows on screen: a
            # transaction that was moved says so, and says why, instead of
            # silently showing a different instrument than the file it
            # came from.
            reassignments_by_transaction_id: dict[int, list] = {}
            if transaction_ids:
                for audit in db.scalars(
                    select(m.BankInstrumentAssignmentAudit)
                    .where(m.BankInstrumentAssignmentAudit.financial_transaction_id.in_(transaction_ids))
                    .order_by(m.BankInstrumentAssignmentAudit.id.desc())
                ).all():
                    reassignments_by_transaction_id.setdefault(
                        audit.financial_transaction_id, []
                    ).append(audit)

            # BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001: the accounting
            # group each visible row belongs to, so a suppressed copy can name
            # its canonical and the canonical can say how many copies it
            # absorbed. Suppressed rows stay VISIBLE here — this is the audit
            # view — they are only excluded from accounting.
            dedup_groups = {}
            canonical_copy_counts = {}
            canonical_by_id = {}
            # BANK_PERFORMANCE_N_PLUS_ONE_001 — the copies absorbed by each
            # canonical row on screen, counted in ONE grouped query (it was
            # one count per row).
            canonical_ids = [t.id for t in transactions
                             if t.accounting_status == accounting_dedup.CANONICAL]
            copies_by_canonical = dict(db.execute(
                select(m.FinancialTransaction.accounting_canonical_transaction_id,
                       func.count(m.FinancialTransaction.id))
                .where(m.FinancialTransaction.accounting_canonical_transaction_id.in_(canonical_ids))
                .group_by(m.FinancialTransaction.accounting_canonical_transaction_id)
            ).all()) if canonical_ids else {}
            for txn in transactions:
                if txn.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED:
                    dedup_groups[txn.id] = accounting_dedup.duplicate_group(db, txn.id)
                    if txn.accounting_canonical_transaction_id is not None:
                        canonical_by_id[txn.accounting_canonical_transaction_id] = db.get(
                            m.FinancialTransaction, txn.accounting_canonical_transaction_id,
                        )
                elif txn.accounting_status == accounting_dedup.CANONICAL:
                    count = copies_by_canonical.get(txn.id, 0)
                    if count:
                        canonical_copy_counts[txn.id] = count

            batches_by_id = {
                b.id: b for b in db.scalars(select(m.BankImportBatch)).all()
            }
            return render_template(
                "bank_review.html", transactions=transactions, instruments=instruments,
                dedup_groups=dedup_groups, canonical_copy_counts=canonical_copy_counts,
                canonical_by_id=canonical_by_id, batches_by_id=batches_by_id,
                DUPLICATE_SUPPRESSED=accounting_dedup.DUPLICATE_SUPPRESSED,
                UNRESOLVED_NO_SETTLEMENT_ACCOUNT=accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT,
                instruments_by_id=instruments_by_id, explanations_by_id=explanations_by_id,
                resolved_decision_statuses=recognition.RESOLVED_DECISION_STATUSES,
                counterpart_by_transaction_id=counterpart_by_transaction_id,
                match_candidates_by_transaction_id=match_candidates_by_transaction_id,
                reassignments_by_transaction_id=reassignments_by_transaction_id,
                filter_year=year, filter_month=month,
                filter_payment_instrument_id=payment_instrument_id,
                filter_batch_id=batch_id, filter_batch=filter_batch,
                review_view=view, queue_counts=queue_counts, tab_args=tab_args,
                row_limit=review_queues.ROW_LIMIT,
                # BANK_SIMPLE_WHO_RULE_001 — the same Rule modal as
                # Classification, preselecting the row's current WHO when
                # it is active.
                active_who_ids=active_who_ids,
                who_rule_why_groups=who_rules.selectable_why_groups(db),
                who_rule_result=pop_rule_result(),
                who_rule_return_to=request.full_path.rstrip("?"),
            )

    # -----------------------------------------------------------------
    # Monthly SOURCE COMPLETENESS (BANK_MONTHLY_SOURCE_COMPLETENESS_001).
    #
    # One question only: did every bank/card that should have produced an
    # original download this month actually produce one? This is not the
    # accounting close, not reconciliation completion and not P&L approval
    # — a month can be source-complete with every transaction still
    # unclassified.
    # -----------------------------------------------------------------

    def _period_or_404(db, period_id: int):
        period = db.get(m.BankMonthlySourcePeriod, period_id)
        if period is None:
            abort(404)
        return period

    @app.route("/bank/monthly")
    @gate
    def bank_monthly():
        """Retired page (BANK_SOURCE_AND_IMPORT_REVIEW_001). Source
        completeness is checked where it matters — on Import and Review —
        so old links land on Check Sources there, for the month they named."""
        selected = _valid_month(
            request.args.get("year", type=int), request.args.get("month", type=int),
        )
        if selected is None:
            return redirect(url_for("bank_home", _anchor="step-sources"))
        return redirect(url_for("bank_home", year=selected[0], month=selected[1],
                                _anchor="step-sources"))

    @app.route("/bank/monthly/control-start", methods=["POST"])
    @gate
    def bank_monthly_control_start():
        """Set the month from which RF-One controls Bank completeness.

        Accepts the date the operator typed and refuses a mid-month one
        rather than rounding it: a half-controlled month is not a state
        RF-One defines, and silently picking a side would hide the choice.

        Setting it for the first time, or moving it EARLIER, also applies it
        to the source files already imported: the controlled months they
        cover are opened (or reused), refreshed and evaluated, without any
        file being uploaded again. Moving it LATER writes only the setting —
        no existing period, coverage row, resolution or status is touched."""
        require_csrf()
        typed = _parse_optional_date(request.form.get("control_start_date"))
        note = request.form.get("note")
        if typed is None:
            flash("Enter the first day of the first month RF-One should control (YYYY-MM-DD).",
                  "error")
            return redirect(url_for("bank_home", _anchor="step-sources"))
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                year, month = monthly_source.control_start_date_from(typed)
                config, _previous, outcome = monthly_source.activate_control_start(
                    db, year=year, month=month, note=note, account_id=account.id,
                )
                month_key = config.control_start_month
                db.commit()
                if outcome is None:
                    detail = ("Months already under control keep their periods, coverage and "
                              "decisions; nothing already recorded was changed.")
                else:
                    detail = (
                        f"{outcome.batches_examined} source file(s) already imported were "
                        f"examined: {len(outcome.created)} controlled month(s) opened, "
                        f"{len(outcome.reused)} reused, none re-imported. Nothing is declared "
                        "complete and no blocker is resolved automatically."
                    )
                flash(
                    f"Reconciliation control starts with {month_key}. Months before it hold "
                    f"imported data but are not under completeness control. {detail}",
                    "info",
                )
                if outcome is not None:
                    _flash_control_outcome(outcome)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("bank_home", _anchor="step-sources"))

    @app.route("/bank/monthly/validated-through", methods=["POST"])
    @gate
    def bank_monthly_validated_through():
        """Set the last month whose loaded data a human has certified.

        Months after it are provisional: kept and shown, never enforced.
        Setting it for the first time or advancing it brings the newly
        validated months under the ordinary rules from the files already
        imported; moving it back only makes later months provisional again —
        nothing is deleted, closed or rewritten."""
        require_csrf()
        raw = (request.form.get("validated_through_month") or "").strip()
        try:
            year, month = (int(part) for part in raw.split("-"))
        except ValueError:
            flash("Enter the validated-through month as YYYY-MM.", "error")
            return redirect(url_for("bank_home", _anchor="step-sources"))
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                config, _previous, outcome = monthly_source.activate_validated_through(
                    db, year=year, month=month, account_id=account.id,
                )
                horizon = config.validated_through_month
                db.commit()
                flash(
                    f"Bank data is validated through {horizon}. Later months are provisional: "
                    "their data is kept, but nothing in them is enforced or concluded.",
                    "info",
                )
                if outcome is not None:
                    _flash_control_outcome(outcome)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("bank_home", _anchor="step-sources"))

    @app.route("/bank/monthly/select", methods=["POST"])
    @gate
    def bank_monthly_select():
        require_csrf()
        year = request.form.get("year", type=int)
        month = request.form.get("month", type=int)
        if not year or not month or not 1 <= month <= 12:
            flash("Enter a year and a month between 1 and 12.", "error")
            return _return_redirect(redirect(url_for("bank_home", _anchor="step-sources")), **_form_month())
        with SessionFactory() as db:
            period = monthly_source.get_or_create_period(db, year, month)
            monthly_source.refresh_coverage(db, period)
            db.commit()
        return _return_redirect(
                redirect(url_for("bank_home", year=year, month=month)), year=year, month=month,
            )

    @app.route("/bank/monthly/<int:period_id>/coverage/<int:coverage_id>/resolve", methods=["POST"])
    @gate
    def bank_monthly_resolve(period_id: int, coverage_id: int):
        """Record what a human decided about an instrument with no source
        file this month.

        This is the ONLY path that may end a Payment Instrument's life, and
        only because the operator named the reason. Absence of a file never
        reaches here on its own.

        A lifecycle-ending resolution is dated by the service, from the
        instrument's last eligible posting date, and the date this form may
        carry is deliberately NOT read for one: there is exactly one way a
        closure can be dated and the operator cannot override it. For every
        other resolution the date is read and passed through exactly as it
        always was."""
        require_csrf()
        resolution = (request.form.get("resolution") or "").strip()
        note = request.form.get("note")
        effective_date = (
            None if resolution in m.LIFECYCLE_ENDING_RESOLUTIONS
            else _parse_optional_date(request.form.get("effective_date"))
        )
        replaced_by = request.form.get("replaced_by_instrument_id", type=int) or None
        with SessionFactory() as db:
            period = _period_or_404(db, period_id)
            coverage = db.get(m.BankMonthlyInstrumentCoverage, coverage_id)
            if coverage is None or coverage.period_id != period.id:
                abort(404)
            account = _current_account(db)
            try:
                monthly_source.resolve_coverage(
                    db, coverage=coverage, resolution=resolution, note=note,
                    effective_date=effective_date,
                    replaced_by_instrument_id=replaced_by, account_id=account.id,
                )
                derived = coverage.resolution_effective_date
                db.commit()
                if resolution in m.LIFECYCLE_ENDING_RESOLUTIONS:
                    detail = (
                        f" — closed as of {derived.isoformat()}, its last posting date"
                        if derived
                        else " — effective date UNKNOWN: this instrument has no eligible "
                             "posting date to close on"
                    )
                else:
                    detail = ""
                flash(
                    f"{coverage.payment_instrument.display_name}: recorded as {resolution}"
                    f"{detail}.",
                    "info",
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
            month = period.period_month
        year_s, month_s = month.split("-")
        return _return_redirect(
            redirect(url_for("bank_home", year=int(year_s), month=int(month_s))),
            year=int(year_s), month=int(month_s),
        )

    @app.route("/bank/monthly/<int:period_id>/coverage/<int:coverage_id>/clear", methods=["POST"])
    @gate
    def bank_monthly_clear_resolution(period_id: int, coverage_id: int):
        require_csrf()
        with SessionFactory() as db:
            period = _period_or_404(db, period_id)
            coverage = db.get(m.BankMonthlyInstrumentCoverage, coverage_id)
            if coverage is None or coverage.period_id != period.id:
                abort(404)
            try:
                monthly_source.clear_resolution(db, coverage=coverage)
                db.commit()
                flash("Resolution cleared.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
            month = period.period_month
        year_s, month_s = month.split("-")
        return _return_redirect(
            redirect(url_for("bank_home", year=int(year_s), month=int(month_s))),
            year=int(year_s), month=int(month_s),
        )

    @app.route("/bank/monthly/<int:period_id>/complete", methods=["POST"])
    @gate
    def bank_monthly_complete(period_id: int):
        """The gate. RF-One cannot mark a monthly Bank source period
        COMPLETE while an expected or unresolved account/card remains
        unexplained — and there is no override."""
        require_csrf()
        with SessionFactory() as db:
            period = _period_or_404(db, period_id)
            account = _current_account(db)
            report = monthly_source.complete_period(
                db, period=period, account_id=account.id,
            )
            db.commit()
            if report.provisional:
                flash(
                    f"{period.period_month} is after the validated-through month, so its data is "
                    "provisional and it cannot be certified yet. Nothing was changed.",
                    "error",
                )
            elif report.can_complete:
                flash(f"{period.period_month} is source-COMPLETE.", "info")
            else:
                flash(
                    f"{period.period_month} stays INCOMPLETE — "
                    f"{len(report.blockers)} account/card still unexplained.",
                    "error",
                )
                for blocker in report.blockers:
                    flash(blocker, "error")
            month = period.period_month
        year_s, month_s = month.split("-")
        return _return_redirect(
            redirect(url_for("bank_home", year=int(year_s), month=int(month_s))),
            year=int(year_s), month=int(month_s),
        )

    @app.route("/bank/monthly/<int:period_id>/reopen", methods=["POST"])
    @gate
    def bank_monthly_reopen(period_id: int):
        require_csrf()
        reason = request.form.get("reason") or ""
        with SessionFactory() as db:
            period = _period_or_404(db, period_id)
            account = _current_account(db)
            try:
                monthly_source.reopen_period(
                    db, period=period, reason=reason, account_id=account.id,
                )
                db.commit()
                flash(f"{period.period_month} reopened. Its previous decision is kept in the audit log.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
            month = period.period_month
        year_s, month_s = month.split("-")
        return _return_redirect(
            redirect(url_for("bank_home", year=int(year_s), month=int(month_s))),
            year=int(year_s), month=int(month_s),
        )

    @app.route("/bank/transactions/<int:transaction_id>/reassign-instrument", methods=["POST"])
    @gate
    def bank_transaction_reassign_instrument(transaction_id: int):
        """Correct ONE transaction's instrument — the case of a source file
        carrying several cards. The row is moved, not recreated; its raw
        row and the batch's original file are untouched."""
        require_csrf()
        payment_instrument_id = request.form.get("payment_instrument_id", type=int)
        reason = (request.form.get("reason") or "").strip()
        if not payment_instrument_id:
            flash("Select the Source this transaction really belongs to.", "error")
            return redirect(request.referrer or url_for("bank_review"))
        if not reason:
            flash("State a short reason for the reassignment.", "error")
            return redirect(request.referrer or url_for("bank_review"))
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                txn = bank_service.reassign_transaction_instrument(
                    db, transaction_id=transaction_id, payment_instrument_id=payment_instrument_id,
                    reason=reason, changed_by_account_id=account.id,
                )
                note = (
                    f"Transaction {transaction_id} reassigned to "
                    f"{txn.payment_instrument.display_name!r}."
                )
                db.commit()
                flash(note, "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    @app.route("/bank/transactions/<int:transaction_id>/duplicate-decision", methods=["POST"])
    @gate
    def bank_transaction_duplicate_decision(transaction_id: int):
        require_csrf()
        decision = request.form.get("decision", "")
        with SessionFactory() as db:
            try:
                bank_service.resolve_duplicate_decision(db, transaction_id=transaction_id, decision=decision)
                # BANK_CLASSIFICATION_BOOTSTRAP_001: a human verdict outranks
                # the automatic accounting key, so it only takes effect once
                # deduplication is re-derived. Confirming DISTINCT without
                # this left the row suppressed despite the decision.
                bank_service.recompute_accounting_deduplication(db)
                db.commit()
                flash(f"Duplicate decision recorded ({decision}) and deduplication recomputed.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    @app.route("/bank/transactions/<int:transaction_id>/reclassify", methods=["POST"])
    @gate
    def bank_transaction_reclassify(transaction_id: int):
        """Re-derive the WHAT of a transaction's ALREADY-decided Why through
        that Why's current mapping. The Who's default Why is never consulted
        (BANK_FINAL_RELEASE_BLOCKERS_001). Explicit by design, and appends a
        new auditable decision rather than rewriting the one it supersedes."""
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                bank_service.reclassify_transaction(
                    db, transaction_id=transaction_id, confirmed_by_account_id=account.id,
                )
                db.commit()
                flash("Transaction reclassified through its Why's current mapping.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    @app.route("/bank/transactions/<int:transaction_id>/match-decision", methods=["POST"])
    @gate
    def bank_transaction_match_decision(transaction_id: int):
        require_csrf()
        counterpart_transaction_id = request.form.get("counterpart_transaction_id", type=int)
        if not counterpart_transaction_id:
            flash("Select the counterpart transaction to confirm as an internal transfer.", "error")
            return redirect(request.referrer or url_for("bank_review"))
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                matching_service.confirm_match(
                    db, transaction_id, counterpart_transaction_id, confirmed_by=account.username,
                )
                db.commit()
                flash("Internal transfer match confirmed.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    # -----------------------------------------------------------------
    # Classification — find the WHO occurrences that are still separate
    # and teach RF-One how to group them (BANK_SIMPLE_WHO_RULE_001).
    #
    # A fast, paginated, searchable list of WHO with one Rule button per
    # row; the Rule modal and its one Apply service are shared with Review.
    # The WHAT / WHY / WHO vocabulary is maintained in Bank > Configuration,
    # not here. The GET runs a handful of bounded queries: no receiver
    # candidates over every transaction, no WHO x WHY rendering, no
    # full-database matching — matching happens only when Apply is pressed.
    # -----------------------------------------------------------------

    @app.route("/bank/classification")
    @gate
    def bank_classification():
        search = (request.args.get("q") or "").strip()
        show_inactive = request.args.get("show") == "merged"
        page_number = request.args.get("page", type=int) or 1
        from bank_general_rule_routes import pop_general_rule_result
        from bank_learning_routes import learning_view
        from rfone_data_store.bank_reconciliation import general_rules
        with SessionFactory() as db:
            page = who_rules.occurrence_page(
                db, search=search, page=page_number, show_inactive=show_inactive,
            )
            # Level 1 first (BANK_GENERAL_RULES_001): each General Rule with
            # its matches (text only, cheap). The full resolution preview is
            # an explicit action, so this page stays fast.
            all_general = general_rules.rules(db)
            counts = general_rules.match_counts(db, all_general)
            general = [(rule, {"matches": counts[rule.id][0], "distinct_candidates": counts[rule.id][1]})
                       for rule in all_general]
            return render_template(
                "bank_classification.html", page=page, search=search,
                show_inactive=show_inactive,
                general_rules=general, general_rule_result=pop_general_rule_result(),
                learning=learning_view(db),
                who_rule_why_groups=who_rules.selectable_why_groups(db),
                who_rule_result=pop_rule_result(),
                # Back to WHO Classification — not the top of the page, which
                # now opens on Classification Learning and General Rules —
                # with the same search / view / page (BANK_WHO_MANUAL_ONLY_001).
                who_rule_return_to=request.full_path.rstrip("?") + "#who-classification",
                manual_only_result=pop_manual_only_result(),
                who_groups=who_rules.GROUP_LABELS,
            )

    # -----------------------------------------------------------------
    # Kermali Monthly Accountant Export.
    # -----------------------------------------------------------------

    @app.route("/bank/export", methods=["GET", "POST"])
    @gate
    def bank_export():
        year = request.values.get("year", type=int)
        month = request.values.get("month", type=int)
        blockers = []

        if year and month:
            with SessionFactory() as db:
                blockers = export_service.compute_export_blockers(db, year=year, month=month)
                if request.method == "POST":
                    require_csrf()
                    if blockers:
                        flash("Export blocked — resolve every reason shown below first.", "error")
                    else:
                        xlsx_bytes = export_service.build_kermali_workbook(db, year=year, month=month)
                        filename = export_service.export_file_name(year=year, month=month)
                        return Response(
                            xlsx_bytes,
                            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename={filename}"},
                        )

        return render_template("bank_export.html", year=year, month=month, blockers=blockers)

    # The simple WHO Rule (BANK_SIMPLE_WHO_RULE_001): the one Apply behind
    # the Rule modal of Classification and Review.
    register_bank_who_rule_routes(
        app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, require_csrf=require_csrf,
    )

    # Classification Learning (BANK_CLASSIFICATION_LEARNING_001): explicit
    # Discover / Backtest / Test / Approve / Reject actions.
    from bank_learning_routes import register_bank_learning_routes
    register_bank_learning_routes(
        app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, require_csrf=require_csrf,
    )

    # General (structural) WHO rules (BANK_GENERAL_RULES_001), shown above
    # WHO Classification.
    from bank_general_rule_routes import register_bank_general_rule_routes
    register_bank_general_rule_routes(
        app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, require_csrf=require_csrf,
    )

    # The "Select WHO / WHY" popup of Review (BANK_MANUAL_WHO_WHY_001):
    # WHO + WHY for one transaction, a HUMAN decision; never a rule.
    from bank_manual_reconciliation_routes import register_bank_manual_reconciliation_routes
    register_bank_manual_reconciliation_routes(
        app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, require_csrf=require_csrf,
    )

    # The real Bank Configuration page (BANK_CONFIGURATION_001).
    from bank_configuration_routes import register_bank_configuration_routes
    register_bank_configuration_routes(
        app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, require_csrf=require_csrf,
    )

    # The real Bank Reconciliation page (BANK_RECONCILIATION_001).
    from bank_reconciliation_routes import register_bank_reconciliation_routes
    register_bank_reconciliation_routes(
        app, gate=gate, SessionFactory=SessionFactory,
        load_current_account=load_current_account, require_csrf=require_csrf,
    )
