"""General (structural) WHO rules — level 1 of Bank WHO recognition
(BANK_GENERAL_RULES_001).

    level 1  GENERAL RULE   where a family of descriptions carries the WHO:
                            the text BETWEEN two markers. One rule, many
                            WHO candidates. (`BankGeneralRule`)
    level 2  WHO RULE       a fixed phrase names one fixed WHO.
                            (`BankRecognitionRule`, `who_rules`)

A candidate is a NAME taken from the transaction. It is first resolved by
the one canonical resolution, `who_recognition.CanonicalWhoResolver.resolve`
(an approved description rule, then the active canonical name, then an
active alias). BANK_GENERAL_RULES_CREATE_WHO_001 (Product Owner, 2026-10-08,
superseding the "never creates a WHO" constraint of BANK_GENERAL_RULES_001):
a valid name that resolves to nothing is CREATED as an active Counterparty
WHO — through the Configuration service, with the identity checks of the
WHO registry (`who_rules.check_new_who`: same name / identity key / alias is
the SAME WHO, never a duplicate; a merged WHO's name or an invalid name is
refused) — and assigned. Only similar-looking names are never merged.
A WHO is created only for a transaction that can receive it (none of the
protections below applies), in the caller's one transaction with its
assignment. Nothing here fuzzy-matches a name or reads or writes a WHY, and
no other rule is created.

The transaction's WHO is recorded as a RULE decision carrying its current
WHY / WHAT unchanged — the same way the simple WHO rule records a WHO
(`who_rules._apply_to_transaction`) — so it moves to Reconciled even while
its WHY is still open. Never overwritten:

  * a HUMAN decision;
  * a decision produced by a Reconciliation Standard;
  * a decision that already names a DIFFERENT WHO (authoritative existing
    assignment) — reported as a protected conflict;
  * an own-account movement (STRUCTURAL recognition, a confirmed internal
    transfer, or a candidate that is one of RF-One's own legal entities),
    which has no external WHO by design.

Two entry points write: `apply_rule` (existing transactions, an explicit
operator action) and `apply_to_new_transaction` (called by the import, right
after the automatic decision and before Standards) — the same
`_who_for` decides both. `preview` writes nothing and names the WHO Apply
would create. Every function flushes and never commits.
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
# BANK_GENERAL_RULE_END_001 — the reserved "Ends before" value: extract from
# after "Starts after" to the end of the field. Recognised in any case, its
# outer spaces ignored; stored as "END".
END_MARKER = "END"
MAX_MARKER = 80
MAX_NAME = 120
_SPACES = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Extraction — a pure function
# ---------------------------------------------------------------------------


def is_end_marker(marker: str | None) -> bool:
    """True for the reserved "Ends before" value END (any case, outer spaces
    ignored)."""
    return (marker or "").strip().casefold() == END_MARKER.casefold()


def describe(start_marker: str, end_marker: str) -> str:
    """How a rule extracts, in words — for notes and the page."""
    if is_end_marker(end_marker):
        return f"after {start_marker!r} to the end of the description"
    return f"between {start_marker!r} and {end_marker!r}"


def extract(text: str | None, start_marker: str, end_marker: str) -> str | None:
    """THE extraction — Preview, Apply, the import and the match counts all
    call it. `start_marker` is literal text (an asterisk is an asterisk),
    found case-insensitively.

    * `end_marker` END: everything after `start_marker` to the end of the
      field, with ONLY its leading and trailing spaces removed;
    * any other `end_marker`: the text strictly between `start_marker` and
      the first `end_marker` after it, trimmed, inner whitespace collapsed.

    None when a marker is missing or nothing is left — never an empty WHO."""
    if not text or not start_marker or not end_marker:
        return None
    upper = text.upper()
    start = upper.find(start_marker.upper())
    if start < 0:
        return None
    begin = start + len(start_marker)
    if is_end_marker(end_marker):
        return text[begin:].strip() or None
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
    if is_end_marker(end_marker):
        end_marker = END_MARKER
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
    extraction: str = ""
    scanned: int = 0
    matches: int = 0
    resolved: int = 0
    newly_assigned: int = 0
    already: int = 0
    unknown: int = 0          # names that cannot become a WHO (refused by the registry checks)
    created_assigned: int = 0  # transactions given a WHO created (or, in Preview, to be created) by this pass
    protected_human: int = 0
    protected_standard: int = 0
    protected_other_who: int = 0
    own_account: int = 0
    candidates: Counter = field(default_factory=Counter)
    unknown_candidates: Counter = field(default_factory=Counter)
    refused_reasons: dict = field(default_factory=dict)      # name -> why it cannot become a WHO
    created_who: Counter = field(default_factory=Counter)    # WHO created (Preview: to create) -> transactions
    reused_who: Counter = field(default_factory=Counter)     # existing WHO assigned -> transactions

    @property
    def protected(self) -> int:
        return self.protected_human + self.protected_standard + self.protected_other_who

    @property
    def no_match(self) -> int:
        return self.scanned - self.matches

    def skipped_reasons(self) -> list[tuple[str, int]]:
        """Why every examined transaction that was NOT updated was left as
        it is — each reason actually found, with its count."""
        reasons = [
            ("No WHO extracted: the “Starts after” marker is not in the description, the end marker "
             "is missing after it, or nothing lies between them", self.no_match),
            ("The extracted name cannot become a WHO (too short, too long, or the name of a merged / "
             "inactive WHO)", self.unknown),
            ("This WHO is already on the transaction", self.already),
            ("Protected: classified by a person (manual classification is never overwritten)",
             self.protected_human),
            ("Protected: classified by a Reconciliation Standard", self.protected_standard),
            ("Protected: another WHO is already assigned", self.protected_other_who),
            ("Own-account movement: no external WHO by design", self.own_account),
        ]
        if not self.applied:
            reasons.append(("Would be updated by Apply (Preview writes nothing)", self.newly_assigned))
        return [(label, count) for label, count in reasons if count]

    def as_dict(self, top: int = 40) -> dict:
        updated = self.newly_assigned if self.applied else 0
        return {
            "scope": "Every imported transaction — all periods, all Sources, no page filter.",
            "updated": updated, "unchanged": self.scanned - updated, "no_match": self.no_match,
            "skipped_reasons": self.skipped_reasons(), "extraction": self.extraction,
            "rule_name": self.rule_name, "applied": self.applied, "scanned": self.scanned,
            "matches": self.matches, "distinct_candidates": len(self.candidates),
            "resolved": self.resolved, "newly_assigned": self.newly_assigned, "already": self.already,
            "unknown": self.unknown, "unknown_distinct": len(self.unknown_candidates),
            "protected": self.protected, "protected_human": self.protected_human,
            "protected_standard": self.protected_standard, "protected_other_who": self.protected_other_who,
            "own_account": self.own_account,
            "unknown_candidates": self.unknown_candidates.most_common(top),
            "refused": [(name, count, self.refused_reasons.get(name, ""))
                        for name, count in self.unknown_candidates.most_common(top)],
            "who_created": len(self.created_who), "who_reused": len(self.reused_who),
            "created_assigned": self.created_assigned,
            "created_names": self.created_who.most_common(top),
            "reused_names": self.reused_who.most_common(top),
        }


class _Context:
    """What evaluating needs once per pass, not once per transaction: the
    canonical resolver and RF-One's own legal-entity keys."""

    def __init__(self, session: Session):
        self.session = session
        self.resolver = wr.CanonicalWhoResolver(session)
        _registered, self.entities, _lookups = wr.build_contexts(session)
        # WHO this pass created (or, in Preview, would create), by identity
        # key: the next transaction with the same name reuses it.
        self.created: dict[str, "m.BankOccurrence | str"] = {}
        self.refused: dict[str, str] = {}

    def own_entity(self, candidate: str) -> bool:
        return wr.legal_entity_key(wr.normalize_who_name(candidate)) in self.entities

    def resolve(self, candidate: str, txn_description: str | None, amount: int | None,
                instrument_id: int | None) -> "wr.WhoResolution":
        return self.resolver.resolve(wr.normalize_who_name(candidate), description=txn_description,
                                     amount_minor=amount, instrument_id=instrument_id)


