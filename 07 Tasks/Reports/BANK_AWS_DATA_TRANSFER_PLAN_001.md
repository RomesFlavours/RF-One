# BANK_AWS_DATA_TRANSFER_PLAN_001 — Proposal: AWS history + local 2026 Bank work

**Status:** PROPOSAL, prepared 2026-10-12. No data has been changed. Executing it needs the Product Owner's
approval of this plan and of the open points in §8. Evidence files (with movement-level rows, kept outside the
repository): `%LOCALAPPDATA%\RF-One\Bank\transfer-review-20261012\`.

Sides compared (read-only): **AWS** = RDS `rfone-dev`/`rfone` at Alembic `7b1d4f9a2c6e`; **local** = the Bank
working database served on port 5080 of MINIPC-KSYR1
(`rf-one-bank-simple-who-rules/03 Software/RF-One Data Store/data/rfone.db`, Alembic `a3c7e5b9d1f4`).

## 1. Principle

AWS stays the base and nothing on it is deleted. The plan **adds** what only the local Bank has and **completes**
AWS rows with the local work, field by field. Ids differ between the two databases; every reference is carried
through the mappings below, resolved technically.

## 2. Entities

| Local | AWS | Proposed | Evidence |
|---|---|---|---|
| Legal Entity 1 "Rome's Flavours Mount Dora LLC" | 2 "RF-Mount Dora" | same entity | name; Source 0336 (MD checking) is LE 1 locally, LE 2 on AWS |
| Legal Entity 2 "Angeli e DemoniLLC" | 1 "RF-Winter Park" | same entity | AWS Reporting Entity "Angeli E Demoni, LLC" is LE 1; Sources 3376 and 7470 are LE 2 locally, LE 1 on AWS |
| Legal Entity 3 "RF Gelati LLC" | 3 "RF Gelati, LLC" | same entity | name; Source 3583 is LE 3 on both |
| Reporting Entity `RE_RFWP` "RFWP" | 1 `RE_ANGELI_E_DEMONI_LLC` | same entity; AWS row takes the local code and name | its Legal Entity (Winter Park) |
| Reporting Entity `RE_RFMD_LLC` "RFMD" | 3 `RE_RF_MOUNT_DORA_LLC` | same; local code and name | its Legal Entity (Mount Dora) |
| Reporting Entity `RE_RFCO` "RFCO" | 2 `RE_RF_GELATI_LLC` | same; local code and name | its Legal Entity (Gelati) |
| Reporting Entity `RE_PINO_PERSONAL` "Owners - Personal" (PERSONAL) | — | transferred (exists locally; not a new invention) | owner of Sources 0214 and 9318 locally |

Legal Entity names on AWS are **not** changed (shared with Tips/Payroll; decision of 2026-09-25). Reporting
Entities are used by Bank only (all foreign keys to `reporting_entities` are Bank tables), so taking the local
code and name is what lets the AI rules' For Whom ("RFWP", "RFCo") resolve on AWS without a new entity.

## 3. Sources

Evidence: the account number in the imported file names (`Chase0214_…`), the last four digits, and the matched
movements of 2026 (date + amount + description).

| Local Source | AWS Source | Proposed | Evidence |
|---|---|---|---|
| Ceo Checking ··0214 | #11 Ceo Checking | same | files `Chase0214`; 7 movements matched |
| MD Checking ··0336 | #10 RFMD Checking | same | files `Chase0336`; 61/68 matched |
| Ink RFWP ··1057 | #9 Business ··1057 | same | `Chase1057`; 108/109 |
| Saffire-Pino ··1562 | #8 Sapphire ··1562 | same | `Chase1562`; 207/223 |
| Checking Pino ··9318 | #2 Pino Checking | same | `Chase9318`; 107/108 |
| Checking RFWP ··3376 | #6 RFWP- Checking ··3376 | same | `Chase3376`; 1,454/1,498 |
| Checking RFCO ··3583 | #5 RF Corporate | same | `Chase3583`; 243/251 |
| Freedom ··2915 | #13 Freedom ··2915 | same | `Chase2915`; 374/381 |
| Ink RFMD ··8076 | #3 Ink Unlimited ··8076 | same | `Chase8076`; 29/33 |
| First Citizens Checking ··7470 | #1 WP-Checking | same | 294/297 matched (AWS file "AccountHistory") |
| **Ink RFCO ··3144** | **#7 Ink Giovanna ··3144** + **#12 Business Anthony ··2270** | **split by the file's `Card` column** | see §3.1 |
| Ink RFCO ··2270 (no movements) | #12 Business Anthony ··2270 | same | last four; local cardholder Anthony = AWS name |
| FirstCitizen Debit ··0632 (no movements) | — | transferred as a Source | exists locally only |
| — | #4 RF Saving (`Chase7129`) | kept on AWS | no local Source |
| — | #15 Amex ··1002 | kept on AWS | no local Source |
| — | #14 Chase-2915 (INACTIVE) | kept on AWS | no 2026 movement |

Source configuration (names, Personal classification, owners, card settlement accounts, cardholders) takes the
local values: it is the newer work. Local cards carry no Legal Entity because the release's model derives a card's
owner from its settlement account (`ck_payment_instrument_single_owner`); the AWS card Legal Entities are
replaced accordingly.

### 3.1 Cards 3144 / 2270 (from the import files, not the Source names)

- One Chase account, **main card 3144 and additional card 2270**. The account-level download
  (`Chase3144_Activity_20261007.csv`, format `CHASE_CREDIT_CARD_WITH_CARD`) carries a `Card` column: its 201
  stored rows all say **2270**. The card-level download of 3144 (`… (1).csv`, no `Card` column) gave 53 rows.
- **Local merged the two cards** in Source #9; **AWS keeps them apart** (its 2270 Source also receives the 2270
  rows of the account-level `Chase3144_…` files).
- Cross-check, row by row: every local row with `Card` = 2270 is on AWS #12 (168) or new in September (33); every
  row of the 3144 card file is on AWS #7 (52) or new (1). No exception.
- Local cardholders agree: 3144 Giovanna (from 2026-10-09; Anthony before), 2270 Anthony.
- Plan: local #9 rows go to AWS #7 or #12 by their raw `Card` value; local #12 = AWS #12.

## 4. Movements

| Group | Rows | Plan |
|---|---|---|
| AWS history before 2026 | 9,318 (2018-12-10 → 2025-12-31) | untouched, decisions included |
| 2026 matched (date + amount + description) | 3,104 | AWS row kept (id, batch, raw lineage); local decisions added field by field (§5) |
| AWS 2026 absent locally | 256 | kept as they are, with their 83 decisions |
| Local 2026 absent on AWS | 130 (all September 2026) | inserted on the mapped AWS Sources with their import batch, raw rows and decisions |
| Repeated rows | see §4.2 | nothing deleted |

### 4.1 Why the 256 AWS movements are not in the local Bank

| Cause | Rows |
|---|---|
| Amex: no local Source | 193 |
| RF Saving: no local Source | 14 |
| RFWP checking 2026-01-02 → 2026-01-07: the local file starts on 2026-01-07 | 36 |
| Repeated rows dropped by the local import (§4.2) | 12 |
| Freedom 2026-07-26, single row, cause not identified | 1 |

### 4.2 Repeated rows (same Source, date, description, amount)

AWS has 13 such groups (27 rows); local has none. **All 13 come from one file each, as distinct lines** (they are not
overlapping downloads). The local import marked the repetitions `DUPLICATE_IN_UPLOAD` and skipped them
(`bank_import_batches.import_log`).

- **Accounts with a running balance — proven real:** RFWP checking (5 groups: two 9,600.00 withdrawals with their
  two 10.00 official-check charges on 2026-01-26 and 2026-03-24, two 10.00 charges on 2026-02-25, two 10.00 fee
  reversals on 2026-02-26) and RF Saving (1 group). In each group the balance moves by the amount between the two
  lines.
- **Cards — no balance in the file:** Amex 1, Business 1, Freedom 3, Sapphire 1 groups. The bank's own export lists
  the line twice; no arithmetic proof.
- Plan: every row is kept. The release's import code still skips such lines — a defect for accounts with balance
  (see §7).

## 5. Decisions on the 3,104 matched movements

| Field | Same | Only local | Only AWS | Different |
|---|---|---|---|---|
| WHO | 147 | 1,448 | 50 | **0** |
| WHY | 134 | 38 | 268 | **1** |

Plan: the local WHO / WHY / For Whom / status go on the AWS row through the mappings (WHO by name, WHY by code,
entities by §2). The previous AWS decision is kept as history (a new current explanation, never an overwrite).
Where only AWS has a value, see §8.

Catalogues: WHY by code — the 81 AWS codes all exist locally, 17 local codes are added, 11 codes take the local
name (same WHAT); WHO by name — 83 shared, 12 local ones added, the 1,241 used only by AWS history kept;
accounting classifications identical (137 = 137).

## 6. AI Rules

- Transferred: the general AI instructions (1), the 8 rules with their versions, the "Solo WHO" run settings, and the
  application history re-pointed to AWS movement ids. Drafts and previews are working state and are not carried.
- Interpretations: the 13 found reusable plus #37 (rule 2), which is valid once the Reporting Entities carry the
  local names (§2): the For Whom "RFWP" resolves to AWS entity 1, "RFCo" to AWS entity 2 (checked with the release
  validator). All 8 current rules then reuse an Opus 5.5 interpretation, with no new AI call.
- Order: entities and instructions first, then interpretations (their key includes the instructions' text).
- New rule texts on AWS (Opus 4.6 on Bedrock): two clarifications in the interpreter's own instructions — "If the
  WHO changes, set 'Da confermare'" is `status`, not `only_if_who_differs` (which needs a rule-level WHO), and a
  general "ignore upper/lower case" also applies to the end delimiter (`end_case: ignore`). Rule texts and validator
  unchanged. Opus 4.6 on the 8 real rules, two runs each: current prompt 7/8 and 7/8 (rule 6 rejected both times);
  clarified prompt 8/8 and 8/8 (rule 6 valid with `end_case: ignore`; no regression on the others). Prepared on
  branch `feature/bank-ai-interpreter-precision`, not deployed.

## 7. Findings that need a code change (not data)

- The import skips lines identical to an earlier line of the same file (`DUPLICATE_IN_UPLOAD`). For files with a
  running balance this drops real movements. Correction: keep such a line as another occurrence when the balance
  differs (as the AWS-side importer did with its occurrence index).

## 8. Open points for the Product Owner

See the session report: only items that cannot be resolved from the evidence.

## 9. Execution (after approval)

A transfer tool with: dry run by default; guards on account, database and Alembic revision; a fresh RDS snapshot;
one transaction; a per-table manifest checked before commit; a refusal on second run. The local Bank must be
frozen (no change) from the moment the final local copy is taken until the transfer is verified.
