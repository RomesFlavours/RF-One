"""CLOVER_MULTISITE_001 — RF-One Web Tips period validation respects the selected
restaurant and the account's authorization, server-side.

Throwaway SQLite built from the models. Never touches AWS.

Usage:
    python -m unittest test_tips_validation_multisite_http
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timezone
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_tips_validation_multisite_")
os.close(_FD)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "tips-validation-multisite-secret"
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import access_profiles  # noqa: E402,F401  (registers its tables on the shared metadata)
from rfone_data_store.database import create_configured_engine  # noqa: E402

_engine = create_configured_engine(os.environ["RFONE_DATABASE_URL"])
m.Base.metadata.create_all(_engine)
_engine.dispose()

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store import site_selection  # noqa: E402

HOST = "https://rfone-web.example"
UTC = timezone.utc


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
    run = m.TipDistributionCalculationRun(
        restaurant_id=restaurant.id, period_start=datetime(2026, 6, 1, 8, tzinfo=UTC),
        period_end=datetime(2026, 6, 2, 8, tzinfo=UTC), status="COMPLETE", state=m.TIPS_RUN_STATE_CALCULATED,
        first_business_date=date(2026, 6, 1), last_business_date=date(2026, 6, 1),
        timezone_name="America/New_York", operating_day_cutoff_time=time(4, 0), control_difference_minor=0,
        notes=f"run of {name}")
    s.add(run)
    s.flush()
    return restaurant, run


class TipsValidationMultisiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as s:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            s.add(source)
            s.flush()
            wp, wp_run = _site(s, source, "Rome's Flavours - WP", "WPMERCH", active=True)
            md, md_run = _site(s, source, "Rome's Flavours - MD", "MDMERCH", active=False)
            tips = account_service.create_account(s, username="tips-user", display_name="Tips User",
                                                  password="a-long-enough-test-password")
            bank = account_service.create_account(s, username="bank-user", display_name="Bank User",
                                                  password="a-long-enough-test-password")
            s.flush()
            account_service.set_domain_access(s, account_id=tips.id, domain_code="TIPS", enabled=True, role_code=None)
            account_service.set_domain_access(s, account_id=bank.id, domain_code="BANK", enabled=True, role_code=None)
            s.commit()
            cls.wp_id, cls.md_id, cls.wp_run, cls.md_run = wp.id, md.id, wp_run.id, md_run.id
            cls.tips = (tips.id, tips.session_version)
            cls.bank = (bank.id, bank.session_version)

    def client(self, account=None):
        c = web_app.app.test_client()
        with c.session_transaction(base_url=HOST) as sess:
            account = account or self.tips
            sess[shared_session.SESSION_ACCOUNT_KEY] = account[0]
            sess[shared_session.SESSION_VERSION_KEY] = account[1]
            self.token = shared_session.csrf_token(sess)
        return c

    def state(self, run_id):
        with SessionFactory() as s:
            return s.get(m.TipDistributionCalculationRun, run_id).state

    def test_list_shows_only_the_selected_restaurant(self):
        c = self.client()
        wp = c.get("/tips/runs", base_url=HOST).get_data(as_text=True)
        self.assertIn('id="site-select"', wp)
        self.assertIn(f'href="/tips/runs/{self.wp_run}"', wp)
        self.assertNotIn(f'href="/tips/runs/{self.md_run}"', wp)
        md = c.get(f"/tips/runs?restaurant_id={self.md_id}", base_url=HOST).get_data(as_text=True)
        self.assertIn(f'href="/tips/runs/{self.md_run}"', md)
        self.assertNotIn(f'href="/tips/runs/{self.wp_run}"', md)
        self.assertIn("Inactive: periods cannot be validated.", md)
        self.assertIn('data-how-works="tips_validation_runs"', md)

    def test_opening_a_run_remembers_its_restaurant(self):
        c = self.client()
        c.get(f"/tips/runs?restaurant_id={self.wp_id}", base_url=HOST)
        self.assertEqual(c.get(f"/tips/runs/{self.md_run}", base_url=HOST).status_code, 200)
        listing = c.get("/tips/runs", base_url=HOST).get_data(as_text=True)
        self.assertIn(f'href="/tips/runs/{self.md_run}"', listing)

    def test_inactive_restaurant_period_is_never_validated(self):
        c = self.client()
        c.post(f"/tips/runs/{self.md_run}/validate", base_url=HOST, data={"csrf_token": self.token})
        self.assertEqual(self.state(self.md_run), m.TIPS_RUN_STATE_CALCULATED)

    def test_account_without_the_restaurant_is_refused_server_side(self):
        # The central extension point decides; simulate an account allowed only Winter Park.
        only_wp = lambda db, account, domain: [s for s in site_selection.list_sites(db) if s.restaurant_id == self.wp_id]
        with patch.object(site_selection, "sites_for_account", only_wp):
            c = self.client()
            listing = c.get(f"/tips/runs?restaurant_id={self.md_id}", base_url=HOST).get_data(as_text=True)
            self.assertNotIn(f'value="{self.md_id}"', listing)
            self.assertNotIn(f'href="/tips/runs/{self.md_run}"', listing)
            self.assertEqual(c.get(f"/tips/runs/{self.md_run}", base_url=HOST).status_code, 403)
            resp = c.post(f"/tips/runs/{self.md_run}/validate", base_url=HOST, data={"csrf_token": self.token})
            self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.state(self.md_run), m.TIPS_RUN_STATE_CALCULATED)

    def test_without_tips_access_nothing_opens(self):
        c = self.client(self.bank)
        self.assertEqual(c.get("/tips/runs", base_url=HOST).status_code, 403)
        self.assertEqual(c.get(f"/tips/runs/{self.wp_run}", base_url=HOST).status_code, 403)
        self.assertEqual(c.post(f"/tips/runs/{self.wp_run}/validate", base_url=HOST,
                                data={"csrf_token": self.token}).status_code, 403)
        self.assertEqual(self.state(self.wp_run), m.TIPS_RUN_STATE_CALCULATED)


if __name__ == "__main__":
    unittest.main()
