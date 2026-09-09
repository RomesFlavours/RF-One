# Domain Architecture — Cross-Domain Conclusions

**Version:** 1.2
**Status:** Approved (canonicalizes TASK_DOMAINS_001; updated by TASK_DOMAINS_002; Selection re-elevated by TASK_DOMAINS_003; Cross Domain / Business Domain taxonomy and Training/Performance extraction documented by the post-reorganization documentation alignment task; Continuous Productivity Development added and Training redefined as Operational Knowledge by a later reorganization — see §4-5)
**Module:** Domain / Cross-Domain Architecture

---

## Related documents

- [README.md](README.md) — `01 Domains/` purpose and authority, and the Cross Domain / Business Domain folder taxonomy
- [Restaurant/README.md](Business%20Domain/Restaurant/README.md), [Restaurant/Roadmap.md](Business%20Domain/Restaurant/Roadmap.md) — Restaurant Domain boundary and roadmap (the current Business Domain)
- [Personnel Management/README.md](Cross%20Domain/Personnel%20Management/README.md) — the transversal Domain canonicalized by §5 below; its modules are Workforce, Personnel Decisions and Compensation (formerly named Payroll; Selection, the former Training, and Performance were extracted — see §4)
- [Selection/README.md](Cross%20Domain/Selection/README.md) — a Cross Domain: originally the former top-level `Selection/` Domain, folded into Personnel Management by TASK_DOMAINS_002, then re-elevated to top-level by TASK_DOMAINS_003
- [Operational Knowledge/README.md](Cross%20Domain/Operational%20Knowledge/README.md) — a Cross Domain extracted from Personnel Management as **Training** (see §4), later redefined as Operational Knowledge (a distinct concept — see its own README)
- [Continuous Productivity Development/README.md](Cross%20Domain/Continuous%20Productivity%20Development/README.md) — a Cross Domain that conceptually superseded Training's original "closes an evidenced gap" scope before Training was itself redefined as Operational Knowledge (see §4, §5)
- [Performance/README.md](Cross%20Domain/Performance/README.md) — Cross Domain extracted from Personnel Management (see §4); documented in depth by TASK_PERSONNEL_001
- [../00 Core/ConceptualArchitecture/](../00%20Core/ConceptualArchitecture/) — Core 2.0 concepts reused below (Subject, Reality, Goal, Decision/Action/Outcome/Learning, Epistemic Boundary)
- [../07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md](../07%20Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md) — task that produced this document
- [../07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md](../07%20Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md) — task that canonicalized Personnel Management and moved Selection under it (superseded for Selection by TASK_DOMAINS_003, `07 Tasks/Reports/TASK_DOMAINS_003_REPORT.md`)

---

## 1. Purpose

This document canonicalizes architectural conclusions reached about how Restaurant relates to a set of **transversal (cross-industry) Domains and Domain candidates**: **Personnel Management** (the transversal Domain whose modules are Workforce, Personnel Decisions and Compensation, formerly named Payroll — see §4 for why Selection, Operational Knowledge (formerly Training) and Performance are no longer among them), and the still-separate transversal Domain candidates Customer Feedback and Review.

TASK_DOMAINS_002 created `01 Domains/Cross Domain/Personnel Management/` and moved the pre-existing `Selection/` Domain under it as a module; Customer Feedback and Review remain candidates only — this document does not create those two. It records the boundaries and distinctions that must hold once Workforce and Personnel Decisions are modeled in depth, and once Customer Feedback/Review are created, so future modeling work is consistent from the start. A later reorganization (§4) re-elevated Selection to top-level and extracted Training (since redefined as Operational Knowledge) and Performance from Personnel Management into their own Cross Domain entries; a further reorganization added Continuous Productivity Development as an independent sibling Cross Domain and redefined Training as Operational Knowledge (see §4).

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

Where a capability is genuinely cross-industry (evaluating candidates, managing an employment relationship, training people, collecting customer feedback, publishing reviews), Restaurant supplies its own technical content as an input to the transversal Domain that owns that capability — it does not own the capability itself. This is consistent with the existing Selection precedent: Restaurant supplies technical requirements for a Kitchen Manager; Selection evaluates candidates against them (see [Selection/README.md](Cross%20Domain/Selection/README.md), "Relationship to target technical Domains").

---

## 3. Transversal Domain principle

A **transversal Domain** is a Domain whose concepts and reasoning structure do not depend on any specific industry. It applies wherever the underlying business situation recurs, consuming industry-specific content from whichever technical Domain (e.g. Restaurant) the situation currently involves, without duplicating that Domain's knowledge.

