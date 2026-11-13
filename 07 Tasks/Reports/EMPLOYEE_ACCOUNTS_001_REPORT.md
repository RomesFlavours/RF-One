# EMPLOYEE_ACCOUNTS_001 — Employee Directory and RF-One accounts

Product Owner decision, 2026-11-02. Branch `feature/employee-directory-accounts`
(worktree `AI-RF-ONE/rf-one-employee-accounts`), based on
`feature/how-works-standard` (6d08519) plus the released record-level identity
holds (59246b0, cherry-picked as 72d9f61). **Not released to AWS.**

## 1. Rules implemented

| Rule | Implementation |
|---|---|
| Positions WP/MD separate; one site ends only its position | `employee_directory.employment_states`: a position = the person's confirmed links at one site; ENDED only when all are `MISSING_REVIEW` from that site's latest complete roster |
| Person ceases only with no active position | status `CEASED` derived; `CEASE` event at the transition |
| Cessation date = last clock-in, even without clock-out | per site: max `Shift.clock_in` at the site; overall: max over every Shift of the person |
| Absence only from a complete, successful import | changes happen inside `import_snapshot` (complete-only, same transaction); sites never imported (MD) and empty rosters end nothing |
| No punches → not an employee, no account | pending names without held clock-ins/outs are a technical observation; "new person" refused; link to an existing person allowed |
| No automatic association; several POS records per person | unchanged explicit approval; multiple links per person kept |
| One account per employee, one employee per account | unique `rfone_account_id` (existing) + partial unique index on `employee_id` (migration `f1a220261102`); service refuses a second account |
| Cessation keeps person/account/history, disables access incl. sessions | account `INACTIVE` + `session_version` + 1; `account_for_session` refuses non-ACTIVE accounts in every app |
| Site-only cessation never touches access | access rule applies only to `CEASED` |
| External accounts | accounts without person link; never affected |
| Dismissis, selectors, history | ceased + manually archived in collapsed Dismissis; `employee_options` excludes ceased by default; historical selectors and stored references unchanged |

## 2. Verification

See the final task REPORT in the session for the complete results; summary:

- `test_employee_accounts.py` (20 tests): every verification requested by the Product Owner.
- Existing directory, person foundation, identity holds, schema chain tests updated to the new rules.
- Employee Directory HTTP tests: 13 (3 new: account from employee, session end and reactivation guard, How Works).
- Clover worker release check on an LF export: `CLOVER_RELEASE_VERIFIED`, 36 tests, artifact verified, no DB writes.
- How Works check: 0 errors (4 pages moved from `help_missing` to `pages`).

## 3. Real data (AWS snapshot 2026-11-02 14:35 UTC, revision e0a120261101)

Read-only consistent dump (temporary security-group rule for this PC, authorized by
the Product Owner and revoked immediately), restored into a disposable local
database, analysed with `employee_accounts_analysis.py`, migration rehearsed, then
the database and dump were deleted. No AWS write, no Clover write.

| Finding | Count |
|---|---:|
| People / Clover links / accounts | 64 / 67 / 6 |
| Active employees (WP) | 23 |
| Ceased (all positions ended; last clock-in 2026-03-08 → 2026-10-11) | 13 (2 without a name) |
| Confirmed people without punches (shown as "not employees") | 28: 26 absent from Clover with no 2026 work, 2 present (Emilia, Giuseppe Miraglia) |
| Pending names with punches (queue) | 3 (Rosas C., Louth T., Arrowood M.: 4/1/2 held shifts) |
| People with more than one account (would block the migration) | 0 |
| Accounts directly linked to a person | 0 → all 6 accounts are external today |
| Account reaching a person only through Training | 1 (`tatiana ceban` → Tatiana Ceban) |
| Accounts that would be disabled | 0 |

Migration `e0a120261101 → f1a220261102`: index created, 11 controlled tables
unchanged (row content hashes). Simulated first poller cycle on the real roster:
no position, cessation or access event. Acquired Shifts start 2026-01-02, so
earlier employment cannot be dated: such people are kept, not ceased, and leave
current selectors once all their Clover records left the rosters.
