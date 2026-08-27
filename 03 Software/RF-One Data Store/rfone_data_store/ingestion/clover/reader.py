"""Reads Clover's already-collected raw/cache evidence from disk.

Source priority (task §6):
    1. dedicated cached endpoint response when it contains richer structure;
    2. full raw Clover export;
    3. bounded additional GET only when required for an INGEST NOW field.

This module implements priorities 1 and 2 (pure disk reads, no network).
Priority 3 (bounded additional GETs) lives in `enrichment.py`.

Nothing here performs any network call. Nothing here writes to Clover.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 03 Software/RF-One Data Store/rfone_data_store/ingestion/clover/reader.py
#   .parents[4] == "03 Software/"
_SOFTWARE_DIR = Path(__file__).resolve().parents[4]
CLOVER_EXPLORER_DATA_DIR = _SOFTWARE_DIR / "Clover Data Explorer" / "data"
RAW_DIR = CLOVER_EXPLORER_DATA_DIR / "raw"
SUPPLEMENTARY_CACHE_DIR = CLOVER_EXPLORER_DATA_DIR / "generated_exports" / "_api_cache" / "supplementary"
TASK3_AUDIT_CACHE_DIR = CLOVER_EXPLORER_DATA_DIR / "generated_exports" / "_api_cache" / "task3_audit"


class SourceEvidenceError(Exception):
    """Raised when expected Clover evidence cannot be located on disk."""


def latest_raw_run_dir() -> Path:
    """The most recent `data/raw/<timestamp>/` export directory (TASK_CLOVER_001).
    Timestamp directory names are ISO-8601-like and therefore lexicographically
    sortable."""
    if not RAW_DIR.is_dir():
        raise SourceEvidenceError(f"No raw Clover export directory found at {RAW_DIR}")
    candidates = sorted(p for p in RAW_DIR.iterdir() if p.is_dir())
    if not candidates:
        raise SourceEvidenceError(f"No raw Clover export run found under {RAW_DIR}")
    return candidates[-1]


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_raw_collection(name: str, run_dir: Path | None = None) -> Any:
    """Load a top-level collection (e.g. 'orders', 'payments', 'items') from
    the latest (or given) raw export run directory."""
    run_dir = run_dir or latest_raw_run_dir()
    path = run_dir / f"{name}.json"
    if not path.is_file():
        raise SourceEvidenceError(f"Expected raw collection file not found: {path}")
    return _load_json(path)


def try_load_cached(directory: Path, filename: str) -> Any | None:
    path = directory / filename
    if not path.is_file():
        return None
    return _load_json(path)


@dataclass
class CloverSourceBundle:
    """Every piece of Clover evidence this task's ingestion needs, loaded
    once from disk (priorities 1-2 only — no enrichment GETs happen here)."""

    run_dir: Path

    merchant: dict[str, Any]
    employees: list[dict[str, Any]]
    roles: list[dict[str, Any]]
    shifts: list[dict[str, Any]]
    order_types: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    modifier_groups: list[dict[str, Any]]
    discounts: list[dict[str, Any]]
    tax_rates: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    payments: list[dict[str, Any]]

    # Priority-1 (richer cached) sources, may be None if never fetched yet.
    items_enriched: list[dict[str, Any]] | None  # expand=categories,tags,modifierGroups
    devices: list[dict[str, Any]] | None
    refunds: list[dict[str, Any]] | None
    # `employees?expand=role` (TASK_CLOVER_004) — each element carries a
    # `roles.elements[]` array with the SPECIFIC named Role (id/name/
    # systemRole), not just the systemRole tier the bulk employees.json
    # carries. May be None if the supplementary cache was never fetched.
    employees_expand_role: list[dict[str, Any]] | None

    # Fallback (priority-2) plain items, always present (bulk raw export).
    items_raw: list[dict[str, Any]] = field(default_factory=list)

    @property
    def items(self) -> list[dict[str, Any]]:
        """The richest available Item source — enriched (with categories/
        tags/modifierGroups) if the cached expand call has been made,
        otherwise the plain bulk export (source priority §6)."""
        return self.items_enriched if self.items_enriched is not None else self.items_raw


def load_source_bundle() -> CloverSourceBundle:
    run_dir = latest_raw_run_dir()

    items_raw = load_raw_collection("items", run_dir)
    items_enriched = try_load_cached(
        TASK3_AUDIT_CACHE_DIR, "items_expand_categories_tags_modifierGroups.json"
    )
    devices = try_load_cached(SUPPLEMENTARY_CACHE_DIR, "devices.json")
    refunds = try_load_cached(TASK3_AUDIT_CACHE_DIR, "refunds_page1.json")
    employees_expand_role = try_load_cached(SUPPLEMENTARY_CACHE_DIR, "employees_expand_role.json")
    # refunds_page1.json was saved as the raw paginated envelope (see
    # TASK_CLOVER_003's supp_get1.py) — normalize to a bare element list.
    if isinstance(refunds, dict):
        refunds = refunds.get("elements", [])

    return CloverSourceBundle(
        run_dir=run_dir,
        merchant=load_raw_collection("merchant", run_dir),
        employees=load_raw_collection("employees", run_dir),
        roles=load_raw_collection("roles", run_dir),
        shifts=load_raw_collection("shifts", run_dir),
        order_types=load_raw_collection("order_types", run_dir),
        categories=load_raw_collection("categories", run_dir),
        modifier_groups=load_raw_collection("modifier_groups", run_dir),
        discounts=load_raw_collection("discounts", run_dir),
        tax_rates=load_raw_collection("tax_rates", run_dir),
        orders=load_raw_collection("orders", run_dir),
        payments=load_raw_collection("payments", run_dir),
        items_enriched=items_enriched,
        devices=devices,
        refunds=refunds,
        employees_expand_role=employees_expand_role,
        items_raw=items_raw,
    )


def dedicated_line_items_cache_path(order_id: str) -> Path:
    """Where the dedicated `line_items?expand=modifications` response for
    `order_id` is (or would be) cached — same file the Clover Data Explorer's
    ApiCache already uses (`lineitems_<orderId>.json`), so enrichment already
    performed by TASK_CLOVER_002/003 is reused automatically."""
    return SUPPLEMENTARY_CACHE_DIR / f"lineitems_{order_id}.json"


def load_dedicated_line_items(order_id: str) -> list[dict[str, Any]] | None:
    return try_load_cached(SUPPLEMENTARY_CACHE_DIR, f"lineitems_{order_id}.json")


def item_tax_rate_cache_path(item_id: str) -> Path:
    return SUPPLEMENTARY_CACHE_DIR / f"itemtaxrate_{item_id}.json"


def load_item_tax_rate(item_id: str) -> float | None:
    value = try_load_cached(SUPPLEMENTARY_CACHE_DIR, f"itemtaxrate_{item_id}.json")
    return value
