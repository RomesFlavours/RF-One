"""RF-One Web's own database wiring — resolves the shared database URL and
builds one engine/session factory for this process.

Deliberately does NOT run Alembic migrations or write anything at import
time: a Gunicorn worker importing this module must never migrate the
schema or write to the database — those are explicit administrative/
deployment operations (`alembic upgrade head`, then, if ever needed,
`create_admin.py`), run once by an operator, never repeated per worker.
This is the same architectural rule `Training/db.py` was corrected to
follow after RF-ONE: REMOVE DB MIGRATION AND TRAINING SEEDING FROM
APPLICATION BOOT — applied here from the start.
"""

from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    create_configured_engine, create_session_factory, get_database_url,
)

DB_URL = get_database_url()
_engine = create_configured_engine(DB_URL)
SessionFactory = create_session_factory(_engine)
