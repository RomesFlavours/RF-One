"""CLOVER_MULTISITE_001 — central per-company/per-site permissions and central
financial authorization (Product Owner rules of 2026-11-21).

Covers, on a throwaway SQLite built from the models:
- site reach (`site_selection.account_restaurant_ids`): existing ALL accesses
  keep every restaurant; SELECTED companies; RFGroup = every company without
  administrator rights; role profiles only in the person's member companies
  with a role opening the Domain; fail-closed restaurant without legal entity;
- `financial_authorization`: approver = signed-in account; restaurant access
  AND payment authorization both required; inactive site refused; grants and
  revocations recorded;
- Tips Approve & Pay and retry: allowed/denied, approver recorded, double
  approval refused, retry with the same authorization, never a duplicate payment.

Never touches AWS or a payment provider (fake Mercury client).

Usage:
    python -m unittest test_multisite_permissions
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from sqlalchemy import func, select  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import access_profiles as profiles  # noqa: E402
from rfone_data_store import financial_authorization as fin  # noqa: E402
from rfone_data_store import rfone_account_service as accounts  # noqa: E402
from rfone_data_store import rfone_web_session  # noqa: E402
from rfone_data_store import site_selection  # noqa: E402
from rfone_data_store.database import create_configured_engine, create_session_factory  # noqa: E402
from rfone_data_store.tips import payment_audit as audit  # noqa: E402
from rfone_data_store.tips import payment_cycle_service as cycle_svc  # noqa: E402
from rfone_data_store.tips import payment_instruction as pi_svc  # noqa: E402
from rfone_data_store import tips_payment_execution_validation as pv  # noqa: E402

TIPS = "TIPS"
PASSWORD = "a-long-enough-test-password"


class _Fixture(unittest.TestCase):
    """WP and MD restaurants with their legal entities and companies, plus a
    restaurant without legal entity."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db", prefix="multisite_perm_")
        os.close(fd)
        self.engine = create_configured_engine("sqlite:///" + self.path.replace(os.sep, "/"))
        m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        db = self.db
        self.le_wp = m.LegalEntity(legal_name="RF-Winter Park", status="ACTIVE")
        self.le_md = m.LegalEntity(legal_name="RF-Mount Dora", status="ACTIVE")
        db.add_all([self.le_wp, self.le_md])
        db.flush()
        self.wp = pv._make_restaurant(db, name="WP")
        self.md = pv._make_restaurant(db, name="MD")
        self.orphan = pv._make_restaurant(db, name="No legal entity")
        self.wp.legal_entity_id, self.md.legal_entity_id = self.le_wp.id, self.le_md.id
        db.flush()
        profiles.seed_companies(db)
        self.company = {c.name: c for c in db.scalars(select(profiles.CompanyContext))}
        db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        os.remove(self.path)

    # --- helpers -----------------------------------------------------------
    def account(self, name, *, tips=True, admin=False):
        a = accounts.create_account(self.db, username=name, display_name=name.title(), password=PASSWORD)
        a.is_admin = admin
        self.db.flush()
        if tips:
            accounts.set_domain_access(self.db, account_id=a.id, domain_code=TIPS, enabled=True, role_code=None)
        self.db.commit()
        return a

    def reach(self, account):
        return site_selection.account_restaurant_ids(self.db, account, TIPS)

    def grant_pay(self, account, *restaurants):
        fin.set_restaurant_grants(self.db, account=account, permission=fin.TIPS_APPROVE_AND_PAY,
                                  restaurant_ids=[r.id for r in restaurants])
        self.db.commit()

    def profile(self, account, company_name, *, with_tips_role=True):
        db = self.db
        area = m.OperationalArea(restaurant_id=None, name=f"Area {company_name} {account.id}", active=True)
        role = m.RestaurantRole(restaurant_id=None, name=f"Role {company_name} {account.id}", active=True)
        db.add_all([area, role])
        db.flush()
        db.add(m.OperationalAreaRole(operational_area_id=area.id, restaurant_role_id=role.id))
        if with_tips_role:
            db.add(profiles.RolePermission(role_id=role.id, domain_code=TIPS, scope="ALL", items=[]))
        member = profiles.CompanyMembership(account_id=account.id, company_id=self.company[company_name].id)
        db.add(member)
        db.flush()
        db.add(profiles.RoleProfileAssignment(membership_id=member.id, role_id=role.id, area_id=area.id))
        db.commit()


