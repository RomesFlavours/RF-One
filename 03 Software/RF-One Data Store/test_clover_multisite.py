"""CLOVER_MULTISITE_001 — two Clover sites (Winter Park + Mount Dora) in one
RF-One database, including one person present on both Clover merchants.

Disposable in-memory SQLite and fake Clover clients only: never contacts
Clover and never touches a real database.

Usage:
    python -m unittest test_clover_multisite
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import select

from rfone_data_store import employee_directory as directory
from rfone_data_store import models as m
from rfone_data_store.clover_acquisition_validation import FakeCloverClient
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.payroll_calculation import worked_time
from rfone_data_store.shift_location import pending_shift_count, resolve_shift_locations, shift_counts_at
from rfone_data_store.technical.connectors.clover import acquisition, acquisition_jobs, correction_sync, live_sync
from rfone_data_store.tips import distribution_engine

# Each image ships the shift-location resolver; its consumers ship where they run: the Tips engine in
# rfone-tips, Compensation worked time in rfone-tips/rfone-web, neither in the Clover worker image.
TIPS_CONSUMER_HERE = hasattr(distribution_engine, "shift_counts_at")
COMPENSATION_CONSUMER_HERE = hasattr(worked_time, "shift_at_locations")

UTC = timezone.utc
WP_MERCHANT, MD_MERCHANT = "WPMERCHANT01", "MDMERCHANT01"
PERIOD_START = datetime(2026, 6, 1, tzinfo=UTC)
PERIOD_END = datetime(2026, 6, 8, tzinfo=UTC)
T0 = PERIOD_START + timedelta(days=1, hours=18)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _ref(source_id: str) -> dict:
    return {"id": source_id}


def _client(merchant_id: str, *, employees, order_id, payment_id, shift_id, employee_id, tip) -> FakeCloverClient:
    client = FakeCloverClient(merchant_id=merchant_id)
    client.employees = employees
    client.tenders = [{"id": f"TND-{merchant_id}", "label": "Credit Card", "labelKey": "com.clover.tender.credit_card",
                       "enabled": True}]
    client.orders_by_id[order_id] = {
        "id": order_id, "employee": _ref(employee_id), "createdTime": _ms(T0), "modifiedTime": _ms(T0),
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 5000, "lineItems": {"elements": []},
    }
    client.payments.append({
        "id": payment_id, "order": _ref(order_id), "employee": _ref(employee_id),
        "tender": {"id": f"TND-{merchant_id}", "label": "Credit Card"}, "amount": 5000, "taxAmount": 0,
        "tipAmount": tip, "createdTime": _ms(T0), "modifiedTime": _ms(T0), "result": "SUCCESS",
    })
    client.shifts = [{"id": shift_id, "employee": _ref(employee_id),
                      "inTime": _ms(T0 - timedelta(hours=2)), "outTime": _ms(T0 + timedelta(hours=4))}]
    return client


class TwoCloverSitesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        self.source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        self.db.add(self.source)
        self.db.flush()
        self.wp, self.wp_merchant, self.wp_restaurant = self._site("Rome's Flavours - WP", WP_MERCHANT, active=True)
        self.md, self.md_merchant, self.md_restaurant = self._site("Rome's Flavours - MD", MD_MERCHANT, active=False)

        # Clover rosters: Anna works at both sites, with a different Clover id at each merchant.
        self.wp_roster = [{"id": "W-ANNA", "name": "Anna Rossi"}, {"id": "W-LUCA", "name": "Luca Bianchi"}]
        self.md_roster = [{"id": "M-ANNA", "name": "Anna Rossi"}, {"id": "M-SARA", "name": "Sara Verdi"}]
        _, pending = directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id=WP_MERCHANT,
                                               records=self.wp_roster)
        for link_id in pending:
            directory.attach_link(self.db, link_id=link_id, create_new=True)
        self.anna = self._person_for("W-ANNA")
        self.luca = self._person_for("W-LUCA")
        _, pending = directory.import_snapshot(self.db, location_id=self.md.id, merchant_id=MD_MERCHANT,
                                               records=self.md_roster)
        for link_id in pending:
            link = self.db.get(m.EmployeeCloverLink, link_id)
            if link.external_employee_id == "M-ANNA":
                directory.attach_link(self.db, link_id=link_id, employee_id=self.anna.id)  # same person
            else:
                directory.attach_link(self.db, link_id=link_id, create_new=True)
        self.sara = self._person_for("M-SARA")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # -- fixture helpers ---------------------------------------------------
    def _site(self, name, merchant_id, *, active):
        merchant = m.Merchant(source_system_id=self.source.id, source_merchant_id=merchant_id, name=name, active=active)
        self.db.add(merchant)
        self.db.flush()
        location = m.Location(merchant_id=merchant.id, source_system_id=self.source.id, source_location_id=merchant_id,
                              name=name, currency="USD", timezone="America/New_York",
                              operating_day_cutoff_time=time(4, 0), active=active)
        restaurant = m.Restaurant(name=name, default_currency="USD")
        self.db.add_all([location, restaurant])
        self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        self.db.flush()
        return location, merchant, restaurant

    def _person_for(self, external_id):
        return self.db.get(m.Employee, self.db.scalar(select(m.EmployeeCloverLink.employee_id).where(
            m.EmployeeCloverLink.external_employee_id == external_id)))

    def _activate_md(self):
        self.md.active = True
        self.md_merchant.active = True
        self.db.commit()

    def _wp_client(self):
        return _client(WP_MERCHANT, employees=self.wp_roster, order_id="WP-ORDER", payment_id="WP-PAY",
                       shift_id="WP-SHIFT", employee_id="W-ANNA", tip=700)

    def _md_client(self):
        return _client(MD_MERCHANT, employees=self.md_roster, order_id="MD-ORDER", payment_id="MD-PAY",
                       shift_id="MD-SHIFT", employee_id="M-ANNA", tip=900)

    def _import(self, location, client):
        summary = acquisition.import_clover_period(self.db, location_id=location.id, period_start=PERIOD_START,
                                                   period_end=PERIOD_END, client=client)
        self.db.commit()
        return summary

    # -- 1. credentials: each merchant its own token, never another's ------
    def test_each_merchant_uses_its_own_token_and_never_another(self):
        class DefaultWp:
            merchant_id = WP_MERCHANT
        env = {"CLOVER_API_TOKEN__MDMERCHANT01": "md-token"}
        with patch.dict(os.environ, env, clear=False), \
                patch.object(acquisition, "get_default_client", return_value=DefaultWp()):
            md = acquisition.get_location_client(MD_MERCHANT)
            self.assertEqual(md.merchant_id, MD_MERCHANT)
            self.assertEqual(md._config.api_token, "md-token")
            self.assertIsInstance(acquisition.get_location_client(WP_MERCHANT), DefaultWp)  # WP path unchanged
            with self.assertRaises(acquisition.CloverConnectionNotConfiguredError):
                acquisition.get_location_client("OTHERMERCH")  # no fallback to WP's token
        legacy = {"CLOVER_MD_MERCHANT_ID": MD_MERCHANT, "CLOVER_MD_API_TOKEN": "legacy-md"}
        with patch.dict(os.environ, legacy, clear=False), \
                patch.object(acquisition, "get_default_client", return_value=DefaultWp()):
            os.environ.pop("CLOVER_API_TOKEN__MDMERCHANT01", None)
            self.assertEqual(acquisition.get_location_client(MD_MERCHANT)._config.api_token, "legacy-md")
        self.assertEqual(acquisition.merchant_token_env_name("wp3nhx517c0m1"), "CLOVER_API_TOKEN__WP3NHX517C0M1")

    # -- 2. MD stays inactive: nothing acquired ------------------------------
    def test_inactive_site_is_never_acquired(self):
        client = self._md_client()
        summary = self._import(self.md, client)
        self.assertTrue(any("not active" in e for e in summary.errors))
        self.assertEqual(client.calls, [], "an inactive site must not even be contacted")
        self.assertEqual(self.db.scalar(select(m.Order).where(m.Order.location_id == self.md.id)), None)
        self.assertEqual(acquisition.active_clover_location_ids(self.db), [self.wp.id])
        with self.assertRaises(acquisition_jobs.LocationNotActiveError):
            acquisition_jobs.request_sync_now(self.db, location_id=self.md.id, launcher=lambda run_id: None)
        with self.assertRaises(acquisition_jobs.LocationNotActiveError):
            acquisition_jobs.request_historical_backfill(self.db, location_id=self.md.id, period_start=PERIOD_START,
                                                         period_end=PERIOD_END, launcher=lambda run_id: None)
        self.assertIsNone(correction_sync.run_correction_cycle(self.db, location_id=self.md.id, client=client))
        self.assertIsNone(live_sync.run_live_sync_cycle(self.db, location_id=self.md.id, client=client))
        self.assertEqual(client.calls, [])
        self.assertIsNone(self.db.scalar(select(m.IngestionRun).where(m.IngestionRun.location_id == self.md.id,
                                                                      m.IngestionRun.lock_key.is_not(None))))

    # -- 3. orders, employees and shifts stay at their own site ---------------
    def test_both_sites_acquire_into_their_own_location_with_a_shared_person(self):
        self.assertEqual(self._import(self.wp, self._wp_client()).errors, [])
        self._activate_md()
        self.assertEqual(self._import(self.md, self._md_client()).errors, [])
        self.db.expire_all()

        orders = {o.source_order_id: o for o in self.db.scalars(select(m.Order))}
        self.assertEqual(orders["WP-ORDER"].location_id, self.wp.id)
        self.assertEqual(orders["MD-ORDER"].location_id, self.md.id)
        self.assertEqual(orders["WP-ORDER"].employee_id, self.anna.id)
        self.assertEqual(orders["MD-ORDER"].employee_id, self.anna.id)  # same person, other merchant id
        shifts = {s.source_shift_id: s for s in self.db.scalars(select(m.Shift))}
        self.assertEqual((shifts["WP-SHIFT"].location_id, shifts["WP-SHIFT"].employee_id), (self.wp.id, self.anna.id))
        self.assertEqual((shifts["MD-SHIFT"].location_id, shifts["MD-SHIFT"].employee_id), (self.md.id, self.anna.id))
        links = {l.external_employee_id: l for l in self.db.scalars(select(m.EmployeeCloverLink))}
        self.assertEqual({k: (l.location_id, l.employee_id) for k, l in links.items()}, {
            "W-ANNA": (self.wp.id, self.anna.id), "W-LUCA": (self.wp.id, self.luca.id),
            "M-ANNA": (self.md.id, self.anna.id), "M-SARA": (self.md.id, self.sara.id)})
        # Each site's Tips and Compensation read only that site's shifts.
        window = (PERIOD_START, PERIOD_END)
        wp_shifts = {s.source_shift_id for s in worked_time.load_location_shifts(
            self.db, location_id=self.wp.id, window_start=window[0], window_end=window[1])}
        md_shifts = {s.source_shift_id for s in worked_time.load_location_shifts(
            self.db, location_id=self.md.id, window_start=window[0], window_end=window[1])}
        self.assertEqual((wp_shifts, md_shifts), ({"WP-SHIFT"}, {"MD-SHIFT"}))
        self.assertEqual(distribution_engine._employees_shift_active_at(self.db, location_id=self.md.id, at=T0),
                         {self.anna.id})

    # -- 4. a site's roster update never changes the other site's states -----
    def test_wp_roster_update_does_not_change_md_states_and_vice_versa(self):
        md_before = {l.id: l.state for l in self.db.scalars(
            select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == MD_MERCHANT))}
        directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id=WP_MERCHANT,
                                  records=[{"id": "W-LUCA", "name": "Luca Bianchi"}])  # Anna left WP's roster
        self.db.commit()
        states = {l.external_employee_id: l.state for l in self.db.scalars(select(m.EmployeeCloverLink))}
        self.assertEqual(states["W-ANNA"], "MISSING_REVIEW")
        self.assertEqual(states["M-ANNA"], "PRESENT", "Anna is still on Mount Dora's roster")
        self.assertEqual({l.id: l.state for l in self.db.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.merchant_id == MD_MERCHANT))}, md_before)
        directory.import_snapshot(self.db, location_id=self.md.id, merchant_id=MD_MERCHANT, records=[])
        self.db.commit()
        self.assertEqual(self.db.scalar(select(m.EmployeeCloverLink.state).where(
            m.EmployeeCloverLink.external_employee_id == "W-LUCA")), "PRESENT")
        self.assertTrue(all(p.active is not False for p in (self.anna, self.luca, self.sara)))  # never deactivated

    def test_cross_site_change_inside_an_import_is_refused(self):
        before = directory._other_site_states(self.db, WP_MERCHANT, self.wp.id)
        md_link = self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == MD_MERCHANT))
        md_link.state = "MISSING_REVIEW"
        with self.assertRaises(ValueError):
            directory._refuse_other_site_changes(self.db, WP_MERCHANT, self.wp.id, before)
        self.db.rollback()
        with self.assertRaises(ValueError):
            directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id=MD_MERCHANT,
                                      records=self.md_roster)  # roster of one merchant onto the other site

    # -- 5. shifts without a Location: reconstructed from Clover, or pending -------
    def _old_shift(self, source_id, employee, *, mirrored_at=None):
        shift = m.Shift(source_system_id=self.source.id, source_shift_id=source_id, employee_id=employee.id,
                        clock_in=T0 - timedelta(hours=1), clock_out=T0 + timedelta(hours=1), location_id=None)
        self.db.add(shift)
        for location in mirrored_at or ():
            run = m.IngestionRun(source_system_id=self.source.id, location_id=location.id if location else None,
                                 status="COMPLETE", started_at=T0)
            self.db.add(run)
            self.db.flush()
            self.db.add(m.SourceRecord(ingestion_run_id=run.id, source_system_id=self.source.id,
                                       entity_type="shift", source_id=source_id, retrieved_at=T0))
        self.db.flush()
        return shift

    def test_shift_without_location_is_reconstructed_from_clover_or_left_pending(self):
        self.luca.location_id = self.wp.id     # home Locations must play NO part any more
        self.sara.location_id = self.md.id
        proven_wp = self._old_shift("OLD-WP", self.luca, mirrored_at=[self.wp, self.wp])
        proven_md = self._old_shift("OLD-MD", self.luca, mirrored_at=[self.md])   # WP-home person, MD record
        conflicting = self._old_shift("OLD-BOTH", self.sara, mirrored_at=[self.wp, self.md])
        no_location_run = self._old_shift("OLD-NORUNLOC", self.sara, mirrored_at=[None])
        orphan = self._old_shift("OLD-ORPHAN", self.sara)                          # no Clover record at all
        self.db.commit()

        resolved = resolve_shift_locations(self.db, [proven_wp, proven_md, conflicting, no_location_run, orphan])
        self.assertEqual(resolved, {proven_wp.id: self.wp.id, proven_md.id: self.md.id, conflicting.id: None,
                                    no_location_run.id: None, orphan.id: None})
        self.assertFalse(shift_counts_at(orphan, self.md.id, resolved))
        # Tips presence and Compensation hours read the same certain Location.
        if TIPS_CONSUMER_HERE:
            self.assertEqual(distribution_engine._employees_shift_active_at(self.db, location_id=self.wp.id, at=T0),
                             {self.luca.id})
            self.assertEqual(distribution_engine._employees_shift_active_at(self.db, location_id=self.md.id, at=T0),
                             {self.luca.id}, "Luca's MD record wins over his WP home; Sara's uncertain shifts count nowhere")
            eligibility = distribution_engine._PeriodEligibility([], [proven_wp, orphan],
                                                                 shift_locations=resolved)
            self.assertEqual(eligibility.on_shift({self.luca.id, self.sara.id}, self.wp.id, T0), {self.luca.id})
        if COMPENSATION_CONSUMER_HERE:
            md_loaded = worked_time.load_location_shifts(self.db, location_id=self.md.id,
                                                         window_start=PERIOD_START, window_end=PERIOD_END)
            self.assertEqual({s.source_shift_id for s in md_loaded}, {"OLD-MD"})
        # The anomalies are counted for reporting; no Shift was modified.
        self.assertEqual(pending_shift_count(self.db, start=PERIOD_START, end=PERIOD_END), 3)
        self.assertEqual(self.db.scalar(select(m.Shift.location_id).where(m.Shift.source_shift_id == "OLD-WP")), None)

    # -- 6. Registry: MD roster prepared while the site is inactive -----------
    def test_md_roster_refresh_allowed_while_inactive_without_touching_wp_or_sales(self):
        wp_links_before = {l.id: (l.state, l.last_seen_at) for l in self.db.scalars(
            select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == WP_MERCHANT))}
        client = self._md_client()
        client.employees = self.md_roster + [{"id": "M-NEW", "name": "Nuovo Cuoco"}]
        problems = correction_sync.refresh_roster_site(self.db, restaurant_id=self.md_restaurant.id, client=client)
        self.assertEqual(problems, [])
        self.db.expire_all()
        new = self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.external_employee_id == "M-NEW"))
        self.assertEqual((new.location_id, new.employee_id, new.state), (self.md.id, None, "PRESENT"))  # pending identity
        self.assertEqual({l.id: (l.state, l.last_seen_at) for l in self.db.scalars(
            select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == WP_MERCHANT))}, wp_links_before)
        self.assertEqual([path for path, _ in client.calls], [f"/v3/merchants/{MD_MERCHANT}/employees"],
                         "roster only: no orders, payments, shifts or refunds are read")
        self.assertEqual(self.db.scalar(select(m.Order.id).where(m.Order.location_id == self.md.id)), None)
        self.assertFalse(self.md.active)


if __name__ == "__main__":
    unittest.main()
