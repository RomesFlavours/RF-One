"""The simple WHO Rule (BANK_SIMPLE_WHO_RULE_001).

The operator writes ONE sentence and presses ONE button:

    WHO   ABC
    Rule  "Dove nella descrizione trovi ABC il WHO è ABC"
    Possible WHY  Beer Purchases, Liquor Purchases
    [Apply]

RF-One translates the sentence ONCE, when it is saved, into the existing
deterministic `BankRecognitionRule` semantics — DESCRIPTION, CONTAINS_TEXT,
the recognition normalization of `recognition.normalize_description_for_
recognition` — and never reads the sentence again. Nothing here is a second
matching engine: matching is `recognition._rule_matches` /
`recognition.find_candidate_rules`, the functions import uses, and future
imports reach the same stored rule through `recognition._propose` and
`who_recognition.CanonicalWhoResolver`. No LLM is involved, at save time or
at transaction-processing time.

`apply_who_rule` is the ONE service behind Apply, whichever page it is
pressed on (Classification or Review). In one database transaction it:

A. saves (or reuses) the WHO-only recognition rule;
B. upserts the selected WHO -> possible WHY associations — a list of
   purposes a person may later choose from, never a choice: no WHY is
   applied to any transaction and the WHO's default WHY is never set
   (BANK_WHO_WHY_INVARIANT_001);
C. gives every SAFE existing matching transaction the selected WHO — a
   transaction a person decided (or a human-approved Standard completed)
   is never touched: a different WHO there is counted as a conflict;
D. merges the WHO records that are clearly fragments of the selected WHO,
   with the mechanics of the canonical WHO/WHY import: aliases preserved
   and copied onto the canonical WHO, the fragment's name recorded as a
   MERGED_WHO_NAME alias, live references re-pointed, the fragment marked
   INACTIVE and never deleted. Decision rows are append-only and keep
   their snapshots: a transaction whose current automatic decision named
   a fragment gets a NEW decision naming the canonical WHO, with its WHY,
   WHAT, status and snapshots carried over unchanged;
E. keeps the rule ACTIVE for every future import.

A rule is not a Standard: it names the WHO and nothing else. A transaction
whose WHY is still open stays in review.

Every function flushes and never commits: the caller commits once, or rolls
the whole Apply back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import case, func, select, union
from sqlalchemy.orm import Session

from .. import models as m
from . import recognition
from . import who_recognition as wr
from . import why_catalog

MERGED_WHO_NAME = "MERGED_WHO_NAME"
_RECOGNIZER_NOTE_PREFIX = "Recognised by "
_MIN_PATTERN_CHARACTERS = 3

# ---------------------------------------------------------------------------
# 1. The instruction
# ---------------------------------------------------------------------------

EXAMPLE_INSTRUCTION = "Dove nella descrizione trovi ABC il WHO è ABC"

# "... il WHO è X" / "... the WHO is X" / "... → WHO X". Everything before
# it says where to look; what follows it, if anything, names the WHO.
_WHO_CLAUSE = re.compile(
    r"(?:^|[\s,;:.])(?:allora\s+|then\s+)?(?:il\s+|the\s+)?who\s*"
    r"(?:è|é|e'|e|=|:|is|sarà|sara|diventa|becomes)(?=\s|$|[\"'“«])\s*(?P<who>.*)$"
    r"|(?:→|->|=>)\s*(?:(?:il\s+|the\s+)?who\s*(?:è|é|e|=|:|is)?\s*)?(?P<who_arrow>.*)$",
    re.IGNORECASE,
)
# The verb that introduces the recognition text.
_FIND_VERB = re.compile(
    r"\b(?:trovi|trova|trovo|trovate|si\s+trova|c['’]\s*è|c['’]\s*e|compare|appare|contiene|"
    r"contengono|include|includes|contains|contain|you\s+find|find|finds|appears)\b",
    re.IGNORECASE,
)
_LEADING_FILLER = re.compile(
    r"^(?:la\s+parola|le\s+parole|il\s+testo|la\s+scritta|la\s+frase|the\s+words?|the\s+text|"
    r"the\s+phrase)(?:\s+|$)",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"\"([^\"]*)\"|“([^”]*)”|«([^»]*)»|'([^']*)'")
# Words that, outside quotes, mean the text names more than one phrase.
_SEVERAL = re.compile(r"(?:\s(?:o|oppure|or|e|and|oppure)\s|[,;/|])", re.IGNORECASE)
_STRUCTURE_WORDS = re.compile(r"\b(?:descrizione|description|who|why|what|dove|where)\b", re.IGNORECASE)


class RuleInstructionError(ValueError):
    """The sentence does not name exactly one recognition text. The message
    is shown to the operator as it is."""


def _rewrite(reason: str) -> RuleInstructionError:
    return RuleInstructionError(
        f"{reason} Rewrite the rule naming exactly one text, for example: "
        f"“{EXAMPLE_INSTRUCTION}” — or put the text in quotes."
    )


@dataclass(frozen=True)
class ParsedRuleInstruction:
    phrase: str               # the recognition text as the operator wrote it
    normalized_pattern: str   # the stored CONTAINS_TEXT pattern
    stated_who: str | None    # the WHO the sentence names, when it names one


def _mask_quotes(text: str) -> str:
    """The same text with every quoted span blanked, so a name in quotes is
    never read as part of the sentence's structure."""
    return _QUOTED.sub(lambda match: " " * len(match.group(0)), text)


def parse_rule_instruction(instruction: str | None) -> ParsedRuleInstruction:
    """Read "where the description contains X (the WHO is Y)" and return X.

    Deterministic, and deliberately narrow: when the sentence does not name
    exactly ONE recognition text, nothing is guessed — `RuleInstructionError`
    asks the operator to rewrite it."""
    text = re.sub(r"\s+", " ", (instruction or "").strip())
    if not text:
        raise _rewrite("The rule is empty.")
    if text.count('"') % 2 or text.count("“") != text.count("”") or text.count("«") != text.count("»"):
        raise _rewrite("The quotes in the rule are not closed.")

    masked = _mask_quotes(text)
    who_match = _WHO_CLAUSE.search(masked)
    if who_match is not None:
        find_part = text[:who_match.start()]
        who_start = who_match.start("who") if who_match.group("who") is not None else who_match.start("who_arrow")
        stated_who = text[who_start:].strip().strip(" .;:,").strip("\"“”«»'").strip() or None
    else:
        find_part, stated_who = text, None

    masked_find = _mask_quotes(find_part)
    verbs = list(_FIND_VERB.finditer(masked_find))
    if len(verbs) > 1:
        raise _rewrite("The rule names more than one place to look.")
    remainder = find_part[verbs[0].end():] if verbs else find_part
    remainder = remainder.strip().strip(" .;:,")

    quoted = [next(g for g in match.groups() if g is not None) for match in _QUOTED.finditer(remainder)]
    if verbs and quoted:
        if len(quoted) > 1:
            raise _rewrite("The rule names more than one text in quotes.")
        outside = _QUOTED.sub("", remainder)
        if _LEADING_FILLER.sub("", outside.strip()).strip(" .;:,"):
            raise _rewrite("The rule has words outside the quoted text that are not understood.")
        phrase = quoted[0].strip()
    elif not verbs:
        # No "trovi"/"contains": only an explicitly quoted text is accepted.
        if len(quoted) == 1 and not _QUOTED.sub("", remainder).strip(" .;:,"):
            phrase = quoted[0].strip()
        else:
            raise _rewrite("The rule does not say which text to look for in the description.")
    else:
        phrase = _LEADING_FILLER.sub("", remainder).strip()
        if _SEVERAL.search(f" {phrase} "):
            raise _rewrite(f"“{phrase}” looks like more than one text.")
        if _STRUCTURE_WORDS.search(phrase):
            raise _rewrite(f"“{phrase}” could not be read as one recognition text.")

    pattern = recognition.normalize_description_for_recognition(phrase)
    if not pattern:
        raise _rewrite("The rule does not contain a text to look for.")
    if len(pattern.replace(" ", "")) < _MIN_PATTERN_CHARACTERS or not re.search(r"[A-Z]", pattern):
        raise _rewrite(
            f"“{phrase}” is too short to recognise a WHO safely (at least "
            f"{_MIN_PATTERN_CHARACTERS} characters, with a letter)."
        )
    return ParsedRuleInstruction(phrase=phrase, normalized_pattern=pattern, stated_who=stated_who)


