# Management-Controlled Intrusiveness

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Service Copilot
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

The level of Service Copilot intervention must be configurable by Restaurant management. The core principle:

> Management controls how intrusive/autonomous Server coaching is.

---

## Relationship to Core Sovereignty and Delegated Authority

This specializes an existing Core principle rather than inventing new authority semantics. `00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md` already establishes:

> "RF-One may act, and act continuously, within a boundary the Subject has knowingly set — but the Subject always retains the authority to see clearly, to be shown consequences, and to change or revoke that boundary. Sovereignty is about who ultimately decides direction; delegated authority is about who executes within that direction."

Here, Restaurant management is the Subject/delegating authority; Service Copilot is what executes within the boundary management has set. Intrusiveness level is that boundary, made concrete for the specific case of real-time Server coaching.

---

## Approved conceptual levels

Illustrative levels, not a mandatory fixed enum (a future implementation may find a better-fitting representation of the same underlying delegated-authority spectrum):

```text
Observe                 RF-One analyzes but does not coach the Server directly.

Recommend to Manager     RF-One proposes an intervention to management, who decides whether
                          and how to deliver it.

Coach with Approval      RF-One prepares coaching content but requires manager approval before
                          it reaches the Server.

Autonomous Coaching       RF-One communicates directly with the Server, within delegated limits
                          management has set.
```

Each level is a different point on the same delegated-authority boundary: how much RF-One may act on its own within the direction management has set, and how much must return to a human before it reaches the Server.

---

## Configuration is per-Restaurant, per-Brand

Like [Brand Expectation](../Server%20Performance/Brand%20Expectation%20and%20Personal%20Baseline.md), the intrusiveness level is Restaurant/Brand-configurable, never a hard-coded default. Different Locations of the same Brand may run at different intrusiveness levels if management chooses (e.g. a newly opened Location starting at `Coach with Approval` while an established Location runs `Autonomous Coaching`), without requiring different Server Performance or Dining Intelligence architecture underneath.

---

## Boundaries

This document does not implement a configuration UI, a permissions model, or an approval workflow — those are future Product/Runtime concerns. It fixes only the conceptual requirement that intrusiveness be explicit, management-controlled, and revocable at any time (mirroring the Core Sovereignty principle's "authority to... change or revoke that boundary").

---

## Related documents

- [README.md](README.md), [Service Copilot.md](Service%20Copilot.md)
- [Next Best Action and Next Best Moment.md](Next%20Best%20Action%20and%20Next%20Best%20Moment.md)
- [../../../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../../../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)
- [../Server Performance/Brand Expectation and Personal Baseline.md](../Server%20Performance/Brand%20Expectation%20and%20Personal%20Baseline.md)
