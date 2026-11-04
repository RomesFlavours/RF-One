"""merge Invoice Intake and Restaurant Wines heads

No schema change. Restaurant Wines (b6e4d2a8c1f9, already applied on AWS)
and Invoice Intake (b3f9d2c6e4a1, already applied to the local working
database) were both written on top of d8e2f5a9c3b7. A merge revision,
rather than re-parenting either one, keeps every database that already
holds one of them upgradable to a single head.

Revision ID: 540ee75caa65
Revises: b3f9d2c6e4a1, b6e4d2a8c1f9
Create Date: 2026-10-12 09:22:07.101407

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '540ee75caa65'
down_revision: Union[str, Sequence[str], None] = ('b3f9d2c6e4a1', 'b6e4d2a8c1f9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
