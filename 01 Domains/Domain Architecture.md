# Domain Architecture — Cross-Domain Conclusions

**Version:** 1.1
**Status:** Approved (canonicalizes TASK_DOMAINS_001; updated by TASK_DOMAINS_002)
**Module:** Domain / Cross-Domain Architecture

---

## Related documents

- [README.md](README.md) — `01 Domains/` purpose and authority
- [Restaurant/README.md](Restaurant/README.md), [Restaurant/Roadmap.md](Restaurant/Roadmap.md) — Restaurant Domain boundary and roadmap
- [Personnel Management/README.md](Personnel%20Management/README.md) — the transversal Domain canonicalized by §5 below (Workforce, Selection, Training, Performance, Personnel Decisions)
- [Personnel Management/Selection/README.md](Personnel%20Management/Selection/README.md) — the first module documented in depth, migrated from the former top-level `Selection/` Domain by TASK_DOMAINS_002
- [Personnel Management/Performance/README.md](Personnel%20Management/Performance/README.md) — the second module documented in depth, by TASK_PERSONNEL_001
- [../00 Core/ConceptualArchitecture/](../00%20Core/ConceptualArchitecture/) — Core 2.0 concepts reused below (Subject, Reality, Goal, Decision/Action/Outcome/Learning, Epistemic Boundary)
- [../07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md](../07%20Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md) — task that produced this document
- [../07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md](../07%20Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md) — task that canonicalized Personnel Management and moved Selection under it

---

## 1. Purpose

This document canonicalizes architectural conclusions reached about how Restaurant relates to a set of **transversal (cross-industry) Domains and Domain candidates**: **Personnel Management** (the transversal Domain that owns the Workforce, Selection, Training, Performance and Personnel Decisions modules), and the still-separate transversal Domain candidates Customer Feedback and Review.

TASK_DOMAINS_002 created `01 Domains/Personnel Management/` and moved the pre-existing `Selection/` Domain under it as a module; Customer Feedback and Review remain candidates only — this document does not create those two. It records the boundaries and distinctions that must hold once Workforce, Training, Performance and Personnel Decisions are modeled in depth, and once Customer Feedback/Review are created, so future modeling work is consistent from the start.

This document does not redefine Core. It does not introduce Product or Runtime design.

---

## 2. Restaurant Domain boundary

Restaurant is primarily the **technical/operational Domain** for running a restaurant.

Restaurant knows restaurant-specific operations and technical knowledge, such as:

- front-of-house and kitchen operations;
- service processes and standards;
- menu and recipe execution;
- restaurant-specific inventory/purchasing semantics;
- restaurant-specific technical role requirements;
- restaurant operational constraints and outcomes.

> Restaurant must not own a capability merely because that capability is first used in a restaurant.

Where a capability is genuinely cross-industry (evaluating candidates, managing an employment relationship, training people, collecting customer feedback, publishing reviews), Restaurant supplies its own technical content as an input to the transversal Domain that owns that capability — it does not own the capability itself. This is consistent with the existing Selection precedent: Restaurant supplies technical requirements for a Kitchen Manager; Selection evaluates candidates against them (see [Personnel Management/Selection/README.md](Personnel%20Management/Selection/README.md), "Relationship to target technical Domains").

---

## 3. Transversal Domain principle

A **transversal Domain** is a Domain whose concepts and reasoning structure do not depend on any specific industry. It applies wherever the underlying business situation recurs, consuming industry-specific content from whichever technical Domain (e.g. Restaurant) the situation currently involves, without duplicating that Domain's knowledge.

Restaurant is currently the first concrete application context for these Domains, not their architectural owner — the same relationship already established for Selection applies to Personnel Management's other modules and to the remaining candidates below.

---

## 4. Current transversal Domains and candidates

```text
Personnel Management        (transversal Domain — created by TASK_DOMAINS_002)
├── Workforce                 (module — placeholder)
├── Selection                 (module — documented; migrated from the former top-level Selection/ Domain)
├── Training                  (module — placeholder)
├── Performance                (module — documented; TASK_PERSONNEL_001)
└── Personnel Decisions        (module — placeholder)

Customer Feedback            (transversal Domain candidate — not yet created)
Review                        (transversal Domain candidate — not yet created)
```

