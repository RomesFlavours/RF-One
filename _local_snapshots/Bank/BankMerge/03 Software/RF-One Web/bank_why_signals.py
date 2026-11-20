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
                                                  who_why_config, who_why_rules, why_patterns)

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
    _, _, service, _ = _cbank()
    return service.new_engine(None)


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


_check_cache = {}


def upload_check(scope_ids, force=False) -> dict:
    """BANK_WHO_WHY_UPLOAD_CHECK_001: the WHO -> WHY questions raised by the new movements of an upload, judged on
    the whole history (`cbank.why_signals.who_why_check`, read-only). Recomputed when Bank knowledge changes."""
    _e, _legacy, service, why_signals = _cbank()
    key = tuple(sorted(scope_ids))
    with _lock:
        signature = service.current_bank_signature()
        if force or _check_cache.get("key") != (signature, key):
            eng = _engine()
            try:
                _check_cache.update(key=(signature, key), data=why_signals.who_why_check(eng, key))
            finally:
                eng.db.close()
        return _check_cache["data"]


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


def _catalog_whys(db):
    from rfone_data_store.bank_reconciliation import why_what
    return [dict(id=y["id"], name=y["name"], what=y["destination"]["label"])
            for y in config_service.configuration_view(db)["whys"] if y["active"]
            and not why_what.is_provisional(db, db.get(m.BankTransactionReason, y["id"]))]


def who_rows(db, *, include_inactive=False) -> list[dict]:
    """BANK_WHO_WHY_CONFIG_001: section 1 of the WHY page - ONE row per active WHO with its configuration: single
    WHY, Personal / Company WHY, "Da regola" (MULTIPLE mode), its company exceptions, and - for a WHO not configured
    yet - whether its former WHO + Source pairs need a person's decision."""
    whys = {r.id: r.name for r in db.scalars(select(m.BankTransactionReason))}
    entities = {e.id: e.name for e in db.scalars(select(m.ReportingEntity))}
    configs, exceptions = who_why_config.load(db)
    modes = who_why_rules.modes(db)
    analysis = who_why_config.analyse_pairs(db)
    out = []
    query = select(m.BankOccurrence)
    if not include_inactive:
        query = query.where(m.BankOccurrence.status == "ACTIVE")
    for who in db.scalars(query):
        c = configs.get(who.id)
        behaviour = who_why_config.RULE if modes.get(who.id) == who_why_rules.MULTIPLE else (c.behaviour if c else None)
        res = analysis.get(who.id) or {}
        replaced = who_why_config.REPLACES.get(behaviour)
        excs = [dict(entity=entities.get(e, f"#{e}"), why=whys.get(x["why_id"]), whom=entities.get(x["whom_id"]),
                     applies=x["replaces"] == replaced, replaces=who_why_config.REPLACES_LABEL[x["replaces"]])
                for e, x in sorted((exceptions.get(who.id) or {}).items(), key=lambda kv: entities.get(kv[0], ""))]
        source_whys = {}
        if include_inactive and behaviour is None:
            for pair in res.get("pairs", []):
                reason = whys.get(pair["why_id"])
                if reason:
                    source_whys.setdefault(reason, []).append(pair["source"] or f'#{pair["source_id"]}')
        out.append(dict(
            source_whys=source_whys, active=who.status == "ACTIVE",
            id=who.id, who=who.canonical_name, behaviour=behaviour,
            single=whys.get(c.why_id) if c and behaviour == who_why_config.SINGLE else None,
            personal=whys.get(c.personal_why_id) if c and behaviour == who_why_config.BY_SUBJECT else None,
            company=whys.get(c.company_why_id) if c and behaviour == who_why_config.BY_SUBJECT else None,
            exceptions=excs,
            conflict=res.get("reason") if behaviour is None and res.get("kind") in who_why_config.CONFLICTS else None))
    out.sort(key=lambda r: r["who"].casefold())
    return out


def who_detail(db, who_id: int) -> dict:
    """What the Edit modal of one WHO needs: its configuration, exceptions, former pairs, catalogs."""
    who = db.get(m.BankOccurrence, who_id)
    if who is None:
        raise ValueError("WHO not found.")
    configs, exceptions = who_why_config.load(db)
    c = configs.get(who_id)
    mode = who_why_rules.modes(db).get(who_id, who_why_rules.UNIQUE)
    behaviour = who_why_config.RULE if mode == who_why_rules.MULTIPLE else (c.behaviour if c else None)
    entities = list(db.scalars(select(m.ReportingEntity).order_by(m.ReportingEntity.name)))
    whys = {r.id: r.name for r in db.scalars(select(m.BankTransactionReason))}
    res = who_why_config.analyse_pairs(db).get(who_id) or {}
    rules = [dict(id=r.id, status=r.status, text=v.rule_text) for r, v, s in who_why_rules.rules(db, active_only=False)
             if who_id in (s.get("who_ids") or [])]
    coherent = (who_why_config.COHERENT_SINGLE, who_why_config.COHERENT_SUBJECT)
    return dict(
        who_id=who_id, who=who.canonical_name, behaviour=behaviour, origin=c.origin if c else None,
        why_id=c.why_id if c else None, personal_why_id=c.personal_why_id if c else None,
        company_why_id=c.company_why_id if c else None,
        exceptions=[dict(x, replaces_label=who_why_config.REPLACES_LABEL[x["replaces"]],
                         applies=x["replaces"] == who_why_config.REPLACES.get(behaviour))
                    for x in (exceptions.get(who_id) or {}).values()],
        pairs=[dict(source=p["source"], owner=p["owner"], subject=p["subject"], why=whys.get(p["why_id"]))
               for p in res.get("pairs", [])],
        conflict=res.get("reason") if res.get("kind") in who_why_config.CONFLICTS else None,
        proposal=dict(behaviour=res["kind"], why_id=res.get("why_id"), personal_why_id=res.get("personal_why_id"),
                      company_why_id=res.get("company_why_id"))
        if behaviour is None and res.get("kind") in coherent else None,
        companies=[dict(id=e.id, name=e.name) for e in entities if not who_why_config.is_personal(e)],
        entities=[dict(id=e.id, name=e.name) for e in entities],
        rules=rules, whys=_catalog_whys(db))