Restaurant is currently the first concrete application context for these Domains, not their architectural owner — the same relationship already established for Selection applies to Personnel Management's other modules and to the remaining candidates below.

---

## 4. Cross Domain / Business Domain taxonomy, and the current transversal Domains

Every Domain under `01 Domains/` belongs to exactly one of two families, physically expressed as the two folders directly under `01 Domains/`:

- **Cross Domain** (`01 Domains/Cross Domain/`) — a Domain whose concepts, ontology and reasoning structure are genuinely industry-independent: it must remain usable by any business/industry, not just the one that happens to be RF-One's first application. A Cross Domain may consume industry-specific content supplied by a Business Domain (as data, configuration or evidence), but must never structurally depend on one specific Business Domain to function or to be defined.
- **Business Domain** (`01 Domains/Business Domain/`) — a Domain whose ontology, integrations, metrics and operational semantics are specific to one industry/business context. A Business Domain may consume Cross Domain capabilities (e.g. Restaurant using Selection to evaluate a candidate, or Personnel Management to reason about its people), and may supply its own technical content into a Cross Domain's reasoning as an input — but it does not own or redefine the Cross Domain capability itself.

This is the same **transversal Domain principle** already established in §3, now given an explicit physical home so the distinction is visible in the folder structure, not only in prose.

```text
01 Domains/
├── Cross Domain/
│   ├── Administration               (transversal Domain, with its Payroll module)
│   ├── Continuous Productivity      (top-level, transversal Domain — conceptually superseded
│   │   Development                   Training's original "closes an evidenced gap" scope
│   │                                 before Training was itself redefined below)
│   ├── Operational Knowledge        (top-level, transversal Domain — formerly "Training",
│   │                                 extracted from Personnel Management, then redefined as
│   │                                 the shared retrievable-information repository)
│   ├── Performance                  (top-level, transversal Domain — extracted from Personnel
│   │                                 Management; documented; TASK_PERSONNEL_001)
│   ├── Personnel Management         (transversal Domain — created by TASK_DOMAINS_002)
│   │   ├── Workforce                   (module — placeholder)
│   │   ├── Personnel Decisions         (module — placeholder)
│   │   └── Compensation                (module — formerly named Payroll; RF-One
│   │                                    determines, composes and approves
│   │                                    compensation but does not itself
│   │                                    perform Payroll)
│   ├── Selection                    (top-level, transversal Domain — re-elevated by
│   │                                 TASK_DOMAINS_003; was a Personnel Management module,
│   │                                 TASK_DOMAINS_002, before that)
│   └── Taxation                     (transversal Domain)
│
└── Business Domain/
    └── Restaurant              (the current, and so far only, Business Domain)

Customer Feedback            (transversal Domain candidate — not yet created; would be a Cross Domain)
Review                        (transversal Domain candidate — not yet created; would be a Cross Domain)
```

