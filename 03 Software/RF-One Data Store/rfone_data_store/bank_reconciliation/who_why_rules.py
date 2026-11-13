"""WHO WHY mode and WHO WHY rules (BANK_WHO_WHY_MODE_001, Product Owner, 2026-11-01).

Recognising WHO and determining WHY are two different steps. Once a WHO is recognised:

  UNIQUE    (default: every WHO without a row in `bank_who_why_modes`) the WHY is the one registered
            on the exact WHO + Source pair. A WHO with different WHYs on different Sources is UNIQUE:
            the pair already resolves it. When the pair has no WHY, an applicable WHO WHY rule may
            determine it; otherwise "Serve una classificazione WHO + Source".
  MULTIPLE  (set only by a person) the WHY depends on the single movement: only a WHO WHY rule decides.
            A WHY registered on the pair is kept but never used for it (no generic bypass).

A WHO WHY rule is stored like the WHY pattern rules (`BankAiRule` + immutable version, engine
`BANK_WHY_PATTERN`, method CODE) with `scope = "WHO"`: it applies only to the WHOs it names, after WHO
recognition, and never identifies a WHO (WHO identification rules are the guided AI rules). It reads the
same verifiable conditions as the WHY pattern rules (`why_patterns`: Source, Source type, accounting
subject at the movement date, direction, amount, description, Source information, RF-One evidence; each
True, False or MISSING) and its result is either a WHY of the catalog or a document from which the WHY is
read (`amazon_order`: the products of the Amazon order report matched to the movement by Charge
Identifier). WHAT always derives from the WHY; WHOM stays the Source owner (engine).

Outcome of the determination for a recognised WHO, with the open reasons:

  WHY_SOURCE_CLASSIFICATION   UNIQUE WHO, WHY from the pair
  WHO WHY RULE                one WHY from the rules that apply
  WHO_SOURCE_CLASSIFICATION_MISSING  "Serve una classificazione WHO + Source" (UNIQUE, no pair WHY, no rule)
  WHY_RULE_MISSING                   "Serve una regola per il WHY" (MULTIPLE, no applicable rule)
  WHY_DOCUMENT_MISSING               "Serve un documento o un chiarimento" (a rule applies but data is missing)
  WHY_RULES_CONFLICT                 "Regole in conflitto" (incompatible results)
  WHY_SPLIT_INCOMPLETE               "Ripartizione incompleta" (BANK_SPLIT_ALLOCATION_001: the document needs
                                     several WHYs and the split cannot be completed, e.g. "Importi di
                                     dettaglio mancanti"); a complete split resolves the movement (method SPLIT)

Scopes (BANK_RULE_SCOPE_AND_WHO_CATEGORY_001 §2-3, Product Owner, 2026-11-03). The same rule, lifecycle and
engine serve three scopes of WHY determination (never WHO recognition):

  WHO        `who_ids`: the WHOs it names
  CATEGORY   `categories`: every WHO whose category is confirmed, or declared on the movement's Source
             (`who_categories`); heterogeneous categories (marketplaces) are refused
  GENERAL    every recognised WHO; at least one condition must not be structural (Source subject, direction or
             Source type alone would be a generic WHY in disguise)

There is no fixed precedence. Every applicable rule of every scope is evaluated: the same WHY from several rules
is one result; different WHYs are "Regole in conflitto" for a person. A specific case that legitimately differs
is kept as an explicit exception of the broader rule (`exceptions`, e.g. WHO is one of ...). Replacing rules
(`supersede`) deactivates them after a person's approval, with history and `restore`.

Nothing here writes a movement classification. `set_mode`, `save_rule`, `set_active`, `supersede` and `restore`
are a person's actions.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import inspect, select

from .. import models as m
from . import who_categories, why_patterns

UNIQUE, MULTIPLE = "UNIQUE", "MULTIPLE"
MODES = (UNIQUE, MULTIPLE)
SCOPE = "WHO"
SCOPE_CATEGORY, SCOPE_GENERAL = "CATEGORY", "GENERAL"
SCOPES = (SCOPE, SCOPE_CATEGORY, SCOPE_GENERAL)
KIND_SUPERSEDE = "WHY_RULE_SUPERSEDE"
DOCUMENTS = {"amazon_order": "Amazon order report (products of the order matched by Charge Identifier)"}

NEEDS_PAIR = "WHO_SOURCE_CLASSIFICATION_MISSING"
NEEDS_RULE = "WHY_RULE_MISSING"
NEEDS_DOCUMENT = "WHY_DOCUMENT_MISSING"
CONFLICT = "WHY_RULES_CONFLICT"
SPLIT_INCOMPLETE = "WHY_SPLIT_INCOMPLETE"
LABELS = {NEEDS_PAIR: "Serve una classificazione WHO + Source",
          NEEDS_RULE: "Serve una regola per il WHY",
          NEEDS_DOCUMENT: "Serve un documento o un chiarimento",
          CONFLICT: "Regole in conflitto",
          SPLIT_INCOMPLETE: "Ripartizione incompleta"}
OPEN_REASONS = tuple(LABELS)

METHOD_PAIR = "WHO + SOURCE"
METHOD_RULE = "WHO WHY RULE"
METHOD_SPLIT = "SPLIT"
SPLIT = "SPLIT"                  # rule outcome: the document resolves the movement with several WHYs

# Amazon order evidence (the report kept by `bank_amazon`, kinds AMAZON_REPORT / AMAZON_RUN).
AMAZON_REPORT, AMAZON_RUN = "AMAZON_REPORT", "AMAZON_RUN"


# ---------------------------------------------------------------- WHO WHY mode

def _has_mode_table(db) -> bool:
    """A database not migrated yet has no mode table: every WHO is then UNIQUE (the behaviour so far)."""
    return inspect(db.get_bind()).has_table("bank_who_why_modes")


def modes(db) -> dict[int, str]:
    if not _has_mode_table(db):
        return {}
    return {r.occurrence_id: r.why_mode for r in db.scalars(select(m.BankWhoWhyMode))}


def set_mode(db, who_id: int, mode: str, *, account_id: int | None, note: str | None = None) -> str:
    """A person's choice. UNIQUE removes the row (the default), MULTIPLE records it. No classification,
    pair or rule is changed."""
    if mode not in MODES:
        raise ValueError("Mode must be UNIQUE or MULTIPLE.")
    who = db.get(m.BankOccurrence, who_id)
    if who is None:
        raise ValueError("WHO not found.")
    if not _has_mode_table(db):
        raise ValueError("The database needs the migration a5c220261101 (run.ps1 start --migrate).")
    row = db.get(m.BankWhoWhyMode, who_id)
    if mode == UNIQUE:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(m.BankWhoWhyMode(occurrence_id=who_id, why_mode=mode, note=(note or None),
                                updated_by_account_id=account_id))
    else:
        row.why_mode, row.note, row.updated_by_account_id = mode, (note or row.note), account_id
    db.flush()
    return mode


# ---------------------------------------------------------------- rules

def is_who_rule(spec) -> bool:
    """A WHY determination rule run after WHO recognition, of any scope (WHO, CATEGORY, GENERAL)."""
    return isinstance(spec, dict) and spec.get("engine") == why_patterns.ENGINE and spec.get("scope") in SCOPES


def rules(db, *, active_only: bool = True) -> list:
    """(rule, version, spec) of the WHO WHY rules; active ones by default."""
    source = why_patterns.all_rules(db)
    return [(r, v, s) for r, v, s in source if is_who_rule(s) and (not active_only or r.status == "ACTIVE")]


def validate(db, spec: dict) -> dict:
    """A WHO WHY rule as RF-One executes it; raises ValueError with a readable reason."""
    from . import why_what
    if not is_who_rule(spec):
        raise ValueError("Not a WHO WHY rule.")
    scope = spec["scope"]
    if scope == SCOPE:
        who_ids = spec.get("who_ids")
        if not isinstance(who_ids, list) or not who_ids or not all(type(x) is int for x in who_ids):
            raise ValueError("A WHO WHY rule names at least one WHO.")
        for who_id in who_ids:
            who = db.get(m.BankOccurrence, who_id)
            if who is None or who.status != "ACTIVE":
                raise ValueError(f"WHO #{who_id} is missing or inactive.")
    elif spec.get("who_ids"):
        raise ValueError("Only a rule for a single WHO names WHOs.")
    if scope == SCOPE_CATEGORY:
        categories = spec.get("categories")
        if not isinstance(categories, list) or not categories or any(c not in who_categories.CATEGORIES for c in categories):
            raise ValueError("A category rule names at least one known WHO category.")
        if any(c in who_categories.HETEROGENEOUS for c in categories):
            raise ValueError("A heterogeneous category (marketplace, general retailer) cannot determine one WHY.")
    elif spec.get("categories"):
        raise ValueError("Only a category rule names WHO categories.")
    if scope == SCOPE_GENERAL and all(why_patterns.kind_of(c) == why_patterns.STRUCTURAL for c in spec.get("conditions") or []):
        raise ValueError("A general rule needs a condition beyond the Source subject, direction or Source type.")
    has_why, has_document = isinstance(spec.get("why_id"), int), spec.get("document") is not None
    if has_why == has_document:
        raise ValueError("The result is either one WHY or one document the WHY is read from.")
    if has_why:
        reason = db.get(m.BankTransactionReason, spec["why_id"])
        if reason is None or reason.status != "ACTIVE":
            raise ValueError("The WHY is missing or inactive.")
        if why_what.is_provisional(db, reason):
            raise ValueError("A provisional WHY cannot be the result of a rule.")
    elif spec["document"] not in DOCUMENTS:
        raise ValueError("Unknown document: only " + ", ".join(DOCUMENTS) + ".")
    # Same vocabulary as the WHY pattern rules; the WHO is the anchor, so a condition on the accounting
    # subject alone (e.g. personal / company Source) is allowed here. At least one condition is required:
    # a WHO -> WHY rule without conditions would be a generic WHY in disguise.
    why_patterns.check_conditions(spec)
    return spec


def describe(spec: dict, whys=None, whos=None) -> str:
    """The rule in plain language."""
    names = [((whos or {}).get(i) or f"WHO #{i}") for i in spec.get("who_ids", [])]
    if spec.get("scope") == SCOPE_CATEGORY:
        anchor = "When the WHO category is " + ", ".join(who_categories.CATEGORIES.get(c, c) for c in spec["categories"])
    elif spec.get("scope") == SCOPE_GENERAL:
        anchor = "For every recognised WHO, when"
    else:
        anchor = f"When WHO is {', '.join(names)}"
    conditions = " and ".join(why_patterns.describe(c) for c in spec.get("conditions", []))
    if spec.get("document"):
        result = "WHY read from the " + DOCUMENTS[spec["document"]]
    else:
        reason = (whys or {}).get(spec.get("why_id"))
        result = "WHY " + (reason.name if reason is not None else spec.get("why") or f"#{spec.get('why_id')}")
    exceptions = "; ".join("except when " + " and ".join(why_patterns.describe(c) for c in e["conditions"])
                           for e in spec.get("exceptions", []))
    joiner = " " if spec.get("scope") == SCOPE_GENERAL else " and "
    return f"{anchor}{joiner}{conditions}: {result}" + (f" ({exceptions})" if exceptions else "")


def save_rule(db, spec: dict, *, account_id: int | None, active: bool = False, title: str | None = None):
    """A person saves a WHO WHY rule (version 1); INACTIVE unless explicitly activated. Nothing is classified
    here: the engine uses an active rule on its next run, human decisions stay protected."""
    spec = validate(db, dict(spec, version=why_patterns.SPEC_VERSION))
    whys = {spec["why_id"]: db.get(m.BankTransactionReason, spec["why_id"])} if spec.get("why_id") else {}
    whos = {i: db.get(m.BankOccurrence, i).canonical_name for i in spec.get("who_ids", [])}
    if spec.get("why_id"):
        spec["why"] = whys[spec["why_id"]].name
    text = describe(spec, whys, whos)
    rule = m.BankAiRule(title=(title or text)[:200], organization_kind="GENERAL",
                        status="ACTIVE" if active else "INACTIVE", apply_future=False,
                        created_by_account_id=account_id)
    db.add(rule)
    db.flush()
    db.add(m.BankAiRuleVersion(rule_id=rule.id, version_no=1, rule_text=text, spec=json.dumps(spec, ensure_ascii=False),
                               method="CODE", create_missing_who=False, override_protected=False,
                               created_by_account_id=account_id))
    db.flush()
    return rule


def set_active(db, rule_id: int, active: bool):
    from . import ai_rule_operations as ops
    rule = db.get(m.BankAiRule, rule_id)
    if rule is None or rule.deleted_at is not None or not is_who_rule(_spec(ops.current_version(rule))):
        raise ValueError("WHO WHY rule not found.")
    rule.status = "ACTIVE" if active else "INACTIVE"
    return rule


def supersede(db, new_rule_id: int, old_rule_ids: list[int], *, account_id: int | None, evidence: dict) -> dict:
    """After a simulation and a person's explicit approval, the rules a broader rule replaces are deactivated —
    never deleted. The record keeps who approved it, when, and the simulation that justified it."""
    from . import ai_rule_operations as ops
    new = db.get(m.BankAiRule, new_rule_id)
    if new is None or new.status != "ACTIVE" or not is_who_rule(_spec(ops.current_version(new))):
        raise ValueError("The replacing rule must be an active WHY rule.")
    olds = []
    for rule_id in old_rule_ids:
        rule = db.get(m.BankAiRule, rule_id)
        version = ops.current_version(rule) if rule is not None else None
        if rule is None or rule.deleted_at is not None or rule.status != "ACTIVE" or not is_who_rule(_spec(version)) \
                or rule.id == new_rule_id:
            raise ValueError(f"Rule #{rule_id} is not an active WHY rule that can be replaced.")
        olds.append((rule, version))
    for rule, _version in olds:
        rule.status = "INACTIVE"
    payload = dict(new_rule_id=new_rule_id, replaced=[dict(rule_id=r.id, version_no=v.version_no) for r, v in olds],
                   evidence=evidence, approved_by=account_id, approved_at=datetime.now(timezone.utc).isoformat(),
                   restored=False)
    record = m.BankFlowArtifact(kind=KIND_SUPERSEDE, payload=json.dumps(payload, ensure_ascii=False), account_id=account_id)
    db.add(record)
    db.flush()
    return dict(payload, record_id=record.id)


def replacements(db) -> list[dict]:
    return [dict(json.loads(a.payload), record_id=a.id) for a in db.scalars(
        select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == KIND_SUPERSEDE).order_by(m.BankFlowArtifact.id.desc()))]


def restore(db, record_id: int, *, account_id: int | None) -> dict:
    """Undo a replacement: the replaced rules are active again and the replacing rule is deactivated."""
    record = db.get(m.BankFlowArtifact, record_id)
    if record is None or record.kind != KIND_SUPERSEDE:
        raise ValueError("Replacement not found.")
    payload = json.loads(record.payload)
    if payload.get("restored"):
        raise ValueError("This replacement was already undone.")
    for item in payload["replaced"]:
        rule = db.get(m.BankAiRule, item["rule_id"])
        if rule is None or rule.deleted_at is not None:
            raise ValueError(f"Rule #{item['rule_id']} no longer exists: it cannot be restored.")
        rule.status = "ACTIVE"
    new = db.get(m.BankAiRule, payload["new_rule_id"])
    if new is not None:
        new.status = "INACTIVE"
    payload.update(restored=True, restored_by=account_id, restored_at=datetime.now(timezone.utc).isoformat())
    record.payload = json.dumps(payload, ensure_ascii=False)
    db.flush()
    return dict(payload, record_id=record.id)


def _spec(version):
    try:
        return json.loads(version.spec) if version is not None and version.spec else None
    except ValueError:
        return None


def knowledge_signature(db) -> str:
    """Changes with the WHO WHY modes and the Amazon order evidence (the rules are already in
    `why_patterns.knowledge_signature`)."""
    rows = sorted(modes(db).items())
    docs = list(db.execute(select(m.BankFlowArtifact.id, m.BankFlowArtifact.kind).where(
        m.BankFlowArtifact.kind.in_((AMAZON_REPORT, AMAZON_RUN))).order_by(m.BankFlowArtifact.id)))
    status = [(i, k, _status(db, i)) for i, k in docs if k == AMAZON_RUN]
    payload = json.dumps([rows, [d[0] for d in docs], status, who_categories.knowledge_signature(db)])
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _status(db, artifact_id):
    a = db.get(m.BankFlowArtifact, artifact_id)
    try:
        return json.loads(a.payload).get("status")
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- Amazon order evidence

_TOKEN = re.compile(r"[A-Z0-9]+")


def charge_groups(db, account_id: int | None = None) -> dict:
    """Products per Charge Identifier from the Amazon order reports; for overlapping exports the newest
    report's complete group wins (the `bank_amazon` rule). All accounts when `account_id` is None."""
    q = select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == AMAZON_REPORT)
    if account_id is not None:
        q = q.where(m.BankFlowArtifact.account_id == account_id)
    groups = {}
    for a in db.scalars(q.order_by(m.BankFlowArtifact.id.desc())):
        report = json.loads(a.payload)
        own = {}
        for row in report["rows"]:
            if row["charge"]:
                own.setdefault(row["charge"], []).append(dict(report_id=a.id, file_name=report["file_name"], **row))
        for code, rows in own.items():
            groups.setdefault(code, rows)
    return groups


