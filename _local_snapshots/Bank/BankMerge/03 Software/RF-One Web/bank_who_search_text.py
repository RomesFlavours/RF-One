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


def _ints(name):
    return [int(x) for x in request.form.getlist(name) if str(x).strip().isdigit()]


def register(app, *, gate, SessionFactory, require_csrf, endpoint):
    @app.route("/bank/who-search-text")
    @gate
    def bank_who_search_text_page():
        return render_template("bank_who_search_text.html")

    @app.route("/bank/who-search-text/data")
    @gate
    @endpoint
    def bank_who_search_text_data():
        with SessionFactory() as db:
            rows = who_search_text.movements(db)
            for r in rows:
                r["amount"] = f"{r['amount_minor'] / 100:,.2f}"
            whos = sorted(({"id": o.id, "name": o.canonical_name} for o in db.scalars(
                select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))), key=lambda w: w["name"].casefold())
            whys = [y for y in config_service.configuration_view(db)["whys"] if y["active"]]
            return jsonify(ok=True, movements=rows, whos=whos,
                           whys=[{"id": y["id"], "name": y["name"], "what": y["destination"]["label"]} for y in whys])

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
