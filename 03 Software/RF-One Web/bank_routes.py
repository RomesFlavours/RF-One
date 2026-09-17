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

Every route calls straight into `rfone_data_store.bank_reconciliation`
(`service`/`export`/`parsers`) — no business logic is duplicated here.
Registered from `app.py` via `register_bank_routes(app, ...)`, mirroring
`compensation_routes.py`'s "pass in collaborators explicitly" convention:
this module never imports `app.py` itself."""

from __future__ import annotations

import calendar
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import export as export_service
from rfone_data_store.bank_reconciliation import matching as matching_service
from rfone_data_store.bank_reconciliation import parsers
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import service as bank_service


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

    @app.route("/bank")
    @gate
    def bank_home():
        with SessionFactory() as db:
            batches = db.scalars(
                select(m.BankImportBatch).order_by(m.BankImportBatch.uploaded_at.desc())
            ).all()
            instruments = db.scalars(
                select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)
            ).all()
            legal_entities = db.scalars(
                select(m.LegalEntity).where(m.LegalEntity.status == "ACTIVE")
                .order_by(m.LegalEntity.legal_name)
            ).all()
            instruments_by_id = {i.id: i for i in instruments}
            return render_template(
                "bank_home.html", batches=batches, instruments=instruments,
                instruments_by_id=instruments_by_id, legal_entities=legal_entities,
            )

    @app.route("/bank/instruments/new", methods=["POST"])
    @gate
    def bank_instrument_new():
        require_csrf()
        institution = (request.form.get("institution") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        instrument_type = request.form.get("instrument_type")
        last_four = (request.form.get("last_four") or "").strip() or None
        external_account_identifier = (request.form.get("external_account_identifier") or "").strip() or None
        legal_entity_id = request.form.get("legal_entity_id", type=int)

        if not institution or not display_name or instrument_type not in ("BANK_ACCOUNT", "CREDIT_CARD"):
            flash("Institution, display name, and instrument type are required.", "error")
            return redirect(url_for("bank_home"))

        with SessionFactory() as db:
            instrument = m.PaymentInstrument(
                institution=institution, display_name=display_name, instrument_type=instrument_type,
                last_four=last_four, external_account_identifier=external_account_identifier,
                legal_entity_id=legal_entity_id or None,
            )
            db.add(instrument)
            db.commit()
            flash(f"Payment Instrument {display_name!r} created.", "info")
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
                    flash(
                        f"{uploaded.filename}: identical file already imported previously "
                        f"(batch #{result.batch.id}) — no changes made.",
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

        return redirect(url_for("bank_home"))

    @app.route("/bank/batches/<int:batch_id>/resolve-instrument", methods=["POST"])
    @gate
    def bank_batch_resolve_instrument(batch_id: int):
        require_csrf()
        payment_instrument_id = request.form.get("payment_instrument_id", type=int)
        if not payment_instrument_id:
            flash("Select a Payment Instrument to resolve this batch.", "error")
            return redirect(url_for("bank_home"))
        with SessionFactory() as db:
            try:
                bank_service.resolve_batch_instrument(
                    db, batch_id=batch_id, payment_instrument_id=payment_instrument_id,
                )
                db.commit()
                flash("Batch instrument resolved and normalized.", "info")
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
            occurrences = db.scalars(
                select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE")
                .order_by(m.BankOccurrence.canonical_name)
            ).all()
            reasons = db.scalars(
                select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
                .order_by(m.BankTransactionReason.name)
            ).all()

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

            return render_template(
                "bank_review.html", transactions=transactions, instruments=instruments,
                instruments_by_id=instruments_by_id, explanations_by_id=explanations_by_id,
                occurrences=occurrences, reasons=reasons,
                resolved_decision_statuses=recognition.RESOLVED_DECISION_STATUSES,
                counterpart_by_transaction_id=counterpart_by_transaction_id,
                match_candidates_by_transaction_id=match_candidates_by_transaction_id,
                filter_year=year, filter_month=month,
                filter_payment_instrument_id=payment_instrument_id, filter_status=status,
            )

    @app.route("/bank/transactions/<int:transaction_id>/duplicate-decision", methods=["POST"])
    @gate
    def bank_transaction_duplicate_decision(transaction_id: int):
        require_csrf()
        decision = request.form.get("decision", "")
        with SessionFactory() as db:
            try:
                bank_service.resolve_duplicate_decision(db, transaction_id=transaction_id, decision=decision)
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(request.referrer or url_for("bank_review"))

    @app.route("/bank/transactions/<int:transaction_id>/recognition-decision", methods=["POST"])
    @gate
    def bank_transaction_recognition_decision(transaction_id: int):
        require_csrf()
        occurrence_id = request.form.get("occurrence_id", type=int)
        transaction_reason_id = request.form.get("transaction_reason_id", type=int)
        reuse_for_future = bool(request.form.get("reuse_for_future"))
        if not occurrence_id or not transaction_reason_id:
            flash("Select both an Occurrence (Who) and a Reason (Why).", "error")
            return redirect(request.referrer or url_for("bank_review"))
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                bank_service.record_recognition_decision(
                    db, transaction_id=transaction_id, occurrence_id=occurrence_id,
                    transaction_reason_id=transaction_reason_id,
                    confirmed_by_account_id=account.id, reuse_for_future=reuse_for_future,
                )
                db.commit()
                flash("Reconciliation decision recorded.", "info")
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
