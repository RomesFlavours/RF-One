# Dining Session Profile

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Dining Intelligence
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

The **Dining Session Profile** represents the evolving consumption pattern of one specific service occasion (one Dining Session). It is **not** a static label assigned once at seating — it must evolve dynamically during the meal, updated as new evidence arrives.

```text
Guest seated
  → order sequence begins
    → Dining Session Profile updates with each new Observed fact
      → continues updating until the session concludes
```

This is the primary supplier of "Available Opportunity" to [Server Performance/Opportunity Capture.md](../Server%20Performance/Opportunity%20Capture.md) and of table-specific context to [Service Copilot](../Service%20Copilot/README.md)'s During-Service phase.

---

## Potential evidence/features (illustrative, not a fixed schema)

```text
guest count
daypart
day of week
service duration
order sequence
first items ordered
food categories/families
drink categories/families
spending level
appetizer behavior
alcohol/non-alcohol behavior
dessert behavior
add-ons/modifiers
progressive check composition
observed guest/service signals (e.g. a smartwatch micro-input — Service Copilot/Smartwatch
  Interaction.md)
```

This list is illustrative and non-exhaustive, matching the same "not a mandatory universal schema" convention already established for [Performance Context](../../Personnel%20Management/Performance/PerformanceContext.md).

---

## Food/drink consumption features

The Dining Session Profile characterizes consumption from Item-level observations. Approved examples:

- food family;
- drink family;
- carb-heavy vs. protein-heavy composition;
- vegetable/other composition where useful;
- beverage-to-food relationship;
- premium/basic product mix;
- sharing patterns where inferable;
- number/type of courses;
- food + beverage combinations;
- modifiers/add-ons;
- sequence of purchasing decisions.

**These are consumption-pattern descriptors based on observed products — never dietary/nutritional or medical inference, and never personal health profiling.** A "carb-heavy" descriptor characterizes what was ordered, not a conclusion about the guest's health, diet, or body.

---

## Progressive, not static

Because Opportunity Capture must evaluate "given what was known about this table at this point in the service, what was reasonably sellable" (`Server Performance/Opportunity Capture.md`), the Dining Session Profile must be queryable **as of a moment**, not only as a final summary once the session concludes. The Profile at 7:15pm (before dessert has been offered) is a different state than the Profile at 8:40pm (check requested) — both are valid, distinct states of the same evolving Profile.

---

## Epistemic status

- Guest count, order sequence, items ordered, service duration are **Observed** (Sales evidence).
- Food/drink family classification, spending level, and progressive check composition are **Derived** (a deterministic classification applied to Observed items, using Commercial Catalog vocabulary).
- Any conclusion about *why* a pattern occurred, or *what the table is likely to order next*, is **Inferred**.

---

## Related documents

- [README.md](README.md)
- [Food and Drink Correlations.md](Food%20and%20Drink%20Correlations.md)
- [Customer Consumption Profile.md](Customer%20Consumption%20Profile.md)
- [../Server Performance/Opportunity Capture.md](../Server%20Performance/Opportunity%20Capture.md)
- [../Service Copilot/Smartwatch Interaction.md](../Service%20Copilot/Smartwatch%20Interaction.md)
