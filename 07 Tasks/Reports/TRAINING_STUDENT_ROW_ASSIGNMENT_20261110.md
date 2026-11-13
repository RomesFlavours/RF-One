# REPORT — Assignment from the student row

## 1. Requested change

The separate Assignments tab/page is removed. Navigation is Content → Students.
Every student row has Assign content, opening a modal for that fixed student.
Only available content appears as checkboxes; there is no recipient picker or
separate objective field. The Content catalog is otherwise unchanged.

## 2. Implementation

`training_workspace_routes.py` redirects the old management entry to Students.
Its old assignment POST is no longer exposed. A trainer-only, CSRF-protected POST
at `/training/manage/students/<id>/assign` fixes the recipient from the route and
uses the existing atomic Training assignment service and replay protection.
The recorded Need uses the neutral description “Training content assignment”.

Students template and workspace JavaScript open the checkbox modal, show the chosen
student, disable confirmation with no selections, preserve selections on errors and
reload the same list URL on success. The central row-return implementation preserves
record, filter, viewport and focus. Archived/inactive students have the action
disabled and server validation rejects assignments to them. Existing histories are
retained. The student editor form ID was made distinct from its help anchor so both
row modals address their own forms correctly.

Removed obsolete assignment page/help and its registry entry. Updated student page
help, including the modal-specific ? anchor, and the local functional specification.
No database migration, catalog data change, AWS change or publication was needed.

## 3. Validation

Rollback-only HTTP tests verify the two tabs, old-entry redirect, removed old POST,
row button and unique modal IDs, checkbox content availability/draft exclusion,
fixed-recipient assignment despite submitted alternate recipients, empty-selection
rejection, CSRF, trainer/student permissions, archived-student rejection, replay
rejection and existing student CRUD/password flows. All test data is rolled back.
Course repository regression tests and JavaScript syntax checks pass.

The whole-app How Works check retains the same 25 pre-existing unrelated registry
errors; none concerns the modified Training pages. Browser interaction/visual QA
remains unverified because the available Edge control previously refused access
when it could not establish the current URL; no new browser verification is claimed.

## 4. Operation and traceability

Local entry: `http://127.0.0.1:5098/training/manage/students`.
Launcher: `03 Software/RF-One Web/training_local.py --serve`.
Tests: launcher with `--test`, `--test-courses`, and live checks `--verify`.
Specification: `03 Software/Training/LOCAL_WORKSPACE.md`.
No existing assignment, course material or student history was deleted.
