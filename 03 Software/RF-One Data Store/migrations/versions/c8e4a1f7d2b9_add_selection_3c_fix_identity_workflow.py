"""add Selection 3C-FIX identity resolution + workflow + policy rule state

Revision ID: c8e4a1f7d2b9
Revises: d9f3b7a2c5e8
Create Date: 2026-09-02 00:00:00.000000

Additive, non-destructive changes implementing the RF-One Selection
3C-FIX task (identity resolution, Selezionatore-only workflow status,
Review Priority Policy rule lifecycle, notes history):

- `candidate_persons.primary_phone_normalized` / `.normalized_name` —
  digits-only phone and normalized full name, used by
  `rfone_data_store/selection/identity_service.py` for confidence-based
  identity matching (VERY_STRONG/STRONG/POSSIBLE). Display fields
  (`primary_phone`, `full_name`) are unchanged.
- `applications.review_priority_reasons` — the reasons behind
  `review_priority_system`, persisted so the Review Queue can show them
  without recomputing.
- `applications.workflow_status` / `.workflow_status_reason` /
  `.workflow_status_updated_at` — the operational NEW/IN_REVIEW/
  ADVANCE_TO_PHONE/HOLD/STOP status, set only by an explicit Selezionatore
  action, never by Review Priority.
- `applications.identity_origin` / `.identity_confirmed_at` — records
  whether an Application's person link was resolved automatically or
  manually confirmed/corrected by a Selezionatore.
- `review_priority_policy_rules.is_active` — a deactivated rule stops
  contributing without being deleted.
- `person_match_candidates` — pending/confirmed/rejected possible-person-
  match suggestions (never an automatic merge).
- `application_notes` — append-only Selezionatore notes, replacing the
  single overwritten `applications.notes` value as the primary notes
  mechanism (that legacy column is kept, untouched, for backward
  compatibility).

No existing table, row or column is altered in a way that loses data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e4a1f7d2b9'
down_revision: Union[str, Sequence[str], None] = 'd9f3b7a2c5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidate_persons', sa.Column('primary_phone_normalized', sa.String(length=32), nullable=True))
    op.add_column('candidate_persons', sa.Column('normalized_name', sa.String(length=255), nullable=True))
    op.create_index(
        op.f('ix_candidate_persons_primary_phone_normalized'), 'candidate_persons',
        ['primary_phone_normalized'], unique=False,
    )
    op.create_index(
        op.f('ix_candidate_persons_normalized_name'), 'candidate_persons', ['normalized_name'], unique=False,
    )

    op.add_column(
        'applications',
        sa.Column('review_priority_reasons', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        'applications',
        sa.Column('workflow_status', sa.String(length=24), nullable=False, server_default='NEW'),
    )
    op.add_column('applications', sa.Column('workflow_status_reason', sa.Text(), nullable=True))
    op.add_column('applications', sa.Column('workflow_status_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'applications',
        sa.Column('identity_origin', sa.String(length=24), nullable=False, server_default='SYSTEM_RESOLVED'),
    )
    op.add_column('applications', sa.Column('identity_confirmed_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        'review_priority_policy_rules',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        'person_match_candidates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('source_person_id', sa.Integer(), nullable=False),
        sa.Column('suggested_person_id', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.String(length=16), nullable=False),
        sa.Column('match_basis', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='PENDING'),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['source_person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['suggested_person_id'], ['candidate_persons.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_person_match_candidates_application_id'), 'person_match_candidates', ['application_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_person_match_candidates_source_person_id'), 'person_match_candidates', ['source_person_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_person_match_candidates_suggested_person_id'), 'person_match_candidates', ['suggested_person_id'],
        unique=False,
    )

    op.create_table(
        'application_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('note_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_application_notes_application_id'), 'application_notes', ['application_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_application_notes_application_id'), table_name='application_notes')
    op.drop_table('application_notes')

    op.drop_index(op.f('ix_person_match_candidates_suggested_person_id'), table_name='person_match_candidates')
    op.drop_index(op.f('ix_person_match_candidates_source_person_id'), table_name='person_match_candidates')
    op.drop_index(op.f('ix_person_match_candidates_application_id'), table_name='person_match_candidates')
    op.drop_table('person_match_candidates')

    op.drop_column('review_priority_policy_rules', 'is_active')

    op.drop_column('applications', 'identity_confirmed_at')
    op.drop_column('applications', 'identity_origin')
    op.drop_column('applications', 'workflow_status_updated_at')
    op.drop_column('applications', 'workflow_status_reason')
    op.drop_column('applications', 'workflow_status')
    op.drop_column('applications', 'review_priority_reasons')

    op.drop_index(op.f('ix_candidate_persons_normalized_name'), table_name='candidate_persons')
    op.drop_index(op.f('ix_candidate_persons_primary_phone_normalized'), table_name='candidate_persons')
    op.drop_column('candidate_persons', 'normalized_name')
    op.drop_column('candidate_persons', 'primary_phone_normalized')
