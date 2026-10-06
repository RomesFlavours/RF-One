"""General (structural) WHO rules — level 1 of Bank WHO recognition
(BANK_GENERAL_RULES_001).

    level 1  GENERAL RULE   where a family of descriptions carries the WHO:
                            the text BETWEEN two markers. One rule, many
                            WHO candidates. (`BankGeneralRule`)
    level 2  WHO RULE       a fixed phrase names one fixed WHO.
                            (`BankRecognitionRule`, `who_rules`)

A candidate is only ever a NAME. It becomes a WHO exclusively through the
one canonical resolution, `who_recognition.CanonicalWhoResolver.resolve`
(an approved description rule, then the active canonical name, then an
active alias) — nothing here creates a WHO, fuzzy-matches a name, or reads
or writes a WHY. A candidate that resolves to nothing stays a *suggested
WHO*: the transaction keeps its current decision and stays To Reconcile.

When a candidate resolves, the transaction's WHO is recorded as a RULE
decision carrying its current WHY / WHAT unchanged — the same way the simple
WHO rule records a WHO (`who_rules._apply_to_transaction`) — so it moves to
Reconciled even while its WHY is still open. Never overwritten:

  * a HUMAN decision;
  * a decision produced by a Reconciliation Standard;
  * a decision that already names a DIFFERENT WHO (authoritative existing
    assignment) — reported as a protected conflict;
  * an own-account movement (STRUCTURAL recognition, a confirmed internal
    transfer, or a candidate that is one of RF-One's own legal entities),
    which has no external WHO by design.

Two entry points write: `apply_rule` (existing transactions, an explicit
operator action) and `apply_to_new_transaction` (called by the import, right
after the automatic decision and before Standards). `preview` writes
nothing. Every function flushes and never commits.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import recognition
from . import who_recognition as wr
from .who_rules import _PURPOSE_FIELDS

ACTIVE, INACTIVE = "ACTIVE", "INACTIVE"
MAX_MARKER = 80
MAX_NAME = 120
_SPACES = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Extraction — a pure function
# ---------------------------------------------------------------------------


def extract(text: str | None, start_marker: str, end_marker: str) -> str | None:
    """The text strictly between `start_marker` and the first `end_marker`
    after it, case-insensitive, trimmed, inner whitespace collapsed. None
    when either marker is missing or nothing lies between them."""
    if not text or not start_marker or not end_marker:
        return None
    upper = text.upper()
    start = upper.find(start_marker.upper())
    if start < 0:
        return None
    begin = start + len(start_marker)
    end = upper.find(end_marker.upper(), begin)
    if end < 0:
        return None
    value = _SPACES.sub(" ", text[begin:end]).strip()
    return value or None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def rules(session: Session) -> list["m.BankGeneralRule"]:
    return list(session.scalars(select(m.BankGeneralRule).order_by(m.BankGeneralRule.id)))


def active_rules(session: Session) -> list["m.BankGeneralRule"]:
    return [r for r in rules(session) if r.status == ACTIVE]


def _clean(value: str | None, label: str, limit: int) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{label} is required.")
    if len(value) > limit:
        raise ValueError(f"{label} is longer than {limit} characters.")
    return value


def save_rule(session: Session, *, rule_id: int | None, name: str | None, start_marker: str | None,
              end_marker: str | None, active: bool, account_id: int | None) -> "m.BankGeneralRule":
    """Create (`rule_id` None) or edit a General Rule. Saving configures
    FUTURE imports only; existing transactions change only through Apply."""
    name = _clean(name, "Name", MAX_NAME)
    # Markers keep their inner spacing exactly as written; only the ends are trimmed.
    start_marker = _clean(start_marker, "Starts after", MAX_MARKER)
    end_marker = _clean(end_marker, "Ends before", MAX_MARKER)
    if start_marker.casefold() == end_marker.casefold():
        raise ValueError("Starts after and Ends before must be different markers.")
    clash = session.scalars(select(m.BankGeneralRule).where(m.BankGeneralRule.name == name)).first()
    if clash is not None and clash.id != rule_id:
        raise ValueError(f"A General Rule named {name!r} already exists.")
    if rule_id is None:
        rule = m.BankGeneralRule(source_field=m.GENERAL_RULE_SOURCE_DESCRIPTION, created_by_account_id=account_id)
        session.add(rule)
    else:
        rule = session.get(m.BankGeneralRule, rule_id)
        if rule is None:
            raise ValueError("That General Rule does not exist.")
    rule.name, rule.start_marker, rule.end_marker = name, start_marker, end_marker
    rule.status = ACTIVE if active else INACTIVE
    session.flush()
    return rule


def set_active(session: Session, *, rule_id: int, active: bool) -> "m.BankGeneralRule":
    rule = session.get(m.BankGeneralRule, rule_id)
    if rule is None:
        raise ValueError("That General Rule does not exist.")
    rule.status = ACTIVE if active else INACTIVE
    session.flush()
    return rule


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class GeneralRuleResult:
    rule_name: str
    applied: bool = False
    scanned: int = 0
    matches: int = 0
    resolved: int = 0
    newly_assigned: int = 0
    already: int = 0
    unknown: int = 0
    protected_human: int = 0
    protected_standard: int = 0
    protected_other_who: int = 0
    own_account: int = 0
    candidates: Counter = field(default_factory=Counter)
    unknown_candidates: Counter = field(default_factory=Counter)

    @property
    def protected(self) -> int:
        return self.protected_human + self.protected_standard + self.protected_other_who

    def as_dict(self, top: int = 40) -> dict:
        return {
            "rule_name": self.rule_name, "applied": self.applied, "scanned": self.scanned,
            "matches": self.matches, "distinct_candidates": len(self.candidates),
            "resolved": self.resolved, "newly_assigned": self.newly_assigned, "already": self.already,
            "unknown": self.unknown, "unknown_distinct": len(self.unknown_candidates),
            "protected": self.protected, "protected_human": self.protected_human,
            "protected_standard": self.protected_standard, "protected_other_who": self.protected_other_who,
            "own_account": self.own_account,
            "unknown_candidates": self.unknown_candidates.most_common(top),
        }


class _Context:
    """What evaluating needs once per pass, not once per transaction: the
    canonical resolver and RF-One's own legal-entity keys."""

    def __init__(self, session: Session):
        self.resolver = wr.CanonicalWhoResolver(session)
        _registered, self.entities, _lookups = wr.build_contexts(session)

    def own_entity(self, candidate: str) -> bool:
        return wr.legal_entity_key(wr.normalize_who_name(candidate)) in self.entities

    def resolve(self, candidate: str, txn_description: str | None, amount: int | None,
                instrument_id: int | None) -> "wr.WhoResolution":
        return self.resolver.resolve(wr.normalize_who_name(candidate), description=txn_description,
                                     amount_minor=amount, instrument_id=instrument_id)


