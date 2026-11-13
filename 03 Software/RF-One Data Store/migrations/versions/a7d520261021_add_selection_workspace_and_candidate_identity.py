"""Selection position workspace and external candidate identity
(SELECTION_AI_INTEGRATION_001).

Additive only: new tables, no change to any existing table or row. See
`rfone_data_store/selection/workspace_models.py`.

Revision ID: a7d520261021
Revises: c8e4b2a6f0d1
"""

from alembic import op
import sqlalchemy as sa

revision = "a7d520261021"
down_revision = "c8e4b2a6f0d1"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", sa.Integer(), primary_key=True)


def _pc_fk():
    return sa.Column("position_candidate_id", sa.Integer(),
                     sa.ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)


def upgrade():
    op.create_table(
        "selection_candidate_accounts", _id(),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_candidate_email_codes", _id(),
        sa.Column("candidate_account_id", sa.Integer(), sa.ForeignKey("selection_candidate_accounts.id"),
                  nullable=False, index=True),
        sa.Column("code_hmac", sa.String(64), nullable=False),
        sa.Column("request_ip", sa.String(64), nullable=True),
        sa.Column("attempts_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_positions", _id(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("location_label", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("headcount", sa.Integer(), nullable=False),
        sa.Column("job_ad_en", sa.Text(), nullable=False),
        sa.Column("questions_json", sa.Text(), nullable=False),
        sa.Column("approved_job_ad_en", sa.Text(), nullable=True),
        sa.Column("approved_questions_json", sa.Text(), nullable=True),
        sa.Column("manager_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False,
                  index=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False),
        sa.Column("requirement_set_id", sa.Integer(), sa.ForeignKey("requirement_sets.id"), nullable=False),
        sa.Column("approved_snapshot_id", sa.Integer(), sa.ForeignKey("requirement_set_snapshots.id"),
                  nullable=True),
        sa.Column("approved_by_account_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("public_token", sa.String(64), nullable=False, unique=True),
        sa.Column("organization_context_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "selection_workspace_position_candidates", _id(),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("selection_workspace_positions.id"), nullable=False,
                  index=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("candidate_account_id", sa.Integer(), sa.ForeignKey("selection_candidate_accounts.id"),
                  nullable=True, index=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("added_by_account_id", sa.Integer(), nullable=True),
        sa.Column("declared_name", sa.String(255), nullable=True),
        sa.Column("declared_email", sa.String(255), nullable=True),
        sa.Column("declared_phone", sa.String(64), nullable=True),
        sa.Column("import_note", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("position_id", "application_id", name="uq_sel_ws_pc_position_application"),
    )
    op.create_table(
        "selection_workspace_candidate_applications", _id(),
        sa.Column("position_candidate_id", sa.Integer(), sa.ForeignKey("selection_workspace_position_candidates.id"),
                  nullable=False, unique=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("questions_json", sa.Text(), nullable=False),
        sa.Column("consent_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_answers", _id(),
        sa.Column("candidate_application_id", sa.Integer(),
                  sa.ForeignKey("selection_workspace_candidate_applications.id"), nullable=False, index=True),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_source", sa.String(16), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("input_mode", sa.String(8), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("candidate_application_id", "question_index",
                            name="uq_sel_ws_answer_application_question"),
    )
    op.create_table(
        "selection_workspace_proposals", _id(), _pc_fk(),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("fit_assessment_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("group_code", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("provider_label", sa.String(200), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_decisions", _id(), _pc_fk(),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("proposal_group", sa.String(32), nullable=True),
        sa.Column("proposal_source", sa.String(16), nullable=True),
        sa.Column("differs_from_proposal", sa.Boolean(), nullable=False),
        sa.Column("actor_account_id", sa.Integer(), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_appointments", _id(), _pc_fk(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("place", sa.String(255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("booked_by", sa.String(16), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_slot_offers", _id(), _pc_fk(),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("slots_json", sa.Text(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("place", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_messages", _id(), _pc_fk(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("approved_by_name", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_events", _id(),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("selection_workspace_positions.id"), nullable=False,
                  index=True),
        sa.Column("position_candidate_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("actor_account_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_position_drafts", _id(),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("selection_workspace_positions.id"), nullable=False,
                  index=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("provider_label", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "selection_workspace_company_profile", _id(),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("updated_by_name", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    for table in ("selection_workspace_company_profile", "selection_workspace_position_drafts",
                  "selection_workspace_events", "selection_workspace_messages", "selection_workspace_slot_offers",
                  "selection_workspace_appointments", "selection_workspace_decisions",
                  "selection_workspace_proposals", "selection_workspace_answers",
                  "selection_workspace_candidate_applications", "selection_workspace_position_candidates",
                  "selection_workspace_positions", "selection_candidate_email_codes",
                  "selection_candidate_accounts"):
        op.drop_table(table)
