# Defect: deactivating a Tip Distribution Rule rewrites history

Status: **open — documented, not fixed** (Product Owner, 2026-11-21: document and propose, do not implement in this intervention).

## Observed

- `TipDistributionRule.is_active` is an undated flag.
- `calculate_tips` reads `distribution_rule_service.list_rules(..., active_only=True)` and therefore ignores an inactive Rule for **every** period, including periods in which its versions were effective.
- The Tips UI exposes the flag directly: `POST /distribution-rules/<id>/toggle-active` (`Tips/app.py`) calls `set_active` with no date, no confirmation of historical impact, and no check against FINAL calculation runs that used the Rule (`tip_distribution_calculation_runs.rule_version_ids`).

## Consequence (proven on AWS, 2026-11-21)

Rule #2 (Host 10%, order-open eligibility, effective from 2026-09-14) was deactivated after Rule #3 was created on 2026-11-11, while its version still had no end date. Every recalculation of September–early November then gave the Hosts 0 and the Service Owners 100%. The stored FINAL runs 7, 9–12 were reproduced exactly only after restoring Rule #2 in memory. The data were corrected by closing version 3 at `2026-11-08 09:00 UTC` (04:00 America/New_York, the business-day cutoff) and reactivating Rule #2.

Stored FINAL runs, entitlements and payments are not affected (they are never recalculated automatically), but any recalculation, review or audit of a past period shows a different distribution.

## Proposed protection (not implemented)

1. **Deactivation = end of validity.** Replace the undated toggle with "end this rule from <date>": it closes the effective version (`effective_to`, business-day boundary via `effective_business_date_boundary`) instead of hiding the whole Rule. `is_active` stays only for rules that never governed any moment.
2. **Guard on history.** Refuse the toggle (or require the dated path) when any version of the Rule overlaps a period already covered by a CALCULATED/FINAL run, naming those runs.
3. **Engine independence from the flag for the past.** Select rule versions by effective window only; the flag must not remove a version from a period it governed.
4. **Test.** A FINAL period recalculated after deactivating its Rule must still equal the stored entitlements.
