# Domain Architecture — Shared-Domains Conclusions

**Version:** 1.4
**Status:** Approved (canonicalizes TASK_DOMAINS_001; updated by TASK_DOMAINS_002; Selection re-elevated by TASK_DOMAINS_003; Shared Domains / Business Domain taxonomy and Training/Performance extraction documented by the post-reorganization documentation alignment task; Continuous Productivity Development added and Training redefined as Operational Knowledge by a later reorganization; Cross Domain renamed Shared Domains and the Purchased Shared Domain added by a later reorganization; Management Shared Domain established, Personnel Management retired and Compensation moved to Administration by Product Owner decision of 2026-10-25 — see §4-5)
**Module:** Domain / Shared-Domains Architecture

---

## Related documents

- [README.md](README.md) — `01 Domains/` purpose and authority, and the Shared Domains / Business Domain folder taxonomy
- [Restaurant/README.md](Business%20Domain/Restaurant/README.md), [Restaurant/Roadmap.md](Business%20Domain/Restaurant/Roadmap.md) — Restaurant Domain boundary and roadmap (the current Business Domain)
- [Management/README.md](Shared%20Domains/Management/README.md) — the Shared Domain of People, Organization and Project Manager (Product Owner decision, 2026-10-25); its Organization component holds the Workforce and Personnel Decisions responsibilities distinguished in §5 below, formerly modules of the now-retired Personnel Management Domain (see §4)
- [Administration/Compensation/README.md](Shared%20Domains/Administration/Compensation/README.md) — Compensation, an Administration module since 2026-10-25 (formerly a Personnel Management module, earlier named Payroll)
- [Selection/README.md](Shared%20Domains/Selection/README.md) — a Shared Domain: originally the former top-level `Selection/` Domain, folded into Personnel Management by TASK_DOMAINS_002, then re-elevated to top-level by TASK_DOMAINS_003
- [Operational Knowledge/README.md](Shared%20Domains/Operational%20Knowledge/README.md) — a Shared Domain extracted from Personnel Management as **Training** (see §4), later redefined as Operational Knowledge (a distinct concept — see its own README)
- [Continuous Productivity Development/README.md](Shared%20Domains/Continuous%20Productivity%20Development/README.md) — a Shared Domain that conceptually superseded Training's original "closes an evidenced gap" scope before Training was itself redefined as Operational Knowledge (see §4, §5)
- [Performance/README.md](Shared%20Domains/Performance/README.md) — Shared Domain extracted from Personnel Management (see §4); documented in depth by TASK_PERSONNEL_001
- [Purchased/README.md](Shared%20Domains/Purchased/README.md) — a Shared Domain added later still (see §4): normalized purchase facts from what a Business Domain was invoiced for
- [../00 Core/ConceptualArchitecture/](../00%20Core/ConceptualArchitecture/) — Core 2.0 concepts reused below (Subject, Reality, Goal, Decision/Action/Outcome/Learning, Epistemic Boundary)
- [../07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md](../07%20Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md) — task that produced this document (historical filename retained — the task predates the Shared Domains rename)
- [../07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md](../07%20Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md) — task that canonicalized Personnel Management and moved Selection under it (superseded for Selection by TASK_DOMAINS_003, `07 Tasks/Reports/TASK_DOMAINS_003_REPORT.md`)

---

## 1. Purpose

This document canonicalizes architectural conclusions reached about how Restaurant relates to a set of **transversal (cross-industry) Domains and Domain candidates**: **Management** (the Shared Domain of People, Organization and Project Manager, whose Organization component holds the Workforce and Personnel Decisions responsibilities formerly documented as modules of **Personnel Management** — see §4), its sibling Shared Domains, and the still-separate transversal Domain candidates Customer Feedback and Review.

