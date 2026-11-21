"""CLOVER_MULTISITE_001 — the account Access page sets the company/restaurant
reach of site-scoped Domains (Tips, Clover Acquisition) and the specific
payment authorizations per restaurant (Product Owner 2026-11-21).

Throwaway SQLite built from the models. Never touches AWS.

Usage:
    python -m unittest test_account_access_multisite_http
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_FD, _DB = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_access_multisite_")
os.close(_FD)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "access-multisite-secret"
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import access_profiles as profiles  # noqa: E402
from rfone_data_store.database import create_configured_engine  # noqa: E402

_engine = create_configured_engine(os.environ["RFONE_DATABASE_URL"])
m.Base.metadata.create_all(_engine)
_engine.dispose()

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import financial_authorization as fin  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store import site_selection  # noqa: E402

HOST = "https://rfone-web.example"
PASSWORD = "a-long-enough-test-password"


def _site(s, source, name, merchant_id, legal_entity):
    merchant = m.Merchant(source_system_id=source.id, source_merchant_id=merchant_id, name=name, active=True)
    s.add(merchant)
    s.flush()
    location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=merchant_id,
                          name=name, currency="USD", timezone="America/New_York",
                          operating_day_cutoff_time=time(4, 0), active=True)
    restaurant = m.Restaurant(name=name, default_currency="USD", legal_entity_id=legal_entity.id)
    s.add_all([location, restaurant])
    s.flush()
    s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    return restaurant


class AccountAccessMultisiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as s:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            le_wp = m.LegalEntity(legal_name="RF-Winter Park", status="ACTIVE")
            le_md = m.LegalEntity(legal_name="RF-Mount Dora", status="ACTIVE")
            s.add_all([source, le_wp, le_md])
            s.flush()
            wp = _site(s, source, "Rome's Flavours - WP", "WPMERCH", le_wp)
            md = _site(s, source, "Rome's Flavours - MD", "MDMERCH", le_md)
            profiles.seed_companies(s)
            admin = account_service.create_account(s, username="access-admin", display_name="Access Admin",
                                                   password=PASSWORD)
            admin.is_admin = True
            s.commit()
            companies = {c.name: c.id for c in s.scalars(select(profiles.CompanyContext))}
            cls.wp_id, cls.md_id, cls.companies = wp.id, md.id, companies
            cls.admin = (admin.id, admin.session_version)

    def setUp(self):
        with SessionFactory() as s:
            target = account_service.create_account(s, username=f"target-{self._testMethodName}"[:60],
                                                    display_name="Target", password=PASSWORD)
            s.commit()
            self.target_id = target.id

    def client(self):
        c = web_app.app.test_client()
        with c.session_transaction(base_url=HOST) as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY] = self.admin[0]
            sess[shared_session.SESSION_VERSION_KEY] = self.admin[1]
            self.token = shared_session.csrf_token(sess)
        return c

    def post(self, c, **fields):
        data = {"csrf_token": self.token, "access_TIPS": "all", "payment_permissions_form": "1"}
        data.update(fields)
        return c.post(f"/admin/accounts/{self.target_id}/access", base_url=HOST, data=data)

    def reach(self):
        with SessionFactory() as s:
            return site_selection.account_restaurant_ids(s, s.get(m.RFOneAccount, self.target_id), "TIPS")

    def test_page_offers_restaurants_payments_and_help(self):
        html = self.client().get(f"/admin/accounts/{self.target_id}/access", base_url=HOST).get_data(as_text=True)
        self.assertIn('name="company_scope_TIPS"', html)
        self.assertIn('name="company_scope_CLOVER_ACQUISITION"', html)
        self.assertNotIn('name="company_scope_BANK"', html)
        self.assertIn("RFGroup (all companies)", html)
        self.assertIn('name="pay_TIPS_APPROVE_AND_PAY"', html)
        self.assertIn('data-how-works="admin_account_access"', html)

    def test_default_keeps_every_restaurant(self):
        self.assertIn(self.post(self.client()).status_code, (302, 303))
        self.assertEqual(self.reach(), {self.wp_id, self.md_id})

    def test_selected_company_is_saved_and_enforced(self):
        c = self.client()
        self.post(c, company_scope_TIPS="selected", companies_TIPS=str(self.companies["WP"]))
        self.assertEqual(self.reach(), {self.wp_id})
        html = c.get(f"/admin/accounts/{self.target_id}/access", base_url=HOST).get_data(as_text=True)
        self.assertIn(f'name="companies_TIPS" value="{self.companies["WP"]}"\n                     checked', html)

    def test_selected_without_company_saves_nothing(self):
        resp = self.post(self.client(), company_scope_TIPS="selected")
        self.assertEqual(resp.status_code, 400)
        with SessionFactory() as s:
            self.assertEqual(account_service.list_direct_domain_access_for_account(s, self.target_id), [])

    def test_payment_authorization_is_granted_by_the_admin_and_revoked(self):
        c = self.client()
        self.post(c, pay_TIPS_APPROVE_AND_PAY=str(self.wp_id))
        with SessionFactory() as s:
            target = s.get(m.RFOneAccount, self.target_id)
            self.assertEqual(fin.granted_restaurant_ids(s, target, fin.TIPS_APPROVE_AND_PAY), {self.wp_id})
            self.assertTrue(fin.decide(s, account=target, permission=fin.TIPS_APPROVE_AND_PAY,
                                       restaurant_id=self.wp_id).allowed)
            self.assertFalse(fin.decide(s, account=target, permission=fin.TIPS_APPROVE_AND_PAY,
                                        restaurant_id=self.md_id).allowed)
            grant = s.scalar(select(m.AuthorityGrant).where(
                m.AuthorityGrant.acting_identity_id == fin.existing_identity_for_account(s, target).id))
            admin_identity = fin.existing_identity_for_account(s, s.get(m.RFOneAccount, self.admin[0]))
            self.assertEqual(grant.granted_by_identity_id, admin_identity.id)
            grant_id = grant.id
        self.post(c)  # unticked
        with SessionFactory() as s:
            self.assertIsNotNone(s.get(m.AuthorityGrant, grant_id).revoked_at)


if __name__ == "__main__":
    unittest.main()
