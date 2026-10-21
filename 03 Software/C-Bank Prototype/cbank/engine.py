"""C-Bank engine — ONE orchestrator, separate stages (spec §3, §7; decision 53).

Stages, in order, each recorded in the decision trace (decision 30):
  1. Source        account/card → owner Entity (the payer)
  2. Matching      transfer / card-payment legs (decisions 22, 37)
  3. WHO           matched counterpart (36) → approved text rules (43) →
                   human memory → AI investigation (11, 45, 50) → exception
  4. Profile       one Recognition Profile per WHO with conditional branches
                   (4, 42); conflicts are never resolved arbitrarily (48)
  5. Beneficiary   independent of the account (01-03): human → profile branch
                   → memory → AI → account owner
  6. Mapping       WHY → Category RF-One (Bank WHAT) → QB account (not mapped yet)
  7. Operation     operating / capital / financing / transfer / card settlement /
                   inter-entity / patrimonial (spec §2, §7)
  8. Status        Reconciled when every pertinent field is set (25)

Human decisions — operational Bank HUMAN decisions and C-Bank experimental
human decisions — are protected (38): the engine still computes its own
proposal, shown next to them, but never replaces them.

Dry run (54): reads Bank through `legacy` (read-only); results go to `store`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict

from sqlalchemy import select

from . import config, matching, store
from .legacy import Catalog, ai_rules, clean, flow, history_key, m

# Operation types (spec §2).
OPERATING_EXPENSE = "OPERATING_EXPENSE"
OPERATING_INCOME = "OPERATING_INCOME"
CAPITAL_ASSET = "CAPITAL_ASSET"
FINANCING = "FINANCING"
INTER_ACCOUNT_TRANSFER = "INTER_ACCOUNT_TRANSFER"
CARD_SETTLEMENT = "CARD_SETTLEMENT"
INTER_ENTITY = "INTER_ENTITY_ADVANCE_REPAYMENT"
INVESTMENT = "INVESTMENT"
OTHER_PATRIMONIAL = "OTHER_PATRIMONIAL"

RECONCILED = "RECONCILED"
EXCEPTION = "EXCEPTION"

# Methods (decision 30: author/means of each value).
HUMAN_CBANK, HUMAN_BANK, CONTEXT, RULE, PROFILE, MEMORY, AI, ACCOUNT = (
    "HUMAN (C-Bank)", "HUMAN (Bank)", "CONTEXT", "RULE", "PROFILE", "MEMORY", "AI", "ACCOUNT")


@dataclass
class Step:
    stage: str
    method: str
    value: str | None
    evidence: str
    confidence: str = ""


@dataclass
class Outcome:
    why_id: int | None
    category_id: int | None
    beneficiary_id: int | None
    method: str
    reference: str


@dataclass
class Result:
    txn_id: int
    date: str
    description: str
    amount_minor: int
    currency: str | None
    source: str | None
    source_type: str | None
    payer_id: int | None = None
    payer: str | None = None
    who_name: str | None = None
    who_id: int | None = None
    who_method: str | None = None
    beneficiary_id: int | None = None
    beneficiary: str | None = None
    beneficiary_method: str | None = None
    why_id: int | None = None
    why: str | None = None
    why_method: str | None = None
    category_id: int | None = None
    category: str | None = None
    qb_account: str | None = None
    operation_type: str | None = None
    status: str = EXCEPTION
    protected: str | None = None
    exceptions: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    proposal: dict | None = None
    bank: dict | None = None
    comparison: str | None = None
    match: dict | None = None
    ledger: dict | None = None
    group_key: str | None = None
    history_key: str | None = None


class Engine:
    def __init__(self, db, con, catalog: Catalog | None = None):
        self.db = db
        self.con = con
        self.c = catalog or Catalog.load(db)
        self.human = store.human_decisions(con)
        self.ai_answers = store.investigation_answers(con)
        self.txns = list(db.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.accounting_status == "CANONICAL").order_by(m.FinancialTransaction.id)))
        self.txns = [t for t in self.txns if t.duplicate_status != "CONFIRMED_DUPLICATE"]
        self.by_id = {t.id: t for t in self.txns}
        self.matches = matching.match_all(self.txns, self.c.instruments, self.c.settlement)
        self._owner_cache: dict = {}
        self._load_bank_decisions()
        self._build_memory()
        self.why_by_name = {clean(r.name): r.id for r in self.c.whys.values()}
        self.why_by_code = {r.code: r.id for r in self.c.whys.values()}
        self.entity_by_name = {}
        for e in self.c.entities.values():
            self.entity_by_name[clean(e.name)] = e.id
            self.entity_by_name[clean(e.code)] = e.id
        self.extractors = [e for e in self.c.rules if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "EXTRACTOR"]
        self.photos = [e for e in self.c.rules if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "PHOTO"]
        self.legacy = [e for e in self.c.rules if e[2].get("engine") != flow.ENGINE]

    # -- preload ------------------------------------------------------------

    def _load_bank_decisions(self):
        ids = [t.explanation_id for t in self.txns if t.explanation_id]
        self.explanations = {}
        for i in range(0, len(ids), 500):
            for e in self.db.scalars(select(m.BankTransactionExplanation).where(
                    m.BankTransactionExplanation.id.in_(ids[i:i + 500]))):
                self.explanations[e.id] = e
        self.allocations = defaultdict(list)
        for a in self.db.scalars(select(m.BankTransactionAllocation)):
            self.allocations[a.financial_transaction_id].append(a)

    def bank_decision(self, txn) -> dict:
        e = self.explanations.get(txn.explanation_id)
        allocs = self.allocations.get(txn.id, [])
        alloc = allocs[0] if len(allocs) == 1 else None
        category = None
        if e is not None:
            category = e.accounting_classification_id
            if category is None and e.transaction_reason_id in self.c.whys:
                category = self.c.whys[e.transaction_reason_id].accounting_classification_id
        return dict(
            who_id=e.occurrence_id if e else None,
            who=self.c.whos.get(e.occurrence_id) if e and e.occurrence_id else None,
            why_id=e.transaction_reason_id if e else None,
            category_id=category,
            beneficiary_id=alloc.reporting_entity_id if alloc else None,
            beneficiary_human=bool(alloc and alloc.decision_source == "HUMAN"),
            split=len(allocs) > 1,
            source=e.decision_source if e else None,
            status=e.decision_status if e else None,
        )

    def _build_memory(self):
        """History of HUMAN decisions by Bank precedent key (memory, spec §3.2)."""
        self.memory = defaultdict(list)
        # WHO memory also reuses WHO identities Bank already assigned by rule
        # (decision 53: reuse compatible data). Only the counterparty name is
        # reused this way; WHY/beneficiary memory stays human-only.
        self.who_memory = defaultdict(list)
        for t in self.txns:
            key = history_key(t.description_original)
            b = self.bank_decision(t)
            if b["who"]:
                self.who_memory[key].append(dict(txn_id=t.id, who=b["who"],
                                                 origin=HUMAN_BANK if b["source"] == "HUMAN" else "Bank rule"))
            h = self.human.get(t.id)
            if h and h["who_name"]:
                self.who_memory[key].append(dict(txn_id=t.id, who=h["who_name"], origin=HUMAN_CBANK))
            if h and (h["note"] or "").startswith("Decision 59"):
                # Decision 59 approvals confirm ONE movement's previous Bank classification:
                # they identify WHO for the pattern (above) but never become WHY/beneficiary
                # precedents, so one approval never spreads to the rest of a WHO.
                continue
            if h:
                self.memory[key].append(dict(txn_id=t.id, who=h["who_name"], why_id=h["why_id"],
                                             category_id=h["category_id"], beneficiary_id=h["beneficiary_id"],
                                             origin=HUMAN_CBANK))
                continue
            if b["source"] == "HUMAN" and b["who_id"]:
                self.memory[key].append(dict(txn_id=t.id, who=b["who"], why_id=b["why_id"],
                                             category_id=b["category_id"],
                                             beneficiary_id=b["beneficiary_id"] if b["beneficiary_human"] else None,
                                             origin=HUMAN_BANK))

    def owner(self, txn):
        key = (txn.payment_instrument_id, txn.posting_date)
        if key not in self._owner_cache:
            self._owner_cache[key] = self.c.owner(txn)
        return self._owner_cache[key]

    # -- public -------------------------------------------------------------

    def evaluate(self, txn) -> dict:
        instrument = self.c.instruments.get(txn.payment_instrument_id)
        r = Result(txn_id=txn.id, date=str(txn.posting_date), description=txn.description_original or "",
                   amount_minor=txn.amount_minor, currency=instrument.currency if instrument else None,
                   source=instrument.display_name if instrument else None,
                   source_type=("card" if instrument and instrument.instrument_type == "CREDIT_CARD" else "bank account"))
        r.history_key = history_key(txn.description_original)
        payer = self.owner(txn)
        r.payer_id, r.payer = (payer.id, payer.name) if payer else (None, None)
        r.trace.append(asdict(Step("Source", ACCOUNT, r.payer,
                                   f"{r.source} ({r.source_type}); owner from Bank Source configuration",
                                   "configured" if payer else "missing")))
        if not payer:
            r.exceptions.append(dict(code="SOURCE_OWNER_MISSING", message="The account/card has no configured owner."))

        auto = self._automatic(txn, r)
        r.bank = self.bank_decision(txn)
        self._apply_protection(txn, r, auto)
        self._finish(txn, r)
        return asdict(r)

    # -- automatic path ----------------------------------------------------

    def _automatic(self, txn, r: Result) -> dict:
        """The engine's own decision, computed even for protected rows."""
        trace = []
        exceptions = []
        mt = self.matches.get(txn.id)
        counterpart = self.by_id.get(mt.counterpart_id) if mt else None
        cp_owner = self.owner(counterpart) if counterpart else None
        if mt:
            r.match = dict(counterpart_id=mt.counterpart_id, kind=mt.kind, basis=mt.basis,
                           counterpart_source=self.c.instruments[mt.counterpart_instrument_id].display_name,
                           counterpart_owner=cp_owner.name if cp_owner else None)
            trace.append(Step("Matching", CONTEXT, f"{mt.kind} with #{mt.counterpart_id}", mt.basis, "matched"))

        # WHO --------------------------------------------------------------
        row = self.c.rule_row(txn)
        names, legacy_hits = [], []
        for rule, version, spec in self.extractors:
            name = flow.extract(spec, txn.description_original)
            if name:
                names.append((name, f"extraction rule #{rule.id} {rule.user_title or rule.title}"))
        for rule, version, spec in self.legacy:
            try:
                ex = ai_rules.execute(spec, row)
            except Exception:  # a malformed legacy spec never stops the run
                continue
            if ex.outcome != "MATCH":
                continue
            legacy_hits.append((rule, version, ex))
            if ex.who and not ex.who_verify:
                names.append((ex.who, f"text rule #{rule.id} {rule.user_title or rule.title}"))
        distinct = {}
        for name, ref in names:
            distinct.setdefault(clean(name), (name, []))[1].append(ref)

        who, who_method, who_evidence = None, None, ""
        ai = self.ai_answers.get(txn.id)
        if mt and cp_owner is not None:
            who = f"{cp_owner.name} · {self.c.instruments[mt.counterpart_instrument_id].display_name}"
            who_method, who_evidence = CONTEXT, f"counterparty of a matched {mt.kind.lower()} ({mt.basis})"
            if distinct:
                who_evidence += "; text rules also matched: " + ", ".join(v[0] for v in distinct.values())
        elif len(distinct) == 1:
            name, refs = next(iter(distinct.values()))
            who, who_method, who_evidence = name.strip().upper(), RULE, "; ".join(refs)
        elif len(distinct) > 1:
            if ai and ai.get("who") and clean(ai["who"]) in distinct and self._ai_sufficient(ai):
                who, who_method = distinct[clean(ai["who"])][0].upper(), AI
                who_evidence = f"rules disagree ({', '.join(v[0] for v in distinct.values())}); AI resolved: {ai.get('justification', '')}"
            else:
                exceptions.append(dict(code="WHO_AMBIGUOUS", message="Text rules disagree on WHO: "
                                       + " / ".join(f"{v[0]} ({'; '.join(v[1])})" for v in distinct.values()),
                                       question=ai.get("question") if ai else None))
        if who is None and not exceptions:
            precedents = [p for p in self.who_memory.get(r.history_key, []) if p["txn_id"] != txn.id]
            wh = {clean(p["who"]) for p in precedents}
            if len(wh) == 1:
                who = precedents[0]["who"]
                who_method = MEMORY
                origins = defaultdict(int)
                for p in precedents:
                    origins[p["origin"]] += 1
                who_evidence = (f"{len(precedents)} earlier movement(s) with the same description pattern ("
                                + ", ".join(f"{n} {o}" for o, n in origins.items()) + f"), e.g. #{precedents[0]['txn_id']}")
            elif ai and ai.get("who") and self._ai_sufficient(ai) and self._who_supported(ai["who"], txn):
                who, who_method = ai["who"].strip().upper(), AI
                who_evidence = ai.get("justification", "")
            else:
                exceptions.append(dict(code="WHO_UNKNOWN" if not wh else "WHO_AMBIGUOUS",
                                       message="No approved rule or memory identifies WHO." if not wh else
                                       "Human precedents disagree on WHO.",
                                       question=ai.get("question") if ai else None))
        who_id = self.c.who_by_name.get(clean(who)) if who else None
        trace.append(Step("WHO", who_method or "—", who, who_evidence or "not identified",
                          "known WHO" if who_id else ("new WHO" if who else "")))

        # PROFILE ------------------------------------------------------------
        outcomes, undecided, profiles = [], [], set()
        if who and who_method != CONTEXT:
            for entry in self.photos:
                rule, version, spec = entry
                if clean(who) not in [clean(spec.get("who"))] + [clean(a) for a in spec.get("aliases", [])]:
                    continue
                profiles.add(rule.id)
                choice = flow.choose(self.db, txn, entry, who, generate=None, allow_missing_whom=True)
                if not choice:
                    undecided.append(f"profile #{rule.id} has no branch that decides this movement")
                    continue
                branch = spec["branches"][choice["branch_index"]]
                beneficiary = None if spec.get("whom_mode") == "SOURCE" else branch.get("whom_id")
                outcomes.append(Outcome(choice["why_id"], choice.get("destination_id"), beneficiary, PROFILE,
                                        f"profile #{rule.id} {rule.user_title or rule.title}, branch {choice['branch_index'] + 1}"))
        for rule, version, ex in legacy_hits:
            # A matched leg's WHO is contextual; its approved text rule still
            # classifies it (decision 43). Otherwise the rule must be this WHO's.
            if ex.who and who and who_method != CONTEXT and clean(ex.who) != clean(who):
                continue
            if not ex.why and not ex.why_verify:
                continue
            profiles.add(rule.id)
            if ex.why_verify or ex.why not in [None] and clean(ex.why) not in self.why_by_name:
                undecided.append(f"rule #{rule.id}: WHY to verify ({ex.why_verify or ex.why})")
                continue
            beneficiary = self.entity_by_name.get(clean(ex.for_whom)) if ex.for_whom else None
            outcomes.append(Outcome(self.why_by_name[clean(ex.why)], ex.destination_id, beneficiary, PROFILE,
                                    f"text rule #{rule.id} {rule.user_title or rule.title}"
                                    + (f", branch {ex.branch}" if ex.branch else "")))
        if len(profiles) > 1:
            r.anomalies.append(dict(code="MULTIPLE_PROFILES_FOR_WHO",
                                    message=f"{len(profiles)} rules/profiles classify WHO {who} (decision 42 expects one)."))

        outcome = None
        keys = {(o.why_id, o.category_id or self._why_category(o.why_id), o.beneficiary_id) for o in outcomes}
        if len(keys) == 1:
            outcome = outcomes[0]
            outcome.reference = "; ".join(o.reference for o in outcomes)
        elif len(keys) > 1:
            exceptions.append(dict(code="PROFILE_CONFLICT", message="Profiles/rules give different results: "
                                   + " / ".join(f"{self._why_name(o.why_id)} ({o.reference})" for o in outcomes),
                                   question=ai.get("question") if ai else None))
        elif undecided:
            exceptions.append(dict(code="PROFILE_UNDECIDED", message="; ".join(undecided),
                                   question=ai.get("question") if ai else None))

        if outcome is None and not any(e["code"] in ("PROFILE_CONFLICT", "PROFILE_UNDECIDED") for e in exceptions):
            if mt:
                outcome = self._transfer_outcome(txn, mt, r.payer_id, cp_owner)
            if outcome is None and who:
                outcome = self._memory_outcome(txn, r.history_key)
        if outcome is None and ai and self._ai_sufficient(ai) and ai.get("why_id") in self.c.whys:
            outcome = Outcome(ai["why_id"], ai.get("category_id") if ai.get("category_id") in self.c.classes else None,
                              ai.get("beneficiary_id") if ai.get("beneficiary_id") in self.c.entities else None,
                              AI, f"AI investigation #{ai['investigation_id']}: {ai.get('justification', '')}")
            exceptions = [e for e in exceptions if e["code"] not in ("PROFILE_UNDECIDED", "PROFILE_CONFLICT")]
        if outcome is None and who and not exceptions:
            exceptions.append(dict(code="NO_PROFILE", message=f"WHO {who} has no Recognition Profile and no "
                                   "concordant precedents: investigate before classifying.",
                                   question=ai.get("question") if ai else None))
        if ai and not self._ai_sufficient(ai) and ai.get("question"):
            for e in exceptions:
                e.setdefault("question", ai["question"])
                e["alternatives"] = ai.get("alternatives") or []
        if outcome:
            trace.append(Step("Profile", outcome.method, self._why_name(outcome.why_id), outcome.reference, ""))
        else:
            trace.append(Step("Profile", "—", None, "no classification", ""))

        # BENEFICIARY -------------------------------------------------------
        beneficiary, b_method, b_evidence = None, None, ""
        why_row = self.c.whys.get(outcome.why_id) if outcome else None
        personal = self._personal_entity()
        if outcome and outcome.beneficiary_id:
            beneficiary, b_method, b_evidence = outcome.beneficiary_id, outcome.method, outcome.reference
        elif why_row is not None and (why_row.code or "").startswith("OWNER_PERSONAL") and personal:
            # Decision 01: a personal expense belongs to the person, whoever pays it.
            beneficiary, b_method = personal, PROFILE
            b_evidence = f"WHY “{why_row.name}” is a personal expense of the owner"
        else:
            precedents = [p for p in self.memory.get(r.history_key, []) if p["txn_id"] != txn.id and p["beneficiary_id"]]
            values = {p["beneficiary_id"] for p in precedents}
            if len(values) == 1 and len(precedents) >= config.MEMORY_MIN_PRECEDENTS and next(iter(values)) != r.payer_id:
                beneficiary, b_method = next(iter(values)), MEMORY
                b_evidence = f"{len(precedents)} human precedent(s) attributed this pattern to another entity"
            elif len(values) > 1:
                exceptions.append(dict(code="BENEFICIARY_UNCERTAIN",
                                       message="Human precedents attribute this pattern to different entities."))
            elif ai and self._ai_sufficient(ai) and ai.get("beneficiary_id") in self.c.entities:
                beneficiary, b_method, b_evidence = ai["beneficiary_id"], AI, ai.get("justification", "")
            elif r.payer_id:
                beneficiary, b_method = r.payer_id, ACCOUNT
                b_evidence = "account owner; no rule, profile, precedent or evidence points to another beneficiary"
                category = self.c.classes.get(outcome.category_id or self._why_category(outcome.why_id)) if outcome else None
                if beneficiary == personal and category is not None and category.statement_type == "PROFIT_LOSS" \
                        and not (category.code or "").startswith("4") and not mt:
                    # Decisions 03/16: a business cost on a personal instrument — which LLC benefits?
                    exceptions.append(dict(code="BENEFICIARY_UNCERTAIN", message=(
                        f"Business category {category.code} {category.name} paid with a personal account/card: "
                        "which entity is the beneficiary?")))
        trace.append(Step("Beneficiary", b_method or "—", self.c.entity_name(beneficiary), b_evidence,
                          "default" if b_method == ACCOUNT else ""))

        why_id = outcome.why_id if outcome else None
        category_id = (outcome.category_id if outcome and outcome.category_id else self._why_category(why_id))
        return dict(who=who, who_id=who_id, who_method=who_method, why_id=why_id,
                    why_method=outcome.method if outcome else None, category_id=category_id,
                    beneficiary_id=beneficiary, beneficiary_method=b_method,
                    exceptions=exceptions, trace=[asdict(s) for s in trace], counterpart_owner=cp_owner)

    def _transfer_outcome(self, txn, mt, payer_id, cp_owner) -> Outcome | None:
        same_owner = cp_owner is not None and cp_owner.id == payer_id
        if mt.kind == "CARD_SETTLEMENT" and same_owner:
            code = "CREDIT_CARD_SETTLEMENT"
        elif same_owner:
            code = "INTERNAL_BANK_TRANSFER"
        else:
            code = "RELATED_PARTY_TRANSFER_OUT" if txn.amount_minor < 0 else "RELATED_PARTY_TRANSFER_IN"
        why_id = self.why_by_code.get(code)
        if why_id is None:
            return None
        return Outcome(why_id, None, payer_id, CONTEXT, f"matched {mt.kind.lower()}: {mt.basis}")

    def _memory_outcome(self, txn, key) -> Outcome | None:
        precedents = [p for p in self.memory.get(key, []) if p["txn_id"] != txn.id and p["why_id"]]
        if len(precedents) < config.MEMORY_MIN_PRECEDENTS:
            return None
        values = {(p["why_id"], p["category_id"] or self._why_category(p["why_id"])) for p in precedents}
        if len(values) != 1:
            return None
        why_id, category_id = next(iter(values))
        bens = {p["beneficiary_id"] for p in precedents}
        return Outcome(why_id, category_id, next(iter(bens)) if len(bens) == 1 else None, MEMORY,
                       f"{len(precedents)} concordant human precedents (e.g. #{precedents[0]['txn_id']})")

    # -- protection ----------------------------------------------------------

    def _apply_protection(self, txn, r: Result, auto: dict):
        h = self.human.get(txn.id)
        b = r.bank
        if h:
            r.protected = HUMAN_CBANK
            values = dict(who=h["who_name"], why_id=h["why_id"], category_id=h["category_id"],
                          beneficiary_id=h["beneficiary_id"] or auto["beneficiary_id"])
            method = HUMAN_CBANK
        elif b["source"] == "HUMAN" and b["who_id"]:
            r.protected = HUMAN_BANK
            values = dict(who=b["who"], why_id=b["why_id"], category_id=b["category_id"],
                          beneficiary_id=b["beneficiary_id"] if b["beneficiary_human"] else auto["beneficiary_id"])
            method = HUMAN_BANK
        else:
            values = None
        r.trace.extend(auto["trace"])
        if values is None:
            r.who_name, r.who_id, r.who_method = auto["who"], auto["who_id"], auto["who_method"]
            r.why_id, r.why_method, r.category_id = auto["why_id"], auto["why_method"], auto["category_id"]
            r.beneficiary_id, r.beneficiary_method = auto["beneficiary_id"], auto["beneficiary_method"]
            r.exceptions.extend(auto["exceptions"])
            return
        r.who_name, r.who_id, r.who_method = values["who"], self.c.who_by_name.get(clean(values["who"])), method
        r.why_id, r.why_method = values["why_id"], method
        r.category_id = values["category_id"] or self._why_category(values["why_id"])
        r.beneficiary_id = values["beneficiary_id"]
        r.beneficiary_method = method if (h and h["beneficiary_id"]) or (not h and b["beneficiary_human"]) else auto["beneficiary_method"]
        r.trace.append(asdict(Step("Protection", method, "human decision kept",
                                   "decision 38: the engine never replaces a human decision")))
        differs = {k for k, a, v in (("WHO", auto["who"], values["who"]), ("WHY", auto["why_id"], values["why_id"]),
                                     ("Category", auto["category_id"], r.category_id),
                                     ("Beneficiary", auto["beneficiary_id"], r.beneficiary_id))
                   if a is not None and (clean(a) if isinstance(a, str) else a) != (clean(v) if isinstance(v, str) else v)}
        if differs:
            r.proposal = dict(fields=sorted(differs), who=auto["who"], why=self._why_name(auto["why_id"]),
                              category=self.c.class_label(auto["category_id"]),
                              beneficiary=self.c.entity_name(auto["beneficiary_id"]),
                              note="Proposal only — requires human approval (decision 38).")
        if not (r.who_name and r.why_id):
            r.exceptions.append(dict(code="HUMAN_INCOMPLETE", message="The human decision lacks WHO or WHY."))

    # -- finish ----------------------------------------------------------------

    def _finish(self, txn, r: Result):
        r.why = self._why_name(r.why_id)
        r.category = self.c.class_label(r.category_id)
        r.qb_account = None  # QuickBooks COA not imported yet (MVP decision): shown as "not mapped".
        r.beneficiary = self.c.entity_name(r.beneficiary_id)
        r.operation_type = self._operation_type(txn, r)
        r.group_key = r.who_name or r.history_key
        if r.match and r.operation_type in (INTER_ACCOUNT_TRANSFER, CARD_SETTLEMENT) and r.match.get("counterpart_owner") \
                and r.payer and r.match["counterpart_owner"] != r.payer:
            r.operation_type = INTER_ENTITY
        if r.payer_id and r.beneficiary_id and r.payer_id != r.beneficiary_id \
                and r.operation_type not in (INTER_ACCOUNT_TRANSFER, CARD_SETTLEMENT):
            # Decision 01: cost attributed to the beneficiary; the payer gets a receivable.
            amount = -r.amount_minor
            r.ledger = dict(kind="PAID_FOR_OTHER", payer_id=r.payer_id, payer=r.payer,
                            beneficiary_id=r.beneficiary_id, beneficiary=r.beneficiary,
                            amount_minor=amount,
                            proposal=(f"{r.beneficiary} owes {r.payer}" if amount > 0 else f"{r.payer} owes {r.beneficiary}"),
                            note="Proposed receivable/payable; accounting qualification to verify.")
        elif r.operation_type == INTER_ENTITY and r.match and r.amount_minor < 0:
            r.ledger = dict(kind="TRANSFER", payer_id=r.payer_id, payer=r.payer,
                            beneficiary=r.match.get("counterpart_owner"),
                            beneficiary_id=self.entity_by_name.get(clean(r.match.get("counterpart_owner"))),
                            amount_minor=-r.amount_minor,
                            proposal="Advance or repayment between entities — propose offset against open balances.",
                            note="Decision 07/14: no new cost; qualify as advance or repayment.")
        if r.why_id and not r.category_id:
            r.exceptions.append(dict(code="CATEGORY_MISSING", message=f"WHY “{r.why}” has no Category RF-One in the "
                                     "Bank catalog: choose it for this movement; a catalog change needs approval (decision 39)."))
        blocking = [e for e in r.exceptions]
        complete = all([r.who_name, r.why_id, r.category_id, r.beneficiary_id, r.operation_type])
        r.status = RECONCILED if complete and not blocking else EXCEPTION
        if r.status == EXCEPTION and complete is False and not blocking:
            missing = [n for n, v in (("WHO", r.who_name), ("WHY", r.why_id), ("Category", r.category_id),
                                      ("Beneficiary", r.beneficiary_id), ("Operation", r.operation_type)) if not v]
            r.exceptions.append(dict(code="INCOMPLETE", message="Missing: " + ", ".join(missing)))
        r.trace.append(asdict(Step("Mapping", r.why_method or "—", r.category,
                                   "Category RF-One = Bank WHAT; QB account not mapped (COA not imported)")))
        r.trace.append(asdict(Step("Operation", "RULE", r.operation_type, self._operation_basis(r))))
        r.trace.append(asdict(Step("Status", "ENGINE", r.status,
                                   "all pertinent fields set" if r.status == RECONCILED else
                                   "; ".join(e["code"] for e in r.exceptions))))
        r.comparison = self._compare(r)

    def _operation_type(self, txn, r: Result) -> str | None:
        if r.match:
            return CARD_SETTLEMENT if r.match["kind"] == "CARD_SETTLEMENT" else INTER_ACCOUNT_TRANSFER
        a = self.c.classes.get(r.category_id)
        if a is None:
            return None
        code = a.code or ""
        if a.statement_type == "PROFIT_LOSS":
            income = (a.normal_balance or "").upper() == "CREDIT" or code.startswith("4")
            return OPERATING_INCOME if income else OPERATING_EXPENSE
        if code.startswith("15"):
            return CAPITAL_ASSET
        if code.startswith("26"):
            return FINANCING
        if code.startswith(("16", "27")):
            return INTER_ENTITY
        if code == "2500":
            return CARD_SETTLEMENT
        if code.startswith("11"):
            return INTER_ACCOUNT_TRANSFER
        if "invest" in (a.name or "").lower():
            return INVESTMENT
        return OTHER_PATRIMONIAL

    def _operation_basis(self, r: Result) -> str:
        if r.match:
            return f"matched leg ({r.match['basis']})"
        a = self.c.classes.get(r.category_id)
        return f"category {a.code} ({a.statement_type})" if a else "no category"

    def _compare(self, r: Result) -> str:
        b = r.bank
        if not b or not b["who_id"]:
            return "BANK_EMPTY" if r.status == RECONCILED else "BOTH_OPEN"
        bank_ben = b["beneficiary_id"] or r.payer_id
        diffs = []
        if r.who_method != CONTEXT and r.who_name and clean(r.who_name) != clean(b["who"]):
            diffs.append("WHO")
        if r.why_id and r.why_id != b["why_id"]:
            diffs.append("WHY")
        if r.category_id and b["category_id"] and r.category_id != b["category_id"]:
            diffs.append("Category")
        if r.beneficiary_id and r.beneficiary_id != bank_ben:
            diffs.append("Beneficiary")
        if r.status != RECONCILED:
            return "CBANK_OPEN"
        return "SAME" if not diffs else "DIFFERENT: " + ", ".join(diffs)

    # -- helpers ---------------------------------------------------------------

    def _personal_entity(self):
        return next((e.id for e in self.c.entities.values() if e.entity_type == "PERSONAL" and e.status == "ACTIVE"), None)

    def _why_category(self, why_id):
        r = self.c.whys.get(why_id)
        return r.accounting_classification_id if r else None

    def _why_name(self, why_id):
        r = self.c.whys.get(why_id)
        return r.name if r else None

    @staticmethod
    def _ai_sufficient(ai: dict) -> bool:
        conf = ai.get("confidence")
        return ai.get("sufficient") is True and isinstance(conf, (int, float)) and conf >= config.AI_MIN_CONFIDENCE

    @staticmethod
    def _who_supported(name: str, txn) -> bool:
        """Decision 36: never invent a WHO — an AI WHO must appear in the text."""
        words = [w for w in clean(name).split() if len(w) > 2]
        text = clean(txn.description_original)
        return bool(words) and all(w in text for w in words[:2])


def summarize(results: list[dict]) -> dict:
    s = defaultdict(int)
    for r in results:
        s["total"] += 1
        s[r["status"]] += 1
        for e in r["exceptions"]:
            s["exc:" + e["code"]] += 1
        s["cmp:" + (r["comparison"] or "").split(":")[0]] += 1
        if r["protected"]:
            s["protected"] += 1
            if r["proposal"]:
                s["protected_with_proposal"] += 1
    return dict(s)