def _own_account_ids(session: Session) -> set[int]:
    structural = set(session.scalars(select(m.BankWhoRecognition.financial_transaction_id).where(
        m.BankWhoRecognition.recognizer_version == wr.RECOGNIZER_VERSION,
        m.BankWhoRecognition.tier == wr.STRUCTURAL)))
    for a, b in session.execute(select(m.FinancialTransactionMatch.transaction_a_id,
                                       m.FinancialTransactionMatch.transaction_b_id)):
        structural.update((a, b))
    return structural


def _record_who(session: Session, txn: "m.FinancialTransaction", current, occurrence: "m.BankOccurrence",
                rule: "m.BankGeneralRule", candidate: str, how: str | None, note_prefix: str) -> None:
    """A RULE decision naming the resolved WHO, with the current WHY / WHAT
    carried over unchanged (or none, when there was no decision)."""
    row = recognition._create_decision_row(
        session, txn, occurrence_id=occurrence.id,
        transaction_reason_id=current.transaction_reason_id if current is not None else None,
        recognition_rule_id=None, decision_source="RULE",
        decision_status=current.decision_status if current is not None else "NEEDS_HUMAN_REVIEW",
        confidence=current.confidence if current is not None else None,
        explanation_notes=(
            f"{note_prefix} General Rule #{rule.id} {rule.name!r} extracted {candidate!r} between "
            f"{rule.start_marker!r} and {rule.end_marker!r}; resolved to WHO {occurrence.canonical_name!r} "
            f"by {how or 'canonical resolution'}. WHO only: "
            + (f"Why, What and status carried over unchanged from decision #{current.id}."
               if current is not None else "no previous decision; the Why stays for a human.")
        ),
        accounting_destination_source=(current.accounting_destination_source
                                       if current is not None else m.DESTINATION_SOURCE_WHY),
    )
    for name in _PURPOSE_FIELDS:
        setattr(row, name, getattr(current, name) if current is not None else None)