class MultisitePermissionsTest(_Fixture):
    # --- site reach --------------------------------------------------------
    def test_existing_access_keeps_every_restaurant(self):
        a = self.account("existing")
        self.assertEqual(self.reach(a), {self.wp.id, self.md.id, self.orphan.id})

    def test_selected_company_limits_the_restaurants(self):
        a = self.account("wponly")
        profiles.set_domain_companies(self.db, account_id=a.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["WP"].id])
        self.db.commit()
        self.assertEqual(self.reach(a), {self.wp.id})
        self.assertEqual([s.restaurant_id for s in site_selection.sites_for_account(self.db, a, TIPS)], [self.wp.id])
        self.assertFalse(site_selection.account_may_use_restaurant(self.db, a, TIPS, self.md.id))

    def test_rfgroup_reaches_every_company_but_is_not_admin(self):
        a = self.account("group")
        profiles.set_domain_companies(self.db, account_id=a.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["RFGroup"].id])
        self.db.commit()
        self.assertEqual(self.reach(a), {self.wp.id, self.md.id, self.orphan.id})
        self.assertFalse(rfone_web_session.account_is_domain_admin(self.db, a, TIPS))
        self.assertFalse(a.is_admin)

    def test_restaurant_without_legal_entity_fails_closed(self):
        a = self.account("md-only")
        profiles.set_domain_companies(self.db, account_id=a.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["MD"].id])
        self.db.commit()
        self.assertEqual(self.reach(a), {self.md.id})

    def test_no_domain_access_reaches_nothing(self):
        a = self.account("nobody", tips=False)
        self.assertEqual(self.reach(a), frozenset())
        self.assertEqual(site_selection.sites_for_account(self.db, a, TIPS), [])

    def test_selected_without_company_is_refused_and_disabling_clears(self):
        a = self.account("invalid")
        with self.assertRaises(ValueError):
            profiles.set_domain_companies(self.db, account_id=a.id, domain_code=TIPS,
                                          company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED, company_ids=[])
        self.db.rollback()
        profiles.set_domain_companies(self.db, account_id=a.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["WP"].id])
        accounts.set_domain_access(self.db, account_id=a.id, domain_code=TIPS, enabled=False, role_code=None)
        profiles.set_domain_companies(self.db, account_id=a.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["WP"].id])
        self.db.commit()
        self.assertEqual(profiles.domain_company_ids(self.db, a.id, TIPS), set())

    def test_role_profile_reaches_only_its_member_companies(self):
        a = self.account("profiled", tips=False)
        self.profile(a, "MD")                        # TIPS role in MD
        self.profile(a, "WP", with_tips_role=False)  # member of WP, but no TIPS role there
        token = profiles.company_context.set(self.company["MD"].id)
        try:
            self.assertTrue(rfone_web_session.account_may_enter_domain(self.db, a, TIPS))
            self.assertEqual(self.reach(a), {self.md.id})
        finally:
            profiles.company_context.reset(token)

    def test_role_profile_in_rfgroup_reaches_every_restaurant(self):
        a = self.account("group-profile", tips=False)
        self.profile(a, "RFGroup")
        token = profiles.company_context.set(self.company["RFGroup"].id)
        try:
            self.assertEqual(self.reach(a), {self.wp.id, self.md.id, self.orphan.id})
            self.assertFalse(rfone_web_session.account_is_domain_admin(self.db, a, TIPS))
        finally:
            profiles.company_context.reset(token)

    # --- financial authorization ------------------------------------------
    def test_payment_needs_restaurant_access_and_payment_authorization(self):
        both = self.account("both")
        self.grant_pay(both, self.wp)
        self.assertTrue(fin.decide(self.db, account=both, permission=fin.TIPS_APPROVE_AND_PAY,
                                   restaurant_id=self.wp.id).allowed)

        access_only = self.account("access-only")
        decision = fin.decide(self.db, account=access_only, permission=fin.TIPS_APPROVE_AND_PAY,
                              restaurant_id=self.wp.id)
        self.assertFalse(decision.allowed)
        self.assertIn("payment authorization", decision.reason)

        grant_only = self.account("grant-only")
        profiles.set_domain_companies(self.db, account_id=grant_only.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["WP"].id])
        self.grant_pay(grant_only, self.md)
        decision = fin.decide(self.db, account=grant_only, permission=fin.TIPS_APPROVE_AND_PAY,
                              restaurant_id=self.md.id)
        self.assertFalse(decision.allowed)
        self.assertIn("no access to this restaurant", decision.reason)

    def test_inactive_site_is_never_paid(self):
        a = self.account("inactive")
        self.grant_pay(a, self.md)
        location = self.db.get(m.Location, self.db.scalar(select(m.RestaurantLocation.location_id).where(
            m.RestaurantLocation.restaurant_id == self.md.id)))
        location.active = False
        self.db.commit()
        decision = fin.decide(self.db, account=a, permission=fin.TIPS_APPROVE_AND_PAY, restaurant_id=self.md.id)
        self.assertFalse(decision.allowed)
        self.assertIn("not active", decision.reason)

    def test_account_identity_is_stable_and_grants_are_audited(self):
        admin = self.account("admin", admin=True)
        a = self.account("payer")
        first = fin.acting_identity_for_account(self.db, a)
        self.assertEqual(first.id, fin.acting_identity_for_account(self.db, a).id)
        fin.set_restaurant_grants(self.db, account=a, permission=fin.TIPS_APPROVE_AND_PAY,
                                  restaurant_ids=[self.wp.id, self.md.id], granted_by_account=admin)
        self.db.commit()
        self.assertEqual(fin.granted_restaurant_ids(self.db, a, fin.TIPS_APPROVE_AND_PAY), {self.wp.id, self.md.id})
        grant = self.db.scalar(select(m.AuthorityGrant).where(m.AuthorityGrant.acting_identity_id == first.id,
                                                             m.AuthorityGrant.scope_id == self.md.id))
        self.assertEqual(grant.granted_by_identity_id, fin.acting_identity_for_account(self.db, admin).id)
        fin.set_restaurant_grants(self.db, account=a, permission=fin.TIPS_APPROVE_AND_PAY,
                                  restaurant_ids=[self.wp.id])
        self.db.commit()
        self.db.refresh(grant)
        self.assertIsNotNone(grant.revoked_at)
        self.assertEqual(fin.granted_restaurant_ids(self.db, a, fin.TIPS_APPROVE_AND_PAY), {self.wp.id})


