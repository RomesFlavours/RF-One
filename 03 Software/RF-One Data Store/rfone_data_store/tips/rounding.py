"""Deterministic minor-unit apportionment (task §13).

Every allocation must reconcile exactly to the source amount in minor
currency units (cents) — never lose or create a cent, and always produce
the same result for the same input. This module implements the
largest-remainder (Hamilton) method, the standard deterministic technique
for apportioning an integer total across proportional shares.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def split_largest_remainder(total: int, weights: list[Decimal]) -> list[int]:
    """Apportion integer `total` across `weights` (non-negative Decimals,
    treated as relative proportions of their own sum — NOT required to sum
    to 100) using the largest-remainder method.

    Deterministic: ties in remainder are broken by original list position
    (earlier index wins the extra cent). Always returns a list the same
    length as `weights`, summing to exactly `total`.
    """
    n = len(weights)
    if n == 0:
        if total != 0:
            raise ValueError("cannot apportion a nonzero total across zero weights")
        return []
    if total == 0:
        return [0] * n

    weight_sum = sum(weights)
    if weight_sum == 0:
        # Nothing to apportion proportionally by definition; the caller is
        # responsible for not calling this with all-zero weights when it
        # actually expects a proportional split. Money is not invented or
        # lost: the full total is placed on the first slot, deterministically.
        result = [0] * n
        result[0] = total
        return result

    raw = [(Decimal(total) * w) / weight_sum for w in weights]
    floors = [int(r.to_integral_value(rounding=ROUND_DOWN)) for r in raw]
    remainders = [r - f for r, f in zip(raw, floors)]

    allocated = sum(floors)
    leftover = total - allocated  # always >= 0 and < n

    order = sorted(range(n), key=lambda i: (-remainders[i], i))
    result = list(floors)
    for i in order[:leftover]:
        result[i] += 1
    return result


def equal_split(amount: int, employee_ids_sorted: list[int]) -> dict[int, int]:
    """Split `amount` (minor units) equally across `employee_ids_sorted`
    (already in a deterministic order, e.g. ascending id) — task §12,
    `EQUAL_ELIGIBLE_HEADCOUNT`. Remainder cents go to the first employees in
    that order, so the same eligible set always produces the same result.
    """
    n = len(employee_ids_sorted)
    if n == 0:
        return {}
    base = amount // n
    remainder = amount - base * n
    return {
        emp_id: base + (1 if i < remainder else 0)
        for i, emp_id in enumerate(employee_ids_sorted)
    }
