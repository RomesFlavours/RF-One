"""Phase 1 — smallest safe read-only Clover connection check.

Reports only: connection success/failure, HTTP status, merchant ID,
merchant name (if returned), and response timestamp. Never prints the
API token. Uses a single GET request.

Usage:
    python check_connection.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from clover_explorer.client import CloverClient
from clover_explorer.config import ConfigError, load_config


def main() -> int:
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        config = load_config()
    except ConfigError as exc:
        print("Clover connection check: FAILED")
        print(f"Response timestamp: {timestamp}")
        print(f"Reason: {exc}")
        return 1

    client = CloverClient(config)
    result = client.get(f"/v3/merchants/{client.merchant_id}")

    print(f"Response timestamp: {timestamp}")
    print(f"Merchant ID: {client.merchant_id}")

    if not result.ok:
        print("Clover connection check: FAILED")
        print(f"HTTP status: {result.status_code}")
        print(f"Error: {result.error}")
        return 1

    merchant_name = result.data.get("name") if isinstance(result.data, dict) else None
    print("Clover connection check: SUCCESS")
    print(f"HTTP status: {result.status_code}")
    print(f"Merchant name: {merchant_name if merchant_name else '(not returned)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
