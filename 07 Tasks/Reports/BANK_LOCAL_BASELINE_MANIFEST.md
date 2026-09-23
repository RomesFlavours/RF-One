# Local Bank Baseline — Certificate

**Tasks:** BANK_LOCAL_BASELINE_CONSOLIDATION_001 → BANK_LOCAL_BASELINE_LEGAL_ENTITY_RESOLUTION_001
**Date:** 2026-09-22
**Status:** **SIGNED — the local Bank baseline is consolidated and certified.**

> **Where this file lives.** `/Bank/` is git-ignored in its entirety
> (`.gitignore` line 106) because it holds real bank downloads and QA
> databases, so a manifest placed only there could never be
> source-controlled. This tracked copy under `07 Tasks/Reports/` is the
> version-controlled certificate; an identical working copy sits at
> `Bank/LOCAL_BANK_BASELINE_MANIFEST.md`, the path the task named.

This is the source certificate for the later AWS reset/copy. Every figure
below was read back from the database after the write, not predicted.

---

## 1. The authoritative database

| | |
|---|---|
| **Path** | `03 Software/RF-One Data Store/data/rfone.db` |
| **SHA-256 (current)** | `ceac487f08da048feafe20e57f12b4cc95761517f94dd1e8907441d892047c5f` |
| **Alembic revision** | `c8f1a3e04d97` (the single head; never downgraded) |
| **Git commit (baseline certified)** | `761c79febe18e4713c1ff537bbe46d6640185023` |

It is the database RF-One Web and the Data Store resolve when no
`RFONE_DATABASE_URL` override exists.

> **Schema advanced 2026-09-23 — the business baseline below did NOT
> change.** See §13. The SHA-256 and the Alembic revision above are the
> post-advance values; everything else in this certificate still describes
> the same certified business content, re-verified after the migration.

### Source, unchanged

| | |
|---|---|
| **Path** | `Bank/qa_web/bank_import_test.db` (READ ONLY throughout) |
| **SHA-256 before and after** | `e1e394bc6e5e9242d336ce1d78624e943d648fbc7bde9447bc3352ef91800799` |
| **Alembic** | `c4a9e7d21b56` — left exactly as it was, not migrated, not deleted |

### Backups taken before writing

- `data/rfone.db.baseline-consolidation-backup-20260922T205851Z`
  — `99e007f339a76c01e9b774688dd5276fc6e78cf66c4999a4b03d850c72bc2559`
- `data/rfone.db.pre-legal-entity-consolidation-20260922T210840Z`
  — `99e007f339a76c01e9b774688dd5276fc6e78cf66c4999a4b03d850c72bc2559`
- `Bank/qa_web/bank_import_test.db.baseline-consolidation-backup-20260922T205851Z`
  — `e1e394bc6e5e9242d336ce1d78624e943d648fbc7bde9447bc3352ef91800799`

All three are read-only on disk and each hash was verified against its source.

---

## 2. Canonical Legal Entities — 3

| Legal name | Status |
|---|---|
| Angeli E Demoni, LLC | ACTIVE |
| RF Gelati, LLC | ACTIVE |
| RF Mount Dora, LLC | ACTIVE |

The legacy labels `RF-WInter Park`, `RF-Mount Dora`, `RF Corporate` and
`Pino-Private` were **not** copied. No `Pino-Private` entity exists: the
personal instruments carry no Legal Entity at all.

`LegalEntity` holds only `legal_name` and `status`, so no EIN, address or
ownership percentage could be — or was — invented.

---

## 3. Payment Instruments — 14

Safe identifiers only. Full account and card numbers are never recorded here
or rendered anywhere in the UI.

### Angeli E Demoni, LLC — 4

| Institution | Display name | ··last4 | Type | Status |
|---|---|---|---|---|
| First Citizens | WP-Checking | ··7470 | BANK_ACCOUNT | ACTIVE |
| Chase | RF Saving | ··7129 | BANK_ACCOUNT | ACTIVE |
| Chase | RFWP- Checking | ··3336 | BANK_ACCOUNT | ACTIVE |
| Chase | Business | ··1057 | CREDIT_CARD | ACTIVE |

### RF Mount Dora, LLC — 2

| Institution | Display name | ··last4 | Type | Status |
|---|---|---|---|---|
| Chase | Ink Unlimited | ··8076 | CREDIT_CARD | ACTIVE |
| Chase | RFMD Checking | ··0336 | BANK_ACCOUNT | ACTIVE |

### RF Gelati, LLC — 3

| Institution | Display name | ··last4 | Type | Status |
|---|---|---|---|---|
| Chase | RF Corporate | ··3583 | BANK_ACCOUNT | ACTIVE |
| Chase | Ink Giovanna | ··3144 | CREDIT_CARD | ACTIVE |
| Chase | Business Anthony | ··2270 | CREDIT_CARD | ACTIVE |

