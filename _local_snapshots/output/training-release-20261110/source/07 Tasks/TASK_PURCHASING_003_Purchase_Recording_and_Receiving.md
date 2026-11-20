# TASK_PURCHASING_003 — Purchase Recording and Physical Receiving

**Type:** Documentation only. No database, software, UI, OCR, camera, Order module or reconciliation engine implementation.
**Scope:** Restaurant/Purchasing (Purchase Recording only).

---

## PURPOSE

Extend and consolidate the Restaurant/Purchasing module documenting the operational part of:

PURCHASE RECORDING

with particular attention to:

- Order vs Invoice vs Physical Receiving;
- receiving mobile;
- receiving based on label;
- receiving based on Order;
- extra/unexpected items;
- damaged items;
- reconciliation;
- Purchasing Alerts;
- ACCEPT / REJECT decisions;
- partial acceptance/rejection;
- returns;
- expected supplier credits;
- credit-note reconciliation;
- long-lived unresolved supplier discrepancies.

This task is DOCUMENTATION ONLY.

Do NOT implement software, database, UI, OCR, camera, Order module or reconciliation engine.

==================================================
0. READ FIRST
==================================================

Read at least:

- `01 Domains/Restaurant/Purchasing/README.md`
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`
- `01 Domains/Restaurant/Purchasing/DataDictionary.md`
- `01 Domains/Restaurant/Purchasing/BusinessRules.md`
- `01 Domains/Restaurant/Purchasing/ValidationRules.md`
- `01 Domains/Restaurant/Purchasing/Workflow.md`
- `01 Domains/Restaurant/Purchasing/AIResponsibilities.md`
- `01 Domains/Restaurant/Purchasing/AcceptanceCriteria.md`
- `01 Domains/Restaurant/Purchasing/DataAcquisition.md`
- `03 Software/User Interaction Architecture.md`
- `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md`
- `07 Tasks/TASK_PURCHASING_002_Alerts_Expectations_and_Operational_Learning.md` if present
- `07 Tasks/Reports/TASK_PURCHASING_002_REPORT.md` if already present

If TASK_PURCHASING_002 has not yet been executed, use the canonical Purchasing files currently in the working tree and do not invent or duplicate concepts unnecessarily.

==================================================
1. PURCHASING MODULE SCOPE
==================================================

Document this distinction:

```text
Restaurant / Purchasing
├── Purchase Recording
└── Purchase Support      [future]
```

Purchase Recording
= records and understands what actually happened.

Purchase Support
= future capability that will help decide what, how much, from whom and under what conditions to buy.

DO NOT design Purchase Support in this task.

==================================================
2. THREE SOURCES OF PURCHASE REALITY
==================================================

Purchase Recording must distinguish three different sources:

ORDER
= what the Restaurant asked the Supplier to provide

INVOICE / PURCHASE DOCUMENT
= what the Supplier states it sold / billed

PHYSICAL RECEIVING
= what the Restaurant actually observed arriving

Canonical reconciliation:

```text
Order
vs
Invoice
vs
Physical Receiving
```

These three representations must never be collapsed into one.

==================================================
3. ORDER MODULE — ASSUMED DEPENDENCY ONLY
==================================================

Assume a future/existing Order capability is available to Purchase Recording.

For this task, use only the minimum conceptual information needed:

```text
Order
- Supplier
- Item
- Quantity
```

Do NOT design the Order module.
Do NOT define purchasing recommendations.
Do NOT define Purchase Orders beyond what is necessary for reconciliation.

The purpose here is only to allow Purchase Recording to compare:

what was ordered
vs
what was invoiced
vs
what physically arrived.

==================================================
4. WHY ALL THREE COMPARISONS MATTER
==================================================

Document these distinct checks:

ORDER vs INVOICE
→ Did the Supplier bill what was ordered?

INVOICE vs RECEIVING
→ Did the Supplier physically deliver what it billed?

ORDER vs RECEIVING
→ Did the Restaurant actually receive what it requested?

Examples:

```text
A)
Ordered: Wine A × 3
Invoiced: Wine A × 3
Received: Wine A × 2
→ physical short delivery

B)
Ordered: Wine A × 3
Invoiced: Wine A × 2
Received: Wine A × 2
→ supplier shorted before invoice

C)
Ordered: Wine A × 3
Invoiced: Wine B × 3
Received: Wine B × 3
→ unauthorized / unexpected substitution relative to Order

