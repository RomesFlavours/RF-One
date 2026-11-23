#!/usr/bin/env python
"""REGISTRY_MULTISITE_001 — the before/after check of the AWS release covers the EFFECTIVE permissions.

A disposable SQLite database built by the real migration chain up to the revision live on AWS
(a1c220261121, before company_scope existed), with accounts, Domain accesses, companies, memberships and a
role profile. Then, with the same check script the release plan runs:

  1. snapshot at a1c220261121 -> alembic upgrade head (b2c320261121, c7d820261122) -> snapshot -> compare:
     identical, effective permissions included (same entries, same restaurants reached).
  2. a simulated revocation (one Domain access disabled) -> compare fails (exit 1) and names the account and
     Domain in `permission_changes`, both as a grant and as an effective permission.
  3. a simulated grant (a new Domain access) and an administrator flag also make it fail.
  4. plan step 2a: a site role made available to every site (restaurant_id -> NULL) changes no permission.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import MetaData, create_engine, insert, text

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import registry_multisite_rollback_rehearsal as rehearsal  # noqa: E402

CHECK = HERE / "registry_multisite_migration_check.py"


def _snapshot(url, path):
    proc = subprocess.run([sys.executable, str(CHECK), "--url", url, "snapshot", "--json", str(path)], cwd=str(HERE),
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _compare(before, after):
    proc = subprocess.run([sys.executable, str(CHECK), "compare", str(before), str(after)], cwd=str(HERE),
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    return proc.returncode, json.loads(proc.stdout[proc.stdout.find("{"):])


def _insert(conn, meta, table, **values):
    """Insert with the columns this revision has; NOT NULL columns without a default get a placeholder."""
    tab = meta.tables[table]
    row = {k: v for k, v in values.items() if k in tab.c}
    for column in tab.columns:
        if column.name not in row and not column.nullable and column.server_default is None and not column.primary_key:
            python_type = getattr(column.type, "python_type", str)
            row[column.name] = ("x" if python_type is str else
                                __import__("datetime").datetime(2026, 1, 1) if python_type.__name__ == "datetime"
                                else False if python_type is bool else 0)
    conn.execute(insert(tab), row)


class EffectivePermissionsCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="registry_permissions_"))
        cls.url = f"sqlite:///{(cls.work / 'aws_line.db').as_posix()}"
        rehearsal._alembic(HERE, cls.url, "upgrade", "r9a120261113")
        rehearsal._run(HERE, "selection_tables", cls.url)
        rehearsal._alembic(HERE, cls.url, "upgrade", "a1c220261121")    # the revision live on AWS
        engine = create_engine(cls.url)
        meta = MetaData(); meta.reflect(engine)
        assert "company_scope" not in meta.tables["rfone_account_domain_access"].c   # really before b2c3
        with engine.begin() as conn:
            _insert(conn, meta, "legal_entities", id=1, legal_name="RF-Winter Park", status="ACTIVE")
            _insert(conn, meta, "legal_entities", id=2, legal_name="RF-Mount Dora", status="ACTIVE")
            _insert(conn, meta, "restaurants", id=1, name="Rome's Flavours - WP", legal_entity_id=1)
            _insert(conn, meta, "restaurants", id=4, name="Rome's Flavours - MD", legal_entity_id=2)
            _insert(conn, meta, "rfone_company_contexts", id=101, name="WP", kind="COMPANY", legal_entity_id=1, active=True)
            _insert(conn, meta, "rfone_company_contexts", id=102, name="MD", kind="COMPANY", legal_entity_id=2, active=True)
            for account_id, admin in ((10, True), (11, False), (12, False), (13, False)):
                _insert(conn, meta, "rfone_accounts", id=account_id, username=f"u{account_id}", display_name=f"U {account_id}",
                        password_hash="x", status="ACTIVE", is_admin=admin, is_owner=False, session_version=1)
            for i, (account_id, domain, role) in enumerate(((10, "EMPLOYEES", "admin"), (11, "TIPS", None),
                                                            (11, "EMPLOYEES", None), (12, "TRAINING", "student"),
                                                            (13, "TIPS", None)), start=1):
                _insert(conn, meta, "rfone_account_domain_access", id=i, account_id=account_id, domain_code=domain,
                        role_code=role, enabled=True, scope="ALL")
            # account 13: a role profile at MD whose role opens TIPS
            _insert(conn, meta, "restaurant_roles", id=1, name="Manager", code="MANAGER")
            _insert(conn, meta, "operational_areas", id=1, name="Restaurant Operations")
            _insert(conn, meta, "rfone_person_company_memberships", id=1, account_id=13, company_id=102)
            _insert(conn, meta, "rfone_role_profile_assignments", id=1, membership_id=1, role_id=1, area_id=1)
            _insert(conn, meta, "rfone_role_permissions", id=1, role_id=1, domain_code="TIPS", scope="ALL", items="[]")
        engine.dispose()
        cls.before = _snapshot(cls.url, cls.work / "before.json")
        rehearsal._alembic(HERE, cls.url, "upgrade", "head")
        cls.after = _snapshot(cls.url, cls.work / "after.json")

    def _db(self):
        return create_engine(self.url)

    def test_1_release_keeps_every_effective_permission(self):
        rc, result = _compare(self.work / "before.json", self.work / "after.json")
        self.assertEqual((rc, result["identical"], result["permission_changes"]), (0, True, []), result)
        self.assertEqual(result["alembic"], [["a1c220261121"], ["c7d820261122"]])
        effective = self.after["effective_permissions"]["rows"]
        self.assertEqual(effective["11:TIPS"], {"enter": True, "admin": False, "restaurants": [1, 4]})
        self.assertEqual(effective["12:TRAINING"]["enter"], True)
        self.assertNotIn("12:TIPS", effective)
        self.assertEqual(self.before["effective_permissions"], self.after["effective_permissions"])

    def test_2_a_simulated_revocation_fails_the_check(self):
        engine = self._db()
        with engine.begin() as conn:
            conn.execute(text("UPDATE rfone_account_domain_access SET enabled = 0 "
                              "WHERE account_id = 11 AND domain_code = 'TIPS'"))
        try:
            _snapshot(self.url, self.work / "revoked.json")
            rc, result = _compare(self.work / "after.json", self.work / "revoked.json")
            self.assertEqual((rc, result["identical"]), (1, False))
            effective = [c for c in result["permission_changes"] if c["kind"] == "effective"]
            self.assertEqual([(c["key"], c["before"]["enter"], c["after"]) for c in effective], [("11:TIPS", True, None)])
            grants = [c for c in result["permission_changes"] if c["kind"] == "grant"]
            self.assertEqual({(c["key"], (c["before"] or c["after"])["enabled"]) for c in grants},
                             {("rfone_account_domain_access", 1), ("rfone_account_domain_access", 0)})
            self.assertIn("effective_permissions", result["differences"])
        finally:
            with engine.begin() as conn:
                conn.execute(text("UPDATE rfone_account_domain_access SET enabled = 1 "
                                  "WHERE account_id = 11 AND domain_code = 'TIPS'"))
            engine.dispose()

    def test_3_a_simulated_grant_or_administrator_flag_fails_the_check(self):
        engine = self._db()
        try:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO rfone_account_domain_access (id, account_id, domain_code, enabled, scope, "
                                  "company_scope, created_at, updated_at) VALUES (99, 12, 'EMPLOYEES', 1, 'ALL', 'ALL', "
                                  "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
            _snapshot(self.url, self.work / "granted.json")
            rc, result = _compare(self.work / "after.json", self.work / "granted.json")
            self.assertEqual(rc, 1)
            self.assertIn("12:EMPLOYEES", [c["key"] for c in result["permission_changes"] if c["kind"] == "effective"])
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM rfone_account_domain_access WHERE id = 99"))
                conn.execute(text("UPDATE rfone_accounts SET is_admin = 1 WHERE id = 12"))
            _snapshot(self.url, self.work / "admin.json")
            rc, result = _compare(self.work / "after.json", self.work / "admin.json")
            self.assertEqual(rc, 1)
            self.assertTrue(any(c["kind"] == "grant" and c["key"] == "rfone_accounts" for c in result["permission_changes"]))
        finally:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM rfone_account_domain_access WHERE id = 99"))
                conn.execute(text("UPDATE rfone_accounts SET is_admin = 0 WHERE id = 12"))
            engine.dispose()

    def test_4_sharing_a_site_role_with_every_site_changes_no_permission(self):
        """Plan step 2a: the WP-only role given to every site (restaurant_id -> NULL), with a role profile on it."""
        engine = self._db()
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE restaurant_roles SET restaurant_id = 1 WHERE id = 1"))
            _snapshot(self.url, self.work / "role_wp_only.json")
            with engine.begin() as conn:
                self.assertEqual(conn.execute(text("UPDATE restaurant_roles SET restaurant_id = NULL "
                                                   "WHERE id = 1 AND restaurant_id = 1")).rowcount, 1)
            _snapshot(self.url, self.work / "role_shared.json")
            rc, result = _compare(self.work / "role_wp_only.json", self.work / "role_shared.json")
            self.assertEqual((rc, result["identical"], result["permission_changes"]), (0, True, []), result)
        finally:
            with engine.begin() as conn:
                conn.execute(text("UPDATE restaurant_roles SET restaurant_id = NULL WHERE id = 1"))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
