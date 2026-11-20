"""Labor Cost query/service (TASK_PAYROLL_001 §31, `Labor Cost.md`).

Every total here is computed from atomic persisted facts at query time —
`payroll_employer_cost_total`-shaped columns are never persisted anywhere in
the schema (see `rfone_data_store/models.py`, Payroll section).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


@dataclass
class EmployeeLaborCost:
    employee_payroll_result_id: int
    employee_id: int
    employer_paid_earnings_minor: int
    employer_liabilities_minor: int
    payment_amount_minor: int | None

    @property
    def payroll_employer_cost_minor(self) -> int:
        # Payroll Employer Cost = employer-paid earnings + employer-side
        # liabilities (Labor Cost.md). Nothing else ever contributes — in
        # particular, no employee-withholding amount, because this schema
        # has no such table to reference in the first place.
        return self.employer_paid_earnings_minor + self.employer_liabilities_minor


@dataclass
class PayrollRunLaborCost:
    payroll_run_id: int
    per_employee: list[EmployeeLaborCost] = field(default_factory=list)

    @property
    def total_employer_paid_earnings_minor(self) -> int:
        return sum(e.employer_paid_earnings_minor for e in self.per_employee)

    @property
    def total_employer_liabilities_minor(self) -> int:
        return sum(e.employer_liabilities_minor for e in self.per_employee)

    @property
    def total_payroll_employer_cost_minor(self) -> int:
        return sum(e.payroll_employer_cost_minor for e in self.per_employee)

    @property
    def total_payment_amount_minor(self) -> int:
        return sum(e.payment_amount_minor or 0 for e in self.per_employee)


def compute_employee_labor_cost(result: "m.EmployeePayrollResult") -> EmployeeLaborCost:
    employer_paid_earnings = sum(
        f.amount_minor for f in result.earning_facts if f.paid_to_employee
    )
    employer_liabilities = sum(f.amount_minor for f in result.liability_facts)
    payment_amounts = [f.payment_amount_minor for f in result.payment_facts]
    payment_amount = sum(payment_amounts) if payment_amounts else None
    return EmployeeLaborCost(
        employee_payroll_result_id=result.id,
        employee_id=result.employee_id,
        employer_paid_earnings_minor=employer_paid_earnings,
        employer_liabilities_minor=employer_liabilities,
        payment_amount_minor=payment_amount,
    )


def compute_payroll_run_labor_cost(session: Session, payroll_run_id: int) -> PayrollRunLaborCost:
    results = session.scalars(
        select(m.EmployeePayrollResult).where(
            m.EmployeePayrollResult.payroll_run_id == payroll_run_id
        )
    ).all()
    return PayrollRunLaborCost(
        payroll_run_id=payroll_run_id,
        per_employee=[compute_employee_labor_cost(r) for r in results],
    )
