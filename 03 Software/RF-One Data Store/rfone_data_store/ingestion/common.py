"""Shared, source-independent ingestion helpers.

Nothing in this module knows about Clover specifically — Clover-specific
transformation lives in `ingestion/clover/`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def epoch_ms_to_utc(value: int | None) -> datetime | None:
    """Convert an epoch-millisecond integer (as every Clover timestamp field
    is represented) to a UTC-aware datetime. Never invents a timezone the
    source did not supply — the input is already unambiguous (epoch), so no
    Location timezone is involved in this conversion at all."""
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def payload_hash(payload: Any) -> str:
    """Deterministic SHA-256 hash of a JSON-serializable payload, used as
    `SourceRecord.payload_hash` — cheap idempotency/change signal without
    duplicating the payload itself into the canonical DB."""
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
