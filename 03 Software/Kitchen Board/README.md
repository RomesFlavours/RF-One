# RF-One Kitchen Board

Approved scope: the Product Owner's Kitchen Board conversation, 2026-11-08.

## Workflow and boundaries

An existing Clover Location feeds a screen replacing the kitchen's paper ticket rail.
The oldest unreleased order is on the left. Five columns are visible by default;
the number is configurable (1–16). Long tickets continue in adjacent columns with
their title repeated and explicit continuation markers, without internal scrolling.
The monitor has no controls, general header, pagination or scrolling (explicit
Product Owner display instruction, 2026-11-08, overriding the standard visible
navigation/help link for this unattended screen). Display only whole orders that
fit in the available columns. Remaining orders stay queued until releases free
space. An exceptionally long oldest order reduces the font to fit the screen.
No items are discarded. The archive remains accessible separately on other devices.
Tickets preserve the order title, covers line when supplied, guest grouping, quantities,
notes and modifiers. Payment/closed status is not kitchen release status.

The order-only Live Sync worker reuses the existing read-only Clover client,
pagination, canonical Order upsert, line/modifier ingester, Provider Mirror and
Location acquisition lock. It polls modified orders every 15 seconds after each
cycle. It does not fetch payments, refunds, shifts or catalogs. The existing
60-second Correction Sync may continue; the shared lock serializes writes.
No Clover write or notification is performed here.

Kitchen-owned tables in the **same RF-One database** store configuration,
the latest complete kitchen ticket projection, and release/archive state. A release
freezes the ticket snapshot. Repeated requests and subsequent Clover reads cannot
reopen it. A new POS order has a different Clover order identifier.

The PC and Shelbi's tablet use one server/database. Shelbi owns her release screen
and busser/server notification; she calls the release endpoint below. This app owns
removal, queue advancement and the archive. Devices refresh every two seconds.

## Setup (no deployment is performed by this change)

Use Python 3.10+, the Data Store dependencies, Flask and requests. From this folder:

```powershell
pip install -r requirements.txt
# Explicitly point at the existing canonical database; there is no SQLite fallback.
$env:RFONE_DATABASE_URL = '<existing RF-One database URL>'
$env:KITCHEN_BOARD_SECRET = '<persistent random session secret, at least 32 characters>'
$env:KITCHEN_BOARD_VIEW_TOKEN = '<random screen access token, at least 32 characters>'
$env:KITCHEN_BOARD_RELEASE_TOKEN = '<different random integration token, at least 32 characters>'
# Create ONLY the three Kitchen Board tables, once, as an explicit operator action.
python manage.py init --location-id 1 --since 2026-11-08T16:00:00-05:00
python manage.py sync --location-id 1
# Separate terminal, same environment. Bind through your authenticated HTTPS proxy.
python manage.py serve --host 127.0.0.1 --port 5090
```

`--since` is a required, explicit service start boundary (timezone offset mandatory).
Choose it to include the current kitchen queue: no paid/closed-order heuristic is
used to guess which earlier orders were released before this system existed.
Initializing again never resets the boundary or erases existing releases.
Existing canonical RF-One schema must already be migrated. Importing/starting the
web app performs no migrations, creates no database and starts no polling worker.
Use a supervised permanent process/container for `sync`; it requires outbound
Clover access and access to the shared database, like existing acquisition workers.
SIGTERM/SIGINT finish the active cycle. Database credentials and Clover credentials
use existing environment configuration (`CLOVER_API_TOKEN`, `CLOVER_MERCHANT_ID`).

Open Microsoft Edge at `/login`. Enter the **view token**, select the configured
Location through `/board/1`, and use the screen. Tokens are sent in a POST body,
never a URL, and are not stored in browser localStorage. The signed session cookie
is HttpOnly/SameSite=Strict/Secure; use HTTPS. For a loopback-only local trial set
`KITCHEN_BOARD_LOCAL=1`; it selects Italian and allows an HTTP loopback cookie.
Shared/default UI is English. `/archive/1` shows released snapshots, newest first,
with pagination. `/api/locations/1/settings` changes the shared visible count via
POST, Bearer release token, JSON `{"visible_count":8}`.

