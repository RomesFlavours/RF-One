"""Field-by-field comparison between RF-One-generated exports and the
official Clover dashboard reference exports.

Uses stable IDs (Payment ID, Order ID) where Clover provides them. Line
Items have no dashboard-exported unique ID, so comparison there is a
grouped-multiset comparison by Order ID with an explicit ambiguity count
for duplicate composite keys within the same order — never a false claim
of row-level uniqueness (per TASK_CLOVER_002's instruction).
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_clock_csv(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Parses the three-section clock CSV (SHIFTS / EMPLOYEE TOTALS /
    OVERRIDDEN SHIFTS) into three separate row lists."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)

    sections: dict[str, list[list[str]]] = {"SHIFTS": [], "EMPLOYEE TOTALS": [], "OVERRIDDEN SHIFTS": []}
    current = None
    header = None
    for row in rows:
        if not row or (len(row) == 1 and row[0] == ""):
            current = None
            continue
        if len(row) == 1 and row[0] in sections:
            current = row[0]
            header = None
            continue
        if current is None:
            continue
        if header is None:
            header = row
            continue
        sections[current].append(dict(zip(header, row)))
    return sections["SHIFTS"], sections["EMPLOYEE TOTALS"], sections["OVERRIDDEN SHIFTS"]


@dataclass
class IdComparisonResult:
    reference_count: int
    generated_count: int
    matched_count: int
    missing_in_generated: list[str] = field(default_factory=list)  # in reference, not generated
    extra_in_generated: list[str] = field(default_factory=list)  # in generated, not reference
    field_match_rate: dict[str, float] = field(default_factory=dict)
    field_mismatch_examples: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)


def compare_by_id(
    reference_rows: list[dict[str, str]],
    generated_rows: list[dict[str, str]],
    id_field: str,
    compare_fields: list[str],
    max_examples: int = 3,
) -> IdComparisonResult:
    ref_by_id = {r[id_field]: r for r in reference_rows if r.get(id_field)}
    gen_by_id = {r[id_field]: r for r in generated_rows if r.get(id_field)}

    ref_ids = set(ref_by_id)
    gen_ids = set(gen_by_id)
    matched = ref_ids & gen_ids

    result = IdComparisonResult(
        reference_count=len(reference_rows),
        generated_count=len(generated_rows),
        matched_count=len(matched),
        missing_in_generated=sorted(ref_ids - gen_ids),
        extra_in_generated=sorted(gen_ids - ref_ids),
    )

    for f in compare_fields:
        match = 0
        examples: list[tuple[str, str, str]] = []
        for _id in matched:
            rv = (ref_by_id[_id].get(f) or "").strip()
            gv = (gen_by_id[_id].get(f) or "").strip()
            if rv == gv:
                match += 1
            elif len(examples) < max_examples:
                examples.append((_id, rv, gv))
        result.field_match_rate[f] = match / len(matched) if matched else 0.0
        if examples:
            result.field_mismatch_examples[f] = examples

    return result


@dataclass
class LineItemComparisonResult:
    reference_count: int
    generated_count: int
    orders_compared: int
    orders_exact_multiset_match: int
    orders_with_duplicate_keys_reference: int
    orders_with_duplicate_keys_generated: int
    orders_missing_entirely_in_generated: list[str] = field(default_factory=list)
    orders_extra_entirely_in_generated: list[str] = field(default_factory=list)
    field_match_rate_on_paired_items: dict[str, float] = field(default_factory=dict)


def _line_item_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row.get("Item ID", ""), row.get("Item Name", ""), (row.get("Item Revenue") or "").strip())


def compare_line_items(
    reference_rows: list[dict[str, str]],
    generated_rows: list[dict[str, str]],
    compare_fields: list[str],
) -> LineItemComparisonResult:
    ref_by_order: dict[str, list[dict[str, str]]] = {}
    for r in reference_rows:
        ref_by_order.setdefault(r.get("Order ID", ""), []).append(r)
    gen_by_order: dict[str, list[dict[str, str]]] = {}
    for r in generated_rows:
        gen_by_order.setdefault(r.get("Order ID", ""), []).append(r)

    ref_orders = set(ref_by_order)
    gen_orders = set(gen_by_order)
    common_orders = ref_orders & gen_orders

    result = LineItemComparisonResult(
        reference_count=len(reference_rows),
        generated_count=len(generated_rows),
        orders_compared=len(common_orders),
        orders_exact_multiset_match=0,
        orders_with_duplicate_keys_reference=0,
        orders_with_duplicate_keys_generated=0,
        orders_missing_entirely_in_generated=sorted(ref_orders - gen_orders),
        orders_extra_entirely_in_generated=sorted(gen_orders - ref_orders),
    )

    field_match = {f: 0 for f in compare_fields}
    field_total = {f: 0 for f in compare_fields}

    for order_id in common_orders:
        ref_rows = ref_by_order[order_id]
        gen_rows = gen_by_order[order_id]
        ref_keys = Counter(_line_item_key(r) for r in ref_rows)
        gen_keys = Counter(_line_item_key(r) for r in gen_rows)

        if any(c > 1 for c in ref_keys.values()):
            result.orders_with_duplicate_keys_reference += 1
        if any(c > 1 for c in gen_keys.values()):
            result.orders_with_duplicate_keys_generated += 1

        if ref_keys == gen_keys:
            result.orders_exact_multiset_match += 1

        # Greedy pairing within the order for field-level comparison, key by key.
        ref_pool: dict[tuple, list[dict[str, str]]] = {}
        for r in ref_rows:
            ref_pool.setdefault(_line_item_key(r), []).append(r)
        for g in gen_rows:
            key = _line_item_key(g)
            bucket = ref_pool.get(key)
            if not bucket:
                continue
            r = bucket.pop(0)
            for f in compare_fields:
                field_total[f] += 1
                if (r.get(f) or "").strip() == (g.get(f) or "").strip():
                    field_match[f] += 1

    for f in compare_fields:
        result.field_match_rate_on_paired_items[f] = (
            field_match[f] / field_total[f] if field_total[f] else 0.0
        )

    return result
