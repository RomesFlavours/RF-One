#!/usr/bin/env python
"""Final End-to-End Validation of RF-One Tips
(TASK_TIPS_END_TO_END_VALIDATION_001).

Exercises the full flow across TWO Restaurants (Winter Park, Mount Dora),
multiple Business Dates, a multi-role Distribution Rule set, all three
Tips payment modes, Restaurant-scoped Authority, the Clover reconciliation
gate, success/failure/retry/reversal, and (as a final phase) the Payment
Control web page itself via Flask's own test client.

IMPORTANT — Mercury sandbox declaration: this environment has no
`MERCURY_SANDBOX_API_TOKEN` configured (verified before writing this
script — `os.environ` carries none, no `.env`/credential file exists in
this repository), so no live network call to Mercury sandbox is possible
from this session. Every Mercury interaction below therefore uses
`_FakeMercuryClient` — the SAME fake this repository's own automated suite
already uses everywhere (`tips_payment_execution_validation.py`), itself
built to reproduce Mercury sandbox behaviors already empirically verified
against the real sandbox in prior work (e.g. the HTTP 409 duplicate-
idempotency-key behavior documented in `Tips Payment Execution.md`). This
is declared here exactly as explicitly permitted for the reversal scenario
by this task's own instructions, extended with the same transparency to
every Mercury-touching phase, since no credential is available to do
otherwise. Never a claim of a real sandbox call actually made this session.

Never contacts Clover or Mercury production. Rolls back / uses a disposable
database throughout.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

_DATA_STORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from sqlalchemy import select  # noqa: E402

from rfone_data_store import acting_identity_service, authority_service, models as m  # noqa: E402
from rfone_data_store.database import (  # noqa: E402
    cleanup_disposable_test_database_url, create_configured_engine, create_session_factory,
    redact_database_url, resolve_test_database_url, run_migrations_to_head,
)
from rfone_data_store.tips import (  # noqa: E402
    distribution_rule_service as rule_svc, payment_cycle_service as cycle_svc,
    payment_readiness as readiness_svc, payout_process as payout_svc, schedule_service as sched_svc,
)
from rfone_data_store.tips import scheduler as tips_scheduler  # noqa: E402
from rfone_data_store.tips_payment_execution_validation import _FakeMercuryClient  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 9, 1, tzinfo=UTC)


@dataclass
class ValidationResult:
    success: bool = True
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def _at(day: float, hour: int = 12) -> datetime:
    return T0 + timedelta(days=day, hours=hour)


# ---------------------------------------------------------------------------
# Fixture: one Restaurant with real CLOVER Location, Server/Host/Busser roles
# ---------------------------------------------------------------------------


def _build_restaurant(session, *, suffix: str, name: str):
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=f"E2E-{suffix}", name=f"{name} Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"E2E-{suffix}",
        name=f"{name} Location", currency="USD",
    )
    session.add(location)
    session.flush()
    restaurant = m.Restaurant(name=name, default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    area = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    session.add(area)
    session.flush()

    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    role_busser = m.RestaurantRole(restaurant_id=restaurant.id, name="Busser")
    session.add_all([role_server, role_host, role_busser])
    session.flush()

    def make_employee(source_id: str, name_: str, role) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id, source_employee_id=source_id,
            display_name=name_, system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        session.add(m.EmployeeAssignment(
            employee_id=emp.id, restaurant_id=restaurant.id, operational_area_id=area.id,
            restaurant_role_id=role.id, valid_from=_at(-300), valid_to=None, assignment_source="MANUAL",
        ))
        return emp

    server_a = make_employee(f"{suffix}-SRVA", "Server A", role_server)
    server_b = make_employee(f"{suffix}-SRVB", "Server B", role_server)
    host = make_employee(f"{suffix}-HOST", "Host", role_host)
    busser = make_employee(f"{suffix}-BUSS", "Busser", role_busser)

    # ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT (the engine's default) requires a
    # RECIPIENT Role's employee to have an active Shift at settlement time —
    # without this, `no_eligible_recipient_behavior=SOURCE_RETAINS` (also
    # the default) makes the Source Role retain 100%, which would silently
    # defeat this fixture's own §3 distribution assertions. A wide-open
    # Shift (clock_in long before T0, never clocked out) keeps every
    # employee eligible for the whole test window.
    for emp in (server_a, server_b, host, busser):
        session.add(m.Shift(employee_id=emp.id, clock_in=_at(-300), clock_out=None))
    session.commit()

    # §3 — one Source Role (Server) with MULTIPLE Recipient Roles (Host,
    # Busser), different percentages.
    rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"), effective_from=_at(-300),
        created_by="e2e",
    )
    rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_busser.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("5.0000"), effective_from=_at(-300),
        created_by="e2e",
    )
    session.commit()
    session.expire_all()

    return restaurant, location, source_system, {"server_a": server_a, "server_b": server_b, "host": host, "busser": busser}


def _make_order_with_tip(session, *, location, source_system, employee, tip_minor, order_suffix, business_date, order_time):
    order = m.Order(
        location_id=location.id, source_system_id=source_system.id, source_order_id=f"ORD-{order_suffix}",
        employee_id=employee.id, source_employee_id=employee.source_employee_id,
        created_at=order_time, business_date=business_date, state="locked", payment_state="PAID",
        currency="USD", total=10000,
    )
    session.add(order)
    session.flush()
    payment = m.Payment(
        order_id=order.id, source_system_id=source_system.id, source_payment_id=f"PAY-{order_suffix}",
        employee_id=employee.id, source_employee_id=employee.source_employee_id, created_at=order_time,
        amount=10000, result="SUCCESS", currency="USD",
    )
    session.add(payment)
    session.flush()
    session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
    session.commit()
    return order


def _link_recipient(session, employee, recipient_id, *, is_active=True):
    existing = session.scalars(
        select(m.EmployeeExternalPaymentAccount).where(
            m.EmployeeExternalPaymentAccount.employee_id == employee.id,
            m.EmployeeExternalPaymentAccount.is_active.is_(True),
        )
    ).first()
    if existing is not None:
        existing.is_active = False
    session.add(m.EmployeeExternalPaymentAccount(
        employee_id=employee.id, provider="MERCURY", provider_recipient_id=recipient_id, is_active=is_active,
    ))
    session.commit()


def _seed_reconciliation(session, *, location, source_system, now, fresh: bool, live_healthy: bool = True):
    live_finished = now - timedelta(seconds=10)
    session.add(m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=live_finished, finished_at=live_finished,
        status="COMPLETE" if live_healthy else "FAILED", mode="LIVE_SYNC",
        source_window_start=live_finished - timedelta(minutes=1), source_window_end=live_finished,
        notes="CLOVER_ACQUISITION mode=LIVE_SYNC",
    ))
    recon_finished = now - timedelta(seconds=5) if fresh else now - readiness_svc.DEFAULT_STALENESS_THRESHOLD - timedelta(minutes=1)
    session.add(m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=recon_finished, finished_at=recon_finished,
        status="COMPLETE", mode="RECONCILIATION",
        source_window_start=recon_finished - timedelta(minutes=1), source_window_end=recon_finished,
        notes="CLOVER_ACQUISITION mode=RECONCILIATION",
    ))
    session.commit()


def _seed_failed_reconciliation(session, *, location, source_system, now):
    session.add(m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=now - timedelta(seconds=5),
        finished_at=now - timedelta(seconds=5), status="FAILED", mode="RECONCILIATION",
        source_window_start=now - timedelta(minutes=1), source_window_end=now - timedelta(seconds=5),
        notes="CLOVER_ACQUISITION mode=RECONCILIATION; FAILED (simulated)",
    ))
    session.commit()


def run_validation(session_factory) -> tuple[ValidationResult, dict]:
    result = ValidationResult()
    with session_factory() as session:
        wp, wp_loc, wp_src, wp_emp = _build_restaurant(session, suffix="WP", name="Winter Park")
        md, md_loc, md_src, md_emp = _build_restaurant(session, suffix="MD", name="Mount Dora")

        # =====================================================================
        # §2 MULTI-DAY + §3 DISTRIBUTION — Winter Park, two Business Dates
        # =====================================================================
        bd1 = date(2026, 9, 5)
        bd2 = date(2026, 9, 6)
        _make_order_with_tip(session, location=wp_loc, source_system=wp_src, employee=wp_emp["server_a"], tip_minor=10000, order_suffix="WP-A1", business_date=bd1, order_time=_at(4, 11))
        _make_order_with_tip(session, location=wp_loc, source_system=wp_src, employee=wp_emp["server_b"], tip_minor=6000, order_suffix="WP-B1", business_date=bd1, order_time=_at(4, 12))
        _seed_reconciliation(session, location=wp_loc, source_system=wp_src, now=_at(4) + timedelta(hours=25), fresh=True)

        calc1 = payout_svc.run_calculation_now(session, restaurant_id=wp.id)
        session.commit()
        result.check("Day 1: calculation ran (Business Date 1)", calc1.ran and calc1.business_date == "2026-09-05")

        _make_order_with_tip(session, location=wp_loc, source_system=wp_src, employee=wp_emp["server_a"], tip_minor=4000, order_suffix="WP-A2", business_date=bd2, order_time=_at(5, 11))
        _seed_reconciliation(session, location=wp_loc, source_system=wp_src, now=_at(5) + timedelta(hours=25), fresh=True)
        calc2 = payout_svc.run_calculation_now(session, restaurant_id=wp.id)
        session.commit()
        result.check("Day 2: calculation ran (Business Date 2)", calc2.ran and calc2.business_date == "2026-09-06")

        entitlements = list(session.scalars(select(m.TipEntitlement).where(m.TipEntitlement.restaurant_id == wp.id)))
        by_emp_total = {}
        for e in entitlements:
            by_emp_total[e.employee_id] = by_emp_total.get(e.employee_id, 0) + e.payable_amount_minor
        total_gross = sum(e.gross_amount_minor for e in entitlements if e.employee_id in (wp_emp["server_a"].id, wp_emp["server_b"].id))
        total_payable = sum(by_emp_total.values())
        result.check(
            "§3 distribution: money is conserved — sum of all payable amounts equals total Server gross tips ($200.00)",
            total_gross == 20000 and total_payable == 20000,
        )
        result.check(
            "§3 distribution: Server A retains 85% across both days ($119.00 = $140 gross - 15%)",
            by_emp_total.get(wp_emp["server_a"].id) == 11900,
        )
        result.check("§3 distribution: Server B retains 85% ($51.00 = $60 gross - 15%)", by_emp_total.get(wp_emp["server_b"].id) == 5100)
        result.check("§3 distribution: Host (recipient role, no own orders) receives 10% of $200 = $20.00", by_emp_total.get(wp_emp["host"].id) == 2000)
        result.check("§3 distribution: Busser (second recipient role, SAME Source Role) receives 5% of $200 = $10.00", by_emp_total.get(wp_emp["busser"].id) == 1000)

        # =====================================================================
        # §4A MANUAL mode + §10 reconciliation gate — Winter Park
        # =====================================================================
        for emp, rid in ((wp_emp["server_a"], "WP-RECIP-SRVA"), (wp_emp["server_b"], "WP-RECIP-SRVB"), (wp_emp["host"], "WP-RECIP-HOST"), (wp_emp["busser"], "WP-RECIP-BUSS")):
            _link_recipient(session, emp, rid)

        cycle_wp = cycle_svc.start_payment_cycle(session, restaurant_id=wp.id, triggered_by="MANUAL")
        session.commit()
        result.check("§2 Payment Cycle aggregates ALL unpaid entitlements across BOTH Business Dates into one instruction per payee", len(list(session.scalars(select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.payment_cycle_id == cycle_wp.id)))) == 4)

        # §1 Authority — Person X authorized for BOTH restaurants; Person Y only Winter Park
        person_x = m.ActingIdentity(kind="HUMAN_USER", display_name="Person X (both restaurants)", is_active=True)
        person_y = m.ActingIdentity(kind="HUMAN_USER", display_name="Person Y (Winter Park only)", is_active=True)
        session.add_all([person_x, person_y])
        session.flush()
        authority_service.grant_authority(session, actor=person_x, domain="TIPS", action="APPROVE_AND_PAY", scope_type=m.SCOPE_RESTAURANT, scope_id=wp.id)
        authority_service.grant_authority(session, actor=person_x, domain="TIPS", action="APPROVE_AND_PAY", scope_type=m.SCOPE_RESTAURANT, scope_id=md.id)
        authority_service.grant_authority(session, actor=person_y, domain="TIPS", action="APPROVE_AND_PAY", scope_type=m.SCOPE_RESTAURANT, scope_id=wp.id)
        session.commit()
        result.check("§1 Authority: Person X CAN act on Winter Park", cycle_svc.can_approve_and_pay(session, acting_identity=person_x, restaurant_id=wp.id))
        result.check("§1 Authority: Person X CAN act on Mount Dora too (same person, two Restaurant-scoped grants)", cycle_svc.can_approve_and_pay(session, acting_identity=person_x, restaurant_id=md.id))
        result.check("§1 Authority: Person Y CAN act on Winter Park", cycle_svc.can_approve_and_pay(session, acting_identity=person_y, restaurant_id=wp.id))
        result.check("§1 Authority: Person Y is DENIED for Mount Dora — configurations stay Restaurant-scoped/separate", not cycle_svc.can_approve_and_pay(session, acting_identity=person_y, restaurant_id=md.id))

        client_wp = _FakeMercuryClient(available_balance=Decimal("100000.00"), recipient_behavior={
            "WP-RECIP-SRVA": "ok", "WP-RECIP-SRVB": "unconfigured", "WP-RECIP-HOST": "ok", "WP-RECIP-BUSS": "ok",
        })

        # §10 reconciliation gate: force STALE, prove Approve & Pay (MANUAL, Person Y) is blocked, NO Mercury call.
        _seed_reconciliation(session, location=wp_loc, source_system=wp_src, now=_at(6), fresh=False)
        calls_before = client_wp.create_transaction_calls
        blocked = False
        try:
            cycle_svc.approve_and_pay_cycle(session, cycle=cycle_wp, acting_identity=person_y, client=client_wp, source_account_id="acct-1", now=_at(6))
        except cycle_svc.PaymentNotReadyError:
            blocked = True
        result.check("§10 reconciliation STALE -> NOT READY -> Approve & Pay blocked", blocked)
        result.check("§10 blocked attempt made NO Mercury call, cycle stays OPEN", client_wp.create_transaction_calls == calls_before and cycle_wp.status == "OPEN")

        _seed_failed_reconciliation(session, location=wp_loc, source_system=wp_src, now=_at(6, 1))
        readiness_failed = readiness_svc.describe_payment_readiness(session, wp.id, now=_at(6, 1))
        result.check("§10 reconciliation FAILED -> NOT READY", not readiness_failed.ready and readiness_failed.reconciliation_status == "FAILED")

        _seed_reconciliation(session, location=wp_loc, source_system=wp_src, now=_at(6, 2), fresh=True)
        readiness_after_retry = readiness_svc.describe_payment_readiness(session, wp.id, now=_at(6, 2))
        result.check("§10 reconciliation success AFTER retry -> READY again", readiness_after_retry.ready)

        # §4A MANUAL: Person Y (Winter-Park-only) now approves — READY.
        approve_result = cycle_svc.approve_and_pay_cycle(session, cycle=cycle_wp, acting_identity=person_y, client=client_wp, source_account_id="acct-1", now=_at(6, 2))
        session.commit()
        result.check("§4A MANUAL: authorized human Approves & Pays once READY — cycle APPROVED", cycle_wp.status == "APPROVED")

        instructions_wp = {i.employee_id: i for i in session.scalars(select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.payment_cycle_id == cycle_wp.id))}

        # =====================================================================
        # §6 SUCCESS CASE — Server A
        # =====================================================================
        srv_a_instr = instructions_wp[wp_emp["server_a"].id]
        result.check("§6 success: instruction created and submitted to Mercury", srv_a_instr.provider_transaction_id is not None)
        result.check("§6 success: reached SENT (pending real postedAt)", srv_a_instr.status in ("SENT", "OUTCOME_VERIFIED"))
        client_wp.set_transaction_status(srv_a_instr.provider_transaction_id, status="sent", posted_at="2026-09-06T00:00:00Z")
        cycle_svc.refresh_outcomes_for_cycle(session, cycle_wp, client_wp)
        session.commit()
        result.check("§6 success: final state sent + postedAt -> OUTCOME_VERIFIED", srv_a_instr.status == "OUTCOME_VERIFIED")
        result.check("§6 success: its entitlements are linked/paid (tip_payment_instruction_id set)", all(e.tip_payment_instruction_id == srv_a_instr.id for e in entitlements if e.employee_id == wp_emp["server_a"].id))
        result.check("§6 success: NO Attention raised for the successful payee", srv_a_instr.attention_item_id is None)
        calls_before_resubmit = client_wp.create_transaction_calls
        no_resubmit = False
        try:
            from rfone_data_store.tips import payment_instruction as pi_svc
            pi_svc.submit_payment_instruction(session, srv_a_instr, client_wp, account_id="acct-1")
        except Exception:  # noqa: BLE001
            no_resubmit = True
        result.check("§6 success is NOT re-payable: submit_payment_instruction refuses an OUTCOME_VERIFIED instruction, no new Mercury call", no_resubmit or client_wp.create_transaction_calls == calls_before_resubmit)

        # =====================================================================
        # §7 FAILURE CASE — Server B (unconfigured recipient)
        # =====================================================================
        srv_b_instr = instructions_wp[wp_emp["server_b"].id]
        result.check("§7 failure: ONLY Server B failed", srv_b_instr.status == "NEEDS_ATTENTION")
        result.check("§7 failure: Host/Busser (other payees) proceeded normally, unaffected", instructions_wp[wp_emp["host"].id].status in ("SENT", "OUTCOME_VERIFIED") and instructions_wp[wp_emp["busser"].id].status in ("SENT", "OUTCOME_VERIFIED"))
        result.check("§7 failure: Attention created and routed", srv_b_instr.attention_item_id is not None)
        attention_b = session.get(m.AttentionItem, srv_b_instr.attention_item_id)
        result.check("§7 failure: routing resolved (resolution_path present or unresolved reason recorded)", attention_b is not None and (attention_b.resolution_path is not None or attention_b.routing_unresolved_reason is not None))
        result.check("§7 failure: no sensitive banking data in the Attention reason", attention_b is not None and "WP-RECIP-SRVB" not in (attention_b.reason or "") and "acct-1" not in (attention_b.reason or ""))
        result.check(
            "§7 failure: exactly one Attention item (no duplicate) for Server B's instruction",
            len(session.scalars(select(m.AttentionItem).where(m.AttentionItem.source_reference == f"TipPaymentInstruction:{srv_b_instr.id}")).all()) == 1,
        )

        # =====================================================================
        # §8 RETRY — fix Server B's recipient, retry ONLY that payee
        # =====================================================================
        srv_a_status_before_retry = srv_a_instr.status
        _link_recipient(session, wp_emp["server_b"], "WP-RECIP-SRVB-FIXED")
        client_wp._recipient_behavior["WP-RECIP-SRVB-FIXED"] = "ok"
        cycle_svc.retry_instruction(session, srv_b_instr, client_wp, source_account_id="acct-1")
        session.commit()
        result.check("§8 retry: the previously-failed payee now succeeded", srv_b_instr.status in ("SENT", "OUTCOME_VERIFIED"))
        result.check("§8 retry: the already-succeeded payee (Server A) was NOT re-paid/untouched", srv_a_instr.status == srv_a_status_before_retry and srv_a_instr.attention_item_id is None)
        prior_history_len = len(session.scalars(select(m.AttentionRoutingResolution).where(m.AttentionRoutingResolution.attention_item_id == attention_b.id)).all())
        attention_b.status = m.ATTENTION_STATUS_RESOLVED
        attention_b.resolved_at = _at(6, 3)
        attention_b.resolved_by_identity_id = person_y.id
        session.commit()
        result.check("§8 retry: Attention explicitly resolved once the cause was fixed (an explicit actor, never auto-resolved)", attention_b.status == m.ATTENTION_STATUS_RESOLVED and attention_b.resolved_by_identity_id == person_y.id)
        result.check("§8 retry: prior routing history preserved (not erased by resolution)", len(session.scalars(select(m.AttentionRoutingResolution).where(m.AttentionRoutingResolution.attention_item_id == attention_b.id)).all()) >= prior_history_len)

        # =====================================================================
        # §9 REVERSAL (declared: fake client, no real-sandbox reversal control
        # available in this session)
        # =====================================================================
        client_wp.set_transaction_status(srv_a_instr.provider_transaction_id, status="reversed")
        cycle_svc.refresh_outcomes_for_cycle(session, cycle_wp, client_wp)
        session.commit()
        result.check("§9 reversal (fake-client-simulated, declared): a later `reversed` observation reopens a verified Outcome to NEEDS_ATTENTION", srv_a_instr.status == "NEEDS_ATTENTION")
        result.check("§9 reversal: a NEW/reopened Attention item was raised (never silently dropped)", srv_a_instr.attention_item_id is not None)

        # =====================================================================
        # §4B AUTO WITH APPROVAL — Mount Dora
        # =====================================================================
        _make_order_with_tip(session, location=md_loc, source_system=md_src, employee=md_emp["server_a"], tip_minor=8000, order_suffix="MD-A1", business_date=date(2026, 9, 5), order_time=_at(4, 11))
        _seed_reconciliation(session, location=md_loc, source_system=md_src, now=_at(4) + timedelta(hours=25), fresh=True)
        calc_md = payout_svc.run_calculation_now(session, restaurant_id=md.id)
        session.commit()
        result.check("Mount Dora: independent calculation, own Restaurant-scoped Distribution Rules", calc_md.ran)

        sched_svc.set_payment_schedule(session, restaurant_id=md.id, mode=m.TIPS_SCHEDULE_MODE_AUTOMATIC, interval_days=7, mercury_source_account_id="acct-1", auto_approval_mode=m.TIPS_PAYMENT_AUTO_APPROVAL_MODE_WITH_APPROVAL, effective_from=_at(-200))
        session.commit()
        outcomes = tips_scheduler.run_due_payment_cycle_starts(session, now=_at(5, 1))
        session.commit()
        cycle_md = cycle_svc.get_open_cycle(session, md.id)
        result.check("§4B AUTO WITH APPROVAL: scheduler opened the cycle automatically", cycle_md is not None and cycle_md.status == "OPEN")
        client_md = _FakeMercuryClient(available_balance=Decimal("100000.00"), recipient_behavior={})
        _link_recipient(session, md_emp["server_a"], "MD-RECIP-SRVA")
        _link_recipient(session, md_emp["host"], "MD-RECIP-HOST")
        _link_recipient(session, md_emp["busser"], "MD-RECIP-BUSS")
        auto_outcomes = tips_scheduler.run_due_payment_cycle_auto_approvals(session, now=_at(5, 1), client=client_md)
        result.check("§4B AUTO WITH APPROVAL: the auto-approval tick NEVER touches this cycle — human step still required", cycle_md.status == "OPEN" and client_md.create_transaction_calls == 0)
        cycle_svc.approve_and_pay_cycle(session, cycle=cycle_md, acting_identity=person_x, client=client_md, source_account_id="acct-1", now=_at(5, 1))
        session.commit()
        result.check("§4B AUTO WITH APPROVAL: human (Person X, cross-Restaurant Authority) Approves & Pays — succeeds", cycle_md.status == "APPROVED")

        # =====================================================================
        # §4C AUTO WITHOUT APPROVAL — Mount Dora, second cycle, later date
        # =====================================================================
        _make_order_with_tip(session, location=md_loc, source_system=md_src, employee=md_emp["server_a"], tip_minor=3000, order_suffix="MD-A2", business_date=date(2026, 9, 12), order_time=_at(11, 11))
        _seed_reconciliation(session, location=md_loc, source_system=md_src, now=_at(11) + timedelta(hours=25), fresh=True)
        payout_svc.run_calculation_now(session, restaurant_id=md.id)
        session.commit()
        sched_svc.set_payment_schedule(session, restaurant_id=md.id, mode=m.TIPS_SCHEDULE_MODE_AUTOMATIC, interval_days=7, mercury_source_account_id="acct-1", auto_approval_mode=m.TIPS_PAYMENT_AUTO_APPROVAL_MODE_WITHOUT_APPROVAL, effective_from=_at(6))
        system_identity = acting_identity_service.get_or_create_system_identity(session)
        authority_service.grant_authority(session, actor=system_identity, domain="TIPS", action="APPROVE_AND_PAY", scope_type=m.SCOPE_RESTAURANT, scope_id=md.id)
        session.commit()
        # Opens the cycle directly via the same aggregation service the
        # scheduler itself calls (`start_payment_cycle`) — the "opens
        # automatically when due" polling mechanic was already exercised
        # above for cycle_md; this phase's own focus is AUTO WITHOUT
        # APPROVAL's auto-approval behavior, not re-proving due-ness a
        # second time (`is_due`'s own `last_triggered_at` comparison reads
        # `TipPaymentCycle.started_at`, which defaults to real wall-clock
        # time rather than this script's synthetic `now` — a pre-existing,
        # out-of-scope-to-fix testability property of `start_payment_cycle`
        # this validation works around rather than "fixing", per this
        # task's explicit no-refactor instruction).
        cycle_md2 = cycle_svc.start_payment_cycle(session, restaurant_id=md.id, now=_at(12, 1), triggered_by=m.TIP_PAYMENT_CYCLE_TRIGGER_AUTOMATIC)
        session.commit()

        _seed_reconciliation(session, location=md_loc, source_system=md_src, now=_at(12, 1), fresh=False)
        outcomes_stale = tips_scheduler.run_due_payment_cycle_auto_approvals(session, now=_at(12, 1), client=client_md)
        session.commit()
        outcome_stale = next((o for o in outcomes_stale if o.restaurant_id == md.id), None)
        result.check("§4C AUTO WITHOUT APPROVAL respects reconciliation: NOT approved while stale, no Mercury call, cycle stays OPEN", outcome_stale is not None and not outcome_stale.approved and cycle_md2.status == "OPEN")

        _seed_reconciliation(session, location=md_loc, source_system=md_src, now=_at(12, 2), fresh=True)
        outcomes_ready = tips_scheduler.run_due_payment_cycle_auto_approvals(session, now=_at(12, 2), client=client_md)
        session.commit()
        outcome_ready = next((o for o in outcomes_ready if o.restaurant_id == md.id), None)
        result.check("§4C AUTO WITHOUT APPROVAL: SYSTEM identity Approves & Pays automatically once READY, within its own Restaurant-scoped Authority grant", outcome_ready is not None and outcome_ready.approved and cycle_md2.status == "APPROVED" and cycle_md2.approved_by_identity_id == system_identity.id)

        # §11 security spot-check across everything built so far
        all_reasons = " ".join((a.reason or "") for a in session.scalars(select(m.AttentionItem)))
        result.check("§11 security: no provider recipient id ever appears in any Attention reason", "WP-RECIP" not in all_reasons and "MD-RECIP" not in all_reasons)
        result.check("§11 security: no account/routing identifiers anywhere in Attention reasons", "routing" not in all_reasons.lower() and "account_number" not in all_reasons.lower())

        session.commit()
        fixture_ids = {
            "wp_id": wp.id, "md_id": md.id, "cycle_wp_id": cycle_wp.id, "cycle_md_id": cycle_md.id,
            "person_x_id": person_x.id, "person_y_id": person_y.id,
        }
        return result, fixture_ids


def main() -> int:
    url = resolve_test_database_url("tips_end_to_end")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    try:
        result, fixture_ids = run_validation(session_factory)
    finally:
        engine.dispose()

    # Deliberately NOT cleaned up yet if backend phase passed — the UI phase
    # (test_tips_end_to_end_ui.py) re-opens this SAME database via the real
    # Flask app to verify Payment Control against this exact fixture.
    if result.success:
        print(f"DB_URL_FOR_UI_PHASE={url}")
    else:
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Tips End-to-End (backend) tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0
    print(f"Tips End-to-End (backend) tests: FAILURE ({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)")
    for d in result.checks_failed:
        print(f"  FAILED: {d}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
