"""Remove Bank: drop every table that belongs exclusively to Bank (BANK_AWS_REMOVAL_001)

Revision ID: 84354dc654ce
Revises: 7b1d4f9a2c6e
Create Date: 2026-10-14

Product Owner decision (2026-10-14): Bank is removed from RF-One on AWS, as if it had never been published. Every
other Domain keeps its tables and rows.

Dropped — 53 tables, each verified on the live database before this revision was written: used only by Bank code,
referenced by no foreign key from a table that stays (checked again below, at run time):

  * every `bank_*` table (44);
  * the Bank ledger: `financial_transactions`, `raw_bank_transactions`, `financial_transaction_matches`,
    `payment_instruments`;
  * Bank's reporting/WHY structures: `reporting_entities`, `reporting_groups`, `reporting_entity_destination_aliases`,
    `purchase_line_classifications`, `supplier_item_category_learnings` (written and read only by Bank's invoice
    evidence; the WHY catalog `bank_transaction_reasons` is referenced only by these).

Deleted rows in shared tables: the `BANK` rows of `rfone_account_domain_access` and
`rfone_account_domain_item_access` (Bank access grants). Accounts, legal entities, suppliers and every other row stay.

No CASCADE anywhere: a table is dropped only after every table that references it, so an unexpected dependency makes
the revision fail instead of removing something else. The one cycle (`financial_transactions.explanation_id` ->
`bank_transaction_explanations`, both dropped) is broken first.

Not reversible: `downgrade` refuses. Recovery is the RDS snapshot taken before this revision ran.

BANK_REINSTALL_001 (2026-10-17) — guard: the revision drops only when the environment variable
`RFONE_CONFIRM_REMOVE_BANK` names it (`RFONE_CONFIRM_REMOVE_BANK=84354dc654ce`). Without it the revision is recorded
as applied and changes nothing, so a database that holds Bank data (the local working databases) keeps it on its
way to the reinstall revision `c8e4b2a6f0d1`. On RDS it already ran on 2026-10-14: the guard changes nothing there.
"""
from __future__ import annotations

import os

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '84354dc654ce'
down_revision: Union[str, Sequence[str], None] = '7b1d4f9a2c6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Referencing tables before the tables they reference (derived from the live foreign keys).
BANK_TABLES_DROP_ORDER: tuple[str, ...] = (
    "bank_ai_rule_application_items", "bank_ai_rule_batch_results", "bank_ai_rule_preview_items",
    "bank_ai_test_results", "bank_card_holder_assignments", "bank_card_settlement_accounts",
    "bank_evidence_bypass_authorizations", "bank_general_rules", "bank_historical_instrument_candidate_evidence",
    "bank_instrument_assignment_audits", "bank_instrument_identity_audits", "bank_invoice_matches",
    "bank_monthly_instrument_coverages", "bank_occurrence_aliases", "bank_occurrence_reason_associations",
    "bank_occurrence_reporting_entities", "bank_occurrence_suppliers", "bank_pattern_suggestions",
    "bank_reconciliation_control_configs", "bank_source_instrument_profiles", "bank_transaction_allocations",
    "bank_transaction_reason_export_mappings", "bank_who_recognitions", "bank_why_rules",
    "financial_transaction_matches", "purchase_line_classifications", "reporting_entity_destination_aliases",
    "bank_ai_rule_applications", "bank_ai_test_runs", "bank_historical_instrument_candidates", "bank_learning_runs",
    "bank_monthly_source_periods", "bank_transaction_explanations", "raw_bank_transactions",
    "supplier_item_category_learnings", "bank_ai_instructions", "bank_ai_rule_previews", "bank_ai_rule_versions",
    "bank_recognition_rules", "bank_reconciliation_standards", "bank_ai_rule_drafts", "bank_ai_rule_interpretations",
    "bank_occurrences", "bank_ai_rules", "bank_occurrence_types", "bank_transaction_reasons",
    "bank_accounting_classifications", "bank_reason_groups", "financial_transactions", "bank_import_batches",
    "payment_instruments", "reporting_entities", "reporting_groups",
)

BANK_DOMAIN_CODE = "BANK"


CONFIRM_VARIABLE = "RFONE_CONFIRM_REMOVE_BANK"


def upgrade() -> None:
    if os.environ.get(CONFIRM_VARIABLE) != revision:
        # Not confirmed: nothing is dropped and no access row is deleted (see the module docstring).
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    bank = set(BANK_TABLES_DROP_ORDER)

    # A table that stays must not depend on a Bank table: refuse rather than cascade.
    for table in sorted(existing - bank):
        for fk in inspector.get_foreign_keys(table):
            if fk["referred_table"] in bank:
                raise RuntimeError(
                    f"refusing to remove Bank: {table}.{fk['constrained_columns']} references {fk['referred_table']}"
                )

    # Break the one cycle between two Bank tables.
    if "financial_transactions" in existing:
        if bind.dialect.name == "sqlite":
            op.execute(sa.text("UPDATE financial_transactions SET explanation_id = NULL"))
        else:
            for fk in inspector.get_foreign_keys("financial_transactions"):
                if fk["referred_table"] == "bank_transaction_explanations" and fk.get("name"):
                    op.drop_constraint(fk["name"], "financial_transactions", type_="foreignkey")

    for access_table in ("rfone_account_domain_item_access", "rfone_account_domain_access"):
        if access_table in existing:
            op.execute(sa.text(f"DELETE FROM {access_table} WHERE domain_code = :code").bindparams(code=BANK_DOMAIN_CODE))

    for table in BANK_TABLES_DROP_ORDER:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    if "bank_transaction_explanations" in sa.inspect(op.get_bind()).get_table_names():
        return  # the Bank tables are there: the revision dropped nothing here (not confirmed), nothing to undo
    raise RuntimeError(
        "84354dc654ce removed Bank and its data; it cannot be undone by a migration. "
        "Restore the RDS snapshot taken before it ran."
    )
