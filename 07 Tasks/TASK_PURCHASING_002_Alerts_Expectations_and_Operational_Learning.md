# TASK_PURCHASING_002 — Alerts, Expectations and Operational Learning

**Type:** Documentation only. No database, software, UI or runtime workflow implementation.
**Scope:** Restaurant/Purchasing (Purchase Recording only). `03 Software/User Interaction Architecture.md` may be updated minimally for Alert/Notification consistency.

---

## PURPOSE

Document, in the Restaurant/Purchasing module, the behavior just approved for:

- variations relative to expected purchases;
- Alert;
- Configured Expectation;
- comparison with previous purchases;
- human decision;
- operational learning;
- the distinction between customer-specific configuration and the need for RF-One module evolution.

This task is DOCUMENTATION ONLY.

Do NOT implement software, database, UI or runtime workflow.

Read at least:

- `01 Domains/Restaurant/Purchasing/README.md`
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`
- `01 Domains/Restaurant/Purchasing/BusinessRules.md`
- `01 Domains/Restaurant/Purchasing/ValidationRules.md`
- `01 Domains/Restaurant/Purchasing/Workflow.md`
- `01 Domains/Restaurant/Purchasing/DataDictionary.md`
- `03 Software/User Interaction Architecture.md`
- `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md`
- `07 Tasks/Reports/TASK_INTERACTION_001_REPORT.md`

---

## 1. Scope — Purchase Recording

These rules belong, for now, to the part of Purchasing that records and understands what actually happened:

**Purchase Recording**

Do NOT design yet the future capability of:

**Purchase Support**

which will later help decide what, how much and from whom to purchase.

Purchase Recording must observe Reality and compare it with what the Restaurant knows or expects.

---

## 2. Product Identity ≠ Commercial Configuration

Formalize this distinction.

A product may remain the same product/Ingredient even if its commercial configuration changes.

Example:

```text
Ricotta → same Product/Ingredient identity

but:
20 × 500 g
1 × 5 kg
are different commercial configurations.
```

Similarly:

```text
Olive Oil → same Product/Ingredient identity

