"""Merge the Bank line of work into main (BANK_AWS_001)

Revision ID: 7b1d4f9a2c6e
Revises: a3c7e5b9d1f4, e8c4a2f6b1d3
Create Date: 2026-10-12

Joins the two heads, changing no table and no row:

  * a3c7e5b9d1f4 — the Bank line (Bank AI Rules, WHO-only mode, Personal entities, account item access /
                   Organization Domain, Project Management first built there by e3a7c5f9b1d4 / f5b8d2a4c6e1);
  * e8c4a2f6b1d3 — main (Restaurant Wines, Project Management by d2f6b9a3e7c1, a Responsible per Task).

Project Management exists on both lines with the same schema: whichever line runs first creates the tables, the other
skips what exists (d2f6b9a3e7c1, e3a7c5f9b1d4, f5b8d2a4c6e1).
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = '7b1d4f9a2c6e'
down_revision: Union[str, Sequence[str], None] = ('a3c7e5b9d1f4', 'e8c4a2f6b1d3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
