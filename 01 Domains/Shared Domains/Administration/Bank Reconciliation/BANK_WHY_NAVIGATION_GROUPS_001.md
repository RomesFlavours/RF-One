# WHY navigation groups and the three-column "Select WHO / WHY" popup

**Task:** BANK_WHY_NAVIGATION_GROUPS_001 (Product Owner approved, 2026-10-04)
**Status:** Implemented on `feature/bank-simple-who-rules` — migration, service, routes, popup, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no schema change. Data migration `e2c6a9f4b7d1` (frozen input `migrations/migration_data/e2c6a9f4b7d1_why_navigation_groups.csv`).
**Builds on:** BANK_MANUAL_WHO_WHY_001 (the popup), BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 (`BankReasonGroup`).

---

## Decision

`BankReasonGroup` is the ONE grouping of WHY. No second "WHY group" model or hierarchy exists. For the
operator its purpose is **navigation**: it organises the WHY catalog in the popup.

    WHY GROUP  ->  WHY  ->  WHAT / accounting destination

A group has **no accounting effect**: nothing is posted to it, exported from it, taxed by it or decided by
it. A WHY keeps its code, name, WHAT and destination; only its group changed.

## The 15 groups, in stored order

**Display order (Product Owner, 2026-10-05):** every Bank UI shows the groups **alphabetically by name**, and the WHY
alphabetically inside each group (case-insensitive) — the Select WHO / WHY popup, Create New WHY, the WHO Rule
modal and the reconciled edit modal alike. The order is applied when the groups are read for display
(`why_catalog.groups`); the stored `display_order` below is unchanged.

| # | Group (code) | WHY |
|---|---|---|
| 1 | Food, Beverage & Supplies (`PRODUCT_COST`) | 8 |
| 2 | Payroll (`PAYROLL`) | 14 |
| 3 | Rent & Occupancy (`OCCUPANCY`) | 4 |
| 4 | Utilities & Communications (`UTILITIES`) | 6 |
| 5 | Maintenance, Repairs & Cleaning (`FACILITY`) | 4 |
| 6 | Professional Services (`PROFESSIONAL_SERVICES`) | 4 |
| 7 | Office, Software & Admin (`OFFICE_ADMIN`) | 5 |
| 8 | Insurance (`INSURANCE`) | 4 |
| 9 | Marketing & Entertainment (`MARKETING`) | 2 |
| 10 | Vehicles & Travel (`VEHICLE_TRAVEL`) | 5 |
| 11 | Banking, Fees & Interest (`BANKING`) | 5 |
| 12 | Transfers & Card Payments (`TRANSFERS_CARD_PAYMENTS`) | 4 |
| 13 | Deposits, Settlements & Liabilities (`DEPOSITS_SETTLEMENTS`) | 6 |
| 14 | Owner (`OWNER_PERSONAL`) | 8 |
| 15 | Capital Purchases (`CAPITAL_PROJECTS`) | 2 |

81 canonical WHY, each in exactly one group (60 resolve to a P&L WHAT, 21 to a Balance Sheet destination).
A group whose concept is unchanged keeps its code and gets the approved name and order; six are new. The
five superseded groups — `KITCHEN_LABOR`, `FOH_LABOR`, `PEOPLE`, `ADMINISTRATION`, `MONEY_MOVEMENT` — are
**inactive, not deleted**. The per-WHY assignment is the current canonical catalog
(`canonical/RFONE_RESTAURANT_WHY_V1.csv`, group columns) and, for the migration, its frozen snapshot.

Product Owner decisions on the items marked REVIEW in the proposal: Workers Compensation, Recruiting /
Training and Tips Settlement → Payroll; Vehicle Insurance → Insurance; Meals / Entertainment → Marketing &
Entertainment; Business Travel / Scouting → Vehicles & Travel; Accounts Payable Settlement → Deposits,
Settlements & Liabilities; Equipment Purchase (capital) → Capital Purchases.

## The popup

`_bank_who_why_modal.html`, `static/js/bank-who-why.js` — about 90% of the viewport width (max 1500px),
three columns on desktop, wrapping on narrow screens:

| WHO | WHY GROUP | WHY |
|---|---|---|
| every active WHO, alphabetical; search covers aliases, the choice is the canonical WHO | the 15 groups, alphabetical, each with its number of WHY and — once a WHO is chosen — how many of them that WHO already uses (● n, or —) | the WHY of the selected group, alphabetical, with WHAT underneath; the WHO's own WHY carry a *used with this WHO* badge; **+ Create New WHY** |

* **Search WHY covers the whole catalog**, not only the selected group, and shows each hit's group;
  choosing a hit selects its group.
* **Any active WHY can be chosen for any WHO.** The WHO's associations only mark WHY; they never limit the
  list, so a WHO with no WHY yet does not force *Create New WHY*.
* **Confirm** (WHO and WHY chosen) → `manual_reconciliation.reconcile_who_why`: when the WHY is not yet
  associated with the WHO the association is added (`why_catalog.associate`) in the same database
  transaction as the HUMAN decision (`row_reconciliation.record_who`, WHAT derived from the WHY). An
  existing association is not duplicated. No Rule is created.
* **Create New WHY** — the one dialog shared with the WHO Rule modal (see `BANK_MANUAL_WHO_WHY_001.md`,
  *Create New WHY*): preselects the current group; the group is **required** (an active group, listed
  alphabetically), as is a P&L WHAT. A name that already is an active WHY (case and spacing ignored)
  reuses that WHY. The WHY is created by `configuration.create_why` (which accepts an optional
  `reason_group_id`; Bank Configuration itself is unchanged and still creates WHY without a group) and
  comes back selected in the popup.
* **Editing from Reconciled** preselects the current WHO, its WHY's group and the WHY. Changing the WHO
  refreshes the marks and keeps every WHY selectable.
* Every state sets its own text and background colour (the options are buttons, and inheriting the
  global white button text was the unreadable white-on-white). Verified in the browser: every text state
  at WCAG AA contrast (≥ 4.5:1).

Loading, no WHO × WHY matrix: `GET /bank/manual-reconciliation/whos` and
`GET /bank/manual-reconciliation/why-catalog` once per page; `GET …/whos/<id>/whys` for the chosen WHO
(only to mark); `GET /bank/whys/create-options` when Create New WHY is first pressed.

## Open points

* A WHY created in **Bank Configuration** has no group (Configuration does not ask for one yet); the popup
  lists such WHY under a trailing **Other** entry rather than hiding them.
* The disabled Confirm is a light button like Cancel: readable, but similar in look.
