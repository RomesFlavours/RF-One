# BANK_SPLIT_ALLOCATION_001 — One bank movement, several classification lines

**Status:** implemented on branch `feature/bank-why-discovery` (Bank) and `feature/cbank-why-rules` (C-Bank). It is not
migrated on the operational database and no allocation has been written. **Product Owner request:** 2026-11-01.
**Builds on:** BANK_ECONOMIC_ALLOCATION_FOUNDATION_001 (allocations), BANK_INVOICE_EVIDENCE_COLLABORATION_001
(invoice evidence → allocations), BANK_WHO_WHY_MODE_001 (UNIQUE / MULTIPLE WHO, WHO WHY rules).

## 1. Model — the QuickBooks Online "Split"

A bank movement stays **one** movement. It carries 1..N lines, and each line has:

- an amount;
- a WHY;
- the WHAT derived from that WHY;
- a description;
- references to the documents or items behind it.

The lines **are** `BankTransactionAllocation` rows. No second model was created. The foundation already guarantees
the rest:

- the amounts are signed integer cents in the movement's sign convention;
- the lines sum to the movement **exactly**, and a set that does not balance is refused;
- the P&L reads the lines, never the parent movement, so nothing is counted twice.

| Added | Where |
|---|---|
| `description` (the QBO line description) | `bank_transaction_allocations`, nullable |
| `evidence_detail` (JSON: the original rows grouped into the line — report, file, CSV line, order, ASIN, title, Family/Class/Commodity) | `bank_transaction_allocations`, nullable |
| QBO account correspondences (`CATEGORY` = WHAT → QBO expense account; `PAYMENT_ACCOUNT` = Source → QBO bank/card account) | `bank_qbo_account_maps`, empty |
| QBO export duplicate protection (`requestid`, payload hash, PREPARED/SENT) | `bank_qbo_exports`, empty |

Migration `b7e320261101` is additive only. Existing rows keep NULL in the new columns, and nothing is reinterpreted
or seeded. Both new columns are *deferred*, so ordinary reads of allocations do not select them.

## 2. Rules

The split rules are in `split_allocation.build`.

1. Items with the same WHY form **one line**, and every original row stays in the line's evidence. Different WHYs
   give different lines. WHAT comes from the WHY, so the same WHY always means the same WHAT.
2. When one WHY covers every item, the movement gets one line for its whole amount.
3. Several WHYs give one line per WHY, **only when every item has a detail amount**. The detail total must equal the
   movement. The only exception is an ancillary amount (TAX / SHIPPING / FEE / DISCOUNT) that the document states
   explicitly. That amount is apportioned with Purchasing's existing proportional rule
   (`invoice_allocation_bridge.proportional_split`, where the last line takes the odd cent), and it stays visible on
   each line as `ancillary_minor`.
4. When amounts are missing, the split stays incomplete:
   - two or more known WHYs without detail amounts → **"Importi di dettaglio mancanti"**;
   - items without a WHY → **"WHY articolo mancante"**.
   The movement is **never** divided in equal parts, the prevailing category is **never** used, and no amount is
   invented.
5. Any other difference is **"Differenza non spiegata"**. It is shown with its amount and never absorbed.
6. Amounts are read as exact decimals. An amount with more than two decimals is refused, never rounded.
7. WHOM keeps the existing logic, `row_reconciliation.for_whom_values`: the WHOM chosen for the movement, otherwise
   the Source owner at the movement date.
8. An incomplete split can be kept as a **draft** (`BankFlowArtifact` kind `SPLIT_DRAFT`), and nothing is allocated.
   A person confirms a complete split, and only then are the lines written as allocations (`decision_source = HUMAN`).

## 3. Amazon order report — meaning of the columns

These meanings were verified on the real export `orders_from_20260101_to_20261026_20261026_1345 (1).csv`: 118 rows,
103 orders and 96 Charge Identifiers.

| Column | Meaning |
|---|---|
| `Order Net Total` | The total of the **order**. It repeats on every row of the order and is constant within each of the 12 multi-row orders (e.g. 286.23 on each of the three fan rows). It is **not** an item price and is read once per order. |
| `Charge Identifier` | The card charge, the same code as the one in the bank description (exact whole token). One charge may cover several orders (its amount is their sum). An order under several charges is a partial charge. `N/A` means a cancelled or never-charged order (quantity 0, total 0.00): the row is kept but never matched. |
| `Payment Date` | The charge date. On the certain links, the bank date minus the payment date was 0–1 days; the accepted window is −1…+5 days. |
| `Item Quantity` | The units on the row. **Identical rows are separate real purchases** and are never de-duplicated. The three ceiling fans of order 111-7130700-7696250 are three rows (Product Owner). |
| `Title`, `Family`, `Class`, `Commodity`, `Amazon-Internal Product Category` | The product evidence used to choose the product's WHY. The Amazon category may be imprecise. |
| *(item price)* | **Not in the report.** A mixed order needs the detail amounts from another document (`AmazonEvidence.item_amounts`), or the person enters them on the Split page. |

## 4. Path and link certainty

```
bank movement → Charge Identifier → order(s) → purchased rows → product WHY → lines by WHY → split
```

