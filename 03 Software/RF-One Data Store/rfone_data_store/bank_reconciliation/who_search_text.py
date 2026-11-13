"""WHO recognition (BANK_WHO_RULES_001, formerly BANK_WHO_SEARCH_TEXT_001): the ONE path that recognises the WHO of
a bank movement, shared by the WHO Rules page and the reconciliation engine — same logic, same order.

Two modes only, in this order:

1. **Guided AI rules** — the approved rules, by precedence: the WHO rules (defined in conversation with the AI to
   read the WHO only) anchored on a text; then the WHO named by the older approved text rules (made mainly for the
   WHY); then the WHO rules anchored on nothing. The first level that reads a WHO decides; rules of that level
   that read different WHO send the movement to a person (RULES_DISAGREE).
2. **Name / alias search** — only for the movements no rule read: the description contains, as whole words, the
   name or an alias of a registered WHO (compared on the WHO identity key, `who_recognition.who_key`). One WHO:
   it is proposed. Several WHO, or an alias held by several WHO: the movement goes to a person (TEXT_AMBIGUOUS).
   A WHO is never invented here.

Nothing else recognises a WHO (no history memory, no AI). Recognition is a proposal: it never writes a WHO, WHY,
WHAT or classification on a movement, and a person's WHO decision is never replaced (the engine protects it).

The page also manages the texts to search: an alias of an existing WHO, or the name of a new WHO
(`manual_reconciliation.create_who`, the one creation path). Saving writes only the catalog.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select

from .. import models as m
from . import ai_rules, flow, manual_reconciliation, who_recognition as wr, who_registration

ALIAS_FAMILY = "WHO_SEARCH_TEXT"
MIN_KEY_LENGTH = 4

RULE, TEXT = "RULE", "TEXT"
FOUND, RULES_DISAGREE, TEXT_AMBIGUOUS, NONE = "FOUND", "RULES_DISAGREE", "TEXT_AMBIGUOUS", "NONE"


def search_keys(db) -> list[tuple[str, int]]:
    """(key, WHO id) for every active WHO's name and every alias of an active WHO."""
    active = {o.id: o.canonical_name for o in db.scalars(select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))}
    keys = {(wr.who_key(name), oid) for oid, name in active.items()}
    for oid, alias_key in db.execute(select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_key)):
        if oid in active:
            keys.add((alias_key, oid))
    return [(k, oid) for k, oid in keys if k and len(k) >= MIN_KEY_LENGTH]


def recognise(description: str | None, keys: list[tuple[str, int]]) -> list[int]:
    """The WHO whose key appears in the description as whole words."""
    text = f" {wr.who_key(description)} "
    return sorted({oid for key, oid in keys if f" {key} " in text})


@dataclass
class Recognition:
    outcome: str                      # FOUND, RULES_DISAGREE, TEXT_AMBIGUOUS, NONE
    who: str | None = None            # the WHO found (its catalog name when it is a registered WHO)
    method: str | None = None         # RULE or TEXT
    known: bool = True                # False: a rule read a name that is not a registered WHO yet
    candidates: list = field(default_factory=list)   # the WHO in conflict
    evidence: str = ""
    legacy_hits: list = field(default_factory=list)  # (rule, version, execution) of older text rules, for WHY