### No Legal Entity — 5 (4 personal + 1 historical)

| Institution | Display name | ··last4 | Type | Status | Kind |
|---|---|---|---|---|---|
| Chase | Pino Checking | ··9318 | BANK_ACCOUNT | ACTIVE | personal |
| Chase | Sapphire | ··1562 | CREDIT_CARD | ACTIVE | personal |
| Chase | Ceo Checking | ··0214 | BANK_ACCOUNT | ACTIVE | personal |
| Chase | Freedom | ··2915 | CREDIT_CARD | ACTIVE | personal |
| Chase | Chase-2915 | — | BANK_ACCOUNT | **INACTIVE** | historical |

Display names, `last_four` and `external_account_identifier` were copied
verbatim: no identity was rewritten.

---

## 4. Settlement relationships — 6

| Card | Settles to | valid_from | valid_to |
|---|---|---|---|
| Ink Unlimited ··8076 | RFMD Checking ··0336 | 2026-08-07 | open |
| Ink Giovanna ··3144 | RF Corporate ··3583 | 2026-08-02 | open |
| Sapphire ··1562 | Ceo Checking ··0214 | 2026-08-03 | open |
| Business ··1057 | RFWP- Checking ··3336 | 2026-08-04 | open |
| Business Anthony ··2270 | RF Corporate ··3583 | 2026-08-02 | open |
| Freedom ··2915 | Ceo Checking ··0214 | 2026-08-02 | open |

`valid_from` values are exactly those validated in the source. All twelve
endpoints resolve to instruments inside the 14-row set.

---

## 5. Lifecycle fields

All four are `NULL` on all 14 instruments:

```
effective_start_date = NULL   effective_end_date        = NULL
lifecycle_end_reason = NULL   replaced_by_instrument_id = NULL
```

The legacy schema predates these columns, so no structured evidence existed
to map. Nothing was inferred from `created_at`, from `status`, or from a
display name. NULL means UNKNOWN.

---

## 6. Every Bank table in the baseline

| Table | Count |
|---|---|
| legal_entities | **3** |
| payment_instruments | **14** |
| bank_card_settlement_accounts | **6** |
| bank_accounting_classifications | 136 |
| bank_transaction_reasons (WHY) | 77 |
| bank_reason_groups | 14 |
| **WHAT** (`is_what`: P&L, non-GROUP, active) | **72** |
| bank_card_holder_assignments | 0 |
| bank_import_batches | 0 |
| bank_instrument_assignment_audits | 0 |
| bank_monthly_instrument_coverages | 0 |
| bank_monthly_source_periods | 0 |
| bank_occurrence_reason_associations | 0 |
| bank_occurrence_types | 0 |
| bank_occurrences (WHO) | 0 |
| bank_recognition_rules | 0 |
| bank_source_instrument_profiles | 0 |
| bank_transaction_explanations | 0 |
| bank_transaction_reason_export_mappings | 0 |
| financial_transaction_matches | 0 |
| financial_transactions | 0 |
| raw_bank_transactions | 0 |

**Operational Bank state is clean:** no transaction, explanation, WHO,
learned rule, import batch, WHO↔WHY association, monthly period or monthly
coverage exists.

---

## 7. Integrity

| Check | Result |
|---|---|
| `PRAGMA integrity_check` | **ok** |
| `PRAGMA foreign_key_check` | **0 violations** |
| Every settlement endpoint resolves to an existing instrument | ✅ |
| Every `linked_instrument_id` resolves inside the set | ✅ |
| No duplicate Payment Instrument business identity | ✅ |
| Historical INACTIVE instrument present | ✅ (1) |
| No lifecycle value invented | ✅ (0 rows) |
| Ownership matches the Product Owner mapping, instrument by instrument | ✅ (14/14) |

---

## 8. Tests

Full Bank regression, all on the suites' own disposable databases — the
authoritative file is never used as a test target.

| Suite | Result |
|---|---|
| test_bank_reconciliation_http | 60/60 |
| test_bank_settlement_ui_repair_http | 38/38 |
| test_bank_classification_bootstrap_http | 33/33 |
| test_bank_cardholder_and_dedup_http | 30/30 |
| test_bank_instrument_assignment_http | 125/125 |
| test_bank_manual_reconciliation_ux_http | 43/43 |
| test_bank_monthly_source_completeness_http | 57/57 |
| test_accounts_and_domains_http | 38/38 |
| test_startup_no_migration_no_write | 4/4 |
| test_payment_instrument | 12/12 |
| test_bank_who_why_what · test_bank_canonical_why_and_who · test_bank_who_why_invariant · test_bank_canonical_accounting_catalog · test_bank_recognition_expert_system · test_bank_reconciliation_service · test_bank_cardholder_and_dedup · test_bank_canonical_migration_immutability | ALL CHECKS PASSED |

