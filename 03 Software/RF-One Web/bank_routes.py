"""RF-One Web — Bank Reconciliation V1 (manual CSV import & normalization).

Scope is exactly BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001: upload
Chase/First Citizens CSVs, detect format, preserve the original file,
normalize into the canonical `FinancialTransaction` ledger, and surface
duplicate candidates and already-imported files for review. No connector,
no invoice matching, no general ledger.

Canonical Financial Model Convergence — Phase 3/4/4B/6 (FINANCIAL_MODEL_
CONVERGENCE_001): every route here uses the canonical `PaymentInstrument`/
`FinancialTransaction` models. Per Product Owner Decisions 1/7/10, human
reconciliation review is ONE action inside this same Bank Review
workflow — confirm/correct the canonical Occurrence (WHO) and Reason
(WHY) Recognition proposed, with an explicit reuse-for-future choice.
There is no separate legacy Supplier/Receiving classification action.

Phase 6 adds one further, minimal action to the same page: confirming a
cross-ledger internal-transfer match (`bank_reconciliation/matching.py`)
when RF-One's own AUTO criteria found insufficient/ambiguous evidence —
no new page, no general matching application.

BANK_RECONCILIATION_WHO_WHY_WHAT_001 makes the classification
hierarchical and moves its configuration out of the Review. Review now
offers exactly ONE control per unclassified transaction — `Select Who` —
because the WHY and the WHAT are derived from the chosen WHO through the
associations stored on the vocabulary itself. Those associations are
configured on the new `Classification` tab (`/bank/classification`,
fourth and last, after `Monthly Export`), which owns the WHAT catalog,
the WHY -> WHAT links and the WHO -> WHY links. Every mutating route here
is behind `require_domain_access("BANK")` and `require_csrf()`, exactly
like every Bank route that came before it.

Every route calls straight into `rfone_data_store.bank_reconciliation`
(`service`/`export`/`parsers`) — no business logic is duplicated here.
Registered from `app.py` via `register_bank_routes(app, ...)`, mirroring
`compensation_routes.py`'s "pass in collaborators explicitly" convention:
this module never imports `app.py` itself."""

from __future__ import annotations

import base64
import calendar
import json
from datetime import date, datetime

from flask import Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import card_configuration
from rfone_data_store.bank_reconciliation import canonical_catalog
from rfone_data_store.bank_reconciliation import why_catalog
from rfone_data_store.bank_reconciliation import receiver_candidates
from rfone_data_store.bank_reconciliation import what_catalog_import
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import export as export_service
from rfone_data_store.bank_reconciliation import matching as matching_service
from rfone_data_store.bank_reconciliation import monthly_source
from rfone_data_store.bank_reconciliation import parsers
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import service as bank_service


