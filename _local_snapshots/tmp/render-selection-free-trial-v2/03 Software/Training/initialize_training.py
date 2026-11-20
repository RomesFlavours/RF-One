#!/usr/bin/env python
"""Explicit, operator-invoked Training initialization step.

Seeds the 3 canonical Training pills and their 27 questions
(`ensure_pills_seeded`) — the only place that content is ever created.
Idempotent: safe to run more than once, since `ensure_pills_seeded` only
fills in what is missing (matched by natural key) and never updates or
duplicates an existing row.

Must be run AFTER Alembic migrations have already brought the database to
head. This script never runs Alembic itself.

It is deliberately NEVER imported or auto-executed by the application
(`Tips/app.py`, `Training/db.py`, `Training/routes.py`, Gunicorn, or the
Docker `CMD`): schema migration and Training initialization are explicit
administrative/deployment operations, run once by an operator, never
repeated per Gunicorn worker.

Usage:
    python initialize_training.py
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
from rfone_data_store.training import service as training_service  # noqa: E402


def main() -> int:
    db_url = get_database_url()
    engine = create_configured_engine(db_url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        try:
            training_service.ensure_pills_seeded(session)
            session.commit()
        except Exception as exc:
            session.rollback()
            print(f"Training initialization FAILED: {type(exc).__name__}")
            return 1

    print("Training initialization OK: pills and questions seeded (or already present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
