#!/usr/bin/env python
"""MyRF Project Management — rules, Project isolation, database constraints,
Gantt geometry and the migrations, on a disposable database
(`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`).

Never touches a real database.

Usage:
    python test_projects_service.py
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
)
from rfone_data_store.projects import service
from rfone_data_store.projects.gantt import timeline_for

MAIN_PM = "d2f6b9a3e7c1"      # Project Management on main
BEFORE_PM = "b6e4d2a8c1f9"    # Restaurant Wines
RESPONSIBLE = "e8c4a2f6b1d3"  # Task Responsible

# The schema e3a7c5f9b1d4 created on the Bank line (chapters without projects), to prove
# d2f6b9a3e7c1 completes it without losing rows.
E3A7_SCHEMA = (
    "CREATE TABLE project_chapter (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT, "
    "sort_order INTEGER NOT NULL DEFAULT 0, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE project_task (id INTEGER PRIMARY KEY, chapter_id INTEGER NOT NULL REFERENCES project_chapter (id), "
    "parent_task_id INTEGER REFERENCES project_task (id), title VARCHAR(200) NOT NULL, description TEXT, "
    "percent_complete INTEGER NOT NULL DEFAULT 0, planned_start_date DATE NOT NULL, "
    "planned_duration_days INTEGER NOT NULL, actual_duration_days INTEGER, sort_order INTEGER NOT NULL DEFAULT 0, "
    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE project_task_dependency (predecessor_task_id INTEGER NOT NULL REFERENCES project_task (id), "
    "successor_task_id INTEGER NOT NULL REFERENCES project_task (id), "
    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (predecessor_task_id, successor_task_id))",
)


def task_input(title, *, chapter_id=None, parent_task_id=None, percent=0, start=date(2026, 3, 1), days=1,
               actual=None, predecessors=(), responsible=""):
    return service.TaskInput(
        title=title, description=None, chapter_id=chapter_id, parent_task_id=parent_task_id,
        percent_complete=percent, planned_start_date=start, planned_duration_days=days,
        actual_duration_days=actual, predecessor_ids=list(predecessors), responsible_name=responsible,
    )


def refused(fn, *args, **kwargs) -> str | None:
    try:
        fn(*args, **kwargs)
    except service.ProjectValidationError as error:
        return str(error)
    return None


def out_of_scope(fn, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except service.ProjectScopeError:
        return True
    return False


def main() -> int:
    url = resolve_test_database_url("projects_service")
    print(f"Database URL: {redact_database_url(url)}")
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    engine = create_configured_engine(url)
    try:
        Session = create_session_factory(engine)
        with Session() as s:
            # ---------------------------------------------------- projects
            check("0a. a project needs a name", refused(service.create_project, s, name="  ") is not None)
            p = service.create_project(s, name="Apertura")
            other = service.create_project(s, name="Secondo locale")
            service.rename_project(s, other.id, name="Secondo locale (Orlando)")
            check("0b. a project can be renamed", s.get(m.Project, other.id).name == "Secondo locale (Orlando)")
            P = p.id

            # ---------------------------------------------------- chapters
            check("1. a chapter needs a title", refused(service.create_chapter, s, P, title="  ", description=None) is not None)
            c1 = service.create_chapter(s, P, title="Apertura", description="Fase 1")
            c2 = service.create_chapter(s, P, title="Menu", description=None)
            check("1b. a chapter created inside a project belongs to it", c1.project_id == P and c2.project_id == P)

            # ---------------------------------------------------- fields and planned end
            a = service.create_task(s, P, task_input("A", chapter_id=c1.id, start=date(2026, 3, 1), days=3, percent=40, actual=2))
            check("2. planned end = start + planned days − 1", service.planned_end(date(2026, 3, 1), 3) == date(2026, 3, 3))
            check("3. one planned day ends the day it starts", service.planned_end(date(2026, 3, 1), 1) == date(2026, 3, 1))
            for label, kwargs in [("percent 101", {"percent": 101}), ("percent −1", {"percent": -1}),
                                  ("planned days 0", {"days": 0}), ("actual days −1", {"actual": -1})]:
                check(f"4. refused: {label}", refused(service.create_task, s, P, task_input("X", chapter_id=c1.id, **kwargs)) is not None)
            zero = service.create_task(s, P, task_input("Zero", chapter_id=c1.id, actual=0, percent=100))
            check("5. actual days may be zero, empty or positive; percent 100 accepted",
                  zero.actual_duration_days == 0 and a.actual_duration_days == 2
                  and service.create_task(s, P, task_input("Empty", chapter_id=c1.id)).actual_duration_days is None)
            check("6. a task needs an existing chapter of the project",
                  refused(service.create_task, s, P, task_input("X", chapter_id=None)) is not None
                  and refused(service.create_task, s, P, task_input("X", chapter_id=9999)) is not None)

            # ---------------------------------------------------- hierarchy
            child = service.create_task(s, P, task_input("A.1", chapter_id=c2.id, parent_task_id=a.id))
            check("7. a child is placed in its parent's chapter, whatever chapter was submitted", child.chapter_id == c1.id)
            check("8. a second level of children is refused",
                  refused(service.create_task, s, P, task_input("A.1.1", parent_task_id=child.id)) is not None)
            b = service.create_task(s, P, task_input("B", chapter_id=c1.id, start=date(2026, 3, 3), days=2))
            message = refused(service.update_task, s, P, a.id, task_input("A", parent_task_id=b.id, days=3))
            check("9. a task with children cannot become a child", message is not None and "subtasks" in message, message or "")
            check("10. a task cannot be its own parent",
                  refused(service.update_task, s, P, b.id, task_input("B", parent_task_id=b.id)) is not None)
            service.update_task(s, P, a.id, task_input("A", chapter_id=c2.id, start=date(2026, 3, 1), days=3, percent=40, actual=2))
            check("11. moving a parent to another chapter moves its children", s.get(m.ProjectTask, child.id).chapter_id == c2.id)
            service.update_task(s, P, a.id, task_input("A", chapter_id=c1.id, start=date(2026, 3, 1), days=3, percent=40, actual=2))

            # ---------------------------------------------------- prerequisites
            check("12. a task cannot be its own prerequisite",
                  refused(service.update_task, s, P, b.id, task_input("B", chapter_id=c1.id, predecessors=[b.id])) is not None)
            c_task = service.create_task(s, P, task_input("C", chapter_id=c2.id, start=date(2026, 3, 10), days=2,
                                                          predecessors=[b.id]))
            check("13. prerequisites may cross chapters of the same project",
                  s.scalar(select(m.ProjectTaskDependency).where(m.ProjectTaskDependency.successor_task_id == c_task.id)) is not None)
            service.update_task(s, P, b.id, task_input("B", chapter_id=c1.id, start=date(2026, 3, 3), days=2, predecessors=[a.id]))
            message = refused(service.update_task, s, P, a.id, task_input("A", chapter_id=c1.id, days=3, predecessors=[c_task.id]))
            check("14. a circular prerequisite (A → B → C → A) is refused, naming the chain",
                  message is not None and "Circular" in message and "“C”" in message, message or "")
            check("15. a missing prerequisite is refused",
                  refused(service.update_task, s, P, b.id, task_input("B", chapter_id=c1.id, predecessors=[9999])) is not None)

            # ---------------------------------------------------- isolation between projects
            oc = service.create_chapter(s, other.id, title="Cantiere", description=None)
            ot = service.create_task(s, other.id, task_input("Ricerca immobile", chapter_id=oc.id))
            message = refused(service.create_task, s, P, task_input("X", chapter_id=c1.id, predecessors=[ot.id]))
            check("P1. a prerequisite from another project is refused, naming it",
                  message is not None and "same project" in message and "Secondo locale (Orlando)" in message, message or "")
            check("P2. ... also when editing a task",
                  refused(service.update_task, s, P, b.id, task_input("B", chapter_id=c1.id, predecessors=[a.id, ot.id])) is not None)
            check("P3. a chapter of another project cannot be chosen for a task",
                  refused(service.create_task, s, P, task_input("X", chapter_id=oc.id)) is not None
                  and refused(service.update_task, s, P, b.id, task_input("B", chapter_id=oc.id)) is not None)
            check("P4. a parent from another project cannot be chosen",
                  refused(service.create_task, s, P, task_input("X", parent_task_id=ot.id)) is not None)
            check("P5. a task or chapter of another project is out of scope (404), never changed",
                  out_of_scope(service.update_task, s, P, ot.id, task_input("Hack", chapter_id=c1.id))
                  and out_of_scope(service.delete_task, s, P, ot.id)
                  and out_of_scope(service.update_chapter, s, P, oc.id, title="Hack", description=None)
                  and out_of_scope(service.delete_chapter, s, P, oc.id)
                  and s.get(m.ProjectTask, ot.id).title == "Ricerca immobile")
            other_plan = service.build_plan(s, other.id)
            check("P6. a project's plan holds only its own chapters and tasks, coded from 1",
                  [c.title for c in other_plan.chapters] == ["Cantiere"]
                  and [(t.code, t.title) for t in other_plan.tasks] == [("1.1", "Ricerca immobile")]
                  and other_plan.project_name == "Secondo locale (Orlando)")
            summaries = {x.name: x for x in service.list_projects(s)}
            check("P7. the projects list counts each project's own chapters and tasks",
                  summaries["Apertura"].chapter_count == 2 and summaries["Apertura"].task_count == 6
                  and summaries["Secondo locale (Orlando)"].chapter_count == 1
                  and summaries["Secondo locale (Orlando)"].task_count == 1, str(summaries))
            check("P8. a project with chapters cannot be deleted", refused(service.delete_project, s, other.id) is not None)

            # ---------------------------------------------------- warnings and the plan
            plan = service.build_plan(s, P)
            by_title = {t.title: t for t in plan.tasks}
            check("P9. the opened project's plan does not contain the other project's task", "Ricerca immobile" not in by_title)
            check("16. starts ON the prerequisite's planned end → warning (B starts 03/03, A ends 03/03)",
                  len(by_title["B"].warnings) == 1 and by_title["B"].conflicting_predecessors[0].title == "A")
            check("17. starts after the prerequisite's planned end → no warning (C starts 10/03, B ends 04/03)",
                  by_title["C"].warnings == [])
            service.update_task(s, P, c_task.id, task_input("C", chapter_id=c2.id, start=date(2026, 3, 2), days=2,
                                                            predecessors=[b.id]))
            plan = service.build_plan(s, P)
            by_title = {t.title: t for t in plan.tasks}
            check("18. starts before → warning, and nothing is rescheduled",
                  len(by_title["C"].warnings) == 1 and by_title["C"].planned_start_date == date(2026, 3, 2))
            check("19. codes follow the display order (1, 1.1, 1.1.1, 2.1)",
                  [c.code for c in plan.chapters] == ["1", "2"] and by_title["A"].code == "1.1"
                  and by_title["A.1"].code == "1.1.1" and by_title["C"].code == "2.1", str([(t.code, t.title) for t in plan.tasks]))
            check("20. a parent's percentage is never derived from its children", by_title["A"].percent_complete == 40)
            check("21. chapter span = earliest start to latest planned end",
                  plan.chapters[0].start == date(2026, 3, 1) and plan.chapters[0].end == date(2026, 3, 4))

            # ---------------------------------------------------- deletion
            check("22. a task with children cannot be deleted", refused(service.delete_task, s, P, a.id) is not None)
            check("23. a chapter with tasks cannot be deleted", refused(service.delete_chapter, s, P, c1.id) is not None)
            service.delete_task(s, P, b.id)
            check("24. deleting a task removes its prerequisite links in both directions",
                  s.scalar(select(m.ProjectTaskDependency).where(
                      (m.ProjectTaskDependency.predecessor_task_id == b.id) | (m.ProjectTaskDependency.successor_task_id == b.id)
                  )) is None)
            empty = service.create_project(s, name="Vuoto")
            service.delete_project(s, empty.id)
            check("24b. an empty project can be deleted", s.get(m.Project, empty.id) is None)

            # ---------------------------------------------------- responsibles
            def names(project_id):
                return [r.name for r in service.list_responsibles(s, project_id)]

            mario = service.create_responsible(s, P, name="  Mario Rossi  ")
            check("R1. a name is stored trimmed in its project's list", names(P) == ["Mario Rossi"] and mario.project_id == P)
            for label, typed in (("same case", "Mario Rossi"), ("other case + spaces", " mario ROSSI ")):
                message = refused(service.create_responsible, s, P, name=typed)
                check(f"R2. duplicate refused ({label})", message is not None and "already" in message, message or "")
            check("R3. a blank name is refused", refused(service.create_responsible, s, P, name="   ") is not None)
            anna = service.create_responsible(s, P, name="Anna")
            check("R4. rename to a name already in the list is refused (case ignored)",
                  refused(service.rename_responsible, s, P, anna.id, name=" MARIO rossi") is not None)
            service.rename_responsible(s, P, mario.id, name="mario rossi")
            check("R5. renaming a name to another case of itself is allowed", names(P) == ["Anna", "mario rossi"])
            service.rename_responsible(s, P, mario.id, name="Mario Rossi")

            d = service.create_task(s, P, task_input("D", chapter_id=c1.id, responsible="mario ROSSI "))
            check("R6. a typed name matching the list assigns the existing entry, no duplicate",
                  d.responsible_id == mario.id and names(P) == ["Anna", "Mario Rossi"])
            e = service.create_task(s, P, task_input("E", chapter_id=c1.id, responsible="Luca Bianchi"))
            luca = [r for r in service.list_responsibles(s, P) if r.name == "Luca Bianchi"]
            check("R7. a new typed name is added to the project's list and assigned",
                  len(luca) == 1 and e.responsible_id == luca[0].id)
            sub = service.create_task(s, P, task_input("D.1", parent_task_id=d.id, responsible="Anna"))
            check("R8. a subtask may have a different responsible from its parent",
                  sub.responsible_id == anna.id and d.responsible_id == mario.id)
            check("R9. the responsible is optional", service.create_task(s, P, task_input("F", chapter_id=c1.id)).responsible_id is None)

            service.rename_responsible(s, P, mario.id, name="Mario R.")
            plan = service.build_plan(s, P)
            by_title = {t.title: t for t in plan.tasks}
            check("R10. a rename shows everywhere the name is read (plan)",
                  by_title["D"].responsible_name == "Mario R." and by_title["D.1"].responsible_name == "Anna"
                  and "Mario R." in [r.name for r in plan.responsibles])
            message = refused(service.delete_responsible, s, P, mario.id)
            check("R11. a name assigned to a task cannot be deleted: reassign first",
                  message is not None and "assign" in message and s.get(m.ProjectResponsible, mario.id) is not None, message or "")
            service.update_task(s, P, d.id, task_input("D", chapter_id=c1.id, responsible="Anna"))
            service.delete_responsible(s, P, mario.id)
            check("R12. after reassignment it can be deleted",
                  s.get(m.ProjectResponsible, mario.id) is None and s.get(m.ProjectTask, d.id).responsible_id == anna.id)
            service.update_task(s, P, e.id, task_input("E", chapter_id=c1.id, responsible=""))
            check("R13. clearing the field leaves the task without a responsible", s.get(m.ProjectTask, e.id).responsible_id is None)

            # isolation
            other_anna = service.create_responsible(s, other.id, name="Anna")
            check("R14. the same name in another project is a separate entry",
                  other_anna.id != anna.id and names(other.id) == ["Anna"])
            service.create_responsible(s, other.id, name="Solo Orlando")
            g = service.create_task(s, P, task_input("G", chapter_id=c1.id, responsible="Solo Orlando"))
            check("R15. a name of another project is never assigned: the task gets its own project's entry",
                  s.get(m.ProjectResponsible, g.responsible_id).project_id == P
                  and names(other.id) == ["Anna", "Solo Orlando"])
            check("R16. another project's name is out of scope (404) for rename and delete",
                  out_of_scope(service.rename_responsible, s, P, other_anna.id, name="X")
                  and out_of_scope(service.delete_responsible, s, P, other_anna.id)
                  and s.get(m.ProjectResponsible, other_anna.id).name == "Anna")
            check("R17. the projects list carries each project's own names with task counts",
                  {x.name: [(r.name, r.task_count) for r in x.responsibles] for x in service.list_projects(s)}["Apertura"]
                  == [("Anna", 2), ("Luca Bianchi", 0), ("Solo Orlando", 1)])
            emptied = service.create_project(s, name="Con nomi")
            service.create_responsible(s, emptied.id, name="Temporaneo")
            service.delete_project(s, emptied.id)
            check("R18. deleting an empty project also removes its list",
                  s.scalar(select(m.ProjectResponsible).where(m.ProjectResponsible.project_id == emptied.id)) is None)
            s.rollback()

        # ---------------------------------------------------- database constraints
        def violates(values: dict, table=m.ProjectTask) -> bool:
            with Session() as s:
                project = service.create_project(s, name="K")
                chapter = service.create_chapter(s, project.id, title="K", description=None)
                row = {"chapter_id": chapter.id, "title": "T", "percent_complete": 0,
                       "planned_start_date": date(2026, 1, 1), "planned_duration_days": 1}
                row.update(values)
                try:
                    if table is m.ProjectTask:
                        s.execute(insert(m.ProjectTask).values(**row))
                    elif table is m.ProjectChapter:
                        s.execute(insert(m.ProjectChapter).values(title="Orfano", project_id=None))
                    else:
                        task = service.create_task(s, project.id, task_input("T", chapter_id=chapter.id))
                        s.execute(insert(m.ProjectTaskDependency).values(predecessor_task_id=task.id, successor_task_id=task.id))
                    s.flush()
                    return False
                except IntegrityError:
                    return True
                finally:
                    s.rollback()

        check("25. the database refuses percent 150", violates({"percent_complete": 150}))
        check("26. the database refuses planned days 0", violates({"planned_duration_days": 0}))
        check("27. the database refuses negative actual days", violates({"actual_duration_days": -1}))
        check("28. the database refuses a task depending on itself", violates({}, table=m.ProjectTaskDependency))
        check("28b. the database refuses a chapter without a project", violates({}, table=m.ProjectChapter))

        # ---------------------------------------------------- Gantt geometry
        with Session() as s:
            def plan_of(*spans):
                s.rollback()
                project = service.create_project(s, name="G")
                chapter = service.create_chapter(s, project.id, title="G", description=None)
                for i, (start, days) in enumerate(spans):
                    service.create_task(s, project.id, task_input(f"G{i}", chapter_id=chapter.id, start=start, days=days))
                return service.build_plan(s, project.id)

            week = timeline_for(plan_of((date(2026, 3, 4), 10), (date(2026, 3, 10), 20)))
            check("29. up to ~2 months the scale is weeks", week.unit == "week" and week.days == 26)
            month = timeline_for(plan_of((date(2026, 1, 15), 30), (date(2026, 6, 1), 60)))
            check("30. up to ~18 months the scale is months", month.unit == "month" and month.segments[0].label == "Jan 26")
            long_plan = plan_of((date(2026, 1, 1), 30), (date(2027, 6, 1), 400))
            quarter = timeline_for(long_plan)
            check("31. a long period (> 18 months) uses quarters", quarter.unit == "quarter" and quarter.segments[0].label == "Q1 2026")
            for name, tl in (("week", week), ("month", month), ("quarter", quarter)):
                total = sum(seg.width for seg in tl.segments)
                check(f"32. {name}: the scale covers exactly 100% of the timeline", abs(total - 100) < 0.01, f"{total}")
            bar = quarter.task_bar(long_plan.tasks[-1])
            check("33. the last bar ends exactly at 100% (nothing cut)", abs(bar.left + bar.width - 100) < 0.01)
            check("34. a bar near the right edge puts its label before it", bar.label == "before")
            first = quarter.task_bar(long_plan.tasks[0])
            check("35. the first bar starts at 0% with its label after it", first.left == 0 and first.label == "after")
            whole = quarter.bar(quarter.start, quarter.end)
            check("35b. a bar spanning the whole plan keeps its label inside (never over the % column)",
                  whole.label == "inside" and whole.end == 100)
            s.rollback()
            check("36. an empty plan has no timeline", timeline_for(service.Plan(chapters=[])) is None)

        # ---------------------------------------------------- migrations
        from alembic import command
        from alembic.config import Config
        here = Path(__file__).resolve().parent
        cfg = Config(str(here / "alembic.ini"))
        cfg.set_main_option("script_location", str(here / "migrations"))
        os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = url
        try:
            engine.dispose()

            def tables():
                with engine.connect() as conn:
                    return {t for t in ("project", "project_chapter", "project_task", "project_task_dependency")
                            if engine.dialect.has_table(conn, t)}

            # A new database (production RDS): the four tables are created, no project.
            command.downgrade(cfg, BEFORE_PM)
            check("37. downgrade below Project Management drops the four tables", tables() == set())
            command.upgrade(cfg, MAIN_PM)
            with engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM project")).scalar()
            check("38. a new database gets the four tables and no project (the list starts empty)",
                  tables() == {"project", "project_chapter", "project_task", "project_task_dependency"} and count == 0)
            command.upgrade(cfg, RESPONSIBLE)
            with engine.connect() as conn:
                ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE name = 'project_task'")).scalar() \
                    if engine.dialect.name == "sqlite" else None
                has_list = engine.dialect.has_table(conn, "project_responsible")
            check("38b. the Responsible revision adds the list and the column, keeping project_task's constraints",
                  has_list and (ddl is None or ("responsible_id" in ddl and "BETWEEN 0 AND 100" in ddl
                                                and "ck_project_task_not_own_parent" in ddl)), ddl or "")

            # A database from the Bank line with e3a7c5f9b1d4 only: chapters without projects, with data.
            command.downgrade(cfg, BEFORE_PM)
            with engine.begin() as conn:
                for ddl in E3A7_SCHEMA:
                    conn.execute(text(ddl))
                conn.execute(text("INSERT INTO project_chapter (id, title, sort_order) VALUES (1, 'Lavori', 1), (2, 'Menu', 2)"))
                conn.execute(text(
                    "INSERT INTO project_task (id, chapter_id, title, percent_complete, planned_start_date, "
                    "planned_duration_days, sort_order) VALUES (1, 1, 'Permessi', 50, '2026-11-02', 10, 1), "
                    "(2, 2, 'Carta vini', 0, '2026-12-01', 7, 2)"))
                conn.execute(text("INSERT INTO project_task_dependency (predecessor_task_id, successor_task_id) VALUES (1, 2)"))
            command.upgrade(cfg, MAIN_PM)
            with engine.connect() as conn:
                projects = conn.execute(text("SELECT id, name FROM project")).fetchall()
                linked = conn.execute(text("SELECT DISTINCT project_id FROM project_chapter")).fetchall()
                kept = (conn.execute(text("SELECT COUNT(*) FROM project_task")).scalar(),
                        conn.execute(text("SELECT predecessor_task_id, successor_task_id FROM project_task_dependency")).fetchall())
            check("39. chapters without projects are linked to one initial project «Progetto da rinominare»",
                  len(projects) == 1 and projects[0][1] == "Progetto da rinominare" and linked == [(projects[0][0],)], str(projects))
            check("40. tasks and prerequisites are kept, inside that project", kept == (2, [(1, 2)]), str(kept))
            command.upgrade(cfg, RESPONSIBLE)  # the code reads the current schema
            with Session() as s:
                plan = service.build_plan(s, projects[0][0])
                service.rename_project(s, projects[0][0], name="Apertura Winter Park")
                s.commit()
                check("41. the initial project shows its data and can be renamed",
                      [t.title for t in plan.tasks] == ["Permessi", "Carta vini"]
                      and plan.tasks[1].predecessors[0].title == "Permessi"
                      and s.get(m.Project, projects[0][0]).name == "Apertura Winter Park")
            command.downgrade(cfg, MAIN_PM)
            with engine.connect() as conn:
                gone = not engine.dialect.has_table(conn, "project_responsible")
                rows_kept = conn.execute(text("SELECT COUNT(*) FROM project_task")).scalar()
            check("41b. downgrading the Responsible revision removes only the list and the column", gone and rows_kept == 2)

            # A database from the Bank line with both revisions (the local 5080 database): nothing changes.
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM alembic_version"))
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": BEFORE_PM})
                before = [conn.execute(text(f"SELECT * FROM {t} ORDER BY 1")).fetchall()
                          for t in ("project", "project_chapter", "project_task", "project_task_dependency")]
            command.upgrade(cfg, MAIN_PM)
            with engine.connect() as conn:
                after = [conn.execute(text(f"SELECT * FROM {t} ORDER BY 1")).fetchall()
                         for t in ("project", "project_chapter", "project_task", "project_task_dependency")]
            check("42. tables already complete (Bank line): the revision changes nothing", before == after and before[0])

            command.upgrade(cfg, "head")
            with engine.connect() as conn:
                after_responsible = [conn.execute(text(f"SELECT * FROM {t} ORDER BY 1")).fetchall()
                                     for t in ("project", "project_chapter", "project_task_dependency")]
                task_rows = conn.execute(text("SELECT id, title, responsible_id FROM project_task ORDER BY id")).fetchall()
            check("44. the Responsible revision keeps every existing row, tasks start without a responsible",
                  after_responsible == [after[0], after[1], after[3]]
                  and [(r[0], r[1]) for r in task_rows] == [(r[0], r[3]) for r in after[2]]  # id, title
                  and all(r[2] is None for r in task_rows), str(task_rows))
            from alembic.script import ScriptDirectory
            heads = ScriptDirectory.from_config(cfg).get_heads()
            check("43. one single head after Project Management", heads == [RESPONSIBLE] , str(heads))
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    print(f"\nProject Management service: {len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