## Shelbi integration contract

Use a **server-side** integration; never embed the release secret in public JS.
All API requests require `Authorization: Bearer <KITCHEN_BOARD_RELEASE_TOKEN>`
(the read-only token also permits GET). Use HTTPS. There is no public CORS access.

* `GET /api/locations/1/orders` returns all unreleased tickets in oldest-first order,
  `visible_count`, `total`, `last_sync`, `sync_error`, and `stale`. `order_id` is the
  original Clover order ID; `rfone_order_id` is a separate canonical identifier.
  The tablet can paginate/display this queue as appropriate for its own screen.
* `POST /api/locations/1/orders/<order_id>/release`, JSON `{"released_by":"tablet-1"}`.
  Response 200: `{"order_id":"...","released":true,"already_released":false}`.
  A repeated request returns 200 with `already_released:true`, preserving the
  original timestamp/actor. A missing order or wrong Location returns 404.
* Call release after the cook's explicit action. A lost response can safely be
  retried. This endpoint sends no notification; Shelbi retains that responsibility.
* A release commits before responding. The next screen refresh removes the ticket;
  the next queued ticket becomes visible. Multiple PCs/tablets see the same state.

`released_by` is supplied integration provenance, not a verified human identity.
The release token authorizes the configured integration for all initialized Locations.
Do not distribute it to unattended display clients. View sessions cannot release.

## Verification

`python -m unittest discover -s tests -v` uses disposable in-memory databases and
fake Clover responses. Production activation, monitor sizing, real merchant ticket
comparison and Shelbi's end-to-end integration remain deployment/UAT steps.
Current limitations: no reopen workflow; later changes to a released Clover order
do not reopen it. Archived snapshots intentionally preserve the release-time ticket.
Only source-provided fields are displayed; no guest count or table is invented.
The UI shows stale/error state without clearing the last successfully read tickets.

## Kitchen beverage exclusion and exit

Clover category membership excludes Beverages/Drinks, Beer, Wine categories and Coffee/Milk/Tea from the kitchen projection, including beverage-only orders. Source records and canonical sales facts are retained. An unclassified item remains visible: do not infer a beverage from its product name. Existing Clover catalog category mappings must be present in the canonical database. The small top-right X opens /exit (the module landing screen), without changing releases or archive state. The offline preview has an equivalent local exit page. This is the only display control, explicitly requested by the Product Owner.

## Service timing and real-data review

The Clover When Serve modifier group supplies service timing. First, Second and Third are displayed in that order; other source values remain separate. No timing is inferred from the dish, guest, cooking temperature or category. Other modifiers and notes remain visible. The existing canonical Modifier/ModifierGroup catalog supports the live board projection. `capture_preview.py --dotenv <existing .env> --output <private JSON path>` reads the latest six kitchen orders from the last 48 hours with the existing read-only Clover client and complete line-item endpoints, plus current item categories and modifier groups. `python tests/export_preview.py <private JSON path>` renders a local snapshot for review. This capture does not establish unreleased status or activate continuous polling. Source captures and rendered previews must never be committed; they are ignored by this module.

Display update: five equal-width columns fill the full viewport, with 20px base ticket text. Resizing reruns measurement and continuation layout. Configured column counts are never simulated by hiding the last grid cell.

## Display configuration page

Open `/settings/<location_id>` from the module landing page (also reached through the monitor X). Sign in using the existing configuration/integration token (`KITCHEN_BOARD_RELEASE_TOKEN`); the view-only token cannot save settings. Browser configuration permission does not authorize a release API request. Forms use session-bound CSRF tokens and optimistic revisions; invalid or conflicting submissions preserve the draft without overwriting saved preferences.

Preferences: Arial/Segoe UI/Verdana; 12–36 pixel base text; 1–16 columns per row; 1–3 rows; continuous columns or one order per cell. The iframe previews draft settings at a 1920x1080 display scale without saving. On Save, preferences are stored in `kitchen_display_settings` in the same RF-One database and returned by the existing orders feed. Displays pick them up at the next refresh. Row count means rows of ticket cells, never a limit hiding order items. One-order mode adapts each ticket text to fit its cell.

