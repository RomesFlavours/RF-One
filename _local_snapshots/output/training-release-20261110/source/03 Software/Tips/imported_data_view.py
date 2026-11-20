"""IMPORTED_CLOVER_DATA_CONTROL_001 — the Tips "Imported Clover data" page as
a control tool: two summaries a person can hold next to Clover's own Orders
and Transactions reports, then the Order and Payment listings below them.

Read-only. Nothing here imports, synchronizes, corrects or writes; it only
reads the Orders, Payments, Payment Tips and Order Fees RF-One already holds.
Money is in minor units (cents), as everywhere in the data store.

Definitions (why each figure is what it is):

- Orders are selected by `Order.created_at` (Clover's "Order Date") inside
  the Location's local civil days; Payments by `Payment.created_at`
  (Clover's "Payment Date"). The two windows are independent, as they are in
  Clover's two reports.
- Completed / Incomplete. Clover's Orders API reports `paymentState: OPEN`
  on every Order of this merchant, paid or not, while Clover's own Orders
  report shows the same Orders as "Paid" (TASK_CLOVER_002 reference export,
  271/271). Clover's report therefore judges an Order by its balance, not by
  that state text. RF-One does the same: an Order is Completed when its
  successful Payments cover its total, otherwise Incomplete. Its displayed
  Payment State is "Paid", "Partially paid" or "Open" on the same basis.
- Payments: only `result == "SUCCESS"` counts (the Tips engine's certified
  rule, `distribution_engine._order_gross_tip_components`). Failed attempts
  stay visible in the listing but never enter a total.
- Payments total is the sum of the Payment amounts (Clover "Amount": tax and
  service charge included, voluntary tip excluded).
- Voluntary Tips come from Payment Tips; Gratuity from Order Fees (Clover's
  "Service Charge" line). They are never merged (CLOVER_TIPS_INGESTION_001).
- Gratuity is an Order-level amount. In the Payment view it is attributed
  once, to the Order's first successful Payment, so a split Order never
  counts it twice and adjacent periods never both count it.
- Gratuity is every Order Fee of the Order, exactly as the Tips engine
  counts it (`_order_gross_tip_components`), so this page and Calculate Tips
  cannot disagree on it. For this merchant every Order Fee is Clover's
  automatic "Gratuity" service charge.
- Taxes and Fees is what RF-One can prove: the Payments' own tax amount
  (Clover "Tax Amount", 100% matched in TASK_CLOVER_002). Gratuity stays out
  of it; RF-One holds no other fee.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from rfone_data_store import models as m

PAYMENT_SUCCESS = "SUCCESS"


def _chunks(values, size=500):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _payments_by_order(session, order_ids) -> dict[int, list]:
    by_order: dict[int, list] = defaultdict(list)
    for chunk in _chunks(order_ids):
        for p in session.scalars(select(m.Payment).where(m.Payment.order_id.in_(chunk))):
            by_order[p.order_id].append(p)
    return by_order


def _fees_by_order(session, order_ids) -> dict[int, list]:
    by_order: dict[int, list] = defaultdict(list)
    for chunk in _chunks(order_ids):
        for f in session.scalars(select(m.OrderFee).where(m.OrderFee.order_id.in_(chunk))):
            by_order[f.order_id].append(f)
    return by_order


def _tips_by_payment(session, payment_ids) -> dict[int, m.PaymentTip]:
    tips: dict[int, m.PaymentTip] = {}
    for chunk in _chunks(payment_ids):
        for t in session.scalars(select(m.PaymentTip).where(m.PaymentTip.payment_id.in_(chunk))):
            tips[t.payment_id] = t
    return tips


def _successful(payments) -> list:
    return sorted((p for p in payments if p.result == PAYMENT_SUCCESS), key=lambda p: (p.created_at, p.id))


def order_payment_state(total: int | None, paid: int) -> str:
    """What Clover's Orders report shows as "Order Payment State"."""
    if total is not None and paid >= total:
        return "Paid"
    return "Partially paid" if paid > 0 else "Open"


