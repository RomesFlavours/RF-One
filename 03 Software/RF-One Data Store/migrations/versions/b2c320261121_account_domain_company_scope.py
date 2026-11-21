"""Company/site reach of a direct Domain access (CLOVER_MULTISITE_001, Product Owner 2026-11-21).

Additive and behaviour-preserving:
- `rfone_account_domain_access.company_scope` ('ALL' | 'SELECTED'), NOT NULL, server default 'ALL':
  every existing access keeps reaching every company/restaurant (Product Owner rule 2).
- `rfone_account_domain_company_access`: the companies chosen when company_scope is SELECTED.
- `tip_payment_audit_events`: append-only audit of Tips payments — who (account or system identity)
  and when each cycle was prepared and approved, each instruction executed, each retry attempted.
No account, access, grant, company or payment row is created, changed or removed.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c320261121'
down_revision = 'a1c220261121'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('rfone_account_domain_access', schema=None) as batch_op:
        batch_op.add_column(sa.Column('company_scope', sa.String(length=16), nullable=False, server_default='ALL'))
        batch_op.create_check_constraint(
            'ck_rfone_account_domain_access_company_scope', "company_scope IN ('ALL', 'SELECTED')",
        )
    op.create_table(
        'rfone_account_domain_company_access',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('domain_code', sa.String(length=32), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('rfone_company_contexts.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('account_id', 'domain_code', 'company_id', name='uq_account_domain_company_access'),
    )
    op.create_index('ix_rfone_account_domain_company_access_account_id',
                    'rfone_account_domain_company_access', ['account_id'])
    op.create_table(
        'tip_payment_audit_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('payment_cycle_id', sa.Integer(), sa.ForeignKey('tip_payment_cycles.id'), nullable=False),
        sa.Column('payment_instruction_id', sa.Integer(), sa.ForeignKey('tip_payment_instructions.id'),
                  nullable=True),
        sa.Column('event', sa.String(length=16), nullable=False),
        sa.Column('actor_kind', sa.String(length=16), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=True),
        sa.Column('acting_identity_id', sa.Integer(), sa.ForeignKey('acting_identities.id'), nullable=True),
        sa.Column('actor_label', sa.String(length=255), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('outcome', sa.String(length=32), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.CheckConstraint("event IN ('PREPARED','APPROVED','EXECUTED','RETRIED')",
                           name='ck_tip_payment_audit_event'),
        sa.CheckConstraint(
            "(actor_kind = 'ACCOUNT' AND account_id IS NOT NULL) OR (actor_kind = 'SYSTEM' AND account_id IS NULL)",
            name='ck_tip_payment_audit_actor'),
    )
    op.create_index('ix_tip_payment_audit_events_payment_cycle_id', 'tip_payment_audit_events',
                    ['payment_cycle_id'])
    op.create_index('ix_tip_payment_audit_events_payment_instruction_id', 'tip_payment_audit_events',
                    ['payment_instruction_id'])


def downgrade() -> None:
    op.drop_index('ix_tip_payment_audit_events_payment_instruction_id', table_name='tip_payment_audit_events')
    op.drop_index('ix_tip_payment_audit_events_payment_cycle_id', table_name='tip_payment_audit_events')
    op.drop_table('tip_payment_audit_events')
    op.drop_index('ix_rfone_account_domain_company_access_account_id',
                  table_name='rfone_account_domain_company_access')
    op.drop_table('rfone_account_domain_company_access')
    with op.batch_alter_table('rfone_account_domain_access', schema=None) as batch_op:
        batch_op.drop_constraint('ck_rfone_account_domain_access_company_scope', type_='check')
        batch_op.drop_column('company_scope')
