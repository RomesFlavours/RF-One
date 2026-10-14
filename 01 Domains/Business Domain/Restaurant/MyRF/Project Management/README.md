# MyRF — Project Management (v1, minimal)

**Status:** v1 approved by the Product Owner (2026-10-12). Implemented in RF-One Web. Project level added the same
day (Product Owner request, 2026-10-12). Task Responsible added on 2026-10-12 (Product Owner request, §3–§5).
Bold parent Tasks and ↑ / ↓ reordering added on 2026-10-14 (Product Owner request, §4 rule 8, §5).
**Module:** MyRF / Project Management.
**Access code:** `PROJECTS`.
**Language:** the interface, this document, the code and the database are in English. Saved content (project names, chapter titles, task descriptions) is shown as entered.

---

## 1. Purpose

MyRF's general model includes managing business activities as projects (see the MyRF Server Tablet README).
This module is the first, minimal tool for that. A person can:

- keep separate **Projects**, each with its own plan;
- break a Project into **Chapters**, **Tasks** and **child activities**;
- record the plan (start, duration) and the progress (percentage, actual days) **by hand**;
- record which tasks must finish first (**prerequisites**);
- name the person **responsible** for each Task, from the Project's own list of names;
- read and print the plan as a **Gantt chart**.

The data is **generic**. Nothing in it is specific to restaurants, and it has no mandatory link to a Legal Entity,
a Restaurant or a Location. It lives under the Restaurant Business Domain only because MyRF does today. If MyRF or
Project Management later becomes a Shared Domain, the tables do not need to change.

A Task here is a unit of planned work. It is **not** the Core concept *Process* (`00 Core/Process.md`), which describes
the knowledge needed to achieve a Goal consistently. The two must not be merged.

---

## 2. Structure

```text
Project
└── Chapter                 (belongs to one Project)
    └── Task                (belongs to one Chapter)
        └── Child activity  (a Task whose parent is a Task of the SAME Chapter)
```

- A **Project** is one plan. Its Chapters, Tasks, prerequisites, Gantt and print never mix with another Project's.
- A Task's Project is **its Chapter's Project**. It is never stored on the Task, so the two can never disagree.
- **One level of child activities.** A child cannot have children of its own, and a Task that has children cannot
  become a child. The data model would allow deeper levels (`parent_task_id`), but the application refuses them
  until they are designed and handled.
- A child activity is a Task in every other respect: it has the same fields, can have prerequisites and can be a
  prerequisite.

---

## 3. Fields

### Project

| Field | Rule |
|---|---|
| Name | required |
| Responsibles | the Project's list of names that can be made responsible for its Tasks (below) |

### Responsible

A name in a Project's list of people who can be responsible for its Tasks.

| Field | Rule |
|---|---|
| Project | required. Set automatically: the list belongs to one Project, and a name never moves to another one. |
| Name | required, at most 200 characters, stored without leading and trailing spaces. Unique within its Project, ignoring upper/lower case and leading/trailing spaces: "Mario Rossi" and " mario rossi " are the same name. |

A Responsible is **only a name**. It is independent of RF-One access accounts and of Employees: it grants no access
and is not linked to any person record. The same name in two Projects is two separate entries.

### Chapter

| Field | Rule |
|---|---|
| Project | required. Set automatically: a Chapter is created from inside its Project, and does not move to another one. |
| Title | required |
| Description | optional |

### Task (and child activity)

| Field | Rule |
|---|---|
| Title | required |
| Description | optional |
| Chapter | required, a Chapter of the same Project. Set automatically when the Task is created from a Chapter. For a child it is always the parent's Chapter. |
| Parent task | optional. Only a Task with no parent can be chosen (one level). |
| Completion percentage | whole number from 0 to 100, entered by hand |
| Planned start date | required, a calendar date |
| Planned days | whole number, at least 1, calendar days |
| Actual days | empty, or a whole number of 0 or more, entered by hand |
| Prerequisites | zero or more other Tasks of the same Project, from any of its Chapters |
| Responsible | optional for now, at most one. A name from the same Project's list. A child activity may have a different Responsible from its parent. Tasks that existed before this field have none until one is assigned. |

