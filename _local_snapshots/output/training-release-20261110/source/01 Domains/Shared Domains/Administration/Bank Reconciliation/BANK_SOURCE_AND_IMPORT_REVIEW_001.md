# Source, and source control at import time

**Task:** BANK_SOURCE_AND_IMPORT_REVIEW_001
**Status:** Implemented on `feature/bank-simple-who-rules` — service, pages, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no migration. No table renamed, no new table.

---

## Product Owner decision

The separation between **Instruments** and **Monthly Sources** was two pages for one subject.
They are replaced by:

| Step | Page | What it answers |
|---|---|---|
| 1 | **Source** (`/bank/sources`) | *What financial sources does RF-One expect data from?* — setup only |
| 2 | **Import and Review** (`/bank`) | *I selected these files. Is this the correct, complete set to import?* — then Confirm or Cancel |
| 3 | **Review Transactions** (`/bank/review`) | reconcile what was imported (unchanged) |

Bank tabs, in order: Import and Review · Review Transactions · Monthly Export · **Source** ·
Classification · Instructions. There is no Instruments tab and no Monthly Sources tab.

## Source

* One row per canonical `PaymentInstrument`. The page says **Source**; the model, its table and
  its services keep their names. A **Source** is the configured, expected financial source; a
  **file** is one uploaded artifact from a Source. Uploading never creates a Source.
* Columns, all existing fields: Source, Type, Institution / Provider, Account (last four only),
  Owning entity (LLC — for a card, derived through its settlement account), Settlement / Funding
  (card settlement account and holder; PayPal "funded by"), State (Active / Inactive), Actions.
* **+ New Source** and **Edit** open ONE modal. It posts to the two existing routes
  (`bank_instrument_new`, `bank_instrument_edit`) and so to `service.create_payment_instrument` /
  `update_payment_instrument`: validation exists once. Saved with fetch: an error stays in the
  modal; success closes it and reloads the list (ordered by name).
* A card's settlement account and cardholder keep their dated history and are changed in the
  card's **Card settings** (the existing sub-page, now under Source in the breadcrumb). They are not
  typed in the modal: a settlement account is a historized fact with an effective date.
* **Active / Inactive is shown, not toggled.** BANK_FINAL_RELEASE_BLOCKERS_001 makes the
  lifecycle change only through a recorded Check Sources decision (Closed / Lost / Replaced /
  Other derive the end date; Still active checks nothing ended it). That rule is unchanged.
* Kept, collapsed below the list: File recognition rules (`BankSourceInstrumentProfile`), Source
  assignment history, Accounting deduplication summary and recompute.
* `/bank/instruments` redirects to `/bank/sources`.

## Import Set Review — the first step of Import and Review

`Upload and review` no longer imports. The sequence is:

```
files selected → staged → rehearsed import, rolled back → Import Set Review modal
               → CONFIRM IMPORT → the real import, once, in one transaction
               → CANCEL         → staged files deleted; Bank data never touched
```

### How the review is produced (reuse, not a second importer)

`rfone_data_store/bank_reconciliation/import_preview.py` runs the set through the real
`service.import_csv` inside the caller's session and **always rolls it back**. Every fact in
the review is therefore the fact the real import would produce, from the same code:

| Review shows | Produced by |
|---|---|
| Unrecognized files | `parsers.parse_csv_bytes` (`UnrecognizedFormatError`) |
| Duplicate in the set / already imported | the content hash `import_csv` already uses (a renamed identical file is the same file) |
| File → Source, multi-card files, rows naming an unknown account | `import_csv`'s own instrument resolution |
| Overlapping periods for one Source | `BankImportBatch.overlap_warning` |
| Transactions already in the ledger | the candidate-duplicate search |
| Expected Sources of a period | `monthly_source.expectation_with_lifecycle_boundary`, restricted to **ACTIVE** Sources |
| Covered by an earlier import | `monthly_source.batches_covering` / `multi_instrument_batches_evidencing` |
| Explained without a file | an existing Check Sources resolution |

Periods are the calendar months the files' own dates cover — never the file name or the upload
date. A file covering three months is shown covering three months.

### The modal

Summary (uploaded files, expected active Sources, recognized, would import, period in files);
Missing Sources (per month; historical months marked); Unrecognized files; Duplicates; Coverage
per month (expected / in this upload / imported earlier / resolved / missing) with a
Source-by-Source detail; Files; Warnings; Blocking issues. Two actions only: **Confirm Import**
and **Cancel**. Closing the modal any other way is a Cancel.

