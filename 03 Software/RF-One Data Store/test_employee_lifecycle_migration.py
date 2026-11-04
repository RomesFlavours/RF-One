"""Migration e3f120261103 on a populated, disposable SQLite file. No real database."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text

from rfone_data_store import models as m
from rfone_data_store.employee_directory_audit import audit

HERE = Path(__file__).resolve().parent
T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


class LifecycleMigrationTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db", prefix="rfone_lifecycle_migration_")
        os.close(fd)
        self.url = "sqlite:///" + self.path.replace(os.sep, "/")
        self.config = Config(str(HERE / "alembic.ini"))
        self.config.set_main_option("script_location", str(HERE / "migrations"))
        os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = self.url
        command.upgrade(self.config, "e1b220261102")
        self.engine = create_engine(self.url)

    def tearDown(self):
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        self.engine.dispose()
        os.remove(self.path)

    def seed(self, c, *, conflict=False):
        """Previous-revision rows only (raw/Core inserts without new columns)."""
        insert = lambda model, **values: c.execute(model.__table__.insert().values(**values)).inserted_primary_key[0]
        source = insert(m.SourceSystem, code="CLOVER", name="Clover")
        merchant = insert(m.Merchant, name="M", source_system_id=source, source_merchant_id="WP")
        site = insert(m.Location, name="WP", merchant_id=merchant, source_system_id=source, source_location_id="WP")
        employee = lambda name, source_id: c.scalar(text(
            "INSERT INTO employees (location_id, source_system_id, source_employee_id, display_name, active) "
            "VALUES (:site, :source, :sid, :name, true) RETURNING id"),
            {"site": site if source_id else None, "source": source if source_id else None, "sid": source_id, "name": name})
        worked, no_clock, native, bridged = (employee("Worked", "W1"), employee("No clocks", "N1"),
                                             employee("Native", None), employee("Bridged", "B1"))
        insert(m.Shift, employee_id=worked, location_id=site, source_system_id=source, source_shift_id="S1", clock_in=T0)
        account = insert(m.RFOneAccount, username="real", display_name="Real", password_hash="hash", status="ACTIVE",
                         is_admin=False, is_owner=False, session_version=1)
        actor = insert(m.ActingIdentity, kind="HUMAN_USER", display_name="Bridged")
        student = insert(m.TrainingAccount, acting_identity_id=actor, username="student", role="student", password_hash="x")
        insert(m.RFOneTrainingIdentityLink, rfone_account_id=account, training_account_id=student)
        insert(m.EmployeeContextLink, employee_id=bridged, training_account_id=student)
        if conflict:
            other = insert(m.RFOneAccount, username="other", display_name="Other", password_hash="hash",
                           status="ACTIVE", is_admin=False, is_owner=False, session_version=1)
            insert(m.EmployeeContextLink, employee_id=bridged, rfone_account_id=other)
        return {"worked": worked, "no_clock": no_clock, "native": native, "bridged": bridged, "account": account}

    def accounts(self, c, employee_id):
        return list(c.scalars(text("SELECT rfone_account_id FROM employee_context_links "
                                   "WHERE employee_id = :e AND rfone_account_id IS NOT NULL"), {"e": employee_id}))

    def test_upgrade_reuses_bridges_provisions_shells_and_defers_unproven_records(self):
        with self.engine.begin() as c:
            ids = self.seed(c)
            before = audit(c)
        self.assertEqual(before["blocking"], {"employees_with_multiple_confirmed_accounts": [],
                                              "accounts_confirmed_for_several_employees": []})
        self.assertEqual(before["accounts_reused_from_confirmed_links"], [ids["bridged"]])
        self.assertEqual(before["accounts_deferred_without_clock_evidence"], [ids["no_clock"]])
        command.upgrade(self.config, "e3f120261103")  # this revision only; later ones have their own tests
        with self.engine.begin() as c:
            self.assertEqual(c.scalar(text("SELECT version_num FROM alembic_version")), "e3f120261103")
            self.assertEqual(self.accounts(c, ids["bridged"]), [ids["account"]])
            self.assertEqual(self.accounts(c, ids["no_clock"]), [])
            for key in ("worked", "native"):
                (shell,) = self.accounts(c, ids[key])
                row = c.execute(text("SELECT password_hash, status, email, is_admin, is_owner FROM rfone_accounts "
                                     "WHERE id = :a"), {"a": shell}).one()
                self.assertEqual(tuple(row), ("!", "INACTIVE", None, False, False))
            self.assertEqual(c.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess.__table__)), 0)
            # No cessation inferred from the old snapshot; IDs and flags preserved.
            self.assertEqual(c.scalar(text("SELECT count(*) FROM employees WHERE dismissed_at IS NOT NULL "
                                           "OR directory_eligible = false OR active IS NOT true")), 0)
            self.assertEqual(c.scalar(text("SELECT employee_id FROM shifts")), ids["worked"])
            with self.assertRaises(Exception):
                c.execute(text("INSERT INTO employee_context_links (employee_id, rfone_account_id, created_at) "
                               "VALUES (:e, :a, CURRENT_TIMESTAMP)"), {"e": ids["bridged"], "a": ids["account"] + 99})
        with self.assertRaisesRegex(RuntimeError, "retained"):
            command.downgrade(self.config, "e1b220261102")
        with self.engine.connect() as c:
            self.assertEqual(c.scalar(text("SELECT version_num FROM alembic_version")), "e3f120261103")

    def test_upgrade_refuses_indirect_conflict_before_any_change(self):
        with self.engine.begin() as c:
            ids = self.seed(c, conflict=True)
            self.assertEqual(audit(c)["blocking"]["employees_with_multiple_confirmed_accounts"], [ids["bridged"]])
            accounts = c.scalar(text("SELECT count(*) FROM rfone_accounts"))
        with self.assertRaisesRegex(RuntimeError, "Multiple RF1 accounts"):
            command.upgrade(self.config, "head")
        with self.engine.connect() as c:
            self.assertEqual(c.scalar(text("SELECT version_num FROM alembic_version")), "e1b220261102")
            self.assertEqual(c.scalar(text("SELECT count(*) FROM rfone_accounts")), accounts)
            columns = [row[1] for row in c.execute(text("PRAGMA table_info(employees)"))]
            self.assertNotIn("dismissed_at", columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)
