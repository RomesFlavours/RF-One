# Quality of Sale

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Performance must evaluate not only "how much did the Server sell?" but "what did the Server sell?"

A Server may create high throughput while wasting commercial opportunity by failing to present appetizers, strategic dishes, premium items, wine, additional drinks, desserts, profitable modifiers/add-ons, or other Brand-priority products. **Quality of Sale reflects alignment between actual selling behavior and Brand commercial priorities** ([Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md)).

Two Servers with equal Sales-per-Hour Productivity can represent materially different economic value to the Brand if their product mix differs — the same distinction [PerformanceMeasure.md](../../Personnel%20Management/Performance/PerformanceMeasure.md) already illustrates generically ("gross per hour" vs. "contribution margin per hour"); Quality of Sale is where that distinction becomes Restaurant-concrete.

---

## What Quality of Sale is measured against

```text
Actual selling behavior (Observed, from Order Item / Modifier evidence)
  vs.
Brand commercial priorities (Brand Expectation — strategic products, category priorities)
```

Both sides use the Commercial Catalog's existing vocabulary (`Commercial Catalog/README.md`: Item, Item Category, Item Group, Brand, Modifier, Modifier Group) — Quality of Sale does not invent a parallel product taxonomy, and does not assume any specific Brand's priorities (Rome's Flavours' actual strategic products are Brand configuration, never hard-coded here).

---

## Candidate dimensions of Quality of Sale (illustrative, not exhaustive, not formula-final)

- strategic product penetration (did the Server present/sell the products the Brand is currently prioritizing?);
- premium product mix (share of premium vs. basic items sold);
- food-category mix (balance across the Brand's category structure);
- beverage mix (alcohol/non-alcohol, by-the-glass vs. bottle, etc.);
- appetizer attach rate;
- dessert attach rate;
- wine attach/conversion;
- modifiers/add-ons attach;
- Brand-priority products specifically.

Exact formulas (time window, aggregation method, rounding, qualifying-table definition) are **not** finalized by this document — see [KPI Framework.md](KPI%20Framework.md), which states this explicitly and applies the ten-question KPI design principle to each of these before any is treated as a permanent Indicator.

---

## Quality of Sale is not the same as Opportunity Capture

```text
Quality of Sale        what was actually sold, evaluated against Brand priorities — a composition question
Opportunity Capture    of what was realistically sellable at this table, how much was captured — a
                         conversion-against-availability question
```

A Server can have strong Quality of Sale (their sold mix aligns well with Brand priorities) while still leaving Opportunity Capture on the table (they sold well *among the tables they engaged*, but missed realistic upsell moments at others). The two dimensions are related but distinct — see [Opportunity Capture.md](Opportunity%20Capture.md).

---

## Epistemic status

- The items actually appearing on an `Order Item` are **Observed** (Sales module fact).
- A ratio such as "dessert attach rate = desserts sold ÷ qualifying checks" is **Derived**.
- "This Server is weak at introducing dessert to this table archetype" is **Inferred** and must never be presented with Observed-grade confidence (see [Evidence Sources.md](Evidence%20Sources.md)).

---

## Related documents

- [Server Performance.md](Server%20Performance.md)
- [Opportunity Capture.md](Opportunity%20Capture.md)
- [Brand Expectation and Personal Baseline.md](Brand%20Expectation%20and%20Personal%20Baseline.md)
- [KPI Framework.md](KPI%20Framework.md)
- [../Commercial Catalog/README.md](../Commercial%20Catalog/README.md)
- [../Sales/Restaurant Sales Model.md](../Sales/Restaurant%20Sales%20Model.md) §7 "Order Item," §18 "Discounts," §19-20 "Modifier/Modifier Group"
