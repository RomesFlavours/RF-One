# Customer Consumption Profile

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Dining Intelligence
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

When a guest can legitimately be identified across visits, RF-One supports a longitudinal **Customer Consumption Profile**, separate from the (per-occasion) [Dining Session Profile](Dining%20Session%20Profile.md).

```text
Dining Session Profile        one specific service occasion — resets/concludes with the session
Customer Consumption Profile   accumulates across many sessions for the same identified guest
```

This concept is strongly approved by the Product Owner. No identification mechanism, storage schema, or matching logic is implemented by this task (see [Exclusions](../Server%20Performance/Exclusions.md), "No software, models, or schema").

---

## What the Profile accumulates

Illustrative, non-exhaustive:

```text
recurring food preferences
drink preferences
consumption families
spending patterns
typical party context
responsiveness to certain recommendations
rejected/accepted complementary products
recurring visit behaviors
```

---

## Observed Facts vs. Inferences — mandatory distinction

```text
Observed:  "Customer ordered Chianti in 6 previous visits."
Inferred:  "Customer appears to prefer structured red wines."
```

**Inference must never silently become fact.** The Profile must preserve both: the atomic, Observed visit-level history (what was actually ordered, when) and any Derived/Inferred generalization drawn from it (a preference, a tendency), kept visibly distinct — the same discipline `Personnel Management/Performance/PerformanceEvidence.md` already requires generically ("Direct observation vs. derived interpretation"), applied here to guest evidence.

A recommendation drawn from an Inferred preference (e.g. Service Copilot suggesting a similar red wine) must remain traceable back to the Observed visit history it was drawn from, and must be revisable the moment new Observed evidence contradicts it — RF-One does not treat six prior Chianti orders as a permanent guest classification.

---

## Reservation / Guest sources

Future Dining/Customer Intelligence may consume guest/reservation evidence from systems such as OpenTable, Resy, future reservation/CRM systems, or walk-in identification where available. **Dining Intelligence is never made dependent on any particular reservation provider.** Provider adapters should eventually map into canonical RF-One:

```text
Guest
Reservation
Dining Session identity/context
```

No such integration is implemented by this task. This document only fixes that the eventual adapter boundary must translate provider-specific guest/reservation data into these three canonical concepts, mirroring the provider-independence discipline already established for Payroll (`01 Domains/Administration/Payroll/Payroll Provider Result.md`, "Provider boundary") and Tips (`Tips/README.md`, "Relationship to Clover source semantics").

---

## Relationship to identity and privacy

This document does not decide how a guest is legitimately identified (loyalty program, reservation platform account, payment-method matching, or another mechanism) — that determination, and any associated privacy/consent handling, is future Product/Runtime work, outside this task's Domain-architecture scope. "When a guest can legitimately be identified" is a precondition this document assumes will be satisfied by a future, separate capability, not something Dining Intelligence itself defines.

---

## Related documents

- [README.md](README.md), [Dining Session Profile.md](Dining%20Session%20Profile.md)
- [../../Personnel Management/Performance/PerformanceEvidence.md](../../Personnel%20Management/Performance/PerformanceEvidence.md), "Direct observation vs. derived interpretation"
- [../../Administration/Payroll/Payroll Provider Result.md](../../Administration/Payroll/Payroll%20Provider%20Result.md), "Provider boundary"
- [../Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md)
