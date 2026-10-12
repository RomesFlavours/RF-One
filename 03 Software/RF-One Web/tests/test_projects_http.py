"""MyRF Project Management over HTTP, on a throwaway database:

* PROJECTS access gates every page and action (403 without it), CSRF on every POST;
* the Home card appears with the access;
* /projects lists Projects; a Project is created, renamed and opened;
* inside a Project: chapters, tasks, child activities and prerequisites are
  created and edited, linked automatically to that Project and Chapter;
* a refusal keeps the dialog open with the values entered and the reason;
* two Projects: lists, Gantt and print show only the opened Project's data,
  a prerequisite from the other Project is refused, and another Project's ids
  answer 404;
* the Gantt renders every row with its bar, percentage, actual days as a
  number, warnings, the Project's name, and the print rules.

Never touches a real database, AWS, or any production system.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_projects_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "projects-http-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from sqlalchemy import select  # noqa: E402
from werkzeug.datastructures import MultiDict  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STATE_RE = re.compile(r'<script type="application/json" id="pm-dialog-state">(.*?)</script>', re.S)


def csrf_of(html: bytes) -> str:
    match = CSRF_RE.search(html.decode())
    assert match, "csrf_token not found"
    return match.group(1)


def dialog_state(response) -> dict:
    match = STATE_RE.search(response.data.decode())
    return json.loads(match.group(1)) if match else {}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        planner = account_service.create_account(s, username="planner", display_name="Planner", password="PlannerPass123!",
                                                 status="ACTIVE")
        account_service.create_account(s, username="outsider", display_name="Outsider", password="OutsiderPass123!",
                                       status="ACTIVE")
        s.commit()
        planner_id = planner.id

    def login(username: str, password: str):
        client = web_app.app.test_client()
        page = client.get("/login")
        client.post("/login", data={"username": username, "password": password, "csrf_token": csrf_of(page.data)})
        return client

    # ------------------------------------------------------------ access
    outsider = login("outsider", "OutsiderPass123!")
    token = csrf_of(outsider.get("/").data)
    check("1. without PROJECTS: list, plan, Gantt and actions answer 403",
          outsider.get("/projects").status_code == 403 and outsider.get("/projects/1").status_code == 403
          and outsider.get("/projects/1/gantt").status_code == 403
          and outsider.post("/projects", data={"name": "X", "csrf_token": token}).status_code == 403)
    check("2. without PROJECTS: no Home card", "Project Management" not in outsider.get("/").data.decode())

    with SessionFactory() as s:
        account_service.set_domain_access(s, account_id=planner_id, domain_code="PROJECTS", enabled=True, role_code=None)
        s.commit()
    client = login("planner", "PlannerPass123!")
    home = client.get("/").data.decode()
    check("3. with PROJECTS: the Home card links to /projects", 'href="/projects"' in home and "Project Management" in home)
    page = client.get("/projects")
    html = page.data.decode()
    check("4. /projects is the projects list: path RF-One › Project Management, empty state",
          page.status_code == 200 and 'class="breadcrumb"' in html and "Nessun progetto" in html)
    token = csrf_of(page.data)
    check("5. a POST without CSRF is refused (400)", client.post("/projects", data={"name": "X"}).status_code == 400)

    # ------------------------------------------------------------ projects
    blank = client.post("/projects", data={"csrf_token": token, "name": "  "})
    check("6. a project without a name is refused, the dialog stays open",
          blank.status_code == 422 and dialog_state(blank).get("kind") == "project" and "obbligatorio" in dialog_state(blank)["error"])
    created = client.post("/projects", data={"csrf_token": token, "name": "Apertura"})
    with SessionFactory() as s:
        p1 = s.scalar(select(m.Project.id).where(m.Project.name == "Apertura"))
    check("7. a new project opens its own plan", created.status_code == 302 and created.headers["Location"].endswith(f"/projects/{p1}"))
    client.post("/projects", data={"csrf_token": token, "name": "Secondo locale"})
    with SessionFactory() as s:
        p2 = s.scalar(select(m.Project.id).where(m.Project.name == "Secondo locale"))
    renamed = client.post(f"/projects/{p2}/rename", data={"csrf_token": token, "name": "Secondo locale Orlando", "from": "list"})
    with SessionFactory() as s:
        check("8. a project is renamed from the list", renamed.status_code == 302 and s.get(m.Project, p2).name == "Secondo locale Orlando")

    plan_page = client.get(f"/projects/{p1}").data.decode()
    check("9. the plan shows the project's name in title, heading and path",
          "<title>Apertura · Project Management" in plan_page and '<h1 class="pm-project-title">Apertura</h1>' in plan_page
          and 'href="/projects">Project Management</a>' in plan_page and '<span aria-current="page">Apertura</span>' in plan_page)

    # ------------------------------------------------------------ inside a project
    def post(path, **data):
        return client.post(path, data={"csrf_token": token, **data})

    r1 = post(f"/projects/{p1}/chapters", title="Apertura locale", description="Lavori e permessi")
    r2 = post(f"/projects/{p1}/chapters", title="Menu")
    post(f"/projects/{p2}/chapters", title="Cantiere Orlando")
    with SessionFactory() as s:
        chapters = {c.title: c for c in s.scalars(select(m.ProjectChapter))}
    c1, c2, oc = chapters["Apertura locale"].id, chapters["Menu"].id, chapters["Cantiere Orlando"].id
    check("10. a chapter created inside a project is linked to it",
          r1.status_code == 302 and r2.status_code == 302 and chapters["Menu"].project_id == p1
          and chapters["Cantiere Orlando"].project_id == p2)

    def task(project, title, chapter, start, days, percent="0", actual="", parent="", preds=()):
        data = {"csrf_token": token, "title": title, "description": "", "chapter_id": str(chapter), "parent_task_id": parent,
                "planned_start_date": start, "planned_duration_days": str(days), "actual_duration_days": actual,
                "percent_complete": percent}
        payload = list(data.items()) + [("predecessor_ids", str(p)) for p in preds]
        return client.post(f"/projects/{project}/tasks", data=MultiDict(payload))

    def task_id(title):
        with SessionFactory() as s:
            return s.scalar(select(m.ProjectTask.id).where(m.ProjectTask.title == title))

    task(p1, "Permessi", c1, "2026-03-01", 10, percent="50", actual="6")
    task(p1, "Lavori", c1, "2026-03-10", 20, preds=[task_id("Permessi")])
    task(p1, "Impianto elettrico", c1, "2026-03-12", 5, parent=str(task_id("Lavori")))
    task(p1, "Carta dei vini", c2, "2026-04-01", 7, preds=[task_id("Lavori")])
    task(p2, "Ricerca immobile", oc, "2027-01-11", 120)
    html = client.get(f"/projects/{p1}").data.decode()
    check("11. tasks, a child activity and cross-chapter prerequisites appear with their codes",
          all(x in html for x in ("1.1</span>", "1.2</span>", "1.2.1</span>", "2.1</span>", "Impianto elettrico")))
    check("12. the plan shows only the opened project's data",
          "Ricerca immobile" not in html and "Cantiere Orlando" not in html)
    check("13. a task starting on its prerequisite's planned end gets a warning",
          "prima o nello stesso giorno della fine prevista del propedeutico 1.1" in html)
    with SessionFactory() as s:
        child = s.get(m.ProjectTask, task_id("Impianto elettrico"))
        check("14. the child is in its parent's chapter", child.chapter_id == c1 and child.parent_task_id == task_id("Lavori"))

    edit = client.post(f"/projects/{p1}/tasks/{task_id('Permessi')}", data={
        "csrf_token": token, "title": "Permessi comunali", "description": "SUAP", "chapter_id": str(c1), "parent_task_id": "",
        "planned_start_date": "2026-03-01", "planned_duration_days": "8", "actual_duration_days": "9", "percent_complete": "100"})
    with SessionFactory() as s:
        t = s.get(m.ProjectTask, task_id("Permessi comunali"))
        check("15. edit: title, description, days, actual days and percentage saved",
              edit.status_code == 302 and t is not None and t.planned_duration_days == 8
              and t.actual_duration_days == 9 and t.percent_complete == 100 and t.description == "SUAP")

    # ------------------------------------------------------------ refusals
    refused = task(p1, "Troppo", c1, "2026-03-01", 3, percent="150")
    data = dialog_state(refused)
    check("16. percent 150 refused: 422, dialog reopened with the values and the reason",
          refused.status_code == 422 and data.get("kind") == "task" and data["values"].get("title") == "Troppo"
          and "tra 0 e 100" in data.get("error", ""))
    grandchild = task(p1, "Nipote", c1, "2026-03-12", 1, parent=str(task_id("Impianto elettrico")))
    check("17. a second level of children is refused", grandchild.status_code == 422 and "un solo livello" in grandchild.data.decode())
    lavori, vini, orlando = task_id("Lavori"), task_id("Carta dei vini"), task_id("Ricerca immobile")
    cycle = client.post(f"/projects/{p1}/tasks/{lavori}", data=MultiDict([
        ("csrf_token", token), ("title", "Lavori"), ("chapter_id", str(c1)), ("parent_task_id", ""),
        ("planned_start_date", "2026-03-10"), ("planned_duration_days", "20"), ("percent_complete", "0"),
        ("predecessor_ids", str(task_id("Permessi comunali"))), ("predecessor_ids", str(vini))]))
    cycle_data = dialog_state(cycle)
    check("18. a circular prerequisite is refused; the chosen prerequisites stay selected",
          cycle.status_code == 422 and "circolare" in cycle_data.get("error", "")
          and sorted(cycle_data["values"]["predecessor_ids"]) == sorted([str(task_id("Permessi comunali")), str(vini)]))
    cross = task(p1, "Inaugurazione", c2, "2027-06-01", 1, preds=[orlando])
    cross_data = dialog_state(cross)
    check("19. a prerequisite from another project is refused, naming that project",
          cross.status_code == 422 and "stesso progetto" in cross_data.get("error", "")
          and "Secondo locale Orlando" in cross_data.get("error", "") and task_id("Inaugurazione") is None)
    foreign_chapter = task(p1, "Altrove", oc, "2026-05-01", 1)
    check("20. a chapter of another project is refused", foreign_chapter.status_code == 422 and task_id("Altrove") is None)
    check("21. another project's task or chapter through this project's path answers 404",
          client.post(f"/projects/{p1}/tasks/{orlando}", data={"csrf_token": token, "title": "Hack", "chapter_id": str(c1),
                      "planned_start_date": "2026-01-01", "planned_duration_days": "1", "percent_complete": "0"}).status_code == 404
          and client.post(f"/projects/{p1}/chapters/{oc}/delete", data={"csrf_token": token}).status_code == 404
          and client.get("/projects/9999").status_code == 404 and task_id("Ricerca immobile") == orlando)
    blocked = client.post(f"/projects/{p1}/chapters/{c1}/delete", data={"csrf_token": token}, follow_redirects=True)
    check("22. deleting a chapter with tasks is refused with a message", "contiene ancora dei task" in blocked.data.decode())

    # ------------------------------------------------------------ list
    listing = client.get("/projects").data.decode()
    check("23. the list shows both projects with their own counts",
          "Apertura</a>" in listing and "Secondo locale Orlando</a>" in listing
          and re.search(r"Apertura</a></td>\s*<td class=\"num\">2</td>\s*<td class=\"num\">4</td>", listing) is not None)

    # ------------------------------------------------------------ Gantt
    gantt = client.get(f"/projects/{p1}/gantt")
    g = gantt.data.decode()
    rows = re.findall(r'data-gantt-node="([ct]\d+)"', g)
    check("24. Gantt: a row for every chapter and task of the project, children included",
          gantt.status_code == 200 and len([r for r in rows if r.startswith("c")]) == 2
          and len([r for r in rows if r.startswith("t")]) == 4)
    check("25. Gantt: only the opened project's data", "Ricerca immobile" not in g and "Cantiere Orlando" not in g)
    check("26. Gantt: the project's name heads the page (printed) and is in the path",
          '<h1 class="pm-project-title">Gantt — Apertura</h1>' in g
          and f'href="/projects/{p1}">Apertura</a>' in g and '<span aria-current="page">Gantt</span>' in g)
    check("27. Gantt: one planned bar per task with the percentage inside it",
          g.count('class="pm-bar"') == 4 and 'class="pm-bar-fill" style="width:100%"' in g)
    check("28. Gantt: actual days are a number, not a second bar", '<td class="num">9</td>' in g and "pm-actual-bar" not in g)
    check("29. Gantt: a child row lists its chapter and parent as ancestors (collapsible)",
          f'data-gantt-ancestors="c{c1} t{lavori}"' in g)
    other = client.get(f"/projects/{p2}/gantt").data.decode()
    check("30. the other project's Gantt has only its own task",
          "Ricerca immobile" in other and "Permessi" not in other and "Gantt — Secondo locale Orlando" in other)
    check("31. Gantt: Print button; commands hidden in print",
          "data-gantt-print" in g and 'class="btn-row no-print pm-gantt-commands"' in g)
    css = web_app.app.test_client().get("/static/css/rf-one-projects.css").data.decode()
    check("32. print CSS: landscape, collapsed rows only hidden on screen, colours kept, rows not split",
          "@page { size: landscape" in css and "@media screen {\n  .pm-gantt tr.pm-collapsed { display: none; }" in css
          and "print-color-adjust: exact" in css and "break-inside: avoid" in css)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    code = main()
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
    sys.exit(code)