D)
Ordered: Wine A × 3
Invoiced: Wine A × 3
Received: Wine B × 3
→ physical delivery does not match invoice
```

Do not reduce these to a generic OK/KO.

==================================================
5. PURCHASE DOCUMENT IS SUPPLIER REPRESENTATION
==================================================

Clarify:

Purchase Document
= source commercial representation supplied by the Supplier.

It is evidence.

It is NOT automatically equivalent to physical Receiving Reality.

A Supplier may:

- omit an ordered product;
- invoice a product that does not arrive;
- deliver a different product;
- deliver different quantity;
- deliver different packaging;
- deliver damaged product;
- include an unexpected product.

Purchase Recording must preserve the distinction.

==================================================
6. PHYSICAL RECEIVING
==================================================

Introduce/consolidate the minimum canonical Receiving concept needed to represent:

the Restaurant's observation of what physically arrived.

Do not overmodel.

The Receiving representation must be able to preserve:

- Supplier
- related Order when known
- related Purchase Document / Invoice when known
- Location / receiving destination
- receiving timestamp
- receiving User
- observed items
- observed quantities
- observed packaging/configuration
- photos/evidence where required
- source/provenance
- completion status

Use the existing repository naming style where possible.

If a new canonical concept is required, prefer a simple name such as:

Receiving Record

and, if necessary:

Receiving Line

Do not create unnecessary ontology.

==================================================
7. RECEIVING IS OBSERVATION, NOT DECISION
==================================================

Strong rule:

```text
Receiving
= recording physical Reality

