"""The structural WHY vocabulary (BANK_RESTORE_STRUCTURAL_WHY_BASELINE_001).

The canonical transaction PURPOSES RF-One itself knows: vocabulary, not
evidence — a Why existing says "RF-One understands what a sales-tax
remittance is", never "this transaction is one". Seeded by
`seed_canonical_accounting_catalog.py` (`seed_structural_reasons`).

Balance-sheet outcomes matter as much as P&L ones. A credit-card payment, a
sales-tax remittance, an internal transfer and a loan advance all reach the
bank feed looking like ordinary money movements, and each of them must
produce NO profit-and-loss effect: their accounts are on the Balance Sheet,
which keeps them out of the P&L by construction.

This module used to also hold the deterministic description matching of the
old rule system (`match`, the mixed-supplier refusals, the historical cost
type maps, `applicable_rules`, `destination_problems`). That matching was
retired with the old rule system (BANK_RULES_RESET_001,
BANK_OLD_RULES_REMOVAL_001); only the vocabulary remains. The migration that
first seeded it (`b6e1c47a20f9`) keeps its own copy of these values and does
not import this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import canonical_catalog
from . import classification as classification_service


@dataclass(frozen=True)
class StructuralWhy:
    """One structural purpose: its Why code and name, and the account it means."""

    account_code: str
    why_code: str
    why_name: str
    rationale: str
    no_pl_effect: bool = False   # True when the destination is a Balance Sheet account


# The canonical purposes that every correctly initialised Bank environment
# holds as vocabulary (Product Owner decision). "FOREIGN_TRANSACTION_FEE means
# 7230" is written here, once.
STRUCTURAL_WHYS: tuple[StructuralWhy, ...] = (
    StructuralWhy(
        account_code="7230", why_code="FOREIGN_TRANSACTION_FEE",
        why_name="Foreign transaction fee charged by the card issuer",
        rationale="The description names the fee itself; no other reading is possible.",
    ),
    StructuralWhy(
        account_code="2500", why_code="CREDIT_CARD_SETTLEMENT",
        why_name="Payment of a credit card statement",
        rationale=(
            "Settling a card balance reduces a liability. The expenses happened when the "
            "card was used, not when the statement was paid."
        ),
        no_pl_effect=True,
    ),
    StructuralWhy(
        account_code="2600", why_code="LOAN_ADVANCE",
        why_name="Loan principal advanced into the account",
        rationale=(
            "Borrowed money is a liability, never revenue. The 2600 group is used rather "
            "than 2610/2620 because the description does not say whether the term is "
            "short or long — that stays for a human."
        ),
        no_pl_effect=True,
    ),
    StructuralWhy(
        account_code="1110", why_code="INTERNAL_BANK_TRANSFER",
        why_name="Transfer between the business's own bank accounts",
        rationale=(
            "Asset to asset. Money moving between the business's own accounts is not "
            "income and not an expense."
        ),
        no_pl_effect=True,
    ),
    StructuralWhy(
        account_code="2200", why_code="SALES_TAX_REMITTANCE",
        why_name="Remittance of sales tax collected from guests",
        rationale=(
            "Sales tax is collected on the state's behalf. Collecting it is a liability "
            "and remitting it discharges that liability — neither is a P&L event."
        ),
        no_pl_effect=True,
    ),
)


def structural_why_baseline() -> tuple[StructuralWhy, ...]:
    """The five structural purposes, in their canonical order."""
    return STRUCTURAL_WHYS


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
