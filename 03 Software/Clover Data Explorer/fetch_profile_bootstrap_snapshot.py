#!/usr/bin/env python
"""Fresh, read-only Clover snapshot for Restaurant Profile bootstrap
(TASK_RESTAURANT_003 §3).

Refreshes the current-state evidence the RF-One Data Store's Restaurant
Profile bootstrap/reconciliation needs to validate that its canonical
`employees` / `source_roles` / `employee_source_roles` tables (populated by
`ingest_clover.py`, a separate pipeline) are still congruent with what
Clover reports RIGHT NOW:

    GET /v3/merchants/{merchantId}/employees?expand=role
    GET /v3/merchants/{merchantId}/roles?expand=employees

Uses only the existing read-only `CloverClient`/`paginate` (GET only — this
module has no write capability by construction). Never performs a Clover
write operation. Never prints the API token.

Output is written to a NEW timestamped directory under
`data/generated_exports/_api_cache/restaurant_profile_bootstrap/` (entirely
git-ignored, see repository `.gitignore`) — it never overwrites any
existing cache used by other tasks, and this script never touches
`data/raw/` (so it does not change what `latest_raw_run_dir()` resolves to
for the unrelated full-ingestion pipeline).

The saved JSON files contain real Employee names/PINs (Clover returns them
inline on the expand=role response, as already noted by TASK_EMPLOYEE_002)
— this is exactly why the output directory is git-ignored. This script
itself never prints an employee name; its stdout is limited to counts.

Usage:
    python fetch_profile_bootstrap_snapshot.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from clover_explorer.client import CloverClient
from clover_explorer.config import ConfigError, load_config
from clover_explorer.pagination import paginate

OUTPUT_ROOT = Path(__file__).resolve().parent / "data" / "generated_exports" / "_api_cache" / "restaurant_profile_bootstrap"


def main() -> int:
    fetched_at = datetime.now(timezone.utc)

    try:
        config = load_config()
    except ConfigError as exc:
        print("Fresh Clover snapshot: FAILED")
        print(f"Reason: {exc}")
        return 1

    client = CloverClient(config)
    merchant_path = f"/v3/merchants/{client.merchant_id}"

    employees_result = paginate(client, f"{merchant_path}/employees", extra_params={"expand": "role"})
    roles_result = paginate(client, f"{merchant_path}/roles", extra_params={"expand": "employees"})

    if not employees_result.ok or not roles_result.ok:
        print("Fresh Clover snapshot: FAILED (read-only GET)")
        if not employees_result.ok:
            print(f"  employees?expand=role error: {employees_result.error}")
        if not roles_result.ok:
            print(f"  roles?expand=employees error: {roles_result.error}")
        return 1

    run_dir = OUTPUT_ROOT / fetched_at.strftime("%Y-%m-%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "employees_expand_role.json").write_text(
        json.dumps(employees_result.elements, indent=2), encoding="utf-8"
    )
    (run_dir / "roles_expand_employees.json").write_text(
        json.dumps(roles_result.elements, indent=2), encoding="utf-8"
    )

    manifest = {
        "fetched_at": fetched_at.isoformat(),
        "merchant_id": client.merchant_id,
        "employees_count": len(employees_result.elements),
        "roles_count": len(roles_result.elements),
        "employees_pages_fetched": employees_result.pages_fetched,
        "roles_pages_fetched": roles_result.pages_fetched,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("Fresh Clover snapshot: SUCCESS")
    print(f"  saved to: {run_dir}")
    print(f"  current Employees (expand=role):  {manifest['employees_count']}")
    print(f"  current Roles (expand=employees): {manifest['roles_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
