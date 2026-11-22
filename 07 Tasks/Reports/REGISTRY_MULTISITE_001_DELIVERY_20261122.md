# REGISTRY_MULTISITE_001 — delivery for independent review (Codex)
## Round 2 — Codex review fixes (review range `8efaba0..HEAD`)

The Codex review report file was not found in the repository; the four findings were taken from the Product
Owner's command of 2026-11-22.

| # | Finding | Fix | Evidence |
|---|---|---|---|
| 1 | Tips: a Clover re-read/correction could move a resolved attribution | `ingest.keep_resolved_attribution` in `upsert` and `acquisition._get_or_create`: `employee_id` / `override_in_employee_id` / `override_out_employee_id` already set are never replaced; NULL stays attributable | `test_registry_multisite`: order of A → POS ID correction → reimport → old ID to B → reimport: order and payment stay A's, new order of B is B's, NULL order attributable later; shift re-read likewise. Both tests fail without the fix |
| 2 | Training created the card before resolving identity | `employee_directory.resolve_training_card` (no write) before arrival, Trainee mark, person, card or invitation; certain = linked card, or one card with the same email and no different phone; uncertain → `CardConfirmationRequired` (`card:<id>` / `card:new`); a card linked to another person is refused. Selection path: `_arrival_source` checks, arrival written after resolution. Invite page: «Is this the same person as an existing Registry card?» | manual WP card with phone and no email + MD invitation with the same phone: asked, nothing saved; confirmed → same card gets MD; repeat → same identity, one live invitation; Selection path: arrival not recorded until confirmed, repeat refused, release `already`; HTTP test of the page |
| 3 | Confirm Hire without a card | card required before EMPLOYEE/event; otherwise error flash, nothing saved; Students shows «Trainee without a Registry card» + **Resolve card and site** (new page, same Training entry rules, no invitation; How Works registered) | HTTP: no card → 302, error, no status/events, no success flash; legacy Trainee → card+site → hire confirmed with HIRE_CONFIRMED on the card |
| 4 | Alembic conflict, exact EMPLOYEE list, rollback | release order a1c2 → b2c3 → **c7d8 (final)** → c4d5 later (re-parented in `rfone-wt/rf1-shared-acquisition`, uncommitted there); c7d8 skips TRAINING_LINK Trainees; `compare` enforces added == expected; `registry_multisite_rollback.py` (plan/detach/reattach); workers never back to `:12` | `registry_multisite_rollback_rehearsal.py`: ALL EXPECTATIONS MET (old code checkout `acd44b2`); AWS data copy: expected `[]`, added `[]`, final `c7d820261122`; with c4d5: one head, up/down |

