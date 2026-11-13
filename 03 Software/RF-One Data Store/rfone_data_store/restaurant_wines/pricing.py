"""Wine list price formula — an exact reproduction of `Wine.xlsb`.

The workbook's "Price Calculator" sheet computes, for a bottle cost C and a
Value V (the manual commercial appreciation of the wine by the clientele):

    E (multiplier)  = (1 / LOG(C, B)) * A               i.e. M = A / log_B(C)
    I (bottle raw)  = C * E * V
    H (glass raw)   = (E * C * V) / G
    bottle price    = ROUND_HALF_UP(I * V)              -> C x M x V^2
    glass price     = ROUND_HALF_UP(H * V)              -> C x M x V^2 / G

with ROUND_HALF_UP written in the sheet as
`IF(x - INT(x) < 0.5, INT(x), INT(x) + 1)`.

Value is deliberately applied twice (V^2): Product Owner decision. G is a
commercial divisor, not a physical yield. Each price is rounded on its own;
the glass price is never derived from the rounded bottle price.

The operations below follow the workbook's own order in binary floating
point, so a result that lands exactly on .5 rounds the way Excel rounds it.
Verified against every computed row of the workbook (128 of 128).

A cost that is missing or not greater than 1 has no valid price (log_B(C)
would be zero or negative): the result is None, never 0, a negative number
or a math error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

DEFAULT_COEFFICIENT_A = Decimal("1.3")
DEFAULT_LOG_BASE_B = Decimal("900")
DEFAULT_GLASS_DIVISOR_G = Decimal("3.5")


@dataclass(frozen=True)
class PricingParameters:
    coefficient_a: Decimal
    log_base_b: Decimal
    glass_divisor_g: Decimal

    def validate(self) -> None:
        if self.coefficient_a is None or self.coefficient_a <= 0:
            raise ValueError("Coefficient A must be greater than 0.")
        if self.log_base_b is None or self.log_base_b <= 1:
            raise ValueError("Logarithm base B must be greater than 1.")
        if self.glass_divisor_g is None or self.glass_divisor_g <= 0:
            raise ValueError("Glass divisor G must be greater than 0.")


@dataclass(frozen=True)
class CalculatedPrices:
    bottle: int | None
    glass: int | None


def round_half_up(x: float) -> int:
    """The workbook's `IF(x-INT(x)<0.5, INT(x), INT(x)+1)`."""
    whole = math.floor(x)
    return whole if x - whole < 0.5 else whole + 1


def cost_is_priceable(cost: Decimal | None) -> bool:
    return cost is not None and cost > 1


def calculate_prices(
    cost: Decimal | None, value: Decimal, parameters: PricingParameters, *, sells_by_glass: bool = True,
) -> CalculatedPrices:
    """Calculated bottle and glass prices (whole dollars) for `cost` and
    `value` under `parameters`; None where no valid price exists."""
    if value is None or value <= 0:
        raise ValueError("Value must be greater than 0.")
    parameters.validate()
    if not cost_is_priceable(cost):
        return CalculatedPrices(bottle=None, glass=None)

    c = float(cost)
    v = float(value)
    a = float(parameters.coefficient_a)
    b = float(parameters.log_base_b)
    g = float(parameters.glass_divisor_g)

    multiplier = (1 / (math.log(c) / math.log(b))) * a   # E
    bottle_raw = c * multiplier * v                      # I
    glass_raw = (multiplier * c * v) / g                 # H
    return CalculatedPrices(
        bottle=round_half_up(bottle_raw * v),
        glass=round_half_up(glass_raw * v) if sells_by_glass else None,
    )