| Link | Condition | Effect |
|---|---|---|
| CERTAIN | Exact code AND equal amount (sum of the orders' totals) AND compatible currency AND compatible date | The proposal may be complete. |
| CODE_ONLY | Exact code, but the amount, date or currency differs, or the charge is partial | Open, with the reason. |
| CANDIDATE | No code in the description, but the same amount and a compatible date as a charge with no coded movement | Open: **"Abbinamento solo candidato"**. |
| AMBIGUOUS | The same code on several movements | Open. |

Refunds and multiple charges:

- **Full refund** (money in, equal amount): the same lines with the positive sign.
- **Partial refund of a one-WHY order:** one line.
- **Partial refund of a mixed order:** **"Rimborso parziale di un ordine misto"**.
- **Several charges in one movement:** the amount is checked against their sum.

**Currency:** 13 of the 14 Sources have no configured currency. Their check is reported as `SOURCE_NOT_CONFIGURED`
and does not block the link. The report currency is USD.

## 5. Engine and the WHO UNIQUE / MULTIPLE path

The Amazon document rule (`document: amazon_order`) reads `AmazonOrders.read`, which uses `split_allocation`:

- **one WHY** for the products → that WHY (method `WHO WHY RULE`);
- **several WHYs** with detail amounts → a **complete split** (method `SPLIT`);
  - the movement is resolved by its lines; it does not stay open because it needs more than one WHY;
- **several WHYs** without amounts → the new open reason **`WHY_SPLIT_INCOMPLETE` "Ripartizione incompleta"**, which
  carries the proposal and its missing data;
- a link that is not certain → `WHY_DOCUMENT_MISSING` with the reason.

| C-Bank engine (`Result.split`) | Shown as |
|---|---|
| Proposal from a document | `origin = DOCUMENT` |
| Split already confirmed in Bank (2+ allocations) | `origin = BANK`. It is **protected**, as a human decision is; it removes the open WHY reasons; it is *Ripartizione incompleta* when it does not balance. |
| Complete split | WHY shown as "Ripartizione: N righe"; Category as the lines' WHATs. |

**WHO recognised ≠ classification complete ≠ split incomplete** are distinct states.

The three-stage simulation does not send a known WHO whose split is complete or incomplete to internet research. The
evidence never replaces a needed split with a single WHY.

## 6. Interface

**Bank › Bank Reconciliation › Split** (`/bank/split`):

- the linked movements with their link state and split state;
- the charges without a bank movement;
- the movements already split.

**Bank › … › Split › Movement #id** (`/bank/split/<id>`) shows:

- the movement and its bank total;
- the linked documents and their products (with file and CSV line);
- the editable lines (amount, WHY, WHAT from WHY, description);
- the split total and the difference;
- the state, or the reasons it is incomplete;
- *Keep as draft* / *Confirm split…* (a modal with a close X);
- the allocations written;
- the QBO preview.

The movements listed on *WHY Rules* link to their Split page. The new tile *Ripartizione incompleta* opens the splits.

## 7. QuickBooks Online export — model and local preview

**Format:** the QuickBooks Online Accounting API entity **Purchase** (the "Expense" in the QBO interface):
<https://developer.intuit.com/docs/api/accounting/purchase>.

**Idempotency:** the `requestid` query parameter, unique per company and at most 50 characters. A repeated request
returns the original response. See the QBO API best practices, and error 600 "Duplicate Request ID" in
<https://developer.intuit.com/app/developer/qbo/docs/develop/troubleshooting/error-codes>.

These facts come from the Intuit pages as returned by search; the pages themselves are rendered by script and could
not be read in full.

`qbo_export.purchase` builds, per movement, **one** Purchase:

| Field | Value |
|---|---|
| `PaymentType` | `CreditCard` for a card; `Cash` for a bank account |
| `AccountRef` | The mapped QBO account of the Source |
| `TotalAmt` | The movement |
| `Line[]` | One `AccountBasedExpenseLineDetail` per allocation (`Amount`, `Description`, the mapped expense `AccountRef`) |
| `DocNumber` | The document codes (e.g. the Charge Identifier) |
| `PrivateNote` | RF-One movement id and bank description |
| `Credit: true` | Only for a credit-card refund |

It never creates one payment per product.

**Blockers:**

- no split confirmed;
- split incomplete or unbalanced;
- QBO category not mapped;
- QBO bank/card account not mapped;
- already exported;
- split changed after the export;
- money in on a bank account (a QBO *Deposit*, outside this export).

`record_export` is the duplicate protection the future sender must call. The local preview writes nothing.

**Missing for the real integration:**

- the QBO app (OAuth 2.0 client, realm id);
- the company's QBO Account list, to fill `bank_qbo_account_maps`;
- the HTTP sender and its retry policy;
- a decision on the vendor (`EntityRef`) of Amazon and on Deposits.

**This supersedes the earlier documented intent** in BANK_INVOICE_EVIDENCE_COLLABORATION_001, which was "a
multi-category movement exports as one total line marked SPLIT REQUIRED". The Product Owner request of 2026-11-01
asks for one Purchase with several lines.

## 8. Code

| Concern | File |
|---|---|
| Split rules, Amazon evidence, drafts, confirmation | `rfone_data_store/bank_reconciliation/split_allocation.py` |
| QBO Purchase preview, mappings, duplicate protection | `rfone_data_store/bank_reconciliation/qbo_export.py` |
| Amazon document → WHY / split / incomplete split | `rfone_data_store/bank_reconciliation/who_why_rules.py` |
| Line description / evidence on allocations | `economic_allocation.AllocationSpec` |
| Pages | `RF-One Web/bank_split.py`, `templates/bank_split.html`, `static/bank-assistant/split.js` |
| Engine (`Result.split`, Bank split protection) | C-Bank `cbank/engine.py`; `cbank/three_stages.py`; `cbank/why_signals.py` |
| Read-only Amazon simulation | C-Bank `cbank/amazon_split.py` |
| Tests | C-Bank `tests/test_split_allocation.py`; Bank `RF-One Web/tests/test_bank_split_http.py` |
