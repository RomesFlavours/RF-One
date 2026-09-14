#!/usr/bin/env python
"""RF-One Tips Core 2.0 Process-First pilot — REAL Mercury Sandbox
end-to-end demonstration (TASK_TIPS_CORE2_PILOT §16).

Deliberately SEPARATE from the automated test suite (`test_tips_payment_
execution.py`, task §18's own requirement) — this script makes REAL HTTP
calls to `https://api-sandbox.mercury.com/api/v1/` using
`MERCURY_SANDBOX_API_TOKEN` from the environment, and is not run as part of
normal CI/test runs.

Demonstrates, against a disposable local SQLite database (NEVER the shared
operational database, NEVER production Mercury):

  1. Process Activation without a UI click (`readiness.describe_readiness`)
  2. a processable Business Date (synthetic fixture)
  3. the untouched deterministic Tip Distribution Engine
  4. idempotent Payment Instructions
  5. a real Mercury funding check
  6. at least one real, successful Mercury Sandbox payout
  7. real status readback
  8. Outcome observation
  9. one real, isolated failure (a sandbox "Banned Recipient")
 10. that failure recorded as NEEDS_ATTENTION with a priority/reason
 11. the OTHER payout unaffected by the failure
 12. resumption of ONLY the failed instruction, after relinking

The token is read from the environment only; this script never prints it,
never writes it to a file, and never touches `.env`.
"""

from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store import authority_service  # noqa: E402
from rfone_data_store.database import (  # noqa: E402
    cleanup_disposable_test_database_url, create_configured_engine, create_session_factory,
    redact_database_url, resolve_test_database_url,
)
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.technical.connectors.mercury.client import MercuryClient  # noqa: E402
from rfone_data_store.tips import payment_cycle_service as cycle_svc  # noqa: E402
from rfone_data_store.tips import payout_process as payout_svc  # noqa: E402
from rfone_data_store.tips import readiness as readiness_svc  # noqa: E402
from rfone_data_store.tips_payment_execution_validation import _build_base_fixture  # noqa: E402


def _link(session, employee, recipient_id: str) -> None:
    session.add(
        m.EmployeeExternalPaymentAccount(
            employee_id=employee.id, provider="MERCURY", provider_recipient_id=recipient_id, is_active=True,
        )
    )
    session.commit()


