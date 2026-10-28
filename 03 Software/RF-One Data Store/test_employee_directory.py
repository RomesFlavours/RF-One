"""Employee directory acceptance tests; disposable SQLite only, fake Clover only."""
from datetime import datetime, timezone
import unittest

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store import employee_directory as directory
from rfone_data_store.database import create_configured_engine, create_session_factory


class EmployeeDirectoryTest(unittest.TestCase):
    def setUp(self):
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
                             source_location_id="WP", timezone="America/New_York")
        self.md = m.Location(name="Mount Dora", merchant_id=merchant.id, source_system_id=self.source.id,
                             source_location_id="MD", timezone="America/New_York")
        self.db.add_all([self.wp, self.md])
        self.db.flush()
        self.legacy = m.Employee(location_id=self.wp.id, source_system_id=self.source.id,
                                 source_employee_id="E1", display_name="Jane Smith", custom_id="INTERNAL", active=True)
        self.db.add(self.legacy)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def sync(self, records, location=None, **kwargs):
        location = location or self.wp
        return directory.import_snapshot(self.db, location_id=location.id,
            merchant_id=location.source_location_id, records=records, **kwargs)

    def count(self, model):
        return self.db.scalar(select(func.count()).select_from(model))

    def test_repeated_import_reuses_legacy_id_and_preserves_management(self):
        records = [{"id": "E1", "name": "Jane Source", "customId": "EXTERNAL", "email": "jane@example.test", "role": "MANAGER"}]
        for _ in range(3):
            result, pending = self.sync(records)
            self.assertEqual(result["E1"], self.legacy.id)
            self.assertEqual(pending, [])
        self.assertEqual(self.count(m.Employee), 1)
        self.assertEqual(self.count(m.EmployeeCloverLink), 1)
        self.assertEqual(self.count(m.EmployeeDirectoryEvent), 1)
        self.assertEqual(self.legacy.display_name, "Jane Smith")
        self.assertEqual(self.legacy.custom_id, "INTERNAL")
        self.assertTrue(self.legacy.active)

    def test_two_merchants_same_external_id_manual_link_one_person(self):
        self.sync([{"id": "E1", "name": "Jane Smith", "email": "jane@example.test"}])
        _, pending = self.sync([{"id": "E1", "name": "Jane Smith", "email": "jane@example.test"}], self.md)
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.count(m.Employee), 1)
        directory.attach_link(self.db, link_id=pending[0], employee_id=self.legacy.id)
        for _ in range(2):
            result, pending = self.sync([{"id": "E1", "name": "Jane Smith", "email": "jane@example.test"}], self.md)
            self.assertEqual(result["E1"], self.legacy.id)
            self.assertFalse(pending)
        self.assertEqual(self.count(m.Employee), 1)
        self.assertEqual(self.count(m.EmployeeCloverLink), 2)

    def test_same_name_never_auto_merges_and_explicit_new_is_possible(self):
        _, pending = self.sync([{"id": "E2", "name": "Jane Smith"}], self.md)
        self.assertEqual(self.count(m.Employee), 1)
        employee = directory.attach_link(self.db, link_id=pending[0], create_new=True)
        self.assertNotEqual(employee.id, self.legacy.id)
        self.assertEqual(self.count(m.Employee), 2)

    def test_email_proposes_match_despite_changed_name(self):
        self.sync([{"id": "E1", "name": "Jane Smith", "email": "jane@example.test"}])
        _, pending = self.sync([{"id": "MD2", "name": "Completely Different", "email": "JANE@example.test"}], self.md)
        self.assertEqual(len(pending), 1)
        suggestions = directory.candidates(self.db, {"name": "Different", "email": "jane@example.test"})
        self.assertEqual(suggestions[0]["employee"].id, self.legacy.id)
        self.assertEqual(suggestions[0]["reason"], "Email")

    def test_conflicts_review_reopens_on_change(self):
        self.sync([{"id": "E1", "name": "Jane Smith", "email": "wp@example.test"}])
        _, pending = self.sync([{"id": "M1", "name": "Jane Smith", "email": "md@example.test"}], self.md)
        directory.attach_link(self.db, link_id=pending[0], employee_id=self.legacy.id)
        links = list(self.db.scalars(select(m.EmployeeCloverLink)))
        self.assertIn("email", directory.source_conflicts(links))
        self.assertFalse(directory.is_reviewed(self.db, self.legacy.id, links))
        directory.review(self.db, self.legacy.id, links, None)
        self.db.flush()
        self.assertTrue(directory.is_reviewed(self.db, self.legacy.id, links))
        self.sync([{"id": "M1", "name": "Jane Smith", "email": "changed@example.test"}], self.md)
        self.assertFalse(directory.is_reviewed(self.db, self.legacy.id, links))
        self.assertEqual(self.legacy.display_name, "Jane Smith")

    def test_incomplete_or_malformed_import_cannot_mark_missing(self):
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        for records, kwargs in [([], {"complete": False}), ([{"name": "No ID"}], {}),
                                ([{"id": "D"}, {"id": "D"}], {}), ([{"id": "E1", "name": []}], {})]:
            with self.assertRaises(ValueError):
                self.sync(records, **kwargs)
        link = self.db.scalar(select(m.EmployeeCloverLink))
        self.assertEqual(link.state, "PRESENT")
        self.assertTrue(self.legacy.active)

    def test_complete_absence_retains_person_history_and_historical_resolution(self):
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        result, _ = self.sync([])
        self.assertEqual(result["E1"], self.legacy.id)
        link = self.db.scalar(select(m.EmployeeCloverLink))
        self.assertEqual(link.state, "MISSING_REVIEW")
        self.assertEqual(self.count(m.Employee), 1)
        self.assertTrue(self.legacy.active)
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        self.assertEqual(link.state, "PRESENT")
        self.assertEqual(self.count(m.EmployeeDirectoryEvent), 3)

    def test_failed_transaction_does_not_publish_absence(self):
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        self.db.commit()
        self.sync([])
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(m.EmployeeCloverLink)).state, "PRESENT")

    def test_source_history_excludes_pin_and_preserves_changed_snapshots(self):
        self.sync([{"id": "E1", "name": "Jane Smith", "pin": "never-store"}])
        self.sync([{"id": "E1", "name": "Jane Updated", "pin": "never-store"}])
        events = list(self.db.scalars(select(m.EmployeeDirectoryEvent)))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].details["snapshot"]["name"], "Jane Smith")
        self.assertNotIn("never-store", str([e.details for e in events]))

    def test_wrong_merchant_rejected_before_writes(self):
        with self.assertRaises(ValueError):
            directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id="MD", records=[])
        self.assertEqual(self.count(m.EmployeeCloverLink), 0)

    def test_unknown_person_created_once(self):
        for _ in range(2):
            result, pending = self.sync([{"id": "NEW", "name": "Robert Jones"}])
            self.assertFalse(pending)
        self.assertEqual(self.count(m.Employee), 2)
        self.assertEqual(self.db.get(m.Employee, result["NEW"]).display_name, "Robert Jones")

    def test_duplicate_confirmed_link_cannot_be_reassigned(self):
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        link = self.db.scalar(select(m.EmployeeCloverLink))
        with self.assertRaises(ValueError):
            directory.attach_link(self.db, link_id=link.id, create_new=True)
        self.assertEqual(self.count(m.Employee), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
