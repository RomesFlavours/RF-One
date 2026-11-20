"""Three-way (Order vs Invoice vs Receiving) reconciliation — deterministic
quantity/identity comparison only.

Purchasing/BusinessRules.md, Rule 26 ("Three-Way Reconciliation") and Rule 33
("Reconciliation Produces Atomic Differences, Not a Boolean Result") are
implemented here exactly as documented: a fixed set of atomic differences
derived from simple comparisons, never collapsed into one boolean, and never
a probabilistic or fuzzy matching algorithm — TASK_PURCHASING_004 explicitly
scopes this task to "enough persistence and simple deterministic comparison
logic to demonstrate that the canonical model can support reconciliation,"
not a reconciliation engine.

`ReconciliationOutcome` is documented as derived, never persisted as
canonical truth (Purchasing/DataDictionary.md, "Persist Facts — Derive
Calculations") — this module is the single place that computes it; nothing
in `rfone_data_store/models.py` stores it as an authoritative column.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Illustrative, not a rigid exhaustive enum (Rule 33) — but kept as a
# constants module so callers/tests reference the same literal strings.
MATCH = "MATCH"
SHORT = "SHORT"
EXTRA = "EXTRA"
SUBSTITUTED = "SUBSTITUTED"
DAMAGED = "DAMAGED"
INVOICE_MISMATCH = "INVOICE_MISMATCH"
ORDER_MISMATCH = "ORDER_MISMATCH"
QUANTITY_DEVIATION = "QUANTITY_DEVIATION"


@dataclass(frozen=True)
class ReconciliationInput:
    """The atomic facts one reconciliation compares — never itself
    persisted; assembled on demand from Purchase Order Line, Purchase Line
    and Receiving Line rows by the repository layer."""

    order_quantity: Decimal | None = None
    invoice_quantity: Decimal | None = None
    received_quantity: Decimal | None = None
    damaged_quantity: Decimal | None = None
    # True when the Receiving Line has no related Purchase Order Line at all
    # (Purchasing/EntityDefinitions.md, "Receiving Line" — Extra/Unexpected
    # Item, by definition).
    is_extra_item: bool = False
    # True when the item identity actually received/invoiced differs from
    # the item identity ordered (e.g. different SupplierProductId) — a
    # simple identity comparison, never inferred/guessed (Rule 26, examples
    # C and D).
    identity_substituted_vs_order: bool = False
    identity_substituted_vs_invoice: bool = False


def compute_reconciliation_outcome(inputs: ReconciliationInput) -> list[str]:
    """Returns the atomic differences for one comparison point (Rule 33).

    Order is deterministic and stable across calls for the same inputs, but
    the returned list is not sorted for meaning — callers should treat it as
    a set of concurrent facts, not a priority-ordered result.
    """

    if inputs.is_extra_item:
        return [EXTRA]

    outcomes: list[str] = []

    if (
        inputs.order_quantity is not None
        and inputs.invoice_quantity is not None
        and inputs.order_quantity != inputs.invoice_quantity
    ):
        outcomes.append(ORDER_MISMATCH)

    if inputs.identity_substituted_vs_order or inputs.identity_substituted_vs_invoice:
        outcomes.append(SUBSTITUTED)
        if inputs.identity_substituted_vs_invoice:
            outcomes.append(INVOICE_MISMATCH)

    # Invoice vs Receiving is the preferred quantity comparison when an
    # Invoice line exists; Order vs Receiving is the fallback when no
    # Invoice line is known yet (goods may arrive before the Invoice,
    # Purchasing/Workflow.md, Step 10).
    reference_quantity = inputs.invoice_quantity if inputs.invoice_quantity is not None else inputs.order_quantity
    if reference_quantity is not None and inputs.received_quantity is not None:
        if inputs.received_quantity < reference_quantity:
            outcomes.append(SHORT)
        elif inputs.received_quantity > reference_quantity:
            outcomes.append(QUANTITY_DEVIATION)

    if inputs.damaged_quantity is not None and inputs.damaged_quantity > 0:
        outcomes.append(DAMAGED)

    if not outcomes:
        outcomes.append(MATCH)

    return outcomes


def describe_outcome(outcomes: list[str], inputs: ReconciliationInput) -> str:
    """A short, human-readable snapshot for `PurchasingAlert.reconciliation_context`
    — descriptive only, never re-read as authoritative (see that column's
    docstring in `models.py`)."""

    parts = [
        f"order={inputs.order_quantity}",
        f"invoiced={inputs.invoice_quantity}",
        f"received={inputs.received_quantity}",
    ]
    if inputs.damaged_quantity:
        parts.append(f"damaged={inputs.damaged_quantity}")
    return f"{'/'.join(outcomes)}: {', '.join(parts)}"
