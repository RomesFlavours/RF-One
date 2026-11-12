# Training course catalog

Approved by the Product Owner on 2026-11-10: adapt the existing catalog into one
course repository. Workflow: New course → general information → materials/lessons
→ save draft → make available. Existing Visual Menu is a course linking to its
existing RF-One page; individual dishes remain withdrawn catalog entries.

The TrainingPill ID remains the course identity used by existing assignments.
Course metadata extends it with a mutable draft and immutable numbered published
revisions. Each revision contains title, description, objective and ordered lessons.
New assignments pin the published revision; later edits do not replace assigned
materials. Existing Visual Menu assignments are linked to its initial revision.
Legacy withdrawn dish assignments are not rewritten.

The editor accepts plain text, an RF-One page link, HTTPS links, PDF files and
MP4/WebM video files. Uploaded bytes and metadata are stored in the canonical local
database, not in a second database, a public folder or Git. Files are capped at
25 MiB each and requests at 30 MiB; executable/HTML uploads are not accepted. File
delivery requires trainer access or an assignment owning that exact version/file.
No background download, email, publishing or external storage is introduced.

A draft needs a title; incomplete lessons may be retained while working. Activation
requires description, objective and at least one complete lesson. A saved active
course remains assignable while another draft is edited. Draft-only courses never
appear as assignment choices. The editor detects conflicting saves and preserves
its fields and selected files on validation errors. Version numbers are automatic.
Uploaded materials retained by earlier versions are not deleted during edits.

Local UI and contextual help use Italian and the existing olive/white shell. The
Content page opens the editor in a modal and returns to the same row after saving.
Course viewing is page-specific; text is escaped and links are validated. Courses
containing materials do not imply a scored quiz or automatic course completion.

Validation uses transactions rolled back on the canonical local database: draft
visibility, activation validation, upload signatures and limits, optimistic edits,
assignment-version pinning, file authorization and Visual Menu preservation.
