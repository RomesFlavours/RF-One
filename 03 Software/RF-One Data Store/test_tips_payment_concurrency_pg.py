"""CLOVER_MULTISITE_001 — Tips money steps under real concurrency, on PostgreSQL with two independent
connections (Product Owner 2026-11-21): preparing a Payment Cycle (manual and automatic at once),
finalizing overlapping periods, approving the same cycle twice, retrying the same failed payment twice.
Nothing may be prepared, finalized or paid twice.

Needs a DISPOSABLE PostgreSQL database (never a shared one): every table is created in it.

Usage:
    RFONE_PG_CONCURRENCY_TEST_URL=postgresql://postgres@127.0.0.1:55499/rfconc python -m unittest test_tips_payment_concurrency_pg
"""
from __future__ import annotations

import os
import threading
import time
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from sqlalchemy import create_engine, func, select, text

from rfone_data_store import authority_service
from rfone_data_store import models as m
from rfone_data_store import tips_payment_execution_validation as pv
from rfone_data_store.database import create_session_factory
from rfone_data_store.tips import calculation_run_service as run_svc
from rfone_data_store.tips import money_lock
from rfone_data_store.tips import payment_cycle_service as cycle_svc
from rfone_data_store.tips import payment_instruction as pi_svc

URL = os.environ.get("RFONE_PG_CONCURRENCY_TEST_URL")


