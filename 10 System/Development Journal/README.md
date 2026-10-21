# Development Journal

## Purpose

A system-level service of RF-One Web for documenting **by hand** every phase of a piece of RF-One work, from study to the AWS release. It is not a business Domain (it models no business field) and not a Product: it is how RF-One's own development is recorded.

One **card** (`DevJournalWork`) is one change with a verifiable result — e.g. "Bank — answers to the wizard questions".

The user interface is in English. Internal codes (`STUDY`, `IN_PROGRESS`, `DECISION`, …) never change; what people type (titles, objectives, entries, file names) is stored and shown exactly as written, never translated.

---

## Access

- One access code in RF-One Web's `domain_registry.py`: `DEV_JOURNAL`, shown on the account's access page (Settings → Accounts → Access) as the single checkbox **"Development Journal access"**. Same mechanism as every other access (`rfone_account_domain_access`), same rule (`rfone_web_session.account_may_enter_domain`): an ACTIVE account with the access ENABLED. Being an administrator does not, by itself, give access.
- Enforced on every route — list, card, forms, uploads, entry corrections, entry versions **and every document download** — by `require_domain_access("DEV_JOURNAL")`. The Home link ("Services" block) is only a convenience, never the control.
- Revoking the access closes pages and documents on the person's next request.
- Responsible persons are chosen only among accounts holding the access. A responsible who later loses the access stays on existing cards (shown as "no longer enabled") until someone changes it.

## Card

| Field | Values |
|---|---|
| Title | free text, required |
| Domain | "General / System" (`SYSTEM`) or any RF-One access code in `domain_registry.py` |
| Objective | the problem to solve and the expected result, required |
| Responsible | an account with the journal access |
| Phase | Study, Specification, Development, Local test, Ready for release, Released (`STUDY` … `RELEASED`) |
| Status | In progress, Waiting, Blocked, Completed, Cancelled (`IN_PROGRESS` … `CANCELLED`) |
| Next step | free text; shown first on the card and in the list ("to be defined" when missing on an open card) |

Author, creation time and last update (time and person) are recorded automatically. Adding or correcting an entry or uploading a document also counts as an update. Every phase or status change is kept in `dev_journal_work_changes`. A Completed or Cancelled card can be **reopened** (status back to In progress, recorded as a status change).

## Journal entries

Chronological (oldest first). Each entry: automatic date and author, reference phase, type — **Analysis, Decision, Activity, Verification, Problem, Release** — free multi-line text (shown verbatim, suited to pasting Claude/Codex reports; never rendered as HTML), optional references: link (http/https only), branch, commit, command/prompt.

Decisions are visibly distinct (own border and badge). A **Release** entry also requires environment (Test/Production), AWS service, version or commit and outcome (Succeeded/Failed), with an optional post-deploy verification. **No entry ever changes the card's phase or status** — a failed release stays documented and does not complete the work; a successful one does not either. Only a person editing the card does.

### Corrections and versions

- Only the **author** of an entry can correct it ("Correct" link; anyone else gets 403 on the page and on the POST).
- A correction never overwrites: the version being replaced is copied whole into `dev_journal_entry_versions`, with who wrote it, when, and when it was replaced. The entry keeps its original author and creation time and records `version`, `edited_by`, `edited_at`.
- Every user with access can consult all versions ("earlier versions" link on a corrected entry), newest first.
- Saving without any change creates no version and no event.
- Entries cannot be deleted.

## Documents

- Upload to the card, or to one entry (from the entry form or later from the entry itself). Up to 10 files per upload.
- Accepted: PDF, PNG, JPG/JPEG, GIF, WEBP, DOC/DOCX, XLS/XLSX, PPT/PPTX, TXT, Markdown. SVG, HTML and executables are refused. The content must match the extension (file signature; TXT/Markdown must be UTF-8 text). Maximum size per file: 20 MB (`RFONE_DEV_JOURNAL_MAX_DOCUMENT_MB`).
- The original name is kept for display only (path parts and unsafe characters removed); the stored object is named by a random id. SHA-256 and size are recorded.
- Opened in the browser (PDF, images, TXT; Markdown as plain text) or downloaded (`?download=1`, Office files always). Served by the app itself with `nosniff` and `no-store`, content type derived from the extension, never from the browser's claim.
- **Never public**, and always on persistent storage:
  - AWS: the private Selection document bucket `rfone-selection-documents-418674484214`, prefix `dev-journal/documents/` (`RFONE_DEV_JOURNAL_DOCUMENT_BUCKET`), SSE-S3.
  - Local: `RFONE_DEV_JOURNAL_DOCUMENT_DIR`, set by the local launcher.
  - **Neither set → no storage.** Uploads fail with "Document storage is not configured…" and nothing is saved (an entry submitted with files is refused as a whole). There is no fallback to the service's own disk.

