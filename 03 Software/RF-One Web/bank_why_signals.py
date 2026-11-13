"""WHY to determine (BANK_WHO_WHY_MODE_001): recognised WHO whose WHY is not determinable.

One page lists the movements grouped by WHO, Source and reason — "Serve una classificazione WHO + Source",
"Serve una regola per il WHY", "Serve un documento o un chiarimento", "Regole in conflitto" — with the number
of movements, the movements themselves and the action that resolves the group. The same page sets a WHO's WHY
mode (UNIQUE / MULTIPLE) and defines WHO WHY rules: verifiable conditions, a WHY (or the document it is read
from), simulated on the WHO's movements before saving, saved INACTIVE unless the person activates it.

The list and the simulation are read-only evaluations of the one engine (C-Bank, read-only session). Writes
are a person's: the WHO mode and the rules. Nothing here writes a movement classification, and nothing
starts an engine run.
"""
import json
import threading

from flask import jsonify, render_template, request
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import (configuration as config_service, rule_application_safety as safety,
                                                  who_why_rules, why_patterns)

_cache = {}
_lock = threading.Lock()


def _cbank():
    """The engine package, through the one mount of Guided Reconciliation (puts the C-Bank code on the path)."""
    import bank_guided_reconciliation
    if not bank_guided_reconciliation.available():
        raise ValueError("The reconciliation engine is not available on this server (RFONE_BANK_GUIDED).")
    bank_guided_reconciliation._cbank_app()
    from cbank import engine, legacy, service, why_signals
    return engine, legacy, service, why_signals


def _engine():
    engine, legacy, _service, _signals = _cbank()
    return engine.Engine(legacy.session(), None)


def compute(force=False) -> dict:
    """Signals for the current Bank knowledge; recomputed when movements, rules, modes or documents change."""
    _e, _legacy, service, why_signals = _cbank()
    with _lock:
        signature = service.current_bank_signature()
        if force or _cache.get("signature") != signature:
            eng = _engine()
            try:
                _cache.update(signature=signature, data=why_signals.signals(eng))
            finally:
                eng.db.close()
        return _cache["data"]


def _rule_rows(db):
    whys = {r.id: r for r in db.scalars(select(m.BankTransactionReason))}
    whos = {o.id: o.canonical_name for o in db.scalars(select(m.BankOccurrence))}
    return [dict(id=r.id, status=r.status, version=v.version_no, text=v.rule_text, who_ids=s.get("who_ids", []),
                 whos=[whos.get(i) for i in s.get("who_ids", [])], why=s.get("why"), document=s.get("document"),
                 conditions=s["conditions"], created_at=str(r.created_at)[:16])
            for r, v, s in who_why_rules.rules(db, active_only=False)]


def _spec_from(body) -> dict:
    spec = body.get("spec")
    if isinstance(spec, str):
        spec = json.loads(spec)
    if not isinstance(spec, dict):
        raise ValueError("Describe the rule: WHO, conditions and result.")
    spec = dict(spec, engine=why_patterns.ENGINE, scope=who_why_rules.SCOPE)
    if not spec.get("why_id"):
        spec.pop("why_id", None)
    if not spec.get("document"):
        spec.pop("document", None)
    return spec


def register(app, *, gate, SessionFactory, require_csrf, owner, endpoint):
    @app.route("/bank/why-signals")
    @gate
    def bank_why_signals_page():
        return render_template("bank_why_signals.html")

    @app.route("/bank/why-signals/data")
    @gate
    @endpoint
    def bank_why_signals_data():
        data = compute(force=request.args.get("refresh") == "1")
        with SessionFactory() as db:
            from rfone_data_store.bank_reconciliation import why_what
            whys = [dict(id=y["id"], name=y["name"], what=y["destination"]["label"])
                    for y in config_service.configuration_view(db)["whys"] if y["active"]
                    and not why_what.is_provisional(db, db.get(m.BankTransactionReason, y["id"]))]
            whos = sorted(({"id": o.id, "name": o.canonical_name} for o in db.scalars(
                select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))), key=lambda w: w["name"].casefold())
            sources = [dict(id=i.id, name=i.display_name) for i in db.scalars(select(m.PaymentInstrument).order_by(m.PaymentInstrument.id))]
            modes = who_why_rules.modes(db)
            return jsonify(ok=True, **data, whys=whys, whos=whos, sources=sources, rules=_rule_rows(db),
                           multiple=[dict(id=w, name=next((x["name"] for x in whos if x["id"] == w), f"#{w}")) for w, md in modes.items()
                                     if md == who_why_rules.MULTIPLE],
                           labels=who_why_rules.LABELS, documents=who_why_rules.DOCUMENTS)

    @app.route("/bank/why-signals/mode", methods=["POST"])
    @gate
    @endpoint
    def bank_why_signals_mode():
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            mode = who_why_rules.set_mode(db, request.form.get("who_id", type=int), request.form.get("mode", ""),
                                          account_id=owner(db), note=(request.form.get("note") or "").strip()[:500])
            db.commit()
        return jsonify(ok=True, mode=mode)

    @app.route("/bank/why-signals/simulate", methods=["POST"])
    @gate
    @endpoint
    def bank_why_signals_simulate():
        require_csrf()
        spec = _spec_from(request.get_json(silent=True) or request.form)
        _e, _legacy, _service, why_signals = _cbank()
        eng = _engine()
        try:
            return jsonify(ok=True, **why_signals.simulate(eng, spec))
        finally:
            eng.db.close()

    @app.route("/bank/why-signals/rules", methods=["POST"])
    @gate
    @endpoint
    def bank_why_signals_save_rule():
        require_csrf()
        body = request.get_json(silent=True) or request.form
        if body.get("simulated") not in (True, "yes"):
            raise ValueError("Simulate the rule on its movements before saving it.")
        spec = _spec_from(body)
        with SessionFactory() as db:
            safety.lock_writes(db)
            rule = who_why_rules.save_rule(db, spec, account_id=owner(db), active=body.get("active") in (True, "yes"))
            db.commit()
            return jsonify(ok=True, id=rule.id, status=rule.status)

    @app.route("/bank/why-signals/rules/<int:rule_id>/<action>", methods=["POST"])
    @gate
    @endpoint
    def bank_why_signals_rule_state(rule_id, action):
        require_csrf()
        if action not in ("activate", "deactivate"):
            raise ValueError("Unknown action.")
        with SessionFactory() as db:
            safety.lock_writes(db)
            who_why_rules.set_active(db, rule_id, action == "activate")
            db.commit()
        return jsonify(ok=True)