**Blocking** is only: *no file in this set would import anything new* (all unrecognized or
already imported). Missing Sources are a warning: a partial set may be imported deliberately,
and the month's completeness gate (Complete Month) is unchanged.

### Staging, Confirm, Cancel (`03 Software/RF-One Web/bank_import_staging.py`)

* Between selection and decision the files exist only in a staging directory
  (`BANK_IMPORT_STAGING_DIR`, default `<tmp>/rfone_bank_import_staging`), named by an
  unguessable token and bound to the uploading account. Nothing is written to the database.
* **Confirm** claims the set by renaming its directory (atomic), so a second Confirm finds
  nothing. All files are imported in ONE transaction: if any fails, nothing of the set is kept.
  The per-file messages and the completeness control that follow an import
  (`monthly_source.bring_months_under_control`) are unchanged.
* **Cancel** deletes the staged set. No `FinancialTransaction`, `RawBankTransaction`,
  `BankImportBatch`, Recognition decision or coverage row was ever written.
* Undecided sets older than 24 hours are removed by the next upload.

## Monthly Sources — what moved where

Nothing of its logic was deleted.

| Former Monthly Sources part | Now |
|---|---|
| Completeness check of a month (expected / received / missing) | Import Set Review, at upload — and Check Sources on Import and Review |
| Per-Source coverage table, resolutions, Clear, Complete Month, Reopen, audit log | Check Sources → *Source details* on Import and Review (same partial, same routes) |
| Reconciliation control start, validated-through | Check Sources → *Completeness control settings* on Import and Review |
| Select / create a month | the month selector and *Open month* already on Import and Review |
| `/bank/monthly` | redirects to `/bank?year=…&month=…#step-sources` |

The `/bank/monthly/...` POST routes keep their names and behaviour; their default redirect now
returns to Import and Review.

## Not changed

WHO / WHY reconciliation semantics, Classification Learning, General Rules, Manual Only,
canonical WHO, Amazon / PayPal connectors, bookkeeping, Export. The `/bank/configuration` page
(BANK_CONFIGURATION_001, reached from the Reconciliation page, not a tab) still edits Accounts
& Cards — see *Open points*.

## Product Owner decisions closing the open points (BANK_FINAL_RELEASE_BLOCKERS_002)

1. **Source is the only place to maintain Sources.** `/bank/configuration` no longer edits Accounts &
   Cards or card settlement / cardholder: block 4 is a "Manage Sources" link to `/bank/sources`, and the
   routes `/bank/configuration/account[/<id>]` and `/bank/configuration/card/<id>` are removed (404).
   No data-model change.
2. **Active / Inactive on Source.** The Edit Source modal carries a State control. It goes through
   `monthly_source.set_source_active` — the same lifecycle fields as the Check Sources resolutions:
   INACTIVE = end reason CLOSED, end date derived from the last eligible posting (UNKNOWN if none);
   ACTIVE = end reason and end date cleared, and an earlier closing decision no longer closes later
   months. A form without the control (Card settings) never changes the state.
3. **Missing Sources warn, never block.** Confirm Import stays available; only "no file would import
   anything new" blocks.

## Duplicate detection against retained rows

`service.comparison_description` — when a stored transaction has an empty `description_normalized`
(rows retained from the historical load), the duplicate comparison derives it from
`description_original` with the existing `normalize_description`. Same engine, same key; nothing is
written to the stored row. A re-downloaded file is therefore reported as candidate duplicates in the
Import Set Review, before Confirm.

## Import staging and AWS

Production `rfone-web` runs on AWS App Runner (gunicorn, 2 workers; see `03 Software/Infrastructure`).
Both workers of one instance share the local staging directory, so Preview -> Confirm works on a
single instance. App Runner can run several instances and replaces them on deployment; it has no
sticky sessions. If Confirm reaches another instance, or the instance was replaced in between, the
set is not found: the operator sees "already imported or cancelled, or expired. Nothing was imported"
and uploads again. It fails safe — never a partial or double import — but it is a usability risk.

The only existing S3 helper is Selection's résumé store (`selection/document_store.py`); reusing it
would make Bank depend on Selection, so it is not reused. For the AWS release, one of:

* configure `rfone-web` with **max 1 instance** (accepting a restart that loses an undecided review); or
* a follow-up task: an S3 (or database) backend behind `bank_import_staging` (same interface:
  stage / load / claim / discard; claim needs an atomic step, e.g. S3 conditional write).
