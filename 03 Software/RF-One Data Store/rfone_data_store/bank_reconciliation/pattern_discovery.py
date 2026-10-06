"""Classification Learning — the ONE shared pattern-discovery engine
(BANK_CLASSIFICATION_LEARNING_001).

    OBSERVE -> DISCOVER PATTERN -> EXPLAIN -> TEST -> HUMAN REVIEW -> HUMAN APPROVE
            -> DETERMINISTIC RULE (in its own existing store)

It sits ABOVE the deterministic rule stores and replaces none of them:

    STRUCTURAL  text between two markers carries the WHO   -> General Rule (`general_rules`)
    WHO         a fixed description phrase names one WHO   -> WHO Rule (`BankRecognitionRule`)
    WHY         for a KNOWN WHO, simple bank evidence names
                the WHY                                    -> WHY Rule (`why_rules`)

Learning data keeps two things apart (`Observation`):

  * RAW INPUT — what the bank gave: description, posting date, instrument and
    its type, direction, amount, source;
  * REFINED TRUTH — what was decided: canonical WHO, WHY, WHAT, with its
    PROVENANCE (HUMAN, STANDARD, RULE, STRUCTURAL, OTHER) and whether a person
    confirmed the row.

Only HUMAN truth is trusted learning truth. Everything else is SUPPORT: it is
labelled, counted separately, never enough for a "verified" evidence level,
and never used to prove the rule that produced it (WHY discovery ignores WHY
the structural engine, a Standard or a WHY rule produced — they are already
deterministic knowledge). A pattern is DETERMINISTIC only when it has no
conflicting evidence; a PROBABILISTIC pattern ("84% of X are Y") is shown,
never approvable.

Discovery and backtests are explicit actions: nothing here runs on page
load, on import, or per transaction at runtime. Approved rules run without
any AI call. `PatternExplainer` is the seam where a future Bank
Reconciliation Agent may phrase or propose; the default explainer is a
deterministic template and calls nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import general_rules, recognition, why_rules
from . import who_recognition as wr

HUMAN, STANDARD, RULE, STRUCTURAL, OTHER = "HUMAN", "STANDARD", "RULE", "STRUCTURAL", "OTHER"
SUPPORT = (STANDARD, RULE, STRUCTURAL, OTHER)
DETERMINISTIC, PROBABILISTIC = "DETERMINISTIC", "PROBABILISTIC"
VERIFIED, SUPPORT_ONLY = "HUMAN_VERIFIED", "SUPPORT_ONLY"

MIN_STRUCTURAL_MATCHES = 10
MIN_STRUCTURAL_VALUES = 3
MIN_STRUCTURAL_CONSISTENCY = 0.98
MIN_WHO_SUPPORT = 3
MIN_HUMAN_FOR_WHY = 3
MIN_PROBABILISTIC_SHARE = 0.6
MIN_HUMAN_FOR_VERIFIED = 3
RELIABLE_HUMAN_TRUTH = 30          # below this a month's human-truth backtest is not reliable
EXAMPLES = 3

# A field label of a structured bank line: up to three words joined by SINGLE
# spaces (a run of spaces is fixed-width padding, never part of a label).
_LABEL = re.compile(r"(?:^|(?<=\s)|(?<=\d))([A-Z][A-Z#&']*(?: [A-Z][A-Z#&']*){0,2}):")
_WORD = re.compile(r"^[A-Z][A-Z&']{2,}$")


# ---------------------------------------------------------------------------
# OBSERVE — raw input and refined truth, kept apart
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawInput:
    transaction_id: int
    description: str
    normalized: str
    posting_date: date
    instrument_id: int | None
    instrument_type: str | None
    direction: str
    amount_minor: int
    bank_source: str | None
    # What the automatic parser (who-v1) read as the counterparty. Derived
    # from the raw text, NOT truth: used only as contrary evidence.
    recognized_who: int | None = None


@dataclass(frozen=True)
class Truth:
    who_id: int | None
    why_id: int | None
    what_id: int | None
    provenance: str
    confirmed: bool


@dataclass(frozen=True)
class Observation:
    raw: RawInput
    truth: Truth | None

    @property
    def human(self) -> bool:
        return self.truth is not None and self.truth.provenance == HUMAN


def provenance_of(explanation: "m.BankTransactionExplanation") -> str:
    notes = explanation.explanation_notes or ""
    if explanation.decision_source == "HUMAN":
        return HUMAN
    if explanation.reconciliation_standard_id is not None:
        return STANDARD
    if notes.startswith("[why-v1:"):
        return STRUCTURAL
    if (explanation.recognition_rule_id is not None or "General Rule" in notes
            or "Simple WHO rule" in notes or "WHY from approved WHY rule" in notes):
        return RULE
    return OTHER


def load_observations(session: Session, *, before: date | None = None) -> list[Observation]:
    """Every transaction (optionally only those posted before `before`) as
    raw input + refined truth. Two queries plus small lookups."""
    types = dict(session.execute(select(m.PaymentInstrument.id, m.PaymentInstrument.instrument_type)).all())
    confirmed = set(session.scalars(select(m.BankTransactionAllocation.financial_transaction_id).where(
        m.BankTransactionAllocation.status == m.ALLOCATION_COMPLETE,
        m.BankTransactionAllocation.decision_source == "HUMAN")))
    recognized = dict(session.execute(select(m.BankWhoRecognition.financial_transaction_id,
                                             m.BankWhoRecognition.occurrence_id).where(
        m.BankWhoRecognition.recognizer_version == wr.RECOGNIZER_VERSION,
        m.BankWhoRecognition.occurrence_id.is_not(None))).all())
    query = select(m.FinancialTransaction, m.BankTransactionExplanation).outerjoin(
        m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
    if before is not None:
        query = query.where(m.FinancialTransaction.posting_date < before)
    out = []
    for t, e in session.execute(query.order_by(m.FinancialTransaction.id)):
        raw = RawInput(t.id, t.description_original or "",
                       recognition.normalize_description_for_recognition(t.description_original or ""),
                       t.posting_date, t.payment_instrument_id, types.get(t.payment_instrument_id),
                       recognition.direction_for_amount(t.amount_minor), t.amount_minor, t.bank_source,
                       recognized.get(t.id))
        truth = None
        if e is not None and (e.occurrence_id is not None or e.transaction_reason_id is not None):
            truth = Truth(e.occurrence_id, e.transaction_reason_id, e.accounting_classification_id,
                          provenance_of(e), t.id in confirmed)
        out.append(Observation(raw, truth))
    return out


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    pattern_type: str
    proposal: dict
    determinism: str
    evidence: dict = field(default_factory=dict)
    covered_by: str | None = None

    @property
    def human_matches(self) -> int:
        return int(self.evidence.get("human_matches", 0))

    @property
    def evidence_level(self) -> str:
        return VERIFIED if self.human_matches >= MIN_HUMAN_FOR_VERIFIED else SUPPORT_ONLY

    @property
    def size(self) -> int:
        return int(self.evidence.get("matches", 0)) + int(self.evidence.get("human_matches", 0))

    def key(self) -> tuple:
        p = self.proposal
        if self.pattern_type == "STRUCTURAL":
            return ("STRUCTURAL", p["start_marker"].upper(), p["end_marker"].upper())
        if self.pattern_type == "WHO":
            return ("WHO", p["phrase"], p["who_id"])
        return ("WHY", p["who_id"], p.get("description_contains"), p.get("direction"),
                p.get("instrument_type"), p["why_id"])

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.key(), sort_keys=True).encode()).hexdigest()


class PatternExplainer(Protocol):
    """Phrases a candidate for the reviewer. The seam for a future Bank
    Reconciliation Agent: it may explain (or later propose), never approve."""

    def explain(self, candidate: Candidate, names: dict) -> str: ...


class DeterministicExplainer:
    """The default: a fixed template. Calls no model."""

    def explain(self, candidate: Candidate, names: dict) -> str:
        p, e = candidate.proposal, candidate.evidence
        if candidate.pattern_type == "STRUCTURAL":
            return (f"The text between {p['start_marker']!r} and {p['end_marker']!r} names the counterparty: "
                    f"{e.get('matches', 0)} transactions, {e.get('distinct_values', 0)} different names, each name "
                    f"always the same WHO where the WHO is known ({e.get('consistency', 0):.0%}).")
        if candidate.pattern_type == "WHO":
            return (f"Descriptions containing {p['phrase']!r} belong to {names.get(('who', p['who_id']), p['who_id'])} "
                    f"in every decided case ({e.get('with_truth', 0)}); {e.get('gap', 0)} more carry no WHO yet.")
        cond = ", ".join(x for x in (f"contains {p['description_contains']!r}" if p.get("description_contains") else "",
                                     p.get("direction") or "", p.get("instrument_type") or "") if x) or "always"
        share = e.get("share", 1.0)
        return (f"For {names.get(('who', p['who_id']), p['who_id'])} ({cond}) the WHY was "
                f"{names.get(('why', p['why_id']), p['why_id'])} in {share:.0%} of {e.get('human_matches', 0)} "
                f"human-confirmed cases.")


# ---------------------------------------------------------------------------
# DISCOVER
# ---------------------------------------------------------------------------


def _ngrams(normalized: str, n_max: int = 3, exclude: frozenset = frozenset()) -> set[str]:
    words = [w for w in normalized.split() if _WORD.match(w) and w not in exclude]
    grams = set()
    for n in range(1, n_max + 1):
        for i in range(len(words) - n + 1):
            grams.add(" ".join(words[i:i + n]))
    return grams


def _structural_marker_pairs(observations: list[Observation]) -> set[tuple[str, str]]:
    """Candidate (start, end) markers: consecutive "LABEL:" pairs, and a
    frequent leading phrase followed, after a variable value, by a stable
    token prefix (e.g. "Zelle payment to" ... "JPM99")."""
    pairs: Counter = Counter()
    leads: dict[str, list[list[str]]] = defaultdict(list)
    for o in observations:
        upper = o.raw.description.upper()
        labels = [mt.group(1).strip() + ":" for mt in _LABEL.finditer(upper)]
        for a, b in zip(labels, labels[1:]):
            pairs[(a, b)] += 1
        tokens = o.raw.description.split()
        for k in (2, 3):
            if len(tokens) > k + 1 and all(t.isalpha() for t in tokens[:k]):
                leads[" ".join(tokens[:k]).upper()].append([t.upper() for t in tokens[k:]])
    found = {pair for pair, n in pairs.items() if n >= MIN_STRUCTURAL_MATCHES}
    for lead, tails in leads.items():
        if len(tails) < MIN_STRUCTURAL_MATCHES or not any(c.isalpha() for c in lead):
            continue
        prefixes: Counter = Counter()
        for tail in tails:
            seen = {t[:5] for t in tail[1:] if len(t) >= 5 and t[:5].isalnum() and not t[:5].isdigit()}
            prefixes.update(seen)
        if prefixes:
            prefix, n = prefixes.most_common(1)[0]
            if n / len(tails) >= 0.75:
                found.add((lead, prefix))
    return found


def _identity_keys(session: Session) -> dict[int, set[str]]:
    """WHO id -> the identity keys that name it: its canonical name and aliases."""
    keys: dict[int, set[str]] = defaultdict(set)
    for oid, name in session.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)):
        keys[oid].add(wr.who_key(name))
    for oid, key in session.execute(select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_key)):
        if key:
            keys[oid].add(key)
    return keys


def _looks_like_name(value: str) -> bool:
    letters = sum(ch.isalpha() for ch in value)
    return letters >= 3 and letters >= 0.5 * len(value.replace(" ", ""))


def _structural(observations, existing_markers, resolver, names, identity) -> list[Candidate]:
    """A marker pair is a WHO pattern only when its values are NAMES that
    recur and, where the WHO is known, the value actually names it (canonical
    name or alias). Unique codes (trace numbers, ids) and our own name in a
    receiver field are rejected, however consistent they look."""
    out = []
    for start, end in sorted(_structural_marker_pairs(observations)):
        values = Counter()
        value_who: dict[str, Counter] = defaultdict(Counter)
        human_value_who: dict[str, Counter] = defaultdict(Counter)
        examples = []
        for o in observations:
            v = general_rules.extract(o.raw.description, start, end)
            if v is None:
                continue
            key = wr.who_key(v)
            values[key] += 1
            if o.truth is not None and o.truth.who_id is not None:
                value_who[key][o.truth.who_id] += 1
                if o.human:
                    human_value_who[key][o.truth.who_id] += 1
            if len(examples) < EXAMPLES:
                examples.append({"description": o.raw.description[:140], "extracted": v})
        matches = sum(values.values())
        if matches < MIN_STRUCTURAL_MATCHES or len(values) < MIN_STRUCTURAL_VALUES:
            continue
        if len(values) > 0.6 * matches:
            continue                                      # values do not recur: codes, not names
        if sum(n for k, n in values.items() if _looks_like_name(k)) < 0.8 * matches:
            continue
        with_truth = sum(sum(c.values()) for c in value_who.values())
        agreeing = sum(c.most_common(1)[0][1] for c in value_who.values() if c)
        conflicts = [{"name": k, "who": [names.get(("who", w), w) for w in c]} for k, c in value_who.items() if len(c) > 1]
        if with_truth == 0:
            continue                                      # nothing proves the value is a WHO
        naming = sum(n for k, c in value_who.items() for w, n in c.items() if k in identity.get(w, ()))
        if naming < 0.6 * with_truth:
            continue                                      # the value does not name the known WHO
        consistency = agreeing / with_truth
        resolvable = sum(n for k, n in values.items() if resolver.by_identity(k)[0] is not None)
        evidence = {"matches": matches, "distinct_values": len(values), "with_truth": with_truth,
                    "human_matches": sum(sum(c.values()) for c in human_value_who.values()),
                    "consistency": round(consistency, 4), "names_known_who": round(naming / with_truth, 4),
                    "conflicts": len(conflicts),
                    "exceptions": conflicts[:EXAMPLES], "resolves_to_existing_who": resolvable,
                    "examples": examples, "top_values": values.most_common(5)}
        if consistency < 0.9:
            continue
        cand = Candidate("STRUCTURAL", {"start_marker": start, "end_marker": end},
                         DETERMINISTIC if consistency >= MIN_STRUCTURAL_CONSISTENCY and not conflicts else PROBABILISTIC,
                         evidence)
        covering = _covering_general_rule(observations, start, end, existing_markers)
        if covering is not None:
            cand.covered_by = f"Pattern already covered by active General Rule {covering!r}"
        out.append(cand)
    return out


def _covering_general_rule(observations, start, end, existing_markers) -> str | None:
    """The active General Rule that already knows this marker pair, or None.

    Identical markers (case-insensitive) cover it. So does a rule with
    different markers that extracts the SAME value from every transaction
    this pair matches (BANK_ACTIONABLE_CLASSIFICATION_LEARNING_001): RF-One
    already reads that counterparty, so there is nothing for a person to
    decide."""
    if (start.upper(), end.upper()) in existing_markers:
        return existing_markers[(start.upper(), end.upper())]
    matched = []
    for o in observations:
        v = general_rules.extract(o.raw.description, start, end)
        if v is not None:
            matched.append((o.raw.description, wr.who_key(v)))
    if not matched:
        return None
    for (rule_start, rule_end), name in existing_markers.items():
        if all((lambda x: x is not None and wr.who_key(x) == key)(
                general_rules.extract(desc, rule_start, rule_end)) for desc, key in matched):
            return name
    return None


def _format_words(observations) -> frozenset:
    """Words of the bank FORMAT (ORIG, TRACE, PAYMENT, our own name...): they
    appear in transactions of many different counterparties."""
    seen: dict[str, set] = defaultdict(set)
    for o in observations:
        who = (o.truth.who_id if o.truth is not None and o.truth.who_id is not None else o.raw.recognized_who)
        if who is None:
            continue
        for w in set(o.raw.normalized.split()):
            seen[w].add(who)
    return frozenset(w for w, whos in seen.items() if len(whos) >= 5)


def _who(observations, existing_who_rules, names, manual_only=frozenset()) -> list[Candidate]:
    """A phrase that, wherever a WHO is known, always means the same WHO, and
    also appears in transactions that have no WHO yet (the gap).

    A Manual Only WHO is never a target (BANK_WHO_MANUAL_ONLY_001); its
    transactions still count as evidence — a phrase that also names it is
    still not unique to another WHO."""
    fmt = _format_words(observations)
    index: dict[str, list[Observation]] = defaultdict(list)
    for o in observations:
        for g in _ngrams(o.raw.normalized, exclude=fmt):
            index[g].append(o)
    by_who: dict[int, list[Observation]] = defaultdict(list)
    for o in observations:
        if o.truth is not None and o.truth.who_id is not None:
            by_who[o.truth.who_id].append(o)
    out = []
    for who_id, obs in by_who.items():
        if who_id in manual_only or len(obs) < MIN_WHO_SUPPORT:
            continue
        common = Counter(g for o in obs for g in _ngrams(o.raw.normalized, exclude=fmt))
        best = None
        for phrase, n in common.items():
            if n < max(MIN_WHO_SUPPORT, 0.8 * len(obs)) or len(phrase) < 5:
                continue
            hits = index[phrase]
            truth_who = Counter(o.truth.who_id for o in hits if o.truth is not None and o.truth.who_id is not None)
            if set(truth_who) != {who_id}:
                continue                                  # the phrase also means another WHO
            gap = [o for o in hits if o.truth is None or o.truth.who_id is None]
            if any(o.raw.recognized_who not in (None, who_id) for o in gap):
                continue                                  # the parser reads another counterparty there
            if not gap:
                continue                                  # nothing left to learn: already covered
            if best is None or len(phrase) > len(best[0]) or (len(phrase) == len(best[0]) and len(hits) > len(best[1])):
                best = (phrase, hits, gap, truth_who[who_id])
        if best is None:
            continue
        phrase, hits, gap, with_truth = best
        evidence = {"matches": len(hits), "with_truth": with_truth, "gap": len(gap),
                    "human_matches": sum(1 for o in hits if o.human), "conflicts": 0, "exceptions": [],
                    "examples": [{"description": o.raw.description[:140]} for o in hits[:EXAMPLES]]}
        cand = Candidate("WHO", {"phrase": phrase, "who_id": who_id}, DETERMINISTIC, evidence)
        covering = next((p for p, w in existing_who_rules if w == who_id and (p in phrase or phrase in p)), None)
        if covering is not None:
            cand.covered_by = f"Pattern already covered by active WHO Rule {covering!r}"
        out.append(cand)
    return out


def _why_rule_coverage(candidate: Candidate, active_why_rules: dict) -> None:
    """Mark a WHY candidate an active WHY Rule already expresses as covered.

    Covered: an active rule of the same WHO with the same WHY and the same
    conditions, or with no condition at all (it already gives that WHY to
    every transaction of the WHO). A rule with the same conditions but a
    DIFFERENT WHY is a real conflict: the candidate stays actionable and
    says so, because a person has to decide."""
    p = candidate.proposal
    phrase = recognition.normalize_description_for_recognition(p.get("description_contains") or "") or None
    conditions = (phrase, p.get("direction"), p.get("instrument_type"))
    for rule in active_why_rules.get(p["who_id"], ()):
        rule_conditions = (rule.description_contains, rule.direction, rule.instrument_type)
        if rule.transaction_reason_id == p["why_id"] and rule_conditions in (conditions, (None, None, None)):
            candidate.covered_by = f"Pattern already covered by active WHY Rule #{rule.id}"
            return
        if rule_conditions == conditions and rule.transaction_reason_id != p["why_id"]:
            candidate.evidence["conflicts_with"] = (
                f"Active WHY Rule #{rule.id} has the same conditions but names a different WHY.")


def _why(observations, associations, names) -> tuple[list[Candidate], dict]:
    """Per WHO, from HUMAN WHY truth only: one universal WHY when the evidence
    proves it, else a stable distinguishing feature; anything less is a
    probabilistic pattern, never a rule."""
    by_who: dict[int, list[Observation]] = defaultdict(list)
    for o in observations:
        if o.human and o.truth.who_id is not None and o.truth.why_id is not None:
            by_who[o.truth.who_id].append(o)
    out, insufficient = [], {}
    for who_id, obs in by_who.items():
        if len(obs) < MIN_HUMAN_FOR_WHY:
            insufficient[who_id] = len(obs)
            continue
        whys = Counter(o.truth.why_id for o in obs)
        top_why, top_n = whys.most_common(1)[0]
        multi_known = len(associations.get(who_id, set())) > 1
        if len(whys) == 1 and not multi_known:
            out.append(Candidate("WHY", {"who_id": who_id, "why_id": top_why}, DETERMINISTIC,
                                 {"human_matches": len(obs), "matches": len(obs), "share": 1.0, "conflicts": 0,
                                  "exceptions": [], "examples": [{"description": o.raw.description[:140]} for o in obs[:EXAMPLES]]}))
            continue
        features: dict[tuple, list[Observation]] = defaultdict(list)
        for o in obs:
            features[("direction", o.raw.direction)].append(o)
            if o.raw.instrument_type:
                features[("instrument_type", o.raw.instrument_type)].append(o)
            for g in _ngrams(o.raw.normalized, 2):
                features[("description_contains", g)].append(o)
        found = False
        for (kind, value), fobs in sorted(features.items(), key=lambda kv: -len(kv[1])):
            fwhys = Counter(o.truth.why_id for o in fobs)
            if len(fobs) >= MIN_HUMAN_FOR_WHY and len(fwhys) == 1 and len(fobs) < len(obs) + 1 and len(whys) > 1:
                why_id = next(iter(fwhys))
                outside = [o for o in obs if o not in fobs and o.truth.why_id == why_id]
                out.append(Candidate("WHY", {"who_id": who_id, "why_id": why_id, kind: value}, DETERMINISTIC,
                                     {"human_matches": len(fobs), "matches": len(fobs), "share": 1.0, "conflicts": 0,
                                      "uncovered_same_why": len(outside), "exceptions": [],
                                      "examples": [{"description": o.raw.description[:140]} for o in fobs[:EXAMPLES]]}))
                found = True
                break
        if not found and top_n / len(obs) >= MIN_PROBABILISTIC_SHARE:
            exceptions = [{"description": o.raw.description[:140], "why": names.get(("why", o.truth.why_id))}
                          for o in obs if o.truth.why_id != top_why][:EXAMPLES]
            out.append(Candidate("WHY", {"who_id": who_id, "why_id": top_why}, PROBABILISTIC,
                                 {"human_matches": len(obs), "matches": len(obs), "share": round(top_n / len(obs), 4),
                                  "conflicts": len(obs) - top_n, "exceptions": exceptions,
                                  "examples": [{"description": o.raw.description[:140]} for o in obs[:EXAMPLES]]}))
    return out, insufficient


def _names(session: Session) -> dict:
    names = {("who", i): n for i, n in session.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name))}
    names.update({("why", i): n for i, n in session.execute(select(m.BankTransactionReason.id, m.BankTransactionReason.name))})
    return names


def _manual_only(session: Session) -> frozenset:
    """WHO a person excluded from individual WHO Rules (BANK_WHO_MANUAL_ONLY_001)."""
    return frozenset(session.scalars(select(m.BankOccurrence.id).where(m.BankOccurrence.manual_only.is_(True))))


def _knowledge(session: Session):
    markers = {(r.start_marker.upper(), r.end_marker.upper()): r.name
               for r in general_rules.rules(session) if r.status == general_rules.ACTIVE}
    who_rules_ = [(r.normalized_pattern, r.occurrence_id) for r in session.scalars(
        select(m.BankRecognitionRule).where(m.BankRecognitionRule.status == "ACTIVE"))]
    associations: dict[int, set] = defaultdict(set)
    for oid, rid in session.execute(select(m.BankOccurrenceReasonAssociation.occurrence_id,
                                           m.BankOccurrenceReasonAssociation.transaction_reason_id)
                                    .where(m.BankOccurrenceReasonAssociation.active.is_(True))):
        associations[oid].add(rid)
    return markers, who_rules_, associations


def find_candidates(session: Session, observations: list[Observation] | None = None,
                    explainer: PatternExplainer | None = None) -> tuple[list[Candidate], dict]:
    """Pure discovery: candidates and a summary, nothing written."""
    observations = observations if observations is not None else load_observations(session)
    names = _names(session)
    markers, who_rules_, associations = _knowledge(session)
    resolver = wr.CanonicalWhoResolver(session)
    candidates = _structural(observations, markers, resolver, names, _identity_keys(session))
    manual_only = _manual_only(session)
    candidates += _who(observations, who_rules_, names, manual_only)
    why_candidates, insufficient = _why(observations, associations, names)
    active_why_rules = why_rules.active_by_who(session)
    for c in why_candidates:
        _why_rule_coverage(c, active_why_rules)
    candidates += why_candidates
    explainer = explainer or DeterministicExplainer()
    for c in candidates:
        c.evidence["explanation"] = explainer.explain(c, names)
        c.evidence["provenance_note"] = (
            "human-confirmed evidence" if c.evidence_level == VERIFIED else
            "support evidence only (rule / structural / standard results) — not human-verified")
    provenance = Counter(o.truth.provenance for o in observations if o.truth is not None)
    summary = {
        "observations": len(observations), "with_truth": sum(provenance.values()),
        "truth_by_provenance": dict(provenance),
        "human_why_examples": sum(1 for o in observations if o.human and o.truth.why_id is not None),
        "who_with_insufficient_human_why": {names.get(("who", k), k): v for k, v in insufficient.items()},
        "manual_only_who_excluded": len(manual_only),
        "first_date": min((o.raw.posting_date for o in observations), default=None),
        "last_date": max((o.raw.posting_date for o in observations), default=None),
    }
    return candidates, summary


def discover(session: Session, *, account_id: int | None = None,
             explainer: PatternExplainer | None = None) -> "m.BankLearningRun":
    """The explicit Discover Patterns action: find candidates and store them
    as suggestions, honouring rejection memory."""
    candidates, summary = find_candidates(session, explainer=explainer)
    run = m.BankLearningRun(kind="DISCOVERY", created_by_account_id=account_id, summary="{}")
    session.add(run)
    session.flush()
    existing = {s.fingerprint: s for s in session.scalars(select(m.BankPatternSuggestion))}
    counts = Counter()
    # What the Product Owner has to decide after this run: new deterministic
    # suggestions, and rejected ones re-proposed on materially new evidence.
    # Covered, approved and probabilistic patterns are knowledge, not work.
    new_actionable = 0
    for c in candidates:
        s = existing.get(c.fingerprint)
        status = "COVERED" if c.covered_by else "SUGGESTED"
        actionable = status == "SUGGESTED" and c.determinism == DETERMINISTIC
        if c.covered_by:
            c.evidence["covered_by"] = c.covered_by
        if s is None:
            session.add(m.BankPatternSuggestion(
                fingerprint=c.fingerprint, pattern_type=c.pattern_type, determinism=c.determinism, status=status,
                proposal=json.dumps(c.proposal), evidence=json.dumps(c.evidence, default=str),
                evidence_level=c.evidence_level, discovery_run_id=run.id))
            counts["new_" + status.lower()] += 1
            new_actionable += actionable
            continue
        if s.status == "APPROVED":
            counts["already_approved"] += 1
            continue
        if s.status == "REJECTED":
            before = s.rejected_evidence_size or 0
            if c.size >= max(before + 3, int(before * 1.5)):
                s.status, s.previously_rejected = status, True
                counts["re_proposed_new_evidence"] += 1
                new_actionable += actionable
            else:
                counts["suppressed_rejected"] += 1
                continue
        else:
            s.status = status
            counts["updated_" + status.lower()] += 1
        s.determinism, s.evidence_level = c.determinism, c.evidence_level
        s.proposal, s.evidence = json.dumps(c.proposal), json.dumps(c.evidence, default=str)
        s.discovery_run_id = run.id
    summary["result"] = dict(counts)
    summary["new_actionable"] = new_actionable
    summary["candidates"] = Counter(f"{c.pattern_type}/{c.determinism}" + ("/COVERED" if c.covered_by else "")
                                    for c in candidates)
    run.summary = json.dumps(summary, default=str)
    session.flush()
    return run


# ---------------------------------------------------------------------------
# TEST — read only
# ---------------------------------------------------------------------------


def _predict(pattern_type: str, proposal: dict, o: Observation, resolver) -> int | None:
    """What the proposed rule would conclude for one raw input: a WHO id
    (STRUCTURAL / WHO) or a WHY id (WHY, given the KNOWN WHO)."""
    if pattern_type == "STRUCTURAL":
        v = general_rules.extract(o.raw.description, proposal["start_marker"], proposal["end_marker"])
        if v is None:
            return None
        found = resolver.by_identity(v)[0]
        return found.id if found is not None else -1        # -1: matched, but no known WHO
    if pattern_type == "WHO":
        return proposal["who_id"] if proposal["phrase"] in o.raw.normalized else None
    rule = _RuleView(proposal)
    if o.truth is None or o.truth.who_id != proposal["who_id"]:
        return None
    return proposal["why_id"] if why_rules.matches(rule, why_rules.Evidence(o.raw.normalized, o.raw.direction,
                                                                           o.raw.instrument_type)) else None


@dataclass
class _RuleView:
    proposal: dict

    @property
    def description_contains(self):
        return self.proposal.get("description_contains")

    @property
    def direction(self):
        return self.proposal.get("direction")

    @property
    def instrument_type(self):
        return self.proposal.get("instrument_type")

    @property
    def transaction_reason_id(self):
        return self.proposal.get("why_id")


def test_suggestion(session: Session, suggestion: "m.BankPatternSuggestion") -> dict:
    """Read-only: what the rule would match, and how that compares with the
    known truth — overall and with HUMAN truth alone."""
    proposal = json.loads(suggestion.proposal)
    observations = load_observations(session)
    resolver = wr.CanonicalWhoResolver(session)
    r = Counter()
    mismatches = []
    for o in observations:
        predicted = _predict(suggestion.pattern_type, proposal, o, resolver)
        if predicted is None:
            continue
        r["matches"] += 1
        if predicted == -1:
            r["matched_unknown_who"] += 1
            continue
        actual = None
        if o.truth is not None:
            actual = o.truth.why_id if suggestion.pattern_type == "WHY" else o.truth.who_id
        if actual is None:
            r["unresolved_truth"] += 1
            continue
        tier = "human" if o.human else "support"
        if actual == predicted:
            r[f"correct_{tier}"] += 1
        else:
            r[f"mismatch_{tier}"] += 1
            if len(mismatches) < EXAMPLES:
                mismatches.append({"description": o.raw.description[:140], "provenance": o.truth.provenance})
    correct = r["correct_human"] + r["correct_support"]
    wrong = r["mismatch_human"] + r["mismatch_support"]
    return {**r, "correct": correct, "false_positives": wrong, "exceptions": mismatches,
            "coverage": round(r["matches"] / len(observations), 4) if observations else 0.0,
            "precision": round(correct / (correct + wrong), 4) if correct + wrong else None,
            "precision_human": (round(r["correct_human"] / (r["correct_human"] + r["mismatch_human"]), 4)
                                if r["correct_human"] + r["mismatch_human"] else None),
            "note": "No transaction is changed by a test."}


# ---------------------------------------------------------------------------
# APPROVE / REJECT — routed to the existing stores
# ---------------------------------------------------------------------------


def approve(session: Session, *, suggestion_id: int, account_id: int | None) -> "m.BankPatternSuggestion":
    s = session.get(m.BankPatternSuggestion, suggestion_id)
    if s is None:
        raise ValueError("That suggestion does not exist.")
    if s.status != "SUGGESTED":
        raise ValueError(f"Only a suggested pattern can be approved (this one is {s.status.lower()}).")
    if s.determinism != DETERMINISTIC:
        raise ValueError("A probabilistic pattern is shown for information only and cannot become a rule.")
    p = json.loads(s.proposal)
    if s.pattern_type == "STRUCTURAL":
        rule = general_rules.save_rule(session, rule_id=None,
                                       name=f"Learned — between {p['start_marker']} and {p['end_marker']}"[:120],
                                       start_marker=p["start_marker"], end_marker=p["end_marker"], active=True,
                                       account_id=account_id)
        s.routed_to = f"general_rule:{rule.id}"
    elif s.pattern_type == "WHO":
        target = session.get(m.BankOccurrence, p["who_id"])
        if target is not None and target.manual_only:
            raise ValueError(f"WHO “{target.canonical_name}” is Manual Only: it takes no WHO Rule.")
        rule = recognition.create_or_reuse_rule(
            session, match_type="CONTAINS_TEXT", normalized_pattern=p["phrase"], occurrence_id=p["who_id"],
            transaction_reason_id=None, payment_instrument_id=None, direction=None, auto_apply_enabled=True,
            created_from_transaction_id=None)
        s.routed_to = f"who_rule:{rule.id}"
    else:
        rule = why_rules.create_rule(session, occurrence_id=p["who_id"], transaction_reason_id=p["why_id"],
                                     description_contains=p.get("description_contains"), direction=p.get("direction"),
                                     instrument_type=p.get("instrument_type"), approved_by_account_id=account_id,
                                     approved_at=datetime.now(UTC), evidence=json.loads(s.evidence))
        s.routed_to = f"why_rule:{rule.id}"
    s.status, s.decided_by_account_id, s.decided_at = "APPROVED", account_id, datetime.now(UTC)
    session.flush()
    return s


def reject(session: Session, *, suggestion_id: int, account_id: int | None) -> "m.BankPatternSuggestion":
    s = session.get(m.BankPatternSuggestion, suggestion_id)
    if s is None:
        raise ValueError("That suggestion does not exist.")
    if s.status == "APPROVED":
        raise ValueError("An approved pattern is a rule now; disable the rule instead.")
    e = json.loads(s.evidence)
    s.status, s.decided_by_account_id, s.decided_at = "REJECTED", account_id, datetime.now(UTC)
    s.rejected_evidence_size = int(e.get("matches", 0)) + int(e.get("human_matches", 0))
    session.flush()
    return s


def actionable_suggestions(session: Session) -> list["m.BankPatternSuggestion"]:
    """What the Classification page shows: only patterns that need a human
    decision (BANK_ACTIONABLE_CLASSIFICATION_LEARNING_001).

    That is a SUGGESTED, DETERMINISTIC pattern — new, or re-proposed on new
    evidence, or in conflict with an existing rule. COVERED (RF-One already
    knows it), APPROVED (it is a rule now, in its own store), REJECTED
    (remembered by fingerprint) and PROBABILISTIC (cannot become a rule) are
    kept for audit and never listed."""
    rows = session.scalars(select(m.BankPatternSuggestion).where(
        m.BankPatternSuggestion.status == "SUGGESTED",
        m.BankPatternSuggestion.determinism == DETERMINISTIC))
    return sorted(rows, key=lambda s: (s.pattern_type, -s.id))


def suggestions(session: Session) -> list["m.BankPatternSuggestion"]:
    """Every stored suggestion, whatever its state — audit and tests only."""
    order = {"SUGGESTED": 0, "COVERED": 1, "APPROVED": 2, "REJECTED": 3}
    rows = list(session.scalars(select(m.BankPatternSuggestion)))
    return sorted(rows, key=lambda s: (order.get(s.status, 9), s.pattern_type, -s.id))


def latest_run(session: Session, kind: str) -> "m.BankLearningRun | None":
    return session.scalars(select(m.BankLearningRun).where(m.BankLearningRun.kind == kind)
                           .order_by(m.BankLearningRun.id.desc())).first()


# ---------------------------------------------------------------------------
# TEMPORAL BACKTEST — train on months before, test the next month, truth hidden
# ---------------------------------------------------------------------------


class _NoResolver:
    """The backtest never resolves through present-day rules."""

    def by_identity(self, *_names):
        return None, None, None


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _learned_rules(train: list[Observation], names: dict, identity: dict, manual_only=frozenset()):
    """What discovery would have proposed from the training months alone —
    and, simulating approval, the deterministic ones as plain rules. The
    structural value -> WHO map is learned from training truth only (no
    present-day alias or rule may leak into the past)."""
    structural = []
    accepted = {(c.proposal["start_marker"], c.proposal["end_marker"])
                for c in _structural(train, {}, _NoResolver(), names, identity) if c.determinism == DETERMINISTIC}
    for start, end in sorted(accepted):
        value_who: dict[str, Counter] = defaultdict(Counter)
        for o in train:
            v = general_rules.extract(o.raw.description, start, end)
            if v is not None and o.truth is not None and o.truth.who_id is not None:
                value_who[wr.who_key(v)][o.truth.who_id] += 1
        with_truth = sum(sum(c.values()) for c in value_who.values())
        if not with_truth or any(len(c) > 1 for c in value_who.values()) or len(value_who) < MIN_STRUCTURAL_VALUES:
            continue
        structural.append((start, end, {k: c.most_common(1)[0][0] for k, c in value_who.items()}))
    who = [(c.proposal["phrase"], c.proposal["who_id"]) for c in _who(train, [], names, manual_only)]
    why_c, _ = _why(train, {}, names)
    why = [c.proposal for c in why_c if c.determinism == DETERMINISTIC]
    return structural, who, why


def backtest(session: Session, *, first_test_month: date = date(2025, 7, 1),
             account_id: int | None = None) -> "m.BankLearningRun":
    """For each month from `first_test_month`: learn from every earlier
    month, hide the month's refined truth, predict from raw input with the
    learned deterministic rules only, then compare with the truth.

    Two truth tiers are reported separately and never merged:
      HUMAN    — decisions a person made: the only real accuracy measure;
      SUPPORT  — rule / structural / Standard decisions: agreement with current
                 deterministic knowledge, NOT accuracy."""
    names = _names(session)
    identity = _identity_keys(session)
    manual_only = _manual_only(session)
    everything = load_observations(session)
    months = sorted({_month_start(o.raw.posting_date) for o in everything if o.raw.posting_date >= first_test_month})
    rows = []
    for month in months:
        nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        train = [o for o in everything if o.raw.posting_date < month]
        test = [o for o in everything if month <= o.raw.posting_date < nxt]
        structural, who_rules_, why_rules_ = _learned_rules(train, names, identity, manual_only)
        tiers = {"HUMAN": Counter(), "SUPPORT": Counter()}
        zero = dict.fromkeys(("tested", "who_tested", "who_correct", "who_false", "who_left", "why_tested",
                              "why_correct", "why_false", "why_left"), 0)
        for o in test:
            hidden = o.truth                               # never read while predicting
            raw = Observation(o.raw, None)
            who_pred = None
            for start, end, mapping in structural:
                v = general_rules.extract(raw.raw.description, start, end)
                if v is not None and wr.who_key(v) in mapping:
                    who_pred = mapping[wr.who_key(v)]
                    break
            if who_pred is None:
                for phrase, who_id in who_rules_:
                    if phrase in raw.raw.normalized:
                        who_pred = who_id
                        break
            why_pred = None
            if who_pred is not None:
                applicable = [_RuleView(p) for p in why_rules_ if p["who_id"] == who_pred]
                chosen = why_rules.choose(applicable, why_rules.Evidence(raw.raw.normalized, raw.raw.direction,
                                                                          raw.raw.instrument_type))
                why_pred = chosen.proposal["why_id"] if chosen is not None else None
            if hidden is None:
                continue
            c = tiers["HUMAN" if hidden.provenance == HUMAN else "SUPPORT"]
            c["tested"] += 1
            if hidden.who_id is not None:
                c["who_tested"] += 1
                if who_pred is None:
                    c["who_left"] += 1
                elif who_pred == hidden.who_id:
                    c["who_correct"] += 1
                else:
                    c["who_false"] += 1
            if hidden.why_id is not None:
                c["why_tested"] += 1
                if why_pred is None:
                    c["why_left"] += 1
                elif why_pred == hidden.why_id:
                    c["why_correct"] += 1
                else:
                    c["why_false"] += 1
        row = {"month": month.isoformat()[:7], "transactions": len(test), "train_transactions": len(train),
               "learned": {"structural": len(structural), "who": len(who_rules_), "why": len(why_rules_)}}
        for tier, c in tiers.items():
            predicted = c["who_correct"] + c["who_false"]
            row[tier] = {
                **zero, **c,
                "coverage": round(predicted / c["who_tested"], 4) if c["who_tested"] else None,
                "precision": round(c["who_correct"] / predicted, 4) if predicted else None,
                "why_coverage": (round((c["why_correct"] + c["why_false"]) / c["why_tested"], 4)
                                 if c["why_tested"] else None),
                "manual_before": c["who_tested"], "manual_after": c["who_tested"] - c["who_correct"],
                "reliable": c["tested"] >= RELIABLE_HUMAN_TRUTH if tier == "HUMAN" else None,
            }
        rows.append(row)
    total = {tier: Counter() for tier in ("HUMAN", "SUPPORT")}
    for row in rows:
        for tier in total:
            for k in ("tested", "who_tested", "who_correct", "who_false", "who_left", "why_tested", "why_correct",
                      "why_false", "why_left", "manual_before", "manual_after"):
                total[tier][k] += row[tier].get(k, 0)
    summary = {"months": rows, "totals": {t: dict(c) for t, c in total.items()},
               "human_truth_reliable": total["HUMAN"]["tested"] >= RELIABLE_HUMAN_TRUTH,
               "note": ("HUMAN rows measure accuracy; SUPPORT rows only measure agreement with rule / structural / "
                        "Standard results and are not accuracy.")}
    run = m.BankLearningRun(kind="BACKTEST", created_by_account_id=account_id, summary=json.dumps(summary, default=str))
    session.add(run)
    session.flush()
    return run