**Planned end** = planned start + planned days − 1, in calendar days. It is computed for display, never stored.
Example: start 1 March, 3 planned days → planned end 3 March.

---

## 4. Rules

1. **Calendar days only.** v1 has no working calendar: weekends and holidays count.
2. **Everything is manual.** v1 does not:
   - reschedule anything: a prerequisite running late moves no date;
   - derive a parent's percentage from its children;
   - derive actual days from dates.
3. **Hierarchy:**
   - a child must be in the same Chapter as its parent;
   - a Task cannot be its own parent;
   - circular hierarchies are refused;
   - deeper levels are refused (§2).

   Moving a parent Task to another Chapter of the same Project moves its children with it. A Task never moves to
   another Project.
4. **Prerequisites:**
   - a Task cannot be its own prerequisite;
   - circular prerequisites are refused. Example: A needs B, B needs C, C needs A.
   - prerequisites may cross Chapters, **only within the same Project**: a prerequisite from another Project is
     refused.

   A prerequisite means "should finish before this starts" (finish-to-start). It is informational: nothing is
   moved automatically.
5. **Warning, not a block.** A Task whose planned start is **on or before** the planned end of one of its
   prerequisites is shown with a warning, in the list, in the Gantt and in print. It is still saved: v1 never
   reschedules.
6. **Deletion:**
   - a Project can be deleted only when it has no Chapters;
   - a Chapter can be deleted only when it has no Tasks;
   - a Task can be deleted only when it has no child activities;
   - a Responsible can be deleted only when no Task has it: its Tasks must first be reassigned (or left without a
     Responsible).

   Deleting a Task also removes its prerequisite links, in both directions. Deleting an empty Project also removes
   its list of Responsibles.
7. **Responsibles:**
   - a Task can only have a Responsible of its own Project;
   - a name is never duplicated within a Project (case and leading/trailing spaces ignored), neither when it is added
     or renamed in the list nor when it is typed in a Task;
   - renaming a Responsible changes it everywhere it is shown, because Tasks point to the entry, not to its text.
8. **Order (↑ / ↓):**
   - a Task moves one place among the Tasks of its own Chapter; a child activity moves one place among the children
     of its own parent;
   - moving a parent Task moves its children with it (they are always listed under it);
   - a move changes only the order: never the Chapter, the parent, the dates, the Responsible or the prerequisites;
   - the first of a group cannot move up and the last cannot move down;
   - the order is saved in the database (`project_task.sort_order`), so it is the same after a refresh, in the Plan,
     in the Gantt and in their print.

---

## 5. Pages

| Page | Path | What it does |
|---|---|---|
| Projects | `/projects` | The list of Projects, with their number of Chapters and Tasks and their planned period. Create a Project, rename it, delete an empty one, open one, manage its Responsibles. |
| Plan | `/projects/<id>` | The opened Project: tree of its Chapters → Tasks → child activities, each with its Responsible, dates, days, percentage, prerequisites and warnings. Create and edit Chapters, Tasks and child activities in dialogs. |
| Gantt | `/projects/<id>/gantt` | Read-only Gantt of the opened Project, with each Task's Responsible. Chapters and parent Tasks can be collapsed and expanded on screen. |

**Responsibles list.** In the Actions column of the Projects list, a person icon (tooltip "Responsible") opens a
dialog with that Project's names. There a name can be added, renamed or deleted. Each name shows how many Tasks it is
assigned to. Deleting a name still assigned is refused with a message asking to reassign its Tasks first.

**Responsible in the Task dialog.** The Task and child-activity dialogs have a **Responsible** field: a searchable
box listing the Project's names. The person either picks an existing name or types a new one; a new name is added to
the Project's list and assigned to the Task when the Task is saved, in the same step. A typed name equal to an
existing one (case and leading/trailing spaces ignored) assigns the existing entry instead of creating a duplicate.
An empty field leaves the Task without a Responsible.

**Responsible on display.** The Responsible's name is shown in the Plan's task rows, in the Gantt and in its print,
in its own column; a Task without one shows "—".

