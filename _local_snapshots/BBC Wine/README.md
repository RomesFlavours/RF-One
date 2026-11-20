# BBC Wine

Trial application for BBC Wine Imports (importer/distributor): inventory by
location, customer wine lists, orders that remove stock immediately,
customer purchases, printable invoices and a QuickBooks Online export.
Separate from RF-One: its own code, database and users. The wine catalog was
copied once from RF-One's Wines "Availability" (`source_ref` keeps the origin);
nothing is synchronised afterwards.

## Pages

| Page | Who | What |
|---|---|---|
| Orders | `orders` | New/edit/cancel orders. Each line: wine, location, bottles, price, discount (% or $). Order discount (% or $). Saving moves stock at once; not enough bottles = not saved |
| Customers | `customers` | Customer registry (Bill To, Ship To, license, terms, rep) and the purchases page (by wine and by order, with a date filter) |
| Wine Lists | `wine_lists` | A selection of wines for a customer, printable with list prices |
| Availability | `inventory` | Catalog with bottles per case and price per bottle, stock per location in bottles (cases derived), manual adjustments with reason, movement log |
| QBO Export | `invoices` | Printable invoice per order (BBC layout) and CSV for QBO's invoice import |
| Company / Locations / Users | administrators | BBC data printed on invoices, warehouses, users with function + level (View/User) |

## Rules

- Stock is in bottles. Every change is a `stock_movements` row (order, order change, cancellation, manual adjustment).
- Changing an order moves only the difference; cancelling returns every bottle. A cancelled order cannot be edited.
- Invoice number = order number (trial). No payments, taxes, service items (freight, duties) or invoice numbering yet.
- Order lines keep a snapshot of code, description and case size, so catalog edits do not rewrite past invoices.

## Local

1. `python setup_local.py` creates the `bbc_wine` database on the local PostgreSQL (127.0.0.1:55571), the tables and the starting data, and copies the wines from the local RF-One database. Settings and the admin password are kept outside OneDrive in `%LOCALAPPDATA%\BBC Wine\local.json`.
2. `Avvia BBC Wine.cmd` starts http://127.0.0.1:5110 and signs in the local administrator automatically (loopback only).
3. Tests: `python tests/test_flows.py` (uses a disposable database and drops it).

## Configuration

`BBC_DATABASE_URL`, `BBC_SECRET_KEY`; `BBC_LOCAL_AUTOLOGIN=1` only for the local launcher.
