"""Merge two WHO (BANK_WHO_MERGE_001).

A person chooses the WHO to KEEP and the WHO to ABSORB. `preview` says,
writing nothing, what will move and which settings conflict; `merge` moves
every reference from the absorbed WHO to the kept one, in the caller's ONE
database transaction (it flushes, never commits):

  * decisions (`BankTransactionExplanation.occurrence_id`, every version —
    reconciled transactions included; their name snapshots are history and
    stay as recorded), WHO recognitions, recognition rules, WHY rules,
    Reconciliation Standards, evidence bypass authorizations;
  * aliases, possible WHY, entities served and supplier links — merged
    without duplicates (a pair the kept WHO already has keeps its row; a
    WHY association adds its confirmations);
  * pending learning suggestions that name the absorbed WHO.

A recognition rule the kept WHO already has in the same form is kept for
history but deactivated, so no duplicate rule stays active. The absorbed
WHO's own name becomes a MERGED_WHO_NAME alias of the kept WHO — so the
recognition finds the kept WHO under the old name — and the absorbed WHO is
marked INACTIVE (never deleted), which removes it from every WHO choice.

Settings that cannot both survive are never chosen silently: two different
default WHY, or a different Manual Only flag, must be decided by the person
(`default_reason_id`, `manual_only`), otherwise `merge` refuses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models as m
from . import who_recognition as wr
from . import why_catalog

MERGED_WHO_NAME = "MERGED_WHO_NAME"   # the same alias family the WHO Rule merge uses

# Tables whose rows simply move to the kept WHO (no uniqueness on the WHO).
_MOVED = (
    ("decisions", m.BankTransactionExplanation),
    ("who_recognitions", m.BankWhoRecognition),
    ("why_rules", m.BankWhyRule),
    ("standards", m.BankReconciliationStandard),
    ("bypass_authorizations", m.BankEvidenceBypassAuthorization),
)


@dataclass
class MergeConflict:
    key: str            # "default_why" | "manual_only"
    label: str
    choices: list = field(default_factory=list)   # [(value, label)]


def _pair(session: Session, keep_id: int | None, absorb_id: int | None):
    if not keep_id or not absorb_id:
        raise ValueError("Choose the WHO to keep and the WHO to absorb.")
    if keep_id == absorb_id:
        raise ValueError("Choose two different WHO.")
    keep = session.get(m.BankOccurrence, keep_id)
    absorb = session.get(m.BankOccurrence, absorb_id)
    if keep is None or absorb is None:
        raise ValueError("One of the two WHO does not exist.")
    if keep.status != "ACTIVE":
        raise ValueError(f"The WHO to keep, “{keep.canonical_name}”, is inactive.")
    if absorb.status != "ACTIVE":
        raise ValueError(f"“{absorb.canonical_name}” is already inactive (merged): nothing to absorb.")
    return keep, absorb


def _count(session: Session, model, occurrence_id: int) -> int:
    return session.scalar(select(func.count()).select_from(model).where(model.occurrence_id == occurrence_id)) or 0


def _reason_name(session: Session, reason_id: int | None) -> str:
    reason = session.get(m.BankTransactionReason, reason_id) if reason_id else None
    return reason.name if reason else "—"


def conflicts(session: Session, keep: "m.BankOccurrence", absorb: "m.BankOccurrence") -> list[MergeConflict]:
    out = []
    if (keep.default_transaction_reason_id and absorb.default_transaction_reason_id
            and keep.default_transaction_reason_id != absorb.default_transaction_reason_id):
        out.append(MergeConflict("default_why", "Both WHO have a different default WHY: which one stays?", [
            (keep.default_transaction_reason_id,
             f"{_reason_name(session, keep.default_transaction_reason_id)} (of {keep.canonical_name})"),
            (absorb.default_transaction_reason_id,
             f"{_reason_name(session, absorb.default_transaction_reason_id)} (of {absorb.canonical_name})"),
        ]))
    if bool(keep.manual_only) != bool(absorb.manual_only):
        out.append(MergeConflict("manual_only", "One WHO is Manual Only and the other is not: which setting stays?", [
            ("1" if keep.manual_only else "0", f"{'Manual Only' if keep.manual_only else 'Not Manual Only'} (of {keep.canonical_name})"),
            ("1" if absorb.manual_only else "0", f"{'Manual Only' if absorb.manual_only else 'Not Manual Only'} (of {absorb.canonical_name})"),
        ]))
    return out


def preview(session: Session, *, keep_id: int | None, absorb_id: int | None) -> dict:
    """What `merge` would do — writes nothing."""
    keep, absorb = _pair(session, keep_id, absorb_id)
    transactions = session.scalar(
        select(func.count(m.FinancialTransaction.id))
        .join(m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
        .where(m.BankTransactionExplanation.occurrence_id == absorb.id)) or 0
    impact = {
        "transactions": transactions,
        "decisions": _count(session, m.BankTransactionExplanation, absorb.id),
        "rules": _count(session, m.BankRecognitionRule, absorb.id),
        "aliases": _count(session, m.BankOccurrenceAlias, absorb.id),
        "possible_why": session.scalar(select(func.count()).select_from(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == absorb.id,
            m.BankOccurrenceReasonAssociation.active.is_(True))) or 0,
        "entities": _count(session, m.BankOccurrenceReportingEntity, absorb.id),
        "standards": _count(session, m.BankReconciliationStandard, absorb.id),
        "why_rules": _count(session, m.BankWhyRule, absorb.id),
        "recognitions": _count(session, m.BankWhoRecognition, absorb.id),
        "suppliers": _count(session, m.BankOccurrenceSupplier, absorb.id),
    }
    return {
        "keep": {"id": keep.id, "name": keep.canonical_name},
        "absorb": {"id": absorb.id, "name": absorb.canonical_name},
        "impact": impact,
        "conflicts": [{"key": c.key, "label": c.label, "choices": [[str(v), lbl] for v, lbl in c.choices]}
                      for c in conflicts(session, keep, absorb)],
    }


@dataclass
class MergeResult:
    keep_name: str
    absorb_name: str
    moved: dict
    rules_deactivated: int = 0


def _rule_shape(rule: "m.BankRecognitionRule") -> tuple:
    return (rule.match_type, rule.normalized_pattern, rule.literal_pattern, rule.match_field,
            rule.payment_instrument_id, rule.direction, rule.determines_purpose, rule.transaction_reason_id)


def merge(session: Session, *, keep_id: int | None, absorb_id: int | None, default_reason_id: int | None = None,
          manual_only: bool | None = None, account_id: int | None = None) -> MergeResult:
    keep, absorb = _pair(session, keep_id, absorb_id)
    for conflict in conflicts(session, keep, absorb):
        if conflict.key == "default_why":
            if default_reason_id not in (keep.default_transaction_reason_id, absorb.default_transaction_reason_id):
                raise ValueError("Choose which default WHY the kept WHO keeps.")
        elif conflict.key == "manual_only" and manual_only is None:
            raise ValueError("Choose whether the kept WHO is Manual Only.")
    moved: dict[str, int] = {}

    for label, model in _MOVED:
        moved[label] = session.execute(
            update(model).where(model.occurrence_id == absorb.id).values(occurrence_id=keep.id)
            .execution_options(synchronize_session=False)).rowcount or 0

    # Recognition rules: moved; one the kept WHO already has in the same form stays for history, inactive.
    kept_shapes = {_rule_shape(r) for r in session.scalars(select(m.BankRecognitionRule).where(
        m.BankRecognitionRule.occurrence_id == keep.id, m.BankRecognitionRule.status == "ACTIVE"))}
    deactivated = 0
    rules = list(session.scalars(select(m.BankRecognitionRule).where(m.BankRecognitionRule.occurrence_id == absorb.id)))
    for rule in rules:
        if rule.status == "ACTIVE" and _rule_shape(rule) in kept_shapes:
            rule.status = "INACTIVE"
            rule.auto_apply_enabled = False
            deactivated += 1
        rule.occurrence_id = keep.id
        if rule.status == "ACTIVE":
            kept_shapes.add(_rule_shape(rule))
    moved["rules"] = len(rules)

    # Aliases: no duplicate (occurrence, text, family).
    have = {(a.alias_text, a.source_family) for a in session.scalars(select(m.BankOccurrenceAlias).where(
        m.BankOccurrenceAlias.occurrence_id == keep.id))}
    aliases = 0
    for alias in list(session.scalars(select(m.BankOccurrenceAlias).where(m.BankOccurrenceAlias.occurrence_id == absorb.id))):
        if (alias.alias_text, alias.source_family) in have:
            session.delete(alias)
        else:
            alias.occurrence_id = keep.id
            have.add((alias.alias_text, alias.source_family))
        aliases += 1
    if (absorb.canonical_name, MERGED_WHO_NAME) not in have:
        session.add(m.BankOccurrenceAlias(
            occurrence_id=keep.id, alias_text=absorb.canonical_name[:255],
            alias_key=wr.who_key(absorb.canonical_name)[:255], source_family=MERGED_WHO_NAME, source="HUMAN"))
    moved["aliases"] = aliases

    # Possible WHY: one row per pair; confirmations add up.
    kept_assoc = {a.transaction_reason_id: a for a in session.scalars(select(m.BankOccurrenceReasonAssociation).where(
        m.BankOccurrenceReasonAssociation.occurrence_id == keep.id))}
    count = 0
    for row in list(session.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == absorb.id))):
        target = kept_assoc.get(row.transaction_reason_id)
        if target is None:
            row.occurrence_id = keep.id
        else:
            target.active = target.active or row.active
            target.confirmation_count = (target.confirmation_count or 0) + (row.confirmation_count or 0)
            firsts = [d for d in (target.first_confirmed_at, row.first_confirmed_at) if d]
            lasts = [d for d in (target.last_confirmed_at, row.last_confirmed_at) if d]
            target.first_confirmed_at = min(firsts) if firsts else None
            target.last_confirmed_at = max(lasts) if lasts else None
            session.delete(row)
        count += 1
    moved["possible_why"] = count

    # Entities served and supplier links: no duplicate pair.
    for label, model, key in (("entities", m.BankOccurrenceReportingEntity, "reporting_entity_id"),
                              ("suppliers", m.BankOccurrenceSupplier, "supplier_id")):
        kept_keys = set(session.scalars(select(getattr(model, key)).where(model.occurrence_id == keep.id)))
        n = 0
        for row in list(session.scalars(select(model).where(model.occurrence_id == absorb.id))):
            if getattr(row, key) in kept_keys:
                session.delete(row)
            else:
                row.occurrence_id = keep.id
                kept_keys.add(getattr(row, key))
            n += 1
        moved[label] = n

    # Pending learning suggestions that name the absorbed WHO.
    n = 0
    for suggestion in session.scalars(select(m.BankPatternSuggestion).where(m.BankPatternSuggestion.status == "SUGGESTED")):
        try:
            proposal = json.loads(suggestion.proposal or "{}")
        except ValueError:
            continue
        if isinstance(proposal, dict) and proposal.get("who_id") == absorb.id:
            proposal["who_id"] = keep.id
            suggestion.proposal = json.dumps(proposal)
            n += 1
    moved["suggestions"] = n

    # Settings: the person's choice where both cannot survive.
    if default_reason_id is not None and default_reason_id in (keep.default_transaction_reason_id,
                                                              absorb.default_transaction_reason_id):
        keep.default_transaction_reason_id = default_reason_id
    elif keep.default_transaction_reason_id is None and absorb.default_transaction_reason_id is not None:
        keep.default_transaction_reason_id = absorb.default_transaction_reason_id
    if manual_only is not None and bool(keep.manual_only) != bool(absorb.manual_only):
        keep.manual_only = bool(manual_only)

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    note = f"Merged into '{keep.canonical_name}' (#{keep.id}) on {stamp} by account {account_id}."
    absorb.optional_notes = f"{absorb.optional_notes}\n{note}" if absorb.optional_notes else note
    absorb.status = "INACTIVE"
    absorb.manual_only = False
    absorb.default_transaction_reason_id = None
    session.flush()
    why_catalog.sync_single_default(session, keep.id)
    session.flush()
    return MergeResult(keep_name=keep.canonical_name, absorb_name=absorb.canonical_name, moved=moved,
                       rules_deactivated=deactivated)
