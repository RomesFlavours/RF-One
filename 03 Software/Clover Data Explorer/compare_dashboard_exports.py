"""Compares RF-One-generated exports against the official Clover dashboard
reference CSVs and prints a structured summary (used to populate
CLOVER_EXPORT_RECONCILIATION.md — see that file for the narrative version
of these results).

Reads only local files; makes no network calls.

Usage:
    python compare_dashboard_exports.py --generated data/generated_exports/2026-08-17_to_2026-08-23
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clover_explorer.export_compare import compare_by_id, compare_line_items, read_clock_csv, read_csv_rows

MODULE_ROOT = Path(__file__).resolve().parent
REFERENCE_DIR = MODULE_ROOT / "data" / "reference_exports"

REFERENCE_PAYMENTS = "Payments-20260824_1107_EDT.csv"
REFERENCE_ORDERS = "Orders-20260824_1107_EDT.csv"
REFERENCE_LINE_ITEMS = "LineItemsExport-20260817_0000_EDT-20260823_2359_EDT.csv"
REFERENCE_CLOCK = "clock (26).csv"

PAYMENTS_COMPARE_FIELDS = [
    "Tender", "Currency", "Amount", "Tax Amount", "Tip Amount", "Service Charge Amount",
    "Payment Employee ID", "Order ID", "Result", "Device",
]
ORDERS_COMPARE_FIELDS = [
    "Order Type", "Order Employee ID", "Currency", "Tax Amount", "Tip", "Service Charge",
    "Discount", "Order Total", "Payments Total", "Tender", "Order Payment State",
]
LINE_ITEMS_COMPARE_FIELDS = [
    "Item Revenue", "Modifiers Revenue", "Total Revenue", "Order Discount Proportion",
    "Item Total", "Item Tax Rate", "Tax Amount", "Item Total with Tax/Fee Amount",
    "Service Charge", "Order Payment State",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", required=True, help="Path to the generated_exports run directory")
    args = parser.parse_args()
    gen_dir = Path(args.generated)

    result = {}

    ref_payments = read_csv_rows(REFERENCE_DIR / REFERENCE_PAYMENTS)
    gen_payments = read_csv_rows(gen_dir / "Payments_RFOne.csv")
    payments_cmp = compare_by_id(ref_payments, gen_payments, "Payment ID", PAYMENTS_COMPARE_FIELDS)
    result["payments"] = payments_cmp.__dict__

    ref_orders = read_csv_rows(REFERENCE_DIR / REFERENCE_ORDERS)
    gen_orders = read_csv_rows(gen_dir / "Orders_RFOne.csv")
    orders_cmp = compare_by_id(ref_orders, gen_orders, "Order ID", ORDERS_COMPARE_FIELDS)
    result["orders"] = orders_cmp.__dict__

    ref_line_items = read_csv_rows(REFERENCE_DIR / REFERENCE_LINE_ITEMS)
    gen_line_items = read_csv_rows(gen_dir / "LineItems_RFOne.csv")
    li_cmp = compare_line_items(ref_line_items, gen_line_items, LINE_ITEMS_COMPARE_FIELDS)
    result["line_items"] = li_cmp.__dict__

    ref_shifts, ref_totals, ref_overridden = read_clock_csv(REFERENCE_DIR / REFERENCE_CLOCK)
    gen_shifts, gen_totals, gen_overridden = read_clock_csv(gen_dir / "clock_RFOne.csv")

    def key_shift(r):
        return f"{r.get('Employee ID','')}|{r.get('Clock In Date','')}|{r.get('Clock In Time','')}"

    ref_shift_keys = {key_shift(r) for r in ref_shifts}
    gen_shift_keys = {key_shift(r) for r in gen_shifts}
    result["clock_shifts"] = {
        "reference_count": len(ref_shifts),
        "generated_count": len(gen_shifts),
        "matched": len(ref_shift_keys & gen_shift_keys),
        "missing_in_generated": sorted(ref_shift_keys - gen_shift_keys),
        "extra_in_generated": sorted(gen_shift_keys - ref_shift_keys),
    }

    ref_tot_by_emp = {r["Employee ID"]: r["Total Hours"] for r in ref_totals}
    gen_tot_by_emp = {r["Employee ID"]: r["Total Hours"] for r in gen_totals}
    common_emp = set(ref_tot_by_emp) & set(gen_tot_by_emp)
    exact = sum(1 for e in common_emp if ref_tot_by_emp[e] == gen_tot_by_emp[e])
    close = sum(
        1 for e in common_emp
        if abs(float(ref_tot_by_emp[e]) - float(gen_tot_by_emp[e])) <= 0.05
    )
    result["clock_employee_totals"] = {
        "reference_count": len(ref_totals),
        "generated_count": len(gen_totals),
        "matched_employees": len(common_emp),
        "exact_match": exact,
        "within_0.05h": close,
        "missing_in_generated": sorted(set(ref_tot_by_emp) - set(gen_tot_by_emp)),
        "extra_in_generated": sorted(set(gen_tot_by_emp) - set(ref_tot_by_emp)),
    }

    def key_override(r):
        return f"{r.get('Employee ID','')}|{r.get('Override Clock In Date','')}|{r.get('Override Clock In Time','')}|{r.get('Override Clock Out Date','')}|{r.get('Override Clock Out Time','')}"

    ref_ov_keys = {key_override(r) for r in ref_overridden}
    gen_ov_keys = {key_override(r) for r in gen_overridden}
    result["clock_overridden"] = {
        "reference_count": len(ref_overridden),
        "generated_count": len(gen_overridden),
        "matched": len(ref_ov_keys & gen_ov_keys),
        "missing_in_generated": sorted(ref_ov_keys - gen_ov_keys),
        "extra_in_generated": sorted(gen_ov_keys - ref_ov_keys),
    }

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
