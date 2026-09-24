# Bank Reconciliation — Manual Import & Normalization Specification V1

**Version:** 2.0 (adds §16, the canonical RF-One accounting catalog — BANK_CANONICAL_ACCOUNTING_CATALOG_001; adds §15, the classification bootstrap — What catalog import and receiver review, BANK_CLASSIFICATION_BOOTSTRAP_001; adds §14, the settlement-configuration repair and the modal contract — BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001; adds §13, cardholder history, card settlement account and accounting deduplication — BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001; adds §12, the hierarchical Who → Why → What classification — BANK_RECONCILIATION_WHO_WHY_WHAT_001; Financial Model Convergence integrated into main through Phase 6B — see below; Phase 4B canonical reconciliation decision unification carried forward unchanged)
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

## 11. Source resolution, correction and reuse (BANK_RECONCILIATION_INSTRUMENT_ASSIGNMENT_001)

Implemented after the first local web collaudo of the V1 slice, which exercised the real operator flow end to end and surfaced what §3.2/§6 had left undesigned. These decisions extend §3.2 and §6; they do not relax any rule stated there.

### 11.1 Order of evidence for resolving the Payment Instrument

A source (a whole file, or a single row) is resolved to a `PaymentInstrument` by the **strongest available evidence**, in this fixed order. Ambiguity is never resolved by picking the first match — when more than one instrument qualifies, the import stops and asks a human.

1. **The identifier the file itself carries.** First Citizens' `Account Number`, Chase credit-card Variant A's `Card`, matched against the instrument's `external_account_identifier` (exact) or its last four digits. Always wins over everything below.
2. **A source rule a human explicitly confirmed** (`BankSourceInstrumentProfile`, §11.4).
3. **The file name's own `Chase####` prefix**, matched against an instrument's **configured** last four digits. This does not make the file name authoritative (§3.2): the name alone resolves nothing, it only selects among instruments a human already configured, and any in-file identifier overrides it. The variable export date and a Windows `(1)`/`(2)` duplication suffix are stripped before matching, because neither is part of the source's identity.
4. **Exactly one compatible instrument exists — First Citizens only.** With a single configured First Citizens account there is genuinely nothing to decide. **Deliberately not applied to Chase:** §3.2 requires explicit human confirmation for a Chase source with no reliable identifier, and that rule stands — having configured few instruments is not evidence about a file.

Institution comparison is normalized (case and separators) so that `Chase`/`CHASE` and `First Citizens`/`FIRST_CITIZENS` are the same institution. Automatic resolution must never depend on which spelling an operator happened to type.

### 11.2 A file is not necessarily one account

A source file carrying **several distinct in-file identifiers** (a Chase export with more than one `Card`) is resolved **row by row**, and the batch itself stays unresolved. Assigning such a file as a whole is refused, not merely discouraged: it would silently attribute other cards' rows to one instrument. Rows whose identifier matches no configured instrument are left unnormalized — their raw rows are preserved and wait for a human, which is always preferable to attributing them to the wrong instrument.

### 11.3 Correcting an assignment already made

The first resolution of a batch and a later correction of it are the **same operation on the same canonical field**, and both are recorded. A correction:

- requires a **stated reason** — changing a decision a human already made must say why;
- **moves the existing `FinancialTransaction` rows in place**; it never deletes a transaction and never creates a second one, so no correction can duplicate or lose a movement;
- leaves the **raw layer byte-for-byte untouched** (`BankImportBatch.raw_file_bytes`, `RawBankTransaction.raw_fields`) — §4.1 is absolute, and a correction re-reads preserved raw fields rather than the original file;
- **re-derives** the identity fingerprint (§8), the candidate-duplicate state (§7, §8), Recognition and cross-ledger matching, and the batch's own status and overlap warning;
- is **idempotent** — repeating it changes nothing the second time.

Two states are deliberately preserved rather than recomputed: a human's own reconciliation decision (`decision_source = HUMAN`) is never overwritten by a rule re-run, and a human's duplicate decision survives as long as the transaction it was decided against is still on the same instrument. A confirmed internal-transfer match that a correction has made nonsensical (both sides now on the same instrument) is **surfaced for review, never deleted**.

Every correction, and every first resolution, writes one `BankInstrumentAssignmentAudit` row: scope (batch or transaction), previous instrument, new instrument, reason, who, when, and how many transactions moved. It is evidence of the change only — the current assignment is always and only `BankImportBatch.payment_instrument_id` / `FinancialTransaction.payment_instrument_id`.

### 11.4 Teaching a source that cannot identify itself

First Citizens' `AccountHistory.csv` never changes name, and with more than one First Citizens account the file alone cannot say which account it is. The human resolves it once and may save that choice as a `BankSourceInstrumentProfile`, keyed on the in-file identifier when there is one and otherwise on the stable part of the file name. Later imports of the same source reuse it (step 2 of §11.1). A rule can be re-pointed at another instrument or disabled; **disabling never deletes it**, so the evidence that a human once taught this mapping is kept.

This is a **source-resolution** rule (which instrument a file came from) and is deliberately a separate model from `BankRecognitionRule`, which is a **reconciliation** rule (who/why for an already-resolved transaction). Merging the two would conflate identity with meaning.

### 11.5 `REQUIRES_REVIEW` must always state why

§9's `REQUIRES_REVIEW` is a status, not an explanation. A batch's review state is therefore **computed from live data, never stored**, and always yields both the concrete reason and the one action that addresses it:

| Actual condition | Reason shown | Action offered |
|---|---|---|
| No instrument resolved, nothing normalized | no identifier this configuration can match | `Resolve instrument` |
| Rows still to normalize (multi-card file) | *n* rows carry an unknown identifier | `Normalize pending rows` |
| Rows that could not be parsed | *n* unreadable rows, preserved unmodified | `Review issues` |
| Candidate duplicates awaiting a decision | *n* candidate duplicates | `Review issues` (deep link to those rows) |
| Match invalidated by a correction | *n* matches now on one instrument | `Reprocess` |

A `Normalize` action is **never** offered for rows that are already normalized. When the batch is fully normalized and only a human decision is missing, the reason says so and links directly to the rows concerned.

