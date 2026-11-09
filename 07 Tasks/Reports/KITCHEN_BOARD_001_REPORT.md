# REPORT — RF-One Kitchen Board

## 1. Scope and implemented behavior

Approved in the Product Owner conversation of 2026-11-08. Kitchen Board replaces
the kitchen paper-ticket rail. A read-only order-only Clover polling worker reuses
the existing connector/client, canonical mapping, Provider Mirror and Location
acquisition lock. Orders appear oldest first; beverages are excluded by Clover
category membership. When Serve modifiers group service timing; guests are sorted
numerically within each group. Other modifiers and notes remain visible.

The default unattended display uses the whole screen, five columns and 20px text.
Long orders flow into adjacent cells with continuation markers. There is no monitor
scrolling or pagination. The only control is the requested top-right exit X.
Releases persist in the shared database, freeze the ticket snapshot and remove it
from all readers. The authenticated, idempotent release API is for Shelbi to call;
this module does not send busser/server notifications or modify Shelbi's screen.

## 2. Display settings

The new `/settings/<location_id>` page uses RF-One Web's stylesheet, olive palette,
form conventions, breadcrumb and page-specific modal help. It configures font
family, text size, columns, grid rows and continuous versus single-order layout.
The 16:9 preview uses the same rendering code as the monitor and applies draft
changes without saving. Saved preferences reach monitors through the existing
refresh feed. Management-session authorization, CSRF, input validation and revision
conflict detection protect saving. View-only display sessions cannot save settings
or release orders. A management browser session alone cannot release via API.

## 3. Observed verification

| Success criterion | Result |
|---|---|
| Order-only acquisition reuses the Location lock and handles failed reads safely | Isolated fake-Clover behavioral tests passed |
| Release retry cannot reopen/duplicate an archived ticket | Persistence/idempotency tests passed |
| Category-based beverage exclusion preserves source sales facts | Tests passed |
| Only the When Serve group supplies service timing | Tests passed |
| Settings persist across application factories and reach the monitor feed | Tests passed |
| Invalid, unauthenticated, CSRF-free and conflicting settings writes are rejected | Tests passed |
| Shared interface defaults to English; local mode is Italian | HTTP rendering tests passed |
| Contextual help matches implemented functionality | Scoped How Works check passed for all four operational pages |
| Full-width five-column rendering and guest ordering | Inspected Edge 1920×1080 rendering |
| Configured 3×2 single-order grid, complete orders and no overflow | Edge rendered audit passed using six captured real Clover orders |

Live read-only Clover access succeeded during development. A private review
capture contained six recent kitchen orders and 25 kitchen items; it was a source
snapshot, not proof of unreleased status or an activated continuous deployment.
Real order captures and generated preview files are outside version control.

## 4. Database, release and limitations

All persistent state uses the configured canonical RF-One database. No fallback
database is created. `manage.py init` explicitly creates this module's three
additive tables; existing installations use `manage.py upgrade-display` for the
new settings table. Application imports/startup never apply schema changes.
Tests use disposable in-memory databases only. No production/AWS data was changed.

Runtime activation, Shelbi's tablet integration and full end-to-end release testing
are not performed by this source handoff. Catalog category and modifier mappings
must be populated in the canonical database. Unclassified items remain visible;
food is never excluded by guessing from its name. Display settings are scoped to
the existing Location, shared across its connected monitors. The exported offline
settings review saves only browser-local preferences and says so; the actual HTTP
application saves shared preferences in the RF-One database.

## 5. Traceability and operation

- Handoff branch: `codex/kitchen-board` in `RomesFlavours/RF-One`.
- Implementation and integration contract: `03 Software/Kitchen Board/README.md`.
- Test command: `python -m unittest discover -s tests -v`, from that module.
- Help check: `python "03 Software/Shared UI/check_how_works.py" --app "Kitchen Board"`.
- The module introduces no production deployment and requires no production restore.
  Existing canonical orders/payments and other modules are not replaced.

## 6. English publication update

Following the Product Owner request, all exported review pages and the standalone preview now use English by default. Runtime language can be explicitly selected independently of loopback cookie configuration. HTTP tests cover all four operational pages in English local mode, alongside the shared English default and existing Italian regression checks. Source facts are not translated. Contextual help remains aligned in both supported interface languages.