Existing installations must run `python manage.py upgrade-display` once (with the existing `RFONE_DATABASE_URL`) before starting this version. It creates only the additive settings table, never another database or changes to existing releases. New `init` creates all three Kitchen Board tables. No DDL runs at application startup.

The settings page uses a byte-identical copy of RF-One Web’s `rf-one.css` palette, form styling and page-specific modal help. English is the shared default and official local mode is Italian. The exported `preview-settings.html` is a local visual review: changes save only in that browser and are explicitly labelled as such. The actual web page saves to the shared database; no online service has been deployed by this work.

## English handoff

The shared application and exported review pages default to English, including settings, notifications, accessibility text and contextual help. To run English locally with loopback cookie settings use `KITCHEN_BOARD_LOCAL=1` and `python manage.py serve --language en`. `RFONE_UI_LANGUAGE=en` is an equivalent environment setting. The separate `--language it` option preserves the Italian development interface. The exporter accepts `--language it` when an Italian local review is needed; its default is `en`. Imported Clover item names, notes, IDs and service-timing values are never translated.

## Proposed improvements (branch `shelbi/kitchen-board-improvements`, not merged)

Proposed on top of `codex/kitchen-board` at 702d2d5 for the Product Owner's review. The approved whole-order release and frozen archive are unchanged.

| Change | What the kitchen sees | How |
|---|---|---|
| Additions after release | Items added in Clover after a ticket was released appear as a new ticket, `ADDITION 1`, `ADDITION 2`, with the same title. Before this they were silently dropped. | `store._save_addition`: lines not in any released snapshot of that order become ticket `<order_id>-add<n>`. Released snapshots stay frozen. |
| Changes on an open ticket | `CHANGED` at the top; changed lines marked `CHANGED:`, new lines `NEW:`, removed lines kept under `REMOVED FROM ORDER` and struck out as `VOID:`. | `store._track_changes` compares each Clover read with the previous one; stored in `payload.changes`. |
| Allergy flag | `⚠ ALLERGY` at the top and on the line, plus "check before cooking". | `kitchen_filter.ALLERGY_WORDS` matches only words typed in a note or modifier. It highlights; it never decides what is safe. |
| Server and timer | Under the title: local time · minutes since the order · server. | Server from Clover's order `employee` (already expanded); minutes tick every 30 s without redrawing. |
| Partial release (Product Owner, 10 Nov: "Both. The kitchen can release in any configuration") | The kitchen releases any dishes that are ready: one, a course, or all. The rest stays on the ticket with `n ALREADY OUT` at the top; at Winter Park the server decides whether to serve now or wait. | Same release endpoint with optional `"line_ids": [...]` (ids from the orders feed). The released dishes become archived ticket `<order_id>-part<n>` ("Partial release n" in the archive); the open ticket keeps the rest and never shows released dishes again. Releasing the last open dishes releases the order as before. A retry returns `already_released`; ids not on the ticket return 409. Undo works on a part (`.../<order_id>-part<n>/undo-release`) while the rest of the order is still open. Without `line_ids` the release is the whole order, unchanged. |
| Undo a release | n/a on the monitor; for the Pass. | `POST /api/locations/<id>/orders/<order_id>/undo-release` with `{"undone_by": "..."}`, release token only. Allowed within 15 minutes and only while no addition ticket exists; each undo is kept in `payload.release_history`. 409 otherwise. |

Every flag is written in words; colour only supports it. No new tables or migrations: all new state lives in the existing ticket `payload`.

Not in this branch (Product Owner decisions): an automatic call when a whole course is ready (Kitchen Flow phase 3; at Winter Park the server decides instead), a changed line after release (only new lines are caught), the "Surname I." display rule for server names (Clover supplies the name as entered), orders deleted in Clover, and printed/sent filtering.

Tests: 27 pass (`python -m unittest discover -s tests`), including 11 new ones for the above. One existing assertion now expects the added `allergy` field.