# ---------------------------------------------------------------------------
# 2. Apply
# ---------------------------------------------------------------------------

# Per-transaction outcome of an Apply.
UPDATE = "update"
ALREADY = "already"
HUMAN_CONFLICT = "human_conflict"
OTHER_RULE = "other_rule"          # another rule names a different WHO for it
STRUCTURAL = "structural"          # RF-One itself (own account / entity): no external WHO

# The decision fields that describe PURPOSE. A WHO given to an existing
# transaction carries them over from its current decision verbatim.
_PURPOSE_FIELDS = (
    "food_cost_snapshot", "operative_snapshot", "deductible_snapshot", "what_label_snapshot",
    "transaction_reason_name_snapshot", "accounting_classification_id",
    "accounting_classification_code_snapshot", "accounting_classification_name_snapshot",
    "accounting_statement_type_snapshot",
)


@dataclass
class WhoRuleResult:
    """What one Apply did, in the operator's terms. No database id is
    meant to be shown."""
    who_name: str
    phrase: str
    pattern: str
    who_created: bool = False
    rule_created: bool = False
    rule_reactivated: bool = False
    matched: int = 0
    updated: int = 0
    already: int = 0
    human_conflicts: int = 0
    other_rule: int = 0
    structural: int = 0
    fragments_merged: list[str] = field(default_factory=list)
    fragments_not_merged: list[tuple[str, str]] = field(default_factory=list)
    why_added: list[str] = field(default_factory=list)
    possible_why: list[str] = field(default_factory=list)
    # Transactions whose recognition or decision was written — `updated`
    # plus the person-decided ones whose recognition followed the rule.
    transactions_written: int = 0

    @property
    def business_changes(self) -> int:
        return (int(self.who_created) + int(self.rule_created) + int(self.rule_reactivated)
                + self.transactions_written
                + len(self.fragments_merged) + len(self.why_added))

    def as_dict(self) -> dict:
        return {
            "who_name": self.who_name, "phrase": self.phrase, "pattern": self.pattern,
            "who_created": self.who_created, "rule_created": self.rule_created, "rule_reactivated": self.rule_reactivated,
            "matched": self.matched, "updated": self.updated, "already": self.already,
            "human_conflicts": self.human_conflicts, "other_rule": self.other_rule,
            "structural": self.structural, "fragments_merged": list(self.fragments_merged),
            "fragments_not_merged": [list(pair) for pair in self.fragments_not_merged],
            "why_added": list(self.why_added), "possible_why": list(self.possible_why),
            "business_changes": self.business_changes,
        }


def _require_active_who(session: Session, occurrence_id: int | None) -> "m.BankOccurrence":
    if not occurrence_id:
        raise ValueError("Choose the WHO this rule recognises.")
    who = session.get(m.BankOccurrence, occurrence_id)
    if who is None:
        raise ValueError("The selected WHO does not exist.")
    if who.status != "ACTIVE":
        raise ValueError(f"WHO “{who.canonical_name}” is inactive. Choose an active WHO.")
    return who


def existing_identity(session: Session, name: str | None) -> "tuple[m.BankOccurrence | None, str | None]":
    """The ACTIVE WHO a typed name already IS, by exact identity only — the
    same name, the same identity key (`who_key`), or an active alias with
    that key — through `CanonicalWhoResolver.by_identity`, the resolver WHO
    recognition uses. Returns (WHO, None), (None, why it is ambiguous or
    held) or (None, None) when the name is genuinely new. Similar-looking
    names are NOT identity: they are only ever offered to the operator."""
    clean = (name or "").strip()
    if not clean:
        return None, None
    occurrence, _how, held = wr.CanonicalWhoResolver(session).by_identity(clean)
    return occurrence, held


def _new_who(session: Session, name: str | None) -> "tuple[m.BankOccurrence | None, str]":
    """Validate a WHO the operator asked to create, WITHOUT creating it.

    Returns (existing ACTIVE WHO to reuse, name) when the identity already
    exists — a duplicate is never created — or (None, clean name) when it
    is new. Refuses an empty or ambiguous name, and a name that belongs to
    a merged (INACTIVE) WHO, which is neither recreated nor reactivated."""
    clean = " ".join((name or "").split())
    if not clean:
        raise ValueError("Type the name of the WHO to create.")
    if sum(ch.isalpha() for ch in clean) < 2:
        raise ValueError(f"“{clean}” is too short to name a WHO.")
    if len(clean) > 255:
        raise ValueError("A WHO name is at most 255 characters.")
    occurrence, held = existing_identity(session, clean)
    if occurrence is not None:
        return occurrence, occurrence.canonical_name
    if held is not None:
        raise ValueError(
            f"“{clean}” cannot be created: {held}. Choose an existing WHO instead."
        )
    exact = session.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == clean))
    if exact is not None:
        raise ValueError(
            f"A WHO named “{clean}” already exists but is inactive (merged). "
            "Choose its active WHO instead."
        )
    return None, clean


def _require_active_whys(session: Session, reason_ids: list[int]) -> list["m.BankTransactionReason"]:
    reasons = []
    for reason_id in dict.fromkeys(reason_ids):
        reason = session.get(m.BankTransactionReason, reason_id)
        if reason is None:
            raise ValueError("One of the selected WHY does not exist.")
        if reason.status != "ACTIVE":
            raise ValueError(f"WHY “{reason.name}” is inactive and cannot be added to a WHO.")
        reasons.append(reason)
    return reasons


def _description_rule_for(session: Session, who: "m.BankOccurrence", pattern: str):
    """This WHO's own unscoped CONTAINS rule on `pattern`, whatever its status."""
    return session.scalars(
        select(m.BankRecognitionRule).where(
            m.BankRecognitionRule.occurrence_id == who.id,
            m.BankRecognitionRule.match_type == recognition.CONTAINS_TEXT,
            m.BankRecognitionRule.normalized_pattern == pattern,
            m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
            m.BankRecognitionRule.determines_purpose.is_(False),
            m.BankRecognitionRule.payment_instrument_id.is_(None),
            m.BankRecognitionRule.direction.is_(None),
        ).order_by(m.BankRecognitionRule.id)
    ).first()


