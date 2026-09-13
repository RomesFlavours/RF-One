"""merge rf-one 2.0 heads (organizational runtime + tips payment execution)

Revision ID: 09ed62634a09
Revises: 749a28964701, efe49dbc7321
Create Date: 2026-09-12 23:52:10.589750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09ed62634a09'
down_revision: Union[str, Sequence[str], None] = ('749a28964701', 'efe49dbc7321')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
