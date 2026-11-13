# Kitchen recipe storage

## DishPrep-List catalog alignment

2026-11-12: the Product Owner designated Food.xlsm / DishPrep-List as the
classification authority: left list = dishes, right list = preparations.
The duplicate Farro Salad entry is processed once; Actual Work Time is excluded.
All 171 distinct dish entries and 102 preparation entries now have matching
records. Twenty missing entries were created as pending metadata-only records;
no compositions or elapsed durations were invented.

Recipe identities were matched through the corresponding DB-Recipes source block
and preserved, keeping all 63 photo records and 1,381 component rows unchanged.
Work minutes use the Time column or Actual Work Time evidence in DB-Recipes;
cached zeroes from empty source cells are not treated as confirmed work time.
Unknown source times preserve existing values. The resulting catalog has 237
records with work minutes, 173 dish rows and 102 preparation rows. The two
historical Asparagus Lemon Butter records and the unlisted unnamed source-row-418
record remain; no historical data was silently merged or deleted.

Source extraction, identity mapping, recovery snapshot and results are in
`output/kitchen-dishprep-alignment/`. Source identity includes workbook hash,
worksheet and row so similarly numbered rows on the two sheets are distinct.
The workbook was read only; no AWS writes occurred.

## Preparation times in Edit

Product Owner request, 2026-11-12: recipe and preparation Edit modals maintain
active labour person-minutes (`actual_work_minutes`, existing data retained)
and total elapsed preparation minutes (`elapsed_preparation_minutes`, nullable).
They are independent, non-negative manual inputs; blank is unknown and zero is
valid. Elapsed time includes cooking, waiting and resting; summed person-minutes
can exceed elapsed time when several people work concurrently.

Work time is not a recipe component or preparation. Components no longer edits
it and cannot overwrite it. Pseudo-items named Actual Work Time are excluded
from recipe/preparation lists and component/preparation selectors, and rejected
as composition inputs. The local audit found none stored as component rows or
preparation records, so no food rows were deleted. The 235 existing populated
labour-time values were preserved exactly by migration `k9b120261112`.

Changing labour time clears outdated cached recipe cost totals while retaining
nutrition. Changing only elapsed duration does not change costs or nutrition.
The workbook remains untouched. Only the specific local migration was applied;
no production database or AWS deployment was changed.

## Approved Menu PDF photograph import

2026-11-12: the Product Owner approved all proposed associations in
`output/kitchen-photo-review/proposed-matches.json`. Imported 52 distinct
photographs into 62 existing recipe records, with 63 photo associations because
panna cotta has two topping photographs. Pizza formats share the same local
image asset while retaining separate recipe photo records. The existing
Shrimp/Pistachio reference was refreshed without creating a duplicate record.
The left panna cotta photograph is the primary preview; the other remains stored
as a topping variant. Future manual uploads retain the existing preview priority.

Files are stored under `output/kitchen-plating/menu-<source hash>/`; hashes,
source pages, record IDs and results are recorded in the review directory.
`before-import.json` preserves prior photo records, menu links and recipe
revisions for targeted recovery. Recipe content, components and nutrition were
not changed. Only recipe revisions advance when photographs are added/refreshed.
All writes were to the canonical local database; no AWS writes were performed.

The recipe list now displays a green check to the right of Plating when at
least one photograph exists. The list query and save responses expose the same
`has_photo` value, so the marker also updates immediately after saving an image.

## Recipe editor extension — 2026-11-10

Revision e8b920261110 adds nullable Category assignment, an optimistic revision
counter and an optional Components configuration FK. The shared Recipes and
Preparations editor uses existing recipe/composition/step identities and preserves
source evidence. Work minutes remain separate from ingredient weight. See
`../RF-One Web/KITCHEN_RECIPES.md` for behavior, validation and cache invalidation.

Approved by the Product Owner on 2026-11-09: prepare Kitchen storage for every
per-dish field in Cartel1.xlsx, organoleptic properties, vegan/vegetarian/standard
classification and future standard-plating photographs consumed by Visual Menu.
The initial task created storage only. The Product Owner subsequently authorized
the Excel import and clarified that the recipe catalog is common to all restaurants.

