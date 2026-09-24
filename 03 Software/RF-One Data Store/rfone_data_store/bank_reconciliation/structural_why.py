"""Deterministic WHY from the transaction's own structure
(BANK_HISTORICAL_DETERMINISTIC_WHY_EXPERTIZATION_001).

Answers one question — why did this financial event happen — and only where
the bank's own text, read together with RF-One's instrument registry,
proves or strongly structurally determines the purpose. It never asks who
the counterparty is: WHO alone never determines WHY. A payment to ADP, to
Amazon, to Cheney or to a person paid by Zelle says who was paid and
nothing about why.

Three outcomes:

    DETERMINISTIC      the source itself proves the purpose
                       ("FOREIGN TRANSACTION FEE", "INTEREST PAYMENT" credited
                       to a bank account, a card statement payment received
                       on the card)
    STRONG_STRUCTURAL  provider-generated structure is specific and reusable
                       enough to determine the purpose, while a separate
                       question (whose card, which related party owes whom)
                       stays with Economic Allocation
    UNRESOLVED         the evidence is not sufficient — including every case
                       where a plausible reading exists but the corpus shows
                       it can be wrong

The rules are code, versioned by `WHY_RECOGNIZER_VERSION`, and deliberately
NOT `BankRecognitionRule` rows: a recognition rule always names a WHO and,
by `ck_bank_recognition_rule_purpose_scope`, a description rule may never
decide purpose. A structural WHY rule has no WHO at all.

Each result is persisted as an ordinary canonical decision
(`BankTransactionExplanation`, decision_source RULE) through the one
function that creates decision rows, so WHAT / the Balance Sheet
destination is always derived from the WHY and never chosen here. No
allocation is created: FOR WHOM is a separate question and the payer is
never taken as the economic owner.

Families deliberately left UNRESOLVED, with the reason, are listed in
`UNRESOLVED_FAMILIES` so the refusal is visible rather than implicit.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import card_configuration, recognition
from .historical_source import instrument_last_four

WHY_RECOGNIZER_VERSION = "why-v1"
WHO_RECOGNIZER_VERSION = "who-v1"

DETERMINISTIC = "DETERMINISTIC"
STRONG_STRUCTURAL = "STRONG_STRUCTURAL"
# Purpose proven by the source MEMO / NOTE wording (a field a person writes
# to say what a payment is for), read through `purpose_evidence`'s MEMO
# rules. Consulted only when the bank structure itself proves nothing.
MEMO_EVIDENCE = "MEMO_EVIDENCE"
UNRESOLVED = "UNRESOLVED"
RESOLVED_TIERS = (DETERMINISTIC, STRONG_STRUCTURAL, MEMO_EVIDENCE)

DEBIT = "DEBIT"
CREDIT = "CREDIT"

BANK_ACCOUNT_FORMATS = frozenset({"CHASE_BANK_ACCOUNT", "FIRST_CITIZENS"})
CARD_FORMATS = frozenset({
    "CHASE_CREDIT_CARD_NO_CARD", "CHASE_CREDIT_CARD_WITH_CARD", "AMEX_QBO", "AMEX_XLSX", "AMEX_CSV",
})

_WS = re.compile(r"\s+")


def _clean(text: str | None) -> str:
    return _WS.sub(" ", (text or "")).strip().upper()


@dataclass(frozen=True)
class InstrumentInfo:
    id: int
    legal_entity_id: int | None
    instrument_type: str


@dataclass(frozen=True)
class WhyContext:
    """What the WHY recognizer may know besides the text: the source layout,
    the instrument it arrived on, and RF-One's own instrument registry.
    Never the counterparty, never history."""

    detected_format: str | None
    amount_minor: int
    instrument: InstrumentInfo
    registered_last_four: dict = field(default_factory=dict)   # last four -> InstrumentInfo
    # card id -> settlement bank account on this transaction's date
    settlement_of: Callable[[int], InstrumentInfo | None] = lambda _card_id: None

    @property
    def direction(self) -> str:
        return CREDIT if self.amount_minor > 0 else DEBIT


@dataclass(frozen=True)
class WhyResult:
    tier: str
    rule_code: str | None = None
    why_code: str | None = None
    family: str | None = None          # for UNRESOLVED: which refusal applied
    evidence: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.tier in RESOLVED_TIERS

    @property
    def confidence(self) -> str:
        return "MEDIUM" if self.tier == STRONG_STRUCTURAL else "HIGH"


@dataclass(frozen=True)
class TextRule:
    """One description structure that carries its own purpose."""

    code: str
    pattern: re.Pattern
    why_code: str
    direction: str
    formats: frozenset
    rationale: str
    tier: str = DETERMINISTIC


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


# Ordered; the first match wins. Every rule is anchored to the bank's own
# wording, restricted to a direction and to the source layouts it was
# verified on, so a similar word elsewhere cannot fire it.
TEXT_RULES: tuple[TextRule, ...] = (
    TextRule(
        "CARD_PAYMENT_RECEIVED", _rx(r"^(?:AUTOPAY PAYMENT|AUTOMATIC PAYMENT|PAYMENT|ONLINE PAYMENT|"
                                     r"MOBILE PAYMENT)\s*-?\s*THANK\b"),
        "CREDIT_CARD_SETTLEMENT", CREDIT, CARD_FORMATS,
        "The card issuer's own acknowledgement of a statement payment, received on the card: "
        "the card liability is settled.",
    ),
    TextRule(
        "FOREIGN_TRANSACTION_FEE", _rx(r"^FOREIGN TRANSACTION FEE$|^FDR DEBIT CARD VISA DEBIT FOREIGN "
                                       r"TRANSACTION FEE\b|\bFOREIGN TRAN FEE\b|^FOREIGN EXCHANGE RATE "
                                       r"ADJUSTMENT FEE\b"),
        "FOREIGN_TRANSACTION_FEE", DEBIT, BANK_ACCOUNT_FORMATS | CARD_FORMATS,
        "The issuer names the foreign transaction / exchange-rate fee itself.",
    ),
    TextRule(
        "BANK_SERVICE_CHARGE", _rx(
            r"^(?:MONTHLY SERVICE FEE|OFFICIAL CHECKS? CHARGE|OVERDRAFT CHARGE|OVERDRAFT FEE FOR A\b|"
            r"INSUFFICIENT FUNDS FEE\b|STOP PAY CHARGE|COUNTER CHECK USAGE FEE|"
            r"CALCULATED SERVICE CHARGE\b|COIN AND CURRENCY DEPOSITED FEE|ZELLE CREDIT TRANSACTION FEE|"
            r"WIRE TRANSFER FEE|ONLINE DOMESTIC WIRE FEE|ONLINE US DOLLAR INTL WIRE FEE|"
            r"CONSUMER ONLINE USD INTL WIRE FEE)"),
        "BANK_SERVICE_CHARGE", DEBIT, BANK_ACCOUNT_FORMATS,
        "A charge the bank levies on the account itself, named by the bank.",
    ),
    TextRule(
        "BANK_SERVICE_CHARGE_REFUND", _rx(r"^\S+ REFUND OF (?:MONTHLY SERVICE FEE|OVERDRAFT FEE) CHARGED\b"),
        "BANK_SERVICE_CHARGE", CREDIT, BANK_ACCOUNT_FORMATS,
        "The bank refunds a named service/overdraft fee: the same purpose, reversed.",
    ),
    TextRule(
        "INTEREST_INCOME", _rx(r"^INTEREST PAYMENT$"),
        "INTEREST_INCOME", CREDIT, BANK_ACCOUNT_FORMATS,
        "Bank-generated interest credited to a deposit account.",
    ),
    TextRule(
        "LOAN_INTEREST_PAID", _rx(r"^DEBIT MEMORANDUM REF: INTEREST PAYMENT ON LOAN\b"),
        "INTEREST_EXPENSE", DEBIT, BANK_ACCOUNT_FORMATS,
        "The bank's debit memorandum names the interest payment on a loan.",
    ),
    TextRule(
        "LOAN_ADVANCE", _rx(r"^CREDIT MEMORANDUM REF: ADVANCE ON LOAN\b"),
        "LOAN_ADVANCE", CREDIT, BANK_ACCOUNT_FORMATS,
        "The bank's credit memorandum names a loan advance: principal received, a liability.",
    ),
    TextRule(
        "MERCHANT_SERVICE_FEE", _rx(r"^FRST BK MRCH SVC (?:FEE|INTERCHNG|DISCOUNT) \*+\d+$"),
        "MERCHANT_PROCESSING_FEE", DEBIT, BANK_ACCOUNT_FORMATS,
        "The merchant-services ACH entry names the fee component (service fee, interchange, "
        "discount) it collects.",
    ),
    TextRule(
        "ISSUER_ACH_CARD_PAYMENT", _rx(
            r"^ORIG CO NAME:(?:AMERICAN EXPRESS\s+ORIG ID:.*CO ENTRY DESCR:ACH PMT\b|"
            # The entry description is a 10-character field: AUTOPAYBUS
            # fills it and runs straight into "SEC:".
            r"CHASE CREDIT CRD\s+ORIG ID:.*CO ENTRY DESCR:(?:AUTOPAYBUS|AUTOPAY|EPAY)(?=\s|SEC:))"
            r"|^AMZ_STORECRD_PMT PAYMENT\b"),
        "CREDIT_CARD_SETTLEMENT", DEBIT, BANK_ACCOUNT_FORMATS,
        "The card issuer originates the debit as a card payment. Which card — and so whose "
        "liability — the line does not say; that stays with Economic Allocation.",
        tier=STRONG_STRUCTURAL,
    ),
)

_CHASE_CARD_PAYMENT = _rx(r"^PAYMENT TO CHASE CARD ENDING IN (\d{4})\b")
_ONLINE_TRANSFER = _rx(r"^ONLINE TRANSFER (TO|FROM)\s+(?:CHK|SAV|MMA)\s*\.{2,}(\d{4})\b")

# Families examined against the corpus and deliberately NOT given a WHY in
# this version, with the reason. Matched only to label the refusal.
UNRESOLVED_FAMILIES: tuple[tuple[str, re.Pattern, str], ...] = (
    ("ADP_TAX_IMPOUND", _rx(r"ORIG CO NAME:ADP TAX\b"),
     "ADP Tax collects the whole payroll tax impound — employee withholdings as well as the "
     "employer's share — so it is not purely Employer Payroll Tax (6500). Splitting it needs the "
     "payroll register."),
    ("ADP_WAGE_PAY", _rx(r"ORIG CO NAME:ADP WAGE PAY\b"),
     "Net wages funding; role, overtime and entity split need payroll detail (Payroll not touched)."),
    ("MERCHANT_SETTLEMENT_DEPOSIT", _rx(r"^FRST BK MRCH SVC DEPOSIT\b|ORIG CO NAME:MERCHANT BANKCD\b"),
     "Card-sales settlement deposit. No clearing / undeposited-funds WHY is defined, and mapping "
     "it to revenue would double-count sales recorded from the POS."),
    ("MERCHANT_OTHER", _rx(r"^FRST BK MRCH SVC (?:CHARGEBACK|FINCL ADJ)\b|ORIG CO NAME:FDMS\b"),
     "Chargeback, adjustment, or an FDMS debit whose entry (PYMT / EQUIP) does not say fee vs "
     "equipment."),
    ("TAX_AUTHORITY", _rx(r"FLA DEPT REVENUE|IRS USATAXPYMT"),
     "The tax authority is a WHO; the code (C01, USATAXPYMT) does not prove sales vs payroll vs "
     "income tax."),
    ("FEE_UNSPECIFIED", _rx(r"^FEE REVERSAL$|^LATE FEE$|^ANNUAL MEMBERSHIP FEE$|^CHARGEBACK FEE$|"
                            r"^CHARGE BACK\b"),
     "A fee whose kind (or whose canonical account for card-issuer fees) is not established."),
    ("ZELLE", _rx(r"^ZELLE\b"),
     "The structured Chase Zelle line carries no payment note; the recipient is a WHO, not a purpose."),
    ("CHECK_OR_CASH", _rx(r"^CHECK\b|^TELLER CASHED|^ATM |^WITHDRAWAL|^DEPOSIT\b|^CUSTOMER DEPOSIT|"
                          r"^REMOTE ONLINE DEPOSIT|^PAPER BILL PAYMENT"),
     "Cheque, cash or deposit: the source names neither party nor purpose."),
    ("TRANSFER_UNKNOWN_ACCOUNT", _rx(r"^FCB (?:FUNDS )?TRANSFER|EXT TRNSFR|^FIRST CITIZENS\s+TRANSFER|"
                                     r"ORIG CO NAME:PAYPAL\b|^WIRE|^FEDWIRE|^CONSUMER ONLINE INTERNATIONAL WIRE"),
     "A transfer to or from an account RF-One has not registered (or a wallet/wire): the other "
     "side is not guessed."),
)


def _unresolved(text: str, default_family: str = "NO_STRUCTURAL_PURPOSE",
                default_reason: str = "The source text states no purpose; identity is not a purpose.") -> WhyResult:
    for family, pattern, reason in UNRESOLVED_FAMILIES:
        if pattern.search(text):
            return WhyResult(UNRESOLVED, family=family, evidence=reason)
    return WhyResult(UNRESOLVED, family=default_family, evidence=default_reason)


def recognize_why(description: str | None, ctx: WhyContext) -> WhyResult:
    """The structural WHY of one transaction, or the reason there is none.
    Pure: no database, no counterparty, no history."""
    text = _clean(description)
    if not text:
        return WhyResult(UNRESOLVED, family="EMPTY", evidence="no description")

    for rule in TEXT_RULES:
        if rule.direction == ctx.direction and ctx.detected_format in rule.formats \
                and rule.pattern.search(text):
            return WhyResult(rule.tier, rule_code=rule.code, why_code=rule.why_code,
                             evidence=f"{rule.rationale} Matched {rule.pattern.search(text).group(0)!r}.")

    if ctx.detected_format in BANK_ACCOUNT_FORMATS:
        match = _CHASE_CARD_PAYMENT.match(text)
        if match and ctx.direction == DEBIT:
            return _card_payment(match.group(1), ctx)
        match = _ONLINE_TRANSFER.match(text)
        if match:
            return _online_transfer(match.group(1).upper(), match.group(2), ctx)

    return _unresolved(text)


def _card_payment(last_four: str, ctx: WhyContext) -> WhyResult:
    card = ctx.registered_last_four.get(last_four)
    if card is None or card.instrument_type != "CREDIT_CARD":
        return WhyResult(UNRESOLVED, family="CARD_PAYMENT_UNREGISTERED_CARD",
                         evidence=f"Payment to card ··{last_four}, which is not a registered RF-One "
                                  "card (an open historical instrument candidate). Its owner, and so "
                                  "the purpose of paying it, is not decided here.")
    settlement = ctx.settlement_of(card.id)
    payer = ctx.instrument
    same_owner = settlement is not None and (
        settlement.id == payer.id
        or (settlement.legal_entity_id is not None and settlement.legal_entity_id == payer.legal_entity_id)
    )
    if not same_owner:
        return WhyResult(UNRESOLVED, family="CARD_PAYMENT_CROSS_OWNER",
                         evidence=f"Payment to registered card ··{last_four}, but the paying account is "
                                  "neither the card's settlement account nor of the same legal entity. "
                                  "Card settlement, member draw and related-party funding read the same "
                                  "on the bank line; not decided.")
    return WhyResult(DETERMINISTIC, rule_code="CARD_PAYMENT_OWN_CARD", why_code="CREDIT_CARD_SETTLEMENT",
                     evidence=f"The bank names the payment to registered card ··{last_four} (instrument "
                              f"{card.id}), settled by this account's own owner: the card liability "
                              "is settled.")


def _online_transfer(direction_word: str, last_four: str, ctx: WhyContext) -> WhyResult:
    other = ctx.registered_last_four.get(last_four)
    here = ctx.instrument
    if other is None:
        return WhyResult(UNRESOLVED, family="TRANSFER_UNKNOWN_ACCOUNT",
                         evidence=f"Transfer {direction_word.lower()} account ··{last_four}, which is not "
                                  "registered; the other side is not guessed.")
    if other.id == here.id:
        return WhyResult(UNRESOLVED, family="TRANSFER_SELF_REFERENCE",
                         evidence="The transfer names the account it appears on.")
    relation = f"between instrument {here.id} and instrument {other.id} (··{last_four})"
    if here.legal_entity_id is None or other.legal_entity_id is None:
        return WhyResult(UNRESOLVED, family="TRANSFER_PERSONAL_INSTRUMENT",
                         evidence=f"Transfer {relation}, at least one of which is a personal instrument. "
                                  "Member contribution, loan, draw or reimbursement read the same; not "
                                  "decided.")
    if here.legal_entity_id == other.legal_entity_id:
        return WhyResult(DETERMINISTIC, rule_code="ONLINE_TRANSFER_SAME_ENTITY",
                         why_code="INTERNAL_BANK_TRANSFER",
                         evidence=f"Online transfer {relation}, both registered to legal entity "
                                  f"{here.legal_entity_id}: money moved between the company's own accounts.")
    why = "RELATED_PARTY_TRANSFER_OUT" if ctx.direction == DEBIT else "RELATED_PARTY_TRANSFER_IN"
    return WhyResult(STRONG_STRUCTURAL, rule_code="ONLINE_TRANSFER_RELATED_ENTITY", why_code=why,
                     evidence=f"Online transfer {relation}; the two accounts belong to different RF-One "
                              f"legal entities ({here.legal_entity_id} and {other.legal_entity_id}). "
                              "Between two companies this is not a transfer between one company's own "
                              "accounts, so INTERNAL_BANK_TRANSFER would be wrong.")


def rule_codes() -> list[str]:
    return [rule.code for rule in TEXT_RULES] + [
        "CARD_PAYMENT_OWN_CARD", "ONLINE_TRANSFER_SAME_ENTITY", "ONLINE_TRANSFER_RELATED_ENTITY",
    ]


# --- persistence ---------------------------------------------------------------


def tag(rule_code: str) -> str:
    return f"[{WHY_RECOGNIZER_VERSION}:{rule_code}]"


@dataclass
class WhySummary:
    transactions: int = 0
    by_tier: Counter = field(default_factory=Counter)
    by_rule: Counter = field(default_factory=Counter)
    by_why: Counter = field(default_factory=Counter)
    unresolved_families: Counter = field(default_factory=Counter)
    decisions_created: int = 0
    decisions_unchanged: int = 0
    skipped_human: int = 0
    conflicts: list = field(default_factory=list)
    refused_destination: list = field(default_factory=list)


def _info(instrument: "m.PaymentInstrument | None") -> InstrumentInfo | None:
    if instrument is None:
        return None
    return InstrumentInfo(instrument.id, instrument.legal_entity_id, instrument.instrument_type)


@dataclass
class Registry:
    """RF-One's instrument registry and batch layouts, read once and reused
    for every transaction of a run."""

    instruments: dict
    registered_last_four: dict
    formats: dict


def load_registry(session: Session) -> Registry:
    instruments = {i.id: i for i in session.scalars(select(m.PaymentInstrument))}
    registered: dict[str, InstrumentInfo] = {}
    for instrument in instruments.values():
        last_four = instrument_last_four(instrument)
        if last_four:
            registered.setdefault(last_four, _info(instrument))
    formats = dict(session.execute(select(m.BankImportBatch.id, m.BankImportBatch.detected_format)).all())
    return Registry(instruments, registered, formats)


def transaction_context(session: Session, txn: "m.FinancialTransaction", registry: Registry) -> WhyContext:
    on_date: date | None = txn.posting_date or txn.transaction_date
    instruments = registry.instruments

    def settlement_of(card_id: int, _on=on_date) -> InstrumentInfo | None:
        card = instruments.get(card_id)
        if card is None:
            return None
        return _info(card_configuration.accounting_account_for(session, instrument=card, on_date=_on))

    detected_format = registry.formats.get(txn.import_batch_id)
    if detected_format is None and txn.import_batch_id is not None:
        batch = session.get(m.BankImportBatch, txn.import_batch_id)
        detected_format = batch.detected_format if batch is not None else None
    instrument = instruments.get(txn.payment_instrument_id)
    if instrument is None and txn.payment_instrument_id is not None:
        instrument = session.get(m.PaymentInstrument, txn.payment_instrument_id)
    return WhyContext(
        detected_format=detected_format, amount_minor=txn.amount_minor,
        instrument=_info(instrument), registered_last_four=registry.registered_last_four,
        settlement_of=settlement_of,
    )


def memo_why(memo: str | None) -> WhyResult | None:
    """The purpose a source MEMO proves, or None. MEMO wording only — the
    description is never searched here, so a counterparty's name can never
    become a purpose (BANK_WHO_WHY_INVARIANT_001)."""
    from . import purpose_evidence as pe
    if not (memo or "").strip():
        return None
    evidence = pe.purpose_evidence(None, memo)
    if not evidence.is_proven or evidence.source_field != pe.MEMO:
        return None
    return WhyResult(
        MEMO_EVIDENCE, rule_code=f"MEMO_{evidence.why_code}", why_code=evidence.why_code,
        evidence=f"The source memo says {evidence.matched_text!r}. {evidence.rationale or ''}".strip(),
    )


def recognize_transaction(
    session: Session, txn: "m.FinancialTransaction", registry: Registry | None = None,
) -> WhyResult:
    """THE automatic WHY of one transaction — the single engine used at
    import, on reprocess, on instrument reassignment and by the batch
    runner (BANK_FINAL_RELEASE_BLOCKERS_001).

    The bank's own structure first (`recognize_why`); only if it proves
    nothing, an explicit purpose in the source memo. Never the
    counterparty's identity, never a Who's default, never history."""
    registry = registry or load_registry(session)
    result = recognize_why(txn.description_original, transaction_context(session, txn, registry))
    if result.is_resolved:
        return result
    return memo_why(txn.source_memo) or result


def usable_reason(
    session: Session, result: WhyResult, reasons: dict | None = None,
) -> "m.BankTransactionReason | None":
    """The ACTIVE Why a resolved result names, if its destination may receive
    an automatic classification; otherwise None (the transaction then waits
    for a human rather than landing on a group or review-sensitive account)."""
    if not result.is_resolved or not result.why_code:
        return None
    if reasons is not None:
        reason = reasons.get(result.why_code)
    else:
        reason = session.scalars(
            select(m.BankTransactionReason).where(m.BankTransactionReason.code == result.why_code)
        ).first()
    if reason is None or reason.status != "ACTIVE":
        return None
    account = reason.accounting_classification
    if account is None or not account.may_receive_automatic_classification:
        return None
    return reason


def recognize_all(session: Session) -> list[tuple["m.FinancialTransaction", WhyResult]]:
    """Recognise every canonical transaction through the one engine. Reads only."""
    registry = load_registry(session)
    return [(txn, recognize_transaction(session, txn, registry))
            for txn in session.scalars(select(m.FinancialTransaction).order_by(m.FinancialTransaction.id))]


def apply_structural_why(session: Session) -> tuple[WhySummary, list]:
    """Persist every resolved WHY as a RULE decision. Idempotent.

    * never writes over a HUMAN decision;
    * a current decision already carrying this version's tag for the same
      WHY is left unchanged;
    * any other existing current decision is a conflict, reported and not
      overwritten;
    * the WHY must exist, be ACTIVE, and point at an account that may
      receive an automatic classification — otherwise it is refused;
    * the WHO recorded on the decision is only a DETERMINISTIC who-v1
      recognition, never used to decide anything;
    * no allocation is written."""
    summary = WhySummary()
    results = recognize_all(session)
    reasons = {r.code: r for r in session.scalars(select(m.BankTransactionReason))}
    who = dict(session.execute(
        select(m.BankWhoRecognition.financial_transaction_id, m.BankWhoRecognition.occurrence_id)
        .where(m.BankWhoRecognition.recognizer_version == WHO_RECOGNIZER_VERSION,
               m.BankWhoRecognition.tier == "DETERMINISTIC")
    ).all())

    for txn, result in results:
        summary.transactions += 1
        summary.by_tier[result.tier] += 1
        if not result.is_resolved:
            summary.unresolved_families[result.family] += 1
            continue
        summary.by_rule[result.rule_code] += 1
        summary.by_why[result.why_code] += 1

        reason = usable_reason(session, result, reasons)
        if reason is None:
            summary.refused_destination.append((txn.id, result.why_code))
            continue

        current = recognition.get_current_explanation(session, financial_transaction_id=txn.id)
        if current is not None:
            if current.decision_source == "HUMAN":
                summary.skipped_human += 1
            elif (current.transaction_reason_id == reason.id
                  and (current.explanation_notes or "").startswith(tag(result.rule_code))):
                summary.decisions_unchanged += 1
            else:
                summary.conflicts.append((txn.id, current.id, result.why_code))
            continue

        recognition._create_decision_row(
            session, txn,
            occurrence_id=who.get(txn.id), transaction_reason_id=reason.id, recognition_rule_id=None,
            decision_source="RULE", decision_status="AUTO_APPLIED",
            confidence=result.confidence,
            explanation_notes=(
                f"{tag(result.rule_code)} {result.tier} structural WHY {result.why_code}. "
                f"{result.evidence} The WHO (if any) is recorded for reference only and did not "
                "determine this WHY. FOR WHOM is not decided: no allocation was created."
            ),
        )
        summary.decisions_created += 1
    session.flush()
    return summary, results
