# Kitchen — inactive or connected-but-unused inventory (2026-11-17)

Read-only survey of the local main checkout (branch `handoff/2026-10-17`) and the
canonical local PostgreSQL (`127.0.0.1:55436/rfone_aws_copy`, Alembic heads
`k9f120261112`, `t9d120261113`). Since 2026-11-16 AWS Kitchen runs the same code
and data (see release memo), so these findings are assumed to hold on AWS too;
AWS itself was **not** queried. Nothing was changed, removed or disabled.

## 1. Code present but never called

| Item | Evidence |
|---|---|
| `RF-One Data Store/rfone_data_store/kitchen_english.py` | No import anywhere in the repository (translation map used once for the 2026-11-10 English release). |
| `RF-One Data Store/visual_menu_english.py` | No import anywhere. |
| `visual_menu.read_card` (legacy card reader) | Only `populate_recipe` is imported by `visual_menu_active.py`; `read_card` is reached only by tests/old scripts. |
| Legacy Visual Menu routes `/visual-menu/<restaurant_id>/<dish_key>[/data,/photo,/phrases]` | Resolve through `kitchen_visual_menu_links`, which is empty → always 404. |
| `/training/visual-menu`, `/myrf/visual-menu` | Not linked from any page except the MyRF Domain tile and a Training course lesson URL; work only as redirects. |
| Visual Menu files inside the Kitchen AWS image | `kitchen_cloud.py` does not register `visual_menu_routes`; the Dockerfile copies them anyway. Visual Menu on AWS is served by the Training entrypoint (`training_cloud.py`). |

## 2. Pages that exist but have no content

| Item | Evidence |
|---|---|
| Kitchen **Dashboard** tab (`/kitchen/dashboard`, `kitchen_dashboard.html`) | Template is 3 lines (help section only), no `kitchen_content` block. It is also the first tab, so `/kitchen` lands on an empty page. |

## 3. Database structures that are empty or unused

| Table / column | Local state |
|---|---|
| `kitchen_recipe_steps` | 0 rows (editor reads/writes it; no data). |
| `kitchen_visual_menu_links` | 0 rows (emptied on 2026-11-16, "Visual Menu to be revisited"). |
| `restaurant_menu_cards` | 342 rows (171 per restaurant) with no link to any recipe → orphaned editorial cards. |
| `kitchen_menu_entries.recipe_id` | Always NULL: the only active menu "WP- Winter" has 3 entries (Caprese Buffalo Mozzarella, Campari & Goat Cheese, Prosciutto & Cantaloupe) not linked to recipes → Visual Menu home shows no card. |
| `kitchen_configuration_items.location_id` | Always NULL. |
| `kitchen_recipes` columns never populated and not exposed in the UI | `dietary_class`, `dietary_evidence`, `appearance`, `aroma`, `taste`, `texture`, `serving_temperature`, `organoleptic_notes`, `portion_count`, `portion_weight_g`, `ingredient_weight_g`, `cooked_yield_g`, `currency`, `nutrition_basis`, `validated_at`. |
| `kitchen_recipes` columns used by code/UI but always NULL | `category_id`, `description`, `actual_work_minutes`, `elapsed_preparation_minutes`, `total_cost`, `cost_per_kg`, `kcal`/`protein_g`/`carbohydrate_g`/`fat_g`/`cholesterol_mg`, `plating_instructions`, `validated_by_id`. |
| `kitchen_recipe_components` | `notes`, `cost`, `cost_per_kg` and all nutrition columns always NULL. |
| `kitchen_recipe_photos.captured_at` | Always NULL. |

## 4. Configuration values defined but not used

| Item | Local state |
|---|---|
| Menu Areas | 22 defined, only 1 used by a menu entry; 21 unused (Salads, Pasta, Dessert, Pizza Personal, Beverages, Wines…). |
| Components | 203 defined, 34 not used in any recipe. |
| Recipes without plating photo | 153 of 215. |

## 5. Access configured but not used

| Item | Local state |
|---|---|
| Kitchen item-level grants (`SELECTED` scope) | Supported in code; no rows in `rfone_account_domain_item_access`. Grants: accounts 15 and 16, scope `ALL`. |
| MyRF Domain grant (Visual Menu "server" role) | No account has `MYRF`; works locally only through the local-admin preview. |

## 6. One-off tooling (not runtime)

Local preparation/import scripts in `RF-One Data Store/` (`create_kitchen_local.py`,
`prepare_*_local.py`, `import_kitchen_*.py`, `import_visual_menu_local.py`,
`clean_kitchen_components_local.py`, `prepare_visual_menu.py`) and release scripts in
`Infrastructure/deploy/rfone-kitchen/` (`publish_content.py`, `upgrade_release.py`)
were used for past imports/releases and are not invoked by the application.

## 7. Not decided here

Whether to remove, hide or complete any item above is a Product Owner decision.
