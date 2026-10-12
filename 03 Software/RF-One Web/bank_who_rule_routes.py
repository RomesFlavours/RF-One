"""RF-One Web — WHO lookups (formerly the simple WHO Rule, BANK_SIMPLE_WHO_RULE_001).

BANK_RULES_RESET_001 — the old (non-AI) WHO rules were removed: no rule is
saved or applied here any more. Only the two read-only GET endpoints remain,
because the "new WHO" dialog (`_bank_who_create_dialog.html`) uses them: the
creatable WHO combo (matching active WHO, the WHO a typed name already is,
similar names, whether "Create" may be offered) and what a chosen WHO
already has. A WHO is never created by these GETs.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

from flask import jsonify, request

from rfone_data_store.bank_reconciliation import who_rules


def register_bank_who_rule_routes(app, *, gate, SessionFactory, load_current_account, require_csrf):

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