def main() -> int:
    if not os.environ.get("MERCURY_SANDBOX_API_TOKEN"):
        print("MERCURY_SANDBOX_API_TOKEN is not set — refusing to run (no fallback to any other token/endpoint).")
        return 1

    url = resolve_test_database_url("tips_sandbox_pilot_e2e")
    print(f"Disposable local database: {redact_database_url(url)}")
    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            client = MercuryClient()

            print("\n[1] Resolving real Mercury sandbox accounts/recipients...")
            accounts = [a for a in client.get_accounts() if a.type == "mercury" and a.status == "active" and a.kind == "checking" and a.available_balance > 0]
            if not accounts:
                print("No usable sandbox source account found.")
                return 1
            source_account_id = accounts[0].id
            print(f"    Source account selected (masked): {source_account_id[:4]}...{source_account_id[-2:]}")

            alex_rivera = client.find_recipient_by_name("Alex Rivera")
            banned = client.find_recipient_by_name("Banned Recipient")
            if alex_rivera is None or banned is None:
                print("Expected sandbox fixtures 'Alex Rivera' / 'Banned Recipient' not found.")
                return 1

            print("\n[2] Building a synthetic Business Date fixture (no Clover call)...")
            restaurant, server_ok, server_fail, make_order = _build_base_fixture(session, suffix="e2e")
            # Amounts deliberately distinct from any amount this pilot's own
            # earlier manual sandbox tests already sent to the SAME
            # recipient within the sandbox's 24h window — Mercury's own
            # duplicate-protection heuristic (task §5's "Mercury duplicate
            # protection is only a safety net") blocks same-recipient +
            # same-amount regardless of idempotencyKey, so reusing a prior
            # amount here would demonstrate that heuristic firing again
            # instead of a fresh successful payout.
            make_order(employee=server_ok, tip_minor=189, order_suffix="OK1")
            make_order(employee=server_fail, tip_minor=312, order_suffix="FAIL1")
            _link(session, server_ok, alex_rivera.id)
            _link(session, server_fail, banned.id)

            state = readiness_svc.describe_readiness(session, restaurant.id)
            print(f"    Process Activation readiness: business_date={state.business_date}, ready_to_calculate={state.ready_to_calculate}")

            print("\n[3] Running Calculation (readiness-gated, entitlements persisted)...")
            calc_result = payout_svc.run_calculation_now(session, restaurant_id=restaurant.id)
            session.commit()
            print(f"    {calc_result.entitlements_created} Tip Entitlement(s) persisted; ran={calc_result.ran}")

            print("\n[4] Starting a Payment Cycle (aggregates unpaid entitlements)...")
            cycle = cycle_svc.start_payment_cycle(session, restaurant_id=restaurant.id, triggered_by="MANUAL")
            session.commit()
            if cycle is None:
                print("Nothing unpaid to aggregate.")
                return 1

            approver = m.ActingIdentity(kind="HUMAN_USER", display_name="Sandbox Pilot Approver", is_active=True)
            session.add(approver)
            session.flush()
            authority_service.grant_authority(
                session, actor=approver, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
                action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_GLOBAL, scope_id=None,
            )
            session.commit()

            print("\n[5-8] Approve & Pay against the REAL Mercury Sandbox...")
            approve_result = cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle, acting_identity=approver, client=client, source_account_id=source_account_id,
            )
            session.commit()

            print(f"    Funding check: {approve_result.funding}")
            instructions = list(
                session.query(m.TipPaymentInstruction).filter_by(payment_cycle_id=cycle.id)
            )
            by_employee = {i.employee_id: i for i in instructions}
            ok_instruction = by_employee[server_ok.id]
            fail_instruction = by_employee[server_fail.id]

            print(f"    [OK payee]     status={ok_instruction.status} provider_status={ok_instruction.provider_status} failure_class={ok_instruction.failure_class} reason={ok_instruction.reason_for_failure}")
            print(f"    [FAIL payee]   status={fail_instruction.status} failure_class={fail_instruction.failure_class} priority={fail_instruction.priority}")
            print(f"    reason: {fail_instruction.reason_for_failure}")

            print("\n[9-11] Isolation check: the OK payout must be unaffected by the FAIL payee...")
            print(f"    OK payee unaffected: {ok_instruction.status != 'NEEDS_ATTENTION'}")

            print("\n[12] Resuming ONLY the failed instruction, after relinking to a valid recipient...")
            for row in session.query(m.EmployeeExternalPaymentAccount).filter_by(employee_id=server_fail.id, is_active=True):
                row.is_active = False
            session.commit()
            _link(session, server_fail, alex_rivera.id)
            cycle_svc.retry_instruction(session, fail_instruction, client, source_account_id=source_account_id)
            session.commit()
            print(
                f"    [FAIL payee after retry] status={fail_instruction.status} "
                f"provider_status={fail_instruction.provider_status} failure_class={fail_instruction.failure_class} "
                f"reason={fail_instruction.reason_for_failure}"
            )
            print(f"    OK payee still untouched: status={ok_instruction.status}")

            success = (
                ok_instruction.status in ("SENT", "OUTCOME_VERIFIED")
                and fail_instruction.status in ("SENT", "OUTCOME_VERIFIED")
            )
            print(f"\nSANDBOX PILOT E2E: {'PASS' if success else 'INCOMPLETE'}")
            return 0 if success else 1
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)


if __name__ == "__main__":
    sys.exit(main())
