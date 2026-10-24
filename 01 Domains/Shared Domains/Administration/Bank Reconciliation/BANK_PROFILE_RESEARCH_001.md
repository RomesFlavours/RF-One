# Bank shared WHO research and recognition profile editing

## 1. Approved behavior
One engine and the same modal serve recognition-profile editing and every reconciliation row. Profiles start with a known WHO; rows start with the transaction description. Public research proposes WHY and WHAT only from Configuration. The human reviews sources and selects catalog entries; unavailable or uncertain research exposes the same lists for manual choice. Multiple WHY/WHAT values require explicit conditions inside one profile.

## 2. Domain meanings
WHAT uses canonical_catalog.what_catalog, the official active Profit & Loss posting vocabulary. Balance Sheet control accounts are not WHAT; a settlement WHY can keep its linked accounting destination with no P&L WHAT. WHOM is the Source owner, resolved through row_reconciliation.default_for_whom/card settlement ownership on the transaction date. An explicit HUMAN allocation overrides that default. Unknown ownership and split allocations stay for review.

## 3. Persistence and safety
Research and choice selection write only the conversation. Preview shows original and proposed real-row values. Save for future updates the same profile and its sourced knowledge; existing rows are unchanged. Save and apply to repository updates that same profile and the previewed rows, with guarded rollback. Changed records remain REQUIRES_REVIEW so the human can adjust WHOM before confirming; already-correct confirmed rows are retained. Profile identity is resolved by canonical WHO/aliases and existing profile rule ID. A concurrent new or changed profile invalidates the preview rather than creating a copy. Existing legacy profiles can be upgraded in place; researched Source profiles supersede their old legacy cases for the same WHO.

## 4. Shared implementation and UI
bank_profile_research is used by profile research, per-row research and background reconciliation research. The review row embeds the actual Rules modal rather than maintaining a second editor. Save returns to the same row and restores position/focus; cancel returns without applying. The new UI remains English.

## 5. Validation
Eight targeted tests cover both entries and both final actions, unchanged record counts for profile updates, new WHO creation once, legacy profile upgrade, Source/manual WHOM, WHAT persistence, multi-WHY branch rules, unavailable research/manual fallback, invalid catalog IDs, stale transactions, Balance Sheet semantics, nested profile flow and compare-safe rollback. A public-name-only live web smoke test returned verified sources and a catalog proposal. Browser validation on synthetic data exercised profile research, catalog selection, preview, future save, per-record modal, repository save, return to the same row and unchanged profile count.

## 6. Traceability
No production rules or profiles are created or applied during deployment. Deployment includes source/database backups, changed-file manifest, verification JSON, screenshots and REPORT.
