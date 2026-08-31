# Concurrent Service Load

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Performance under pressure is a first-class concept. The relevant load variable is **not** total guests served during a whole shift — it is:

> **Concurrent Service Load** — the number of guests/tables being served concurrently by a Server at a given moment.

This name is retained as the canonical term (no clearly superior existing repository term was found). It is distinct from, and must not be confused with, cumulative shift volume (`Total Hours` / `Sales per Hour Worked`, a Productivity Measure — see [Server Performance.md](Server%20Performance.md), "Productivity").

---

## Where Concurrent Service Load comes from

Concurrent Service Load is **derived**, not a new canonical fact this task introduces. It is computed from evidence Sales and Organization already own:

```text
Table Service / Order evidence (open, concurrently assigned to this Server, at time T)
  + Employee Assignment / Restaurant Role (which Server is actually responsible for that table at time T)
    → count of concurrently open tables/guests for this Server at time T
```

`Restaurant Sales Model.md` §2 ("Fundamental service entity: Table Service") and §4 ("Table Service and Employees") already model the entities this concept reads from. No new schema is introduced or required by this document — Concurrent Service Load is a query/derivation over existing Table Service, Order and Employee Assignment evidence, to be implemented by a future Software task, not this Domain document.

---

## Capacity, Acceleration, Resilience

RF-One must learn how each individual Server performs as concurrent load increases. A Server may perform very well at low load and deteriorate sharply under high simultaneous demand; another may maintain quality even as workload rises. At minimum:

- **Capacity** — how much simultaneous service demand the Server can effectively manage before quality/discipline measurably degrades.
- **Acceleration** — how effectively the Server increases pace when simultaneous demand increases (does throughput rise appropriately, or does the Server fall behind).
- **Resilience** — how well Quality of Sale, Perceived Service Quality and Operational Discipline are maintained as simultaneous load rises (does the Server sacrifice quality to keep up, or hold the line).

```text
Concurrent Load ↑
  → observe what happens to:
      Productivity
      Quality of Sale
      Opportunity Capture
      Tips
      Perceived Service Quality
      Operational Discipline (errors/anomalies)
```

Performance under load is therefore evaluated as a **curve** across observed load levels for that Server, not a single aggregate number — consistent with [Individual Performance Profile.md](Individual%20Performance%20Profile.md), which stores the Server's observed load-behavior curve rather than one summary figure.

---

## Low load also matters

Low volume must not automatically excuse weak performance. Some ratio-based Productivity measures already normalize for lower volume, but low load also creates *greater* opportunity for attentive service, product knowledge, targeted recommendation, upselling and guest engagement. RF-One should therefore be able to learn whether Quality of Sale and Opportunity Capture *improve* when a Server has more available service capacity — a Server who performs identically regardless of load is not automatically "consistent" in a positive sense if their low-load Opportunity Capture never rises to reflect the extra attention they could have given.

---

## Explicit exclusion: this is not table assignment authority

**Concurrent Service Load is an input/context variable for Server Performance. It does not authorize this module, or [Service Copilot](../Service%20Copilot/README.md), to decide table/floor assignment.**

```text
Concurrent Service Load   → OBSERVES how much load a Server currently carries
Table/floor assignment    → DECIDES which Server receives the next table — a separate,
                              already-proven method the Restaurant already uses
```

This module never decides which Server receives the next table, floor rotation, section assignment, or host seating decisions. See [Exclusions.md](Exclusions.md).

---

## Epistemic status

- The count of concurrently open tables assigned to a Server at time T is **Derived** from Observed Table Service/Order/Employee Assignment evidence.
- "This Server's Capacity threshold is approximately N concurrent tables" is **Inferred** from a pattern observed across many shifts, carries uncertainty, and must be presented as such.

---

## Related documents

- [Server Performance.md](Server%20Performance.md)
- [Opportunity Capture.md](Opportunity%20Capture.md), "Opportunity Capture at low load also matters"
- [Individual Performance Profile.md](Individual%20Performance%20Profile.md)
- [Exclusions.md](Exclusions.md)
- [../Sales/Restaurant Sales Model.md](../Sales/Restaurant%20Sales%20Model.md) §2-4
- [../Organization/Employee Assignment.md](../Organization/Employee%20Assignment.md)
