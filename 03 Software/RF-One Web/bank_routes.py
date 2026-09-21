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

import calendar
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import classification as classification_service
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
            )

    # -----------------------------------------------------------------
    # Payment Instrument configuration — create and edit.
    # -----------------------------------------------------------------

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

            return render_template(
                "bank_instrument_edit.html",
                instrument=instrument,
                legal_entities=_active_legal_entities(db),
                instruments=[i for i in _instruments(db) if i.id != instrument_id],
                export_warning=bank_service.instrument_export_warning(instrument),
                transaction_count=db.scalar(
                    select(func.count(m.FinancialTransaction.id))
                    .where(m.FinancialTransaction.payment_instrument_id == instrument_id)
                ) or 0,
            )

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

            return render_template(
                "bank_review.html", transactions=transactions, instruments=instruments,
                instruments_by_id=instruments_by_id, explanations_by_id=explanations_by_id,
                who_options=who_options,
                resolved_decision_statuses=recognition.RESOLVED_DECISION_STATUSES,
                counterpart_by_transaction_id=counterpart_by_transaction_id,
                match_candidates_by_transaction_id=match_candidates_by_transaction_id,
                reassignments_by_transaction_id=reassignments_by_transaction_id,
                filter_year=year, filter_month=month,
                filter_payment_instrument_id=payment_instrument_id, filter_status=status,
                filter_batch_id=batch_id, filter_batch=filter_batch,
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
                db.commit()
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
            whys = classification_service.list_transaction_reasons(db, search=why_search)
            whos = classification_service.list_occurrences(db, search=who_search)

            # Assignable options are the COMPLETE ones only — the UI never
            # offers a choice the service layer would then refuse.
            assignable_whats = [w for w in classification_service.list_accounting_classifications(db)
                                if w.active and w.statement_type is not None]
            assignable_whys = [r for r in classification_service.list_transaction_reasons(db)
                               if r.status == "ACTIVE" and r.accounting_classification_id is not None]

            whats_by_id = {
                w.id: w for w in classification_service.list_accounting_classifications(db)
            }
            whys_by_id = {r.id: r for r in classification_service.list_transaction_reasons(db)}
            types_by_id = {t.id: t for t in classification_service.list_occurrence_types(db)}

            return render_template(
                "bank_classification.html",
                whats=whats, whys=whys, whos=whos,
                whats_by_id=whats_by_id, whys_by_id=whys_by_id, types_by_id=types_by_id,
                assignable_whats=assignable_whats, assignable_whys=assignable_whys,
                occurrence_types=classification_service.list_occurrence_types(db),
                chains=classification_service.resolve_chains(db, whos),
                usage={w.id: classification_service.accounting_classification_usage(db, w.id) for w in whats},
                statement_type_labels=classification_service.STATEMENT_TYPE_LABELS,
                what_search=what_search, why_search=why_search, who_search=who_search,
            )

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
