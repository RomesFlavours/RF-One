# Next Best Action and Next Best Moment

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Service Copilot
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

Two distinct questions Service Copilot must eventually answer — **not implemented by this task**; this document defines their inputs, output responsibility, and boundaries only.

```text
Next Best Action     what should the Server do?
Next Best Moment      when should RF-One intervene (or not at all)?
```

A correct recommendation delivered at the wrong moment may reduce service quality — the two questions are genuinely separate and must not be collapsed into one "recommendation" concept.

---

## Next Best Action

### Inputs

```text
Brand Playbook                        (Server Performance/Brand Expectation and Personal Baseline.md)
Dining Session Profile                 (Dining Intelligence/Dining Session Profile.md)
Customer Consumption Profile           (Dining Intelligence/Customer Consumption Profile.md, when available)
products already ordered               (Sales Order Item evidence)
open opportunities                     (Server Performance/Opportunity Capture.md)
individual Server performance profile  (Server Performance/Individual Performance Profile.md)
prior coaching outcomes                (Server Performance/Coaching Model.md)
concurrent service load                (Server Performance/Concurrent Service Load.md)
operational context                    (Sales / Organization evidence)
```

### Output responsibility

Next Best Action's output is a single, short, actionable suggestion for this table/moment — never a list, never a dashboard. It must be traceable to the inputs above (the same traceability requirement `Personnel Management/Performance/PerformanceIndicator.md` already places on a Performance Indicator), so a Server or manager can understand why a given suggestion was made.

### Boundaries

Next Best Action never recommends a personnel decision, never recommends a table/floor assignment (see [Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md)), and never presents an Inferred suggestion with Observed-grade certainty (see [Server Performance/Evidence Sources.md](../Server%20Performance/Evidence%20Sources.md)).

---

## Next Best Moment

### Inputs

```text
table state
open opportunity
concurrent load
current problems/urgencies
likelihood the Server can act right now
past response to similar interventions (this Server's own history)
```

### Output responsibility

Next Best Moment's output is a timing decision: intervene now, or not now. **"Do not interrupt now" is a valid, and sometimes correct, output.** Delivering a correct Next Best Action at a poor moment (mid-conversation with the guest, during a rush, immediately after a complaint) can actively harm service quality — Next Best Moment exists specifically to prevent that failure mode.

### Boundaries

Next Best Moment does not decide *what* to suggest (that is Next Best Action's responsibility) and never overrides a Server's own judgment signal once [Judgment / Customer Reading](../Server%20Performance/Future%20Development.md) is eventually built — a Server's explicit "not now"/rejection input should suppress further prompting for that same opportunity, not trigger repeated interruption.

---

## Relationship between the two

```text
Next Best Action   → WHAT should help this Server next
Next Best Moment    → WHEN (or whether) to actually deliver it
```

Both are required together — an engine that only answers "what" without "when" risks becoming exactly the dashboard-style, high-interruption interface [Smartwatch Interaction.md](Smartwatch%20Interaction.md) explicitly rejects.

---

## Not implemented by this task

No recommendation engine, ranking model, or scoring algorithm is built here. This document only fixes the inputs, output responsibility, and boundaries a future implementation must respect.

---

## Related documents

- [README.md](README.md), [Service Copilot.md](Service%20Copilot.md)
- [Management Intrusiveness.md](Management%20Intrusiveness.md)
- [../Server Performance/Opportunity Capture.md](../Server%20Performance/Opportunity%20Capture.md)
- [../Server Performance/Future Development.md](../Server%20Performance/Future%20Development.md) — Judgment / Customer Reading
