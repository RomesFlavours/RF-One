"""Directory HTTP/access/job and populated migration acceptance. No live services."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest

# Reuse the existing isolated web-test bootstrap, including migration to head.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_clover_acquisition_http as fixture

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from rfone_data_store import employee_directory as directory

m = fixture.m
web = fixture.web_app
SessionFactory = fixture.SessionFactory
jobs = fixture.jobs
PASSWORD = fixture.PASSWORD
ROOT = "/administration/employees"


class EmployeeDirectoryHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the REAL migration on a populated previous-head database,
        # with a Shift referencing the stable legacy employee ID.
        store = Path(fixture._DATA_STORE_DIR)
        config = Config(str(store / "alembic.ini"))
        config.set_main_option("script_location", str(store / "migrations"))
        os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = os.environ["RFONE_DATABASE_URL"]
        command.downgrade(config, "d5a120261021")
        with SessionFactory() as db:
            source = m.SourceSystem(code="CLOVER", name="Clover")
            db.add(source)
            db.flush()
            merchant = m.Merchant(name="Directory Test", source_system_id=source.id, source_merchant_id="DIR-WP")
            db.add(merchant)
            db.flush()
            location = m.Location(name="Winter Park", merchant_id=merchant.id, source_system_id=source.id,
                                  source_location_id="DIR-WP", timezone="America/New_York")
            db.add(location)
            db.flush()
            employee_id = db.scalar(text("INSERT INTO employees (location_id, source_system_id, source_employee_id, display_name, custom_id, active) VALUES (:location, :source, 'E1', 'Jane Smith', 'MANAGEMENT', true) RETURNING id"),
                                    {"location": location.id, "source": source.id})
            cls.employee_id, cls.location_id, cls.source_id = employee_id, location.id, source.id
            db.add(m.Shift(employee_id=employee_id, location_id=location.id, source_system_id=source.id,
                           source_shift_id="S1", clock_in=datetime(2026, 10, 1, tzinfo=timezone.utc)))
            db.add(m.EmployeeCompensationTerm(employee_id=employee_id, function_label="Manager",
                compensation_basis="HOURLY", hourly_rate_minor=2500,
                valid_from=datetime(2026, 10, 1, tzinfo=timezone.utc), source_note="Management only"))
            for username, permissions in [("directory-user", ("EMPLOYEES",)),
                                          ("directory-manager", ("EMPLOYEES",)),
                                          ("directory-sync", ("EMPLOYEES", "CLOVER_ACQUISITION")),
                                          ("directory-denied", ("BANK",))]:
                account = fixture.account_service.create_account(db, username=username, display_name=username,
                    password=PASSWORD, status="ACTIVE", is_admin=False)
                for permission in permissions:
                    fixture.account_service.set_domain_access(db, account_id=account.id, domain_code=permission, enabled=True,
                        role_code="admin" if username == "directory-manager" else None)
            owner = fixture.account_service.create_account(db, username="directory-owner", display_name="Directory Owner",
                password=PASSWORD, status="ACTIVE", is_admin=True)
            owner.is_owner = True
            db.commit()
        command.upgrade(config, "head")
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        web.app.config["TESTING"] = True
        web.clover_job_launcher = fixture.RecordingLauncher()

    def client(self, username=None):
        client = web.app.test_client()
        if username:
            response = fixture.login(client, username)
            self.assertIn(response.status_code, (302, 303))
        return client

    def csrf(self, client):
        return fixture.csrf(client.get(f"{ROOT}/{self.employee_id}", base_url=fixture.HOST).data)

    def test_01_populated_migration_keeps_ids_and_work_history(self):
        with SessionFactory() as db:
            link = db.scalar(select(m.EmployeeCloverLink))
            self.assertEqual(link.employee_id, self.employee_id)
            self.assertEqual(link.merchant_id, "DIR-WP")
            self.assertEqual(db.scalar(select(m.Shift)).employee_id, self.employee_id)
            self.assertEqual(db.get(m.Employee, self.employee_id).custom_id, "MANAGEMENT")
            keys = inspect(db.get_bind()).get_unique_constraints("employees")
            self.assertTrue(any(set(key["column_names"]) == {"location_id", "source_system_id", "source_employee_id"} for key in keys))
            owner = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == "directory-owner"))
            self.assertTrue(fixture.account_service.list_domain_access_for_account(db, owner.id)[0].enabled)

    def test_02_access_and_home_administration_link(self):
        self.assertEqual(self.client().get(ROOT, base_url=fixture.HOST).status_code, 302)
        denied = self.client("directory-denied")
        self.assertEqual(denied.get(ROOT, base_url=fixture.HOST).status_code, 403)
        self.assertNotIn(ROOT.encode(), denied.get("/", base_url=fixture.HOST).data)
        allowed = self.client("directory-user")
        response = allowed.get("/", base_url=fixture.HOST)
        html = response.data.decode()
        self.assertTrue(html.index("Administration") < html.index("Anagrafica dipendenti") < html.index("Settings"))
        self.assertEqual(allowed.get(ROOT, base_url=fixture.HOST).status_code, 200)
        self.assertEqual(allowed.get(f"{ROOT}/{self.employee_id}", base_url=fixture.HOST).status_code, 200)
        token = fixture.csrf(allowed.get('/profile', base_url=fixture.HOST).data)
        self.assertEqual(allowed.post(f"{ROOT}/{self.employee_id}", data={"csrf_token": token,
            "action": "management", "display_name": "Not authorized"}, base_url=fixture.HOST).status_code, 403)

    def test_03_management_csrf_and_import_preserves_terms(self):
        client = self.client("directory-manager")
        path = f"{ROOT}/{self.employee_id}"
        data = {"action": "management", "display_name": "Jane Managed", "custom_id": "RF1", "active": "true"}
        self.assertEqual(client.post(path, data=data, base_url=fixture.HOST).status_code, 400)
        data["csrf_token"] = self.csrf(client)
        self.assertEqual(client.post(path, data=data, base_url=fixture.HOST).status_code, 302)
        with SessionFactory() as db:
            directory.import_snapshot(db, location_id=self.location_id, merchant_id="DIR-WP",
                records=[{"id": "E1", "name": "Jane Smith", "customId": "CLOVER", "email": "wp@example.test", "role": "EMPLOYEE"}])
            db.commit()
            employee = db.get(m.Employee, self.employee_id)
            self.assertEqual((employee.display_name, employee.custom_id, employee.active), ("Jane Managed", "RF1", True))
            term = db.scalar(select(m.EmployeeCompensationTerm))
            self.assertEqual((term.function_label, term.hourly_rate_minor, term.source_note), ("Manager", 2500, "Management only"))

    def test_04_manual_site_link_conflict_and_review(self):
        with SessionFactory() as db:
            wp = db.get(m.Location, self.location_id)
            md = m.Location(name="Mount Dora", merchant_id=wp.merchant_id, source_system_id=self.source_id,
                            source_location_id="DIR-MD", timezone="America/New_York")
            db.add(md)
            db.flush()
            _, pending = directory.import_snapshot(db, location_id=md.id, merchant_id="DIR-MD",
                records=[{"id": "E1", "name": "Jane Smith", "email": "md@example.test", "role": "MANAGER"}])
            self.assertEqual(len(pending), 1)  # imported name still suggests renamed management identity
            link_id = pending[0]
            db.commit()
        client = self.client("directory-manager")
        data = {"employee_id": self.employee_id, "csrf_token": self.csrf(client)}
        self.assertEqual(client.post(f"{ROOT}/links/{link_id}/confirm", data=data, base_url=fixture.HOST).status_code, 302)
        detail = client.get(f"{ROOT}/{self.employee_id}", base_url=fixture.HOST)
        self.assertIn(b"wp@example.test", detail.data)
        self.assertIn(b"md@example.test", detail.data)
        self.assertIn(b"Da risolvere", detail.data)
        self.assertIn(b"Mount Dora", detail.data)
        with SessionFactory() as db:
            links = list(db.scalars(select(m.EmployeeCloverLink)))
            fingerprint = directory.review_fingerprint(links)
        review = {"action": "review", "fingerprint": fingerprint, "csrf_token": self.csrf(client)}
        client.post(f"{ROOT}/{self.employee_id}", data=review, base_url=fixture.HOST)
        self.assertIn(b"Esaminate", client.get(f"{ROOT}/{self.employee_id}", base_url=fixture.HOST).data)
        with SessionFactory() as db:
            self.assertEqual(len(list(db.scalars(select(m.Employee)))), 1)

    def test_05_sync_reuses_jobs_permissions_and_csrf(self):
        user = self.client("directory-user")
        data = {"location_id": self.location_id, "csrf_token": fixture.csrf(user.get('/profile', base_url=fixture.HOST).data)}
        self.assertEqual(user.post(ROOT + "/sync-now", data=data, base_url=fixture.HOST).status_code, 403)
        allowed = self.client("directory-sync")
        self.assertEqual(allowed.post(ROOT + "/sync-now", data={"location_id": self.location_id}, base_url=fixture.HOST).status_code, 400)
        with SessionFactory() as db:
            now = datetime.now(timezone.utc)
            db.add(m.IngestionRun(source_system_id=self.source_id, location_id=self.location_id, status="COMPLETE",
                started_at=now-timedelta(hours=2), finished_at=now-timedelta(hours=1),
                acquisition_mode=jobs.MODE_BACKFILL, source_window_end=now-timedelta(hours=1)))
            db.commit()
        data["csrf_token"] = fixture.csrf(allowed.get(ROOT, base_url=fixture.HOST).data)
        response = allowed.post(ROOT + "/sync-now", data=data, base_url=fixture.HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(web.clover_job_launcher.run_ids), 1)
        page = allowed.get(ROOT, base_url=fixture.HOST).data
        self.assertIn(b"Ultima sincronizzazione:", page)
        self.assertNotIn(b"QUEUED", page)
        self.assertLess(page.index(b"Ultima sincronizzazione:"), page.index(b"Sincronizza ora"))
        # Duplicate submission uses exactly the existing acquisition lock.
        allowed.post(ROOT + "/sync-now", data=data, base_url=fixture.HOST)
        self.assertEqual(len(web.clover_job_launcher.run_ids), 1)

    def test_06_consolidation_works_on_migrated_schema_and_preserves_history(self):
        with SessionFactory() as db:
            other = m.Employee(location_id=self.location_id, display_name="Legacy Duplicate")
            db.add(other)
            db.flush()
            old_id = other.id
            db.add(m.Shift(employee_id=old_id, location_id=self.location_id, source_system_id=self.source_id,
                           source_shift_id="MERGE-SHIFT", clock_in=datetime.now(timezone.utc)))
            db.commit()
        client = self.client("directory-manager")
        response = client.post(f"{ROOT}/{old_id}", data={"action": "consolidate", "target_employee_id": self.employee_id,
            "confirm_identity": "yes", "csrf_token": self.csrf(client)}, base_url=fixture.HOST)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(f"/{self.employee_id}"))
        self.assertTrue(client.get(f"{ROOT}/{old_id}", base_url=fixture.HOST).location.endswith(f"/{self.employee_id}"))
        with SessionFactory() as db:
            self.assertEqual(db.scalar(select(m.Shift).where(m.Shift.source_shift_id == "MERGE-SHIFT")).employee_id, self.employee_id)

    def test_07_reconciliation_options_keep_inactive_sites_and_exclude_aliases(self):
        with SessionFactory() as db:
            inactive = m.Employee(location_id=self.location_id, display_name="Inactive <Person>", active=False)
            retired = m.Employee(location_id=self.location_id, display_name="Retired selector copy")
            db.add_all([inactive, retired]); db.flush()
            inactive_id, retired_id = inactive.id, retired.id
            db.add(m.EmployeeIdentityAlias(employee_id=retired_id, canonical_employee_id=inactive_id))
            db.add(m.EmployeeCloverLink(location_id=self.location_id, merchant_id="DIR-WP",
                external_employee_id="PENDING-SELECTOR", snapshot={"name": "Review person"}, state="PRESENT"))
            db.commit()
        client = self.client("directory-manager")
        for path in (ROOT, f"{ROOT}/{self.employee_id}"):
            response = client.get(path, base_url=fixture.HOST)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn(f'<option value="{inactive_id}">Inactive &lt;Person&gt;', html)
            self.assertNotIn(f'<option value="{retired_id}">', html)
            self.assertIn("Non attivo", html)
            self.assertIn("Winter Park", html)

    def test_08_native_person_without_pos_and_create_permissions(self):
        ordinary = self.client("directory-user")
        self.assertEqual(ordinary.post(ROOT + "/new", data={"csrf_token": fixture.csrf(ordinary.get("/profile", base_url=fixture.HOST).data),
            "display_name": "Not authorized"}, base_url=fixture.HOST).status_code, 403)
        manager = self.client("directory-manager")
        self.assertEqual(manager.post(ROOT + "/new", data={"display_name": "No token"}, base_url=fixture.HOST).status_code, 400)
        response = manager.post(ROOT + "/new", data={"csrf_token": self.csrf(manager),
            "display_name": "Native RF1 person", "email": "native@example.test", "phone": "123"}, base_url=fixture.HOST)
        self.assertEqual(response.status_code, 302)
        with SessionFactory() as db:
            person = db.scalar(select(m.Employee).where(m.Employee.display_name == "Native RF1 person"))
            self.assertIsNone(person.location_id)
            self.assertIsNone(person.source_system_id)
            self.assertEqual(person.email, "native@example.test")
        home = manager.get(ROOT, base_url=fixture.HOST)
        self.assertEqual(home.status_code, 200)
        self.assertIn("Senza sede", home.get_data(as_text=True))

    def test_09_context_links_require_confirmation_and_target_management_rights(self):
        with SessionFactory() as db:
            target = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == "directory-user"))
            target_id = target.id
        manager = self.client("directory-manager")
        payload = {"action": "context_link", "context_target": f"RFONE_ACCOUNT:{target_id}", "confirm_identity": "yes"}
        payload["csrf_token"] = self.csrf(manager)
        self.assertEqual(manager.post(f"{ROOT}/{self.employee_id}", data=payload, base_url=fixture.HOST).status_code, 403)
        owner = self.client("directory-owner")
        payload["csrf_token"] = self.csrf(owner)
        payload.pop("confirm_identity")
        owner.post(f"{ROOT}/{self.employee_id}", data=payload, base_url=fixture.HOST)
        with SessionFactory() as db:
            self.assertIsNone(directory.context_person_id(db, "RFONE_ACCOUNT", target_id))
        payload["confirm_identity"] = "yes"
        self.assertEqual(owner.post(f"{ROOT}/{self.employee_id}", data=payload, base_url=fixture.HOST).status_code, 302)
        self.assertIn(b"Persona RF1", self.client("directory-user").get("/profile", base_url=fixture.HOST).data)
        with SessionFactory() as db:
            self.assertEqual(directory.context_person_id(db, "RFONE_ACCOUNT", target_id), self.employee_id)
            self.assertFalse(db.get(m.RFOneAccount, target_id).is_admin)
            link = db.scalar(select(m.EmployeeContextLink).where(m.EmployeeContextLink.rfone_account_id == target_id))
            link_id = link.id
        self.assertEqual(owner.post(f"{ROOT}/{self.employee_id}", data={"csrf_token": self.csrf(owner),
            "action": "context_unlink", "context_link_id": link_id, "confirm_identity": "yes"}, base_url=fixture.HOST).status_code, 302)
        with SessionFactory() as db:
            self.assertIsNone(directory.context_person_id(db, "RFONE_ACCOUNT", target_id))

    def test_10_downgrade_refuses_to_discard_native_person_data(self):
        config = Config(str(Path(fixture._DATA_STORE_DIR) / "alembic.ini"))
        config.set_main_option("script_location", str(Path(fixture._DATA_STORE_DIR) / "migrations"))
        os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = os.environ["RFONE_DATABASE_URL"]
        try:
            with self.assertRaisesRegex(RuntimeError, "Refusing to discard"):
                command.downgrade(config, "c8e1f4a7b2d6")
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        with SessionFactory() as db:
            self.assertEqual(db.scalar(text("SELECT version_num FROM alembic_version")), "d9e220261029")
            self.assertIsNotNone(db.scalar(select(m.Employee).where(m.Employee.display_name == "Native RF1 person")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
