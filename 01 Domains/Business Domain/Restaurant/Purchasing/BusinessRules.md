# Purchasing Business Rules

## Purpose

This document defines the immutable business rules governing the Purchasing Module.

Business Rules describe how the restaurant purchasing domain behaves.

They are independent from software implementation, database design and user interface.

---

# Rule 1 – Every Purchase Generates One Purchase Document

Every purchasing event must generate exactly one Purchase Document.

The Purchase Document represents the source commercial evidence of the purchase, regardless of whether it originates from an Invoice, a Receipt, a Credit Note, an API purchase record, or another real document.

The acquisition method is irrelevant.

---

# Rule 2 – The Purchase Document Is Immutable

The original supplier document is never modified.

Corrections, interpretations and validations are stored separately.

The supplier document always represents business reality.

---

# Rule 3 – Supplier Product Relationship Depends on Line Type

```text
PRODUCT    → may/reference a Supplier Product, when supplier product
             identity is available from the source
SURCHARGE  → Supplier Product = NULL / not applicable
DISCOUNT   → Supplier Product = NULL / not applicable
```

A surcharge or a discount is not a product and therefore never references a Supplier Product. This replaces the earlier rule that every Purchase Line must reference exactly one Supplier Product.

Supplier terminology, when present, is always preserved.

---

# Rule 4 – Ingredient Mapping Applies Only in the Food/Ingredient Context

A `PRODUCT` Purchase Line's Supplier Product may eventually be mapped to exactly one Ingredient, when its merchandise/economic classification places it in the Food/Ingredient context (typically `FOOD`).

Ingredient mapping is not a universal requirement for every purchased product — a Supplier Product classified `DRINK`, `SUPPLIES` or `OTHER` is not required to map to an Ingredient.

A newly acquired Supplier Product may temporarily remain unclassified and unmapped until validation is completed.

The mapping is approved by an authorized user. Artificial Intelligence may only propose mappings.

Many Supplier Products may reference the same Ingredient.

---

# Rule 5 – Ingredients Are Supplier Independent

Ingredients belong to the Restaurant Domain.

Suppliers never define Ingredients.

Supplier Products only reference existing Ingredients.

---

# Rule 6 – Product and Specifications Define Ingredient Identity

An Ingredient is uniquely identified by:

- one Product
- zero or more Specifications

Changing the Product or one or more Specifications creates a different Ingredient.

---

# Rule 7 – Internal Quantities Are Standardized

Every purchasable Ingredient is represented, for costing purposes, using a normalized quantity in grams — a derived measure (see `DataDictionary.md`, "Persist Facts — Derive Calculations").

Commercial purchasing units are always preserved as source information.

---

# Rule 8 – Merchandise/Economic Classification and Ingredient Cost Are Derived

For every `PRODUCT` Purchase Line, the Purchasing Module supports deriving:

- Supplier Price (persisted source fact)
- Effective Product Cost (derived — see Rule 12)
- Ingredient cost per gram, when the Food/Ingredient context applies (derived)

The merchandise/economic classification itself (`FOOD`, `DRINK`, `SUPPLIES`, `OTHER`) is a persisted, human-confirmed fact once known, not a derived value — see `DataDictionary.md`.

---

# Rule 9 – Surcharge Purchase Lines Are Allocated to Eligible PRODUCT Lines

A `SURCHARGE` Purchase Line (e.g. Fuel Surcharge, Delivery Surcharge, Service Fee, Environmental Fee) does not itself represent a purchased product. Its cost is proportionally allocated across the `PRODUCT` Purchase Lines it is eligible for, when deriving their Effective Product Cost.

```text
allocation share      = product base line amount / sum of eligible PRODUCT base line amounts
allocated surcharge   = allocation share × surcharge amount
```

Eligible lines default to **all `PRODUCT` lines on the Purchase Document**, unless the source document or a confirmed rule establishes a narrower scope (for example, a cold-chain surcharge applying only to refrigerated items) — a narrower scope is a fact to be recorded on the `SURCHARGE` line, never assumed.

The allocation share and the allocated amount are derived, not persisted (see `DataDictionary.md`).

---

# Rule 10 – Discount Purchase Lines Are Allocated to Eligible PRODUCT Lines

A `DISCOUNT` Purchase Line follows the same allocation logic as a `SURCHARGE`, in reverse: it proportionally reduces, rather than increases, the Effective Product Cost of eligible `PRODUCT` lines.

