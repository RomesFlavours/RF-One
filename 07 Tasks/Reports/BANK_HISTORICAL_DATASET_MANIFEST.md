# Bank Historical Dataset Manifest

**Tasks:** BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 (import) · BANK_HISTORICAL_DATASET_AUDIT_REPAIR_001 · BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_IDEMPOTENCY_001 (this regeneration)  
**Generated (UTC):** 2026-09-23 20:45 UTC by `generate_historical_dataset_manifest.py`  
**Git commit:** 6ee27ea14f9d24186cc292116536cddc00f9a722  
**Alembic revision:** `b31e7c0d9a54`  
**Golden DB SHA-256 at generation:** `85677e673d05303e4087f443f191a4a900d653b978e7f96b481a7fcfdb5b4927`  
**Clean staging manifest SHA-256:** `2723fb3def19bba901dbc36b218198c40eb28bf2892af7d907adb3bc72f15207`  
**Canonical DB manifest SHA-256:** `eb64a5f30414d222084cabc28cd5a393f7b2cf398d3247688766f09f1a4d8c8a`

Safe, aggregate metadata only. No raw transaction description, no full account number and no counterparty detail appears in this file — the cleaned dataset itself stays in the git-ignored staging workspace.

Every figure below is computed from the golden database and verified against the certified staging run; the generator refuses to write if the two disagree. A raw row is attributed to the instrument of the canonical transaction it evidences, never to its file's batch header.

---

## 1. Source corpus fingerprints

