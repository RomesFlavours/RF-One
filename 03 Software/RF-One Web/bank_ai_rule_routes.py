"""RF-One Web — Bank > AI Rules (BANK_AI_RULES_001 … 006).

  GET  /bank/ai-rules                          every in-scope movement of a period (From / To),
                                               each selectable and with an "AI Rules" button;
                                               the operative rules and the drafts
  POST /bank/ai-rules/preview                  evaluate a rule on its scope: the period, ALL the
                                               movements, or the SELECTED ones (JSON)
  POST /bank/ai-rules/drafts                   Save Draft — kept only, never active (JSON)
  POST /bank/ai-rules/save                     Salva — operative rule, applied to nothing now;
                                               "Per il futuro" enables it for new imports (JSON)
  POST /bank/ai-rules/save-apply               Salva e Applica — on the strength of a valid
                                               preview of the same text and scope (JSON)
  GET  /bank/ai-rules/rules/<id>               an operative rule, to reopen it (JSON)
  POST /bank/ai-rules/rules/<id>/status        activate / deactivate an operative rule
  POST /bank/ai-rules/previews/<id>/create-who "Inserisci nuovi WHO in elenco" (JSON)
  POST /bank/ai-rules/instructions             the optional general AI instructions

The routes only call `ai_rules` / `ai_rule_operations`. Classifications are
written only by "Salva e Applica" (and by the import, for rules enabled "Per
il futuro"); a provider that is missing or failing is answered with its
reason; no AI answer is ever simulated.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

import calendar
from datetime import date

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rule_operations as operations
from rfone_data_store.bank_reconciliation import ai_rules
from rfone_data_store.selection.parsing import ai_client


def _date(raw: str | None) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ai_rules.AiRuleError(f"The date “{raw}” could not be read.") from None


def _latest_month(db) -> tuple[date | None, date | None]:
    """The default period: the latest month that has movements."""
    latest = db.scalar(select(func.max(m.FinancialTransaction.posting_date)))
    if latest is None:
        return None, None
    return latest.replace(day=1), latest.replace(day=calendar.monthrange(latest.year, latest.month)[1])


def _selected_ids() -> list[int]:
    ids = []
    for part in (request.form.get("selected_ids") or "").split(","):
        part = part.strip()
        if part:
            if not part.isdigit():
                raise ai_rules.AiRuleError("The selection could not be read; reload the page.")
            ids.append(int(part))
    return sorted(set(ids))


def _scope() -> tuple[str, list[int], bool]:
    """(scope for the preview / application, selected ids, Per il futuro).
    "Tutte" and "Solo selezionate" are alternatives; neither = the period."""
    all_ = request.form.get("scope_all") == "on"
    selected = request.form.get("scope_selected") == "on"
    if all_ and selected:
        raise ai_rules.AiRuleError("Choose either “Tutte le transazioni esistenti” or “Solo le transazioni selezionate”.")
    scope = ai_rules.SCOPE_ALL if all_ else ai_rules.SCOPE_SELECTED if selected else ai_rules.SCOPE_PERIOD
    return scope, _selected_ids() if selected else [], request.form.get("scope_future") == "on"


def _rule_as_dict(db, rule: "m.BankAiRule") -> dict:
    version = operations.current_version(rule)
    origin = ai_rules.row_for(db, rule.origin_transaction_id)
    return {
        "ok": True, "rule_id": rule.id, "status": rule.status, "apply_future": rule.apply_future,
        "rule_text": version.rule_text if version else "", "version_no": version.version_no if version else None,
        "method": version.method if version else None,
        "create_missing_who": bool(version.create_missing_who) if version else False,
        "override_protected": bool(version.override_protected) if version else False,
        "origin": origin.as_dict() if origin is not None else {
            "id": None, "date": None, "description": rule.origin_description or "", "amount": "", "currency": "",
            "source": "", "who": None, "why": None},
    }


def register_bank_ai_rule_routes(app, *, gate, SessionFactory, load_current_account, require_csrf):

    def _account_id(db):
        account = load_current_account(db)
        return account.id if account is not None else None

    @app.route("/bank/ai-rules")
    @gate
    def bank_ai_rules():
        with SessionFactory() as db:
            default_from, default_to = _latest_month(db)
            error = None
            # BANK_AI_RULES_019 — the list's "Classificazione" filter (never the modal's scope).
            cls = request.args.get("cls") or "all"
            if cls not in ai_rules.CLASSIFICATION_FILTERS:
                cls = "all"
            try:
                date_from = _date(request.args.get("date_from")) if "date_from" in request.args else default_from
                date_to = _date(request.args.get("date_to")) if "date_to" in request.args else default_to
                period = ai_rules.period_rows(db, date_from=date_from, date_to=date_to)
            except ai_rules.AiRuleError as exc:
                error, period = str(exc), []
                date_from, date_to = default_from, default_to
            rows = ai_rules.classification_filter(period, cls)
            shown = {r.id for r in rows}
            excluded_ids = [r.id for r in period if r.id not in shown]
            provider, model = ai_rules.active_ai_description()
            who_names, why_names = ai_rules.catalog_names(db)
            operative = [(rule, operations.current_version(rule)) for rule in operations.rules(db)]
            return render_template(
                "bank_ai_rules.html",
                rows=rows, error=error, who_names=who_names, why_names=why_names,
                cls=cls, cls_options=ai_rules.CLASSIFICATION_FILTERS, period_total=len(period),
                excluded_ids=excluded_ids,
                date_from=date_from.isoformat() if date_from else "",
                date_to=date_to.isoformat() if date_to else "",
                drafts=ai_rules.drafts(db), operative_rules=operative,
                instruction=ai_rules.current_instruction(db),
                provider=provider, model=model,
                batch_size=ai_rules.BATCH_SIZE, max_period=ai_rules.MAX_PERIOD_MOVEMENTS,
            )

    @app.route("/bank/ai-rules/selection-check", methods=["POST"])
    @gate
    def bank_ai_rules_selection_check():
        """BANK_AI_RULES_020 — which selected movements (any period) satisfy
        the "Classificazione" filter. Read only: nothing is written."""
        require_csrf()
        cls = request.form.get("cls") or "all"
        if cls not in ai_rules.CLASSIFICATION_FILTERS:
            return jsonify({"ok": False, "error": "Unknown filter."}), 400
        ids = []
        for part in (request.form.get("ids") or "").split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        with SessionFactory() as db:
            matching = ai_rules.ids_matching_classification(db, ids, cls)
        return jsonify({"ok": True, "cls": cls, "matching": [str(i) for i in matching]})

    @app.route("/bank/ai-rules/preview", methods=["POST"])
    @gate
    def bank_ai_rules_preview():
        require_csrf()
        with SessionFactory() as db:
            try:
                scope, selected, _future = _scope()
                preview = ai_rules.preview_rule(
                    db, rule_text=request.form.get("rule_text"),
                    origin_transaction_id=request.form.get("origin_transaction_id", type=int),
                    date_from=_date(request.form.get("date_from")), date_to=_date(request.form.get("date_to")),
                    draft_id=request.form.get("draft_id", type=int) or None,
                    account_id=_account_id(db),
                    create_missing_who=request.form.get("create_missing_who") == "on",
                    override_protected=request.form.get("override_protected") == "on",
                    only_unsettled=request.form.get("only_unsettled") == "on",
                    who_only=request.form.get("who_only") == "on",
                    scope=scope, selected_ids=selected, ai_rule_id=request.form.get("rule_id", type=int) or None,
                    # BANK_AI_RULES_008: never an automatic fallback — only when asked.
                    allow_ai_batches=request.form.get("allow_ai_batches") == "on",
                )
                db.commit()
            except ai_rules.AiRuleError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": str(exc)}), 400
            return jsonify(ai_rules.preview_as_dict(preview))

    @app.route("/bank/ai-rules/previews/<int:preview_id>/create-who", methods=["POST"])
    @gate
    def bank_ai_rules_create_who(preview_id: int):
        """"Inserisci nuovi WHO in elenco" (BANK_AI_RULES_003): the missing WHO
        of the preview's certain matches — the WHO catalog only."""
        require_csrf()
        with SessionFactory() as db:
            try:
                result = ai_rules.create_missing_whos(db, preview_id=preview_id)
                db.commit()
            except ai_rules.AiRuleError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:  # noqa: BLE001 — nothing is half-created: rolled back and reported
                db.rollback()
                return jsonify({"ok": False, "error": f"No WHO was created: {exc}"}), 500
            return jsonify(result)

    @app.route("/bank/ai-rules/drafts", methods=["POST"])
    @gate
    def bank_ai_rules_save_draft():
        """Save Draft: kept only. For an operative rule, a draft of a change —
        its current version is not touched."""
        require_csrf()
        with SessionFactory() as db:
            try:
                draft = ai_rules.save_draft(
                    db, draft_id=request.form.get("draft_id", type=int) or None,
                    rule_text=request.form.get("rule_text"),
                    origin_transaction_id=request.form.get("origin_transaction_id", type=int),
                    account_id=_account_id(db),
                    create_missing_who=request.form.get("create_missing_who") == "on",
                    override_protected=request.form.get("override_protected") == "on",
                    only_unsettled=request.form.get("only_unsettled") == "on",
                    ai_rule_id=request.form.get("rule_id", type=int) or None,
                )
                db.commit()
            except ai_rules.AiRuleError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": str(exc)}), 400
            return jsonify({"ok": True, "draft_id": draft.id})

    def _save(db, *, apply_future: bool):
        return operations.save_rule(
            db, rule_id=request.form.get("rule_id", type=int) or None, rule_text=request.form.get("rule_text"),
            create_missing_who=request.form.get("create_missing_who") == "on", apply_future=apply_future,
            override_protected=request.form.get("override_protected") == "on",
            origin_transaction_id=request.form.get("origin_transaction_id", type=int), account_id=_account_id(db),
            draft_id=request.form.get("draft_id", type=int) or None)

    def _done(db) -> bool:
        """After success only: the draft the window came from leaves the drafts."""
        return operations.remove_draft(db, request.form.get("draft_id", type=int) or None)

    def _saved(result) -> dict:
        return {"rule_id": result.rule.id, "version_no": result.version.version_no, "new_version": result.new_version,
                "created": result.created, "apply_future": result.rule.apply_future, "method": result.version.method}

    @app.route("/bank/ai-rules/save", methods=["POST"])
    @gate
    def bank_ai_rules_save():
        """Salva: an operative rule, applied to nothing now."""
        require_csrf()
        with SessionFactory() as db:
            try:
                _scope_, _selected, future = _scope()
                result = _save(db, apply_future=future)
                draft_removed = _done(db)
                db.commit()
            except operations.InterpretationInvalid as exc:
                db.commit()            # only the interpretation, kept with its reason; no rule saved
                return jsonify({"ok": False, "error": str(exc)}), 400
            except ai_rules.AiRuleError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": str(exc)}), 400
            return jsonify({"ok": True, **_saved(result), "applied": False, "draft_removed": draft_removed})

    @app.route("/bank/ai-rules/save-apply", methods=["POST"])
    @gate
    def bank_ai_rules_save_apply():
        """Salva e Applica. With only "Per il futuro": saved and enabled, the
        history untouched. With "Tutte" / "Solo selezionate": a valid preview
        of the same text, scope, selection and option is required BEFORE
        anything is written (`needs_preview` otherwise)."""
        require_csrf()
        with SessionFactory() as db:
            try:
                scope, selected, future = _scope()
                if scope == ai_rules.SCOPE_PERIOD:
                    if not future:
                        raise ai_rules.AiRuleError("Choose where to apply the rule.")
                    result = _save(db, apply_future=True)
                    draft_removed = _done(db)
                    db.commit()
                    return jsonify({"ok": True, **_saved(result), "applied": False, "draft_removed": draft_removed})
                text = (request.form.get("rule_text") or "").strip()
                create = request.form.get("create_missing_who") == "on"
                preview = db.get(m.BankAiRulePreview, request.form.get("preview_id", type=int) or 0)
                problem = ai_rules.preview_problem(preview, rule_text=text, scope=scope, selected_ids=selected,
                                                   create_missing_who=create,
                                                   override_protected=request.form.get("override_protected") == "on",
                                                   only_unsettled=request.form.get("only_unsettled") == "on",
                                                   who_only=request.form.get("who_only") == "on") \
                    or operations.already_applied(db, preview.id if preview is not None else None)
                if problem:
                    return jsonify({"ok": False, "needs_preview": True, "error": problem}), 409
                result = _save(db, apply_future=future)
                application = operations.apply_rule(db, rule=result.rule, scope=scope, selected_ids=selected,
                                                    preview_id=preview.id, account_id=_account_id(db),
                                                    only_unsettled=request.form.get("only_unsettled") == "on",
                                                    who_only=request.form.get("who_only") == "on")
                # A movement that could not be changed is an ERROR item: the
                # application is then NOT complete, and the draft is kept.
                complete = application.status == "COMPLETED" and not application.errors
                draft_removed = _done(db) if complete else False
                db.commit()
                return jsonify({"ok": True, **_saved(result), "applied": True, "complete": complete,
                                "draft_removed": draft_removed,
                                "application": operations.application_as_dict(application)})
            except operations.NeedsPreview as exc:
                db.rollback()
                return jsonify({"ok": False, "needs_preview": True, "error": str(exc)}), 409
            except operations.InterpretationInvalid as exc:
                db.commit()            # only the interpretation, kept with its reason; nothing saved or applied
                return jsonify({"ok": False, "error": str(exc)}), 400
            except ai_rules.AiRuleError as exc:
                db.rollback()
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:  # noqa: BLE001 — rolled back: nothing saved, nothing applied, said so
                db.rollback()
                return jsonify({"ok": False, "error": f"Non applicata: nulla è stato salvato né modificato ({exc})."}), 500

    @app.route("/bank/ai-rules/rules/<int:rule_id>")
    @gate
    def bank_ai_rules_rule(rule_id: int):
        with SessionFactory() as db:
            rule = db.get(m.BankAiRule, rule_id)
            if rule is None or rule.deleted_at is not None:
                return jsonify({"ok": False, "error": f"AI rule #{rule_id} no longer exists (deleted): reload the "
                                                      "page."}), 404
            return jsonify(_rule_as_dict(db, rule))

    @app.route("/bank/ai-rules/rules/<int:rule_id>/delete", methods=["POST"])
    @gate
    def bank_ai_rules_rule_delete(rule_id: int):
        """Delete (BANK_AI_RULES_014): the rule is never executed again; what
        it already classified, and the history of it, stay unchanged."""
        require_csrf()
        with SessionFactory() as db:
            try:
                rule = operations.delete_rule(db, rule_id=rule_id, account_id=_account_id(db))
                db.commit()
                flash(f"AI rule #{rule.id} deleted: it will not be executed again. The classifications it already "
                      "applied to movements are unchanged, and their history is kept.", "info")
            except ai_rules.AiRuleError as exc:
                db.rollback()
                flash(str(exc), "error")
        back = {k: request.form.get(k) for k in ("date_from", "date_to", "cls") if request.form.get(k)}
        return redirect(url_for("bank_ai_rules", **back) + "#ai-operative-rules")

    @app.route("/bank/ai-rules/rules/<int:rule_id>/status", methods=["POST"])
    @gate
    def bank_ai_rules_rule_status(rule_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                rule = operations.set_status(db, rule_id=rule_id, active=request.form.get("active") == "1")
                db.commit()
                flash(f"AI rule #{rule.id} {'activated' if rule.status == 'ACTIVE' else 'disabled'}. "
                      "No classification was changed.", "info")
            except ai_rules.AiRuleError as exc:
                db.rollback()
                flash(str(exc), "error")
        back = {k: request.form.get(k) for k in ("date_from", "date_to", "cls") if request.form.get(k)}
        return redirect(url_for("bank_ai_rules", **back) + "#ai-operative-rules")

    @app.route("/bank/ai-rules/instructions", methods=["POST"])
    @gate
    def bank_ai_rules_save_instructions():
        require_csrf()
        with SessionFactory() as db:
            ai_rules.save_instructions(db, text=request.form.get("instructions"), account_id=_account_id(db))
            db.commit()
        flash("General AI instructions saved. Existing rules and classifications are unchanged.", "info")
        back = {k: request.form.get(k) for k in ("date_from", "date_to", "cls") if request.form.get(k) is not None}
        return redirect(url_for("bank_ai_rules", **back))

    @app.route("/bank/ai-rules/drafts/<int:draft_id>")
    @gate
    def bank_ai_rules_draft(draft_id: int):
        """A draft with its origin, to reopen it in the modal (JSON)."""
        with SessionFactory() as db:
            draft = db.get(m.BankAiRuleDraft, draft_id)
            if draft is None:
                abort(404)
            origin = ai_rules.row_for(db, draft.origin_transaction_id)
            return jsonify({
                "ok": True, "draft_id": draft.id, "rule_text": draft.rule_text,
                "create_missing_who": draft.create_missing_who, "rule_id": draft.ai_rule_id,
                "override_protected": bool(draft.override_protected),
                "only_unsettled": bool(draft.only_unsettled),
                "origin": origin.as_dict() if origin is not None else {
                    "id": None, "date": draft.origin_posting_date.isoformat() if draft.origin_posting_date else None,
                    "description": draft.origin_description or "", "amount":
                    f"{(draft.origin_amount_minor or 0) / 100:.2f}", "currency": "", "source": "", "who": None,
                    "why": None},
            })
