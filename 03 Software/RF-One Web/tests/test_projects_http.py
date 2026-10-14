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
          page.status_code == 200 and 'class="breadcrumb"' in html and "No projects yet" in html)
    token = csrf_of(page.data)
    check("5. a POST without CSRF is refused (400)", client.post("/projects", data={"name": "X"}).status_code == 400)

    # ------------------------------------------------------------ projects
    blank = client.post("/projects", data={"csrf_token": token, "name": "  "})
    check("6. a project without a name is refused, the dialog stays open",
          blank.status_code == 422 and dialog_state(blank).get("kind") == "project" and "required" in dialog_state(blank)["error"])
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
          "on or before the planned end date of prerequisite 1.1" in html)
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
          and "between 0 and 100" in data.get("error", ""))
    grandchild = task(p1, "Nipote", c1, "2026-03-12", 1, parent=str(task_id("Impianto elettrico")))
    check("17. a second level of children is refused", grandchild.status_code == 422 and "only one level" in grandchild.data.decode())
    lavori, vini, orlando = task_id("Lavori"), task_id("Carta dei vini"), task_id("Ricerca immobile")
    cycle = client.post(f"/projects/{p1}/tasks/{lavori}", data=MultiDict([
        ("csrf_token", token), ("title", "Lavori"), ("chapter_id", str(c1)), ("parent_task_id", ""),
        ("planned_start_date", "2026-03-10"), ("planned_duration_days", "20"), ("percent_complete", "0"),
        ("predecessor_ids", str(task_id("Permessi comunali"))), ("predecessor_ids", str(vini))]))
    cycle_data = dialog_state(cycle)
    check("18. a circular prerequisite is refused; the chosen prerequisites stay selected",
          cycle.status_code == 422 and "Circular" in cycle_data.get("error", "")
          and sorted(cycle_data["values"]["predecessor_ids"]) == sorted([str(task_id("Permessi comunali")), str(vini)]))
    cross = task(p1, "Inaugurazione", c2, "2027-06-01", 1, preds=[orlando])
    cross_data = dialog_state(cross)
    check("19. a prerequisite from another project is refused, naming that project",
          cross.status_code == 422 and "same project" in cross_data.get("error", "")
          and "Secondo locale Orlando" in cross_data.get("error", "") and task_id("Inaugurazione") is None)
    foreign_chapter = task(p1, "Altrove", oc, "2026-05-01", 1)
    check("20. a chapter of another project is refused", foreign_chapter.status_code == 422 and task_id("Altrove") is None)
    check("21. another project's task or chapter through this project's path answers 404",
          client.post(f"/projects/{p1}/tasks/{orlando}", data={"csrf_token": token, "title": "Hack", "chapter_id": str(c1),
                      "planned_start_date": "2026-01-01", "planned_duration_days": "1", "percent_complete": "0"}).status_code == 404
          and client.post(f"/projects/{p1}/chapters/{oc}/delete", data={"csrf_token": token}).status_code == 404
          and client.get("/projects/9999").status_code == 404 and task_id("Ricerca immobile") == orlando)
    blocked = client.post(f"/projects/{p1}/chapters/{c1}/delete", data={"csrf_token": token}, follow_redirects=True)
    check("22. deleting a chapter with tasks is refused with a message", "still contains tasks" in blocked.data.decode())

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
    # Line endings depend on the checkout (CRLF on Windows): compare without them.
    css = web_app.app.test_client().get("/static/css/rf-one-projects.css").data.decode().replace("\r\n", "\n")
    check("32. print CSS: landscape, collapsed rows only hidden on screen, colours kept, rows not split",
          "@page { size: landscape" in css and "@media screen {\n  .pm-gantt tr.pm-collapsed { display: none; }" in css
          and "print-color-adjust: exact" in css and "break-inside: avoid" in css)

    # ------------------------------------------------------------ responsibles
    def responsible_id(project_id, name):
        with SessionFactory() as s:
            return s.scalar(select(m.ProjectResponsible.id).where(
                m.ProjectResponsible.project_id == project_id, m.ProjectResponsible.name == name))

    listing = client.get("/projects").data.decode()
    check("R1. the projects list has a person icon with the tooltip “Responsible” in Actions",
          listing.count('title="Responsible"') == 2 and "data-pm-responsibles=" in listing and 'id="pm-responsibles-dialog"' in listing)
    added = post(f"/projects/{p1}/responsibles", name="  Mario Rossi ")
    check("R2. a name is added; the list reopens its dialog",
          added.status_code == 302 and added.headers["Location"].endswith(f"/projects?responsibles={p1}")
          and responsible_id(p1, "Mario Rossi") is not None
          and dialog_state(client.get(f"/projects?responsibles={p1}")).get("kind") == "responsibles")
    dup = post(f"/projects/{p1}/responsibles", name="MARIO rossi")
    check("R3. a duplicate (case and spaces ignored) is refused, dialog open with the reason",
          dup.status_code == 422 and "already" in dialog_state(dup).get("error", "") and dialog_state(dup).get("id") == p1)
    post(f"/projects/{p1}/responsibles", name="Anna")
    anna = responsible_id(p1, "Anna")
    dup_rename = post(f"/projects/{p1}/responsibles/{anna}", name=" mario ROSSI")
    check("R4. renaming to an existing name is refused", dup_rename.status_code == 422 and responsible_id(p1, "Anna") == anna)

    plan_html = client.get(f"/projects/{p1}").data.decode()
    check("R5. the task dialog has a searchable Responsible field listing only this project's names",
          'name="responsible_name"' in plan_html and 'list="pm-responsible-options"' in plan_html
          and '<option value="Mario Rossi">' in plan_html and "<th>Responsible</th>" in plan_html)
    t_sel = post(f"/projects/{p1}/tasks", title="Insegna", chapter_id=str(c1), planned_start_date="2026-11-03",
                 planned_duration_days="2", percent_complete="0", responsible_name="mario rossi")
    t_new = post(f"/projects/{p1}/tasks", title="Arredi", chapter_id=str(c1), planned_start_date="2026-11-04",
                 planned_duration_days="2", percent_complete="0", responsible_name="Giulia Verdi")
    with SessionFactory() as s:
        tasks = {t.title: t for t in s.scalars(select(m.ProjectTask))}
        giulia = responsible_id(p1, "Giulia Verdi")
        count = len(list(s.scalars(select(m.ProjectResponsible).where(m.ProjectResponsible.project_id == p1))))
    check("R6. selecting an existing name assigns it (no duplicate)",
          t_sel.status_code == 302 and tasks["Insegna"].responsible_id == responsible_id(p1, "Mario Rossi"))
    check("R7. a new name typed in the combo is created in the project's list and assigned",
          t_new.status_code == 302 and giulia is not None and tasks["Arredi"].responsible_id == giulia and count == 3)
    parent = tasks["Insegna"].id
    child = post(f"/projects/{p1}/tasks", title="Montaggio insegna", parent_task_id=str(parent), chapter_id=str(c1),
                 planned_start_date="2026-11-04", planned_duration_days="1", percent_complete="0", responsible_name="Anna")
    with SessionFactory() as s:
        sub_task = s.scalar(select(m.ProjectTask).where(m.ProjectTask.title == "Montaggio insegna"))
    check("R8. a subtask can have a different responsible from its parent",
          child.status_code == 302 and sub_task.responsible_id == anna and tasks["Insegna"].responsible_id != anna)

    mario = responsible_id(p1, "Mario Rossi")
    post(f"/projects/{p1}/responsibles/{mario}", name="Mario R.")
    plan_html = client.get(f"/projects/{p1}").data.decode()
    gantt_html = client.get(f"/projects/{p1}/gantt").data.decode()
    check("R9. a rename shows everywhere: plan rows, task dialog, Gantt/print",
          '<td class="pm-resp-cell">Mario R.</td>' in plan_html and '<option value="Mario R.">' in plan_html
          and '<td class="pm-g-resp">Mario R.</td>' in gantt_html and "Mario Rossi" not in plan_html + gantt_html
          and "<th>Responsible</th>" in gantt_html)
    blocked = post(f"/projects/{p1}/responsibles/{mario}/delete")
    check("R10. deleting a name still assigned is refused, asking to reassign first",
          blocked.status_code == 422 and "assign" in dialog_state(blocked).get("error", "") and responsible_id(p1, "Mario R.") == mario)
    post(f"/projects/{p1}/tasks/{parent}", title="Insegna", chapter_id=str(c1), planned_start_date="2026-11-03",
         planned_duration_days="2", percent_complete="0", responsible_name="Giulia Verdi")
    deleted = post(f"/projects/{p1}/responsibles/{mario}/delete")
    with SessionFactory() as s:
        reassigned = s.get(m.ProjectTask, parent).responsible_id
    check("R11. after reassignment the name can be deleted",
          deleted.status_code == 302 and responsible_id(p1, "Mario R.") is None and reassigned == giulia)

    post(f"/projects/{p2}/responsibles", name="Solo Orlando")
    orlando = responsible_id(p2, "Solo Orlando")
    other_plan = client.get(f"/projects/{p2}").data.decode()
    check("R12. another project's dialog never lists this project's names",
          '<option value="Anna">' not in other_plan and '<option value="Solo Orlando">' in other_plan)
    check("R13. another project's name is out of scope (404) for rename and delete",
          post(f"/projects/{p1}/responsibles/{orlando}", name="X").status_code == 404
          and post(f"/projects/{p1}/responsibles/{orlando}/delete").status_code == 404
          and responsible_id(p2, "Solo Orlando") == orlando)
    post(f"/projects/{p1}/tasks", title="Pulizie", chapter_id=str(c1), planned_start_date="2026-11-05",
         planned_duration_days="1", percent_complete="0", responsible_name="Solo Orlando")
    with SessionFactory() as s:
        pulizie = s.scalar(select(m.ProjectTask).where(m.ProjectTask.title == "Pulizie"))
        owner = s.get(m.ProjectResponsible, pulizie.responsible_id).project_id
    check("R14. typing another project's name creates this project's own entry, never links across projects",
          owner == p1 and pulizie.responsible_id != orlando)

    # ------------------------------------------------------------ bold parents and ↑ / ↓
    client.post("/projects", data={"csrf_token": token, "name": "Ordine"})
    with SessionFactory() as s:
        p3 = s.scalar(select(m.Project.id).where(m.Project.name == "Ordine"))
    post(f"/projects/{p3}/chapters", title="Staff")
    post(f"/projects/{p3}/chapters", title="Kitchen")
    with SessionFactory() as s:
        staff, kitchen = (s.scalar(select(m.ProjectChapter.id).where(m.ProjectChapter.title == t)) for t in ("Staff", "Kitchen"))
    task(p3, "Hiring", staff, "2026-05-01", 3)
    hiring = task_id("Hiring")
    for title in ("Interviews", "Contracts", "Onboarding"):
        task(p3, title, staff, "2026-05-02", 1, parent=str(hiring))
    task(p3, "Uniforms", staff, "2026-05-01", 2, preds=[task_id("Contracts")])
    task(p3, "Appliances", kitchen, "2026-05-01", 4)
    task(p3, "Fridge", kitchen, "2026-05-02", 1, parent=str(task_id("Appliances")))
    ids = {t: task_id(t) for t in ("Hiring", "Interviews", "Contracts", "Onboarding", "Uniforms", "Appliances", "Fridge")}

    def rows(page: str) -> list[str]:
        """Task titles in the order the page shows them, with their codes."""
        return re.findall(r'<span class="pm-code">([\d.]+)</span> (?:<span class="pm-title">)?([^<]+)', page)

    def actions_of(page: str, title: str) -> str:
        row = re.search(r'data-rr-key="task:%d">.*?</tr>' % ids[title], page, re.S).group(0)
        return row[row.index('class="pm-actions"'):]

    plan3 = client.get(f"/projects/{p3}").data.decode()
    check("B1. plan: number and title in bold for tasks with subtasks only, description outside the bold",
          '<span class="pm-name pm-name-parent"><span class="pm-code">1.1</span> <span class="pm-title">Hiring</span></span>' in plan3
          and '<span class="pm-name pm-name-parent"><span class="pm-code">2.1</span> <span class="pm-title">Appliances</span></span>' in plan3
          and plan3.count("pm-name-parent") == 2
          and '<span class="pm-name"><span class="pm-code">1.2</span> <span class="pm-title">Uniforms</span></span>' in plan3)
    gantt3 = client.get(f"/projects/{p3}/gantt").data.decode()
    check("B2. Gantt (and its print): the same tasks in bold",
          '<span class="pm-name pm-name-parent"><span class="pm-code">1.1</span> Hiring</span>' in gantt3
          and '<span class="pm-name pm-name-parent"><span class="pm-code">2.1</span> Appliances</span>' in gantt3
          and gantt3.count("pm-name-parent") == 2)
    css = web_app.app.test_client().get("/static/css/rf-one-projects.css").data.decode()
    check("B3. the bold rule covers number and title", ".pm-name-parent, .pm-name-parent .pm-code { font-weight: 700; }" in css)

    hiring_actions = actions_of(plan3, "Hiring")
    check("M1. every task and subtask row ends its Actions with ↑ “Move up” and ↓ “Move down”",
          all(actions_of(plan3, t).count('title="Move up"') == 1 and actions_of(plan3, t).count('title="Move down"') == 1
              for t in ids)
          and re.search(r'title="Move down"[^>]*>↓</button>\s*</form>\s*</span>\s*</td>', hiring_actions) is not None
          and hiring_actions.index("Edit") < hiring_actions.index("Move up"))

    def disabled(title: str, tip: str) -> bool:
        return re.search(r'title="%s" aria-label="%s" disabled>' % (tip, tip), actions_of(plan3, title)) is not None

    check("M2. ↑ disabled on the first and ↓ on the last of each group (chapter tasks, subtasks)",
          disabled("Hiring", "Move up") and not disabled("Hiring", "Move down")
          and disabled("Uniforms", "Move down") and not disabled("Uniforms", "Move up")
          and disabled("Interviews", "Move up") and disabled("Onboarding", "Move down")
          and not disabled("Contracts", "Move up") and not disabled("Contracts", "Move down")
          and disabled("Appliances", "Move up") and disabled("Appliances", "Move down")
          and disabled("Fridge", "Move up") and disabled("Fridge", "Move down"))

    def move(title: str, direction: str, project=None):
        return post(f"/projects/{project or p3}/tasks/{ids[title]}/move", direction=direction)

    def fields():
        with SessionFactory() as s:
            out = {}
            for t in s.scalars(select(m.ProjectTask).where(m.ProjectTask.id.in_(ids.values()))):
                deps = sorted(s.scalars(select(m.ProjectTaskDependency.predecessor_task_id)
                                        .where(m.ProjectTaskDependency.successor_task_id == t.id)))
                out[t.id] = (t.chapter_id, t.parent_task_id, t.planned_start_date, t.planned_duration_days,
                             t.percent_complete, t.responsible_id, deps)
            return out

    before = fields()
    moved = move("Hiring", "down")
    plan3 = client.get(f"/projects/{p3}").data.decode()  # a refresh: read back from the database
    check("M3. a parent moves down with all its children; codes follow the new order",
          moved.status_code == 302 and moved.headers["Location"].endswith(f"/projects/{p3}")
          and rows(plan3)[:5] == [("1.1", "Uniforms"), ("1.2", "Hiring"), ("1.2.1", "Interviews"),
                                  ("1.2.2", "Contracts"), ("1.2.3", "Onboarding")])
    check("M4. Gantt and print show the same order",
          rows(client.get(f"/projects/{p3}/gantt").data.decode())[:5] == rows(plan3)[:5])
    move("Onboarding", "up")
    plan3 = client.get(f"/projects/{p3}").data.decode()
    check("M5. a subtask moves among its parent's children only",
          rows(plan3)[:5] == [("1.1", "Uniforms"), ("1.2", "Hiring"), ("1.2.1", "Interviews"),
                              ("1.2.2", "Onboarding"), ("1.2.3", "Contracts")])
    check("M6. a prerequisite keeps its task and shows its new code",
          re.search(r'<span class="pm-pred-chip[^"]*" title="Contracts[^"]*">1\.2\.3</span>', plan3) is not None)
    edge = client.post(f"/projects/{p3}/tasks/{ids['Uniforms']}/move", data={"csrf_token": token, "direction": "up"},
                       follow_redirects=True)
    check("M7. moving past the edge of a group is refused with a message; nothing changes",
          "already the first of its group" in edge.data.decode() and rows(edge.data.decode())[:5] == rows(plan3)[:5]
          and move("Fridge", "down").status_code == 302 and rows(client.get(f"/projects/{p3}").data.decode()) == rows(plan3))
    check("M8. only the order changed: ids, chapter, parent, dates, percentage, responsible, prerequisites kept",
          fields() == before)
    check("M9. CSRF required; another project's task answers 404; without PROJECTS 403",
          client.post(f"/projects/{p3}/tasks/{ids['Hiring']}/move", data={"direction": "up"}).status_code == 400
          and move("Hiring", "up", project=p1).status_code == 404
          and outsider.post(f"/projects/{p3}/tasks/{ids['Hiring']}/move",
                            data={"csrf_token": csrf_of(outsider.get("/").data), "direction": "up"}).status_code == 403
          and rows(client.get(f"/projects/{p3}").data.decode()) == rows(plan3))
    check("M10. the waiting state and the guard against repeated clicks are on the page",
          "data-pm-move" in plan3 and "rf-one-row-return.js" in plan3
          and "pm-moving" in web_app.app.test_client().get("/static/js/rf-one-projects.js").data.decode())

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    code = main()
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
    sys.exit(code)
