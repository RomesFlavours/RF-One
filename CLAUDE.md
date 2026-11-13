# CLAUDE.md

# RF-One Project Instructions

## Local preview links — Product Owner, 2026-11-12

Never open previews inside Codex. Provide browser links only. Do not call
`open_in_codex` to display a preview unless the Product Owner explicitly reverses
this preference.

## Local automatic sign-in — Product Owner, 2026-11-09

In the Product Owner's local development/testing environment, open RF-One pages
without asking for username or password. Local launchers must automatically sign
in as the existing local operator `rfone`, preserving that account's actual
permissions. For the local Kitchen/Visual Menu preview, the existing local
administrator may open the preview even when local Domain/item grants have not
been configured; do not persist new grants for this. Keep this behavior limited to a loopback-bound local launcher and
the canonical local database; shared/production authentication is unchanged.
Do not create accounts, grant permissions or store passwords to achieve this.

Verbatim: “Quando sei in locale salta la firma con utente e password.
Scrivitelo dove te lo puoi ricordare. Esegui.”

## Mandatory scope instruction — Product Owner, 2026-11-05

Bank status requests (Product Owner, 2026-11-06): include the outstanding work with three descriptive lines per item, consulting `01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_BACKLOG.md`. Deferred items are not authorization to implement them; first make the current Bank flow work.

Bank handoff (2026-11-06): before recalling or resuming the current Bank work, read `01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_SESSION_2026_11_06.md`. It records the latest WHO pattern/AI decisions, corrected PayPal counts, superseded occurrence-window instructions and unverified work. The Product Owner stopped the rule discussion; do not resume implementation without a task.

Read this instruction before responding to the Product Owner or drafting any command for Claude/C.

The Product Owner determines how to proceed. Answer the specific request and include only the changes explicitly requested in commands for C. Do not add unsolicited features, improvements, refactoring, cleanup, extra deliverables or adjacent tasks. Do not turn a layout request into a broader functional or architectural task. Do not accumulate earlier tasks into a new command unless the Product Owner asks for their integration.

If a requested change necessarily requires work beyond the stated scope, explain that dependency briefly before adding it to the command; do not silently expand the assignment. Suggestions are not authorization. Applicable standing standards still apply within the requested scope, but must not be used to launch unrelated work.

Verbatim order: “Allora smettila anche tu di aggiungere cose che non ti ho chiesto nei comandi. So io come procedere. Questo è un ordine, scrivitelo dove lo devi vedere per forza prima di rispondermi o creare comandi per C.”

This file defines the working rules that must always be followed when contributing to the RF-One repository.

---

# What RF-One Is

RF-One is built around a **domain-independent Core**.

The Core is not a restaurant product and is not itself a commercial application.

It defines generic concepts, their meaning, and their relationships.

Examples may include:

- Subject
- Purpose
- Value
- Belief
- Desire
- Goal
- Resource
- Condition
- Constraint
- Process
- Decision
- Action
- Outcome
- Learning

Application Domains use only the Core concepts they require.

Every Domain lives under one of two families, physically expressed as the two folders directly inside `01 Domains/` (verify against `01 Domains/README.md` and `01 Domains/Domain Architecture.md` §4 before assuming this list is complete — those files are authoritative, this is a pointer to them):

- **Shared Domains** (`01 Domains/Shared Domains/`, formerly named **Cross Domain**) — industry-independent, reusable by any business: Management, Selection, Operational Knowledge, Continuous Productivity Development, Performance, Taxation, Administration, Purchased, Intercompany Funding & Settlement.
- **Business Domain** (`01 Domains/Business Domain/`) — industry-specific: Restaurant (currently the only one).

A Shared Domain may consume industry-specific content a Business Domain supplies, but must never structurally depend on one specific Business Domain. `_Shared/` holds domain-independent-but-not-universal knowledge reused across multiple Domains (e.g. `_Shared/Environment/`) — it is not itself a Domain, and lives outside both families, directly under `01 Domains/`. **Do not confuse `_Shared/` (not a Domain; not-yet-universal environment/context knowledge) with the `Shared Domains/` family (Domains that are Domains, just reusable by any Business Domain).**

