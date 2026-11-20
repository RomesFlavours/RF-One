# Kitchen page

## Reliable local opening

Double-click `Open Kitchen.cmd` in this directory, or run
`python open_kitchen_local.py`. It checks the real page on port 5097, starts the
existing loopback-only `visual_menu_local.py` launcher when necessary, waits for
the actual recipe workspace to respond and opens it in Microsoft Edge. It uses
the established canonical local database and automatic local operator session;
it does not create accounts, change grants or use a static preview. Server logs
remain in `output/kitchen-configuration`. `--verify` checks readiness without
opening a browser. Shared/production startup and authentication are unchanged.

## Recipes and Preparations editor — 2026-11-10

The Recipes shell described below is superseded by the approved implementation
in [KITCHEN_RECIPES.md](KITCHEN_RECIPES.md): two expandable lists, shared name/
Category dialog and a composition dialog with Components, Preparation used,
Grams, Instructions and separate work minutes. Existing RECIPES permission and
the approved English interface are retained. Schema revision e8b920261110 was
applied locally without altering existing recipe content.

Validation: HTTP/editor tests cover CRUD, category choices, repeated rows, weight,
work time, source/instruction preservation, optimistic revisions, cycle detection,
CSRF and tab permissions. Edge tests exercise real modal saves against a temporary
in-memory fixture; the real local page is visually checked without saving changes.

Product Owner request, 2026-11-09: an English Kitchen page matching the supplied
Selection reference. Dashboard is the default and its content area is empty.
Recipes is the second tab; this task creates its shell only. No recipe import,
editing or photo-upload controls are introduced.

`/kitchen` selects the first permitted tab, normally Dashboard. Routes are
`/kitchen/dashboard` and `/kitchen/recipes`. The existing KITCHEN account Domain
grant is required, including the shared login/active-account gate. Existing
ALL/SELECTED account item permissions control the tabs. Item codes are
`DASHBOARD` and `RECIPES`; selected-only accounts see only granted tabs and
cannot open other routes directly. An account with only Recipes opens Recipes.
No account receives access automatically. Existing account administration can
grant full Kitchen access; item assignments use the existing item-access store.
Older schemas without the scope column retain the original full-Domain meaning.

Layout reuses RF-One branding, olive palette and breadcrumbs, with Kitchen-only
styles. English is explicit for these pages at the Product Owner's request.
The shared How Works component opens tab-specific modal help with a sticky close
button and native keyboard/Escape behavior. Help is registered with the pages.

Validation: `python "03 Software/RF-One Web/tests/test_kitchen_http.py"`.
The in-memory fixture checks default/allowed tabs and direct-URL authorization.
The full RF-One Web How Works scan also identifies pre-existing coverage and
registry mismatches in unrelated pages; this task does not reclassify them.