TASK_DOMAINS_002 created `01 Domains/Shared Domains/Personnel Management/` and moved the pre-existing `Selection/` Domain under it as a module; Customer Feedback and Review remain candidates only — this document does not create those two. It records the boundaries and distinctions that must hold once Workforce and Personnel Decisions are modeled in depth, and once Customer Feedback/Review are created, so future modeling work is consistent from the start. A later reorganization (§4) re-elevated Selection to top-level and extracted Training (since redefined as Operational Knowledge) and Performance from Personnel Management into their own Shared Domain entries; a further reorganization added Continuous Productivity Development as an independent sibling Shared Domain and redefined Training as Operational Knowledge (see §4). On 2026-10-25 the Product Owner retired Personnel Management as a Domain: its Workforce and Personnel Decisions responsibilities moved to Management / Organization and its Compensation module to Administration (see §4).

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

Where a capability is genuinely cross-industry (evaluating candidates, managing an employment relationship, training people, collecting customer feedback, publishing reviews), Restaurant supplies its own technical content as an input to the transversal Domain that owns that capability — it does not own the capability itself. This is consistent with the existing Selection precedent: Restaurant supplies technical requirements for a Kitchen Manager; Selection evaluates candidates against them (see [Selection/README.md](Shared%20Domains/Selection/README.md), "Relationship to target technical Domains").

---

## 3. Transversal Domain principle

A **transversal Domain** is a Domain whose concepts and reasoning structure do not depend on any specific industry. It applies wherever the underlying business situation recurs, consuming industry-specific content from whichever technical Domain (e.g. Restaurant) the situation currently involves, without duplicating that Domain's knowledge.

Restaurant is currently the first concrete application context for these Domains, not their architectural owner — the same relationship already established for Selection applies to Management and the other Shared Domains, and to the remaining candidates below.

---

### 3.1 Shared person organizational applicability

**Approved Product Owner decision, 2026-11-03:** organizational applicability is
configured exclusively in the shared Employee Directory (Anagrafica), as one
organizational unit, several units, or the entire group. Every Domain, module
and shared service must consume that same source through shared services rather
than define its own applicability or infer it from local workplace data.
Applicability, active employment and access authorization remain distinct.
The canonical contract, examples and consumer checks are defined in
[Person Organizational Applicability](Shared%20Domains/PERSON_ORGANIZATIONAL_APPLICABILITY_001.md).
This is a shared functional rule, not a claim of completed runtime adoption.

## 4. Shared Domains / Business Domain taxonomy, and the current transversal Domains

Every Domain under `01 Domains/` belongs to exactly one of two families, physically expressed as the two folders directly under `01 Domains/`:

- **Shared Domains** (`01 Domains/Shared Domains/`, **formerly named `Cross Domain`** — renamed by a later reorganization; see below) — a Domain whose concepts, ontology and reasoning structure are genuinely industry-independent: it must remain usable by any business/industry, not just the one that happens to be RF-One's first application. A Shared Domain may consume industry-specific content supplied by a Business Domain (as data, configuration or evidence), but must never structurally depend on one specific Business Domain to function or to be defined.
- **Business Domain** (`01 Domains/Business Domain/`) — a Domain whose ontology, integrations, metrics and operational semantics are specific to one industry/business context. A Business Domain may consume Shared Domain capabilities (e.g. Restaurant using Selection to evaluate a candidate, or Management to reason about its people and work), and may supply its own technical content into a Shared Domain's reasoning as an input — but it does not own or redefine the Shared Domain capability itself. **"BD"** is an accepted textual abbreviation for "Business Domain" in RF-One documents (prose shorthand only; the folder stays spelled out as `Business Domain/`).

This is the same **transversal Domain principle** already established in §3, now given an explicit physical home so the distinction is visible in the folder structure, not only in prose. The family itself was originally named **Cross Domain** (TASK_DOMAINS_002 onward) and was renamed **Shared Domains** by a later reorganization, at the same time the **Purchased** Shared Domain was added (see below) — the rename changed no Domain's functional meaning; it only replaced the family label and its folder name (`01 Domains/Cross Domain/` → `01 Domains/Shared Domains/`) everywhere it was live/canonical. Do not confuse this **Shared Domains** family with **`_Shared/`** (§ README.md) — `_Shared/` is not a Domain at all.