def _draft_from(body) -> dict:
    draft = body.get("draft")
    if isinstance(draft, str):
        draft = json.loads(draft)
    if not isinstance(draft, dict):
        raise ValueError("Describe the WHO configuration.")
    return draft


def register(app, *, gate, SessionFactory, require_csrf, owner, endpoint):
    @app.route("/bank/why-signals")
    @gate
    def bank_why_signals_page():
        """BANK_WHO_WHY_FINAL_LOGIC_001 / BANK_LAYOUT_NAVIGATION_001 (2026-11-05): the WHY page, in four sections —
        1 direct WHO -> WHY associations, 2 rules for variable cases, 3 Ripartizioni, 4 the fixed WHY -> WHAT
        mappings. Sections 1 and 4 are a read-only view of the one editor, Configurazione (WHO + Source
        classifications and the WHY catalog), opened from here; nothing is edited twice."""
        with SessionFactory() as db:
            view = config_service.configuration_view(db)
            # BANK_WHO_WHY_CONFIG_001 (2026-11-06): section 1 is one row per WHO, edited here (Edit modal).
            rows = who_rows(db)
            mappings = [dict(why=y["name"], what=y["destination"]["label"], kind=y["destination"]["kind"])
                        for y in view["whys"] if y["active"]]
        return render_template("bank_why_signals.html", who_rows=rows, mappings=mappings,
                               to_decide=sum(1 for r in rows if r["conflict"]))

    @app.route("/bank/why-signals/who/<int:who_id>")
    @gate
    @endpoint
    def bank_why_who_detail(who_id):
        with SessionFactory() as db:
            return jsonify(ok=True, **who_detail(db, who_id))

    @app.route("/bank/why-signals/who/simulate", methods=["POST"])
    @gate
    @endpoint
    def bank_why_who_simulate():
        """The existing read-only simulation, for a draft WHO configuration: which movements would change."""
        require_csrf()
        draft = _draft_from(request.get_json(silent=True) or request.form)
        _e, _legacy, _service, why_signals = _cbank()
        eng = _engine()
        try:
            result = why_signals.simulate_config(eng, draft)
        finally:
            eng.db.close()
        result.pop("spec", None)
        return jsonify(ok=True, **result)

    @app.route("/bank/why-signals/who/save", methods=["POST"])
    @gate
    @endpoint
    def bank_why_who_save():
        """A person's explicit confirmation after the simulation. Only the WHO's configuration, mode and exceptions
        are written; no movement, no pair, no engine run."""
        require_csrf()
        body = request.get_json(silent=True) or request.form
        if body.get("simulated") not in (True, "yes"):
            raise ValueError("Simulate the change on the movements before saving it.")
        if body.get("confirmed") not in (True, "yes"):
            raise ValueError("Confirm the change explicitly.")
        draft = _draft_from(body)
        with SessionFactory() as db:
            safety.lock_writes(db)
            spec = who_why_config.save(db, draft, account_id=owner(db))
            db.commit()
        return jsonify(ok=True, who_id=spec["who_id"], behaviour=spec["behaviour"])

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

    @app.route("/bank/why-signals/editor-data")
    @gate
    @endpoint
    def bank_why_signals_editor_data():
        """What the WHO WHY rule editor needs when it is opened outside the WHY page (Riconosci WHO, WHO page):
        the catalogs only — no engine computation."""
        with SessionFactory() as db:
            from rfone_data_store.bank_reconciliation import why_what
            whys = [dict(id=y["id"], name=y["name"], what=y["destination"]["label"])
                    for y in config_service.configuration_view(db)["whys"] if y["active"]
                    and not why_what.is_provisional(db, db.get(m.BankTransactionReason, y["id"]))]
            whos = sorted(({"id": o.id, "name": o.canonical_name} for o in db.scalars(
                select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))), key=lambda w: w["name"].casefold())
            sources = [dict(id=i.id, name=i.display_name) for i in db.scalars(select(m.PaymentInstrument).order_by(m.PaymentInstrument.id))]
            return jsonify(ok=True, whys=whys, whos=whos, sources=sources, documents=who_why_rules.DOCUMENTS)

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
