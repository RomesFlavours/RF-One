# Live Visual Menu

## Dish card layout

2026-11-10: compact photo first on desktop (340px), full content width at tablet
and phone sizes (up to 1100px). Separate sections follow in order: direct recipe
components without quantities; allergens including nested preparations;
nutritional profile; dish description; characteristics/curiosities; sales phrases.
Missing content is explicit. Recipe quantities and batch weights are not shown.
Trainer phrase editing remains below the reading sections. Shared help matches
the layout and role. All recipe data continues to be read live.

## Independent module and audiences

2026-11-10: Visual Menu is registered directly by RF-One Web, independently of
Kitchen. `_visual_menu_base.html` displays Visual Menu as the module title and
RF-One > Visual Menu navigation. Kitchen remains only the recipe/photo provider.

The trainer edits `description_phrases` and `sales_phrases` in the existing
restaurant card JSON. Writes use CSRF and optimistic content-version checks;
conflicts preserve the draft and restaurant cards remain independent.

Shared access is derived from linked Training trainer/student identities or
the enabled MYRF application grant. Assigned trainees and MyRF users only read;
Kitchen grants are irrelevant. `/training/visual-menu` and `/myrf/visual-menu`
enter the same module. The local administrator previews trainer or MyRF views
without login; shared access checks remain server-side.

Training content slug `visual-menu` is registered once in the existing catalog
and assignment picker. Assigned consultation opens the live module, with no
invented quiz or certification. It does not block assessments of other courses.

Approved scope, 2026-11-09: read Kitchen on demand; never duplicate components,
recipe details or derived allergens in Visual Menu. English UI, source references
hidden, two restaurant-specific cards for shrimp and pistachio fettuccine.

Routes: `/visual-menu/<restaurant_id>/<dish_key>` (HTML), `/data` (JSON), `/photo`.
All three use the same Training/MyRF audience authorization; they do not require
Kitchen access. No saved grants are added. Responses use `Cache-Control:
no-store`. The HTML uses the existing shared modal help and registered section.
Sources, costs and raw Excel payloads are not exposed. No Kitchen write occurs
on GET. Exact restaurant/dish links determine the recipe; no name guessing.

The reader recursively expands preparations, detects cycles and missing links,
and derives positive allergen evidence from ingredient names. It never asserts
absence, product-label completeness or cross-contact safety. Broad ingredient
labels need specification checks. Preparation batch quantities are labelled and
never presented as served-portion quantities. Active work is not waiting time.

The existing shrimp/pistachio reference photo was moved into Kitchen-owned
`RF-One Data Store/data/kitchen/photos/D125/`. Both restaurant links select the
Kitchen photo record. The Menu-owned image was removed after hash verification
and transaction commit. There is no fallback to a Menu-owned file. Kitchen photo
replacement is visible on the next request. Plating validation remains pending.

`visual_menu_local.py` runs the shared shell with automatic local access on port 5097,
using the existing canonical local PostgreSQL connection and persistent Web key.
It creates no database, migrations or access grants. At the Product Owner's
explicit request, local launchers sign in automatically as the existing active
`rfone` operator, for loopback clients and the loopback database only. The existing
administrator can open Kitchen/Visual Menu locally without saved Domain/item
grants; no grants are written. Shared/production Domain/item rules are unchanged.
No username/password prompt is required. This local
runtime does not deploy to AWS. Local HTTP cookies follow the existing local
shell convention; production cookie configuration remains unchanged.

Checks: `test_visual_menu.py`, `tests/test_visual_menu_http.py` and the existing
Kitchen HTTP suite. The global How Works scan reports 25 unrelated pre-existing
coverage/missing-template errors; the new card and help are registered.
