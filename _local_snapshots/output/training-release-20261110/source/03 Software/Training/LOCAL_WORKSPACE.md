# Local Training workspace

Approved scope: Product Owner request, 2026-11-09. Local only; no deployment.

Navigation, left to right: Content, Students. Assignments are opened from each
student row through the Assign content button, not a separate page/tab. The existing RF-One
olive/white shell is the graphic reference. All local interface text is Italian.

Students use the existing Training identity and RF-One login. Trainers can create
and edit name, email, phone and username, set an initial/reset password and archive
or restore a student. Archiving retains historical assignments and disables the
student's RF-One login. The student may also choose another available username
at the first-access screen. Credentials can be managed only for pure Training student
accounts, never administrators or accounts with another enabled Domain. A new or
reset password must be changed before the student accesses Training. Passwords are
hashed through the canonical account service and never redisplayed. Email is
required; this local workflow does not send email or grant email verification.

The content page manages the course repository approved on 2026-11-10: general
information, ordered lessons/materials, drafts and numbered available versions.
See COURSE_CATALOG.md for supported materials and lifecycle. Each active student's
row opens a modal showing that fixed recipient and the available course checkboxes.
There is no recipient selector or separate objective field. Confirmation uses the
existing Training service to create the Need and selected assignments atomically;
the objective records that this is a Training content assignment. Archived/inactive
students cannot receive new assignments. Existing employee links and all historical
assignments remain stored, but the former multi-recipient management page is removed.
Refreshing a submitted form cannot duplicate it. Errors preserve checkbox state;
success/cancel returns to the same student row and action with list context intact.

One additive profile table records phone, archive state, first-access requirement
and the optional existing employee link; a submission-token table prevents replay
of confirmed assignment batches. Both use the canonical local PostgreSQL
database. Existing content and histories are reused, not imported over local work.
The local launcher automatically signs the operator `rfone` into management using
its actual trainer permission. Student access remains an explicit credential flow.

Validation: isolated transactional service/HTTP checks with rollback; access,
CSRF, archive/restore, password replacement and old-session revocation, atomic
multi-recipient assignment, catalog, page help and browser layout. No AWS writes.

## Catalog withdrawal — Product Owner, 2026-11-10

Only the existing Visual Menu course remains available in the local catalog.
The 54 individual-dish pills are withdrawn through `training_retired_pills`;
their content, questions and historical assignments remain intact. Both individual
and bulk assignment services reject withdrawn entries. Migration `e7f120261110`
follows the current local schema `e8b920261110`, preserving intervening Kitchen work.
Course creation and repository ingestion were subsequently approved and implemented;
see COURSE_CATALOG.md and revision e9f120261110.