def _refuse_conflicting_rule(session: Session, who: "m.BankOccurrence | None", pattern: str) -> None:
    """One text cannot recognise two WHO: an ACTIVE rule giving the same
    match to another WHO is refused before anything is written. `who` is
    None for a WHO about to be created: then any such rule is another WHO's."""
    query = select(m.BankRecognitionRule).where(
        m.BankRecognitionRule.match_type == recognition.CONTAINS_TEXT,
        m.BankRecognitionRule.normalized_pattern == pattern,
        m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
        m.BankRecognitionRule.status == "ACTIVE",
    )
    if who is not None:
        query = query.where(m.BankRecognitionRule.occurrence_id != who.id)
    clash = session.scalars(query).first()
    if clash is not None:
        other = session.get(m.BankOccurrence, clash.occurrence_id)
        raise ValueError(
            f"Descriptions containing “{pattern}” are already recognised as WHO "
            f"“{other.canonical_name if other else '?'}”. One text cannot recognise two WHO: "
            "change that WHO's rule in Configuration first, or write a more specific text."
        )


def _save_rule(session: Session, who: "m.BankOccurrence", pattern: str,
               created_from_transaction_id: int | None, result: WhoRuleResult) -> "m.BankRecognitionRule":
    """A. The WHO-only rule (BANK_CONFIGURATION_001 D2 shape): DESCRIPTION,
    CONTAINS_TEXT, no WHY, no instrument or direction scope, auto-applied.
    Reused when it already exists, so a second Apply adds nothing."""
    rule = _description_rule_for(session, who, pattern)
    if rule is not None:
        if rule.status != "ACTIVE" or not rule.auto_apply_enabled:
            rule.status = "ACTIVE"
            rule.auto_apply_enabled = True
            result.rule_reactivated = True
        session.flush()
        return rule
    rule = m.BankRecognitionRule(
        match_type=recognition.CONTAINS_TEXT, normalized_pattern=pattern,
        match_field=recognition.DESCRIPTION, determines_purpose=False,
        payment_instrument_id=None, direction=None, occurrence_id=who.id,
        transaction_reason_id=None, priority=0, status="ACTIVE", auto_apply_enabled=True,
        human_confirmations=1, human_contradictions=0,
        created_from_transaction_id=created_from_transaction_id,
    )
    session.add(rule)
    session.flush()
    result.rule_created = True
    return rule


def _save_possible_whys(session: Session, who: "m.BankOccurrence",
                        reasons: list["m.BankTransactionReason"], result: WhoRuleResult) -> None:
    """B. Additive upsert of WHO -> possible WHY. An association already
    active is left exactly as it is (no confirmation counted), so a second
    Apply changes nothing — except one created by "Create New WHY" and not
    confirmed yet (count 0): this Apply is its one human confirmation.
    Never touches `default_transaction_reason_id`."""
    existing = {
        row.transaction_reason_id: row for row in session.scalars(
            select(m.BankOccurrenceReasonAssociation)
            .where(m.BankOccurrenceReasonAssociation.occurrence_id == who.id)
        )
    }
    for reason in reasons:
        row = existing.get(reason.id)
        if row is not None and row.active:
            if row.confirmation_count == 0:
                why_catalog.associate(session, occurrence_id=who.id, transaction_reason_id=reason.id,
                                      source="HUMAN")
            continue
        if row is not None:
            row.active = True
        else:
            why_catalog.associate(session, occurrence_id=who.id, transaction_reason_id=reason.id,
                                  source="HUMAN")
        result.why_added.append(reason.name)
    session.flush()


@dataclass
class _Candidate:
    transaction_id: int
    instrument_id: int | None
    description: str | None
    amount_minor: int
    detected_format: str | None
    outcome: str
    current: "m.BankTransactionExplanation | None"
    recognition: "m.BankWhoRecognition | None"
    engine_rule_id: int | None = None
    update_recognition: bool = False
    update_decision: bool = False


def _plan_transactions(session: Session, who: "m.BankOccurrence",
                       rule: "m.BankRecognitionRule") -> list[_Candidate]:
    """Every existing transaction the rule matches, and what Apply may do
    with it. Writes nothing.

    Matching is the import's own: `_rule_matches` selects the transactions
    and `find_candidate_rules` asks, as import does, which WHO the ACTIVE
    rules name. Only when every matching rule names this WHO is anything
    changed. A person's decision and a Standard's are never changed; the
    transaction's RECOGNITION — what its bank text proves, a separate fact
    that `who_recognition.recognize_transactions` would rewrite from the
    rule anyway — does follow the rule, so no recognition is left pointing
    at a merged fragment."""
    rows = session.execute(
        select(m.FinancialTransaction.id, m.FinancialTransaction.payment_instrument_id,
               m.FinancialTransaction.description_original, m.FinancialTransaction.source_memo,
               m.FinancialTransaction.amount_minor, m.FinancialTransaction.explanation_id,
               m.BankImportBatch.detected_format)
        .outerjoin(m.BankImportBatch, m.BankImportBatch.id == m.FinancialTransaction.import_batch_id)
        .order_by(m.FinancialTransaction.id)
    ).all()
    matching = []
    for tx_id, instrument_id, description, memo, amount, explanation_id, fmt in rows:
        normalized = recognition.normalize_description_for_recognition(description or "")
        if recognition._rule_matches(rule, normalized):
            matching.append((tx_id, instrument_id, description, memo, amount, explanation_id, normalized, fmt))
    if not matching:
        return []

    explanation_ids = [row[5] for row in matching if row[5] is not None]
    explanations = {}
    for start in range(0, len(explanation_ids), 500):
        for row in session.scalars(select(m.BankTransactionExplanation).where(
                m.BankTransactionExplanation.id.in_(explanation_ids[start:start + 500]))):
            explanations[row.id] = row
    transaction_ids = [row[0] for row in matching]
    recognitions = {}
    for start in range(0, len(transaction_ids), 500):
        for row in session.scalars(select(m.BankWhoRecognition).where(
                m.BankWhoRecognition.recognizer_version == wr.RECOGNIZER_VERSION,
                m.BankWhoRecognition.financial_transaction_id.in_(transaction_ids[start:start + 500]))):
            recognitions[row.financial_transaction_id] = row

    rules = recognition.active_rules(session)
    plan = []
    for tx_id, instrument_id, description, memo, amount, explanation_id, normalized, fmt in matching:
        current = explanations.get(explanation_id)
        known = recognitions.get(tx_id)
        candidate = _Candidate(tx_id, instrument_id, description, amount, fmt, ALREADY, current, known)
        plan.append(candidate)
        protected = current is not None and (current.decision_source == "HUMAN"
                                             or current.reconciliation_standard_id is not None)
        structural = known is not None and known.tier == wr.STRUCTURAL
        candidates = recognition.find_candidate_rules(
            session, normalized_description=normalized, payment_instrument_id=instrument_id,
            direction=recognition.direction_for_amount(amount),
            normalized_memo=recognition.normalize_memo_for_recognition(memo), rules=rules,
        )
        agreed = {c.occurrence_id for c in candidates} == {who.id}
        if agreed:
            candidate.engine_rule_id = candidates[0].id
        candidate.update_recognition = agreed and not structural and (
            known is None or known.occurrence_id != who.id)
        candidate.update_decision = agreed and not protected and not structural and (
            current is None or current.occurrence_id != who.id)
        if protected:
            candidate.outcome = ALREADY if current.occurrence_id == who.id else HUMAN_CONFLICT
        elif structural:
            candidate.outcome = STRUCTURAL
        elif not agreed:
            candidate.outcome = OTHER_RULE
        elif candidate.update_decision or candidate.update_recognition:
            candidate.outcome = UPDATE
    return plan


