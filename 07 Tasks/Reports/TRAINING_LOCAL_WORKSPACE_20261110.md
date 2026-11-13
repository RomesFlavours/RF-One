# REPORT — Local Training workspace

## 1. Requested result

Local pages in this order: Assignments, Content, Students. Existing RF-One
olive/white visual identity, Italian controls, contextual modal help on each page.

## 2. Implementation

- Students: create/edit name, email, optional phone and username; set initial/reset
  password; archive/restore with history preserved. Existing RF-One login and
  Training identity are reused. Password replacement is mandatory at first access;
  students may also change username. No credentials are returned in HTML or stored
  in plaintext. Privileged/non-Training accounts cannot be managed by the trainer.
- Content: searchable existing catalog with objectives, versions and question counts.
  Upload remains unimplemented as explicitly deferred by the Product Owner.
- Assignments: explicit selection of students and existing employees, multiple pills,
  goal, confirmation and recent history. Uses canonical Training Need/Assignment
  services. Employee links use IDs; no employee credentials or registry changes.
- Additive local migration `e6f120261109`: profile metadata and unique assignment
  submission tokens, on the existing local database. Existing content is preserved.
- Local-only launcher `RF-One Web/training_local.py` and `Training/Avvia Training.cmd`.
  Management automatically uses the existing local `rfone` trainer; student access
  at `/training/access` retains an explicit credential flow.

## 3. Validation and limits

Rollback-only HTTP tests cover all three pages, Italian navigation/help, CSRF,
student create/edit/archive/restore, first-access username/password replacement,
password reset/session revocation, trainer/student permission boundaries,
multi-recipient assignment, replay rejection and atomic failure. No test records
remain. JavaScript syntax checks pass. Shared help component is byte-identical.

The whole-app How Works check reports 25 pre-existing errors outside the Training
workspace (unregistered unrelated pages and stale registry entries). The new
Training workspace pages produce no errors; unrelated pages were not changed.

Visual browser verification could not finish: Computer Use refused to control Edge
because it could not establish the current browser URL. No screenshot-based visual
verification is claimed. Legacy student study/quiz screens are reused; they were
not redesigned by this management-page task.

## 4. Traceability and operation

Main implementation: `RF-One Web/training_workspace_routes.py`, templates under
`RF-One Web/templates/training_workspace/`, page help under `templates/help/training_*`,
static `training-workspace.css/js`, canonical row-return script, registry entries,
`rfone_data_store/training/workspace.py`, and the migration above.

Functional scope: `Training/LOCAL_WORKSPACE.md`.
Run: `python "03 Software/RF-One Web/training_local.py" --serve`.
Tests: same launcher with `--test`; live checks with `--verify`.
Local URL: `http://127.0.0.1:5098/training/manage`.
No Git push, deployment or AWS write was performed.

## 5. Catalog correction — 2026-11-10

At the Product Owner's request, the 54 individual-dish entries were withdrawn from
the local catalog. The only available course is Visual Menu. Existing questions
and assignment histories were retained and their counts checked before/after.
`training_retired_pills` records withdrawal; both single/bulk assignment paths and
the workspace reject retired content. Page help was updated. The migration follows
the latest local Kitchen revision rather than overwriting its schema state.
Recovery is reactivation of selected retained entries, without recovering deleted
content. No AWS data was modified. Course repository/ingestion remains a proposal.