def charge_matches(groups: dict, txns) -> dict:
    """Movements per Charge Identifier: the exact whole token in the description, no substring, date,
    amount or card fallback."""
    matches = {code: [] for code in groups}
    for t in txns:
        for token in set(_TOKEN.findall((t.description_original or "").upper())) & groups.keys():
            matches[token].append(t)
    return matches


class AmazonOrders:
    """The WHY of a movement read from its matched Amazon order (BANK_SPLIT_ALLOCATION_001 evidence).

    The link must be certain: exact Charge Identifier, equal amount, compatible currency and date
    (`split_allocation.AmazonEvidence`). Product WHYs come from the latest completed Amazon analysis of exactly
    those products, with HIGH confidence. Products with one WHY → that WHY; several WHYs → a split when the
    detail amounts allow it, otherwise "Importi di dettaglio mancanti". Never a blanket WHY."""

    def __init__(self, db, txns):
        from . import split_allocation
        self.evidence = split_allocation.amazon_evidence(db, txns)
        self.proposals = {}

    def proposal(self, txn):
        if txn.id not in self.proposals:
            self.proposals[txn.id] = self.evidence.proposal(txn)
        return self.proposals[txn.id]

    def read(self, txn) -> dict:
        """dict(state, why_id?, detail, proposal). States: WHY, SPLIT, NO_DOCUMENT, AMBIGUOUS, NOT_VERIFIED,
        NOT_ANALYSED, ITEM_UNCLEAR, MIXED (several WHYs, split incomplete)."""
        from . import split_allocation as S
        link = self.evidence.links.get(txn.id)
        p = self.proposal(txn)
        text = "; ".join(r["label"] + (f" ({r['detail']})" if r["detail"] else "") for r in p.reasons)
        if link is None:
            return dict(state="NO_DOCUMENT", detail="no Amazon order report has the Charge Identifier of this movement",
                        proposal=p)
        codes = ", ".join(link.codes)
        if link.state == S.AMBIGUOUS:
            return dict(state="AMBIGUOUS", detail=f"Charge Identifier {codes} is not matched to this movement alone",
                        proposal=p)
        if link.state != S.CERTAIN:
            return dict(state="NOT_VERIFIED", detail=f"order {codes}: {text}", proposal=p)
        if not all(c in self.evidence.item_whys for c in link.codes):
            return dict(state="NOT_ANALYSED", detail=f"the products of order {codes} have no current Amazon analysis",
                        proposal=p)
        if p.complete:
            if len(p.lines) == 1:
                return dict(state="WHY", why_id=p.lines[0].why_id, proposal=p,
                            detail=f"order {codes}: {sum(len(ln.items) for ln in p.lines)} product(s), one WHY")
            return dict(state="SPLIT", proposal=p,
                        detail=f"order {codes}: {len(p.lines)} split lines, total equal to the movement")
        found = {r["code"] for r in p.reasons}
        if S.ITEM_WHY_MISSING in found:
            unclear = next(r for r in p.reasons if r["code"] == S.ITEM_WHY_MISSING)
            return dict(state="ITEM_UNCLEAR", proposal=p,
                        detail=f"order {codes}: product without a WHY with HIGH confidence — {unclear['detail']}")
        return dict(state="MIXED", proposal=p, detail=f"order {codes} mixes products with different WHYs: {text}")