### 11.6 Payment Instrument registry — editable, with one guard

§6's registry is the canonical `PaymentInstrument` (no parallel model). It is editable from the web interface: name, institution, type, last four / external identifier, Company/Legal Entity, currency, linked settlement instrument, and active/closed state. Three rules:

- **The full account number is never stored for display and never rendered** — only the last four digits, and the identifier exactly as the source file writes it (typically already masked).
- **A configuration that would make automatic recognition ambiguous is refused** — two ACTIVE instruments of the same institution and type sharing a last four or an account identifier. Closing one (setting it INACTIVE) resolves it, so reusing a last four on a replacement card is legitimate.
- **A missing Company/Legal Entity does not block saving**, but it does block the Monthly Export for every month containing that instrument's transactions — stated explicitly at the point of editing rather than discovered later at export time.

---

## 12. Hierarchical classification — Who → Why → What (BANK_RECONCILIATION_WHO_WHY_WHAT_001)

Implemented after §11, on the same canonical models. This section supersedes nothing in §10–§11; it states the shape the classification decision has had since the hierarchy was introduced, and the boundaries that shape must respect.

### 12.1 The three levels

A bank movement is classified as a chain of exactly three levels, each with a single owner:

| Level | Question | Canonical model | Meaning |
|---|---|---|---|
| **Who** | Which subject/receiver is involved? | `BankOccurrence` | The party a movement concerns — US Foods, ADP, the Florida Department of Revenue. `Supplier` remains only one possible `BankOccurrenceType`, never a default. |
| **Why** | Why does this movement exist? | `BankTransactionReason` | The economic reason — supplier invoice payment, payroll, tax payment. |
| **What** | What is this, in accounting terms? | `BankAccountingClassification` | The final accounting classification: **one line of a Profit & Loss statement or of a Balance Sheet** (`statement_type` ∈ `PROFIT_LOSS`, `BALANCE_SHEET`), with a self-referential `parent_id` for hierarchy. |

No model is duplicated to express this. Who and Why are the models that already existed; What is the one genuinely new concept, and the Kermali export mapping (`BankTransactionReasonExportMapping`: Food $ / Oper / Deduct / `what_label`) is untouched and keeps feeding the Kermali columns exactly as before. **What is an accounting statement line; the Kermali mapping is an export attribute. They coexist and are not the same fact.**

### 12.2 The associations are stored, not re-chosen per transaction

- A **Why** has exactly one current **What** (`BankTransactionReason.accounting_classification_id`).
- A **Who** has exactly one current default **Why** (`BankOccurrence.default_transaction_reason_id`), and through it inherits that Why's What.

Both are stored on the vocabulary itself and configured once, on the **Classification** tab. They are never selected again transaction by transaction.

A Why cannot be created or activated without a What; a Who cannot be created or activated without a default Why. A Who whose chain is incomplete — no default Why, an inactive Why, a Why with no What, an inactive or statement-type-less What — is **refused in reconciliation**, with the concrete reason and a link to where it is fixed. It is never silently completed with a guess.

### 12.3 The Review asks for the Who and nothing else

Review offers exactly one control per unclassified transaction: **Select Who**, which opens a searchable modal listing every Who with its type, its derived Why and its derived What. Why and What are consequences of the Who and are not selectable there. A Who that cannot be used is shown anyway, greyed, with the reason and a link to the Classification tab — more useful than a name silently missing from the list.

The two separate Who and Why menus this replaced no longer exist.

### 12.4 A decision is an immutable snapshot

Confirming a transaction writes one append-only `BankTransactionExplanation` row recording the Who, the Why, the What (by id, code, name and statement type), the account that confirmed it and when. That snapshot is captured once and never re-read from the live vocabulary — the same rule Phase 4B already established for the Occurrence name and the Kermali attributes, now extended to the whole chain.

Consequently: **editing a Who → Why or a Why → What association applies to future classifications only.** An already-confirmed transaction does not change, silently or otherwise.

### 12.5 Reclassification is explicit and auditable

Applying a changed chain to a historical transaction is a deliberate **Reclassify** action. It re-resolves the *same* Who through the *current* chain and writes a **new** decision row (`decision_status = HUMAN_RECLASSIFIED`); the superseded row is never edited and never deleted, so both remain queryable as history. Changing the Who itself is a different action — confirming a different Who — and stays distinguishable in the audit trail.

### 12.6 Learning recognizes the Who

A confirmed human decision may teach RF-One that a normalized description means a particular Who (`BankRecognitionRule`, `EXACT_NORMALIZED_DESCRIPTION`). What a rule recognizes is the **Who**; the Why and the What are re-derived from that Who's current chain every time the rule applies, so re-pointing a Who at another Why takes effect immediately without touching a single rule.

Unchanged from the original expert system: a single description never creates a broader `CONTAINS_TEXT`/`PREFIX` rule on its own — that requires an explicit separate human choice — and confirmations and contradictions accumulate on the rule rather than promoting it by an invented numeric threshold. Where compatible rules recognize different Whos, or where a matched rule's Who has an incomplete chain, the transaction is left at `NEEDS_HUMAN_REVIEW` and the modal is the operator's next step. Nothing is guessed.

The former "Reuse for future" checkbox no longer has anything to do with whether Who → Why → What persists — those associations always persist. It is now a description-learning control only, labelled as such.

### 12.7 Export

The Monthly Export reads the **confirmed snapshots**, never the currently editable associations. Its blockers are: a missing Who; a Who with no Why; a Why with no What; an incomplete historical classification (a decision whose recorded What has no statement type). A What being inactive blocks nothing that already carries a valid snapshot of it — deactivating a What never retroactively invalidates a month that was correctly classified.

A confirmed internal transfer remains exempt, exactly as Phase 6B established.

### 12.8 Invoice classification stays separate from bank classification

A supplier paid by invoice may legitimately classify to an **Accounts Payable settlement** What (a Balance Sheet line): the bank movement settles a liability, and that is the whole of what the bank movement says.

