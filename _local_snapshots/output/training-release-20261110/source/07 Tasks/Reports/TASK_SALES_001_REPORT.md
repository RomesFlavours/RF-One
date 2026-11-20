# TASK_SALES_001 — Sales Domain Completion Audit — Report

**Task:** TASK_SALES_001
**Scope:** Restaurant Domain / Sales module, audit only (no application implementation)
**Repository:** RF One

---

## A. Executive conclusion

**GAPS FOUND.**

The canonical Sales model (`01 Domains/Restaurant/Sales/Restaurant Sales Model.md`) is substantially more mature than the repository's own `Roadmap.md` indicated before this audit — it already provides a genuinely provider-independent, historically-immutable model of Table Service, Order, Order Item, Payment, Tip, Tax, Fees, and Discounts, and it explicitly separates atomic facts from derived Performance metrics. Most of the 14 reality scenarios in this task's brief are already representable once a small number of missing cross-references (Location, Commercial Catalog Item/Modifier) and one missing entity (Refund) are documented — all fixed directly during this audit, see § G.

However, three genuine Critical Domain Gaps remain and block a COMPLETE verdict:

1. **Order Item quantity.** The canonical model's own stated principle — one Order Item row per physical sold unit, no `quantity` field, "Order Item = aggregated quantity" listed as a forbidden assumption (§7, §25) — is contradicted by confirmed real restaurant sales evidence: a single sold line can itself be a fractional quantity (e.g. a half portion), which cannot be represented as a whole number of repeated unit-rows. This is not a Clover artifact; it is real economic reality the model cannot currently express.
2. **Business Date.** No concept anywhere in the Domain distinguishes the restaurant's operating day from a literal timestamp. A restaurant open past midnight cannot have its late-night sales correctly attributed to "last night" rather than "this morning."
3. **Order/Item Void and Cancellation before settlement.** The model has no way to represent an item removed or an order abandoned before payment, and therefore no way to distinguish that event from a Refund occurring after a completed sale, as this task's own Scenario 6 requires.

None of these three is fixable by documentation clarification alone — each requires either amending an already-Approved principle (quantity) or a genuine architectural choice among real alternatives (business date, void). They are reported in § E and § O rather than resolved unilaterally, per this task's instructions.

---

## B. Canonical Sales model found

From `Sales/Restaurant Sales Model.md` (the only substantive canonical Sales file prior to this audit, alongside `Sales/Combo.md` in Commercial Catalog):

| Entity | Responsibility |
|---|---|
| `TABLE_SERVICE` | One real service occasion involving a group of guests — the operational context Orders, people, and physical tables relate through. Not the physical table, not the POS Order. |
| `PHYSICAL_TABLE` | A persistent restaurant resource (table_number, seat_capacity, area). M:N with Table Service. |
| `ORDER` | Commercial/POS grouping of sold units and settlements within a Table Service. Owns subtotal/discount/tax/total, sold units, order-level discounts, tax, mandatory fees, and the payments that settle it. |
| `ORDER_ITEM` | The atomic sales event — one individual sold unit, referencing `ITEM`, preserving historical unit price and `guest_number` independent of later catalog changes. |
| `ITEM` (via Commercial Catalog) | Anything the restaurant can sell — not "current menu item." Cross-referenced (this audit) to Commercial Catalog's canonical `Item.md`. |
| `PAYMENT` | Independent atomic settlement entity; an Order may have many. |
| `TIP` | Belongs to Payment, not Order; higher-level Tip totals are always derived sums, never stored aggregates. |
| `TAX` | Belongs to Order; Payment settles it but never owns it. |
| `ORDER_FEE` | Order-level mandatory fee (Service Charge, Cork Fee, etc.), explicitly distinct from Tip. |
| `ORDER_DISCOUNT` / `ORDER_ITEM_DISCOUNT` | Two structurally distinct discount levels, never collapsed. |
| `MODIFIER` / `MODIFIER_GROUP` (via Commercial Catalog) | POS-selected variant/option on an Order Item. Cross-referenced (this audit) to Commercial Catalog's canonical `Modifier.md`/`ModifierGroup.md`. |
| `REFUND` (added by this audit, § G) | Independent economic reversal fact against an Order/Payment, never rewriting the original. |
| `declared_guest_count` / `derived_guest_count` | Two independently preserved guest-count facts, kept apart deliberately to surface process/data-quality mismatches. |

