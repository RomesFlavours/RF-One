"""Pure, source-detail parsing rules — no database access, no network.

Every function here implements one specific, evidence-confirmed parsing
rule from TASK_CLOVER_003 / TASK_DATABASE_002. Nothing here guesses beyond
what was empirically confirmed — an unrecognized shape returns `None`
(preserved as missing) rather than a best-effort guess.
"""

from __future__ import annotations

import re
from typing import Any

# TASK_CLOVER_003 confirmed exactly these two non-empty binName shapes across
# the full 23,342-line-item history, with zero malformed/unexpected values.
# Anything else is left unparsed (guest_number = NULL) rather than guessed.
_GUEST_LABEL_PATTERN = re.compile(r"^Guest (\d+)(?: \(From Table #\d+\))?$")


def parse_guest_number(guest_label_raw: str | None) -> int | None:
    """Parse `OrderItem.guest_number` from Clover's `binName` free text.

    Only the two confirmed patterns ("Guest N" and "Guest N (From Table #X)")
    are ever parsed. A blank/missing/unrecognized label yields `None` — never
    defaulted to Guest 1 (task §25)."""
    if not guest_label_raw:
        return None
    match = _GUEST_LABEL_PATTERN.match(guest_label_raw)
    if not match:
        return None
    return int(match.group(1))


def ref_id(value: Any) -> str | None:
    """Extract the `id` from a Clover reference sub-object (e.g.
    `{"id": "ABC", "href": "..."}`), or None if the reference is absent."""
    if isinstance(value, dict):
        return value.get("id")
    return None


def classify_applied_discount(discount_element: dict[str, Any]) -> dict[str, Any]:
    """Classify one `order.discounts[]` / (hypothetical future) Order Item
    discount element into the three confirmed shapes (task §28, TASK_CLOVER_003
    § L):

    - catalog-referenced: has a `discount` sub-reference (+ `discType`)
    - ad hoc percentage:  has `percentage`, no `discount` reference
    - ad hoc fixed amount: has `amount`, no `discount` reference

    Returns a dict with `source_discount_id`, `discount_definition_source_id`
    (the catalog reference, if any), `percentage`, `amount`, `name_raw`, and
    `shape` (one of "catalog", "ad_hoc_percentage", "ad_hoc_amount",
    "unrecognized") — `raw_shape_json` is simply `discount_element` itself,
    to be stored verbatim by the caller.
    """
    catalog_ref = ref_id(discount_element.get("discount"))
    percentage = discount_element.get("percentage")
    amount = discount_element.get("amount")

    if catalog_ref is not None:
        shape = "catalog"
    elif percentage is not None:
        shape = "ad_hoc_percentage"
    elif amount is not None:
        shape = "ad_hoc_amount"
    else:
        shape = "unrecognized"

    return {
        "source_discount_id": discount_element.get("id"),
        "discount_definition_source_id": catalog_ref,
        "percentage": percentage,
        "amount": amount,
        "name_raw": discount_element.get("name"),
        "shape": shape,
    }


def referenced_employee_ids(
    shifts: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    refunds: list[dict[str, Any]] | None,
) -> set[str]:
    """Every Employee source id referenced anywhere in the ingested source
    collections (Shift main/override, Order, Payment, Refund) — used both to
    create stub Employee rows for ids Clover's current `/employees` snapshot
    no longer returns, and to reconcile the expected Employee count against
    it (see `ingest.ingest_employee_stub_references`)."""
    referenced: set[str] = set()
    for s in shifts:
        for key in ("employee", "overrideInEmployee", "overrideOutEmployee"):
            ref = ref_id(s.get(key))
            if ref:
                referenced.add(ref)
    for o in orders:
        ref = ref_id(o.get("employee"))
        if ref:
            referenced.add(ref)
    for p in payments:
        ref = ref_id(p.get("employee"))
        if ref:
            referenced.add(ref)
    for r in refunds or []:
        ref = ref_id(r.get("employee"))
        if ref:
            referenced.add(ref)
    return referenced


def canonical_tax_rate(raw_rate: int | float | None) -> float | None:
    """Convert Clover's own tax-rate integer encoding (`rate / 10_000_000`,
    e.g. `650000` -> `0.065`) to the canonical decimal fraction stored in
    `TaxRate.rate` / `OrderItemTax.rate_applied` — never persisted in
    Clover's own scaling (DATABASE_SCHEMA.md § 0)."""
    if raw_rate is None:
        return None
    return raw_rate / 10_000_000