def _is_recognizer_fragment(occurrence: "m.BankOccurrence", counterparty_type_id: int | None) -> bool:
    """A WHO RF-One's recognizer created from bank text and nobody curated:
    still the recognizer's own upper-case identity key, recognizer notes,
    the generic COUNTERPARTY type."""
    return (occurrence.canonical_name == wr.who_key(occurrence.canonical_name)
            and (occurrence.optional_notes or "").startswith(_RECOGNIZER_NOTE_PREFIX)
            and occurrence.occurrence_type_id == counterparty_type_id)


def _plan_fragments(session: Session, who: "m.BankOccurrence", rule: "m.BankRecognitionRule",
                    plan: list[_Candidate]) -> tuple[list["m.BankOccurrence"], list[tuple[str, str]]]:
    """D (planning). The ACTIVE WHO records this rule recognises by their
    own name, split into the ones that are clearly fragments of the selected
    WHO — safe to merge — and the ones that are not, with the reason.

    A record is merged only when nothing about it was configured or decided
    by a person, and when every transaction it holds is one this Apply
    gives to the selected WHO. Anything else is an ACTIVE different WHO:
    it is left as it is and reported, never merged automatically."""
    counterparty_type_id = session.scalar(
        select(m.BankOccurrenceType.id).where(m.BankOccurrenceType.code == wr.OCCURRENCE_TYPE_CODE)
    )
    candidates = [
        occurrence for occurrence in session.scalars(
            select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE",
                                           m.BankOccurrence.id != who.id))
        if recognition._rule_matches(
            rule, recognition.normalize_description_for_recognition(occurrence.canonical_name))
    ]
    if not candidates:
        return [], []
    ids = [occurrence.id for occurrence in candidates]
    absorbed = set(session.scalars(select(m.BankOccurrenceAlias.occurrence_id).where(
        m.BankOccurrenceAlias.occurrence_id.in_(ids), m.BankOccurrenceAlias.source_family == MERGED_WHO_NAME)))
    with_rules = set(session.scalars(select(m.BankRecognitionRule.occurrence_id).where(
        m.BankRecognitionRule.occurrence_id.in_(ids), m.BankRecognitionRule.status == "ACTIVE")))
    with_standards = set(session.scalars(select(m.BankReconciliationStandard.occurrence_id).where(
        m.BankReconciliationStandard.occurrence_id.in_(ids))))
    with_entities = set(session.scalars(select(m.BankOccurrenceReportingEntity.occurrence_id).where(
        m.BankOccurrenceReportingEntity.occurrence_id.in_(ids), m.BankOccurrenceReportingEntity.active.is_(True))))
    human_decided = set(session.scalars(
        select(m.BankTransactionExplanation.occurrence_id)
        .join(m.FinancialTransaction, m.FinancialTransaction.explanation_id == m.BankTransactionExplanation.id)
        .where(m.BankTransactionExplanation.occurrence_id.in_(ids),
               m.BankTransactionExplanation.decision_source == "HUMAN")))
    # Every transaction each record currently holds, through its recognition
    # or its current decision — all of them must move with it.
    held_by_recognition: dict[int, set[int]] = {}
    for occurrence_id, tx_id in session.execute(
            select(m.BankWhoRecognition.occurrence_id, m.BankWhoRecognition.financial_transaction_id)
            .where(m.BankWhoRecognition.occurrence_id.in_(ids))):
        held_by_recognition.setdefault(occurrence_id, set()).add(tx_id)
    held_by_decision: dict[int, set[int]] = {}
    for occurrence_id, tx_id in session.execute(
            select(m.BankTransactionExplanation.occurrence_id, m.FinancialTransaction.id)
            .join(m.FinancialTransaction, m.FinancialTransaction.explanation_id == m.BankTransactionExplanation.id)
            .where(m.BankTransactionExplanation.occurrence_id.in_(ids))):
        held_by_decision.setdefault(occurrence_id, set()).add(tx_id)
    recognised_as_who = {c.transaction_id for c in plan if c.update_recognition or (
        c.recognition is not None and c.recognition.occurrence_id == who.id)}
    decided_as_who = {c.transaction_id for c in plan if c.update_decision or (
        c.current is not None and c.current.occurrence_id == who.id)}

    safe, refused = [], []
    for occurrence in sorted(candidates, key=lambda o: o.canonical_name):
        if not _is_recognizer_fragment(occurrence, counterparty_type_id):
            reason = "a configured WHO, not a fragment"
        elif occurrence.id in absorbed:
            reason = "a canonical WHO that already holds merged names"
        elif occurrence.manual_only:
            reason = "a person marked it Manual Only"
        elif occurrence.id in with_rules:
            reason = "it has its own recognition rule"
        elif occurrence.id in with_standards:
            reason = "a Standard uses it"
        elif occurrence.id in with_entities:
            reason = "it has configured For Whom entities"
        elif occurrence.id in human_decided:
            reason = "a person chose it for a transaction"
        elif not (held_by_recognition.get(occurrence.id, set()) <= recognised_as_who
                  and held_by_decision.get(occurrence.id, set()) <= decided_as_who):
            reason = "some of its transactions are not covered by this rule"
        else:
            safe.append(occurrence)
            continue
        refused.append((occurrence.canonical_name, reason))
    return safe, refused