# ---------------------------------------------------------------- determination

def _scope_note(spec) -> str:
    if spec.get("scope") == SCOPE_CATEGORY:
        return " [category " + ", ".join(spec["categories"]) + "]"
    return " [general]" if spec.get("scope") == SCOPE_GENERAL else ""


@dataclass
class Determination:
    mode: str
    why_id: int | None = None
    method: str | None = None
    reference: str = ""
    code: str | None = None           # open reason (OPEN_REASONS) when no WHY
    message: str | None = None
    missing: list = field(default_factory=list)
    rules: list = field(default_factory=list)          # [(rule id, outcome, WHY or detail)]
    unused_pair_why: int | None = None                 # MULTIPLE: the registered pair WHY that was not used
    split: object = None                               # split_allocation.Proposal (complete: method SPLIT)

    @property
    def label(self):
        return LABELS.get(self.code)


class Resolver:
    """Determines the WHY of a movement whose WHO is recognised. Read-only."""

    def __init__(self, db, *, txns=(), rows=None):
        self.db = db
        self.modes = modes(db)
        self.rules = rules(db)
        self.by_who, self.by_category, self.general = {}, {}, []
        for entry in self.rules:
            self._index(entry)
        self.categories = who_categories.Categories(db)
        self._hidden = set()                            # rule ids left out by a simulation (`variant`)
        self._rows = rows
        self._txns = list(txns)
        self._info = None
        self._amazon = None
        self.splits = {}                                # txn id → split_allocation.Proposal from a document

    def mode(self, who_id) -> str:
        return self.modes.get(who_id, UNIQUE)

    def _index(self, entry):
        spec = entry[2]
        if spec["scope"] == SCOPE:
            for who_id in spec["who_ids"]:
                self.by_who.setdefault(who_id, []).append(entry)
        elif spec["scope"] == SCOPE_CATEGORY:
            for category in spec["categories"]:
                self.by_category.setdefault(category, []).append(entry)
        else:
            self.general.append(entry)

    def applicable(self, who_id, txn) -> list:
        """Every rule of every scope that concerns this WHO on this movement's Source — no precedence."""
        category, _basis = self.categories.category_for(who_id, txn.payment_instrument_id)
        entries = self.by_who.get(who_id, []) + (self.by_category.get(category, []) if category else []) + self.general
        return [e for e in entries if e[0].id not in self._hidden]

    @contextmanager
    def variant(self, add=(), hide=()):
        """Read-only simulation: some draft rules counted as active, some rule ids left out."""
        saved = ({k: list(v) for k, v in self.by_who.items()}, {k: list(v) for k, v in self.by_category.items()},
                 list(self.general), set(self._hidden))
        try:
            for entry in add:
                self._index(entry)
            self._hidden |= set(hide)
            yield self
        finally:
            self.by_who, self.by_category, self.general, self._hidden = saved

    @property
    def info_builder(self):
        if self._info is None:
            self._info = why_patterns.InfoBuilder(self.db, rows=self._rows)
        return self._info

    @property
    def amazon(self):
        if self._amazon is None:
            self._amazon = AmazonOrders(self.db, self._txns)
        return self._amazon

    def evaluate_rule(self, spec, txn, info) -> tuple[str, int | None, list, str]:
        """(MATCH | NO_MATCH | INCOMPLETE, WHY, missing, detail) of one rule on one movement."""
        verdict = why_patterns.evaluate(spec, info)
        if verdict.outcome != why_patterns.MATCH:
            return verdict.outcome, None, verdict.missing, verdict.exception or ""
        if spec.get("why_id"):
            return why_patterns.MATCH, spec["why_id"], [], ""
        read = self.amazon.read(txn)
        self.splits[txn.id] = read.get("proposal")
        if read["state"] == "WHY":
            return why_patterns.MATCH, read["why_id"], [], read["detail"]
        if read["state"] == "SPLIT":
            return SPLIT, None, [], read["detail"]
        missing = [r["label"] for r in read["proposal"].reasons] if read["state"] == "MIXED" else [read["detail"]]
        return why_patterns.INCOMPLETE, None, missing, read["state"]

    def determine(self, txn, *, who_id: int, who: str | None, pair_why: int | None, row=None) -> Determination:
        mode = self.mode(who_id)
        if mode == UNIQUE and pair_why:
            return Determination(mode, why_id=pair_why, method=METHOD_PAIR,
                                 reference=f"WHO #{who_id} + Source #{txn.payment_instrument_id}; WHAT from WHY; WHOM from Source")
        d = Determination(mode, unused_pair_why=pair_why if mode == MULTIPLE else None)
        applicable = self.applicable(who_id, txn)
        matched, incomplete, splits = {}, [], []
        if applicable:
            info = self.info_builder.info(txn, who=who, row=row)
            for rule, version, spec in applicable:
                outcome, why_id, missing, detail = self.evaluate_rule(spec, txn, info)
                d.rules.append((rule.id, outcome, why_id or detail))
                if outcome == why_patterns.MATCH:
                    matched.setdefault(why_id, []).append(f"rule #{rule.id} v{version.version_no}{_scope_note(spec)}"
                                                          + (f" ({detail})" if detail else ""))
                elif outcome == SPLIT:
                    splits.append(f"rule #{rule.id} v{version.version_no} ({detail})")
                elif outcome == why_patterns.INCOMPLETE:
                    incomplete.append((rule.id, missing, detail))
        if len(matched) + bool(splits) > 1:
            d.code = CONFLICT
            d.message = (LABELS[CONFLICT] + ": " + "; ".join(
                [f"{', '.join(refs)} → WHY #{w}" for w, refs in matched.items()]
                + ([", ".join(splits) + " → split"] if splits else [])))
            return d
        if splits and not incomplete:
            d.split, d.method = self.splits.get(txn.id), METHOD_SPLIT
            d.reference = ", ".join(splits) + "; WHAT from each line's WHY; WHOM from Source"
            return d
        if matched and not incomplete:
            (why_id, refs), = matched.items()
            d.why_id, d.method = why_id, METHOD_RULE
            d.reference = ", ".join(refs) + "; WHAT from WHY; WHOM from Source"
            return d
        if incomplete:
            # Also when another rule matched: the incomplete one could give a different WHY, so nothing is
            # decided until the missing information is there.
            # A document that needs several WHYs and cannot be split yet is "Ripartizione incompleta", not a
            # missing document: the WHO and the products are known, the detail amounts are not.
            mixed = all(detail == "MIXED" for _rid, _missing, detail in incomplete)
            d.code = SPLIT_INCOMPLETE if mixed else NEEDS_DOCUMENT
            d.split = self.splits.get(txn.id) if mixed else None
            d.missing = [x for _rid, missing, _detail in incomplete for x in missing]
            d.message = LABELS[d.code] + ": " + "; ".join(
                f"rule #{rid} — " + ", ".join(missing) for rid, missing, _detail in incomplete)
            return d
        d.code = NEEDS_PAIR if mode == UNIQUE else NEEDS_RULE
        d.message = LABELS[d.code] + (
            ": set the WHY of this WHO on this Source in Configuration." if mode == UNIQUE else
            ": the WHY of this WHO depends on the movement and no active rule applies"
            + (" (the WHY registered on the pair is not used for a MULTIPLE WHO)." if pair_why else "."))
        return d
