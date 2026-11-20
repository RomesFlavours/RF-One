"""Payment Execution Provider guard (TASK_PAYROLL_002/003, `Payment
Execution.md`).

Payroll calculation != Payroll result acquisition != Payment execution. This
module implements the third layer's production-critical invariants: at most
one Payment Execution Provider ever executes a given `PayrollRun`'s payable
amounts, and a Run's provider is never inferred merely from which provider
supplied the underlying payroll result (TASK_PAYROLL_003 — the source of the
data does not determine who pays it).

`MERCURY_ACH` is a structural placeholder only — no function here calls a
Mercury API, sends an ACH instruction, or fabricates Mercury credentials or
sandbox behavior. It exists so the canonical model can represent a future
provider selection without a later Payroll redesign.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

ADP_DIRECT_DEPOSIT = "ADP_DIRECT_DEPOSIT"
MERCURY_ACH = "MERCURY_ACH"
PAYMENT_EXECUTION_PROVIDERS: tuple[str, ...] = (ADP_DIRECT_DEPOSIT, MERCURY_ACH)

UNKNOWN = "UNKNOWN"
EVIDENCED = "PAYMENT_EVIDENCED"


def assign_payment_execution_provider(payroll_run: "m.PayrollRun", provider: str) -> None:
    """Assign `payroll_run.payment_execution_provider`, enforcing the
    double-payment-prevention invariant (`Payment Execution.md`).

    - Rejects any value other than `ADP_DIRECT_DEPOSIT`/`MERCURY_ACH`.
    - Re-asserting the value already on the Run is a safe no-op.
    - Reassigning a Run already carrying a *different* non-null value raises
      `ValueError` — a Run's Payment Execution Provider is immutable once
      assigned. This is what makes it architecturally impossible for a Run
      already assigned to ADP to later be switched to Mercury (or vice
      versa) by any code path, including one written in the future.
    """
    if provider not in PAYMENT_EXECUTION_PROVIDERS:
        raise ValueError(
            f"Unsupported payment_execution_provider {provider!r} — must be one of "
            f"{PAYMENT_EXECUTION_PROVIDERS!r}."
        )

    current = payroll_run.payment_execution_provider
    if current is not None and current != provider:
        raise ValueError(
            f"PayrollRun {payroll_run.id} already has payment_execution_provider={current!r} — "
            f"refusing to reassign it to {provider!r}. A Payroll Run's payment executor is "
            "immutable once assigned (double-payment prevention, Payment Execution.md)."
        )

    payroll_run.payment_execution_provider = provider


def approved_provider_at(
    session: Session, *, restaurant_id: int, at: datetime
) -> str | None:
    """The Payment Execution Provider approved for this Restaurant's new
    PayrollRuns at instant `at`, per `PayrollExecutionConfiguration`
    (TASK_PAYROLL_003) — or `None` if no configuration row covers that
    instant. Never a fallback/default value: an unconfigured Restaurant
    simply has no approved provider yet, exactly like an unconfigured
    `TipPolicy` (`Tip Policy.md`, "never defaults to a universal
    percentage/role split").

    Where more than one configuration row could technically cover the same
    instant (a data-entry error this schema does not structurally forbid),
    the most recently started row wins, deterministically — never a random
    or ambiguous pick, mirroring `rfone_data_store/tips/engine.py`'s
    `_valid_policy_at` precedence convention."""
    candidates = session.scalars(
        select(m.PayrollExecutionConfiguration).where(
            m.PayrollExecutionConfiguration.restaurant_id == restaurant_id,
            m.PayrollExecutionConfiguration.valid_from <= at,
            (m.PayrollExecutionConfiguration.valid_to.is_(None))
            | (m.PayrollExecutionConfiguration.valid_to > at),
        )
    ).all()
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c.valid_from.timestamp(), c.id), reverse=True)
    return candidates[0].provider


def has_payment_execution_evidence(payroll_run: "m.PayrollRun") -> bool:
    """True when at least one `PayrollPaymentFact` exists under this Run's
    Employee results — i.e. the provider's own report evidences an actual
    payment. Never inferred from `PayrollRun.status` or from the mere
    presence of a `payment_execution_provider` assignment."""
    return any(
        employee_result.payment_facts for employee_result in payroll_run.employee_results
    )


def payment_execution_status(payroll_run: "m.PayrollRun") -> str:
    """Derived, never stored (`Payment Execution.md`, "Payment evidence vs.
    payment execution status"). `UNKNOWN` until `PayrollPaymentFact` evidence
    exists for at least one Employee in this Run — RF-One never fabricates a
    "paid" conclusion merely because Payroll was calculated or imported."""
    return EVIDENCED if has_payment_execution_evidence(payroll_run) else UNKNOWN