**Purchased** (`01 Domains/Shared Domains/Purchased/`) is a Shared Domain consumed by Business Domains: it turns what the business was invoiced for into normalized purchased facts (one line per economic item/service/charge on a source document), owning only the purchase fact — never whether it was paid (Bank Reconciliation boundary, owned by the consuming Business Domain). See `01 Domains/Shared Domains/Purchased/README.md`. It does not redefine or merge with Restaurant's existing, Business-Domain-specific `Purchasing` module (see below) — their relationship is an explicitly open question, not decided by Purchased's own definition.

**Management** (`01 Domains/Shared Domains/Management/`) is a Shared Domain made of three components (Product Owner decision, 2026-10-25): **People** (continuous professional knowledge of the person — capability, experience, evidence, confidential observations, coaching and development; link to the Training service), **Organization** (design of work — processes, functions, roles, responsibilities, authority, role coverage and assignments; it absorbed the former Workforce and Personnel Decisions modules) and **Project Manager** (planning, execution and verification of approved assignments). **Personnel Management is no longer a Domain** — do not recreate it; its documents are archived in `90 Archive/Superseded Documents/`. Management introduces no new register of people, roles, assignments or authority: it links Restaurant's Employee Assignment and the `10 System/` Position foundation. **Cognito** provides sensory functions, language understanding and conversation management; People (and Selection in its field) leads the specialist reasoning and decides what to explore — do not re-attribute that reasoning to Cognito (`00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md` §9). Open boundaries: `01 Domains/Shared Domains/Management/DECISIONS_AND_GAPS.md`.

**Selection, Operational Knowledge, Continuous Productivity Development and Performance are each their own top-level Shared Domain** (`01 Domains/Shared Domains/Selection/`, `.../Operational Knowledge/`, `.../Continuous Productivity Development/`, `.../Performance/` — TASK_DOMAINS_003 for Selection; the Cross Domain/Business Domain reorganization (Cross Domain since renamed Shared Domains) for the former Training (now Operational Knowledge) and Performance; a later reorganization for Continuous Productivity Development), not components of Management or modules of Restaurant — usable by any industry, closely related to but not owned by Management / Organization (which holds the former Personnel Decisions responsibility). Do not nest any of them under either. The training cycle stays with the Training service (`01 Domains/Shared Domains/TRAINING_SERVICE_001.md`) and is not absorbed by People. **Operational Knowledge is the shared repository of retrievable operational information (Operational Knowledge Pills) that Copilot and other RF-One functions may retrieve — it does not train, test, assess, or certify.** It is independent of, and must not be confused with, Continuous Productivity Development, which identifies gaps/opportunities, decides interventions (of which actual human training is only one candidate), measures outcomes, and learns from results. Restaurant's Industry Extension of Selection (role catalog, client/role configurations) lives at `01 Domains/Business Domain/Restaurant/Selection/`, depending on Selection Core, never the reverse.

Several familiar business-capability names are **modules of an existing Domain**, not Domains in their own right. Do not create a new top-level `01 Domains/<name>/` folder for any of these — extend the owning Domain instead:

- Purchasing and Sales are modules of the Restaurant Domain (`Restaurant Domain └── Purchasing module`, `Restaurant Domain └── Sales module`, canonically `01 Domains/Business Domain/Restaurant/Purchasing/` and `01 Domains/Business Domain/Restaurant/Sales/`). Restaurant's Purchasing module is not the same thing as the Purchased Shared Domain above; see that Domain's README for the currently-open question about their relationship.
- People, Organization and Project Manager are components of the Management Domain (`01 Domains/Shared Domains/Management/<component>/`). **Workforce** and **Personnel Decisions** (not "Personal Decision") are no longer modules or folders: they are responsibilities inside Management / Organization. **Operational Knowledge, Continuous Productivity Development and Performance are NOT components of Management** — all three are independent top-level Shared Domains (see above); do not nest them under Management.
- Compensation and Payroll are distinct sibling modules of the Administration Domain (`01 Domains/Shared Domains/Administration/Compensation/` and `.../Payroll/`): Compensation determines and approves what is owed (including Compensation Terms); Payroll and the external Payroll Provider handle processing and result acquisition. Do not merge or duplicate them.

