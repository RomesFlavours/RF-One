"""One Bank engine: Source owner, matched transfers/card payments, approved WHO rules then name/alias.
Purpose is the exact WHO + Source classification, with no WHO-global or cross-Source fallback.
WHOM is the Source owner at the movement date. WHAT derives from WHY. Human WHO/WHY decisions remain
protected; missing pair classifications stay open. No activity labels, history memory or automatic AI.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict, replace

from sqlalchemy import select

from . import config, matching, store
from .legacy import Catalog, ai_rules, clean, flow, history_key, m, who_search_text, who_why_rules, why_patterns, why_what

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
NAME_ALIAS = "NAME/ALIAS"   # BANK_WHO_RULES_001: WHO found by its name or an alias in the description
WHO_SOURCE_CLASSIFICATION = "WHO + SOURCE"
WHO_CLASSIFICATION = WHO_SOURCE_CLASSIFICATION
WHY_RULE = "WHY RULE"   # an approved WHY pattern rule (BANK_WHY_PATTERNS_001), executed as code


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
    # Decision 86: the Source owner IS the accounting subject. `beneficiary_*` is only the management
    # destination (who the cost/revenue is for, operationally); it never moves the accounting.
    subject_id: int | None = None
    subject: str | None = None
    management: dict | None = None   # a management destination other than the subject (signalled, never posted)
    why_mode: str | None = None      # BANK_WHO_WHY_MODE_001: UNIQUE / MULTIPLE of the recognised WHO
    # BANK_SPLIT_ALLOCATION_001: the movement's split lines — proposed from a document (complete or not) or the
    # split already confirmed in Bank (allocations). A complete split takes the place of the single WHY.
    split: dict | None = None


class Engine:
    def __init__(self, db, con, catalog: Catalog | None = None):
        self.db = db
        self.con = con
        self.c = catalog or Catalog.load(db)
        # Phase 3A: no separate C-Bank decisions — Bank's human decisions are read and protected through
        # `bank_decision` (HUMAN (Bank)); this stays empty.
        self.human = {}
        self.ai_answers = {}  # manual investigations remain advisory; never loaded by reconciliation
        self.txns = list(db.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.accounting_status == "CANONICAL").order_by(m.FinancialTransaction.id)))
        self.txns = [t for t in self.txns if t.duplicate_status != "CONFIRMED_DUPLICATE"]
        self.by_id = {t.id: t for t in self.txns}
        self.ambiguous: dict[int, list] = {}
        self.matches = matching.match_all(self.txns, self.c.instruments, self.c.settlement, self.ambiguous)
        self.card_payment_out = matching.card_payment_pattern(self.c.instruments)
        self._owner_cache: dict = {}
        self._load_bank_decisions()
        self.memory = defaultdict(list)
        self.who_memory = defaultdict(list)  # advisory consumers only; never populated from history
        self.why_by_name = {clean(r.name): r.id for r in self.c.whys.values()}
        # Provisional WHYs (decisions 74-76, 79): a movement holding one is always an Exception.
        self.provisional = {w for w, r in self.c.whys.items() if why_what.is_provisional(self.db, r)}
        self.why_by_code = {r.code: r.id for r in self.c.whys.values()}
        self.entity_by_name = {}
        for e in self.c.entities.values():
            self.entity_by_name[clean(e.name)] = e.id
            self.entity_by_name[clean(e.code)] = e.id
        self.extractors = [e for e in self.c.rules if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "EXTRACTOR"]
        self.photos = [e for e in self.c.rules if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "PHOTO"]
        self.legacy = [e for e in self.c.rules if e[2].get("engine") != flow.ENGINE]
        # BANK_WHO_RULES_001: the same WHO recognition as the WHO Rules page, on the same rules.
        self.recogniser = who_search_text.WhoRecogniser(db, rules=self.c.rules)
        self.who_registration_holds = {}
        self.source_classifications = {(x.occurrence_id, x.payment_instrument_id): x.transaction_reason_id
            for x in db.scalars(select(m.BankWhoSourceClassification))}
        # BANK_WHO_WHY_MODE_001: once WHO is recognised, its WHY comes from the WHO + Source pair (UNIQUE WHO)
        # or from the WHO WHY rules (MULTIPLE WHO, or a UNIQUE WHO whose pair has no WHY). Rules read the
        # BANK_WHY_PATTERNS_001 information; missing information leaves the movement open, never fails.
        self.why_resolver = who_why_rules.Resolver(db, txns=self.txns, rows=self.c.row_builder)

    def split_view(self, proposal) -> dict:
        """A `split_allocation.Proposal` with each line's WHY name, WHAT and Category."""
        whys = {w: dict(why=self._why_name(w), what=self.c.class_label(self._why_category(w)),
                        category_id=self._why_category(w)) for w in {ln.why_id for ln in proposal.lines if ln.why_id}}
        return dict(proposal.to_dict(whys), origin="DOCUMENT")

    def bank_split(self, txn) -> dict | None:
        """The split already written in Bank (2+ allocations): protected, as a human decision is."""
        allocs = sorted(self.allocations.get(txn.id, []), key=lambda a: a.allocation_index)
        if len(allocs) < 2:
            return None
        allocated = sum(a.amount_minor for a in allocs)
        complete = allocated == txn.amount_minor and all(a.status == m.ALLOCATION_COMPLETE for a in allocs)
        lines = [dict(amount_minor=a.amount_minor, why_id=a.transaction_reason_id, why=a.transaction_reason_name_snapshot,
                      category_id=a.accounting_classification_id,
                      what=" ".join(x for x in (a.accounting_classification_code_snapshot, a.accounting_classification_name_snapshot) if x),
                      description=getattr(a, "description", None),
                      items=json.loads(a.evidence_detail) if getattr(a, "evidence_detail", None) else [],
                      status=a.status, decision_source=a.decision_source) for a in allocs]
        reasons = [] if complete else [dict(code="BANK_SPLIT_INCOMPLETE", label="Ripartizione incompleta",
                                            detail=f"allocated {allocated / 100:.2f} of {txn.amount_minor / 100:.2f}; "
                                                   + ", ".join(sorted({a.status for a in allocs})))]
        return dict(origin="BANK", total_minor=txn.amount_minor, allocated_minor=allocated,
                    difference_minor=txn.amount_minor - allocated, complete=complete,
                    status="COMPLETE" if complete else "INCOMPLETE", reasons=reasons, lines=lines,
                    human=any(a.decision_source == "HUMAN" for a in allocs), link=None, documents=[])

    def determine_why(self, txn, who_id, who=None, row=None):
        """The WHY of a recognised WHO on this movement (`who_why_rules.Determination`)."""
        pair = self.source_classifications.get((who_id, txn.payment_instrument_id))
        return self.why_resolver.determine(txn, who_id=who_id, who=who, row=row,
                                           pair_why=pair if pair in self.c.whys else None)

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
        if mt:
            # A certain transfer/payment follows only the matching path, ahead of text rules and profiles.
            outcome = self._transfer_outcome(txn, mt, r.payer_id, cp_owner)
            who = f"{cp_owner.name} · {self.c.instruments[mt.counterpart_instrument_id].display_name}" if cp_owner else None
            trace.append(Step("WHO", CONTEXT, who, f"counterparty of a matched {mt.kind.lower()} ({mt.basis})", ""))
            trace.append(Step("Profile", CONTEXT, self._why_name(outcome.why_id) if outcome else None,
                              "matched transfer/payment: the transfer path takes precedence over rules and profiles", ""))
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
                        beneficiary_id=r.payer_id, beneficiary_method=ACCOUNT if r.payer_id else None, exceptions=[exc],
                        trace=[asdict(s) for s in trace], counterpart_owner=None)

        # WHO --------------------------------------------------------------
        row = self.c.rule_row(txn)
        # BANK_WHO_RULES_001 — one shared path: guided AI rules, then WHO name/alias search.
        recognition = self.recogniser.recognise(txn, row=row)
        legacy_hits = recognition.legacy_hits
        from rfone_data_store.bank_reconciliation.who_recognition import who_key
        held = self.who_registration_holds.get(who_key(recognition.who)) if recognition.who else None
        if held:
            recognition = who_search_text.Recognition(who_search_text.TEXT_AMBIGUOUS,
                candidates=[recognition.who], evidence=held, legacy_hits=recognition.legacy_hits)
        who, who_method, who_evidence = None, None, ""
        if recognition.outcome == who_search_text.FOUND:
            who = recognition.who
            who_method = RULE if recognition.method == who_search_text.RULE else NAME_ALIAS
            who_evidence = recognition.evidence
        elif recognition.outcome in (who_search_text.RULES_DISAGREE, who_search_text.TEXT_AMBIGUOUS):
            exceptions.append(dict(code="WHO_AMBIGUOUS", message=recognition.evidence[:1].upper() + recognition.evidence[1:] + ".",
                                   question=None))
        else:
            exceptions.append(dict(code="WHO_UNKNOWN", message="No WHO rule and no WHO name or alias identifies WHO.",
                                   question=None))
        who_id = self.c.who_by_name.get(clean(who)) if who else None
        trace.append(Step("WHO", who_method or "—", who, who_evidence or "not identified",
                          "known WHO" if who_id else ("new WHO" if who else "")))

        # BANK_WHO_WHY_MODE_001: UNIQUE WHO → exact WHO + Source classification; MULTIPLE WHO (or a UNIQUE
        # WHO whose pair has no WHY) → WHO WHY rules. No WHO-only default or another Source decides WHY.
        outcome, split = None, None
        if who_id:
            det = self.determine_why(txn, who_id, who=who, row=row)
            r.why_mode = det.mode
            if det.split is not None:
                split = self.split_view(det.split)
            if det.why_id:
                outcome = Outcome(det.why_id, self._why_category(det.why_id), r.payer_id, det.method, det.reference)
            elif det.method == who_why_rules.METHOD_SPLIT and split and split["complete"]:
                trace.append(Step("Split", det.method, f"{len(split['lines'])} lines", det.reference, "complete"))
            else:
                exceptions.append(dict(code=det.code, message=det.message, label=det.label, missing=det.missing,
                                       question=None))
            if det.unused_pair_why:
                r.anomalies.append(dict(code="PAIR_WHY_NOT_USED_FOR_MULTIPLE_WHO", message=(
                    f"“{self._why_name(det.unused_pair_why)}” is registered on this WHO + Source, but the WHO is "
                    "MULTIPLE: its WHY comes from a WHO WHY rule only.")))
        elif who:
            exceptions.append(dict(code=who_why_rules.NEEDS_PAIR, label=who_why_rules.LABELS[who_why_rules.NEEDS_PAIR],
                                   message="Set WHY for this exact WHO + Source pair in Configuration."))
        if outcome and not mt and txn.amount_minor < 0 and self._is_income(
                self.c.classes.get(outcome.category_id or self._why_category(outcome.why_id))):
            # E1: a text rule can match the words ("INTEREST PAYMENT") of an operation whose direction
            # contradicts it (interest PAID on a loan is not interest income): never reconcile it silently.
            exceptions.append(dict(code="DIRECTION_CONFLICT", message=(
                f"“{self._why_name(outcome.why_id)}” is an income, but this movement is money OUT "
                f"({outcome.reference}): verify the nature of the operation."),
                question=None))
        if outcome:
            trace.append(Step("Classification", outcome.method, self._why_name(outcome.why_id), outcome.reference, ""))
        else:
            trace.append(Step("Classification", "—", None, "no classification", ""))

        # MANAGEMENT DESTINATION (decision 86: never the accounting subject) ----------------
        beneficiary, b_method = r.payer_id, ACCOUNT if r.payer_id else None
        b_evidence = "WHOM is the Source owner at the movement date"
        trace.append(Step("Destination", b_method or "—", self.c.entity_name(beneficiary),
                          (b_evidence or "") + " — management only; the accounting subject is the Source owner",
                          "default" if b_method == ACCOUNT else ""))

        why_id = outcome.why_id if outcome else None
        # BANK_WHY_REQUIRES_WHAT_001: the WHAT derives from the WHY. A different WHAT proposed by a profile
        # destination or by the AI is never applied; it is only signalled.
        category_id = self._why_category(why_id) or (outcome.category_id if outcome else None)
        if outcome and outcome.category_id and self._why_category(why_id) \
                and outcome.category_id != self._why_category(why_id):
            r.anomalies.append(dict(code="WHAT_NOT_FROM_WHY", message=(
                f"{outcome.reference} proposed WHAT {self.c.class_label(outcome.category_id)}; the WHAT of "
                f"“{self._why_name(why_id)}” ({self.c.class_label(self._why_category(why_id))}) is used.")))
        return dict(who=who, who_id=who_id, who_method=who_method, why_id=why_id,
                    why_method=outcome.method if outcome else (who_why_rules.METHOD_SPLIT if split and split["complete"] else None),
                    category_id=category_id, split=split,
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

    # -- protection ----------------------------------------------------------

    def _apply_protection(self, txn, r: Result, auto: dict):
        bank = r.bank
        r.trace.extend(auto["trace"])
        if bank["source"] != "HUMAN" or not bank["who_id"]:
            r.who_name, r.who_id, r.who_method = auto["who"], auto["who_id"], auto["who_method"]
            r.why_id, r.why_method, r.category_id = auto["why_id"], auto["why_method"], auto["category_id"]
            r.split = auto.get("split")
            r.beneficiary_id, r.beneficiary_method = r.payer_id, ACCOUNT if r.payer_id else None
            r.exceptions.extend(auto["exceptions"])
            return
        r.protected = HUMAN_BANK
        r.who_name, r.who_id, r.who_method = bank["who"], bank["who_id"], HUMAN_BANK
        r.why_id, r.why_method = bank["why_id"], HUMAN_BANK if bank["why_id"] else None
        if not r.why_id:
            # Completed as for an automatic WHO: pair (UNIQUE) or WHO WHY rule (MULTIPLE).
            det = self.determine_why(txn, bank["who_id"], who=bank["who"], row=self.c.rule_row(txn))
            r.why_mode = det.mode
            if det.why_id and det.why_id not in self.provisional:
                r.why_id, r.why_method = det.why_id, det.method + " (completing a human decision)"
            elif det.split is not None:
                r.split = self.split_view(det.split)
                if r.split["complete"]:
                    r.why_method = det.method + " (completing a human decision)"
        r.category_id = self._why_category(r.why_id)
        r.beneficiary_id, r.beneficiary_method = r.payer_id, ACCOUNT if r.payer_id else None
        r.trace.append(asdict(Step("Protection", HUMAN_BANK, "human WHO/WHY preserved",
                                   "Only a missing WHY is completed from the same WHO + Source; WHAT derives from WHY; WHOM defaults to the Source owner unless manually chosen.")))
        differs = [field for field, proposed, actual in (("WHO",auto["who"],r.who_name),
                    ("WHY",auto["why_id"],r.why_id)) if proposed is not None and proposed != actual]
        if differs:
            r.proposal = dict(fields=differs, who=auto["who"], why=self._why_name(auto["why_id"]),
                              category=self.c.class_label(auto["category_id"]), beneficiary=r.payer,
                              note="Proposal only; the confirmed human decision stays protected.")
        if not r.why_id and not (r.split and r.split["complete"]):
            r.exceptions.append(dict(code="HUMAN_INCOMPLETE", message="Set WHY for this human WHO and the exact Source."))

    # -- finish ----------------------------------------------------------------

    def _finish(self, txn, r: Result):
        # BANK_SPLIT_ALLOCATION_001: a split already written in Bank decides the WHYs of the movement; it is
        # protected like a human decision, and an open WHY reason no longer applies to it.
        confirmed = self.bank_split(txn)
        if confirmed:
            r.split = confirmed
            if confirmed["human"]:
                r.protected = r.protected or HUMAN_BANK
            if confirmed["complete"]:
                r.why_id, r.why_method = None, (HUMAN_BANK if confirmed["human"] else "RULE") + " split"
                r.exceptions = [x for x in r.exceptions if x["code"] not in who_why_rules.OPEN_REASONS
                                and x["code"] not in ("HUMAN_INCOMPLETE", "DIRECTION_CONFLICT")]
            r.trace.append(asdict(Step("Split", r.why_method or "—", f"{len(confirmed['lines'])} lines in Bank",
                                       "allocations of this movement; WHAT from each line's WHY", confirmed["status"])))
        if r.split and not r.split["complete"] and r.split["origin"] == "BANK":
            r.exceptions.append(dict(code=who_why_rules.SPLIT_INCOMPLETE, label=who_why_rules.LABELS[who_why_rules.SPLIT_INCOMPLETE],
                                     message="; ".join(x["label"] + (f" ({x['detail']})" if x["detail"] else "")
                                                       for x in r.split["reasons"]), missing=[]))
        # A manual movement-level WHOM overrides the Source-owner default independently of WHO/WHY.
        if r.bank.get("beneficiary_human") and r.bank.get("beneficiary_id"):
            r.beneficiary_id = r.bank["beneficiary_id"]
            r.beneficiary_method = HUMAN_BANK
            r.trace.append(asdict(Step("Protection", HUMAN_BANK, "manual WHOM preserved",
                                       "Movement-level destination; Source owner and accounting subject unchanged.")))
        r.why = self._why_name(r.why_id)
        r.category = self.c.class_label(r.category_id)
        split_done = bool(r.split and r.split["complete"] and not r.why_id)
        if split_done:
            r.why = f"Ripartizione: {len(r.split['lines'])} righe"
            r.category = "; ".join(dict.fromkeys(ln.get("what") or "—" for ln in r.split["lines"]))
        r.qb_account = None  # QuickBooks COA not imported yet (MVP decision): shown as "not mapped".
        r.beneficiary = self.c.entity_name(r.beneficiary_id)
        r.operation_type = self._operation_type(txn, r)
        if split_done:
            ops = {self._operation_type(txn, replace(r, category_id=ln.get("category_id"))) for ln in r.split["lines"]}
            r.operation_type = next(iter(ops)) if len(ops) == 1 else None
            if r.operation_type is None:
                # Lines of different operation types (e.g. an expense and an asset): shown, never merged.
                r.anomalies.append(dict(code="SPLIT_MIXED_OPERATION", message=(
                    "The split lines belong to different operation types: " + ", ".join(sorted(str(o) for o in ops)))))
                r.operation_type = "SPLIT"
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
        # Decision 86: the Source owner is the accounting subject. Another entity is only a management
        # destination: signalled, never posted to it, and never a receivable/payable by itself.
        r.subject_id, r.subject = r.payer_id, r.payer
        personal = self._personal_entity()
        if r.payer_id and r.beneficiary_id and r.payer_id != r.beneficiary_id \
                and r.operation_type not in (INTER_ACCOUNT_TRANSFER, CARD_SETTLEMENT):
            r.management = dict(destination_id=r.beneficiary_id, destination=r.beneficiary,
                                basis=r.beneficiary_method, amount_minor=-r.amount_minor)
            if r.beneficiary_id == personal:
                # A personal expense paid from an LLC Source: posted in the LLC (its WHY/WHAT); whether it is a
                # draw, an advance to the owner or the settlement of an earlier one is the relationship to decide.
                r.management["note"] = (f"Paid by {r.payer} for {r.beneficiary}: posted in {r.payer}; the relationship "
                                        "with the owner is to be decided (draw, advance or settlement).")
                if not r.protected:
                    r.exceptions.append(dict(code="RELATIONSHIP_TO_DECIDE", message=(
                        f"Rapporto economico da decidere: {r.payer} paid an expense of {r.beneficiary} — "
                        f"it stays in the accounts of {r.payer} (decision 86); only the relationship is open.")))
            elif r.payer_id == personal:
                r.management["note"] = (f"Business use of a personal Source ({r.beneficiary}): signalled only; "
                                        "it stays in personal accounting (decision 86).")
                r.anomalies.append(dict(code="PROMISCUOUS_USE", message=r.management["note"]))
            else:
                r.management["note"] = (f"Management destination {r.beneficiary}; posted in {r.payer} (decision 86). "
                                        "Any recharge between entities is decided later.")
                r.anomalies.append(dict(code="MANAGEMENT_DESTINATION", message=r.management["note"]))
        category = self.c.classes.get(r.category_id)
        if r.payer_id and r.payer_id == personal and category is not None and category.statement_type == "PROFIT_LOSS" \
                and not self._is_income(category) and r.operation_type not in (INTER_ACCOUNT_TRANSFER, CARD_SETTLEMENT):
            # Personal accounting (decision 86) with a business P&L WHAT of the LLC chart: the WHY does not fit
            # the subject (e.g. a business meal on a personal card). Never moved to an LLC; a person decides.
            item = dict(code="PERSONAL_SOURCE_BUSINESS_WHAT", message=(
                f"Personal Source, business WHAT {category.code} {category.name}: in personal accounting this needs "
                "a personal WHY, or a recorded decision (decision 86 — never moved to an LLC automatically)."))
            (r.anomalies if r.protected else r.exceptions).append(item)
        if r.operation_type == INTER_ENTITY and r.match and r.amount_minor < 0:
            r.ledger = dict(kind="TRANSFER", payer_id=r.payer_id, payer=r.payer,
                            beneficiary=r.match.get("counterpart_owner"),
                            beneficiary_id=self.entity_by_name.get(clean(r.match.get("counterpart_owner"))),
                            amount_minor=-r.amount_minor,
                            proposal="Advance or repayment between entities — propose offset against open balances.",
                            note="Decision 07/14: no new cost; qualify as advance or repayment.")
        if r.why_id in self.provisional:
            r.exceptions.append(dict(code="PROVISIONAL_WHY", message=(
                f"“{r.why}” is a provisional WHY: the nature of this movement is still to be established "
                "(investigate with AI or decide). It is never Reconciled with a provisional WHY.")))
        elif r.why_id and not r.category_id:
            r.exceptions.append(dict(code="CATEGORY_MISSING", message=f"WHY “{r.why}” has no Category RF-One in the "
                                     "Bank catalog: choose it for this movement; a catalog change needs approval (decision 39)."))
        blocking = [e for e in r.exceptions]
        complete = all([r.who_name, r.why_id or split_done, r.category_id or split_done, r.subject_id, r.operation_type])
        r.status = RECONCILED if complete and not blocking else EXCEPTION
        if r.status == EXCEPTION and complete is False and not blocking:
            missing = [n for n, v in (("WHO", r.who_name), ("WHY", r.why_id), ("Category", r.category_id),
                                      ("Accounting subject (Source owner)", r.subject_id),
                                      ("Operation", r.operation_type)) if not v]
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