---

## 9. Local browser smoke — PASS

Bank Home, Monthly Sources, Review, Classification and Monthly Export all
return HTTP 200 with no error page. All 14 instruments render, the three
canonical Legal Entities are shown, no `Pino-Private` label appears
anywhere, the historical INACTIVE instrument is visible, and **no full
external account identifier reaches any page** — only the ··last-four form.
No month, transaction, batch or WHO was created.

The smoke ran against a byte-for-byte **copy** of the authoritative
database, because that database holds zero login accounts and creating one
inside it would have seeded the certified baseline with a test identity. The
authoritative file's SHA-256 was identical before and after.

> **Operational note for local UAT:** `rfone.db` has no RF-One account, so a
> human opening the Bank pages locally must first create one
> (`create_admin.py`). That is a deployment step, deliberately not part of
> the baseline.

---

## 10. What was NOT copied, and why

| Not copied | Reason |
|---|---|
| Legacy LegalEntity labels | Product Owner replaced them with the three canonical entities |
| `Pino-Private` | by decision — personal instruments carry no Legal Entity |
| Canonical catalogs (136 / 77 / 14 / 72) | already present and **semantically identical**, compared by business key; copying would be noise, overwriting was forbidden |
| `bank_occurrence_types` (1 row in source) | WHO *type* vocabulary, not instrument configuration, and outside the expected final state. Still available in the legacy file if it is ever wanted |
| Transactions, import batches, WHO, learned WHY, recognition rules, explanations, monthly periods/coverages | forbidden, and all zero in the source anyway |

## 11. What was explicitly NOT changed

`Restaurant.legal_entity_id` (still NULL) · EmployeeCompensationTerm ·
PayrollCalculationRun · ApprovedCompensationSnapshot · Tips · Compensation ·
Payroll · schema · Alembic revision · application code · the legacy source
database · AWS (never contacted).

---

## 12. Certificate

The local Bank baseline is **CERTIFIED**: one authoritative database holds
the complete Bank configuration — 3 canonical Legal Entities, 14 Payment
Instruments with their ownership, 6 settlement relationships, the canonical
catalogs — over a clean operational state, at Alembic head `a5e1c93f7b20`,
with integrity and foreign keys verified, the full Bank regression green and
the local Bank UI rendering it correctly.

**SHA-256 as certified:** `7b569772a51ff6e4f72da0c926f9d1af9ddd4794c961a1c0e542bdf773e46bf4`
(superseded by the schema advance in §13, which changed no business content.)

---

## 13. Schema advance — 2026-09-23

**SCHEMA CHANGED. BUSINESS BANK BASELINE DID NOT CHANGE.**

BANK_LOCAL_GOLDEN_SCHEMA_ADVANCE_001 brought this database to the
repository's Alembic head. It is a schema alignment and nothing else: no
row of business content was added, removed or rewritten, and every figure
in §2 through §7 above was re-verified afterwards and still holds.

| | |
|---|---|
| **Alembic before** | `a5e1c93f7b20` |
| **Alembic after** | **`b7d4e92a1c58`** — the single repository head |
| **Migration applied** | `b7d4e92a1c58_add_bank_reconciliation_control_start.py` — one, purely additive |
| **SHA-256 before** | `7b569772a51ff6e4f72da0c926f9d1af9ddd4794c961a1c0e542bdf773e46bf4` |
| **SHA-256 after** | **`06292315e4f67c181c41f117cf9feb12ac4d2fdb8373a21c9302be23dc6955a7`** |
| **Backup taken first** | `data/rfone.db.pre-schema-advance-b7d4e92a1c58-20260923T022946Z` — hash verified identical to the source before migrating |

### Business content, re-verified after the migration

| | Before | After |
|---|---|---|
| Legal Entities | 3 | **3** |
| Payment Instruments | 14 | **14** |
| Settlement relationships | 6 | **6** |
| Canonical accounts · WHAT · WHY · WHY groups | 136 · 72 · 77 · 14 | **136 · 72 · 77 · 14** |
| All 15 operational Bank tables | 0 | **0** |

All 14 instruments compared field by field on safe business identity —
institution, display name, last four, type, status, Legal Entity, linked
instrument and all four lifecycle fields — and are **identical**. Every
`effective_start_date` is still NULL, meaning UNKNOWN: the migration
manufactured none. The 6 settlement relationships were compared by business
identity rather than by id and are unchanged, valid-from dates included.

### The new table

`bank_reconciliation_control_configs` exists, with its expected columns,
its `rfone_accounts` foreign key, and no default baked into
`control_start_month`. Both constraints were probed and are genuinely
enforced: a value that is not `YYYY-MM` is refused by `ck_brcc_month_shape`,
and a second row is refused by `ck_brcc_singleton`. The probes ran inside a
transaction that was rolled back, and the file's SHA-256 was identical
before and after them.

