# TASK_SALES_002 — Close Sales Domain Gaps — Report

**Task:** TASK_SALES_002
**Scope:** Restaurant Domain / Sales module, canonical documentation closure (no application implementation)
**Repository:** RF One

---

## A. Executive summary

All three Critical Domain Gaps identified by `07 Tasks/Reports/TASK_SALES_001_REPORT.md` (§ E) have been closed per the Product Owner's approved decisions:

1. `ORDER_ITEM` now carries an explicit, provider-independent, decimal `quantity` fact.
2. A canonical `business_date` concept now exists on `ORDER`, with the Business Day Rule configuration owned by `LOCATION`.
3. `ORDER_ITEM_VOID` and `ORDER_CANCELLATION` now exist as pre-settlement concepts, independent of `REFUND`.

`01 Domains/Restaurant/Sales/Restaurant Sales Model.md` was extended with new §§ 6a, 7 (Quantity, Quantity is not aggregation, Derived line amounts), 14b, and updated relationship diagram (§ 21), derived-metrics note (§ 22), and non-assumption list (§ 25). `01 Domains/Restaurant/Organization/Restaurant Profile.md` gained a new "Location Business Day Rule (Business Date)" section. `01 Domains/Restaurant/Roadmap.md` was updated to reflect Sales' completed status.

**SALES DOMAIN STATUS: COMPLETE — READY FOR FUTURE DEVELOPMENT** (see § P).

---

## B. Quantity decision implemented

**Old principle** (§7, pre-edit): `ORDER_ITEM = one individual sold unit`, with "Order Item = aggregated quantity" listed as a forbidden assumption (§25). No `quantity` field existed; a sale of 3 identical units required 3 rows, and a fractional sale (e.g. half a portion) could not be represented at all.

**New principle:** `ORDER_ITEM` = one recorded sold line / sold item occurrence, with its own observed `quantity` and historical economic attributes. Atomicity now concerns historical **event identity**, not a forced `quantity = 1`.

**Canonical quantity semantics** (§ 7, "Quantity"):
- decimal-capable (`0.5`, `1.5`, etc.), not whole-unit-only;
- preserves the source-observed quantity when available;
- never a provider-specific (e.g. Clover) encoding;
- never inferred from the number of Order Item rows;
- never silently defaulted (missing source quantity is preserved as missing, never assumed `1`);
- independent from historical unit price.

**Implications for metrics and historical integrity:** any previously implicit "row count = units sold" reading is now corrected — derived measures counting sold units must use `SUM(quantity)`, not `COUNT(Order Item rows)` (§ 22). Historical integrity is unaffected and reinforced: quantity is preserved per-fact exactly as observed, and `quantity` and unit price remain independently preserved atomic facts, consistent with the model's existing historical-preservation discipline (§ 9). A new "Quantity is not aggregation" subsection explicitly forbids merging two separately recorded identical-looking Order Item events into one — the quantity amendment does not license retroactive aggregation.

---

## C. Business Date model

**Location configuration:** `LOCATION` owns the Business Day Rule via a new `operating_day_cutoff_time` field (§ 6a, Restaurant Profile.md "Location Business Day Rule (Business Date)"). This is deliberately the smallest adequate mechanism — a single cutoff time evaluated in the Location's own timezone — not a calendar/scheduling engine.

**Timezone relationship:** the cutoff is meaningless without a timezone; `timezone` is already an existing `Location` fact (`DATABASE_SCHEMA.md` §2). Business Date computation is defined as relative to Location's timezone, never a hard-coded timezone.

**Transaction business_date:** `ORDER.business_date` (§ 6, § 6a) is the canonical, minimum-required Business Date fact. It is computed once from the Order's timestamp and the Location's Business Day Rule in effect at that time, then persisted on the Order — never recomputed at read time. Table Service does not persist its own independent Business Date; it may derive one from its Orders' `business_date` where needed, but Order remains the canonical source.

**Historical immutability:** because `business_date` is persisted at determination time rather than derived at read time from the Location's *current* configuration, a later change to `operating_day_cutoff_time` cannot retroactively rewrite a historical Order's `business_date` (§ 6a, "Historical immutability"; mirrored in Restaurant Profile.md).