**Workforce, Selection, Training, Performance and Personnel Decisions are modules of one transversal Domain, Personnel Management — not independent top-level Domains.** This supersedes the earlier framing (TASK_DOMAINS_001) that treated Selection, Workforce, Personnel Management, Performance and Training as five separate transversal Domain candidates of equal standing; Personnel Management is the transversal Domain, and the other four are its modules.

Customer Feedback and Review remain separate transversal Domain candidates, outside Personnel Management. Neither folder is created by this document. See [Personnel Management/README.md](Personnel%20Management/README.md) for the module map, and the task that performed this reorganization: [../07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md](../07%20Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md).

---

## 5. Workforce / Selection / Training / Performance / Personnel Decisions distinctions

These five are Personnel Management's modules. They are related but must not be collapsed into one another: Workforce answers "who," Selection answers "who else is viable," Personnel Decisions answers "what do we do about the person who is there," Performance answers "what actually happened," and Training answers "how do we close an evidenced gap."

### 5.1 Selection is continuously active

Selection is not vacancy-only.

> Selection continuously creates credible human alternatives for roles, whether or not the role is currently vacant.

Its role is to continuously identify and evaluate economically viable human alternatives for roles. Selection consumes Goals, Brand expectations, role/context requirements, target-Domain technical requirements, Candidate Evidence, trainable gaps, expected performance, uncertainty, and replacement/training/transition economics.

### 5.2 Workforce represents the current human structure

Workforce represents the organization's current human structure: who currently occupies or can occupy organizational roles.

> Workforce describes who currently occupies or can occupy organizational roles.

Possible future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship. These are not defined here (see [Restaurant/Roadmap.md](Restaurant/Roadmap.md) §3 for the previously approved sequencing note, and [Personnel Management/Selection/README.md](Personnel%20Management/Selection/README.md), "Future Workforce dependency").

### 5.3 Personnel Decisions decides what happens to the current person

Personnel Decisions is distinct from both Selection and Workforce. It applies Core Decision semantics to the person currently performing the role — their observed performance and, when warranted, their replacement.

> Personnel Decisions compares the current person's expected value against available alternatives and concludes retain / develop / move / replace.

Conceptual flow:

```text
Observed performance
→ communicate / correct / give opportunity to improve
→ observe again
→ compare current expected value with available alternatives
→ retain / develop / move / replace
```

Selection finds alternatives. Personnel Decisions decides what to do about the current person and may use those alternatives when comparing current expected value against them. The question Personnel Decisions answers is operational/economic performance, not moral judgment.

### 5.4 Performance is what is actually produced

Performance is distinct from Selection, Workforce and Personnel Decisions. It represents what people actually produce in Reality (Core `Reality` — see [../00 Core/ConceptualArchitecture/01_Subject_and_Reality.md](../00%20Core/ConceptualArchitecture/01_Subject_and_Reality.md)).

Restaurant examples may include sales, items sold, margin, service time, throughput, customer reactions, product mix, and other observed outcomes (Core `Outcome` — see [../00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](../00%20Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)).

No universal performance score is defined here, and none should be assumed to exist. See also §8, KPI discovery, and [Personnel Management/Performance/README.md](Personnel%20Management/Performance/README.md) for the module now documented in depth by TASK_PERSONNEL_001.

### 5.5 Training is transversal

Training consumes:

- the required standard from the target Domain;
- the observed/assessed gap (see [Personnel Management/Selection/TrainableGap.md](Personnel%20Management/Selection/TrainableGap.md) for the currently drawn Selection/Training boundary);
- role/context;
- learning methods;
- later performance evidence.

Restaurant supplies restaurant-specific knowledge to Training; Training itself is potentially cross-industry, in the same way Selection is.

### 5.6 Relationship summary

