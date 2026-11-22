#!/usr/bin/env python
"""REGISTRY_MULTISITE_001 — Registry and Anagrafica pages over HTTP (Product Owner specification 2026-11-22).

Proves on the real RF-One Web application (throwaway SQLite built from the models, never AWS or Clover):
  1. Registry > People and Anagrafica list only the people explicitly assigned to the selected site;
     a person assigned to WP and MD appears at both with one RF-One ID; an empty MD shows an empty list;
     an unknown site shows a notice and never WP instead.
  2. No "Clover identities to confirm", no "Links to reconcile", no Sync Now: their routes are gone.
  3. Manual entry needs the site (Anagrafica and Registry); a site is added to an existing card; the POS ID
     is typed on the card and refused for a second person at the same site.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from datetime import time as dtime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
for path in (APP_DIR, DATA_STORE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_registry_multisite_")
os.close(_FD)
os.remove(_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"
os.environ.pop("RFONE_UI_LANGUAGE", None)

from sqlalchemy import select, text  # noqa: E402
from rfone_data_store import models as m, access_profiles as profiles  # noqa: E402,F401
from rfone_data_store import people_registry, student_registry  # noqa: E402,F401
from rfone_data_store.training import enrollment  # noqa: E402,F401
from rfone_data_store.database import create_configured_engine  # noqa: E402

# The SQLite migration chain cannot be replayed from scratch (known, pre-existing); build the schema from the
# models and record the head revision, as the schema check of the application expects.
_engine = create_configured_engine(os.environ["RFONE_DATABASE_URL"])
m.Base.metadata.create_all(_engine)
from alembic.script import ScriptDirectory  # noqa: E402
from rfone_data_store.schema_compatibility import _MIGRATIONS_DIR  # noqa: E402
with _engine.begin() as _c:
    _c.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
    _c.execute(text("INSERT INTO alembic_version VALUES (:h)"),
               {"h": ScriptDirectory(str(_MIGRATIONS_DIR)).get_current_head()})
_engine.dispose()

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import employee_directory as directory  # noqa: E402
from rfone_data_store import rfone_account_service as accounts  # noqa: E402

HOST = "https://rfone-web.example"
PASSWORD = "a-long-enough-test-password"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf(html: bytes) -> str:
    return CSRF_RE.search(html.decode("utf-8")).group(1)


class RegistryMultisiteHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as db:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            db.add(source); db.flush()
            sites = {}
            for key, name, merchant_id, active in (("wp", "Rome's Flavours - WP", "WPM", True),
                                                   ("md", "Rome's Flavours - MD", "MDM", False)):
                merchant = m.Merchant(source_system_id=source.id, source_merchant_id=merchant_id, name=name, active=active)
                db.add(merchant); db.flush()
                location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=merchant_id,
                                      name=name, currency="USD", timezone="America/New_York",
                                      operating_day_cutoff_time=dtime(4, 0), active=active)
                restaurant = m.Restaurant(name=name, default_currency="USD")
                db.add_all([location, restaurant]); db.flush()
                db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
                sites[key] = restaurant
            area = m.OperationalArea(name="Restaurant Operations")
            db.add(area); db.flush()
            cook = m.RestaurantRole(name="Cook", code="COOK")
            db.add(cook); db.flush()
            db.add(m.OperationalAreaRole(operational_area_id=area.id, restaurant_role_id=cook.id))
            db.flush()
            admin = accounts.create_account(db, username="admin", display_name="Admin A.", password=PASSWORD,
                                            email="admin@example.invalid", is_admin=True)
            db.flush()
            accounts.set_domain_access(db, account_id=admin.id, domain_code="EMPLOYEES", enabled=True, role_code="admin")
            pick = lambda site: dict(restaurant_id=site.id, role_id=cook.id, area_id=area.id)
            anna = directory.create_person(db, display_name="Anna Both", email="anna@example.invalid", **pick(sites["wp"]))
            directory.assign_site(db, employee_id=anna.id, **pick(sites["md"]))
            luca = directory.create_person(db, display_name="Luca Winter", **pick(sites["wp"]))
            # Clover evidence at MD for Luca must not list him at MD.
            db.add(m.EmployeeCloverLink(employee_id=luca.id, location_id=db.scalar(select(m.Location.id).where(
                m.Location.source_location_id == "MDM")), merchant_id="MDM", external_employee_id="M-LUCA", state="PRESENT"))
            db.commit()
            cls.wp, cls.md, cls.area_id, cls.cook_id = sites["wp"].id, sites["md"].id, area.id, cook.id
            cls.anna_id, cls.luca_id = anna.id, luca.id
        cls.client = web_app.app.test_client()
        page = cls.client.get("/login", base_url=HOST)
        cls.client.post("/login", base_url=HOST, data={"username": "admin", "password": PASSWORD,
                                                      "csrf_token": csrf(page.data)})

    def get(self, path):
        response = self.client.get(path, base_url=HOST)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def post(self, path, data, page):
        return self.client.post(path, base_url=HOST, data={"csrf_token": csrf(self.client.get(page, base_url=HOST).data),
                                                           **data})

    # 1. lists ----------------------------------------------------------------------------------------
    def test_registry_lists_only_the_selected_site(self):
        wp = self.get(f"/admin/roles?tab=people&site={self.wp}")
        self.assertIn("Anna Both", wp); self.assertIn("Luca Winter", wp)
        md = self.get(f"/admin/roles?tab=people&site={self.md}")
        self.assertIn("Anna Both", md)
        self.assertNotIn("Luca Winter", md)                     # no WP fallback, Clover link ignored
        unknown = self.get("/admin/roles?tab=people&site=9999")
        self.assertIn("The selected site is not available", unknown)
        self.assertNotIn("Luca Winter", unknown); self.assertNotIn("Anna Both", unknown)
        self.assertNotIn("Clover identities to confirm", wp)
        self.assertNotIn("clover_confirm", wp)

    def test_anagrafica_lists_only_the_selected_site_and_has_no_clover_queue(self):
        md = self.get(f"/administration/employees?site={self.md}")
        self.assertIn("Anna Both", md); self.assertNotIn("Luca Winter", md)
        wp = self.get(f"/administration/employees?site={self.wp}")
        self.assertIn("Luca Winter", wp)
        for absent in ("Collegamenti da riconciliare", "Sincronizza ora", "Conferma che è una persona nuova"):
            self.assertNotIn(absent, wp)
        self.assertIn("Sede non disponibile", self.get("/administration/employees?site=9999"))
        self.assertIn('data-how-works="employee_directory"', wp)                 # contextual help
        self.assertEqual(self.client.post("/administration/employees/sync-now", base_url=HOST).status_code, 404)
        self.assertEqual(self.client.post("/administration/employees/links/1/confirm", base_url=HOST).status_code, 404)

    def test_empty_md_shows_an_empty_list(self):
        with SessionFactory() as db:
            empty = m.Restaurant(name="Empty Site"); db.add(empty); db.commit(); empty_id = empty.id
        page = self.get(f"/administration/employees?site={empty_id}")
        self.assertIn("Nessuna persona assegnata a questa sede.", page)
        self.assertNotIn("Luca Winter", page.split("Persone senza sede")[0])
        self.assertIn("No people assigned to this site.", self.get(f"/admin/roles?tab=people&site={empty_id}"))

    # 3. manual entry, sites, POS -----------------------------------------------------------------------
    def test_manual_entry_requires_the_site_and_lands_only_there(self):
        page = f"/administration/employees?site={self.md}"
        refused = self.post("/administration/employees/new", {"display_name": "No Site Person"}, page)
        self.assertEqual(refused.status_code, 302)
        created = self.post("/administration/employees/new", {"display_name": "Mara Dora",
                            "site_role": f"{self.md}:{self.cook_id}:{self.area_id}"}, page)
        self.assertEqual(created.status_code, 302)
        with SessionFactory() as db:
            self.assertIsNone(db.scalar(select(m.Employee).where(m.Employee.display_name == "No Site Person")))
            mara = db.scalar(select(m.Employee).where(m.Employee.display_name == "Mara Dora"))
            self.assertEqual(directory.employee_site_ids(db, mara.id), {self.md})
        self.assertIn("Mara Dora", self.get(page))
        self.assertNotIn("Mara Dora", self.get(f"/administration/employees?site={self.wp}").split("Persone senza sede")[0])

    def test_registry_add_person_requires_the_site(self):
        page = "/admin/roles?tab=people"
        bad = self.post("/admin/roles", {"action": "person_create", "tab": "people", "name": "Reg No Site",
                                         "person_roles": "[]"}, page)
        self.assertEqual(bad.status_code, 422)
        good = self.post("/admin/roles", {"action": "person_create", "tab": "people", "name": "Reg With Site",
                                          "person_roles": "[]", "site_role": f"{self.wp}:{self.cook_id}:{self.area_id}"}, page)
        self.assertEqual(good.status_code, 302)
        self.assertIn("Reg With Site", self.get(f"/admin/roles?tab=people&site={self.wp}"))

    def test_card_adds_a_site_and_a_unique_pos_id(self):
        with SessionFactory() as db:   # own people: the list tests keep their fixture unchanged
            pia = directory.create_person(db, display_name="Pia Card", restaurant_id=self.wp, role_id=self.cook_id,
                                          area_id=self.area_id)
            rex = directory.create_person(db, display_name="Rex Other", restaurant_id=self.wp, role_id=self.cook_id,
                                          area_id=self.area_id)
            db.commit(); pia_id, rex_id = pia.id, rex.id
        detail = f"/administration/employees/{pia_id}"
        self.assertIn('id="sites"', self.get(detail))
        self.post(detail, {"action": "assign_site", "site_role": f"{self.md}:{self.cook_id}:{self.area_id}"}, detail)
        self.assertIn("Pia Card", self.get(f"/administration/employees?site={self.md}"))
        self.post(detail, {"action": "pos_id", "restaurant_id": str(self.wp), "pos_id": "W-PIA"}, detail)
        other = f"/administration/employees/{rex_id}"
        self.post(other, {"action": "pos_id", "restaurant_id": str(self.wp), "pos_id": "W-PIA"}, other)
        with SessionFactory() as db:
            self.assertEqual(directory.resolved_identities(db, "WPM").get("W-PIA"), pia_id)
            self.assertNotIn(rex_id, directory.resolved_identities(db, "WPM").values())
        self.assertIn("W-PIA", self.get(f"/administration/employees?site={self.wp}"))


if __name__ == "__main__":
    unittest.main()