```text
01 Domains/
├── Shared Domains/                  (formerly Cross Domain/)
│   ├── Administration               (transversal Domain, with its Compensation, Payroll and
│   │                                 Invoice Intake modules — Compensation moved here from
│   │                                 Personnel Management on 2026-10-25)
│   ├── Continuous Productivity      (top-level, transversal Domain — conceptually superseded
│   │   Development                   Training's original "closes an evidenced gap" scope
│   │                                 before Training was itself redefined below)
│   ├── Intercompany Funding &       (top-level, transversal Domain — financial relationships
│   │   Settlement                    between Legal Entities: prefunding, Payment/Receipt On
│   │                                 Behalf, settlement, netting, allocation, all governed by
│   │                                 a Corporate-configured SettlementPolicy)
│   ├── Management                   (transversal Domain — Product Owner decision, 2026-10-25)
│   │   ├── People                      (component — continuous professional knowledge of the person)
│   │   ├── Organization                (component — design of work, roles, responsibilities,
│   │   │                                authority, coverage and assignments; absorbs the former
│   │   │                                Workforce and Personnel Decisions modules)
│   │   └── Project Manager             (component — planning, execution and verification of
│   │                                    approved assignments)
│   ├── Operational Knowledge        (top-level, transversal Domain — formerly "Training",
│   │                                 extracted from Personnel Management, then redefined as
│   │                                 the shared retrievable-information repository)
│   ├── Performance                  (top-level, transversal Domain — extracted from Personnel
│   │                                 Management; documented; TASK_PERSONNEL_001)
│   ├── Purchased                    (top-level, transversal Domain — added by a later
│   │                                 reorganization; normalizes what a Business Domain
│   │                                 was invoiced for into Purchased Lines; owns the
│   │                                 purchase fact, never its payment/settlement)
│   ├── Selection                    (top-level, transversal Domain — re-elevated by
│   │                                 TASK_DOMAINS_003; was a Personnel Management module,
│   │                                 TASK_DOMAINS_002, before that)
│   └── Taxation                     (transversal Domain)
│
└── Business Domain/
    └── Restaurant              (the current, and so far only, Business Domain)

Customer Feedback            (transversal Domain candidate — not yet created; would be a Shared Domain)
Review                        (transversal Domain candidate — not yet created; would be a Shared Domain)
```

**Management replaces Personnel Management (Product Owner decision, 2026-10-25).** Management is a Shared Domain made of three components: **People** (continuous professional knowledge of the person — capability, experience, evidence, confidential observations, coaching and development, with a link to the Training service), **Organization** (design of work — processes, functions, roles, responsibilities, authority, role coverage and assignments) and **Project Manager** (planning, execution and verification of approved assignments). **Personnel Management is no longer a Domain.** Its Workforce and Personnel Decisions responsibilities were absorbed by Management / Organization, which keeps design and proposals, approved assignments and actual coverage, comparison of alternatives, and decisions reserved to authorized people distinct (see `Shared Domains/Management/Organization/README.md`). Its Compensation module moved to Administration (`Shared Domains/Administration/Compensation/`): Compensation determines and approves what is owed, while Payroll and the external Payroll Provider handle their own processing and result acquisition — the two are sibling Administration modules and must not be merged or duplicated. Management introduces no new register of people, roles, assignments or authority: it preserves and links Restaurant's Employee Assignment and the System Position / occupancy foundation. The training cycle attributed to the Training service is unchanged and not absorbed by People, and Continuous Productivity Development keeps its distinct mandate. Remaining open boundaries are recorded in `Shared Domains/Management/DECISIONS_AND_GAPS.md`. The former Personnel Management documents are preserved unchanged in `90 Archive/Superseded Documents/`.