def _evaluate(session: Session, rule: "m.BankGeneralRule", *, write: bool,
              account_id: int | None) -> GeneralRuleResult:
    result = GeneralRuleResult(rule_name=rule.name, applied=write)
    ctx = _Context(session)
    own = _own_account_ids(session)
    rows = session.execute(select(
        m.FinancialTransaction.id, m.FinancialTransaction.description_original, m.FinancialTransaction.amount_minor,
        m.FinancialTransaction.payment_instrument_id, m.FinancialTransaction.explanation_id,
    ).order_by(m.FinancialTransaction.id)).all()
    explanations = {e.id: e for e in session.scalars(select(m.BankTransactionExplanation).where(
        m.BankTransactionExplanation.id.in_([r[4] for r in rows if r[4] is not None] or [-1])))}
    for tx_id, description, amount, instrument_id, explanation_id in rows:
        result.scanned += 1
        candidate = extract(description, rule.start_marker, rule.end_marker)
        if candidate is None:
            continue
        result.matches += 1
        result.candidates[candidate] += 1
        if tx_id in own or ctx.own_entity(candidate):
            result.own_account += 1
            continue
        resolution = ctx.resolve(candidate, description, amount, instrument_id)
        if resolution.occurrence is None:
            result.unknown += 1
            result.unknown_candidates[candidate] += 1
            continue
        result.resolved += 1
        current = explanations.get(explanation_id)
        occurrence = resolution.occurrence
        if current is not None and current.occurrence_id == occurrence.id:
            result.already += 1
        elif current is not None and current.decision_source == "HUMAN":
            result.protected_human += 1
        elif current is not None and current.reconciliation_standard_id is not None:
            result.protected_standard += 1
        elif current is not None and current.occurrence_id is not None:
            result.protected_other_who += 1
        else:
            result.newly_assigned += 1
            if write:
                _record_who(session, session.get(m.FinancialTransaction, tx_id), current, occurrence, rule,
                            candidate, resolution.how,
                            f"General Rule applied to existing transactions by account {account_id}.")
    if write:
        rule.last_applied_at = datetime.now(UTC)
        session.flush()
    return result


def match_counts(session: Session, rules_: list["m.BankGeneralRule"]) -> dict[int, tuple[int, int]]:
    """{rule id: (matching transactions, distinct candidates)} — one pass
    over the descriptions, text only: cheap enough for every page view."""
    found: dict[int, Counter] = {r.id: Counter() for r in rules_}
    if rules_:
        for (description,) in session.execute(select(m.FinancialTransaction.description_original)):
            for rule in rules_:
                candidate = extract(description, rule.start_marker, rule.end_marker)
                if candidate is not None:
                    found[rule.id][candidate] += 1
    return {rid: (sum(c.values()), len(c)) for rid, c in found.items()}


def preview(session: Session, rule: "m.BankGeneralRule") -> GeneralRuleResult:
    """What Apply would do, writing nothing."""
    return _evaluate(session, rule, write=False, account_id=None)


def apply_rule(session: Session, *, rule_id: int, account_id: int | None) -> GeneralRuleResult:
    """Apply one ACTIVE General Rule to every existing transaction."""
    rule = session.get(m.BankGeneralRule, rule_id)
    if rule is None:
        raise ValueError("That General Rule does not exist.")
    if rule.status != ACTIVE:
        raise ValueError("Activate the General Rule before applying it.")
    return _evaluate(session, rule, write=True, account_id=account_id)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class ImportContext:
    """Built once per import pass (None when no General Rule is active)."""

    def __init__(self, session: Session, active: list["m.BankGeneralRule"]):
        self.rules = active
        self.ctx = _Context(session)


def import_context(session: Session) -> ImportContext | None:
    active = active_rules(session)
    return ImportContext(session, active) if active else None


def apply_to_new_transaction(session: Session, txn: "m.FinancialTransaction",
                             context: ImportContext | None) -> bool:
    """The import step, run right after the automatic decision: when that
    decision names no WHO, the first ACTIVE General Rule whose markers are in
    the description and whose candidate resolves records the WHO. A WHO a
    level-2 rule already named is never replaced. True when a WHO was
    recorded."""
    if context is None:
        return False
    current = recognition.get_current_explanation(session, financial_transaction_id=txn.id)
    if current is not None and (current.occurrence_id is not None or current.decision_source == "HUMAN"
                                or current.reconciliation_standard_id is not None):
        return False
    for rule in context.rules:
        candidate = extract(txn.description_original, rule.start_marker, rule.end_marker)
        if candidate is None:
            continue
        if context.ctx.own_entity(candidate):
            return False
        resolution = context.ctx.resolve(candidate, txn.description_original, txn.amount_minor,
                                         txn.payment_instrument_id)
        if resolution.occurrence is None:
            continue
        _record_who(session, txn, current, resolution.occurrence, rule, candidate, resolution.how,
                    "General Rule at import.")
        session.flush()
        return True
    return False
