"""Registry Role/Department table + Clover role sync + historical roles (REGISTRY_CLOVER_DEPARTMENTS_001).
Disposable SQLite, fake Clover."""
from datetime import datetime, timezone
import unittest

from sqlalchemy import func, select

from rfone_data_store import models as m
try:  # registers the Registry role catalog tables where that module is shipped (not in the Clover worker image)
    from rfone_data_store import access_profiles  # noqa: F401
except ImportError:
    access_profiles = None
from rfone_data_store import employee_directory as directory
from rfone_data_store import registry_departments as reg
from rfone_data_store.database import create_configured_engine, create_session_factory


def emp(eid, name, role_id=None, role_name=None):
    raw = {"id": eid, "name": name, "role": "EMPLOYEE"}
    if role_id:
        raw["roles"] = {"elements": [{"id": role_id, "name": role_name, "systemRole": "EMPLOYEE"}]}
    return raw


class RegistryDepartmentsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        db = self.db = create_session_factory(self.engine)()
        self.source = m.SourceSystem(code="CLOVER", name="Clover")
        db.add(self.source); db.flush()
        merchant = m.Merchant(name="RF", source_system_id=self.source.id, source_merchant_id="WP")
        db.add(merchant); db.flush()
        self.wp = m.Location(name="WP", merchant_id=merchant.id, source_system_id=self.source.id,
                             source_location_id="WP", timezone="America/New_York")
        self.md = m.Location(name="MD", merchant_id=merchant.id, source_system_id=self.source.id,
                             source_location_id="MD", timezone="America/New_York")
        db.add_all([self.wp, self.md]); db.flush()
        self.r_wp, self.r_md = m.Restaurant(name="RF WP"), m.Restaurant(name="RF MD")
        db.add_all([self.r_wp, self.r_md]); db.flush()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.add_all([m.RestaurantLocation(restaurant_id=self.r_wp.id, location_id=self.wp.id, valid_from=t0, is_primary=True),
                    m.RestaurantLocation(restaurant_id=self.r_md.id, location_id=self.md.id, valid_from=t0, is_primary=True)])
        self.area = m.OperationalArea(restaurant_id=self.r_wp.id, name="Restaurant Operations", code="ROOT", active=True)
        db.add(self.area); db.flush()
        self.foh = reg.save_department(db, name="Front of House", code="FOH")
        self.boh = reg.save_department(db, name="Back of House", code="BOH")
        self.roles = {}
        for code, name, dep in (("SERVER", "Server", self.foh), ("HOST", "Host", self.foh),
                                ("MANAGER", "Manager", None), ("COOK", "Cook", self.boh)):
            role = m.RestaurantRole(restaurant_id=self.r_wp.id, name=name, code=code, active=True)
            db.add(role); db.flush()
            db.add(m.OperationalAreaRole(operational_area_id=self.area.id, restaurant_role_id=role.id))
            reg.set_role_department(db, restaurant_role_id=role.id, department_id=dep.id if dep else None)
            self.roles[code] = role
        self.alice = m.Employee(location_id=self.wp.id, source_system_id=self.source.id, source_employee_id="A",
                                display_name="Alice Hand", active=True)
        self.bob = m.Employee(location_id=self.wp.id, source_system_id=self.source.id, source_employee_id="B",
                              display_name="Bob Cook")
        db.add_all([self.alice, self.bob]); db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def sync(self, records, location=None):
        location = location or self.wp
        out = directory.import_snapshot(self.db, location_id=location.id, merchant_id=location.source_location_id,
                                        records=records)
        self.db.commit()
        return out

    def map(self, clover_id, role_code=None, department=None, restaurant=None):
        return reg.set_role_mapping(self.db, restaurant_id=(restaurant or self.r_wp).id, source=reg.CLOVER,
                                    original_key=clover_id, restaurant_role_id=self.roles[role_code].id if role_code else None,
                                    department_id=department.id if department else None)

    def open_assignments(self, employee):
        return list(self.db.scalars(select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.employee_id == employee.id, m.EmployeeAssignment.valid_to.is_(None))))

    def count(self, model):
        return self.db.scalar(select(func.count()).select_from(model))

    def roster(self, alice_role=("R1", "Server"), bob_role=("R2", "BOH")):
        return [emp(e, n, *r) for e, n, r in (("A", "Alice Hand", alice_role), ("B", "Bob Cook", bob_role)) if r is not None]

    def first_import_with_table(self):
        self.sync(self.roster())                       # roles become known
        self.map("R1", "SERVER"); self.map("R2", None, self.boh)
        self.db.commit()

    def test_mapping_assigns_and_classifies(self):
        self.first_import_with_table()
        [a] = self.open_assignments(self.alice)
        self.assertEqual((a.restaurant_role_id, a.operational_area_id, a.assignment_source),
                         (self.roles["SERVER"].id, self.area.id, "CLOVER_ROLE_SYNC"))
        self.assertEqual(self.open_assignments(self.bob), [])          # BOH: department certain, RF-One role not
        self.assertEqual(reg.department_of(self.db, self.alice.id), {"FOH"})
        self.assertEqual(reg.department_of(self.db, self.bob.id), {"BOH"})

    def test_department_follows_rf_role(self):
        self.first_import_with_table()
        reg.set_role_department(self.db, restaurant_role_id=self.roles["SERVER"].id, department_id=self.boh.id)
        self.assertEqual(reg.department_of(self.db, self.alice.id), {"BOH"})
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RegistryRoleDepartment).where(
            m.RegistryRoleDepartment.restaurant_role_id == self.roles["SERVER"].id)), 2)   # history kept

    def test_second_import_without_changes_creates_nothing(self):
        self.first_import_with_table()
        models = (m.EmployeeAssignment, m.SourceRole, m.RegistryRoleMapping, m.RegistryRoleDepartment,
                  m.EmployeeDirectoryEvent, m.Employee, m.EmployeeCloverLink)
        before = {model: self.count(model) for model in models}
        self.sync(self.roster()); self.sync(self.roster())
        self.assertEqual(before, {model: self.count(model) for model in models})

    def test_role_change_closes_previous_and_opens_new(self):
        self.first_import_with_table()
        self.sync(self.roster(alice_role=("R3", "Host")))
        self.map("R3", "HOST"); self.db.commit()
        history = list(self.db.scalars(select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.employee_id == self.alice.id).order_by(m.EmployeeAssignment.id)))
        self.assertEqual(len(history), 2)
        self.assertIsNotNone(history[0].valid_to)
        self.assertEqual(history[1].restaurant_role_id, self.roles["HOST"].id)
        self.assertEqual(len(self.open_assignments(self.alice)), 1)

    def test_left_clover_closes_assignment_keeps_person(self):
        self.first_import_with_table()
        self.sync(self.roster(alice_role=None))
        self.assertEqual(self.open_assignments(self.alice), [])
        self.assertEqual(self.count(m.EmployeeAssignment), 1)          # history kept
        self.assertIsNotNone(self.db.get(m.Employee, self.alice.id))
        self.assertEqual(reg.department_of(self.db, self.alice.id), set())

    def test_manual_assignment_is_never_replaced(self):
        self.db.add(m.EmployeeAssignment(employee_id=self.alice.id, restaurant_id=self.r_wp.id,
            operational_area_id=self.area.id, restaurant_role_id=self.roles["MANAGER"].id, location_id=self.wp.id,
            valid_from=datetime(2026, 2, 1, tzinfo=timezone.utc), assignment_source="MANUAL"))
        self.db.commit()
        self.first_import_with_table()
        [a] = self.open_assignments(self.alice)
        self.assertEqual((a.assignment_source, a.restaurant_role_id), ("MANUAL", self.roles["MANAGER"].id))

    def test_dry_run_counts_without_writing(self):
        self.sync(self.roster())
        self.db.add(m.RegistryRoleMapping(restaurant_id=self.r_wp.id, source=reg.CLOVER, original_key="R1",
            original_label="Server", restaurant_role_id=self.roles["SERVER"].id,
            valid_from=datetime.now(timezone.utc), origin="SEED"))
        self.db.commit()
        summary = reg.sync_site(self.db, location_id=self.wp.id, merchant_id="WP", dry_run=True)
        self.assertEqual(summary.opened, 1)
        self.assertEqual(self.count(m.EmployeeAssignment), 0)

    def test_md_same_role_name_separate_mapping_and_no_duplicate_person(self):
        self.first_import_with_table()
        _, pending = self.sync([emp("Z", "Alice Hand", "M1", "Server")], self.md)
        self.assertEqual(len(pending), 1)                               # reported for verification
        directory.attach_link(self.db, link_id=pending[0], employee_id=self.alice.id); self.db.commit()
        self.sync([emp("Z", "Alice Hand", "M1", "Server")], self.md)
        self.assertEqual(self.count(m.Employee), 2)                     # no duplicate person
        rows = {r["restaurant_id"]: r for r in reg.classification(self.db, employee_ids=[self.alice.id])}
        self.assertEqual(rows[self.r_wp.id]["department_code"], "FOH")
        self.assertIsNone(rows[self.r_md.id]["department_code"])        # MD "Server" not mapped yet
        self.map("M1", None, self.boh, restaurant=self.r_md)
        rows = {r["restaurant_id"]: r for r in reg.classification(self.db, employee_ids=[self.alice.id])}
        self.assertEqual((rows[self.r_wp.id]["department_code"], rows[self.r_md.id]["department_code"]), ("FOH", "BOH"))

    def test_overview_history_and_missing_flags(self):
        self.first_import_with_table()
        self.map("R1", "HOST"); self.db.commit()
        data = reg.overview(self.db)
        server = [r for s in data["sites"] for r in s["rows"] if r["original_label"] == "Server"][0]
        self.assertEqual(len(server["history"]), 2)
        self.assertEqual(server["people"], 1)
        self.sync(self.roster() + [emp("C", "Carl New", "R9", "Dishwasher")])
        data = reg.overview(self.db)
        dish = [r for s in data["sites"] for r in s["rows"] if r["original_label"] == "Dishwasher"][0]
        self.assertTrue(dish["missing_department"])
        manager = [r for r in data["roles"] if r["name"] == "Manager"][0]
        self.assertTrue(manager["missing_department"])

    @unittest.skipIf(access_profiles is None, "Registry role catalog not shipped in this image")
    def test_save_role_uses_registry_catalog_and_sets_department(self):
        role = reg.save_role(self.db, name="Server Help", department_id=self.foh.id)
        self.assertIsNone(role.restaurant_id)                            # shared Registry catalog
        self.assertNotEqual(role.id, self.roles["SERVER"].id)            # never merged with Server
        self.assertEqual(reg.role_departments(self.db)[role.id], self.foh.id)
        with self.assertRaises(ValueError):
            reg.save_role(self.db, name="server help", department_id=None)

    def test_department_crud_and_uniqueness(self):
        d = reg.save_department(self.db, name="Bar", code="bar")
        self.assertEqual(d.code, "BAR")
        with self.assertRaises(ValueError):
            reg.save_department(self.db, name="Front of house", code="X")
        reg.save_department(self.db, department_id=d.id, name="Bar & Lounge", code="BAR", active=False)
        self.assertFalse(self.db.get(m.RegistryDepartment, d.id).active)

    def test_historical_roles_reconcile_without_touching_current(self):
        self.first_import_with_table()
        reg.set_role_mapping(self.db, restaurant_id=self.r_wp.id, source=reg.EXCEL_WP_NOTE, original_key="4-Cook",
                             restaurant_role_id=self.roles["COOK"].id)
        records = [{"row": 2, "register_id": "A", "name": "Alice Hand", "house": "BOH", "role": "4-Cook"},
                   {"row": 3, "register_id": "B", "name": "Robert Cook", "house": "BOH", "role": "4-Cook"},
                   {"row": 4, "register_id": "B", "name": "Robert Cook", "house": "BOH", "role": "4-Cook"},
                   {"row": 5, "register_id": "X", "name": "Nobody", "house": "FOH", "role": "2-Serv"},
                   {"row": 6, "register_id": None, "name": "QQQ", "house": None, "role": None}]
        dry = reg.load_source_roles(self.db, records, restaurant_id=self.r_wp.id, merchant_id="WP", reference="test", dry_run=True)
        self.assertEqual((dry.reconciled, dry.loaded, len(dry.not_found), len(dry.duplicates), len(dry.incomplete)), (2, 2, 1, 1, 1))
        self.assertEqual(self.count(m.RegistryPersonSourceRole), 0)
        self.assertEqual(len(dry.current_role_differences), 1)            # Alice: Server today, Cook in the document
        self.assertEqual(len(dry.name_differences), 1)                    # Bob Cook vs Robert Cook
        before = (self.count(m.Employee), self.count(m.EmployeeAssignment))
        reg.load_source_roles(self.db, records, restaurant_id=self.r_wp.id, merchant_id="WP", reference="test")
        again = reg.load_source_roles(self.db, records, restaurant_id=self.r_wp.id, merchant_id="WP", reference="test")
        self.assertEqual((again.loaded, again.already_loaded), (0, 2))
        self.assertEqual(before, (self.count(m.Employee), self.count(m.EmployeeAssignment)))
        self.assertEqual(reg.department_of(self.db, self.alice.id, include_history=True), {"FOH"})   # current wins
        self.sync(self.roster(alice_role=None))
        self.assertEqual(reg.department_of(self.db, self.alice.id, include_history=True), {"BOH"})   # history only

    def test_legacy_source_roles_do_not_accumulate(self):
        from rfone_data_store.technical.connectors.clover.historical_backfill_detail import _drop_stale_source_roles
        r1 = m.SourceRole(location_id=self.wp.id, source_system_id=self.source.id, source_role_id="X1", name="Server")
        r2 = m.SourceRole(location_id=self.wp.id, source_system_id=self.source.id, source_role_id="X2", name="Host")
        self.db.add_all([r1, r2]); self.db.flush()
        now = datetime.now(timezone.utc)
        self.db.add_all([m.EmployeeSourceRole(employee_id=self.alice.id, source_role_id=r.id,
                         source_system_id=self.source.id, observed_at=now) for r in (r1, r2)])
        self.db.flush()
        _drop_stale_source_roles(self.db, self.alice.id, self.source.id, {r2.id})
        self.db.flush()
        self.assertEqual([r.source_role_id for r in self.db.scalars(select(m.EmployeeSourceRole))], [r2.id])


if __name__ == "__main__":
    unittest.main()