def _who_for(ctx: _Context, candidate: str, description: str | None, amount: int | None,
             instrument_id: int | None, *, write: bool) -> "tuple[m.BankOccurrence | str | None, bool, str | None]":
    """THE WHO of an extracted name, for Apply, Preview and the import:
    (WHO, created_now, refusal). The existing WHO when the name resolves or
    already IS one (registry identity); otherwise a NEW active Counterparty
    WHO created through the Configuration service — or, with `write` False,
    the clean name that Apply would create. (None, False, why) when the name
    cannot become a WHO. Called only for a transaction that can receive it."""
    from . import configuration
    from . import who_rules

    key = wr.who_key(candidate)
    if key in ctx.created:
        return ctx.created[key], False, None
    if key in ctx.refused:
        return None, False, ctx.refused[key]
    resolution = ctx.resolve(candidate, description, amount, instrument_id)
    if resolution.occurrence is not None:
        return resolution.occurrence, False, None
    try:
        existing, clean = who_rules.check_new_who(ctx.session, candidate)
    except ValueError as exc:
        ctx.refused[key] = str(exc)
        return None, False, str(exc)
    if existing is not None:
        return existing, False, None
    if not write:
        ctx.created[key] = clean
        return clean, True, None
    occurrence = configuration.save_who(
        ctx.session, occurrence_id=None, name=clean, active=True, reason_ids=[], default_reason_id=None,
        reporting_entity_ids=[], rules=[],
    )
    ctx.created[key] = occurrence
    return occurrence, True, None


