"""TIPS_REGISTRY_ONLY_001 (Product Owner, 2026-11-21): Registry decides who a person is and which roles they
hold; Clover only records what happens. The Tips engine reads roles exclusively from the Registry
assignments valid at the date, site and role of the work — never the role a person has in Clover.

Disposable in-memory SQLite; no external data.

Usage:
    python -m unittest test_tips_registry_only
"""
import unittest
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from unittest import mock

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from rfone_data_store import models as m
from rfone_data_store.tips import distribution_engine as engine, distribution_rule_service as rules

UTC = timezone.utc
T = datetime(2026, 10, 21, 8, tzinfo=UTC)  # 04:00 New York: business-day cutoff


class RegistryOnlyTips(unittest.TestCase):
    def setUp(self):
        self.db = create_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.db)
        self.s = Session(self.db)
        self.ss = self.add(m.SourceSystem(code="CLOVER", name="Clover", active=True))
        self.merchant = self.add(m.Merchant(source_system_id=self.ss.id, source_merchant_id="WP", name="WP"))
        self.loc = self.location("WP")
        self.other_loc = self.location("WP-PATIO")
        self.restaurant = self.add(m.Restaurant(name="WP", default_currency="USD"))
        for loc in (self.loc, self.other_loc):
            self.add(m.RestaurantLocation(restaurant_id=self.restaurant.id, location_id=loc.id, is_primary=loc is self.loc))
        self.area = self.add(m.OperationalArea(restaurant_id=self.restaurant.id, name="FOH"))
        self.server_role = self.add(m.RestaurantRole(restaurant_id=self.restaurant.id, name="Server"))
        self.host_role = self.add(m.RestaurantRole(restaurant_id=self.restaurant.id, name="Host"))
        self.n = 0
        self.server = self.employee("S", self.server_role)
        self.a, self.b = self.employee("A", self.host_role), self.employee("B", self.host_role)
        self.rule = rules.create_rule(self.s, restaurant_id=self.restaurant.id, source_role_id=self.server_role.id,
            recipient_role_id=self.host_role.id, calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal(10),
            effective_from=T - timedelta(days=30), aggregation_scope=m.AGGREGATION_SCOPE_SOURCE_BUSINESS_DAY,
            eligibility_mode=m.ELIGIBILITY_MODE_WORKED_DURING_BUSINESS_DAY,
            distribution_method=m.DISTRIBUTION_METHOD_HOURS_PROPORTIONAL)

    def tearDown(self):
        self.s.close()
        self.db.dispose()

    # --- fixture helpers -----------------------------------------------------------------------
    def add(self, obj):
        self.s.add(obj)
        self.s.flush()
        return obj

    def location(self, code):
        return self.add(m.Location(merchant_id=self.merchant.id, source_system_id=self.ss.id,
            source_location_id=code, name=code, currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=time(4)))

    def employee(self, code, role, *, valid_from=None, valid_to=None, location_id=None):
        e = self.add(m.Employee(location_id=self.loc.id, source_system_id=self.ss.id,
            source_employee_id=code, display_name=code, system_role="EMPLOYEE"))
        if role is not None:
            self.assign(e, role, valid_from=valid_from, valid_to=valid_to, location_id=location_id)
        return e

    def assign(self, e, role, *, valid_from=None, valid_to=None, location_id=None, source="MANUAL"):
        return self.add(m.EmployeeAssignment(employee_id=e.id, restaurant_id=self.restaurant.id,
            operational_area_id=self.area.id, restaurant_role_id=role.id, location_id=location_id,
            valid_from=valid_from or T - timedelta(days=30), valid_to=valid_to, assignment_source=source))

    def clover_link(self, e, external_id, role_name, *, merchant="WP", location=None):
        """The person's identity in Clover, with the role Clover shows for it (never read by Tips)."""
        link = self.add(m.EmployeeCloverLink(employee_id=e.id, location_id=(location or self.loc).id,
            merchant_id=merchant, external_employee_id=external_id, state="PRESENT", last_seen_at=T,
            snapshot={"id": external_id, "roles": [{"id": f"R-{role_name}", "name": role_name}],
                      "roles_observed_at": T.isoformat()}))
        self.add(m.EmployeeDirectoryEvent(employee_id=e.id, link_id=link.id, action="IMPORT",
            details={"snapshot": link.snapshot, "observed_at": T.isoformat()}))
        return link

    def shift(self, who, lo, hi, location=None):
        self.n += 1
        return self.add(m.Shift(employee_id=who.id, source_system_id=self.ss.id, source_shift_id=f"SH{self.n}",
            clock_in=lo, clock_out=hi, location_id=(location or self.loc).id))

    def order(self, tip, at=None, who=None):
        self.n += 1
        who = who or self.server
        at = at or T + timedelta(hours=8)
        o = self.add(m.Order(location_id=self.loc.id, source_system_id=self.ss.id, source_order_id=f"O{self.n}",
            employee_id=who.id, created_at=at - timedelta(hours=1), state="locked", payment_state="PAID",
            currency="USD", total=10000))
        p = self.add(m.Payment(order_id=o.id, source_system_id=self.ss.id, source_payment_id=f"P{self.n}",
            employee_id=who.id, created_at=at, amount=10000, result="SUCCESS", currency="USD"))
        self.add(m.PaymentTip(payment_id=p.id, amount=tip, source_present=True))
        return o

    def calculate(self, start=None, end=None):
        self.s.flush()
        return engine.calculate_tips(self.s, restaurant_id=self.restaurant.id,
            period_start=start or T, period_end=end or T + timedelta(days=1))

    @staticmethod
    def received(result):
        out = {}
        for line in result.recipient_lines:
            out[line.recipient_employee_id] = out.get(line.recipient_employee_id, 0) + line.allocated_amount_minor
        return out

    @staticmethod
    def fingerprint(result):
        return (result.blocked_reason, sorted(
            (l.order_id, l.rule_version_id, l.recipient_employee_id, l.allocated_amount_minor, l.pool_amount_minor)
            for l in result.lines))

    def standard_day(self):
        self.shift(self.a, T + timedelta(hours=2), T + timedelta(hours=8))      # 6 h
        self.shift(self.b, T + timedelta(hours=8), T + timedelta(hours=10))     # 2 h
        self.shift(self.server, T + timedelta(hours=2), T + timedelta(hours=12))
        self.order(1000)
        self.order(3000, at=T + timedelta(hours=9))

    # --- 1. changing the Clover role never changes Tips -----------------------------------------
    def test_changing_the_clover_role_does_not_change_the_result(self):
        self.standard_day()
        links = {e.id: self.clover_link(e, f"C-{e.source_employee_id}", role)
                 for e, role in ((self.server, "Server"), (self.a, "Host"), (self.b, "Host"))}
        self.add(m.RegistryRoleMapping(restaurant_id=self.restaurant.id, source="CLOVER", original_key="R-Host",
            original_label="Host", restaurant_role_id=self.host_role.id, valid_from=T - timedelta(days=60), origin="SEED"))
        before = self.calculate()
        self.assertIsNone(before.blocked_reason)
        self.assertEqual(self.received(before), {self.a.id: 300, self.b.id: 100})

        # Arbitrary Clover-side changes: roles swapped, an undefined role, a role change event, the Registry
        # correspondence of Clover roles removed. None of them is a Registry assignment.
        for e, new_role in ((self.server, "Admin"), (self.a, "BOH"), (self.b, "Employee")):
            link = links[e.id]
            link.snapshot = {**link.snapshot, "roles": [{"id": f"R-{new_role}", "name": new_role}]}
            self.add(m.EmployeeDirectoryEvent(employee_id=e.id, link_id=link.id, action="CLOVER_ROLE_CHANGE",
                details={"previous_observed_at": T.isoformat(), "before": ["R-Host"], "after": [f"R-{new_role}"],
                         "observed_at": (T + timedelta(hours=5)).isoformat()}))
        self.s.execute(delete(m.RegistryRoleMapping))
        after = self.calculate()
        self.assertEqual(self.fingerprint(after), self.fingerprint(before))

    def test_a_clover_import_with_changed_roles_changes_neither_registry_nor_tips(self):
        from rfone_data_store import employee_directory as directory
        from sqlalchemy import select

        def roster(server_role, host_role):
            return [{"id": f"C-{e.source_employee_id}", "name": e.display_name, "role": "EMPLOYEE",
                     "roles": {"elements": [{"id": f"R-{r}", "name": r, "systemRole": "EMPLOYEE"}]}}
                    for e, r in ((self.server, server_role), (self.a, host_role), (self.b, host_role))]

        # As at Winter Park today: the assignments were once written by the former automatic Clover sync,
        # in the Restaurant Operations area, and Registry holds correspondences for the Clover roles.
        self.area.code = "ROOT"
        for a in self.s.scalars(select(m.EmployeeAssignment)):
            a.assignment_source = "CLOVER_ROLE_SYNC"
        for key, role in (("R-Server", self.server_role), ("R-Host", self.host_role), ("R-Admin", self.host_role)):
            self.add(m.RegistryRoleMapping(restaurant_id=self.restaurant.id, source="CLOVER", original_key=key,
                original_label=key[2:], restaurant_role_id=role.id, valid_from=T - timedelta(days=60), origin="SEED"))
        for e in (self.server, self.a, self.b):
            self.add(m.EmployeeCloverLink(employee_id=e.id, location_id=self.loc.id, merchant_id="WP",
                external_employee_id=f"C-{e.source_employee_id}", state="PRESENT", last_seen_at=T, snapshot={}))
        self.standard_day()
        assignments = lambda: sorted((a.employee_id, a.restaurant_role_id, a.valid_to)
                                     for a in self.s.scalars(select(m.EmployeeAssignment)))
        before, registry_before = self.calculate(), assignments()
        # REGISTRY_MULTISITE_001: no staff-list import exists any more; even Clover data stored on the links
        # saying the server is now "Admin" (which a correspondence maps to Host) changes nothing.
        for link in self.s.scalars(select(m.EmployeeCloverLink)):
            link.snapshot = {"roles": [{"id": "R-Admin", "name": "Admin"}]}
        self.s.flush()
        self.assertEqual(assignments(), registry_before)
        self.assertEqual(self.fingerprint(self.calculate()), self.fingerprint(before))

    def test_the_engine_never_reads_clover_roles(self):
        self.standard_day()
        self.clover_link(self.a, "C-A", "Host")
        with mock.patch("rfone_data_store.employee_directory.named_roles",
                        side_effect=AssertionError("Tips read a Clover role")):
            result = self.calculate()
        self.assertIsNone(result.blocked_reason)
        self.assertNotIn("Clover role", " ".join(result.registry_anomalies))

    # --- 2. two Clover identities, one RF-One person --------------------------------------------
    def test_two_clover_identities_are_one_person(self):
        self.clover_link(self.a, "WP-A", "Host", merchant="WP")
        self.clover_link(self.a, "MD-A", "Server", merchant="MD")   # same person, another Clover identity
        # Both identities resolve to the same RF-One person (the Directory link): two Shifts, one recipient.
        self.shift(self.a, T + timedelta(hours=2), T + timedelta(hours=5))
        self.shift(self.a, T + timedelta(hours=6), T + timedelta(hours=9))
        self.shift(self.b, T + timedelta(hours=2), T + timedelta(hours=8))
        self.shift(self.server, T + timedelta(hours=2), T + timedelta(hours=12))
        self.order(2400)
        result = self.calculate()
        self.assertIsNone(result.blocked_reason)
        recipients = {l.recipient_employee_id for l in result.recipient_lines}
        self.assertEqual(recipients, {self.a.id, self.b.id})
        worked = {l.recipient_employee_id: l.recipient_worked_seconds for l in result.recipient_lines}
        self.assertEqual(worked[self.a.id], Decimal(6 * 3600))      # 3 h + 3 h of the same person
        self.assertEqual(self.received(result), {self.a.id: 120, self.b.id: 120})
        review = engine.build_employee_review(self.s, result)
        self.assertEqual(sum(1 for row in review if row.employee_id == self.a.id), 1)

    # --- 3. Registry assignments by site and date -------------------------------------------------
    def test_assignment_is_respected_for_site_and_date(self):
        self.s.execute(delete(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == self.b.id))
        self.assign(self.b, self.host_role, location_id=self.other_loc.id)            # Host only on the patio
        late = self.employee("C", self.host_role, valid_from=T + timedelta(hours=6))  # Host from 6 h into the day
        gone = self.employee("D", self.host_role, valid_to=T)                         # no longer Host that day
        self.shift(self.a, T + timedelta(hours=2), T + timedelta(hours=8))
        self.shift(self.b, T + timedelta(hours=2), T + timedelta(hours=8))
        self.shift(late, T + timedelta(hours=2), T + timedelta(hours=8))
        self.shift(gone, T + timedelta(hours=2), T + timedelta(hours=8))
        self.shift(self.server, T + timedelta(hours=2), T + timedelta(hours=12))
        self.order(2000)
        result = self.calculate()
        self.assertIsNone(result.blocked_reason)
        worked = {l.recipient_employee_id: l.recipient_worked_seconds for l in result.recipient_lines}
        self.assertEqual(worked, {self.a.id: Decimal(6 * 3600), late.id: Decimal(2 * 3600)})
        self.assertEqual(self.received(result), {self.a.id: 150, late.id: 50})

    # --- 4. a historical Registry role change ------------------------------------------------------
    def test_historical_registry_change_gives_the_right_result_per_period(self):
        change = T + timedelta(days=1)                    # B: Host until the change, Server afterwards
        assignment_b = next(a for a in self.s.query(m.EmployeeAssignment).filter_by(employee_id=self.b.id))
        assignment_b.valid_to = change
        self.assign(self.b, self.server_role, valid_from=change)
        for day in (0, 1):
            base = T + timedelta(days=day)
            self.shift(self.a, base + timedelta(hours=2), base + timedelta(hours=8))
            self.shift(self.b, base + timedelta(hours=2), base + timedelta(hours=8))
            self.shift(self.server, base + timedelta(hours=2), base + timedelta(hours=12))
            self.order(1000, at=base + timedelta(hours=7))
        self.order(500, at=change + timedelta(hours=7), who=self.b)     # B's own order, as Server, on day 2
        day1 = self.calculate(T, T + timedelta(days=1))
        day2 = self.calculate(T + timedelta(days=1), T + timedelta(days=2))
        self.assertEqual(self.received(day1), {self.a.id: 50, self.b.id: 50})
        self.assertEqual(self.received(day2), {self.a.id: 150})          # B is no longer a recipient
        self.assertTrue(any(l.source_employee_id == self.b.id for l in day2.lines))   # B's order is a source

    # --- 5. missing Registry role: explicit anomaly, no fallback ---------------------------------
    def test_missing_registry_role_of_an_order_owner_blocks_explicitly(self):
        self.standard_day()
        self.clover_link(self.server, "C-S", "Server")    # Clover says Server: it must not be used
        self.s.execute(delete(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == self.server.id))
        result = self.calculate()
        self.assertIsNotNone(result.blocked_reason)
        self.assertIn("Registry role missing or ambiguous", result.blocked_reason)
        self.assertIn(f"S (#{self.server.id})", result.blocked_reason)
        self.assertIn("no Registry role valid at that time", result.blocked_reason)
        self.assertEqual(result.lines, [])

    def test_owner_without_role_does_not_block_a_rule_that_ignores_the_owner_role(self):
        # An ORDER_SERVICE_OWNER rule does not need the owner's role: no anomaly, no block.
        for version in rules.list_versions(self.s, self.rule.id):
            version.status = m.TIP_RULE_VERSION_STATUS_CANCELLED
        rules.create_rule(self.s, restaurant_id=self.restaurant.id, recipient_role_id=self.host_role.id,
            calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal(10), effective_from=T - timedelta(days=30),
            source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER, source_role_id=None)
        self.standard_day()
        self.s.execute(delete(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == self.server.id))
        result = self.calculate()
        self.assertIsNone(result.blocked_reason)
        self.assertFalse(any(a.startswith("BLOCKING") for a in result.registry_anomalies))

    def test_worker_without_registry_role_is_reported_and_never_assumed(self):
        self.standard_day()
        kitchen = self.employee("K", None)
        self.clover_link(kitchen, "C-K", "Host")           # Clover says Host: ignored
        self.shift(kitchen, T + timedelta(hours=2), T + timedelta(hours=8))
        result = self.calculate()
        self.assertIsNone(result.blocked_reason)
        self.assertNotIn(kitchen.id, self.received(result))
        self.assertEqual(result.summary.shifts_without_registry_role, 1)
        self.assertTrue(any(f"K (#{kitchen.id})" in a and "without a Registry role" in a
                            for a in result.registry_anomalies))
        self.assertIn("shifts_without_registry_role=1", engine.summarize_notes(result))


if __name__ == "__main__":
    unittest.main()