The opened Project's name is in the page title, in the heading and in the path. Every list and choice on these pages
— Chapters, Tasks, parents, prerequisites — shows only that Project's data.

**Numbering.** Each row has a code: Chapter `1`, Task `1.2`, child activity `1.2.1`. Codes follow the display order
and are not stored, so after a move they are renumbered while ids and prerequisite links stay the same. Prerequisites
are shown by code and title, always with the current code.

**Tasks with child activities.** A Task with at least one child activity shows its code and title in **bold**, in the
Plan, in the Gantt and in their print. Its description stays in normal type.

**Reordering.** At the far right of the Actions column of every Task and child-activity row there are two compact
buttons, ↑ (tooltip "Move up") and ↓ (tooltip "Move down"), following rule 8 of §4. ↑ is disabled on the first row of
its group and ↓ on the last. While a move is being saved, every arrow is disabled and the clicked one shows "…", so a
repeated click sends nothing. After the save the page reloads with the moved row at the same place on the screen
(row return, below). A move past the edge of a group, sent anyway, is refused with a message and changes nothing.

**Gantt rows:**

- **Chapter:** its span (earliest planned start to latest planned end of its Tasks) as a thin neutral bar. A Chapter
  has no percentage of its own.
- **Task and child activity:** one bar for the planned period, filled inside up to the completion percentage, with
  the percentage written next to it.
- **Actual days** are shown as a **number** in their own column, never as a second bar: v1 has no actual start date,
  so there is nothing to place such a bar on.

**Timeline scale.** The timeline always covers the whole plan, from the earliest planned start to the latest
planned end, and fits the available width. Its scale adapts:

| Plan length | Scale |
|---|---|
| up to about 2 months | weeks |
| up to about 18 months | months |
| longer | quarters |

**Print.** The **Print** button opens the browser's print dialog, which also offers "Save as PDF". The print:

- is in landscape;
- shows the Project's name in its heading;
- includes **every** Chapter and Task of the Project, also those collapsed on screen;
- hides the menu, the path and every command;
- repeats the column and timeline headings on each page;
- keeps each row whole;
- keeps the bar colours, also when the browser would drop background graphics.

Because the timeline is proportional to the page width, a long period is compressed, never cut.

Navigation follows the RF-One UI Rules (`03 Software/Shared UI/UI Rules.md`):

- the path is `RF-One › Project Management › <Project name> › Gantt` (§4);
- a refusal keeps the dialog open, with the values entered and the reason;
- after Save or Cancel in a dialog, and after ↑ / ↓, the person is back on the same row (§5): each row carries a
  stable `data-rr-key` read by the shared row-return component (`rf-one-row-return.js`).

---

## 6. Access

The Home page shows a **Project Management** card to accounts holding the `PROJECTS` access. An administrator grants
it account by account, on the existing access screen (Settings › Accounts › Access). Every page and every action
checks the access on the server, not only the Home link.

---

## 7. Data (technical)

On `main`, the four tables are created by Alembic revision `d2f6b9a3e7c1`, which revises `b6e4d2a8c1f9`
(Restaurant Wines):

| Table | Content |
|---|---|
| `project` | id, name, sort_order, created_at, updated_at |
| `project_chapter` | id, project_id → `project` (required), title, description, sort_order, created_at, updated_at |
| `project_task` | id, chapter_id → `project_chapter`, parent_task_id → `project_task` (nullable), title, description, percent_complete (0–100), planned_start_date, planned_duration_days (≥ 1), actual_duration_days (null or ≥ 0), sort_order, created_at, updated_at |
| `project_task_dependency` | predecessor_task_id → `project_task`, successor_task_id → `project_task`; both together are the primary key; a CHECK forbids a task depending on itself |
| `project_responsible` | id, project_id → `project` (required), name, name_key (the name trimmed and case-folded; unique together with project_id), created_at, updated_at |

`project_task.responsible_id` → `project_responsible` (nullable) holds the Task's Responsible. Both are added by
Alembic revision `e8c4a2f6b1d3`, which revises `d2f6b9a3e7c1`. It only adds the table and the empty column: no
existing row is changed, so every existing Task starts without a Responsible.

