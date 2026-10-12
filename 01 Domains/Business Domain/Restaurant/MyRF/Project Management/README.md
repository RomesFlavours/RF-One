# MyRF — Project Management (v1, minimal)

**Status:** v1 approved by the Product Owner (2026-10-12). Implemented in RF-One Web. Project level added the same
day (Product Owner request, 2026-10-12).
**Module:** MyRF / Project Management.
**Access code:** `PROJECTS`.
**Language:** the interface is in Italian. This document, the code and the database are in English.

---

## 1. Purpose

MyRF's general model includes managing business activities as projects (see the MyRF Server Tablet README).
This module is the first, minimal tool for that. A person can:

- keep separate **Projects**, each with its own plan;
- break a Project into **Chapters**, **Tasks** and **child activities**;
- record the plan (start, duration) and the progress (percentage, actual days) **by hand**;
- record which tasks must finish first (**prerequisites**);
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
   - a Task can be deleted only when it has no child activities.

   Deleting a Task also removes its prerequisite links, in both directions.

---

## 5. Pages

| Page | Path | What it does |
|---|---|---|
| Projects | `/projects` | The list of Projects, with their number of Chapters and Tasks and their planned period. Create a Project, rename it, delete an empty one, open one. |
| Plan | `/projects/<id>` | The opened Project: tree of its Chapters → Tasks → child activities, each with dates, days, percentage, prerequisites and warnings. Create and edit Chapters, Tasks and child activities in dialogs. |
| Gantt | `/projects/<id>/gantt` | Read-only Gantt of the opened Project. Chapters and parent Tasks can be collapsed and expanded on screen. |

The opened Project's name is in the page title, in the heading and in the path. Every list and choice on these pages
— Chapters, Tasks, parents, prerequisites — shows only that Project's data.

**Numbering.** Each row has a code: Chapter `1`, Task `1.2`, child activity `1.2.1`. Codes follow the display order
and are not stored. Prerequisites are shown by code and title.

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

**Print.** The **Stampa** button opens the browser's print dialog, which also offers "Save as PDF". The print:

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
- after Save or Cancel in a dialog the person is back on the same row (§5);
- a refusal keeps the dialog open, with the values entered and the reason.

---

## 6. Access

The Home page shows a **Project Management** card to accounts holding the `PROJECTS` access. An administrator grants
it account by account, on the existing access screen (Settings › Accounts › Access). Every page and every action
checks the access on the server, not only the Home link.

---

## 7. Data (technical)

Three tables were added by Alembic revision `e3a7c5f9b1d4`. Revision `f5b8d2a4c6e1` added `project` and
`project_chapter.project_id`:

| Table | Content |
|---|---|
| `project` | id, name, sort_order, created_at, updated_at |
| `project_chapter` | id, project_id → `project` (required), title, description, sort_order, created_at, updated_at |
| `project_task` | id, chapter_id → `project_chapter`, parent_task_id → `project_task` (nullable), title, description, percent_complete (0–100), planned_start_date, planned_duration_days (≥ 1), actual_duration_days (null or ≥ 0), sort_order, created_at, updated_at |
| `project_task_dependency` | predecessor_task_id → `project_task`, successor_task_id → `project_task`; both together are the primary key; a CHECK forbids a task depending on itself |

The database itself enforces:

- the value ranges;
- that a task is neither its own parent nor its own prerequisite;
- that a Chapter or a parent Task cannot be deleted while something still points to it.

The application (`rfone_data_store/projects/service.py`) enforces the rest of §4:

- same Chapter as the parent, one level;
- no cycles;
- prerequisites and Chapter changes only within the Task's Project.

**Migration `f5b8d2a4c6e1` and existing data.** Every row already entered is kept:

- if Chapters exist, they are all linked to one initial Project named **"Progetto da rinominare"**, which can be
  renamed from the Projects page;
- their Tasks and prerequisites stay as they were, so they all fall within that Project;
- if no Chapter exists, no Project is created and the list starts empty.

The table names are singular, as approved for this module. This differs from the plural convention stated in
`rfone_data_store/models.py`.

| Code | Where |
|---|---|
| Models | `rfone_data_store/models.py` (`Project`, `ProjectChapter`, `ProjectTask`, `ProjectTaskDependency`) |
| Rules and plan building | `rfone_data_store/projects/service.py` |
| Routes | `03 Software/RF-One Web/projects_routes.py` |
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
- No manual reordering: rows follow the order in which they were created.
- No assignee, no history of changes.