**Bank Reconciliation never infers the Food / Operating composition of that invoice's lines from the bank movement.** That detailed classification continues to come from the invoice (Invoice Intake / Purchased). §2.2's boundary is unchanged and is, if anything, made sharper by the What level: the bank answers "which accounting line did this movement hit", the invoice answers "what was actually bought".

---

## 13. Cardholder, settlement account and accounting deduplication (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001)

Implemented after §12, on the same canonical models. It answers two questions §§6/11 left open — which company a card's spending belongs to, and who was carrying the card — and closes a real accounting defect: the same operation reaching the books more than once.

### 13.1 Card → Settlement Account → Company

A Credit Card settles to a bank account, and **that account decides the Company**:

```text
Credit Card → Settlement Bank Account → Company / Legal Entity
```

The Company of a card transaction is read from the settlement account's `legal_entity_id`. It is **never** taken from the card's own `legal_entity_id`, and **never** from whoever holds the card. A card whose settlement account is unconfigured has no Company — visibly, not silently.

The assignment is **historized** (`BankCardSettlementAccount`, `valid_from`/`valid_to`), because a transaction posted in 2025 must be attributed to the configuration that was true in 2025. Reassignment closes the previous row and inserts a new one; nothing is deleted. Rules: the settlement target must be a `BANK_ACCOUNT` (never another card), a card never settles to itself, the chain never forms a cycle, and at most one assignment is open per card (`ux_bcsa_one_open_per_card`).

`PaymentInstrument.linked_instrument_id` keeps its existing role as the current-state link cross-ledger matching already reads; the service layer keeps it pointed at whichever assignment is open, so the two can never drift. Where no historized assignment covers a date, that column is the fallback — which is what lets a card configured before this task still be attributed correctly.

**Nothing is invented for existing cards.** A card with no assignment stays unconfigured, its transactions are reported as un-deduplicable, and the months containing them are blocked from export — months containing no such transaction are unaffected.

### 13.2 Card → Cardholder

`BankCardHolderAssignment` records **who physically held a card**, historized the same way. Its purpose is responsibility, analysis and possible personal benefits.

It is **inert for accounting**. The holder never determines the Company, never determines the settlement account, and never takes part in duplicate identity — two transactions are the same accounting fact or not, regardless of who was carrying which plastic. A `BANK_ACCOUNT` has no cardholder and the service layer refuses one.

At most one holder is open per card; a reassignment closes the previous period, so responsibility for a past charge stays with whoever held the card then.

**Identity reference — a decision worth recording.** RF-One has no single canonical "person" table that fits every cardholder: `ActingIdentity` is the Core accountability identity but exists only for someone who acts in RF-One, and `Employee` is Location-scoped and Clover-sourced, so neither covers (for example) an owner who holds a company card and never touches the POS. Rather than force one or invent a third person table, the holder is a **typed reference** — `holder_kind` ∈ `ACTING_IDENTITY` / `EMPLOYEE` / `UNLINKED_PERSON` — the same convention `AuthorityGrant.scope_type`/`scope_id` already uses. A canonical identity IS reused wherever one genuinely exists; the remaining case is explicit rather than hidden.

### 13.3 The accounting deduplication key

The same economic operation reaches the books twice when it appears on a mother card AND its linked card, in two overlapping Chase downloads, twice inside one file, in files saved under different names, or in imports run weeks apart. **A different `last_four` does not make a row a different accounting fact.**

The Product-Owner-defined key is four elements, and only these four:

1. settlement bank account
2. accounting/posting date
3. signed amount, to the cent
4. normalized payee/receiver description

When all four coincide the rows are one accounting fact, and exactly one occurrence may feed accounting, the monthly export, P&L and Balance Sheet.

This is deliberately a **different** key from §8's `compute_identity_fingerprint`, which stays as it is. That one is per-INSTRUMENT and includes transaction type, reference and balance precisely so a reviewer can see why two similar rows might be distinct (§7.4). The accounting key is per-SETTLEMENT-ACCOUNT and ignores all three, because the accountant's question is narrower: did this money movement already hit the books?

**Payee normalization** (`accounting_dedup.normalize_payee`, version `v1`) is deterministic and conservative: trim, upper-case, remove the two technical card markers Chase adds (`CARD #1234`, a masked `****1234`), collapse punctuation that varies between export formats of the same merchant, collapse whitespace. **No number and no word is dropped on a guess** — an invoice, store or order number is exactly what tells two charges to the same supplier apart. Every transaction stores its original description, its normalized payee, the normalization version and the resulting key, so any grouping decision stays reproducible and auditable after the algorithm evolves.

### 13.4 What happens to a duplicate

**No raw row is ever deleted, and no transaction is ever deleted.** For each group:

- one transaction is **canonical** and feeds accounting;
- the others are marked `DUPLICATE_SUPPRESSED`, linked to the canonical, and carry the reason and the key that produced the decision;
- they are excluded from the monthly export, from accounting counts, and from any future P&L / Balance Sheet feed;
- they remain fully visible in the import and audit screens, showing which batch/file they came from and which transaction was kept.

The **canonical choice is the earliest acquired occurrence** (lowest id), skipping any row a human already confirmed as a duplicate. Id is unique and immutable, so re-running deduplication over the same data — or re-importing that data — never moves the canonical row: a newly imported copy always loses to the occurrence already there.

Deduplication works within one batch, across batches, between a mother card's and a linked card's files, regardless of `last_four`, and regardless of file name.

**Where the settlement account is unknown, nothing is merged.** Such rows are marked `UNRESOLVED_NO_SETTLEMENT_ACCOUNT` and reported. Two cards whose accounts are both unknown are not thereby the same account.

### 13.5 Precedence over existing human duplicate decisions

§8's `duplicate_status` flow (per-instrument candidate duplicates, judged by a person) is a **different mechanism asking a different question**, and it is unchanged. Where it has already produced a verdict, that verdict wins:

| Existing human verdict | Accounting deduplication does |
|---|---|
| `CONFIRMED_DISTINCT` | Leaves the row CANONICAL even if the key matches another. A person said these are not the same operation; automatic logic must not overrule that. |
| `CONFIRMED_DUPLICATE` | Suppresses the row regardless of the key, recording that a human decided it. |
| `NONE` / `CANDIDATE_DUPLICATE` / unset | Decides normally. |

