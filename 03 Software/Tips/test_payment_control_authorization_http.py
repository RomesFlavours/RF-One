"""CLOVER_MULTISITE_001 — Payment Control acts only as the signed-in account
(Product Owner 2026-11-21): no approver can be picked on the page; Approve &
Pay and retry need restaurant access AND the account's payment authorization;
a second approval or a retry never pays twice.

Throwaway SQLite built from the models + Flask test client + fake payment
provider. Never touches AWS or Mercury.

Usage:
    python -m unittest test_payment_control_authorization_http
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="tips_payment_authz_http_")
os.close(_FD)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-payment-authz-test-secret"
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import access_profiles  # noqa: E402,F401  (registers its tables on the shared metadata)
from rfone_data_store.database import create_configured_engine  # noqa: E402

_engine = create_configured_engine(os.environ["RFONE_DATABASE_URL"])
m.Base.metadata.create_all(_engine)
_engine.dispose()

import app as tips_app  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import authority_service  # noqa: E402
from rfone_data_store import financial_authorization as fin  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import tips_payment_execution_validation as pv  # noqa: E402
from rfone_data_store.tips import payment_instruction as pi_svc  # noqa: E402
from tips_test_session import sign_in  # noqa: E402

PASSWORD = "a-long-enough-test-password"


class PaymentControlAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.provider = pv._FakeMercuryClient(available_balance=Decimal("100000.00"), recipient_behavior={})
        self.connector = pv._connector_for(self.provider)
        patcher = patch.object(tips_app, "_resolve_restaurant_connector", lambda session, rid: self.connector)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(tips_app.cycle_svc, "resolve_source_account_id", lambda *a, **k: "acct-1")
        patcher.start()
        self.addCleanup(patcher.stop)
        with tips_app.SessionFactory() as s:
            self.restaurant_id = pv._make_restaurant(s, name=f"R{self.id()[-12:]}").id
            location_id = s.scalar(select(m.RestaurantLocation.location_id).where(
                m.RestaurantLocation.restaurant_id == self.restaurant_id))
            location = s.get(m.Location, location_id)
            employee = m.Employee(location_id=location_id, source_system_id=location.source_system_id,
                                  source_employee_id=f"E{self.restaurant_id}", display_name="Payee",
                                  system_role="EMPLOYEE")
            s.add(employee)
            s.commit()
            pv._link_recipient(s, employee, f"recipient-{self.restaurant_id}")
            cycle = pv._open_cycle(s, restaurant_id=self.restaurant_id)
            instruction = m.TipPaymentInstruction(payment_cycle_id=cycle.id, employee_id=employee.id,
                                                  amount_minor=1200, status=pi_svc.STATUS_READY)
            s.add(instruction)
            s.flush()
            # The authorized amount: one FINAL period's entitlement aggregated into the instruction.
            run = m.TipDistributionCalculationRun(restaurant_id=self.restaurant_id, period_start=pv.T0,
                                                  period_end=pv.T0, status="COMPLETE", state=m.TIPS_RUN_STATE_FINAL)
            s.add(run)
            s.flush()
            s.add(m.TipEntitlement(calculation_run_id=run.id, restaurant_id=self.restaurant_id, employee_id=employee.id,
                                   gross_amount_minor=1200, outbound_amount_minor=0, inbound_amount_minor=0,
                                   payable_amount_minor=1200, tip_payment_instruction_id=instruction.id))
            s.add(m.EmployeeCloverLink(employee_id=employee.id, location_id=location_id, merchant_id="M",
                                       external_employee_id=employee.source_employee_id, state="PRESENT"))
            self.employee_id = employee.id
            # An identity authorized for every restaurant, NOT bound to any account:
            # posting its id must never let someone approve "as" it.
            other = m.ActingIdentity(kind="HUMAN_USER", display_name="Someone Else", is_active=True)
            s.add(other)
            s.flush()
            authority_service.grant_authority(s, actor=other, domain="TIPS", action="APPROVE_AND_PAY",
                                              scope_type=m.SCOPE_GLOBAL, scope_id=None)
            s.commit()
            self.cycle_id, self.instruction_id, self.other_identity_id = cycle.id, instruction.id, other.id

    def account(self, name, *, pay=False):
        with tips_app.SessionFactory() as s:
            a = account_service.create_account(s, username=f"{name}-{self.restaurant_id}", display_name=name.title(),
                                               password=PASSWORD)
            s.flush()
            account_service.set_domain_access(s, account_id=a.id, domain_code="TIPS", enabled=True, role_code=None)
            if pay:
                fin.set_restaurant_grants(s, account=a, permission=fin.TIPS_APPROVE_AND_PAY,
                                          restaurant_ids=[self.restaurant_id])
            s.commit()
            return a.id, a.session_version

    def client(self, account):
        c = tips_app.app.test_client()
        sign_in(c, account)
        c.get(f"/payment-control?site={self.restaurant_id}", follow_redirects=True)  # renders the forms: CSRF token
        return c

    @staticmethod
    def post(c, url, data=None, **kwargs):
        """A form post as the page sends it, with the RF-One session's CSRF token."""
        return c.post(url, data={**(data or {})}, **kwargs)

    def cycle(self):
        with tips_app.SessionFactory() as s:
            return s.get(m.TipPaymentCycle, self.cycle_id)

    def instruction(self):
        with tips_app.SessionFactory() as s:
            return s.get(m.TipPaymentInstruction, self.instruction_id)

    def test_page_names_the_signed_in_approver_and_offers_no_choice(self):
        c = self.client(self.account("viewer"))
        html = c.get("/payment-control").get_data(as_text=True)
        self.assertIn("Approving as <strong>Viewer</strong>", html)
        self.assertNotIn('name="acting_identity_id"', html)
        self.assertIn("no payment authorization for this restaurant", html)
        self.assertIn('<section id="tips_payment_control">', html)

    def test_unauthorized_account_cannot_approve_even_posting_another_identity(self):
        c = self.client(self.account("intruder"))
        self.post(c, "/payment-control/approve-and-pay", data={"acting_identity_id": self.other_identity_id})
        self.assertEqual(self.cycle().status, m.TIP_PAYMENT_CYCLE_STATUS_OPEN)
        self.assertEqual(self.provider.create_transaction_calls, 0)

    def test_authorized_account_approves_as_itself_and_only_once(self):
        account = self.account("payer", pay=True)
        c = self.client(account)
        self.post(c, "/payment-control/approve-and-pay", data={"acting_identity_id": self.other_identity_id})
        cycle = self.cycle()
        self.assertEqual(cycle.status, m.TIP_PAYMENT_CYCLE_STATUS_APPROVED)
        with tips_app.SessionFactory() as s:
            mine = fin.existing_identity_for_account(s, s.get(m.RFOneAccount, account[0]))
            self.assertEqual(cycle.approved_by_identity_id, mine.id)
            self.assertNotEqual(cycle.approved_by_identity_id, self.other_identity_id)
        self.post(c, "/payment-control/approve-and-pay", data={})
        self.assertEqual(self.provider.create_transaction_calls, 1)

    def test_retry_needs_the_payment_authorization_and_a_verified_failure(self):
        payer = self.account("payer", pay=True)
        self.post(self.client(payer), "/payment-control/approve-and-pay", data={})
        tx_id = self.instruction().provider_transaction_id
        retry = f"/payment-control/instruction/{self.instruction_id}/retry"
        # Not failed at the provider: refused, nothing sent.
        with tips_app.SessionFactory() as s:
            s.get(m.TipPaymentInstruction, self.instruction_id).status = pi_svc.STATUS_NEEDS_ATTENTION
            s.commit()
        resp = self.post(self.client(payer), retry, follow_redirects=True)
        self.assertIn("already paid or in progress", resp.get_data(as_text=True))
        self.assertEqual(self.instruction().status, pi_svc.STATUS_SENT)
        # Verified failed at the provider: a stranger is refused, the payer retries once with a new key.
        self.provider.set_transaction_status(tx_id, status="failed")
        with tips_app.SessionFactory() as s:
            s.get(m.TipPaymentInstruction, self.instruction_id).status = pi_svc.STATUS_NEEDS_ATTENTION
            s.commit()
        self.post(self.client(self.account("stranger")), retry)
        self.assertEqual(self.provider.create_transaction_calls, 1)
        self.post(self.client(payer), retry)
        self.assertEqual(self.provider.create_transaction_calls, 2)
        self.assertEqual(self.instruction().status, pi_svc.STATUS_SENT)
        statuses = sorted(t.status for t in self.provider._transactions_by_id.values())
        self.assertEqual(statuses, ["failed", "sent"])              # exactly one payment that counts


if __name__ == "__main__":
    unittest.main()
