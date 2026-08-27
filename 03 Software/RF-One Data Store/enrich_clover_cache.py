#!/usr/bin/env python
"""Standalone resumable dedicated-line-item / item-tax-rate cache enrichment.

Also invoked automatically by `ingest_clover.py`, but exposed as its own
entry point so enrichment can be run (and safely interrupted/resumed)
independently of a full ingestion attempt.

Usage:
    python enrich_clover_cache.py [--max N]

GET only. Never prints the API token, order/item identifiers, or payloads —
only aggregate progress counts.
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store.ingestion.clover import enrichment, reader


def _progress(done: int, total: int) -> None:
    print(f"Enriching dedicated line items: {done}/{total} complete", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max", type=int, default=None, help="Maximum number of NEW line-item fetches this run (default: no limit)"
    )
    args = parser.parse_args()

    bundle = reader.load_source_bundle()
    order_ids = [o["id"] for o in bundle.orders]

    already = len(order_ids) - len(enrichment.missing_line_item_order_ids(order_ids))
    print(f"Dedicated line items: {already}/{len(order_ids)} already cached before this run.")

    client = enrichment.get_client()
    summary = enrichment.enrich_dedicated_line_items(
        client, order_ids, max_to_fetch=args.max, progress=_progress
    )
    print(
        f"Dedicated line items: {summary.already_cached + summary.fetched_ok}/{summary.total} cached "
        f"({summary.fetched_ok} fetched this run, {summary.fetched_failed} failed)."
    )
    if summary.failed_ids:
        print(f"  {len(summary.failed_ids)} order(s) failed and will be retried on the next run.")

    # Small, bounded catch-up: items needing a per-item tax-rate override.
    non_default_tax_item_ids = [i["id"] for i in bundle.items_raw if i.get("defaultTaxRates") is False]
    tax_summary = enrichment.enrich_item_tax_rates(client, non_default_tax_item_ids)
    print(
        f"Item tax-rate overrides: {tax_summary.already_cached + tax_summary.fetched_ok}/{tax_summary.total} cached "
        f"({tax_summary.fetched_ok} fetched this run, {tax_summary.fetched_failed} failed)."
    )

    overall_complete = summary.complete and tax_summary.complete
    print(f"Enrichment status: {'COMPLETE' if overall_complete else 'INCOMPLETE'}")
    return 0 if overall_complete else 1


if __name__ == "__main__":
    sys.exit(main())
