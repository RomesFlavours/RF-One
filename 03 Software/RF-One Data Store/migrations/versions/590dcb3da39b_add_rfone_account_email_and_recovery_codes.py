"""add rfone_account email/verification and rfone_account_verification_codes

Revision ID: 590dcb3da39b
Revises: 6a4816849735
Create Date: 2026-09-11 12:00:00.000000

Adds the general RF-One Account email/recovery foundation (task: "recupero
password generale di RF-One tramite codice email"):

  - `rfone_accounts.email` (nullable, unique) and `email_verified_at`
    (nullable) — an account may have an email on file that is not yet
    verified; both NULL means no email was ever recorded. Existing rows
    get NULL/NULL — no email is ever invented or auto-verified for an
    existing account.
  - `rfone_accounts.session_version` (NOT NULL, default 1) — the minimal
    server-side session-revocation mechanism; every existing row starts at
    1, matching what every already-issued session cookie implicitly
    carries as "no version claim yet" only in the sense that the
    application always WRITES a version into a session at login time from
    now on, so this default only matters for rows, never for cookies.
  - `rfone_account_verification_codes` — one new table for both email
    verification and password recovery codes (never a per-purpose or
    per-Domain duplicate).

Purely additive — no existing column is altered or dropped, no existing
row's data is rewritten, and no other table (Training, Tips, Compensation,
Selection) is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '590dcb3da39b'
down_revision: Union[str, Sequence[str], None] = '6a4816849735'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('rfone_accounts', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('rfone_accounts', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'rfone_accounts',
        sa.Column('session_version', sa.Integer(), nullable=False, server_default='1'),
    )
    # Batch mode: SQLite's own ALTER TABLE cannot add a constraint to an
    # existing table at all (Alembic's own error for a plain
    # create_unique_constraint here points at "batch mode" as the
    # workaround); on PostgreSQL (RDS) batch mode issues the same plain
    # ALTER TABLE ... ADD CONSTRAINT directly, no table rebuild — so this
    # is the portable way to add a real UNIQUE CONSTRAINT (matching
    # `models.RFOneAccount.email`'s `unique=True`) on an EXISTING table
    # across both dialects.
    with op.batch_alter_table('rfone_accounts') as batch_op:
        batch_op.create_unique_constraint('uq_rfone_accounts_email', ['email'])

    op.create_table(
        'rfone_account_verification_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('purpose', sa.String(length=24), nullable=False),
        sa.Column('target_email', sa.String(length=255), nullable=False),
        sa.Column('code_hmac', sa.String(length=64), nullable=False),
        sa.Column('attempts_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('request_ip', sa.String(length=64), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invalidated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')", name='ck_rfone_verification_code_purpose',
        ),
        sa.ForeignKeyConstraint(['account_id'], ['rfone_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_rfone_account_verification_codes_account_id'),
        'rfone_account_verification_codes', ['account_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_rfone_account_verification_codes_account_id'), table_name='rfone_account_verification_codes',
    )
    op.drop_table('rfone_account_verification_codes')
    with op.batch_alter_table('rfone_accounts') as batch_op:
        batch_op.drop_constraint('uq_rfone_accounts_email', type_='unique')
    op.drop_column('rfone_accounts', 'session_version')
    op.drop_column('rfone_accounts', 'email_verified_at')
    op.drop_column('rfone_accounts', 'email')