*History, superseded by the paragraph above where it concerns Personnel Management:* TASK_DOMAINS_002 created Personnel Management as a transversal Domain; Selection, Training and Performance were later extracted from it into their own top-level Shared Domains (TASK_DOMAINS_003 and the Shared Domains / Business Domain reorganization), on the grounds that they are genuinely industry-independent capabilities that should not depend structurally on a parent Domain. Training has since been redefined as **Operational Knowledge**. A further module, Employee Income Composition & Payroll, was added to Personnel Management and renamed **Compensation** by explicit Product Owner decision — RF-One determines, composes and approves compensation but does not itself perform Payroll (see `Shared Domains/Administration/Compensation/README.md`, "Why this module is not called Payroll"). Until 2026-10-25 Personnel Management's modules were Workforce, Personnel Decisions and Compensation; TASK_DOMAINS_002 had already superseded the earlier TASK_DOMAINS_001 framing of Selection, Workforce, Personnel Management, Performance and Training as five separate Domain candidates of equal standing.

**Selection, Operational Knowledge (formerly Training), Performance and Continuous Productivity Development are each a top-level, transversal Shared Domain in their own right — siblings of Management, not components of it.** All of them remain closely related to Management / Organization — in particular to its comparison of alternatives, which consumes Selection's output and draws on Performance evidence — without being owned by it; see §5 below.

**Continuous Productivity Development is a further independent sibling Shared Domain**, added after the above extraction. It identifies gaps/opportunities, estimates their economic value, determines the best intervention, measures outcomes, and learns from results — the role Training's placeholder originally reserved ("closes an evidenced, trainable gap"), generalized well beyond it (see [Continuous Productivity Development/README.md](Shared%20Domains/Continuous%20Productivity%20Development/README.md)). Training's folder was, separately, later redefined as **Operational Knowledge**: the shared repository of retrievable operational information (Operational Knowledge Pills) that Copilot and other RF-One functions may retrieve — it does not identify gaps, decide interventions, or measure outcomes; that remains Continuous Productivity Development's role. The two are independent siblings, not two names for the same thing.

Customer Feedback and Review remain separate transversal Domain candidates (would be Shared Domains if created), outside Management. Neither folder is created by this document. See [Management/README.md](Shared%20Domains/Management/README.md) for Management's components, [Selection/README.md](Shared%20Domains/Selection/README.md), [Operational Knowledge/README.md](Shared%20Domains/Operational%20Knowledge/README.md), [Continuous Productivity Development/README.md](Shared%20Domains/Continuous%20Productivity%20Development/README.md) and [Performance/README.md](Shared%20Domains/Performance/README.md) for these Shared Domains, and the tasks that performed these reorganizations: [../07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md](../07%20Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md), `07 Tasks/Reports/TASK_DOMAINS_003_REPORT.md`, `07 Tasks/Reports/DOMAIN_REORGANIZATION_CROSS_VS_BUSINESS_REPORT.md`, and the Management reorganization of 2026-10-25 (`Shared Domains/Management/DECISIONS_AND_GAPS.md`, D01–D08).

---

## 5. Workforce / Selection / Continuous Productivity Development / Performance / Personnel Decisions distinctions

Two of these five (Workforce, Personnel Decisions) are responsibilities of **Management / Organization** since 2026-10-25 — formerly modules of the retired Personnel Management Domain; the names are kept here because the distinctions remain valid; Selection, Continuous Productivity Development and Performance are each a sibling top-level Shared Domain, described in §4. They are closely related but must not be collapsed into one another: Workforce answers "who," Selection answers "who else is viable," Personnel Decisions answers "what do we do about the person who is there," Performance answers "what actually happened," and Continuous Productivity Development answers "how do we close an evidenced gap or capture an opportunity." (Operational Knowledge, the former Training, is a further sibling Shared Domain but sits outside this particular five-way distinction — see §5.7: it answers a different question, "what retrievable information already exists," not a question about the person or the decision made about them.)

### 5.1 Selection is continuously active

Selection is not vacancy-only.

