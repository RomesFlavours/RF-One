#!/usr/bin/env python
"""REGISTRY_CLOVER_CREATE_001 — «Crea in Clover» on the Registry card, against a simulated Clover (never a real one).

WP and MD with the same person, merchant and role per request, one Clover ID per site, missing/ambiguous/
unsafe role, disabled installation, uncertain answer, interruption between creation and save, concurrency,
refusal, and the manual POS ID that stays available.
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

_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_clover_create_")
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

import threading  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from rfone_data_store import clover_employee_create as cc  # noqa: E402
from rfone_data_store.technical.connectors.clover import employee_writer as ew  # noqa: E402


class Interrupted(Exception):
    """The process stops between Clover's creation and RF-One's save."""


class FakeClover:
    """Simulated Clover: per merchant, the existing roles and the employees created. Records every call."""

    def __init__(self):
        self.roles = {}            # merchant -> {role_id: (name, systemRole)}
        self.employees = {}        # merchant -> [dict]
        self.calls = []            # (merchant, op, details)
        self.behaviour = {}        # merchant -> "ok" | "uncertain_created" | "uncertain_nothing" | "refuse" | "interrupt" | "slow"
        self.search_ok = True

    def writer(self, merchant_id):
        clover = self

        class Writer:
            mode = "simulated"

            def __init__(self):
                self.merchant_id = merchant_id

            def check_role(self, role_id):
                clover.calls.append((merchant_id, "check_role", role_id))
                role = clover.roles.get(merchant_id, {}).get(role_id)
                return ew.RoleCheck(found=role is not None, name=role and role[0], system_role=role and role[1])

            def create_employee(self, *, name, custom_id, role_id):
                clover.calls.append((merchant_id, "create", {"name": name, "custom_id": custom_id, "role_id": role_id}))
                behaviour = clover.behaviour.get(merchant_id, "ok")
                if behaviour == "refuse":
                    return ew.CreateResult("REFUSED", status_code=400, message="invalid name")
                if behaviour == "uncertain_nothing":
                    return ew.CreateResult("UNCERTAIN", message="Clover did not answer in time.")
                if behaviour == "slow":
                    time.sleep(0.6)
                staff = clover.employees.setdefault(merchant_id, [])
                new_id = f"{merchant_id}-E{len(staff) + 1}"
                staff.append({"id": new_id, "name": name, "customId": custom_id, "roles": [role_id]})
                if behaviour == "uncertain_created":
                    return ew.CreateResult("UNCERTAIN", message="Clover did not answer in time.")
                if behaviour == "interrupt":
                    raise Interrupted()
                return ew.CreateResult("CREATED", employee_id=new_id, status_code=200)

            def employee_role_ids(self, employee_id):
                return next((e["roles"] for e in clover.employees.get(merchant_id, []) if e["id"] == employee_id), None)

            def find_by_custom_id(self, custom_id):
                clover.calls.append((merchant_id, "find", custom_id))
                if not clover.search_ok:
                    return ew.FindResult(ok=False, error="network error")
                return ew.FindResult(ok=True, employee_ids=[e["id"] for e in clover.employees.get(merchant_id, [])
                                                             if e["customId"] == custom_id])
        return Writer()

    def creates(self, merchant_id=None):
        return [c for c in self.calls if c[1] == "create" and (merchant_id is None or c[0] == merchant_id)]


CLOVER = FakeClover()
web_app.app.config["CLOVER_EMPLOYEE_WRITER_FACTORY"] = CLOVER.writer
web_app.app.config["CLOVER_EMPLOYEE_WRITER_AVAILABLE"] = lambda merchant_id: None


def csrf(html):
    return CSRF_RE.search(html if isinstance(html, str) else html.decode("utf-8")).group(1)


class CloverCreateHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as db:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            db.add(source); db.flush()
            sites = {}
            for key, merchant_id in (("wp", "MERCH-WP"), ("md", "MERCH-MD"), ("nopos", None)):
                restaurant = m.Restaurant(name=f"Site {key.upper()}", default_currency="USD")
                db.add(restaurant); db.flush()
                if merchant_id:
                    merchant = m.Merchant(source_system_id=source.id, source_merchant_id=merchant_id, name=key, active=True)
                    db.add(merchant); db.flush()
                    location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=merchant_id,
                                          name=key, currency="USD", timezone="America/New_York",
                                          operating_day_cutoff_time=dtime(4, 0), active=True)
                    db.add(location); db.flush()
                    db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
                sites[key] = restaurant
            area = m.OperationalArea(name="Restaurant Operations"); db.add(area); db.flush()
            roles = {}
            for name in ("Server", "Cook", "Host", "Dishwasher"):
                role = m.RestaurantRole(name=name, code=name.upper()); db.add(role); db.flush()
                db.add(m.OperationalAreaRole(operational_area_id=area.id, restaurant_role_id=role.id))
                roles[name] = role
            now = datetime.now(timezone.utc)

            def mapping(site, clover_role, label, role):
                db.add(m.RegistryRoleMapping(restaurant_id=sites[site].id, source="CLOVER", original_key=clover_role,
                                             original_label=label, restaurant_role_id=roles[role].id,
                                             valid_from=now, origin="SEED"))
            mapping("wp", "CR-WP-SERVER", "Server", "Server")
            mapping("md", "CR-MD-SERVER", "Server", "Server")
            mapping("wp", "CR-WP-HOST", "Host", "Host")                   # exists in Clover at MANAGER level
            mapping("wp", "CR-WP-DISH-A", "Dish A", "Dishwasher")         # ambiguous: two Clover roles
            mapping("wp", "CR-WP-DISH-B", "Dish B", "Dishwasher")
            mapping("md", "CR-MD-GONE", "Old role", "Host")               # configured but missing in Clover
            CLOVER.roles = {"MERCH-WP": {"CR-WP-SERVER": ("Server", "EMPLOYEE"), "CR-WP-HOST": ("Host", "MANAGER")},
                            "MERCH-MD": {"CR-MD-SERVER": ("Server", "EMPLOYEE")}}
            admin = accounts.create_account(db, username="admin", display_name="Admin A.", password=PASSWORD,
                                            email="admin@example.invalid", is_admin=True)
            db.flush()
            accounts.set_domain_access(db, account_id=admin.id, domain_code="EMPLOYEES", enabled=True, role_code="admin")

            def person(name, role, *at):
                card = directory.create_person(db, display_name=name, restaurant_id=sites[at[0]].id,
                                               role_id=roles[role].id, area_id=area.id)
                for extra in at[1:]:
                    directory.assign_site(db, employee_id=card.id, restaurant_id=sites[extra].id,
                                          role_id=roles[role].id, area_id=area.id)
                return card.id
            cls.ids = {
                "giulia": person("Giulia Both", "Server", "wp", "md"),
                "cook": person("Carlo Cook", "Cook", "wp"),
                "host": person("Hana Host", "Host", "wp"),
                "dish": person("Dino Dish", "Dishwasher", "wp"),
                "gone": person("Gina Gone", "Host", "md"),
                "nopos": person("Nora NoPos", "Server", "nopos"),
                "unsure": person("Ugo Uncertain", "Server", "wp"),
                "crash": person("Cora Crash", "Server", "md"),
                "race": person("Rita Race", "Server", "wp"),
                "refuse": person("Rolf Refused", "Server", "md"),
                "manual": person("Mara Manual", "Server", "wp"),
            }
            db.commit()
            cls.admin_id = admin.id
            cls.sites = {k: v.id for k, v in sites.items()}
        cls.client = web_app.app.test_client()
        page = cls.client.get("/login", base_url=HOST)
        cls.client.post("/login", base_url=HOST, data={"username": "admin", "password": PASSWORD, "csrf_token": csrf(page.data)})

    def card(self, key):
        response = self.client.get(f"/administration/employees/{self.ids[key]}", base_url=HOST)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def site_block(self, key, site):
        page = self.card(key)
        start = page.index(f'id="site-{self.sites[site]}"')
        return page[start:page.index("</section>", start)]

    def act(self, key, site, action="clover_create"):
        response = self.client.post(f"/administration/employees/{self.ids[key]}", base_url=HOST, follow_redirects=True,
                                    data={"csrf_token": csrf(self.card(key)), "action": action,
                                          "restaurant_id": self.sites[site]})
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def pos(self, key):
        with SessionFactory() as db:
            return {site: link.external_employee_id for site, link in directory.pos_links(db, self.ids[key]).items()}

    # 1-2. WP and MD, same person ------------------------------------------------------------------------------
    def test_same_person_wp_and_md_each_merchant_with_its_role_and_its_own_id(self):
        block = self.site_block("giulia", "wp")
        self.assertIn("Crea in Clover", block); self.assertIn("ruolo Clover <strong>Server</strong>", block)
        before = len(CLOVER.calls)
        self.assertIn("Created in Clover", self.act("giulia", "wp"))
        self.assertIn("Created in Clover", self.act("giulia", "md"))
        creates = [c for c in CLOVER.calls[before:] if c[1] == "create"]
        self.assertEqual([(c[0], c[2]["role_id"], c[2]["custom_id"]) for c in creates],
                         [("MERCH-WP", "CR-WP-SERVER", f"RF1-{self.ids['giulia']}"),
                          ("MERCH-MD", "CR-MD-SERVER", f"RF1-{self.ids['giulia']}")])
        pos = self.pos("giulia")
        self.assertEqual(pos[self.sites["wp"]], creates[0][2] and "MERCH-WP-E" + pos[self.sites["wp"]].split("-E")[1])
        self.assertTrue(pos[self.sites["wp"]].startswith("MERCH-WP-E") and pos[self.sites["md"]].startswith("MERCH-MD-E"))
        # Reopen the card: each site keeps its own Clover ID; the second save did not overwrite the first.
        self.assertIn(pos[self.sites["wp"]], self.site_block("giulia", "wp"))
        self.assertIn(pos[self.sites["md"]], self.site_block("giulia", "md"))
        # Already linked: the link is shown and nothing is sent again.
        again = len(CLOVER.creates())
        self.assertIn("already has the POS ID", self.act("giulia", "wp"))
        self.assertEqual(len(CLOVER.creates()), again)
        self.assertNotIn(">Crea in Clover</button>", self.site_block("giulia", "wp"))

    # 1. what is missing, shown before any request --------------------------------------------------------------
    def test_missing_or_unsafe_configuration_stops_before_writing(self):
        before = len(CLOVER.creates())
        self.assertIn("No Clover role corresponds to the RF-One role «Cook»", self.site_block("cook", "wp"))
        self.assertIn("No Clover role corresponds", self.act("cook", "wp"))
        self.assertIn("more than one Clover role", self.site_block("dish", "wp"))
        self.assertIn("no Clover connection", self.site_block("nopos", "nopos"))
        self.assertIn("level MANAGER, above the base Employee level", self.act("host", "wp"))
        self.assertIn("does not exist in this merchant", self.act("gone", "md"))
        self.assertEqual(len(CLOVER.creates()), before)                    # nothing was written
        self.assertIn("non inviato", self.site_block("host", "wp"))         # outcome shown on the card
        self.assertEqual(self.pos("host"), {})

    def test_disabled_installation_shows_why(self):
        web_app.app.config["CLOVER_EMPLOYEE_WRITER_AVAILABLE"] = ew.availability
        try:
            os.environ.pop(ew.ENABLE_ENV, None)
            self.assertIn("not enabled on this installation", self.site_block("manual", "wp"))
            os.environ[ew.ENABLE_ENV] = "sandbox"
            self.assertIn("CLOVER_SANDBOX_API_TOKEN__MERCH-WP", self.site_block("manual", "wp"))
        finally:
            os.environ.pop(ew.ENABLE_ENV, None)
            web_app.app.config["CLOVER_EMPLOYEE_WRITER_AVAILABLE"] = lambda merchant_id: None

    # 3. uncertain answers, interruption, concurrency -------------------------------------------------------------
    def test_uncertain_answer_never_sends_a_second_creation_until_resolved(self):
        CLOVER.behaviour["MERCH-WP"] = "uncertain_nothing"
        try:
            self.assertIn("uncertain", self.act("unsure", "wp"))
        finally:
            CLOVER.behaviour.pop("MERCH-WP")
        creates = len(CLOVER.creates())
        page = self.act("unsure", "wp")                                      # search finds nothing -> no new insert
        self.assertIn("No second employee is sent", page)
        CLOVER.search_ok = False
        self.assertIn("could not be searched", self.act("unsure", "wp"))
        CLOVER.search_ok = True
        self.assertEqual(len(CLOVER.creates()), creates)
        self.assertIn("Verifica e recupera da Clover", self.site_block("unsure", "wp"))
        self.assertIn("too recent", self.act("unsure", "wp", "clover_clear"))
        with SessionFactory() as db:                                        # two minutes later
            for e in cc.open_attempts(db, self.ids["unsure"], self.sites["wp"]):
                e.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
        self.assertIn("request is closed", self.act("unsure", "wp", "clover_clear"))
        self.assertIn("Created in Clover", self.act("unsure", "wp"))
        self.assertEqual(len(CLOVER.creates()), creates + 1)
        self.assertEqual(len([e for e in CLOVER.employees["MERCH-WP"] if e["customId"] == f"RF1-{self.ids['unsure']}"]), 1)

    def test_created_but_interrupted_before_save_is_recovered_first(self):
        CLOVER.behaviour["MERCH-MD"] = "interrupt"
        try:
            with self.assertRaises(Interrupted):
                cc.create_in_clover(SessionFactory, employee_id=self.ids["crash"], restaurant_id=self.sites["md"],
                                    account_id=self.admin_id, writer_factory=CLOVER.writer,
                                    writer_available=lambda merchant_id: None)
        finally:
            CLOVER.behaviour.pop("MERCH-MD")
        self.assertEqual(self.pos("crash"), {})                              # Clover has it, RF-One does not
        self.assertIn("Una richiesta a Clover è aperta", self.site_block("crash", "md"))
        creates = len(CLOVER.creates())
        self.assertIn("Link recovered", self.act("crash", "md"))
        self.assertEqual(len(CLOVER.creates()), creates)                     # recovered, not created again
        created = [e for e in CLOVER.employees["MERCH-MD"] if e["customId"] == f"RF1-{self.ids['crash']}"]
        self.assertEqual(len(created), 1)
        self.assertEqual(self.pos("crash"), {self.sites["md"]: created[0]["id"]})
        self.assertIn("collegamento recuperato", self.site_block("crash", "md"))

    def test_uncertain_but_created_is_recovered(self):
        CLOVER.behaviour["MERCH-MD"] = "uncertain_created"
        try:
            self.act("refuse", "md")
        finally:
            CLOVER.behaviour.pop("MERCH-MD")
        self.assertIn("Link recovered", self.act("refuse", "md"))
        self.assertEqual(len([e for e in CLOVER.employees["MERCH-MD"] if e["customId"] == f"RF1-{self.ids['refuse']}"]), 1)

    def test_double_click_and_concurrent_requests_send_at_most_one(self):
        CLOVER.behaviour["MERCH-WP"] = "slow"
        outcomes, barrier = [], threading.Barrier(3)

        def click():
            barrier.wait()
            outcomes.append(cc.create_in_clover(SessionFactory, employee_id=self.ids["race"], restaurant_id=self.sites["wp"],
                                                account_id=self.admin_id, writer_factory=CLOVER.writer,
                                                writer_available=lambda merchant_id: None))
        threads = [threading.Thread(target=click) for _ in range(3)]
        try:
            for t in threads: t.start()
            for t in threads: t.join()
        finally:
            CLOVER.behaviour.pop("MERCH-WP")
        created = [c for c in CLOVER.creates("MERCH-WP") if c[2]["custom_id"] == f"RF1-{self.ids['race']}"]
        self.assertEqual(len(created), 1, [o.message for o in outcomes])
        self.assertEqual(sum(o.message.startswith("Created in Clover") for o in outcomes), 1)
        self.assertEqual(len(self.pos("race")), 1)

    def test_refused_is_shown_and_creates_nothing(self):
        with SessionFactory() as db:
            card = directory.create_person(db, display_name="Rex Refused", restaurant_id=self.sites["md"],
                                           role_id=db.scalar(select(m.RestaurantRole.id).where(m.RestaurantRole.name == "Server")),
                                           area_id=db.scalar(select(m.OperationalArea.id)))
            db.commit(); self.ids["rex"] = card.id
        CLOVER.behaviour["MERCH-MD"] = "refuse"
        try:
            self.assertIn("Clover refused the creation (HTTP 400)", self.act("rex", "md"))
        finally:
            CLOVER.behaviour.pop("MERCH-MD")
        self.assertIn("rifiutato da Clover", self.site_block("rex", "md"))
        self.assertIn(">Crea in Clover</button>", self.site_block("rex", "md"))   # a new attempt is allowed

    # 2. manual entry stays; no Clover -> Registry import -------------------------------------------------------
    def test_manual_pos_id_still_links_an_existing_clover_employee(self):
        self.client.post(f"/administration/employees/{self.ids['manual']}", base_url=HOST,
                         data={"csrf_token": csrf(self.card("manual")), "action": "pos_id",
                               "restaurant_id": self.sites["wp"], "pos_id": "EXISTING-77"})
        self.assertEqual(self.pos("manual"), {self.sites["wp"]: "EXISTING-77"})
        with SessionFactory() as db:
            names = set(db.scalars(select(m.Employee.display_name)))
        self.assertFalse(any(n and n.startswith("MERCH-") for n in names))


if __name__ == "__main__":
    unittest.main()
