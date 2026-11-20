#!/usr/bin/env python
"""Provisional WHYs — the only exception to BANK_WHY_REQUIRES_WHAT_001
(Product Owner decisions 74-76 and 79, 2026-10-24).

Exactly the listed WHYs (Online Purchase – Unidentified, Cash / Check
Deposit, Withdrawal), in the "Provisional" group and with no WHAT, may be
assigned without a WHAT. Every other WHY without a WHAT is still a draft.

Runs on a throwaway database. Never touches AWS or a real bank file.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import classification, why_what
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{detail}]"))

    url = resolve_test_database_url("bank_provisional_why")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            group = m.BankReasonGroup(code=why_what.PROVISIONAL_GROUP_CODE, name="Provisional", display_order=99,
                                      active=True)
            other_group = s.scalars(select(m.BankReasonGroup).where(m.BankReasonGroup.code != "TO_REVIEW")).first()
            s.add(group)
            s.flush()

            def why(code, name, group_id, what_id=None):
                # The seed catalog of a fresh database may already hold one of these codes: moved aside.
                seed = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == code)).first()
                if seed is not None:
                    seed.code = code + "_SEED"
                    s.flush()
                r = classification.create_transaction_reason(s, code=code, name=name, accounting_classification_id=what_id)
                r.reason_group_id = group_id
                s.flush()
                return r

            withdrawal = why("WITHDRAWAL", "Withdrawal", group.id)
            deposit = why("CASH_CHECK_DEPOSIT", "Cash / Check Deposit", group.id)
            online = why("ONLINE_PURCHASE_UNIDENTIFIED", "Online Purchase – Unidentified", group.id)
            stranger = why("SOMETHING_ELSE", "Something else", group.id)
            misplaced = why("ONLINE_PURCHASE_UNIDENTIFIED_2", "Online purchase elsewhere", other_group.id)

            check("1. the three listed WHYs in the Provisional group are provisional",
                  all(why_what.is_provisional(s, r) for r in (withdrawal, deposit, online)))
            check("2. they can be assigned without a WHAT",
                  all(why_what.assignment_problem(s, r) is None for r in (withdrawal, deposit, online))
                  and why_what.require_what(s, withdrawal.id) is None)
            check("3. any other WHY without a WHAT in the same group is still a draft",
                  not why_what.is_provisional(s, stranger)
                  and why_what.assignment_problem(s, stranger) == why_what.NO_WHAT_MESSAGE)
            check("4. a WHY outside the Provisional group is never provisional",
                  not why_what.is_provisional(s, misplaced)
                  and why_what.assignment_problem(s, misplaced) == why_what.NO_WHAT_MESSAGE)
            what = next(a for a in s.scalars(select(m.BankAccountingClassification)) if why_what.valid_what(a))
            withdrawal.accounting_classification_id = what.id
            s.flush()
            check("5. a listed WHY that is given a WHAT is an ordinary WHY again",
                  not why_what.is_provisional(s, withdrawal) and why_what.require_what(s, withdrawal.id).id == what.id)
            s.rollback()
    finally:
        engine.dispose()
    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
