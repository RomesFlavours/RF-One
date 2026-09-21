"""add hierarchical who why what bank classification

Revision ID: f1c7a94d6e02
Revises: b2f6c4a8d713
Create Date: 2026-09-20

BANK_RECONCILIATION_WHO_WHY_WHAT_001 — the hierarchical bank
classification WHO -> WHY -> WHAT, added to the EXISTING canonical Bank
models. No parallel model of an existing concept is created: WHO stays
`bank_occurrences`, WHY stays `bank_transaction_reasons`, the Kermali
export mapping stays `bank_transaction_reason_export_mappings` (entirely
untouched, still feeding Food $/Oper/Deduct exactly as before), and the
decision/audit row stays `bank_transaction_explanations`.

Schema:

  * NEW `bank_accounting_classifications` — WHAT: the final accounting
    classification, a Profit & Loss or Balance Sheet line, with a
    self-referential `parent_id` so the fixed chart of accounts can later
    be LOADED into this structure rather than requiring a schema change.
    **No chart of accounts is invented by this migration.**
  * `bank_transaction_reasons.accounting_classification_id` — WHY -> WHAT.
  * `bank_occurrences.default_transaction_reason_id` — WHO -> WHY.
  * `bank_transaction_explanations` gains the immutable WHY/WHAT snapshot
    (`transaction_reason_name_snapshot`, `accounting_classification_id`,
    `accounting_classification_code_snapshot`,
    `accounting_classification_name_snapshot`,
    `accounting_statement_type_snapshot`) and accepts the new
    `HUMAN_RECLASSIFIED` decision status.

Data (preserving, never inventing):

  1. Every distinct non-empty `what_label` already configured in
     `bank_transaction_reason_export_mappings` becomes a
     `bank_accounting_classifications` row, and the Reason(s) that used it
     are linked to it. The `what_label` values themselves are left in
     place — nothing is deleted or moved.
  2. Those migrated rows are created with `statement_type = NULL`, i.e.
     explicitly INCOMPLETE. A Kermali `what_label` does not say whether it
     is a P&L or a Balance Sheet line, and this migration does not guess.
     The Classification page shows them as incomplete; one edit each, when
     the chart of accounts is approved, completes them.
  3. `bank_occurrences.default_transaction_reason_id` is filled ONLY where
     it is genuinely determinable — a Who whose entire history (confirmed
     decisions and recognition rules) used exactly ONE Why. A Who with
     zero or several is left NULL: explicitly incomplete, never guessed.
  4. Historical decision rows that already carry a `what_label_snapshot`
     are linked to the classification migrated from that same label, and
     their code/name snapshots filled from it. Their statement-type
     snapshot stays NULL for the same reason as (2). Nothing else about a
     historical decision is touched — `occurrence_name_snapshot`,
     `food_cost_snapshot`, `operative_snapshot`, `deductible_snapshot` and
     `what_label_snapshot` keep their exact recorded values, so every
     already-exported Kermali figure stays identical.

Raw preservation (`bank_import_batches.raw_file_bytes`,
`raw_bank_transactions.raw_fields`) is not read, not written, and not
affected. No `financial_transactions` row is created, deleted or
duplicated.

Runs on SQLite and PostgreSQL. SQLite does not support altering a CHECK
constraint, so the `bank_transaction_explanations` status vocabulary is
widened by an Alembic batch table rebuild there (SQLAlchemy does not
reflect SQLite CHECK constraints, so both of that table's constraints are
re-declared explicitly); PostgreSQL drops and re-adds the one constraint
in place.

Downgrade removes only what this migration added, and REFUSES to run
while any `HUMAN_RECLASSIFIED` decision exists rather than silently
rewriting an audited human decision to fit the narrower vocabulary.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c7a94d6e02'
down_revision: Union[str, Sequence[str], None] = 'b2f6c4a8d713'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DECISION_SOURCE_CK = "ck_bank_transaction_explanation_decision_source"
_DECISION_STATUS_CK = "ck_bank_transaction_explanation_decision_status"

_DECISION_SOURCE_SQL = "decision_source IS NULL OR decision_source IN ('HUMAN', 'RULE')"
_DECISION_STATUS_SQL_NEW = (
    "decision_status IS NULL OR decision_status IN "
    "('SUGGESTED', 'AUTO_APPLIED', 'HUMAN_CONFIRMED', 'HUMAN_OVERRIDDEN', "
    "'HUMAN_RECLASSIFIED', 'NEEDS_HUMAN_REVIEW')"
)
_DECISION_STATUS_SQL_OLD = (
    "decision_status IS NULL OR decision_status IN "
    "('SUGGESTED', 'AUTO_APPLIED', 'HUMAN_CONFIRMED', 'HUMAN_OVERRIDDEN', 'NEEDS_HUMAN_REVIEW')"
)

_NEW_EXPLANATION_COLUMNS = (
    ("transaction_reason_name_snapshot", sa.String(length=255)),
    ("accounting_classification_id", sa.Integer()),
    ("accounting_classification_code_snapshot", sa.String(length=64)),
    ("accounting_classification_name_snapshot", sa.String(length=255)),
    ("accounting_statement_type_snapshot", sa.String(length=16)),
)


def _slug(label: str) -> str:
    """A stable, readable code derived from a legacy Kermali `what_label`.

    `LEGACY_` marks it as migrated evidence rather than an approved chart
    of accounts code, so the real codes can be introduced later without
    colliding with, or being confused for, these."""
    kept = [c if (c.isalnum() or c == "_") else "_" for c in label.strip().upper()]
    slug = "".join(kept)
    while "__" in slug:
        slug = slug.replace("__", "_")
    slug = slug.strip("_") or "UNLABELLED"
    return ("LEGACY_" + slug)[:64]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # --- WHAT ---------------------------------------------------------------
    op.create_table(
        "bank_accounting_classifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("statement_type", sa.String(length=16), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "statement_type IS NULL OR statement_type IN ('PROFIT_LOSS', 'BALANCE_SHEET')",
            name="ck_bank_accounting_classification_statement_type",
        ),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_bac_parent_not_self"),
        sa.ForeignKeyConstraint(["parent_id"], ["bank_accounting_classifications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_bank_accounting_classification_code"),
    )
    op.create_index(
        "ix_bank_accounting_classifications_parent_id",
        "bank_accounting_classifications", ["parent_id"], unique=False,
    )

    # --- WHY -> WHAT --------------------------------------------------------
    with op.batch_alter_table("bank_transaction_reasons", schema=None) as batch_op:
        batch_op.add_column(sa.Column("accounting_classification_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_btr_accounting_classification_id", "bank_accounting_classifications",
            ["accounting_classification_id"], ["id"],
        )
    op.create_index(
        "ix_bank_transaction_reasons_accounting_classification_id",
        "bank_transaction_reasons", ["accounting_classification_id"], unique=False,
    )

    # --- WHO -> WHY ---------------------------------------------------------
    with op.batch_alter_table("bank_occurrences", schema=None) as batch_op:
        batch_op.add_column(sa.Column("default_transaction_reason_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_bo_default_transaction_reason_id", "bank_transaction_reasons",
            ["default_transaction_reason_id"], ["id"],
        )
    op.create_index(
        "ix_bank_occurrences_default_transaction_reason_id",
        "bank_occurrences", ["default_transaction_reason_id"], unique=False,
    )

    # --- Decision snapshot + widened status vocabulary ----------------------
    if is_sqlite:
        # SQLite cannot alter a CHECK constraint, and SQLAlchemy does not
        # reflect SQLite CHECK constraints — so the batch rebuild must
        # re-declare BOTH of this table's constraints explicitly, or the
        # rebuilt table would silently lose the decision_source one too.
        with op.batch_alter_table("bank_transaction_explanations", schema=None, recreate="always") as batch_op:
            for column_name, column_type in _NEW_EXPLANATION_COLUMNS:
                batch_op.add_column(sa.Column(column_name, column_type, nullable=True))
            batch_op.create_foreign_key(
                "fk_bte_accounting_classification_id", "bank_accounting_classifications",
                ["accounting_classification_id"], ["id"],
            )
            batch_op.create_check_constraint(_DECISION_SOURCE_CK, _DECISION_SOURCE_SQL)
            batch_op.create_check_constraint(_DECISION_STATUS_CK, _DECISION_STATUS_SQL_NEW)
    else:
        for column_name, column_type in _NEW_EXPLANATION_COLUMNS:
            op.add_column(
                "bank_transaction_explanations", sa.Column(column_name, column_type, nullable=True),
            )
        op.create_foreign_key(
            "fk_bte_accounting_classification_id", "bank_transaction_explanations",
            "bank_accounting_classifications", ["accounting_classification_id"], ["id"],
        )
        op.drop_constraint(_DECISION_STATUS_CK, "bank_transaction_explanations", type_="check")
        op.create_check_constraint(
            _DECISION_STATUS_CK, "bank_transaction_explanations", _DECISION_STATUS_SQL_NEW,
        )

    _migrate_existing_data(bind)


def _migrate_existing_data(bind) -> None:
    """Preserve every existing value; fill a new reference only where it is
    genuinely determinable; leave the rest explicitly incomplete."""

    # --- 1. Legacy Kermali `what_label` -> WHAT rows ------------------------
    rows = bind.execute(sa.text(
        "SELECT bank_transaction_reason_id, what_label "
        "FROM bank_transaction_reason_export_mappings "
        "WHERE what_label IS NOT NULL AND TRIM(what_label) <> ''"
    )).fetchall()

    label_to_classification_id: dict[str, int] = {}
    used_codes: set[str] = set()
    for reason_id, what_label in rows:
        label = what_label.strip()
        if label not in label_to_classification_id:
            code = _slug(label)
            suffix = 2
            while code in used_codes:
                code = f"{_slug(label)[:60]}_{suffix}"
                suffix += 1
            used_codes.add(code)
            bind.execute(
                sa.text(
                    "INSERT INTO bank_accounting_classifications "
                    "(code, name, statement_type, parent_id, description, active) "
                    "VALUES (:code, :name, NULL, NULL, :description, 1)"
                ),
                {
                    "code": code,
                    "name": label[:255],
                    "description": (
                        "Migrated from the Kermali export label "
                        f"{label!r} (BANK_RECONCILIATION_WHO_WHY_WHAT_001). Its statement type "
                        "(Profit & Loss or Balance Sheet) was not derivable from the label and "
                        "was deliberately left unset — complete it when the chart of accounts "
                        "is approved."
                    ),
                },
            )
            label_to_classification_id[label] = bind.execute(
                sa.text("SELECT id FROM bank_accounting_classifications WHERE code = :code"),
                {"code": code},
            ).scalar_one()

        bind.execute(
            sa.text(
                "UPDATE bank_transaction_reasons SET accounting_classification_id = :cid "
                "WHERE id = :rid AND accounting_classification_id IS NULL"
            ),
            {"cid": label_to_classification_id[label], "rid": reason_id},
        )

    # --- 2. WHO -> WHY, only where a single Why is the whole history --------
    # Evidence considered: the Why of every decision that actually recorded
    # one, plus the Why of every recognition rule for that Who. Exactly one
    # distinct value across both is determinable; anything else is not.
    determinable = bind.execute(sa.text(
        "SELECT occurrence_id, MIN(transaction_reason_id) AS only_reason_id "
        "FROM ("
        "  SELECT occurrence_id, transaction_reason_id FROM bank_transaction_explanations "
        "   WHERE occurrence_id IS NOT NULL AND transaction_reason_id IS NOT NULL "
        "  UNION "
        "  SELECT occurrence_id, transaction_reason_id FROM bank_recognition_rules "
        "   WHERE occurrence_id IS NOT NULL AND transaction_reason_id IS NOT NULL "
        ") AS evidence "
        "GROUP BY occurrence_id "
        "HAVING COUNT(DISTINCT transaction_reason_id) = 1"
    )).fetchall()
    for occurrence_id, reason_id in determinable:
        bind.execute(
            sa.text(
                "UPDATE bank_occurrences SET default_transaction_reason_id = :rid "
                "WHERE id = :oid AND default_transaction_reason_id IS NULL"
            ),
            {"rid": reason_id, "oid": occurrence_id},
        )

    # --- 3. Historical decision snapshots -----------------------------------
    # The WHY name a decision recorded is its Reason's name; a Reason's name
    # is not versioned, so this is the only value that ever existed for it.
    bind.execute(sa.text(
        "UPDATE bank_transaction_explanations SET transaction_reason_name_snapshot = ("
        "  SELECT name FROM bank_transaction_reasons "
        "   WHERE bank_transaction_reasons.id = bank_transaction_explanations.transaction_reason_id"
        ") WHERE transaction_reason_id IS NOT NULL AND transaction_reason_name_snapshot IS NULL"
    ))

    # A decision that recorded a Kermali `what_label` is linked to the WHAT
    # migrated from that same label — the snapshot's own recorded value, not
    # a re-read of today's configuration. Statement type stays NULL: it was
    # never part of what that decision recorded.
    for label, classification_id in label_to_classification_id.items():
        bind.execute(
            sa.text(
                "UPDATE bank_transaction_explanations SET "
                "  accounting_classification_id = :cid, "
                "  accounting_classification_code_snapshot = ("
                "    SELECT code FROM bank_accounting_classifications WHERE id = :cid), "
                "  accounting_classification_name_snapshot = :label "
                "WHERE TRIM(what_label_snapshot) = :label "
                "  AND accounting_classification_id IS NULL"
            ),
            {"cid": classification_id, "label": label},
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    reclassified = bind.execute(sa.text(
        "SELECT COUNT(*) FROM bank_transaction_explanations "
        "WHERE decision_status = 'HUMAN_RECLASSIFIED'"
    )).scalar_one()
    if reclassified:
        raise RuntimeError(
            f"Refusing to downgrade: {reclassified} audited HUMAN_RECLASSIFIED decision(s) exist. "
            "The narrower pre-migration status vocabulary cannot represent them, and rewriting a "
            "recorded human decision to fit it would destroy audit history. Resolve these rows "
            "deliberately before downgrading."
        )

    # Historical Kermali values (`occurrence_name_snapshot`, `food_cost_snapshot`,
    # `operative_snapshot`, `deductible_snapshot`, `what_label_snapshot`) are
    # pre-existing columns and are NOT touched here — every already-exported
    # figure survives the downgrade unchanged.
    if is_sqlite:
        with op.batch_alter_table("bank_transaction_explanations", schema=None, recreate="always") as batch_op:
            for column_name, _ in reversed(_NEW_EXPLANATION_COLUMNS):
                batch_op.drop_column(column_name)
            batch_op.create_check_constraint(_DECISION_SOURCE_CK, _DECISION_SOURCE_SQL)
            batch_op.create_check_constraint(_DECISION_STATUS_CK, _DECISION_STATUS_SQL_OLD)
    else:
        op.drop_constraint(_DECISION_STATUS_CK, "bank_transaction_explanations", type_="check")
        op.drop_constraint("fk_bte_accounting_classification_id", "bank_transaction_explanations", type_="foreignkey")
        for column_name, _ in reversed(_NEW_EXPLANATION_COLUMNS):
            op.drop_column("bank_transaction_explanations", column_name)
        op.create_check_constraint(
            _DECISION_STATUS_CK, "bank_transaction_explanations", _DECISION_STATUS_SQL_OLD,
        )

    op.drop_index("ix_bank_occurrences_default_transaction_reason_id", table_name="bank_occurrences")
    with op.batch_alter_table("bank_occurrences", schema=None) as batch_op:
        batch_op.drop_constraint("fk_bo_default_transaction_reason_id", type_="foreignkey")
        batch_op.drop_column("default_transaction_reason_id")

    op.drop_index(
        "ix_bank_transaction_reasons_accounting_classification_id", table_name="bank_transaction_reasons",
    )
    with op.batch_alter_table("bank_transaction_reasons", schema=None) as batch_op:
        batch_op.drop_constraint("fk_btr_accounting_classification_id", type_="foreignkey")
        batch_op.drop_column("accounting_classification_id")

    op.drop_index(
        "ix_bank_accounting_classifications_parent_id", table_name="bank_accounting_classifications",
    )
    op.drop_table("bank_accounting_classifications")
