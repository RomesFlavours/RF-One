"""Repopulate and reorder the Bank WHY catalog as the RF1 USAR-based catalog
(BANK_WHY_USAR_CATALOG_001, 2026-10-21).

Reference: the Uniform System of Accounts for Restaurants (USAR), National
Restaurant Association. Only the PUBLIC REVIEW COPIES were consulted —
restaurantowner.com "USAR_chart_of_accounts_review_copy.pdf" and
"USAR_expense_dictionary_review_copy.pdf", both marked "PRELIMINARY - FOR
REVIEW AND DISCUSSION ONLY". The result is an RF1 catalog BASED ON USAR,
adapted to bank movements; it is not an official or complete reproduction.

What this does, in one transaction, after a full backup of the database:

* reorganises the WHY navigation groups (existing groups renamed and reused,
  missing groups added, emptied ones deactivated);
* gives every WHY an English name, a short definition and its basis
  ("USAR (review copy): <section>" or "RF1 integration");
* adds the missing WHYs, each pointing only at an EXISTING accounting
  classification (the WHAT catalog is never modified);
* merges a WHY into another only where the meaning is the same AND the
  accounting destination is the same, re-pointing movements, allocations,
  WHO associations / defaults and WHO knowledge; the absorbed WHY stays,
  INACTIVE, so every historical reference stays valid;
* moves WHYs with no unambiguous USAR match to the "To Review" group,
  without reassigning any movement.

Existing WHY -> WHAT links are never changed. Run without --apply for a
dry run. A JSON change log is written next to the backup.

    python apply_rf1_usar_why_catalog.py --db <rfone.db> [--apply]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

TAG = "BANK_WHY_USAR_CATALOG_001"
U = "USAR (review copy): "
RF1 = "RF1 integration"

# (code, name, basis). Existing codes are reused with their ids.
GROUPS = [
    ("REVENUE", "Revenue", U + "Sales; Other Operating Income"),
    ("DEPOSITS_SETTLEMENTS", "Sales Deposits & Settlements", RF1),
    ("PRODUCT_COST", "Food & Beverage Purchases", U + "Cost of Sales (purchases side)"),
    ("PAYROLL", "Payroll & Personnel", U + "Labor; Employee Benefits"),
    ("DIRECT_OPERATING", "Direct Operating Expenses", U + "Direct Operating Expenses"),
    ("MARKETING", "Marketing", U + "Marketing"),
    ("UTILITIES", "Utilities", U + "Utilities"),
    ("OFFICE_ADMIN", "General & Administrative", U + "General and Administrative Expenses"),
    ("FACILITY", "Repairs & Maintenance", U + "Repairs and Maintenance"),
    ("OCCUPANCY", "Occupancy", U + "Occupancy Costs"),
    ("INSURANCE", "Insurance", U + "G&A Insurance; Occupancy insurance"),
    ("VEHICLE_TRAVEL", "Vehicles & Travel", U + "Auto or Truck Expenses; G&A Travel"),
    ("BANKING", "Bank, Card & Interest Charges", U + "G&A Bank Charges, Credit Card Fees; Interest Expense"),
    ("OTHER_INCOME_EXPENSE", "Other Income & Expense", U + "Other (Income) Expense"),
    ("TAXES", "Taxes", RF1 + " (USAR: Sales Taxes, State Business Taxes, Income Taxes)"),
    ("CAPITAL_PROJECTS", "Capital Expenditures", RF1 + " (USAR balance sheet: Property and Equipment)"),
    ("LOANS_FINANCING", "Loans & Financing", RF1 + " (USAR balance sheet: Notes Payable)"),
    ("TRANSFERS_CARD_PAYMENTS", "Transfers & Card Payments", RF1),
    ("INTERCOMPANY", "Intercompany & Related Parties", RF1),
    ("OWNER_PERSONAL", "Owner & Personal", RF1),
    ("TO_REVIEW", "Legacy - To Resolve", RF1),
]
# Groups whose WHYs all move elsewhere; deactivated, never deleted.
RETIRED_GROUPS = ["PROFESSIONAL_SERVICES"]

# Existing WHYs: code -> (group, new name or None, definition, basis, review note or None)
E = {}


def keep(code, group, definition, basis, name=None):
    E[code] = (group, name, definition, basis, None)


def review(code, definition, note, name=None):
    E[code] = ("TO_REVIEW", name, definition, RF1, note)


# --- Revenue / sales settlements -------------------------------------------
keep("ONLINE_INCOME", "REVENUE", 'Revenue from online or gift platforms that is not recorded in the POS. Payouts of POS-recorded sales are Delivery Platform Payout or Merchant / Card Sales Settlement.', U + "Sales / Other Operating Income")
keep("MERCHANT_CARD_SETTLEMENT", "DEPOSITS_SETTLEMENTS", "Card processor payout for sales already recorded as revenue; not revenue again.", RF1)
keep("CASH_CHECK_DEPOSIT", "DEPOSITS_SETTLEMENTS", "Deposit of cash or checks collected from sales.", RF1)
keep("GIFT_CARD_SETTLEMENT", "DEPOSITS_SETTLEMENTS", "Settlement of gift card sales; a liability until the card is redeemed.", U + "Other Liabilities - Gift Certificates")
# --- Food & beverage purchases ---------------------------------------------
_P = " A purchase, not cost of sales: cost of sales is purchases adjusted for inventory."
keep("FOOD_PURCHASES", "PRODUCT_COST", "Purchase of food products for the menu." + _P, U + "Cost of Sales - Food Cost")
keep("NON_ALCOHOLIC_BEVERAGES", "PRODUCT_COST", "Purchase of soft drinks and other non-alcoholic beverages for sale." + _P, U + "Cost of Sales - Soft Beverage Cost")
keep("BEER_PURCHASES", "PRODUCT_COST", "Purchase of beer for sale." + _P, U + "Cost of Sales - Beer Cost")
keep("WINE_PURCHASES", "PRODUCT_COST", "Purchase of wine for sale." + _P, U + "Cost of Sales - Wine Cost")
keep("LIQUOR_PURCHASES", "PRODUCT_COST", "Purchase of liquor and cocktail ingredients for sale." + _P, U + "Cost of Sales - Liquor Cost")
# --- Payroll & personnel -----------------------------------------------------
keep("FOH_REGULAR_PAYROLL", "PAYROLL", "Regular wages of front-of-house staff.", U + "Labor - Staff - Front of House")
keep("FOH_OVERTIME", "PAYROLL", "Overtime wages of front-of-house staff.", U + "Labor - Staff - Front of House")
keep("BOH_REGULAR_PAYROLL", "PAYROLL", "Regular wages of back-of-house staff.", U + "Labor - Staff - Back of House")
keep("BOH_OVERTIME", "PAYROLL", "Overtime wages of back-of-house staff.", U + "Labor - Staff - Back of House")
keep("CONTRACT_1099_LABOR", "PAYROLL", 'Work paid to independent contractors (1099), front or back of house; the role does not change the WHAT.', U + "Labor - Staff")
keep("MANAGEMENT_PAYROLL", "PAYROLL", "Salaries and wages of managers.", U + "Labor - Management")
keep("BONUS_INCENTIVE", "PAYROLL", "Bonuses and incentives paid to staff or managers.", U + "Labor - Staff / Management (bonuses)")
keep("PAYROLL_WAGES_PAYMENT", "PAYROLL", 'Net wages paid through a payroll provider in one aggregate payment; settles Payroll Payable. Wage cost by role (FOH, BOH, management) comes from payroll records.', U + "Labor")
keep("TIPS_SETTLEMENT", "PAYROLL", "Payment of tips collected for staff; settles a liability, not an expense.", U + "Other Liabilities - Charge Tips Withheld")
keep("EMPLOYER_PAYROLL_TAX", "PAYROLL", 'Employer share of payroll taxes recognised as an expense. A remittance to the tax agency is Payroll Tax Payment.', U + "Employee Benefits - Payroll Taxes")
keep("PAYROLL_TAX_PAYMENT", "PAYROLL", 'Remittance or refund of payroll taxes (employer and withheld together); settles Payroll Tax Payable. Employer Payroll Tax is the expense side.', U + "Employee Benefits - Payroll Taxes")
keep("EMPLOYEE_BENEFITS", "PAYROLL", 'Employer-paid benefits: health, disability and life insurance, retirement plan contributions.', U + "Employee Benefits - Insurance and Retirement")
keep("WORKERS_COMPENSATION", "PAYROLL", "Workers' compensation insurance premiums.", U + "Employee Benefits - Workers' Compensation")
keep("RECRUITING_TRAINING", "PAYROLL", "Recruiting, help-wanted ads and staff training.", U + "G&A - Personnel Expenses; Training")
keep("OTHER_PERSONNEL_COST", "PAYROLL", 'Other employee expenses: gifts, awards, parties and similar costs not covered by a more specific WHY.', U + "Employee Benefits - Other Employee Expenses")
# --- Direct operating --------------------------------------------------------
keep("DIRECT_CONSUMABLES", "DIRECT_OPERATING", 'Single-use guest and bar supplies consumed in service (napkins, straws, stirrers). To-go containers are Packaging / To-Go Consumables.', U + "Direct Operating Exp. - Guest Supplies; Bar Supplies")
keep("TO_GO_PACKAGING", "DIRECT_OPERATING", "To-go containers, paper and packaging.", U + "Direct Operating Exp. - Paper and Packaging")
keep("RESTAURANT_OPERATING_SUPPLIES", "DIRECT_OPERATING", 'Durable operating supplies and smallwares: china, glassware, flatware, kitchen utensils and tools. Single-use guest items are Direct Restaurant Consumables.', U + "Direct Operating Exp. - Tableware and Smallwares; Kitchen Utensils and Supplies", name='Operating Supplies & Smallwares')
keep("UNIFORMS", "DIRECT_OPERATING", "Staff uniforms, aprons and similar garments.", U + "Direct Operating Exp. - Uniforms", name="Uniforms")
keep("LINEN_SERVICE", "DIRECT_OPERATING", "Rented table linen delivered and laundered by a linen service. Cleaning the business's own textiles is Laundry & Dry Cleaning.", U + "Direct Operating Exp. - Linen and Linen Rental")
keep("JANITORIAL_CLEANING", "DIRECT_OPERATING", 'Contract cleaning of the premises (janitorial, windows). Hood cleaning, pest control and cleaning products have their own WHY.', U + "Direct Operating Exp. - Contract Cleaning")
keep("HOOD_CLEANING", "DIRECT_OPERATING", 'Specialised cleaning of kitchen hoods and exhaust ducts (fire-safety service), kept apart from general janitorial cleaning.', U + "Direct Operating Exp. - Contract Cleaning")
keep("PEST_CONTROL", "DIRECT_OPERATING", "Pest control and exterminating service.", U + "Direct Operating Exp. - Pest Control")
# --- Marketing ---------------------------------------------------------------
keep("MARKETING_ADVERTISING", "MARKETING", 'Paid advertising and promotion (online, print, outdoor, agencies). Printing services, donations and guest platforms have their own WHY.', U + "Marketing - Advertising")
keep("PRINTING_SERVICE", "MARKETING", "Printing of promotional or guest-facing materials.", U + "Marketing - Printing and Mail Services", name="Printing Services")
keep("MEALS_ENTERTAINMENT", "MARKETING", 'Local business meals and entertainment with clients, partners or staff. A meal during a business trip is Business Travel - Meal.', U + "Marketing - Other", name='Business Meals & Entertainment')
# --- Utilities ---------------------------------------------------------------
keep("ELECTRICITY", "UTILITIES", "Electric service.", U + "Utilities - Electricity")
keep("NATURAL_GAS", "UTILITIES", "Natural gas service.", U + "Utilities - Gas")
keep("WATER_SEWER", "UTILITIES", "Water and sewer service.", U + "Utilities - Water and Sewage")
keep("WASTE_GARBAGE", "UTILITIES", "Trash and waste removal.", U + "Utilities - Trash Removal")
keep("MUNICIPAL_UTILITIES", "UTILITIES", "Combined municipal utility bill.", U + "Utilities")
keep("PHONE_INTERNET", "UTILITIES", "Telephone, internet and communications.", U + "G&A - Telephone and Communications")
# --- General & administrative ------------------------------------------------
keep("ACCOUNTING_BOOKKEEPING", "OFFICE_ADMIN", 'Accounting, bookkeeping, tax preparation and payroll-service fees.', U + "G&A - Accounting and Payroll", name='Accounting, Bookkeeping & Payroll Services')
keep("LEGAL", "OFFICE_ADMIN", "Legal services and court fees.", U + "G&A - Professional Services")
keep("CONSULTING", "OFFICE_ADMIN", "Consulting and other professional services.", U + "G&A - Consulting and Coaching Services")
keep("CORPORATE_MANAGEMENT_FEES", "OFFICE_ADMIN", "Corporate or management fees.", U + "Other (Income) Expense - Management Fee")
keep("DUES_SUBSCRIPTIONS", "OFFICE_ADMIN", 'Association memberships and trade publications. Software subscriptions are Software / POS / Technology.', U + "G&A - Dues and Subscriptions")
keep("LICENSES_PERMITS", "OFFICE_ADMIN", "Business, food and beverage licenses and permits.", U + "G&A - Licenses and Permits")
keep("OFFICE_SUPPLIES", "OFFICE_ADMIN", "Office printing and supplies.", U + "G&A - Office Printing and Supplies")
keep("SHIPPING_POSTAGE", "OFFICE_ADMIN", "Postage, shipping and delivery charges.", U + "G&A - Postage and Delivery")
keep("SOFTWARE_POS_TECHNOLOGY", "OFFICE_ADMIN", 'Operational software and technology: POS, accounting, office and back-office systems. Guest-facing reservation and loyalty platforms are Marketing.', U + "G&A - Computer and Data Processing Costs")
# --- Repairs & maintenance ---------------------------------------------------
keep("FACILITY_MAINTENANCE", "FACILITY", 'Repairs and maintenance of the building, structure, grounds and parking lot. Equipment repairs have their own WHY.', U + "Repairs and Maintenance - Building and Structure; Grounds and Parking Lot", name='Building, Facility & Grounds Maintenance')
keep("EQUIPMENT_REPAIR", "FACILITY", "Repairs and maintenance of equipment and furniture.", U + "Repairs and Maintenance - Equipment and Furniture")
# --- Occupancy ---------------------------------------------------------------
keep("BASE_RENT", "OCCUPANCY", "Fixed rent for the restaurant premises.", U + "Occupancy Costs - Rent")
keep("STORAGE_RENT", "OCCUPANCY", "Rent for storage space.", U + "Occupancy Costs - Rent")
keep("CAM", "OCCUPANCY", "Common area maintenance charges.", U + "Occupancy Costs - Common Area Maintenance")
keep("OCCUPANCY_PROPERTY_CHARGES", "OCCUPANCY", 'Real estate, personal property and municipal occupancy taxes on the premises and contents.', U + "Occupancy Costs - Real Estate, Personal Property and Other Municipal Taxes", name='Property & Occupancy Taxes')
# --- Insurance ---------------------------------------------------------------
keep("GENERAL_LIABILITY_INSURANCE", "INSURANCE", "General liability insurance premiums.", U + "G&A - Insurance - Liability and General")
keep("PROPERTY_BUSINESS_INSURANCE", "INSURANCE", "Insurance on building, contents and business interruption.", U + "Occupancy Costs - Insurance on Building and Contents")
keep("OTHER_BUSINESS_INSURANCE", "INSURANCE", "Other business insurance premiums.", U + "G&A - Insurance - Liability and General")
# --- Vehicles & travel -------------------------------------------------------
keep("VEHICLE_LEASE", "VEHICLE_TRAVEL", "Lease payments for company vehicles.", U + "Direct Operating Exp. - Auto or Truck Expenses")
keep("VEHICLE_FUEL", "VEHICLE_TRAVEL", "Fuel for company vehicles.", U + "Direct Operating Exp. - Auto or Truck Expenses", name="Vehicle - Fuel")
keep("VEHICLE_INSURANCE", "VEHICLE_TRAVEL", "Insurance for company vehicles.", U + "Direct Operating Exp. - Auto or Truck Expenses")
keep("VEHICLE_REPAIRS", "VEHICLE_TRAVEL", "Repairs, maintenance and running costs of company vehicles.", U + "Direct Operating Exp. - Auto or Truck Expenses", name="Vehicle - Repairs & Maintenance")
keep("TOLLS_PARKING", "VEHICLE_TRAVEL", "Tolls and parking for business use.", U + "Direct Operating Exp. - Parking")
keep("BUSINESS_TRAVEL_HOTEL", "VEHICLE_TRAVEL", "Lodging on a business trip.", U + "G&A - Travel")
keep("BUSINESS_TRAVEL_MEAL", "VEHICLE_TRAVEL", "Meals on a business trip.", U + "G&A - Travel")
keep("BUSINESS_TRAVEL_TRANSPORTATION", "VEHICLE_TRAVEL", "Airfare, car rental or other transport on a business trip.", U + "G&A - Travel")
keep("BUSINESS_TRAVEL_OTHER", "VEHICLE_TRAVEL", "Other costs of a business trip.", U + "G&A - Travel")
# --- Bank, card & interest charges -----------------------------------------
keep("BANK_SERVICE_CHARGE", "BANKING", 'Bank account fees and business credit card service fees, including annual card fees. Foreign transaction fees and card processing fees on sales have their own WHY.', U + "G&A - Bank Charges", name='Bank & Card Service Charges')
keep("MERCHANT_PROCESSING_FEE", "BANKING", 'Fees for accepting card payments: processing commissions and payment terminal / equipment charges.', U + "G&A - Credit Card Fees", name='Card Processing Fees & Equipment')
keep("FOREIGN_TRANSACTION_FEE", "BANKING", "Foreign transaction fee charged by the card issuer.", U + "G&A - Bank Charges", name="Foreign Transaction Fee")
keep("INTEREST_EXPENSE", "BANKING", 'Interest and financing fees on loans, notes and credit lines. Loan principal is Loan Principal Repayment.', U + "Interest Expense", name='Interest & Financing Charges')
# --- Other income & expense --------------------------------------------------
keep("INTEREST_INCOME", "OTHER_INCOME_EXPENSE", "Interest earned on bank balances.", U + "Other (Income) Expense")
keep("MOVING_HAULING_SERVICES", "OTHER_INCOME_EXPENSE", "Moving and hauling services.", RF1, name="Moving & Hauling Services")
# --- Taxes -------------------------------------------------------------------
keep("SALES_TAX_REMITTANCE", "TAXES", "Remittance of sales tax collected from guests; settles a liability, never an expense.", U + "Taxes Collected - Sales Tax", name="Sales Tax Remittance")
# --- Capital expenditures ----------------------------------------------------
keep("EQUIPMENT_PURCHASE_CAPEX", "CAPITAL_PROJECTS", "Purchase of equipment or appliances recorded as a fixed asset.", U + "Property and Equipment - Furniture and Equipment")
keep("LEASEHOLD_IMPROVEMENT", "CAPITAL_PROJECTS", "Leasehold improvements and remodeling recorded as a fixed asset.", U + "Property and Equipment - Leasehold Improvements")
# --- Loans & financing -------------------------------------------------------
keep("LOAN_ADVANCE", "LOANS_FINANCING", "Loan principal received into the account; a liability, never revenue.", U + "Notes Payable", name="Loan Proceeds Received")
# --- Transfers & card payments -----------------------------------------------
keep("INTERNAL_BANK_TRANSFER", "TRANSFERS_CARD_PAYMENTS", "Money moved between the business's own bank accounts.", RF1, name="Internal Bank Transfer")
keep("CREDIT_CARD_SETTLEMENT", "TRANSFERS_CARD_PAYMENTS", "Payment of a credit card statement; the purchases were already recorded, so this is not an expense.", RF1, name="Credit Card Statement Payment")
keep("PAYABLE_SETTLEMENT", "TRANSFERS_CARD_PAYMENTS", "Settlement of a supplier balance whose purpose is recorded elsewhere. Use only when the operational purpose cannot be identified.", U + "Payables - Accounts Payable")
# --- Intercompany ------------------------------------------------------------
keep("RELATED_PARTY_TRANSFER_IN", "INTERCOMPANY", "Money received from a related company or party.", RF1)
keep("RELATED_PARTY_TRANSFER_OUT", "INTERCOMPANY", "Money sent to a related company or party.", RF1)
# --- Owner & personal --------------------------------------------------------
keep("MEMBER_CONTRIBUTION", "OWNER_PERSONAL", "Capital contributed by a member or owner.", U + "Equity - Members' Capital Accounts")
keep("MEMBER_DRAW", "OWNER_PERSONAL", 'Money paid out to a member or owner as a distribution. Personal expenses paid by the business are Owner Personal.', U + "Equity - Members' Capital Accounts")
for _c, _d in [("OWNER_PERSONAL_FOOD", "Personal food expense of the owner."),
               ("OWNER_PERSONAL_HEALTH", "Personal health expense of the owner."),
               ("OWNER_PERSONAL_HOME", "Personal home expense of the owner."),
               ("OWNER_PERSONAL_RESTAURANT", "Personal restaurant meal of the owner."),
               ("OWNER_PERSONAL_TAX", "Personal tax of the owner."),
               ("OWNER_PERSONAL_TRAVEL", "Personal travel of the owner."),
               ("OWNER_PERSONAL_OTHER", "Other personal expense of the owner.")]:
    keep(_c, "OWNER_PERSONAL", _d + " Treated as an owner draw, not a business expense.", RF1)
# --- Legacy to resolve: no unambiguous canonical match. Visible, excluded from
# new assignments (BANK_WHY_LEGACY_001); movements NOT reassigned ---------
review("PERSONNEL_PAYMENT", "Direct payment to personnel.", "Mixes wages, tips and advances; the components are not separated.")
review("INSURANCE_PREMIUM", "Insurance premium.", "The policy type (liability, property, vehicle, workers' compensation) is not stated.")
review("BUSINESS_TRAVEL_SCOUTING", "Scouting or research trip.", "A trip purpose, not a cost type; overlaps Business Travel - Hotel / Transportation / Meal / Other.")
review("CARD_PAYMENT", "Card-related movement.", "Mixes credit card statement payments (Credit Card Statement Payment) with card fees; current WHAT 7220 Bank Service Charges would count statement payments as an expense twice.")
review("ONLINE_TRANSFER", "Online transfer.", "Says how money moved, not why; current WHAT 7220 treats a transfer as a bank charge.")
review("DEPOSIT", "Deposit.", "Says money arrived, not why (customer deposit vs cash deposit).")
review("WITHDRAWAL", "Withdrawal.", "Says money left, not why; includes checks and cash withdrawals.")
review("BANK_REVERSAL", "Reversal or reimbursement credited by the bank.", "Mixes fee reversals, check reversals and customer-claim reimbursements; the reversed item decides the WHY.")
review("COMPANY_CARS_FEES", "Company vehicle fees.", "Observed movements are toll charges (Tolls / Parking, WHAT 7960) but the WHY resolves to 7930; not merged because the WHAT differs.", name="Vehicle - Fees")
review("COUNTY_TAX", "County tax payment.", "The county tax collector collects property taxes, business taxes and vehicle fees; the nature is not stated.")
review("RENT_VEICLES", "Vehicle rental.", "Rental may be a lease (Vehicle - Lease) or travel transport (Business Travel - Transportation); no movements yet.", name="Vehicle - Rental")
review("APPLIANCE", "Appliance purchase.", "Capital purchase vs operating supply is not stated; current WHAT 7970 is an operating-lease line, not a purchase.")
review("RESTAURANT_EQUIPMENT_SUPPLIES_PURCHASE", "Restaurant equipment or supplies purchase.", "Capital vs operating treatment is not stated.")
review("CONSTRUCTION_REMODELING_SERVICES", "Construction, remodeling or handyman services.", "Repair expense vs leasehold improvement (capital) is not stated.")
review("WINE_REPRESENTATIVE_PAYMENT", "Payment to a wine representative.", "Wine purchase vs commission or representation is not stated.")
review("ONLINE_PURCHASE_UNIDENTIFIED", "Online purchase whose content is not identified.", "Nature unknown.", name="Online Purchase - Unidentified")
review("MIXED_PURCHASES_PENDING_ITEM_DETAILS", "Provisional mixed purchases awaiting item detail.", "User-approved provisional WHY; reassess per item when evidence arrives.")
review("DIGITAL_SUBSCRIPTION", "Digital service subscription.", "Software (G&A) vs dues/subscriptions vs personal use is not stated.")
review("PSYCHOLOGIST_THERAPY", "Psychologist or therapy session.", "Employee benefit vs owner personal health is not stated.")
review("ACCOMMODATION", "Lodging.", "Business trip vs personal travel is not stated (trip-level question).")
review("AIR_TRAVEL", "Airfare.", "Business trip vs personal travel is not stated (trip-level question).")

# Merges: absorbed code -> surviving code (same meaning AND same accounting destination).
MERGES = {
    "CAR_INSURANCE": "VEHICLE_INSURANCE",
    "COMPANY_CARS_INSURANCE": "VEHICLE_INSURANCE",
    "COMPANY_CARS_FUEL": "VEHICLE_FUEL",
    "COMPANY_CARS_LEASE": "VEHICLE_LEASE",
    "COMPANY_CARS_MAINTENANCE": "VEHICLE_REPAIRS",
    # Semantic consolidation (BANK_WHY_SEMANTIC_CONSOLIDATION_001, 2026-10-21)
    "PROPERTY_TAXES": "OCCUPANCY_PROPERTY_CHARGES",
    "BUSINESS_MEAL": "MEALS_ENTERTAINMENT",
    "PAYROLL_SERVICE_FEES": "ACCOUNTING_BOOKKEEPING",
    "PAYMENT_EQUIPMENT_SERVICE": "MERCHANT_PROCESSING_FEE",
    "CARD_ANNUAL_FEE": "BANK_SERVICE_CHARGE",
    "LOAN_FEES": "INTEREST_EXPENSE",
    "SMALLWARES": "RESTAURANT_OPERATING_SUPPLIES",
    "GROUNDS_MAINTENANCE": "FACILITY_MAINTENANCE",
    "RETIREMENT_PLAN_CONTRIBUTIONS": "EMPLOYEE_BENEFITS",
    "EMPLOYEE_GIFTS_EVENTS": "OTHER_PERSONNEL_COST",
    "FOH_CONTRACT_LABOR": "CONTRACT_1099_LABOR",
    "BOH_CONTRACT_LABOR": "CONTRACT_1099_LABOR",
}
# Merges whose WHAT differs: same meaning; the survivor's WHAT applies to NEW
# assignments only, every historical decision keeps its recorded WHAT snapshot.
DEST_CHANGE_OK = {"BUSINESS_MEAL", "EMPLOYEE_GIFTS_EVENTS"}

# New WHYs: (code, name, group, definition, basis, account code or None)
NEW = [
    ("CATERING_EVENT_REVENUE", "Catering / Event Revenue", "REVENUE", "Payment received for catering, banquets or private events.", U + "Other Operating Income - Banquet and Catering", "4310"),
    ("SUPPLIER_REBATES", "Supplier Rebates", "REVENUE", "Rebate received from a supplier or manufacturer on purchased products.", U + "Other Operating Income - Product Rebates", "4320"),
    ("DELIVERY_PLATFORM_PAYOUT", "Delivery Platform Payout", "DEPOSITS_SETTLEMENTS", "Payout from a third-party delivery or ordering platform for sales already recorded.", RF1, "1210"),
    ("RETIREMENT_PLAN_CONTRIBUTIONS", "Retirement Plan Contributions", "PAYROLL", "Employer contributions to employee retirement plans.", U + "Employee Benefits - Insurance and Retirement", "6600"),
    ("EMPLOYEE_GIFTS_EVENTS", "Employee Gifts & Events", "PAYROLL", "Gifts, awards and parties for employees.", U + "Employee Benefits - Other Employee Expenses", "6600"),
    ("CLEANING_SUPPLIES", "Cleaning Supplies", "DIRECT_OPERATING", "Detergents, chemicals and cleaning materials.", U + "Direct Operating Exp. - Cleaning Supplies", "7810"),
    ("SMALLWARES", "Tableware, Smallwares & Kitchen Utensils", "DIRECT_OPERATING", "China, glassware, flatware, utensils and small kitchen tools.", U + "Direct Operating Exp. - Tableware and Smallwares", "7830"),
    ("FLOWERS_DECORATIONS", "Flowers & Decorations", "DIRECT_OPERATING", "Flowers, plants and dining-room decorations.", U + "Direct Operating Exp. - Flowers and Decorations", "7830"),
    ("EQUIPMENT_RENTAL", "Equipment / Other Rentals", "DIRECT_OPERATING", "Short-term rental of equipment, furniture or other items.", U + "Direct Operating Exp. - Equipment/Other Rentals", "7970"),
    ("LAUNDRY_DRY_CLEANING", "Laundry & Dry Cleaning", "DIRECT_OPERATING", "Laundry and dry cleaning of uniforms, drapes and textiles.", U + "Direct Operating Exp. - Laundry and Dry Cleaning", None),
    ("DONATIONS_SPONSORSHIPS", "Donations & Sponsorships", "MARKETING", "Donations, community projects and sponsorships.", U + "Marketing - Public Relations and Publicity", "7500"),
    ("RESERVATION_LOYALTY_PLATFORMS", "Reservation & Loyalty Platforms", "MARKETING", "Reservation systems, loyalty programs and guest marketing platforms.", U + "Marketing - Direct Response / Other - Reservation System", "7500"),
    ("PAYROLL_SERVICE_FEES", "Payroll Service Fees", "OFFICE_ADMIN", "Fees charged by a payroll service provider.", U + "G&A - Accounting and Payroll", "7610"),
    ("GROUNDS_MAINTENANCE", "Grounds & Parking Lot Maintenance", "FACILITY", "Landscaping, sidewalk and parking-lot upkeep.", U + "Repairs and Maintenance - Grounds and Parking Lot", "7320"),
    ("PROPERTY_TAXES", "Property Taxes", "OCCUPANCY", "Real estate and personal property taxes on the premises and contents.", U + "Occupancy Costs - Real Estate / Personal Property Taxes", "7130"),
    ("CARD_ANNUAL_FEE", "Credit Card Annual Fee", "BANKING", "Annual membership fee of a business credit card.", U + "G&A - Bank Charges", "7220"),
    ("LOAN_FEES", "Loan / Financing Fees", "BANKING", "Fees for obtaining or maintaining a loan or credit line.", U + "Interest Expense - Other", "8200"),
    ("CARD_CHARGEBACKS", "Card Chargebacks", "BANKING", "Card sales reversed by a customer dispute.", U + "G&A - Bad Debts and Backcharges", None),
    ("GREASE_WASTE_SALES", "Grease & Waste Sales", "OTHER_INCOME_EXPENSE", "Income from selling used grease, recyclables or waste.", U + "Other (Income) Expense - Grease and Waste Sales", "8500"),
    ("INSURANCE_CLAIM_PROCEEDS", "Insurance Claim Proceeds", "OTHER_INCOME_EXPENSE", "Payment received from an insurer on a claim.", RF1, "8500"),
    ("INCOME_TAX_PAYMENT", "Income Tax Payment", "TAXES", "Federal or state income tax paid by the business.", U + "Federal and State Income Taxes", None),
    ("BUSINESS_TAX_PAYMENT", "State / Local Business Taxes", "TAXES", "Franchise, business-receipt and other state or local business taxes.", U + "G&A - State Business Taxes", None),
    ("FURNITURE_FIXTURES_CAPEX", "Furniture & Fixtures Purchase - Capital", "CAPITAL_PROJECTS", "Purchase of furniture or fixtures recorded as a fixed asset.", U + "Property and Equipment - Furniture and Equipment", "1510"),
    ("VEHICLE_PURCHASE_CAPEX", "Vehicle Purchase - Capital", "CAPITAL_PROJECTS", "Purchase of a company vehicle recorded as a fixed asset.", U + "Property and Equipment - Automobiles and Trucks", "1540"),
    ("SECURITY_DEPOSIT_PAID", "Security Deposit Paid", "CAPITAL_PROJECTS", "Refundable deposit paid to a landlord or utility; an asset, not an expense.", U + "Other Assets - Deposits", "1320"),
    ("LOAN_PRINCIPAL_REPAYMENT", "Loan Principal Repayment", "LOANS_FINANCING", "Repayment of loan principal; reduces the liability, not an expense. Interest goes to Interest Expense.", U + "Notes Payable", "2600"),
]


# BANK_WHY_REQUIRES_WHAT_001 — a WHAT for a WHY that has NONE, only where the
# existing catalog holds a correct match. Never changes an existing link.
# (code, account, why it is correct)
COMPLETE_WHAT = [
    ("PAYROLL_TAX_PAYMENT", "2420", "a payroll-tax remittance settles Payroll Tax Payable (employer and withheld amounts together); no employer-only expense is asserted"),
    ("PAYROLL_WAGES_PAYMENT", "2410", "an aggregate net-wage disbursement settles Payroll Payable"),
    ("CONTRACT_1099_LABOR", "6800", "Temporary / Contract Restaurant Labor needs no FOH/BOH role"),
    ("LINEN_SERVICE", "7830", "USAR Direct Operating Exp. - Linen; RF1 posts direct operating supplies to 7830"),
    ("LAUNDRY_DRY_CLEANING", "7810", "laundry and dry cleaning is a cleaning service (7810 Janitorial / Cleaning)"),
    ("PAYMENT_EQUIPMENT_SERVICE", "7210", "USAR G&A - Credit Card Fees: card-processing equipment/service charges"),
    ("CARD_CHARGEBACKS", "4920", "a chargeback reverses a sale: Refunds / Returns (contra revenue)"),
]


def describe(definition, basis, note, previous):
    text = f"{definition} Basis: {basis}."
    if note:
        text += f" TO REVIEW: {note}"
    if previous and not previous.startswith("Canonical RF-One WHY") and not previous.startswith("RF1 catalog"):
        text += f" Prior note: {previous}"
    return f"RF1 catalog ({TAG}). {text}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    db = Path(args.db)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log = {"task": TAG, "db": str(db), "at": stamp, "groups": [], "kept": [], "renamed": [],
           "review": [], "added": [], "merged": [], "what_missing": [], "problems": []}

    con = sqlite3.connect(db, timeout=30)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    reasons = {r["code"]: dict(r) for r in cur.execute("SELECT * FROM bank_transaction_reasons")}
    accounts = {r["code"]: dict(r) for r in cur.execute("SELECT * FROM bank_accounting_classifications")}
    acc_by_id = {a["id"]: a for a in accounts.values()}

    # Every existing active WHY must be planned exactly once.
    active = {c for c, r in reasons.items() if r["status"] == "ACTIVE"}
    planned = set(E) | set(MERGES) | {n[0] for n in NEW}
    unplanned = active - planned
    if unplanned:
        sys.exit(f"Refused: WHYs not covered by the plan: {sorted(unplanned)}")
    for absorbed, survivor in MERGES.items():
        a, s = reasons.get(absorbed), reasons.get(survivor)
        if a is None or s is None:
            sys.exit(f"Refused: merge {absorbed}->{survivor} references a missing WHY")
        if (a["status"] == "ACTIVE" and absorbed not in DEST_CHANGE_OK
                and a["accounting_classification_id"] != s["accounting_classification_id"]):
            sys.exit(f"Refused: merge {absorbed}->{survivor} would change the accounting destination")
    # AI rules must not reference an absorbed WHY.
    absorbed_ids = {reasons[c]["id"] for c in MERGES}
    for rule_id, spec in cur.execute("SELECT rule_id, spec FROM bank_ai_rule_versions"):
        s = json.loads(spec or "{}")
        ids = set(s.get("allowed_why_ids") or []) | {b.get("why_id") for b in s.get("branches") or []}
        if ids & absorbed_ids:
            sys.exit(f"Refused: AI rule {rule_id} references an absorbed WHY; extend the plan first.")

    if args.apply:
        backup_dir = db.parent / "previous"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"rfone_before_why_usar_{stamp}.db"
        with sqlite3.connect(backup) as dst:
            con.backup(dst)
        log["backup"] = str(backup)
        cur.execute("BEGIN IMMEDIATE")

    # --- groups ---
    groups = {r["code"]: dict(r) for r in cur.execute("SELECT * FROM bank_reason_groups")}
    for order, (code, name, basis) in enumerate(GROUPS, start=1):
        g = groups.get(code)
        if g is None:
            cur.execute("INSERT INTO bank_reason_groups (code, name, display_order, active) VALUES (?,?,?,1)",
                        (code, name, order * 10))
            groups[code] = {"id": cur.lastrowid, "code": code, "name": name}
            log["groups"].append({"code": code, "name": name, "action": "added", "basis": basis})
        else:
            cur.execute("UPDATE bank_reason_groups SET name=?, display_order=?, active=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (name, order * 10, g["id"]))
            log["groups"].append({"code": code, "id": g["id"], "old_name": g["name"], "name": name,
                                  "action": "kept" if g["name"] == name and g["active"] else "renamed/reactivated",
                                  "basis": basis})

    # --- existing WHYs ---
    for code, (group, name, definition, basis, note) in E.items():
        r = reasons[code]
        new_name = name or r["name"]
        desc = describe(definition, basis, note, r["description"])
        cur.execute("UPDATE bank_transaction_reasons SET name=?, description=?, reason_group_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_name, desc, groups[group]["id"], r["id"]))
        entry = {"id": r["id"], "code": code, "name": new_name, "group": group}
        if new_name != r["name"]:
            log["renamed"].append({**entry, "old_name": r["name"]})
        (log["review"] if note else log["kept"]).append({**entry, "note": note} if note else entry)
        acc = acc_by_id.get(r["accounting_classification_id"])
        if acc is None:
            log["what_missing"].append(entry)

    # --- new WHYs ---
    for code, name, group, definition, basis, account in NEW:
        acc_id = accounts[account]["id"] if account else None
        if account and accounts[account]["node_type"] == "GROUP":
            sys.exit(f"Refused: {code} would point at reporting group {account}")
        desc = describe(definition, basis, None, None)
        existing = reasons.get(code)
        if existing is None:
            cur.execute("""INSERT INTO bank_transaction_reasons (code, name, description, status, accounting_classification_id, reason_group_id)
                           VALUES (?,?,?,'ACTIVE',?,?)""", (code, name, desc, acc_id, groups[group]["id"]))
            new_id = cur.lastrowid
        elif existing["status"] != "ACTIVE":
            continue        # already merged into a canonical WHY
        else:
            new_id = existing["id"]
            cur.execute("UPDATE bank_transaction_reasons SET name=?, description=?, reason_group_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (name, desc, groups[group]["id"], new_id))
        log["added"].append({"id": new_id, "code": code, "name": name, "group": group, "account": account})
        if account is None:
            log["what_missing"].append({"id": new_id, "code": code, "name": name, "group": group})

    # --- merges ---
    for absorbed, survivor in MERGES.items():
        a, s = reasons[absorbed], reasons[survivor]
        if a["status"] != "ACTIVE":
            continue
        s_name = E[survivor][1] or s["name"]
        moved = {}
        moved["explanations"] = cur.execute(
            "UPDATE bank_transaction_explanations SET transaction_reason_id=?, transaction_reason_name_snapshot=? WHERE transaction_reason_id=?",
            (s["id"], s_name, a["id"])).rowcount
        moved["allocations"] = cur.execute(
            "UPDATE bank_transaction_allocations SET transaction_reason_id=?, transaction_reason_name_snapshot=? WHERE transaction_reason_id=?",
            (s["id"], s_name, a["id"])).rowcount
        moved["who_defaults"] = cur.execute(
            "UPDATE bank_occurrences SET default_transaction_reason_id=? WHERE default_transaction_reason_id=?",
            (s["id"], a["id"])).rowcount
        moved["who_knowledge"] = cur.execute(
            "UPDATE bank_who_knowledge SET suggested_reason_id=? WHERE suggested_reason_id=?",
            (s["id"], a["id"])).rowcount
        assoc = 0
        for row in cur.execute("SELECT * FROM bank_occurrence_reason_associations WHERE transaction_reason_id=?",
                               (a["id"],)).fetchall():
            other = cur.execute("SELECT * FROM bank_occurrence_reason_associations WHERE occurrence_id=? AND transaction_reason_id=?",
                                (row["occurrence_id"], s["id"])).fetchone()
            if other is None:
                cur.execute("UPDATE bank_occurrence_reason_associations SET transaction_reason_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (s["id"], row["id"]))
            else:
                cur.execute("""UPDATE bank_occurrence_reason_associations SET active=MAX(active, ?),
                               confirmation_count=confirmation_count+?,
                               first_confirmed_at=MIN(COALESCE(first_confirmed_at, ?), COALESCE(?, first_confirmed_at)),
                               last_confirmed_at=MAX(COALESCE(last_confirmed_at, ?), COALESCE(?, last_confirmed_at)),
                               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (row["active"], row["confirmation_count"], row["first_confirmed_at"], row["first_confirmed_at"],
                             row["last_confirmed_at"], row["last_confirmed_at"], other["id"]))
                cur.execute("DELETE FROM bank_occurrence_reason_associations WHERE id=?", (row["id"],))
            assoc += 1
        moved["who_associations"] = assoc
        cur.execute("UPDATE bank_transaction_reasons SET status='INACTIVE', reason_group_id=?, description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (groups[E[survivor][0]]["id"],
                     f"RF1 catalog ({TAG}): merged into {survivor} (id {s['id']}) — same meaning, same accounting destination. "
                     f"Kept inactive so historical references stay valid. Prior note: {a['description'] or '-'}",
                     a["id"]))
        log["merged"].append({"absorbed": absorbed, "absorbed_id": a["id"], "absorbed_name": a["name"],
                              "into": survivor, "into_id": s["id"], "moved": moved})

    # --- complete missing WHATs (BANK_WHY_REQUIRES_WHAT_001) ---
    log["what_completed"] = []
    for code, account, why in COMPLETE_WHAT:
        row = cur.execute("SELECT id, accounting_classification_id, description FROM bank_transaction_reasons WHERE code=?",
                          (code,)).fetchone()
        acc = accounts[account]
        if not acc["active"] or acc["statement_type"] is None or acc["node_type"] == "GROUP":
            sys.exit(f"Refused: {account} is not a valid WHAT for {code}")
        if row["accounting_classification_id"] not in (None, acc["id"]):
            continue        # an existing link is never changed
        if row["accounting_classification_id"] == acc["id"] and "WHAT completed" in (row["description"] or ""):
            continue
        cur.execute("UPDATE bank_transaction_reasons SET accounting_classification_id=?, description=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (acc["id"], f"{row['description']} WHAT completed ({account} {acc['name']}): {why}.", row["id"]))
        log["what_completed"].append({"id": row["id"], "code": code, "account": account, "why": why})
    log["what_missing"] = [x for x in log["what_missing"]
                           if x["code"] not in {c for c, _, _ in COMPLETE_WHAT}]

    # --- retire emptied groups ---
    for code in RETIRED_GROUPS:
        g = groups.get(code)
        if g is None:
            continue
        left = cur.execute("SELECT COUNT(*) FROM bank_transaction_reasons WHERE reason_group_id=? AND status='ACTIVE'", (g["id"],)).fetchone()[0]
        if left == 0:
            cur.execute("UPDATE bank_reason_groups SET active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?", (g["id"],))
            log["groups"].append({"code": code, "id": g["id"], "action": "deactivated (emptied)"})

    # --- integrity checks inside the transaction ---
    fk = cur.execute("PRAGMA foreign_key_check").fetchall()
    fk = [tuple(x) for x in fk if x[2] in ("bank_transaction_reasons", "bank_reason_groups")]
    if fk:
        log["problems"].append(f"foreign key violations: {fk[:10]}")
    ungrouped = cur.execute("""SELECT code FROM bank_transaction_reasons r WHERE status='ACTIVE' AND (reason_group_id IS NULL OR
        reason_group_id NOT IN (SELECT id FROM bank_reason_groups WHERE active=1))""").fetchall()
    if ungrouped:
        log["problems"].append(f"active WHYs outside an active group: {[x[0] for x in ungrouped]}")
    inactive_refs = cur.execute("""SELECT COUNT(*) FROM bank_transaction_explanations e JOIN bank_transaction_reasons r
        ON r.id=e.transaction_reason_id WHERE r.status='INACTIVE'""").fetchone()[0]
    if inactive_refs:
        log["problems"].append(f"{inactive_refs} movements still point at an inactive WHY")

    if args.apply and not log["problems"]:
        con.commit()
        out = Path(log["backup"]).with_suffix(".changes.json")
        out.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
        log["log"] = str(out)
        print(f"APPLIED. Backup: {log['backup']}  Change log: {out}")
    else:
        con.rollback()
        print("DRY RUN (nothing written)" if not log["problems"] else "ROLLED BACK — problems found")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in log.items()}, indent=1))
    for p in log["problems"]:
        print("PROBLEM:", p)
    return 1 if log["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
