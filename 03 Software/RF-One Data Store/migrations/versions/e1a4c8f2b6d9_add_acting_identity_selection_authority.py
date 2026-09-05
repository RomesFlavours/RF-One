"""add ActingIdentity + Selection authority FK references (GLOBAL_INTEGRITY_FIX_002)

Revision ID: e1a4c8f2b6d9
Revises: a2d8f4c1b9e6
Create Date: 2026-09-05 00:00:00.000000

Addresses Global Integrity Review 001 findings C-1 (no stable Acting
Identity), I-4 (inconsistent Selection authority patterns) and I-12 (no
regression coverage for ownership/authority logic) —
`07 Tasks/Reports/RF_ONE_GLOBAL_INTEGRITY_REVIEW_001.md`.

One new, additive, domain-independent table — `acting_identities`
(`rfone_data_store/models.py`'s `ActingIdentity`) — placed in the shared
substrate, never inside Selection, per Core Principle 21 ("no Domain or
Module may define its own independent identity, authority or audit
mechanism"). Every other change in this migration is a purely additive,
nullable FK column on an EXISTING Selection table, pointing at
`acting_identities.id`, alongside the pre-existing free-text actor column
(`owner_name`/`assigned_by`/`selezionatore_name`/`confirmed_by`/
`performed_by`) — never replacing or backfilling it. No historical row is
modified, no existing column's meaning changes, and no existing free-text
value is fabricated into a guessed identity (Historical Integrity — honest
uncertainty over invented certainty).

Columns added:
- `selection_session_assignments.acting_identity_id` (+ new unique
  constraint on (session_id, acting_identity_id), alongside the pre-existing
  one on (session_id, selezionatore_name))
- `application_ownerships.acting_identity_id`,
  `application_ownerships.assigned_by_identity_id`
- `selection_rule_set_versions.confirmed_by_identity_id`
- `selection_rule_changes.performed_by_identity_id`
- `compliance_dispositions.performed_by_identity_id`
- `application_stage_transitions.performed_by_identity_id`
- `selection_outcome_decisions.performed_by_identity_id`

Also bootstraps exactly one deterministic, idempotent SYSTEM `ActingIdentity`
row (`kind='SYSTEM'`, `authentication_provider='rfone-internal'`,
`external_subject_id='SYSTEM'`) so automated/system-originated actions never
need to invent a fresh row or write a bare string like "SYSTEM" as an actor
— see `rfone_data_store/acting_identity_service.get_or_create_system_
identity`, which performs the same get-or-create check at runtime and is
therefore safe to run again even if this migration's bootstrap already ran.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a4c8f2b6d9'
down_revision: Union[str, Sequence[str], None] = 'a2d8f4c1b9e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_PROVIDER = 'rfone-internal'
SYSTEM_SUBJECT = 'SYSTEM'


def upgrade() -> None:
    """Upgrade schema."""

    # -- acting_identities (new shared substrate table) ----------------------
    op.create_table(
        'acting_identities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('authentication_provider', sa.String(length=64), nullable=True),
        sa.Column('external_subject_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(
            "kind IN ('HUMAN_USER', 'SYSTEM', 'AI_AGENT', 'EXTERNAL_SERVICE')", name='ck_acting_identity_kind',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'authentication_provider', 'external_subject_id', name='uq_acting_identity_external_subject',
        ),
    )
    op.create_index(op.f('ix_acting_identities_kind'), 'acting_identities', ['kind'], unique=False)

    # -- selection_session_assignments.acting_identity_id ---------------------
    with op.batch_alter_table('selection_session_assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('acting_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_selection_session_assignments_acting_identity_id', 'acting_identities', ['acting_identity_id'], ['id'],
        )
        batch_op.create_unique_constraint(
            'uq_session_assignment_session_identity', ['session_id', 'acting_identity_id'],
        )
    op.create_index(
        op.f('ix_selection_session_assignments_acting_identity_id'),
        'selection_session_assignments', ['acting_identity_id'], unique=False,
    )

    # -- application_ownerships.acting_identity_id / assigned_by_identity_id --
    with op.batch_alter_table('application_ownerships', schema=None) as batch_op:
        batch_op.add_column(sa.Column('acting_identity_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('assigned_by_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_application_ownerships_acting_identity_id', 'acting_identities', ['acting_identity_id'], ['id'],
        )
        batch_op.create_foreign_key(
            'fk_application_ownerships_assigned_by_identity_id', 'acting_identities', ['assigned_by_identity_id'], ['id'],
        )
    op.create_index(
        op.f('ix_application_ownerships_acting_identity_id'), 'application_ownerships', ['acting_identity_id'], unique=False,
    )
    op.create_index(
        op.f('ix_application_ownerships_assigned_by_identity_id'),
        'application_ownerships', ['assigned_by_identity_id'], unique=False,
    )

    # -- selection_rule_set_versions.confirmed_by_identity_id ------------------
    with op.batch_alter_table('selection_rule_set_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confirmed_by_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_selection_rule_set_versions_confirmed_by_identity_id',
            'acting_identities', ['confirmed_by_identity_id'], ['id'],
        )
    op.create_index(
        op.f('ix_selection_rule_set_versions_confirmed_by_identity_id'),
        'selection_rule_set_versions', ['confirmed_by_identity_id'], unique=False,
    )

    # -- selection_rule_changes.performed_by_identity_id -----------------------
    with op.batch_alter_table('selection_rule_changes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('performed_by_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_selection_rule_changes_performed_by_identity_id',
            'acting_identities', ['performed_by_identity_id'], ['id'],
        )
    op.create_index(
        op.f('ix_selection_rule_changes_performed_by_identity_id'),
        'selection_rule_changes', ['performed_by_identity_id'], unique=False,
    )

    # -- compliance_dispositions.performed_by_identity_id ----------------------
    with op.batch_alter_table('compliance_dispositions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('performed_by_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_compliance_dispositions_performed_by_identity_id',
            'acting_identities', ['performed_by_identity_id'], ['id'],
        )
    op.create_index(
        op.f('ix_compliance_dispositions_performed_by_identity_id'),
        'compliance_dispositions', ['performed_by_identity_id'], unique=False,
    )

    # -- application_stage_transitions.performed_by_identity_id ----------------
    with op.batch_alter_table('application_stage_transitions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('performed_by_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_application_stage_transitions_performed_by_identity_id',
            'acting_identities', ['performed_by_identity_id'], ['id'],
        )
    op.create_index(
        op.f('ix_application_stage_transitions_performed_by_identity_id'),
        'application_stage_transitions', ['performed_by_identity_id'], unique=False,
    )

    # -- selection_outcome_decisions.performed_by_identity_id ------------------
    with op.batch_alter_table('selection_outcome_decisions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('performed_by_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_selection_outcome_decisions_performed_by_identity_id',
            'acting_identities', ['performed_by_identity_id'], ['id'],
        )
    op.create_index(
        op.f('ix_selection_outcome_decisions_performed_by_identity_id'),
        'selection_outcome_decisions', ['performed_by_identity_id'], unique=False,
    )

    # -- deterministic, idempotent SYSTEM identity bootstrap -------------------
    bind = op.get_bind()
    acting_identities = sa.table(
        'acting_identities',
        sa.column('id', sa.Integer()),
        sa.column('kind', sa.String()),
        sa.column('display_name', sa.String()),
        sa.column('is_active', sa.Boolean()),
        sa.column('authentication_provider', sa.String()),
        sa.column('external_subject_id', sa.String()),
    )
    existing_system = bind.execute(
        sa.select(acting_identities.c.id).where(
            acting_identities.c.authentication_provider == SYSTEM_PROVIDER,
            acting_identities.c.external_subject_id == SYSTEM_SUBJECT,
        )
    ).first()
    if existing_system is None:
        bind.execute(
            acting_identities.insert().values(
                kind='SYSTEM', display_name='RF-One System', is_active=True,
                authentication_provider=SYSTEM_PROVIDER, external_subject_id=SYSTEM_SUBJECT,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f('ix_selection_outcome_decisions_performed_by_identity_id'), table_name='selection_outcome_decisions',
    )
    with op.batch_alter_table('selection_outcome_decisions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_selection_outcome_decisions_performed_by_identity_id', type_='foreignkey')
        batch_op.drop_column('performed_by_identity_id')

    op.drop_index(
        op.f('ix_application_stage_transitions_performed_by_identity_id'), table_name='application_stage_transitions',
    )
    with op.batch_alter_table('application_stage_transitions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_application_stage_transitions_performed_by_identity_id', type_='foreignkey')
        batch_op.drop_column('performed_by_identity_id')

    op.drop_index(
        op.f('ix_compliance_dispositions_performed_by_identity_id'), table_name='compliance_dispositions',
    )
    with op.batch_alter_table('compliance_dispositions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_compliance_dispositions_performed_by_identity_id', type_='foreignkey')
        batch_op.drop_column('performed_by_identity_id')

    op.drop_index(
        op.f('ix_selection_rule_changes_performed_by_identity_id'), table_name='selection_rule_changes',
    )
    with op.batch_alter_table('selection_rule_changes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_selection_rule_changes_performed_by_identity_id', type_='foreignkey')
        batch_op.drop_column('performed_by_identity_id')

    op.drop_index(
        op.f('ix_selection_rule_set_versions_confirmed_by_identity_id'), table_name='selection_rule_set_versions',
    )
    with op.batch_alter_table('selection_rule_set_versions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_selection_rule_set_versions_confirmed_by_identity_id', type_='foreignkey')
        batch_op.drop_column('confirmed_by_identity_id')

    op.drop_index(op.f('ix_application_ownerships_assigned_by_identity_id'), table_name='application_ownerships')
    op.drop_index(op.f('ix_application_ownerships_acting_identity_id'), table_name='application_ownerships')
    with op.batch_alter_table('application_ownerships', schema=None) as batch_op:
        batch_op.drop_constraint('fk_application_ownerships_assigned_by_identity_id', type_='foreignkey')
        batch_op.drop_constraint('fk_application_ownerships_acting_identity_id', type_='foreignkey')
        batch_op.drop_column('assigned_by_identity_id')
        batch_op.drop_column('acting_identity_id')

    op.drop_index(
        op.f('ix_selection_session_assignments_acting_identity_id'), table_name='selection_session_assignments',
    )
    with op.batch_alter_table('selection_session_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('uq_session_assignment_session_identity', type_='unique')
        batch_op.drop_constraint('fk_selection_session_assignments_acting_identity_id', type_='foreignkey')
        batch_op.drop_column('acting_identity_id')

    op.drop_index(op.f('ix_acting_identities_kind'), table_name='acting_identities')
    op.drop_table('acting_identities')