@unittest.skipUnless(URL, "set RFONE_PG_CONCURRENCY_TEST_URL to a disposable PostgreSQL database")
class TipsMoneyConcurrencyPg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(URL, pool_size=5)
        try:
            from rfone_data_store import access_profiles  # noqa: F401  (registers its tables)
        except ImportError:
            pass
        with cls.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        # The real schema comes from the migrations; the models carry SQLite-style boolean defaults
        # ('0'/'1'), so this disposable copy translates them for PostgreSQL (in memory, test only).
        from sqlalchemy import Boolean
        from sqlalchemy.schema import DefaultClause
        for table in m.Base.metadata.sorted_tables:
            for column in table.columns:
                default = column.server_default
                arg = getattr(default, "arg", None)
                value = arg if isinstance(arg, str) else getattr(arg, "text", None)
                if isinstance(column.type, Boolean) and value in ("0", "1"):
                    column.server_default = DefaultClause(text("true" if value == "1" else "false"))
        # Every table this flow uses; tables of other Domains that do not build on PostgreSQL from the
        # models alone are skipped (they are not involved here).
        for table in m.Base.metadata.sorted_tables:
            try:
                table.create(cls.engine, checkfirst=True)
            except Exception:  # noqa: BLE001
                pass
        cls.factory = create_session_factory(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.client = pv._FakeMercuryClient(available_balance=Decimal("100000.00"), recipient_behavior={})
        self.connector = pv._connector_for(self.client)
        with self.factory() as s:
            restaurant = pv._make_restaurant(s, name=f"R-{self.id()[-20:]}")
            location_id = s.scalar(select(m.RestaurantLocation.location_id).where(
                m.RestaurantLocation.restaurant_id == restaurant.id))
            location = s.get(m.Location, location_id)
            self.employees = []
            for n in range(3):
                e = m.Employee(location_id=location_id, source_system_id=location.source_system_id,
                               source_employee_id=f"C{restaurant.id}-{n}", display_name=f"Payee {n}",
                               system_role="EMPLOYEE")
                s.add(e)
                s.flush()
                self.employees.append(e.id)
                s.add(m.EmployeeExternalPaymentAccount(employee_id=e.id, provider="MERCURY",
                                                       provider_recipient_id=f"rcpt-{e.id}", is_active=True))
            self.approver = self._identity(s, restaurant.id, "Person")
            self.system = self._identity(s, restaurant.id, "Scheduler")
            s.commit()
            self.restaurant_id = restaurant.id

    def _identity(self, s, restaurant_id, name):
        identity = m.ActingIdentity(kind="HUMAN_USER", display_name=f"{name} {restaurant_id}", is_active=True)
        s.add(identity)
        s.flush()
        authority_service.grant_authority(s, actor=identity, domain="TIPS", action="APPROVE_AND_PAY",
                                          scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant_id)
        return identity.id

    def final_entitlements(self, amount=1000, *, day=0):
        with self.factory() as s:
            start = pv.T0 + timedelta(days=day)
            run = m.TipDistributionCalculationRun(
                restaurant_id=self.restaurant_id, period_start=start, period_end=start + timedelta(days=1),
                status="COMPLETE", state=m.TIPS_RUN_STATE_FINAL, first_business_date=start.date(),
                last_business_date=start.date())
            s.add(run)
            s.flush()
            for employee_id in self.employees:
                s.add(m.TipEntitlement(calculation_run_id=run.id, restaurant_id=self.restaurant_id,
                      employee_id=employee_id, gross_amount_minor=amount, outbound_amount_minor=0,
                      inbound_amount_minor=0, payable_amount_minor=amount))
            s.commit()
            return run.id

    @staticmethod
    def race(*jobs, hold=None):
        """Runs the jobs in parallel threads, each with its own session/connection. `hold` makes the FIRST
        thread that reaches it sleep inside its transaction, so the other one really competes."""
        results, errors = [None] * len(jobs), [None] * len(jobs)
        barrier = threading.Barrier(len(jobs))

        def run(i, job):
            barrier.wait()
            try:
                results[i] = job()
            except Exception as exc:  # noqa: BLE001
                errors[i] = exc
        threads = [threading.Thread(target=run, args=(i, job)) for i, job in enumerate(jobs)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        return results, errors

    def holding(self, module, name, seconds=1.0):
        """Wraps `module.name` so the first caller sleeps right after it (inside its transaction)."""
        original, first = getattr(module, name), threading.Event()

        def wrapper(*args, **kwargs):
            out = original(*args, **kwargs)
            if not first.is_set():
                first.set()
                time.sleep(seconds)
            return out
        return mock.patch.object(module, name, wrapper)

    # --- A. preparation, manual and automatic at the same time -----------------------------------
    def test_manual_and_automatic_preparation_aggregate_each_entitlement_once(self):
        self.final_entitlements()

        def prepare(trigger):
            def job():
                with self.factory() as s:
                    cycle = cycle_svc.start_payment_cycle(s, restaurant_id=self.restaurant_id, triggered_by=trigger)
                    s.commit()
                    return cycle.id
            return job
        with self.holding(cycle_svc, "get_unpaid_entitlements"):
            results, errors = self.race(prepare("MANUAL"), prepare("AUTOMATIC"))
        self.assertEqual(errors, [None, None])
        self.assertEqual(results[0], results[1])                    # the second found the first one's cycle
        with self.factory() as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipPaymentCycle).where(
                m.TipPaymentCycle.restaurant_id == self.restaurant_id)), 1)
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipPaymentInstruction).where(
                m.TipPaymentInstruction.payment_cycle_id == results[0])), 3)
            self.assertEqual(s.scalar(select(func.sum(m.TipPaymentInstruction.amount_minor)).where(
                m.TipPaymentInstruction.payment_cycle_id == results[0])), 3000)

    def test_without_the_lock_the_database_guards_still_refuse_a_second_cycle(self):
        self.final_entitlements()

        def prepare():
            with self.factory() as s:
                cycle = cycle_svc.start_payment_cycle(s, restaurant_id=self.restaurant_id, triggered_by="MANUAL")
                s.commit()
                return cycle.id
        with mock.patch.object(cycle_svc, "lock_restaurant", lambda session, restaurant_id: None), \
                self.holding(cycle_svc, "get_unpaid_entitlements"):
            results, errors = self.race(prepare, prepare)
        self.assertEqual(sum(e is None for e in errors), 1, errors)  # one prepared, the other refused
        with self.factory() as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipPaymentCycle).where(
                m.TipPaymentCycle.restaurant_id == self.restaurant_id)), 1)
            linked = s.scalars(select(m.TipEntitlement.tip_payment_instruction_id).where(
                m.TipEntitlement.restaurant_id == self.restaurant_id)).all()
            self.assertTrue(all(linked))

    # --- A. finalization of overlapping periods at the same time ---------------------------------
    def test_two_overlapping_periods_never_both_become_final(self):
        with self.factory() as s:
            account_ids = []
            for name in ("v1", "v2"):
                from rfone_data_store import rfone_account_service as accounts
                a = accounts.create_account(s, username=f"{name}-{self.restaurant_id}", display_name=name,
                                            password="a-long-enough-test-password")
                s.flush()
                account_ids.append(a.id)
            run_ids = []
            for _ in range(2):
                run = m.TipDistributionCalculationRun(
                    restaurant_id=self.restaurant_id, period_start=pv.T0, period_end=pv.T0 + timedelta(days=1),
                    status="COMPLETE", state=m.TIPS_RUN_STATE_CALCULATED, first_business_date=pv.T0.date(),
                    last_business_date=pv.T0.date(), control_difference_minor=0)
                s.add(run)
                s.flush()
                run_ids.append(run.id)
            s.commit()

        def validate(run_id, account_id):
            def job():
                with self.factory() as s:
                    run, reason = run_svc.validate_run(s, run_id=run_id, account_id=account_id)
                    s.commit()
                    return run is not None
            return job
        with self.holding(run_svc, "finalization_blockers"):
            results, errors = self.race(validate(run_ids[0], account_ids[0]), validate(run_ids[1], account_ids[1]))
        self.assertEqual(errors, [None, None])
        self.assertEqual(sorted(results), [False, True])
        with self.factory() as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipDistributionCalculationRun).where(
                m.TipDistributionCalculationRun.id.in_(run_ids),
                m.TipDistributionCalculationRun.state == m.TIPS_RUN_STATE_FINAL)), 1)

    # --- B/C. approval and retry at the same time -------------------------------------------------
    def prepared_cycle(self):
        self.final_entitlements()
        with self.factory() as s:
            cycle = cycle_svc.start_payment_cycle(s, restaurant_id=self.restaurant_id, triggered_by="MANUAL")
            s.commit()
            return cycle.id

    def approve_job(self, cycle_id, identity_id):
        def job():
            with self.factory() as s:
                cycle_svc.approve_and_pay_cycle(s, cycle=s.get(m.TipPaymentCycle, cycle_id),
                    acting_identity=s.get(m.ActingIdentity, identity_id), connector=self.connector,
                    source_account_id="acct-1")
                s.commit()
                return True
        return job

    def test_a_person_and_the_scheduler_approving_together_pay_once(self):
        cycle_id = self.prepared_cycle()
        with self.holding(cycle_svc, "_payment_authority"):
            results, errors = self.race(self.approve_job(cycle_id, self.approver), self.approve_job(cycle_id, self.system))
        self.assertEqual(sum(r is True for r in results), 1, (results, errors))
        self.assertTrue(any(isinstance(e, cycle_svc.ApproveAndPayError) and "not OPEN" in str(e) for e in errors))
        self.assertEqual(self.client.create_transaction_calls, 3)
        with self.factory() as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipPaymentSubmission).where(
                m.TipPaymentSubmission.payment_cycle_id == cycle_id)), 3)

    def test_two_retries_of_the_same_failed_payment_send_one(self):
        cycle_id = self.prepared_cycle()
        self.approve_job(cycle_id, self.approver)()
        with self.factory() as s:
            instruction = s.scalars(select(m.TipPaymentInstruction).where(
                m.TipPaymentInstruction.payment_cycle_id == cycle_id).order_by(m.TipPaymentInstruction.id)).first()
            instruction_id = instruction.id
            self.client.set_transaction_status(instruction.provider_transaction_id, status="failed")
            instruction.status = pi_svc.STATUS_NEEDS_ATTENTION
            s.commit()

        def retry(identity_id):
            def job():
                with self.factory() as s:
                    cycle_svc.retry_instruction(s, s.get(m.TipPaymentInstruction, instruction_id), self.connector,
                        source_account_id="acct-1", acting_identity=s.get(m.ActingIdentity, identity_id))
                    s.commit()
                    return True
            return job
        with self.holding(cycle_svc, "_payment_authority"):
            results, errors = self.race(retry(self.approver), retry(self.system))
        self.assertEqual(sum(r is True for r in results), 1, (results, errors))
        self.assertEqual(self.client.create_transaction_calls, 4)          # 3 first payments + 1 retry
        with self.factory() as s:
            states = s.scalars(select(m.TipPaymentSubmission.state).where(
                m.TipPaymentSubmission.payment_instruction_id == instruction_id)
                .order_by(m.TipPaymentSubmission.id)).all()
            self.assertEqual(states, [m.TIP_SUBMISSION_VERIFIED_FAILED, m.TIP_SUBMISSION_ACCEPTED])

    def test_the_restaurant_lock_is_held_by_one_transaction_at_a_time(self):
        with self.factory() as s1, self.factory() as s2:
            money_lock.lock_restaurant(s1, self.restaurant_id)
            s2.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with self.assertRaises(Exception):                # the second connection cannot take it
                money_lock.lock_restaurant(s2, self.restaurant_id)
            s2.rollback()
            s1.commit()
            money_lock.lock_restaurant(s2, self.restaurant_id)  # free once the first transaction ends
            s2.commit()


if __name__ == "__main__":
    unittest.main()