Receiving
≠ Purchasing Decision
```

Operational staff receiving merchandise normally have no authority to decide whether a Supplier deviation is commercially acceptable.

Their responsibility is to record facts.

They do NOT decide:

- whether a substitution is acceptable;
- whether an extra product should be kept;
- whether a Supplier made an acceptable commercial change;
- whether a different package should become standard;
- whether a disputed amount should be accepted economically.

Those decisions belong to the responsible Purchasing authority.

==================================================
8. MOBILE-FIRST RECEIVING
==================================================

Receiving is primarily a mobile operational function.

It must be compatible with:

`03 Software/User Interaction Architecture.md`

The receiving employee may have:

- no access to the full RF-One Web Operational Workspace;
- only the mobile Receiving capability for the assigned organizational scope.

The mobile Receiving interaction must be intentionally simple and low-interpretation.

The operator records evidence and quantities.

RF-One performs interpretation and reconciliation.

Do NOT design exact UI layout.

==================================================
9. RECEIVING MODE A — LABEL-BASED
==================================================

For structured Suppliers such as large distributors, Receiving may use package/case labels.

Conceptual workflow:

1. Employee frames/scans the Invoice/Purchase Document.
2. RF-One recognizes the document and returns an acknowledgement that Receiving can begin.
3. System asks Employee to capture package/case labels.
4. Employee captures one label for each received package/case as required.
5. RF-One extracts/recognizes available facts such as:
   - Supplier item
   - product identity
   - brand/variant
   - packaging
   - pack size
   - unit
   - quantity
   - other label facts
6. RF-One reconstructs Physical Receiving.
7. RF-One reconciles it with Order and Invoice.

The Employee should not classify the discrepancy.

==================================================
10. RECEIVING MODE B — ORDER-BASED
==================================================

Small Suppliers may not use machine-readable or useful labels.

Receiving must therefore support an Order-based mode.

Conceptually:

RF-One opens the relevant Order.

For each expected item:

- show recognizable item identity/description;
- show expected quantity;
- ask only for actual quantity received;
- optionally allow simple confirmation when actual = expected.

Example:

```text
Mozzarella
Expected: 4
Received: [4]
```

If only 3 arrive:

```text
Received: [3]
```

The operator does NOT choose "SHORTAGE."

RF-One derives:

```text
Expected 4
Received 3
→ shortage 1
```

==================================================
11. RECEIVING METHODS ARE FALLBACK-CAPABLE
==================================================

Receiving method can be configured/preferred by Supplier, but must not become rigid.

Even a structured Supplier may have:

- unreadable label;
- missing label;
- damaged packaging;
- exceptional item.

Therefore:

Label-based receiving
→ may fall back to Order-based/manual factual capture.

The Receiving session must not fail merely because a preferred capture mechanism fails.

==================================================
12. EXTRA / UNEXPECTED ITEM
==================================================

Receiving must support merchandise physically delivered but not present in the Order.

Operational Employee records only facts.

Minimum:

- free-text description
- quantity
- unit/packaging if recognizable
- PHOTO — mandatory
- receiving context/provenance

Example:

```text
+ EXTRA ITEM
Description: Zucchine
Quantity: 2 cases
Photo: required
```

The Employee does not decide:

- whether it is acceptable;
- whether it is a substitution;
- how it should be economically classified;
- whether it should be retained.

==================================================
13. EXTRA ITEM ALWAYS GENERATES ALERT
==================================================

Strong rule:

```text
Unexpected / Extra Item
→ ALERT mandatory
```

The Alert must be routed to the responsible Purchasing authority.

It should make available:

- Supplier
- Order
- Invoice if available
- description entered
- quantity
- photo
- Receiving evidence
- any AI identification/proposal clearly marked as interpretation, not fact.

The responsible Purchasing User resolves the issue later.

==================================================
14. DAMAGED ITEM
==================================================

Receiving must allow the Employee to record damaged merchandise.

For damaged quantity, preserve:

- affected Item
- quantity damaged
- PHOTO — mandatory
- Receiving context/provenance

The Employee is not asked to determine economic responsibility.

```text
Damaged item
→ factual Receiving observation
→ ALERT to Purchasing authority.
```

==================================================
15. PARTIAL QUANTITY
==================================================

Receiving and later Purchasing decisions must work at quantity level.

Example:

```text
Ordered: 10
Received: 10
Damaged: 2
```

Purchasing decision may be:

```text
8 ACCEPT
2 REJECT / RETURN
```

Do not assume an entire Purchase Line must be accepted or rejected as one indivisible unit.

==================================================
16. RECEIVING CAN COMPLETE WITH OPEN ISSUES
==================================================

Strong rule:

```text
Receiving completion
≠ resolution of Purchasing problems.
```

The Receiving Employee must normally be able to finish the Receiving session even when:

- shortage exists;
- extra item exists;
- substitution exists;
- damaged item exists;
- packaging deviation exists;
- Invoice mismatch exists.

Therefore:

```text
Receiving Status = COMPLETED
```

may coexist with:

```text
Purchasing Alerts = OPEN
```

The person unloading/receiving merchandise should not be blocked waiting for a Purchasing Manager decision.

==================================================
17. RECONCILIATION OUTPUT
==================================================

RF-One must derive detailed reconciliation results rather than generic OK/KO.

Possible semantic outcomes include:

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

Do not create a rigid exhaustive enum unless required by existing documentation.

The important principle:

record atomic differences;
do not collapse all differences into one boolean result.

==================================================
18. PURCHASING ALERT ROUTING
==================================================

Receiving discrepancies are routed to the responsible Purchasing authority.

Receiving staff:

→ record Reality

RF-One:

→ reconciles and identifies discrepancies

Purchasing responsible User:

→ evaluates and decides

Keep this consistent with the Alert semantics documented by TASK_PURCHASING_002 / User Interaction Architecture.

==================================================
19. PURCHASING DECISION — ACCEPT OR REJECT
==================================================

For a received discrepancy/item/quantity, the Purchasing authority ultimately has two fundamental economic outcomes:

```text
ACCEPT
```

or

```text
REJECT / RETURN
```

Other contextual choices may exist around configuration learning, but the physical/economic merchandise outcome is either accepted or rejected.

==================================================
20. ACCEPT
==================================================

If Purchasing chooses ACCEPT:

- the received quantity is accepted as part of the Purchase;
- economically it becomes a valid acquired quantity;
- normal Purchase downstream calculations may include it;
- the discrepancy Alert can be resolved once any required related decision/configuration step is complete.

If the item/configuration was exceptional, acceptance may be:

- one-time only;
- accepted as alternative;
- change future expectation;

according to the separate Configured Expectation semantics already documented.

Do not duplicate those rules; cross-reference them.

==================================================
21. REJECT / RETURN
==================================================

If Purchasing chooses REJECT / RETURN:

Historical Reality remains immutable:

the merchandise DID arrive physically.

Therefore DO NOT erase the Receiving observation.

Instead preserve conceptually:

```text
Received
→ Rejected / Returned
```

Economic meaning:

the rejected quantity must not remain as a valid final acquired cost/quantity once the return/rejection is established.

The return/rejection creates an expectation that the Supplier will economically correct the original billing.

==================================================
22. RETURN IS NOT "NEVER RECEIVED"
==================================================

Strong epistemic rule:

Physical history:

```text
Received
→ Returned
```

must not be rewritten as:

```text
Never received
```

even if the final economic result is equivalent to not retaining/acquiring the merchandise.

Preserve both:

what physically happened
and
what economic decision followed.

==================================================
23. EXPECTED SUPPLIER CREDIT
==================================================

When rejected/returned merchandise has already been invoiced, RF-One must preserve an operational expectation that the Supplier owes a correction.

Use a minimal canonical concept/term such as:

Expected Supplier Credit

unless an existing repository concept already models this more appropriately.

This expectation may remain OPEN for a very long time.

Do not impose an arbitrary expiration.

Real supplier disputes may remain unresolved for months or years.

==================================================
24. CREDIT CORRECTION FORMS
==================================================

An Expected Supplier Credit may later be satisfied by:

- dedicated Credit Note;
- credit/adjustment on a later Invoice;
- another explicit Supplier commercial correction represented by real source evidence.

Credit Note is already a supported Purchase Document type and should remain so.

Do not invent a second credit-document ontology.

==================================================
25. PARTIAL CREDIT
==================================================

Supplier correction may be partial.

Example:

```text
Expected Supplier Credit = $200

