# Historical Tip Payments

## 1. Purpose

An imported payout document is evidence of historical tip payments to named recipients for stated periods. It does not establish POS-collected tips, daily allocations, a calculation rule, or a new obligation to pay. User request: reconstruct the historical Tips view from the supplied Chase activity PDF, preserving Bank and existing consolidated periods.

## 2. Source and identity

Persist immutable document observations using the existing SourceSystem, IngestionRun and SourceRecord provenance facilities. Use a dedicated CHASE_PDF source, never CLOVER. Identity is document SHA256 plus physical parsed row ordinal; identical displayed payments at different ordinals remain separate observations. Reimporting the same document is idempotent. A changed document is a distinct import and must not be automatically added to the same total as an overlapping document.

Keep amount in integer USD cents, recipient text, payment send date, status, literal memo, source page and earnings-period interpretation. A unique exact normalized employee name within the restaurant may resolve the recipient. Ambiguous or missing names remain unresolved; no fuzzy match, invented employee or trial classification is allowed. Periods crossing year boundaries are retained without apportionment. Unusual periods and duplicate-looking entries are explicitly flagged.

## 3. Tips boundary

Only Completed observations explicitly labelled Tip/Tips with a complete earnings period inside the requested scope contribute to the reported historical paid total. Other explicit tips and unclear observations remain visible with their classification. Pay and blank memos cannot silently become tip facts.

These observations never create or update TipDistributionCalculationRun, TipEntitlement, TipPaymentCycle or TipPaymentInstruction. They never advance payment readiness, trigger an executor, validate/finalize a period, change existing employee identities, or modify Bank. Historical payment evidence is displayed separately inside Tips; the ordinary calculation and finalization controls remain unchanged.

## 4. Review and controls

The Tips historical-payments view selects one document at a time and shows per-person totals, source references, unresolved identities and questionable observations. It is authenticated through the existing RF-One login. Imports use a transaction and document-specific concurrency lock on PostgreSQL. Reimport verifies every stored payload rather than overwriting existing observations. Compare protected tip-table fingerprints and the local Bank checksum before and after the authorized import.