```text
allocation share     = product base line amount / sum of eligible PRODUCT base line amounts
allocated discount   = allocation share × discount amount
```

A `DISCOUNT` Purchase Line never modifies historical purchasing knowledge — it is preserved as its own Purchase Line and enters only the derived Effective Product Cost calculation.

---

# Rule 11 – Purchasing History Is Permanent

Every validated purchase becomes part of the permanent Purchase History.

Historical purchasing information is never overwritten.

New purchases create new history.

---

# Rule 12 – Effective Product Cost

For every `PRODUCT` Purchase Line:

```text
Effective Product Cost
=
Base Product Line Amount
+ proportional share of applicable SURCHARGE lines     (Rule 9)
- proportional share of applicable DISCOUNT lines       (Rule 10)
+ tax, only when a future applicable fiscal rule establishes that tax
  is economically borne by the business                 (see OpenQuestions.md,
                                                           "Invoice Tax Treatment — OPEN")
```

Effective Product Cost is always derived, never persisted as canonical stored truth (see `DataDictionary.md`, "Persist Facts — Derive Calculations").

---

# Rule 13 – Validation Never Changes Reality

Validation records business anomalies — including an unknown Supplier Product, an unknown merchandise/economic classification, or an unresolved Ingredient mapping.

Validation never modifies the original supplier document.

Every anomaly is stored inside the Validation Log.

---

# Rule 14 – Human Knowledge Has Priority

Artificial Intelligence supports business decisions.

Only authorized users may:

- create Ingredients;
- approve merchandise/economic classifications;
- approve Ingredient mappings;
- resolve Validation Logs;
- make business decisions.

---

# Rule 15 – The Purchasing Module Produces Knowledge

The objective of the Purchasing Module is not to manage suppliers.

Its objective is to transform purchasing information into standardized Restaurant knowledge.

---

# Rule 16 – The Purchase Document Is the Single Source of Truth

Every purchasing calculation originates from the Purchase Document.

No downstream module may alter purchasing history.

Recipes, Inventory, Food Cost and Forecasting consume purchasing knowledge but never modify it.

---

# Rule 17 – Purchasing Precedes Administration and Taxation

Restaurant/Purchasing understands **what** was purchased — item-level identity, classification and cost composition. Administration and Taxation do not reinterpret item-level semantics; they consume the economic result Purchasing already derived.

```text
Restaurant/Purchasing
→ Economic Classification
→ derived category allocation (e.g. Food = $X, Drink = $Y, Supplies = $Z)
→ Administration
→ Taxation / Accounting treatment
```

Example: Olive Oil, Beef Tenderloin and Tomatoes are all classified `FOOD` by Purchasing. Administration does not need their item identity — it consumes the derived allocation, "Food = $X."

Purchasing comes before fiscal treatment; a jurisdiction or fiscal rule may later determine how a derived category total is treated for tax purposes, but it never redefines what was purchased or how it was classified.

---

# Rule 18 – FinancialTransaction Is Not a Purchase Document

```text
FinancialTransaction  ≠  Purchase Document
```

`FinancialTransaction` (owned outside this module, at Administration level) represents a movement of money — a bank debit or settlement. `Purchase Document` represents the economic composition of the purchase — what was bought, at what classified cost.

The future relationship is `FinancialTransaction ↔ Payment/Invoice Matching ↔ Purchase Document`. No bank-matching engine is designed or implemented by the Purchasing Module; this rule only preserves the conceptual boundary.

---

# Rule 19 – Purchase Configuration Variation Is Observable Even When Identity Is Unchanged

A `PRODUCT` Purchase Line's commercial configuration (packaging, pack count, pack size, unit, brand, variant, grade, and similar source facts — `DataDictionary.md`) may vary between purchases without changing Product/Ingredient identity (`EntityDefinitions.md`, "Product Identity vs Commercial Configuration"; Rule 6).

This variation is never treated as noise. It can affect normalized cost, freshness, shelf life after opening, waste, yield, storage, usability, quality and recipe/food cost, and must remain observable to Purchase Recording (Rule 20).

---

# Rule 20 – Two Reference Levels for Variation Detection

Purchase Recording determines whether a `PRODUCT` Purchase Line's observed commercial configuration deviates from what the Restaurant expects, using two reference levels, in strict priority order:

