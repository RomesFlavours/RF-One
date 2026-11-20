# Smartwatch Interaction

**Version:** 1.0
**Status:** Approved — future interaction concept, not current implementation
**Module:** Restaurant Domain / Service Copilot
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

The Product Owner envisions a company smartwatch as the principal real-time Service Copilot interface during service. This document records that as an **approved future interaction concept**, not a current implementation — no smartwatch or mobile application is built by this task (see [Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md)).

---

## Smartwatch as output — During-Service micro-guidance

The smartwatch is the envisioned primary surface for [Service Copilot.md](Service%20Copilot.md)'s "During Service" phase. It must be:

- discreet;
- hands-free;
- extremely concise;
- actionable;
- low-interruption.

It must **not** display dashboard-style complexity during active service — this is the same failure mode [Next Best Action and Next Best Moment.md](Next%20Best%20Action%20and%20Next%20Best%20Moment.md) already guards against by separating "what" from "when."

Illustrative examples (not canonical UI text — actual wording is a future Product/Runtime concern):

```text
"Table 12 — wine opportunity"
"Table 8 — dessert moment"
"Table 4 — returning guest / known preference"
"High load — use short recommendation"
```

These examples exist to convey the *shape* of an acceptable message (short, table-scoped, actionable), never to fix canonical semantics or exact wording.

---

## Smartwatch as human sensor — micro-input

The watch is not only an output device. It should allow the Server to contribute tiny pieces of context unavailable from POS/reservation systems. Potential one-tap inputs (illustrative, Brand-configurable, not exhaustive):

```text
first time
regular
celebration
in a hurry
problem / waiting
not interested in wine
special request
very satisfied
```

### Critical rule: micro-input, not data entry

> This must remain micro-input, not data entry. If the Server must type significant information, the interaction design has failed.

This constrains any future implementation structurally: a smartwatch interaction that requires typing, multi-step forms, or free text has violated this concept, regardless of how useful the captured information might be. Micro-input feeds [Dining Intelligence's Dining Session Profile](../Dining%20Intelligence/Dining%20Session%20Profile.md) as an observed guest/service signal, and — once [Judgment / Customer Reading](../Server%20Performance/Future%20Development.md) exists — as the Server's own rejection/acceptance signal for a Copilot suggestion.

---

## Boundaries

No smartwatch or mobile application, firmware, notification protocol, or hardware integration is designed or built by this task. This document fixes only the interaction *shape* (discreet output, one-tap input) a future implementation must respect, and the explicit non-goal of requiring the Server to type.

---

## Related documents

- [README.md](README.md), [Service Copilot.md](Service%20Copilot.md)
- [Next Best Action and Next Best Moment.md](Next%20Best%20Action%20and%20Next%20Best%20Moment.md)
- [../Dining Intelligence/Dining Session Profile.md](../Dining%20Intelligence/Dining%20Session%20Profile.md)
- [../Server Performance/Future Development.md](../Server%20Performance/Future%20Development.md)
- [../Server Performance/Exclusions.md](../Server%20Performance/Exclusions.md)
