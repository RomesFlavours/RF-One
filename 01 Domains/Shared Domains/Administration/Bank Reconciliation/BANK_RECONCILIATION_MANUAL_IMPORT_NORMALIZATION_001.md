# Bank Reconciliation — Manual Import & Normalization Specification V1

**Version:** 1.5 (Financial Model Convergence integrated into main through Phase 6B — see below; Phase 4B canonical reconciliation decision unification carried forward unchanged)
**Status:** Integrated into `main` (Canonical Financial Model Convergence, `FINANCIAL_MODEL_CONVERGENCE_001`, Phases 1-6B): manual CSV upload, format detection, raw preservation, normalization, duplicate detection, and the Bank Recognition Expert System (`BANK_RECONCILIATION_EXPERT_SYSTEM_001` — `BankOccurrenceType`, `BankOccurrence`, `BankTransactionReason`, `BankRecognitionRule`, `recognition.py`) — all in `03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/` (`parsers.py`, `service.py`, `recognition.py`, `export.py`, `matching.py`), `03 Software/RF-One Data Store/rfone_data_store/models.py` (`PaymentInstrument`, `BankImportBatch`, `RawBankTransaction`, `FinancialTransaction`, `BankOccurrenceType`, `BankOccurrence`, `BankTransactionReason`, `BankRecognitionRule`, `BankTransactionReasonExportMapping`, `BankTransactionExplanation`, `FinancialTransactionMatch`), and `03 Software/RF-One Web/bank_routes.py`. As of Phase 4B, `BankTransactionExplanation` is the ONE canonical reconciliation decision (Product Owner Decision 1) — the legacy V1 Supplier/Receiving catalog workflow (`service.assign_explanation`, `bank_explanation_new`/`bank_transaction_explanation` routes) has been retired; Supplier/Receiving is `BankOccurrence.canonical_name` (Decision 2), and the Kermali accounting/export attributes (Food $/Oper/Deduct/What) live on `BankTransactionReasonExportMapping`, associated with the canonical Reason (Decision 4). Kermali export (`export.py`) reads the current canonical decision's immutable snapshot fields only, never the legacy fields (retired from the schema) and never the live Occurrence/Export Mapping rows — a later rename/edit never changes an already-exported historical value (Decision 8). `RfBank.xlsx` and the real source CSV files were read-only inputs to the original V1 task and were never modified. See "§10. Implementation Decisions" below for the decisions recorded when the V1 slice was originally built.

