# Bank codebase cleanup before release

**Task:** BANK_FINAL_CLEANUP_001
**Status:** Implemented on `feature/bank-simple-who-rules`. Not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no migration.

---

## Purpose

One coherent Bank implementation: one authoritative path for each function, no superseded
product code. Nothing was redesigned; the approved behaviour is unchanged.

## One authoritative path per function

| Function | The one path |
|---|---|
| Source create / edit | `bank_instrument_new` / `bank_instrument_edit` → `service.create_payment_instrument` / `update_payment_instrument` (Source modal) |
| Source Active / Inactive | `monthly_source.set_source_active` (Edit Source) and the Check Sources resolutions — same lifecycle fields |
| Import preview / confirm / cancel | `/bank/upload` → `import_preview.preview_import`; `/bank/upload/<token>/confirm` / `cancel` (`bank_import_staging`) |
| WHO Rule apply | `who_rules.apply_who_rule` (`/bank/who-rules/apply`) |
| General Rule extraction | `general_rules.extract` / `apply_to_new_transaction` (import) and Apply |
| Manual WHO + WHY | `/bank/transactions/<id>/who-why` → `manual_reconciliation.reconcile_who_why` → `row_reconciliation.record_who` |
| Create New WHY | `/bank/whys/create` → `manual_reconciliation.create_why_for_who` |
| WHY association | `why_catalog.associate` (one confirmation per human event) |
| Canonical WHO resolution | `who_recognition.CanonicalWhoResolver` |
| Review queue split | `review_queues` (To Reconcile / Reconciled) |
| Internal-transfer resolution | `matching` + `review_queues.own_account_movement` |
| Classification Learning discovery | `pattern_discovery.discover` (actionable suggestions only) |

## Retired (removed or redirect-only)

| Retired | Why | Now |
|---|---|---|
| `bank_classification_legacy.html` and the routes it alone used: `/bank/classification/what/import[/confirm]`, `/receivers/approve`, `/what|why|who/new`, `/<id>/edit`, `/<id>/status` | Superseded vocabulary editor and receiver-group approval; reachable only from the legacy template | WHAT / WHY / WHO on Bank Configuration; WHO by the WHO Rule; services kept |
| `/bank/transactions/<id>/why`, `/recognition-decision` | No current caller; superseded by Select WHO / WHY | `/who-why` |
| Standalone `/bank/reconciliation` month page, its WHO modal and `/bank/reconciliation/<id>/who` (with inline Add WHO, `row_reconciliation.NewWho`) | A second writable manual-WHO path beside Select WHO / WHY | `GET /bank/reconciliation` redirects to Review > Reconciled (same month); the row actions Confirm / Standard / Reopen / Save stay |
| `/bank/instruments`, `/bank/monthly` pages | Replaced by Source and Check Sources | Bookmark redirects |
| `/bank/configuration` Accounts & Cards, card settlement editing | Duplicate Source maintenance | "Manage Sources" link |
| `/bank/configuration` Support: file recognition rules (`/source[/<id>]`), control settings (`/control`), deduplication recompute (`/dedup/recompute`); and the now-unused `configuration.create_account / update_account / owning_entity / save_card / create_source / update_source / update_control` | Second writable implementation of functions owned by Source and Check Sources | A "Maintained elsewhere" link list |
| Run Backtest button and table | Development tool | Engine and admin-only route kept |
| Dead CSS (`.who-option-chain`, `.who-option.is-blocked`, `.who-option-blocked`, `.why-option-new .ww-option-note`, the standalone page's `rp-*` modal/header rules), unused imports and helpers | No remaining use | — |

## Authoritative locations of the former Configuration duplicates

| Function | Authoritative page / route |
|---|---|
| File recognition rules | Source › File recognition rules (`POST /bank/source-profiles/<id>`: re-point, enable / disable); created by "Reuse for this source" when a file's Source is resolved on Import and Review (`POST /bank/batches/<id>/resolve-instrument`) |
| Completeness control (control start, validated through) | Import and Review › Check Sources › Completeness control settings (`POST /bank/monthly/control-start`, `POST /bank/monthly/validated-through`) |
| Accounting deduplication recompute | Source › Accounting deduplication (`POST /bank/accounting-dedup/recompute`) |

## Retired script kept retired

`apply_deterministic_bank_classification.py` was retired by BANK_FINAL_RELEASE_BLOCKERS_001: its `main`
refuses before reading anything (a WHO's default WHY deciding a transaction is "WHO determines WHY"). It
follows the repository convention for retired scripts — body kept, `main` refusing, documented — and its
canonical-WHO helper is still exercised by `test_bank_deterministic_classification_who_safety.py`. It is not
revived and not part of the Bank product.

## Decision: structural extraction never creates a raw WHO

The `who-v1` recognizer (`who_recognition.recognize_transactions`, run only by the manual CLI
`apply_who_recognition.py`, never at import) no longer creates a `BankOccurrence` for a name that is not a
known WHO: the name is held as PROPOSED and a person creates the WHO (Select WHO / WHY, WHO Rule,
Configuration). The General Rule is the one import-time structural WHO path; it never creates a WHO either.
Existing WHO created by earlier runs are kept.

## WHY and bookkeeping

Bank reconciliation is WHO + WHY. A WHY is created with Name + Group; the WHAT is optional. A WHY rule no
longer requires its WHY to have a WHAT. Existing WHY → WHAT mappings are preserved (removing one is still
refused by Bank Configuration); accounting capability is unchanged.

## User-facing terminology

Import and Review and Check Sources say **Source** where they said Instrument / Payment Instrument.
Review Transactions keeps its "Instrument" column: its "Source" column already shows the file format, and
renaming would make two columns with the same name. Internal names (`PaymentInstrument`) are unchanged.
