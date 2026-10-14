"""RF-One Web — Bank Configuration (BANK_CONFIGURATION_001).

One page, `/bank/configuration`, in the approved order: WHAT, WHY, WHO,
Sources (a link only: every Source, including a card's settlement account and
cardholder, is maintained on `/bank/sources` — BANK_FINAL_RELEASE_BLOCKERS_002),
then Support (entities; Balance Sheet destinations, read-only). File
recognition rules and deduplication live on Source, the completeness control
in Check Sources — Support only links there (BANK_FINAL_CLEANUP_001). Each modal on the page posts to one of the
routes below. Every route:

* is behind the BANK gate and `require_csrf()`;
* reads the form, calls ONE function of
  `rfone_data_store.bank_reconciliation.configuration` — where every
  business rule lives — and commits only when that call succeeds;
* flashes a plain sentence either way;
* redirects to `/bank/configuration`, at the section the change belongs
  to. The section is fixed by the route itself, never read from the
  request, so no redirect target can be supplied from outside.

Registered from `bank_routes.register_bank_routes`, which passes in its
own collaborators; this module never imports `app.py`.
"""

from __future__ import annotations


from flask import flash, jsonify, redirect, render_template, request, url_for

from rfone_data_store.bank_reconciliation import configuration as config_service
from rfone_data_store.bank_reconciliation import who_merge


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
        if not raw:
            continue
        try:
            values.append(int(raw))
        except ValueError:
            raise ValueError(f"{name} must hold numbers, got {raw!r}.") from None
    return values


def _flag(name: str) -> bool:
    return request.form.get(name) == "1"


def _text(name: str) -> str:
    return (request.form.get(name) or "").strip()