> Selection continuously creates credible human alternatives for roles, whether or not the role is currently vacant.

Its role is to continuously identify and evaluate economically viable human alternatives for roles. Selection consumes Goals, Brand expectations, role/context requirements, target-Domain technical requirements, Candidate Evidence, trainable gaps, expected performance, uncertainty, and replacement/training/transition economics.

### 5.2 Workforce represents the current human structure

Workforce — today Management / Organization's "approved assignments and actual coverage" — represents the organization's current human structure: who currently occupies or can occupy organizational roles.

> Workforce describes who currently occupies or can occupy organizational roles.

Possible future concepts include Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship. These are not defined here, and Organization introduces no new register for them: it links the existing Restaurant Employee Assignment and System Position semantics (see [Management/Organization/README.md](Shared%20Domains/Management/Organization/README.md) §3, [Restaurant/Roadmap.md](Business%20Domain/Restaurant/Roadmap.md) §3 for the previously approved sequencing note, and [Selection/README.md](Shared%20Domains/Selection/README.md), "Future Workforce dependency").

### 5.3 Personnel Decisions decides what happens to the current person

Personnel Decisions — today Management / Organization's "comparison of alternatives" and "decisions reserved to authorized people" — is distinct from both Selection and Workforce. It applies Core Decision semantics to the person currently performing the role — their observed performance and, when warranted, their replacement.

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

No universal performance score is defined here, and none should be assumed to exist. See also §8, KPI discovery, and [Performance/README.md](Shared%20Domains/Performance/README.md) — the Shared Domain (not a Management component, and formerly not a Personnel Management module either — see §4) documented in depth by TASK_PERSONNEL_001.

### 5.5 Continuous Productivity Development is transversal

Continuous Productivity Development generalizes what the former Training placeholder originally reserved ("closes an evidenced, trainable gap"): it identifies a Gap/Opportunity, estimates its economic value, selects the best available intervention (of which formal training/development is only one candidate among several), measures the outcome, and learns from it. It consumes the observed/assessed gap (see [Selection/TrainableGap.md](Shared%20Domains/Selection/TrainableGap.md) for the currently drawn Selection boundary), role/context, and later Performance evidence. This document does not restate that Domain's model in depth — see [Continuous Productivity Development/README.md](Shared%20Domains/Continuous%20Productivity%20Development/README.md) and its own concept specification.

Restaurant supplies restaurant-specific knowledge and standards this Domain's interventions are evaluated against; Continuous Productivity Development itself is potentially cross-industry, in the same way Selection is.

### 5.6 Relationship summary

```text
Workforce                         → who currently occupies or can occupy roles
Selection                         → continuously identifies credible alternatives for roles
Personnel Decisions                → decides what to do about the current occupant: retain/develop/move/replace
Performance                        → what is actually produced (grounded in Reality/Outcome)
Continuous Productivity Development → closes an evidenced gap/opportunity via the best available intervention
```

Workforce and Personnel Decisions are responsibilities of Management / Organization (formerly Personnel Management modules); Selection, Performance and Continuous Productivity Development are each a sibling top-level Shared Domain (see §4). They must not be collapsed into one another: Workforce answers "who," Selection answers "who else is viable," Personnel Decisions answers "what do we do about the person who is there," Performance answers "what actually happened," and Continuous Productivity Development answers "how do we close an evidenced gap or capture an opportunity."

### 5.7 Operational Knowledge is orthogonal to this distinction

Operational Knowledge (the former Training placeholder, redefined — see §4) is a further sibling top-level Shared Domain, but it does not belong to the five-way personnel-decision distinction above: it answers **"what retrievable operational information already exists that could help here,"** never a question about a person's standing, alternatives, or the decision made about them. It stores and organizes Operational Knowledge Pills — small, contextual, retrievable pieces of operational information — that Copilot or another RF-One function may retrieve before or during an operational activity. It does not identify gaps, decide interventions, or measure outcomes (Continuous Productivity Development's role, §5.5); it does not evaluate a person's capability (Selection's role, §5.1). See [Operational Knowledge/README.md](Shared%20Domains/Operational%20Knowledge/README.md).

