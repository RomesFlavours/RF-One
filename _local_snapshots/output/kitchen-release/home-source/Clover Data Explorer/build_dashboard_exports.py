"""TASK_CLOVER_002 entry point — reconstruct dashboard-comparable Clover CSV
exports from the raw API export, compare them against the official Clover
reference CSVs, and (re)generate the mapping/reconciliation documentation.

Only GET requests are issued (a bounded number of supplementary calls not
captured by TASK_CLOVER_001's raw export — cardTransaction per payment,
modifications per order's line items, devices, non-default item tax
rates — each cached locally so repeated runs do not re-hit the live API).
Nothing here writes to Clover, and the original raw JSON under
`data/raw/` is never modified.

Usage:
    python build_dashboard_exports.py
    python build_dashboard_exports.py --start 2026-08-17 --end 2026-08-23
    python build_dashboard_exports.py --raw-run 2026-08-24T231114Z --out data/generated_exports/custom
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from clover_explorer.api_cache import ApiCache
from clover_explorer.client import CloverClient
from clover_explorer.config import ConfigError, load_config
from clover_explorer.export_clock import (
    EMPLOYEE_TOTALS_COLUMNS,
    OVERRIDDEN_SHIFTS_COLUMNS,
    SHIFTS_COLUMNS,
    build_employee_totals_rows,
    build_overridden_shifts_rows,
    build_shifts_rows,
    overridden_shift_row_values,
)
from clover_explorer.export_line_items import LINE_ITEMS_COLUMNS, build_line_item_rows
from clover_explorer.export_models import RawData, ref_id
from clover_explorer.export_orders import ORDERS_COLUMNS, build_order_rows
from clover_explorer.export_payments import PAYMENTS_COLUMNS, build_payment_rows
from clover_explorer.time_money import MERCHANT_TIMEZONE

MODULE_ROOT = Path(__file__).resolve().parent
RAW_ROOT = MODULE_ROOT / "data" / "raw"
DEFAULT_OUT_ROOT = MODULE_ROOT / "data" / "generated_exports"

DEFAULT_START = "2026-08-17"
DEFAULT_END = "2026-08-23"  # inclusive


def latest_raw_run() -> Path:
    runs = sorted(p for p in RAW_ROOT.iterdir() if p.is_dir())
    if not runs:
        raise SystemExit(f"No raw export runs found under {RAW_ROOT}")
    return runs[-1]


def window_bounds_ms(start_date: str, end_date: str) -> tuple[int, int]:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MERCHANT_TIMEZONE)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, microsecond=999000, tzinfo=MERCHANT_TIMEZONE
    )
    return int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)


def in_window(ms: int | None, start_ms: int, end_ms: int) -> bool:
    return ms is not None and start_ms <= ms <= end_ms


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_clock_csv(
    path: Path,
    shifts_rows: list[dict[str, str]],
    totals_rows: list[dict[str, str]],
    overridden_rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["SHIFTS"])
        writer.writerow(SHIFTS_COLUMNS)
        for row in shifts_rows:
            writer.writerow([row[c] for c in SHIFTS_COLUMNS])
        writer.writerow([])

        writer.writerow(["EMPLOYEE TOTALS"])
        writer.writerow(EMPLOYEE_TOTALS_COLUMNS)
        for row in totals_rows:
            writer.writerow([row[c] for c in EMPLOYEE_TOTALS_COLUMNS])
        writer.writerow([])

        writer.writerow(["OVERRIDDEN SHIFTS"])
        writer.writerow(OVERRIDDEN_SHIFTS_COLUMNS)
        for row in overridden_rows:
            writer.writerow(overridden_shift_row_values(row))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct Clover dashboard-style CSV exports from API data.")
    parser.add_argument("--raw-run", default=None, help="Raw export run folder name under data/raw/ (default: latest)")
    parser.add_argument("--start", default=DEFAULT_START, help="Window start date, YYYY-MM-DD (Eastern), inclusive")
    parser.add_argument("--end", default=DEFAULT_END, help="Window end date, YYYY-MM-DD (Eastern), inclusive")
    parser.add_argument("--out", default=None, help="Output directory (default: data/generated_exports/<start>_to_<end>/)")
    args = parser.parse_args()

    try:
        config = load_config()
    except ConfigError as exc:
        print("Aborted: configuration error.")
        print(f"Reason: {exc}")
        return 1

    client = CloverClient(config)

    run_dir = RAW_ROOT / args.raw_run if args.raw_run else latest_raw_run()
    if not run_dir.exists():
        print(f"Raw export run not found: {run_dir}")
        return 1

    out_dir = Path(args.out) if args.out else DEFAULT_OUT_ROOT / f"{args.start}_to_{args.end}"
    cache_dir = DEFAULT_OUT_ROOT / "_api_cache"

    print(f"Raw export run: {run_dir}")
    print(f"Window: {args.start} to {args.end} (America/New_York)")
    print(f"Output: {out_dir}")

    start_ms, end_ms = window_bounds_ms(args.start, args.end)

    raw = RawData(run_dir)

    orders_in_window = [o for o in raw.orders if in_window(o.get("createdTime"), start_ms, end_ms)]
    payments_in_window = [p for p in raw.payments if in_window(p.get("createdTime"), start_ms, end_ms)]
    shifts_in_window = [s for s in raw.shifts if in_window(s.get("inTime"), start_ms, end_ms)]

    print(f"Orders in window: {len(orders_in_window)}")
    print(f"Payments in window: {len(payments_in_window)}")
    print(f"Shifts in window: {len(shifts_in_window)}")

    cache = ApiCache(cache_dir, "supplementary")

    print("Building Payments_RFOne.csv ...")
    payment_rows = build_payment_rows(client, raw, payments_in_window, ApiCache(cache_dir, "supplementary"))
    write_csv(out_dir / "Payments_RFOne.csv", PAYMENTS_COLUMNS, payment_rows)

    print("Building Orders_RFOne.csv ...")
    order_rows, unresolved_discount_orders = build_order_rows(
        client, raw, orders_in_window, ApiCache(cache_dir, "supplementary")
    )
    write_csv(out_dir / "Orders_RFOne.csv", ORDERS_COLUMNS, order_rows)

    print("Building LineItems_RFOne.csv (fetching per-order modifications; this issues one GET per order) ...")
    line_item_rows = build_line_item_rows(client, raw, orders_in_window, ApiCache(cache_dir, "supplementary"))
    write_csv(out_dir / "LineItems_RFOne.csv", LINE_ITEMS_COLUMNS, line_item_rows)

    print("Building clock_RFOne.csv ...")
    shifts_rows = build_shifts_rows(shifts_in_window, raw)
    totals_rows = build_employee_totals_rows(shifts_in_window, raw)
    overridden_rows = build_overridden_shifts_rows(shifts_in_window, raw)
    write_clock_csv(out_dir / "clock_RFOne.csv", shifts_rows, totals_rows, overridden_rows)

    print(f"Done. {len(payment_rows)} payments, {len(order_rows)} orders, {len(line_item_rows)} line items, "
          f"{len(shifts_rows)} shifts, {len(totals_rows)} employee totals, {len(overridden_rows)} overridden shifts.")
    if unresolved_discount_orders:
        print(f"Orders with a non-percentage (unresolved) discount component: {len(unresolved_discount_orders)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