The direction is deliberately conservative: keeping a real transaction in the books is recoverable, silently dropping one is not.

### 13.6 Recalculation

Deduplication can be recomputed at any time, and is, after: an import; a settlement account being assigned or corrected; a batch or transaction being reassigned to another instrument; or on explicit request from Bank › Import & Instruments.

It is **idempotent and safe**: it re-derives everything from the current transactions and the current card configuration and writes only the accounting-deduplication columns. It never touches `raw_file_bytes` or `raw_fields`, never an amount, date or description, never the `duplicate_status` human flow, and never a reconciliation decision. When scoped to one instrument it still resolves the FULL group each affected row belongs to, so a canonical choice never depends on what the caller happened to pass in.

### 13.7 Interface

**Import & Instruments** reports raw rows preserved, canonical transactions, duplicate groups, rows excluded from accounting, and rows that cannot be deduplicated for want of a settlement account — read-only counters plus an explicit recompute action. The Payment Instruments list shows Name, Institution, Type, Last 4, derived Company, Settlement Account, Current Cardholder and State. A card's edit page owns its settlement account and cardholder, both with their full history and a correction path that keeps the row and records why.

**Review** shows a suppressed copy, clearly marked, with an expandable group detail naming its canonical transaction and the batch/file each member came from. Who → Why → What is **not** requested on a suppressed copy — the classification belongs to the canonical transaction and covers the whole group.

The **monthly export** uses canonical transactions only.

Full account numbers are never rendered anywhere — only a name and the last four digits, unchanged from §11.6.

### 13.8 Export blockers added

A missing settlement account blocks the months that actually contain the affected transactions, reported once per instrument with the row count, and never blocks a month those rows do not appear in. A missing Company on the settlement account blocks too — the card's own Legal Entity is not a fallback. Rows whose settlement account is unknown remain in the blocker scope so their other reasons (an undecided candidate duplicate, a missing Who) are still reported rather than replaced by this one.

---

## 14. Settlement configuration repair and the modal contract (BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001)

A corrective intervention after §13 was used for real. Two defects, both found by an operator rather than by a test, and both fixed at the cause.

### 14.1 One canonical control for the settlement account

The Edit Payment Instrument page offered **two apparently equivalent controls**: the older `Settles to` (`PaymentInstrument.linked_instrument_id`) and the new historized Settlement Account panel. An operator reasonably used the first. The information was saved — but only into the legacy column, leaving `bank_card_settlement_accounts` empty, which is what the accounting layer actually reads.

The rule now:

- a **CREDIT_CARD** has exactly ONE visible control, the Settlement Account panel. It writes the historized record, closes the previous period, keeps the history, and keeps `linked_instrument_id` in step purely as a **compatibility projection** of the current period;
- a **BANK_ACCOUNT** has no settlement account control — it is not applicable;
- the legacy select survives only for **PAYPAL**, whose linked bank account is a different fact (the one cross-ledger matching needs) with no historized equivalent;
- **any** legacy submission that still reaches the server for a card is routed through the canonical service, never written straight to the column. That is what makes a split configuration impossible rather than merely unlikely.

### 14.2 Recovering a configuration saved the old way

`repair_legacy_settlement_accounts.py` moves an existing, human-entered `linked_instrument_id` into the historized table. It **invents nothing**: the only source is the value a human already saved — never a file name, a `last_four` or an institution.

- `valid_from` is the card's **earliest imported transaction**, so the recovered period covers the whole history the database actually holds;
- a card with **no transactions** is reported for a human, never dated on a guess;
- a card whose link points at something other than a BANK_ACCOUNT is reported, never recovered;
- a card already configured through the canonical path is skipped entirely — a human decision is never overwritten;
- every recovered row carries the note `Recovered from legacy Settles to configuration`;
- it **previews by default** and writes only with `--apply`; `--expect N` refuses to write unless exactly N cards are recoverable;
- it is **idempotent**: a second run finds nothing to do.

No schema change was needed, so no migration was created: this is a controlled repair of existing application data.

### 14.3 The modal contract

The root cause of the "frozen page with an empty dialog" was a CSS specificity defect: `.org-modal-overlay` sets `display: flex`, and an author rule always beats the user agent's `[hidden] { display: none }`. Setting `hidden` therefore did nothing — a full-screen, fixed, `z-index: 50` backdrop stayed painted over the page and swallowed every click. The panel looked empty because it was showing a list that legitimately had no rows yet.

Fixed at the cause with a generic `[hidden] { display: none !important }` guard, which also repairs the Organization chart's dialog (same class, same toggle, same latent defect), plus one shared controller (`static/js/rf-one-modal.js`) that every RF-One dialog uses:

- one instance per page, opened and closed repeatably without a reload;
- closable by X, Cancel, Escape and a backdrop click (press AND release on the backdrop, so a drag-select released outside does not close it);
- Escape and Tab-trapping bound once at document level, acting on the topmost open dialog — not on the overlay, where they only worked if focus happened to be inside;
- focus returns to the trigger, page scroll is locked while open and released on close, and `aria-hidden` always agrees with what is painted;
- the panel scrolls internally and never exceeds the viewport on a small screen.

A second defect fixed here: the Select Who form action was built with `template.replace(/0$/, id)` against `/bank/transactions/0/recognition-decision`, which does not end in `0`, so the regex never matched and **every confirmation would have posted to transaction 0**. It now substitutes an explicit `/transactions/0/` placeholder, which cannot fail silently.

### 14.4 Empty states are statements, not blank panels

- **Select Who** with no Who configured says `No Who configured`, links to the Classification tab, renders **no** Confirm button (a control that could never fire), and still closes normally.
- **Cardholder** with no linkable person says `No linked people available` and still allows a named `UNLINKED_PERSON`. Only `HUMAN_USER` identities are offered — a card is held by a person, and listing a SYSTEM identity (the only one present in QA) offered a choice that is never correct. An Employee already represented by an identity of the same name is not shown twice.

---

