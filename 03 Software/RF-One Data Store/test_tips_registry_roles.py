"""Tips reads Clover role -> RF-One role only from Registry (TIPS_REGISTRY_ROLES_001). Disposable SQLite."""
from datetime import datetime, timedelta, timezone
import unittest

from rfone_data_store import models as m
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.tips.clover_role_history import CloverRoleHistory

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
SEED = datetime(2026, 11, 21, 3, 20, tzinfo=timezone.utc)


class TipsRegistryRolesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        db = self.db = create_session_factory(self.engine)()
        src = m.SourceSystem(code="CLOVER", name="Clover"); db.add(src); db.flush()
        merchant = m.Merchant(name="RF", source_system_id=src.id, source_merchant_id="WP"); db.add(merchant); db.flush()
        self.wp = m.Location(name="WP", merchant_id=merchant.id, source_system_id=src.id, source_location_id="WP")
        self.md = m.Location(name="MD", merchant_id=merchant.id, source_system_id=src.id, source_location_id="MD")
        db.add_all([self.wp, self.md]); db.flush()
        self.r_wp, self.r_md = m.Restaurant(name="WP"), m.Restaurant(name="MD"); db.add_all([self.r_wp, self.r_md]); db.flush()
        self.server = m.RestaurantRole(restaurant_id=self.r_wp.id, name="Server", code="SERVER", active=True)
        self.host = m.RestaurantRole(restaurant_id=self.r_wp.id, name="Host", code="HOST", active=True)
        db.add_all([self.server, self.host]); db.flush()
        self.alice = m.Employee(location_id=self.wp.id, source_system_id=src.id, source_employee_id="A", display_name="Alice")
        db.add(self.alice); db.flush()
        self.link = m.EmployeeCloverLink(employee_id=self.alice.id, location_id=self.wp.id, merchant_id="WP",
                                         external_employee_id="A", state="PRESENT", last_seen_at=T0,
                                         snapshot={"id": "A", "roles": [{"id": "R-SERV", "name": "Server"}],
                                                   "roles_observed_at": T0.isoformat()})
        db.add(self.link); db.flush()
        db.add(m.EmployeeDirectoryEvent(employee_id=self.alice.id, link_id=self.link.id, action="IMPORT",
               details={"snapshot": self.link.snapshot, "observed_at": T0.isoformat()}))
        self.src = src
        db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def mapping(self, key, label, role, restaurant=None, valid_from=SEED, valid_to=None):
        self.db.add(m.RegistryRoleMapping(restaurant_id=(restaurant or self.r_wp).id, source="CLOVER", original_key=key,
                                          original_label=label, restaurant_role_id=role.id if role else None,
                                          valid_from=valid_from, valid_to=valid_to, origin="SEED"))
        self.db.commit()

    def history(self, restaurant=None, location=None):
        return CloverRoleHistory(self.db, (restaurant or self.r_wp).id, [(location or self.wp).id])

    def test_registry_mapping_recognized_including_before_the_seed_date(self):
        self.mapping("R-SERV", "Server", self.server)
        h = self.history()
        self.assertEqual(h.roles_at(self.alice.id, self.wp.id, T0 + timedelta(hours=5)), {self.server.id})
        self.assertFalse(h.uncertain_shift(self.alice.id, self.wp.id, T0 + timedelta(hours=1), T0 + timedelta(hours=9)))

    def test_later_version_applies_only_from_its_date(self):
        change = SEED + timedelta(days=2)
        self.mapping("R-SERV", "Server", self.server, valid_to=change)
        self.mapping("R-SERV", "Server", self.host, valid_from=change)
        h = self.history()
        self.assertEqual(h.roles_at(self.alice.id, self.wp.id, T0 + timedelta(hours=5)), {self.server.id})
        self.assertEqual(h.roles_at(self.alice.id, self.wp.id, change + timedelta(hours=1)), {self.host.id})

    def test_missing_correspondence_is_to_be_defined_with_a_clear_name(self):
        self.mapping("R-SERV", "Server", None)            # in Registry, RF-One role still to be defined
        h = self.history()
        self.assertEqual(h.roles_at(self.alice.id, self.wp.id, T0 + timedelta(hours=5)), set())
        self.assertEqual(h.undefined_roles(self.alice.id, self.wp.id, T0, T0 + timedelta(hours=9)), ["Server"])

    def test_no_row_at_all_is_also_to_be_defined(self):
        h = self.history()
        self.assertEqual(h.undefined_roles(self.alice.id, self.wp.id, T0, T0 + timedelta(hours=9)), ["Server"])

    def test_mount_dora_mapping_never_used_for_winter_park(self):
        self.mapping("R-SERV", "Server", self.server, restaurant=self.r_md)
        h = self.history()
        self.assertEqual(h.roles_at(self.alice.id, self.wp.id, T0 + timedelta(hours=5)), set())

    def test_old_tips_table_is_not_read(self):
        sr = m.SourceRole(location_id=self.wp.id, source_system_id=self.src.id, source_role_id="R-SERV", name="Server")
        self.db.add(sr); self.db.flush()
        self.db.add(m.SourceRoleMapping(restaurant_id=self.r_wp.id, source_system_id=self.src.id, source_role_id=sr.id,
                                        restaurant_role_id=self.host.id, valid_from=T0 - timedelta(days=30),
                                        mapping_status="ACTIVE", mapping_source="MANUAL"))
        self.db.commit()
        self.mapping("R-SERV", "Server", self.server)
        h = self.history()
        self.assertEqual(h.roles_at(self.alice.id, self.wp.id, T0 + timedelta(hours=5)), {self.server.id})


if __name__ == "__main__":
    unittest.main()