**"BD" is an accepted textual abbreviation for "Business Domain"** in RF-One documents (never a folder/path rename — `Business Domain/` stays spelled out on disk).

Commercial Products may combine one or more Domains.

---

# Fundamental Architectural Rule

Always distinguish between:

## 1. Core

The Core defines **what concepts mean and how they may relate**.

A concept existing in the Core does NOT imply:

- that every Domain must use it;
- that every implementation must collect data for it;
- that it must always be instantiated;
- that RF-One must be able to measure it;
- that every Product must expose it.

The Core is definition, not implementation.

## 2. Domain

A Domain applies and, where necessary, specializes Core concepts for a specific field.

Domains should remain conceptually modular and reusable.

## 3. Product

A Product is a commercial application built using one or more Domains.

Products are designed to create measurable value for their users.

## 4. Runtime

Runtime is where actual data, inference, execution, recommendations and actions occur.

Do not reject a Core concept because runtime data may not currently exist for it.

**Core definition and data availability are separate questions.**

---

# Product Philosophy

RF-One does not begin from available data or existing software features.

The general direction is:

**understand the subject and its objectives first, then determine what knowledge, processes, decisions, actions and data are required.**

Do not narrow the Core to fit the first Product or Domain.

Restaurant is currently an important application and testing environment, but it must not unnecessarily constrain the Core.

---

# Language

Always communicate with the Product Owner in **Italian**, unless explicitly requested otherwise.

Use **English** for:

- source code;
- variable and function names;
- database objects;
- API definitions;
- GitHub documentation;
- repository documentation;
- technical documentation intended for developers.

---

# Repository Structure

Respect the repository structure.

Do not rename, move or reorganize folders without explicit approval.

Do not create parallel definitions when an existing concept should be updated.

Before making structural changes, inspect all references that may be affected.

The canonical top-level structure (established by TASK_CORE_005) is:

```text
00 Core/                    highest authority — universal ontology
01 Domains/                 canonical per-Domain business knowledge
02 Products/                canonical Product-level configuration
03 Software/                runtime behavior, not concept meaning
04 Generated Documentation/ derived material, never a source of truth
05 Research/                not canonical
06 Meetings/                not canonical
07 Tasks/                   task specs, reports, backlog — historical record
08 External/                external/reference material only, not RF-One authority
09 Strategy/                canonical for RF-One's own company/product strategy
10 System/                  system-level capabilities spanning the whole platform (not a Domain, not a Product)
90 Archive/                 never current authority, regardless of status text inside
```

Each top-level directory carries its own `README.md` stating purpose, authority level, and what does/does not belong there — consult it before assuming where new material belongs.

---

# Documentation First

Documentation comes before implementation.

Default workflow:

1. Concept / README
2. Functional Specification
3. User Stories when applicable
4. Data Requirements
5. Business Rules
6. Development
7. Testing
8. Consistency Review

Do not start coding when the required functional or architectural definition has not been approved.

---

# Approved Architectural Decisions

When an architectural or conceptual specification has been explicitly approved:

- implement it faithfully;
- identify contradictions with existing repository content;
- identify affected dependencies;
- update dependent documentation consistently;
- report unresolved conflicts.

Do **not** replace an approved abstraction with a different model simply because another theory or implementation would also be possible.

External theories, frameworks or industry models may be suggested as references, but must not become architectural constraints unless explicitly approved.

---

# Challenge Rules

Challenge:

- contradictions;
- logical inconsistencies;
- duplicate concepts;
- unclear relationships;
- hidden dependencies;
- implementation risks;
- security or compliance risks;
- assumptions that materially affect correctness.

Do not challenge an abstraction merely because:

- it is broad;
- it is difficult to measure;
- current data does not exist;
- a current Product does not need it;
- another theoretical model exists.

When raising an objection, always identify:

1. the exact contradiction or risk;
2. the affected files or concepts;
3. why it matters;
4. the smallest reasonable correction.

Do not turn implementation work into an unrelated theoretical debate.

---

# Role of Claude

Act as a **Repository Architect, Implementation Engineer and Consistency Reviewer**.

Your responsibilities are to:

- inspect the repository;
- implement approved specifications;
- maintain conceptual consistency;
- find affected references;
- update documentation and code;
- identify genuine unresolved architectural questions;
- test implementations;
- report what changed.

Conceptual architecture is established through approved specifications.

If a specification is clear, implement it.

If a genuine ambiguity prevents correct implementation, ask the Product Owner.

Do not redesign approved concepts unless explicitly asked to do so.

---

# Modular Architecture

Domains should be modular and reusable.

Avoid unnecessary coupling.

However, do not create artificial separation when two Domains naturally share Core knowledge.

Products may combine multiple Domains when their combined value is greater than their standalone value.

---

# External Technology

RF-One may use external APIs and commercial services for commodity capabilities.

Examples include:

- LLMs;
- speech-to-text;
- text-to-speech;
- translation;
- avatars;
- video;
- OCR;
- scheduling;
- messaging;
- external datasets.

Do not rebuild commodity technology unless there is a clear strategic reason.

Keep RF-One's proprietary value in its:

- model;
- logic;
- knowledge;
- orchestration;
- decision processes;
- learning mechanisms.

Where practical, keep provider-specific integrations behind abstractions so providers can be replaced.

---

# Simplicity

Prefer simple, understandable and maintainable solutions.

Avoid:

- unnecessary complexity;
- premature optimization;
- speculative abstractions without conceptual value;
- technology introduced only because it is fashionable.

Complexity is acceptable when the underlying concept genuinely requires it.

---

# Coding Standards

Write clean, readable and maintainable code.

Use consistent naming.

Document non-obvious decisions.

Prefer clarity over cleverness.

Do not silently change the meaning of an existing approved concept.

---

# Before Editing

For significant architectural tasks:

1. Read the supplied task/specification.
2. Inspect all relevant repository references.
3. Identify the files that will probably change.
4. Identify contradictions or blockers.
5. Implement unless a genuine unresolved ambiguity prevents doing so.

---

# After Editing

Provide a concise implementation report containing:

- files created;
- files modified;
- concepts implemented;
- references updated;
- tests or consistency checks performed;
- How Works Help updated with the change, or why the change is technical only;
- unresolved issues;
- questions requiring Product Owner decisions.

Never hide unresolved contradictions.

---

# Outcome-first, single-flow development — mandatory

**Standing instruction (UI_OUTCOME_SINGLE_FLOW_001, Product Owner, 2026-11-04).** Design first for the outcome the person wants and one clear primary workflow to reach it; then implement the software. The system performs work it can reliably do and asks only necessary information/decisions at the relevant step. Do not expose internal modules, irrelevant filters, shortcuts into unrelated stages or competing row actions as user workflows. Contextual subtasks stay inside the current journey and preserve drafts, group, selection, position and focus. Technical correctness alone does not establish usability.

Read and apply `03 Software/Shared UI/Outcome and Single-Flow Design Standard.md` for every interface/function task. Before completion, compare the actual result with all applicable written project/Domain/UI/How Works/language/safety rules, correct deviations within the authorized scope, and rerun affected checks. Do not weaken rules or tests to claim compliance. Report only concrete remaining conflicts or limitations. Include contextual help and the local-Italian/shared-English policy.