class TipsPaymentAuthorizationTest(_Fixture):
    """Approve & Pay and retry through the account-bound gate."""

    def setUp(self):
        super().setUp()
        self.client = pv._FakeMercuryClient(available_balance=Decimal("100000.00"), recipient_behavior={})
        self.connector = pv._connector_for(self.client)
        location_id = self.db.scalar(select(m.RestaurantLocation.location_id).where(
            m.RestaurantLocation.restaurant_id == self.wp.id))
        location = self.db.get(m.Location, location_id)
        self.employee = m.Employee(location_id=location_id, source_system_id=location.source_system_id,
                                   source_employee_id="E1", display_name="Payee One", system_role="EMPLOYEE")
        self.db.add(self.employee)
        self.db.commit()
        pv._link_recipient(self.db, self.employee, "recipient-1")

    def cycle_with_instruction(self, restaurant=None, *, amount=1500):
        cycle = pv._open_cycle(self.db, restaurant_id=(restaurant or self.wp).id)
        instruction = m.TipPaymentInstruction(payment_cycle_id=cycle.id, employee_id=self.employee.id,
                                              amount_minor=amount, status=pi_svc.STATUS_READY)
        self.db.add(instruction)
        self.db.commit()
        return cycle, instruction

    def approve(self, account, cycle):
        identity = cycle_svc.account_payment_identity(self.db, account=account, restaurant_id=cycle.restaurant_id)
        result = cycle_svc.approve_and_pay_cycle(self.db, cycle=cycle, acting_identity=identity,
                                                 connector=self.connector, source_account_id="acct-1")
        self.db.commit()
        return result

    def retry(self, account, instruction):
        cycle = self.db.get(m.TipPaymentCycle, instruction.payment_cycle_id)
        identity = cycle_svc.account_payment_identity(self.db, account=account, restaurant_id=cycle.restaurant_id)
        outcome = cycle_svc.retry_instruction(self.db, instruction, self.connector, source_account_id="acct-1",
                                              acting_identity=identity)
        self.db.commit()
        return outcome

    def failed_after_approval(self):
        payer = self.account("payer")
        self.grant_pay(payer, self.wp)
        cycle, instruction = self.cycle_with_instruction()
        self.approve(payer, cycle)
        self.assertEqual(instruction.status, pi_svc.STATUS_SENT)
        return payer, cycle, instruction

    # --- Approve & Pay ----------------------------------------------------
    def test_approval_is_recorded_as_the_signed_in_account(self):
        payer = self.account("payer")
        self.grant_pay(payer, self.wp)
        cycle, instruction = self.cycle_with_instruction()
        self.approve(payer, cycle)
        self.assertEqual(cycle.status, m.TIP_PAYMENT_CYCLE_STATUS_APPROVED)
        self.assertEqual(cycle.approved_by_identity_id, fin.acting_identity_for_account(self.db, payer).id)
        self.assertEqual(self.client.create_transaction_calls, 1)

    def test_approval_denied_without_authorization_makes_no_call(self):
        cycle, instruction = self.cycle_with_instruction()
        for account in (self.account("no-grant"), None):
            with self.assertRaises(cycle_svc.ApproveAndPayError):
                cycle_svc.account_payment_identity(self.db, account=account, restaurant_id=self.wp.id)
        self.assertEqual(self.client.create_transaction_calls, 0)
        self.assertEqual(cycle.status, m.TIP_PAYMENT_CYCLE_STATUS_OPEN)

    def test_approval_denied_for_a_restaurant_outside_the_account_reach(self):
        payer = self.account("wp-payer")
        profiles.set_domain_companies(self.db, account_id=payer.id, domain_code=TIPS,
                                      company_scope=m.DOMAIN_COMPANY_SCOPE_SELECTED,
                                      company_ids=[self.company["WP"].id])
        self.grant_pay(payer, self.wp, self.md)
        with self.assertRaises(cycle_svc.ApproveAndPayError):
            cycle_svc.account_payment_identity(self.db, account=payer, restaurant_id=self.md.id)

    def test_second_approval_of_the_same_cycle_is_refused(self):
        payer, cycle, instruction = self.failed_after_approval()
        with self.assertRaises(cycle_svc.ApproveAndPayError):
            self.approve(payer, cycle)
        self.assertEqual(self.client.create_transaction_calls, 1)

    # --- retry ------------------------------------------------------------
    def test_retry_needs_the_same_authorization(self):
        payer, cycle, instruction = self.failed_after_approval()
        self.client.set_transaction_status(instruction.provider_transaction_id, status="failed")
        instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
        self.db.commit()
        stranger = self.account("stranger")  # Tips access, no payment authorization
        with self.assertRaises(cycle_svc.ApproveAndPayError):
            self.retry(stranger, instruction)
        # The service gate itself also refuses an identity without the authority.
        bare = fin.acting_identity_for_account(self.db, stranger)
        with self.assertRaises(cycle_svc.PaymentRetryError):
            cycle_svc.retry_instruction(self.db, instruction, self.connector, source_account_id="acct-1",
                                        acting_identity=bare)
        self.db.rollback()
        self.assertEqual(self.client.create_transaction_calls, 1)

    def test_retry_of_a_ready_instruction_of_an_open_cycle_is_refused(self):
        payer = self.account("payer")
        self.grant_pay(payer, self.wp)
        cycle, instruction = self.cycle_with_instruction()
        with self.assertRaises(cycle_svc.PaymentRetryError):
            self.retry(payer, instruction)
        self.assertEqual(self.client.create_transaction_calls, 0)

    def test_retry_of_a_paid_or_pending_payment_never_pays_twice(self):
        payer, cycle, instruction = self.failed_after_approval()
        with self.assertRaises(cycle_svc.PaymentRetryError):  # SENT: nothing failed
            self.retry(payer, instruction)
        # Marked as needing attention, but the provider shows it pending: still paid.
        self.client.set_transaction_status(instruction.provider_transaction_id, status="pending")
        instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
        self.db.commit()
        with self.assertRaisesRegex(cycle_svc.PaymentRetryError, "already paid"):
            self.retry(payer, instruction)
        self.db.commit()
        self.assertEqual(instruction.status, pi_svc.STATUS_SENT)
        self.assertEqual(self.client.create_transaction_calls, 1)

    def test_reversed_payment_is_not_resubmitted(self):
        payer, cycle, instruction = self.failed_after_approval()
        self.client.set_transaction_status(instruction.provider_transaction_id, status="reversed")
        instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
        self.db.commit()
        with self.assertRaisesRegex(cycle_svc.PaymentRetryError, "reversed"):
            self.retry(payer, instruction)
        self.assertEqual(self.client.create_transaction_calls, 1)

    def test_failed_payment_is_retried_once_and_audited(self):
        payer, cycle, instruction = self.failed_after_approval()
        self.client.set_transaction_status(instruction.provider_transaction_id, status="failed")
        instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
        self.db.commit()
        # Corrected recipient -> new idempotency key, one new provider call.
        self.db.execute(m.EmployeeExternalPaymentAccount.__table__.update().values(is_active=False))
        self.db.commit()
        pv._link_recipient(self.db, self.employee, "recipient-2")
        self.assertEqual(self.retry(payer, instruction), cycle_svc.RETRY_SUBMITTED)
        self.assertEqual(instruction.status, pi_svc.STATUS_SENT)
        self.assertEqual(self.client.create_transaction_calls, 2)
        retried = [e for e in audit.events_for_cycle(self.db, cycle.id) if e.event == m.TIP_PAYMENT_AUDIT_RETRIED]
        self.assertEqual([(e.actor_kind, e.account_id, e.outcome) for e in retried],
                         [(m.TIP_PAYMENT_AUDIT_ACTOR_ACCOUNT, payer.id, pi_svc.STATUS_SENT)])
        self.assertEqual(retried[0].payment_instruction_id, instruction.id)
        self.assertIsNotNone(retried[0].occurred_at)
        # A second click after success is refused: no third call.
        with self.assertRaises(cycle_svc.PaymentRetryError):
            self.retry(payer, instruction)
        self.assertEqual(self.client.create_transaction_calls, 2)

    def test_unknown_outcome_with_changed_recipient_is_not_resubmitted(self):
        payer = self.account("payer")
        self.grant_pay(payer, self.wp)
        cycle, instruction = self.cycle_with_instruction()
        self.approve(payer, cycle)
        # Simulate: the earlier attempt reached the provider but its answer was lost.
        instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
        instruction.failure_class = pi_svc.FAILURE_PROVIDER_UNAVAILABLE
        instruction.provider_transaction_id = None
        self.db.commit()
        self.db.execute(m.EmployeeExternalPaymentAccount.__table__.update().values(is_active=False))
        self.db.commit()
        pv._link_recipient(self.db, self.employee, "recipient-2")
        with self.assertRaisesRegex(cycle_svc.PaymentRetryError, "different recipient"):
            self.retry(payer, instruction)
        self.assertEqual(self.client.create_transaction_calls, 1)

    def test_unknown_outcome_same_recipient_is_deduplicated_by_the_provider(self):
        payer = self.account("payer")
        self.grant_pay(payer, self.wp)
        cycle, instruction = self.cycle_with_instruction()
        self.approve(payer, cycle)
        instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
        instruction.failure_class = pi_svc.FAILURE_PROVIDER_UNAVAILABLE
        instruction.provider_transaction_id = None
        self.db.commit()
        self.retry(payer, instruction)
        # Same idempotency key: the provider refuses a second payment.
        self.assertEqual(instruction.failure_class, pi_svc.FAILURE_DUPLICATE_PROTECTION)
        self.assertEqual(len(self.client._transactions_by_id), 1)


