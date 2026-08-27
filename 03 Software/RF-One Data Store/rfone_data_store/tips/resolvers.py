"""Service-attribution boundary (task §5-6).

Never assume `Payment.employee` or `Order.employee` is the service owner —
those are POS-operational associations, not universal service-ownership
semantics. The engine resolves service responsibility exclusively through a
`ServiceAttributionResolver`, injected by the caller. The concrete
resolution strategy is Restaurant/Profile/source configuration, never
hard-coded Tips semantics — this module provides only the abstraction and
synthetic, test-only resolvers, never a Rome's Flavours mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
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