**Training and Performance are no longer modules of Personnel Management.** They were extracted into their own top-level Cross Domain entries by explicit Product Owner direction, on the same grounds as Selection's re-elevation (§4 below and TASK_DOMAINS_003): both are genuinely industry-independent capabilities, not exclusively a people-management concern, and neither should depend structurally on Personnel Management as a parent Domain any more than Selection should. **Personnel Management's modules are Workforce, Personnel Decisions and Compensation.** This supersedes every earlier statement in this document (and elsewhere) that listed Training and/or Performance as Personnel Management modules. Training has since been redefined as **Operational Knowledge** (see below) — a distinct concept, still not a Personnel Management module. A third module — Employee Income Composition & Payroll — was added later still, then renamed from **Payroll** to **Compensation** by explicit Product Owner decision: RF-One determines, composes and approves compensation but does not itself perform Payroll, which is the responsibility of an external Payroll Provider — see `Cross Domain/Personnel Management/Compensation/README.md`, "Why this module is not called Payroll." `01 Domains/Cross Domain/Administration/Payroll/` is a separate, unrenamed module of the Administration Domain (the administrative execution/recording boundary — see §4's Administration entry above) and must not be confused with this Compensation module.

**Workforce, Personnel Decisions and Compensation remain modules of one transversal Domain, Personnel Management — not independent top-level Domains.** This supersedes the earlier framing (TASK_DOMAINS_001) that treated Selection, Workforce, Personnel Management, Performance and Training as five separate transversal Domain candidates of equal standing; Personnel Management is the transversal Domain, and these three are its modules today.

**Selection, Operational Knowledge (formerly Training) and Performance are each a top-level, transversal Cross Domain in their own right — siblings of Personnel Management, not modules of it.** TASK_DOMAINS_002 originally folded all three into Personnel Management alongside Workforce/Personnel Decisions; a later Product Owner direction re-elevated Selection first (TASK_DOMAINS_003), then extracted Training and Performance the same way when the Cross Domain / Business Domain taxonomy was introduced. All three remain closely related to Personnel Management's modules — in particular Personnel Decisions, which consumes Selection's output and draws on Performance evidence — without being owned by it; see §5 below.

**Continuous Productivity Development is a further independent sibling Cross Domain**, added after the above extraction. It identifies gaps/opportunities, estimates their economic value, determines the best intervention, measures outcomes, and learns from results — the role Training's placeholder originally reserved ("closes an evidenced, trainable gap"), generalized well beyond it (see [Continuous Productivity Development/README.md](Cross%20Domain/Continuous%20Productivity%20Development/README.md)). Training's folder was, separately, later redefined as **Operational Knowledge**: the shared repository of retrievable operational information (Operational Knowledge Pills) that Copilot and other RF-One functions may retrieve — it does not identify gaps, decide interventions, or measure outcomes; that remains Continuous Productivity Development's role. The two are independent siblings, not two names for the same thing.

Customer Feedback and Review remain separate transversal Domain candidates (would be Cross Domains if created), outside Personnel Management. Neither folder is created by this document. See [Personnel Management/README.md](Cross%20Domain/Personnel%20Management/README.md) for Personnel Management's module map, [Selection/README.md](Cross%20Domain/Selection/README.md), [Operational Knowledge/README.md](Cross%20Domain/Operational%20Knowledge/README.md), [Continuous Productivity Development/README.md](Cross%20Domain/Continuous%20Productivity%20Development/README.md) and [Performance/README.md](Cross%20Domain/Performance/README.md) for these Cross Domains, and the tasks that performed these reorganizations: [../07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md](../07%20Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md), `07 Tasks/Reports/TASK_DOMAINS_003_REPORT.md`, and `07 Tasks/Reports/DOMAIN_REORGANIZATION_CROSS_VS_BUSINESS_REPORT.md`.

---

## 5. Workforce / Selection / Continuous Productivity Development / Performance / Personnel Decisions distinctions

Two of these five (Workforce, Personnel Decisions) are Personnel Management's modules; Selection, Continuous Productivity Development and Performance are each a sibling top-level Cross Domain, described in §4. They are closely related but must not be collapsed into one another: Workforce answers "who," Selection answers "who else is viable," Personnel Decisions answers "what do we do about the person who is there," Performance answers "what actually happened," and Continuous Productivity Development answers "how do we close an evidenced gap or capture an opportunity." (Operational Knowledge, the former Training, is a further sibling Cross Domain but sits outside this particular five-way distinction — see §5.7: it answers a different question, "what retrievable information already exists," not a question about the person or the decision made about them.)

### 5.1 Selection is continuously active

Selection is not vacancy-only.

> Selection continuously creates credible human alternatives for roles, whether or not the role is currently vacant.

Its role is to continuously identify and evaluate economically viable human alternatives for roles. Selection consumes Goals, Brand expectations, role/context requirements, target-Domain technical requirements, Candidate Evidence, trainable gaps, expected performance, uncertainty, and replacement/training/transition economics.

### 5.2 Workforce represents the current human structure

Workforce represents the organization's current human structure: who currently occupies or can occupy organizational roles.

> Workforce describes who currently occupies or can occupy organizational roles.

Possible future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship. These are not defined here (see [Restaurant/Roadmap.md](Business%20Domain/Restaurant/Roadmap.md) §3 for the previously approved sequencing note, and [Selection/README.md](Cross%20Domain/Selection/README.md), "Future Workforce dependency").

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

No universal performance score is defined here, and none should be assumed to exist. See also §8, KPI discovery, and [Performance/README.md](Cross%20Domain/Performance/README.md) — the Cross Domain (not a Personnel Management module, see §4) documented in depth by TASK_PERSONNEL_001.

### 5.5 Continuous Productivity Development is transversal

Continuous Productivity Development generalizes what the former Training placeholder originally reserved ("closes an evidenced, trainable gap"): it identifies a Gap/Opportunity, estimates its economic value, selects the best available intervention (of which formal training/development is only one candidate among several), measures the outcome, and learns from it. It consumes the observed/assessed gap (see [Selection/TrainableGap.md](Cross%20Domain/Selection/TrainableGap.md) for the currently drawn Selection boundary), role/context, and later Performance evidence. This document does not restate that Domain's model in depth — see [Continuous Productivity Development/README.md](Cross%20Domain/Continuous%20Productivity%20Development/README.md) and its own concept specification.

Restaurant supplies restaurant-specific knowledge and standards this Domain's interventions are evaluated against; Continuous Productivity Development itself is potentially cross-industry, in the same way Selection is.

### 5.6 Relationship summary

```text
Workforce                         → who currently occupies or can occupy roles
Selection                         → continuously identifies credible alternatives for roles
Personnel Decisions                → decides what to do about the current occupant: retain/develop/move/replace
Performance                        → what is actually produced (grounded in Reality/Outcome)
Continuous Productivity Development → closes an evidenced gap/opportunity via the best available intervention
```

Workforce and Personnel Decisions are modules of Personnel Management; Selection, Performance and Continuous Productivity Development are each a sibling top-level Cross Domain (see §4). They must not be collapsed into one another: Workforce answers "who," Selection answers "who else is viable," Personnel Decisions answers "what do we do about the person who is there," Performance answers "what actually happened," and Continuous Productivity Development answers "how do we close an evidenced gap or capture an opportunity."

### 5.7 Operational Knowledge is orthogonal to this distinction

Operational Knowledge (the former Training placeholder, redefined — see §4) is a further sibling top-level Cross Domain, but it does not belong to the five-way personnel-decision distinction above: it answers **"what retrievable operational information already exists that could help here,"** never a question about a person's standing, alternatives, or the decision made about them. It stores and organizes Operational Knowledge Pills — small, contextual, retrievable pieces of operational information — that Copilot or another RF-One function may retrieve before or during an operational activity. It does not identify gaps, decide interventions, or measure outcomes (Continuous Productivity Development's role, §5.5); it does not evaluate a person's capability (Selection's role, §5.1). See [Operational Knowledge/README.md](Cross%20Domain/Operational%20Knowledge/README.md).

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

