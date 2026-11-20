"""WHO Search Text (BANK_WHO_SEARCH_TEXT_001): the person manages the text that recognises a WHO.

Every movement shows the WHO recognised in its description (or null). From a row the person opens the
movement's text, writes the text to search and saves it as an alias of an existing WHO, or — with no WHO
chosen — as a new WHO. When the WHO saved has no WHO-WHY-WHAT association yet, the page asks for it at
once; the association is saved by the one WHO implementation, `configuration.save_who`.

Nothing here writes a WHO, WHY, WHAT or classification on a movement.
"""
from flask import jsonify, render_template, request
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import configuration as config_service, rule_application_safety as safety, who_search_text
from rfone_data_store.bank_reconciliation import who_intermediaries, who_why_config, who_why_rules
import bank_who_discovery


def _ints(name):
    return [int(x) for x in request.form.getlist(name) if str(x).strip().isdigit()]


def _new_name_allowed(db, data, name):
    """A name can become a WHO from these buttons when it is among the new WHO found by «Cerca nuovi WHO», or — from
    the Completa window (Product Owner, 2026-11-18) — when a WHO rule reads exactly this unregistered name on the
    movement given (`transaction_id`), recomputed here with the engine's recognition."""
    if any(c["name"] == name for c in data["candidates"]):
        return True
    txn = db.get(m.FinancialTransaction, request.form.get("transaction_id", type=int) or 0)
    if txn is None:
        return False
    hit = bank_who_discovery.read_by_rule(who_search_text.WhoRecogniser(db), txn)
    return bool(hit and hit[0] == name)