class WhoRecogniser:
    """Load once (rules and the name/alias catalog), then `recognise` each movement."""

    def __init__(self, db, rules=None):
        rules = flow.entries(db, future=True) if rules is None else rules
        self.extractors = [e for e in rules if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "EXTRACTOR"]
        self.legacy = [e for e in rules if e[2].get("engine") != flow.ENGINE]
        self.keys = search_keys(db)
        self.names = {o.id: o.canonical_name for o in db.scalars(select(m.BankOccurrence))}
        self.by_key = {}
        for key, oid in self.keys:
            self.by_key.setdefault(key, set()).add(oid)
        self._db, self._rows = db, None
        self.new_who_guard = who_registration.NewWhoGuard(db)

    def _row(self, txn):
        if self._rows is None:
            self._rows = ai_rules.RowBuilder(self._db)
        return self._rows.row(txn, None)

    def catalog_name(self, name):
        owners = self.by_key.get(wr.who_key(name), set())
        return self.names[next(iter(owners))] if len(owners) == 1 else None

    def recognise(self, txn, row=None) -> Recognition:
        """`row`: the movement's rule row when the caller already has it (only older text rules read it)."""
        description = txn.description_original
        names, generic, legacy_names, legacy_hits = [], [], [], []
        for rule, version, spec in self.extractors:
            name = flow.extract(spec, description)
            if name:
                (generic if flow.is_generic(spec) else names).append(
                    (name, f"WHO rule #{rule.id} {rule.user_title or rule.title}"))
        if self.legacy:
            row = row if row is not None else self._row(txn)
            for rule, version, spec in self.legacy:
                try:
                    ex = ai_rules.execute(spec, row)
                except Exception:  # a malformed older rule never stops recognition
                    continue
                if ex.outcome != "MATCH":
                    continue
                legacy_hits.append((rule, version, ex))
                if ex.who and not ex.who_verify:
                    legacy_names.append((ex.who, f"text rule #{rule.id} {rule.user_title or rule.title}"))
        # A rule made to read the WHO is more specific than an older text rule that also names one.
        names = names or legacy_names or generic
        distinct = {}
        for name, ref in names:
            distinct.setdefault(wr.who_key(name), (name.strip().upper(), []))[1].append(ref)
        if len(distinct) == 1:
            name, refs = next(iter(distinct.values()))
            assessment = self.new_who_guard.assess(name)
            if assessment.state not in ("NEW", "EXISTING"):
                return Recognition(TEXT_AMBIGUOUS, method=RULE, known=False,
                                   candidates=assessment.candidates or [name], evidence=assessment.evidence,
                                   legacy_hits=legacy_hits)
            known = assessment.name if assessment.state == "EXISTING" else None
            return Recognition(FOUND, known or name, RULE, known is not None, evidence="; ".join(refs),
                               legacy_hits=legacy_hits)
        if len(distinct) > 1:
            return Recognition(RULES_DISAGREE, candidates=[v[0] for v in distinct.values()],
                               evidence="WHO rules disagree: " + " / ".join(
                                   f"{v[0]} ({'; '.join(v[1])})" for v in distinct.values()),
                               legacy_hits=legacy_hits)
        found = recognise(description, self.keys)
        if len(found) == 1:
            return Recognition(FOUND, self.names[found[0]], TEXT,
                               evidence="name or alias of the WHO found in the description", legacy_hits=legacy_hits)
        if found:
            whos = [self.names[i] for i in found]
            return Recognition(TEXT_AMBIGUOUS, candidates=whos, legacy_hits=legacy_hits,
                               evidence="the description contains several WHO names/aliases: " + " / ".join(whos))
        return Recognition(NONE, evidence="no WHO rule and no WHO name or alias in the description",
                           legacy_hits=legacy_hits)


def knowledge_signature(db) -> str:
    """Changes whenever what recognises a WHO changes — a rule saved, revised, paused or deleted, an alias added or
    moved, a WHO created, renamed or (de)activated: the engine then runs again (BANK_WHO_RULES_001)."""
    rules = [(r.id, r.status, v.id) for r, v, _s in flow.entries(db, future=True)]
    aliases = sorted(db.execute(select(m.BankOccurrenceAlias.id, m.BankOccurrenceAlias.occurrence_id,
                                       m.BankOccurrenceAlias.alias_key)).all())
    whos = sorted(db.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name, m.BankOccurrence.status)).all())
    reasons = sorted(db.execute(select(m.BankTransactionReason.id, m.BankTransactionReason.name, m.BankTransactionReason.status,
                                       m.BankTransactionReason.accounting_classification_id)).all())
    pairs = sorted(db.execute(select(m.BankWhoSourceClassification.occurrence_id,
        m.BankWhoSourceClassification.payment_instrument_id, m.BankWhoSourceClassification.transaction_reason_id)).all())
    whats = sorted(db.execute(select(m.BankAccountingClassification.id, m.BankAccountingClassification.code,
        m.BankAccountingClassification.name, m.BankAccountingClassification.statement_type,
        m.BankAccountingClassification.normal_balance)).all())
    data = json.dumps([rules, [list(a) for a in aliases], [list(w) for w in whos],
                       [list(x) for x in reasons], [list(x) for x in pairs], [list(x) for x in whats]], default=str)
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def movements(db) -> list[dict]:
    """Every movement with its recognised WHO (`whos`: the WHO, or the candidates in conflict) and `by`:
    RULE, TEXT, RULES_DISAGREE, TEXT_AMBIGUOUS or None — exactly what the engine computes."""
    recogniser = WhoRecogniser(db)
    sources = {i.id: i.display_name for i in db.scalars(select(m.PaymentInstrument))}
    out = []
    for t in db.scalars(select(m.FinancialTransaction)):
        r = recogniser.recognise(t)
        out.append(dict(id=t.id, source=sources.get(t.payment_instrument_id) or "—",
                        date=str(t.posting_date or t.transaction_date or ""), description=t.description_original or "",
                        amount_minor=t.amount_minor or 0, whos=[r.who] if r.who else r.candidates,
                        by=r.method if r.outcome == FOUND else (None if r.outcome == NONE else r.outcome),
                        known=r.known))
    out.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return out