This is already an approved development instruction. Formal insertion of the universal principle into the Core remains a separate proposal for discussion with Shelbi; do not silently amend the approved Core. This rule does not authorize data changes, publishing, pushes or deployment.

---

# RF-One UI Rules

**Standing Product Owner browser preference (2026-10-26): always open user-facing pages and local trials in Microsoft Edge. Never present them in Codex's internal browser or an assistant-owned browser window. Reuse Edge where possible.**

**Standing instruction, applied automatically to every RF-One interface
task.** Full text and implementation pointers:
`03 Software/Shared UI/UI Rules.md`. In short:

1. Times shown to a person are the Location's local time (its
   `Location.timezone`), never UTC. UTC stays internal.
2. Employees in operational displays are "Surname I." ("Ceban T."), never
   a technical id, unless the full name is genuinely needed.
3. Frequent actions are available where they are needed, calling the one
   central implementation — never a copy — so the person does not have to
   open a sub-page just to perform them.
4. Every sub-page shows its clickable hierarchical path (breadcrumb)
   instead of a generic "Home" link; the path reflects the real structure
   and never invents levels.
5. After an action started from a list row (Edit, Save, Cancel, Confirm…)
   the person is back on that same record, at the same place on screen,
   with focus on the button used — never at the top of the list, also
   after a reload (`rf-one-row-return.js`, rows marked `data-rr-key`).
6. Every modal window has a close X at its top right, visible while the
   window scrolls, calling the window's own Cancel/close.

Every future UI refinement reuses these rules.

---

# RF-One How Works Standard

**Standing Product Owner instruction (2026-11-02), mandatory for every
Domain and Module (UI_HOW_WORKS_001).** The one normative text is
`03 Software/Shared UI/How Works Standard.md`; this is a pointer to it.

1. Every page shows a visible contextual help link that opens a **modal**
   with the help of *that* page (on a Home: of the system or module) — see
   *Contextual help on every page* below (UI_CONTEXTUAL_HELP_001).
2. The Help describes the behaviour actually implemented in the published
   version and how to use it. It never describes planned features.
3. **Code and Help are one release unit.** A functional change without its
   Help update is incomplete and is not released. A technical-only commit
   says so on its own line: `How-Works: technical - <reason>`.
4. Every new page is registered, with its Help target, in
   `03 Software/Shared UI/how_works_registry.json`. Its `help_missing`
   list only shrinks: a new page never enters it.
5. Before a release: `python "03 Software/Shared UI/check_how_works.py"
   --app <App> --rev <commit> --since <live commit>`. Any error is a
   release error (`release_selection.py` runs it itself). Checklist:
   `03 Software/Infrastructure/deploy/RELEASE_CHECKLIST.md`.

MIEAF — every function explains how it works, in the same release in which
it is published.

---

# Contextual help on every page (UI_CONTEXTUAL_HELP_001)

**Standing Product Owner instruction (2026-11-05), for every RF-One page,
app and agent.** Normative text: `03 Software/Shared UI/How Works Standard.md`
§1 and §6; this is a pointer to it. Verbatim:

> Prima di ogni attività leggere le istruzioni principali del repository.
> Ogni pagina RF-One deve avere un aiuto contestuale accessibile tramite un
> link coerente che apre una modale. Le home spiegano il sistema o modulo;
> le altre pagine spiegano la pagina specifica. Ogni creazione o modifica di
> pagina deve includere la verifica e l'eventuale aggiornamento del relativo
> aiuto. L'attività non è completa se interfaccia e spiegazione non
> corrispondono.

In short:

1. Before any task, read the repository's main instructions (this file;
   `AGENTS.md` points here).
2. One consistent link per page, opening a **modal** (reference: the
   "How Selection works" link). General Home: **How RF-One works** — RF-One
   and its navigation. Home of a Domain/Module: **How <Module> works** —
   purpose, how it works, operating flow. Every other page (lists, details,
   forms, settings, administration, services): **How this page works** — what
   the page is for, what the person can do, fields and buttons, consequences
   of the actions, next steps. A module explanation never replaces a page's
   own explanation.
