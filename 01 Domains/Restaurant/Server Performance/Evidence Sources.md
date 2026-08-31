# Evidence Sources

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

This document identifies likely evidence sources for Server Performance without making them the ontology — a source is where evidence comes from, never what Server Performance canonically means. Maintains, throughout:

```text
Source Evidence  ≠  Canonical Interpretation  ≠  Inference
```

---

## Canonical evidence sources (illustrative, not exhaustive)

```text
Clover / other POS              → transactional evidence, mediated entirely through Sales' canonical
                                    model (Order, Order Item, Payment, Tip, Refund, Void) — Clover is
                                    an EVIDENCE SOURCE, never the definition of Server Performance

Shifts / timekeeping             → hours worked, presence (Sales/Organization evidence, already the
                                    basis of Tips' presence-based eligibility, `Tips/README.md`)

Sales                             → Order, Order Item, quantity, Modifier, Discount, Payment, Tip,
                                    Refund, Void/Cancellation, Location, business_date
                                    (`Sales/Restaurant Sales Model.md`, TASK_SALES_002)

Tips                              → realized Tip Allocation, service-attribution boundary
                                    (`Tips/README.md`, `Tips/Tip Allocation.md`)

Organization / Employee           → canonical Employee, Restaurant, Location, Restaurant Role,
Assignment                         Employee Assignment (TASK_ORGANIZATION_002)

Dining / Consumption Intelligence → Dining Session Profile, Customer Consumption Profile
                                    (`../Dining Intelligence/README.md`) — consumed, not owned

Reservation / Guest platforms     → future evidence (OpenTable, Resy, future CRM, walk-in
                                    identification) via Dining Intelligence, not directly

Guest QR Survey                   → future direct Perceived Service Quality evidence
                                    (`Perceived Service Quality.md`)

Server smartwatch inputs          → future micro-input evidence (`../Service Copilot/Smartwatch
                                    Interaction.md`) — micro-input only, never data entry

Training history                  → Personnel Management/Training intervention record

Management configuration          → Brand Expectation, intrusiveness level, gamification settings
                                    (Brand-configurable, never hard-coded)
```

None of these sources is required to be present for Server Performance to function partially — absence of a source (e.g. no QR Survey deployed yet) is an Unknown for that evidence category, never treated as a negative signal.

---

## Epistemic model: Observed / Derived / Inferred

Every important Server Performance concept distinguishes, where appropriate, these three epistemic states — the same discipline `Personnel Management/Performance/PerformanceEvidence.md` requires generically, applied here to Restaurant Server evidence specifically:

### Observed

Directly evidenced. Example: *"Server sold wine on 8 of 20 qualifying tables."* — an atomic fact traceable to specific `Order Item`/Payment records.

### Derived

Deterministically calculated from Observed canonical facts, with a repeatable, auditable formula. Example: *"Wine conversion = 40%."* — a [Performance Measure](../../Personnel%20Management/Performance/PerformanceMeasure.md).

### Inferred

A model-generated conclusion carrying uncertainty. Example: *"This Server may be weak at introducing wine to this table archetype."* — a [Performance Indicator](../../Personnel%20Management/Performance/PerformanceIndicator.md)-adjacent conclusion or a Coaching Model hypothesis, never presented with Observed-grade confidence, and never silently collapsed back into an Observed or Derived fact.

RF-One does not collapse these states into each other anywhere in this module — not in the Individual Performance Profile, not in a Service Copilot recommendation, not in a coaching dollar estimate.

---

## Source Evidence ≠ Canonical Interpretation ≠ Inference — worked example

```text
Source Evidence          Clover Order Item: "1x Chianti, Table 12, 7:42pm, Server: Maria"

Canonical Interpretation  Sales module fact: an Order Item exists, attributed to this Order/Employee
                          per Sales' own attribution rules (not automatically "Maria's sale" —
                          see Tips' existing caution that Order.employee ≠ Service Employee)

Inference                 "Maria is effective at wine upselling at Table 12's archetype" — a
                          Coaching-relevant conclusion, uncertain, never a Fact
```

This mirrors the service-attribution caution Tips already established (`Tips/README.md`, "Relationship to Clover source semantics": `Order.employee ≠ Service Employee`) — Server Performance reuses that same attribution discipline rather than assuming POS-operational fields are service-ownership facts.

---

## Related documents

- [Server Performance.md](Server%20Performance.md)
- [../../Personnel Management/Performance/PerformanceEvidence.md](../../Personnel%20Management/Performance/PerformanceEvidence.md)
- [../Tips/README.md](../Tips/README.md)
- [../Dining Intelligence/README.md](../Dining%20Intelligence/README.md)
