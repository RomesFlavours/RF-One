# REGISTRY_MULTISITE_001 — delivery for independent review (Codex)

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