def build(session, *, location_ids_subq, start: datetime, end: datetime) -> dict:
    """Summaries and listings for one period. Always returns every figure,
    zero when the period holds no data."""
    orders = session.scalars(
        select(m.Order)
        .where(m.Order.location_id.in_(location_ids_subq), m.Order.created_at >= start, m.Order.created_at <= end)
        .order_by(m.Order.created_at)
    ).all()
    payments = session.scalars(
        select(m.Payment)
        .join(m.Order, m.Payment.order_id == m.Order.id)
        .where(m.Order.location_id.in_(location_ids_subq), m.Payment.created_at >= start, m.Payment.created_at <= end)
        .order_by(m.Payment.created_at)
    ).all()

    # Everything both views need, loaded once for every Order they touch.
    all_order_ids = {o.id for o in orders} | {p.order_id for p in payments}
    payments_of = _payments_by_order(session, all_order_ids)
    fees_of = _fees_by_order(session, all_order_ids)
    tips = _tips_by_payment(session, [p.id for p in payments])
    source_order_id = dict(
        session.execute(select(m.Order.id, m.Order.source_order_id).where(m.Order.id.in_(all_order_ids))).all()
    ) if all_order_ids else {}

    def gratuity(order_id) -> int:
        return sum((f.amount or 0) for f in fees_of.get(order_id, []))

    # --- Orders -----------------------------------------------------------
    orders_rows = []
    completed = incomplete = incomplete_value = 0
    for o in orders:
        ok = _successful(payments_of.get(o.id, []))
        paid = sum(p.amount for p in ok)
        state = order_payment_state(o.total, paid)
        if state == "Paid":
            completed += 1
        else:
            incomplete += 1
            incomplete_value += o.total or 0
        orders_rows.append({
            "source_order_id": o.source_order_id,
            "employee_id": o.source_employee_id,
            "total": o.total,
            "num_payments": len(ok),
            "gratuity_total": gratuity(o.id),
            # Settlement Time = the last successful Payment
            # (acquisition.get_order_settlement_time), read here from the
            # Payments already loaded instead of one query per Order.
            "settlement_time": ok[-1].created_at if ok else None,
            "state": o.state,
            "payment_state": state,
        })

    # --- Payments ---------------------------------------------------------
    payments_rows = []
    pay_count = pay_total = tips_total = gratuity_total = taxes_total = failed = 0
    for p in payments:
        tip = tips.get(p.id)
        tip_amount = (tip.amount or 0) if tip is not None else None
        success = p.result == PAYMENT_SUCCESS
        # Gratuity belongs to the Order: shown on its first successful
        # Payment only.
        first_ok = _successful(payments_of.get(p.order_id, []))
        grat = gratuity(p.order_id) if success and first_ok[0].id == p.id else 0
        if success:
            pay_count += 1
            pay_total += p.amount
            tips_total += tip_amount or 0
            gratuity_total += grat
            taxes_total += p.tax_amount_source or 0
        else:
            failed += 1
        payments_rows.append({
            "source_payment_id": p.source_payment_id,
            "source_order_id": source_order_id.get(p.order_id),
            "employee_id": p.source_employee_id,
            "amount": p.amount,
            "tip_amount": tip_amount,
            "gratuity": grat,
            "tip_plus_gratuity": (tip_amount or 0) + grat if success else None,
            "created_at": p.created_at,
            "result": p.result,
            "success": success,
        })

    return {
        "orders_summary": {
            "all": len(orders),
            "completed": completed,
            "incomplete": incomplete,
            "incomplete_value": incomplete_value,
        },
        "payments_summary": {
            "total": pay_total,
            "count": pay_count,
            "failed": failed,
            "voluntary_tips": tips_total,
            "gratuity": gratuity_total,
            "tips_plus_gratuity": tips_total + gratuity_total,
            "taxes_and_fees": taxes_total,
        },
        "orders_rows": orders_rows,
        "payments_rows": payments_rows,
    }


def empty() -> dict:
    """The same shape with every figure at zero — a period with no data, or
    no period chosen yet."""
    return {
        "orders_summary": {"all": 0, "completed": 0, "incomplete": 0, "incomplete_value": 0},
        "payments_summary": {
            "total": 0, "count": 0, "failed": 0, "voluntary_tips": 0, "gratuity": 0,
            "tips_plus_gratuity": 0, "taxes_and_fees": 0,
        },
        "orders_rows": [],
        "payments_rows": [],
    }
