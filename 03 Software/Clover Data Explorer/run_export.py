"""Phase 2 — full read-only export + data-discovery report.

Runs the connection check first; aborts cleanly without further calls if it
fails. Otherwise exports every collection listed in
`clover_explorer.orchestrator.COLLECTIONS`, writes the raw JSON + manifest
under `data/raw/<run timestamp>/`, and regenerates
`CLOVER_DATA_DISCOVERY.md`.

Only GET requests are issued. No tip calculation, no KPI derivation, no
write to Clover.

Usage:
    python run_export.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from clover_explorer.client import CloverClient
from clover_explorer.config import ConfigError, load_config
from clover_explorer.discovery import write_discovery_report
from clover_explorer.orchestrator import run_full_export

MODULE_ROOT = Path(__file__).resolve().parent
DISCOVERY_REPORT_PATH = MODULE_ROOT / "CLOVER_DATA_DISCOVERY.md"


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print("Export aborted before any request: configuration error.")
        print(f"Reason: {exc}")
        return 1

    client = CloverClient(config)

    print(f"Starting Clover export for merchant {client.merchant_id} against {client.base_url}")
    run = run_full_export(client)

    merchant_entry = next((e for e in run.manifest["collections"] if e["name"] == "merchant"), None)
    if not merchant_entry or not merchant_entry["http_success"]:
        print("Export aborted: merchant connection check failed.")
        print(f"HTTP status: {merchant_entry.get('http_status_last') if merchant_entry else 'n/a'}")
        print(f"Error: {merchant_entry.get('error') if merchant_entry else 'n/a'}")
        print(f"Manifest written to: {run.run_dir / 'manifest.json'}")
        return 1

    print(f"Merchant connection OK (HTTP {merchant_entry['http_status_last'] or 200}).")

    collections_data: dict[str, list | None] = {}
    merchant_data = None
    merchant_file = run.run_dir / "merchant.json"
    if merchant_file.exists():
        merchant_data = json.loads(merchant_file.read_text(encoding="utf-8"))

    for entry in run.manifest["collections"]:
        name = entry["name"]
        if name == "merchant":
            continue
        if entry["http_success"] and entry.get("output_file"):
            file_path = run.run_dir / entry["output_file"]
            collections_data[name] = json.loads(file_path.read_text(encoding="utf-8"))
        else:
            collections_data[name] = None
        status = "OK" if entry["http_success"] else "FAILED"
        count = entry.get("record_count")
        print(f"  - {entry['category']:<10} {name:<20} {status:<7} records={count if count is not None else '-'}")

    write_discovery_report(DISCOVERY_REPORT_PATH, run.manifest, collections_data, merchant_data)

    print(f"Raw export directory: {run.run_dir}")
    print(f"Manifest: {run.run_dir / 'manifest.json'}")
    print(f"Discovery report: {DISCOVERY_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
