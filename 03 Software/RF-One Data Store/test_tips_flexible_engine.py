"""Executable financial scenarios for the composable Tips engine; no external data."""
import unittest
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from rfone_data_store import models as m
from rfone_data_store.tips import distribution_engine as engine, distribution_rule_service as rules
from rfone_data_store.tips import rule_ai_authoring as authoring

UTC = timezone.utc
T = datetime(2026, 10, 21, 8, tzinfo=UTC)  # 04:00 New York


class FlexibleTips(unittest.TestCase):
    def setUp(self):
        self.db = create_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.db)
        self.s = Session(self.db)
        self.ss = self.add(m.SourceSystem(code="TEST", name="Test", active=True))
        merchant = self.add(m.Merchant(source_system_id=self.ss.id, source_merchant_id="M", name="Test"))
        self.loc = self.add(m.Location(merchant_id=merchant.id, source_system_id=self.ss.id,
            source_location_id="L", name="Test", currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=time(4)))
        self.restaurant = self.add(m.Restaurant(name="Test", default_currency="USD"))
        self.add(m.RestaurantLocation(restaurant_id=self.restaurant.id, location_id=self.loc.id, is_primary=True))
        self.area = self.add(m.OperationalArea(restaurant_id=self.restaurant.id, name="FOH"))
        self.server_role = self.add(m.RestaurantRole(restaurant_id=self.restaurant.id, name="Server"))
        self.host_role = self.add(m.RestaurantRole(restaurant_id=self.restaurant.id, name="Host"))
        self.server = self.employee("S", self.server_role)
        self.a, self.b = self.employee("A", self.host_role), self.employee("B", self.host_role)
        self.n = 0
        self.rule = rules.create_rule(self.s, restaurant_id=self.restaurant.id, source_role_id=self.server_role.id,
            recipient_role_id=self.host_role.id, calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal(10),
            effective_from=T-timedelta(days=30), aggregation_scope=m.AGGREGATION_SCOPE_SOURCE_BUSINESS_DAY,
            eligibility_mode=m.ELIGIBILITY_MODE_WORKED_DURING_BUSINESS_DAY,
            distribution_method=m.DISTRIBUTION_METHOD_HOURS_PROPORTIONAL)
        self.version = rules.list_versions(self.s, self.rule.id)[0]

    def add(self, obj):
        self.s.add(obj); self.s.flush(); return obj

    def employee(self, code, role):
        e = self.add(m.Employee(location_id=self.loc.id, source_system_id=self.ss.id,
            source_employee_id=code, display_name=code, system_role="EMPLOYEE"))
        self.add(m.EmployeeAssignment(employee_id=e.id, restaurant_id=self.restaurant.id,
            operational_area_id=self.area.id, restaurant_role_id=role.id, valid_from=T-timedelta(days=30),
            assignment_source="MANUAL"))
        return e

    def shift(self, who, lo, hi, location=None):
        self.n += 1
        return self.add(m.Shift(employee_id=who.id, source_system_id=self.ss.id, source_shift_id=str(self.n),
            clock_in=lo, clock_out=hi, location_id=location or self.loc.id))

    def order(self, tip, at=None, who=None, gratuity=0):
        self.n += 1; who = who or self.server; at = at or T+timedelta(hours=8)
        o = self.add(m.Order(location_id=self.loc.id, source_system_id=self.ss.id,
            source_order_id=str(self.n), employee_id=who.id, created_at=at-timedelta(hours=1),
            state="locked", payment_state="PAID", currency="USD", total=10000))
        p = self.add(m.Payment(order_id=o.id, source_system_id=self.ss.id, source_payment_id=str(self.n),
            employee_id=who.id, created_at=at, amount=10000, result="SUCCESS", currency="USD"))
        self.add(m.PaymentTip(payment_id=p.id, amount=tip, source_present=True))
        return o

    def calculate(self, start=None, end=None):
        self.s.flush()
        return engine.calculate_tips(self.s, restaurant_id=self.restaurant.id,
            period_start=start or T, period_end=end or T+timedelta(days=1))

    def received(self, result):
        return {i:sum(l.allocated_amount_minor for l in result.recipient_lines if l.recipient_employee_id==i)
            for i in (self.a.id, self.b.id)}

    def tearDown(self):
        self.s.close(); self.db.dispose()

    def test_hours_and_pool_round_once_per_server(self):
        self.shift(self.a,T,T+timedelta(hours=1)); self.shift(self.b,T,T+timedelta(hours=3))
        self.order(15); self.order(15)
        r=self.calculate()
        self.assertEqual(r.distributed_total_minor,3)  # per-order rounding would be 4
        self.assertEqual(self.received(r),{self.a.id:1,self.b.id:2})
        self.assertIsNone(r.blocked_reason)
        self.assertEqual(engine.build_operational_totals(r, engine.build_employee_review(self.s,r)).total_employee_entitlements_minor,30)

    def test_multiple_servers_each_contributes_ten_percent(self):
        self.shift(self.a,T,T+timedelta(hours=1)); self.shift(self.b,T,T+timedelta(hours=3))
        other=self.employee("S2",self.server_role)
        self.order(1000); self.order(2000,who=other)
        r=self.calculate();self.assertEqual(self.received(r),{self.a.id:75,self.b.id:225})
        self.assertEqual(r.distributed_total_minor,300)

    def test_no_host_no_deduction(self):
        self.order(1000);r=self.calculate()
        self.assertEqual(r.distributed_total_minor,0);self.assertEqual(len(r.no_eligible_recipient_lines),1)
        self.assertTrue(all(l.pool_amount_minor==0 for l in r.lines))

    def test_host_does_not_need_to_be_present_at_order_time(self):
        self.shift(self.a,T,T+timedelta(hours=1));self.order(1000,at=T+timedelta(hours=12))
        self.assertEqual(self.calculate().distributed_total_minor,100)

    def test_overlapping_and_duplicate_shifts_are_merged(self):
        self.shift(self.a,T,T+timedelta(hours=2));self.shift(self.a,T+timedelta(hours=1),T+timedelta(hours=3))
        self.shift(self.a,T,T+timedelta(hours=2));self.shift(self.b,T,T+timedelta(hours=3))
        self.order(1000);self.assertEqual(self.received(self.calculate()),{self.a.id:50,self.b.id:50})

    def test_role_coverage_clips_hours(self):
        assignment=self.s.scalars(select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id==self.a.id)).one()
        assignment.valid_from=T+timedelta(hours=2)
        self.shift(self.a,T,T+timedelta(hours=3));self.shift(self.b,T,T+timedelta(hours=3))
        self.order(1000);self.assertEqual(self.received(self.calculate()),{self.a.id:25,self.b.id:75})

    def test_incomplete_shift_blocks(self):
        self.shift(self.a,T,None);self.order(1000)
        self.assertIn("Incomplete shift",self.calculate().blocked_reason)

    def test_cross_day_and_partial_window_consistency(self):
        self.shift(self.a,T-timedelta(hours=2),T+timedelta(hours=1));self.shift(self.b,T,T+timedelta(hours=3))
        first=self.order(15,at=T+timedelta(hours=2));self.order(15,at=T+timedelta(hours=8))
        full=self.calculate();partial=self.calculate(end=T+timedelta(hours=4))
        self.assertEqual(partial.lines,[l for l in full.lines if l.order_id==first.id])
        self.assertEqual(self.received(full),{self.a.id:1,self.b.id:2})

    def test_dst_business_day_uses_actual_elapsed_hours(self):
        day,start,end=engine._business_day_window(self.loc,datetime(2026,11,1,7,tzinfo=UTC))
        self.assertEqual(str(day),"2026-10-31")
        self.assertEqual((end-start).total_seconds(),25*3600)
        day,start,end=engine._business_day_window(self.loc,datetime(2026,3,8,7,tzinfo=UTC))
        self.assertEqual((end-start).total_seconds(),23*3600)

    def test_invalid_axes_rejected_before_version_change(self):
        with self.assertRaises(ValueError):
            rules.create_new_version(self.s,self.rule.id,recipient_role_id=self.host_role.id,
                source_role_id=self.server_role.id,calculation_base=m.CALC_BASE_VOLUNTARY_TIP,
                rate=Decimal(10),effective_from=T,aggregation_scope=m.AGGREGATION_SCOPE_SOURCE_BUSINESS_DAY)
        self.assertIsNone(self.version.effective_to)

    def test_daily_equal_and_order_hours_are_composable(self):
        self.shift(self.a,T,T+timedelta(hours=1));self.shift(self.b,T,T+timedelta(hours=3))
        self.order(15);self.order(15)
        self.version.distribution_method=m.DISTRIBUTION_METHOD_EQUAL
        self.assertEqual(self.calculate().distributed_total_minor,3)
        self.version.aggregation_scope=m.AGGREGATION_SCOPE_ORDER
        self.version.distribution_method=m.DISTRIBUTION_METHOD_HOURS_PROPORTIONAL
        self.assertEqual(self.calculate().distributed_total_minor,4)

    def test_zero_tips_and_signed_corrections_conserve_cents(self):
        self.shift(self.a,T,T+timedelta(hours=1));self.shift(self.b,T,T+timedelta(hours=3))
        self.order(0);self.assertEqual(self.calculate().distributed_total_minor,0)
        self.order(1000);self.order(-100)
        r=self.calculate();self.assertEqual(r.distributed_total_minor,90)
        self.assertEqual(sum(l.allocated_amount_minor for l in r.lines),90)

    def test_order_at_cutoff_belongs_to_next_day(self):
        self.shift(self.a,T,T+timedelta(hours=1))
        self.order(1000,at=T+timedelta(days=1))
        self.assertEqual(self.calculate().summary.orders_considered,0)
        following=self.calculate(start=T+timedelta(days=1),end=T+timedelta(days=2))
        self.assertEqual(following.summary.orders_considered,1)
        self.assertEqual(following.distributed_total_minor,0)

    def test_other_location_shift_is_excluded(self):
        self.shift(self.a,T,T+timedelta(hours=3),location=999)
        self.order(1000);self.assertEqual(self.calculate().distributed_total_minor,0)

    def test_full_rate_cannot_overcharge_a_small_order(self):
        self.version.rate=Decimal(100)
        self.shift(self.a,T,T+timedelta(hours=1));self.shift(self.b,T,T+timedelta(hours=1))
        first=self.order(1);second=self.order(1)
        r=self.calculate()
        for order in (first,second):
            self.assertEqual(sum(l.allocated_amount_minor for l in r.lines if l.order_id==order.id),1)

    def test_ai_proposes_and_confirms_daily_rule(self):
        raw={"outcome":"PROPOSED","proposal":{"source_semantics":"ROLE","source_role_name":"Server",
            "recipient_role_name":"Host","calculation_base":"VOLUNTARY_TIP","rate":"10",
            "effective_from":"2026-01-01","effective_to":None,"human_readable_summary":"Each server contributes 10% daily to Hosts by hours.",
            "aggregation_scope":"SOURCE_BUSINESS_DAY","eligibility_mode":"WORKED_DURING_BUSINESS_DAY",
            "distribution_method":"HOURS_PROPORTIONAL"}}
        result=authoring.interpret_rule_statement(self.s,restaurant_id=self.restaurant.id,
            statement="From January 1, 2026 take 10% of each server's voluntary tips daily and share among Hosts by hours worked. No Host means no deduction.",
            ai_generate_json_fn=lambda prompt:raw)
        self.assertEqual(result.outcome,"PROPOSED")
        rule=authoring.confirm_rule_proposal(self.s,result.proposal)
        version=rules.list_versions(self.s,rule.id)[0]
        self.assertEqual(version.aggregation_scope,"SOURCE_BUSINESS_DAY")
        self.assertEqual(engine._aware_utc(version.effective_from),datetime(2026,1,1,9,tzinfo=UTC))


if __name__ == "__main__": unittest.main(verbosity=2)
