"""Centralized date/time and monetary conversion for dashboard-style exports.

Clover API timestamps are epoch milliseconds (UTC). The Clover dashboard
exports display them in the merchant's local Eastern time, DST-aware
(EDT/EST), in a handful of different textual layouts. This module is the
single place that performs both kinds of conversion so every export module
formats dates/money identically.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

MERCHANT_TIMEZONE = ZoneInfo("America/New_York")


def round_half_up_cents(cents: float) -> int:
    """Round a fractional cents value (e.g. a tax or discount apportionment
    computed from a percentage) to the nearest integer cent, half rounding
    up — matching the rounding observed in Clover's dashboard exports
    (e.g. 29.00 * 0.065 = 1.885 -> 1.89, not banker's-rounding's 1.88)."""
    return int(Decimal(str(cents)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_percentage(pct: float) -> str:
    """50 -> "50", 18.5 -> "18.5" — matches the dashboard's undecorated
    percentage text in Discounts-style descriptive columns."""
    if pct == int(pct):
        return str(int(pct))
    return str(pct)


def to_eastern(epoch_ms: int | None) -> datetime | None:
    """Convert an epoch-millisecond timestamp to an aware Eastern datetime."""
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=MERCHANT_TIMEZONE)


def format_dashboard_datetime(epoch_ms: int | None) -> str:
    """"23-Aug-2026 09:34 PM EDT" — used by Payment Date / Order Date / Line Item Date."""
    dt = to_eastern(epoch_ms)
    if dt is None:
        return ""
    return dt.strftime("%d-%b-%Y %I:%M %p %Z")


def format_clock_date(epoch_ms: int | None) -> str:
    """"18-Aug-2026" — used by the Clock export's date columns."""
    dt = to_eastern(epoch_ms)
    if dt is None:
        return ""
    return dt.strftime("%d-%b-%Y")


def format_clock_time(epoch_ms: int | None) -> str:
    """"08:50:37 AM" — used by the Clock export's time columns (includes seconds,
    unlike format_dashboard_datetime which does not)."""
    dt = to_eastern(epoch_ms)
    if dt is None:
        return ""
    return dt.strftime("%I:%M:%S %p")


def elapsed_hours_str(start_ms: int | None, end_ms: int | None) -> str:
    """Elapsed hours between two epoch-millisecond timestamps, 2 decimals,
    matching the Clock export's "Elapsed Hours" / "*Elapsed Hours" columns."""
    if start_ms is None or end_ms is None:
        return ""
    hours = (end_ms - start_ms) / 1000 / 3600
    return f"{hours:.2f}"


def cents_to_amount_str(cents: int | float | None) -> str:
    """13206 (API minor units) -> "132.06" (dashboard CSV decimal string).

    Returns "" (not "0.00") when `cents` is None, to preserve the
    missing-vs-zero distinction the source data may carry. Callers decide
    whether a missing value should be defaulted to 0 based on demonstrated
    dashboard semantics for that specific column (see CLOVER_EXPORT_MAPPING.md).
    """
    if cents is None:
        return ""
    return f"{cents / 100:.2f}"


def negate_cents_to_amount_str(cents: int | float | None) -> str:
    """Same as cents_to_amount_str but negated, for discount-style columns
    the dashboard displays as negative (e.g. Line Items "Total Discount")."""
    if cents is None:
        return ""
    return f"{-cents / 100:.2f}"
