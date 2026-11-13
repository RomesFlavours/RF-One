# REPORT

## 1. Outcome

Compared the 22 reconstructed tip recipients against the user-provided Chase PDF. Produced private per-person totals and every supporting PDF payment, retaining memo, page, status and classification. No Bank writes or database connections were made; its physical hash was unchanged during the comparison.

## 2. Observed totals and comparable scope

| Measure | USD |
| --- | ---: |
| Reconstructed January 1–October 4, weekly rounded | 259,827.95 |
| January 1–4 reconstruction, separated | 5,893.61 |
| Reconstructed January 5–October 4 | 253,934.34 |
| Completed explicit Tip payments wholly within January 5–October 4 | 252,462.73 |
| Difference on that comparable period | 1,471.61 |
| Explicit Tip payments crossing December/January, not apportioned | 5,512.73 |
| Unclear memo/type or period, across reconstructed recipients | 5,536.21 |

The difference is reconstructed minus documented explicit tip payments. It is provisional, not a certified debt or overpayment. The full-period difference before separating January 1–4 is 7,365.22 USD and is not a like-for-like settlement balance. Individual weekly rounding adds five cents relative to exact Clover gross.

## 3. Classification and uncertainty

Only Completed PDF entries explicitly marked Tip/Tips and with a parseable period wholly inside the reconstruction are counted as comparable paid tips. Payment send date does not determine earnings period. Pay/marketing/other transfers, rejected or pending entries, and tips for periods outside scope are separated. A single-date tip memo is retained as uncertain period, not silently discarded.

Cross-year December–January payments are not proportionally allocated without evidence. One cross-year payment without an explicit Tip label remains unclear rather than being inferred from its size. Empty memos and malformed years are also retained for clarification.

Some recipients have multiple PDF rows for the same earnings period, including three exact date/amount/memo repetitions in September. All are retained and flagged. The PDF contains no transaction identifiers, so these rows cannot certify that distinct bank transactions occurred or establish duplication. No automatic deduplication was applied.

Eight explicit Tip entries belong to a recipient absent from the reconstruction. They remain separately listed, without treating that person as a trial or assigning the money to another employee. This is an unresolved gap for a complete reconciliation.

## 4. Verification and changes

Re-extracted all 47 PDF pages: 700 records, zero unparsed payment rows, 687 Completed, 11 Rejected and two Pending. These totals include late 2025 and October 2026 entries, not only the comparison period. Visually inspected a source page containing blank memos and multiple same-period payments; inspected complete text of pages showing September repetitions.

Assertions passed: reconstructed totals match the saved calculation; every mapped completed payment belongs to exactly one monetary category; no noncompleted payment contributes to paid totals. Bank bytes remained unchanged. All calculation and source files remain intact. The only new outputs are a comparison helper and private JSON/HTML reports; the existing reconstruction was not changed.

## 5. Limits and next decisions

Resolve unclear causals, December–January splits, possible duplicate PDF rows and the recipient absent from reconstruction before using differences as amounts due. No modifications were made to Bank, source employees, payroll or consolidated tips. This compares evidence in the PDF, not bank settlement independently verified from Chase or Bank records.

## 6. References

- Source: `C:/Users/servi/Downloads/Payment Activity - chase.com.pdf`.
- Private per-person report: `output/tips_reconstruction_2026/zelle_comparison.html`.
- Private evidence and input hashes: `output/tips_reconstruction_2026/zelle_comparison.json`.
- Prior reconstruction: `output/tips_reconstruction_2026/reconstruction.json` and `TIPS_DAILY_RULE_RECONSTRUCTION_2026_20261019.md`.
- Readonly comparison helper: `tmp/compare_zelle_tips_2026.py`.

No database recovery is required; preserve the PDF and reconstruction alongside the comparison evidence to reproduce the result.
