"""RF-One Web — the simple WHO Rule (BANK_SIMPLE_WHO_RULE_001).

One modal, shared by Bank > Classification and Bank > Review Transactions,
and ONE action behind it: `POST /bank/who-rules/apply`, which calls
`who_rules.apply_who_rule` — the single service that saves the rule, the
possible WHY, applies the rule to existing transactions and merges the WHO
fragments it proves. Neither page has rule logic of its own.

The two GET endpoints only feed the modal: the creatable WHO combo (matching
active WHO, the WHO a typed name already is, similar names, and whether
"Create" may be offered), and what a chosen WHO already has (its possible
WHY and rules). A new WHO is never created by these GETs — only by Apply,
in the same transaction as its rule.

Apply answers JSON to the modal's own request (so a refusal is shown inside
the modal, next to the sentence the operator wrote) and redirects for a
plain form post. The result is kept in the session once and shown by the
page the operator returns to; the return target must be a Bank page.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

from flask import jsonify, redirect, request, session, url_for

from rfone_data_store.bank_reconciliation import who_rules

RESULT_SESSION_KEY = "bank_who_rule_result"
MANUAL_ONLY_SESSION_KEY = "bank_who_manual_only_result"


def pop_rule_result() -> dict | None:
    """The last Apply's result, shown once by whichever Bank page follows."""
    return session.pop(RESULT_SESSION_KEY, None)


def pop_manual_only_result() -> dict | None:
    """The last Manual Only change — or the conflict waiting for the
    person's choice — shown once by Classification."""
    return session.pop(MANUAL_ONLY_SESSION_KEY, None)


def _safe_return(target: str | None) -> str:
    target = (target or "").strip()
    if target.startswith("/bank/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("bank_classification")


def _ints(name: str) -> list[int]:
    values = []
    for raw in request.form.getlist(name):
        raw = raw.strip()
        if raw:
            try:
                values.append(int(raw))
            except ValueError:
                raise ValueError("The selected WHY could not be read; reload the page and try again.") from None
    return values


def register_bank_who_rule_routes(app, *, gate, SessionFactory, load_current_account, require_csrf):

    @app.route("/bank/who-rules/apply", methods=["POST"])
    @gate
    def bank_who_rule_apply():
        require_csrf()
        wants_json = request.headers.get("X-Requested-With") == "fetch"
        back = _safe_return(request.form.get("return_to"))
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                result = who_rules.apply_who_rule(
                    db,
                    occurrence_id=request.form.get("occurrence_id", type=int),
                    instruction=request.form.get("instruction"),
                    transaction_reason_ids=_ints("transaction_reason_id"),
                    applied_by_account_id=account.id if account is not None else None,
                    created_from_transaction_id=request.form.get("transaction_id", type=int),
                    # A WHO to create in this same Apply, when no existing
                    # WHO was chosen (the modal's "Create" option).
                    new_who_name=request.form.get("new_who_name"),
                )
                db.commit()
            except ValueError as exc:
                db.rollback()
                if wants_json:
                    return jsonify({"ok": False, "error": str(exc)}), 400
                session[RESULT_SESSION_KEY] = {"error": str(exc)}
                return redirect(back)
        session[RESULT_SESSION_KEY] = result.as_dict()
        if wants_json:
            return jsonify({"ok": True, "redirect": back})
        return redirect(back)

    # Manual Only (BANK_WHO_MANUAL_ONLY_001): one plain form post per row.
    # A WHO that still has an active WHO Rule is not marked: the page shows
    # the explicit choice "Disable existing WHO Rule and mark Manual Only"
    # or Cancel, and only that second post (disable_rules=1) changes both.
    @app.route("/bank/who-rules/manual-only", methods=["POST"])
    @gate
    def bank_who_manual_only():
        require_csrf()
        back = _safe_return(request.form.get("return_to"))
        # From the row button's formaction (query) or a plain form field.
        manual_only = request.values.get("manual_only") == "1"
        with SessionFactory() as db:
            try:
                result = who_rules.set_manual_only(
                    db, occurrence_id=request.form.get("occurrence_id", type=int), manual_only=manual_only,
                    disable_rules=request.form.get("disable_rules") == "1",
                )
                db.commit()
            except who_rules.ManualOnlyConflict as conflict:
                db.rollback()
                session[MANUAL_ONLY_SESSION_KEY] = {"conflict": True, "who_id": conflict.who_id,
                                                    "who_name": conflict.who_name, "rules": conflict.rules}
                return redirect(back)
            except ValueError as exc:
                db.rollback()
                session[MANUAL_ONLY_SESSION_KEY] = {"error": str(exc)}
                return redirect(back)
        session[MANUAL_ONLY_SESSION_KEY] = result
        return redirect(back)

    @app.route("/bank/who-rules/who-options")
    @gate
    def bank_who_rule_who_options():
        with SessionFactory() as db:
            return jsonify(who_rules.who_options(db, search=request.args.get("q") or ""))

    @app.route("/bank/who-rules/who/<int:occurrence_id>")
    @gate
    def bank_who_rule_who(occurrence_id: int):
        with SessionFactory() as db:
            summary = who_rules.who_summary(db, occurrence_id)
            if summary is None:
                return jsonify({"error": "This WHO does not exist."}), 404
            return jsonify(summary)
