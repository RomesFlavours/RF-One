"""Business rules: discounts and totals, stock changes, orders, QBO export."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

import models as m

CENT = Decimal("0.01")


class RuleError(ValueError):
    """A request that breaks a business rule; the message is shown to the user."""


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def cases_label(bottles: int, per_case: int | None) -> str:
    """'2 cs + 6 btl' for 30 bottles of 12; just bottles when the case size is unknown."""
    if not per_case:
        return f"{bottles} btl"
    cases, rest = divmod(bottles, per_case)
    if cases and rest:
        return f"{cases} cs + {rest} btl"
    if cases:
        return f"{cases} cs"
    return f"{rest} btl"


def discount_amount(gross: Decimal, kind: str, value) -> Decimal:
    value = Decimal(value or 0)
    if value < 0:
        raise RuleError("A discount cannot be negative.")
    if kind == m.DISCOUNT_PERCENT:
        if value > 100:
            raise RuleError("A percentage discount cannot exceed 100%.")
        return money(gross * value / 100)
    return min(money(value), money(gross))


def line_totals(line) -> dict:
    gross = money(Decimal(line.bottles) * Decimal(line.unit_price))
    discount = discount_amount(gross, line.discount_type, line.discount_value)
    return {"gross": gross, "discount": discount, "net": gross - discount}


def order_totals(order: m.Order) -> dict:
    lines = [line_totals(line) for line in order.lines]
    subtotal = sum((t["net"] for t in lines), Decimal("0.00"))
    discount = discount_amount(subtotal, order.discount_type, order.discount_value)
    return {"lines": lines, "subtotal": subtotal, "line_discounts": sum((t["discount"] for t in lines), Decimal("0.00")),
            "order_discount": discount, "total": subtotal - discount,
            "bottles": sum(line.bottles for line in order.lines)}


def due_date(order: m.Order) -> date:
    return order.order_date + timedelta(days=order.terms_days or 0)


# ---------------------------------------------------------------- stock

def _stock_row(session: Session, wine_id: int, location_id: int) -> m.Stock:
    row = session.scalars(select(m.Stock).where(m.Stock.wine_id == wine_id, m.Stock.location_id == location_id)
                          .with_for_update()).first()
    if row is None:
        row = m.Stock(wine_id=wine_id, location_id=location_id, bottles=0)
        session.add(row)
        session.flush()
    return row


def move_stock(session: Session, wine_id: int, location_id: int, delta: int, reason: str, *,
               order_id: int | None = None, note: str | None = None, user_id: int | None = None) -> m.Stock:
    row = _stock_row(session, wine_id, location_id)
    if row.bottles + delta < 0:
        wine = session.get(m.Wine, wine_id)
        location = session.get(m.Location, location_id)
        raise RuleError(f"Not enough stock of {wine.display_name} at {location.name}: "
                        f"{row.bottles} bottles available, {-delta} needed.")
    row.bottles += delta
    session.add(m.StockMovement(wine_id=wine_id, location_id=location_id, bottles=delta, balance_after=row.bottles,
                                reason=reason, order_id=order_id, note=note, user_id=user_id))
    return row


def set_stock(session: Session, wine_id: int, location_id: int, new_count: int, note: str | None, user_id: int):
    if new_count < 0:
        raise RuleError("Stock cannot be negative.")
    if not (note or "").strip():
        raise RuleError("Write the reason for the adjustment (e.g. physical count, breakage, arrival).")
    row = _stock_row(session, wine_id, location_id)
    delta = new_count - row.bottles
    if delta:
        move_stock(session, wine_id, location_id, delta, m.MOVE_ADJUSTMENT, note=note.strip(), user_id=user_id)


# ---------------------------------------------------------------- orders

@dataclass
class LineInput:
    wine_id: int
    location_id: int
    bottles: int
    unit_price: Decimal
    discount_type: str
    discount_value: Decimal


def _allocation(lines) -> dict:
    out = defaultdict(int)
    for line in lines:
        out[(line.wine_id, line.location_id)] += line.bottles
    return out


def save_order(session: Session, order: m.Order, lines: list[LineInput], user_id: int) -> m.Order:
    """Create or change an open order. Stock moves only by the difference
    between the old and the new bottles per wine and location; the whole
    save is refused if any location does not have enough bottles."""
    if order.status != m.ORDER_OPEN:
        raise RuleError("A cancelled order cannot be changed.")
    if not lines:
        raise RuleError("Add at least one wine to the order.")
    for line in lines:
        if line.bottles <= 0:
            raise RuleError("Every line needs at least one bottle.")
        if line.unit_price < 0:
            raise RuleError("A price cannot be negative.")
        discount_amount(money(line.unit_price * line.bottles), line.discount_type, line.discount_value)
    is_new = order.id is None
    old = _allocation(order.lines) if not is_new else {}
    new = _allocation(lines)
    if is_new:
        session.add(order)
        session.flush()
    order.lines.clear()
    session.flush()
    for position, line in enumerate(lines):
        wine = session.get(m.Wine, line.wine_id)
        location = session.get(m.Location, line.location_id)
        if wine is None or location is None:
            raise RuleError("A wine or location in the order no longer exists.")
        order.lines.append(m.OrderLine(
            position=position, wine_id=wine.id, location_id=location.id, bottles=line.bottles,
            unit_price=money(line.unit_price), discount_type=line.discount_type,
            discount_value=Decimal(line.discount_value or 0), item_code=wine.item_code,
            description=f"{wine.display_name} ({wine.bottle_size_ml} ml)", bottles_per_case=wine.bottles_per_case))
    reason = m.MOVE_ORDER if is_new else m.MOVE_ORDER_CHANGE
    # Returns first, so a wine moved between locations is never blocked by itself.
    for key in sorted(set(old) | set(new), key=lambda k: new.get(k, 0) - old.get(k, 0)):
        delta = old.get(key, 0) - new.get(key, 0)
        if delta:
            move_stock(session, key[0], key[1], delta, reason, order_id=order.id, user_id=user_id)
    order_totals(order)  # validates the order discount against the final subtotal
    return order


def cancel_order(session: Session, order: m.Order, user_id: int) -> None:
    if order.status != m.ORDER_OPEN:
        raise RuleError("This order is already cancelled.")
    for (wine_id, location_id), bottles in _allocation(order.lines).items():
        move_stock(session, wine_id, location_id, bottles, m.MOVE_ORDER_CANCEL, order_id=order.id, user_id=user_id)
    order.status = m.ORDER_CANCELLED


# ---------------------------------------------------------------- QuickBooks Online

QBO_COLUMNS = ["InvoiceNo", "Customer", "InvoiceDate", "DueDate", "Terms", "Memo", "Item(Product/Service)",
               "ItemDescription", "ItemQuantity", "ItemRate", "ItemAmount"]


def qbo_invoices_csv(orders: list[m.Order]) -> str:
    """CSV in the layout of QuickBooks Online's invoice import
    (Settings > Import data > Invoices): one row per invoice line, rows of
    the same invoice share InvoiceNo. Discounts are negative 'Discount' lines,
    so quantity x rate always equals the amount."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(QBO_COLUMNS)
    for order in orders:
        totals = order_totals(order)
        head = [str(order.id), order.customer.name, order.order_date.strftime("%m/%d/%Y"),
                due_date(order).strftime("%m/%d/%Y"), f"Net {order.terms_days}",
                f"Order {order.id}" + (f" - PO {order.po_number}" if order.po_number else "")]
        for line, t in zip(order.lines, totals["lines"]):
            writer.writerow(head + [line.item_code, line.description, line.bottles, f"{money(line.unit_price)}",
                                    f"{t['gross']}"])
            if t["discount"]:
                writer.writerow(head + ["Discount", f"Discount on {line.item_code}", 1, f"-{t['discount']}",
                                        f"-{t['discount']}"])
        if totals["order_discount"]:
            writer.writerow(head + ["Discount", "Order discount", 1, f"-{totals['order_discount']}",
                                    f"-{totals['order_discount']}"])
    return out.getvalue()
