"""Selection start-up against a shared database (MIGRATIONS.md).

Each scenario starts Selection (`import app`) in a separate process against a
copy of one disposable SQLite database. Selection must never migrate an
existing database: it checks its tables read-only, starts when they are
present even if the revision is unknown, and refuses an incompatible schema.
"""
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_STORE = HERE.parent / "RF-One Data Store"
UNKNOWN = "ffff20991231"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _start(db_path):
    env = dict(os.environ, RFONE_DATABASE_URL="sqlite:///" + Path(db_path).as_posix())
    return subprocess.run([sys.executable, "-c", "import app; print('SELECTION STARTED')"], cwd=HERE, env=env,
                          capture_output=True, text=True, timeout=600)


def _revision(path):
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    finally:
        connection.close()


class SelectionStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.base = cls.tmp / "base.db"
        cls.first = _start(cls.base)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _copy(self, name, *statements):
        path = self.tmp / name
        shutil.copyfile(self.base, path)
        connection = sqlite3.connect(path)
        try:
            for statement in statements:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()
        return path

    def _assert_starts_unchanged(self, path):
        before, revision = _sha(path), _revision(path)
        result = _start(path)
        self.assertIn("SELECTION STARTED", result.stdout, result.stderr[-3000:])
        self.assertEqual((_sha(path), _revision(path)), (before, revision), "Selection wrote to the database")
        return result

    def test_new_private_database_is_created_at_head_with_workspace(self):
        self.assertIn("SELECTION STARTED", self.first.stdout, self.first.stderr[-3000:])
        self.assertEqual(_revision(self.base), ["e1b220261102"])
        connection = sqlite3.connect(self.base)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
        self.assertIn("selection_workspace_positions", tables)

    def test_unknown_newer_revision_with_compatible_schema_starts_with_warning(self):
        path = self._copy("unknown.db", f"UPDATE alembic_version SET version_num='{UNKNOWN}'")
        result = self._assert_starts_unchanged(path)
        self.assertIn(UNKNOWN, result.stderr)
        self.assertIn("not in this code's migration chain", result.stderr)

    def test_older_known_revision_is_not_upgraded_at_start(self):
        path = self._copy("older.db", "DROP TABLE interview_sessions",
                          "UPDATE alembic_version SET version_num='d9e220261029'")
        self._assert_starts_unchanged(path)

    def test_other_domains_tables_are_not_required(self):
        path = self._copy("no-tips.db", "DROP TABLE tip_distribution_rule_versions", "DROP TABLE interview_sessions")
        self._assert_starts_unchanged(path)

    def test_missing_selection_table_refuses_to_start(self):
        path = self._copy("no-workspace.db", "DROP TABLE selection_workspace_positions")
        before = _sha(path)
        result = _start(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IncompatibleSchemaError", result.stderr)
        self.assertIn("selection_workspace_positions", result.stderr)
        self.assertEqual(_sha(path), before)

    def test_missing_shared_column_refuses_to_start(self):
        path = self._copy("no-column.db", "ALTER TABLE rfone_accounts RENAME COLUMN display_name TO display_name_old")
        result = _start(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rfone_accounts.display_name", result.stderr)


class RequiredTablesDeclarationTests(unittest.TestCase):
    def test_every_shared_model_used_by_selection_code_is_required(self):
        """REQUIRED_TABLES must follow the code: a new shared model used by
        Selection has to be declared, or the start check would miss it."""
        sys.path[:0] = [str(HERE), str(DATA_STORE)]
        from rfone_data_store.models import Base
        from workspace.schema import REQUIRED_TABLES

        classes = {mp.class_.__name__: mp.local_table.name for mp in Base.registry.mappers
                   if mp.class_.__module__ == "rfone_data_store.models"}
        used = set()
        roots = (DATA_STORE / "rfone_data_store" / "selection", HERE)
        for path in (p for root in roots for p in root.rglob("*.py") if not p.name.startswith("test")):
            source = path.read_text(encoding="utf-8", errors="ignore")
            aliases = {"models"} | set(re.findall(r"import\s+models\s+as\s+(\w+)", source))
            imported = set()
            for block in re.findall(r"from (?:rfone_data_store\.models|\.+models)\s+import\s+\(?([^)]*?)\)?\n", source):
                imported |= set(re.findall(r"\w+", block))
            used |= {t for c, t in classes.items()
                     if c in imported or any(re.search(rf"\b{a}\.{c}\b", source) for a in aliases)}
        self.assertEqual(sorted(used - set(REQUIRED_TABLES)), [])


if __name__ == "__main__":
    unittest.main()
