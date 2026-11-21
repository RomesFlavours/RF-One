"""CLOVER_MULTISITE_001 — Clover Acquisition restaurant selector (WP active, MD inactive).

Proves the selected restaurant decides status, history and jobs; a job always
targets the restaurant of the page that was submitted (never another tab's
choice); an inactive restaurant is visible but starts no acquisition; the
Clover Acquisition permission applies to both restaurants alike; the page has
its contextual help explaining the selection.

Throwaway SQLite built from the models; a recording launcher stands in for
Fargate. Never touches AWS or Clover.

Usage:
    python -m unittest test_clover_acquisition_multisite_http
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, time, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_clover_multisite_")
os.close(_FD)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "clover-multisite-test-secret"
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
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402

HOST = "https://rfone-web.example"
UTC = timezone.utc


class RecordingLauncher:
    def __init__(self):
        self.run_ids = []

    def __call__(self, run_id):
        self.run_ids.append(run_id)


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
    # A finished acquisition, so each site has its own history and a Sync Now starting point.
    s.add(m.IngestionRun(source_system_id=source.id, location_id=location.id, status="COMPLETE",
                         acquisition_mode="BACKFILL", started_at=datetime(2026, 6, 1, tzinfo=UTC),
                         finished_at=datetime(2026, 6, 1, 1, tzinfo=UTC),
                         source_window_start=datetime(2026, 5, 1, tzinfo=UTC),
                         source_window_end=datetime(2026, 6, 1, tzinfo=UTC), notes=f"history of {name}"))
    s.flush()
    return restaurant, location


class CloverAcquisitionMultisiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as s:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            s.add(source)
            s.flush()
            wp, wp_loc = _site(s, source, "Rome's Flavours - WP", "WPMERCH", active=True)
            md, md_loc = _site(s, source, "Rome's Flavours - MD", "MDMERCH", active=False)
            operator = account_service.create_account(s, username="clover-op", display_name="Clover Operator",
                                                      password="a-long-enough-test-password")
            bank_only = account_service.create_account(s, username="bank-only", display_name="Bank Only",
                                                       password="a-long-enough-test-password")
            s.flush()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="CLOVER_ACQUISITION",
                                              enabled=True, role_code=None)
            account_service.set_domain_access(s, account_id=bank_only.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            s.commit()
            cls.wp_id, cls.md_id, cls.wp_loc, cls.md_loc = wp.id, md.id, wp_loc.id, md_loc.id
            cls.operator = (operator.id, operator.session_version)
            cls.bank_only = (bank_only.id, bank_only.session_version)
        cls.launcher = RecordingLauncher()
        web_app.clover_job_launcher = cls.launcher

    def client(self, account=None):
        c = web_app.app.test_client()
        with c.session_transaction(base_url=HOST) as sess:
            account = account or self.operator
            sess[shared_session.SESSION_ACCOUNT_KEY] = account[0]
            sess[shared_session.SESSION_VERSION_KEY] = account[1]
            self.token = shared_session.csrf_token(sess)
        return c

    def runs(self, location_id):
        with SessionFactory() as s:
            return s.scalar(select(func.count()).select_from(m.IngestionRun).where(
                m.IngestionRun.location_id == location_id))

    def test_default_page_is_wp_with_selector_help_and_its_own_history(self):
        html = self.client().get("/clover-acquisition", base_url=HOST).get_data(as_text=True)
        self.assertIn('id="site-select"', html)
        self.assertIn(f'<option value="{self.wp_id}" selected', html)
        self.assertIn("Rome&#39;s Flavours - MD — inactive", html)
        self.assertIn('data-how-works="clover_acquisition"', html)
        self.assertIn("Choosing the restaurant", html)
        self.assertNotIn("disabled>Run Historical Backfill", html)

    def test_md_selected_is_shown_inactive_with_disabled_buttons(self):
        html = self.client().get(f"/clover-acquisition?restaurant_id={self.md_id}", base_url=HOST).get_data(as_text=True)
        self.assertIn(f'<option value="{self.md_id}" selected', html)
        self.assertIn("Inactive: no acquisition can be started", html)
        self.assertIn(f'name="restaurant_id" value="{self.md_id}"', html)
        self.assertIn("disabled>Sync Now", html.replace(" >", ">"))
        self.assertIn("disabled>Run Historical Backfill", html.replace(" >", ">"))

    def test_inactive_md_refuses_jobs_even_if_posted(self):
        c = self.client()
        before = self.runs(self.md_loc)
        c.post("/clover-acquisition/sync-now", base_url=HOST,
               data={"csrf_token": self.token, "restaurant_id": self.md_id})
        c.post("/clover-acquisition/backfill", base_url=HOST,
               data={"csrf_token": self.token, "restaurant_id": self.md_id,
                     "from_date": "2026-06-01", "through_date": "2026-06-02"})
        self.assertEqual(self.runs(self.md_loc), before)
        self.assertEqual(self.launcher.run_ids, [])

    def test_job_targets_the_submitted_page_site_not_another_tab(self):
        c = self.client()
        c.get(f"/clover-acquisition?restaurant_id={self.md_id}", base_url=HOST)  # another tab selected MD
        wp_before, md_before = self.runs(self.wp_loc), self.runs(self.md_loc)
        c.post("/clover-acquisition/backfill", base_url=HOST,
               data={"csrf_token": self.token, "restaurant_id": self.wp_id,
                     "from_date": "2026-06-01", "through_date": "2026-06-02"})  # submitted from the WP page
        self.assertEqual(self.runs(self.wp_loc), wp_before + 1)
        self.assertEqual(self.runs(self.md_loc), md_before)
        with SessionFactory() as s:
            run = s.get(m.IngestionRun, self.launcher.run_ids[-1])
            self.assertEqual(run.location_id, self.wp_loc)
            run.status, run.lock_key = "COMPLETE", None  # release for the other tests
            s.commit()

    def test_status_is_per_site(self):
        c = self.client()
        wp = c.get(f"/clover-acquisition/status.json?restaurant_id={self.wp_id}", base_url=HOST).get_json()
        md = c.get(f"/clover-acquisition/status.json?restaurant_id={self.md_id}", base_url=HOST).get_json()
        self.assertEqual(md["active_run_id"], None)
        self.assertIn("active_run_id", wp)

    def test_permission_applies_to_both_sites(self):
        c = self.client(self.bank_only)
        self.assertEqual(c.get(f"/clover-acquisition?restaurant_id={self.wp_id}", base_url=HOST).status_code, 403)
        self.assertEqual(c.get(f"/clover-acquisition?restaurant_id={self.md_id}", base_url=HOST).status_code, 403)
        before = self.runs(self.wp_loc)
        c.post("/clover-acquisition/sync-now", base_url=HOST, data={"csrf_token": self.token, "restaurant_id": self.wp_id})
        self.assertEqual(self.runs(self.wp_loc), before)


if __name__ == "__main__":
    unittest.main()
