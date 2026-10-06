"""RF-One Web — the "Select WHO / WHY" popup (BANK_MANUAL_WHO_WHY_001).

ONE popup, shared by Review > To Reconcile and Review > Reconciled, and ONE
writing action behind it: `POST /bank/transactions/<id>/who-why`, which calls
`manual_reconciliation.reconcile_who_why` — WHO + WHY for this transaction,
a HUMAN decision, optionally creating the WHY through the Bank Configuration
service. No rule is created here: the Rule button is the only way to teach
recognition.

The GET endpoints only feed the popup, so the page never ships the WHO x WHY
matrix: the WHO list and the grouped WHY catalog once per page (fetched on
first open), the WHY already associated with the ONE WHO chosen (to mark
them), and — when "Create New WHY" is pressed — the P&L WHAT list with the
names of the WHY that already exist.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

from flask import flash, jsonify, redirect, request, url_for

from rfone_data_store.bank_reconciliation import manual_reconciliation


def _safe_return(target: str | None) -> str:
    """Back to the Review tab the popup was opened on — only a Review address."""
    target = (target or "").strip()
    if target.startswith("/bank/review") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("bank_review")


def _int(name: str) -> int | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError("The selection could not be read; reload the page and try again.") from None


def register_bank_manual_reconciliation_routes(app, *, gate, SessionFactory, load_current_account, require_csrf):

    @app.route("/bank/manual-reconciliation/whos")
    @gate
    def bank_manual_reconciliation_whos():
        with SessionFactory() as db:
            return jsonify(manual_reconciliation.active_who_list(db))

    @app.route("/bank/manual-reconciliation/whos/<int:occurrence_id>/whys")
    @gate
    def bank_manual_reconciliation_whys(occurrence_id: int):
        with SessionFactory() as db:
            try:
                return jsonify(manual_reconciliation.whys_for_who(db, occurrence_id))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 404

    @app.route("/bank/manual-reconciliation/why-catalog")
    @gate
    def bank_manual_reconciliation_why_catalog():
        """The WHY GROUP and WHY columns: every navigation group and every
        active WHY, fetched once per page. The WHO's own WHY (above) only
        MARK entries of this catalog; they never limit it."""
        with SessionFactory() as db:
            return jsonify(manual_reconciliation.why_navigation_catalog(db))

    @app.route("/bank/manual-reconciliation/whats")
    @gate
    def bank_manual_reconciliation_whats():
        """For "Create New WHY": the P&L WHAT a new WHY may take, and the
        names of the WHY that already exist (suggested, so a purpose that
        exists is reused rather than created twice)."""
        with SessionFactory() as db:
            return jsonify({"whats": manual_reconciliation.what_options(db),
                            "whys": manual_reconciliation.catalog_whys(db)})

    # ---- "Create New WHY": ONE flow, used by Select WHO / WHY and by the
    # WHO Rule modal alike (the shared dialog `_bank_why_create_dialog.html`).

    @app.route("/bank/whys/create-options")
    @gate
    def bank_why_create_options():
        """WHY groups (alphabetical), P&L WHAT and existing WHY names — once
        per page, when "Create New WHY" is first pressed."""
        with SessionFactory() as db:
            return jsonify(manual_reconciliation.create_why_options(db))

    @app.route("/bank/whys/create", methods=["POST"])
    @gate
    def bank_why_create():
        """Create the WHY (or reuse the existing one of that name) and add it
        to the WHO, in one database transaction: committed whole or rolled
        back whole. Answers JSON for the dialog; never navigates."""
        require_csrf()
        with SessionFactory() as db:
            try:
                created = manual_reconciliation.create_why_for_who(
                    db, occurrence_id=_int("occurrence_id"),
                    new_why=manual_reconciliation.NewWhy(
                        name=(request.form.get("name") or "").strip(), what_id=_int("what_id"),
                        group_id=_int("group_id")),
                )
                reason = created.reason
                payload = {
                    "ok": True, "reused": created.reused, "associated": created.associated,
                    "why": {"id": reason.id, "name": reason.name, "group_id": reason.reason_group_id,
                            "group_name": reason.reason_group.name if reason.reason_group else None,
                            "what": reason.resolution_label, "code": reason.code},
                    "message": "Existing WHY found — reused." if created.reused else "WHY created.",
                }
                db.commit()
            except ValueError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception:
                db.rollback()
                raise
        return jsonify(payload)

    @app.route("/bank/transactions/<int:transaction_id>/who-why", methods=["POST"])
    @gate
    def bank_transaction_who_why(transaction_id: int):
        require_csrf()
        wants_json = request.headers.get("X-Requested-With") == "fetch"
        back = _safe_return(request.form.get("return_to"))
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                new_why = None
                if (request.form.get("new_why_name") or "").strip():
                    new_why = manual_reconciliation.NewWhy(
                        name=request.form.get("new_why_name", "").strip(), what_id=_int("new_why_what_id"),
                        group_id=_int("new_why_group_id"),
                    )
                manual_reconciliation.reconcile_who_why(
                    db, transaction_id=transaction_id, occurrence_id=_int("occurrence_id"),
                    reason_id=_int("transaction_reason_id"),
                    account_id=account.id if account is not None else None, new_why=new_why,
                )
                db.commit()
            except ValueError as exc:
                db.rollback()
                if wants_json:
                    return jsonify({"ok": False, "error": str(exc)}), 400
                flash(str(exc), "error")
                return redirect(back)
        flash("WHO and WHY recorded for this transaction. It is now under Reconciled.", "success")
        target = f"{back}#t-{transaction_id}" if "view=reconciled" in back else back
        if wants_json:
            return jsonify({"ok": True, "redirect": target})
        return redirect(target)
