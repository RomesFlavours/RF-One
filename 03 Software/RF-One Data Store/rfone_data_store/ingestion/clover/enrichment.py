"""Resumable dedicated-endpoint enrichment (task §7, §9 of TASK_DATABASE_002).

TASK_CLOVER_003 established that the bulk `orders?expand=lineItems` source
never carries selected `modifications` at all — only the dedicated
`GET /orders/{id}/line_items?expand=modifications` endpoint does. TASK_CLOVER_002
enriched a 271-order window this way; the remaining ~3,250 orders in the full
history still need it for COMPLETE (not just PARTIAL) ingestion.

This module performs exactly that catch-up, plus the analogous (much
smaller) per-item tax-rate enrichment for items with `defaultTaxRates=False`.

Resumability is structural, not a separate progress file: every response is
cached under the same `data/generated_exports/_api_cache/supplementary/`
directory TASK_CLOVER_002 already uses (`lineitems_<orderId>.json`,
`itemtaxrate_<itemId>.json`), via the same `ApiCache.get_or_fetch` used
there. Re-running this module after an interruption simply finds the
already-cached files present and only fetches what is still missing — no
separate checkpoint bookkeeping is needed, and no completed work is redone.

GET only. The API token is never printed. Only progress counts are printed.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import reader

# Make the existing, already-reviewed read-only Clover client/config/cache
# code importable, without pulling any Clover Data Explorer *business logic*
# (dashboard CSV reconstruction, discovery reports) into the canonical
# ingestion path — only the low-level GET/pagination/cache primitives.
_CLOVER_EXPLORER_DIR = Path(__file__).resolve().parents[4] / "Clover Data Explorer"
if str(_CLOVER_EXPLORER_DIR) not in sys.path:
    sys.path.insert(0, str(_CLOVER_EXPLORER_DIR))

from clover_explorer.api_cache import ApiCache  # noqa: E402
from clover_explorer.client import CloverClient  # noqa: E402
from clover_explorer.config import load_config  # noqa: E402
from clover_explorer.pagination import paginate  # noqa: E402

# Conservative inter-request pacing. Not required by any documented Clover
# rate limit — a deliberate politeness margin on top of CloverClient's own
# 429/5xx retry+backoff, per the task's "conservative request pacing"
# instruction.
DEFAULT_PACE_SECONDS = 0.12


@dataclass
class EnrichmentSummary:
    already_cached: int = 0
    fetched_ok: int = 0
    fetched_failed: int = 0
    failed_ids: list[str] = field(default_factory=list)
    total: int = 0

    @property
    def complete(self) -> bool:
        return self.fetched_failed == 0 and (self.already_cached + self.fetched_ok) == self.total


def get_client() -> CloverClient:
    return CloverClient(load_config())


def missing_line_item_order_ids(order_ids: Iterable[str]) -> list[str]:
    return [oid for oid in order_ids if not reader.dedicated_line_items_cache_path(oid).is_file()]


def missing_item_tax_rate_ids(item_ids: Iterable[str]) -> list[str]:
    return [iid for iid in item_ids if not reader.item_tax_rate_cache_path(iid).is_file()]


def enrich_dedicated_line_items(
    client: CloverClient,
    order_ids: list[str],
    *,
    pace_seconds: float = DEFAULT_PACE_SECONDS,
    max_to_fetch: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> EnrichmentSummary:
    """Fetch `line_items?expand=modifications` for every order in
    `order_ids` that is not already cached, up to `max_to_fetch` new fetches
    (None = no limit). Safe to interrupt and re-run."""
    cache = ApiCache(reader.CLOVER_EXPLORER_DATA_DIR / "generated_exports" / "_api_cache", "supplementary")
    summary = EnrichmentSummary(total=len(order_ids))

    to_fetch = missing_line_item_order_ids(order_ids)
    summary.already_cached = len(order_ids) - len(to_fetch)

    if max_to_fetch is not None:
        to_fetch = to_fetch[:max_to_fetch]

    for i, order_id in enumerate(to_fetch, start=1):
        try:
            _fetch_and_cache_line_items(client, cache, order_id)
            summary.fetched_ok += 1
        except Exception:  # noqa: BLE001 — record and continue; never abort the whole run
            summary.fetched_failed += 1
            summary.failed_ids.append(order_id)
        if progress and (i % 25 == 0 or i == len(to_fetch)):
            progress(summary.already_cached + summary.fetched_ok, summary.total)
        time.sleep(pace_seconds)

    return summary


def _fetch_and_cache_line_items(client: CloverClient, cache: ApiCache, order_id: str) -> list[dict[str, Any]]:
    def _fetch() -> list[dict[str, Any]]:
        result = paginate(
            client,
            f"/v3/merchants/{client.merchant_id}/orders/{order_id}/line_items",
            extra_params={"expand": "modifications"},
        )
        if not result.ok and not result.elements:
            raise RuntimeError(f"line_items fetch failed for order (status recorded, id withheld from logs)")
        return result.elements

    return cache.get_or_fetch(f"lineitems_{order_id}", _fetch)


def enrich_item_tax_rates(
    client: CloverClient,
    item_ids: list[str],
    *,
    pace_seconds: float = DEFAULT_PACE_SECONDS,
    progress: Callable[[int, int], None] | None = None,
) -> EnrichmentSummary:
    cache = ApiCache(reader.CLOVER_EXPLORER_DATA_DIR / "generated_exports" / "_api_cache", "supplementary")
    summary = EnrichmentSummary(total=len(item_ids))

    to_fetch = missing_item_tax_rate_ids(item_ids)
    summary.already_cached = len(item_ids) - len(to_fetch)

    for i, item_id in enumerate(to_fetch, start=1):
        try:
            _fetch_and_cache_item_tax_rate(client, cache, item_id)
            summary.fetched_ok += 1
        except Exception:  # noqa: BLE001
            summary.fetched_failed += 1
            summary.failed_ids.append(item_id)
        if progress:
            progress(summary.already_cached + summary.fetched_ok, summary.total)
        time.sleep(pace_seconds)

    return summary


def _fetch_and_cache_item_tax_rate(client: CloverClient, cache: ApiCache, item_id: str) -> float:
    def _fetch() -> float:
        r = client.get(
            f"/v3/merchants/{client.merchant_id}/items/{item_id}",
            params={"expand": "taxRates"},
        )
        if not r.ok:
            raise RuntimeError("item tax-rate fetch failed (status recorded, id withheld from logs)")
        rates = (r.data.get("taxRates") or {}).get("elements", [])
        # Empty per-item taxRates list means 0%, confirmed by TASK_CLOVER_002/003
        # — not "fetch failed, fall back to default".
        return rates[0]["rate"] / 10_000_000 if rates else 0.0

    return cache.get_or_fetch(f"itemtaxrate_{item_id}", _fetch)