def _merge_fragment(session: Session, who: "m.BankOccurrence", fragment: "m.BankOccurrence",
                    rule: "m.BankRecognitionRule", aliases_on_who: set[tuple[str, str]]) -> None:
    """D (writing). The canonical WHO/WHY import's merge, for one fragment:
    its aliases are kept and copied onto the canonical WHO, its own name
    becomes a MERGED_WHO_NAME alias of it, its possible WHY and Supplier
    links are carried over, and it is marked INACTIVE — never deleted, and
    no decision row is rewritten."""
    def add_alias(text: str, family: str, source: str, first_tx: int | None) -> None:
        if (text, family) in aliases_on_who:
            return
        session.add(m.BankOccurrenceAlias(
            occurrence_id=who.id, alias_text=text[:255], alias_key=wr.who_key(text)[:255],
            source_family=family, source=source, first_financial_transaction_id=first_tx,
        ))
        aliases_on_who.add((text, family))

    for alias in session.scalars(select(m.BankOccurrenceAlias).where(
            m.BankOccurrenceAlias.occurrence_id == fragment.id).order_by(m.BankOccurrenceAlias.id)):
        add_alias(alias.alias_text, alias.source_family, alias.source, alias.first_financial_transaction_id)
    add_alias(fragment.canonical_name, MERGED_WHO_NAME, "HUMAN", None)

    who_reasons = {row.transaction_reason_id: row for row in session.scalars(
        select(m.BankOccurrenceReasonAssociation).where(m.BankOccurrenceReasonAssociation.occurrence_id == who.id))}
    for row in session.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == fragment.id,
            m.BankOccurrenceReasonAssociation.active.is_(True))):
        target = who_reasons.get(row.transaction_reason_id)
        if target is None:
            session.add(m.BankOccurrenceReasonAssociation(
                occurrence_id=who.id, transaction_reason_id=row.transaction_reason_id, active=True,
                confirmation_count=row.confirmation_count, first_confirmed_at=row.first_confirmed_at,
                last_confirmed_at=row.last_confirmed_at, source=row.source,
            ))
        elif not target.active:
            target.active = True

    linked = set(session.scalars(select(m.BankOccurrenceSupplier.supplier_id).where(
        m.BankOccurrenceSupplier.occurrence_id == who.id)))
    for link in session.scalars(select(m.BankOccurrenceSupplier).where(
            m.BankOccurrenceSupplier.occurrence_id == fragment.id)):
        if link.supplier_id not in linked:
            session.add(m.BankOccurrenceSupplier(
                occurrence_id=who.id, supplier_id=link.supplier_id, link_source=link.link_source,
                notes=f"Carried over from merged WHO fragment {fragment.canonical_name!r}.",
            ))
            linked.add(link.supplier_id)

    fragment.status = "INACTIVE"
    note = (f"Merged into '{who.canonical_name}' (#{who.id}) by WHO rule #{rule.id} "
            f"(description contains {rule.normalized_pattern!r}).")
    fragment.optional_notes = f"{fragment.optional_notes}\n{note}" if fragment.optional_notes else note
    session.flush()


def _apply_to_transaction(session: Session, who: "m.BankOccurrence", rule: "m.BankRecognitionRule",
                          candidate: _Candidate, contexts, applied_by_account_id: int | None) -> None:
    """C (writing), for one transaction: its recognition and/or its current
    automatic decision, as the plan decided."""
    note = (f"WHO from approved recognition rule #{rule.id} "
            f"({rule.match_type} {rule.normalized_pattern!r}).")
    known = candidate.recognition
    if candidate.update_recognition and known is None:
        registered, entities, lookups = contexts
        first = wr.recognize(candidate.description, wr.WhoContext(
            detected_format=candidate.detected_format, instrument_type=lookups["type"].get(candidate.instrument_id),
            institution=lookups["institution"].get(candidate.instrument_id),
            amount_minor=candidate.amount_minor, registered_last_four=registered, legal_entities=entities,
        ))
        session.add(m.BankWhoRecognition(
            financial_transaction_id=candidate.transaction_id, recognizer_version=wr.RECOGNIZER_VERSION,
            tier=wr.DETERMINISTIC, family=first.family, parser_code=first.parser_code,
            extracted_name=(wr.normalize_who_name(first.extracted)[:255] if first.extracted else None),
            proposed_name=None, occurrence_id=who.id, evidence=f"{first.evidence} {note}".strip(),
        ))
    elif candidate.update_recognition:
        known.tier = wr.DETERMINISTIC
        known.occurrence_id = who.id
        known.proposed_name = None
        known.evidence = f"{known.evidence} {note}".strip()

    current = candidate.current
    if not candidate.update_decision:
        session.flush()
        return
    row = recognition._create_decision_row(
        session, session.get(m.FinancialTransaction, candidate.transaction_id),
        occurrence_id=who.id,
        transaction_reason_id=current.transaction_reason_id if current is not None else None,
        recognition_rule_id=candidate.engine_rule_id, decision_source="RULE",
        decision_status=current.decision_status if current is not None else "NEEDS_HUMAN_REVIEW",
        confidence=current.confidence if current is not None else None,
        explanation_notes=(
            f"Simple WHO rule applied to existing transactions by account {applied_by_account_id}: "
            f"Who {who.canonical_name!r}. {note} WHO only: "
            + (f"Why, What and status carried over unchanged from decision #{current.id}."
               if current is not None else "no previous decision; the Why stays for a human.")
        ),
        accounting_destination_source=(current.accounting_destination_source
                                       if current is not None else m.DESTINATION_SOURCE_WHY),
    )
    for name in _PURPOSE_FIELDS:
        setattr(row, name, getattr(current, name) if current is not None else None)
    session.flush()


def apply_who_rule(
    session: Session, *, occurrence_id: int | None, instruction: str | None,
    transaction_reason_ids: list[int] | None = None, applied_by_account_id: int | None = None,
    created_from_transaction_id: int | None = None, new_who_name: str | None = None,
) -> WhoRuleResult:
    """THE Apply — Classification and Review both call this, and nothing
    else writes a simple WHO rule. Validates everything before writing
    anything; raises `ValueError` (with an operator-readable message) when
    the rule is unsafe, and the caller then rolls back, so nothing is ever
    partially applied. Idempotent: a second identical Apply reports zero
    business changes.

    `new_who_name` (with no `occurrence_id`) asks for a WHO that does not
    exist yet. It is created HERE, through the Configuration service
    (`configuration.save_who`: a COUNTERPARTY, no default WHY), only after
    every check has passed and inside the same database transaction as the
    rule and its application — so a refusal or failure anywhere leaves
    neither a WHO without its rule nor a rule without its WHO. A name whose
    identity already exists reuses that WHO instead of creating a duplicate."""
    from . import configuration

    if occurrence_id:
        who, new_name = _require_active_who(session, occurrence_id), None
        who_label = who.canonical_name
    else:
        who, new_name = _new_who(session, new_who_name)
        who_label = who.canonical_name if who is not None else new_name
    if who is not None and who.manual_only:
        raise ValueError(
            f"WHO “{who.canonical_name}” is Manual Only: it is reconciled by hand and takes no WHO Rule. "
            "Remove Manual Only in Classification first if it should have one."
        )
    parsed = parse_rule_instruction(instruction)
    if parsed.stated_who and wr.who_key(parsed.stated_who) not in {
            wr.who_key(who_label), wr.who_key(new_who_name or who_label)}:
        raise ValueError(
            f"The rule says the WHO is “{parsed.stated_who}”, but the "
            f"{'new' if who is None else 'selected'} WHO is “{who_label}”. "
            "Choose that WHO, or rewrite the rule."
        )
    reasons = _require_active_whys(session, list(transaction_reason_ids or []))
    _refuse_conflicting_rule(session, who, parsed.normalized_pattern)

    created = False
    if who is None:
        who = configuration.save_who(
            session, occurrence_id=None, name=new_name, active=True, reason_ids=[],
            default_reason_id=None, reporting_entity_ids=[], rules=[],
        )
        created = True
    result = WhoRuleResult(who_name=who.canonical_name, phrase=parsed.phrase,
                           pattern=parsed.normalized_pattern, who_created=created)
    rule = _save_rule(session, who, parsed.normalized_pattern, created_from_transaction_id, result)
    _save_possible_whys(session, who, reasons, result)

    plan = _plan_transactions(session, who, rule)
    safe, refused = _plan_fragments(session, who, rule, plan)
    result.fragments_not_merged = refused
    aliases_on_who = {(text, family) for text, family in session.execute(
        select(m.BankOccurrenceAlias.alias_text, m.BankOccurrenceAlias.source_family)
        .where(m.BankOccurrenceAlias.occurrence_id == who.id))}
    for fragment in safe:
        _merge_fragment(session, who, fragment, rule, aliases_on_who)
        result.fragments_merged.append(fragment.canonical_name)

    contexts = wr.build_contexts(session) if any(
        c.update_recognition and c.recognition is None for c in plan) else None
    for candidate in plan:
        result.matched += 1
        if candidate.update_recognition or candidate.update_decision:
            _apply_to_transaction(session, who, rule, candidate, contexts, applied_by_account_id)
            result.transactions_written += 1
        if candidate.outcome == UPDATE:
            result.updated += 1
        elif candidate.outcome == ALREADY:
            result.already += 1
        elif candidate.outcome == HUMAN_CONFLICT:
            result.human_conflicts += 1
        elif candidate.outcome == OTHER_RULE:
            result.other_rule += 1
        else:
            result.structural += 1

    result.possible_why = [reason.name for reason in why_catalog.reasons_by_occurrence(session).get(who.id, [])]
    session.flush()
    return result


