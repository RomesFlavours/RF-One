"""Merge two WHO (BANK_WHO_MERGE_001).

A person chooses the WHO to KEEP and the WHO to ABSORB. `preview` says,
writing nothing, what will move and which settings conflict; `merge` moves
every reference from the absorbed WHO to the kept one, in the caller's ONE
database transaction (it flushes, never commits):

  * decisions (`BankTransactionExplanation.occurrence_id`, every version —
    reconciled transactions included; their name snapshots are history and
    stay as recorded), evidence bypass authorizations;
  * aliases, possible WHY, entities served and supplier links — merged
    without duplicates (a pair the kept WHO already has keeps its row; a
    WHY association adds its confirmations).

The absorbed WHO's own name becomes a MERGED_WHO_NAME alias of the kept WHO
— so the kept WHO is found under the old name — and the absorbed WHO is
marked INACTIVE (never deleted), which removes it from every WHO choice.
(The old rule system's recognition rules, WHO recognitions, WHY rules,
Standards and learning suggestions, which a merge also moved, were removed
by BANK_RULES_RESET_001.)

Settings that cannot both survive are never chosen silently: two different
default WHY must be decided by the person (`default_reason_id`), otherwise
`merge` refuses. (The Manual Only flag, BANK_WHO_MANUAL_ONLY_001, only kept a
WHO out of the old WHO Rules and Classification Learning; it went with them.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models as m
from . import who_recognition as wr
from . import why_catalog

MERGED_WHO_NAME = "MERGED_WHO_NAME"   # the alias family of a merged WHO's old name

# Tables whose rows simply move to the kept WHO (no uniqueness on the WHO).
_MOVED = (
    ("decisions", m.BankTransactionExplanation),
    ("bypass_authorizations", m.BankEvidenceBypassAuthorization),
)


@dataclass
class MergeConflict:
    key: str            # "default_why"
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
        "aliases": _count(session, m.BankOccurrenceAlias, absorb.id),
        "possible_why": session.scalar(select(func.count()).select_from(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == absorb.id,
            m.BankOccurrenceReasonAssociation.active.is_(True))) or 0,
        "entities": _count(session, m.BankOccurrenceReportingEntity, absorb.id),
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


def merge(session: Session, *, keep_id: int | None, absorb_id: int | None, default_reason_id: int | None = None,
          account_id: int | None = None) -> MergeResult:
    keep, absorb = _pair(session, keep_id, absorb_id)
    for conflict in conflicts(session, keep, absorb):
        if conflict.key == "default_why":
            if default_reason_id not in (keep.default_transaction_reason_id, absorb.default_transaction_reason_id):
                raise ValueError("Choose which default WHY the kept WHO keeps.")
    moved: dict[str, int] = {}

    for label, model in _MOVED:
        moved[label] = session.execute(
            update(model).where(model.occurrence_id == absorb.id).values(occurrence_id=keep.id)
            .execution_options(synchronize_session=False)).rowcount or 0

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

    # Settings: the person's choice where both cannot survive.
    if default_reason_id is not None and default_reason_id in (keep.default_transaction_reason_id,
                                                              absorb.default_transaction_reason_id):
        keep.default_transaction_reason_id = default_reason_id
    elif keep.default_transaction_reason_id is None and absorb.default_transaction_reason_id is not None:
        keep.default_transaction_reason_id = absorb.default_transaction_reason_id

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    note = f"Merged into '{keep.canonical_name}' (#{keep.id}) on {stamp} by account {account_id}."
    absorb.optional_notes = f"{absorb.optional_notes}\n{note}" if absorb.optional_notes else note
    absorb.status = "INACTIVE"
    absorb.default_transaction_reason_id = None
    session.flush()
    why_catalog.sync_single_default(session, keep.id)
    session.flush()
    return MergeResult(keep_name=keep.canonical_name, absorb_name=absorb.canonical_name, moved=moved)