The model's stated design principle (§1) is explicit and correct: preserve atomic operational facts, derive metrics later; do not structure around a POS export, a spreadsheet, or a KPI dashboard.

---

## C. Sales lifecycle coverage

| Concept | Status |
|---|---|
| Service Context (Table Service, Physical Table, Employee participation) | COMPLETE |
| Order | COMPLETE (Location cross-reference added by this audit) |
| Order Item | PARTIAL — quantity semantics contradict real evidence (§ E.1) |
| Modifier | COMPLETE (price-adjustment historical preservation clarified by this audit) |
| Discount | COMPLETE (fixed-vs-percentage preservation clarified by this audit) |
| Tax | COMPLETE |
| Payment | COMPLETE |
| Tip | COMPLETE (owned by `Tips/` module, correctly consuming Payment-attached fact) |
| Refund | COMPLETE (added by this audit, § G) — previously MISSING |
| Void/Reversal (before settlement) | MISSING (§ E.3) |

---

## D. Scenario validation

1. **Simple dine-in sale** — PASS. TableService, PhysicalTable, Employee(s), Order, Order Items, Tax, Payment, Tip are all directly representable.
2. **Split payment** — PASS. `ORDER 1:N PAYMENT`, each Payment carries its own independent Tip; no ambiguity in the model.
3. **Fixed discount** — PASS (after this audit's fix to §18 clarifying `amount` is preserved as its own independently optional fact, never derived from a percentage).
4. **Percentage discount** — PASS (same fix; percentage is preserved as evidence and the resulting monetary amount is always determinable).
5. **Item discount** — PASS. `ORDER_ITEM_DISCOUNT` is structurally distinct from `ORDER_DISCOUNT`; `Order.subtotal/discount_total/total` remain reconciliable.
6. **Item void before payment** — FAIL. No concept exists to record that an item was entered and removed before settlement, or to distinguish that event from a later Refund. See § E.3.
7. **Full refund next day** — PARTIAL. The new Refund entity (§ G) correctly keeps Monday's sale intact and represents Tuesday's refund as an independent later fact — but "business date" itself cannot be represented at all (§ E.2), so the scenario's exact operating-day framing is only partly satisfiable.
8. **Partial refund** — PASS. Refund is independently amount-bearing and multiple Refunds per Payment are explicitly supported; the original Payment is never rewritten.
9. **Modifier pricing** — PASS (after this audit's fix to §19 clarifying that `ORDER_ITEM_MODIFIER` preserves its own historical price impact, independent of the Modifier's current catalog price).
10. **Quantity** — FAIL. Three identical units sold as quantity 3 collides directly with the model's "one row per unit, no quantity field" principle when the same mechanism must also represent a single fractional-quantity line (see § E.1) — the model does not yet have a coherent, evidence-consistent position on quantity.
11. **Takeout** — PASS. Table Service ↔ Physical Table is explicitly optional M:N ("a service with no physical table, such as To Go").
12. **Across midnight** — FAIL. No Business Date concept exists anywhere in the Domain (§ E.2).
13. **Multiple locations** — PASS (after this audit's fix adding a `location_id` cross-reference on Order to `Organization/Restaurant Profile.md`'s Restaurant↔Location model). Transactions remain Location-specific while Items/Modifiers stay canonically shared via Commercial Catalog.
14. **POS incomplete evidence** — PASS. The model is built around optional, per-fact evidence throughout (§4, §23), explicitly rejecting "missing source value = zero" and similar assumptions.

---

## E. Critical Domain Gaps

### E.1 — Order Item quantity model contradicts real restaurant reality

`Restaurant Sales Model.md` §7 states the design principle "`ORDER_ITEM` = one individual sold unit" and explicitly forbids the assumption "Order Item = aggregated quantity" (§25). This is a deliberate, reasoned choice (preserve three identical sold units as three rows, not one row with `quantity=3`) — but real restaurant sales data includes lines that are themselves fractionally quantified (e.g. a single sold line representing half a portion), which cannot be expressed by repeating whole-unit rows. A `quantity` field is structurally required to represent this reality; the current principle prevents it.

This is not a Clover peculiarity to be filtered out — a fractional-quantity sale is genuine restaurant reality (portion-based selling), and the audit principle "do not omit necessary Sales concepts merely because [a source] does not expose them cleanly" cuts the other way here: this is a concept the Domain itself needs, independent of any POS.

**Affected files/concepts:** `Sales/Restaurant Sales Model.md` §7, §25.
**Why it matters:** Without resolution, RF-One cannot correctly record a class of real sold-unit facts, which corrupts any downstream count-based or per-unit metric derived from Order Items.
**Smallest reasonable correction:** Add an explicit, provider-independent `quantity` fact (decimal, never defaulted, present only when the source explicitly states it) to `ORDER_ITEM`, and revise the §25 non-assumption accordingly. See § O — this is a substantive amendment to an Approved document and is reported rather than made unilaterally.

### E.2 — No Business Date concept

Nothing in the Sales Domain (or, per the background research performed for this audit, anywhere else in the repository) distinguishes a restaurant's operating/business day from a literal event timestamp. A restaurant open past midnight has no way to have its post-midnight activity correctly attributed to the prior operating day rather than the calendar day the timestamp falls on.

**Affected files/concepts:** `Sales/Restaurant Sales Model.md` (Order, Table Service); no equivalent concept exists in `Organization/Restaurant Profile.md` either.
**Why it matters:** Nightly sales reporting, shift-based Tip/Payroll periods, and any "yesterday vs. today" operational question are all ambiguous without it — this is ordinary restaurant reality, not an edge case.
**Smallest reasonable correction:** Define a Restaurant-configured operating-day cutoff (e.g., on Restaurant Profile) and a resulting `business_date` fact attributable to Table Service/Order. See § O — genuine architectural alternatives exist for where this cutoff and the derived fact should live, so this is reported for a decision rather than guessed.

### E.3 — No Order/Item Void or Cancellation concept

The model has no way to represent an item entered and removed before settlement, or an order abandoned before payment, and therefore cannot satisfy this task's own Scenario 6 ("system can distinguish this from a later refund"). This also connects to the model's own stated concern for using data-quality evidence to detect process/malpractice issues (§23) — an unrecorded void is exactly the kind of event that concern anticipates but the model does not yet capture.

**Affected files/concepts:** `Sales/Restaurant Sales Model.md` — no section addresses Order/Item lifecycle status before settlement.
**Why it matters:** Refund (after settlement) and Void (before settlement) are economically and operationally distinct events; collapsing "no evidence of a void" into "therefore nothing to model" forecloses ever recording this even where a future source could supply it.
**Smallest reasonable correction:** Not proposed here — see § O. Genuine open question: whether any current or plausible future POS source can even supply void-before-settlement evidence at all (§ I), which should inform whether/how the Domain models it.

---

## F. Domain Clarifications

**None remaining.** The clarifications found during this audit (discount amount-vs-percentage preservation, Modifier historical price-impact preservation, Item/Modifier/ModifierGroup's relationship to Commercial Catalog, Order's relationship to Location) were all cases where the intended architecture was already evident from the rest of the repository, and were resolved directly as documentation fixes — see § G.

One boundary is worth recording as background, not as a blocking clarification: `Restaurant Semantic Model.md` §"Related documents" already self-discloses that `Sales/Restaurant Sales Model.md` "does not reference Operational Area/Physical Area/Restaurant Role at this time" — `PHYSICAL_TABLE.area`/`section/location` (§3) remain loose descriptive attributes rather than a formal reference to the canonical `Physical Area` entity in `Organization/Physical Area.md`. This is a pre-existing, self-acknowledged boundary, not a new finding, and does not block any of the 14 scenarios.

---

## G. Documentation fixes made during this audit

All changes are to existing files; no new database tables, APIs, or services were created.

**`01 Domains/Restaurant/Sales/Restaurant Sales Model.md`:**
- Added a `location_id` field and a cross-reference to `Organization/Restaurant Profile.md`'s Restaurant↔Location model on `ORDER` (§6).
- Added an explicit cross-reference stating that `ITEM`, `MODIFIER`, and `MODIFIER_GROUP` are the same canonical entities defined by Commercial Catalog (`Item.md`, `Modifier.md`, `ModifierGroup.md`), not parallel Sales-owned definitions (§9).
- Added new § 14a, **Refund** — a provider-independent canonical definition of Refund as an independent atomic fact (nullable links to Order/Payment, never rewrites the original, may be partial, may occur on a later business date, existence must not be inferred from Order/Payment status fields, relationship to Tip reversal is evidence-based not assumed). This concept previously did not exist anywhere in the canonical Sales Domain despite being a fully implemented, well-reasoned entity in the software layer (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §10) and being required by this task's own Scenarios 7–8.
- Added a clarification to § 18 (Discounts) that `percentage` and `amount` are independently preserved facts, neither derived from the other.
- Added a clarification to § 19 (Modifier) that `ORDER_ITEM_MODIFIER` preserves its own historical price impact, independent of the Modifier's current catalog price.
- Extended the § 25 non-assumption list with three Refund-related non-assumptions ("Refund status = visible in Order/Payment status fields," "Refund = full reversal unless evidenced," "Refund business date = Order business date").

**`01 Domains/Restaurant/Roadmap.md`:**
- Corrected a stale classification: Sales was still listed under "Partial" as "only the Combo concept is documented," left over from the same commit that actually added the 800+ line `Restaurant Sales Model.md`. Moved to "Documented" with an accurate summary and a pointer to this report's open items.
- Updated the "Planned Restaurant knowledge areas" § 2 bullet for Sales (KD-003) to reflect that the Order/Payment/Refund/Discount/Tip model now exists, narrowing the remaining planned work to void/cancellation semantics and the still-empty Clover/Toast provider-mapping scaffolds.

---

## H. Implementation gaps (software, not Domain — recorded, not fixed)

- **`Sales/Clover/*.md` (10 files) and `Sales/Toast/README.md` are entirely empty scaffolding.** Real Clover-specific mapping knowledge already exists — but only inside `03 Software/RF-One Data Store/CLOVER_INGESTION.md` and `03 Software/Clover Data Explorer/*.md` — and has never been distilled into the Domain's own provider-mapping folder. This is knowledge-transfer debt, not a Domain gap; per `Roadmap.md`'s own non-goals, filling these scaffolds was explicitly out of scope for this task.
- **Table Service reconstruction is unimplemented.** `table_services`, `physical_tables`, and the Table Service ↔ Employee/Physical Table linking tables exist in the schema but hold zero rows in the current database — the Domain and schema fully support Table Service, but no ingestion step currently populates it from Clover.
- **Item-level discounts (`order_item_discounts`) are structurally supported but empty** in the real ingested data — see § I, this may be a source limitation rather than a missing ingestion step.
- **Failed-Payment ingestion is schema-ready but not implemented.** The `payments` table is designed to be populated from Clover's complete top-level Payments collection (which includes `FAIL` results); the currently documented ingestion pipeline instead uses the Order-nested Payments collection, which silently excludes 36 failed payment attempts in the reconciled dataset. No ingestion code implementing the complete pipeline exists yet.

---

## I. Provider/Data Acquisition gaps (Clover-specific — recorded, not fixed)

- **No Merchant/Location timezone field exists in Clover** for this integration, which would make populating a Business Date (§ E.2) difficult even once the Domain concept is defined — a provider limitation layered on top of the Domain gap.
- **Line-item-level discounts are unavailable from Clover**: confirmed zero of 23,000+ line items in the full ingested history carry any discount field, even though the canonical `ORDER_ITEM_DISCOUNT` table structurally supports it.
- **Clover's own `Order.state`/`Order.paymentState`/`Payment.result`/`OrderItem.refunded` fields do not reliably reflect a Refund** — two known real refunds remain invisible in all four fields, confirmed by exact ID cross-reference. Whether Clover ever exposes a genuinely cancelled-before-completion order at all (as opposed to simply never finalizing/exporting one) was not established by the underlying research and remains an open acquisition question relevant to § E.3.
- **Refund evidence in the current dataset is thin**: only 2 real Refund records exist, both apparently full refunds — Scenario 8 (partial refund) and the `Refund.voided=true` case remain empirically unconfirmed against real data, though both are structurally supported by the schema and now by the Domain (§ G).

---

## J. Domain boundaries

- **Menu** — `Menu.md` is an empty scaffold; Sales correctly does not depend on it. `ITEM` (§8, cross-referenced to Commercial Catalog in this audit) is explicitly separated from menu presentation/exposure — a sound boundary independent of whether Menu.md itself is ever written.
- **Commercial Catalog** — Sales references `Item`, `Modifier`, `Modifier Group` (cross-references added in this audit); `Price`/`Tax Category` remain Catalog-owned and are consumed, not duplicated, by Sales' historical Order Item/Payment facts. Clean boundary.
- **People / Employees** — Sales' `EMPLOYEE` participation model (Table Service ↔ Employee, per-fact employee attribution) is deliberately generic and does not yet reference `Organization/Restaurant Role` or `Operational Area` — a boundary `Restaurant Semantic Model.md` already self-discloses as open (§ F), not newly found here, and not blocking.
- **Locations** — now explicitly cross-referenced on Order (§ G) to `Organization/Restaurant Profile.md`'s Restaurant↔Location model.
- **Performance** — correctly stays out of Sales. `Personnel Management/Performance/Performance.md` treats Sales-derived facts (transactions, gross, product mix) purely as consumed Evidence; Sales does not own or duplicate any Performance concept.
- **Tips** — clean boundary, already well-documented: Sales owns the atomic `Tip` fact attached to Payment; `Tips/` module owns post-hoc allocation to Employees. `Tips/Tip.md` explicitly consumes, never redefines, this Sales fact.
- **Purchasing** — sell-side Discount (Sales, Order/Order Item level) and buy-side discount concepts (Purchasing, Purchase Line/Invoice level) are already explicitly distinguished in `07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md` §18 cross-reference. No overlap found.
- **Inventory** — not yet modeled anywhere in the repository; Sales does not claim to own it. Appropriate boundary for the current state.
- **Accounting/Financial** — no Financial Domain exists yet (deferred per `Roadmap.md` §3); Sales does not overreach into financial/accounting concepts. Appropriate.

---

## K. Historical integrity

Confirmed strong, with one addition made by this audit. Historical Order Item price is explicitly preserved independent of later Item price changes (§9); Commercial Catalog `Price` is itself immutable, versioned by validity period; Tip's temporal anchor is fixed to the Payment's own timestamp, never recalculation time. This audit's new Refund section (§ G) extends the same discipline to settlement reversal: the original Order/Payment is never rewritten by a later Refund, and this audit's Modifier clarification extends it to Modifier price impact. No historical-integrity violation was found anywhere in the canonical Sales model.

---

## L. Derived versus persisted data

Confirmed correct. § 22 of `Restaurant Sales Model.md` already explicitly separates atomic/observed facts (timestamps, Order Items, Payments, Tips, Discounts, Taxes, Fees, Modifiers) from derived measures (service duration, gross/guest, tip/hour, table turnover, product mix, and others) and states plainly that the derived list "belongs to analytics and Performance layers." `Performance.md` (Personnel Management) independently confirms it consumes Evidence rather than storing its own copy of raw Sales facts. No leakage found in either direction.

---

## M. Provider independence

Sales is genuinely POS-independent as documented: `Restaurant Sales Model.md` contains no Clover field names, API paths, or vendor-specific mechanisms anywhere in its text, before or after this audit's edits, and explicitly states its own scope boundary excludes them (§26). The software layer maintains equivalent discipline — every source-ingested entity uses an RF-One surrogate primary key with `(source_system_id, source_*_id)` kept as separate provenance columns, never as identity.

One process-level concern, not a textual contamination, is worth surfacing to the Product Owner: the Refund entity, the fixed-vs-percentage Discount distinction, and the fractional-quantity finding underlying § E.1 were all first established at the software layer (a task referred to in code comments as "TASK_CLOVER_003," for which no corresponding Domain-level task or report exists in `07 Tasks/`) rather than through the Documentation-First sequence CLAUDE.md specifies. In the Refund and Discount cases the resulting architecture was sound and has now been reflected back into the canonical Domain by this audit; in the quantity case (§ E.1) it directly contradicts the Domain's own Approved principle. This suggests Sales-adjacent software work has, at least once, proceeded ahead of Domain documentation rather than after it — worth a general reminder, not a specific correction beyond what § E.1 already reports.

---

## N. Exact files changed

- `01 Domains/Restaurant/Sales/Restaurant Sales Model.md` — modified (see § G for full list of additions)
- `01 Domains/Restaurant/Roadmap.md` — modified (see § G)
- `07 Tasks/Reports/TASK_SALES_001_REPORT.md` — created (this report)

No other files were modified. No database, API, ingestion, or UI code was touched.

---

## O. Product Owner decisions required

1. **Order Item quantity (§ E.1).** `Restaurant Sales Model.md` is marked Approved and explicitly forbids a `quantity` field on Order Item. Real evidence shows this principle cannot represent fractional-quantity sold lines. Recommend adding an explicit, provider-independent `quantity` fact (present only when a source explicitly states it, never defaulted) — but this is a substantive amendment to an Approved document's core principle, not a wording clarification, and needs explicit sign-off before `Restaurant Sales Model.md` §7/§25 are edited.
2. **Business Date (§ E.2).** RF-One needs a decision on where a Restaurant's operating-day cutoff is configured (most likely `Organization/Restaurant Profile.md`, alongside Restaurant↔Location) and how the resulting `business_date` fact attaches to Table Service/Order. Genuine alternatives exist for where this concept should live; not decided by this audit.
3. **Order/Item Void and Cancellation (§ E.3).** RF-One needs a decision on whether a Void/Cancellation concept, distinct from Refund, should be added to Sales at all, given the open question of whether any current or plausible future POS source can supply this evidence. If no source can ever supply it, the Product Owner may reasonably decide not to model it now — but that is a decision, not a default this audit should assume.

---

## P. Final readiness statement

`SALES DOMAIN STATUS: NOT COMPLETE — DOMAIN GAPS REQUIRE RESOLUTION`

Blocking gaps:

1. Order Item quantity model contradicts confirmed real restaurant sales evidence (§ E.1).
2. No Business Date concept exists to distinguish operating day from timestamp (§ E.2).
3. No Order/Item Void or Cancellation concept exists, distinct from Refund (§ E.3).