```text
PRIORITY 1 — Configured Expectation
  If an approved Configured Expectation exists for the Supplier Product, it prevails.

PRIORITY 2 — Previous Purchase (fallback)
  If no Configured Expectation is applicable, compare against the previous purchase
  of the same Supplier + Supplier Product.
```

The previous-purchase fallback is empirical and observational only — it never automatically becomes an approved Configured Expectation (`EntityDefinitions.md`, "Previous Purchase (Fallback Reference)").

A detected deviation generates an Alert when required (`EntityDefinitions.md`, "Alert"). A deviation does not, by itself, imply a wrong product, a rejected purchase, a new Product identity, or an automatic block of the Purchase Document — identity certainty and operational acceptability are distinct questions.

---

# Rule 21 – Alert Does Not Block Purchase Recording When Identity Is Certain

If Product identity is certain, Purchase Recording continues and the `PRODUCT` Purchase Line is recorded correctly even when its commercial configuration deviates from the applicable reference (Rule 20). The resulting Alert remains **OPEN**; it is not resolved by recording the line, and the deviation is never silently accepted as a permanent configuration change (`EntityDefinitions.md`, "Alert").

If Product identity is uncertain, this is not an Alert — it is a Validation matter, and human review may be required before the line is finally validated (`ValidationRules.md`, "Alert vs Validation").

---

# Rule 22 – Alert Lifecycle and Closure

An Alert requires: a responsible User/role; an **OPEN** state until handled; an explicit human acknowledgement; a recorded Human Decision when a decision is required; who responded and when; what was decided; and closure only after the required response is complete. Closing an Alert is never merely a status flip disconnected from a decision — see Rule 23.

---

# Rule 23 – Human Decisions on an Alert Update Knowledge Prospectively, Never Historical Reality

A Human Decision on an Alert produces exactly one of three effects on the Supplier Product's Configured Expectation:

```text
ACCEPT THIS PURCHASE ONLY
  → this Purchase Line/purchase is accepted
  → the Configured Expectation is unchanged
  → the exceptional configuration never becomes the new baseline
  → future comparison continues against the existing Configured Expectation

ACCEPT AS ALTERNATIVE
  → the current configuration is accepted
  → the existing valid configuration remains valid
  → the new configuration becomes an additional approved alternative

CHANGE EXPECTATION
  → the newly observed configuration becomes the new approved expected configuration
  → future purchases are compared against the updated expectation
```

**Worked example (one-time acceptance):** expected `20 × 500 g`; an exceptional purchase of `1 × 5 kg` is decided as "accept this purchase only"; the next purchase of `20 × 500 g` generates no "change back" Alert, because `20 × 500 g` remained the valid Configured Expectation throughout.

None of these three effects ever rewrites a historical Purchase Line, the packaging actually received, the price actually paid, the Alert that occurred, or the decision made at that time (Rule 11; `DataDictionary.md`, "Persist Facts — Derive Calculations"). Configured knowledge evolves only prospectively.

---

# Rule 24 – Configuration Learning vs Module Capability Gap

Every Human Decision that would change operational knowledge (Rule 23) is first tested against one question: **can the existing Purchasing model correctly represent the User's operational rule?**

```text
YES → Configuration Learning
      → apply the decision as a Configured Expectation update for this
        Organization/Restaurant context
      → no RF-One software/module redesign is required

NO  → Module Capability Gap
      → do not force the answer into an incorrect configuration
      → escalate the requirement to the function responsible for RF-One/module
        evolution, for evaluation
```

Example of a Module Capability Gap: "accept the 5 kg package only when forecast consumption during the next four days exceeds 4 kg" — a conditional rule the current model has no concept to represent. This is customer-specific knowledge only when it is representable; a requirement that is not representable is a candidate for RF-One's general capability, never a customer-specific workaround forced into an unsupported shape.

This task does not implement the escalation mechanism itself — only the distinction and the principle that RF-One should ask the responsible User the minimum useful contextual question needed to tell these two cases apart, rather than silently inferring strategic intent (`EntityDefinitions.md`, "Alert").

---

# Rule 25 – Three Sources of Purchase Reality

Purchase Recording distinguishes three independent representations of a purchase, and never collapses them into one:

```text
ORDER               = what the Restaurant asked the Supplier to provide
INVOICE / PURCHASE DOCUMENT = what the Supplier states it sold / billed
PHYSICAL RECEIVING  = what the Restaurant actually observed arriving
```