class TipsPaymentAuditTest(TipsPaymentAuthorizationTest):
    """Payment audit: account or system identity, date and time of preparation,
    approval, execution and retry (CLOVER_MULTISITE_001)."""

    def prepared_cycle(self, prepared_by=None, triggered_by="MANUAL"):
        # One unpaid entitlement, as the calculation would leave it (its own
        # creation is covered by tips_payment_execution_validation).
        from types import SimpleNamespace
        from unittest import mock
        unpaid = [SimpleNamespace(employee_id=self.employee.id, payable_amount_minor=1200,
                                  business_date=None, tip_payment_instruction_id=None)]
        with mock.patch.object(cycle_svc, "get_unpaid_entitlements", return_value=unpaid):
            cycle = cycle_svc.start_payment_cycle(self.db, restaurant_id=self.wp.id, triggered_by=triggered_by,
                                                  prepared_by=prepared_by)
        self.db.commit()
        self.assertIsNotNone(unpaid[0].tip_payment_instruction_id)
        return cycle

    def test_preparation_by_a_person_records_the_account_and_time(self):
        payer = self.account("payer")
        cycle = self.prepared_cycle(prepared_by=fin.acting_identity_for_account(self.db, payer))
        [event] = audit.events_for_cycle(self.db, cycle.id)
        self.assertEqual((event.event, event.actor_kind, event.account_id, event.actor_label),
                         (m.TIP_PAYMENT_AUDIT_PREPARED, m.TIP_PAYMENT_AUDIT_ACTOR_ACCOUNT, payer.id, "Payer"))
        self.assertIsNotNone(event.occurred_at)

    def test_automatic_preparation_records_the_system_identity(self):
        cycle = self.prepared_cycle(triggered_by="AUTOMATIC")
        [event] = audit.events_for_cycle(self.db, cycle.id)
        self.assertEqual((event.event, event.actor_kind, event.account_id),
                         (m.TIP_PAYMENT_AUDIT_PREPARED, m.TIP_PAYMENT_AUDIT_ACTOR_SYSTEM, None))
        self.assertIsNotNone(event.acting_identity_id)

    def test_approval_and_execution_are_audited_per_instruction(self):
        payer = self.account("payer")
        self.grant_pay(payer, self.wp)
        cycle, instruction = self.cycle_with_instruction()
        self.approve(payer, cycle)
        events = [(e.event, e.actor_kind, e.account_id, e.payment_instruction_id, e.outcome)
                  for e in audit.events_for_cycle(self.db, cycle.id)]
        self.assertEqual(events, [
            (m.TIP_PAYMENT_AUDIT_APPROVED, m.TIP_PAYMENT_AUDIT_ACTOR_ACCOUNT, payer.id, None,
             m.TIP_PAYMENT_CYCLE_STATUS_APPROVED),
            (m.TIP_PAYMENT_AUDIT_EXECUTED, m.TIP_PAYMENT_AUDIT_ACTOR_ACCOUNT, payer.id, instruction.id,
             pi_svc.STATUS_SENT),
        ])

    def test_refused_approval_leaves_no_audit_row(self):
        cycle, instruction = self.cycle_with_instruction()
        bare = fin.acting_identity_for_account(self.db, self.account("no-grant"))
        with self.assertRaises(cycle_svc.ApproveAndPayError):
            cycle_svc.approve_and_pay_cycle(self.db, cycle=cycle, acting_identity=bare,
                                            connector=self.connector, source_account_id="acct-1")
        self.db.rollback()
        self.assertEqual(audit.events_for_cycle(self.db, cycle.id), [])

    def test_refused_retry_is_audited_without_a_payment(self):
        payer, cycle, instruction = self.failed_after_approval()
        with self.assertRaises(cycle_svc.PaymentRetryError):
            self.retry(payer, instruction)
        self.db.commit()  # as the Payment Control route does after a refused retry
        retried = [e for e in audit.events_for_cycle(self.db, cycle.id) if e.event == m.TIP_PAYMENT_AUDIT_RETRIED]
        self.assertEqual([(e.account_id, e.outcome) for e in retried], [(payer.id, "REFUSED")])
        self.assertIn("no failed payment", retried[0].detail)
        self.assertEqual(self.client.create_transaction_calls, 1)

    def test_system_approval_is_recorded_as_system(self):
        from rfone_data_store import acting_identity_service
        from rfone_data_store.authority_service import grant_authority
        system = acting_identity_service.get_or_create_system_identity(self.db)
        grant_authority(self.db, actor=system, domain=TIPS, action="APPROVE_AND_PAY",
                        scope_type=m.SCOPE_RESTAURANT, scope_id=self.wp.id)
        cycle, instruction = self.cycle_with_instruction()
        cycle_svc.approve_and_pay_cycle(self.db, cycle=cycle, acting_identity=system,
                                        connector=self.connector, source_account_id="acct-1")
        self.db.commit()
        kinds = {(e.event, e.actor_kind, e.account_id) for e in audit.events_for_cycle(self.db, cycle.id)}
        self.assertEqual(kinds, {(m.TIP_PAYMENT_AUDIT_APPROVED, m.TIP_PAYMENT_AUDIT_ACTOR_SYSTEM, None),
                                 (m.TIP_PAYMENT_AUDIT_EXECUTED, m.TIP_PAYMENT_AUDIT_ACTOR_SYSTEM, None)})


if __name__ == "__main__":
    unittest.main()