**Cross-domain use:** `business_date` is defined once, here, as the single canonical concept Tips, Payroll, and Performance should reuse rather than each inventing an independent business-date rule (§ 6a, "Cross-domain use"; Restaurant Profile.md). No changes were made to Tips/Payroll/Performance documentation beyond this cross-reference — none of their existing canonical statements currently contradict or duplicate a business-date rule (see § J).

---

## D. Void / Cancellation model

New § 14b, inserted between Refund (§ 14a) and Tax (§ 15):

- **`ORDER_CANCELLATION`** — records an entire Order abandoned/cancelled before completion (0:1 per Order).
- **`ORDER_ITEM_VOID`** — records a specific Order Item voided/cancelled before settlement (0:N per Order Item).
- Both preserve the original `ORDER`/`ORDER_ITEM` fact; neither deletes it. Where both the original event and later Void evidence are observable, RF-One represents both.
- **Distinction from Refund:** the dividing line is whether a completed economic settlement had already occurred — before settlement is Void/Cancellation, after settlement is Refund. The two are never merged. The pre-existing Refund section's own note about `voided` flags being Refund-lifecycle evidence (not a general void mechanism) was updated to point at § 14b instead of the now-resolved open item.
- **Order vs. Order Item:** kept as two distinct facts because they represent different operational reality; not forced into one shared generic state.
- **Payment Void boundary:** no separate Payment Void entity was introduced. A voided payment attempt is treated as evidence relevant to the Order's/Order Item's Void/Cancellation state (or a `Payment.result` value where a source separately models it), not a fourth parallel concept — consistent with the task's instruction not to invent unnecessary complexity. Failed payment, cancelled Order, Order Item void, payment void, and Refund remain explicitly non-equivalent (§ 25).
- **Source evidence limitations:** documented explicitly as a Provider/Data Acquisition Gap, never inferred from absence in a POS export.

---

## E. Canonical model changes

`01 Domains/Restaurant/Sales/Restaurant Sales Model.md`:

- § 6 (Order): added `business_date` to the Order fact list.
- New **§ 6a — Business Date**: Location Business Day Rule (`operating_day_cutoff_time`), Order's persisted `business_date`, historical immutability, Table Service treatment, cross-domain use, provider independence, non-assumptions.
- § 7 (Order Item): principle rewritten from "one individual sold unit" to "one recorded sold line / sold item occurrence, with its own observed quantity and historical economic attributes"; added `quantity` to the fact list; replaced the forced-triplication example with a source-driven-shape statement.
- New **§ 7, "Quantity"**: canonical quantity semantics (decimal, source-observed, provider-independent, never inferred/defaulted, independent from unit price).
- New **§ 7, "Quantity is not aggregation"**: clarifies atomicity is event identity, not `quantity = 1`; forbids merging separate identical-looking Order Item facts.
- New **§ 7, "Derived line amounts"**: quantity × unit price ± modifiers/discounts remains derived where deterministic; a source-reported total is preserved separately only if reconciliation requires it.
- § 14a (Refund): updated the `voided`-flag note to cross-reference the new § 14b instead of the (now-resolved) open item.
- New **§ 14b — Void / Cancellation**: `ORDER_ITEM_VOID`, `ORDER_CANCELLATION`, Order-vs-Item distinction, Payment Void boundary, source evidence limitation.
- § 21 (relationship diagram): added `business_date` under Order, `quantity` under Order Item, `ORDER_ITEM_VOID` under Order Item, `REFUND` and `ORDER_CANCELLATION` under Order (Refund was previously missing from this diagram despite existing since TASK_SALES_001 — corrected as part of this task's consistency review).
- § 22 (observed vs. derived): added `Order business_date`, `Order Item quantity`, `Refunds`, `Order/Order Item Void and Cancellation` to the atomic-facts list; added an explicit note that unit-count-based derived measures must use `SUM(quantity)`, not row count.
- § 25 (non-assumptions): removed the now-superseded "Order Item = aggregated quantity" line; added quantity-, void-, and business-date-related non-assumptions.

`01 Domains/Restaurant/Organization/Restaurant Profile.md`:

- New **"Location Business Day Rule (Business Date)"** section: `operating_day_cutoff_time` on `LOCATION`, ownership boundary (Restaurant Profile owns the configuration input; Sales owns and persists the resulting `business_date`), historical immutability cross-reference, cross-domain reuse note.

`01 Domains/Restaurant/Roadmap.md`:

- Updated the "Documented" table's Sales row and the § 2 "Planned Restaurant knowledge areas" Sales (KD-003) bullet to reflect that all three TASK_SALES_001 Domain gaps are closed and Sales is Domain-COMPLETE, with remaining work reclassified as software implementation/POS mapping rather than Domain modeling.

---

## F. Scenario validation

### TASK_SALES_001's original 14 scenarios

| # | Scenario | Status |
|---|---|---|
| 1 | Simple dine-in sale | PASS |
| 2 | Split payment | PASS |
| 3 | Fixed discount | PASS |
| 4 | Percentage discount | PASS |
| 5 | Item discount | PASS |
| 6 | Item void before payment | **PASS** (was FAIL) — § 14b `ORDER_ITEM_VOID` now represents this, distinct from Refund |
| 7 | Full refund next day | **PASS** (was PARTIAL) — Refund fact unaffected; Business Date (§ 6a) now closes the previously-missing operating-day framing |
| 8 | Partial refund | PASS |
| 9 | Modifier pricing | PASS |
| 10 | Quantity (3 identical units + fractional line) | **PASS** (was FAIL) — § 7 `quantity` field represents both without contradiction |
| 11 | Takeout | PASS |
| 12 | Across midnight | **PASS** (was FAIL) — § 6a Business Date closes this directly |
| 13 | Multiple locations | PASS |
| 14 | POS incomplete evidence | PASS |

All three previously blocking scenarios (6, 10, 12) now PASS; scenario 7 upgrades from PARTIAL to PASS.

### Additional scenarios A–H (this task)

| Scenario | Expected | Result |
|---|---|---|
| A — Fractional quantity (0.5 portion) | Representable without duplicating/inventing rows | **PASS** — one `ORDER_ITEM` with `quantity = 0.5` |
| B — Multiple quantity (Water, qty 3) | Representable as one fact if that is how it was recorded | **PASS** — one `ORDER_ITEM` with `quantity = 3`; no forced triplication |
| C — Separate identical events (Water qty 1 × 2) | Remain two independent events, not auto-merged | **PASS** — § 7 "Quantity is not aggregation" explicitly forbids merging |
| D — Across midnight | Timestamps unchanged; `business_date` correctly reflects operating day | **PASS** — § 6a |
| E — Location changes cutoff later | Historical Order `business_date` remains stable | **PASS** — § 6a "Historical immutability"; persisted-at-determination-time mechanism |
| F — Item void | Original sale may remain visible; Void independently representable; no Refund created | **PASS** — § 14b `ORDER_ITEM_VOID` |
| G — Order cancelled | Cancellation represented without implying a completed sale | **PASS** — § 14b `ORDER_CANCELLATION` |
| H — Refund after completed sale | Original sale remains historical fact; Refund separate; no Void semantics used | **PASS** — § 14a unchanged, now cross-referencing the distinct § 14b |

---

## G. Historical integrity

Confirmed:

- **Quantity is preserved**: `ORDER_ITEM.quantity` is a per-fact atomic value, never recomputed or defaulted; independent from unit price (§ 7).
- **Business Date is stable historically**: `ORDER.business_date` is persisted at determination time; a later Location cutoff change cannot rewrite it (§ 6a).
- **Void does not erase original evidence**: `ORDER_ITEM_VOID`/`ORDER_CANCELLATION` are additive facts; the original `ORDER`/`ORDER_ITEM` rows are never deleted or rewritten (§ 14b).
- **Refund does not rewrite original Sale**: unchanged from TASK_SALES_001 (§ 14a) — still an independent, additive fact.

No historical-integrity violation was introduced by any of the three changes.

---

## H. Provider independence

No Clover-specific (or any other provider-specific) assumption was introduced:

- `quantity` is explicitly required to be provider-independent and never a Clover-specific encoding (§ 7).
- `operating_day_cutoff_time`/`business_date` are RF-One-defined concepts; a source's own business-date-like value, if any, is preserved only as evidence, never treated as canonical over RF-One's own computation (§ 6a, "Provider independence").
- `ORDER_ITEM_VOID`/`ORDER_CANCELLATION` are defined independently of whether Clover (or any POS) can currently supply the evidence; § 14b explicitly states a source's inability to expose Void evidence is a Provider/Data Acquisition Gap, not a reason to omit the concept.

---

## I. Derived metrics implications

The pre-existing implicit equivalence `COUNT(Order Item rows) = units sold`, used by any unit-count-based derived measure (e.g. "items / guest," "items / hour," unit-count product mix), is no longer valid now that a row does not necessarily represent exactly one unit. § 22 now states explicitly that such measures must use `SUM(quantity)` where economically appropriate. This is a semantic correction only — no Performance calculation code was touched (out of scope for this task), and Sales facts remain sufficient: `quantity` is available per Order Item, so `SUM(quantity)` is directly computable from atomic facts without any new persisted aggregate.

---

## J. Cross-domain implications

- **Organization**: `Restaurant Profile.md` gains ownership of the Location-level Business Day Rule configuration (`operating_day_cutoff_time`). No other Organization concept changes.
- **Tips**: `Tip.md`'s temporal anchor (Payment's own timestamp) and its Refund-reversal evidence rule are unaffected. `business_date`, once available, is a candidate future anchor for period-based Tip reporting/eligibility windows, but Tips' existing Shift-based resolution path (`Tips/README.md`) is not modified by this task.
- **Payroll**: not modified. `business_date` is flagged as the concept Payroll should reuse if/when it needs operating-day attribution, rather than inventing its own — no existing Payroll documentation was found to contradict this.
- **Performance**: `Performance.md` was reviewed; it reasons in Shift/context terms (e.g., "Tuesday lunch shift") rather than asserting `Order Item count = units sold`, so no existing Performance canonical statement required correction. It remains a consumer of Sales-derived Evidence per § 22's existing boundary; the `SUM(quantity)` correction (§ I) is a Sales-side clarification of how that Evidence must be computed, not a Performance-document change.