| | |
|---|---|
| **Configuration rows** | **0** |
| **Reconciliation control start value** | **NOT SET** |

The threshold is a Product Owner decision that has not been taken. No value
was invented — not 2026-01, not 2025-01, not any other. No monthly period
and no coverage row was created by the migration.

### Verification

`PRAGMA integrity_check` = **ok** and **0** foreign-key violations, before
and after. The full Bank regression is green on disposable databases —
**12 web suites (553 checks)** and **12 Data Store suites** — and the
authoritative file's SHA-256 was identical before and after running them,
so no test touched it.

---

## 14. Configuration evolution — 2026-09-23

**This is a CONFIGURATION evolution of the Golden baseline, not a new
baseline.** The certified business content of §2 to §7 is unchanged except
for the two verified items below, and Bank operational data is still
entirely empty.

| | |
|---|---|
| **Alembic** | `b7d4e92a1c58` → **`c8f1a3e04d97`** (additive; `b7d4e92a1c58` not edited) |
| **SHA-256** | `06292315e4f6…6955a7` → **`ceac487f08da048feafe20e57f12b4cc95761517f94dd1e8907441d892047c5f`** |
| **Backup first** | `data/rfone.db.pre-historical-foundation-20260923T032701Z`, hash verified identical before writing |
| **Legal Entities** | 3, unchanged |
| **Payment Instruments** | 14 → **15** |
| **Settlement relationships** | **6**, unchanged, `valid_from` dates untouched |
| **Operational Bank data** | **0**, unchanged, across every table |
| **integrity_check / FK** | **ok** / **0** |

### 14.1 RFWP- Checking: ··3336 corrected to ··3376

The registered last four were wrong. Corrected **in place** — the same
instrument, the same id — so no second account exists and every existing
relationship follows unchanged. The settlement now reads
`Business ··1057 → RFWP- Checking ··3376`, with its `valid_from` of
2026-08-04 untouched.

Evidence: two independent original Chase exports name the account ··3376,
one week apart, both in the genuine Chase bank-account layout. A **ledger
test** settles that they are one account rather than two similarly named
files: they share 1 370 row identities and the running balance is identical
on **all 1 370**, with zero disagreements. Business context matches RFWP /
Angeli E Demoni — ANGELI E DEMONI LLC (89 rows), ROME'S FLAVOURS (59),
GIUSEPPE MIRAGLIA (64).

**No credible ··3336 source exists.** The literal string occurs five times
across the whole corpus and is never an account identity: it is a digit run
inside an ACH trace number, a merchant order reference and two running
balances. The old value had been hand-entered with an empty
`external_account_identifier`, so nothing corroborated it.

### 14.2 American Express ··1002 registered

| | |
|---|---|
| Institution / provider | AMEX / American Express |
| Type · currency · status | CREDIT_CARD · USD · ACTIVE |
| Legal Entity | Angeli E Demoni, LLC |
| Lifecycle | `effective_start_date`, `effective_end_date`, `lifecycle_end_reason`, `replaced_by_instrument_id`, `linked_instrument_id` — **all NULL** |

Evidence: eight original Amex exports agree. The three QBO/OFX files carry
structured provider metadata — `<ORG>AMEX`, `<FID>3106`, statement type
`CCSTMTRS` (credit card), `<CURDEF>USD` and an `<ACCTID>` ending 1002 — and
every QBO row carries a distinct `<FITID>`, a stable provider transaction
identifier. The five CSV/XLSX exports carry an `Account #` ending 1002 and
a `Card Member` of GIUSEPPE MIRAGLIA across 341 rows.

The sources stop at 2026-03. That is a **source boundary**, not a closure:
nothing about the card's life was inferred from where the files happen to
end.

### 14.3 Audit

Both changes are recorded in `bank_instrument_identity_audits` (2 rows)
with the old value, the new value, the reason, the source evidence
including file hashes, and the timestamp. That table is new because the
existing `bank_instrument_assignment_audits` cannot hold these facts: its
own CHECK constraint requires a batch or a transaction to point at, and an
identity correction has neither.

### 14.4 Structures added

`bank_instrument_identity_audits` and
`bank_historical_instrument_candidates` — the second for accounts the
evidence names but the registry does not contain, which cannot be
represented as `BankMonthlyInstrumentCoverage` rows because every one of
those is anchored to a non-NULL `payment_instrument_id`. Both created
empty; the candidate table is still empty because the census that fills it
is read-only until sources are actually imported.

### 14.5 Regression

**67 checks** in the new historical-source-control suite plus the full Bank
regression green — **12 web suites** and **13 Data Store suites** — all on
disposable databases.
