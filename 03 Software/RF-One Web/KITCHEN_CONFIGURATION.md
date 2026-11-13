# Kitchen Configuration

## Recipe Type extension — 2026-11-10

The Product Owner requested a sixth expandable section, Recipe Type, initially
populated with the exact stored names `Ricetta` and `Preparazione`. It reuses the
same add/edit/archive service and account permissions as the other configuration
lists. Migration `e7a820261110` extends the section constraint; the local setup
script inserts missing initial values without overwriting existing records.
Existing recipe `kind` values and Components remain unchanged. The English page
and its contextual How Works include the new section. Its values retain the
Italian names explicitly supplied by the Product Owner.

Approved request, 2026-11-10: add a local Configuration page with five initially
collapsed rows: Menu Type, Menu Area, Category, Components, Supplier. Each row
expands to a list supporting addition, name editing and non-destructive archival.
Continue the existing English Kitchen UI, account tab access and contextual help.

The first four lists are shared Kitchen configuration values (name and active/
archived status). They do not create a second purchasing Ingredient identity or
automatically classify existing recipes. Initial creation did not seed data.
Supplier reuses Purchasing's `suppliers` and preserves its restaurant ownership;
new suppliers require a restaurant, renaming preserves the previous name as an
alias through the existing repository, and Archive sets the existing INACTIVE
status. Other consumers of that supplier see the same changes.

New table: `kitchen_configuration_items`; Alembic revision `e6f720261110`.
Case/compatibility-normalized names are unique per section, including archived
rows. Supplier duplicate checks include aliases within the same restaurant.
Blank and oversized names are rejected. No record is deleted.

New Kitchen item grant: CONFIGURATION. Both reads and writes require the existing
Kitchen grant and this permitted tab (or existing ALL scope). The approved local
administrator preview exception remains loopback-only; no grants are persisted.
All writes use the existing RF-One CSRF control. Changes commit in the canonical
local database, not browser storage. Page and sections retain position/focus after
save, cancel or archive. How Works documents the actual inline form flow.

## Approved Excel population — 2026-11-10

The Product Owner subsequently requested population from Cartel1.xlsx and
explicitly assigned its Suppliers to both Winter Park and Mount Dora.
`import_kitchen_configuration_excel.py` maps BasicData H → Menu Type (5),
G → Menu Area (22), I → Category (21), A → Components (282 distinct values)
and E → Supplier (42 names, 84 restaurant-owned records). The duplicate
L-Water-Sparkling-500ml is represented once, with both source cells retained in
the import audit. Whitespace-only H14 is excluded. Source labels, including
non-food components and generic supplier labels, are retained without inferring
classification or renaming companies.

Imports preserve existing/archived rows, match normalized names and Supplier
aliases, and reject ambiguous matches. After commit, a second lookup verifies
that all requested values exist and would be skipped on a repeated import.
The source hash, exact cells/original labels and target IDs are recorded in
`output/kitchen-configuration/excel-import-both-committed.json`.
Existing 255 recipes, 1,381 recipe component rows, 246 notes and two Menu cards
are unchanged. No UI behavior or How Works change is required for data population.

## Approved Components cleanup — 2026-11-10

The Product Owner subsequently requested keeping all F- entries and only those
other entries used in a recipe, stripping the first two characters from retained
names and removing the remaining configuration entries. Applied result: 183 F-
entries plus 13 other recipe-used entries retained and renamed; 86 unused entries
removed; 196 Components remain. Original recipe references and quantities are
unchanged. Only the Components configuration list was modified.

`clean_kitchen_components_local.py` compares typed ingredient/preparation
references and original E/F recipe source cells. It uses the original import
mapping to avoid stripping names twice, refuses name collisions or intervening
edits, and checks hashes of recipe tables, Menu links/photos/cards, suppliers and
other configuration lists before/after the transaction and again after commit.

Audit: `output/kitchen-configuration/components-cleanup-committed.json`.
Pre-change backup (all original Components rows/IDs):
`output/kitchen-configuration/components-before-cleanup-b35974a93047.json`.
Restoration uses those rows for section COMPONENT only, preserving other lists;
it requires an explicit restore task. Do not rerun the original raw Excel import
without accounting for this later approved cleanup, which supersedes its names
and inclusion rules for Components. How-Works: data-only change; controls unchanged.