3. The help describes only what is really available, in clear English
   without unnecessary technical detail, and is visible exactly to whoever
   may see the page (role-restricted parts carry the page's own condition).
4. One component for every app: `03 Software/Shared UI/help/_how_works.html`
   (byte-identical copy `templates/_how_works.html` in each app). A page
   declares `{% set help_section = "<section>" %}` (and `help_title` on a
   Home); its content is `templates/help/<section>.html`; it is registered in
   `how_works_registry.json` and checked by `check_how_works.py`. Keyboard
   and mobile use are part of the component.
5. Every creation or change of a page includes checking and, where needed,
   updating its help. The task is not complete while interface and
   explanation do not match.

---

# Local Database Policy

**Standing Product Owner instruction (2026-10-26): one local RF-One database.**

- Maintain one canonical local working database for RF-One. Modules and worktrees must reuse it; do not create permanent parallel databases or dated working copies.
- Keep the local database aligned with AWS when needed and compatible with the work being performed. Data alignment is strictly one-way: **AWS to local**. Never synchronize local data back to AWS. This policy does not authorize AWS writes.
- Create a separate disposable database only when a test requires isolation. Delete that test database after the test finishes; do not leave completed test environments or staging databases behind.
- Before creating a database, locate and reuse the canonical local database. Temporary staging for a safe refresh must be removed after successful verification. A rollback database must not become another permanent working database; retain recovery as a clearly identified backup file instead.
- Keep backup files distinct from working databases, with clear purpose and restore references. Do not silently accumulate backups or treat them as additional environments; agree retention when consolidating existing copies.
- Existing local databases and legacy copies require an inventory and a controlled consolidation into the single canonical database. This instruction records the target policy; it does not by itself authorize indiscriminate deletion of existing databases or backups.

This policy supersedes earlier instructions that would require separate permanent local databases for individual modules. Existing launcher and data-safety rules still apply until consolidation is implemented; report conflicts instead of creating further copies.

---

# Bank Local Environment

**Final Bank page logic (Product Owner, 2026-11-05):** Read `01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_WHO_WHY_FINAL_LOGIC_001.md` before Bank work. WHO page: the different WHO recognition methods. WHY page: unambiguous WHO-to-WHY associations, conditional rules for ambiguous cases (including Amazon and employee Zelle payments), and the fixed WHY-to-WHAT mappings at the bottom. This is the final approved functional direction, not a claim of implementation; preserve explicitly approved conventional WHO identities.

**Standing Product Owner instruction (2026-10-17): purpose first when populating Bank WHY.**
Read the complete bank description, direction, dates, source and related evidence.
Record the recognizable general purpose even when its detailed composition is unknown.
Example: `ADP Tax` identifies a payroll-tax payment; it must not remain without WHY
merely because employer taxes and employee withholdings are not separated.
`IND NAME: RF GELATI LLC` identifies the named beneficiary context independently.
Use an appropriate general WHY, without forcing a detailed WHAT or an unsupported
employer-only expense. The current Bank service permits WHY without WHAT.
Distinguish direct textual evidence from contextual deductions in decision notes;
leave open only purposes that are actually unclear, not merely less detailed.

**User-provided general monthly reconciliation rules (2026-10-17).**
Retain these for the future user-facing page of general rules provided by the user.
They are user policy, not universal accounting/tax law. Recording them here does
not itself change transactions, WHO defaults, or executable AI Rules.

1. **Restaurant meals:** a restaurant payment on a company card is a business
   meal; a restaurant payment on a personal card is a personal expense. Use the
   configured card ownership, not a guessed interpretation of the card name.
2. **Travel:** recognize a trip from related transaction evidence and ask about
   the trip as a whole, rather than repeatedly asking about its individual rows.
   Example modal: "Vedo un viaggio a Cozumel. Personale o business?" Exactly two
   choices: "Personale" and "Business". After selection, close the modal and
   populate the associated classifications. Destination is an example, not a
   hardcoded trigger. Do not infer vacation versus work from destination alone.
   The user also specified: "se la carta è personale è personale altrimenti business".
   Preserve this card-based instruction alongside the trip-level question.
   **Open precedence question:** when the explicit trip answer and card ownership
   disagree, which governs classification? The user has not yet resolved this;
   do not silently override the answer or silently invent an exception.
3. **Research each WHO before deducing WHY:** look up the counterparty on the
   web, prefer its official website, verify the identity against location and
   transaction context, and retain the URL, lookup date and relevant evidence.
   Do not classify a supplier payment merely as Accounts Payable Settlement
   when the operational purpose is identifiable. Web research informs the
   deduction; it does not prove the precise contents of every purchase or
   justify attaching a namesake's activity to a private individual.
   **Explicit user correction:** PRIME LINE DISTR = FOOD_PURCHASES (2026-10-17).
   Official evidence: https://www.primelinedist.com/about (food importer and
   distributor serving restaurants); https://www.primelinedist.com/contact
   (Orlando division). Preserve this approved WHO/WHY knowledge for reuse.
