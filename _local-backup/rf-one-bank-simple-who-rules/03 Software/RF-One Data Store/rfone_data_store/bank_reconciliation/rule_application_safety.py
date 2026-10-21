"""Explicit rule execution modes and compare-before-restore rollback.

Only transaction classifications/allocations are restored. Catalog additions
and financial source data are never deleted. Old applications without exact
snapshots are deliberately not offered an unsafe, guessed rollback.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, delete, select
from .. import models as m

FILL_MISSING = "FILL_MISSING"
UPDATE_ASSIGNED = "UPDATE_ASSIGNED"
MODES = (FILL_MISSING, UPDATE_ASSIGNED)


def validate_mode(mode):
    if mode is not None and mode not in MODES:
        raise ValueError("Choose Fill missing data or Update assigned data.")
    return mode


def prepare_target(target, row, planner):
    mode = validate_mode(target.application_mode)
    if mode != FILL_MISSING:
        return target
    current = row.explanation
    return dataclasses.replace(
        target,
        who_set=target.who_set and not (current and current.occurrence_id is not None),
        destination_id=target.destination_id if not (current and current.accounting_classification_id is not None) else None,
        why_set=target.why_set and not (current and current.transaction_reason_id is not None)
                and not target.why_clear,
        for_whom_set=target.for_whom_set and not any(
            a.reporting_entity_id is not None for a in planner.allocations_of(row.id)),
    )


def _values(obj):
    if obj is None:
        return None
    values = {col.name: getattr(obj, col.name) for col in obj.__table__.columns}
    # SQLite drops timezone offsets on reload; PostgreSQL retains them.
    # Normalize both before comparing snapshots across commit boundaries.
    for key, value in values.items():
        if isinstance(value, datetime) and value.tzinfo is not None:
            values[key] = value.astimezone(timezone.utc).replace(tzinfo=None)
    return values


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def snapshot(session, txn):
    session.flush()
    return encode({
        "transaction": _values(txn),
        "explanation": _values(session.get(m.BankTransactionExplanation, txn.explanation_id))
                       if txn.explanation_id else None,
        "allocations": [_values(a) for a in session.scalars(
            select(m.BankTransactionAllocation)
            .where(m.BankTransactionAllocation.financial_transaction_id == txn.id)
            .order_by(m.BankTransactionAllocation.allocation_index, m.BankTransactionAllocation.id))],
    })


def fingerprint(session, rows):
    """Bind the reviewed plan to movements, catalogs, competing rules and matches."""
    session.flush()
    ids = [r.id for r in rows]
    explanations = {e.id: e for e in session.scalars(select(m.BankTransactionExplanation).where(
        m.BankTransactionExplanation.id.in_([r.txn.explanation_id for r in rows if r.txn.explanation_id])))}
    allocations = {}
    for a in session.scalars(select(m.BankTransactionAllocation).where(
            m.BankTransactionAllocation.financial_transaction_id.in_(ids))
            .order_by(m.BankTransactionAllocation.allocation_index, m.BankTransactionAllocation.id)):
        allocations.setdefault(a.financial_transaction_id, []).append(_values(a))
    data = {"rows": [{"transaction": _values(r.txn),
                      "explanation": _values(explanations.get(r.txn.explanation_id)),
                      "allocations": allocations.get(r.id, [])} for r in rows]}
    for cls in (m.BankOccurrence, m.BankTransactionReason, m.BankAccountingClassification,
                m.ReportingEntity, m.FinancialTransactionMatch):
        data[cls.__tablename__] = [_values(x) for x in session.scalars(select(cls).order_by(cls.id))]
    return hashlib.sha256(encode(data).encode()).hexdigest()


def serialize_application(app):
    return {
        "id": app.id, "rule_id": app.rule_id, "mode": app.application_mode,
        "started_at": str(app.started_at), "updated": app.updated,
        "rolled_back_at": str(app.rolled_back_at) if app.rolled_back_at else None,
        "can_rollback": not app.rolled_back_at and any(
            i.outcome == "UPDATED" and i.before_state and i.after_state for i in app.items),
        "items": [{"id": i.financial_transaction_id, "outcome": i.outcome,
                   "who_before": i.who_before, "who_after": i.who_after,
                   "why_before": i.why_before, "why_after": i.why_after,
                   "for_whom_before": i.for_whom_before, "for_whom_after": i.for_whom_after,
                   "rollback": i.rollback_outcome} for i in app.items],
    }


def lock_writes(session):
    """SQLite compare+restore requires a writer lock before reading the snapshot."""
    connection = session.connection()
    if connection.dialect.name == "sqlite":
        raw = connection.connection.driver_connection
        if not raw.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            # The shared engine starts transactions with BEGIN. Acquire its
            # writer lock before reading anything we may compare-and-restore.
            connection.exec_driver_sql("UPDATE bank_ai_rule_applications SET id=id WHERE 0")


def _typed(cls, values, *, omit=()):
    result = {}
    for col in cls.__table__.columns:
        if col.name in omit or col.name not in values:
            continue
        value = values[col.name]
        if value is not None and isinstance(col.type, DateTime):
            value = datetime.fromisoformat(value)
        elif value is not None and isinstance(col.type, Date):
            value = date.fromisoformat(value)
        result[col.name] = value
    return result


def restore_snapshot(session, txn, before_state, after_state, note):
    """Compare the full recorded result before restoring mutable classifications."""
    if not after_state or snapshot(session, txn) != after_state:
        return False
    before, after = json.loads(before_state), json.loads(after_state)
    # Preserve the immutable decision chain: restore by inserting a new decision.
    if before["explanation"] != after["explanation"]:
        previous = before["explanation"]
        if previous:
            values = _typed(m.BankTransactionExplanation, previous,
                            omit=("id", "created_at", "updated_at"))
            values["explanation_notes"] = (values.get("explanation_notes") or "") + (
                " " + note)
        else:
            values = dict(financial_transaction_id=txn.id, decision_source="HUMAN",
                          decision_status="NEEDS_HUMAN_REVIEW",
                          explanation_notes=note + " Previously unclassified.")
        decision = m.BankTransactionExplanation(**values)
        session.add(decision)
        session.flush()
        txn.explanation_id = decision.id
    if before["allocations"] != after["allocations"]:
        session.execute(delete(m.BankTransactionAllocation).where(
            m.BankTransactionAllocation.financial_transaction_id == txn.id))
        for previous in before["allocations"]:
            session.add(m.BankTransactionAllocation(**_typed(
                m.BankTransactionAllocation, previous, omit=("id", "created_at", "updated_at"))))
    # A rule may withdraw acceptance. Never restore source/amount/date fields.
    for field in ("review_status", "classification"):
        if before["transaction"][field] != after["transaction"][field]:
            setattr(txn, field, before["transaction"][field])
    session.flush()
    return True


def rollback_application(session, application_id, account_id=None):
    lock_writes(session)
    app = session.scalar(select(m.BankAiRuleApplication).where(
        m.BankAiRuleApplication.id == application_id).with_for_update())
    if app is None:
        raise ValueError("Application not found.")
    eligible = [i for i in app.items if i.outcome == "UPDATED"]
    if not eligible or not any(i.before_state and i.after_state for i in eligible):
        raise ValueError("This historical application has no rollback snapshots.")
    if app.rolled_back_at:
        return {"ok": True, "already_rolled_back": True, "restored": 0, "skipped": [],
                "application_id": app.id}
    restored, skipped = 0, []
    for item in eligible:
        txn = session.scalar(select(m.FinancialTransaction).where(
            m.FinancialTransaction.id == item.financial_transaction_id).with_for_update())
        # Lock child records too on PostgreSQL. SQLite already holds the writer lock.
        if txn:
            list(session.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == txn.id).with_for_update()))
            if txn.explanation_id:
                session.scalar(select(m.BankTransactionExplanation).where(
                    m.BankTransactionExplanation.id == txn.explanation_id).with_for_update())
        if not txn or not item.after_state or snapshot(session, txn) != item.after_state:
            item.rollback_outcome = "SKIPPED_LATER_CHANGE"
            skipped.append({"id": item.financial_transaction_id,
                            "reason": "Movement, decision or allocation changed after this application."})
            continue
        restore_snapshot(session, txn, item.before_state, item.after_state,
                         f"Rollback of AI rule application #{app.id}, requested by account {account_id}.")
        item.rollback_outcome = "RESTORED"
        restored += 1
        session.flush()
    app.rolled_back_at = datetime.now(timezone.utc)
    app.rolled_back_by_account_id = account_id
    session.flush()
    return {"ok": True, "application_id": app.id, "restored": restored, "skipped": skipped}
