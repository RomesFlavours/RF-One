# RF1 WHY catalog based on USAR (BANK_WHY_USAR_CATALOG_001)

**Date:** 2026-10-21 · **Applied to:** the local (old) Bank working database only (port 5080). Not deployed to AWS.
**Tool:** [apply_rf1_usar_why_catalog.py](apply_rf1_usar_why_catalog.py). It runs a dry run by default; `--apply` backs up the database first and writes a JSON change log next to the backup.

## Source and provenance

The reference is the *Uniform System of Accounts for Restaurants* (USAR, National Restaurant Association,
<https://shop.restaurant.org/The-Uniform-System-of-Accounts-for-Restaurants-Print>). Only these public **review copies** were consulted:

- <https://www.restaurantowner.com/USAR_chart_of_accounts_review_copy.pdf>
- <https://www.restaurantowner.com/USAR_expense_dictionary_review_copy.pdf>

Both are marked "PRELIMINARY – FOR REVIEW AND DISCUSSION ONLY". The catalog below is **an RF1 catalog based on USAR,
adapted to bank movements**. It is not an official or complete reproduction of USAR. USAR balance-sheet accounts and
accounting entries were not copied: they appear only where a bank movement needs a WHY for them.

## Rules applied

- WHY describes the nature or purpose of a movement. It never names a supplier, person or location.
- Every WHY description states its basis: `USAR (review copy): <section>` or `RF1 integration`.
- **Purchases are not cost of sales.** Food & beverage WHYs are purchases; cost of sales is purchases adjusted for inventory.
- **Card statement payments are not expenses.** `Credit Card Statement Payment` settles the card liability. The purchases on the card were already recorded.
- Existing WHY → WHAT links are unchanged. The WHAT catalog is unchanged. New WHYs point only at existing accounts.
- A merge happens only when the meaning **and** the accounting destination coincide. The absorbed WHY stays INACTIVE, so historical references stay valid.
- A legacy WHY with no unambiguous match moves to **To Review**. No movement is reassigned.

## Groups

The UI lists groups alphabetically and WHYs alphabetically within each group.

| Group | Basis |
|---|---|
| Revenue | USAR Sales; Other Operating Income |
| Sales Deposits & Settlements | RF1 |
| Food & Beverage Purchases | USAR Cost of Sales (purchases side) |
| Payroll & Personnel | USAR Labor; Employee Benefits |
| Direct Operating Expenses | USAR Direct Operating Expenses |
| Marketing | USAR Marketing |
| Utilities | USAR Utilities |
| General & Administrative | USAR G&A (absorbs the former "Professional Services" group) |
| Repairs & Maintenance | USAR Repairs and Maintenance |
| Occupancy | USAR Occupancy Costs |
| Insurance | USAR G&A Insurance; Occupancy insurance |
| Vehicles & Travel | USAR Auto or Truck Expenses; G&A Travel |
| Bank, Card & Interest Charges | USAR G&A Bank Charges, Credit Card Fees; Interest Expense |
| Other Income & Expense | USAR Other (Income) Expense |
| Taxes | RF1 (USAR Sales Taxes, State Business Taxes, Income Taxes) |
| Capital Expenditures | RF1 (USAR balance sheet: Property and Equipment) |
| Loans & Financing | RF1 (USAR balance sheet: Notes Payable) |
| Transfers & Card Payments | RF1 |
| Intercompany & Related Parties | RF1 |
| Owner & Personal | RF1 |
| To Review | RF1 |

The full per-WHY definitions are in the script (`E`, `NEW`, `MERGES`) and in each WHY's description.

## Merges

| Absorbed (now inactive) | Into |
|---|---|
| CAR_INSURANCE, COMPANY_CARS_INSURANCE | VEHICLE_INSURANCE |
| COMPANY_CARS_FUEL | VEHICLE_FUEL |
| COMPANY_CARS_LEASE | VEHICLE_LEASE |
| COMPANY_CARS_MAINTENANCE | VEHICLE_REPAIRS |

The merge re-points movements (`bank_transaction_explanations`, including the WHY name snapshot), allocations, WHO
associations, WHO defaults and WHO knowledge. No AI rule referenced an absorbed WHY. Historical AI previews keep their
original id. WHAT snapshots on movements are unchanged.

## Open WHAT issues (reported, not changed)

- **Possibly incompatible:**
  - CARD_PAYMENT → 7220 counts card statement payments as an expense.
  - ONLINE_TRANSFER → 7220 treats a transfer as a bank charge.
  - BANK_REVERSAL → 7220 depends on what was reversed.
  - APPLIANCE → 7970 is an operating-lease line, not a purchase.
  - COMPANY_CARS_FEES → 7930: the movements are tolls (7960).
  - BUSINESS_MEAL → 7500 Marketing, while MEALS_ENTERTAINMENT → 7950.
  - MOVING_HAULING_SERVICES → 8600 (non-operating).
  - Food/beverage WHATs are named "COGS" while the WHY is a purchase.
- **Missing destination:** see the next section.

## Every usable WHY has a WHAT (BANK_WHY_REQUIRES_WHAT_001, 2026-10-21)

This rule supersedes BANK_WHY_WITHOUT_WHAT_001.

- "WHAT" here means the WHY's single accounting classification. That is a P&L posting category, or the Balance Sheet
  destination of a WHY that settles a liability or moves money (for example Credit Card Statement Payment → 2500).
  The P&L is not forced onto Balance Sheet WHYs.
- **Draft WHY.** An active WHY with no valid WHAT (missing, inactive, incomplete or a reporting group) is a draft. A draft
  stays in the catalog but never classifies a movement. If a draft is proposed, the system refuses it with: "This WHY has
  no associated WHAT. Complete its configuration before using it."
- **Derived WHAT.** When a valid WHY is assigned, its WHAT is derived from it. A decision or allocation whose WHAT differs
  from its WHY's WHAT is refused. A transaction-level WHAT exception is no longer accepted for a new assignment.
- **Protected links.** The WHAT of a usable WHY cannot be removed. A WHAT still required by active WHYs cannot be
  deactivated, turned into a group or deleted.
- **Enforcement.** The rule is enforced on the server by one check on every database flush
  (`rfone_data_store/bank_reconciliation/why_what.py`). It covers manual reconciliation, AI rules, BANK_FLOW_2 rules,
  imports, bulk applications, allocations and configuration.
  - Human decisions (`recognition.record_human_decision`) refuse a draft earlier.
  - The AI `Planner` marks a draft WHY as UNRESOLVED in the preview and in the application.
  - The "Select WHO / WHY" popup shows the message as soon as a draft is chosen.
- **History is not reclassified.** A new decision that only carries over the WHY/WHAT pair a movement already holds is
  allowed, for example an AI rule that changes only the WHO.

### WHAT completed where the existing catalog has a correct match

| WHY | WHAT | Why it is correct |
|---|---|---|
| PAYROLL_TAX_PAYMENT | 2420 Payroll Tax Payable | Payroll-tax remittance; employer and withheld amounts together. No employer-only expense is asserted |
| PAYROLL_WAGES_PAYMENT | 2410 Payroll Payable | Aggregate net-wage disbursement |
| CONTRACT_1099_LABOR | 6800 Temporary / Contract Restaurant Labor | Needs no FOH/BOH role |
| LINEN_SERVICE | 7830 Restaurant Operating Supplies | USAR Direct Operating – Linen |
| LAUNDRY_DRY_CLEANING | 7810 Janitorial / Cleaning | Cleaning service |
| PAYMENT_EQUIPMENT_SERVICE | 7210 Merchant Processing Fees | USAR G&A – Credit Card Fees |
| CARD_CHARGEBACKS | 4920 Refunds / Returns | A chargeback reverses a sale |

The remaining drafts have no correct match without a decision:

- Personnel Payment, Insurance Premium, Income Tax Payment, State / Local Business Taxes.
- The To Review items Accommodation, Air Travel, Construction / Remodeling Services, Deposit, Digital Subscription,
  Psychologist / Therapy, Restaurant Equipment / Supplies Purchase, Wine Representative Payment and Withdrawal.

Movements already recorded with these WHYs keep their decisions. Movements recorded before a WHAT was completed keep
their empty WHAT snapshot. The explicit Reclassify action applies the current chain when someone chooses to.

## Semantic consolidation (BANK_WHY_SEMANTIC_CONSOLIDATION_001, 2026-10-21)

All active WHYs were reviewed by meaning, not by name. The result is one catalog: one canonical WHY per meaning.
A category stays separate only where its definition states a real difference, for example Hood Cleaning vs
Janitorial, Linen Service vs Laundry, or Payroll Tax Payment (settlement) vs Employer Payroll Tax (expense).

| Absorbed (now inactive, kept for history) | Canonical WHY |
|---|---|
| PROPERTY_TAXES | OCCUPANCY_PROPERTY_CHARGES — Property & Occupancy Taxes |
| BUSINESS_MEAL | MEALS_ENTERTAINMENT — Business Meals & Entertainment |
| PAYROLL_SERVICE_FEES | ACCOUNTING_BOOKKEEPING — Accounting, Bookkeeping & Payroll Services |
| PAYMENT_EQUIPMENT_SERVICE | MERCHANT_PROCESSING_FEE — Card Processing Fees & Equipment |
| CARD_ANNUAL_FEE | BANK_SERVICE_CHARGE — Bank & Card Service Charges |
| LOAN_FEES | INTEREST_EXPENSE — Interest & Financing Charges |
| SMALLWARES | RESTAURANT_OPERATING_SUPPLIES — Operating Supplies & Smallwares |
| GROUNDS_MAINTENANCE | FACILITY_MAINTENANCE — Building, Facility & Grounds Maintenance |
| RETIREMENT_PLAN_CONTRIBUTIONS | EMPLOYEE_BENEFITS |
| EMPLOYEE_GIFTS_EVENTS | OTHER_PERSONNEL_COST |
| FOH_CONTRACT_LABOR, BOH_CONTRACT_LABOR | CONTRACT_1099_LABOR |

Movements, allocations, WHO associations and defaults, and WHO knowledge were re-pointed to the canonical WHY. No AI
rule referenced an absorbed WHY. Every historical decision keeps its recorded WHAT. BUSINESS_MEAL was recorded as 7500;
its canonical WHY resolves to 7950 for new assignments only.

**Legacy – To Resolve (BANK_WHY_LEGACY_001).** WHYs without an unambiguous canonical meaning are in the group with code
`TO_REVIEW`, named "Legacy - To Resolve". They stay visible for the movements they already classify. They are refused
for any new assignment, manual or AI, even when they have a WHAT (`why_what.assignment_problem`). Three more WHYs moved
there: Personnel Payment, Insurance Premium and Business Travel / Scouting.

**Result:** 131 active WHYs.

- 108 are usable.
- 2 are drafts without a WHAT: Income Tax Payment and State / Local Business Taxes. The existing chart of accounts has
  no correct account for them.
- 21 are legacy.
