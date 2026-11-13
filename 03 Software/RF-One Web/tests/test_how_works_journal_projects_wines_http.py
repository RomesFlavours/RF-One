#!/usr/bin/env python
"""HTTP-level checks of the contextual help ("How … works" modal) on the
Development Journal, Project Management and Restaurant Wines pages.

Every reachable page is fetched and must carry its own help section: the
layout's link (`data-how-works="<section>"`) with the right label ("How X
works" on a module home, "How this page works" elsewhere), the section
content (`id="help-<section>"`) and exactly one help dialog.

Mirrors this app's own test convention: throwaway SQLite database created
before `app.py` is imported, migrated explicitly, a throwaway document
folder, Werkzeug's Flask test client, `main()` returning an exit code.
Never touches AWS or any shared database.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_how_works_jpw_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
_DOC_DIR = tempfile.mkdtemp(prefix="rfoneweb_how_works_jpw_docs_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "how-works-jpw-secret"
os.environ["RFONE_DEV_JOURNAL_DOCUMENT_DIR"] = _DOC_DIR
os.environ.pop("RFONE_DEV_JOURNAL_DOCUMENT_BUCKET", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import legal_entity_service  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.dev_journal import models as dj  # noqa: E402
from rfone_data_store.restaurant_wines import wine_types  # noqa: E402
from sqlalchemy import select  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    resp = client.get("/login")
    csrf = extract_csrf(resp.data)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


def link_label(html: str, section: str) -> str | None:
    match = re.search(r'<button[^>]*data-how-works="' + re.escape(section) + r'"[^>]*>([^<]*)</button>', html)
    return match.group(1).strip() if match else None


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def page_has_help(client, path: str, section: str, title: str | None = None) -> str:
        resp = client.get(path)
        html = resp.data.decode("utf-8")
        expected = f"How {title} works" if title else "How this page works"
        check(f"{path}: 200", resp.status_code == 200, str(resp.status_code))
        check(f"{path}: link data-how-works=\"{section}\"", f'data-how-works="{section}"' in html)
        check(f"{path}: section id help-{section}", f'id="help-{section}"' in html)
        check(f"{path}: label '{expected}'", link_label(html, section) == expected, repr(link_label(html, section)))
        check(f"{path}: exactly one help dialog", html.count('id="rf-help-dialog"') == 1, str(html.count('id="rf-help-dialog"')))
        return html

    try:
        with SessionFactory() as s:
            user = account_service.create_account(s, username="worker", display_name="Worker One",
                                                  password="WorkerPass123!")
            admin = account_service.create_account(s, username="boss", display_name="Boss Admin",
                                                   password="BossPass123!", is_admin=True)
            for code in ("DEV_JOURNAL", "PROJECTS", "WINES"):
                account_service.set_domain_access(s, account_id=user.id, domain_code=code, enabled=True, role_code=None)
            account_service.set_domain_access(s, account_id=admin.id, domain_code="DEV_JOURNAL", enabled=True,
                                              role_code=None)
            wine_types.seed_reference_wine_types(s)
            s.commit()
            user_id = user.id

        c = web_app.app.test_client()
        login(c, "worker", "WorkerPass123!")

        # ---- Development Journal -----------------------------------------
        page_has_help(c, "/dev-journal", "dev-journal-home", "Development Journal")
        new_page = page_has_help(c, "/dev-journal/new", "dev-journal-work-form")
        check("new work form: help speaks of the create mode", "<h2>New work</h2>" in new_page and "Create work" in new_page)
        csrf = extract_csrf(c.get("/dev-journal/new").data)
        resp = c.post("/dev-journal/new", data={
            "csrf_token": csrf, "title": "Help test work", "domain_code": "SYSTEM", "objective": "Check the help.",
            "responsible_account_id": str(user_id), "phase": "STUDY", "status": "IN_PROGRESS", "next_step": "",
        })
        check("a work is created", resp.status_code == 302, str(resp.status_code))
        with SessionFactory() as s:
            work_id = s.scalar(select(dj.DevJournalWork.id).where(dj.DevJournalWork.title == "Help test work"))
        resp = c.post(f"/dev-journal/{work_id}/entries", data={
            "csrf_token": csrf, "phase": "STUDY", "entry_type": "ACTIVITY", "body": "First text",
        })
        check("an entry is added", resp.status_code == 302, str(resp.status_code))
        with SessionFactory() as s:
            entry_id = s.scalar(select(dj.DevJournalEntry.id).where(dj.DevJournalEntry.work_id == work_id))

        work_page = page_has_help(c, f"/dev-journal/{work_id}", "dev-journal-work")
        check("open work: the help does not describe Reopen", "<dt>Reopen</dt>" not in work_page)
        edit_page = page_has_help(c, f"/dev-journal/{work_id}/edit", "dev-journal-work-form")
        check("edit work form: help speaks of the edit mode", "<h2>Edit work</h2>" in edit_page)
        own = page_has_help(c, f"/dev-journal/{work_id}/entries/{entry_id}/edit", "dev-journal-entry-correct")
        check("own entry: the help does not speak of an administrator correction", "as an administrator" not in own
              .split('id="help-dev-journal-entry-correct"', 1)[1])
        resp = c.post(f"/dev-journal/{work_id}/entries/{entry_id}/edit", data={
            "csrf_token": csrf, "phase": "STUDY", "entry_type": "ACTIVITY", "body": "Corrected text",
        })
        check("the entry is corrected", resp.status_code == 302, str(resp.status_code))
        page_has_help(c, f"/dev-journal/{work_id}/entries/{entry_id}/versions", "dev-journal-entry-versions")

        resp = c.post(f"/dev-journal/{work_id}/edit", data={
            "csrf_token": csrf, "title": "Help test work", "domain_code": "SYSTEM", "objective": "Check the help.",
            "responsible_account_id": str(user_id), "phase": "RELEASED", "status": "COMPLETED", "next_step": "",
        })
        check("the work is completed", resp.status_code == 302, str(resp.status_code))
        closed = page_has_help(c, f"/dev-journal/{work_id}", "dev-journal-work")
        check("closed work: the help describes Reopen", "<dt>Reopen</dt>" in closed)

        a = web_app.app.test_client()
        login(a, "boss", "BossPass123!")
        other = page_has_help(a, f"/dev-journal/{work_id}/entries/{entry_id}/edit", "dev-journal-entry-correct")
        check("administrator on another's entry: the help explains the administrator correction",
              "as an administrator" in other.split('id="help-dev-journal-entry-correct"', 1)[1])

        # ---- Project Management -------------------------------------------
        page_has_help(c, "/projects", "projects-home", "Project Management")
        token = extract_csrf(c.get("/projects").data)
        resp = c.post("/projects", data={"csrf_token": token, "name": "Help project"})
        check("a project is created", resp.status_code == 302, str(resp.status_code))
        with SessionFactory() as s:
            project_id = s.scalar(select(m.Project.id).where(m.Project.name == "Help project"))
        page_has_help(c, f"/projects/{project_id}", "projects-plan")
        page_has_help(c, f"/projects/{project_id}/gantt", "projects-gantt")
        c.post(f"/projects/{project_id}/chapters", data={"csrf_token": token, "title": "Chapter A"})
        with SessionFactory() as s:
            chapter_id = s.scalar(select(m.ProjectChapter.id).where(m.ProjectChapter.project_id == project_id))
        resp = c.post(f"/projects/{project_id}/tasks", data={
            "csrf_token": token, "title": "Task A", "chapter_id": str(chapter_id), "planned_start_date": "2026-11-02",
            "planned_duration_days": "3", "percent_complete": "10",
        })
        check("a task is created", resp.status_code == 302, str(resp.status_code))
        page_has_help(c, "/projects", "projects-home", "Project Management")
        page_has_help(c, f"/projects/{project_id}", "projects-plan")
        page_has_help(c, f"/projects/{project_id}/gantt", "projects-gantt")

        # ---- Restaurant Wines ----------------------------------------------
        page_has_help(c, "/restaurant/wines", "wines-home", "Wines")  # no Entity yet
        with SessionFactory() as s:
            entity_id = legal_entity_service.create_legal_entity(s, legal_name="Help Entity LLC").id
            s.commit()
        home = page_has_help(c, "/restaurant/wines", "wines-home", "Wines")
        check("the old 'How Wines works' tab is gone from the section tabs", "wines-help-link" not in home
              and 'href="/restaurant/wines/how-it-works"' not in home)
        csrf = extract_csrf(c.get("/restaurant/wines").data)
        resp = c.post("/restaurant/wines/lists/new", data={
            "csrf_token": csrf, "entity_id": str(entity_id), "effective_from": "2026-01-01", "mode": "EMPTY"})
        check("a Wine list is created", resp.status_code == 302, str(resp.status_code))
        page_has_help(c, f"/restaurant/wines?entity={entity_id}", "wines-home", "Wines")
        page_has_help(c, "/restaurant/wines/availability", "wines-availability")
        page_has_help(c, "/restaurant/wines/types", "wines-types")

        guide = c.get("/restaurant/wines/how-it-works")
        guide_html = guide.data.decode("utf-8")
        check("the full Wines guide still opens", guide.status_code == 200, str(guide.status_code))
        check("the full guide reuses the three help sections",
              all(f'id="help-{s}"' in guide_html for s in ("wines-home", "wines-availability", "wines-types")))
        check("the full guide has no help dialog of its own", 'id="rf-help-dialog"' not in guide_html)
    finally:
        shutil.rmtree(_DOC_DIR, ignore_errors=True)
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"{len(passed)} passed, {len(failed)} failed")
    if not failed:
        print("ALL CHECKS PASSED")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
