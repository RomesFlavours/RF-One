# TIPS_LEGACY_ENGINE_RETIREMENT_001 — Implementation Report

Scope: retire the legacy, experimental, Payment-level Tips calculation engine
(`rfone_data_store/tips/engine.py`, `TipPolicy`) now that the canonical,
Order-level Tip Distribution Engine (`rfone_data_store/tips/
distribution_engine.py`, `TipDistributionRule`) is implemented and
validated. Per the Product Owner decision stated in the task: the Order-level
engine is now the ONLY canonical Tips calculation engine; the old engine
must not remain as an alternative runtime path.

---

## 1. Legacy components found (dependency inventory)

A full-repo dependency sweep (code, migrations, docs, templates) was run
before any deletion. Summary:

**Confirmed legacy-only (safe to delete):**
- `rfone_data_store/tips/engine.py` — the engine itself.
- `rfone_data_store/tips_validation.py` — its synthetic-fixture test suite.
- `test_tips_engine.py` — its test runner.
- `calculate_tips.py` — CLI entry point (dry-run/persist).
- `validate_tips_readiness.py` — read-only readiness-report CLI against
  real data.
- `configure_rome_flavours_tip_policy.py` — CLI that wrote Rome's Flavours'
  real `TipPolicy`/`TipPolicyComponent` rows.
