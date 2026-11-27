"""Tips per site (TIPS_PER_SITE_001, Product Owner 2026-11-27).

Winter Park and Mount Dora each configure their own Tip Distribution Rules
and percentages. Every Order contributes to the Tips of the site where Clover
recorded it. A person who works at both sites on the same day receives, for
each site, the share computed with that site's own rules and that site's own
worked time. No external data; in-memory SQLite.
"""
import unittest
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rfone_data_store import models as m
from rfone_data_store.tips import distribution_engine as engine, distribution_rule_service as rules

UTC = timezone.utc
DAY = datetime(2026, 11, 20, 9, tzinfo=UTC)  # 04:00 New York: start of the business day
NY = lambda hour: DAY + timedelta(hours=hour - 4)  # noqa: E731 — New York wall-clock hour of DAY


class TipsPerSite(unittest.TestCase):
    def setUp(self):
        self.db = create_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.db)
        self.s = Session(self.db)
        self.ss = self.add(m.SourceSystem(code="TEST", name="Test", active=True))
        self.n = 0
        self.wp = self.site("WP")
        self.md = self.site("MD")
        # One person, Host at both sites; a second Host only at Winter Park.
        self.both = self.employee("BOTH", self.wp)
        self.assign(self.both, self.md, self.md["host"])
        self.assign(self.both, self.wp, self.wp["host"])
        self.wp_only = self.employee("WPONLY", self.wp)
        self.assign(self.wp_only, self.wp, self.wp["host"])
        self.wp_server = self.employee("WPS", self.wp)
        self.assign(self.wp_server, self.wp, self.wp["server"])
        self.md_server = self.employee("MDS", self.md)
        self.assign(self.md_server, self.md, self.md["server"])
        # Winter Park: 10% of tips, Servers -> Hosts, by hours worked in the business day.
        rules.create_rule(self.s, restaurant_id=self.wp["restaurant"].id, source_role_id=self.wp["server"].id,
            recipient_role_id=self.wp["host"].id, calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal(10),
            effective_from=DAY - timedelta(days=30), aggregation_scope=m.AGGREGATION_SCOPE_SOURCE_BUSINESS_DAY,
            eligibility_mode=m.ELIGIBILITY_MODE_WORKED_DURING_BUSINESS_DAY,
            distribution_method=m.DISTRIBUTION_METHOD_HOURS_PROPORTIONAL)
        # Mount Dora: a different formula — 5%, equal split among Hosts on shift when the order opened.
        rules.create_rule(self.s, restaurant_id=self.md["restaurant"].id, source_role_id=self.md["server"].id,
            recipient_role_id=self.md["host"].id, calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal(5),
            effective_from=DAY - timedelta(days=30), aggregation_scope=m.AGGREGATION_SCOPE_ORDER,
            eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
            distribution_method=m.DISTRIBUTION_METHOD_EQUAL)

    def tearDown(self):
        self.s.close()
        self.db.dispose()

    # -- fixture helpers ---------------------------------------------------
    def add(self, obj):
        self.s.add(obj)
        self.s.flush()
        return obj

    def site(self, code):
        merchant = self.add(m.Merchant(source_system_id=self.ss.id, source_merchant_id=code, name=code))
        location = self.add(m.Location(merchant_id=merchant.id, source_system_id=self.ss.id,
            source_location_id=code, name=code, currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=time(4)))
        restaurant = self.add(m.Restaurant(name=code, default_currency="USD"))
        self.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        area = self.add(m.OperationalArea(restaurant_id=restaurant.id, name="FOH"))
        return {"restaurant": restaurant, "location": location, "area": area,
                "server": self.add(m.RestaurantRole(restaurant_id=restaurant.id, name="Server")),
                "host": self.add(m.RestaurantRole(restaurant_id=restaurant.id, name="Host"))}

    def employee(self, code, home):
        return self.add(m.Employee(location_id=home["location"].id, source_system_id=self.ss.id,
            source_employee_id=code, display_name=code, system_role="EMPLOYEE"))

    def assign(self, employee, site, role):
        self.add(m.EmployeeAssignment(employee_id=employee.id, restaurant_id=site["restaurant"].id,
            operational_area_id=site["area"].id, restaurant_role_id=role.id,
            valid_from=DAY - timedelta(days=30), assignment_source="MANUAL"))

    def shift(self, who, site, start_hour, end_hour):
        self.n += 1
        self.add(m.Shift(employee_id=who.id, source_system_id=self.ss.id, source_shift_id=f"S{self.n}",
            clock_in=NY(start_hour), clock_out=NY(end_hour), location_id=site["location"].id))

    def order(self, site, server, tip, open_hour, paid_hour):
        self.n += 1
        order = self.add(m.Order(location_id=site["location"].id, source_system_id=self.ss.id,
            source_order_id=f"O{self.n}", employee_id=server.id, created_at=NY(open_hour),
            state="locked", payment_state="PAID", currency="USD", total=10000))
        payment = self.add(m.Payment(order_id=order.id, source_system_id=self.ss.id,
            source_payment_id=f"P{self.n}", employee_id=server.id, created_at=NY(paid_hour),
            amount=10000, result="SUCCESS", currency="USD"))
        self.add(m.PaymentTip(payment_id=payment.id, amount=tip, source_present=True))
        return order

    def calculate(self, site):
        self.s.flush()
        return engine.calculate_tips(self.s, restaurant_id=site["restaurant"].id,
            period_start=DAY, period_end=DAY + timedelta(days=1))

    @staticmethod
    def received(result, employee):
        return sum(line.allocated_amount_minor for line in result.recipient_lines
                   if line.recipient_employee_id == employee.id)

    # -- scenarios ---------------------------------------------------------
    def test_person_working_both_sites_same_day_gets_each_site_share_with_its_own_rule(self):
        # Same business day: BOTH works 10-14 at Winter Park and 17-22 at Mount Dora.
        self.shift(self.both, self.wp, 10, 14)
        self.shift(self.both, self.md, 17, 22)
        self.shift(self.wp_only, self.wp, 10, 18)
        self.shift(self.wp_server, self.wp, 10, 18)
        self.shift(self.md_server, self.md, 17, 22)
        wp_order = self.order(self.wp, self.wp_server, tip=1000, open_hour=12, paid_hour=13)
        md_order = self.order(self.md, self.md_server, tip=2000, open_hour=18, paid_hour=19)

        wp = self.calculate(self.wp)
        md = self.calculate(self.md)
        self.assertIsNone(wp.blocked_reason)
        self.assertIsNone(md.blocked_reason)

        # Each Order contributes only to the Tips of the site where it was recorded.
        self.assertEqual({line.order_id for line in wp.lines}, {wp_order.id})
        self.assertEqual({line.order_id for line in md.lines}, {md_order.id})
        self.assertEqual(wp.voluntary_total_minor, 1000)
        self.assertEqual(md.voluntary_total_minor, 2000)

        # Winter Park, 10% by hours worked AT WINTER PARK: pool 100; BOTH 4h, WPONLY 8h.
        # (Counting BOTH's 5 Mount Dora hours would give 9h vs 8h — it must not.)
        self.assertEqual(wp.distributed_total_minor, 100)
        self.assertEqual(self.received(wp, self.both), 33)
        self.assertEqual(self.received(wp, self.wp_only), 67)

        # Mount Dora, 5% equal among Hosts on shift when the order opened: pool 100, BOTH alone.
        self.assertEqual(md.distributed_total_minor, 100)
        self.assertEqual(self.received(md, self.both), 100)
        self.assertEqual(self.received(md, self.wp_only), 0)

    def test_each_site_keeps_its_own_rules_and_percentages(self):
        wp_versions = [v for r in rules.list_rules(self.s, self.wp["restaurant"].id)
                       for v in rules.list_versions(self.s, r.id)]
        md_versions = [v for r in rules.list_rules(self.s, self.md["restaurant"].id)
                       for v in rules.list_versions(self.s, r.id)]
        self.assertEqual([v.rate for v in wp_versions], [Decimal(10)])
        self.assertEqual([v.rate for v in md_versions], [Decimal(5)])
        self.assertEqual(wp_versions[0].distribution_method, m.DISTRIBUTION_METHOD_HOURS_PROPORTIONAL)
        self.assertEqual(md_versions[0].distribution_method, m.DISTRIBUTION_METHOD_EQUAL)

    def test_a_site_without_rules_distributes_nothing_and_does_not_borrow_the_other_sites_rules(self):
        for rule in rules.list_rules(self.s, self.md["restaurant"].id):
            rule.is_active = False
        self.shift(self.both, self.md, 17, 22)
        self.shift(self.md_server, self.md, 17, 22)
        self.order(self.md, self.md_server, tip=2000, open_hour=18, paid_hour=19)
        md = self.calculate(self.md)
        self.assertEqual(md.distributed_total_minor, 0)
        self.assertEqual(self.received(md, self.both), 0)


if __name__ == "__main__":
    unittest.main()