but:
4 × 1 GAL
6 × 1 L
are different packaging.
```

A packaging change must NOT automatically create a new Ingredient/Product.

---

## 3. Purchase Configuration Facts

For a `PRODUCT` Purchase Line, the following must be preservable when present:

- pack count
- pack size
- unit
- quantity
- brand
- product variant
- grade
- manufacturer/product code
- supplier item code
- unit price
- line amount
- other relevant source facts

These are source facts. Their operational meaning may differ by product.

---

## 4. Why Packaging Matters

Document explicitly that packaging/configuration changes are NOT irrelevant. They can affect:

- normalized cost
- freshness
- shelf life after opening
- waste
- yield
- storage requirements
- operational usability
- product quality
- recipe/food cost consequences

Canonical example:

```text
Expected / previous:  Ricotta 20 × 500 g
Received:              Ricotta 1 × 5 kg
```

Product identity may be certain and unchanged, but the change can produce more waste, less freshness, and economic/quality consequences. It must therefore be observable and may generate an Alert.

---

## 5. Two Reference Levels

Purchase Recording must be able to determine a variation using two reference levels.

**PRIORITY 1 — Configured Expectation.** If an explicit, approved rule/configuration exists, it prevails.

**PRIORITY 2 — Previous Purchase.** If no applicable Configured Expectation exists, RF-One compares the new `PRODUCT` Purchase Line with the previous purchase of the same Supplier + Supplier Product. The previous purchase is an empirical fallback. It does NOT automatically become an approved rule.

---

## 6. Configured Expectation

Document conceptually a Configured Expectation as approved operational knowledge about what the Restaurant considers normal/acceptable for a Supplier Product.

May concern, when relevant: packaging, pack count, pack size, unit, brand, variant, grade, other observable characteristics, future alert conditions.

Do not define a DB schema now. A Configured Expectation may contain one or more acceptable conditions/configurations.

---

## 7. Variation Detection

Canonical behavior:

```text
Current Purchase Reality
→ compare with Configured Expectation if available
→ otherwise compare with previous Supplier + Supplier Product purchase
→ detect meaningful deviation
→ generate Alert when required
```

A deviation does NOT necessarily imply: wrong product; rejected purchase; new Product identity; automatic blocking of the Purchase Document. Identity certainty and operational acceptability are distinct concepts.

---

## 8. Alert ≠ Notification

Preserve the distinction already established in the Interaction Architecture.

- **Notification:** informs.
- **Alert:** requires a traceable human response.

Every Alert must provide for: responsible User/role; OPEN state until handled; explicit acknowledgement; human decision when a decision is required; who responded; when; what was decided; closure only after the required response is complete.

Do not design the UI.

---

## 9. Alert May Not Block Purchase Recording

If Product identity is certain and the Purchase Line can be recorded correctly:

→ Purchase Recording may continue; the Alert remains OPEN.

Example: same Ricotta identity but unexpected packaging → record Reality correctly, generate Alert, do not invent a new Ingredient, do not silently accept the deviation as a permanent configuration.

If Product identity is uncertain: Validation/exception workflow — human review may be required before final validation.

---

## 10. Human Decision Must Create Knowledge

Handling an Alert does not simply mean "Close Alert." The human decision must, when appropriate, update operational knowledge. RF-One must ask a contextual question capable of distinguishing the meaning of the decision.

Example question semantics:

> "This packaging differs from the expected/previous configuration. Do you want to:
> A. accept it for this purchase only;
> B. accept it as an additional valid alternative;
> C. change the normal expected configuration?"

Do not prescribe exact UI wording.

---

## 11. Accept This Purchase Only

Meaning: this specific Purchase Line/purchase is accepted; the Configured Expectation does NOT change; the exceptional configuration does NOT become the new baseline; future comparison continues against the existing Configured Expectation.

Critical example:

```text
Expected: 20 × 500 g
Exceptional purchase: 1 × 5 kg
User chooses: ACCEPT THIS PURCHASE ONLY
Next purchase: 20 × 500 g → NO Alert for "change back"
```

because `20 × 500 g` remained the valid Configured Expectation all along. The temporary exception must not replace the baseline.

---

## 12. Accept as Alternative

Meaning: the current configuration is accepted; the existing valid configuration remains valid; the new configuration becomes another approved alternative.

Example: `20 × 500 g` and `10 × 1 kg` may both be accepted configurations if the User explicitly decides so. Future purchases matching either approved alternative do not generate the same deviation Alert.

---

## 13. Change Expectation

Meaning: the newly observed configuration becomes the new approved expected configuration; future purchases are compared against the updated expectation.

Historical Purchase Lines are NEVER rewritten. The decision changes future operational knowledge, not historical Reality.

---

## 14. Decision History

Preserve the distinction: historical purchase fact ≠ current configured expectation.

A later decision must never rewrite: what was actually purchased; what packaging was received; what price was paid; what Alert occurred; what decision was made at that time.

Configured knowledge may evolve prospectively.

---

## 15. Configuration Learning

Formalize the first type of learning: **Customer/Operational Configuration Learning.**

If the User's answer can already be represented by the existing Purchasing model: process the answer, update the Configured Expectation, reuse it automatically in future — no RF-One software/module redesign is required.

Conceptual flow:

```text
Alert → contextual question → Human Decision → Configured Expectation update → future automatic behavior
```

---

## 16. Module Capability Gap

Formalize the second type of learning: **Module/RF-One Capability Learning.**

Sometimes the User's answer describes a valid operational rule that the current module cannot represent.

Example: "Accept the 5 kg package only when forecast consumption during the next four days exceeds 4 kg."

If the current Purchasing model cannot represent such a rule: DO NOT force the answer into an incorrect configuration. Instead:

```text
Operational conversation → requirement identified → existing model cannot represent it
→ capability gap → escalate to the person/function responsible for RF-One/module evolution
→ evaluate whether Purchasing should be upgraded
```

Do not implement this escalation mechanism now.

---

## 17. Configuration vs Module Evolution

Formalize the decision test: **Can the existing model correctly represent the User's operational rule?**

- YES → Configuration Learning → apply to this Organization/Restaurant context.
- NO → Module Capability Gap → escalate for RF-One evolution.

This distinction is fundamental. Do not confuse customer-specific knowledge with general RF-One ontology/capability changes.

---

## 18. RF-One Asks Questions to Learn Reality

Document this behavioral principle: when an exception reveals ambiguity about operational intent, RF-One should ask the responsible User the minimum useful contextual question required to understand the desired rule.

The answer may produce: one-time decision; new approved alternative; changed expectation; customer-specific configuration; identification of a missing RF-One capability.

RF-One should not silently infer strategic/operational intent where human confirmation is required.

---

## 19. Alert and Interaction Architecture

Keep Domain meaning separate from Interaction Architecture.

Restaurant/Purchasing defines: what deviation occurred; why it matters; which operational knowledge is affected; what decisions are semantically possible.

User Interaction Architecture defines: where/how the Alert is surfaced; desktop/mobile presentation; acknowledgement interaction; approval/decision interaction.

Do NOT implement Alerts as a Purchasing-specific UI architecture. If needed, update `03 Software/User Interaction Architecture.md` only minimally to ensure it is consistent with the rule: Alert = actionable, accountable, acknowledged interaction, rather than a passive Notification. Do not redesign the Interaction Architecture.

---

## 20. Purchase Recording Workflow Update

Update the canonical Purchasing workflow coherently. After Product recognition/classification, Purchase Recording should include conceptually: compare observed commercial configuration; use Configured Expectation when available; otherwise use previous Supplier Product purchase as fallback; identify deviations; create Alerts when required; continue recording when identity is certain; collect Human Decision; update operational configuration prospectively when appropriate; escalate capability gaps rather than inventing unsupported rules.

Do not turn every Purchase Line into a human approval workflow. Normal known/coherent lines continue automatically.

---

## 21. Exception-Driven Operating Principle

Formalize:

```text
Known + coherent → automatic processing → no unnecessary human review
Unknown / ambiguous / material deviation → exception / Alert / Validation as appropriate → human attention
```

The User works primarily on exceptions, not on re-validating every correctly recognized invoice line.

Do not merge Alert and Validation into one concept if the existing documentation already distinguishes their purposes. Clarify the boundary instead.

---

## 22. Alert vs Validation

If useful, formalize this distinction:

- **Validation issue:** RF-One lacks sufficient certainty about the factual interpretation/classification.
- **Alert:** RF-One may know exactly what happened, but the known Reality deviates from an operational expectation or requires human attention.

Example: unknown item identity → Validation. Known Ricotta, unexpected `1 × 5 kg` packaging → Alert. A case may potentially involve both if Reality requires it.

---

## 23. Do Not Overmodel

Do not create unnecessary new entities beyond what is required to document the semantics. In particular: do not create a complex rule engine ontology; do not create workflow-engine concepts; do not design alert severity taxonomies; do not define arbitrary price thresholds; do not design forecasting; do not design Purchase Support; do not implement DB schemas.

Document the minimum canonical concepts required by the decisions above.

---

## 24. Files to Update

Prefer updating existing canonical Purchasing documents rather than creating parallel documentation.

At minimum review/update as necessary:

```text
01 Domains/Restaurant/Purchasing/README.md
01 Domains/Restaurant/Purchasing/EntityDefinitions.md
01 Domains/Restaurant/Purchasing/BusinessRules.md
01 Domains/Restaurant/Purchasing/ValidationRules.md
01 Domains/Restaurant/Purchasing/Workflow.md
01 Domains/Restaurant/Purchasing/DataDictionary.md
01 Domains/Restaurant/Purchasing/AIResponsibilities.md
01 Domains/Restaurant/Purchasing/AcceptanceCriteria.md
```

Optionally update `03 Software/User Interaction Architecture.md` only if required for Alert/Notification consistency.

Do not alter unrelated Domains.

---

## 25. Report

Create `07 Tasks/Reports/TASK_PURCHASING_002_REPORT.md` with sections:

A. Summary; B. Purchase Recording scope; C. Product identity vs commercial configuration; D. Configured Expectation; E. Previous-purchase fallback; F. Variation detection; G. Alert semantics; H. Alert vs Validation; I. One-time acceptance; J. Alternative acceptance; K. Change expectation; L. Historical immutability; M. Configuration Learning; N. Module Capability Gap; O. Configuration vs RF-One evolution; P. Contextual questioning principle; Q. Interaction Architecture boundary; R. Workflow changes; S. Exact files changed; T. Remaining unresolved issues; U. Git scope confirmation.

---

## 26. Validation

Before finishing, verify that active canonical documentation consistently reflects:

- packaging/configuration changes can matter even when Product identity does not change;
- Configured Expectation takes precedence;
- previous Supplier Product purchase is only a fallback;
- one-time acceptance does not modify the baseline;
- returning to the valid baseline after a one-time exception does not create a false new deviation;
- Human Decisions can prospectively update configuration;
- historical Purchase Reality is never rewritten;
- representable answers become configuration;
- non-representable valid requirements become capability gaps/escalations;
- known/coherent purchases remain exception-driven and largely automatic;
- Alert and Notification are not treated as synonyms;
- Alert and Validation have distinct semantics.

Report any remaining contradiction instead of silently resolving something not covered by this task.

---

## 27. Git

Do NOT run `git add`, `git commit`, or `git push`.

At the end print only:

- task file created;
- report created;
- files modified;
- any unresolved issues;
- confirmation that no git add/commit/push was performed.
