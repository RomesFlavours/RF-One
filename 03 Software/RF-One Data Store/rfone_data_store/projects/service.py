"""MyRF Project Management v1 — the rules and the plan as read by the pages.

`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md` §4:

* calendar days; planned end = planned start + planned days − 1, never stored;
* percentage and actual days are manual — nothing is derived or rescheduled;
* a child activity is in its parent's Chapter, one level only, no cycles;
* a Chapter belongs to one Project; a Task's Project is its Chapter's;
* prerequisites may cross Chapters within the same Project, never self,
  never circular;
* a Task starting on or before a prerequisite's planned end gets a warning,
  never a refusal.

Every refusal is a `ProjectValidationError` whose message is shown to the
person as it is (Italian, like the pages).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from rfone_data_store import models as m

TITLE_MAX_LENGTH = 200


class ProjectValidationError(ValueError):
    """A change refused by the rules; the message is meant for the person."""


def planned_end(start: date, planned_days: int) -> date:
    """Calendar days: 1 planned day ends the same day it starts."""
    return start + timedelta(days=planned_days - 1)


def format_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


# ---------------------------------------------------------------- input


@dataclass
class TaskInput:
    title: str
    description: str | None
    chapter_id: int | None
    parent_task_id: int | None
    percent_complete: int
    planned_start_date: date
    planned_duration_days: int
    actual_duration_days: int | None
    predecessor_ids: list[int] = field(default_factory=list)


def _text(form: Mapping, name: str) -> str:
    return (form.get(name) or "").strip()


def _whole_number(form: Mapping, name: str, label: str, *, required: bool) -> int | None:
    raw = _text(form, name)
    if not raw:
        if required:
            raise ProjectValidationError(f"{label}: valore obbligatorio.")
        return None
    try:
        return int(raw)
    except ValueError:
        raise ProjectValidationError(f"{label}: inserire un numero intero (ricevuto «{raw}»).") from None


def _optional_id(form: Mapping, name: str) -> int | None:
    raw = _text(form, name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ProjectValidationError("Selezione non valida.") from None


def task_input_from_form(form) -> TaskInput:
    """Reads the task dialog's fields. `form` is a Werkzeug MultiDict (or any
    mapping with `getlist` for the prerequisites)."""
    raw_start = _text(form, "planned_start_date")
    if not raw_start:
        raise ProjectValidationError("Data di inizio prevista: valore obbligatorio.")
    try:
        start = date.fromisoformat(raw_start)
    except ValueError:
        raise ProjectValidationError(f"Data di inizio prevista non valida («{raw_start}»).") from None
    raw_predecessors = form.getlist("predecessor_ids") if hasattr(form, "getlist") else form.get("predecessor_ids", [])
    try:
        predecessor_ids = sorted({int(v) for v in raw_predecessors if str(v).strip()})
    except ValueError:
        raise ProjectValidationError("Selezione delle attività propedeutiche non valida.") from None
    return TaskInput(
        title=_text(form, "title"),
        description=_text(form, "description") or None,
        chapter_id=_optional_id(form, "chapter_id"),
        parent_task_id=_optional_id(form, "parent_task_id"),
        percent_complete=_whole_number(form, "percent_complete", "Percentuale di completamento", required=True),
        planned_start_date=start,
        planned_duration_days=_whole_number(form, "planned_duration_days", "Giorni previsti", required=True),
        actual_duration_days=_whole_number(form, "actual_duration_days", "Giorni effettivi", required=False),
        predecessor_ids=predecessor_ids,
    )


def _clean_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise ProjectValidationError("Il titolo è obbligatorio.")
    if len(title) > TITLE_MAX_LENGTH:
        raise ProjectValidationError(f"Il titolo può avere al massimo {TITLE_MAX_LENGTH} caratteri.")
    return title


# ---------------------------------------------------------------- scope


class ProjectScopeError(LookupError):
    """The requested Project, Chapter or Task does not exist in the opened
    Project — the page answers 404, never another Project's data."""


def _next_sort_order(session: Session, model) -> int:
    return (session.scalar(select(func.max(model.sort_order))) or 0) + 1


def get_project(session: Session, project_id: int) -> m.Project:
    project = session.get(m.Project, project_id)
    if project is None:
        raise ProjectScopeError(project_id)
    return project


