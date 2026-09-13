# Organizational Responsibility

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core

---

## Related documents

- [Entity.md](Entity.md) §6 (Roles) — Position generalizes the Actor/Owner role pattern specifically for organizational responsibility.
- [Corporate.md](Corporate.md), [Brand.md](Brand.md), [Operational Unit.md](Operational%20Unit.md), [OperationalArea.md](OperationalArea.md) — the existing organizational-context hierarchy Position is scoped within; this document does not introduce a parallel hierarchy.
- [Process.md](Process.md) — Process Ownership (§4 below) reuses Process's existing Components and "Phases of Execution."
- [ConceptualArchitecture/09_Identity_Authority_and_Accountability.md](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md) — Acting Identity, Authority, Delegation; Position is typically the source of role-derived Authority and the organizational context for Delegation and temporary coverage.
- [ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) — requires every Process to name the Acting Identity responsible for a required human contribution; this document defines the organizational concept that makes that naming concrete and stable across personnel change.
- See also [ConceptualArchitecture/12_Attention_Management.md](ConceptualArchitecture/12_Attention_Management.md), which consumes, and does not redefine, the concepts below.
- See also [ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md](ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md) — status PROPOSED, post-baseline conceptual extension. It states explicitly that Human Operational State never modifies Position, Authority, Process Ownership or Position scope; it may only influence routing through Temporary Coverage/Backup Position/Fallback as already defined below.

---

## Purpose

This document defines **Position**, its scope, its relationship to the person(s) who occupy it, temporary delegation/coverage, and **Process Ownership** — the minimal organizational knowledge RF-One needs in order to know not only what an Acting Identity may do (Authority — doc 09), but which Position is responsible for a given Process or activity, and who currently occupies that Position.

---

## 1. Why this must be explicit

Doc 09 already establishes Identity, Authority, Delegation and Accountability, and states that Authority is evaluated in context via Corporate → Brand → Operational Unit → Domain/Module (§3). That chain says *where* Authority applies; it does not say *who, structurally, within the organization* is responsible for a given Process or exception, independent of which specific person currently holds that responsibility. [Process Autonomy](ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) (§2, §4) already requires every Process description to name "the Acting Identity responsible" for a condition requiring human contribution. This document defines the organizational concept — Position — that makes that naming concrete and durable across personnel change.

---

## 2. Position

**Position** is a stable organizational responsibility, independent of who currently occupies it. A Position is not itself an Acting Identity ([doc 09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md) §2) — it is what one or more Acting Identities occupy, temporarily or durably, in order to act with the Authority and responsibility the Position carries.

A Position has:

- a **scope** — the Corporate/Brand/Operational Unit/Operational Area/Domain/Module/Process context within which its responsibility applies, expressed using the existing hierarchy above, never a new parallel one;
- an **Authority** ([doc 09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md) §3) — role-derived Authority is typically Authority derived from occupying a Position;
- one or more **Process Ownership** relationships (§4 below);
- a relationship to whoever currently **occupies** it (§3).

Illustrative, not exhaustive or mandatory: Kitchen Manager, Shift Lead, General Manager, Payroll Administrator, IT Maintainer. Core does not fix a taxonomy of Positions — a Domain or Product configures the Positions its organization actually has.

---

## 3. Position vs. Occupant

Responsibility belongs to the Position, not directly to the person. A person occupies a Position for a period of time — Entity's existing Temporal Semantics ([Entity.md](Entity.md) §14) already supports this without a new mechanism.

```text
Process
→ responsible Position
→ current occupant (an Acting Identity, doc 09 §2)
→ temporary delegate / replacement, if one is active
```

This preserves continuity across personnel change, shift change, leave, absence or reassignment: the Position, its scope and its Process Ownership do not change merely because its occupant changes — the organizational counterpart of [Entity.md](Entity.md) §15, "Specialization Extends Rather Than Erases Identity," applied here to Position vs. occupant rather than to specialization.

An occupant may indicate who **temporarily covers** their Position (for example, for a planned absence). A temporary coverage is a form of Delegation ([doc 09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md) §4): it has an explicit Grantor, a bounded scope and duration, and must remain auditable exactly as any other Delegation. Core does not prescribe how a temporary coverage is authorized, recorded or revoked — that is Domain/Runtime design.

---

## 4. Process Ownership

Every Process ([Process.md](Process.md)) must be attributable to at least one responsible Position — not necessarily a specific person — so that an exception, a decision outside Delegated Authority, or a problem RF-One cannot resolve autonomously always has somewhere concrete to go ([doc 11](ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §4).

A Process may have a single owning Position across its whole execution, or a different owning Position per phase (Process.md, "Phases of Execution" — Planning / Scheduling-Programming / Management / Operations):

```text
Planning               → Position A
Scheduling/Programming → Position B
Management             → Position C
Operations             → Position D
```

Core does not require distinct Positions per phase, nor forbid one Position from owning several or all phases — both are legitimate, Domain-specific configurations.

**Autonomy does not remove ownership.** A Process RF-One executes entirely autonomously, within Delegated Authority, must still have a responsible Position to which an exception, an out-of-delegation decision, or an unresolved problem is attributed ([doc 11](ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md) §1, §4). Autonomous execution changes who performs the Decision/Action stages ([doc 06](ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md) §3) — it does not change whether a Position remains accountable for the Process.

---

## 5. Organizational structure is not one shape

RF-One must not assume a single universal hierarchical shape. Organizations may be more vertical, more delegated/horizontal, or hybrid; a Position's relationships to other Positions (reporting, peer, delegated-to) are configured per organization, not fixed by Core.

Core does not fix an escalation rule — for example, "if the responsible Position does not respond, always escalate to its superior." How unavailability or non-response is handled is organizational policy/configuration, consumed by Attention Management ([ConceptualArchitecture/12_Attention_Management.md](ConceptualArchitecture/12_Attention_Management.md)), not a Core rule.

---

## 6. Relationship to existing Core concepts

- **Entity / Roles** ([Entity.md](Entity.md) §6): an Acting Identity occupying a Position is an Entity assuming the Actor role ([doc 09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md) §2) in relation to that Position. A Domain may model Position as an Entity when it needs identity/attributes/lifecycle ([Entity.md](Entity.md) §2), or as a Relationship Entity ([Relationship.md](Relationship.md) §7) connecting an organizational-context Entity to an occupant — Core does not fix which.
- **Corporate / Brand / Operational Unit / Operational Area**: unchanged. Position's scope is expressed using this existing hierarchy. "Manager" as a simple mutable attribute of Operational Unit/Operational Area ([Operational Unit.md](Operational%20Unit.md), [OperationalArea.md](OperationalArea.md)) is a lightweight precedent this document generalizes — it remains valid where a full Position model is not needed.
- **Authority / Delegation** ([doc 09](ConceptualArchitecture/09_Identity_Authority_and_Accountability.md)): unchanged. Position is typically the source of role-derived Authority and the organizational context for Delegation and temporary coverage.
- **Process** ([Process.md](Process.md)): unchanged. Process Ownership is a new, minimal relationship between a Process (or Process phase) and a Position — not a redefinition of Process's own Components.

---

## Non-assumptions

Do not assume:

```text
Position is a new Entity type mandatory for every Domain
Core fixes a specific organizational hierarchy shape (vertical-only)
Core fixes an escalation rule for an unavailable or non-responding Position
every Process phase must have a different owning Position
Position replaces Acting Identity, Authority or Delegation (doc 09)
a data model, database table or schema is specified here
```
