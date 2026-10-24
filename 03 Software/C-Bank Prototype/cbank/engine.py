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
    ai_partial: dict | None = None   # AI fields with their acceptance (kept even when not applied)


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
        self.ambiguous: dict[int, list] = {}
        self.matches = matching.match_all(self.txns, self.c.instruments, self.c.settlement, self.ambiguous)
        self.card_payment_out = matching.card_payment_pattern(self.c.instruments)
        self._owner_cache: dict = {}
        self._load_who_whys()
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

    def _load_who_whys(self):
        """WHO -> possible WHY from Bank Configuration. Source HUMAN = explicitly approved by a
        person (approval lists, Configuration edits); anything else (HISTORY…) = historical
        association, AI evidence only. Only WHYs with a Category count."""
        self.who_whys_approved, self.who_whys_history = defaultdict(list), defaultdict(list)
        for a in self.db.scalars(select(m.BankOccurrenceReasonAssociation).where(
                m.BankOccurrenceReasonAssociation.active.is_(True))):
            w = self.c.whys.get(a.transaction_reason_id)
            if w is None or not w.accounting_classification_id:
                continue
            (self.who_whys_approved if a.source == "HUMAN" else self.who_whys_history)[a.occurrence_id].append(w.id)

    def _approved_why(self, who_id, payer_id):
        """(WHY id, evidence) from the WHO's APPROVED associations, or (None, reason). One approved
        WHY decides; several are narrowed only by the approved personal/company Source rule
        (OWNER_PERSONAL_* on a personal Source, never on a company one); still several = ambiguous."""
        approved = sorted(set(self.who_whys_approved.get(who_id, [])))
        if not approved:
            return None, None
        personal = payer_id is not None and payer_id == self._personal_entity()
        if len(approved) > 1:
            narrowed = [w for w in approved if (self.c.whys[w].code or "").startswith("OWNER_PERSONAL") == personal]
            if len(narrowed) == 1:
                return narrowed[0], (f"approved WHO→WHY association ({len(approved)} approved WHYs; "
                                     f"{'personal' if personal else 'company'} Source rule leaves one)")
            return None, "AMBIGUOUS"
        return approved[0], "approved WHO→WHY association (Bank Configuration, confirmed by a person)"

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
        self.approved_rule_decisions = self._approved_rule_decisions()

    def _approved_rule_decisions(self) -> dict:
        """Movements whose CURRENT Bank decision was written by an approved rule or Recognition Profile:
        an application item that produced the current explanation, not rolled back, of an ACTIVE, not
        deleted rule with `apply to future`. Rules without `apply to future` are left out (their behaviour
        is unchanged); Codex sessions never appear here (they are not rule applications)."""
        current = {t.explanation_id: t.id for t in self.txns if t.explanation_id}
        out = {}
        rows = self.db.execute(
            select(m.BankAiRuleApplicationItem.explanation_id, m.BankAiRule.id, m.BankAiRule.user_title,
                   m.BankAiRule.title, m.BankAiRuleVersion.version_no)
            .join(m.BankAiRuleApplication, m.BankAiRuleApplication.id == m.BankAiRuleApplicationItem.application_id)
            .join(m.BankAiRule, m.BankAiRule.id == m.BankAiRuleApplication.rule_id)
            .join(m.BankAiRuleVersion, m.BankAiRuleVersion.id == m.BankAiRuleApplication.version_id)
            .where(m.BankAiRuleApplication.rolled_back_at.is_(None), m.BankAiRule.deleted_at.is_(None),
                   m.BankAiRule.status == "ACTIVE", m.BankAiRule.apply_future.is_(True)))
        for explanation_id, rule_id, user_title, title, version_no in rows:
            if explanation_id in current:
                out[current[explanation_id]] = f"Bank rule #{rule_id} v{version_no} {user_title or title} (approved, apply to future)"
        return out

    def _is_codex(self, txn) -> bool:
        """Codex WHY sessions (CODEX_WHY_*) wrote unreviewed classifications: never treated as confirmed."""
        e = self.explanations.get(txn.explanation_id)
        return bool(e and (e.explanation_notes or "").startswith("CODEX_"))

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
                # WHO memory is unchanged; only its provenance is stated honestly. Codex sessions decided the
                # WHY (never reused as a precedent below); the WHO they carried came from Bank's earlier reading.
                origin = HUMAN_BANK if b["source"] == "HUMAN" else (
                    "Bank (Codex WHY session, unreviewed)" if self._is_codex(t) else "Bank rule")
                self.who_memory[key].append(dict(txn_id=t.id, who=b["who"], origin=origin))
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
            elif b["source"] == "RULE" and b["why_id"] and t.id in self.approved_rule_decisions:
                # WHY precedent from an approved rule / Recognition Profile (provenance kept). It never
                # carries a beneficiary: beneficiary precedents stay human-only.
                self.memory[key].append(dict(txn_id=t.id, who=b["who"], why_id=b["why_id"],
                                             category_id=b["category_id"], beneficiary_id=None,
                                             origin=self.approved_rule_decisions[t.id], rule=True))

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
                           counterpart_owner=cp_owner.name if cp_owner else None, state="MATCHED")
            trace.append(Step("Matching", CONTEXT, f"{mt.kind} with #{mt.counterpart_id}", mt.basis, "matched"))
        if mt and mt.kind == "CARD_SETTLEMENT":
            # CARD_SETTLEMENT_001: a certain card payment follows ONLY the transfer path — no WHO text rule,
            # Recognition Profile, memory or AI can reclassify it (bank charge, purchase, CHASE payment…).
            outcome = self._transfer_outcome(txn, mt, r.payer_id, cp_owner)
            who = f"{cp_owner.name} · {self.c.instruments[mt.counterpart_instrument_id].display_name}" if cp_owner else None
            trace.append(Step("WHO", CONTEXT, who, f"counterparty of a matched card settlement ({mt.basis})", ""))
            trace.append(Step("Profile", CONTEXT, self._why_name(outcome.why_id) if outcome else None,
                              "card settlement: the transfer path takes precedence over rules and profiles", ""))
            trace.append(Step("Beneficiary", ACCOUNT, self.c.entity_name(r.payer_id), "owner of this leg's instrument", ""))
            return dict(who=who, who_id=None, who_method=CONTEXT, why_id=outcome.why_id if outcome else None,
                        why_method=CONTEXT if outcome else None,
                        category_id=self._why_category(outcome.why_id) if outcome else None,
                        beneficiary_id=r.payer_id, beneficiary_method=ACCOUNT, exceptions=[],
                        trace=[asdict(s) for s in trace], counterpart_owner=cp_owner)
        if not mt and (txn.id in self.ambiguous
                       or matching.is_card_payment_out(txn, self.c.instruments, self.card_payment_out)):
            # A card payment whose counterpart is ambiguous or not imported yet: never classified as an
            # ordinary payment to the issuer; it waits for a person (ambiguous) or for the statement.
            if txn.id in self.ambiguous:
                exc = dict(code="CARD_PAYMENT_AMBIGUOUS", message=(
                    "Card payment with more than one possible counterpart: "
                    + ", ".join(f"#{i}" for i in self.ambiguous[txn.id]) + ". Choose the right one."))
            else:
                exc = dict(code="CARD_PAYMENT_UNMATCHED", message=(
                    "Card payment without its card-side credit: import the missing card statement; "
                    "it is matched automatically on the next run."))
            r.match = dict(state="AMBIGUOUS" if txn.id in self.ambiguous else "WAITING",
                           candidates=self.ambiguous.get(txn.id, []), kind="CARD_SETTLEMENT")
            trace.append(Step("Matching", CONTEXT, r.match["state"], exc["message"], ""))
            return dict(who=None, who_id=None, who_method=None, why_id=None, why_method=None, category_id=None,
                        beneficiary_id=None, beneficiary_method=None, exceptions=[exc],
                        trace=[asdict(s) for s in trace], counterpart_owner=None)

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
            if ai and ai.get("who") and clean(ai["who"]) in distinct and self._ai_field_ok(ai, "who"):
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
            elif ai and ai.get("who") and self._ai_field_ok(ai, "who") and self._who_supported(ai["who"], txn):
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
            if outcome is None and who_id and config.WHO_WHY_KNOWLEDGE:
                # After the Recognition Profile: an EXPLICITLY APPROVED WHO -> WHY association.
                why_id, note = self._approved_why(who_id, r.payer_id)
                if why_id:
                    outcome = Outcome(why_id, None, None, RULE, note)
                elif note == "AMBIGUOUS":
                    exceptions.append(dict(code="WHO_WHY_AMBIGUOUS", message=(
                        f"WHO {who} has several approved WHYs ("
                        + ", ".join(self._why_name(w) for w in self.who_whys_approved[who_id])
                        + ") and nothing in this movement chooses one."), question=ai.get("question") if ai else None))
        if outcome and outcome.method == PROFILE and who_id and config.WHO_WHY_KNOWLEDGE \
                and self.who_whys_approved.get(who_id) and outcome.why_id not in self.who_whys_approved[who_id]:
            r.anomalies.append(dict(code="PROFILE_VS_APPROVED_WHY", message=(
                f"Profile gives {self._why_name(outcome.why_id)}, the approved WHO→WHY association "
                + ", ".join(self._why_name(w) for w in self.who_whys_approved[who_id]) + ": the profile wins.")))
        if outcome is None and ai and self._ai_field_ok(ai, "why") and ai.get("why_id") in self.c.whys:
            # Each AI field is accepted on its own evidence: a certain WHY does not carry an uncertain
            # category or beneficiary with it (they stay open and the movement stays an Exception).
            outcome = Outcome(ai["why_id"],
                              ai.get("category_id") if self._ai_field_ok(ai, "category") and ai.get("category_id") in self.c.classes else None,
                              ai.get("beneficiary_id") if self._ai_field_ok(ai, "beneficiary") and ai.get("beneficiary_id") in self.c.entities else None,
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
        if outcome and not mt and txn.amount_minor < 0 and self._is_income(
                self.c.classes.get(outcome.category_id or self._why_category(outcome.why_id))):
            # E1: a text rule can match the words ("INTEREST PAYMENT") of an operation whose direction
            # contradicts it (interest PAID on a loan is not interest income): never reconcile it silently.
            exceptions.append(dict(code="DIRECTION_CONFLICT", message=(
                f"“{self._why_name(outcome.why_id)}” is an income, but this movement is money OUT "
                f"({outcome.reference}): verify the nature of the operation."),
                question=ai.get("question") if ai else None))
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
            elif ai and self._ai_field_ok(ai, "beneficiary") and ai.get("beneficiary_id") in self.c.entities:
                beneficiary, b_method, b_evidence = ai["beneficiary_id"], AI, ai.get("justification", "")
            elif outcome and outcome.method == AI and self._ai_field_declared(ai, "beneficiary"):
                # The AI established the WHY but explicitly NOT the beneficiary: no account-owner default.
                exceptions.append(dict(code="AI_PARTIAL", message="AI identified the WHY but not the beneficiary "
                                       "with sufficient evidence: confirm who the cost/revenue belongs to.",
                                       question=ai.get("question")))
            elif r.payer_id:
                beneficiary, b_method = r.payer_id, ACCOUNT
                b_evidence = "account owner; no rule, profile, precedent or evidence points to another beneficiary"
                category = self.c.classes.get(outcome.category_id or self._why_category(outcome.why_id)) if outcome else None
                if beneficiary == personal and category is not None and category.statement_type == "PROFIT_LOSS" \
                        and not self._is_income(category) and not mt:
                    # Decisions 03/16: a business cost (or its refund) on a personal instrument — which LLC
                    # benefits? Income on a personal account (E1: interest earned) is not a business cost:
                    # it keeps the account owner as beneficiary.
                    exceptions.append(dict(code="BENEFICIARY_UNCERTAIN", message=(
                        f"Business category {category.code} {category.name} paid with a personal account/card: "
                        "which entity is the beneficiary?")))
        trace.append(Step("Beneficiary", b_method or "—", self.c.entity_name(beneficiary), b_evidence,
                          "default" if b_method == ACCOUNT else ""))

        why_id = outcome.why_id if outcome else None
        category_id = (outcome.category_id if outcome and outcome.category_id else self._why_category(why_id))
        if ai:
            r.ai_partial = self._ai_fields(ai)
        return dict(who=who, who_id=who_id, who_method=who_method, why_id=why_id,
                    why_method=outcome.method if outcome else None, category_id=category_id,
                    beneficiary_id=beneficiary, beneficiary_method=b_method,
                    exceptions=exceptions, trace=[asdict(s) for s in trace], counterpart_owner=cp_owner)

    def _transfer_outcome(self, txn, mt, payer_id, cp_owner) -> Outcome | None:
        same_owner = cp_owner is not None and cp_owner.id == payer_id
        if mt.kind == "CARD_SETTLEMENT":
            # Whoever owns the two instruments, the transfer itself is a card statement payment; a
            # relationship between different owners is a separate question (RELATIONSHIP_TO_DECIDE).
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
        human = [p for p in precedents if not p.get("rule")]
        bens = {p["beneficiary_id"] for p in human}
        rules = sorted({p["origin"] for p in precedents if p.get("rule")})
        basis = f"{len(human)} human" + (f", {len(precedents) - len(human)} from approved rules ({'; '.join(rules)})"
                                         if rules else "")
        return Outcome(why_id, category_id, next(iter(bens)) if len(bens) == 1 else None, MEMORY,
                       f"{len(precedents)} concordant precedents ({basis}; e.g. #{precedents[0]['txn_id']})")

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
        if not values["why_id"] and values["who"] and config.WHO_WHY_KNOWLEDGE:
            # Completion of an incomplete human decision: the person's fields stay as they are; only
            # the missing WHY is filled, from an approved source, and its provenance is kept.
            human_who_id = b["who_id"] if not h else self.c.who_by_name.get(clean(values["who"]))
            fill, fill_method, fill_note = None, None, ""
            if auto["why_id"] and auto["why_method"] in (PROFILE, RULE) and auto["who"] \
                    and clean(auto["who"]) == clean(values["who"]):
                fill, fill_method, fill_note = auto["why_id"], auto["why_method"], "engine decision for the same WHO"
            elif human_who_id:
                why_id, note = self._approved_why(human_who_id, r.payer_id)
                if why_id:
                    fill, fill_method, fill_note = why_id, RULE, note
            human_category = values["category_id"]
            if fill and human_category and self._why_category(fill) != human_category:
                fill = None   # the person's Category disagrees: never overridden, the movement stays open
            if fill:
                values["why_id"] = r.why_id = fill
                r.why_method = f"{fill_method} (completing a human decision)"
                r.trace.append(asdict(Step("Completion", fill_method, self._why_name(fill),
                                           f"missing WHY of the {method} decision filled: {fill_note}; "
                                           "WHO and the other confirmed fields stay human")))
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
        if r.match and r.match.get("state") == "WAITING":
            r.group_key = "Card payments waiting for their card statement"
        elif r.match and r.match.get("state") == "AMBIGUOUS":
            r.group_key = "Card payments with more than one possible counterpart"
        if r.match and r.match.get("state") == "MATCHED" and r.match["kind"] == "CARD_SETTLEMENT":
            # The transfer is matched and complete. Only the BANK-ACCOUNT leg (money out) is the posting;
            # the card leg is its counterpart, kept for traceability (never posted a second time).
            own = self.c.instruments.get(txn.payment_instrument_id)
            r.match["posting"] = "COUNTERPART" if matching.is_card(own) else "POSTED"
            different = r.match.get("counterpart_owner") and r.payer and r.match["counterpart_owner"] != r.payer
            r.match["relationship"] = "TO_DECIDE" if different else "SAME_OWNER"
            if different:
                # Both legs of one payment, and every payment between the same two owners, form one
                # Dashboard group: "<who paid> → <whose card>".
                paid_by, card_of = ((r.payer, r.match["counterpart_owner"]) if r.match["posting"] == "POSTED"
                                    else (r.match["counterpart_owner"], r.payer))
                r.group_key = f"Card payments: {paid_by} → card of {card_of}"
            if different and not r.protected:
                # Never a receivable/payable created automatically: it may settle an earlier advance or be
                # another patrimonial operation. One exception, for a person to decide.
                r.exceptions.append(dict(code="RELATIONSHIP_TO_DECIDE", message=(
                    f"Rapporto economico da decidere: {r.payer} ({r.source}) e {r.match['counterpart_owner']} "
                    f"({r.match['counterpart_source']}) — the card payment itself is matched and complete.")))
        elif r.match and r.match.get("state") == "MATCHED" and r.operation_type == INTER_ACCOUNT_TRANSFER \
                and r.match.get("counterpart_owner") and r.payer and r.match["counterpart_owner"] != r.payer:
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
            personal = self._personal_entity()
            if personal in (r.payer_id, r.beneficiary_id):
                # A personal expense paid by an LLC (or the reverse): the ECONOMIC ATTRIBUTION is decided
                # (the cost belongs to the beneficiary); the credit/debit towards the owner is NOT created —
                # it may settle an earlier advance or be a draw/contribution. One exception to decide it.
                r.ledger.update(relationship="TO_DECIDE", note=(
                    f"Economic attribution: {r.beneficiary}. No receivable/payable created: the relationship "
                    f"between {r.payer} and {r.beneficiary} is to be decided."))
                if not r.protected:
                    r.exceptions.append(dict(code="RELATIONSHIP_TO_DECIDE", message=(
                        f"Rapporto economico da decidere: {r.payer} paid an expense of {r.beneficiary} — "
                        "the classification is complete; only the relationship between them is open.")))
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
        if r.match and r.match.get("state") == "MATCHED":
            return CARD_SETTLEMENT if r.match["kind"] == "CARD_SETTLEMENT" else INTER_ACCOUNT_TRANSFER
        a = self.c.classes.get(r.category_id)
        if a is None:
            return None
        code = a.code or ""
        if a.statement_type == "PROFIT_LOSS":
            return OPERATING_INCOME if self._is_income(a) else OPERATING_EXPENSE
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
        if r.match and r.match.get("state") == "MATCHED":
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

    @staticmethod
    def _is_income(category) -> bool:
        """A P&L category whose nature is income (credit balance or 4xxx revenue), e.g. 8100 Interest Income."""
        return category is not None and category.statement_type == "PROFIT_LOSS" and (
            (category.normal_balance or "").upper() == "CREDIT" or (category.code or "").startswith("4"))

    def _personal_entity(self):
        return next((e.id for e in self.c.entities.values() if e.entity_type == "PERSONAL" and e.status == "ACTIVE"), None)

    def _why_category(self, why_id):
        r = self.c.whys.get(why_id)
        return r.accounting_classification_id if r else None

    def _why_name(self, why_id):
        r = self.c.whys.get(why_id)
        return r.name if r else None

    FIELDS = ("who", "why", "category", "beneficiary")

    @staticmethod
    def _ai_field_declared(ai: dict | None, name: str) -> bool:
        return bool(ai) and isinstance(ai.get("fields"), dict) and isinstance(ai["fields"].get(name), dict)

    def _ai_field_ok(self, ai: dict | None, name: str) -> bool:
        """Field-level acceptance (sufficient + confidence ≥ threshold). Answers recorded before field-level
        evidence existed declared one `sufficient` for every field: for them the global flag still applies."""
        if not ai:
            return False
        if self._ai_field_declared(ai, name):
            f = ai["fields"][name]
            conf = f.get("confidence")
            return f.get("sufficient") is True and isinstance(conf, (int, float)) and conf >= config.AI_MIN_CONFIDENCE
        return self._ai_sufficient(ai)

    def _ai_fields(self, ai: dict) -> dict:
        values = dict(who=ai.get("who"), why=self._why_name(ai.get("why_id")),
                      category=self.c.class_label(ai.get("category_id")), beneficiary=self.c.entity_name(ai.get("beneficiary_id")))
        out = {}
        for name in self.FIELDS:
            f = ai["fields"][name] if self._ai_field_declared(ai, name) else {}
            out[name] = dict(value=values[name], confidence=f.get("confidence", ai.get("confidence")),
                             accepted=self._ai_field_ok(ai, name) and values[name] is not None,
                             investigation_id=ai.get("investigation_id"))
        return out

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