| # | File | Bytes | SHA-256 (first 16) | Format | Status | Rows | Rows by instrument |
|---:|---|---:|---|---|---|---:|---|
| 1 | `Download/AccountHistory.csv` | 31808 | `9f8879e09c474091` | FIRST_CITIZENS | PARSED | 286 | 1: 286 |
| 2 | `Download/Chase0214_Activity_20260915.csv` | 378 | `664037c1f7ba397d` | CHASE_BANK_ACCOUNT | PARSED | 3 | 11: 3 |
| 3 | `Download/Chase0336_Activity_20260915.csv` | 7967 | `ad71c55e95a5f565` | CHASE_BANK_ACCOUNT | PARSED | 46 | 10: 46 |
| 4 | `Download/Chase1057_Activity_20260915 (1).csv` | 7608 | `a594bda8991d116f` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 108 | 9: 108 |
| 5 | `Download/Chase1057_Activity_20260915.csv` | 8153 | `53c8ecb9ce066bad` | CHASE_CREDIT_CARD_WITH_CARD | PARSED | 108 | 9: 108 |
| 6 | `Download/Chase1562_Activity_20260915.csv` | 12262 | `ec84094288a8254c` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 184 | 8: 184 |
| 7 | `Download/Chase2270_Activity_20260915.csv` | 11587 | `ef3baf171b81ded3` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 157 | 12: 157 |
| 8 | `Download/Chase2915_Activity_20260915.csv` | 22589 | `4885081519cfbdeb` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 342 | 13: 342 |
| 9 | `Download/Chase3144_Activity_20260915.csv` | 15946 | `ce6ffa3f00285fba` | CHASE_CREDIT_CARD_WITH_CARD | MULTI_INSTRUMENT_SOURCE | 203 | 7: 46, 12: 157 |
| 10 | `Download/Chase3376_Activity_20260915.csv` | 301796 | `8717bf1b36a52c8d` | CHASE_BANK_ACCOUNT | PARSED | 1376 | 6: 1376 |
| 11 | `Download/Chase3583_Activity_20260915.csv` | 45231 | `4e694bd159c82418` | CHASE_BANK_ACCOUNT | PARSED | 221 | 5: 221 |
| 12 | `Download/Chase7129_Activity_20260915.csv` | 1038 | `1822b4880bd83ca4` | CHASE_BANK_ACCOUNT | PARSED | 14 | 4: 14 |
| 13 | `Download/Chase8076_Activity_20260915.csv` | 2132 | `452170b48aa83d60` | CHASE_CREDIT_CARD_WITH_CARD | PARSED | 25 | 3: 25 |
| 14 | `Download/Chase9318_Activity_20260915.csv` | 10318 | `958bd58563df73e6` | CHASE_BANK_ACCOUNT | PARSED | 101 | 2: 101 |
| 15 | `Historic Data/AccountHistory (1).csv` | 759341 | `3e35343e503dc6ea` | FIRST_CITIZENS | PARSED | 7890 | 1: 7890 |
| 16 | `Historic Data/AmeActivity.xlsx` | 9324 | `371835a8e9aa8303` | AMEX_XLSX | PARSED | 46 | 15: 46 |
| 17 | `Historic Data/Amex  activity.xlsx` | 9499 | `1b5ab75070f8753e` | AMEX_XLSX | PARSED | 48 | 15: 48 |
| 18 | `Historic Data/Amex (2).xlsx` | 20394 | `e410e21845724731` | AMEX_XLSX | PARSED | 89 | 15: 89 |
| 19 | `Historic Data/Amex (3).qbo` | 15034 | `4f0501a8a110663d` | AMEX_QBO | PARSED | 45 | 15: 45 |
| 20 | `Historic Data/Amex-activity.qbo` | 17777 | `ddc9dd5f18699cf1` | AMEX_QBO | PARSED | 54 | 15: 54 |
| 21 | `Historic Data/Amex.csv` | 7530 | `aff7569c0e05d7dd` | AMEX_CSV | PARSED | 94 | 15: 94 |
| 22 | `Historic Data/Amex.qbo` | 22871 | `941fb87b3970681a` | AMEX_QBO | PARSED | 70 | 15: 70 |
| 23 | `Historic Data/Amex.xlsx` | 11281 | `dadbf3db35eab4c7` | AMEX_XLSX | PARSED | 64 | 15: 64 |
| 24 | `Historic Data/Chase0214_Activity_20260922.csv` | 1036 | `ce2e3431ea220726` | CHASE_BANK_ACCOUNT | PARSED | 7 | 11: 7 |
| 25 | `Historic Data/Chase0336_Activity_20260922.csv` | 10972 | `3eb088e97d283721` | CHASE_BANK_ACCOUNT | PARSED | 61 | 10: 61 |
| 26 | `Historic Data/Chase1057_Activity_20260922 (1).csv` | 9544 | `d252939a0e836d0d` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 136 | 9: 136 |
| 27 | `Historic Data/Chase1057_Activity_20260922.csv` | 10229 | `e6af106acb90856a` | CHASE_CREDIT_CARD_WITH_CARD | PARSED | 136 | 9: 136 |
| 28 | `Historic Data/Chase1562_Activity_20260922.csv` | 26343 | `8a3d77e38ae3ffd1` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 399 | 8: 399 |
| 29 | `Historic Data/Chase2915_Activity_20260922.csv` | 69806 | `ccefde64bcd4dab3` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 1065 | 13: 1065 |
| 30 | `Historic Data/Chase3144_Activity_20260922 (1).csv` | 3838 | `47f64f3306b97ac4` | CHASE_CREDIT_CARD_NO_CARD | PARSED | 52 | 7: 52 |
| 31 | `Historic Data/Chase3144_Activity_20260922.csv` | 1200 | `4096bcadeb6ded06` | CHASE_CREDIT_CARD_WITH_CARD | MULTI_INSTRUMENT_SOURCE | 14 | 7: 3, 12: 11 |
| 32 | `Historic Data/Chase3376_Activity_20260922.csv` | 328405 | `3730541f8c5eb6d2` | CHASE_BANK_ACCOUNT | PARSED | 1504 | 6: 1504 |
| 33 | `Historic Data/Chase3583_Activity_20260922.csv` | 93622 | `2e8c21e2e2389cf0` | CHASE_BANK_ACCOUNT | PARSED | 545 | 5: 545 |
| 34 | `Historic Data/Chase7129_Activity_20260922.csv` | 3262 | `68b5e7d7286804ab` | CHASE_BANK_ACCOUNT | PARSED | 43 | 4: 43 |
| 35 | `Historic Data/Chase8076_Activity_20260922.csv` | 970 | `693c728aa5cbe000` | CHASE_CREDIT_CARD_WITH_CARD | PARSED | 11 | 3: 11 |
| 36 | `Historic Data/Chase9318_Activity_20260922.csv` | 28062 | `5c649a865dbac0ef` | CHASE_BANK_ACCOUNT | PARSED | 269 | 2: 269 |
| 37 | `Historic Data/Zelle 1-08.pdf` | 7364913 | `214e9507409f8261` | — | INVENTORY_ONLY | 0 | — |

