"""Service-attribution boundary (task §5-6).

Never assume `Payment.employee` or `Order.employee` is the service owner —
those are POS-operational associations, not universal service-ownership
semantics. The engine resolves service responsibility exclusively through a
`ServiceAttributionResolver`, injected by the caller. The concrete
resolution strategy is Restaurant/Profile/source configuration, never
hard-coded Tips semantics.

`OrderEmployeeServiceAttributionResolver` (TASK_TIPS_004) is the first real
resolver: built entirely from evidence the canonical Sales model already
contains (`Order.employee_id`, cross-checked against `Payment.employee_id`)
— it is a generic, provider-independent resolution strategy, not a Rome's
Flavours-specific mapping (no Rome's Flavours identifier, name, or
percentage appears anywhere in this module). `NullServiceAttributionResolver`
and `StaticServiceAttributionResolver` remain the safe-default and
synthetic-test resolvers, respectively.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

RESOLVED = "RESOLVED"
UNRESOLVED = "UNRESOLVED"
AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ServiceAttributionResult:
    status: str  # RESOLVED | UNRESOLVED | AMBIGUOUS
    employee_ids: list[int] = field(default_factory=list)
    detail: str | None = None


class ServiceAttributionResolver:
    """Abstract service-attribution boundary. A concrete subclass decides,
    for a given Order, which Employee(s) are responsible for the service it
    represents — RESOLVED (one or more employees), UNRESOLVED (cannot be
    determined), or AMBIGUOUS (more than one candidate, no disambiguation
    rule). Never consults `Order.employee`/`Payment.employee` as if either
    were automatically the answer — a resolver is free to use them as one
    input among others, but that is the resolver's own configured decision,
    not something the engine assumes on its behalf.
    """

    def resolve(self, session: Session, order: "m.Order") -> ServiceAttributionResult:
        raise NotImplementedError


class NullServiceAttributionResolver(ServiceAttributionResolver):
    """The safe default when no Restaurant-specific service-attribution
    configuration exists yet — always UNRESOLVED, never guesses. This is
    what read-only validation against current RF-One data uses (task §24),
    since Rome's Flavours has no service-attribution configuration yet.
    """

    def resolve(self, session: Session, order: "m.Order") -> ServiceAttributionResult:
        return ServiceAttributionResult(
            status=UNRESOLVED,
            employee_ids=[],
            detail="No service-attribution configuration is available for this Restaurant.",
        )


class StaticServiceAttributionResolver(ServiceAttributionResolver):
    """Synthetic, test-only resolver (task §6: "may provide resolver
    abstractions and synthetic test resolvers without inventing Rome's
    Flavours mappings"). The caller supplies an explicit, in-memory
    `{order_id: ServiceAttributionResult}` mapping — never sourced from real
    Restaurant configuration, never persisted, used only to exercise the
    engine's handling of RESOLVED/UNRESOLVED/AMBIGUOUS outcomes in tests.
    """

    def __init__(self, mapping: dict[int, ServiceAttributionResult]):
        self._mapping = mapping

    def resolve(self, session: Session, order: "m.Order") -> ServiceAttributionResult:
        result = self._mapping.get(order.id)
        if result is None:
            return ServiceAttributionResult(
                status=UNRESOLVED,
                employee_ids=[],
                detail=f"No configured service-attribution mapping for Order {order.id}.",
            )
        return result


class OrderEmployeeServiceAttributionResolver(ServiceAttributionResolver):
    """The first real, Restaurant-configurable service-attribution resolver
    (TASK_TIPS_004), built entirely from evidence the canonical Sales model
    already contains — no new server identity is introduced.

    **Evidence source and why it is authoritative:** `Order.employee_id` is
    the single-value field the source POS associates with an Order
    (`Restaurant Sales Model.md` §4, "the Employee associated with an
    Order") — for a table-service Order this is, in real operational
    practice, the server who opened/owns the table, and it is essentially
    always populated by ingestion (confirmed by direct inspection of the
    real Rome's Flavours data: 100% of real Orders carry a non-null
    `employee_id`). `TableServiceEmployee` (the M:N participation
    relationship `Restaurant Sales Model.md` §4 documents as the
    conceptually broader answer, and which explicitly rejects a mandatory
    `primary_server` field) is deliberately **not** used: Table Service
    reconstruction has never been ingested for the real Restaurant (0 rows
    in `table_services`/`table_service_employees`, confirmed by direct
    inspection) — building this resolver around it would resolve every real
    Order to UNRESOLVED, defeating the SERVICE_OWNER component entirely.

    **Corroboration, not blind trust:** `Order.employee` alone is never
    automatically the service owner (`Tip Allocation.md`, "service-
    attribution boundary"). This resolver therefore cross-checks it against
    every **economically valid** `Payment.employee_id` already recorded
    under the same Order — a second, independent POS observation:

    ```text
    Order.employee_id is NULL
      -> UNRESOLVED (no order-level evidence at all)
    Order.employee_id set, no disagreeing SUCCESS Payment.employee_id
      -> RESOLVED, employee_ids=[order.employee_id]
    Order.employee_id set, at least one SUCCESS Payment.employee_id disagrees
      -> AMBIGUOUS (two independent POS observations conflict; never
         guessed which is correct)
    ```

    **FAILED Payments are not attribution evidence (Product Owner decision,
    TASK_RESTAURANT_STRUCTURE_001).** A failed payment attempt is evidence
    that a payment was *attempted*, not authoritative evidence of who
    actually served the table — `Order.employee_id` remains the primary
    Sales evidence, and only a Payment whose `result` is the canonical
    economically-valid value `"SUCCESS"` (the same value `tips/engine.py`
    already treats as the sole economically valid Payment state, see
    `ISSUE_FAILED_PAYMENT_WITH_TIP`) may corroborate or contradict it. A
    `Payment.result` of `"FAIL"`, any other non-`"SUCCESS"` value, or `NULL`
    (result unknown) is excluded from the query below entirely — it can
    neither confirm the Service Owner, create `AMBIGUOUS`, override a valid
    resolution, nor turn an otherwise-RESOLVED Order into `UNRESOLVED`.

    **Location-correct by construction:** the resolved Employee always
    comes from this specific Order's own `employee_id` — the Order itself
    belongs to exactly one Location, so no cross-Location evidence can ever
    leak into this resolution.

    **Auditable:** every result carries a `detail` naming the exact
    evidence (or disagreement) that produced it.
    """

    def resolve(self, session: Session, order: "m.Order") -> ServiceAttributionResult:
        if order.employee_id is None:
            return ServiceAttributionResult(
                status=UNRESOLVED,
                employee_ids=[],
                detail=f"Order {order.id} has no employee_id recorded — no order-level "
                "service-attribution evidence exists.",
            )

        payment_employee_ids = set(
            session.scalars(
                select(m.Payment.employee_id).where(
                    m.Payment.order_id == order.id,
                    m.Payment.employee_id.is_not(None),
                    # Only economically valid Payments participate in
                    # SERVICE_OWNER evidence — a FAILED (or otherwise
                    # non-SUCCESS/unknown-result) payment attempt is not
                    # authoritative evidence of who served the table
                    # (Product Owner decision, TASK_RESTAURANT_STRUCTURE_001).
                    m.Payment.result == "SUCCESS",
                )
            ).all()
        )
        disagreeing = payment_employee_ids - {order.employee_id}
        if disagreeing:
            return ServiceAttributionResult(
                status=AMBIGUOUS,
                employee_ids=[],
                detail=(
                    f"Order {order.id}.employee_id={order.employee_id} disagrees with "
                    f"SUCCESS Payment.employee_id value(s) {sorted(disagreeing)} recorded under "
                    "the same Order — two independent POS observations conflict; RF-One never "
                    "guesses which is correct."
                ),
            )

        return ServiceAttributionResult(
            status=RESOLVED,
            employee_ids=[order.employee_id],
            detail=f"Order {order.id}.employee_id={order.employee_id}, corroborated by "
            f"{len(payment_employee_ids)} agreeing SUCCESS Payment employee reference(s).",
        )