**Phase 5/6/6B addendum (PayPal, cross-ledger matching, operationalized):** a PayPal connector (`technical/connectors/paypal/`) acquires transactions into the same canonical `FinancialTransaction` ledger as CSV import, using the same `SourceSystem`/`IngestionRun`/`SourceRecord` provenance convention as every other connector in this codebase (Phase 5). `FinancialTransactionMatch` (Phase 6) records a confirmed cross-ledger internal-transfer link between two `FinancialTransaction` rows on different `PaymentInstrument`s (e.g. a PayPal settlement and the matching Bank deposit, or a Bank payment and the matching Credit Card charge), deterministically — same exact-opposite-amount/linked-instrument/compatible-currency/date-tolerance criteria as every other reconciliation decision in this codebase, never fuzzy/probabilistic. As of Phase 6B, this matching is **automatic**: the canonical post-acquisition hook (`matching.on_financial_transaction_acquired`) is called by both the CSV path (`service.py`) and the PayPal path (`technical/connectors/paypal/ingest.py`) immediately after a `FinancialTransaction` is normalized/upserted, so a confirmed AUTO match is attempted regardless of which side of a transfer (Bank, Credit Card, or PayPal) is acquired first — no manual trigger is required for the deterministic case. The HUMAN fallback (`bank_routes.py`'s Bank Review page, `require_linked_instrument=False` candidate discovery, `confirm_match`) remains fully available for evidence the automatic criteria cannot see (e.g. no `linked_instrument_id` configured yet) — Phase 6B narrows nothing HUMAN could previously confirm. A confirmed `INTERNAL_TRANSFER` (`classification` AND a confirmed `FinancialTransactionMatch` together — classification alone is never trusted) is exempt from the Kermali "Missing reconciliation decision" blocker and excluded from Kermali workbook rows, since WHAT (a confirmed transfer) is sufficient economic classification on its own and Kermali must never receive a fabricated WHO/WHY for it.
**Module:** Shared Domains / Administration / Bank Reconciliation
**Origin:** BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001

---

## Related documents

- [../README.md](../README.md) — Administration Domain purpose, module map, and its `Administration ≠ Restaurant/Personnel Management/Taxation/Accounting` boundaries
- [../../Purchased/README.md](../../Purchased/README.md), "Bank Reconciliation boundary" and "What Purchased does NOT own" — Purchased explicitly excludes Bank Reconciliation from its own scope; see "Open Points" below for a placement inconsistency this document surfaces but does not resolve
- [../Invoice Intake/README.md](../Invoice%20Intake/README.md) — the sibling Administration module this Domain must remain separate from (see "Scope and boundaries")
- `CLAUDE.md` — Core/Domain/Product/Runtime distinction; this document is Domain-level functional definition, not Product or Runtime design

---

## 1. Purpose

Bank Reconciliation is the Shared Domains / Administration capability responsible for acquiring bank-side evidence of what actually moved through RF-One's financial accounts, and for normalizing that evidence into a single, canonical transaction format.

This specification covers **exactly one** slice of Bank Reconciliation:

> **Manual CSV import from Chase and First Citizens, full preservation of the received file, and normalization of the different bank formats into the unified format already used by the `Bank` sheet of `RfBank.xlsx`, together with detection/control of already-acquired files, overlapping downloads, and potentially duplicate rows.**

No other Bank Reconciliation capability (automated bank feeds, invoice matching, payment/settlement logic, reporting) is designed, authorized, or implied by this document.

---

## 2. Scope and boundaries

### 2.1 Bank Reconciliation ≠ Purchasing, ≠ Invoice Intake

Bank Reconciliation is a distinct Shared Domains / Administration module. It must remain separate from:

- **Purchasing** (`01 Domains/Business Domain/Restaurant/Purchasing/`) — owns the supplier invoice / Purchase Document / Purchase Line business and cost model;
- **Invoice Intake** (`../Invoice Intake/`) — owns document acquisition/OCR/normalization of supplier documents;
- **Purchased** (`../../Purchased/`) — owns the normalized purchase fact (what was invoiced/purchased).

None of these three is redefined, merged, or extended by this document.

### 2.2 A bank movement is not an invoice

> **A bank movement is a financial fact of payment, receipt, transfer, or settlement. It is not the economic detail of an invoice.**

Consequently, as a conceptual/naming boundary for future work (not implemented here):

- `FinancialTransaction` is **not** `SupplierInvoice`;
- Bank Reconciliation may, in the future, associate a bank movement with an invoice, a payment, a deposit, or another RF-One object — but that association mechanism is **not** designed or implemented by this document;
- Bank Reconciliation must **not** arbitrarily reconstruct the content of an invoice starting from a bank movement (amount, description, and timing on a bank movement are evidence of settlement, not evidence of what was purchased);
- **the link with Invoice Intake / Purchased is explicitly out of scope for this task** and is not designed here.

### 2.3 What this document does not do

As originally written (V1.0), this specification itself did not write code, define models or tables, define migrations, implement a parser, import any data, or design an interface — it was documentation/design only. The V1 vertical slice built afterward (§10) implements exactly the scope this document defines, no more: it still does not design invoice matching, does not design a general-purpose API beyond the RF-One Web routes needed for this slice, does not modify `RfBank.xlsx` or the real source CSV files (read-only inputs), and does not reorganize existing repository structure. See "Explicit prohibitions" at the end.

---

## 3. Source formats (manual CSV download)

Three verified source structures exist today. All three must reduce to the single normalized format defined in §5.

### 3.1 Chase — bank accounts

Fields present in the source file:

| Column |
|---|
| `Details` |
| `Posting Date` |
| `Description` |
| `Amount` |
| `Type` |
| `Balance` |
| `Check or Slip #` |

Some files contain a final, undeclared empty column not present in the header. It must be ignored, provided it is genuinely empty; it must not be silently assumed empty without a check.

### 3.2 Chase — credit cards

Two variants have been observed for the same bank/product family.

**Variant A — explicit card identifier:**

| Column |
|---|
| `Card` |
| `Transaction Date` |
| `Post Date` |
| `Description` |
| `Category` |
| `Type` |
| `Amount` |
| `Memo` |

**Variant B — no explicit card identifier:**

| Column |
|---|
| `Transaction Date` |
| `Post Date` |
| `Description` |
| `Category` |
| `Type` |
| `Amount` |
| `Memo` |

When `Card` is not present in the file, the account/card must be resolved through the **configured import source** (i.e., which account/card the operator selected or configured for that specific download), never by relying definitively on the file name. A file name may be used as a hint, but it is not an authoritative identifier of the account/card.

### 3.3 First Citizens

Fields present in the source file:

| Column |
|---|
| `Account Number` |
| `Post Date` |
| `Check` |
| `Description` |
| `Debit` |
| `Credit` |
| `Status` |
| `Balance` |

For First Citizens:

> `Amount = Credit − Debit`

Therefore: a credit is a positive amount; a debit is a negative amount. This computed sign convention must match the sign convention already used by Chase's own `Amount` column (§3.1, §3.2), so that the normalized `Amount` (§5) is comparable across banks without further transformation.

---

## 4. Source preservation — two distinct levels

Two conceptually distinct records must exist for every acquired row. Neither level is optional, and neither replaces the other.

### 4.1 Raw Bank Import

Must preserve, unmodified, at minimum:

- the original file, exactly as received;
- the file name;
- the bank;
- the account or card associated with the file;
- upload date and time;
- the import batch the file belongs to;
- the original row number within the source file;
- all original fields of the row, including any not used by the normalized format (§5) — unused fields must **not** be discarded;
- a fingerprint of the file (to detect "same file already uploaded" — see §8);
- a logical fingerprint of the row (to support duplicate/overlap analysis — see §8);
- the outcome of reading the row (successfully parsed, anomalous, unreadable, etc.);
- any anomaly detected while reading the row.

### 4.2 Normalized Bank Transaction

Must produce the logical equivalent of the 12 columns of the `Bank` sheet of `RfBank.xlsx` — see §5 for the full mapping. A Normalized Bank Transaction is always derived from, and traceable back to, exactly one Raw Bank Import row.

---

## 5. Normalized Bank Transaction — field mapping

| Normalized field | Rule |
|---|---|
| `Account` | Canonical account name, resolved from the RF-One Financial Account Registry (§6) — never a raw value copied from the source file. |
| `Date` | Chase bank accounts: `Posting Date`. Chase credit cards / First Citizens: `Post Date`. |
| `Description` | Original bank description. The raw value must never be lost, even where a later classification step derives a cleaner/normalized description for display. |
| `Amount` | Chase: already signed in the source file, used as-is. First Citizens: computed as `Credit − Debit` (§3.3). |
| `Supplier/Receiving` | Result of a later recognition step or of a human decision. Not present in bank data. |
| `Food $` | Derived from classification. Not present in bank data. |
| `Oper` | Derived from classification. Not present in bank data. |
| `Deduct` | Derived from classification. Not present in bank data. |
| `What` | Type of cost or movement, derived from classification. Not present in bank data. |
| `Month` | Derived from `Date`. |
| `Year` | Derived from `Date`. |
| `Company` | Legal Entity / Company, resolved from the RF-One Financial Account Registry (§6) for the transaction's `Account` — never a raw value from the source file. |

### 5.1 What is not bank data

> **`Supplier/Receiving`, `Food $`, `Oper`, `Deduct`, and `What` do not come directly from the bank.**

They may legitimately remain **unclassified** after normalization. Normalization (this document's scope) and classification (a later, separate step) must not be conflated: a Normalized Bank Transaction with empty `Supplier/Receiving`/`Food $`/`Oper`/`Deduct`/`What` is a valid, complete normalization outcome, not an error.

### 5.2 `Company` must come from a registry, not a rule

> **`Company` must not be determined by a rigid rule based on a single account number.**

Account, Company, Legal Entity, account type, and account status must all be resolved from an RF-One registry of financial accounts (§6) — never hard-coded per account number, per bank, or inferred from a file name.

---

## 6. Financial Account Registry (anagrafica) — required configuration

Normalization (§5) depends on an RF-One registry of financial accounts that resolves, for each account/card: canonical `Account` name, `Company`/Legal Entity, account type, and account status. This registry is a **prerequisite** for normalization; its data model is not designed by this document.

The following accounts/cards have been identified in the received source files and require configuration in that registry before normalization can run for them. This document does **not** invent the Company, Legal Entity, or any other property for these accounts — they are recorded here as configuration still required from the Product Owner:

- Chase 0214
- Chase 3583
- Chase 7129
- Chase 8076
- Chase 9318
- First Citizens 7470

---

## 7. Verified results on received files (first analysis)

The following results were verified against the files actually received and are recorded here as evidence supporting §8 and §9. They describe the current state of the received files; they do not constitute an approved import or any modification to `RfBank.xlsx` or the CSV files.

### 7.1 Overall volume

- 14 CSV files received.
- 3,174 rows overall.
- No row is missing a date, a description, or an amount.
- All rows reduce to one of the three source structures in §3.

### 7.2 Certain overlaps between files

- The two Chase 1057 files each contain 108 rows, and both files contain the same 108 rows. Where both are available, the variant carrying the `Card` column (§3.2, Variant A) must be preferred. **Verified re-check:** a distinct-value (date, description, amount) comparison between the two files returns 107, not 108, matches — this is not a discrepancy in the underlying data. Both files independently contain the same internal duplicate (the `SEASONS 52` / 04/05/2026 / −24.05 row appears twice in *each* file — see §7.3); a distinct-value comparison collapses that duplicate pair to one entry per file, capping the measurable overlap at 107 even though all 108 rows of one file are, in fact, matched by a corresponding row in the other.
- All 157 rows of the Chase 2270 file are already contained in the Chase 3144 file, which contains movements for both card 2270 and card 3144.
- Rows certainly redundant across downloads: 265.
- Excluding the two redundant downloads leaves 2,909 source rows.

### 7.3 Identical rows within the files to be used

**Verified result: 13 excess occurrences** were found within the files retained after §7.2. An earlier pass through this document recorded 6; that count was not exhaustive across all twelve retained files — a full read-only re-verification (see the Bank Reconciliation V1 vertical-slice QA) found 7 additional excess occurrences, all in files that first pass had not covered (Chase 3376 and Chase 7129).

Originally identified (confirmed unchanged):

- Chase 1057: a second identical row for `SEASONS 52`, 04/05/2026, −24.05.
- Chase 1562: a second identical row for `PY *WINE BY GEORGE`, 03/31/2026, −14.18.
- Chase 2915:
  - a second identical row for `FOREIGN TRANSACTION FEE`, 08/13/2026, −1.04;
  - three identical rows for `UBER *TRIP`, 07/29/2026, −3.00 (i.e. two excess occurrences beyond the first);
  - a second identical row for `UBER *TRIP`, 04/17/2026, −6.50.

Additionally found on re-verification, in Chase 3376 and Chase 7129:

- Chase 3376:
  - a second identical row for `OFFICIAL CHECKS CHARGE`, 03/24/2026, −10.00;
  - a second identical row for `WITHDRAWAL 03/24`, 03/24/2026, −9,600.00;
  - a second identical row for `FEE REVERSAL`, 02/26/2026, 10.00;
  - a second identical row for `OFFICIAL CHECKS CHARGE`, 02/25/2026, −10.00;
  - a second identical row for `OFFICIAL CHECKS CHARGE`, 01/26/2026, −10.00;
  - a second identical row for `WITHDRAWAL 01/26`, 01/26/2026, −9,600.00.
- Chase 7129: a second identical row for `FEE REVERSAL`, 07/30/2026, 20.00.

> **These rows must not be automatically deleted.** The bank may have genuinely recorded more than one distinct operation with identical visible values (same merchant, date, and amount).

### 7.4 Similar but not identical operations

In the Chase 3376 and Chase 7129 accounts, movements exist with the same date, description, and amount, but a different running balance.

> **A different balance is evidence that these may be distinct operations. They must not be automatically treated as duplicates.**

### 7.5 Overlap with RfBank history

After excluding the two redundant downloads (§7.2), at least 841 rows of the CSV files correspond to rows already present in `RfBank.xlsx`, matched on:

> `Account + Posting Date + normalized Description + Amount`

Import must therefore also check bank movements already acquired by RF-One, not only overlaps between the newly received files.

---

## 8. Idempotency rules

The system must check the following five conditions **separately** — they are distinct failure modes, not one check:

1. the same file has already been loaded (file-level);
2. the same data is present in two different downloads (cross-file overlap, e.g. §7.2);
3. temporal overlap exists between successive downloads of the same account (a later download's date range overlaps an earlier one's);
4. the movement is already present in the normalized ledger (e.g. §7.5, against `RfBank.xlsx` history);
5. more than one operation is genuinely distinct despite sharing the same visible values (e.g. §7.3, §7.4).

> **The combination `Account + Date + Description + Amount` must not be defined as the single/sole identity key.** It is not sufficient on its own, because it could cause legitimate, genuinely distinct operations to be discarded as duplicates (§7.3, §7.4).

To support the five checks above and any future human review, the specification must retain at least:

- file fingerprint;
- row fingerprint;
- bank and account;
- import batch and source row number;
- transaction date, when available (Chase credit cards only expose this separately from post date — §3.2);
- posting date;
- type;
- reference/check/memo, when available;
- balance, when available;
- number of identical occurrences observed within the same download (§7.3);
- a `candidate_duplicate` status;
- routing to human review whenever identity cannot be determined with certainty.

> **A suspect movement must be preserved and flagged, never deleted.** Automatic deletion of a row that is only apparently duplicate is not permitted under any of the five checks above.

---

## 9. Minimal functional states

The following are a first functional terminology only. They name concepts to be reasoned about; they do **not** authorize the creation of an enum, a database table, or an application workflow.

- `RECEIVED`
- `PARSED`
- `NORMALIZED`
- `CANDIDATE_DUPLICATE`
- `REQUIRES_REVIEW`
- `ACCEPTED`
- `REJECTED`

No transition model, no state-machine implementation, and no software representation of these states is designed by this document.

---

## 10. Implementation Decisions (V1 vertical slice)

These decisions were recorded when the V1 vertical slice described above was built, and govern how the runtime implementation must be read against this specification. As of Phase 4B of the Canonical Financial Model Convergence, `BankTransactionExplanation` no longer carries a `category`/flat catalog shape (see the Status line above) — bullets below referencing it describe the historical V1 design intent that Phase 4B's canonical decision now fulfills, not the current literal field shape.

- **Bank Reconciliation is a Shared Domains administrative module.** It is industry-independent and reusable by any Business Domain, exactly like Payroll, Invoice Intake, and Purchased — never Restaurant-specific, never owned by a single Business Domain.
- **`RfBank.xlsx` is the Monthly Accountant Export.** It is the name of the recurring output artifact this Domain produces for the accountant (Kermali), generated as `RfBank_YYYY_MM.xlsx`. It is not a synonym for Bank Reconciliation itself and not a datastore.
- **The 12 columns of the `RfBank.xlsx` `Bank` sheet are an export shape, not the canonical `FinancialTransaction` model.** `FinancialTransaction` (the runtime canonical model — see `models.py`) may hold more fields than the export needs and may evolve independently of the export layout; the export module (`bank_reconciliation/export.py`) is the only place the 12-column shape is defined, and it is always derived from the canonical model, never the reverse.
- **The analytic classification of purchased products comes from invoices, not from Bank Reconciliation.** Bank Reconciliation's own classification (`BankTransactionExplanation`: Supplier/Receiving, category, Food Cost/Operative/Deductible, What) is the general classification the current accountant export needs — it is not, and must not be confused with, the analytic composition of what was actually purchased (that belongs to Invoice Intake/Purchased).
- **Bank Reconciliation does not determine the economic composition of purchases.** It records and normalizes financial movements (payments, receipts, transfers, settlements) — it never reconstructs or asserts what was bought, in what quantity, or at what unit cost.
- **Bank Reconciliation's own responsibility is to record and normalize financial movements** into the bank-independent `FinancialTransaction` shape, with full raw preservation (`RawBankTransaction`) and duplicate/overlap detection — nothing more.
- **Invoice Intake remains a separate module.** No table, route, or service introduced by this vertical slice reads from, writes to, or links against Invoice Intake/Purchased/Purchasing; the boundary stated in §2.1–§2.3 is unchanged by the implementation.
- **Chase and First Citizens are the initial CSV Source Adapters.** "Source Adapter" here means: a source-specific CSV layout + parsing function (`bank_reconciliation/parsers.py`) that produces the same bank-independent normalized shape as every other adapter — not a runtime plugin architecture, which this vertical slice does not build.
- **Mercury is a future source, to be integrated through a connector — not implemented here.** No Mercury code, credential, or endpoint exists anywhere in this vertical slice (see "Prohibited changes"/"Divieti" — connectors are explicitly out of scope for this task).
- **Changing the bank or the acquisition source must never require changing the internal model or the export.** `FinancialTransaction` and `bank_reconciliation/export.py` are bank-agnostic by construction: adding a future source means adding a new parser function that produces the same normalized shape, not modifying the schema or the Kermali column layout.
- **Automating the accountant's own work is explicitly out of scope**, now and for any foreseeable future iteration referenced by this document. This vertical slice produces the export the accountant currently consumes manually; it does not attempt to replace, pre-fill, or reason about the accountant's own downstream work.

---

## Open Points

- **Placement inconsistency with `Purchased/README.md`.** `01 Domains/Shared Domains/Purchased/README.md`, section "Bank Reconciliation boundary," currently describes Bank Reconciliation as belonging to "the consuming Business Domain" — implying a Business-Domain-owned capability. This document instead places Bank Reconciliation as a transversal Shared Domains / Administration capability (per explicit placement instruction for this task), consistent with how Payroll, Invoice Intake, and Purchased itself are positioned as reusable-across-industries Shared Domains. This is a genuine, unresolved wording/ownership inconsistency between the two documents. It is not resolved here and `Purchased/README.md` is not modified by this task — it requires an explicit Product Owner decision.
- **Duplicate legacy folder — historical, now resolved.** At the time this document was originally written (on the Financial Model Convergence integration branch, before main integration), a second, older `01 Domains/Cross Domain/Administration/` folder still existed alongside the canonical `01 Domains/Shared Domains/Administration/` used by this document. That duplicate no longer exists: the canonical Shared Domains structural migration (completed on `main` independently of this document) retired `01 Domains/Cross Domain/` entirely before this document was integrated here. This document was written under `Shared Domains/Administration/Bank Reconciliation/` from the start, so no path adjustment was needed at integration time.
- **Financial Account Registry does not yet exist.** §6 lists six accounts/cards requiring configuration (Chase 0214, 3583, 7129, 8076, 9318; First Citizens 7470); their Company/Legal Entity and other registry properties are not known/invented here and must be supplied by the Product Owner. The registry's own data model is not designed by this document.
- **File-name-based card resolution is explicitly disallowed (§3.2) but no alternative mechanism is designed.** How the "configured import source" actually identifies the account/card when `Card` is absent from a Chase credit-card file is left open.
- **Deduplication/equivalence-check logic is not designed.** §8 establishes that five conditions must be checked separately and that no single key is sufficient, but no algorithm, scoring, or matching procedure is specified — this is intentionally left for a future implementation task.
- **Relationship to Invoice Intake / Purchased / Purchasing remains unspecified**, beyond the negative boundary stated in §2.2–§2.3 (a bank movement is not an invoice, and no association mechanism is designed here). Designing that association is explicitly out of scope for this task.
- **Automated bank feeds are out of scope.** This document covers manual CSV download/import only; whether and how an automated feed (e.g. bank API/aggregator) might later coexist with or replace manual CSV import is not addressed.