# ---------------------------------------------------------------------------
# 3. The Classification list
# ---------------------------------------------------------------------------

CLASSIFICATION_PAGE_SIZE = 50

# The three groups of the active WHO list (BANK_WHO_MANUAL_ONLY_001), in
# display order: WHO still without an individual WHO Rule first — the work
# left — then WHO that have one, then WHO a person excluded from WHO Rules.
# "Has Rule" means an ACTIVE description recognition rule names the WHO;
# General Rules, WHY Rules, inactive rules and suggestions do not count.
NEEDS_RULE = "NEEDS_RULE"
HAS_RULE = "HAS_RULE"
MANUAL_ONLY = "MANUAL_ONLY"
CLASSIFICATION_GROUPS = (NEEDS_RULE, HAS_RULE, MANUAL_ONLY)
GROUP_LABELS = {NEEDS_RULE: "Needs Rule", HAS_RULE: "Has Rule", MANUAL_ONLY: "Manual Only"}


@dataclass(frozen=True)
class LastTransaction:
    """The most recent bank transaction a WHO holds — what tells a person
    what the WHO really is before choosing a Rule or Manual Only."""
    transaction_id: int
    posting_date: date
    instrument: str
    description: str
    amount_minor: int


@dataclass(frozen=True)
class OccurrenceRow:
    id: int
    name: str
    type_name: str
    status: str
    transactions: int
    rules: tuple[str, ...]
    suggested_who_id: int
    suggested_who_name: str
    group: str | None = None
    manual_only: bool = False
    # The Rule button names the suggested (canonical) WHO: it is unavailable
    # when THAT WHO is Manual Only, whatever the row itself is.
    rule_target_manual_only: bool = False
    last_transaction: LastTransaction | None = None


@dataclass(frozen=True)
class OccurrencePage:
    rows: list[OccurrenceRow]
    total: int
    page: int
    pages: int
    active_total: int
    inactive_total: int
    # Matching WHO per group (search applied), for the group headings; empty
    # for the merged-WHO view, which is not grouped.
    group_counts: dict[str, int] = field(default_factory=dict)


def _has_active_who_rule():
    """SQL: the WHO has an ACTIVE individual (description) WHO Rule."""
    return select(m.BankRecognitionRule.id).where(
        m.BankRecognitionRule.occurrence_id == m.BankOccurrence.id,
        m.BankRecognitionRule.status == "ACTIVE",
        m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
    ).exists()


def _group_expression():
    return case(
        (m.BankOccurrence.manual_only.is_(True), 2),
        (_has_active_who_rule(), 1),
        else_=0,
    )


def _curated_index(session: Session) -> tuple[dict[int, str], dict[str, set[int]]]:
    """Active WHO that are canonical rather than raw recognizer output —
    anything a person created or curated, a WHO holding merged names, or one
    with a rule of its own — by id, and the alias keys they hold."""
    absorbed = set(session.scalars(select(m.BankOccurrenceAlias.occurrence_id).where(
        m.BankOccurrenceAlias.source_family == MERGED_WHO_NAME).distinct()))
    ruled = set(session.scalars(select(m.BankRecognitionRule.occurrence_id).where(
        m.BankRecognitionRule.status == "ACTIVE",
        m.BankRecognitionRule.match_field == recognition.DESCRIPTION).distinct()))
    counterparty_type_id = session.scalar(
        select(m.BankOccurrenceType.id).where(m.BankOccurrenceType.code == wr.OCCURRENCE_TYPE_CODE)
    )
    curated = {
        occurrence.id: occurrence.canonical_name for occurrence in session.scalars(
            select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))
        if not _is_recognizer_fragment(occurrence, counterparty_type_id)
        or occurrence.id in absorbed or occurrence.id in ruled
    }
    alias_owners: dict[str, set[int]] = {}
    for occurrence_id, alias_key in session.execute(
            select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_key)):
        if occurrence_id in curated:
            alias_owners.setdefault(alias_key, set()).add(occurrence_id)
    return curated, alias_owners


def suggest_canonical(name: str, own_id: int, curated: dict[int, str],
                      alias_owners: dict[str, set[int]]) -> int:
    """The canonical WHO an occurrence most clearly belongs to, for the
    Rule modal's preselection only — never applied by itself. The row's own
    WHO when it is canonical; else the one canonical WHO holding its name as
    an alias; else the canonical WHO whose name its name begins with (the
    longest, word by word); else the row itself."""
    if own_id in curated:
        return own_id
    key = wr.who_key(name)
    owners = alias_owners.get(key, set())
    if len(owners) == 1:
        return next(iter(owners))
    best_id, best_len = own_id, 0
    for occurrence_id, canonical in curated.items():
        canonical_key = wr.who_key(canonical)
        if canonical_key and (key == canonical_key or key.startswith(canonical_key + " ")):
            if len(canonical_key) > best_len:
                best_id, best_len = occurrence_id, len(canonical_key)
    return best_id


