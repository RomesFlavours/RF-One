"""seed the structural Why vocabulary

Revision ID: b6e1c47a20f9
Revises: a3d7f60b9e15
Create Date: 2026-09-21

BANK_RESTORE_STRUCTURAL_WHY_BASELINE_001 — a DATA migration only. No table
is created, altered or dropped, and the schema is byte-identical before and
after.

Why a migration

Five transaction PURPOSES are structural Bank vocabulary: RF-One knows
what a foreign transaction fee, a card settlement, a loan advance, an
internal transfer and a sales-tax remittance ARE. Until now those rows
only ever appeared as a side effect of running
`apply_deterministic_bank_classification.py` over already-imported
transactions, which made the vocabulary depend on having data — so a fresh
environment could not resolve a proven purpose to an account until someone
had imported something and run a script. That is backwards: vocabulary
comes before evidence.

After this revision an ordinary `alembic upgrade head` leaves every
environment, including AWS, holding the five purposes with no manual step.

Vocabulary is not evidence

Seeding a Why does NOT classify anything. It says the purpose is
understood, never that a transaction has it. The interpreter must still
prove the purpose from the transaction's own text
(`purpose_evidence` / the deterministic description rules), and WHO stays
completely independent of both — a counterparty's identity resolves no
Why, which is BANK_WHO_WHY_INVARIANT_001 and is untouched here.

Accordingly this revision creates VOCABULARY ONLY:

  * no BankOccurrence (WHO);
  * no BankRecognitionRule;
  * no FinancialTransaction, raw row, explanation or human decision;
  * no `created_from_transaction_id` anywhere.

The five rows, frozen

Carried INLINE (`_STRUCTURAL_REASONS`) rather than read from
`deterministic_rules`, for the reason BANK_CANONICAL_MIGRATION_IMMUTABILITY_001
established: a shipped migration must not change behaviour when a live
module is edited later. `deterministic_rules.structural_why_baseline()`
remains the authoritative CURRENT definition that the runtime seed and the
tests read; this is the frozen copy of what it said when the revision was
written. The two are checked against each other by
`test_bank_structural_why_baseline.py`, so drift is caught by a failing
test rather than by a silent divergence.

Idempotent and non-destructive:

  * a code already present and pointing at the same account is left
    untouched;
  * a code present pointing SOMEWHERE ELSE RAISES — a Why is what
    historical decisions resolved their What through, and repointing one
    would rewrite what those decisions meant;
  * an account this revision names that does not exist RAISES, rather than
    creating a Why with no What.

Downgrade removes the five rows, and only while they are still unused: a
Why referenced by a Who, a rule or a decision is kept, because removing it
would break records that point at it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6e1c47a20f9'
down_revision: Union[str, Sequence[str], None] = 'a3d7f60b9e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REASONS = "bank_transaction_reasons"
ACCOUNTS = "bank_accounting_classifications"

# code -> (name, account code, description)
_STRUCTURAL_REASONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "FOREIGN_TRANSACTION_FEE", "Foreign transaction fee charged by the card issuer",
        "7230",
        "Structural Bank vocabulary. The description names the fee itself; no other reading "
        "is possible.",
    ),
    (
        "CREDIT_CARD_SETTLEMENT", "Payment of a credit card statement", "2500",
        "Structural Bank vocabulary. Paying the card statement settles the card liability; "
        "the purchases it covers were already recorded when they were made.",
    ),
    (
        "LOAN_ADVANCE", "Loan principal advanced into the account", "2600",
        "Structural Bank vocabulary. Loan principal received is a liability, never revenue.",
    ),
    (
        "INTERNAL_BANK_TRANSFER", "Transfer between the business's own bank accounts", "1110",
        "Structural Bank vocabulary. Money moved between the company's own accounts changes "
        "no economic position and has no profit-and-loss effect.",
    ),
    (
        "SALES_TAX_REMITTANCE", "Remittance of sales tax collected from guests", "2200",
        "Structural Bank vocabulary. Sales tax collected from guests is a liability; "
        "remitting it settles that liability and is never an expense.",
    ),
)

_NOTE = (
    " Vocabulary only: a transaction reaches this Why when its own evidence proves the "
    "purpose, never because of who was paid. Seeded by migration b6e1c47a20f9."
)


def upgrade() -> None:
    """Create the five structural purposes. Creates no Who, rule or transaction."""
    bind = op.get_bind()

    accounts = {
        code: identifier
        for code, identifier in bind.execute(
            sa.text(f"SELECT code, id FROM {ACCOUNTS}")
        ).fetchall()
    }
    existing = {
        code: (identifier, classification_id)
        for code, identifier, classification_id in bind.execute(
            sa.text(f"SELECT code, id, accounting_classification_id FROM {REASONS}")
        ).fetchall()
    }
    by_id = {identifier: code for code, identifier in accounts.items()}

    missing_accounts = [
        account_code for _, _, account_code, _ in _STRUCTURAL_REASONS
        if account_code not in accounts
    ]
    if missing_accounts:
        raise RuntimeError(
            "Refusing to seed the structural Why vocabulary: these canonical accounts do not "
            "exist in this database, so the purposes would have no What — "
            + ", ".join(sorted(set(missing_accounts)))
            + ". Run the canonical catalog migrations first."
        )

    conflicts = [
        f"{code}: already exists pointing at {by_id.get(existing[code][1], 'nothing')!r}, "
        f"this revision says {account_code!r}"
        for code, _, account_code, _ in _STRUCTURAL_REASONS
        if code in existing and existing[code][1] != accounts[account_code]
    ]
    if conflicts:
        raise RuntimeError(
            "Refusing to seed the structural Why vocabulary: these codes already mean "
            "something else, and a Why that historical decisions resolved their What through "
            "is never silently repointed. Resolve them by hand, then re-run the migration. "
            + "; ".join(conflicts)
        )

    created = 0
    for code, name, account_code, description in _STRUCTURAL_REASONS:
        if code in existing:
            continue
        bind.execute(
            sa.text(
                f"INSERT INTO {REASONS} "
                "(code, name, accounting_classification_id, description, status) "
                "VALUES (:code, :name, :classification_id, :description, 'ACTIVE')"
            ),
            {
                "code": code, "name": name,
                "classification_id": accounts[account_code],
                "description": description + _NOTE,
            },
        )
        created += 1

    print(
        f"[b6e1c47a20f9] structural Why vocabulary: {created} created, "
        f"{len(_STRUCTURAL_REASONS) - created} already present. "
        "No Who, rule, transaction or decision was created."
    )


def downgrade() -> None:
    """Remove the five rows, and only while nothing references them."""
    bind = op.get_bind()

    referenced: set[int] = set()
    for statement in (
        "SELECT DISTINCT default_transaction_reason_id FROM bank_occurrences "
        "WHERE default_transaction_reason_id IS NOT NULL",
        "SELECT DISTINCT transaction_reason_id FROM bank_recognition_rules",
        "SELECT DISTINCT transaction_reason_id FROM bank_transaction_explanations "
        "WHERE transaction_reason_id IS NOT NULL",
        "SELECT DISTINCT bank_transaction_reason_id FROM bank_transaction_reason_export_mappings",
    ):
        referenced.update(row[0] for row in bind.execute(sa.text(statement)).fetchall())

    for code, _, _, _ in _STRUCTURAL_REASONS:
        row = bind.execute(
            sa.text(f"SELECT id FROM {REASONS} WHERE code = :code"), {"code": code},
        ).fetchone()
        if row is None or row[0] in referenced:
            continue  # absent, or in use — left alone
        bind.execute(sa.text(f"DELETE FROM {REASONS} WHERE id = :id"), {"id": row[0]})