Credit received = $120

→ outstanding = $80
```

Later:

```text
Credit received = $80

→ resolved
```

Preserve actual source credit facts.

The remaining outstanding amount is derived from:

```text
Expected Credit
minus
recognized applicable Supplier Credits.
```

Do not persist recalculable outstanding totals as canonical truth if they can be derived reliably from facts.

==================================================
26. CREDIT RECONCILIATION
==================================================

Purchase Recording must conceptually support:

```text
Original Purchase Document
→ rejected/returned quantity
→ Expected Supplier Credit
→ future Supplier Purchase Document / Credit Note
→ reconciliation
```

If the Supplier correctly provides the expected correction:

→ resolve expectation

If the Supplier:

- omits the credit;
- provides an incorrect amount;
- applies it to the wrong item/document;
- only partially satisfies it;

→ keep remaining expectation OPEN
→ generate/maintain Purchasing Alert as appropriate.

==================================================
27. NEXT-INVOICE CHECK
==================================================

When later Supplier invoices/documents arrive, RF-One should check whether an outstanding Expected Supplier Credit has been respected.

Conceptually:

```text
New Supplier Purchase Document
→ inspect available credit/adjustment evidence
→ reconcile against open Expected Supplier Credits
```

Match
→ resolve fully or partially

No match / wrong match
→ Alert

Do NOT assume the correction must occur on exactly the next invoice.

The expectation remains open until actually satisfied or a responsible User explicitly resolves it by another valid decision.

==================================================
28. LONG-LIVED OPEN SUPPLIER ISSUES
==================================================

Document explicitly:

Purchasing discrepancy lifecycle
may extend beyond the delivery date and beyond the original Invoice.

Purchase Recording is therefore not necessarily complete when Physical Receiving ends.

A supplier issue may remain:

```text
OPEN
for months or years
```

until the commercial correction is actually reconciled or formally resolved.

==================================================
29. RECEIVING EVIDENCE
==================================================

Apply RF-One Evidence/Reality discipline.

Preserve source evidence such as:

- Invoice image/document;
- package labels;
- photos of extra items;
- photos of damaged merchandise;
- manual quantity observations;
- Receiving User/timestamp;
- Supplier documents later providing credit.

Derived interpretations must remain distinguishable from source evidence.

==================================================
30. EMPLOYEE SIMPLICITY PRINCIPLE
==================================================

Formalize strongly:

Operational Receiving UI should minimize interpretation by receiving staff.

The Employee should perform actions analogous to:

```text
SCAN INVOICE
SCAN LABEL
SCAN LABEL
...
or
CONFIRM ACTUAL QUANTITY
...
ADD EXTRA ITEM + PHOTO
MARK DAMAGED QUANTITY + PHOTO
FINISH
```

The Employee should NOT be required to understand:

- accounting;
- Food Cost;
- Supplier disputes;
- economic classification;
- substitutions policy;
- credit handling;
- purchasing configuration rules.

RF-One and the responsible Purchasing User handle those layers.

==================================================
31. AUTHORIZATION BOUNDARY
==================================================

Receiving permission may be substantially narrower than general Purchasing access.

Conceptually:

```text
Receiving User
→ assigned organizational scope/location
→ Mobile Receiving
→ capture evidence
→ record actual quantities
→ record extra/damaged items
→ complete Receiving
```

No automatic right to:

- full Purchasing Web pages;
- supplier configuration;
- cost analysis;
- approve deviations;
- resolve Alerts;
- change Configured Expectations.

Do not hardcode customer-specific roles.

==================================================
32. PURCHASE RECORDING FLOW
==================================================

Update the canonical workflow to reflect conceptually:

```text
Order
        ↓
Purchase Document / Invoice
        ↓
Physical Receiving
        ↓
Three-way reconciliation:
Order vs Invoice vs Receiving
        ↓
Discrepancies
        ↓
Purchasing Alerts
        ↓
Responsible Purchasing Decision
        ↓
ACCEPT
or
REJECT / RETURN
        ↓
if returned and invoiced:
Expected Supplier Credit
        ↓
future Supplier document / Credit Note
        ↓
Credit reconciliation
        ↓
Resolved OR remains Open / Alert
```

---

## Report

Create `07 Tasks/Reports/TASK_PURCHASING_003_REPORT.md` describing files created/modified, concepts implemented, references updated, unresolved issues and questions requiring Product Owner decisions, per `CLAUDE.md`, "After Editing."

## Git

Do NOT run `git add`, `git commit`, or `git push`.