4. **Clarifications must be conversational (2026-10-17):** do not ask the user
   to fill a WHY selection form. Let the user explain in chat; ask follow-up
   questions where needed; restate the complete reusable rule and obtain its
   explicit confirmation. Only then show an actual preview over the entire
   database, all periods and Sources, including already-classified movements.
   Show before/after values, unchanged/protected/conflicting/unclear cases and
   any excluded accounting duplicates. Do not apply classifications merely
   because the user confirmed the interpretation or requested its preview.

The local Bank working environment (both PCs) is run ONLY through
`03 Software/Infrastructure/Bank Local Environment/` (Configura PC, Avvia
Bank, Chiudi Bank / Cambia PC) — never by an ad-hoc launcher or by opening
a database inside OneDrive. Until it is merged, it lives in the worktree
`AI-RF-ONE/rf-one-bank-simple-who-rules` (branch
`feature/bank-simple-who-rules`). When the Product Owner asks to **interpret
the AI Rules waiting** («Interpreta le AI Rules in attesa»), follow
`SESSION_INTERPRETATION.md` in that folder.

---

# RF-One Report Standard

**Standing instruction, applied automatically to every RF-One task.** It is
never to be re-requested from the Product Owner and never needs repeating
inside an individual command. It governs every Domain, Module, deploy,
test, import, migration, UAT and any other RF-One work.

Every RF-One task ends with a final **REPORT**. The REPORT must:

- carry the title **REPORT**, clearly visible;
- be organized in numbered sections;
- use plain, human, understandable language;
- use compact tables wherever they make a comparison easier;
- clearly distinguish **observed facts** from **interpretations** and from
  **solutions adopted or proposed**;
- state what was changed and, where relevant, what was deliberately **not**
  changed;
- surface problems, missing capabilities, and any decisions the Product
  Owner still has to make;
- include the success criteria and the outcome of each;
- end with the references needed for traceability, backup or restore.

After the REPORT, always emit the RF-One completion **beep**. The beep is
the absolute last action of the work — **no text may appear after it.**

---

# RF-One Blocked Alert

**Standing instruction, valid for every session.** Whenever work stops
because of an error, a permission block, a required confirmation, or any
other obstacle Claude cannot resolve on its own:

1. Immediately emit **3 beeps** (PowerShell):

   ```powershell
   [console]::beep(1000,300); Start-Sleep -Milliseconds 200; [console]::beep(1000,300); Start-Sleep -Milliseconds 200; [console]::beep(1000,400)
   ```

2. Write **BLOCCATO**, the precise reason, and the minimum action needed
   to resume.
3. Never sit waiting without alerting the Product Owner.

This alert is distinct from the Report Standard's single completion beep:
here the text in step 2 deliberately follows the beeps.

