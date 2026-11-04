"""RF-One Web — Bank Configuration (BANK_CONFIGURATION_001).

One page, `/bank/configuration`, in the approved order: WHAT, WHY, WHO,
Accounts & Cards, then Support. Each modal on the page posts to one of the
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

from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for

from rfone_data_store.bank_reconciliation import configuration as config_service
from rfone_data_store.bank_reconciliation import service as bank_service


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


def _date(name: str) -> date | None:
    raw = _text(name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{raw!r} is not a valid date (expected YYYY-MM-DD).") from None


def _rules() -> list[config_service.RuleInput]:
    ids = request.form.getlist("rule_id")
    patterns = request.form.getlist("rule_pattern")
    matches = request.form.getlist("rule_match")
    actives = request.form.getlist("rule_active")
    if not (len(ids) == len(patterns) == len(matches) == len(actives)):
        raise ValueError("The recognition rules were sent incompletely; reload the page and try again.")
    rules = []
    for rule_id, pattern, match, active in zip(ids, patterns, matches, actives):
        if not pattern.strip():
            continue  # an empty row the person added and left blank
        try:
            parsed_id = int(rule_id) if rule_id.strip() else None
        except ValueError:
            raise ValueError(f"Unknown recognition rule {rule_id!r}.") from None
        rules.append(config_service.RuleInput(
            rule_id=parsed_id, pattern=pattern, match=match, active=active == "1",
        ))
    return rules


def register_bank_configuration_routes(
    app, *, gate, SessionFactory, load_current_account, require_csrf,
):
    def _account_id(db) -> int:
        account = load_current_account(db)
        if account is None:
            abort(403)
        return account.id

    def _back(section: str):
        return redirect(url_for("bank_configuration", _anchor=section))

    def _apply(section: str, action, success):
        """Run one configuration change in its own transaction. `action`
        receives the session and returns what `success` turns into the
        feedback sentence(s)."""
        require_csrf()
        with SessionFactory() as db:
            try:
                result = action(db)
                messages = success(result)
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return _back(section)
        for message in ([messages] if isinstance(messages, str) else messages):
            flash(message, "info")
        return _back(section)

    @app.route("/bank/configuration")
    @gate
    def bank_configuration():
        """The single Bank Configuration page."""
        with SessionFactory() as db:
            view = config_service.configuration_view(db, today=date.today())
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
            reporting_entity_ids=_ints("entity_ids"), rules=_rules(),
        ), lambda who: f"WHO {who.canonical_name!r} saved.")

    @app.route("/bank/configuration/who", methods=["POST"])
    @gate
    def bank_configuration_who_new():
        return _save_who(None)

    @app.route("/bank/configuration/who/<int:occurrence_id>", methods=["POST"])
    @gate
    def bank_configuration_who_edit(occurrence_id: int):
        return _save_who(occurrence_id)

    # ------------------------------------------------------ Accounts & Cards

    @app.route("/bank/configuration/account", methods=["POST"])
    @gate
    def bank_configuration_account_new():
        return _apply("cp-accounts", lambda db: config_service.create_account(
            db, label=_text("label"), instrument_type=_text("instrument_type"),
            reporting_entity_id=_int("entity_id"), reference=_text("reference") or None,
            active=_flag("active"),
        ), lambda instrument: f"{instrument.display_name!r} created.")

    @app.route("/bank/configuration/account/<int:instrument_id>", methods=["POST"])
    @gate
    def bank_configuration_account_edit(instrument_id: int):
        def done(instrument):
            messages = [f"{instrument.display_name!r} saved."]
            warning = bank_service.instrument_export_warning(instrument)
            if warning and instrument.instrument_type != "CREDIT_CARD":
                messages.append(f"{instrument.display_name}: {warning}")
            return messages
        return _apply("cp-accounts", lambda db: config_service.update_account(
            db, instrument_id=instrument_id, label=_text("label"),
            instrument_type=_text("instrument_type"), reporting_entity_id=_int("entity_id"),
            reference=_text("reference") or None,
        ), done)

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

    @app.route("/bank/configuration/source", methods=["POST"])
    @gate
    def bank_configuration_source_new():
        def action(db):
            return config_service.create_source(
                db, detected_format=_text("detected_format"), file_name_key=_text("file_name_key"),
                account_hint=_text("account_hint"), payment_instrument_id=_int("payment_instrument_id"),
                active=_flag("active"), created_by_account_id=_account_id(db),
            )
        return _apply("cp-sources", action, lambda profile: f"Source rule #{profile.id} created.")

    @app.route("/bank/configuration/source/<int:profile_id>", methods=["POST"])
    @gate
    def bank_configuration_source_edit(profile_id: int):
        return _apply("cp-sources", lambda db: config_service.update_source(
            db, profile_id=profile_id, detected_format=_text("detected_format"),
            file_name_key=_text("file_name_key"), account_hint=_text("account_hint"),
            payment_instrument_id=_int("payment_instrument_id"), active=_flag("active"),
        ), lambda profile: f"Source rule #{profile.id} saved.")

    @app.route("/bank/configuration/control", methods=["POST"])
    @gate
    def bank_configuration_control():
        return _apply("cp-control", lambda db: config_service.update_control(
            db, control_start=_text("control_start"),
            validated_through=_text("validated_through"), account_id=_account_id(db),
        ), lambda messages: messages or ["Control settings unchanged."])

    @app.route("/bank/configuration/card/<int:card_id>", methods=["POST"])
    @gate
    def bank_configuration_card(card_id: int):
        return _apply("cp-dedup", lambda db: config_service.save_card(
            db, card_id=card_id, settlement_account_id=_int("settlement_account_id"),
            settlement_valid_from=_date("settlement_valid_from"),
            holder_kind=_text("holder_kind") or None, holder_id=_int("holder_id"),
            holder_name=_text("holder_name"), holder_valid_from=_date("holder_valid_from"),
            account_id=_account_id(db),
        ), lambda messages: messages or ["Card settings unchanged."])

    @app.route("/bank/configuration/dedup/recompute", methods=["POST"])
    @gate
    def bank_configuration_dedup_recompute():
        """An ACTION, not a setting: re-derive accounting deduplication from
        the current transactions and card configuration."""
        return _apply("cp-dedup", bank_service.recompute_accounting_deduplication, lambda outcome: (
            f"Accounting deduplication recomputed: {outcome.canonical_transactions} canonical, "
            f"{outcome.duplicate_groups} duplicate group(s), {outcome.suppressed_transactions} "
            f"excluded from accounting, {outcome.unresolved_transactions} without a settlement "
            f"account. {outcome.raw_rows_preserved} raw rows preserved."
        ))