Exact byte duplicates across paths: **0**. Rows from the two `MULTI_INSTRUMENT_SOURCE` files are split across the cards they actually belong to.

## 2. Clean staging construction

| Measure | Value |
|---|---:|
| Source files inventoried | 37 |
| Files parsed for financial content | 36 |
| Files inventory-only (Zelle PDF, not OCR'd) | 1 |
| Parsed source rows | 15816 |
| Promoted to clean economic event | 12678 |
| Duplicate evidence (overlapping downloads) | 3138 |
| AMBIGUOUS_DUPLICATE | 0 |
| UNRESOLVED_INSTRUMENT | 0 |
| PARSE_ERROR | 0 |
| UNSUPPORTED | 0 |
| Raw rows not linked to a canonical transaction | 0 |
| **Clean economic events** | **12678** |

Identity basis: provider transaction id **3,261** rows, canonical evidence **12,555** rows.

## 3. Ingestion order invariance

| Run | Source order | Clean manifest SHA-256 |
|---|---|---|
| A | forward | `2723fb3def19bba901dbc36b218198c40eb28bf2892af7d907adb3bc72f15207` |
| B | reverse | `2723fb3def19bba901dbc36b218198c40eb28bf2892af7d907adb3bc72f15207` |
| C | grouped | `2723fb3def19bba901dbc36b218198c40eb28bf2892af7d907adb3bc72f15207` |

**Identical across all three orders.**

## 4. File overlap relationships (diagnostic)

- `DISJOINT`: 31 pair(s)
- `PARTIAL_OVERLAP`: 1 pair(s)
- `TRANSACTION_EQUIVALENT`: 3 pair(s)
- `TRANSACTION_SUBSET`: 14 pair(s)
- `TRANSACTION_SUPERSET`: 1 pair(s)

## 5. Per-instrument controls

| Inst | Name | Type | Last 4 | LE | Files | Raw rows | Clean events | Dup. evidence | First | Last | Months | Gaps | Debit | Credit |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|
| 1 | WP-Checking | BANK_ACCOUNT | 7470 | 1 | 2 | 8176 | 7890 | 286 | 2018-12-10 | 2026-09-21 | 94 | 0 | -2,003,224.49 | 1,982,003.39 |
| 2 | Pino Checking | BANK_ACCOUNT | 9318 | — | 2 | 370 | 269 | 101 | 2024-10-01 | 2026-09-14 | 24 | 0 | -1,706,175.64 | 1,699,066.48 |
| 3 | Ink Unlimited | CREDIT_CARD | 8076 | 3 | 2 | 36 | 29 | 7 | 2026-05-14 | 2026-09-18 | 5 | 0 | -8,710.40 | 6,734.49 |
| 4 | RF Saving | BANK_ACCOUNT | 7129 | 1 | 2 | 57 | 43 | 14 | 2024-09-27 | 2026-08-31 | 24 | 0 | -1,012,602.47 | 658,253.05 |
| 5 | RF Corporate | BANK_ACCOUNT | 3583 | 2 | 2 | 766 | 545 | 221 | 2024-09-26 | 2026-09-21 | 25 | 0 | -1,116,623.96 | 1,129,776.47 |
| 6 | RFWP- Checking | BANK_ACCOUNT | 3376 | 1 | 2 | 2880 | 1504 | 1376 | 2025-12-30 | 2026-09-22 | 10 | 0 | -2,103,007.65 | 1,992,617.53 |
| 7 | Ink Giovanna | CREDIT_CARD | 3144 | 2 | 3 | 101 | 52 | 49 | 2026-04-20 | 2026-09-16 | 6 | 0 | -7,852.26 | 32,981.46 |
| 8 | Sapphire | CREDIT_CARD | 1562 | — | 2 | 583 | 399 | 184 | 2024-09-23 | 2026-09-21 | 25 | 0 | -71,152.30 | 67,840.76 |
| 9 | Business | CREDIT_CARD | 1057 | 1 | 4 | 488 | 136 | 352 | 2025-10-22 | 2026-09-04 | 12 | 0 | -23,370.66 | 23,284.66 |
| 10 | RFMD Checking | BANK_ACCOUNT | 0336 | 3 | 2 | 107 | 61 | 46 | 2026-03-25 | 2026-09-21 | 7 | 0 | -109,868.84 | 117,000.00 |
| 11 | Ceo Checking | BANK_ACCOUNT | 0214 | — | 2 | 10 | 7 | 3 | 2026-08-20 | 2026-09-16 | 2 | 0 | -15,037.93 | 69,945.05 |
| 12 | Business Anthony | CREDIT_CARD | 2270 | 2 | 3 | 325 | 168 | 157 | 2026-05-15 | 2026-09-21 | 5 | 0 | -24,756.12 | 0.00 |
| 13 | Freedom | CREDIT_CARD | 2915 | — | 2 | 1407 | 1065 | 342 | 2024-09-22 | 2026-09-18 | 25 | 0 | -164,326.27 | 162,114.81 |
| 14 | Chase-2915 | BANK_ACCOUNT | — | — | 0 | 0 | 0 | 0 | — | — | 0 | 0 | 0.00 | 0.00 |
| 15 | Amex | CREDIT_CARD | 1002 | 1 | 8 | 510 | 510 | 0 | 2025-08-01 | 2026-03-31 | 8 | 0 | -102,613.42 | 102,918.93 |

Totals: raw rows **15,816**, clean events **12,678**, duplicate evidence **3,138**; debits **-8,469,322.41**, credits **8,044,537.08**, net **-424,785.33**. First/Last are canonical posting dates. Every row above was checked against the certified staging controls (raw rows, clean events, duplicate evidence, debits, credits) and matches.

## 6. Historical instrument census

Registered instruments: **15**. With canonical transactions: **14**.

| Inst | Name | Last 4 | Census state |
|---:|---|---|---|
| 1 | WP-Checking | 7470 | REGISTERED_AND_SOURCED |
| 2 | Pino Checking | 9318 | REGISTERED_AND_SOURCED |
| 3 | Ink Unlimited | 8076 | REGISTERED_AND_SOURCED |
| 4 | RF Saving | 7129 | REGISTERED_AND_SOURCED |
| 5 | RF Corporate | 3583 | REGISTERED_AND_SOURCED |
| 6 | RFWP- Checking | 3376 | REGISTERED_AND_SOURCED |
| 7 | Ink Giovanna | 3144 | REGISTERED_AND_SOURCED |
| 8 | Sapphire | 1562 | REGISTERED_AND_SOURCED |
| 9 | Business | 1057 | REGISTERED_AND_SOURCED |
| 10 | RFMD Checking | 0336 | REGISTERED_AND_SOURCED |
| 11 | Ceo Checking | 0214 | REGISTERED_AND_SOURCED |
| 12 | Business Anthony | 2270 | REGISTERED_AND_SOURCED |
| 13 | Freedom | 2915 | REGISTERED_AND_SOURCED |
| 14 | Chase-2915 | not set | REGISTERED_NO_SOURCE |
| 15 | Amex | 1002 | REGISTERED_AND_SOURCED |

**Historical instrument candidates persisted:** 4 (`bank_historical_instrument_candidates`). Discovered generically from the raw evidence by `historical_source.discover_indirect_reference_candidates`; none has a Payment Instrument, none is resolved.

| Last 4 | Discovery | Canonical transactions | Raw evidence rows | First seen | Last seen | Resolution | State |
|---|---|---:|---:|---|---|---|---|
| ··0246 | INDIRECT_REFERENCE | 4 | 7 | 2026-07-21 | 2026-09-08 | unresolved | REFERENCED_WITHOUT_REGISTERED_INSTRUMENT |
| ··2813 | INDIRECT_REFERENCE | 6 | 11 | 2025-11-10 | 2026-04-23 | unresolved | REFERENCED_WITHOUT_REGISTERED_INSTRUMENT |
| ··5871 | INDIRECT_REFERENCE | 6 | 11 | 2025-08-14 | 2026-08-25 | unresolved | REFERENCED_WITHOUT_REGISTERED_INSTRUMENT |
| ··8321 | INDIRECT_REFERENCE | 3 | 5 | 2025-10-21 | 2026-02-02 | unresolved | REFERENCED_WITHOUT_REGISTERED_INSTRUMENT |

First/last seen are source boundaries of the evidence, never lifecycle dates.

## 7. Knowledge coverage

| State | Value |
|---|---|
| Financial ingestion | 12,678 clean events, 15,816 raw rows, 36 batches |
| WHO resolution | 0 / 12,678 |
| WHY classification | 0 / 12,678 |
| Invoice matches | 0 |
| Allocations | 0 |

## 8. Reconciliation control

`bank_reconciliation_control_configs`: **0**. `bank_monthly_source_periods`: **0**. `bank_monthly_instrument_coverages`: **0**.

## 9. ··3376 overlap: 1,370 vs 1,376

The earlier identity audit counted **1,370** shared rows between the two ··3376 exports: DISTINCT (posting date, amount, description) keys, a set. Certified staging counts **1,376**: the full canonical evidence identity (running balance included) with multiplicity. The difference is 6 key(s) where two genuinely separate transactions share date, amount and text and differ in running balance:

| Posting date | Amount | Transactions per file |
|---|---:|---:|
| 2026-01-26 | -9,600.00 | 2 |
| 2026-01-26 | -10.00 | 2 |
| 2026-02-25 | -10.00 | 2 |
| 2026-02-26 | 10.00 | 2 |
| 2026-03-24 | -9,600.00 | 2 |
| 2026-03-24 | -10.00 | 2 |

Staging is correct; the earlier count under-stated the overlap and its conclusion (one account, balances in agreement) is unaffected. No money changed.

## 10. Migration note

`a9e6d3c71f24` widens `bank_import_batches.detected_format` to admit the three American Express source shapes. It was applied to the golden database before the historical rows were promoted. The file's last modification is later than the golden database's last write, and because it was never committed the applied text cannot be recovered. What can be proven is the outcome: replaying the CURRENT file from the pre-migration backup produces a `sqlite_master` byte-identical to the golden database's, and a full downgrade/upgrade cycle returns to it. The applied schema and the file agree, so no corrective migration is needed. `test_bank_historical_audit_repair.py` pins this.

## 11. Corrections to the previous version of this file

- §5 raw rows for instruments 7 (Ink Giovanna ··3144) and 12 (Business Anthony ··2270) were 52 and 157; the rows of the two multi-instrument files were counted for no instrument. Every raw count is now attributed through the canonical transaction, and they add up to the raw total.
- §5 Batches column replaced by Files: the number of original files carrying evidence for the instrument, again through the rows.
- §6 candidates were reported only as a list of mentions; they are now persisted records.
- §9 is new: the ··3376 1,370 vs 1,376 reconciliation.
- Clean-event, canonical, debit and credit figures were correct and are unchanged.
- BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_IDEMPOTENCY_001: each candidate's evidence is now a keyed set (`bank_historical_instrument_candidate_evidence`, migration `b31e7c0d9a54`, one row per raw bank row). Candidate counts and dates are recomputed from that set, so re-running discovery cannot inflate them; the raw evidence column is new.