If the block concerns login, network or the extension itself and prevents
the session from running commands at all, the beeps cannot be emitted:
state that limit and propose an external check — never claim the
notification is guaranteed.

---

# RF-One Problem-Solving Rule (MIEAF)

**Standing Product Owner instruction (2026-10-23), applied to all RF-One
development.** The task is not only to find problems but to solve them.
**MIEAF: the technical complexity is Claude's to manage, never transferred
to the user.**

When an obstacle appears:

1. Analyze its cause autonomously.
2. Find the simplest, cheapest solution compatible with approved decisions.
3. Verify it technically as far as possible.
4. If it is within the authorizations already given, implement it and continue.
5. If it needs new authorization, spending, a production change, or carries
   significant risk: propose one concrete solution and ask **only** for the
   indispensable approval.

Never change approved architectural decisions without a documented reason.
Never present a list of problems without first having looked for their
solutions. Never ask the Product Owner to choose between technical
alternatives Claude can evaluate itself — choose, and state why. Never run
operations blocked by security controls and never try to bypass them.

Reports state, for each obstacle: **problem found → solution identified →
action taken, or the strictly necessary authorization.** This complements
the Report Standard and the Blocked Alert above (a Blocked Alert is only for
what genuinely needs the Product Owner, after this rule has been applied).

---

# Final Principles

When working on the **Core**, ask first:

**"Is this concept correctly defined at the level of abstraction where it belongs?"**

Then:

**"Is it consistent with the rest of the Core and reusable across Domains?"**

When working on a **Domain**, ask:

**"Does this Domain correctly apply the Core without contaminating it with domain-specific assumptions?"**

When working on a **Product**, ask:

**"Does this create meaningful value for the intended user?"**

And always remember:

**Core ≠ Domain ≠ Product ≠ Runtime.**

## Bank AI provider preference (updated 2026-10-23)
Bank conversation AI uses ChatGPT/OpenAI; never silently fall back to another provider.
For reconciliation (the unified engine, `reconcile_engine.py`), the Product Owner decided on 2026-10-23 to use
**both** ChatGPT and Claude as directors: their results are integrated after a non-overlap check — when one
names a WHO (or WHY) and the other a different one, the case is flagged to a person, never decided silently.

## Bank rule learning lifecycle (2026-10-17)
Parliamone is the queue for unresolved transactions. Once a conversational rule is explicitly confirmed, persist it in the Bank rule catalogue and display it under rules. Preserve its identity and versions. Keep or return ambiguous/conflicting exceptions to Parliamone with the existing rule as context, refine in chat, then confirm the revised rule. Never equate rule confirmation or preview with applying transaction classifications.

# Local development and publication language

**Standing instruction (UI_DEVELOPMENT_LANGUAGE_001, Product Owner, 2026-11-03).**
All UI shown during the Product Owner’s local development/testing is Italian, including secondary pages, dialogs, client-side messages and How Works. Before any explicitly requested Git push/publication or AWS deployment, prepare and verify the shared/release interface in English while preserving the Italian local working copy. Prefer locale selection (shared/production default English, official local launcher Italian), or use an isolated release checkout. Never leave the PO’s working copy in English after a release. Do not translate stored facts, names, identifiers, API/status values or export schemas. This instruction does not itself authorize publication. Full policy: `03 Software/Shared UI/Development Language Policy.md`.

# Contextual How Works for pages and modals

**Standing instruction (UI_HOW_WORKS_MODAL_001, Product Owner, 2026-11-03).** Every Bank page has page-specific How Works (opened as a modal, UI_CONTEXTUAL_HELP_001); every modal has a visible `?` opening the exact anchored explanation of that modal in the Domain guide, preserving its state and draft. Local Italian and shared/release English follow UI_DEVELOPMENT_LANGUAGE_001. Normative text: `03 Software/Shared UI/How Works Standard.md`, section 1.1. Bank rule-scope/category decisions: `01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_RULE_SCOPE_AND_WHO_CATEGORY_001.md`. These documented requirements do not certify implementation.
