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

    def link(self, location, external_id, employee=None, state="PRESENT", name="Jane Smith"):
        """A Clover link as it exists in Registry history (REGISTRY_MULTISITE_001: no import creates one)."""
        row = m.EmployeeCloverLink(employee_id=(employee or self.legacy).id if employee is not False else None,
                                   location_id=location.id, merchant_id=location.source_location_id,
                                   external_employee_id=external_id, state=state, snapshot={"id": external_id, "name": name})
        self.db.add(row)
        self.db.flush()
        return row

    def restore(self, location):
        for row in self.db.scalars(select(m.EmployeeCloverLink).where(
                m.EmployeeCloverLink.merchant_id == location.source_location_id)):
            row.state = "PRESENT"
        self.db.flush()

    def absent(self, location):
        for row in self.db.scalars(select(m.EmployeeCloverLink).where(
                m.EmployeeCloverLink.merchant_id == location.source_location_id)):
            row.state = "MISSING_REVIEW"
        self.db.flush()

    def count(self, model):
        return self.db.scalar(select(func.count()).select_from(model))

    def test_explicit_consolidation_preserves_work_and_retired_id(self):
        self.link(self.wp, "E1")
        duplicate = m.Employee(location_id=self.md.id, display_name="Different Known Name")
        self.db.add(duplicate); self.db.flush()
        duplicate_id = duplicate.id
        self.link(self.md, "M2", employee=duplicate)
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
        duplicate = m.Employee(location_id=self.md.id, display_name="Different Known Name")
        self.db.add(duplicate); self.db.flush()
        duplicate_id = duplicate.id
        self.link(self.md, "M2", employee=duplicate)
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

    def test_md_shift_keeps_actual_location_after_linking_to_wp_person(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from rfone_data_store.technical.connectors.clover import acquisition
        self.link(self.wp, "E1")
        self.link(self.md, "E1")
        observed = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        run = m.IngestionRun(source_system_id=self.source.id, location_id=self.md.id, status="RUNNING", started_at=observed)
        self.db.add(run)
        self.db.flush()
        result = SimpleNamespace(ok=True, truncated_by_safety_guard=False, elements=[
            {"id": "MD-SHIFT", "employee": {"id": "E1"}, "inTime": int(observed.timestamp()*1000)}])
        with patch.object(acquisition, "paginate", return_value=result):
            acquisition._fetch_and_ingest_shifts(SimpleNamespace(merchant_id="MD"), self.db,
                period_start=observed, period_end=observed, source_system_id=self.source.id,
                employee_by_source_id={"E1": self.legacy.id}, ingestion_run_id=run.id, retrieved_at=observed)
        shift = self.db.scalar(select(m.Shift))
        self.assertEqual(shift.employee_id, self.legacy.id)
        self.assertEqual(shift.location_id, self.md.id)

    def test_location_scope_includes_shared_person_and_historical_links_once(self):
        self.link(self.wp, "E1")
        self.link(self.md, "MD-E1")
        ids = lambda locations: list(self.db.scalars(directory.employees_for_locations(locations)))
        self.assertEqual([e.id for e in ids([self.md.id])], [self.legacy.id])
        self.assertEqual(len(ids([self.wp.id, self.md.id])), 1)
        self.absent(self.md)
        self.assertEqual([e.id for e in ids([self.md.id])], [self.legacy.id])
        self.assertEqual(ids([]), [])
        self.assertEqual([e.id for e in ids(select(m.Location.id).where(m.Location.id == self.md.id))], [self.legacy.id])

    def test_location_scope_excludes_retired_identity(self):
        retired = m.Employee(location_id=self.md.id, display_name="Retired copy")
        self.db.add(retired)
        self.db.flush()
        self.db.add(m.EmployeeIdentityAlias(employee_id=retired.id, canonical_employee_id=self.legacy.id))
        self.db.flush()
        rows = list(self.db.scalars(directory.employees_for_locations([self.wp.id, self.md.id])))
        self.assertEqual([e.id for e in rows], [self.legacy.id])

    def test_payroll_resolves_shared_person_in_second_restaurant(self):
        from rfone_data_store.payroll.adp_importer import ParsedEmployeeRow, resolve_employee_mappings
        self.link(self.wp, "E1")
        self.link(self.md, "MD-E1")
        restaurant = m.Restaurant(name="MD restaurant")
        self.db.add(restaurant); self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=self.md.id))
        self.db.flush()
        result = resolve_employee_mappings(self.db, source_system_id=self.source.id,
            restaurant_id=restaurant.id, rows=[ParsedEmployeeRow(1, "Smith, Jane", None, None, None)])
        self.assertEqual([r.employee_id for r in result.values()], [self.legacy.id])

    def test_role_bootstrap_never_creates_an_assignment_from_clover_roles(self):
        # OQ-7: the Registry is the only authority for assignments, also with second-site Clover evidence.
        from rfone_data_store.profile.bootstrap import bootstrap_restaurant_profile, MODE_PERSIST
        self.link(self.wp, "E1")
        self.link(self.md, "MD-E1")
        restaurant = m.Restaurant(name="MD restaurant")
        self.db.add(restaurant); self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=self.md.id))
        role = m.SourceRole(location_id=self.md.id, source_system_id=self.source.id,
                            source_role_id="MD-SERVER", name="Server")
        self.db.add(role); self.db.flush()
        self.db.add(m.EmployeeSourceRole(employee_id=self.legacy.id, source_role_id=role.id, source_system_id=self.source.id))
        self.db.flush()
        wp_role = m.SourceRole(location_id=self.wp.id, source_system_id=self.source.id,
                               source_role_id="WP-HOST", name="Host")
        self.db.add(wp_role); self.db.flush()
        self.db.add(m.EmployeeSourceRole(employee_id=self.legacy.id, source_role_id=wp_role.id,
                                         source_system_id=self.source.id))
        self.db.flush()
        now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        for _ in range(2):
            bootstrap_restaurant_profile(self.db, restaurant_id=restaurant.id,
                source_system_id=self.source.id, mode=MODE_PERSIST, sync_time=now)
            self.db.flush()
        self.assertEqual(list(self.db.scalars(select(m.EmployeeAssignment))), [])
        self.assertEqual(self.legacy.location_id, self.wp.id)

    def test_selector_state_matches_directory_and_preserves_internal_override(self):
        self.legacy.active = None
        self.link(self.wp, "E1") if not self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.external_employee_id == "E1", m.EmployeeCloverLink.merchant_id == "WP")) else self.restore(self.wp)
        self.assertTrue(directory.employee_options(self.db)[0].is_active)
        self.absent(self.wp)
        self.assertTrue(directory.employee_options(self.db)[0].is_active)
        historical = directory.employee_options(self.db, include_inactive=True)
        self.assertEqual([option.id for option in historical], [self.legacy.id])
        self.assertTrue(historical[0].is_active)
        self.legacy.active = True
        self.assertTrue(directory.employee_options(self.db)[0].is_active)
        self.legacy.active = False
        self.link(self.wp, "E1") if not self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.external_employee_id == "E1", m.EmployeeCloverLink.merchant_id == "WP")) else self.restore(self.wp)
        self.assertEqual(directory.employee_options(self.db), [])
        self.assertFalse(directory.employee_options(self.db, include_inactive=True)[0].is_active)

    def test_selector_sites_are_scoped_and_unique_with_historical_absence(self):
        self.link(self.wp, "E1")
        self.link(self.md, "MD-E1")
        options = directory.employee_options(self.db)
        self.assertEqual(len(options), 1)
        self.assertEqual(set(options[0].location_ids), {self.wp.id, self.md.id})
        scoped = directory.employee_options(self.db, location_ids=[self.md.id])
        self.assertEqual(scoped[0].location_names, (self.md.name,))
        self.absent(self.md)
        self.assertEqual(directory.employee_options(self.db, location_ids=[self.md.id]), [])
        historical = directory.employee_options(self.db, location_ids=[self.md.id], include_inactive=True)
        self.assertEqual([option.id for option in historical], [self.legacy.id])
        self.assertEqual(directory.employee_options(self.db, location_ids=[]), [])

    def test_selector_resolves_selected_alias_without_widening_scope(self):
        self.legacy.active = False
        retired = m.Employee(location_id=self.wp.id, display_name="Old identity")
        self.db.add(retired); self.db.flush()
        self.db.add(m.EmployeeIdentityAlias(employee_id=retired.id, canonical_employee_id=self.legacy.id))
        self.db.flush()
        options = directory.employee_options(self.db, selected_employee_ids=[retired.id])
        self.assertEqual([option.id for option in options], [self.legacy.id])
        self.assertTrue(options[0].is_selected)
        self.assertFalse(options[0].is_active)
        self.assertEqual(directory.employee_options(self.db, location_ids=[self.md.id],
            selected_employee_ids=[retired.id]), [])

    def test_selector_keeps_homonyms_and_has_stable_order(self):
        other = m.Employee(location_id=self.wp.id, display_name=self.legacy.display_name)
        unnamed = m.Employee(location_id=self.wp.id)
        self.db.add_all([other, unnamed]); self.db.flush()
        options = directory.employee_options(self.db)
        self.assertEqual([option.id for option in options], [unnamed.id, self.legacy.id, other.id])
        self.assertEqual(options[0].location_names, (self.wp.name,))
        self.assertEqual(len(options), 3)

    def test_selector_is_readonly_and_unverified_people_stay_available(self):
        self.legacy.active = None
        self.link(self.wp, "E1", state="UNVERIFIED")
        self.db.commit()
        from sqlalchemy import event
        statements = []
        def track(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", track)
        try:
            options = directory.employee_options(self.db, location_ids=select(m.Location.id))
        finally:
            event.remove(self.engine, "before_cursor_execute", track)
        self.assertEqual([option.id for option in options], [self.legacy.id])
        self.assertTrue(options[0].is_active)
        self.assertFalse(self.db.dirty)
        self.assertFalse(self.db.new)
        self.assertTrue(all(statement.lstrip().upper().startswith(("SELECT", "BEGIN", "PRAGMA")) for statement in statements))
        self.assertLessEqual(sum(statement.lstrip().upper().startswith("SELECT") for statement in statements), 6)

    def test_bank_employee_choices_use_shared_state_and_exclude_aliases(self):
        from rfone_data_store.bank_reconciliation.configuration import cardholder_candidates
        self.legacy.active = None
        self.link(self.wp, "E1") if not self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.external_employee_id == "E1", m.EmployeeCloverLink.merchant_id == "WP")) else self.restore(self.wp)
        retired = m.Employee(location_id=self.wp.id, display_name="Old copy")
        self.db.add(retired); self.db.flush()
        self.db.add(m.EmployeeIdentityAlias(employee_id=retired.id, canonical_employee_id=self.legacy.id))
        self.db.flush()
        choices = cardholder_candidates(self.db)
        self.assertEqual([choice["id"] for choice in choices], [self.legacy.id])
        self.assertEqual(choices[0]["location_names"], (self.wp.name,))
        self.absent(self.wp)
        self.assertEqual([choice["id"] for choice in cardholder_candidates(self.db)], [self.legacy.id])

    def test_tips_history_selector_renders_inactive_and_resolves_alias_in_scope(self):
        import importlib.util
        import os
        from pathlib import Path
        import sys
        from unittest.mock import patch
        from rfone_data_store.database import create_session_factory
        restaurant = m.Restaurant(name="WP selector test")
        self.db.add(restaurant); self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=self.wp.id))
        self.legacy.active = False
        outside = m.Employee(location_id=self.md.id, display_name="Outside scope")
        retired = m.Employee(location_id=self.wp.id, display_name="Retired selector identity")
        self.db.add_all([outside, retired]); self.db.flush()
        self.db.add(m.EmployeeIdentityAlias(employee_id=retired.id, canonical_employee_id=self.legacy.id))
        restaurant_id, retired_id, employee_id, outside_id = restaurant.id, retired.id, self.legacy.id, outside.id
        self.db.commit()
        tips = Path(__file__).resolve().parent.parent / "Tips"
        sys.path.insert(0, str(tips))
        with patch.dict(os.environ, {"RFONE_DATABASE_URL": "sqlite://", "RFONE_FLASK_SECRET_KEY": "test-only"}):
            spec = importlib.util.spec_from_file_location("tips_selector_http_test", tips / "app.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        # Flask's context processors open a second session. A file-backed
        # disposable snapshot provides separate connections for that lifecycle.
        import sqlite3
        import tempfile
        temporary = tempfile.TemporaryDirectory(prefix="rfone-selector-http-")
        self.addCleanup(temporary.cleanup)
        database_path = Path(temporary.name) / "selectors.db"
        with sqlite3.connect(database_path) as target, self.engine.connect() as source:
            source.connection.driver_connection.backup(target)
        target.close()
        http_engine = create_configured_engine("sqlite:///" + database_path.as_posix())
        self.addCleanup(http_engine.dispose)
        module.SessionFactory = create_session_factory(http_engine)
        # A signed-in account with TIPS access (Registry gate) — this test is about the selector, not access.
        # The stub carries the attributes the central site authorization reads (an administrator: every site).
        from types import SimpleNamespace
        signed_in = SimpleNamespace(id=0, status="ACTIVE", is_admin=True, is_owner=False, display_name="Test", username="test")
        with patch.object(module.rfone_identity, "current_account", return_value=signed_in),                 patch.object(module.shared_session, "account_may_enter_domain", return_value=True):
            response = module.app.test_client().get(f"/host-audit?employee_id={retired_id}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(f'value="{employee_id}" selected', html)
        self.assertIn("Inactive", html)
        self.assertIn(self.wp.name, html)
        self.assertNotIn("Retired selector identity", html)
        self.assertNotIn("Outside scope", html)
        start, end = datetime(2026, 10, 1), datetime(2026, 10, 2)
        with module.SessionFactory() as db, patch.object(module, "_restaurant_period_config", return_value=(None, "America/New_York", None, None, None)), patch.object(module, "_calculation_period_dt", return_value=(start, end)), patch.object(module.audit_svc, "build_host_audit_report", return_value=None) as build:
            scoped_restaurant = db.get(m.Restaurant, restaurant_id)
            for path in ("/host-audit", "/host-audit/export.csv"):
                with module.app.test_request_context(f"{path}?employee_id={retired_id}&start_at=2026-10-01&end_at=2026-10-02"):
                    module._host_audit_report_from_request(db, scoped_restaurant)
                    self.assertEqual(build.call_args.kwargs["host_employee_id"], employee_id)
                build.reset_mock()
                with module.app.test_request_context(f"{path}?employee_id={outside_id}&start_at=2026-10-01&end_at=2026-10-02"):
                    self.assertIsNone(module._host_audit_report_from_request(db, scoped_restaurant))
                    build.assert_not_called()

    def test_bank_selector_never_deduplicates_people_by_equal_name(self):
        from rfone_data_store.bank_reconciliation.configuration import cardholder_candidates
        identity = m.ActingIdentity(kind="HUMAN_USER", display_name=self.legacy.display_name)
        system = m.ActingIdentity(kind="SYSTEM", display_name="System")
        homonym = m.Employee(location_id=self.wp.id, display_name=self.legacy.display_name)
        self.db.add_all([identity, system, homonym]); self.db.flush()
        choices = cardholder_candidates(self.db)
        self.assertEqual({(choice["kind"], choice["id"]) for choice in choices}, {
            (m.CARD_HOLDER_KIND_ACTING_IDENTITY, identity.id),
            (m.CARD_HOLDER_KIND_EMPLOYEE, self.legacy.id),
            (m.CARD_HOLDER_KIND_EMPLOYEE, homonym.id)})


if __name__ == "__main__":
    unittest.main(verbosity=2)