## Events for MyRF

Every write records a `DevJournalEvent` in the same transaction, linked to its card, its author (`actor_account_id`) and, where relevant, its entry, entry version, document or change:

| Event | When |
|---|---|
| `WORK_CREATED` | New work |
| `ENTRY_ADDED` | New entry (any type except Release) |
| `RELEASE_RECORDED` | Release recorded (replaces `ENTRY_ADDED` for a release entry — one event per entry) |
| `ENTRY_EDITED` | Entry corrected by its author (`entry_version_id` = the version it replaced) |
| `DOCUMENT_UPLOADED` | Document uploaded (one per file) |
| `PHASE_CHANGED`, `STATUS_CHANGED` | Phase or status change (including reopen) |

Intended recipients: the accounts holding `DEV_JOURNAL` (`service.journal_accounts`). **Nothing is sent, notified or marked delivered.** There is deliberately no delivery column: delivery is per recipient and will be modelled by MyRF when it is built. The card shows its events in a collapsed "Events recorded for MyRF" section.

## Not integrated (by design)

No automatic link to Git, Claude, Codex or AWS: references are typed by hand.

---

## Implementation

| Part | Location |
|---|---|
| Tables | `03 Software/RF-One Data Store/rfone_data_store/dev_journal/models.py` |
| Rules, labels, file checks, versions, events | `…/dev_journal/service.py` |
| Document store (S3 / local folder / none) | `…/dev_journal/document_store.py` |
| Migration | `…/migrations/versions/c4e820261021_add_dev_journal.py` — revises `c8e4b2a6f0d1`; additive, 6 new tables |
| Routes | `03 Software/RF-One Web/dev_journal_routes.py` |
| Templates / CSS | `templates/dev_journal_*.html`, `templates/_dev_journal_macros.html`, `static/css/rf-one-dev-journal.css` |
| Tests | `03 Software/RF-One Web/tests/test_dev_journal_http.py` |

## Running it locally

From a checkout of `main`, in `03 Software/RF-One Web/`:

```text
Avvia RF-One Web.cmd                      (or: python local_server.py)
python local_server.py --create-admin    first time only: create a local admin (prompts for the password)
```

Then open `http://localhost:5095/dev-journal` and grant yourself "Development Journal access" (Settings → Accounts → Access).

`local_server.py` keeps everything in `%LOCALAPPDATA%\RF-One\RF-One Web\` (local SQLite database, this PC's session secret, uploaded documents) — outside OneDrive and the repository. It accepts only a SQLite database, clears the S3 bucket and the public address, migrates the local database explicitly at start, and never creates accounts on its own. It is not used on AWS.

## AWS configuration (applied 2026-10-21)

| Item | Value |
|---|---|
| Service | App Runner `rfone-web`, variable `RFONE_DEV_JOURNAL_DOCUMENT_BUCKET=rfone-selection-documents-418674484214` |
| Permissions | inline policy `rfone-web-dev-journal-documents` on `rfone-web-apprunner-instance-role`: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` on `arn:aws:s3:::rfone-selection-documents-418674484214/dev-journal/documents/*` only (versioned in `03 Software/Infrastructure/deploy/rfone-web/dev-journal-documents-policy.json`) |
| Network | unchanged: `rfone-web` already leaves through the VPC connector shared with Selection, which reaches S3 through the existing gateway endpoint |
| Bucket | unchanged: Block Public Access, AES256, versioning, TLS-only policy |
| Database | migration `c4e820261021` on RDS `rfone-dev` / `rfone` |
| Access | granted to the Product Owner's account only |

The release record is `07 Tasks/Reports/DEV_JOURNAL_RELEASE_001.md`.
