"""Single Bank engine (Bank unification Phase 3A, BANK_UNIFICATION_PHASE3_PLAN_001). Additive.

* `bank_engine_runs` / `bank_engine_results`: the runs of the one reconciliation engine and, per run, the
  result of every movement (status, exceptions, per-field method and trace). They never replace a decision:
  explanations stay the record of human decisions.
* `financial_transaction_matches` also holds the engine's matched transfers and card settlements: new
  match types and method ENGINE, the relationship between the owners, the leg that is posted, and the
  engine runs that first/last saw the pair.
"""
from alembic import op
import sqlalchemy as sa

revision = "e3a120261024"
down_revision = "c7a120261021"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "bank_engine_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("scope_json", sa.Text, nullable=False),
        sa.Column("summary_json", sa.Text, nullable=True),
        sa.Column("origin", sa.String(16), nullable=False, server_default="ENGINE"),
        sa.Column("origin_run_id", sa.Integer, nullable=True),
        sa.UniqueConstraint("origin", "origin_run_id", name="uq_bank_engine_run_origin"),
    )
    op.create_table(
        "bank_engine_results",
        sa.Column("run_id", sa.Integer, sa.ForeignKey("bank_engine_runs.id"), primary_key=True),
        sa.Column("financial_transaction_id", sa.Integer, sa.ForeignKey("financial_transactions.id"),
                  primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
    )
    op.create_index("ix_bank_engine_results_transaction", "bank_engine_results", ["financial_transaction_id"])
    with op.batch_alter_table("financial_transaction_matches", recreate="always") as batch:
        batch.drop_constraint("ck_ftm_match_type", type_="check")
        batch.drop_constraint("ck_ftm_match_method", type_="check")
        batch.add_column(sa.Column("relationship", sa.String(16), nullable=True))
        batch.add_column(sa.Column("posting_transaction_id", sa.Integer, nullable=True))
        batch.add_column(sa.Column("first_engine_run_id", sa.Integer, nullable=True))
        batch.add_column(sa.Column("last_engine_run_id", sa.Integer, nullable=True))
        batch.create_check_constraint(
            "ck_ftm_match_type", "match_type IN ('INTERNAL_TRANSFER', 'TRANSFER', 'CARD_SETTLEMENT')")
        batch.create_check_constraint("ck_ftm_match_method", "match_method IN ('AUTO', 'HUMAN', 'ENGINE')")
        batch.create_foreign_key("fk_ftm_posting_transaction", "financial_transactions",
                                 ["posting_transaction_id"], ["id"])
        batch.create_foreign_key("fk_ftm_first_engine_run", "bank_engine_runs", ["first_engine_run_id"], ["id"])
        batch.create_foreign_key("fk_ftm_last_engine_run", "bank_engine_runs", ["last_engine_run_id"], ["id"])


def downgrade():
    op.execute("DELETE FROM financial_transaction_matches WHERE match_method = 'ENGINE'")
    with op.batch_alter_table("financial_transaction_matches", recreate="always") as batch:
        batch.drop_constraint("fk_ftm_last_engine_run", type_="foreignkey")
        batch.drop_constraint("fk_ftm_first_engine_run", type_="foreignkey")
        batch.drop_constraint("fk_ftm_posting_transaction", type_="foreignkey")
        batch.drop_constraint("ck_ftm_match_type", type_="check")
        batch.drop_constraint("ck_ftm_match_method", type_="check")
        batch.drop_column("last_engine_run_id")
        batch.drop_column("first_engine_run_id")
        batch.drop_column("posting_transaction_id")
        batch.drop_column("relationship")
        batch.create_check_constraint("ck_ftm_match_type", "match_type IN ('INTERNAL_TRANSFER')")
        batch.create_check_constraint("ck_ftm_match_method", "match_method IN ('AUTO', 'HUMAN')")
    op.drop_index("ix_bank_engine_results_transaction", table_name="bank_engine_results")
    op.drop_table("bank_engine_results")
    op.drop_table("bank_engine_runs")