def _chapter_in(session: Session, project_id: int, chapter_id: int | None) -> m.ProjectChapter:
    chapter = session.get(m.ProjectChapter, chapter_id) if chapter_id is not None else None
    if chapter is None or chapter.project_id != project_id:
        raise ProjectValidationError("Capitolo non trovato in questo progetto.")
    return chapter


def _project_of_tasks(session: Session, task_ids: Iterable[int]) -> dict[int, int]:
    """task id → its Project (the Project of its Chapter)."""
    ids = list(task_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(m.ProjectTask.id, m.ProjectChapter.project_id)
        .join(m.ProjectChapter, m.ProjectChapter.id == m.ProjectTask.chapter_id)
        .where(m.ProjectTask.id.in_(ids))
    )
    return {task_id: project_id for task_id, project_id in rows}


def _task_in(session: Session, project_id: int, task_id: int) -> m.ProjectTask:
    task = session.get(m.ProjectTask, task_id)
    if task is None or _project_of_tasks(session, [task_id]).get(task_id) != project_id:
        raise ProjectScopeError(task_id)
    return task


def check_chapter_scope(session: Session, project_id: int, chapter_id: int) -> None:
    chapter = session.get(m.ProjectChapter, chapter_id)
    if chapter is None or chapter.project_id != project_id:
        raise ProjectScopeError(chapter_id)


# ---------------------------------------------------------------- projects


@dataclass
class ProjectSummary:
    id: int
    name: str
    chapter_count: int
    task_count: int
    start: date | None
    end: date | None


def list_projects(session: Session) -> list[ProjectSummary]:
    projects = list(session.scalars(select(m.Project).order_by(m.Project.sort_order, m.Project.id)))
    chapters = dict(session.execute(
        select(m.ProjectChapter.project_id, func.count(m.ProjectChapter.id)).group_by(m.ProjectChapter.project_id)
    ).tuples().all())
    tasks: dict[int, list[m.ProjectTask]] = {}
    for task, project_id in session.execute(
        select(m.ProjectTask, m.ProjectChapter.project_id)
        .join(m.ProjectChapter, m.ProjectChapter.id == m.ProjectTask.chapter_id)
    ).tuples():
        tasks.setdefault(project_id, []).append(task)
    summaries = []
    for project in projects:
        rows = tasks.get(project.id, [])
        summaries.append(ProjectSummary(
            id=project.id, name=project.name, chapter_count=chapters.get(project.id, 0), task_count=len(rows),
            start=min((t.planned_start_date for t in rows), default=None),
            end=max((planned_end(t.planned_start_date, t.planned_duration_days) for t in rows), default=None),
        ))
    return summaries


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ProjectValidationError("Il nome del progetto è obbligatorio.")
    if len(name) > TITLE_MAX_LENGTH:
        raise ProjectValidationError(f"Il nome può avere al massimo {TITLE_MAX_LENGTH} caratteri.")
    return name


def create_project(session: Session, *, name: str) -> m.Project:
    project = m.Project(name=_clean_name(name), sort_order=_next_sort_order(session, m.Project))
    session.add(project)
    session.flush()
    return project


def rename_project(session: Session, project_id: int, *, name: str) -> m.Project:
    project = get_project(session, project_id)
    project.name = _clean_name(name)
    session.flush()
    return project


def delete_project(session: Session, project_id: int) -> None:
    project = get_project(session, project_id)
    if session.scalar(select(func.count(m.ProjectChapter.id)).where(m.ProjectChapter.project_id == project.id)):
        raise ProjectValidationError("Il progetto contiene ancora dei capitoli: eliminali prima.")
    session.delete(project)
    session.flush()


# ---------------------------------------------------------------- chapters


def create_chapter(session: Session, project_id: int, *, title: str, description: str | None) -> m.ProjectChapter:
    project = get_project(session, project_id)
    chapter = m.ProjectChapter(
        project_id=project.id, title=_clean_title(title), description=(description or "").strip() or None,
        sort_order=_next_sort_order(session, m.ProjectChapter),
    )
    session.add(chapter)
    session.flush()
    return chapter


def update_chapter(session: Session, project_id: int, chapter_id: int, *, title: str,
                   description: str | None) -> m.ProjectChapter:
    check_chapter_scope(session, project_id, chapter_id)
    chapter = session.get(m.ProjectChapter, chapter_id)
    chapter.title = _clean_title(title)
    chapter.description = (description or "").strip() or None
    session.flush()
    return chapter


