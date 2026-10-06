"""RF-One Web — General (structural) WHO rules (BANK_GENERAL_RULES_001).

Bank > Classification shows GENERAL RULES above WHO CLASSIFICATION. These
routes only call `general_rules`:

  POST /bank/general-rules/save               create or edit (future imports only)
  POST /bank/general-rules/<id>/status        activate / deactivate
  POST /bank/general-rules/<id>/preview       what Apply would do — nothing written
  POST /bank/general-rules/<id>/apply         apply to EXISTING transactions

The Apply result is kept in the session once and shown by Classification.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

from flask import flash, redirect, request, session, url_for

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import general_rules

RESULT_SESSION_KEY = "bank_general_rule_result"


def pop_general_rule_result() -> dict | None:
    return session.pop(RESULT_SESSION_KEY, None)


def _back():
    return redirect(url_for("bank_classification") + "#general-rules")


def register_bank_general_rule_routes(app, *, gate, SessionFactory, load_current_account, require_csrf):

    @app.route("/bank/general-rules/save", methods=["POST"])
    @gate
    def bank_general_rule_save():
        require_csrf()
        raw_id = (request.form.get("rule_id") or "").strip()
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                rule = general_rules.save_rule(
                    db, rule_id=int(raw_id) if raw_id.isdigit() else None,
                    name=request.form.get("name"), start_marker=request.form.get("start_marker"),
                    end_marker=request.form.get("end_marker"), active=request.form.get("active") == "on",
                    account_id=account.id if account is not None else None,
                )
                db.commit()
                flash(f"General Rule {rule.name!r} saved. It applies to future imports; use "
                      "Apply to Existing Transactions to process what is already imported.", "success")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _back()

    @app.route("/bank/general-rules/<int:rule_id>/status", methods=["POST"])
    @gate
    def bank_general_rule_status(rule_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                rule = general_rules.set_active(db, rule_id=rule_id, active=request.form.get("active") == "1")
                db.commit()
                flash(f"General Rule {rule.name!r} is now {'active' if rule.status == 'ACTIVE' else 'disabled'}.",
                      "success")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _back()

    @app.route("/bank/general-rules/<int:rule_id>/preview", methods=["POST"])
    @gate
    def bank_general_rule_preview(rule_id: int):
        """What Apply would do now — resolved, to assign, unknown — nothing written."""
        require_csrf()
        with SessionFactory() as db:
            rule = db.get(m.BankGeneralRule, rule_id)
            if rule is None:
                flash("That General Rule does not exist.", "error")
            else:
                session[RESULT_SESSION_KEY] = general_rules.preview(db, rule).as_dict()
        return _back()

    @app.route("/bank/general-rules/<int:rule_id>/apply", methods=["POST"])
    @gate
    def bank_general_rule_apply(rule_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                result = general_rules.apply_rule(db, rule_id=rule_id,
                                                  account_id=account.id if account is not None else None)
                db.commit()
                session[RESULT_SESSION_KEY] = result.as_dict()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _back()
