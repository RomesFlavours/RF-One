"""Record-level identity holds (EMPLOYEE_DIRECTORY_RECORD_HOLD_001).

An unconfirmed Clover employee must hold only the records that depend on that
person, never the Location's whole acquisition. Disposable SQLite and a fake
Clover client only.
"""
from datetime import date, datetime, time, timedelta, timezone
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store import employee_directory as directory
from rfone_data_store.clover_correction_sync_validation import _CorrectionFakeCloverClient
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.technical.connectors.clover import acquisition, identity_holds
from rfone_data_store.technical.connectors.clover.correction_sync import run_correction_cycle
from rfone_data_store.tips import calculation_run_service

UTC = timezone.utc
NOW = datetime(2026, 10, 31, 20, 0, tzinfo=UTC)
NEW_DAY = date(2026, 10, 31)  # 15:00 New York, Business Date of the unknown employee's order
KNOWN_DAY = date(2026, 10, 30)  # 18:00 New York the day before, known employee only


def _ms(value):
    return int(value.timestamp() * 1000)


class IdentityRecordHoldTest(unittest.TestCase):
    POSTGRES_URL = os.environ.get("RFONE_HOLDS_TEST_POSTGRES_URL")  # optional disposable database, dialect check

    @classmethod
    def setUpClass(cls):
        if cls.POSTGRES_URL:
            from alembic.script import ScriptDirectory
            from rfone_data_store.database import MIGRATION_TARGET_ENV, run_migrations_to_head
            from rfone_data_store.schema_compatibility import _MIGRATIONS_DIR
            os.environ[MIGRATION_TARGET_ENV] = ScriptDirectory(str(_MIGRATIONS_DIR)).get_current_head()
            run_migrations_to_head(cls.POSTGRES_URL)

    def setUp(self):
        if self.POSTGRES_URL:
            self.engine = create_configured_engine(self.POSTGRES_URL)
            tables = ", ".join(f'"{t.name}"' for t in m.Base.metadata.sorted_tables)
            with self.engine.begin() as connection:
                connection.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
        else:
            self.engine = create_configured_engine("sqlite:///:memory:")
            m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        self.source = m.SourceSystem(code="CLOVER", name="Clover")
        self.db.add(self.source)
        self.db.flush()
        merchant = m.Merchant(name="Test Merchant", source_system_id=self.source.id, source_merchant_id="WP")
        self.db.add(merchant)
        self.db.flush()
        self.wp = m.Location(name="Winter Park", merchant_id=merchant.id, source_system_id=self.source.id,
                             source_location_id="WP", timezone="America/New_York",
                             operating_day_cutoff_time=time(4, 0), currency="USD")
        self.db.add(self.wp)
        self.db.flush()
        self.restaurant = m.Restaurant(name="Synthetic Hold Restaurant", default_currency="USD")
        self.db.add(self.restaurant)
        self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=self.restaurant.id, location_id=self.wp.id, is_primary=True))
        self.known = m.Employee(location_id=self.wp.id, source_system_id=self.source.id,
                                source_employee_id="E1", display_name="Known Server", active=True)
        self.db.add(self.known)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def client(self):
        client = _CorrectionFakeCloverClient("WP")
        client.employees = [{"id": "E1", "name": "Known Server"}, {"id": "U1", "name": "New Hire"}]
        known_at, new_at = NOW - timedelta(hours=22), NOW - timedelta(hours=1)
        for order_id, employee, at in (("O-KNOWN", "E1", known_at), ("O-NEW", "U1", new_at)):
            client.orders.append({
                "id": order_id, "employee": {"id": employee}, "createdTime": _ms(at), "modifiedTime": _ms(at),
                "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 1000,
                "lineItems": {"elements": []},
            })
            client.payments.append({
                "id": f"P-{order_id}", "order": {"id": order_id}, "employee": {"id": employee},
                "tender": {"id": "T1", "label": "Cash"}, "amount": 1000, "taxAmount": 0, "tipAmount": 200,
                "createdTime": _ms(at), "modifiedTime": _ms(at), "result": "SUCCESS",
            })
        client.refunds.append({
            "id": "R-NEW", "orderRef": {"id": "O-NEW"}, "payment": {"id": "P-O-NEW"}, "employee": {"id": "U1"},
            "createdTime": _ms(new_at), "amount": 100, "status": "PROCESSED",
        })
        return client

    def cycle(self):
        summary = run_correction_cycle(self.db, location_id=self.wp.id, client=self.client(), now=NOW)
        self.db.commit()
        self.db.expire_all()
        return summary

    def order(self, source_id):
        return self.db.scalar(select(m.Order).filter_by(source_order_id=source_id))

    def payment(self, source_id):
        return self.db.scalar(select(m.Payment).filter_by(source_payment_id=source_id))

    def pending_link(self):
        return self.db.scalar(select(m.EmployeeCloverLink).filter_by(external_employee_id="U1"))

    def run_for(self, day):
        return m.TipDistributionCalculationRun(restaurant_id=self.restaurant.id, first_business_date=day,
                                               last_business_date=day, period_start=NOW, period_end=NOW,
                                               status="COMPLETE")

    def test_unknown_employee_does_not_block_other_transactions(self):
        with self.assertLogs("clover_correction_sync", level="WARNING") as logs:
            summary = self.cycle()
        self.assertEqual(summary.employee_errors, [])
        self.assertEqual([r.status for r in summary.results], ["COMPLETE"] * 3)
        self.assertEqual(self.order("O-KNOWN").employee_id, self.known.id)
        self.assertEqual(self.payment("P-O-KNOWN").employee_id, self.known.id)
        held_order, held_payment = self.order("O-NEW"), self.payment("P-O-NEW")
        self.assertIsNone(held_order.employee_id)
        self.assertEqual(held_order.source_employee_id, "U1")
        self.assertIsNone(held_payment.employee_id)
        self.assertEqual(held_payment.source_employee_id, "U1")
        refund = self.db.scalar(select(m.Refund).filter_by(source_refund_id="R-NEW"))
        self.assertIsNotNone(refund)
        self.assertIsNone(refund.employee_id)
        mirrored = self.db.scalar(select(m.SourceRecord).filter_by(entity_type="refund", source_id="R-NEW"))
        self.assertEqual(mirrored.raw_json["employee"]["id"], "U1")
        # Nobody invented: the unknown identity is still pending, no person created.
        self.assertIsNone(self.pending_link().employee_id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 1)
        # Visible, never silent: the cycle and its history row say what waits and why.
        self.assertTrue(summary.identity_holds)
        self.assertIn("orders=1", summary.identity_holds[0])
        self.assertIn("payments=1", summary.identity_holds[0])
        self.assertIn("refunds=1", summary.identity_holds[0])
        self.assertTrue(any("identities pending" in line and "orders=1" in line for line in logs.output))
        lock_row = self.db.scalar(select(m.IngestionRun).where(
            m.IngestionRun.acquisition_mode == "CORRECTION").order_by(m.IngestionRun.id.desc()))
        self.assertEqual(lock_row.status, "COMPLETE")
        self.assertIn("IDENTITY HOLDS", lock_row.notes)
        # Checkpoints advance: nothing is re-read forever because of one person.
        cursors = self.db.scalars(select(m.IngestionRun).where(m.IngestionRun.resource_type.is_not(None))).all()
        self.assertTrue(cursors and all(c.status == "COMPLETE" for c in cursors))

    def test_confirmation_reattributes_idempotently_and_is_traced(self):
        self.cycle()
        # Orders only, no clock-in: not a new employee (EMPLOYEE_ACCOUNTS_001);
        # the identity is confirmed as an existing RF-One person instead.
        person = directory.attach_link(self.db, link_id=self.pending_link().id,
                                       employee_id=directory.create_person(self.db, display_name="New Hire").id)
        self.db.commit()
        self.db.expire_all()
        self.assertEqual(self.order("O-NEW").employee_id, person.id)
        self.assertEqual(self.payment("P-O-NEW").employee_id, person.id)
        self.assertEqual(self.db.scalar(select(m.Refund).filter_by(source_refund_id="R-NEW")).employee_id, person.id)
        self.assertEqual(self.order("O-KNOWN").employee_id, self.known.id)  # untouched
        event = self.db.scalar(select(m.EmployeeDirectoryEvent).filter_by(action="REATTRIBUTE"))
        self.assertEqual(event.employee_id, person.id)
        self.assertEqual({k: event.details["counts"][k] for k in ("orders", "payments", "refunds")},
                         {"orders": 1, "payments": 1, "refunds": 1})
        again = identity_holds.reattribute_link(self.db, self.pending_link())
        self.assertEqual(set(again.values()), {0})
        summary = self.cycle()  # a later cycle neither duplicates nor reverts
        self.assertFalse(summary.identity_holds)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Order)), 2)
        self.assertEqual(self.order("O-NEW").employee_id, person.id)

    def test_held_shift_waits_in_mirror_then_is_created_on_confirmation(self):
        directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id="WP",
                                  records=[{"id": "E1", "name": "Known Server"}, {"id": "U1", "name": "New Hire"}])
        run = m.IngestionRun(source_system_id=self.source.id, location_id=self.wp.id, status="RUNNING", started_at=NOW)
        self.db.add(run)
        self.db.flush()
        shifts = SimpleNamespace(ok=True, truncated_by_safety_guard=False, elements=[
            {"id": "S-KNOWN", "employee": {"id": "E1"}, "inTime": _ms(NOW - timedelta(hours=5))},
            {"id": "S-NEW", "employee": {"id": "U1"}, "inTime": _ms(NOW - timedelta(hours=4)),
             "outTime": _ms(NOW - timedelta(hours=1))},
        ])
        fake = SimpleNamespace(merchant_id="WP", get=lambda path, params=None: SimpleNamespace(
            ok=True, status_code=200, error=None, data={"id": path.rsplit("/", 1)[-1], "name": "New Hire"}))
        held = []
        with patch.object(acquisition, "paginate", return_value=shifts):
            touched = acquisition._fetch_and_ingest_shifts(
                fake, self.db, period_start=NOW - timedelta(days=1), period_end=NOW,
                source_system_id=self.source.id, employee_by_source_id={"E1": self.known.id},
                ingestion_run_id=run.id, retrieved_at=NOW, held=held)
        self.assertEqual(touched, 1)
        self.assertEqual(len(held), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Shift)), 1)
        self.assertIn("S-NEW", identity_holds.held_shifts(self.db, location_ids=[self.wp.id], external_ids={"U1"}))
        person = directory.attach_link(self.db, link_id=self.pending_link().id, create_new=True)
        shift = self.db.scalar(select(m.Shift).filter_by(source_shift_id="S-NEW"))
        self.assertEqual((shift.employee_id, shift.location_id), (person.id, self.wp.id))
        self.assertFalse(identity_holds.held_shifts(self.db, location_ids=[self.wp.id], external_ids={"U1"}))

    def test_tips_final_allocation_blocked_only_for_affected_day(self):
        self.cycle()
        self.assertEqual(self.order("O-NEW").business_date, NEW_DAY)
        self.assertEqual(self.order("O-KNOWN").business_date, KNOWN_DAY)
        blocked = calculation_run_service.identity_hold_blockers(self.db, self.run_for(NEW_DAY))
        self.assertEqual(len(blocked), 1)
        self.assertIn(str(NEW_DAY), blocked[0])
        self.assertIn(blocked[0], calculation_run_service.finalization_blockers(self.db, self.run_for(NEW_DAY)))
        self.assertEqual(calculation_run_service.identity_hold_blockers(self.db, self.run_for(KNOWN_DAY)), [])
        directory.attach_link(self.db, link_id=self.pending_link().id,
                              employee_id=directory.create_person(self.db, display_name="New Hire").id)
        self.assertEqual(calculation_run_service.identity_hold_blockers(self.db, self.run_for(NEW_DAY)), [])

    def test_poller_attributes_confirmation_made_by_older_web_release(self):
        self.cycle()
        link = self.pending_link()
        person = m.Employee(location_id=self.wp.id, display_name="New Hire")
        self.db.add(person)
        self.db.flush()
        link.employee_id = person.id  # what the previous attach_link did: LINK event, no reattribution
        directory._event(self.db, "LINK", employee_id=person.id, link=link, details={"create_new": True})
        self.db.commit()
        self.assertIsNone(self.order("O-NEW").employee_id)
        self.cycle()
        self.assertEqual(self.order("O-NEW").employee_id, person.id)
        self.assertEqual(self.payment("P-O-NEW").employee_id, person.id)
        self.cycle()  # traced once, never again
        events = self.db.scalars(select(m.EmployeeDirectoryEvent).filter_by(action="REATTRIBUTE")).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].details["by"], "correction_sync")
        # Legacy links without a LINK event (migration seed) are never reattributed.
        self.assertIsNone(self.db.scalar(select(m.EmployeeDirectoryEvent).where(
            m.EmployeeDirectoryEvent.action == "REATTRIBUTE",
            m.EmployeeDirectoryEvent.employee_id == self.known.id)))

    def test_employee_read_failure_still_preserves_work_checkpoints(self):
        client = self.client()
        client.fail_employees = True
        summary = run_correction_cycle(self.db, location_id=self.wp.id, client=client, now=NOW)
        self.assertTrue(summary.employee_errors)
        self.assertEqual(summary.results, [])
        self.assertIsNone(self.order("O-KNOWN"))


if __name__ == "__main__":
    unittest.main()
