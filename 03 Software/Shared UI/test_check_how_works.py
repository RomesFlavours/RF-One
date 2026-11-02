#!/usr/bin/env python
"""Tests of the How Works release check (UI_HOW_WORKS_001) on a throwaway Git repository. No network.

    python test_check_how_works.py
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_how_works as chk

GUIDE = '{% extends "base.html" %}<section id="list">List</section><section id="edit">Edit</section>'
BASE = '<html><body><a data-how-works="{{ section }}" href="/guide#{{ section }}">How Works</a></body></html>'


class HowWorksCheckTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="how_works_check_"))
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.test")
        self.git("config", "user.name", "Test")
        self.registry = {"apps": {"Demo": {
            "root": "03 Software/Demo", "templates": "03 Software/Demo/templates",
            "pages": {"list.html": "guide.html#list", "edit.html": ["guide.html#edit"]},
            "not_operational": {"base.html": "layout", "guide.html": "the guide"},
            "help_missing": {"old.html": "legacy"}}}}
        self.write("templates/base.html", BASE)
        self.write("templates/guide.html", GUIDE)
        self.write("templates/list.html", '{% extends "base.html" %}list')
        self.write("templates/edit.html", '{% extends "modal.html" if modal else "base.html" %}edit')
        self.write("templates/old.html", '{% extends "base.html" %}old')
        self.write("templates/_part.html", "a fragment, never classified")
        self.write("app.py", "VALUE = 1\n")
        self.save_registry()
        self.base = self.commit("initial")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # helpers
    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.dir, check=True, capture_output=True, text=True).stdout.strip()

    def write(self, rel, text):
        path = self.dir / "03 Software/Demo" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def save_registry(self):
        path = self.dir / chk.REGISTRY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.registry), encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run_check(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = chk.main(["--root", str(self.dir), *args])
        return code, out.getvalue()

    # tree checks
    def test_clean_repository_passes(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("2 page(s) with Help, 1 still without, 0 error(s)", out)

    def test_new_page_without_how_works_is_an_error(self):
        self.write("templates/new.html", '{% extends "base.html" %}new')
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("page new.html has no How Works", out)

    def test_page_without_link_is_an_error(self):
        self.write("templates/base.html", "<html><body>no link</body></html>")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("list.html shows no How Works link", out)

    def test_target_must_be_an_existing_section(self):
        self.registry["apps"]["Demo"]["pages"]["list.html"] = "guide.html"
        self.registry["apps"]["Demo"]["pages"]["edit.html"] = "guide.html#missing"
        self.save_registry()
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("opens the top of the guide", out)
        self.assertIn('no section id "missing"', out)

    def test_stale_registry_entry_is_an_error(self):
        (self.dir / "03 Software/Demo/templates/old.html").unlink()
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("help_missing entry old.html does not exist", out)

    def test_report_lists_pages_without_help(self):
        code, out = self.run_check("--report")
        self.assertEqual(code, 0)
        self.assertIn("WARN  Demo: old.html still without page-specific Help", out)

    def test_rev_reads_the_commit_not_the_working_tree(self):
        self.write("templates/new.html", '{% extends "base.html" %}new')       # uncommitted
        self.assertEqual(self.run_check("--rev", "HEAD")[0], 0)
        self.assertEqual(self.run_check()[0], 1)

    # release correspondence
    def test_page_change_without_its_help_is_a_release_error(self):
        self.write("templates/list.html", '{% extends "base.html" %}list with a new filter')
        self.commit("List: add a filter")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base)
        self.assertEqual(code, 1)
        self.assertIn("changes page list.html but its Help", out)

    def test_page_change_with_its_help_passes(self):
        self.write("templates/list.html", '{% extends "base.html" %}list with a new filter')
        self.commit("List: add a filter")
        self.write("templates/guide.html", GUIDE.replace("List", "List and its filter"))
        self.commit("Guide: the filter")                                  # same release, later commit
        self.assertEqual(self.run_check("--rev", "HEAD", "--since", self.base)[0], 0)

    def test_code_change_needs_some_help_of_the_app(self):
        self.write("app.py", "VALUE = 2\n")
        self.commit("Change a rule")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base)
        self.assertEqual(code, 1)
        self.assertIn("changes 03 Software/Demo/app.py but no Demo Help is updated", out)

    def test_declared_technical_change_passes(self):
        self.write("app.py", "VALUE = 1  # same behaviour\n")
        self.commit("Refactor\n\nHow-Works: technical - same behaviour, comment only")
        self.assertEqual(self.run_check("--rev", "HEAD", "--since", self.base)[0], 0)

    def test_tests_and_documents_are_not_functional(self):
        self.write("test_app.py", "assert True\n")
        self.write("README.md", "notes\n")
        self.commit("Tests and notes")
        self.assertEqual(self.run_check("--rev", "HEAD", "--since", self.base)[0], 0)

    def test_change_to_a_page_without_help_is_a_release_error(self):
        self.write("templates/old.html", '{% extends "base.html" %}old, changed')
        self.commit("Old page: change")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base)
        self.assertEqual(code, 1)
        self.assertIn("changes page old.html, which has no Help yet", out)

    def test_new_page_cannot_enter_help_missing(self):
        self.write("templates/new.html", '{% extends "base.html" %}new')
        self.registry["apps"]["Demo"]["help_missing"]["new.html"] = "added later"
        self.save_registry()
        self.commit("New page\n\nHow-Works: technical - wrongly declared")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base)
        self.assertEqual(code, 1)
        self.assertIn("new page new.html was put in help_missing", out)

    def test_unchanged_legacy_pages_never_block_a_release(self):
        # PO decision 2026-11-02: a release that changes a page with Help, and its Help, passes even though a
        # legacy page without Help is still in the registry.
        self.write("templates/list.html", '{% extends "base.html" %}list with a new filter')
        self.write("templates/guide.html", GUIDE.replace("List", "List and its filter"))
        self.commit("List: add a filter, with its Help")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base, "--report")
        self.assertEqual(code, 0, out)
        self.assertIn("WARN  Demo: old.html still without page-specific Help", out)

    def test_new_operational_page_blocks_the_release(self):
        self.write("templates/new.html", '{% extends "base.html" %}new')
        self.commit("New page\n\nHow-Works: technical - wrongly declared")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base)
        self.assertEqual(code, 1)
        self.assertIn("page new.html has no How Works", out)

    def test_new_not_operational_page_is_shown_for_review(self):
        self.write("templates/public.html", "<html><body>candidate page</body></html>")
        self.registry["apps"]["Demo"]["not_operational"]["public.html"] = "public candidate page"
        self.save_registry()
        self.commit("Public page\n\nHow-Works: technical - not an operational page")
        code, out = self.run_check("--rev", "HEAD", "--since", self.base)
        self.assertEqual(code, 0, out)
        self.assertIn("new page public.html is classified not operational", out)

    def test_uncommitted_work_is_checked_in_working_tree_mode(self):
        self.write("app.py", "VALUE = 3\n")
        code, out = self.run_check("--since", self.base)
        self.assertEqual(code, 1)
        self.assertIn("working tree changes", out)


class RepositoryRegistryTest(unittest.TestCase):
    def test_this_repository_passes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = chk.main([])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
