"""Shared-database migration rule (MIGRATIONS.md): build chain check, no
migration at service start, read-only compatibility instead of exact revisions.

Every database here is a disposable SQLite file in a temporary directory.
"""
import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import check_migration_chain as chain
import clover_connector_release_check as clover_check
from rfone_data_store import database
from rfone_data_store.schema_compatibility import (
    IncompatibleSchemaError, known_revisions, read_only_engine, require_compatible_schema,
)

HERE = Path(__file__).resolve().parent
UNKNOWN = "ffff20991231"
# This tree's single head: the AWS revision or a later one built on it
# (e4a120261103 applicability, on e3f120261103 lifecycle, on AWS revision e1b220261102).
TREE_HEAD = "e4a120261103"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _url(path):
    return "sqlite:///" + Path(path).as_posix()


def _execute(path, *statements):
    connection = sqlite3.connect(path)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def _revision(path):
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    finally:
        connection.close()


class MigrationChainCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.versions = self.tmp / "versions"
        shutil.copytree(chain.VERSIONS_DIR, self.versions, ignore=shutil.ignore_patterns("__pycache__"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add(self, name, revision, down):
        (self.versions / name).write_text(f"revision = {revision!r}\ndown_revision = {down!r}\n", encoding="utf-8")

    def test_tree_contains_the_registered_aws_revision_as_its_single_head(self):
        heads, problems = chain.check(chain.VERSIONS_DIR, chain.aws_revision()[0])
        self.assertEqual(problems, [])
        self.assertEqual(heads, [TREE_HEAD])
        self.assertEqual(chain.main([]), 0)

    def test_tree_without_the_aws_revision_is_refused(self):
        (self.versions / "e0a120261101_add_interviews_test.py").unlink()
        _, problems = chain.check(self.versions, "e0a120261101")
        self.assertTrue(any("not in this tree" in p for p in problems), problems)

    def test_a_newer_branch_revision_on_top_of_aws_passes(self):
        self._add("aaaa20991231_next.py", "aaaa20991231", TREE_HEAD)
        heads, problems = chain.check(self.versions, "e0a120261101")
        self.assertEqual((heads, problems), (["aaaa20991231"], []))

    def test_fork_of_the_shared_chain_is_refused(self):
        self._add("bbbb20991231_fork.py", "bbbb20991231", "d9e220261029")
        _, problems = chain.check(self.versions, "e0a120261101")
        self.assertTrue(any("exactly one head" in p for p in problems), problems)

    def test_duplicate_revision_and_missing_parent_are_refused(self):
        self._add("dup_e0a1.py", "e0a120261101", "d9e220261029")
        self._add("cccc20991231_orphan.py", "cccc20991231", "notinthetree")
        _, problems = chain.check(self.versions, "e0a120261101")
        self.assertTrue(any("declared by both" in p for p in problems), problems)
        self.assertTrue(any("missing parent notinthetree" in p for p in problems), problems)

    def test_environment_revision_overrides_registry(self):
        os.environ[chain.ENV_VAR] = UNKNOWN
        try:
            self.assertEqual(chain.aws_revision(), (UNKNOWN, chain.ENV_VAR))
            self.assertEqual(chain.main([]), 1)
        finally:
            del os.environ[chain.ENV_VAR]

    def test_superseded_interview_prototype_is_not_in_the_chain(self):
        parents, _ = chain.load_graph()
        self.assertNotIn("f8d120261101", parents)
        self.assertNotIn("f9e220261101", parents)


class SharedDatabaseRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.base = cls.tmp / "base.db"
        cls.created = database.prepare_new_private_database(_url(cls.base))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _copy(self, name, *statements):
        path = self.tmp / name
        shutil.copyfile(self.base, path)
        _execute(path, *statements)
        return path

    def test_new_private_sqlite_file_is_created_at_head(self):
        self.assertTrue(self.created)
        self.assertEqual(_revision(self.base), [TREE_HEAD])

    def test_existing_database_is_never_migrated_by_prepare(self):
        path = self._copy("older.db", "DROP TABLE interview_sessions",
                          "UPDATE alembic_version SET version_num='d9e220261029'")
        before = _sha(path)
        self.assertFalse(database.prepare_new_private_database(_url(path)))
        self.assertEqual((_sha(path), _revision(path)), (before, ["d9e220261029"]))

    def test_shared_database_migration_requires_explicit_target(self):
        url = "postgresql://nobody@127.0.0.1:1/never_connected"
        with self.assertRaises(database.SharedDatabaseMigrationRefused):
            database.run_migrations_to_head(url)
        os.environ[database.MIGRATION_TARGET_ENV] = "d9e220261029"
        try:
            with self.assertRaises(database.SharedDatabaseMigrationRefused):
                database.run_migrations_to_head(url)
        finally:
            del os.environ[database.MIGRATION_TARGET_ENV]
        self.assertFalse(database.prepare_new_private_database(url))

    def test_read_only_engine_cannot_write(self):
        path = self._copy("readonly.db")
        before = _sha(path)
        engine = read_only_engine(_url(path))
        try:
            with self.assertRaises(Exception):
                with engine.begin() as connection:
                    connection.exec_driver_sql("UPDATE alembic_version SET version_num='x'")
        finally:
            engine.dispose()
        self.assertEqual(_sha(path), before)

    def test_known_revisions_cover_the_chain(self):
        self.assertIn("e0a120261101", known_revisions())
        self.assertNotIn(UNKNOWN, known_revisions())

    def _clover(self, path):
        engine = read_only_engine(_url(path))
        try:
            return clover_check.database_summary(engine)
        finally:
            engine.dispose()

    def test_clover_accepts_unknown_newer_revision_with_compatible_schema(self):
        path = self._copy("clover-unknown.db", f"UPDATE alembic_version SET version_num='{UNKNOWN}'")
        before = _sha(path)
        with self.assertLogs("rfone_data_store.schema_compatibility", "WARNING"):
            summary = self._clover(path)
        self.assertEqual((summary["schema_revision"], summary["revision_known"]), ([UNKNOWN], False))
        self.assertEqual(summary["orphan_shifts"], 0)
        self.assertEqual(_sha(path), before)

    def test_clover_does_not_need_other_domains_tables(self):
        path = self._copy("clover-no-interviews.db", "DROP TABLE interview_sessions",
                          "UPDATE alembic_version SET version_num='d9e220261029'")
        self.assertTrue(self._clover(path)["revision_known"])

    def test_clover_refuses_incomplete_employee_directory_schema(self):
        path = self._copy("clover-incomplete.db", "DROP TABLE employee_clover_links")
        with self.assertRaises(IncompatibleSchemaError) as raised:
            self._clover(path)
        self.assertIn("employee_clover_links", str(raised.exception))
        path = self._copy("clover-no-column.db", "ALTER TABLE employees RENAME COLUMN phone TO phone_old")
        with self.assertRaises(IncompatibleSchemaError) as raised:
            self._clover(path)
        self.assertIn("employees.phone", str(raised.exception))

    def test_database_without_revision_table_is_a_warning_when_compatible(self):
        from rfone_data_store.models import Base
        path = self._copy("no-version.db", "DROP TABLE alembic_version")
        engine = read_only_engine(_url(path))
        try:
            with self.assertLogs("rfone_data_store.schema_compatibility", "WARNING"):
                report = require_compatible_schema(engine, [Base.metadata.tables["shifts"]], service="test")
        finally:
            engine.dispose()
        self.assertEqual(report.revisions, ())


if __name__ == "__main__":
    unittest.main()