def register_bank_configuration_routes(
    app, *, gate, SessionFactory, load_current_account, require_csrf,
):
    def _back(section: str):
        return redirect(url_for("bank_configuration", _anchor=section))

    def _apply(section: str, action, success):
        """Run one configuration change in its own transaction. `action`
        receives the session and returns what `success` turns into the
        feedback sentence(s)."""
        require_csrf()
        # BANK_WHO_EDIT_SAVE_001 — a modal saving with fetch gets JSON: a
        # refusal is shown INSIDE the modal (values kept), never only as a
        # message on a reloaded page.
        wants_json = request.headers.get("X-Requested-With") == "fetch"
        with SessionFactory() as db:
            try:
                result = action(db)
                messages = success(result)
                db.commit()
            except ValueError as exc:
                db.rollback()
                if wants_json:
                    return jsonify({"ok": False, "error": str(exc)}), 400
                flash(str(exc), "error")
                return _back(section)
        for message in ([messages] if isinstance(messages, str) else messages):
            flash(message, "info")
        if wants_json:
            return jsonify({"ok": True, "redirect": url_for("bank_configuration", _anchor=section)})
        return _back(section)

    @app.route("/bank/configuration")
    @gate
    def bank_configuration():
        """The single Bank Configuration page."""
        with SessionFactory() as db:
            view = config_service.configuration_view(db)
        return render_template("bank_configuration.html", config=view)

    # ------------------------------------------------------------------ WHAT

    @app.route("/bank/configuration/what", methods=["POST"])
    @gate
    def bank_configuration_what_new():
        return _apply("cp-what", lambda db: config_service.create_what(
            db, code=_text("code"), name=_text("name"), group_id=_int("group_id"),
            active=_flag("active"),
        ), lambda what: f"WHAT {what.code} — {what.name} created.")

    @app.route("/bank/configuration/what/<int:classification_id>", methods=["POST"])
    @gate
    def bank_configuration_what_edit(classification_id: int):
        return _apply("cp-what", lambda db: config_service.update_what(
            db, classification_id=classification_id, name=_text("name"),
            group_id=_int("group_id"), active=_flag("active"),
        ), lambda what: f"WHAT {what.code} — {what.name} saved.")

    # ------------------------------------------------------------------- WHY

    @app.route("/bank/configuration/why", methods=["POST"])
    @gate
    def bank_configuration_why_new():
        return _apply("cp-why", lambda db: config_service.create_why(
            db, name=_text("name"), description=_text("description"),
            what_id=_int("what_id"), active=_flag("active"),
        ), lambda why: f"WHY {why.name!r} created (code {why.code}).")

    @app.route("/bank/configuration/why/<int:transaction_reason_id>", methods=["POST"])
    @gate
    def bank_configuration_why_edit(transaction_reason_id: int):
        return _apply("cp-why", lambda db: config_service.update_why(
            db, transaction_reason_id=transaction_reason_id, name=_text("name"),
            description=_text("description"), what_id=_int("what_id"), active=_flag("active"),
        ), lambda why: f"WHY {why.name!r} saved.")

    # ------------------------------------------------------------------- WHO

    def _save_who(occurrence_id):
        return _apply("cp-who", lambda db: config_service.save_who(
            db, occurrence_id=occurrence_id, name=_text("name"), active=_flag("active"),
            reason_ids=_ints("why_ids"), default_reason_id=_int("default_why_id"),
            reporting_entity_ids=_ints("entity_ids"),
        ), lambda who: f"WHO {who.canonical_name!r} saved.")

    # BANK_WHO_MERGE_001 — merge two WHO: a preview (writes nothing), then
    # the merge itself, one database transaction, back to the WHO section.
    @app.route("/bank/configuration/who/merge/preview", methods=["POST"])
    @gate
    def bank_configuration_who_merge_preview():
        require_csrf()
        with SessionFactory() as db:
            try:
                return jsonify(who_merge.preview(db, keep_id=_int("keep_id"), absorb_id=_int("absorb_id")))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

    @app.route("/bank/configuration/who/merge", methods=["POST"])
    @gate
    def bank_configuration_who_merge():

        def action(db):
            account = load_current_account(db)
            return who_merge.merge(
                db, keep_id=_int("keep_id"), absorb_id=_int("absorb_id"), default_reason_id=_int("default_why"),
                account_id=account.id if account is not None else None)

        def success(result):
            moved = result.moved
            return (f"WHO {result.absorb_name!r} merged into {result.keep_name!r}: "
                    f"{moved.get('decisions', 0)} decision(s), "
                    f"{moved.get('aliases', 0)} alias(es), {moved.get('possible_why', 0)} possible WHY moved"
                    f". {result.absorb_name!r} is now inactive and an alias of {result.keep_name!r}.")

        return _apply("cp-who", action, success)

    @app.route("/bank/configuration/who", methods=["POST"])
    @gate
    def bank_configuration_who_new():
        return _save_who(None)

    @app.route("/bank/configuration/who/<int:occurrence_id>", methods=["POST"])
    @gate
    def bank_configuration_who_edit(occurrence_id: int):
        return _save_who(occurrence_id)

    # Accounts & Cards are no longer edited here (BANK_FINAL_RELEASE_BLOCKERS_002):
    # every Source is maintained on the Source page (`/bank/sources`).

    # --------------------------------------------------------------- Support

    @app.route("/bank/configuration/entity", methods=["POST"])
    @gate
    def bank_configuration_entity_new():
        return _apply("cp-entities", lambda db: config_service.create_entity(
            db, name=_text("name"), legal_name=_text("legal_name"), active=_flag("active"),
        ), lambda entity: f"Entity {entity.name!r} created.")

    @app.route("/bank/configuration/entity/<int:reporting_entity_id>", methods=["POST"])
    @gate
    def bank_configuration_entity_edit(reporting_entity_id: int):
        return _apply("cp-entities", lambda db: config_service.update_entity(
            db, reporting_entity_id=reporting_entity_id, name=_text("name"),
            legal_name=_text("legal_name"), active=_flag("active"),
        ), lambda entity: f"Entity {entity.name!r} saved.")

