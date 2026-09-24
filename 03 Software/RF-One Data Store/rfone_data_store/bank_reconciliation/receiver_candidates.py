"""Unclassified receivers — Who candidates derived from transactions
(BANK_CLASSIFICATION_BOOTSTRAP_001).

The problem: 423 canonical transactions is too many to classify one at a
time, but they are not 423 different receivers. Grouping them by the
receiver they actually name turns the work into a few hundred decisions
that each cover many rows, and every future import of the same receiver
is then recognized automatically.

Everything here is DERIVED. No candidate is stored, no row is written, and
no `BankOccurrence` is created as a side effect of looking: a candidate
becomes a Who only when a human approves it (`approve_candidate`).

What is considered, and what is deliberately not:

* only ACCOUNTING-CANONICAL transactions — the 49 suppressed copies are
  never offered as candidates of their own, because classifying a copy is
  work that can never reach the books;
* not a confirmed internal transfer — a transfer between the business's
  own instruments has no receiver to identify;
* not a transaction that already carries a resolved human decision.

Grouping is EXACT on the normalized payee. Two descriptions that merely
look alike are shown as SUGGESTIONS, side by side, with the reason — they
are never merged automatically, because the difference between
`US FOODS 4821` and `US FOODS 4822` may be two invoices or two entirely
different counterparties, and only a person can tell.

The normalization reused here is `accounting_dedup.normalize_payee`, but
the two questions must not be confused: that one asks "is this the SAME
accounting fact", this one asks "is this the SAME receiver". The first
includes the settlement account, the date and the amount; this one is
about the description alone.

No external AI and no network call: every outcome is explainable from the
stored data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup, classification as classification_service, recognition
from . import purpose_evidence, structural_why

STATUS_UNCLASSIFIED = "UNCLASSIFIED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_ASSIGNED = "ASSIGNED"

# How a transaction's classification came about — shown on every row so a
# reader never has to guess whether a person or a rule decided it.
ORIGIN_HUMAN = "HUMAN"
ORIGIN_LEARNED_EXACT = "LEARNED_EXACT_MATCH"
ORIGIN_AMBIGUOUS = "AMBIGUOUS"
ORIGIN_MISSING = "MISSING"

_TOKEN_SPLIT = re.compile(r"[^A-Z0-9]+")
# A token that is purely digits of this length or more is treated as an
# invoice/order/store number for SIMILARITY SUGGESTIONS only. It is never
# removed from the grouping key itself.
_MIN_VARIABLE_DIGITS = 3


@dataclass
class SimilarGroup:
    payee_normalized: str
    transaction_count: int
    reason: str


@dataclass
class ReceiverCandidate:
    """One group of canonical transactions naming the same receiver."""

    payee_normalized: str
    direction: str                 # DEBIT | CREDIT
    transaction_count: int
    first_date: date | None
    last_date: date | None
    total_minor: int
    absolute_total_minor: int
    sample_descriptions: list[str] = field(default_factory=list)
    transaction_ids: list[int] = field(default_factory=list)
    legal_entity_names: list[str] = field(default_factory=list)
    instrument_names: list[str] = field(default_factory=list)
    suggested_occurrence_id: int | None = None
    suggested_occurrence_name: str | None = None
    confidence: str | None = None
    confidence_reason: str | None = None
    status: str = STATUS_UNCLASSIFIED
    origin: str = ORIGIN_MISSING
    similar: list[SimilarGroup] = field(default_factory=list)
    # BANK_MEMO_PURPOSE_CLASSIFICATION_001 — WHO and PURPOSE shown as two
    # separate answers, so a reviewer can see that the person is known and
    # the reason is not.
    channel: str = "OTHER"          # ZELLE | ACH | CHECK | CARD | WIRE | OTHER
    counterparty_name: str | None = None
    is_person_channel: bool = False
    source_memos: list[str] = field(default_factory=list)
    purpose_status: str = "ABSENT"  # PROVEN | AMBIGUOUS | ABSENT
    purpose_account_code: str | None = None
    purpose_rationale: str | None = None

    @property
    def group_key(self) -> str:
        return f"{self.direction}|{self.payee_normalized}"

    @property
    def purpose_is_proven(self) -> bool:
        return self.purpose_status == "PROVEN"

    @property
    def learning_warning(self) -> str | None:
        """What a "learn this" tick would actually teach, in the reviewer's
        own terms. Shown next to the checkbox so nobody creates
        "this person always means this account" without meaning to."""
        if not self.is_person_channel:
            return None
        who = self.counterparty_name or "this counterparty"
        return (
            f"{who} is a person/payee, so the learned rule will recognise WHO only. The "
            "accounting treatment stays a decision per payment — a later payment to the "
            "same person may be something else entirely."
        )


def _similarity_stem(payee: str) -> str:
    """The payee with variable numeric tokens masked.

    Used ONLY to propose that two groups might be the same receiver. The
    numbers are masked here and never in the grouping key, precisely
    because they may be what distinguishes two receivers rather than two
    invoices of one."""
    tokens = [t for t in _TOKEN_SPLIT.split(payee) if t]
    stem = [
        "#" if (token.isdigit() and len(token) >= _MIN_VARIABLE_DIGITS) else token
        for token in tokens
    ]
    return " ".join(stem)


def _classification_origin(
    session: Session, explanation: "m.BankTransactionExplanation | None",
) -> str:
    if explanation is None or explanation.decision_status not in recognition.RESOLVED_DECISION_STATUSES:
        return ORIGIN_MISSING
    if explanation.decision_source == "HUMAN":
        return ORIGIN_HUMAN
    if explanation.recognition_rule_id is not None:
        rule = session.get(m.BankRecognitionRule, explanation.recognition_rule_id)
        if rule is not None and rule.match_type == recognition.EXACT_NORMALIZED_DESCRIPTION:
            return ORIGIN_LEARNED_EXACT
    return ORIGIN_LEARNED_EXACT


def _candidate_transactions(session: Session) -> list["m.FinancialTransaction"]:
    """The transactions a receiver candidate may be built from.

    Excludes suppressed accounting copies, un-evaluable rows, confirmed
    internal transfers and confirmed duplicates. Every exclusion is a case
    where asking a human to name a receiver would be wasted work."""
    transactions = list(session.scalars(
        select(m.FinancialTransaction).where(
            m.FinancialTransaction.accounting_status == accounting_dedup.CANONICAL,
            or_(
                m.FinancialTransaction.duplicate_status.is_(None),
                m.FinancialTransaction.duplicate_status != "CONFIRMED_DUPLICATE",
            ),
        ).order_by(m.FinancialTransaction.posting_date, m.FinancialTransaction.id)
    ).all())

    transfer_ids = _confirmed_transfer_ids(session, [t.id for t in transactions])
    return [t for t in transactions if t.id not in transfer_ids]


def _confirmed_transfer_ids(session: Session, transaction_ids: list[int]) -> set[int]:
    if not transaction_ids:
        return set()
    matches = session.scalars(
        select(m.FinancialTransactionMatch).where(
            m.FinancialTransactionMatch.match_type == "INTERNAL_TRANSFER",
            or_(
                m.FinancialTransactionMatch.transaction_a_id.in_(transaction_ids),
                m.FinancialTransactionMatch.transaction_b_id.in_(transaction_ids),
            ),
        )
    ).all()
    confirmed: set[int] = set()
    for match in matches:
        confirmed.add(match.transaction_a_id)
        confirmed.add(match.transaction_b_id)
    return confirmed


def _who_decided(explanation: "m.BankTransactionExplanation | None") -> bool:
    """Whether this decision settles the WHO — the only question this review
    answers. A resolved decision does; so does a person's Who-only decision,
    whose Why is still open (BANK_FINAL_RELEASE_BLOCKERS_001): its Who was
    decided by a human and is never re-asked or overwritten here."""
    if explanation is None:
        return False
    if explanation.decision_status in recognition.RESOLVED_DECISION_STATUSES:
        return True
    return explanation.decision_source == "HUMAN" and explanation.occurrence_id is not None


def build_candidates(
    session: Session, *, include_assigned: bool = True,
) -> list[ReceiverCandidate]:
    """Every receiver group, most transactions first.

    Derived on every call from the current transactions — there is no
    stored candidate to go stale, and nothing here writes."""
    transactions = _candidate_transactions(session)

    instruments = {
        i.id: i for i in session.scalars(select(m.PaymentInstrument)).all()
    }
    entities = {e.id: e for e in session.scalars(select(m.LegalEntity)).all()}
    explanation_ids = {t.explanation_id for t in transactions if t.explanation_id is not None}
    explanations = {
        e.id: e for e in session.scalars(
            select(m.BankTransactionExplanation)
            .where(m.BankTransactionExplanation.id.in_(explanation_ids))
        ).all()
    } if explanation_ids else {}

    registry = structural_why.load_registry(session)
    reasons = {r.code: r for r in session.scalars(select(m.BankTransactionReason)).all()}

    groups: dict[tuple[str, str], ReceiverCandidate] = {}
    occurrences_seen: dict[tuple[str, str], set[int]] = {}
    origins_seen: dict[tuple[str, str], set[str]] = {}

    for txn in transactions:
        payee = txn.payee_normalized or accounting_dedup.normalize_payee(txn.description_original)
        direction = recognition.direction_for_amount(txn.amount_minor)
        key = (direction, payee)

        candidate = groups.get(key)
        if candidate is None:
            candidate = ReceiverCandidate(
                payee_normalized=payee, direction=direction, transaction_count=0,
                first_date=txn.posting_date, last_date=txn.posting_date,
                total_minor=0, absolute_total_minor=0,
            )
            groups[key] = candidate
            occurrences_seen[key] = set()
            origins_seen[key] = set()

        candidate.transaction_count += 1
        candidate.total_minor += txn.amount_minor
        candidate.absolute_total_minor += abs(txn.amount_minor)
        candidate.transaction_ids.append(txn.id)
        if txn.posting_date is not None:
            if candidate.first_date is None or txn.posting_date < candidate.first_date:
                candidate.first_date = txn.posting_date
            if candidate.last_date is None or txn.posting_date > candidate.last_date:
                candidate.last_date = txn.posting_date
        if txn.description_original and txn.description_original not in candidate.sample_descriptions:
            if len(candidate.sample_descriptions) < 5:
                candidate.sample_descriptions.append(txn.description_original)

        # WHO and PURPOSE, asked separately and answered separately.
        who = purpose_evidence.who_evidence(txn.description_original)
        if candidate.channel == "OTHER":
            candidate.channel = who.channel
        candidate.is_person_channel = candidate.is_person_channel or who.is_person_channel
        if who.counterparty_name and candidate.counterparty_name is None:
            candidate.counterparty_name = who.counterparty_name
        memo = (txn.source_memo or "").strip()
        if memo and memo not in candidate.source_memos and len(candidate.source_memos) < 5:
            candidate.source_memos.append(memo)
        # Purpose shown through the ONE automatic engine, so this review can
        # never display a Why the engine would not assign.
        engine = structural_why.recognize_transaction(session, txn, registry)
        engine_reason = structural_why.usable_reason(session, engine, reasons)
        purpose_status = "PROVEN" if engine_reason is not None else "ABSENT"
        purpose_account = (engine_reason.accounting_classification.code
                           if engine_reason is not None else None)
        # PROVEN beats ABSENT, and a group is only ever reported as proven
        # when every one of its transactions is.
        if candidate.transaction_count == 1:
            candidate.purpose_status = purpose_status
            candidate.purpose_account_code = purpose_account
            candidate.purpose_rationale = engine.evidence
        elif purpose_status != candidate.purpose_status or (
            purpose_account != candidate.purpose_account_code
        ):
            candidate.purpose_status = (
                "AMBIGUOUS" if candidate.purpose_status == "PROVEN"
                or purpose.status == "PROVEN" else candidate.purpose_status
            )
            candidate.purpose_account_code = None
            candidate.purpose_rationale = (
                "The transactions in this group do not agree about why the money moved."
            )

        instrument = instruments.get(txn.payment_instrument_id)
        if instrument is not None and instrument.display_name not in candidate.instrument_names:
            candidate.instrument_names.append(instrument.display_name)
        settlement = instruments.get(txn.accounting_settlement_account_id)
        entity = entities.get(settlement.legal_entity_id) if settlement is not None else None
        if entity is not None and entity.legal_name not in candidate.legal_entity_names:
            candidate.legal_entity_names.append(entity.legal_name)

        explanation = explanations.get(txn.explanation_id) if txn.explanation_id else None
        origins_seen[key].add(_classification_origin(session, explanation))
        if (
            explanation is not None
            and explanation.decision_status in recognition.RESOLVED_DECISION_STATUSES
            and explanation.occurrence_id is not None
        ):
            occurrences_seen[key].add(explanation.occurrence_id)

    # --- status, origin and suggestion -------------------------------------
    for key, candidate in groups.items():
        decided = occurrences_seen[key]
        origins = origins_seen[key]

        if len(decided) > 1:
            # Two different Who values already recorded for what is textually
            # the same receiver: a person must resolve it, never the engine.
            candidate.status = STATUS_AMBIGUOUS
            candidate.origin = ORIGIN_AMBIGUOUS
            names = []
            for occurrence_id in sorted(decided):
                occurrence = session.get(m.BankOccurrence, occurrence_id)
                names.append(occurrence.canonical_name if occurrence else str(occurrence_id))
            candidate.confidence = "NONE"
            candidate.confidence_reason = (
                "Transactions with this exact normalized payee are already classified under "
                f"different Who values ({', '.join(names)}). RF-One will not choose between them."
            )
        elif len(decided) == 1 and len(decided) == len(occurrences_seen[key]):
            occurrence_id = next(iter(decided))
            occurrence = session.get(m.BankOccurrence, occurrence_id)
            candidate.suggested_occurrence_id = occurrence_id
            candidate.suggested_occurrence_name = (
                occurrence.canonical_name if occurrence else None
            )
            fully_decided = len([
                t for t in transactions
                if t.id in candidate.transaction_ids
                and t.explanation_id is not None
                and _who_decided(explanations.get(t.explanation_id))
            ]) == candidate.transaction_count
            candidate.status = STATUS_ASSIGNED if fully_decided else STATUS_UNCLASSIFIED
            candidate.origin = (
                ORIGIN_HUMAN if ORIGIN_HUMAN in origins
                else (ORIGIN_LEARNED_EXACT if ORIGIN_LEARNED_EXACT in origins else ORIGIN_MISSING)
            )
            candidate.confidence = "HIGH" if candidate.status == STATUS_ASSIGNED else "MEDIUM"
            candidate.confidence_reason = (
                f"Every decided transaction with this payee resolves to "
                f"{candidate.suggested_occurrence_name!r}."
                if candidate.status == STATUS_ASSIGNED else
                f"Some transactions with this payee are already classified as "
                f"{candidate.suggested_occurrence_name!r}; the rest are not."
            )
        else:
            candidate.status = STATUS_UNCLASSIFIED
            candidate.origin = ORIGIN_MISSING
            match = _rule_suggestion(session, candidate)
            if match is not None:
                occurrence, reason = match
                candidate.suggested_occurrence_id = occurrence.id
                candidate.suggested_occurrence_name = occurrence.canonical_name
                candidate.confidence = "MEDIUM"
                candidate.confidence_reason = reason

    _attach_similarity(list(groups.values()))

    candidates = sorted(
        groups.values(),
        key=lambda c: (-c.transaction_count, -c.absolute_total_minor, c.payee_normalized),
    )
    if not include_assigned:
        candidates = [c for c in candidates if c.status != STATUS_ASSIGNED]
    return candidates


def _rule_suggestion(
    session: Session, candidate: ReceiverCandidate,
) -> tuple["m.BankOccurrence", str] | None:
    """An existing ACTIVE exact rule that already recognizes this payee.
    Only an exact-match rule is used as a suggestion — a broad
    CONTAINS/PREFIX rule is not evidence about a specific receiver."""
    rule = session.scalars(
        select(m.BankRecognitionRule).where(
            m.BankRecognitionRule.status == "ACTIVE",
            m.BankRecognitionRule.match_type == recognition.EXACT_NORMALIZED_DESCRIPTION,
            m.BankRecognitionRule.normalized_pattern == candidate.payee_normalized,
        )
    ).first()
    if rule is None:
        return None
    occurrence = session.get(m.BankOccurrence, rule.occurrence_id)
    if occurrence is None:
        return None
    return occurrence, (
        f"An existing exact-match rule (#{rule.id}) already recognizes this description as "
        f"{occurrence.canonical_name!r}."
    )


def _attach_similarity(candidates: list[ReceiverCandidate]) -> None:
    """Group SUGGESTIONS, never merges.

    Two candidates whose payees differ only in numeric tokens are shown to
    each other with the reason. They stay separate groups: the numbers may
    be two invoices of one supplier, or two different counterparties, and
    that is a human judgement."""
    by_stem: dict[str, list[ReceiverCandidate]] = {}
    for candidate in candidates:
        by_stem.setdefault(_similarity_stem(candidate.payee_normalized), []).append(candidate)

    for stem, group in by_stem.items():
        if len(group) < 2 or "#" not in stem:
            continue
        for candidate in group:
            for other in group:
                if other is candidate:
                    continue
                candidate.similar.append(SimilarGroup(
                    payee_normalized=other.payee_normalized,
                    transaction_count=other.transaction_count,
                    reason=(
                        "Identical apart from numeric tokens "
                        f"(shared pattern: {stem!r}). Shown as a suggestion only — RF-One never "
                        "merges these automatically, because the digits may distinguish two "
                        "invoices of one receiver or two different receivers."
                    ),
                ))


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


@dataclass
class ApprovalOutcome:
    occurrence_id: int
    occurrence_name: str
    transactions_classified: int
    transactions_skipped_human: int
    rules_created: list[int] = field(default_factory=list)
    payees: list[str] = field(default_factory=list)


def approve_candidates(
    session: Session, *, payee_keys: list[str], occurrence_id: int | None = None,
    new_occurrence_name: str | None = None, occurrence_type_id: int | None = None,
    default_transaction_reason_id: int | None = None,
    confirmed_by_account_id: int | None = None, learn_description: bool = True,
) -> ApprovalOutcome:
    """Approve one or more receiver groups onto one Who, in one operation.

    Atomic by construction: every check that can fail raises BEFORE any
    decision row is written, and the caller's transaction is what commits
    — so a partially classified group is not a state this can produce.

    Either an existing `occurrence_id` is supplied, or a new Who is created
    from `new_occurrence_name` + `occurrence_type_id` +
    `default_transaction_reason_id`. Only the WHO is recorded: the Who's
    default Why is never applied (BANK_FINAL_RELEASE_BLOCKERS_001), so each
    transaction keeps its own Why question for the automatic engine or a
    person.

    A transaction that already carries a HUMAN decision is SKIPPED, never
    overwritten. Suppressed accounting copies are not in the candidate set
    at all, so they are never classified here."""
    if not payee_keys:
        raise ValueError("Select at least one receiver group to approve.")

    if occurrence_id is not None:
        occurrence = session.get(m.BankOccurrence, occurrence_id)
        if occurrence is None:
            raise ValueError(f"Who {occurrence_id} does not exist.")
    else:
        occurrence = classification_service.create_occurrence(
            session,
            canonical_name=new_occurrence_name or "",
            occurrence_type_id=occurrence_type_id or 0,
            default_transaction_reason_id=default_transaction_reason_id,
        )

    # BANK_FINAL_RELEASE_BLOCKERS_001 — approving a group names its WHO.
    # The Who's default Why is never applied to the transactions: each keeps
    # its own Why question, answered by the automatic engine or a human.

    wanted = set(payee_keys)
    candidates = [c for c in build_candidates(session) if c.group_key in wanted]
    if not candidates:
        raise ValueError("None of the selected receiver groups still exists — reload the page.")

    ambiguous = [c for c in candidates if c.status == STATUS_AMBIGUOUS]
    if ambiguous:
        raise ValueError(
            "These groups are AMBIGUOUS and must be resolved by hand first: "
            + ", ".join(c.payee_normalized for c in ambiguous)
        )

    outcome = ApprovalOutcome(
        occurrence_id=occurrence.id, occurrence_name=occurrence.canonical_name,
        transactions_classified=0, transactions_skipped_human=0,
        payees=[c.payee_normalized for c in candidates],
    )

    for candidate in candidates:
        for transaction_id in candidate.transaction_ids:
            txn = session.get(m.FinancialTransaction, transaction_id)
            if txn is None:
                continue
            current = recognition.get_current_explanation(
                session, financial_transaction_id=txn.id,
            )
            if (
                current is not None
                and current.decision_source == "HUMAN"
                and _who_decided(current)
            ):
                outcome.transactions_skipped_human += 1
                continue

            recognition.record_human_decision(
                session,
                recognition.HumanDecisionRequest(
                    transaction_id=txn.id,
                    occurrence_id=occurrence.id,
                    confirmed_by_account_id=confirmed_by_account_id,
                    # The rule is created once per group, below, rather than
                    # once per transaction: the pattern is the same for all of
                    # them and re-creating it per row is pure noise.
                    learn_description=False,
                    notes=(
                        f"Approved from the Unclassified Receivers review for payee "
                        f"{candidate.payee_normalized!r} ({candidate.transaction_count} "
                        "transaction(s) in the group)."
                    ),
                ),
            )
            outcome.transactions_classified += 1

        # A rule's stored reason is a required column that decides nothing;
        # it is filed under the Who's own default, or not learned at all.
        if learn_description and occurrence.default_transaction_reason_id is not None:
            # BANK_MEMO_PURPOSE_CLASSIFICATION_001 §10 /
            # BANK_WHO_WHY_INVARIANT_001 — approving a group together is a
            # HUMAN DECISION ABOUT THOSE TRANSACTIONS. The rule it leaves
            # behind recognises the counterparty and nothing more: "eight
            # payments to Tatiana were tips" must not become "Tatiana
            # means tips forever", because the ninth may be a
            # reimbursement or a draw. The same holds for a supplier —
            # `create_or_reuse_rule` stores every description rule
            # Who-only and refuses anything else.
            rule = recognition.create_or_reuse_rule(
                session,
                match_type=recognition.EXACT_NORMALIZED_DESCRIPTION,
                normalized_pattern=candidate.payee_normalized,
                occurrence_id=occurrence.id,
                transaction_reason_id=occurrence.default_transaction_reason_id,
                payment_instrument_id=None,
                direction=None,
                auto_apply_enabled=True,
                created_from_transaction_id=(
                    candidate.transaction_ids[0] if candidate.transaction_ids else None
                ),
            )
            outcome.rules_created.append(rule.id)

    session.flush()
    return outcome


def summary(session: Session) -> dict:
    """Counters for the Classification page header."""
    candidates = build_candidates(session)
    return {
        "groups": len(candidates),
        "unclassified_groups": len([c for c in candidates if c.status == STATUS_UNCLASSIFIED]),
        "ambiguous_groups": len([c for c in candidates if c.status == STATUS_AMBIGUOUS]),
        "assigned_groups": len([c for c in candidates if c.status == STATUS_ASSIGNED]),
        "transactions": sum(c.transaction_count for c in candidates),
        "unclassified_transactions": sum(
            c.transaction_count for c in candidates if c.status != STATUS_ASSIGNED
        ),
        "suppressed_copies": session.scalar(
            select(func.count(m.FinancialTransaction.id))
            .where(
                m.FinancialTransaction.accounting_status == accounting_dedup.DUPLICATE_SUPPRESSED
            )
        ) or 0,
    }