may inform Personnel Performance, Restaurant Operations, Continuous Productivity Development, Customer Feedback, Review, and later Selection learning — from a single observed piece of evidence.

This document does not define a new data hierarchy, evidence schema, or ownership model for shared evidence. It only records that evidence reuse across Domains is expected and must not be blocked by artificial Domain silos. How evidence is captured, stored and routed to each consuming Domain is a Product/Runtime concern, consistent with Core's Epistemic Boundary (Evidence, Observation, Belief, Inference — see [../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md)), already applied by Selection's `CandidateEvidence.md`.

---

## 8. KPI discovery principle

RF-One does not canonize a fixed KPI list for any role or Domain.

RF-One should eventually determine relevant indicators from Goals, Brand, the target Domain, the role, available Evidence, and observed relationships with Outcomes — not from a hard-coded table.

Sales/hour, contribution margin, named reviews, product mix, service time, customer feedback, and similar measures are possible indicators, not universal permanent KPIs. Which indicators matter depends on context and must be derived, not assumed.

No KPI algorithm, scoring formula, or derivation mechanism is designed by this document. That is future Product/Runtime/Intelligence Engine work, built once a transversal Domain (most likely Performance) exists to anchor it.

---

## 9. Open questions

1. **Sequencing.** `Restaurant/Roadmap.md` §3 previously recorded that Workforce semantics should be established before Selection/Training/Performance are designed (Training since redefined as Operational Knowledge), yet Selection was created first (TASK_SELECTION_002, explicitly authorized) and now sits inside Personnel Management (TASK_DOMAINS_002). Confirm whether Workforce, Performance, Continuous Productivity Development, Operational Knowledge, or Personnel Decisions should be modeled in depth next, and in what order.
2. **Personnel Decisions vs. Workforce boundary in practice.** Both concern "the person in the role," but from different angles (structural occupancy vs. ongoing relationship/performance management). Confirm this boundary holds once concrete entities (e.g. Assignment, Employment Relationship) are modeled, or whether some concepts naturally belong to both.
3. **Customer Feedback ↔ Review linkage.** How and whether these two Domains share an underlying evidence/entity model (e.g. a Review as one possible representation of Feedback) is not decided here.
4. **Performance and KPI ownership.** Whether Performance is the (Cross Domain) capability that hosts KPI-discovery logic, or whether KPI discovery reads from Performance among other sources, is not decided here.
5. **Naming.** "Personnel Management" and its modules (Workforce, Personnel Decisions, Compensation) are the fixed canonical names (TASK_DOMAINS_002). Selection, Operational Knowledge (formerly Training), Continuous Productivity Development and Performance are each a fixed canonical name too, each a sibling top-level Cross Domain rather than a Personnel Management module (TASK_DOMAINS_003 for Selection; the Cross Domain / Business Domain reorganization for Training and Performance; a later reorganization for Continuous Productivity Development and Operational Knowledge). No final names are fixed for the remaining candidates, Customer Feedback and Review.