Also found while re-running the validators (they could not run before `8efaba0` because of the duplicate-column
error): the Historical Backfill still read `/employees?expand=role` to write the cards' Clover roles, and the
staff list was a pre-flight source. Both removed (spec §3: no path reads Clover's staff list for Registry).
Validator fixtures updated to record POS IDs on cards (no staff-list import).

| Validator / suite | Result |
|---|---|
| `test_clover_acquisition.py` | SUCCESS 60/60 (incl. «staff list never read») |
| `test_clover_correction_sync.py` | SUCCESS 69/69 |
| `test_clover_acquisition_safety.py` | SUCCESS 35/35 (Employees-denied scenario removed: list not read) |
| `test_clover_acquisition_jobs.py` / `test_clover_live_sync.py` / `test_historical_backfill_extractor.py` | SUCCESS 36/36, 29/29, 29/29 |
| Data Store unittest set (registry_multisite 22, employee_directory, person_foundation, registry_departments, clover_multisite, identity_record_holds, tips_registry_only, training_release_arrival, employee_history, monthly_recovery) | 94 OK |
| RF-One Web `tests.test_registry_multisite_http` 6, `tests.test_registry_training_http` 5, `test_training_release_http` 4 | OK |
| `test_restaurant_profile_bootstrap.py`, `test_sales_validation.py` | SUCCESS |

Open: the Server Course self-invitation (`training_server_course.py`, `enroll.issue` without a site) is refused
since `e8a44b5` because the Training entry needs a site; not changed (outside these findings).


Branch `feature/registry-multisite` (local, not pushed). Review range: `acd44b2..HEAD`.

| Commit | Content |
|---|---|
| `4ab0b04` | Unchanged port of the uncommitted OQ-7 / Selection → Training work of `feature/clover-multisite-registry` (release step 1, arrival confirmation step 2). Reviewed separately by Codex on 2026-11-22 §3; included because Send to Training depends on it. |
| `e8a44b5` | The new Registry (code, How Works, tests, migration `c7d820261122`, read-only check script). |
| `45da94f` | Specification record, release/switch-over plan, this delivery note. |
| next | Duplicate-column fix in `k9g120261112` (idempotent steps) and PostgreSQL migration evidence. |

Base choice: `feature/clover-multisite-registry` already holds the site selector, the central per-site
authorization, Registry-only Tips roles and the OQ-7 work Training needs; its old Clover → Registry parts
are removed in `e8a44b5` rather than carried. The release branches (`release/registry-*-20261121`,
`release/clover-multisite-*-20261121`) were used to establish the live schema (`a1c220261121`) and chain.

## Points to verify

1. Site list = current explicit `EmployeeAssignment` (restaurant, or a location of the restaurant) only —
   `employee_directory.site_employee_ids`; no fallback (`role_profile_routes.registry_site_view`,
   `employee_directory_routes.employee_directory_home`).
2. Manual entry requires site + role (an assignment needs a role: schema `restaurant_role_id NOT NULL`);
   duplicate by email/phone refused → add the site to the existing card.
3. Training: `enrollment.issue` now requires the training site and role (Training operator's reachable
   sites, `site_selection.account_restaurant_ids(..., 'TRAINING')`); creates or reuses the card
   (`employee_directory.training_card`): linked card first, else the single unlinked card with the same
   email; a direct invitation now creates the person and marks Trainee at invitation time (previously at
   activation). `people_registry.company_statuses` no longer derives EMPLOYEE from a card link.
4. POS ID: `employee_directory.set_pos_id` — site assignment required, site must have a Clover location,
   unique per merchant, correction detaches the old ID (state CORRECTED) and attributes only NULL work.
5. Removed: `import_snapshot`, `attach_link`, `observe_historical_employee`, `candidates`, review/conflict
   helpers, `registry_clover.py`, `_registry_clover.html`, the two Anagrafica routes, `sync_site`,
   correction-sync staff-list refresh and roster-only MD path, acquisition historical identity reader.
   `identity_holds.pending_external_ids` now derives waiting IDs from unattributed work.

## Tests (local, disposable databases)

| Suite | Result |
|---|---|
| Data Store, all 98 modules, new vs base `4ab0b04` | identical results except the removed obsolete cases; new `test_registry_multisite` 16/16 OK |
| Updated: employee_directory 15, person_foundation 11, registry_departments 9, clover_multisite 5, identity_record_holds 6, tips_registry_only 9, training_release_arrival 10, employee_history 4, monthly_recovery 3 | all OK |
| RF-One Web new: `tests.test_registry_multisite_http` 6, `tests.test_registry_training_http` 2 | OK |
| RF-One Web `test_training_release_http` | 4 OK |
| `tests.test_employee_directory_http` | chain now upgrades; its setUp still downgrades to `d5a120261021`, which irreversible later migrations (`t9e120261113`) refuse by design — pre-existing, not changed |
| Migration on AWS data copy and on the full local copy | see release plan §6 — fingerprints identical |
| Full chain from empty (after the k9g fix) | SQLite: reaches head. PostgreSQL: real chain to `a1c220261121`, AWS rows loaded, `b2c3`+`c7d8` up/down → identical |
| How Works | RF-One Web / Registry / Training: same errors as base (all inherited), +2 pages with help |

## Known limits / decisions to confirm

- Role at the site is required for every entry (manual and Training) because an assignment needs one; MD
  today offers only the shared roles Cook, Dishwasher, Server Help (WP roles are WP-only).
- Training UI and Training help stay in English as the existing Training pages are (no locale switch there).
- Mount Dora people can be entered and given POS IDs while the MD site is inactive; MD acquisition stays off.
