"""CLOVER_MULTISITE_001 — Tips restaurant selector (Winter Park active, Mount Dora inactive).

Proves that the selected restaurant decides every datum and operation, that no
operation can act on the other restaurant (two tabs, foreign records), that an
inactive restaurant is visible but never calculates or pays, and that Domain
permissions apply to both restaurants alike.

Throwaway SQLite built from the models + Flask test client. Never touches AWS or Clover.

Usage:
    python -m unittest test_multisite_selection_http
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="tips_multisite_http_")
os.close(_FD)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-multisite-test-secret"
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import access_profiles  # noqa: E402,F401  (registers its tables on the shared metadata)
from rfone_data_store.database import create_configured_engine  # noqa: E402

_engine = create_configured_engine(os.environ["RFONE_DATABASE_URL"])
m.Base.metadata.create_all(_engine)
_engine.dispose()

import app as tips_app  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import site_selection  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips import payment_cycle_service as cycle_svc  # noqa: E402
from rfone_data_store.tips import payout_process as payout_svc  # noqa: E402
from rfone_data_store.tips import scheduler  # noqa: E402
from tips_test_session import sign_in, test_account  # noqa: E402


def _site(s, source, name, merchant_id, *, active):
    merchant = m.Merchant(source_system_id=source.id, source_merchant_id=merchant_id, name=name, active=active)
    s.add(merchant)
    s.flush()
    location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=merchant_id,
                          name=name, currency="USD", timezone="America/New_York",
                          operating_day_cutoff_time=time(4, 0), active=active)
    restaurant = m.Restaurant(name=name, default_currency="USD")
    s.add_all([location, restaurant])
    s.flush()
    s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    server = m.RestaurantRole(restaurant_id=restaurant.id, name=f"Server {name[-2:]}", code=f"SRV_{name[-2:]}")
    host = m.RestaurantRole(restaurant_id=restaurant.id, name=f"Host {name[-2:]}", code=f"HST_{name[-2:]}")
    s.add_all([server, host])
    s.flush()
    return restaurant, location, server, host


class TipsMultisiteSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tips_app.SessionFactory() as s:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            s.add(source)
            s.flush()
            cls.wp, _, wp_server, wp_host = _site(s, source, "Rome's Flavours - WP", "WPMERCH", active=True)
            cls.md, _, md_server, md_host = _site(s, source, "Rome's Flavours - MD", "MDMERCH", active=False)
            s.commit()
            cls.wp_id, cls.md_id = cls.wp.id, cls.md.id
            cls.wp_role_id, cls.md_role_id = wp_server.id, md_server.id
            cls.wp_rule_id = cls._rule(s, cls.wp_id, wp_server.id, wp_host.id)
            cls.md_rule_id = cls._rule(s, cls.md_id, md_server.id, md_host.id)
            s.commit()
            no_tips = account_service.create_account(s, username="no-tips", display_name="No Tips",
                                                     password="a-long-enough-test-password")
            s.commit()
            cls.no_tips = (no_tips.id, no_tips.session_version)

    @staticmethod
    def _rule(s, restaurant_id, source_role_id, recipient_role_id):
        rule = m.TipDistributionRule(restaurant_id=restaurant_id, is_active=True)
        s.add(rule)
        s.flush()
        return rule.id

    def client(self, account=None):
        c = tips_app.app.test_client()
        sign_in(c, account or test_account(tips_app))
        return c

    def selected(self, c):
        with c.session_transaction() as sess:
            return sess.get(tips_app.SITE_SESSION_KEY)

    # -- selection decides the page ---------------------------------------
    def test_default_is_wp_and_selector_lists_md_as_inactive(self):
        c = self.client()
        html = c.get("/configuration").get_data(as_text=True)
        self.assertIn('id="site-select"', html)
        self.assertIn(f'<option value="{self.wp_id}" selected', html)
        self.assertIn("Rome&#39;s Flavours - MD — inactive", html)
        self.assertNotIn("Inactive: data can be viewed", html)

    def test_switching_to_md_changes_every_page_and_marks_it_inactive(self):
        c = self.client()
        resp = c.get(f"/configuration?site={self.md_id}")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.selected(c), self.md_id)
        html = c.get("/configuration").get_data(as_text=True)
        self.assertIn(f'<option value="{self.md_id}" selected', html)
        self.assertIn("Inactive: data can be viewed and configured", html)
        self.assertIn("Rome&#39;s Flavours - MD", html.split("</header>")[0])  # header names the site
        for path in ("/", "/calculate-tips", "/tips-runs", "/payment-control", "/host-audit", "/roles"):
            page = c.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertIn(f'<option value="{self.md_id}" selected', page.get_data(as_text=True), path)

    def test_unknown_site_falls_back_to_a_valid_one(self):
        c = self.client()
        c.get("/configuration?site=99999")
        self.assertEqual(self.selected(c), self.wp_id)

    # -- inactive MD never calculates or pays ------------------------------
    def test_inactive_md_refuses_calculations_and_payments(self):
        c = self.client()
        c.get(f"/calculate-tips?site={self.md_id}")
        with tips_app.SessionFactory() as s:
            runs_before = s.scalar(select(func.count()).select_from(m.TipDistributionCalculationRun))
        for path in ("/calculate-tips/run", "/calculate-tips/consolidate", "/tips-configuration/run-calculation-now",
                     "/payment-control/start-cycle", "/payment-control/approve-and-pay"):
            resp = c.post(path, data={"start_at": "2026-06-01", "end_at": "2026-06-02"})
            self.assertEqual(resp.status_code, 302, path)
        with c.session_transaction() as sess:
            messages = [m_ for _, m_ in sess.get("_flashes", [])]
        self.assertTrue(messages and all("not active yet" in msg for msg in messages), messages)
        with tips_app.SessionFactory() as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipDistributionCalculationRun)), runs_before)
            self.assertEqual(s.scalar(select(func.count()).select_from(m.TipPaymentCycle)), 0)

    def test_services_and_scheduler_refuse_the_inactive_site(self):
        with tips_app.SessionFactory() as s:
            run, reason = run_svc.save_calculation_run(s, restaurant_id=self.md_id, first_business_date=date(2026, 6, 1),
                                                       last_business_date=date(2026, 6, 1))
            self.assertIsNone(run)
            self.assertIn("not active", reason)
            self.assertIn("not active", payout_svc.run_calculation_now(s, restaurant_id=self.md_id).blocked_reason)
            with self.assertRaises(site_selection.SiteNotOperationalError):
                cycle_svc.start_payment_cycle(s, restaurant_id=self.md_id)
            self.assertEqual(scheduler._all_restaurant_ids(s), [self.wp_id])
            self.assertTrue(site_selection.restaurant_is_operational(s, self.wp_id))

    # -- no operation can act on the other restaurant ----------------------
    def test_form_from_another_tab_is_refused(self):
        c = self.client()
        c.get(f"/configuration?site={self.wp_id}")
        with tips_app.SessionFactory() as s:
            before = s.get(m.TipDistributionRule, self.wp_rule_id).is_active
        resp = c.post(f"/distribution-rules/{self.wp_rule_id}/toggle-active",
                      data={tips_app.SITE_FORM_FIELD: str(self.md_id)})  # page was shown for MD
        self.assertEqual(resp.status_code, 302)
        with tips_app.SessionFactory() as s:
            self.assertEqual(s.get(m.TipDistributionRule, self.wp_rule_id).is_active, before)

    def test_operation_on_a_record_of_the_other_site_is_refused(self):
        c = self.client()
        c.get(f"/configuration?site={self.wp_id}")
        with tips_app.SessionFactory() as s:
            before = s.get(m.TipDistributionRule, self.md_rule_id).is_active
        c.post(f"/distribution-rules/{self.md_rule_id}/toggle-active", data={})
        c.post(f"/roles/{self.md_role_id}/edit", data={"name": "Changed", "code": "X", "active": "on"})
        with tips_app.SessionFactory() as s:
            self.assertEqual(s.get(m.TipDistributionRule, self.md_rule_id).is_active, before)
            self.assertNotEqual(s.get(m.RestaurantRole, self.md_role_id).name, "Changed")

    def test_link_to_a_record_of_the_other_site_opens_it_on_its_site(self):
        c = self.client()
        c.get(f"/configuration?site={self.wp_id}")
        page = c.get(f"/distribution-rules/{self.md_rule_id}")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.selected(c), self.md_id)
        self.assertIn(f'<option value="{self.md_id}" selected', page.get_data(as_text=True))

    def test_wp_operation_still_works_when_wp_is_selected(self):
        c = self.client()
        c.get(f"/configuration?site={self.wp_id}")
        with tips_app.SessionFactory() as s:
            before = s.get(m.TipDistributionRule, self.wp_rule_id).is_active
        c.post(f"/distribution-rules/{self.wp_rule_id}/toggle-active", data={tips_app.SITE_FORM_FIELD: str(self.wp_id)})
        with tips_app.SessionFactory() as s:
            self.assertEqual(s.get(m.TipDistributionRule, self.wp_rule_id).is_active, not before)
            rule = s.get(m.TipDistributionRule, self.wp_rule_id)
            rule.is_active = before
            s.commit()

    # -- permissions --------------------------------------------------------
    def test_domain_permission_applies_to_both_sites(self):
        c = self.client(self.no_tips)
        self.assertEqual(c.get(f"/configuration?site={self.wp_id}").status_code, 403)
        self.assertEqual(c.get(f"/configuration?site={self.md_id}").status_code, 403)
        self.assertEqual(c.post("/calculate-tips/run", data={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