def latest_transactions(session: Session, occurrence_ids: list[int]) -> dict[int, LastTransaction]:
    """The latest transaction of each WHO in `occurrence_ids`, in ONE query
    whatever their number (never one per WHO).

    A WHO holds a transaction through its recognition or its current
    decision — the same family the Transactions count reads. A canonical WHO
    also answers for the merged WHO it absorbed (an INACTIVE WHO whose name it
    holds as a MERGED_WHO_NAME alias), should any of them still hold one.
    Latest = greatest `posting_date`, then greatest transaction id — never a
    WHO, recognition or alias date. The description is the bank's original
    text, as it arrived."""
    if not occurrence_ids:
        return {}
    owner = {occurrence_id: occurrence_id for occurrence_id in occurrence_ids}
    for canonical_id, merged_id in session.execute(
            select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrence.id)
            .join(m.BankOccurrence, m.BankOccurrence.canonical_name == m.BankOccurrenceAlias.alias_text)
            .where(m.BankOccurrenceAlias.occurrence_id.in_(occurrence_ids),
                   m.BankOccurrenceAlias.source_family == MERGED_WHO_NAME,
                   m.BankOccurrence.status == "INACTIVE")):
        owner.setdefault(merged_id, canonical_id)
    family = list(owner)
    held = union(
        select(m.BankWhoRecognition.occurrence_id.label("occurrence_id"),
               m.BankWhoRecognition.financial_transaction_id.label("transaction_id"))
        .where(m.BankWhoRecognition.occurrence_id.in_(family)),
        select(m.BankTransactionExplanation.occurrence_id.label("occurrence_id"),
               m.FinancialTransaction.id.label("transaction_id"))
        .join(m.FinancialTransaction, m.FinancialTransaction.explanation_id == m.BankTransactionExplanation.id)
        .where(m.BankTransactionExplanation.occurrence_id.in_(family)),
    ).subquery()
    ranked = (
        select(held.c.occurrence_id, m.FinancialTransaction.id.label("transaction_id"),
               m.FinancialTransaction.posting_date, m.FinancialTransaction.description_original,
               m.FinancialTransaction.amount_minor, m.PaymentInstrument.display_name,
               func.row_number().over(
                   partition_by=held.c.occurrence_id,
                   order_by=(m.FinancialTransaction.posting_date.desc(), m.FinancialTransaction.id.desc()),
               ).label("rank"))
        .join(m.FinancialTransaction, m.FinancialTransaction.id == held.c.transaction_id)
        .outerjoin(m.PaymentInstrument, m.PaymentInstrument.id == m.FinancialTransaction.payment_instrument_id)
    ).subquery()
    latest: dict[int, LastTransaction] = {}
    for row in session.execute(select(ranked).where(ranked.c.rank == 1)):
        candidate = LastTransaction(
            transaction_id=row.transaction_id, posting_date=row.posting_date, instrument=row.display_name or "",
            description=row.description_original or "", amount_minor=row.amount_minor)
        # One best row per family member; the canonical WHO keeps the latest of them.
        key = owner[row.occurrence_id]
        best = latest.get(key)
        if best is None or (candidate.posting_date, candidate.transaction_id) > (best.posting_date, best.transaction_id):
            latest[key] = candidate
    return latest