def transaction_text(db, transaction_id: int) -> dict:
    """The movement's text as it arrived from the bank file: every field of its raw row."""
    txn = db.get(m.FinancialTransaction, transaction_id)
    if txn is None:
        raise ValueError("This movement no longer exists.")
    raw = db.scalar(select(m.RawBankTransaction).where(m.RawBankTransaction.normalized_transaction_id == txn.id).limit(1))
    fields = raw.raw_fields if raw is not None else {}
    if isinstance(fields, str):
        fields = json.loads(fields or "{}")
    return dict(id=txn.id, description=txn.description_original or "", fields=[[k, "" if v is None else str(v)] for k, v in fields.items()])


def has_association(db, occurrence_id: int) -> bool:
    """True when the WHO has at least one active possible WHY (each WHY carries its WHAT)."""
    return db.scalar(select(m.BankOccurrenceReasonAssociation.id).where(
        m.BankOccurrenceReasonAssociation.occurrence_id == occurrence_id,
        m.BankOccurrenceReasonAssociation.active.is_(True)).limit(1)) is not None


def save(db, *, text: str | None, occurrence_id: int | None, transaction_id: int | None = None) -> dict:
    """Save the text to search. With a WHO: an alias of that WHO. Without: a new WHO with this text as name
    (an existing WHO with the same identity is reused, never duplicated). Flushes, never commits."""
    clean = " ".join(str(text or "").split())
    key = wr.who_key(clean)
    if len(key) < MIN_KEY_LENGTH:
        raise ValueError(f"The text to search needs at least {MIN_KEY_LENGTH} letters or digits.")
    if occurrence_id is None:
        created = manual_reconciliation.create_who(db, name=clean)
        occurrence, outcome = created.occurrence, "reused" if created.reused else "created"
    else:
        occurrence = db.get(m.BankOccurrence, occurrence_id)
        if occurrence is None or occurrence.status != "ACTIVE":
            raise ValueError("This WHO does not exist or is inactive.")
        outcome = _add_alias(db, occurrence, clean, key, transaction_id)
    db.flush()
    return dict(who_id=occurrence.id, who=occurrence.canonical_name, outcome=outcome,
                needs_association=not has_association(db, occurrence.id))


def _add_alias(db, occurrence, text: str, key: str, transaction_id: int | None) -> str:
    """A text another active WHO is already recognised by is refused, never taken over."""
    for owner in db.scalars(select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE", m.BankOccurrence.id != occurrence.id)):
        if wr.who_key(owner.canonical_name) == key:
            raise ValueError(f"“{text}” is the name of the WHO {owner.canonical_name}.")
    owners = set(db.scalars(select(m.BankOccurrenceAlias.occurrence_id).where(m.BankOccurrenceAlias.alias_key == key)))
    for owner in owners - {occurrence.id}:
        other = db.get(m.BankOccurrence, owner)
        if other is not None and other.status == "ACTIVE":
            raise ValueError(f"“{text}” is already an alias of the WHO {other.canonical_name}.")
    if key == wr.who_key(occurrence.canonical_name) or occurrence.id in owners:
        return "already"
    db.add(m.BankOccurrenceAlias(occurrence_id=occurrence.id, alias_text=text[:255], alias_key=key[:255],
                                 source_family=ALIAS_FAMILY, source="HUMAN", first_financial_transaction_id=transaction_id))
    return "alias"