A Purchase Document is the Supplier's own commercial representation — it is evidence, not automatically equivalent to physical Receiving Reality (`EntityDefinitions.md`, "Purchase Document"). A Supplier may omit an ordered product, invoice a product that never arrives, deliver a different product, deliver a different quantity or packaging, deliver damaged product, or include an unexpected product. Physical Receiving (`EntityDefinitions.md`, "Receiving Record," "Receiving Line") is the Restaurant's own, independent observation of Reality, and is never inferred from the Order or from the Invoice.

---

# Rule 26 – Three-Way Reconciliation

Purchase Recording performs three distinct comparisons, each answering a different question, and never reduces them to one generic match/mismatch result:

```text
ORDER vs INVOICE      → Did the Supplier bill what was ordered?
INVOICE vs RECEIVING  → Did the Supplier physically deliver what it billed?
ORDER vs RECEIVING    → Did the Restaurant actually receive what it requested?
```

Example:

```text
Ordered: Wine A × 3        Invoiced: Wine A × 3        Received: Wine A × 2
→ physical short delivery (Invoice vs Receiving mismatch; Order vs Invoice matched)

Ordered: Wine A × 3        Invoiced: Wine A × 2        Received: Wine A × 2
→ supplier shorted before invoice (Order vs Invoice mismatch; Invoice vs Receiving matched)

Ordered: Wine A × 3        Invoiced: Wine B × 3        Received: Wine B × 3
→ unauthorized/unexpected substitution relative to Order

Ordered: Wine A × 3        Invoiced: Wine A × 3        Received: Wine B × 3
→ physical delivery does not match the Invoice
```

Reconciliation compares the Purchase Order Line, the `PRODUCT` Purchase Line and the Receiving Line for the same item whenever more than one of the three exists. See Rule 33 for the derived reconciliation output.

---

# Rule 27 – Receiving Is Observation, Not Decision

```text
Receiving   = recording physical Reality
Receiving  ≠ Purchasing Decision
```

The Employee performing Receiving records facts. The Employee does not decide whether a substitution is acceptable, whether an extra product should be kept, whether a Supplier's commercial change is acceptable, whether a different package should become the new standard, or whether a disputed amount should be accepted economically. Those are Purchasing Decisions, reserved for the responsible Purchasing authority (Rule 35).

---

# Rule 28 – Receiving Is Mobile-First and Fallback-Capable

Receiving is primarily a mobile operational function and must remain compatible with `03 Software/User Interaction Architecture.md`. It supports two conceptual capture modes:

```text
LABEL-BASED  — for structured Suppliers: scan the Invoice, then scan each package/
               case label; RF-One extracts product identity, brand/variant,
               packaging, pack size, unit and quantity, and reconstructs the
               Receiving Record for reconciliation against Order and Invoice.

ORDER-BASED  — for Suppliers without useful machine-readable labels: RF-One shows
               each expected item and quantity from the Order, and the Employee
               enters only the actual quantity received; RF-One derives the
               deviation (e.g. expected 4, received 3 → shortage 1) rather than
               asking the Employee to classify it.
```

A preferred capture method is never rigid. Label-based Receiving may fall back to Order-based or manual factual capture (unreadable label, missing label, damaged packaging, exceptional item); a Receiving session must never fail merely because its preferred capture mechanism fails.

---

# Rule 29 – Extra/Unexpected Item Always Generates an Alert

Merchandise physically delivered but not present in the Order is recorded as a Receiving Line with no related Purchase Order Line (`EntityDefinitions.md`, "Receiving Line"). The Employee records only facts: free-text description, quantity, unit/packaging if recognizable, receiving context/provenance, and a **mandatory photograph**.

An Extra/Unexpected Item always raises an Alert (Trigger = `RECEIVING_DISCREPANCY`), routed to the responsible Purchasing authority, making available Supplier, Order, Invoice (if available), the entered description, quantity, photo, Receiving evidence, and any AI identification proposal, clearly marked as interpretation rather than fact. The Employee never decides whether the item is acceptable, a substitution, how it should be economically classified, or whether it should be retained — those are Purchasing Decisions (Rule 35).

---

# Rule 30 – Damaged Item Is a Factual Receiving Observation

The Employee may record a damaged quantity against a Receiving Line: the affected item, the quantity damaged, receiving context/provenance, and a **mandatory photograph**. The Employee is not asked to determine economic responsibility for the damage.

```text
Damaged item → factual Receiving observation → Alert to the Purchasing authority (Rule 29's routing applies equally here).
```