```text
Workforce            → who currently occupies or can occupy roles
Selection            → continuously identifies credible alternatives for roles
Personnel Decisions  → decides what to do about the current occupant: retain/develop/move/replace
Performance          → what is actually produced (grounded in Reality/Outcome)
Training             → closes an evidenced, trainable gap against a target Domain's standard
```

All five are modules of Personnel Management (see §4). They must not be collapsed into one another: Workforce answers "who," Selection answers "who else is viable," Personnel Decisions answers "what do we do about the person who is there," Performance answers "what actually happened," and Training answers "how do we close an evidenced gap."

---

## 6. Customer Feedback / Review distinction

### 6.1 Customer Feedback is transversal

Any business with customers can receive feedback about an experience, product, service, employee, process, or other business aspect. Customer Feedback is therefore a transversal Domain candidate, not a Restaurant-owned concept.

### 6.2 Review is distinct from Customer Feedback

Review is also a transversal Domain candidate, but it is not the same concept as Customer Feedback.

- **Customer Feedback** concerns what the customer communicates to the business.
- **Review** concerns a public or publishable representation of an experience intended for third-party readers.

They may be linked:

```text
Customer Feedback ↔ Review
```

but must not be collapsed prematurely into a single concept. A future Domain design may relate them; this document only fixes that they are distinct today.

---

## 7. Cross-domain evidence principle

The same Reality may inform multiple Domains. For example:

```text
"Tatiana was excellent but the entrée took too long."
```

may inform Personnel Performance, Restaurant Operations, Training, Customer Feedback, Review, and later Selection learning — from a single observed piece of evidence.

This document does not define a new data hierarchy, evidence schema, or ownership model for shared evidence. It only records that evidence reuse across Domains is expected and must not be blocked by artificial Domain silos. How evidence is captured, stored and routed to each consuming Domain is a Product/Runtime concern, consistent with Core's Epistemic Boundary (Evidence, Observation, Belief, Inference — see [../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)), already applied by Selection's `CandidateEvidence.md`.

---

## 8. KPI discovery principle

RF-One does not canonize a fixed KPI list for any role or Domain.

RF-One should eventually determine relevant indicators from Goals, Brand, the target Domain, the role, available Evidence, and observed relationships with Outcomes — not from a hard-coded table.

Sales/hour, contribution margin, named reviews, product mix, service time, customer feedback, and similar measures are possible indicators, not universal permanent KPIs. Which indicators matter depends on context and must be derived, not assumed.

No KPI algorithm, scoring formula, or derivation mechanism is designed by this document. That is future Product/Runtime/Intelligence Engine work, built once a transversal Domain (most likely Performance) exists to anchor it.

---

## 9. Open questions

1. **Sequencing.** `Restaurant/Roadmap.md` §3 previously recorded that Workforce semantics should be established before Selection/Training/Performance are designed, yet Selection was created first (TASK_SELECTION_002, explicitly authorized) and now sits inside Personnel Management (TASK_DOMAINS_002). Confirm whether Workforce, Performance, Training, or Personnel Decisions should be modeled in depth next, and in what order.
2. **Personnel Decisions vs. Workforce boundary in practice.** Both concern "the person in the role," but from different angles (structural occupancy vs. ongoing relationship/performance management). Confirm this boundary holds once concrete entities (e.g. Assignment, Employment Relationship) are modeled, or whether some concepts naturally belong to both.
3. **Customer Feedback ↔ Review linkage.** How and whether these two Domains share an underlying evidence/entity model (e.g. a Review as one possible representation of Feedback) is not decided here.
4. **Performance and KPI ownership.** Whether "Performance" is the module that hosts KPI-discovery logic, or whether KPI discovery is a cross-module capability that reads from Performance among other modules, is not decided here.
5. **Naming.** "Personnel Management" and its five modules (Workforce, Selection, Training, Performance, Personnel Decisions) are now the fixed canonical names (TASK_DOMAINS_002). No final names are fixed for the remaining candidates, Customer Feedback and Review.