None of these Domains were expanded or redesigned beyond the cross-references above, per task scope.

---

## K. Remaining Domain gaps

None.

---

## L. Implementation gaps

Software work required to realize this canonical model, not blocking Domain completion:

- **Quantity persistence/ingestion**: add `quantity` to the `order_items` table and to the Clover ingestion pipeline; determine how Clover's own line-item shape maps to `quantity` (may require provider-specific investigation — TASK_SALES_001 § I did not establish whether/how Clover exposes fractional or multi-unit quantities distinctly from repeated rows).
- **Business Date calculation/persistence**: add `operating_day_cutoff_time` to the `locations` table (Restaurant Profile/Location schema); implement the computation and persist `business_date` on `orders` at ingestion time; TASK_SALES_001 § I noted no timezone field currently exists on the Clover Merchant object for this integration, which will need to be resolved (operator-confirmed value) before `business_date` can be computed in practice.
- **Void ingestion**: add `order_item_voids`/`order_cancellations` tables; determine what, if anything, Clover can supply as Void/Cancellation evidence (open per TASK_SALES_001 § I — not established whether Clover ever exposes a genuinely pre-settlement cancelled Order).
- **Clover mapping**: the `Sales/Clover/*.md` scaffolds remain empty (pre-existing gap, out of scope here); once filled, they should document how (or whether) quantity, business-date, and void evidence map from Clover's actual API surface.
- **Table Service reconstruction**: still unimplemented (pre-existing gap, noted in TASK_SALES_001 § H).
- **Failed-payment ingestion**: still schema-ready but not implemented (pre-existing gap, noted in TASK_SALES_001 § H).

---

## M. Product Owner decisions required

The three TASK_SALES_001 decisions are resolved by this task and are not reopened.

None.

---

## N. Exact files changed

- `01 Domains/Restaurant/Sales/Restaurant Sales Model.md` — modified (§ E)
- `01 Domains/Restaurant/Organization/Restaurant Profile.md` — modified (§ E)
- `01 Domains/Restaurant/Roadmap.md` — modified (§ E)
- `07 Tasks/Reports/TASK_SALES_002_REPORT.md` — created (this report)

No database, API, ingestion, or UI code was touched. No ORM models or migrations were modified.

---

## O. Git status

- No commit was made.
- No push was made.
- Pre-existing unrelated uncommitted work in the working tree (Core, Purchasing, Personnel Management, InvoiceIntake, RF-One Data Store, PROJECT_STATE.md, OpenQuestions.md, CLAUDE.md, and others, per `git status` at task start) was left untouched — verified after edits that only the three target files plus this new report changed.

---

## P. Final readiness statement

`SALES DOMAIN STATUS: COMPLETE — READY FOR FUTURE DEVELOPMENT`