---

# Rule 31 – Partial Quantity

Receiving, reconciliation and the resulting Purchasing Decision operate at quantity level, never assuming an entire Purchase Line or Receiving Line must be accepted or rejected as one indivisible unit.

```text
Ordered: 10
Received: 10
Damaged: 2

Purchasing Decision may be:
8 ACCEPT
2 REJECT / RETURN
```

---

# Rule 32 – Receiving Completion Is Independent of Alert Resolution

```text
Receiving Status = COMPLETED
```

may coexist with:

```text
Purchasing Alerts = OPEN
```

The Employee performing Receiving must normally be able to finish the Receiving session even when a shortage, an Extra/Unexpected Item, a substitution, a damaged item, a packaging deviation, or an Invoice mismatch exists. Receiving completion is not the resolution of a Purchasing problem (Rule 27); the person unloading/receiving merchandise is never blocked waiting for a Purchasing Manager decision.

---

# Rule 33 – Reconciliation Produces Atomic Differences, Not a Boolean Result

RF-One derives detailed reconciliation results from the three-way comparison (Rule 26) rather than a generic OK/KO. Possible semantic outcomes include:

```text
MATCH
SHORT
EXTRA / UNEXPECTED
SUBSTITUTED
DAMAGED
INVOICE MISMATCH
ORDER MISMATCH
PACKAGING DEVIATION
QUANTITY DEVIATION
```

This list is illustrative, not a rigid exhaustive enum. The governing principle: record atomic differences; never collapse all differences into one boolean result. Reconciliation Outcome is derived on demand from persisted Order/Invoice/Receiving facts — it is never itself persisted as canonical truth (`DataDictionary.md`, "Persist Facts — Derive Calculations").

---

# Rule 34 – Receiving Discrepancies Are Routed to the Responsible Purchasing Authority

```text
Receiving staff        → record Reality
RF-One                 → reconciles and identifies discrepancies
Purchasing responsible User → evaluates and decides
```

This mirrors, for `RECEIVING_DISCREPANCY` Alerts, the same routing and lifecycle already established for `CONFIGURATION_DEVIATION` Alerts (Rule 22, "Alert Lifecycle and Closure"; `03 Software/User Interaction Architecture.md`, Section 7.1).

---

# Rule 35 – Purchasing Decision on a Receiving Discrepancy: ACCEPT or REJECT/RETURN

For a received discrepancy/item/quantity, the responsible Purchasing authority resolves the Alert with exactly one of two economic outcomes:

```text
ACCEPT
  → the received quantity is accepted as part of the Purchase
  → it becomes a valid acquired quantity for downstream Purchase calculations
  → the Alert can close once any required related decision/configuration step is
    complete; if the accepted item/configuration was exceptional, acceptance may
    further be classified as one-time only, accepted as alternative, or a changed
    expectation, per the Configured Expectation semantics of Rules 20 and 23 —
    those rules are not duplicated here

REJECT / RETURN
  → see Rule 36
```

Configuration-learning-related contextual choices (Rules 23–24) may still apply once ACCEPT is chosen for an exceptional configuration; the physical/economic merchandise outcome itself is always exactly ACCEPT or REJECT/RETURN.

---

# Rule 36 – Rejection Preserves Historical Reality

If Purchasing chooses REJECT/RETURN, the Receiving observation is never erased: the merchandise DID arrive physically. The historical fact is preserved and extended, never rewritten:

```text
Received → Rejected / Returned
```

must never become:

```text
Never received
```

even though the final economic result is equivalent to not retaining/acquiring the merchandise. Both facts remain preserved: what physically happened, and what economic decision followed. Economically, the rejected quantity must not remain as a valid final acquired cost/quantity once the return/rejection is established; the return/rejection creates the expectation documented in Rule 37.

---

# Rule 37 – Expected Supplier Credit

When rejected/returned merchandise has already been invoiced (a related `PRODUCT` Purchase Line exists), RF-One preserves an Expected Supplier Credit — the operational expectation that the Supplier owes an economic correction (`EntityDefinitions.md`, "Expected Supplier Credit"). This expectation may remain **OPEN** for a very long time; no arbitrary expiration is imposed (Rule 40).

An Expected Supplier Credit may later be satisfied by a dedicated Credit Note, a credit/adjustment on a later Invoice, or another explicit Supplier commercial correction represented by real source evidence. Credit Note remains a supported Purchase Document type; no second credit-document ontology is created.