## 15. Classification bootstrap — from import to classified books (BANK_CLASSIFICATION_BOOTSTRAP_001)

§12 made classification a chain and §13 made the ledger clean. This section is what makes it usable: 423 canonical transactions are not 423 decisions, and nobody should review them one at a time.

### 15.1 The What catalog is loaded, not typed

**Import What Catalog** (Bank › Classification › A) reads a chart of accounts from CSV or XLSX. The flow is fixed: **upload → parse → preview → human confirmation → import**. There is deliberately no route that takes a file and writes accounts in one step — the catalog is the vocabulary every future decision is phrased in.

What is imported, and what is refused:

- **structure only**: statement type, code, name, hierarchy. Amounts, balances and periods are figures *about* accounts and are never part of a What; a code column holding what reads as an amount is rejected as a misread file rather than imported;
- rows reading as **totals** or **headings** are reported and skipped, never turned into accounts;
- `statement_type` is mandatory. A file with no statement column and no statement stated for the upload is refused — RF-One does not guess which statement an account belongs to;
- a parent and a child must belong to the **same statement**; P&L and Balance Sheet stay distinct.

Where a plan carries **no codes of its own**, RF-One generates a `GEN-…` technical code derived deterministically from the statement type and the account's position in the hierarchy. The same catalog therefore always yields the same codes — which is what makes a re-import idempotent — and every generated code is marked as generated so nobody mistakes it for the accountant's.

Re-importing an identical catalog changes nothing. A code that already exists with a **different meaning** is reported as a **conflict and never overwritten**: a What referenced by a historical decision must not change meaning under the snapshots that point at it. Nothing is ever deleted.

**Status of the Kermali plan.** The fixed P&L / Balance Sheet plan is **not present in this repository**. What `Bank/RfBank.xlsx` contains (sheet `Lists`) is a flat 48-entry cost-type vocabulary and a 134-entry Supplier/Receiving list — with **no statement type, no account codes and no hierarchy**. Deriving a chart of accounts from it would mean inventing the statement side of every line, so no What was created from it. The importer is in place and the catalog is empty, awaiting the real file.

### 15.2 Unclassified Receivers

Section D lists the receivers the canonical transactions actually name, **derived live** — nothing is stored, and opening the page writes nothing.

Considered: canonical accounting transactions only. **Excluded**: the accounting duplicates (classifying a copy is work that can never reach the books), confirmed internal transfers (a transfer between your own instruments has no receiver), and rows already confirmed as duplicates.

Grouping is **exact on the normalized payee**, with direction kept separate so a refund never merges into a payment. Each group reports its sample original descriptions, transaction count, first and last date, signed and absolute totals, the companies and instruments involved, any suggestion with its confidence and reason, and a status of `UNCLASSIFIED`, `AMBIGUOUS` or `ASSIGNED`.

**Similar is not the same.** Two payees differing only in numeric tokens are shown to each other as suggestions, with the reason, and are **never merged automatically**: `PUBLIX 1488` and `PUBLIX 1661` are two stores, `EXPEDIA 73514944881264` and `EXPEDIA 72077652395580` are two bookings, and only a person can tell which case is which. The normalization reused here is the conservative one from §13.3, but the two questions stay separate: that one asks whether this is the same accounting fact, this one asks whether this is the same receiver.

No external AI and no network call: every grouping and every suggestion is explainable from the stored data alone.

### 15.3 Approving a group

One approval covers a whole group, and several groups can be approved onto one Who in a single operation. The operator links an existing Who or creates one; the **Why comes from that Who and the What from that Why**, exactly as everywhere else — never chosen per transaction.

On confirmation: an append-only decision with a full snapshot is written for every canonical transaction of the group that no human has already decided; **a human decision is skipped, never overwritten**; the suppressed copies are untouched; and an `EXACT_NORMALIZED_DESCRIPTION` recognition rule is recorded so the same receiver is classified automatically on the next import. Broader `CONTAINS`/`PREFIX` rules still require an explicit, separate choice.

The operation is **atomic**: every check that can fail — an incomplete Who chain, an ambiguous group — raises before anything is written.

Where transactions with the same payee are already classified under **different** Who values, the group is `AMBIGUOUS` and bulk approval is refused. RF-One will not choose between two human decisions.

### 15.4 What the next import does by itself

A certain rule recognises the **Who**; the Why and the What are re-derived from that Who's current chain at application time, so re-pointing a Who takes effect immediately without touching a rule. Contradictory rules, or a Who whose chain is incomplete, leave the transaction at `NEEDS_HUMAN_REVIEW`. Suppressed copies are never asked for a classification. Every row states how its classification came about: `HUMAN`, `LEARNED_EXACT_MATCH`, `AMBIGUOUS` or `MISSING`.

### 15.5 Suppliers paid by invoice — the boundary, restated

A bank movement says **who was paid**, not **what was bought**. A supplier paid against an invoice is classified as the settlement it is — typically an *Accounts Payable settlement* on the Balance Sheet. The Food Cost / Operating / Deductible composition comes from the invoice (Invoice Intake / Purchased), never from the bank line: one Costco, Instacart, Sam's, Cheney Brothers or Prime Line payment routinely covers several cost families at once, and splitting it from the bank side would be invention. Where the invoice or its link is missing, that is reported as a matching gap. **Building the Bank ↔ Invoice matching is deliberately out of scope here** — this states the boundary and nothing more.

---

## 16. The canonical RF-One accounting catalog (BANK_CANONICAL_ACCOUNTING_CATALOG_001)

§15 built the machinery and left the catalog empty, waiting for the accountant's chart. **RF-One no longer waits.** It defines its own canonical restaurant accounting structure, and Kermali may later map QuickBooks onto it — mapping is not the same as owning the meaning. `Bank/RfBank.xlsx` stays what it always was: historical classification EVIDENCE, never the source of truth.

### 16.1 What is canonical

134 accounts, 91 Profit & Loss and 43 Balance Sheet, in a fixed numbering:

| Range | Meaning |
|---|---|
| 1000–1999 | Assets |
| 2000–2999 | Liabilities |
| 3000–3999 | Equity |
| 4000–4999 | Revenue |
| 5000–5999 | Cost of Goods Sold |
| 6000–6999 | Labor Cost |
| 7000–7999 | Operating Expenses |
| 8000–8999 | Other Income / Expense |

The definition lives at `rfone_data_store/bank_reconciliation/canonical/RFONE_RESTAURANT_COA_V1.csv` — inside the package, under version control, shipped with the code.

Semantics worth stating because getting them wrong is expensive:

- **Sales tax collected is not revenue** (2200 Sales Tax Payable, a liability). **Guest tips collected are not revenue** (2300 Tips Payable). Collecting and remitting either has **no P&L effect at all**.
- **Merchant processing fees are an operating expense** (7210), never COGS. So are **management fees** (7640).
- **Employees are WHO, never accounts.** There is no "Anthony Walter" account. An annual bonus is 6400, temporary help is 6800, and the person is preserved separately as the Who.
- **Vendors are WHO, never accounts.** There is no Costco account, no Publix account.
- **Derived totals are calculations, never accounts.** Net Revenue, Gross Profit, Prime Cost, EBITDA, Operating Profit and Net Income are computed from the hierarchy; creating a posting account for any of them would let a total be posted to.

### 16.2 How it reaches every environment

Migration `b8d3f1a72c64` seeds it. An ordinary `alembic upgrade head` — the deployment this repository already performs — installs the catalog in a fresh or production database with **no manual SQL and no spreadsheet upload**, and with no startup work that could rewrite data on every request.

The migration reads the version-controlled CSV and writes with SQLAlchemy Core, deliberately not through the ORM: a migration must keep working against the schema of its own revision. The general-purpose importer (§15.1) remains the validated path for an operator's own upload, and `seed_canonical_accounting_catalog.py` uses it for databases migrated before the catalog existed.

Idempotent and non-destructive: a code already present with the same name is left untouched; a code present with a **different meaning FAILS LOUDLY** and nothing is overwritten, because an account that historical decisions reference by code must never be silently redefined. Downgrade removes only the seeded accounts still untouched — anything renamed by a human, or referenced by a Why or a decision, is kept.

### 16.3 Deterministic recognition, and what is refused

A rule exists only where the description itself carries the accounting meaning. `FOREIGN TRANSACTION FEE` is a fee whatever else is true; `COSTCO` is a shop that sells food, cleaning supplies, equipment and office paper.

Recognised deterministically: foreign transaction fees (7230), bank service charges (7220), merchant processing fees (7210), interest credited (8100), and the balance-sheet movements that must never reach the P&L — internal transfers (1110), credit-card settlements (2500), sales-tax remittances (2200) and loan advances (2600).

**Refused by name**: Costco, Sam's Club, Instacart, Amazon, Publix, Cheney Brothers, Prime Line and the other mixed suppliers. A payment to any of them says who was paid, not what was bought; the invoice carries the composition (§15.5). That a vendor was *usually* classified one way in a spreadsheet is evidence for a human, not a rule.

**Unknown is REVIEW_REQUIRED.** 6900, 7880, 8500 and 8600 exist for genuine residual cases and are never an automatic fallback — no rule may target them.

A loan advance uses the 2600 group rather than 2610/2620: the description does not say whether the term is short or long, and inventing one would be worse than leaving it for a person.

### 16.4 Historical Kermali cost types

21 of the 48 historical cost types map deterministically onto the canonical chart (Accountant → 7610, Bank Costs → 7220, Products-Food → 5100, Products-Wine → 5230, Sales Tax → 2200, Tips → 2300, …). The rest are reported with the reason rather than guessed — `Company Cars` does not say lease, fuel, insurance or capital purchase; `Incoming` says money arrived, not what it was; `Personal Deductable` asserts a tax treatment RF-One must not invent; `Payroll - FOH` identifies the 6100 family but not regular versus overtime, which needs payroll detail.

### 16.5 What the model still cannot say

Three properties of the approved chart have no queryable field on `BankAccountingClassification`. They are recorded here rather than worked around with a second accounting model:

- **`node_type`** — GROUP versus POSTING. Derived as "a classification with children is a group", which is true of this catalog but is a structural coincidence rather than a stated fact.
- **`contra`** — 1590, 4910 and 4920 belong to their parent's subtree but subtract from it. A subtree sum cannot know this, so Net Revenue is computed with an explicit contra list.
- **`review_sensitive`** — the catalog says in prose that 6900/7880/8500/8600 are never an automatic fallback; nothing enforces it at the model level.

None of the three blocks this work. Each is a candidate for a small additive column when the reporting layer is built.

## 17. Historical instrument candidates — evidence identity (BANK_HISTORICAL_SOURCE_CONTROL_FOUNDATION_001 → BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_IDEMPOTENCY_001)