The database itself enforces:

- the value ranges;
- that a task is neither its own parent nor its own prerequisite;
- that a Chapter or a parent Task cannot be deleted while something still points to it.

The application (`rfone_data_store/projects/service.py`) enforces the rest of §4:

- same Chapter as the parent, one level;
- no cycles;
- prerequisites and Chapter changes only within the Task's Project;
- a Responsible only from the Task's Project, and no deletion of a Responsible still assigned (the foreign key also
  prevents it).

**Migrations, existing data and the second line of work.** The module was first built in the Bank worktree
(`feature/bank-simple-who-rules`), where two revisions created the same schema in two steps on the Bank chain:

- `e3a7c5f9b1d4`, after `a1b5c3d7e9f2`, created Chapters, Tasks and prerequisites;
- `f5b8d2a4c6e1`, after `c3d9e1f5a7b2`, added Projects.

Those revisions are applied to the local working database and are **not rewritten**. Their parents are Bank revisions
that are not on `main`, so they cannot be on `main` either. `d2f6b9a3e7c1` therefore creates the final schema
directly, and only what is missing:

| Database | What `d2f6b9a3e7c1` does |
|---|---|
| Without the tables (production RDS, a new database) | Creates the four tables |
| Already holding them, through `e3a7c5f9b1d4` / `f5b8d2a4c6e1` | Nothing |
| Holding Chapters without `project_id`, through `e3a7c5f9b1d4` only | Adds Projects as `f5b8d2a4c6e1` does |

In the last case every row is kept:

- existing Chapters are linked to one initial Project named **"Progetto da rinominare"**, which can be renamed from
  the Projects page;
- their Tasks and prerequisites stay as they were, so they all fall within that Project;
- if no Chapter exists, no Project is created.

**The Bank line merged into `main` (BANK_AWS_001, 2026-10-12):**

- merge revision `7b1d4f9a2c6e` joins the two heads (`a3c7e5b9d1f4` and `e8c4a2f6b1d3`);
- the local database, which already holds the tables, passes through `d2f6b9a3e7c1` without changes;
- a database that came from `main` — production included — already holds the tables when it reaches `e3a7c5f9b1d4`
  and `f5b8d2a4c6e1`: both now skip what exists, so nothing is created twice and no row is touched.

**Order.** ↑ / ↓ reuse `project_task.sort_order`, which already existed: no migration was needed, and the order shown
before the change is the initial one. A new Task gets the next value, so it goes last in its group. A move hands the
group's own values out again in the new order; values shared by older rows are first made strictly increasing
without changing their order.

The table names are singular, as approved for this module. This differs from the plural convention stated in
`rfone_data_store/models.py`.

| Code | Where |
|---|---|
| Models | `rfone_data_store/models.py` (`Project`, `ProjectChapter`, `ProjectTask`, `ProjectTaskDependency`, `ProjectResponsible`) |
| Rules and plan building | `rfone_data_store/projects/service.py` |
| Routes | `03 Software/RF-One Web/projects_routes.py` (↑ / ↓: `POST /projects/<id>/tasks/<task id>/move`, field `direction` = `up` / `down`) |
| Pages | `templates/projects_list.html`, `templates/projects_plan.html`, `templates/projects_gantt.html`, `templates/_projects_macros.html` |
| Style and print | `static/css/rf-one-projects.css` |
| Script | `static/js/rf-one-projects.js` |
| Tests | `RF-One Data Store/test_projects_service.py`, `RF-One Web/tests/test_projects_http.py` |

---

## 8. Not in v1 (known limits)

- No actual start or end date, so no "actual" bar and no variance in dates.
- No working calendar (weekends and holidays count as days).
- No automatic rescheduling, no critical path, no roll-up of percentages or dates to parents and Chapters.
- One level of child activities.
- No link to Legal Entity, Restaurant or Location.
- No prerequisites across Projects, and no moving of Chapters or Tasks between Projects.
- Chapters cannot be reordered; Tasks move one place at a time (↑ / ↓), never to another Chapter or parent.
- One Responsible per Task, optional, as a plain name: no link to accounts or Employees, no notifications.
- No history of changes.
