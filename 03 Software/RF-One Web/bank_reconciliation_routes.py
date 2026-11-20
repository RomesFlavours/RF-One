"""RF-One Web — Bank Reconciliation (BANK_RECONCILIATION_001).

`/bank/reconciliation` is the approved Reconciliation page on real data:
one row per bank transaction of the selected month, one WHO modal for the
whole page. Every rule lives in
`rfone_data_store.bank_reconciliation.row_reconciliation`; this module
reads forms, calls one function, commits or rolls back, flashes a plain
sentence and returns to the SAME row of the SAME month. The month and the
row come from the transaction itself, never from the request, so no
redirect target can be supplied from outside.
"""

from __future__ import annotations

import calendar
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

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


def _ints(name: str) -> list[int]:
    values = []
    for raw in request.form.getlist(name):
        raw = raw.strip()
        if raw:
            try:
                values.append(int(raw))
            except ValueError:
                raise ValueError(f"{name} must hold numbers, got {raw!r}.") from None
    return values


def register_bank_reconciliation_routes(
    app, *, gate, SessionFactory, load_current_account, require_csrf, default_month,
):
    def _account_id(db) -> int:
        account = load_current_account(db)
        if account is None:
            abort(403)
        return account.id

    def _back_to_row(db, transaction_id: int):
        transaction = db.get(m.FinancialTransaction, transaction_id)
        on_date = (transaction.posting_date or transaction.transaction_date) if transaction else None
        if on_date is None:
            return redirect(url_for("bank_reconciliation"))
        return redirect(url_for("bank_reconciliation", year=on_date.year, month=on_date.month,
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
        """The month's transactions, one reconcilable row each."""
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if year is None or month is None or not (1 <= month <= 12) or not (2000 <= year <= 2100):
            year, month = default_month()
        previous = (year - 1, 12) if month == 1 else (year, month - 1)
        following = (year + 1, 1) if month == 12 else (year, month + 1)
        with SessionFactory() as db:
            view = recon_service.month_view(db, year=year, month=month)
        return render_template(
            "bank_reconciliation.html", view=view,
            period_label=f"{calendar.month_name[month]} {year}",
            previous_month=previous, next_month=following,
        )

    @app.route("/bank/reconciliation/<int:transaction_id>/who", methods=["POST"])
    @gate
    def bank_reconciliation_who(transaction_id: int):
        """Confirm WHO (and the chosen WHY) for one transaction — optionally
        creating the WHO first through the Configuration service."""
        def action(db):
            new_who = None
            if request.form.get("new_who") == "1":
                new_who = recon_service.NewWho(
                    name=request.form.get("new_name", ""), reason_ids=_ints("new_why_ids"),
                    default_reason_id=_int("new_default_why_id"),
                    reporting_entity_ids=_ints("new_entity_ids"),
                )
            recon_service.record_who(
                db, transaction_id=transaction_id, occurrence_id=_int("occurrence_id"),
                reason_id=_int("why_id"), account_id=_account_id(db), new_who=new_who,
            )
        return _apply(transaction_id, action, "WHO recorded. Confirm the row when it is complete.")

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