A **historical instrument candidate** (`bank_historical_instrument_candidates`) is an account or card the evidence names but the Payment Instrument registry does not contain. It is discovered either DIRECTLY (a source file whose own identity matches no instrument) or INDIRECTLY (another account's transaction text refers to it, e.g. "Payment to Chase card ending in 0246"). A candidate never creates a `PaymentInstrument`, never receives a lifecycle date from its evidence span, and stays unresolved until a person chooses CONFIRMED_INSTRUMENT, SOURCE_FILE_MISSING, CLOSED/LOST/REPLACED/OTHER or NOT_OUR_INSTRUMENT.

### 17.1 Candidate identity + evidence set → deterministic state

Every piece of evidence is stored once, with a **stable key**, in `bank_historical_instrument_candidate_evidence`:

- a preserved raw bank row is `raw:<RawBankTransaction id>` — the same row processed again is the same evidence;
- evidence that is not a row (a whole source file, a summary) is keyed by its own description, dates and declared count.

The candidate's figures are **recomputed from that set**, never accumulated:

- `occurrence_count` = distinct canonical `FinancialTransaction`s evidenced + the declared occurrences of evidence not tied to a transaction. Several raw copies of one transaction (overlapping downloads) count once;
- `first_seen_date` / `last_seen_date` = minimum / maximum observed date — source boundaries only;
- the raw evidence count and the canonical transaction count are read from the set.

Consequences: re-running discovery over the same history changes nothing; a new download that only repeats a known transaction adds a raw evidence row and no occurrence; a genuinely new transaction adds exactly one occurrence and may widen the span. A human resolution is never touched by discovery.

### 17.2 What counts as a reference

Only explicit account/card phrasing (`… card ending in NNNN`, `… account xxxxNNNN`). Trace numbers, order references, check numbers and balances are never read as accounts. A reference whose last four matches any registered instrument, whatever its status, is not a candidate. An institution is recorded only when the text names one that the registry already uses.

## 18. WHO recognition from the bank's own text (BANK_HISTORICAL_WHO_RECOGNITION_001)

Recognition is an earlier, separate fact from the reconciliation decision: what the bank's own text proves about the counterparty. It is stored in `bank_who_recognitions` (one row per transaction and recognizer version, migration `c6a2e8f41d93`) and never in `bank_transaction_explanations`, because a decision row repoints `FinancialTransaction.explanation_id` and presents the row as reviewed. Every spelling a WHO was recognised from is preserved in `bank_occurrence_aliases`.

Four tiers: **DETERMINISTIC** (a proven structure names the counterparty — Chase Zelle recipient before the bank reference, ACH originator field, fixed-width merchant fields, card descriptors), **PROPOSED** (a name whose boundary is not proven — an operator decides), **UNRESOLVED** (the text names nobody, or an unregistered account) and **STRUCTURAL** (the counterparty is RF-One itself: a registered instrument, one of its legal entities, a card settlement received). Only DETERMINISTIC creates a `BankOccurrence` (CHECK-enforced). Two spellings are one WHO only on an identical normalized key; store numbers are kept. A WHO is linked to a Supplier only on an exact normalized name. Recognition carries no WHY, no role and no beneficiary. Runner: `apply_who_recognition.py`.

## 19. Deterministic structural WHY (BANK_HISTORICAL_DETERMINISTIC_WHY_EXPERTIZATION_001)

`bank_reconciliation/structural_why.py` decides WHY only where the transaction's own text, read with the instrument registry, proves it (DETERMINISTIC) or provider structure strongly determines it while an ownership question stays with Economic Allocation (STRONG_STRUCTURAL). Everything else is UNRESOLVED with a named family and reason. The rules are versioned code (`why-v1`), not `bank_recognition_rules` rows — a recognition rule always names a WHO, and a description rule may never decide purpose (schema CHECK `ck_bank_recognition_rule_purpose_scope`). Each result is an ordinary RULE decision created through the one decision-row function, so WHAT / the Balance Sheet destination is derived from the WHY; no allocation is written; a HUMAN decision is never overwritten. Runner: `apply_structural_why.py`.

Transfers are split by ownership: two accounts of the same legal entity → INTERNAL_BANK_TRANSFER; two different legal entities → RELATED_PARTY_TRANSFER_OUT / _IN (INTERNAL_BANK_TRANSFER, "between the company's own accounts", would be false); a personal instrument on either side → unresolved. A card payment settles the card only when the paying account is that card's settlement owner.

## 20. Reconciliation Control Start (BANK_RECONCILIATION_CONTROL_START_DATE_001 → BANK_ACTIVATE_CONTROL_START_001)

One configurable value, `bank_reconciliation_control_configs.control_start_month` (single row, `YYYY-MM`), names the **first controlled month**. A mid-month date is refused, never rounded. Nothing is seeded or inferred: with no value, no month is controlled automatically.

- **Before the start (historical):** transactions are imported and kept; no period is opened automatically, no missing account is demanded, nothing is certified. An operator's own historical period is left untouched.
- **From the start onward (controlled):** the existing period is reused or created, its coverage refreshed and its completeness evaluated — `get_or_create_period`, `refresh_coverage`, `evaluate`, via `monthly_source.bring_months_under_control`. A COMPLETE month is history and is not touched.

Months come only from `BankImportBatch.date_range_start` / `date_range_end`. The boundary is applied in two moments, through the same function:

1. **on import** — the months the new batch spans;
2. **on activation** (`monthly_source.activate_control_start`, used by the Monthly Sources screen and `activate_reconciliation_control_start.py`) — when the start is set for the first time or moved EARLIER, every existing non-rejected, dated batch is examined, so history already imported does not have to be uploaded again. Moving it LATER writes only the setting: no period, coverage, resolution or status is deleted or rewritten.

Opening a controlled month is not declaring it complete: missing accounts and files stay blockers, human resolutions stay authoritative, and absence of a source never closes an instrument.

---

## Open Points

- **Structural WHY — business rules not yet defined (§19), Product Owner decisions.** (a) Card-sales settlement deposits (merchant processor deposits) have no clearing / undeposited-funds WHY; mapping them to revenue would double-count POS sales. (b) `ADP Tax` debits are the whole payroll-tax impound (employee withholdings + employer share), so EMPLOYER_PAYROLL_TAX (6500) alone is not correct without the payroll register. (c) Transfers between a personal instrument and an LLC account: member contribution, loan, draw or reimbursement. (d) An LLC paying a card owned by another owner. (e) Card-issuer late / annual fees: 7220 or a dedicated account. (f) Whether `FLA DEPT REVENUE C01` may be treated as sales-and-use tax. (g) Confirmation that LLC↔LLC online transfers are RELATED_PARTY_TRANSFER (current STRONG_STRUCTURAL reading) rather than contributions or fees.
- **Own trade names are not registered.** Card purchases at the business's own restaurant name the brand as merchant; without a trade-name registry linked to legal entities they remain an external WHO.

- **Placement inconsistency with `Purchased/README.md`.** `01 Domains/Shared Domains/Purchased/README.md`, section "Bank Reconciliation boundary," currently describes Bank Reconciliation as belonging to "the consuming Business Domain" — implying a Business-Domain-owned capability. This document instead places Bank Reconciliation as a transversal Shared Domains / Administration capability (per explicit placement instruction for this task), consistent with how Payroll, Invoice Intake, and Purchased itself are positioned as reusable-across-industries Shared Domains. This is a genuine, unresolved wording/ownership inconsistency between the two documents. It is not resolved here and `Purchased/README.md` is not modified by this task — it requires an explicit Product Owner decision.
- **Duplicate legacy folder — historical, now resolved.** At the time this document was originally written (on the Financial Model Convergence integration branch, before main integration), a second, older `01 Domains/Cross Domain/Administration/` folder still existed alongside the canonical `01 Domains/Shared Domains/Administration/` used by this document. That duplicate no longer exists: the canonical Shared Domains structural migration (completed on `main` independently of this document) retired `01 Domains/Cross Domain/` entirely before this document was integrated here. This document was written under `Shared Domains/Administration/Bank Reconciliation/` from the start, so no path adjustment was needed at integration time.
- **Financial Account Registry — data model resolved (§11.6), content still owed by the Product Owner.** The registry is the canonical `PaymentInstrument`, now fully editable from the web interface including its Company/Legal Entity (§11.6). What remains open is unchanged and is data, not design: the Company/Legal Entity and the identifying last four of each account/card in §6 are still not known or invented here, and automatic recognition of a Chase source (§11.1 step 3) cannot work for an instrument whose last four has not been filled in.
- **~~File-name-based card resolution is explicitly disallowed (§3.2) but no alternative mechanism is designed.~~ Resolved — see §11.1.** The "configured import source" is the ordered evidence chain in §11.1: the file's own identifier, then a rule a human explicitly confirmed, then a `Chase####` file-name prefix matched against a **configured** last four. The file name remains non-authoritative exactly as §3.2 requires — it never resolves anything on its own and is always overridden by in-file content.
- **~~The Kermali P&L / Balance Sheet plan has not been supplied.~~ Resolved by decision — see §16.** RF-One no longer waits for it: it defines its own canonical chart, seeded by migration `b8d3f1a72c64`. Kermali may map QuickBooks onto it later without changing RF-One's semantics. What remains open is the mapping itself, and the 27 historical cost types listed in §16.4 that are not deterministic.
- **Three accounting properties have no field on the model — see §16.5.** `node_type`, `contra` and `review_sensitive` are derived, listed or stated in prose rather than stored. None blocks classification; all three matter once P&L reporting is built, and each is a small additive column when that happens. §15.1's importer is in place, but the plan itself is not in this repository. `Bank/RfBank.xlsx` sheet `Lists` holds a flat 48-entry cost-type vocabulary and a 134-entry Supplier/Receiving list with no statement type, no codes and no hierarchy — not a chart of accounts. Until the real plan is supplied the What catalog stays empty, and no transaction can be classified, because a Why cannot exist without a What. Assigning a statement side to those 48 cost types is a Product Owner decision and was deliberately not taken.
- **The fixed chart of accounts is not defined here.** §12's `BankAccountingClassification` is the STRUCTURE the approved chart of accounts will be loaded into — codes, names, statement side and hierarchy — and deliberately contains no real account tree. Loading the approved chart is a data task, not a schema change. Until then, the only What rows that exist are those a human created and those the hierarchy migration recovered from existing Kermali `what_label` values. **Those migrated rows are explicitly INCOMPLETE: they carry no `statement_type`, because a Kermali label does not say whether it is a Profit & Loss or a Balance Sheet line, and inventing one was refused.** They are shown as incomplete on the Classification tab, and a month containing a transaction still classified against one of them is blocked from export until the statement side is set — one edit per migrated What. This is a deliberate, visible gap awaiting a Product Owner decision, not a defect.
- **Two genuinely separate identical charges on one day are indistinguishable under the accounting key — open.** The key is settlement account + posting date + signed amount + normalized payee, by explicit Product Owner decision. It therefore cannot tell one $1.04 `FOREIGN TRANSACTION FEE` from a second, genuinely separate $1.04 `FOREIGN TRANSACTION FEE` posted the same day to the same card: it treats them as one accounting fact and suppresses the second. This is not hypothetical — QA verification against the already-imported Chase files found exactly such a pair (Freedom ··2915, 2026-08-13, two rows of −$1.04). Small repeating per-transaction fees are the realistic case. The mitigation that exists today is §8's per-instrument human review: marking such a row `CONFIRMED_DISTINCT` keeps it in accounting and outranks the automatic key (§13.5). Whether the key should additionally consider a distinguishing element for this case is a Product Owner decision and is deliberately not taken here.
- **~~Deduplication/equivalence-check logic is not designed.~~ Partly resolved — see §13.3.** The ACCOUNTING deduplication key (settlement account + posting date + signed amount + normalized payee) is now specified and implemented, and it deliberately does not replace §8's per-instrument candidate-duplicate review, which remains a separate, human-judged mechanism with its own five conditions. What is still not designed is any scoring or fuzzy matching: both mechanisms are exact-match only, by design.
- **Relationship to Invoice Intake / Purchased / Purchasing remains unspecified**, beyond the negative boundary stated in §2.2–§2.3 (a bank movement is not an invoice, and no association mechanism is designed here). Designing that association is explicitly out of scope for this task.
- **Automated bank feeds are out of scope.** This document covers manual CSV download/import only; whether and how an automated feed (e.g. bank API/aggregator) might later coexist with or replace manual CSV import is not addressed.
- **Future correlation between an operational payment and `FinancialTransaction` — Product Owner decision recorded, not designed here.** Operational Domains (e.g. Restaurant/Tips, Clover POS) may in the future want to know that a payment they instructed has actually settled in the bank. Any such correlation must be **connector-neutral**: the intended conceptual chain is RF-One operational instruction → configured payment connector → provider/external transaction identity → observed canonical `FinancialTransaction`. The connector may supply provider transaction identifiers/provenance that later help correlation, but Bank Reconciliation must never encode Mercury-specific or Clover-specific payment semantics, and an operational domain must never build a competing financial ledger of its own. **Current state:** the existing HUMAN Occurrence/Reason reconciliation (and Phase 6B's automatic Bank↔Bank/PayPal internal-transfer matching, both above) remain the valid mechanism until a generic automatic correlation is specifically designed. No schema, FK, or correlation model is chosen by this note — it only records the boundary a future design must respect.
