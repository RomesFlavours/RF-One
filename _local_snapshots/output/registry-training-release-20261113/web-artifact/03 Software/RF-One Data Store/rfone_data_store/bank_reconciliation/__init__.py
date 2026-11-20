"""Bank Reconciliation (Shared Domains / Administration) — manual CSV
import and normalization vertical slice only.

Scope is exactly BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001
("01 Domains/Shared Domains/Administration/Bank Reconciliation/
BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md"): Chase and First
Citizens manual CSV download, full preservation of the received file,
normalization into the canonical `FinancialTransaction` ledger, and
duplicate/overlap detection. No connector, no invoice matching, no
general ledger.

Canonical Financial Model Convergence — Phase 3
(FINANCIAL_MODEL_CONVERGENCE_001): normalization targets the canonical
`PaymentInstrument`/`FinancialTransaction` models. The Kermali `.xlsx`
Monthly Accountant Export and Supplier/Receiving classification
(`BankTransactionExplanation`) are NOT part of this package on this
branch — both are structurally dependent on the Recognition/Explanation
model, which Phase 3 explicitly excludes; they are deferred to the phase
that ports Recognition.
"""