def delete_chapter(session: Session, project_id: int, chapter_id: int) -> None:
    check_chapter_scope(session, project_id, chapter_id)
    chapter = session.get(m.ProjectChapter, chapter_id)
    if session.scalar(select(func.count(m.ProjectTask.id)).where(m.ProjectTask.chapter_id == chapter.id)):
        raise ProjectValidationError("Il capitolo contiene ancora dei task: eliminali o spostali prima.")
    session.delete(chapter)
    session.flush()


# ---------------------------------------------------------------- tasks


def _children_ids(session: Session, task_id: int) -> list[int]:
    return list(session.scalars(select(m.ProjectTask.id).where(m.ProjectTask.parent_task_id == task_id)))


def _dependency_edges(session: Session) -> list[tuple[int, int]]:
    rows = session.execute(
        select(m.ProjectTaskDependency.predecessor_task_id, m.ProjectTaskDependency.successor_task_id)
    )
    return [(p, s) for p, s in rows]


def _cycle_path(edges: Iterable[tuple[int, int]], start: int, targets: set[int]) -> list[int] | None:
    """A path start → … → t (following predecessor → successor) reaching any
    of `targets`, or None. Used to refuse a prerequisite that would close a
    cycle: if the task already leads to one of its new prerequisites, adding
    prerequisite → task closes the loop."""
    successors: dict[int, list[int]] = {}
    for p, s in edges:
        successors.setdefault(p, []).append(s)
    stack: list[tuple[int, list[int]]] = [(start, [start])]
    seen = {start}
    while stack:
        node, path = stack.pop()
        for nxt in successors.get(node, []):
            if nxt in targets:
                return path + [nxt]
            if nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, path + [nxt]))
    return None


def _validate_numbers(data: TaskInput) -> None:
    if not 0 <= data.percent_complete <= 100:
        raise ProjectValidationError("La percentuale di completamento deve essere tra 0 e 100.")
    if data.planned_duration_days < 1:
        raise ProjectValidationError("I giorni previsti devono essere almeno 1.")
    if data.actual_duration_days is not None and data.actual_duration_days < 0:
        raise ProjectValidationError("I giorni effettivi possono essere vuoti, zero o positivi.")


def _resolve_chapter_and_parent(session: Session, project_id: int, task: m.ProjectTask | None,
                                data: TaskInput) -> tuple[int, int | None]:
    if data.parent_task_id is None:
        return _chapter_in(session, project_id, data.chapter_id).id, None

    parent = session.get(m.ProjectTask, data.parent_task_id)
    if parent is None or _project_of_tasks(session, [parent.id]).get(parent.id) != project_id:
        raise ProjectValidationError("Task padre non trovato in questo progetto.")
    if task is not None:
        if parent.id == task.id:
            raise ProjectValidationError("Un task non può essere padre di se stesso.")
        # A circular hierarchy: the chosen parent sits below this task.
        ancestor, guard = parent, 0
        while ancestor is not None and guard < 1000:
            if ancestor.id == task.id:
                raise ProjectValidationError("Gerarchia circolare: il task padre scelto dipende già da questo task.")
            ancestor = session.get(m.ProjectTask, ancestor.parent_task_id) if ancestor.parent_task_id else None
            guard += 1
        if _children_ids(session, task.id):
            raise ProjectValidationError(
                "Questo task ha delle attività figlie: non può diventare a sua volta un'attività figlia "
                "(è gestito un solo livello)."
            )
    if parent.parent_task_id is not None:
        raise ProjectValidationError(
            "Il task padre scelto è già un'attività figlia: è gestito un solo livello di attività figlie."
        )
    # A child activity is always in its parent's Chapter.
    return parent.chapter_id, parent.id


