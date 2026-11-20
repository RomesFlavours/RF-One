"""Provision only new Selection tables without changing shared Alembic state.

Run once before deployment, after a snapshot. Other RF-One services retain
their existing migration history and can restart with their current images.
"""
from rfone_data_store.models import Base
from rfone_data_store.selection import workspace_models  # noqa: F401
from .aruba_bridge import CandidateBridgeTicket  # noqa: F401
from .mail_delivery import EmailOutbox  # noqa: F401


def provision(bind):
    tables = [t for t in Base.metadata.tables.values()
              if t.name.startswith(('selection_workspace_', 'selection_candidate_'))]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    return [t.name for t in tables]
