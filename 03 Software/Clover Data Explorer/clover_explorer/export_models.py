"""Loading raw Clover API collections and building ID-keyed lookup maps.

Read-only with respect to the raw export: nothing here ever writes into
`data/raw/`. Joins are always performed by Clover ID, never by display name
(per TASK_CLOVER_002's join-strategy requirement).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_collection(run_dir: Path, name: str) -> list[dict[str, Any]]:
    path = run_dir / f"{name}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in records if "id" in r}


def ref_id(value: Any) -> str | None:
    """Extract the id from a Clover reference object like {"id": "..."} or
    None if the reference itself is absent."""
    if isinstance(value, dict):
        return value.get("id")
    return None


class RawData:
    """Convenience bundle of every collection this task's exports need,
    loaded once from a single raw export run directory."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.employees = load_collection(run_dir, "employees")
        self.orders = load_collection(run_dir, "orders")
        self.payments = load_collection(run_dir, "payments")
        self.items = load_collection(run_dir, "items")
        self.order_types = load_collection(run_dir, "order_types")
        self.tax_rates = load_collection(run_dir, "tax_rates")
        self.discounts = load_collection(run_dir, "discounts")
        self.shifts = load_collection(run_dir, "shifts")
        self.modifier_groups = load_collection(run_dir, "modifier_groups")

        self.employees_by_id = by_id(self.employees)
        self.orders_by_id = by_id(self.orders)
        self.payments_by_id = by_id(self.payments)
        self.items_by_id = by_id(self.items)
        self.order_types_by_id = by_id(self.order_types)
        self.tax_rates_by_id = by_id(self.tax_rates)

        self.default_tax_rate = next(
            (t for t in self.tax_rates if t.get("isDefault")), None
        )

    def employee_fields(self, employee_id: str | None) -> tuple[str, str, str]:
        """Returns (id, name, customId), each "" if unavailable."""
        if not employee_id:
            return "", "", ""
        emp = self.employees_by_id.get(employee_id)
        if not emp:
            return employee_id, "", ""
        return employee_id, emp.get("name", ""), emp.get("customId", "")