- Model classes `TipCalculationRun`, `TipAllocation`, `TipCalculationIssue`
  (the legacy engine's own result tables).

**Confirmed SHARED — explicitly NOT removed:**
- `rfone_data_store/tips/rounding.py` (`equal_split`) — used by the
  canonical `distribution_engine.py` too.
- `rfone_data_store/tips/resolvers.py` (`ServiceAttributionResolver` and
  friends) — used by `sales_validation.py` (Sales domain, unrelated to
  either Tips engine) and, until this task, by
  `organization_validation.py`/`profile_validation.py`.
- `rfone_data_store/tips/policy_bootstrap.py` — mixed file: its
  `earliest_tip_evidence_at` helper is used by the canonical
  `seed_tip_distribution_rules.py`; only its
  `configure_location_tip_policy`/`ComponentSpec`/`PolicyBootstrapResult`
  write path was legacy-only.
- Models `TipPolicy`/`TipPolicyComponent` — see §4, real historical data.

**Blocking dependencies found and resolved (the most important finding of
the inventory):** `rfone_data_store/organization_validation.py` and
`rfone_data_store/profile_validation.py` — two UNRELATED domain validation
suites (Organization/TASK_ORGANIZATION_002 and Restaurant Profile
bootstrap/TASK_RESTAURANT_003) — each called the legacy engine's
`run_tip_calculation` as one of their own cross-domain regression checks.
Deleting `tips/engine.py` outright would have broken both suites. See §5.

## 2. Files removed

- `rfone_data_store/tips/engine.py`
- `rfone_data_store/tips_validation.py`
- `test_tips_engine.py`
- `calculate_tips.py`
- `validate_tips_readiness.py`
- `configure_rome_flavours_tip_policy.py`

## 3. Files modified

- `rfone_data_store/models.py` — `TipPolicy`/`TipPolicyComponent` kept but
  re-documented as LEGACY/NON-CANONICAL/READ-ONLY; `TipCalculationRun`/
  `TipAllocation`/`TipCalculationIssue` classes removed entirely; the same
  three names removed from the `ALL_MODELS` registry tuple (which would
  otherwise `NameError` at import).
- `rfone_data_store/tips/policy_bootstrap.py` — stripped to only
  `earliest_tip_evidence_at`; the legacy `TipPolicy`-writing function and
  its supporting dataclasses/mode constants removed.
- `rfone_data_store/organization_validation.py` — its cross-domain
  "Location-scoped EmployeeAssignment eligibility" check rewritten against
  the canonical engine (see §5).
- `rfone_data_store/profile_validation.py` — its "bootstrap doesn't invent
  a policy" check rewritten against the canonical engine (see §5).
- `03 Software/Tips/app.py` — stale module docstring (referencing the
  deleted `calculate_tips.py`/`tips/engine.py` and predating the
  TIP_DISTRIBUTION_ENGINE_001 UI work) corrected to describe current
  reality. No route/behavior change — `app.py` never imported the legacy
  engine in the first place.
- `PROJECT_STATE.md` — the single "Tips:" status bullet updated; it
  previously described only the legacy `TipPolicy` as production-ready with
  no mention of the canonical engine at all. Left `01 Domains/Business
  Domain/Restaurant/Tips/*.md`, `RESTAURANT_PROFILE.md`, and `Roadmap.md`
  untouched — these are deeper Domain/onboarding documents whose full
  reconciliation is out of this cleanup task's scope; flagged below.

No other file required a code change. Numerous files (migrations,
`payroll/adp_importer.py`, `payroll/payment_execution.py`,
`profile/bootstrap.py`, `sales_validation.py`, `distribution_engine.py`
itself) contain doc-comment mentions of the legacy engine as historical
narrative or "mirrors X's pattern" style references — left as-is, per "do
not refactor unrelated code."

## 4. Database-table decision

Read-only inspection of the real operational database
(`03 Software/RF-One Data Store/data/rfone.db`) before any schema change:

| Table | Row count |
|---|---|
| `tip_policies` | **1** |
| `tip_policy_components` | **2** |
| `tip_calculation_runs` | 0 |
| `tip_allocations` | 0 |
| `tip_calculation_issues` | 0 |

**Mixed outcome, handled per-table as the task's decision tree implies:**

- **`tip_policies` / `tip_policy_components` — contain real historical data**
  (Rome's Flavours/Winter Park's actual approved policy, written by the
  now-deleted `configure_rome_flavours_tip_policy.py`). Per task §4: tables
  **preserved**, models kept (re-documented LEGACY/NON-CANONICAL/READ-ONLY),
  all runtime write paths removed (the only writer,
  `configure_location_tip_policy`, is deleted along with its CLI), no
  migration touches them, and no historical row is reinterpreted.
- **`tip_calculation_runs` / `tip_allocations` / `tip_calculation_issues` —
  confirmed empty / experimental-only.** Per task §4: models removed, and a
  new additive migration drops these three tables outright. No data is
  lost.

**The real operational database itself was NOT migrated by this task** —
only inspected (read-only `SELECT COUNT(*)`) and the migration file was
created and tested against disposable databases only, per task §8's "do not
touch operational DB during automated tests." Note for the Product Owner:
because `03 Software/Tips/app.py` (like every other entry point in this
repository) calls `run_migrations_to_head()` against the real database at
startup, the next time the Tips app (or any other script pointed at the real
`data/rfone.db`) runs, this migration will apply automatically and drop the
three empty tables — this is the repository's existing, intentional
self-migrating convention, not a new behavior introduced here, but worth
knowing before the next real run.

## 5. Runtime paths retired

- **Legacy calculation entry points removed**: `calculate_tips.py` (CLI),
  `validate_tips_readiness.py` (CLI), `configure_rome_flavours_tip_policy.py`
  (CLI) — all deleted.
- **No legacy UI/routes/buttons existed to retire** — confirmed by
  inspection that `03 Software/Tips/app.py` and its templates only ever
  imported `clover_import_service`/`distribution_engine`/
  `distribution_rule_service`; there was no legacy `/calculate-tips`-style
  route wired to `tips/engine.py`.
- **Two blocking cross-domain checks rewritten** (not simply deleted, since
  each asserted a still-valid cross-domain safety property):
  - `organization_validation.py`: "an Employee whose only matching Role
    Assignment is Location-scoped is not silently excluded from Tips
    eligibility" — previously exercised via a `TipPolicy`
    `ROLE_PRESENT_AT_PAYMENT` component + `run_tip_calculation`; now
    exercised via a dedicated `TipDistributionRule` (Source Role held by a
    new, isolated Employee who owns the Order; Recipient Role held by the
    existing Location-scoped Employee) + `distribution_engine.
    run_tip_distribution_calculation`, asserting the Location-scoped
    Employee still receives an allocation.
  - `profile_validation.py`: "bootstrapping real EmployeeAssignments does
    not itself invent a Tips calculation policy" — previously asserted via
    `TipCalculationIssue.issue_type == NO_VALID_POLICY`; now asserted
    directly and, if anything, more simply: zero active
    `TipDistributionRule`s exist for the fresh Restaurant, so the canonical
    engine's `rules_applied` count is 0 and zero
    `TipDistributionAllocation` rows are produced for the test Order.
  - Both replacements required no new production code — only test-fixture
    changes — and both were built with a NEW, dedicated `RestaurantRole`/
    `Employee`/`TipDistributionRule` scoped tightly enough (in one case, a
    tightly-bounded rule effective window; in the other, reliance on the
    existing fixture's Shift-presence exclusivity) to avoid interference
    from the rest of each file's large, shared fixture — the same lesson
    already documented in `TIP_DISTRIBUTION_ENGINE_001.md`'s own test
    design.
  - One incidental fix needed to make both replacements pass: both files'
    own `_dt()` helper returns **naive** UTC datetimes (their established,
    documented convention), while `distribution_engine`'s period-bound
    comparisons require timezone-aware values (SQLite round-trips
    `DateTime(timezone=True)` as offset-naive, and the engine normalizes its
    *Settlement Time* side of the comparison to aware UTC accordingly). Each
    call site now passes `_dt(...).replace(tzinfo=UTC)` for its two period
    bounds only — the rest of each file's fixture data is untouched and
    stays naive, matching its existing convention. This is a call-site fix,
    not a change to `distribution_engine.py` itself (left untouched, per
    the task's explicit "do not modify the canonical Distribution Engine
    behavior").

## 6. Tests removed / replaced

- **Removed** (legacy-only, no replacement needed — they tested the
  retired engine's own internals): `rfone_data_store/tips_validation.py`,
  `test_tips_engine.py`.
- **Replaced in place** (shared cross-domain assertions redirected to the
  canonical engine, same file, same suite): `organization_validation.py`,
  `profile_validation.py` — see §5.
- **Untouched**: `test_tips_clover_import.py`, `test_tips_import_
  concurrency_guard.py`, `test_tips_distribution_rules.py`, `test_tips_
  distribution_engine.py` — these already exercised only canonical code and
  needed no change.

## 7. Migration

New additive, forward migration:
`migrations/versions/e2c7b4a9f1d6_drop_legacy_tip_calculation_tables.py`
(`down_revision = d8f3a6c1e9b4`, the prior head — now the new head is
`e2c7b4a9f1d6`). Drops `tip_allocations` and `tip_calculation_issues`
(children) before `tip_calculation_runs` (parent, self-referential FK), per
FK dependency order. `downgrade()` recreates all three tables' exact
pre-migration shape (verified: upgrade → downgrade → re-upgrade all succeed
cleanly against a disposable database). No historical migration file was
modified. `tip_policies`/`tip_policy_components` are untouched by this or
any migration.

## 8. Static search result (task §6)

Full-repo grep after all deletions/edits:

- `tips.engine` / `tips/engine.py`: **zero real imports remain anywhere** —
  every remaining hit is a doc-comment/docstring mention (historical
  narrative, "mirrors X's pattern," or this task's own explanatory
  comments in `models.py`/`organization_validation.py`/
  `profile_validation.py`/`distribution_engine.py`/`policy_bootstrap.py`).
- `TipCalculationRun`, `TipAllocation`, `TipCalculationIssue`: **zero code
  references remain** (class definitions removed; `models.py` imports and
  runs cleanly) — only doc-comment mentions remain, all explicitly noting
  these classes were removed.
- `TipPolicy`/`TipPolicyComponent`: remain only as their (explicitly
  preserved, read-only) model class definitions in `models.py` plus
  doc-comment mentions elsewhere — no runtime write path references them
  anywhere in the codebase.

## 9. Regression results

All required suites, run against disposable databases only:

| Suite | Result |
|---|---|
| `test_tips_clover_import.py` | 38/38 |
| `test_tips_import_concurrency_guard.py` | 15/15 |
| `test_tips_distribution_rules.py` | 24/24 |
| `test_tips_distribution_engine.py` | 29/29 |
| `test_organization_validation.py` (directly affected — blocking dependency fixed) | 14/14 |
| `test_restaurant_profile_bootstrap.py` (directly affected — blocking dependency fixed) | 14/14 |
| `test_purchasing_engine.py` (shared-schema sanity check, since `models.py`/migrations changed) | 24/24 |

Migration verified in both directions (upgrade to head, downgrade one step,
re-upgrade to head) against a disposable database — all clean. No test
suite touched the real operational database.

## Confirmation

Only the canonical Order-level Tip Distribution Engine
(`rfone_data_store/tips/distribution_engine.py`, reading
`TipDistributionRule`/`TipDistributionRuleVersion`) remains as an active
Tips calculation runtime path in this codebase. The legacy Payment-level
engine (`tips/engine.py`) and its CLI entry points no longer exist. Its
result tables (empty) are dropped by migration; its configuration tables
(real Winter Park data) are preserved read-only, clearly marked, with no
remaining write path.

## Follow-ups flagged, not acted on (out of this task's scope)

- `01 Domains/Business Domain/Restaurant/Tips/*.md` (README, Tip Policy.md,
  Tip Allocation.md, Tip.md), `03 Software/RF-One Data Store/
  DATABASE_SCHEMA.md` §4b, `RESTAURANT_PROFILE.md`, and `01 Domains/
  Business Domain/Restaurant/Roadmap.md` still describe the legacy
  `TipPolicy` model as the (only) Domain-level Tips implementation
  reference, with no mention of the canonical `TipDistributionRule` model.
  A full documentation reconciliation across these was judged out of scope
  for a "cleanup and retirement" task (would require touching several
  Domain-authoritative files well beyond the runtime code this task
  targets) — flagged here per this report's own "do not hide unresolved
  contradictions" obligation, left for a dedicated documentation task.