def _protection(current) -> str | None:
    """Why a transaction's current decision must not be replaced."""
    if current is None:
        return None
    if current.decision_source == "HUMAN":
        return "human"
    if current.reconciliation_standard_id is not None:
        return "standard"
    if current.occurrence_id is not None:
        return "other_who"
    return None


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
            f"{note_prefix} General Rule #{rule.id} {rule.name!r} extracted {candidate!r} "
            f"{describe(rule.start_marker, rule.end_marker)}; resolved to WHO {occurrence.canonical_name!r} "
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
    result = GeneralRuleResult(rule_name=rule.name, applied=write,
                               extraction=describe(rule.start_marker, rule.end_marker))
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
        current = explanations.get(explanation_id)
        # The WHO a protected transaction already has (or would get): a
        # protected movement is never changed and gets no WHO created for it.
        protection = _protection(current)
        if protection is not None:
            resolution = ctx.resolve(candidate, description, amount, instrument_id)
            if resolution.occurrence is not None and current.occurrence_id == resolution.occurrence.id:
                result.already += 1
            elif protection == "human":
                result.protected_human += 1
            elif protection == "standard":
                result.protected_standard += 1
            else:
                result.protected_other_who += 1
            continue
        who, created_now, refusal = _who_for(ctx, candidate, description, amount, instrument_id, write=write)
        if who is None:
            result.unknown += 1
            result.unknown_candidates[candidate] += 1
            result.refused_reasons[candidate] = refusal or ""
            continue
        result.resolved += 1
        result.newly_assigned += 1
        name = who if isinstance(who, str) else who.canonical_name
        if created_now or ctx.created.get(wr.who_key(candidate)) is who:
            result.created_who[name] += 1
            result.created_assigned += 1
        else:
            result.reused_who[name] += 1
        if write:
            _record_who(session, session.get(m.FinancialTransaction, tx_id), current, who, rule,
                        candidate, "a WHO created from this name" if created_now else None,
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
    the description records the WHO of its candidate — the existing one, or
    one created from the name exactly as Apply does (`_who_for`). A WHO a
    level-2 rule already named, a HUMAN or Standard decision and an
    own-account movement are never changed. True when a WHO was recorded."""
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
        who, created_now, _refusal = _who_for(context.ctx, candidate, txn.description_original, txn.amount_minor,
                                              txn.payment_instrument_id, write=True)
        if who is None:
            continue
        _record_who(session, txn, current, who, rule, candidate,
                    "a WHO created from this name" if created_now else None, "General Rule at import.")
        session.flush()
        return True
    return False