def register(app, *, gate, SessionFactory, require_csrf, endpoint, owner=lambda db: None):
    @app.route("/bank/who-search-text")
    @gate
    def bank_who_search_text_page():
        return render_template("bank_who_search_text.html", page="who")

    # Product Owner, 2026-11-17: the WHO recognition rules have their own Regole page (same sections, same data).
    @app.route("/bank/rules")
    @gate
    def bank_rules_page():
        return render_template("bank_who_search_text.html", page="rules")

    @app.route("/bank/who-search-text/data")
    @gate
    @endpoint
    def bank_who_search_text_data():
        with SessionFactory() as db:
            if 'page' in request.args:
                data = who_search_text.movement_page(db, page=request.args.get('page', 1, type=int),
                    per_page=request.args.get('per_page', 100, type=int), show=request.args.get('show', ''),
                    search=request.args.get('q', ''))
            else:
                # Preserve the unpaginated response for existing API consumers.
                data = dict(movements=who_search_text.movements(db))
            rows = data['movements']
            for r in rows:
                r["amount"] = f"{r['amount_minor'] / 100:,.2f}"
            # Product Owner, 2026-11-17/18: WHO univoci (one fixed WHY = the SINGLE configuration), WHO con più WHY
            # (the MULTIPLE mode, "Da regola") and intermediaries (not WHO). Every WHO starts univoco.
            configs, _exceptions = who_why_config.load(db)
            modes = who_why_rules.modes(db)
            via = who_intermediaries.ids(db)
            whos = sorted(({"id": o.id, "name": o.canonical_name,
                            "multiple": o.id not in via and modes.get(o.id) == who_why_rules.MULTIPLE,
                            "intermediary": o.id in via,
                            "why_id": configs[o.id].why_id if o.id in configs and configs[o.id].behaviour == who_why_config.SINGLE else None,
                            "other_config": o.id in configs and configs[o.id].behaviour != who_why_config.SINGLE}
                           for o in db.scalars(select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))),
                          key=lambda w: w["name"].casefold())
            return jsonify(ok=True, **data, whos=whos, whys=config_service.why_choices(db),
                           fixed_whys=config_service.why_choices(db, exclude_provisional=True),
                           discovery=bank_who_discovery.load(db))

    @app.route("/bank/who-search-text/discover", methods=["POST"])
    @gate
    @endpoint
    def bank_who_discover():
        """"Cerca nuovi WHO": WHO Pattern Training run automatically; the new names are kept as candidates."""
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            data = bank_who_discovery.discover(db)
            bank_who_discovery.save(db, data)
            db.commit()
            return jsonify(ok=True, found=len(data["candidates"]), read=data["read"], movements=data["movements"])

    @app.route("/bank/who-search-text/discovered/create", methods=["POST"])
    @gate
    @endpoint
    def bank_who_discovered_create():
        """Singolo / Più WHY / Intermediario on a new name: created now in that list."""
        require_csrf()
        name = (request.form.get("name") or "").strip()
        kind = request.form.get("kind")
        with SessionFactory() as db:
            safety.lock_writes(db)
            data = bank_who_discovery.load(db)
            if not _new_name_allowed(db, data, name):
                raise ValueError("Questo nome non è più tra i nuovi WHO (forse esiste già).")
            who = config_service.save_who(db, occurrence_id=None, name=name, active=True, reason_ids=[],
                                          default_reason_id=None, reporting_entity_ids=[])
            db.flush()
            if kind == "multiple":
                who_why_rules.set_mode(db, who.id, who_why_rules.MULTIPLE, account_id=owner(db))
            elif kind == "intermediary":
                who_intermediaries.set_intermediary(db, who.id, True, account_id=owner(db))
            data["candidates"] = [c for c in data["candidates"] if c["name"] != name]
            bank_who_discovery.save(db, data)
            db.commit()
            return jsonify(ok=True, who=dict(id=who.id, name=who.canonical_name, multiple=kind == "multiple",
                                             intermediary=kind == "intermediary", why_id=None, other_config=False))

    @app.route("/bank/who-search-text/discovered/alias", methods=["POST"])
    @gate
    @endpoint
    def bank_who_discovered_alias():
        """«È alias di…» on a new WHO (Product Owner, 2026-11-18): the name is the same counterparty written
        differently, so it is saved as an alias of the chosen existing WHO (the one alias implementation,
        `who_search_text.save`, which refuses a text already owned by another WHO)."""
        require_csrf()
        name = (request.form.get("name") or "").strip()
        who_id = request.form.get("who_id", type=int)
        with SessionFactory() as db:
            safety.lock_writes(db)
            data = bank_who_discovery.load(db)
            if not _new_name_allowed(db, data, name):
                raise ValueError("Questo nome non è più tra i nuovi WHO (forse esiste già).")
            who = db.get(m.BankOccurrence, who_id) if who_id else None
            if who is None or who.status != "ACTIVE":
                raise ValueError("Scegli un WHO esistente dall'elenco.")
            result = who_search_text.save(db, text=name, occurrence_id=who.id, transaction_id=None)
            data["candidates"] = [c for c in data["candidates"] if c["name"] != name]
            bank_who_discovery.save(db, data)
            db.commit()
            return jsonify(ok=True, who=result["who"], outcome=result["outcome"])

    @app.route("/bank/who-search-text/fixed-why", methods=["POST"])
    @gate
    @endpoint
    def bank_who_fixed_why():
        """The one WHY of a WHO univoco (its SINGLE configuration); empty removes it. Exceptions, rules and
        movements are left as they are."""
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            who = db.get(m.BankOccurrence, request.form.get("who_id", type=int))
            if who is None:
                raise ValueError("This WHO no longer exists.")
            why_id = request.form.get("why_id", type=int)
            row = db.get(m.BankWhoWhyConfig, who.id)
            if why_id is None:
                if row is not None:
                    db.delete(row)
            else:
                reason = db.get(m.BankTransactionReason, why_id)
                if reason is None or reason.status != "ACTIVE":
                    raise ValueError("This WHY no longer exists.")
                if row is None:
                    row = m.BankWhoWhyConfig(occurrence_id=who.id, behaviour=who_why_config.SINGLE)
                    db.add(row)
                row.behaviour, row.why_id, row.personal_why_id, row.company_why_id = who_why_config.SINGLE, why_id, None, None
                row.origin, row.updated_by_account_id = who_why_config.ORIGIN_PERSON, owner(db)
            db.commit()
            return jsonify(ok=True)

    @app.route("/bank/who-search-text/who-kind", methods=["POST"])
    @gate
    @endpoint
    def bank_who_kind():
        """Moves a WHO between the lists: Più WHY (MULTIPLE mode), Intermediario (not a WHO), Univoco (back to the
        default). Its WHY configuration is kept."""
        require_csrf()
        kind = request.form.get("kind")
        who_id = request.form.get("who_id", type=int)
        with SessionFactory() as db:
            safety.lock_writes(db)
            if kind == "intermediary":
                who_intermediaries.set_intermediary(db, who_id, True, account_id=owner(db))
            else:
                who_intermediaries.set_intermediary(db, who_id, False, account_id=owner(db))
                who_why_rules.set_mode(db, who_id, who_why_rules.MULTIPLE if kind == "multiple" else who_why_rules.UNIQUE,
                                       account_id=owner(db))
            db.commit()
            return jsonify(ok=True, kind=kind)

    @app.route("/bank/who-search-text/movement/<int:transaction_id>")
    @gate
    @endpoint
    def bank_who_search_text_movement(transaction_id):
        with SessionFactory() as db:
            return jsonify(ok=True, **who_search_text.transaction_text(db, transaction_id))

    @app.route("/bank/who-search-text/save", methods=["POST"])
    @gate
    @endpoint
    def bank_who_search_text_save():
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            result = who_search_text.save(db, text=request.form.get("text"), occurrence_id=request.form.get("who_id", type=int),
                                          transaction_id=request.form.get("transaction_id", type=int))
            db.commit()
            return jsonify(ok=True, **result)

    @app.route("/bank/who-search-text/association", methods=["POST"])
    @gate
    @endpoint
    def bank_who_search_text_association():
        """The WHO's possible WHY and default WHY; its name, state and entities are kept as they are."""
        require_csrf()
        why_ids = _ints("why_ids")
        if not why_ids:
            raise ValueError("Choose at least one WHY.")
        with SessionFactory() as db:
            safety.lock_writes(db)
            who = db.get(m.BankOccurrence, request.form.get("who_id", type=int))
            if who is None:
                raise ValueError("This WHO no longer exists.")
            current = [a.transaction_reason_id for a in db.scalars(select(m.BankOccurrenceReasonAssociation).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == who.id, m.BankOccurrenceReasonAssociation.active.is_(True)))]
            entities = [e.reporting_entity_id for e in db.scalars(select(m.BankOccurrenceReportingEntity).where(
                m.BankOccurrenceReportingEntity.occurrence_id == who.id, m.BankOccurrenceReportingEntity.active.is_(True)))]
            config_service.save_who(db, occurrence_id=who.id, name=who.canonical_name, active=who.status == "ACTIVE",
                                    reason_ids=current + why_ids, default_reason_id=request.form.get("default_why_id", type=int),
                                    reporting_entity_ids=entities)
            db.commit()
            return jsonify(ok=True, who=who.canonical_name)
