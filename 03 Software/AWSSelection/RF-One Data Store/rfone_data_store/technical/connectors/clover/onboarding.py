"""Live (network) canonical Merchant/Location onboarding for a single Clover
account.

`acquisition.py`'s `import_clover_period()` refuses to run against a Location
it cannot resolve, and its own docstring points operators at "the full
Clover onboarding ingestion" (`ingest_clover.py`) to create one — but that
pipeline requires a full on-disk Clover export bundle and stages/promotes
through a local SQLite file, neither of which a fresh target database (e.g.
a new environment with zero on-disk Clover evidence yet) needs just to
satisfy that prerequisite.

This module fetches only the single Merchant resource live from the Clover
API and reuses the exact same canonical upsert logic
(`ingest.ingest_merchant_and_location`) the historical bulk pipeline already
uses — no duplicated mapping/upsert logic, and no Orders/Payments/Items/
Employees/Shifts touched here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from . import ingest, reader
from .acquisition import CloverReadClient


def onboard_merchant_and_location_live(
    session: Session,
    client: CloverReadClient,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> tuple[int, int]:
    """Fetches `GET /v3/merchants/{id}` live and upserts canonical
    Merchant/Location from it, via `ingest.ingest_merchant_and_location`
    (unchanged) — never fabricates Order-derived fields (e.g. `Location.
    currency`) that only real Order evidence can supply."""
    result = client.get(f"/v3/merchants/{client.merchant_id}")
    if not result.ok:
        raise RuntimeError(
            f"Clover merchant fetch failed: HTTP {result.status_code} ({result.error})"
        )

    bundle = reader.CloverSourceBundle(
        run_dir=Path("live-onboarding") / client.merchant_id,
        merchant=result.data,
        employees=[],
        roles=[],
        shifts=[],
        order_types=[],
        categories=[],
        modifier_groups=[],
        discounts=[],
        tax_rates=[],
        orders=[],
        payments=[],
        items_enriched=None,
        devices=None,
        refunds=None,
        employees_expand_role=None,
        items_raw=[],
    )

    return ingest.ingest_merchant_and_location(
        session, bundle, source_system_id, ingestion_run_id, retrieved_at
    )
