"""RF-One Web — Classification Learning (BANK_CLASSIFICATION_LEARNING_001).

Bank > Classification shows CLASSIFICATION LEARNING above the deterministic
rules. Every route here is an explicit action; nothing runs on page load:

  POST /bank/learning/discover                     Discover Patterns
  POST /bank/learning/backtest                     month-by-month temporal backtest —
                                                   administrators only, not in the page
  POST /bank/learning/suggestions/<id>/test        read-only test of one suggestion
  POST /bank/learning/suggestions/<id>/approve     human approval -> rule in its own store
  POST /bank/learning/suggestions/<id>/reject      rejection (remembered by fingerprint)

BANK_ACTIONABLE_CLASSIFICATION_LEARNING_001: the page lists ONLY patterns a
person has to decide (`pattern_discovery.actionable_suggestions`). Covered,
approved, rejected and probabilistic patterns stay stored for audit and
rejection memory, and are never shown. The backtest is a development tool:
its engine and route are kept, its button and table are not on the page.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

import json

from flask import abort, flash, redirect, session, url_for
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import pattern_discovery

TEST_SESSION_KEY = "bank_learning_test_result"


def _back():
    return redirect(url_for("bank_classification") + "#classification-learning")


def learning_view(db) -> dict:
    """What the Classification page shows — the actionable suggestions only,
    read only. Never discovers anything."""
    rows = pattern_discovery.actionable_suggestions(db)
    who_ids, why_ids = set(), set()
    parsed = []
    for s in rows:
        proposal, evidence = json.loads(s.proposal), json.loads(s.evidence)
        who_ids.add(proposal.get("who_id"))
        why_ids.add(proposal.get("why_id"))
        parsed.append({"row": s, "proposal": proposal, "evidence": evidence})
    who_names = dict(db.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)
                                .where(m.BankOccurrence.id.in_([i for i in who_ids if i] or [-1]))).all())
    why_names = dict(db.execute(select(m.BankTransactionReason.id, m.BankTransactionReason.name)
                                .where(m.BankTransactionReason.id.in_([i for i in why_ids if i] or [-1]))).all())
    return {
        "suggestions": parsed, "who_names": who_names, "why_names": why_names,
        "test_result": session.pop(TEST_SESSION_KEY, None),
    }


def register_bank_learning_routes(app, *, gate, SessionFactory, load_current_account, require_csrf):

    def _account_id(db):
        account = load_current_account(db)
        return account.id if account is not None else None

    @app.route("/bank/learning/discover", methods=["POST"])
    @gate
    def bank_learning_discover():
        require_csrf()
        with SessionFactory() as db:
            run = pattern_discovery.discover(db, account_id=_account_id(db))
            db.commit()
            found = int(json.loads(run.summary).get("new_actionable", 0))
        flash(f"New patterns found: {found}" if found else "No new classification patterns to review.",
              "success")
        return _back()

    @app.route("/bank/learning/backtest", methods=["POST"])
    @gate
    def bank_learning_backtest():
        """Development / audit tool. Not offered on the Classification page;
        kept for administrators and for the tests that exercise it."""
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            if account is None or not account.is_admin:
                abort(403)
            pattern_discovery.backtest(db, account_id=_account_id(db))
            db.commit()
        flash("Backtest finished.", "success")
        return _back()

    @app.route("/bank/learning/suggestions/<int:suggestion_id>/test", methods=["POST"])
    @gate
    def bank_learning_test(suggestion_id: int):
        require_csrf()
        with SessionFactory() as db:
            suggestion = db.get(m.BankPatternSuggestion, suggestion_id)
            if suggestion is None:
                flash("That suggestion does not exist.", "error")
            else:
                session[TEST_SESSION_KEY] = {"id": suggestion_id, **pattern_discovery.test_suggestion(db, suggestion)}
            db.rollback()
        return _back()

    @app.route("/bank/learning/suggestions/<int:suggestion_id>/approve", methods=["POST"])
    @gate
    def bank_learning_approve(suggestion_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                s = pattern_discovery.approve(db, suggestion_id=suggestion_id, account_id=_account_id(db))
                db.commit()
                flash(f"Approved: the pattern is now an active deterministic rule ({s.routed_to}).", "success")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _back()

    @app.route("/bank/learning/suggestions/<int:suggestion_id>/reject", methods=["POST"])
    @gate
    def bank_learning_reject(suggestion_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                pattern_discovery.reject(db, suggestion_id=suggestion_id, account_id=_account_id(db))
                db.commit()
                flash("Rejected. The same pattern will not be proposed again unless new evidence appears.", "success")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _back()
