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
| **SHA-256 (final)** | `7b569772a51ff6e4f72da0c926f9d1af9ddd4794c961a1c0e542bdf773e46bf4` |
| **Alembic revision** | `a5e1c93f7b20` (the single head; never downgraded) |
| **Git commit** | `761c79febe18e4713c1ff537bbe46d6640185023` |

It is the database RF-One Web and the Data Store resolve when no
`RFONE_DATABASE_URL` override exists.

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

**Final SHA-256:** `7b569772a51ff6e4f72da0c926f9d1af9ddd4794c961a1c0e542bdf773e46bf4`