Kitchen is part of the existing canonical RF-One operational database, not a
second permanent database. Initial migration: `e4d520261110`, after `e3c420261109`;
shared-catalog correction: `e5e620261110` (applied while recipe tables were empty).
Metadata: `rfone_data_store/kitchen.py` (the existing SQLAlchemy Base).

| Table | Stored information |
|---|---|
| kitchen_recipes | Shared catalog: code/name, dish/preparation type, description, dietary evidence/class, appearance, aroma, taste, texture, serving temperature, sensory notes, plating instructions, portions, ingredient weight, cooked yield, work minutes, costs/currency, nutrition and its basis, source provenance and validation |
| kitchen_recipe_components | Ordered ingredient/preparation lines, original references, optional resolved shared preparation, quantity/unit, notes, line cost and nutrition, original row and payload |
| kitchen_recipe_steps | Ordered instructions, including rows without ingredient quantities, original source row |
| kitchen_recipe_photos | Multiple future photo assets, URI, hash, MIME type, caption, accessible description, origin and capture time |
| kitchen_visual_menu_links | Existing restaurant-specific Menu card → Kitchen recipe → selected standard-plating photo |

## Data rules and Excel mapping

- Configuration Menu Areas are shared across restaurant locations (Product Owner,
  current decision). Their names are globally unique, including archived records.
  A menu entry's recipe Category must match its Area name (case and whitespace
  normalized). The Recipe selector applies the same rule; labels need no recipe.
  Migration `k9e120261112` preserves Area IDs and menu entries while clearing the
  former location assignments.

- Recipes and preparations belong to one common catalog, not to a restaurant.
  Recipe code is globally unique. Both occurrences of duplicate source code D053
  are preserved separately as D053~ROW162 and D053~ROW962; the original code remains
  in payload. The uncoded/unnamed block becomes SOURCE-ROW-418 with an explicitly
  provisional label. These records remain pending; no duplicates are merged.
- Excel A/B line identifiers are preserved in component source keys and source
  payload. C/D map to recipe code/name; E/F to ingredient/preparation references;
  G to quantity (normally grams, but the Pr000 work row uses minutes); H to
  instructions/notes; I/J to cost and cost/kg; K:O to kcal, protein, carbohydrate,
  fat and cholesterol. P and any other original cells can be preserved in payload.
- Recipe and component `source_payload` preserve original formulas, cached
  values, errors, external references and unmapped cells as JSON. A future importer
  must serialize these explicitly. Source file/hash/sheet/row preserve traceability.
- Work-time rows must not become food mass or nutrient contributions. Keep their
  original line/cost evidence in payload and minutes in `actual_work_minutes`.
- Cached costs/nutrition are source observations, not independently verified
  calculations. Do not invent currency from the `$` label. Unknowns and formula
  errors remain null in numeric fields, retaining their raw evidence in payload.
  Cached zeroes are preserved as source observations, not interpreted as verified costs.
- Summed ingredient grams are separate from cooked yield and portion weight.
- `dietary_class` is nullable, or `vegan`, `vegetarian`, `standard`. Null means
  unknown; standard is an explicit classification, never a default for unknowns.
  Record evidence; do not guess dietary or organoleptic properties from the title.
- Validation starts pending. Validator references the shared acting identity;
  Kitchen introduces no separate identity register.
- Photos are external asset references; no files are copied or generated here.
  Standard photo selection is optional until photos arrive. Menu cards remain
  restaurant-scoped but may reference the same shared recipe. Composite foreign
  keys prevent selecting another recipe's photo.
- Visual Menu reads Kitchen through `rfone_data_store/visual_menu.py` at request
  time. The two restaurant-specific shrimp/pistachio cards link to shared recipe
  D125. Components, nested preparations, inferred allergens, sensory properties,
  portion/work fields and selected photo references are not copied into Menu.
  The HTTP reader uses no response cache and exposes no costs or source metadata.

## Excel import