def _validate_predecessors(session: Session, project_id: int, task_id: int | None, predecessor_ids: list[int]) -> None:
    if not predecessor_ids:
        return
    if task_id is not None and task_id in predecessor_ids:
        raise ProjectValidationError("Un task non può essere propedeutico a se stesso.")
    projects = _project_of_tasks(session, predecessor_ids)
    if set(projects) != set(predecessor_ids):
        raise ProjectValidationError("Una delle attività propedeutiche scelte non esiste più.")
    outside = [i for i, p in projects.items() if p != project_id]
    if outside:
        rows = session.execute(
            select(m.ProjectTask.title, m.Project.name)
            .join(m.ProjectChapter, m.ProjectChapter.id == m.ProjectTask.chapter_id)
            .join(m.Project, m.Project.id == m.ProjectChapter.project_id)
            .where(m.ProjectTask.id.in_(outside))
        ).first()
        raise ProjectValidationError(
            f"Le attività propedeutiche devono appartenere allo stesso progetto: «{rows[0]}» è nel progetto "
            f"«{rows[1]}»."
        )
    if task_id is None:
        return  # a new task has no successors yet: it cannot close a cycle
    edges = [(p, s) for p, s in _dependency_edges(session) if s != task_id]
    path = _cycle_path(edges, task_id, set(predecessor_ids))
    if path:
        rows = session.execute(select(m.ProjectTask.id, m.ProjectTask.title).where(m.ProjectTask.id.in_(path)))
        titles = {row_id: title for row_id, title in rows}
        chain = " → ".join(f"«{titles.get(i, i)}»" for i in path + [task_id])
        raise ProjectValidationError(f"Dipendenza circolare: {chain}.")


def _set_predecessors(session: Session, task_id: int, predecessor_ids: list[int]) -> None:
    session.execute(delete(m.ProjectTaskDependency).where(m.ProjectTaskDependency.successor_task_id == task_id))
    for predecessor_id in predecessor_ids:
        session.add(m.ProjectTaskDependency(predecessor_task_id=predecessor_id, successor_task_id=task_id))
    session.flush()


def create_task(session: Session, project_id: int, data: TaskInput) -> m.ProjectTask:
    get_project(session, project_id)
    title = _clean_title(data.title)
    _validate_numbers(data)
    chapter_id, parent_id = _resolve_chapter_and_parent(session, project_id, None, data)
    _validate_predecessors(session, project_id, None, data.predecessor_ids)
    task = m.ProjectTask(
        chapter_id=chapter_id, parent_task_id=parent_id, title=title, description=data.description,
        percent_complete=data.percent_complete, planned_start_date=data.planned_start_date,
        planned_duration_days=data.planned_duration_days, actual_duration_days=data.actual_duration_days,
        sort_order=_next_sort_order(session, m.ProjectTask),
    )
    session.add(task)
    session.flush()
    _set_predecessors(session, task.id, data.predecessor_ids)
    return task


def update_task(session: Session, project_id: int, task_id: int, data: TaskInput) -> m.ProjectTask:
    task = _task_in(session, project_id, task_id)
    title = _clean_title(data.title)
    _validate_numbers(data)
    chapter_id, parent_id = _resolve_chapter_and_parent(session, project_id, task, data)
    _validate_predecessors(session, project_id, task.id, data.predecessor_ids)
    if chapter_id != task.chapter_id:
        # Children follow their parent: they are always in its Chapter.
        for child_id in _children_ids(session, task.id):
            session.get(m.ProjectTask, child_id).chapter_id = chapter_id
    task.chapter_id, task.parent_task_id, task.title = chapter_id, parent_id, title
    task.description = data.description
    task.percent_complete = data.percent_complete
    task.planned_start_date = data.planned_start_date
    task.planned_duration_days = data.planned_duration_days
    task.actual_duration_days = data.actual_duration_days
    session.flush()
    _set_predecessors(session, task.id, data.predecessor_ids)
    return task


def delete_task(session: Session, project_id: int, task_id: int) -> None:
    task = _task_in(session, project_id, task_id)
    if _children_ids(session, task.id):
        raise ProjectValidationError("Il task ha delle attività figlie: eliminale prima.")
    session.execute(delete(m.ProjectTaskDependency).where(or_(
        m.ProjectTaskDependency.predecessor_task_id == task.id,
        m.ProjectTaskDependency.successor_task_id == task.id,
    )))
    session.delete(task)
    session.flush()


# ---------------------------------------------------------------- the plan as read