---

### 5.8 Management's People and Project Manager components

Management's other two components sit beside the five-way distinction without collapsing into it. **People** answers "what do we professionally know about this person, on which evidence and with which limits" — it supplies evidence-based professional knowledge to Organization's comparison of alternatives without replacing Performance (what was actually produced), Selection (who else is viable) or the decision itself, and it leads the specialist reasoning in its field while Cognito provides perception, language understanding and conversation (`00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md` §9). **Project Manager** answers "how is approved work planned, executed and verified". See [Management/README.md](Shared%20Domains/Management/README.md).

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

1. **Sequencing.** `Restaurant/Roadmap.md` §3 previously recorded that Workforce semantics should be established before Selection/Training/Performance are designed (Training since redefined as Operational Knowledge), yet Selection was created first (TASK_SELECTION_002, explicitly authorized). For Management, the Product Owner's staging is People first, then Organization, ending with Project Manager (`Shared Domains/Management/README.md`). Confirm whether Performance, Continuous Productivity Development or Operational Knowledge should be modeled in depth next, and in what order relative to Management.
2. **Approved assignments vs. comparison/decisions in practice.** Both now live in Management / Organization (formerly Workforce vs. Personnel Decisions) and concern "the person in the role" from different angles (structural occupancy vs. ongoing relationship/performance management). Confirm this internal boundary holds once concrete entities (e.g. Assignment, Employment Relationship) are modeled, and how it maps onto the existing Restaurant Employee Assignment and System Position records (`Shared Domains/Management/DECISIONS_AND_GAPS.md`, G02, G03, G32).
3. **Customer Feedback ↔ Review linkage.** How and whether these two Domains share an underlying evidence/entity model (e.g. a Review as one possible representation of Feedback) is not decided here.
4. **Performance and KPI ownership.** Whether Performance is the (Shared Domain) capability that hosts KPI-discovery logic, or whether KPI discovery reads from Performance among other sources, is not decided here.
5. **Naming.** "Management" and its components People, Organization and Project Manager are the canonical names (Product Owner decision, 2026-10-25), replacing "Personnel Management" (TASK_DOMAINS_002); "Workforce" and "Personnel Decisions" survive only as names of responsibilities within Organization, and Compensation is an Administration module. Selection, Operational Knowledge (formerly Training), Continuous Productivity Development and Performance are each a fixed canonical name too, each a sibling top-level Shared Domain rather than a Personnel Management module (TASK_DOMAINS_003 for Selection; the Cross Domain / Business Domain reorganization (Cross Domain since renamed Shared Domains) for Training and Performance; a later reorganization for Continuous Productivity Development and Operational Knowledge). No final names are fixed for the remaining candidates, Customer Feedback and Review.
6. **Purchased vs. Restaurant/Purchasing.** The new Purchased Shared Domain (§4; `Shared Domains/Purchased/README.md`) and Restaurant's pre-existing, Business-Domain-specific `Purchasing` module (`Business Domain/Restaurant/Purchasing/README.md`) both normalize supplier invoices into purchase-line-level facts. **Partially closed** by "Align legacy Invoice Intake with Purchased": for the `03 Software/InvoiceIntake/` runtime path specifically, Purchased now owns the Purchase Fact (capture + normalize + publish) and Restaurant/Purchasing consumes it — see Purchased's own README, "Relationship to Restaurant's existing Purchasing module — Invoice Intake alignment (closed)." Whether Restaurant/Purchasing's *remaining* scope (Purchase Order, Configured Expectation, Physical Receiving, Reconciliation, Alert, Expected Supplier Credit) should eventually become Restaurant's own consumer/specialization of Purchased more broadly, analogous to Service Copilot's recognized relationship to Ambient Operational Context, remains open; Restaurant/Purchasing's own approved content is otherwise unmodified.