`import_kitchen_excel.py` reads the existing local PostgreSQL configuration and
refuses remote hosts. Dry-run is default; `--persist` inserts all records in one
transaction, then verifies recipe/component/step counts after commit. Source hash
plus source row makes repeat imports skip already imported records. Existing code
conflicts from another source abort rather than overwrite. Preparation IDs are
resolved only for unambiguous source codes; unresolved references retain their text.
Complete source rows, formula text, cached values and external-link provenance
are preserved in JSON alongside typed fields. Work rows are excluded from food
components; their original data/costs stay in the recipe payload.

Validation: `test_kitchen_excel_import.py` imports the actual workbook into an
in-memory database and checks all 255 blocks/4,080 source rows, component and note
counts, work-time separation, null dietary classification, duplicate preservation
and repeat-import behavior. It never touches the canonical database.

How-Works: technical - database-only change; no page or interaction changed.

## Menu composition

Kitchen Menu (`/kitchen/menus`, item permission `MENU`) stores named menus in
`kitchen_menus` and ordered entries in `kitchen_menu_entries`. Each menu belongs
to one canonical Location. Entries use shared Menu Areas, and linked dish recipes must have the matching Category.
Only existing dish recipes can be linked; a null recipe reference denotes a text
label, never an inferred recipe. Menu names and entries are edited together with
CSRF protection and revision checks; a draft key makes creation retries safe.
Archived menus retain their entries and are read-only. Existing archived Areas
may be retained on their original entries. Areas are common to WP and MD. Recipe components, photos, categories and times
are not copied or changed. Migration: `k9d120261112`.

### Active menu per location

`kitchen_menus.active` is an explicit selection, separate from archival. New and
pre-existing menus start as drafts; migration `k9f120261112` does not infer a
winner. `activate()` atomically demotes the previous active menu at the same
location and activates the selected menu, with revisions and the Kitchen
transaction lock. A partial unique index enforces at most one active menu per
location; a check prevents active archived menus. Archiving clears activation.
Changing an active menu's location makes it a draft and does not replace the
new location's active menu. `active_for_location()` returns the selected menu
and entries, or None. Visual Menu now reads this selection live through
`visual_menu_active.py`, groups entries by Area, and exposes recipe cards only
while their entries belong to the active menu. Labels stay text. Current Kitchen
photo selection and recipe projection are reused without storing recipe copies. Existing account MENU access and CSRF
checks also protect activation.

### Visual Menu active-menu projection

`visual_menu_active.read_home/read_entry` are read-only. Location/entry URLs validate
active membership on every HTML, data and photo request. Legacy restaurant/card
URLs resolve only when their exact recipe link is in an active menu. No static
card list or draft menu is a fallback. Existing restaurant-specific phrases are
read through exact recipe links; trainer saves reuse their record or create only
phrase content and a recipe FK in the existing editorial tables. No recipe facts
or image files are copied into Visual Menu. Training and MyRF permissions remain
independent of Kitchen grants. No database migration or menu activation is
performed by this integration.

### Trainer dish-card management

`/visual-menu/manage` is a trainer-only workspace for presentation and sales
phrases, scoped to canonical Restaurant and Kitchen dish recipe IDs. It covers
all dish recipes, including future menus, and reuses the same editorial records
read by active Visual Menu cards. Only phrase fields are writable; recipe facts
and photographs stay read-only in Kitchen. Reads create no card records. Saves
use CSRF and optimistic content versions and preserve legacy phrase records.
Visual Menu home and dish pages have no editing forms for any role. In the Training course catalog, Descrizione opens the existing information
modal; Contenuti opens the trainer management page for Visual Menu. The title
and course entry `/training/visual-menu` open the read-only dish list for
consultation; MyRF also opens consultation. No schema migration,
account grants, course assignments or recipe facts change for this separation.

Trainer management starts with the full Kitchen dish catalog. Selecting a
Restaurant filters recipes to the union of that restaurant's menus; selecting
one of its menus narrows the list. Menu ownership follows current canonical
RestaurantLocation links and is validated on the server. All Kitchen dishes
restores the catalog while retaining the restaurant's phrase-editing context.
Without a selected restaurant, editing is disabled and phrase counts are unknown.
Labels and repeated menu occurrences do not create duplicate recipe rows.
