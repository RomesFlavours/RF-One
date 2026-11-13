# REPORT — Training course repository

## 1. Approved result

The Content page manages one course repository: New course → general information
→ ordered materials/lessons → Save draft → Make available. The interface stays
Italian and uses the existing olive/white shell and contextual modal help.

## 2. Changes

Existing TrainingPill IDs remain course identities. Four additive tables store
drafts, immutable numbered versions, uploaded bytes and assignment-to-version
references. Migration `e9f120261110` follows `e7f120261110`, on the canonical local
PostgreSQL database. Visual Menu is initialized as an available course referencing
`/training/visual-menu`; existing Visual Menu assignments are pinned to version 1.
The 54 retired dish entries remain retired and their history remains intact.

The editor manages title, description, objective and ordered lessons. Supported
materials: plain text, internal RF-One pages, HTTPS links, PDF, MP4 and WebM files.
Files live in the existing database, with a 25 MiB per-file limit and 30 MiB request
limit. Access checks enforce trainer permission or ownership of the exact assigned
version/file. Draft-only courses are excluded from assignments. Course versions
create no implied quiz score or automatic completion.

Main code: `rfone_data_store/training/courses.py`, shared Training assignment
services/models, `RF-One Web/training_course_routes.py`, workspace Content/course
templates, `training-courses.js`, Training CSS and local launcher. The existing
student assignment route opens the pinned course view. Page help and registry were
updated with the functional change. Functional definition: `Training/COURSE_CATALOG.md`.

## 3. Validation

Transactional HTTP tests verify draft creation and assignment exclusion; rejection
of incomplete activation; text/PDF lessons and upload validation; activation;
draft isolation from the active version; stale-edit rejection; immutable published
versions; assignment pinning; file access and cross-student denial; escaped text;
malformed/unsafe link rejection; CSRF; Italian page/help and Visual Menu retention.
Test records and files are rolled back. The existing student/workspace tests pass.
JavaScript syntax checks pass. The course editor's IDs and help anchors are distinct.

The global How Works check retains the same 25 unrelated, pre-existing registry
errors. No Training course page is reported as an error; unrelated pages were not
changed to make the global check pass.

Computer Use could not control Edge because it could not establish the current
browser URL. Visual browser QA therefore remains unverified; HTTP and service
checks are not represented as screenshot/interactive-browser verification.

## 4. Operation and recovery

Open `http://127.0.0.1:5098/training/manage/content`. Management automatically uses
the existing local operator and its actual trainer permissions. Course authoring
does not publish to AWS or any external service. No Git push or deployment occurred.

Initialize explicitly with `training_local.py --initialize-courses`; tests with
`--test-courses`, existing workspace checks with `--test`, live checks with `--verify`.
Published revisions are retained when a new version is activated. Schema downgrade
is destructive to the new course repository tables and is not an ordinary restore
operation; rollback should preserve a database backup containing versions/files.