---

# Rule 38 – Partial Supplier Credit

A Supplier correction may be partial:

```text
Expected Supplier Credit = $200
Credit received = $120
→ outstanding = $80

Later:
Credit received = $80
→ resolved
```

RF-One persists the actual source credit facts (each recognized Supplier Credit and its amount). The outstanding amount is always derived — Expected Amount minus recognized applicable Supplier Credits — and is never persisted as canonical truth if it can be reliably recalculated (`DataDictionary.md`, "Persist Facts — Derive Calculations").

---

# Rule 39 – Credit Reconciliation Against Future Supplier Documents

```text
Original Purchase Document
→ rejected/returned quantity
→ Expected Supplier Credit
→ future Supplier Purchase Document / Credit Note
→ reconciliation
```

When a later Supplier Purchase Document arrives, RF-One inspects its available credit/adjustment evidence and reconciles it against open Expected Supplier Credits. A correct match resolves the expectation, fully or partially. If the Supplier omits the credit, provides an incorrect amount, applies it to the wrong item/document, or only partially satisfies it, the remaining expectation stays **OPEN** and a Purchasing Alert is generated/maintained as appropriate. RF-One never assumes the correction must occur on exactly the next invoice — the expectation remains open until actually satisfied, or until a responsible User explicitly resolves it by another valid decision.

---

# Rule 40 – No Arbitrary Expiration for Long-Lived Open Supplier Issues

A Purchasing discrepancy's lifecycle may extend beyond the delivery date and beyond the original Invoice — Purchase Recording is not necessarily complete when Physical Receiving ends. A supplier issue (an open Alert, or an open Expected Supplier Credit) may remain **OPEN** for months or years, until the commercial correction is actually reconciled or formally resolved. No module logic imposes an automatic expiration, write-off, or closure.

---

# Rule 41 – Receiving Evidence and Employee Simplicity

Receiving applies the same Reality/Evidence discipline as the rest of the module (`ErrorHandling.md`; `00 Core/ConceptualArchitecture/01_Subject_and_Reality.md`). Source evidence — the Invoice image/document, package labels, photos of extra items, photos of damaged merchandise, manual quantity observations, Receiving User/timestamp, and later Supplier documents providing credit — is preserved and kept distinguishable from any derived interpretation.

The operational Receiving interaction is intentionally low-interpretation. The Employee performs actions analogous to `SCAN INVOICE`, `SCAN LABEL` (repeated), or `CONFIRM ACTUAL QUANTITY` (repeated), `ADD EXTRA ITEM + PHOTO`, `MARK DAMAGED QUANTITY + PHOTO`, `FINISH`. The Employee is never required to understand accounting, Food Cost, Supplier disputes, economic classification, substitution policy, credit handling, or purchasing configuration rules — RF-One and the responsible Purchasing User handle those layers (Rule 27).

---

# Rule 42 – Receiving Authorization May Be Narrower Than Purchasing Access

Receiving permission may be substantially narrower than general Purchasing access:

```text
Receiving User
→ assigned organizational scope/location
→ Mobile Receiving
→ capture evidence
→ record actual quantities
→ record extra/damaged items
→ complete Receiving
```

A Receiving User has no automatic right to full Purchasing Web pages, supplier configuration, cost analysis, approving deviations, resolving Alerts, or changing Configured Expectations. This follows the general Authorization Model of `03 Software/User Interaction Architecture.md`, Section 4 (Domain → Module → Page/Function → Permission → Scope); no customer-specific role is hardcoded by this rule (see `BusinessPermissions.md`, "Receiving User").

---

# Design Principles

- Preserve business reality.
- Preserve supplier terminology.
- Standardize purchasing knowledge.
- Separate supplier information from restaurant knowledge.
- Preserve historical information.
- Persist facts. Derive calculations.
- Human knowledge prevails over Artificial Intelligence.
- A configuration exception is not a redefinition: one-time acceptance leaves the baseline untouched, and only an explicit decision changes it prospectively.
- Known and coherent purchases process automatically; the User's attention belongs to genuine exceptions.
- Order, Invoice and Physical Receiving are three independent sources of Purchase Reality and are never collapsed into one.
- Receiving records Reality; it never decides commercial acceptability.
- A rejection/return is preserved alongside the original receipt, never as if the merchandise had never arrived.
- A long-lived open supplier discrepancy is not a defect to be silently closed — it stays open until genuinely resolved.
