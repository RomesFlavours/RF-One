# CLOVER_MULTISITE_001 — fix of the blocking issues of the Codex audit (2026-11-21)

Integration branch `feature/clover-multisite-registry`, local commits only (no push, no deploy, no
merge). Release branches unchanged. Migration `b2c320261121` extended, still **not applied** on AWS.

## Commits

| Issue | Commit | Content |
|---|---|---|
| A. Concurrent preparation / finalization | `88ce52a` | `tips/money_lock.lock_restaurant` (PostgreSQL `SELECT … FOR UPDATE` on the restaurant) in preparation, approval, save, validation, automatic finalization, calculate-now; partial unique index: one OPEN cycle per restaurant; entitlement linked only while unlinked |
| B. Durable record before the provider call / C. Retry | `9be3033` | `tip_payment_submissions` committed before every call; PENDING/UNCERTAIN = awaiting reconciliation, never resent; retry only after a verified failure, with authority, authorized amount and recipient, new key |
| D. Recipient change + CSRF | `e36ee82` | authority `TIPS_MANAGE_RECIPIENTS`, Registry site check, refusal while awaiting reconciliation, `tip_payment_recipient_changes`; CSRF token on Tips financial POSTs |
| E. Shifts and roles | `736fbed`, `9862153` (approved) | Registry assignments only, resolved Shift Location; Clover import never writes assignments |

## Verification

- Concurrency, PostgreSQL 18.3, two independent connections (`test_tips_payment_concurrency_pg`, 6/6):
  manual + automatic preparation → one cycle, each entitlement once; with the lock disabled the database
  guards still refuse the second cycle; overlapping finalizations → one FINAL; person + scheduler
  approving → one approval, 3 provider calls for 3 instructions; two retries of one failed payment → one
  new attempt; the restaurant lock is held by one transaction at a time.
- Provider accepted then answer lost (timeout) → attempt UNCERTAIN, instruction OUTCOME_UNKNOWN, retry and
  re-approval refused, exactly one transaction at the provider. Provider accepted then local crash before
  the outcome commit → attempt PENDING and instruction SUBMITTING survive (committed before the call),
  retry and recipient change refused, exactly one transaction.
- Migration `a1c220261121 → b2c320261121 → a1c220261121 → b2c320261121` on PostgreSQL: OK (5 tips_payment
  tables, both partial unique indexes).
- Regression (Registry, Clover, Tips, Compensation, permissions, WP/MD): 65 files, 209 unittest cases;
  3 failing files, all failing identically on the live web code (test schema of other Domains).

## F. Winter Park historical amounts

In memory, read-only, on the canonical local AWS copy (snapshot **2026-11-12 01:03 UTC**), every FINAL
WP run (7, 9–14) recalculated with the current engine and compared employee by employee with its stored
entitlements:

| Comparison | Result |
|---|---|
| Rules as recorded on each run (`rule_version_ids`) | runs 7, 9–13 identical; run 14 identical except an extra all-zero row (Matthew Arrowood) |
| Rules as they are today | totals identical, per-employee differences in every run |

The differences come only from the historical Tips rules, not from this change: rule 3 was deactivated
and, by the known defect (`RULE_DEACTIVATION_RETROACTIVE_DEFECT.md`, TIPS_RULE_END_OF_VALIDITY_001
excluded), disappears from past periods; rule version 4 (effective 2026-11-08) was created after run 14
was calculated. Not corrected here. Stored results were not modified.

## Open points

1. **Reconciliation of an UNCERTAIN/PENDING attempt.** The provider connector can read a transaction
   by its id but cannot look one up by idempotency key, and an uncertain attempt has no transaction id.
   Resolving it needs a decision on the mechanism (connector lookup by key/memo, or a person's
   recorded verification). Until then such a payment stays blocked: never resent, never retried.
2. Fresher WP data: the local copy is from 2026-11-12; FINAL runs created on AWS after that date were not
   compared. Needs authorization for a read-only refresh into a separate disposable database.
3. Release branches and release plan to be updated before any release.
