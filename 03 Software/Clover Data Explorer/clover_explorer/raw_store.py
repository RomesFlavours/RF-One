"""Local persistence of raw Clover API responses.

Every export run writes into its own timestamped directory under
`data/raw/`, which is Git-ignored (see repository root `.gitignore`).
Raw JSON is preserved as returned by Clover, without normalization.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = MODULE_ROOT / "data" / "raw"


def new_run_dir(base_dir: Path = RAW_DATA_DIR) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = base_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def save_json(run_dir: Path, filename: str, data: Any) -> Path:
    """Write `data` as pretty JSON. Never called for an empty/failed collection."""
    out_path = run_dir / filename
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    return out_path


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    return save_json(run_dir, "manifest.json", manifest)
