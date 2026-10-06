"""RF-One Web — Bank Reconciliation row actions (BANK_RECONCILIATION_001).

The reconciliation rows are Review > Reconciled (BANK_TWO_STAGE_REVIEW_001):
the row editor posts here to Confirm, Standard, Reopen and Save. The former
standalone `/bank/reconciliation` month page and its own WHO modal are
retired (BANK_FINAL_CLEANUP_001): `/bank/reconciliation` now redirects to
Review > Reconciled for the same month, and the WHO and WHY of a transaction
are chosen only in the Select WHO / WHY popup. Every rule lives in
`rfone_data_store.bank_reconciliation.row_reconciliation`; this module
reads forms, calls one function, commits or rolls back, flashes a plain
sentence and returns to the SAME row of the SAME month. The month and the
row come from the transaction itself, never from the request, so no
redirect target can be supplied from outside.
"""

from __future__ import annotations

from flask import abort, flash, redirect, request, url_for

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import row_reconciliation as recon_service


def _int(name: str) -> int | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}.") from None


def register_bank_reconciliation_routes(
    app, *, gate, SessionFactory, load_current_account, require_csrf,
):
    def _account_id(db) -> int:
        account = load_current_account(db)
        if account is None:
            abort(403)
        return account.id

    def _back_to_row(db, transaction_id: int):
        # BANK_TWO_STAGE_REVIEW_001 — a row acted on from Review > Reconciled
        # returns there, with its filters; only a Review address is accepted.
        back = (request.form.get("return_to") or "").strip()
        if back.startswith("/bank/review") and not back.startswith("//") and "\\" not in back:
            return redirect(f"{back}#t-{transaction_id}")
        transaction = db.get(m.FinancialTransaction, transaction_id)
        on_date = (transaction.posting_date or transaction.transaction_date) if transaction else None
        if on_date is None:
            return redirect(url_for("bank_review", view="reconciled"))
        return redirect(url_for("bank_review", view="reconciled", year=on_date.year, month=on_date.month,
                                _anchor=f"t-{transaction_id}"))

    def _apply(transaction_id: int, action, message: str):
        require_csrf()
        with SessionFactory() as db:
            try:
                action(db)
                db.commit()
                flash(message, "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
            return _back_to_row(db, transaction_id)

    @app.route("/bank/reconciliation")
    @gate
    def bank_reconciliation():
        """Retired standalone page: kept as a redirect for bookmarks, to
        Review > Reconciled for the month asked for."""
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if year is None or month is None or not (1 <= month <= 12) or not (2000 <= year <= 2100):
            return redirect(url_for("bank_review", view="reconciled"))
        return redirect(url_for("bank_review", view="reconciled", year=year, month=month))

    @app.route("/bank/reconciliation/<int:transaction_id>/confirm", methods=["POST"])
    @gate
    def bank_reconciliation_confirm(transaction_id: int):
        return _apply(transaction_id, lambda db: recon_service.confirm_row(
            db, transaction_id=transaction_id, reporting_entity_id=_int("for_whom_id"),
            account_id=_account_id(db),
        ), "Transaction confirmed.")

    @app.route("/bank/reconciliation/<int:transaction_id>/standard", methods=["POST"])
    @gate
    def bank_reconciliation_standard(transaction_id: int):
        """Compact-row Set as Standard: confirm this row and approve its
        current result as a Standard for future matching imports."""
        return _apply(transaction_id, lambda db: recon_service.set_as_standard(
            db, transaction_id=transaction_id, reporting_entity_id=_int("for_whom_id"),
            account_id=_account_id(db),
        ), "Transaction confirmed and set as Standard: future matching transactions will be Automatic.")

    @app.route("/bank/reconciliation/<int:transaction_id>/save", methods=["POST"])
    @gate
    def bank_reconciliation_save(transaction_id: int):
        """The expanded editor: Save — keep Standard unchanged (mode=keep) or
        Save as New Standard (mode=standard)."""
        mode = request.form.get("mode")
        if mode not in ("keep", "standard"):
            mode = "keep"
        message = ("Transaction saved and a Standard approved for this variant." if mode == "standard"
                   else "Transaction saved. Every Standard is unchanged.")
        return _apply(transaction_id, lambda db: recon_service.save_row(
            db, transaction_id=transaction_id, occurrence_id=_int("occurrence_id"),
            reason_id=_int("why_id"), destination_id=_int("what_id"),
            reporting_entity_id=_int("for_whom_id"), account_id=_account_id(db),
            as_standard=mode == "standard",
        ), message)

    @app.route("/bank/reconciliation/<int:transaction_id>/reopen", methods=["POST"])
    @gate
    def bank_reconciliation_reopen(transaction_id: int):
        return _apply(transaction_id, lambda db: recon_service.reopen_row(
            db, transaction_id=transaction_id,
        ), "Transaction reopened. It needs a new confirmation.")
