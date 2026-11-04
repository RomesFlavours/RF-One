"""Organizational applicability (EMPLOYEE_APPLICABILITY_001). Disposable SQLite only."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text

from rfone_data_store import employee_applicability as ap
from rfone_data_store import employee_directory as d
from rfone_data_store import models as m
from rfone_data_store.database import create_configured_engine, create_session_factory

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


class EmployeeApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        self.wp, self.md, self.dt = (m.Restaurant(name=name) for name in ("Winter Park", "Mount Dora", "Downtown"))
        self.db.add_all([self.wp, self.md, self.dt]); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def person(self, name, kind=None, *restaurants):
        person = d.create_person(self.db, display_name=name)
        if kind:
            ap.set_applicability(self.db, person.id, kind=kind, restaurant_ids=[r.id for r in restaurants])
        return person

    def test_three_explicit_scopes_and_not_configured_is_its_own_state(self):
        single = self.person("Server One", ap.RESTAURANT, self.wp)
        several = self.person("Server Two", ap.RESTAURANTS, self.wp, self.md)
        group = self.person("Group Director", ap.GROUP)
        unset = self.person("Not Configured")
        self.assertEqual(ap.get_applicability(self.db, single.id), ap.Applicability(ap.RESTAURANT, frozenset({self.wp.id})))
        self.assertEqual(ap.get_applicability(self.db, several.id).restaurant_ids, frozenset({self.wp.id, self.md.id}))
        self.assertEqual(ap.get_applicability(self.db, group.id), ap.Applicability(ap.GROUP))
        unset_scope = ap.get_applicability(self.db, unset.id)
        self.assertEqual(unset_scope.kind, ap.NOT_CONFIGURED)
        self.assertNotEqual(unset_scope, ap.get_applicability(self.db, group.id))
        self.assertFalse(unset_scope.covers_restaurant(self.wp.id))
        self.assertTrue(ap.get_applicability(self.db, group.id).covers_restaurant(self.dt.id))

    def test_incoherent_scopes_are_refused_and_nothing_is_saved(self):
        person = self.person("Someone")
        cases = [(ap.RESTAURANT, [self.wp.id, self.md.id]), (ap.RESTAURANT, []), (ap.RESTAURANTS, [self.wp.id]),
                 (ap.GROUP, [self.wp.id]), (ap.NOT_CONFIGURED, [self.wp.id]), ("", []), (None, []),
                 (ap.RESTAURANT, [999999]), (ap.RESTAURANT, ["x"])]
        for kind, restaurants in cases:
            with self.subTest(kind=kind, restaurants=restaurants), self.assertRaises(ValueError):
                ap.set_applicability(self.db, person.id, kind=kind, restaurant_ids=restaurants)
        self.assertEqual(ap.get_applicability(self.db, person.id), ap.UNCONFIGURED)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.EmployeeApplicability)), 0)

    def test_dismissal_keeps_applicability_and_history(self):
        server = self.person("WP Server", ap.RESTAURANT, self.wp)
        server.dismissed_at, server.active = NOW, False
        self.db.flush()
        self.assertNotIn(server.id, {o.id for o in d.employee_options(self.db)})
        self.assertEqual(ap.get_applicability(self.db, server.id), ap.Applicability(ap.RESTAURANT, frozenset({self.wp.id})))

    def test_no_perimeter_selection_api(self):
        # Applicability does not decide which people a user may select (PO, 2026-11-04).
        for name in ("active_people_within", "require_active_within", "PersonInScope"):
            self.assertFalse(hasattr(ap, name), name)
        self.assertFalse(hasattr(ap.Applicability, "includes"))

    def test_changes_are_appended_to_the_person_history(self):
        person = self.person("Someone", ap.RESTAURANT, self.wp)
        ap.set_applicability(self.db, person.id, kind=ap.GROUP)
        ap.set_applicability(self.db, person.id, kind=ap.GROUP)  # unchanged: no event
        ap.set_applicability(self.db, person.id, kind=ap.NOT_CONFIGURED)
        events = list(self.db.scalars(select(m.EmployeeDirectoryEvent).where(
            m.EmployeeDirectoryEvent.action == "APPLICABILITY_SET").order_by(m.EmployeeDirectoryEvent.id)))
        self.assertEqual([(e.details["before"]["kind"], e.details["after"]["kind"]) for e in events],
                         [(ap.NOT_CONFIGURED, ap.RESTAURANT), (ap.RESTAURANT, ap.GROUP), (ap.GROUP, ap.NOT_CONFIGURED)])
        self.assertEqual(events[0].details["after"]["restaurant_ids"], [self.wp.id])
        self.assertEqual(ap.get_applicability(self.db, person.id), ap.UNCONFIGURED)

    def test_alias_and_consolidation_use_the_one_identity(self):
        kept = self.person("Kept", ap.RESTAURANT, self.md)
        retired = self.person("Retired")
        d.consolidate(self.db, from_employee_id=retired.id, into_employee_id=kept.id)
        self.assertEqual(ap.get_applicability(self.db, retired.id).restaurant_ids, frozenset({self.md.id}))
        moved_from = self.person("Has scope", ap.GROUP)
        target = self.person("Target")
        d.consolidate(self.db, from_employee_id=moved_from.id, into_employee_id=target.id)
        self.assertEqual(ap.get_applicability(self.db, target.id).kind, ap.GROUP)
        first, second = self.person("First", ap.GROUP), self.person("Second", ap.RESTAURANT, self.wp)
        with self.assertRaises(ValueError):  # both configured: refused, never merged by guess
            d.consolidate(self.db, from_employee_id=first.id, into_employee_id=second.id)
        self.assertEqual(ap.get_applicability(self.db, first.id).kind, ap.GROUP)

    def test_applicability_is_not_access(self):
        person = self.person("Group Director", ap.GROUP)
        account = d.employee_account(self.db, person.id)
        self.assertEqual(ap.account_applicability(self.db, account.id).kind, ap.GROUP)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess)), 0)
        self.assertEqual(account.status, "INACTIVE")
        external = m.RFOneAccount(username="external", display_name="External", password_hash="x", status="ACTIVE",
                                  is_admin=True, session_version=1)
        self.db.add(external); self.db.flush()
        self.assertEqual(ap.account_applicability(self.db, external.id), ap.UNCONFIGURED)  # admin is not GROUP


class ApplicabilityMigrationTest(unittest.TestCase):
    """Migration e4a120261103 on a disposable SQLite file, on top of the single chain."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db", prefix="rfone_applicability_migration_")
        os.close(fd)
        here = Path(__file__).resolve().parent
        self.config = Config(str(here / "alembic.ini"))
        self.config.set_main_option("script_location", str(here / "migrations"))
        os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = "sqlite:///" + self.path.replace(os.sep, "/")
        command.upgrade(self.config, "e3f120261103")
        self.engine = create_engine(os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"])

    def tearDown(self):
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        self.engine.dispose()
        os.remove(self.path)

    def version(self):
        with self.engine.connect() as c:
            return c.scalar(text("SELECT version_num FROM alembic_version"))

    def test_additive_no_backfill_and_guarded_downgrade(self):
        with self.engine.begin() as c:
            employee = c.execute(m.Employee.__table__.insert().values(display_name="Existing")).inserted_primary_key[0]
        command.upgrade(self.config, "head")
        self.assertEqual(self.version(), "e4a120261103")
        with self.engine.begin() as c:
            self.assertEqual(c.scalar(text("SELECT count(*) FROM employee_applicability")), 0)  # NOT_CONFIGURED
            with self.assertRaises(Exception):  # kinds are explicit
                c.execute(text("INSERT INTO employee_applicability (employee_id, scope_kind) VALUES (:e, 'ALL')"),
                          {"e": employee})
        command.downgrade(self.config, "e3f120261103")  # nothing configured: reversible
        self.assertEqual(self.version(), "e3f120261103")
        command.upgrade(self.config, "head")
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO employee_applicability (employee_id, scope_kind) VALUES (:e, 'GROUP')"),
                      {"e": employee})
        with self.assertRaisesRegex(RuntimeError, "restore a verified backup"):
            command.downgrade(self.config, "e3f120261103")
        self.assertEqual(self.version(), "e4a120261103")


if __name__ == "__main__":
    unittest.main()
