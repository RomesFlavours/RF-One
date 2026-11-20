"""Deterministic accounting recognition
(BANK_CANONICAL_ACCOUNTING_CATALOG_001).

A small, explicit, auditable set of rules that map a normalized bank
description to a canonical account — and, just as importantly, the list of
things that must NOT be decided automatically.

The governing principle: a rule exists here only when the description
itself carries the accounting meaning. `FOREIGN TRANSACTION FEE` is a fee
whatever else is true of the transaction. `COSTCO` is a shop that sells
food, cleaning supplies, equipment and office paper, so a Costco payment
says who was paid and nothing about what was bought.

Three classes of thing are deliberately absent:

* **mixed suppliers** (Costco, Sam's Club, Instacart, Amazon, Publix,
  Cheney Brothers, Prime Line, …) — these need the invoice, or an explicit
  human rule, and are refused here by name so nobody adds them casually;
* **anything resolved only by history** — that a vendor was usually
  classified one way in a spreadsheet is evidence for a human, not a rule;
* **"I don't know"** — an unrecognised description is REVIEW_REQUIRED.
  Miscellaneous (7880), Other Personnel (6900) and the two Other
  Non-Operating accounts exist for genuine residual cases and are never an
  automatic fallback. Since
  BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 that is not a convention a
  contributor has to remember: those accounts carry
  `review_sensitive = True` in the catalog, `applicable_rules` drops any
  rule pointing at one, and `destination_problems` fails loudly if a rule
  is ever added that does. The same guard drops a rule aimed at a GROUP,
  which is a reporting node and never a destination.

This module also owns the STRUCTURAL WHY BASELINE
(BANK_RESTORE_STRUCTURAL_WHY_BASELINE_001): the canonical transaction
PURPOSES RF-One itself knows how to recognise. They are vocabulary, not
evidence — a Why existing says "RF-One understands what a sales-tax
remittance is", never "this transaction is one". The interpreter still has
to prove the purpose from the transaction's own text before any What
resolves, and WHO remains entirely independent of both.

Balance-sheet outcomes matter as much as P&L ones. A credit-card payment,
a sales-tax remittance, a tip settlement, an internal transfer and a loan
advance all reach the bank feed looking like ordinary money movements, and
each of them must produce NO profit-and-loss effect. Those are encoded
here as accounts on the Balance Sheet, which is what keeps them out of the
P&L by construction rather than by a rule somewhere downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import canonical_catalog
from . import classification as classification_service

REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class DeterministicRule:
    """One description pattern that carries its own accounting meaning."""

    pattern: str                 # regex, matched against the normalized payee
    account_code: str
    why_code: str
    why_name: str
    rationale: str
    no_pl_effect: bool = False   # True when the destination is a Balance Sheet account


# Suppliers that sell across several cost families. Listed explicitly so a
# future contributor sees the refusal rather than inferring it. A payment to
# any of these is WHO-only until an invoice says what was bought.
MIXED_SUPPLIER_PATTERNS = (
    r"\bCOSTCO\b", r"\bSAM ?S? CLUB\b", r"\bINSTACART\b", r"\bIC \b", r"\bAMAZON\b",
    r"\bAMZN\b", r"\bPUBLIX\b", r"\bCHENEY\b", r"\bPRIME ?LINE\b", r"\bWALMART\b",
    r"\bTARGET\b", r"\bRESTAURANT DEPOT\b", r"\bWALGREENS\b", r"\bCVS\b",
)

# --- The rules ------------------------------------------------------------
#
# Ordered: the first match wins, so the more specific pattern comes first.

DETERMINISTIC_RULES: tuple[DeterministicRule, ...] = (
    # ---- Financial & payment costs (P&L) --------------------------------
    DeterministicRule(
        pattern=r"\bFOREIGN (TRANSACTION|PURCHASE) FEE\b",
        account_code="7230", why_code="FOREIGN_TRANSACTION_FEE",
        why_name="Foreign transaction fee charged by the card issuer",
        rationale="The description names the fee itself; no other reading is possible.",
    ),
    DeterministicRule(
        pattern=r"\b(MONTHLY SERVICE FEE|SERVICE CHARGE|MAINTENANCE FEE|"
                r"OVERDRAFT FEE|RETURNED ITEM FEE|WIRE FEE|STOP PAYMENT FEE)\b",
        account_code="7220", why_code="BANK_SERVICE_CHARGE",
        why_name="Bank account service charge",
        rationale="A charge levied by the bank on the account itself.",
    ),
    DeterministicRule(
        pattern=r"\b(MERCHANT (ACCOUNT )?FEE|CARD PROCESSING|INTERCHANGE|"
                r"DISCOUNT FEE MERCH|MERCH(ANT)? DISCOUNT)\b",
        account_code="7210", why_code="MERCHANT_PROCESSING_FEE",
        why_name="Card acquiring / merchant processing fee",
        rationale=(
            "A merchant acquiring fee. Operating expense, never COGS, whatever the "
            "processor is called."
        ),
    ),
    DeterministicRule(
        pattern=r"\bINTEREST (EARNED|PAID TO YOU|CREDIT)\b|\bCREDIT INTEREST\b",
        account_code="8100", why_code="INTEREST_INCOME",
        why_name="Interest credited by the bank",
        rationale="Interest received. Non-operating income, never restaurant revenue.",
    ),
    # ---- Balance-sheet movements: NO P&L effect -------------------------
    DeterministicRule(
        pattern=r"\b(ONLINE|INTERNAL|BOOK) TRANSFER (TO|FROM)\b|\bTRANSFER (TO|FROM) (CHK|SAV)\b",
        account_code="1110", why_code="INTERNAL_BANK_TRANSFER",
        why_name="Transfer between the business's own bank accounts",
        rationale=(
            "Asset to asset. Money moving between the business's own accounts is not "
            "income and not an expense."
        ),
        no_pl_effect=True,
    ),
    DeterministicRule(
        pattern=r"\b(PAYMENT THANK YOU|AUTOMATIC PAYMENT THANK|"
                r"CARDMEMBER (SERV|PAYMENT)|CHASE CREDIT CRD (AUTOPAY|EPAY)|"
                r"AMEX EPAYMENT)\b",
        account_code="2500", why_code="CREDIT_CARD_SETTLEMENT",
        why_name="Payment of a credit card statement",
        rationale=(
            "Settling a card balance reduces a liability. The expenses happened when the "
            "card was used, not when the statement was paid."
        ),
        no_pl_effect=True,
    ),
    DeterministicRule(
        pattern=r"\b(SALES ?TAX|DEPT OF REVENUE|DEPARTMENT OF REVENUE|"
                r"FL ?DOR|DOR ?E?SALESTAX)\b",
        account_code="2200", why_code="SALES_TAX_REMITTANCE",
        why_name="Remittance of sales tax collected from guests",
        rationale=(
            "Sales tax is collected on the state's behalf. Collecting it is a liability "
            "and remitting it discharges that liability — neither is a P&L event."
        ),
        no_pl_effect=True,
    ),
    DeterministicRule(
        pattern=r"\b(CREDIT MEMORANDUM.*ADVANCE ON LOAN|ADVANCE ON LOAN|LOAN ADVANCE|"
                r"LOAN PROCEEDS|LOAN DISBURSEMENT)\b",
        account_code="2600", why_code="LOAN_ADVANCE",
        why_name="Loan principal advanced into the account",
        rationale=(
            "Borrowed money is a liability, never revenue. The 2600 group is used rather "
            "than 2610/2620 because the description does not say whether the term is "
            "short or long — that stays for a human."
        ),
        no_pl_effect=True,
    ),
)

# Historical Kermali cost types that map deterministically onto the canonical
# chart. `RfBank.xlsx` is evidence, not truth: a mapping appears here only
# where the historical label means exactly one canonical account.
HISTORICAL_COST_TYPE_MAP = {
    "Accountant": "7610",
    "Bank Costs": "7220",
    "Card Fees": "7210",
    "Legal": "7620",
    "Licences": "7740",
    "Marketing": "7500",
    "Products-Food": "5100",
    "Products-Wine": "5230",
    "Products-Beer": "5220",
    "Products-Drinks": "5210",
    "Sales Tax": "2200",
    "Tips": "2300",
    "Bank Transfer": "1110",
    "Payroll - Tax": "6500",
    "Payroll - Management": "6310",
    "Work Compensation": "6700",
    "General Liability": "7710",
    "Web/Phone": "7450",
    "Register Costs": "7850",
    "New Appliances": "1520",
    "UR-Recruiting/Training": "7860",
}

# Historical cost types that are NOT deterministic, with the reason. Reported
# for human review rather than guessed.
HISTORICAL_UNRESOLVED = {
    "Company Cars": "does not say lease, fuel, insurance, repair or capital purchase",
    "Incoming": "says money arrived, not what it was — revenue, loan, transfer or refund",
    "Incoming RFG": "same, and the counterparty is a related entity whose nature must be confirmed",
    "Personal Deductable": "asserts a tax treatment RF-One must not invent",
    "Personal - Food": "personal spending has no restaurant account; owner-draw treatment is a decision",
    "Personal - Healt": "same",
    "Personal - Restaurant": "same",
    "Personal - Tax": "same",
    "Personal Various": "same",
    "Da Verificare": "explicitly 'to be verified' in the source itself",
    "Payroll - FOH": "the 6100 family is right, but regular vs overtime needs payroll detail",
    "Payroll - BOH": "the 6200 family is right, but regular vs overtime needs payroll detail",
    "Emploees -Extra Cost": "could be bonus, benefit, temporary labour or reimbursement",
    "Products-Supports": "'supports' spans direct consumables and ordinary operating supplies",
    "Products-Pers": "ambiguous between personal and personnel",
    "Maintenance": "equipment or building maintenance are different accounts",
    "Improving": "capital improvement or repair changes the statement side entirely",
    "Remodeling": "same",
    "Mount Dora Start up": "a project, not an account — its costs span several",
    "RF Gelati": "a related entity or a product line; needs confirmation",
    "Home": "no restaurant account; likely owner draw, which is a decision",
    "Scouting": "travel, meals or consulting depending on what was actually done",
    "Lease Central st": "premises lease or equipment lease is not stated",
    "Lease Morse": "same",
    "Lease Storage": "same",
    "Utility Morse/Central": "which utility is not stated",
    "Company Tax": "income tax, property tax and licence fees are different accounts",
    "Payroll - BOH ": "the 6200 family is right, but regular vs overtime needs payroll detail",
}


# The canonical purposes that every correctly initialised Bank environment
# holds as vocabulary (BANK_RESTORE_STRUCTURAL_WHY_BASELINE_001, Product
# Owner decision). Listed BY CODE only: the name and the account come from
# the `DeterministicRule` above, so "FOREIGN_TRANSACTION_FEE means 7230" is
# written in exactly one place and a code/account mismatch cannot be
# introduced by editing one of two copies.
#
# Deliberately a SUBSET of the rules in this module. The purposes this
# interpreter can also produce but which are NOT structural baseline —
# BANK_SERVICE_CHARGE, MERCHANT_PROCESSING_FEE, INTEREST_INCOME here, and
# TIPS_SETTLEMENT, CONTRACT_LABOR, PAYABLE_SETTLEMENT, MEMBER_DRAW,
# BASE_RENT in `purpose_evidence` — have no Why row until a human creates
# one, which means a transaction proving one of those purposes reaches a
# human instead of classifying itself. That is a real gap, reported rather
# than closed unilaterally: widening the baseline is a Product Owner
# decision about accounting vocabulary, not a refactor.
STRUCTURAL_WHY_CODES: tuple[str, ...] = (
    "FOREIGN_TRANSACTION_FEE",
    "CREDIT_CARD_SETTLEMENT",
    "LOAN_ADVANCE",
    "INTERNAL_BANK_TRANSFER",
    "SALES_TAX_REMITTANCE",
)


def structural_why_baseline() -> tuple[DeterministicRule, ...]:
    """The five structural purposes, resolved from the rules above.

    Raises if a code in `STRUCTURAL_WHY_CODES` names no rule — the two must
    not drift apart silently."""
    by_code = {rule.why_code: rule for rule in DETERMINISTIC_RULES}
    missing = [code for code in STRUCTURAL_WHY_CODES if code not in by_code]
    if missing:
        raise ValueError(
            "The structural Why baseline names purposes no deterministic rule defines: "
            + ", ".join(missing)
            + ". The baseline and the rules are one vocabulary and must stay together."
        )
    return tuple(by_code[code] for code in STRUCTURAL_WHY_CODES)


@dataclass
class StructuralWhyOutcome:
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def seed_structural_reasons(session: Session, *, strict: bool = True) -> StructuralWhyOutcome:
    """Install the structural Why vocabulary. Idempotent.

    A second run creates nothing: a code already present and pointing at the
    account this module says it means is counted as unchanged. A code
    present pointing SOMEWHERE ELSE is a conflict — raised with `strict`
    (the default) rather than repointed, because a Why is what historical
    decisions resolved their What through, and silently moving it would
    rewrite what those decisions meant.

    Creates VOCABULARY ONLY. No Who, no rule, no transaction, no decision:
    that a purpose is understood is not evidence that any transaction has
    it."""
    outcome = StructuralWhyOutcome()
    existing = {
        reason.code: reason
        for reason in session.scalars(select(m.BankTransactionReason)).all()
    }

    for rule in structural_why_baseline():
        account = canonical_catalog.by_code(session, rule.account_code)
        if account is None:
            outcome.conflicts.append(
                f"{rule.why_code}: account {rule.account_code} does not exist in this "
                "database — seed the canonical catalog first."
            )
            continue

        current = existing.get(rule.why_code)
        if current is not None:
            held = (
                canonical_catalog.by_code(session, rule.account_code)
                if current.accounting_classification_id == account.id else None
            )
            if held is not None:
                outcome.unchanged.append(rule.why_code)
            else:
                pointed_at = session.get(
                    m.BankAccountingClassification, current.accounting_classification_id,
                )
                outcome.conflicts.append(
                    f"{rule.why_code}: already exists pointing at "
                    f"{pointed_at.code if pointed_at else 'nothing'}, this module says "
                    f"{rule.account_code}. Not repointed."
                )
            continue

        classification_service.create_transaction_reason(
            session, code=rule.why_code, name=rule.why_name,
            accounting_classification_id=account.id,
            description=(
                f"Structural Bank vocabulary. {rule.rationale} "
                "Vocabulary only: a transaction reaches this Why when its own evidence "
                "proves the purpose, never because of who was paid."
            ),
        )
        outcome.created.append(rule.why_code)

    session.flush()
    if strict and outcome.conflicts:
        raise ValueError(
            "The structural Why baseline conflicts with what is already in this database, "
            "and nothing was repointed. Resolve these by hand: "
            + "; ".join(outcome.conflicts)
        )
    return outcome


@dataclass
class RuleMatch:
    rule: DeterministicRule
    account_code: str


def match(payee_normalized: str) -> RuleMatch | None:
    """The deterministic rule for this description, or None.

    Returns None — meaning REVIEW_REQUIRED — for anything not explicitly
    recognised, including every mixed supplier. That is the point: an
    unrecognised description must reach a human, never Miscellaneous."""
    text = (payee_normalized or "").upper()
    if not text:
        return None
    if is_mixed_supplier(text):
        return None
    for rule in DETERMINISTIC_RULES:
        if re.search(rule.pattern, text):
            return RuleMatch(rule=rule, account_code=rule.account_code)
    return None


def is_mixed_supplier(payee_normalized: str) -> bool:
    """Whether this description names a supplier that sells across cost
    families. Such a payment is never classified from the bank line alone —
    the invoice carries the composition."""
    text = (payee_normalized or "").upper()
    return any(re.search(pattern, text) for pattern in MIXED_SUPPLIER_PATTERNS)


def applicable_rules(session: Session) -> list[DeterministicRule]:
    """The rules whose destination account exists in this database AND may
    legitimately receive an automatic classification.

    A rule pointing at a missing account is skipped rather than failing the
    run, so a partially seeded catalog degrades to review instead of error.
    A rule pointing at a GROUP or at a review-sensitive account is skipped
    for a different reason: landing there automatically is precisely what
    the catalog forbids, and degrading to REVIEW_REQUIRED is the correct
    outcome. `destination_problems` reports such a rule so it is fixed
    rather than silently ignored."""
    return [
        rule for rule in DETERMINISTIC_RULES
        if canonical_catalog.may_receive_automatic_classification(
            canonical_catalog.by_code(session, rule.account_code)
        )
    ]


def destination_problems(session: Session) -> list[str]:
    """Every deterministic rule whose destination this catalog refuses as an
    automatic classification. An empty list means the rule set is safe.

    Checked against the stored catalog rather than a list of codes kept
    here, so marking an account review-sensitive is enough to make every
    rule aimed at it fail this check."""
    problems: list[str] = []
    for rule in DETERMINISTIC_RULES:
        account = canonical_catalog.by_code(session, rule.account_code)
        if account is None:
            continue  # a partially seeded catalog is not a rule defect
        if not account.is_posting_account:
            problems.append(
                f"{rule.why_code}: points at {account.code} {account.name!r}, which is a "
                f"{account.node_type} and is never an automatic destination."
            )
        if account.review_sensitive:
            problems.append(
                f"{rule.why_code}: points at {account.code} {account.name!r}, which is "
                "review-sensitive and must never be reached automatically."
            )
    return problems
