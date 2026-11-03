# REPORT

## 1. Result

Reconstructed a payment-based tip ledger directly from the Chase PDF, independently of Clover amounts or allocation rules. The earnings scope remains January 1–October 4, 2026. Literal memo periods wholly inside that scope contain 325 completed Tip/Tips rows, grouped into 319 person/period entries, totaling USD 253,490.62. This includes USD 1,027.89 for the recipient absent from the prior Clover reconstruction.

These are recorded paid tips, not inferred earned tips or daily allocations. Prior reconstructed names supply only zero-payment display rows; they supply no monetary values or role assumptions.

## 2. Separate evidence and scenarios

| Evidence | USD | Treatment |
| --- | ---: | --- |
| Explicit completed tips wholly within scope | 253,490.62 | Main literal PDF total |
| Extra occurrences of exact date/name/amount/memo repetitions | 269.44 | Retained and flagged |
| Hypothetical total if exact repetitions counted once | 253,221.18 | Sensitivity only; not a confirmed correction |
| Explicit tips crossing December/January | 5,512.73 | Separate, not apportioned |
| Explicit tip without complete earnings period | 140.37 | Separate pending period clarification |

Three identical repetitions concern different recipients. Other multiple payments for a common period are retained even when amounts differ. The PDF has no transaction IDs, so neither deletion nor confirmation of distinct settlement is justified.

Blank memos, Pay, marketing and other payments are not inferred as tips. Nonstandard memo intervals remain literal and flagged rather than silently changed into standard weeks. The cross-year payments cannot establish the amount paid specifically for January 1–4.

## 3. Verification and protection

Re-extracted all 47 source pages: 700 rows, zero unparsed records. Every row has one category: 325 in scope, seven crossing the boundary, one explicit tip with unclear period, 22 outside scope, 332 completed without an explicit Tip label, and 13 not completed.

Verified the source PDF SHA256 against the prior comparison. Independently reconciled the total to the preceding mapped tip total plus all eight previously unmapped tip payments. Ledger, grouped period and person totals agree exactly in integer cents.

Bank bytes remained unchanged across the operation. No database connection or write occurred. Existing Clover reconstruction and consolidated tip data were not modified. Outputs are private and already covered by the reconstruction folder's ignore rule.

## 4. Interpretation and limits

This ledger can serve as the evidence of tips paid through the displayed Chase activity. A payment date is not an earnings date; the memo controls attribution. Missing PDF payments do not prove nonpayment through other channels. Weekly payment totals do not identify daily earned tips, host hours or the historical allocation rule. No unresolved memo was assigned by matching its amount to Clover.

## 5. References

- Source: `C:/Users/servi/Downloads/Payment Activity - chase.com.pdf`.
- Private per-person and per-period view: `output/tips_reconstruction_2026/chase_tip_reconstruction.html`.
- Complete classified ledger, source hash and checks: `output/tips_reconstruction_2026/chase_tip_reconstruction.json`.
- Helper: `tmp/reconstruct_tips_from_chase_pdf.py`.
- Previous comparison for independent reconciliation: `output/tips_reconstruction_2026/zelle_comparison.json`.

Preserve the PDF and generated ledger together. No database restore is needed.
