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

    def test_explicit_consolidation_preserves_work_and_retired_id(self):
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        result, _ = self.sync([{"id": "M2", "name": "Different Known Name"}], self.md)
        duplicate_id = result["M2"]
        self.db.add(m.Shift(employee_id=duplicate_id, location_id=self.md.id,
            source_system_id=self.source.id, source_shift_id="MD-SHIFT",
            clock_in=datetime(2026, 10, 1, tzinfo=timezone.utc)))
        self.db.flush()
        directory.consolidate(self.db, from_employee_id=duplicate_id, into_employee_id=self.legacy.id)
        self.assertEqual(directory.resolve_employee_id(self.db, duplicate_id), self.legacy.id)
        self.assertEqual(len(list(self.db.scalars(directory.canonical_employees()))), 1)
        self.assertEqual(self.db.scalar(select(m.Shift)).employee_id, self.legacy.id)
        self.assertEqual({l.employee_id for l in self.db.scalars(select(m.EmployeeCloverLink))}, {self.legacy.id})
        self.assertEqual(self.db.get(m.Employee, duplicate_id).display_name, "Different Known Name")
        self.assertEqual(self.db.get(m.Employee, self.legacy.id).custom_id, "INTERNAL")

    def test_consolidation_constraint_conflict_rolls_back_every_reference(self):
        result, _ = self.sync([{"id": "M2", "name": "Different Known Name"}], self.md)
        duplicate_id = result["M2"]
        role = m.SourceRole(location_id=self.wp.id, source_system_id=self.source.id,
                            source_role_id="SHARED", name="Source role")
        self.db.add(role)
        self.db.flush()
        for employee_id in (duplicate_id, self.legacy.id):
            self.db.add(m.EmployeeSourceRole(employee_id=employee_id, source_role_id=role.id,
                                            source_system_id=self.source.id))
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "Nothing was moved"):
            directory.consolidate(self.db, from_employee_id=duplicate_id, into_employee_id=self.legacy.id)
        self.assertEqual(self.count(m.EmployeeIdentityAlias), 0)
        link = self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == "MD"))
        self.assertEqual(link.employee_id, duplicate_id)
        self.assertEqual(self.count(m.EmployeeSourceRole), 2)

    def test_source_account_replacement_can_link_to_same_person_after_removal(self):
        self.sync([{"id": "E1", "name": "Jane Smith"}])
        self.sync([])
        _, pending = self.sync([{"id": "REPLACEMENT", "name": "Jane Smith"}])
        directory.attach_link(self.db, link_id=pending[0], employee_id=self.legacy.id)
        self.assertEqual(self.count(m.Employee), 1)
        self.assertEqual(self.count(m.EmployeeCloverLink), 2)

    def test_active_poller_imports_and_failed_employee_read_preserves_roster(self):
        from rfone_data_store.clover_correction_sync_validation import _CorrectionFakeCloverClient
        from rfone_data_store.technical.connectors.clover.correction_sync import run_correction_cycle
        client = _CorrectionFakeCloverClient("WP")
        client.employees = [{"id": "E1", "name": "Jane Source", "email": "poller@example.test"}]
        summary = run_correction_cycle(self.db, location_id=self.wp.id, client=client)
        self.assertFalse(summary.employee_errors)
        self.assertEqual(len(summary.results), 3)
        self.assertEqual(self.db.scalar(select(m.EmployeeCloverLink)).snapshot["email"], "poller@example.test")
        client.fail_employees = True
        failed = run_correction_cycle(self.db, location_id=self.wp.id, client=client)
        self.assertTrue(failed.employee_errors)
        self.assertEqual(failed.results, [])
        self.assertEqual(self.db.scalar(select(m.EmployeeCloverLink)).state, "PRESENT")
        self.assertEqual(self.db.get(m.Employee, self.legacy.id).custom_id, "INTERNAL")

    def test_pending_md_identity_does_not_block_wp_poller(self):
        from rfone_data_store.clover_correction_sync_validation import _CorrectionFakeCloverClient
        from rfone_data_store.technical.connectors.clover.correction_sync import run_correction_cycle
        md_client = _CorrectionFakeCloverClient("MD")
        md_client.employees = [{"id": "M1", "name": "Jane Smith"}]
        summary = run_correction_cycle(self.db, location_id=self.md.id, client=md_client)
        self.assertTrue(summary.employee_errors)
        self.assertFalse(summary.results)
        md_work_cursors = list(self.db.scalars(select(m.IngestionRun).where(
            m.IngestionRun.location_id == self.md.id, m.IngestionRun.resource_type.is_not(None))))
        self.assertFalse(md_work_cursors)
        wp_client = _CorrectionFakeCloverClient("WP")
        wp_client.employees = [{"id": "E1", "name": "Jane Smith"}]
        wp_summary = run_correction_cycle(self.db, location_id=self.wp.id, client=wp_client)
        self.assertFalse(wp_summary.employee_errors)
        self.assertEqual(len(wp_summary.results), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
