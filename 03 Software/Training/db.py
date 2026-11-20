"""Training's own database wiring — deliberately independent of `Tips/
app.py` (no import from it, avoiding any circular import between the two
and keeping "minimo collegamento necessario a Tips" — see `routes.py`,
which Tips imports FROM, never the other way around). Follows the exact
same top-of-file pattern `Tips/app.py`/`Selection/app.py` already use to
resolve the shared database URL and build one engine/session factory for
this process.

Deliberately does NOT run Alembic migrations or seed any data at import
time: a Gunicorn worker importing this module must never migrate the
schema or write to the database — those are explicit administrative/
deployment operations (`alembic upgrade head`, then
`python initialize_training.py`), run once before the application starts,
never repeated per worker. See `initialize_training.py` for the explicit,
operator-invoked equivalent of what this module used to do automatically.
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