@dataclass(eq=False)  # identity: a task is itself, not its field values
class PlanTask:
    id: int
    code: str
    title: str
    description: str | None
    chapter_id: int
    parent_task_id: int | None
    percent_complete: int
    planned_start_date: date
    planned_duration_days: int
    planned_end_date: date
    actual_duration_days: int | None
    predecessors: list["PlanTask"] = field(default_factory=list)
    # Prerequisites whose planned end is on or after this task's planned
    # start: a warning, never a refusal (nothing is rescheduled).
    conflicting_predecessors: list["PlanTask"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    children: list["PlanTask"] = field(default_factory=list)

    @property
    def is_child(self) -> bool:
        return self.parent_task_id is not None

    @property
    def predecessor_ids(self) -> list[int]:
        return [p.id for p in self.predecessors]


@dataclass(eq=False)  # identity: a task is itself, not its field values
class PlanChapter:
    id: int
    code: str
    title: str
    description: str | None
    tasks: list[PlanTask] = field(default_factory=list)

    @property
    def all_tasks(self) -> list[PlanTask]:
        return [t for task in self.tasks for t in [task, *task.children]]

    @property
    def start(self) -> date | None:
        return min((t.planned_start_date for t in self.all_tasks), default=None)

    @property
    def end(self) -> date | None:
        return max((t.planned_end_date for t in self.all_tasks), default=None)


@dataclass
class Plan:
    chapters: list[PlanChapter]
    project_id: int | None = None
    project_name: str = ""

    @property
    def tasks(self) -> list[PlanTask]:
        return [t for chapter in self.chapters for t in chapter.all_tasks]

    @property
    def start(self) -> date | None:
        return min((c.start for c in self.chapters if c.start), default=None)

    @property
    def end(self) -> date | None:
        return max((c.end for c in self.chapters if c.end), default=None)

    @property
    def warning_count(self) -> int:
        return sum(1 for t in self.tasks if t.warnings)


def build_plan(session: Session, project_id: int) -> Plan:
    """The opened Project only: its Chapters → Tasks → child activities in
    display order, with codes (1, 1.2, 1.2.1), planned ends, prerequisites
    and warnings. Nothing of another Project is read into it."""
    project = get_project(session, project_id)
    chapters = list(session.scalars(
        select(m.ProjectChapter).where(m.ProjectChapter.project_id == project.id)
        .order_by(m.ProjectChapter.sort_order, m.ProjectChapter.id)
    ))
    rows = list(session.scalars(
        select(m.ProjectTask).where(m.ProjectTask.chapter_id.in_([c.id for c in chapters]))
        .order_by(m.ProjectTask.sort_order, m.ProjectTask.id)
    )) if chapters else []

    plan_chapters = [PlanChapter(id=c.id, code=str(i), title=c.title, description=c.description)
                     for i, c in enumerate(chapters, start=1)]
    by_chapter = {c.id: c for c in plan_chapters}
    tasks: dict[int, PlanTask] = {}
    for row in rows:
        tasks[row.id] = PlanTask(
            id=row.id, code="", title=row.title, description=row.description, chapter_id=row.chapter_id,
            parent_task_id=row.parent_task_id, percent_complete=row.percent_complete,
            planned_start_date=row.planned_start_date, planned_duration_days=row.planned_duration_days,
            planned_end_date=planned_end(row.planned_start_date, row.planned_duration_days),
            actual_duration_days=row.actual_duration_days,
        )
    for row in rows:  # rows are in display order, so children keep it too
        task = tasks[row.id]
        if task.parent_task_id is None:
            by_chapter[task.chapter_id].tasks.append(task)
        elif task.parent_task_id in tasks:
            tasks[task.parent_task_id].children.append(task)
    for chapter in plan_chapters:
        for i, task in enumerate(chapter.tasks, start=1):
            task.code = f"{chapter.code}.{i}"
            for j, child in enumerate(task.children, start=1):
                child.code = f"{task.code}.{j}"

    for predecessor_id, successor_id in sorted(_dependency_edges(session)):
        if predecessor_id in tasks and successor_id in tasks:
            tasks[successor_id].predecessors.append(tasks[predecessor_id])
    for task in tasks.values():
        task.predecessors.sort(key=lambda p: [int(x) for x in p.code.split(".")] if p.code else [0])
        for predecessor in task.predecessors:
            if task.planned_start_date <= predecessor.planned_end_date:
                task.conflicting_predecessors.append(predecessor)
                task.warnings.append(
                    f"Inizia il {format_date(task.planned_start_date)}, prima o nello stesso giorno della fine "
                    f"prevista del propedeutico {predecessor.code} «{predecessor.title}» "
                    f"({format_date(predecessor.planned_end_date)})."
                )
    return Plan(chapters=plan_chapters, project_id=project.id, project_name=project.name)