def occurrence_page(session: Session, *, search: str = "", page: int = 1, show_inactive: bool = False,
                    page_size: int = CLASSIFICATION_PAGE_SIZE) -> OccurrencePage:
    """One page of WHO occurrences for the Classification tab: a handful of
    bounded queries whatever the size of the dataset. Merged (INACTIVE)
    records are hidden unless asked for.

    Active WHO come in three groups (Needs Rule, Has Rule, Manual Only),
    alphabetical inside each; the group is computed in the same query that
    orders and pages the list, never per WHO. Search covers all groups."""
    status = "INACTIVE" if show_inactive else "ACTIVE"
    counts = dict(session.execute(
        select(m.BankOccurrence.status, func.count(m.BankOccurrence.id)).group_by(m.BankOccurrence.status)
    ).all())
    conditions = [m.BankOccurrence.status == status]
    needle = (search or "").strip()
    if needle:
        conditions.append(func.upper(m.BankOccurrence.canonical_name).contains(needle.upper()))
    group_counts: dict[str, int] = {}
    if show_inactive:
        total = session.scalar(select(func.count(m.BankOccurrence.id)).where(*conditions)) or 0
        order = (func.upper(m.BankOccurrence.canonical_name), m.BankOccurrence.id)
    else:
        group = _group_expression()
        by_group = dict(session.execute(
            select(group, func.count(m.BankOccurrence.id)).where(*conditions).group_by(group)).all())
        group_counts = {name: by_group.get(i, 0) for i, name in enumerate(CLASSIFICATION_GROUPS)}
        total = sum(group_counts.values())
        order = (group, func.upper(m.BankOccurrence.canonical_name), m.BankOccurrence.id)
    pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(page, 1), pages)
    occurrences = session.scalars(
        select(m.BankOccurrence).where(*conditions).order_by(*order)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    ids = [o.id for o in occurrences]
    types = dict(session.execute(select(m.BankOccurrenceType.id, m.BankOccurrenceType.name)).all())

    held: dict[int, set[int]] = {}
    rules: dict[int, list[str]] = {}
    if ids:
        for occurrence_id, tx_id in session.execute(
                select(m.BankWhoRecognition.occurrence_id, m.BankWhoRecognition.financial_transaction_id)
                .where(m.BankWhoRecognition.occurrence_id.in_(ids))):
            held.setdefault(occurrence_id, set()).add(tx_id)
        for occurrence_id, tx_id in session.execute(
                select(m.BankTransactionExplanation.occurrence_id, m.FinancialTransaction.id)
                .join(m.FinancialTransaction,
                      m.FinancialTransaction.explanation_id == m.BankTransactionExplanation.id)
                .where(m.BankTransactionExplanation.occurrence_id.in_(ids))):
            held.setdefault(occurrence_id, set()).add(tx_id)
        labels = {recognition.CONTAINS_TEXT: "contains", recognition.PREFIX: "starts with",
                  recognition.EXACT_NORMALIZED_DESCRIPTION: "is exactly"}
        for occurrence_id, match_type, pattern in session.execute(
                select(m.BankRecognitionRule.occurrence_id, m.BankRecognitionRule.match_type,
                       m.BankRecognitionRule.normalized_pattern)
                .where(m.BankRecognitionRule.occurrence_id.in_(ids),
                       m.BankRecognitionRule.status == "ACTIVE",
                       m.BankRecognitionRule.match_field == recognition.DESCRIPTION)
                .order_by(m.BankRecognitionRule.id)):
            rules.setdefault(occurrence_id, []).append(f"{labels.get(match_type, match_type)} “{pattern}”")

    curated, alias_owners = _curated_index(session) if (ids and not show_inactive) else ({}, {})
    manual = set(session.scalars(select(m.BankOccurrence.id).where(
        m.BankOccurrence.manual_only.is_(True)))) if (ids and not show_inactive) else set()
    last = latest_transactions(session, ids)
    rows = []
    for occurrence in occurrences:
        suggested = (suggest_canonical(occurrence.canonical_name, occurrence.id, curated, alias_owners)
                     if not show_inactive else occurrence.id)
        if show_inactive:
            group = None
        elif occurrence.manual_only:
            group = MANUAL_ONLY
        else:
            group = HAS_RULE if occurrence.id in rules else NEEDS_RULE
        rows.append(OccurrenceRow(
            id=occurrence.id, name=occurrence.canonical_name,
            type_name=types.get(occurrence.occurrence_type_id, ""), status=occurrence.status,
            transactions=len(held.get(occurrence.id, ())), rules=tuple(rules.get(occurrence.id, ())),
            suggested_who_id=suggested,
            suggested_who_name=curated.get(suggested, occurrence.canonical_name),
            group=group, manual_only=bool(occurrence.manual_only),
            rule_target_manual_only=suggested in manual,
            last_transaction=last.get(occurrence.id),
        ))
    return OccurrencePage(rows=rows, total=total, page=page, pages=pages,
                          active_total=counts.get("ACTIVE", 0), inactive_total=counts.get("INACTIVE", 0),
                          group_counts=group_counts)


# ---------------------------------------------------------------------------
# 4. Manual Only (BANK_WHO_MANUAL_ONLY_001)
# ---------------------------------------------------------------------------

class ManualOnlyConflict(ValueError):
    """Marking Manual Only a WHO that still has active WHO Rules: refused
    until the person explicitly asks to disable those rules too."""

    def __init__(self, who: "m.BankOccurrence", rules: list[str]):
        self.who_id = who.id
        self.who_name = who.canonical_name
        self.rules = rules
        super().__init__(
            f"WHO “{who.canonical_name}” has an active WHO Rule ({'; '.join(rules)}). "
            "Disable it and mark Manual Only, or cancel."
        )


def active_who_rules(session: Session, occurrence_id: int) -> list["m.BankRecognitionRule"]:
    return list(session.scalars(select(m.BankRecognitionRule).where(
        m.BankRecognitionRule.occurrence_id == occurrence_id,
        m.BankRecognitionRule.status == "ACTIVE",
        m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
    ).order_by(m.BankRecognitionRule.id)))


def set_manual_only(session: Session, *, occurrence_id: int | None, manual_only: bool,
                    disable_rules: bool = False) -> dict:
    """Mark (or unmark) a WHO as Manual Only — the ONE service behind the
    Classification button.

    Marking a WHO that still has active WHO Rules never leaves both: it
    raises `ManualOnlyConflict` unless `disable_rules` says the person chose
    "Disable existing WHO Rule and mark Manual Only"; those rules then
    become INACTIVE (kept for history, never deleted). Transactions already
    recognised stay as they are. Unmarking only clears the flag: disabled
    rules are not re-enabled. Flushes, never commits."""
    who = _require_active_who(session, occurrence_id)
    disabled: list[str] = []
    if manual_only and not who.manual_only:
        rules = active_who_rules(session, who.id)
        if rules and not disable_rules:
            raise ManualOnlyConflict(who, [f"contains “{r.normalized_pattern}”" for r in rules])
        for rule in rules:
            rule.status = "INACTIVE"
            rule.auto_apply_enabled = False
            disabled.append(f"contains “{rule.normalized_pattern}”")
    changed = bool(who.manual_only) != bool(manual_only)
    who.manual_only = bool(manual_only)
    session.flush()
    return {"who_name": who.canonical_name, "manual_only": who.manual_only, "changed": changed,
            "rules_disabled": disabled}


def who_options(session: Session, *, search: str = "", limit: int = 25) -> dict:
    """What the modal's creatable WHO combo shows for a typed text.

    * `matches` — ACTIVE WHO whose name contains the text;
    * `identity` — the ACTIVE WHO the text already IS (same name, identity
      key or alias), which is offered instead of creating a duplicate;
    * `similar` — ACTIVE WHO that only look alike (one name begins with the
      other, word by word): shown for the operator to decide, never chosen;
    * `create` — the name to offer as "Create", or None when the identity
      already exists or the text is empty.

    Bounded: one query over active WHO names, never rendered as a list."""
    needle = " ".join((search or "").split())
    if not needle:
        return {"matches": [], "identity": None, "similar": [], "create": None}
    matches = [
        {"id": occurrence_id, "name": name} for occurrence_id, name in session.execute(
            select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)
            .where(m.BankOccurrence.status == "ACTIVE",
                   func.upper(m.BankOccurrence.canonical_name).contains(needle.upper()))
            .order_by(func.upper(m.BankOccurrence.canonical_name)).limit(limit))
    ]
    identity, held = existing_identity(session, needle)
    key = wr.who_key(needle)
    similar = []
    if key:
        shown = {match["id"] for match in matches} | ({identity.id} if identity else set())
        for occurrence_id, name in session.execute(
                select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)
                .where(m.BankOccurrence.status == "ACTIVE")):
            other = wr.who_key(name)
            if occurrence_id in shown or not other or len(other) < 4:
                continue
            if key.startswith(other + " ") or other.startswith(key + " "):
                similar.append({"id": occurrence_id, "name": name})
        similar = sorted(similar, key=lambda o: o["name"].upper())[:10]
    inactive_exact = session.scalar(select(func.count(m.BankOccurrence.id)).where(
        m.BankOccurrence.canonical_name == needle, m.BankOccurrence.status != "ACTIVE"))
    can_create = identity is None and held is None and not inactive_exact and sum(
        ch.isalpha() for ch in needle) >= 2
    return {
        "matches": matches,
        "identity": {"id": identity.id, "name": identity.canonical_name} if identity else None,
        "similar": similar,
        "create": needle if can_create else None,
        "held": held,
    }


def who_summary(session: Session, occurrence_id: int) -> dict | None:
    """What the modal shows for a WHO once chosen: its active possible WHY
    and its active description rules."""
    who = session.get(m.BankOccurrence, occurrence_id)
    if who is None:
        return None
    reasons = why_catalog.reasons_by_occurrence(session).get(who.id, [])
    rules = session.scalars(select(m.BankRecognitionRule).where(
        m.BankRecognitionRule.occurrence_id == who.id, m.BankRecognitionRule.status == "ACTIVE",
        m.BankRecognitionRule.match_field == recognition.DESCRIPTION).order_by(m.BankRecognitionRule.id)).all()
    return {
        "id": who.id, "name": who.canonical_name, "active": who.status == "ACTIVE",
        "manual_only": bool(who.manual_only),
        "possible_why_ids": [reason.id for reason in reasons],
        "rules": [f"{'contains' if r.match_type == recognition.CONTAINS_TEXT else r.match_type.lower()} "
                  f"“{r.normalized_pattern}”" for r in rules],
    }


def selectable_whys(session: Session) -> list["m.BankTransactionReason"]:
    """The WHY the modal offers: every active WHY — with or without an
    accounting destination (BANK_WHY_WITHOUT_WHAT_001) — alphabetical
    (case-insensitive)."""
    return list(session.scalars(
        select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
        ).order_by(func.lower(m.BankTransactionReason.name), m.BankTransactionReason.id)
    ))


def selectable_why_groups(session: Session) -> list[tuple[str, list["m.BankTransactionReason"]]]:
    """The same selectable WHY, under their approved WHY navigation group
    (`BankReasonGroup`, alphabetical like every Bank UI — `why_catalog.
    groups`), WHY alphabetical inside each — the modal's Possible WHY list.
    A WHY with no group, or in an inactive group, is still offered, under a
    trailing "Other". Two queries; organisation only, nothing is decided here."""
    groups = why_catalog.groups(session)
    by_group: dict[int | None, list] = {}
    known = {g.id for g in groups}
    for reason in selectable_whys(session):
        key = reason.reason_group_id if reason.reason_group_id in known else None
        by_group.setdefault(key, []).append(reason)
    result = [(g.name, by_group[g.id]) for g in groups if by_group.get(g.id)]
    if by_group.get(None):
        result.append(("Other", by_group[None]))
    return result