def _months_spanned(batch) -> set[tuple[int, int]]:
    """The calendar months a source file's own covered range touches.

    Uses the range the parser already recorded on the batch — the same
    fact `monthly_source.batches_covering` matches a month against — so a
    file is never attributed to a month by its name or upload date. A
    batch RF-One could not date covers nothing: an unreadable file is not
    evidence about any month.
    """
    start, end = batch.date_range_start, batch.date_range_end
    if start is None or end is None:
        return set()
    months, year, month = set(), start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.add((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _report_missing_accounts(db, covered_months: set[tuple[int, int]]) -> None:
    """Re-evaluate the months this import touched, so an expected account
    that no file represented becomes visible instead of disappearing.

    Entirely the EXISTING monthly coverage logic — `refresh_coverage` and
    `evaluate`, the same pair the monthly screen runs on every view. It
    adds no second definition of "expected account" and no second place to
    resolve one: the resolution itself still happens on the monthly screen,
    through the workflow that was already there.

    It refreshes only months that ALREADY EXIST. Whether importing a file
    should OPEN a month nobody opened is a workflow decision RF-One has not
    made, and inventing one here would put months — potentially years of
    them, from a single historical download — into the completeness control
    on RF-One's initiative rather than the Product Owner's.
    """
    flagged = False
    for year, month in sorted(covered_months):
        period = monthly_source.get_period(db, year, month)
        if period is None or period.status == "COMPLETE":
            continue
        monthly_source.refresh_coverage(db, period)
        report = monthly_source.evaluate(db, period)
        if report.blockers:
            flagged = True
            flash(
                f"MISSING ACCOUNTS — {period.period_month}: "
                f"{len(report.blockers)} expected account(s) not represented by the data "
                "received. Each needs a decision: the file/data is still missing, or the "
                "account is closed. " + " ".join(report.blockers),
                "error",
            )
    db.commit()
    if flagged:
        flash(
            "Resolve them on Monthly Sources — nothing was closed or deactivated by this "
            "import.",
            "info",
        )


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

    @app.route("/bank")
    @gate
    def bank_home():
        with SessionFactory() as db:
            batches = db.scalars(
                select(m.BankImportBatch).order_by(m.BankImportBatch.uploaded_at.desc())
            ).all()
            instruments = _instruments(db)
            legal_entities = _active_legal_entities(db)
            instruments_by_id = {i.id: i for i in instruments}

            # The concrete reason each batch is in the status it shows, and
            # the one action that addresses it — computed live, never read
            # from a stored field. A bare `REQUIRES_REVIEW` with no reason
            # and no available action was the defect this replaces.
            batch_states = {
                batch.id: bank_service.compute_batch_review_state(db, batch) for batch in batches
            }
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
                "bank_home.html", batches=batches, instruments=instruments,
                instruments_by_id=instruments_by_id, legal_entities=legal_entities,
                batch_states=batch_states, instrument_warnings=instrument_warnings,
                source_profiles=source_profiles, assignment_audits=assignment_audits,
                settlement_accounts=settlement_accounts, cardholders=cardholders,
                derived_companies=derived_companies, card_warnings=card_warnings,
                dedup=dedup,
            )

    # -----------------------------------------------------------------
    # Payment Instrument configuration — create and edit.
    # -----------------------------------------------------------------

    def _cardholder_candidates(db):
        """Real people this database can link a cardholder to.

        `ActingIdentity` is filtered to `HUMAN_USER`: a card is held by a
        person, and a SYSTEM identity is never a valid answer. An Employee
        already represented by an identity of the same name is dropped, so
        the list does not show the same human twice under two labels.
        Returns plain dicts because the modal renders them uniformly and
        must not care which table each one came from."""
        identities = db.scalars(
            select(m.ActingIdentity)
            .where(
                m.ActingIdentity.is_active.is_(True),
                m.ActingIdentity.kind == "HUMAN_USER",
            )
            .order_by(m.ActingIdentity.display_name)
        ).all()
        employees = db.scalars(
            select(m.Employee)
            .where(or_(m.Employee.active.is_(True), m.Employee.active.is_(None)))
            .order_by(m.Employee.display_name)
        ).all()

        candidates = [
            {
                "kind": "ACTING_IDENTITY", "id": identity.id,
                "name": identity.display_name, "source": "RF-One identity",
            }
            for identity in identities
        ]
        seen = {(c["name"] or "").strip().casefold() for c in candidates}
        for employee in employees:
            name = (employee.display_name or "").strip()
            if name and name.casefold() in seen:
                continue  # same person, already offered as a canonical identity
            candidates.append({
                "kind": "EMPLOYEE", "id": employee.id,
                "name": name or f"Employee {employee.id}", "source": "Employee",
            })
            if name:
                seen.add(name.casefold())
        return candidates

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

    @app.route("/bank/instruments/new", methods=["POST"])
    @gate
    def bank_instrument_new():
        require_csrf()
        values = _instrument_form_values(request.form)
        with SessionFactory() as db:
            try:
                instrument = bank_service.create_payment_instrument(db, **values)
                warning = bank_service.instrument_export_warning(instrument)
                display_name = instrument.display_name
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("bank_home"))
        flash(f"Payment Instrument {display_name!r} created.", "info")
        if warning:
            flash(f"{display_name}: {warning}", "error")
        return redirect(url_for("bank_home"))

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
                            flash(str(exc), "error")
                            return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))
                else:
                    values["linked_instrument_id"] = legacy_link

                try:
                    bank_service.update_payment_instrument(db, instrument_id=instrument_id, **values)
                    warning = bank_service.instrument_export_warning(instrument)
                    display_name = instrument.display_name
                    db.commit()
                except ValueError as exc:
                    db.rollback()
                    flash(str(exc), "error")
                    return redirect(url_for("bank_instrument_edit", instrument_id=instrument_id))
                flash(f"Payment Instrument {display_name!r} updated.", "info")
                if warning:
                    flash(f"{display_name}: {warning}", "error")
                return redirect(url_for("bank_home"))

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
        return redirect(url_for("bank_home"))

    # -----------------------------------------------------------------
    # Upload — multiple files, format recognition, instrument confirmation.
    # -----------------------------------------------------------------

    @app.route("/bank/upload", methods=["POST"])
    @gate
    def bank_upload():
        require_csrf()
        payment_instrument_id = request.form.get("payment_instrument_id", type=int) or None
        uploaded_files = [f for f in request.files.getlist("files") if f and f.filename]
        if not uploaded_files:
            flash("Select at least one CSV file to upload.", "error")
            return redirect(url_for("bank_home"))

        with SessionFactory() as db:
            account = _current_account(db)
            covered_months: set[tuple[int, int]] = set()
            for uploaded in uploaded_files:
                data = uploaded.read()
                try:
                    result = bank_service.import_csv(
                        db, file_bytes=data, original_file_name=uploaded.filename,
                        uploaded_by_account_id=account.id, payment_instrument_id=payment_instrument_id,
                    )
                except parsers.UnrecognizedFormatError as exc:
                    db.rollback()
                    flash(f"{uploaded.filename}: rejected — {exc}", "error")
                    continue

                db.commit()
                if not result.created:
                    # BANK_MONTHLY_SOURCE_COMPLETENESS_001 §10 — the same
                    # bytes were already imported, so the normal duplicate
                    # import STOPS here: no second batch, no duplicate
                    # transactions. The message names the four facts the
                    # operator needs to recognise what they already have,
                    # rather than a bare batch number. Identity is content,
                    # not file name: a renamed identical file lands here
                    # too, and a same-named file with different bytes does
                    # not.
                    existing = result.batch
                    instrument = existing.payment_instrument
                    covered = (
                        f"{existing.date_range_start} to {existing.date_range_end}"
                        if existing.date_range_start and existing.date_range_end
                        else "date range unknown"
                    )
                    period_note = ""
                    if existing.date_range_start is not None:
                        period_note = (
                            f", month {existing.date_range_start.strftime('%Y-%m')}"
                        )
                    flash(
                        f"SOURCE FILE ALREADY IMPORTED — {uploaded.filename}: "
                        f"instrument {instrument.display_name if instrument else 'NOT RESOLVED'}"
                        f"{period_note}, original batch #{existing.id} "
                        f"({existing.original_file_name}, {covered}), "
                        f"imported {existing.uploaded_at:%Y-%m-%d %H:%M}. "
                        "Nothing was imported again.",
                        "info",
                    )
                    continue

                note = f"{uploaded.filename}: {result.batch.detected_format}, {result.parsed_row_count} row(s)"
                if result.batch.date_range_start and result.batch.date_range_end:
                    note += f", {result.batch.date_range_start} to {result.batch.date_range_end}"
                if result.unreadable_row_count:
                    note += f", {result.unreadable_row_count} unreadable row(s)"
                if result.candidate_duplicate_count:
                    note += f", {result.candidate_duplicate_count} candidate duplicate(s)"
                category = "info"
                if result.batch.payment_instrument_id is None:
                    note += " — INSTRUMENT NOT RESOLVED, requires manual resolution below"
                    category = "error"
                elif result.unreadable_row_count or result.candidate_duplicate_count:
                    category = "error"
                if result.batch.overlap_warning:
                    note += f" — {result.batch.overlap_warning}"
                flash(note, category)
                covered_months |= _months_spanned(result.batch)

            _report_missing_accounts(db, covered_months)

        return redirect(url_for("bank_home"))

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
            flash("Select a Payment Instrument to resolve this batch.", "error")
            return redirect(url_for("bank_home"))
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
        return redirect(url_for("bank_home"))

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
                return redirect(url_for("bank_home"))
        if normalized:
            note = f"Batch #{batch_id}: {normalized} pending row(s) normalized"
            if candidates:
                note += f", {candidates} candidate duplicate(s) to review"
            flash(note + ".", "info")
        else:
            flash(
                f"Batch #{batch_id}: no pending row could be resolved — the in-file identifier "
                "still matches no configured Payment Instrument.",
                "error",
            )
        return redirect(url_for("bank_home"))

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
        return redirect(url_for("bank_home"))

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
        return redirect(url_for("bank_home"))

    # -----------------------------------------------------------------
    # Review — filter, resolve duplicates, assign classification.
    # -----------------------------------------------------------------

    @app.route("/bank/review")
    @gate
    def bank_review():
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        payment_instrument_id = request.args.get("payment_instrument_id", type=int)
        status = request.args.get("status") or None
        # Deep link target for a batch's "Review issues" action, so a
        # concrete batch reason leads straight to the rows it is about.
        batch_id = request.args.get("batch_id", type=int)

        with SessionFactory() as db:
            query = select(m.FinancialTransaction).order_by(
                m.FinancialTransaction.posting_date.desc(),
                m.FinancialTransaction.id.desc(),
            )
            if year and month:
                last_day = calendar.monthrange(year, month)[1]
                start, end = date(year, month, 1), date(year, month, last_day)
                query = query.where(
                    m.FinancialTransaction.posting_date >= start,
                    m.FinancialTransaction.posting_date <= end,
                )
            if payment_instrument_id:
                query = query.where(m.FinancialTransaction.payment_instrument_id == payment_instrument_id)
            if batch_id:
                query = query.where(m.FinancialTransaction.import_batch_id == batch_id)
            if status == "CANDIDATE_DUPLICATE":
                query = query.where(m.FinancialTransaction.duplicate_status == "CANDIDATE_DUPLICATE")
            elif status == "REQUIRES_REVIEW":
                query = query.where(m.FinancialTransaction.review_status == "REQUIRES_REVIEW")

            transactions = db.scalars(query.limit(500)).all()
            instruments = db.scalars(select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)).all()
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
            # BANK_RECONCILIATION_WHO_WHY_WHAT_001: the Review offers the
            # WHO and nothing else. Each candidate carries its derived
            # Why/What — or, when its chain is incomplete, the concrete
            # reason it cannot be selected and where to go and fix it.
            # INACTIVE Whos are included deliberately: the modal shows
            # them as unselectable WITH the reason, which is far more
            # useful than a human hunting for a name that silently is not
            # in the list.
            occurrences = classification_service.list_occurrences(db)
            occurrence_types_by_id = {
                t.id: t for t in classification_service.list_occurrence_types(db)
            }
            chains = classification_service.resolve_chains(db, occurrences)
            who_options = [
                {
                    "id": occurrence.id,
                    "name": occurrence.canonical_name,
                    "type": (
                        occurrence_types_by_id[occurrence.occurrence_type_id].name
                        if occurrence.occurrence_type_id in occurrence_types_by_id else ""
                    ),
                    "status": occurrence.status,
                    "why": (
                        chains[occurrence.id].transaction_reason.name
                        if chains[occurrence.id].transaction_reason is not None else None
                    ),
                    "what": (
                        f"{chains[occurrence.id].accounting_classification.code} — "
                        f"{chains[occurrence.id].accounting_classification.name}"
                        if chains[occurrence.id].accounting_classification is not None else None
                    ),
                    "selectable": chains[occurrence.id].is_complete,
                    "blocking_reason": chains[occurrence.id].blocking_reason,
                }
                for occurrence in occurrences
            ]

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
            match_candidates_by_transaction_id: dict[int, list[m.FinancialTransaction]] = {}
            for txn in transactions:
                if txn.id in counterpart_by_transaction_id:
                    continue
                candidates = matching_service.find_cross_ledger_candidates(
                    db, txn, require_linked_instrument=False,
                )
                if candidates:
                    match_candidates_by_transaction_id[txn.id] = candidates

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

            filter_batch = db.get(m.BankImportBatch, batch_id) if batch_id else None

            # BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001: the accounting
            # group each visible row belongs to, so a suppressed copy can name
            # its canonical and the canonical can say how many copies it
            # absorbed. Suppressed rows stay VISIBLE here — this is the audit
            # view — they are only excluded from accounting.
            dedup_groups = {}
            canonical_copy_counts = {}
            canonical_by_id = {}
            for txn in transactions:
                if txn.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED:
                    dedup_groups[txn.id] = accounting_dedup.duplicate_group(db, txn.id)
                    if txn.accounting_canonical_transaction_id is not None:
                        canonical_by_id[txn.accounting_canonical_transaction_id] = db.get(
                            m.FinancialTransaction, txn.accounting_canonical_transaction_id,
                        )
                elif txn.accounting_status == accounting_dedup.CANONICAL:
                    count = db.scalar(
                        select(func.count(m.FinancialTransaction.id)).where(
                            m.FinancialTransaction.accounting_canonical_transaction_id == txn.id
                        )
                    ) or 0
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
                who_options=who_options,
                # BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §21-§22.
                # `why_by_occurrence` is the ORDINARY dropdown: per Who,
                # only the purposes a human already confirmed for it.
                # `why_catalog_groups` is the "+ New" modal ONLY — the full
                # catalog, grouped. Management groups appear nowhere else.
                why_by_occurrence={
                    option["id"]: why_catalog.reasons_for_occurrence(db, option["id"])
                    for option in who_options
                },
                # Serialisable form for the page script: Who id -> Why ids.
                why_ids_by_occurrence={
                    str(option["id"]): [
                        reason.id
                        for reason in why_catalog.reasons_for_occurrence(db, option["id"])
                    ]
                    for option in who_options
                },
                why_catalog_groups=why_catalog.catalog_by_group(db),
                resolved_decision_statuses=recognition.RESOLVED_DECISION_STATUSES,
                counterpart_by_transaction_id=counterpart_by_transaction_id,
                match_candidates_by_transaction_id=match_candidates_by_transaction_id,
                reassignments_by_transaction_id=reassignments_by_transaction_id,
                filter_year=year, filter_month=month,
                filter_payment_instrument_id=payment_instrument_id, filter_status=status,
                filter_batch_id=batch_id, filter_batch=filter_batch,
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
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        with SessionFactory() as db:
            period = None
            if year and month:
                try:
                    period = monthly_source.get_period(db, year, month)
                except ValueError:
                    flash("Month must be between 1 and 12.", "error")
            if period is None:
                period = db.scalars(
                    select(m.BankMonthlySourcePeriod)
                    .order_by(m.BankMonthlySourcePeriod.period_month.desc())
                ).first()

            rows, report, extra_batches = [], None, {}
            if period is not None:
                # An OPEN month re-evaluates on every view, so the screen is
                # never stale. A COMPLETE one is history and is read as-is.
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

            return render_template(
                "bank_monthly.html",
                period=period,
                periods=monthly_source.list_periods(db),
                coverages=rows,
                report=report,
                extra_batches=extra_batches,
                instruments=db.scalars(
                    select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)
                ).all(),
                EXPECTED=m.COVERAGE_EXPECTED,
                NOT_EXPECTED=m.COVERAGE_NOT_EXPECTED,
                NEEDS_CONFIRMATION=m.COVERAGE_NEEDS_CONFIRMATION,
                RESOLUTIONS=m.COVERAGE_RESOLUTIONS,
            )

    @app.route("/bank/monthly/select", methods=["POST"])
    @gate
    def bank_monthly_select():
        require_csrf()
        year = request.form.get("year", type=int)
        month = request.form.get("month", type=int)
        if not year or not month or not 1 <= month <= 12:
            flash("Enter a year and a month between 1 and 12.", "error")
            return redirect(url_for("bank_monthly"))
        with SessionFactory() as db:
            period = monthly_source.get_or_create_period(db, year, month)
            monthly_source.refresh_coverage(db, period)
            db.commit()
        return redirect(url_for("bank_monthly", year=year, month=month))

    @app.route("/bank/monthly/<int:period_id>/coverage/<int:coverage_id>/resolve", methods=["POST"])
    @gate
    def bank_monthly_resolve(period_id: int, coverage_id: int):
        """Record what a human decided about an instrument with no source
        file this month.

        This is the ONLY path that may end a Payment Instrument's life, and
        only because the operator named the reason. Absence of a file never
        reaches here on its own.

        No closure date is read from the form. For a lifecycle-ending
        resolution the service derives it from the instrument's last
        eligible posting date, so there is exactly one way a closure can be
        dated and the operator cannot override it."""
        require_csrf()
        resolution = (request.form.get("resolution") or "").strip()
        note = request.form.get("note")
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
        return redirect(url_for("bank_monthly", year=int(year_s), month=int(month_s)))

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
        return redirect(url_for("bank_monthly", year=int(year_s), month=int(month_s)))

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
            if report.can_complete:
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
        return redirect(url_for("bank_monthly", year=int(year_s), month=int(month_s)))

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
        return redirect(url_for("bank_monthly", year=int(year_s), month=int(month_s)))

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
            flash("Select the Payment Instrument this transaction really belongs to.", "error")
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

    @app.route("/bank/transactions/<int:transaction_id>/why", methods=["POST"])
    @require_domain_access("BANK")
    def bank_transaction_why_decision(transaction_id: int):
        """Assign the WHY an operator chose for one transaction.

        BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §22-§23 — this is the
        "+ New" path and the ordinary dropdown path, which are the same
        action: the Why is recorded for THIS transaction, the WHO <-> WHY
        association is created or reconfirmed so the dropdown offers it
        next time, and the WHAT is DERIVED from the Why. The operator
        never picks a What here; if the mapping is wrong the central Why
        definition is corrected instead."""
        # BANK_MANUAL_RECONCILIATION_UX_001 — this route writes a
        # classification decision, so it needs the same CSRF check every
        # other writing Bank route performs. It was the one POST endpoint
        # in this module without it, which only went unnoticed while no
        # browser flow actually reached it.
        require_csrf()
        occurrence_id = request.form.get("occurrence_id", type=int)
        transaction_reason_id = request.form.get("transaction_reason_id", type=int)
        # The same learning control the Who-only route already exposes, and
        # the one the checkbox on this form has always described: it decides
        # whether this confirmation also teaches RF-One that this normalized
        # DESCRIPTION means this WHO. It is orthogonal to the WHY — the
        # WHO <-> WHY association below is recorded either way — and it never
        # teaches a WHO -> WHY recognition.
        learn_description = bool(request.form.get("learn_description"))
        if not occurrence_id or not transaction_reason_id:
            flash("Choose both a Who and a Why.", "error")
            return redirect(request.referrer or url_for("bank_review"))
        with SessionFactory() as db:
            # `_current_account(db)` — the same session-scoped resolution
            # every other writing route in this module uses. This line
            # previously called a bare `current_account()`, a name that
            # exists nowhere here, so the route raised NameError on every
            # request; nothing reached it while the Why step was unwired.
            account = _current_account(db)
            try:
                recognition.record_human_decision(
                    db,
                    recognition.HumanDecisionRequest(
                        transaction_id=transaction_id,
                        occurrence_id=occurrence_id,
                        transaction_reason_id=transaction_reason_id,
                        confirmed_by_account_id=account.id,
                        learn_description=learn_description,
                    ),
                )
                reason = db.get(m.BankTransactionReason, transaction_reason_id)
                label = reason.resolution_label if reason else ""
                db.commit()
                flash(f"Classified as {label}.", "success")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    @app.route("/bank/transactions/<int:transaction_id>/recognition-decision", methods=["POST"])
    @gate
    def bank_transaction_recognition_decision(transaction_id: int):
        """The Who is the only classification input this route accepts.
        Why and What are derived from the Who's stored chain by
        `record_recognition_decision`; an incomplete chain comes back as a
        `ValueError` carrying the sentence to show the human."""
        require_csrf()
        occurrence_id = request.form.get("occurrence_id", type=int)
        # Learning control only — it decides whether this confirmation also
        # teaches RF-One that this normalized description means this Who.
        # It has no effect on the Who -> Why -> What associations, which
        # live on the vocabulary and persist regardless.
        learn_description = bool(request.form.get("learn_description"))
        if not occurrence_id:
            flash("Select a Who for this transaction.", "error")
            return redirect(request.referrer or url_for("bank_review"))
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                bank_service.record_recognition_decision(
                    db, transaction_id=transaction_id, occurrence_id=occurrence_id,
                    confirmed_by_account_id=account.id, learn_description=learn_description,
                )
                db.commit()
                flash("Reconciliation decision recorded.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    @app.route("/bank/transactions/<int:transaction_id>/reclassify", methods=["POST"])
    @gate
    def bank_transaction_reclassify(transaction_id: int):
        """Apply the CURRENT Who -> Why -> What chain to a transaction that
        was decided under an earlier one. Explicit by design: editing an
        association never reaches back into confirmed history on its own,
        and this action appends a new auditable decision rather than
        rewriting the one it supersedes."""
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                bank_service.reclassify_transaction(
                    db, transaction_id=transaction_id, confirmed_by_account_id=account.id,
                )
                db.commit()
                flash("Transaction reclassified against the current chain.", "info")
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
    # Classification — the WHO -> WHY -> WHAT vocabulary and its links.
    #
    # One tab, three sections, because the three levels are one chain and
    # splitting them across pages would hide exactly the relationship the
    # operator needs to see. Every list is searchable from the server, so
    # none of the three can grow into an unusable menu.
    # -----------------------------------------------------------------

    @app.route("/bank/classification")
    @gate
    def bank_classification():
        what_search = (request.args.get("what_q") or "").strip()
        why_search = (request.args.get("why_q") or "").strip()
        who_search = (request.args.get("who_q") or "").strip()

        with SessionFactory() as db:
            whats = classification_service.list_accounting_classifications(db, search=what_search)
            # BANK_WHAT_PL_VOCABULARY_001 — WHAT is the official P&L
            # posting vocabulary, not the whole chart of accounts. The two
            # are handed to the template SEPARATELY so the page cannot show
            # a Balance Sheet account under the WHAT heading.
            what_catalog = canonical_catalog.what_catalog(db)
            what_group_nodes = canonical_catalog.what_groups(db)
            accounting_destinations = canonical_catalog.accounting_destinations(db)
            whys = classification_service.list_transaction_reasons(db, search=why_search)
            whos = classification_service.list_occurrences(db, search=who_search)

            # Assignable options are the COMPLETE, POSTABLE ones only — the
            # UI never offers a choice the service layer would then refuse,
            # and since BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 a
            # reporting GROUP is one of those refusals.
            assignable_whats = [w for w in classification_service.list_accounting_classifications(db)
                                if w.active and w.statement_type is not None
                                and w.is_posting_account]
            assignable_whys = [r for r in classification_service.list_transaction_reasons(db)
                               if r.status == "ACTIVE" and r.accounting_classification_id is not None]

            whats_by_id = {
                w.id: w for w in classification_service.list_accounting_classifications(db)
            }
            whys_by_id = {r.id: r for r in classification_service.list_transaction_reasons(db)}
            types_by_id = {t.id: t for t in classification_service.list_occurrence_types(db)}

            # BANK_CLASSIFICATION_BOOTSTRAP_001 — the receiver review.
            # Derived on every request from the current transactions: there
            # is no stored candidate that could go stale, and rendering the
            # page writes nothing.
            receiver_search = (request.args.get("receiver_q") or "").strip()
            receiver_status = (request.args.get("receiver_status") or "").strip().upper()
            receiver_sort = request.args.get("receiver_sort") or "count"
            receiver_page = max(request.args.get("receiver_page", type=int) or 1, 1)
            page_size = 25

            all_candidates = receiver_candidates.build_candidates(db)
            filtered = all_candidates
            if receiver_search:
                needle = receiver_search.lower()
                filtered = [
                    c for c in filtered
                    if needle in c.payee_normalized.lower()
                    or any(needle in d.lower() for d in c.sample_descriptions)
                ]
            if receiver_status in (
                receiver_candidates.STATUS_UNCLASSIFIED,
                receiver_candidates.STATUS_AMBIGUOUS,
                receiver_candidates.STATUS_ASSIGNED,
            ):
                filtered = [c for c in filtered if c.status == receiver_status]
            if receiver_sort == "value":
                filtered = sorted(filtered, key=lambda c: -c.absolute_total_minor)
            elif receiver_sort == "recent":
                filtered = sorted(filtered, key=lambda c: (c.last_date is None, c.last_date), reverse=True)
            else:
                filtered = sorted(
                    filtered, key=lambda c: (-c.transaction_count, -c.absolute_total_minor)
                )

            total_pages = max((len(filtered) + page_size - 1) // page_size, 1)
            receiver_page = min(receiver_page, total_pages)
            page_start = (receiver_page - 1) * page_size
            receiver_page_items = filtered[page_start:page_start + page_size]

            learned_rules = db.scalars(
                select(m.BankRecognitionRule)
                .order_by(m.BankRecognitionRule.id.desc())
                .limit(100)
            ).all()

            return render_template(
                "bank_classification.html",
                whats=whats, whys=whys, whos=whos,
                # BANK_WHAT_PL_VOCABULARY_001 — the official P&L vocabulary
                # and the Balance Sheet destinations, kept apart so the page
                # cannot show one under the other's heading.
                what_catalog=what_catalog,
                what_group_nodes=what_group_nodes,
                accounting_destinations=accounting_destinations,
                receiver_candidates_page=receiver_page_items,
                receiver_summary=receiver_candidates.summary(db),
                receiver_filtered_count=len(filtered),
                receiver_page=receiver_page, receiver_total_pages=total_pages,
                receiver_search=receiver_search, receiver_status=receiver_status,
                receiver_sort=receiver_sort,
                learned_rules=learned_rules,
                occurrences_by_id={o.id: o for o in whos},
                STATUS_UNCLASSIFIED=receiver_candidates.STATUS_UNCLASSIFIED,
                STATUS_AMBIGUOUS=receiver_candidates.STATUS_AMBIGUOUS,
                STATUS_ASSIGNED=receiver_candidates.STATUS_ASSIGNED,
                what_preview=None,
                whats_by_id=whats_by_id, whys_by_id=whys_by_id, types_by_id=types_by_id,
                assignable_whats=assignable_whats, assignable_whys=assignable_whys,
                occurrence_types=classification_service.list_occurrence_types(db),
                chains=classification_service.resolve_chains(db, whos),
                usage={w.id: classification_service.accounting_classification_usage(db, w.id) for w in whats},
                statement_type_labels=classification_service.STATEMENT_TYPE_LABELS,
                what_search=what_search, why_search=why_search, who_search=who_search,
            )

    # --- What catalog import (BANK_CLASSIFICATION_BOOTSTRAP_001) ------
    #
    # Upload -> parse -> PREVIEW -> human confirmation -> import. There is
    # deliberately no route that takes a file and writes accounts in one
    # step: a chart of accounts is the vocabulary every future decision is
    # phrased in, and it is not imported on trust.

    @app.route("/bank/classification/what/import", methods=["POST"])
    @gate
    def bank_classification_what_import_preview():
        """Parse an uploaded plan and show what it contains. Writes nothing."""
        require_csrf()
        uploaded = request.files.get("catalog_file")
        if uploaded is None or not uploaded.filename:
            flash("Choose a .csv or .xlsx chart of accounts to import.", "error")
            return _redirect_to_classification("what")

        payload = uploaded.read()
        parsed = what_catalog_import.parse(
            payload,
            file_name=uploaded.filename,
            sheet_name=(request.form.get("sheet_name") or "").strip() or None,
            default_statement_type=(request.form.get("default_statement_type") or "").strip() or None,
        )

        with SessionFactory() as db:
            whats = classification_service.list_accounting_classifications(db)
            whys = classification_service.list_transaction_reasons(db)
            whos = classification_service.list_occurrences(db)
            what_catalog = canonical_catalog.what_catalog(db)
            what_group_nodes = canonical_catalog.what_groups(db)
            accounting_destinations = canonical_catalog.accounting_destinations(db)
            return render_template(
                "bank_classification.html",
                whats=whats, whys=whys, whos=whos,
                what_catalog=what_catalog,
                what_group_nodes=what_group_nodes,
                accounting_destinations=accounting_destinations,
                whats_by_id={w.id: w for w in whats},
                whys_by_id={r.id: r for r in whys},
                types_by_id={t.id: t for t in classification_service.list_occurrence_types(db)},
                assignable_whats=[
                    w for w in whats if w.active and w.statement_type is not None
                ],
                assignable_whys=[
                    r for r in whys
                    if r.status == "ACTIVE" and r.accounting_classification_id is not None
                ],
                occurrence_types=classification_service.list_occurrence_types(db),
                chains=classification_service.resolve_chains(db, whos),
                usage={
                    w.id: classification_service.accounting_classification_usage(db, w.id)
                    for w in whats
                },
                statement_type_labels=classification_service.STATEMENT_TYPE_LABELS,
                what_search="", why_search="", who_search="",
                receiver_candidates_page=[], receiver_summary=receiver_candidates.summary(db),
                receiver_filtered_count=0, receiver_page=1, receiver_total_pages=1,
                receiver_search="", receiver_status="", receiver_sort="count",
                learned_rules=[], occurrences_by_id={o.id: o for o in whos},
                STATUS_UNCLASSIFIED=receiver_candidates.STATUS_UNCLASSIFIED,
                STATUS_AMBIGUOUS=receiver_candidates.STATUS_AMBIGUOUS,
                STATUS_ASSIGNED=receiver_candidates.STATUS_ASSIGNED,
                what_preview=parsed,
                what_preview_file_name=uploaded.filename,
                # The PARSED ROWS travel back for confirmation, not the file:
                # the preview a human approved is exactly what gets imported,
                # and no uploaded document is retained anywhere.
                what_preview_token=base64.b64encode(json.dumps({
                    "file_name": uploaded.filename,
                    "sheet_name": parsed.sheet_name,
                    "rows": [
                        {
                            "source_row_number": row.source_row_number,
                            "statement_type": row.statement_type,
                            "code": row.code,
                            "code_is_generated": row.code_is_generated,
                            "name": row.name,
                            "parent_code": row.parent_code,
                            "level": row.level,
                            "row_type": row.row_type,
                            "source_label": row.source_label,
                        }
                        for row in parsed.importable_rows
                    ],
                }).encode("utf-8")).decode("ascii"),
            )

    @app.route("/bank/classification/what/import/confirm", methods=["POST"])
    @gate
    def bank_classification_what_import_confirm():
        """Import exactly the rows the human just saw in the preview."""
        require_csrf()
        token = request.form.get("preview_token") or ""
        try:
            payload = json.loads(base64.b64decode(token).decode("utf-8"))
        except Exception:  # noqa: BLE001 — a malformed token is operator error
            flash("The preview could not be read. Upload the file again.", "error")
            return _redirect_to_classification("what")

        parsed = what_catalog_import.ParsedWhatCatalog(sheet_name=payload.get("sheet_name"))
        for row in payload.get("rows", []):
            parsed.rows.append(what_catalog_import.ParsedWhatRow(
                source_row_number=row["source_row_number"],
                statement_type=row["statement_type"],
                code=row["code"],
                code_is_generated=row["code_is_generated"],
                name=row["name"],
                parent_code=row["parent_code"],
                level=row["level"],
                row_type=row["row_type"],
                source_label=row["source_label"],
            ))

        with SessionFactory() as db:
            try:
                outcome = what_catalog_import.apply_import(
                    db, parsed,
                    source_note=f"Confirmed from the preview of {payload.get('file_name')!r}.",
                )
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("what")

        message = (
            f"What catalog imported: {len(outcome.created)} created, "
            f"{len(outcome.unchanged)} already present and unchanged, "
            f"{outcome.skipped_totals} total row(s) and {outcome.skipped_headings} heading(s) "
            f"skipped, {outcome.rejected} row(s) rejected."
        )
        flash(message, "info")
        for conflict in outcome.conflicts:
            flash(f"Conflict, not overwritten — {conflict}", "error")
        return _redirect_to_classification("what")

    # --- Receiver approval --------------------------------------------

    @app.route("/bank/classification/receivers/approve", methods=["POST"])
    @gate
    def bank_classification_receivers_approve():
        """Approve one or more receiver groups onto one Who.

        Atomic: `approve_candidates` raises before writing anything if the
        Who's chain is incomplete or a group is ambiguous, and the commit
        is all-or-nothing."""
        require_csrf()
        payee_keys = request.form.getlist("payee_key")
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                outcome = receiver_candidates.approve_candidates(
                    db,
                    payee_keys=payee_keys,
                    occurrence_id=request.form.get("occurrence_id", type=int) or None,
                    new_occurrence_name=(request.form.get("new_occurrence_name") or "").strip() or None,
                    occurrence_type_id=request.form.get("occurrence_type_id", type=int) or None,
                    default_transaction_reason_id=request.form.get(
                        "default_transaction_reason_id", type=int,
                    ) or None,
                    confirmed_by_account_id=account.id,
                    learn_description=bool(request.form.get("learn_description")),
                )
                db.commit()
                flash(
                    f"{outcome.transactions_classified} transaction(s) classified as "
                    f"{outcome.occurrence_name!r} across {len(outcome.payees)} receiver group(s). "
                    + (
                        f"{outcome.transactions_skipped_human} left untouched because a human had "
                        "already decided them. " if outcome.transactions_skipped_human else ""
                    )
                    + (
                        f"{len(outcome.rules_created)} exact-match rule(s) recorded for future "
                        "imports." if outcome.rules_created else
                        "No recognition rule was recorded."
                    ),
                    "info",
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _redirect_to_classification("receivers")

    def _redirect_to_classification(section: str):
        return redirect(url_for("bank_classification") + f"#{section}")

    def _commit_or_flash(db, success_message: str, section: str):
        """The one place every Classification mutation ends, so no branch
        can forget to roll back or to say what happened."""
        try:
            db.commit()
            flash(success_message, "info")
        except Exception as exc:  # noqa: BLE001 — surfaced verbatim, never swallowed
            db.rollback()
            flash(str(exc), "error")
        return _redirect_to_classification(section)

    # --- A. WHAT -----------------------------------------------------

    @app.route("/bank/classification/what/new", methods=["POST"])
    @gate
    def bank_classification_what_new():
        require_csrf()
        with SessionFactory() as db:
            try:
                classification_service.create_accounting_classification(
                    db,
                    code=request.form.get("code", ""),
                    name=request.form.get("name", ""),
                    statement_type=request.form.get("statement_type"),
                    parent_id=request.form.get("parent_id", type=int) or None,
                    description=request.form.get("description"),
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("what")
            return _commit_or_flash(db, "What created.", "what")

    @app.route("/bank/classification/what/<int:classification_id>/edit", methods=["POST"])
    @gate
    def bank_classification_what_edit(classification_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                classification_service.update_accounting_classification(
                    db,
                    classification_id=classification_id,
                    name=request.form.get("name", ""),
                    statement_type=request.form.get("statement_type"),
                    parent_id=request.form.get("parent_id", type=int) or None,
                    description=request.form.get("description"),
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("what")
            return _commit_or_flash(db, "What updated.", "what")

    @app.route("/bank/classification/what/<int:classification_id>/status", methods=["POST"])
    @gate
    def bank_classification_what_status(classification_id: int):
        """Activate/deactivate. There is deliberately no delete route: a
        What referenced by a Why or by a historical decision must stay
        readable forever."""
        require_csrf()
        active = request.form.get("active") == "1"
        with SessionFactory() as db:
            try:
                classification_service.set_accounting_classification_active(
                    db, classification_id=classification_id, active=active,
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("what")
            return _commit_or_flash(
                db, "What activated." if active else "What deactivated.", "what",
            )

    # --- B. WHY -> WHAT ----------------------------------------------

    @app.route("/bank/classification/why/new", methods=["POST"])
    @gate
    def bank_classification_why_new():
        require_csrf()
        with SessionFactory() as db:
            try:
                classification_service.create_transaction_reason(
                    db,
                    code=request.form.get("code", ""),
                    name=request.form.get("name", ""),
                    accounting_classification_id=request.form.get(
                        "accounting_classification_id", type=int,
                    ) or None,
                    description=request.form.get("description"),
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("why")
            return _commit_or_flash(db, "Why created.", "why")

    @app.route("/bank/classification/why/<int:transaction_reason_id>/edit", methods=["POST"])
    @gate
    def bank_classification_why_edit(transaction_reason_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                classification_service.update_transaction_reason(
                    db,
                    transaction_reason_id=transaction_reason_id,
                    name=request.form.get("name", ""),
                    accounting_classification_id=request.form.get(
                        "accounting_classification_id", type=int,
                    ) or None,
                    description=request.form.get("description"),
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("why")
            return _commit_or_flash(
                db,
                "Why updated. Future classifications use the new What; confirmed transactions keep "
                "their own snapshot until an explicit Reclassify.",
                "why",
            )

    @app.route("/bank/classification/why/<int:transaction_reason_id>/status", methods=["POST"])
    @gate
    def bank_classification_why_status(transaction_reason_id: int):
        require_csrf()
        status = "ACTIVE" if request.form.get("active") == "1" else "INACTIVE"
        with SessionFactory() as db:
            try:
                classification_service.set_transaction_reason_status(
                    db, transaction_reason_id=transaction_reason_id, status=status,
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("why")
            return _commit_or_flash(db, f"Why set to {status}.", "why")

    # --- C. WHO -> WHY -> WHAT ---------------------------------------

    @app.route("/bank/classification/who/new", methods=["POST"])
    @gate
    def bank_classification_who_new():
        require_csrf()
        with SessionFactory() as db:
            try:
                classification_service.create_occurrence(
                    db,
                    canonical_name=request.form.get("canonical_name", ""),
                    occurrence_type_id=request.form.get("occurrence_type_id", type=int) or 0,
                    default_transaction_reason_id=request.form.get(
                        "default_transaction_reason_id", type=int,
                    ) or None,
                    optional_notes=request.form.get("optional_notes"),
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("who")
            return _commit_or_flash(db, "Who created.", "who")

    @app.route("/bank/classification/who/<int:occurrence_id>/edit", methods=["POST"])
    @gate
    def bank_classification_who_edit(occurrence_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                classification_service.update_occurrence(
                    db,
                    occurrence_id=occurrence_id,
                    canonical_name=request.form.get("canonical_name", ""),
                    occurrence_type_id=request.form.get("occurrence_type_id", type=int) or 0,
                    default_transaction_reason_id=request.form.get(
                        "default_transaction_reason_id", type=int,
                    ) or None,
                    optional_notes=request.form.get("optional_notes"),
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("who")
            return _commit_or_flash(
                db,
                "Who updated. Future classifications use the new Why; confirmed transactions keep "
                "their own snapshot until an explicit Reclassify.",
                "who",
            )

    @app.route("/bank/classification/who/<int:occurrence_id>/status", methods=["POST"])
    @gate
    def bank_classification_who_status(occurrence_id: int):
        """Activate/deactivate. A Who already used by a decision or a
        recognition rule is never physically deleted."""
        require_csrf()
        status = "ACTIVE" if request.form.get("active") == "1" else "INACTIVE"
        with SessionFactory() as db:
            try:
                classification_service.set_occurrence_status(
                    db, occurrence_id=occurrence_id, status=status,
                )
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _redirect_to_classification("who")
            return _commit_or_flash(db, f"Who set to {status}.", "who")

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
