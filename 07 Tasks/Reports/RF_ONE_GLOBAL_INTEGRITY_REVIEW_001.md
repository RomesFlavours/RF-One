# RF-One Global Integrity Review 001

**Type:** Read-only diagnostic audit (no files modified, no runtime/DB writes)
**Date:** 2026-09-05
**Method:** Direct inspection of canonical documentation (`00 Core/`, `01 Domains/`, `02 Products/`, `03 Software/`, `09 Strategy/`, both `CLAUDE.md` files) plus six parallel read-only deep-dive passes over: (1) cross-domain dependencies and taxonomy compliance, (2) Selection's data model (`models.py`, `selection/core/`), (3) Selection's service layer (`selection/*.py`), (4) Selection's Flask UI and industry-extension seam, (5) the non-Selection data model and all 36 Alembic migrations, (6) security/tenancy/test-quality/dead-code across all of `03 Software/`. Every finding below is anchored to a concrete file:line citation gathered during this review; none is speculative.

---

## 1. Executive Summary

RF-One's Core/Domain/Product/Software layering, its recently-canonicalized Cross Domain vs. Business Domain taxonomy, and the actual `01 Domains/` folder structure are **fully compliant** with each other — no stray folders, no reversed dependencies, and the Selection ↔ Restaurant industry-extension seam (`selection/industry/restaurant.py`) is respected in every file checked: Selection Core never imports Restaurant specifics, and the one direction of coupling that exists (`analysis.py`, `normalization.py`, `signal_service.py` importing the concrete `industry.restaurant` module) is explicitly self-documented as intentional single-client debt, not a hidden violation. Purchasing, Payroll, Sales and Tips all correctly key actor fields to `employees.id` foreign keys, the migration chain is a single clean linear history with no branching heads, and the four "business-side" runtime subpackages (`payroll/`, `purchasing/`, `profile/`, `tips/`) are cleanly decoupled from each other and from Selection.

Set against that solid foundation, the audit found a materially weaker layer specifically where **Selection's runtime (not its Domain documentation) meets Identity/Authority/Accountability** — the architecture this repository canonicalized in its immediately preceding task. Ownership/authority checks and audit-trail "who did this" fields throughout Selection are unverified free text, not a stable Acting Identity; a legacy `Application.outcome` field can be silently overwritten with zero actor, reason or audit record while a parallel governed decision system exists for the same concept; near-identical mutation routes enforce authority inconsistently depending on which button was clicked; and there is no tenant/company scoping primitive anywhere in the schema, with two incompatible "location" hierarchies already coexisting. None of this is hidden — much of it is candidly documented in code comments as known, temporary, single-client-deployment debt — but several items cross from "acceptable pre-industrialization gap" into "actively dangerous to build more on top of," detailed in Section 3.

## 2. Overall Architecture Health

**Strong areas:**
- Core/Domain/Product/Software separation is respected everywhere checked; no Domain redefines Core semantics.
- Cross Domain / Business Domain taxonomy: 100% compliant folder structure; Selection's industry-extension dependency direction is correct in every file reviewed.
- Purchasing/Payroll/Sales/Tips actor identity: 100% FK-based (`*_employee_id`), zero free-text actor fields found outside Selection.
- Migration chain: single linear history, 36 files, one root, one head, no branches, no unsafe destructive operations.
- Historical Integrity is genuinely implemented (not just documented) for `PayrollRun` (SUPERSEDED chaining), `ConfiguredExpectation`/`EmployeeAssignment`/`TipPolicy`/`WorkweekDefinition` (close-old/open-new temporal rows), and most of Selection's append-only decision/stage tables.
- Provider adapter boundaries (Clover client, Clover ingestion mapping layer, InvoiceIntake OCR) are clean — no vendor-specific leakage into business logic found anywhere.
- Cross-subpackage discipline inside `rfone_data_store`: zero unauthorized imports found between `payroll/`, `purchasing/`, `profile/`, `tips/`, and `selection/`.

**Weak areas:**
- Identity/Authority/Accountability is aspirational in canonical docs but not yet load-bearing in Selection's runtime — see Section 3 (C-1, C-2) and Section 11.
- No tenant/company scoping primitive exists anywhere in the schema; two incompatible "location" hierarchies already coexist (Section 3, C-3; Section 12).
- Test/validation execution safety is inconsistent — some suites self-isolate correctly, others default to the shared database file (Section 3, C-4; Section 15).
- A meaningful amount of genuinely generic platform capability (messaging, scheduling, template versioning, inbound classification) is built once, well, but entirely inside one Domain (Section 9).

**Industrialization readiness:** the architecture is a sound foundation to industrialize *on top of*, provided the four CRITICAL items are addressed first — none require a redesign, but all four are the kind of gap that becomes exponentially more expensive to fix once real customer data and real users depend on the current behavior.

---

## 3. CRITICAL Findings

### C-1: No stable Acting Identity — Authority, Ownership and Audit records in Selection are spoofable free text

**Finding:** Selection's entire notion of "who did this" — including a feature that functions as a real authorization gate — is built on unverified, uniqueness-unenforced string columns, not a foreign key to any identity table. `models.py` defines no `User`/`Account`/`Identity` table anywhere; the only person-identity table usable for this is `Employee` (POS-sourced HR data, not an app login).

**Evidence:**
- `03 Software/RF-One Data Store/rfone_data_store/selection/ownership_service.py:40-70` — `take_in_charge(session, application_id, *, owner_name: str)` is called from `03 Software/Selection/app.py:907` as `request.form.get("owner_name")` with no identity check whatsoever.
- `ownership_service.py:96-101` `_authority_order()` and `:182-189` `can_write()` compare `actor_name == current.owner_name` — a same-string-equality check between two independently free-typed HTTP form fields. Any client can claim any name and thereby "take in charge" an Application or successfully pass an authority comparison to reassign it.
- `models.py:4905-4909` `ApplicationStageTransition.performed_by`, `:5070` `SelectionOutcomeDecision.performed_by`, `:6010-6029` `SelectionSessionAssignment.selezionatore_name` (the join-key for a `UniqueConstraint`), `:4970-4979` `authority_label` — all free-text `String` columns, each with a comment acknowledging "no authentication/RBAC system exists in Selection."
- `03 Software/Selection/app.py` surfaces ≥10 differently-named free-text actor fields across its ~183 routes (`actor`, `performed_by`, `created_by`, `approved_by`, `confirmed_by`, `acknowledged_by`, `corrected_by`, `reported_by`, `owner_name`, `new_owner`, `selezionatore_name`), several of which (`app.py:2720-2733`, `:3544-3557`) silently accept a blank/`None` value.
- `templates/audit.html:148,159` renders `{{ d.performed_by or '-' }}` — the audit view itself tolerates and displays blank actors.
- **Contrast, proving the fix is cheap and already precedented in this codebase**: `models.py:2655` `ConfiguredExpectation.approved_by_employee_id` and `:2840` `PurchasingAlert.decided_by_employee_id` are proper FKs to `employees.id`, in the same file, ~2,000 lines earlier.

**Impact:** Records that look like a legitimate accountability trail (`"Reassigned from X to Y by Z"`, an approved Rule Change, a confirmed Rule Set version) are unverifiable and fabricable by anyone with HTTP access. This directly contradicts `00 Core/RF-ONE Core Principles.md` Principle 21 ("Every meaningful Decision and Action must be attributable to an identifiable Acting Identity") and Selection's own documented safeguard (`01 Domains/Cross Domain/Selection/README.md:171`: "the authority behind a Selection Decision must be known"). It is worse than an honest absence of authorization, because it produces evidence that *looks* trustworthy to a future auditor or compliance reviewer.

**Recommendation direction:** Introduce one shared Acting Identity concept (per `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md`) and migrate every free-text actor field to reference it, starting with `ownership_service.py`'s authority comparison (the only place free text is actively load-bearing for an authorization decision, not just descriptive).

**When it must be fixed:** Before any real (non-single-operator) usage of Selection, and certainly before this becomes a compliance-relevant system of record for a second customer. Can technically wait until an Authentication/Authorization mechanism exists at all (per `03 Software/Identity Authority and Security Architecture.md`), but the ownership/authority *comparison* logic (not just field-naming) should not be extended further in the meantime.

---

### C-2: Split-brain Outcome/Workflow-Status mutation — an ungoverned legacy path bypasses authority checks, audit trail, and is still read by the AI evaluator

**Finding:** Two structurally independent code paths mutate what a user experiences as "an Application's outcome," through different data models, with different (and in one case absent) governance.

**Evidence:**
- **Ungoverned path**: `03 Software/Selection/app.py:1172-1179` route `POST /applications/<id>/outcome` → `application_service.py:178-186` `set_outcome()`, which does `application.outcome = outcome; session.flush()` directly on the legacy scalar column `Application.outcome` (`models.py:3757-3759`). No actor parameter anywhere in the call chain, no reason, no `ownership_service.assert_can_operate` call, no audit record, no communication side-effect. Bound to `templates/application_detail.html:92`, a plain `<select name="outcome">` with zero actor/reason fields.
- **Governed path**: `app.py:997-1022` route `POST /applications/<id>/outcome/apply` → calls `ownership_service.assert_can_operate(...)` then `outcome_service.apply_outcome(..., performed_by=actor, reason=..., note_text=...)`, which creates a proper `SelectionOutcomeDecision` row (`outcome_service.py:215-266`, explicitly append-only per its own docstring) and triggers `communication_service.on_outcome_decision`. Bound to `templates/decision_summary.html:73` and `templates/dossier.html:365`.
- Both routes are live simultaneously in the same application on different screens with overlapping vocabulary ("outcome").
- **Confirmed live consumer of the ungoverned field**: `03 Software/RF-One Data Store/rfone_data_store/selection/primary_screening_ai_evaluator.py:160` reads `prior[-1].outcome` — the AI evaluator building context about a candidate's prior applications can consume this stale, unaudited, directly-overwritten field instead of the true append-only `SelectionOutcomeDecision` history for the same conceptual data.
- **The same enforcement gap recurs one layer up**: `app.py:935-955` route `/applications/<id>/workflow-status` calls `workflow_projection_service.apply_legacy_workflow_action(...)` — which internally performs the *same* Stage/Outcome mutations as the two "modern" routes — but, unlike its siblings (`app.py:968-994` `/stage`, `:997` `/outcome/apply`), never calls `assert_can_operate` and collects no actor at all (`templates/application_detail.html:108-116` has only a status `<select>` and a `<textarea>`).
- **And again at the Primary Screening evaluation level**: `app.py:2297-2362` — of five near-identical mutation routes (`enter`, `override`, `confirm`, `not-applicable`, `insufficient-evidence`), only the sixth sibling route (`override-hard-disqualifier`) calls `assert_can_operate`; the underlying service functions (`primary_screening_service.py:489,521,541,565,650`) take no actor parameter at all.

**Impact:** A legally-relevant HR decision (candidate outcome) can be changed with zero attribution or audit trail through one of three code paths, while its two siblings enforce an authority check the third silently skips — this is a direct Historical Integrity violation (Core `ArchitecturePrinciples.md`) and creates real ambiguity about which button governs the "true" state of an Application. Retrofitting Authority later requires auditing every mutation route individually rather than adding one choke point, because the choke point (`assert_can_operate`) was applied inconsistently even before any real Authority engine exists.

**Recommendation direction:** Retire `application_service.set_outcome`/`Application.outcome` as a write target (route all outcome changes through `outcome_service.apply_outcome`); make `assert_can_operate` mandatory at the single Stage/Outcome/Evaluation transition function these routes funnel into, not at each route individually.

**When it must be fixed:** Before industrialization — this is a live correctness/attribution gap in the one Domain that is otherwise "functionally closed," and the AI evaluator dependency (line 160) means it can already silently affect a live business decision.

---

### C-3: No tenant/company scoping primitive anywhere in the schema; two incompatible "Location" hierarchies already coexist

**Finding:** RF-One's schema has no `company_id`/`tenant_id`/`corporate_id` column anywhere. Isolation today is "there is exactly one row in `restaurants`," enforced by nothing (no singleton constraint). Worse, two independent physical-location hierarchies already exist and meet only through a temporal join table.

**Evidence:**
- `models.py:139-194` `Merchant`/`Location` (the Clover/POS ingestion hierarchy) vs. `models.py:468-536` `Restaurant`/`RestaurantLocation` (the business-configuration hierarchy). Every Sales/POS fact table — `Order`, `Payment`, `Employee`, `Item`, `Tender`, `Device`, `Category`, `Modifier*`, `TaxRate`, `DiscountDefinition` (15+ tables, e.g. `models.py:210,235,303,337,1207,1232,1301,1337,1360,1379,1498,1577,1651,1785`) — is scoped only to `locations.id`. Every business-configuration table (`Supplier`, `PayrollRun`, `TipCalculationRun`, `WorkweekDefinition`, `OperationalArea`, `RestaurantRole`, `EmployeeAssignment`) is scoped to `restaurants.id`. The only bridge is `RestaurantLocation` (`models.py:495-536`), itself temporal (`valid_from`/`valid_to`).
- Consequence: "which Restaurant does this Order/Employee belong to" is not a stable FK anywhere — it's a point-in-time derived join that could resolve to zero or ambiguous rows if the `RestaurantLocation` history has a gap.
- `database.py:25,56-73` — `get_database_url()` resolves exactly one hardcoded SQLite file path with no company/tenant parameter in the resolution path at all.
- Separately, `restaurant_id`/`m.Restaurant` is used as Selection's *only* client-scoping key: **237 occurrences across 27 files** in `rfone_data_store/selection/*.py`, and ~140+ call sites in `03 Software/Selection/app.py` (`_bootstrap_restaurant()`, called from 20+ route handlers, resolves "the restaurant" as "the first row in the Restaurant table" with no restaurant_id in the URL/session at all).
- `00 Core/Corporate.md:120` states "Every RF-ONE installation contains exactly one Corporate" — implying the intended model may be one-database-per-installation rather than row-level multi-tenancy — but this is not confirmed anywhere as the deliberate choice for Selection's `restaurant_id` pattern, and the two conventions (`restaurant_id` scoping vs. `location_id`/`merchant_id`-only scoping) already disagree with each other inside the same schema.

**Impact:** Onboarding a second customer today would require reconciling two different scoping conventions inside one schema, generalizing ~27 files' and ~140+ call sites' worth of "the restaurant" assumptions in Selection, and deciding (for the first time, under pressure) whether RF-One is row-level multi-tenant or one-database-per-customer. No test anywhere exercises a second Restaurant/tenant (`schema_validation.py:159` creates exactly one).

**Recommendation direction:** Make the single-installation-per-Corporate model (or its alternative) an explicit, written Product Owner decision now, before a second customer is contracted — not after. Whichever is chosen, reconcile the `restaurant_id` vs. `location_id`-only scoping split before generalizing Selection.

**When it must be fixed:** Before onboarding any second customer; can safely wait if RF-One remains single-customer through the next development phase, but the *decision* (row-level vs. per-installation) should be made explicitly now while the blast radius is still one Domain.

---

### C-4: Validation/test suites default to the shared production SQLite file; only some self-isolate

**Finding:** Several of the repository's primary validation entry points do not self-isolate their database, and default to the same file used for real data if an environment variable is forgotten — and their own docstrings already warn this causes real collisions.

**Evidence:**
- `03 Software/RF-One Data Store/rfone_data_store/database.py:56-73` `get_database_url()` defaults to the shared local SQLite file `data/rfone.db` when `RFONE_DATABASE_URL` is unset.
- `test_payroll_engine.py:8-13`, `test_restaurant_profile_bootstrap.py:10-15`, `test_tips_engine.py:9-16` each explicitly warn in their own docstrings that running against the default/already-populated database will cause real `UNIQUE` constraint collisions (`SourceSystem(code="CLOVER")`) *before* any rollback happens, and instruct the operator to manually pass `RFONE_DATABASE_URL=sqlite:///path/to/fresh.db`. There is no code-level guard preventing accidental execution against the shared file.
- `selection_validation.py` (9,838 lines) — despite its own docstring claiming tests "always roll back," `run_validation()` (lines 87-117) calls ~20 separate `_assert_*` helpers, each opening its own session and doing a **real `session.commit()`** (confirmed at lines 148, 208, 234, 421, 463, 489, 521, and more), relying on manual `session.delete()` + a second real commit in a `finally:` block (e.g. lines 221-235) for cleanup rather than true transactional isolation. Any unhandled exception between a commit and its cleanup block permanently leaves synthetic rows (e.g. "Synthetic Batch Import Test Restaurant") in whatever database was targeted.
- **Contrast, showing the correct pattern already exists in-repo**: `test_purchasing_engine.py:51-58` builds and deletes/recreates its own disposable `data/purchasing_test.db` every run; `Selection/test_batch_upload.py:35-38` generates a `tempfile.mkstemp()` throwaway path and sets `RFONE_DATABASE_URL` in-process before importing `app.py`.

**Impact:** This is a live, easy-to-trigger risk (not a hypothetical future one) of polluting or corrupting the one database this single customer's real Payroll/Tips/Restaurant-profile data lives in, purely by omitting an environment variable — and the fact that three separate docstrings already warn about this suggests it has already caused a problem at least once.

**Recommendation direction:** Make every validation entry point either require an explicit `RFONE_DATABASE_URL` (fail loudly if unset, rather than silently defaulting) or self-provision a disposable database the way `test_purchasing_engine.py` and `test_batch_upload.py` already do; wrap `selection_validation.py`'s `_assert_*` helpers in real transactional rollback instead of manual delete-based cleanup.

**When it must be fixed:** Before industrialization — this is cheap to fix and the risk (silent production-adjacent data corruption from a routine command) is disproportionate to the effort.

---

## 4. IMPORTANT Findings

**I-1 — `CandidatePerson` and `Employee` are fully disconnected identities with no reconciliation path.**
`models.py:3679-3723` `CandidatePerson` has no FK, relationship, or code path connecting it to `models.py:294` `Employee`; `selection_validation.py:8627` confirms HIRABLE "never itself creates any employee/hire record (no such table exists in Selection)." A person's entire hiring history (flags, notes, outcome decisions, communications) becomes untraceable the moment they're hired. *Impact:* breaks the Auditability chain across the Selection→Personnel Management boundary. *Direction:* a deliberate (even if manual) linking mechanism at the hire-confirmation step, owned jointly by Selection and the future Workforce module. *Timing:* can wait until Workforce/Personnel Decisions is built out, but should not be forgotten as an integration requirement when it is.

**I-2 — `SelectionRuleSetVersion` is a "version" that isn't fully immutable.**
`models.py:6079-6096` docstring itself: 5 of its constituent parts (`signal_definition_ids`, `outcome_definition_ids`, etc.) "reference LIVE configuration rows — no immutable snapshot mechanism exists yet... an honestly-scoped limitation," while `requirement_set_snapshot_id` and `SelectionOutcomeDefinitionSnapshot` (`models.py:3416-3465`, `4995-5045`) show the codebase already knows the correct copy-by-value pattern. *Impact:* a historical Rule Set version's meaning can silently drift if a referenced Signal/Outcome Definition is later edited or deactivated. *Direction:* finish applying the existing snapshot pattern to the remaining five reference lists. *Timing:* before Selection's Rule Set history is relied on for compliance/audit purposes.

**I-3 — Missing uniqueness constraint allows duplicate `CandidatePerson` identities under concurrency; identity reassignment audit is optional.**
`models.py:3679-3706` has no `UniqueConstraint` on `(restaurant_id, primary_email)`/`(restaurant_id, primary_phone_normalized)` — dedup is application-code-only (`identity_service.py:35-53`), so concurrent résumé imports can fork one person into two records. Separately, `identity_service.py:232-259` `reassign_application` only records what a `person_id` was reassigned *from* if the caller supplies an optional `note`. *Direction:* add the DB-level unique constraint; make the audit note mandatory, not optional, on identity reassignment. *Timing:* before real-volume batch import usage.

**I-4 — Three internally-inconsistent, ad hoc Authority patterns coexist within Selection itself, and one is entirely unwired.**
`ownership_service.py` compares `SelectionAuthorityLevel.level_order`; `rule_change_service.py:41-44` requires only a `reason` string, no actor-authorization check at all; `rule_set_service.py:133-176` `confirm_rule_set_version` requires only a non-empty free-text `confirmed_by`. Separately, `governance_service.py`'s `get_governance_requirement_for_action` (lines 80-96) is fully configured (`SelectionAuthorityLevel`/`SelectionGovernanceRequirement`) but has **zero callers anywhere** in the ~45 service files reviewed — dead authorization scaffolding. *Direction:* consolidate on one Authority-checking convention before extending governance further; either wire `get_governance_requirement_for_action` in or remove it. *Timing:* alongside C-1's remediation, since it's the same underlying gap.

**I-5 — Genuinely generic platform capabilities are built once, well, but entirely inside Selection.**
`communication_providers.py` (SMS/Email provider abstraction — its own docstring confirms zero Selection-specific content), `communication_template_service.py` + `communication_service.py`'s `find_reminder_policy` (the same "most-specific-wins" template-resolution algorithm implemented independently three times), `inbound_communication_service.py` (a generic keyword-based intent classifier + inbox/alerts), and `scheduling_service.py` (a complete, generic appointment window/slot/capacity/token booking engine) are all reusable capabilities that happen to live only in Selection. *Direction:* candidates for future extraction to shared/Core infrastructure (see Section 9) — do not extract now, but avoid deepening Selection-specific coupling into them further. *Timing:* opportunistic, not blocking.

**I-6 — Transaction-boundary inconsistency in two Selection files; one long unguarded side-effect chain.**
`import_pipeline.py:106` and `normalization.py:142` call `session.commit()` internally, breaking the flush-only convention every other of the ~45 Selection service files follows (callers own the transaction boundary everywhere else); `normalization.py:142` has no `try/except` around it at all. `outcome_service.apply_outcome` (`outcome_service.py:215-318`) performs up to 7 sequential writes/service calls with only `flush()` between them and no enclosing `try/except` — the correct centralization, but the longest and highest-value candidate for a stricter rollback boundary. *Direction:* align `import_pipeline.py`/`normalization.py` to the flush-only convention; add a transactional guard around `apply_outcome`'s side-effect chain. *Timing:* low-cost, do opportunistically.

**I-7 — `restaurant_id`/`Restaurant` is pervasively baked in as Selection's only tenant-scoping key.**
See C-3 evidence; called out separately here because, independent of the schema-level tenant question, this specific code-level pattern (237 occurrences/27 files in the service layer, ~140+ call sites in `app.py`) is what will need mechanical, wide-blast-radius rework whichever tenant model is chosen. *Direction:* introduce an industry-neutral `client_id`/`organization_id` concept before a second Business Domain or second customer is added. *Timing:* before either of those events, not before.

**I-8 — Two independent purchase-document intake paths write into the same canonical model.**
`03 Software/InvoiceIntake/` (its own Flask app + `purchasing_bridge.py`) and the main Purchasing module's own Physical Receiving flow both ultimately write `PurchaseDocument`/`PurchaseLine` rows via `rfone_data_store.purchasing.repository`, confirmed still live and referenced in `PROJECT_STATE.md`. *Impact:* two independently-maintained code paths can diverge in validation/business-rule enforcement for the same canonical entity. *Direction:* evaluate consolidating InvoiceIntake's intake logic behind the same service Receiving uses, or explicitly document why two intake paths are intentional. *Timing:* not urgent; worth a deliberate decision before either path is invested in further.

**I-9 — The two `CLAUDE.md` files disagree on the canonical Domain taxonomy.**
`c:\Users\servi\OneDrive\AI-RF-ONE\CLAUDE.md` (repo-external, one level up) still lists the old flat taxonomy ("Restaurant, Personnel Management, Selection, Taxation, Administration," Selection as a Personnel Management module) while `RF One\CLAUDE.md` (in-repo, current) has the Cross Domain/Business Domain split adopted since TASK_DOMAINS_003. *Impact:* both files are read as binding instructions by any AI agent working in this tree; the stale one could cause a future contributor or agent to misclassify a new Domain. *Direction:* update or retire the outer file. *Timing:* low-cost, should be done soon since it actively feeds into every session's instructions.

**I-10 — Missing DB indexes on `location_id` across ~10 Sales/POS tables.**
`Order` (`models.py:1232`), `Employee` (`:303`), `Item` (`:1301`), `Category`, `ModifierGroup`, `Modifier`, `DiscountDefinition`, `TaxRate`, `Tender` (`:1651`), `Device` (`:1785`), `OrderType` (`:1207`) all declare `location_id` as a bare `ForeignKey` without `index=True`; by contrast `Shift.location_id`, `RestaurantLocation.location_id`, and `ReceivingRecord.location_id` correctly are indexed. Neither SQLite nor PostgreSQL auto-indexes non-PK FK columns. *Impact:* per-location sales reporting (the most obvious operational query pattern) will degrade as `orders` grows. *Direction:* one follow-up migration adding the missing indexes. *Timing:* before real reporting-scale data volume; not urgent for the current two-Location dataset.

**I-11 — Naming collision between Core doctrine's "Operational Unit" and the implemented schema.**
`00 Core/Corporate.md`/`Operational Unit.md` define a `Corporate → Brand → Operational Unit` chain where "Operational Unit... represents one physical operational location." None of `Corporate`, `Brand`, or `OperationalUnit` exist as tables in `models.py`; the physical-location role is instead played by four different tables across the two hierarchies in C-3, and `models.py:537-556` `OperationalArea` (a functional FOH/BOH grouping, not a location) closely echoes but does not implement the Core concept. *Direction:* Product Owner reconciliation of Core doctrine naming vs. implemented schema naming — not urgent given single-Restaurant reality, but a real source of confusion for anyone (human or AI) cross-referencing docs and code. *Timing:* alongside C-3's resolution.

**I-12 — No test coverage exists for the spoofable ownership/authority logic.**
`ownership_service.py`'s `can_reassign`/`assert_can_operate` — the one place free text is load-bearing for an authorization decision (C-1) — has zero test coverage in any of the reviewed `*_validation.py`/`test_*.py` files. *Direction:* add regression coverage for the current (admittedly weak) behavior before changing it, so the eventual C-1 fix has a safety net. *Timing:* alongside C-1.

---

## 5. MINOR Findings

- **M-1:** Stale code-comment path references to the pre-TASK_DOMAINS_003 structure `01 Domains/Cross Domain/Personnel Management/Selection/...` (which no longer exists) in `organization_intelligence.py:6`, `contextual_age.py:1`, `industry/restaurant.py:189`, and migration `b8f1c4a2e6d9_add_selection_resume_screening_schema.py:8`. Comment-only; does not affect behavior.
- **M-2:** `01 Domains/Cross Domain/Selection/reports/` holds ~22 task-implementation reports that were never migrated to the canonical `07 Tasks/Reports/` location established by TASK_CORE_005 and have no counterpart there — fragmenting Selection's implementation history outside the repository's stated single historical-record location.
- **M-3:** N+1 query patterns in `03 Software/Selection/app.py`: `applications_home` (lines 745-768, one `list_prior_applications` + one `_original_cv_available` query per rendered row), `sessions_home` (2545-2547) and `session_detail` (2596-2599, redundant with `sessions_home`) each re-querying `get_current_owner()` per Application. Cheap today at current data volume; will not scale without eager loading.
- **M-4:** `ApplicationNote.context_id` (`models.py:4100-4112`) enforces its "exactly one of application_id/session_id" invariant only in application code (`session_service.add_session_note`), while the directly analogous invariant on `InterviewSchedulingWindow` (`models.py:6474-6478`) *is* DB-enforced via `CheckConstraint` — inconsistent rigor for the same pattern in the same file.
- **M-5:** `SupplierProduct.ingredient_id` (`models.py:2490`) is a bare, self-documented placeholder `Integer`, not a real `ForeignKey` — no `ingredients` table exists yet anywhere in the schema.
- **M-6:** `PurchasingAlert`'s six nullable FKs (`models.py:2806-2819`) have no `CHECK` constraint tying the required non-null subset to the `trigger` value.
- **M-7:** `PurchaseDocument.status`/`PurchasingAlert.status` transitions (`models.py:2539`, `2832`) have no persisted history of intermediate states/who/when — only the final actor/timestamp is captured, unlike `PurchasingValidationLogEntry`'s explicitly immutable message history.
- **M-8:** Unnormalized exact-string employer-name matching in `selection/core/trajectory.py:54-66`'s `RETURN_TO_EMPLOYER` detection — inconsistent with the careful `normalize_name`/`normalize_email`/`normalize_phone` discipline used a few files away in `identity_model.py` for person-identity matching.
- **M-9:** `rfone_data_store/ingestion/clover/enrichment.py:37-44` mutates `sys.path` at runtime to import the sibling `03 Software/Clover Data Explorer/` project's low-level client/cache primitives, rather than a proper package dependency — deliberately scoped to non-business-logic primitives and documented as such, but fragile (breaks silently if that sibling project is ever renamed/moved).
- **M-10:** Empty, tracked-looking `01 Domains/Cross Domain/Selection/.claude/` directory with zero files — harmless stray artifact.

---

## 6. Observations

- **O-1:** No provider-specific leakage was found in any adapter boundary checked (Clover client/config, Clover ingestion mapping, InvoiceIntake OCR) — these are genuinely clean, worth preserving as the reference pattern when Selection's provider abstractions (I-5) are eventually extracted.
- **O-2:** No `TODO`/`FIXME`/`HACK`/`XXX` markers exist anywhere in `03 Software/` Selection code — known gaps are instead documented via explicit "NOT implemented"/"explicitly out of scope" docstrings (e.g. `governance_service.py:8-10`, `core/organization_intelligence.py`), a better-than-average discipline worth continuing.
- **O-3:** `02 Products/` contains no canonical Product configuration yet (`02 Products/README.md:31-33`) — expected at this stage; nothing to assess against multi-tenant readiness until a Product exists.
- **O-4:** The Selection ↔ Restaurant industry-extension seam direction is respected without exception in every file checked, including the Core algorithmic modules (`experience_analysis.py`, `trajectory.py`), which receive industry knowledge as injected parameters rather than importing it — a genuinely well-executed modular boundary.
- **O-5:** `core/organization_intelligence.py` is a correctly-scoped, `NOT_IMPLEMENTED = True` placeholder exactly matching its own Domain documentation's claim that no employer-quality/enrichment logic exists — the audit's specific concern about this file did not materialize as a defect (though see M-1 for its stale path reference).
- **O-6:** `selection/core/identity_model.py`'s name-based person-matching (`STRONG`/`POSSIBLE` similarity) is a legitimate, conservative use of fuzzy matching — it only ever produces a suggestion requiring explicit human confirmation, never an auto-merge; this is the correct pattern, distinct from C-1/I-3's concerns about *authority* being decided by string comparison.

---

## 7. Cross-Domain Dependency Map

**Major dependencies (all verified legitimate/compliant):**
- `01 Domains/Business Domain/Restaurant/Selection/` → Selection Core (industry extension depends on Core, documented and enforced direction).
- `rfone_data_store/selection/industry/restaurant.py` → `rfone_data_store/selection/core/role_model.py` only (one-way, confirmed no reverse import anywhere in `core/`).
- `rfone_data_store/selection/{analysis,normalization,signal_service}.py` → `rfone_data_store/selection/industry/restaurant.py` (service layer, not Core, consuming the industry module by concrete name — self-documented single-client debt, not a hidden violation; see I-7/C-3).
- `rfone_data_store/{payroll,purchasing,profile,tips}/*.py` → `rfone_data_store/models.py` only; zero cross-imports between these four subpackages or with `selection/`.
- `rfone_data_store/ingestion/clover/enrichment.py` → sibling project `03 Software/Clover Data Explorer/` via `sys.path` injection, scoped to low-level API primitives only (M-9).

**Suspicious dependencies:** none found beyond the M-9 `sys.path` mechanism (fragile but not a layering violation) and the already-covered I-7 single-client-name coupling.

**Circular/hidden coupling:** none found. No file in `core/` imports from `industry/`; no file in `payroll/purchasing/profile/tips` imports from `selection/` or from each other.

---

## 8. Duplicated / Overlapping Concepts

| Concept | Locations | Likely canonical owner | Severity |
|---|---|---|---|
| Physical location | `Merchant`/`Location` (POS) vs. `Restaurant`/`RestaurantLocation` (business config) | Unresolved — needs explicit reconciliation | CRITICAL (C-3) |
| Person identity: candidate vs. employee | `CandidatePerson` (Selection) vs. `Employee` (Personnel/Payroll) | Legitimately distinct today; needs a hire-time linking mechanism, not a merge | IMPORTANT (I-1) |
| "Operational Unit" (doctrine) vs. physical-location tables | `00 Core/Operational Unit.md` vs. `Restaurant`/`RestaurantLocation`/`Location`/`Merchant` | Core doctrine should be reconciled to name what the schema actually does | IMPORTANT (I-11) |
| "Most-specific-wins" scoping/precedence resolver | `communication_template_service.find_best_template`, `find_template_for_outcome_event`, `communication_service.find_reminder_policy` | A single shared resolver algorithm, currently implemented 3× independently | IMPORTANT (folds into I-5) |
| Versioned-configuration-with-immutable-snapshot pattern | `outcome_service.py` (Outcome Definitions) and `communication_template_service.py` (Templates) hand-implement the same shape independently | A shared "versioned configuration entity" helper | MINOR (efficiency/duplication, not a risk) |
| "Who is allowed to do this consequential thing" | `ownership_service` (authority-order comparison), `rule_change_service` (reason-only), `rule_set_service` (free-text name-only), `governance_service` (configured, unwired) | None yet — candidate for shared Authority (Core §09) | IMPORTANT (I-4, ties to C-1) |
| Generic messaging/scheduling/classification capabilities | `communication_providers.py`, `communication_template_service.py`, `inbound_communication_service.py`, `scheduling_service.py` | Selection today; shared/Core eventually | IMPORTANT (I-5, Section 9) |
| Task/implementation reports location | `01 Domains/Cross Domain/Selection/reports/` vs. canonical `07 Tasks/Reports/` | `07 Tasks/Reports/` per repo-wide convention | MINOR (M-2) |

No accidental duplication was found for: Note/Evidence/Attachment/Audit tables outside Selection (checked across Payroll/Purchasing/Sales/Tips — none exist there beyond `PurchasingValidationLogEntry`), or Decision/Outcome concepts (Selection's `SelectionOutcomeDecision` and Restaurant's Purchasing-domain decisions are cleanly scoped to their own tables with no overlap).

---

## 9. Shared Infrastructure Candidates

Capabilities currently implemented once, entirely inside Selection, that are genuinely generic and would be reasonable to extract to shared/Core infrastructure **later** (do not extract now):

1. **SMS/Email provider abstraction** (`communication_providers.py`) — already has a clean `SmsProvider`/`EmailProvider` abstract-base + swap-in-provider seam; zero Selection-specific content per its own docstring.
2. **Template render/send/record engine** (`communication_service.py`'s `send_communication`/`_render`) — generic "template → multi-channel send → persist delivery row," distinct from the genuinely Selection-specific trigger logic (`on_stage_transition`, `on_outcome_decision`) that should stay.
3. **Versioned-template CRUD + specificity resolver** (`communication_template_service.py`) — the "most-specific-wins" scoping resolver (restaurant/branch/role/stage/outcome) is duplicated 3× (Section 8) and is itself a generic rules-precedence pattern.
4. **Inbound message classification + inbox/alerts** (`inbound_communication_service.py`) — a general-purpose deterministic intent classifier (withdrawal/decline/reschedule/etc.) with no candidate-screening-specific logic in the classifier itself.
5. **Appointment scheduling engine** (`scheduling_service.py`) — a complete, self-contained window/slot/capacity/booking/token-link system with DB-level race protection; nothing about it is intrinsically about candidate screening.

Each of these was built well (clean internal boundaries, DB-level race protection where it matters, no provider-name leakage) — the finding is about *ownership location*, not quality.

---

## 10. Data Model / Migration Assessment

**Migrations:** 36 files, single linear chain, one root (`9516f3bd1495`), one head (`a2d8f4c1b9e6`), no branches. One destructive operation found (`c1a9f0d3e7b2_add_location_business_day_and_.py`, a SQLite rename-copy-drop table recreation) — verified safe, verbatim row-preserving, correctly documented. Three `nullable=False` columns added to already-populated tables all carry safe `server_default` values. No obsolete-but-still-carried columns found; no evidence of orphaned migrations.

**Data model:** Actor identity is exemplary outside Selection (100% FK-based) and broken inside it (C-1). Historical Integrity is genuinely implemented for Payroll/Purchasing/Tips configuration tables (temporal close-old/open-new pattern) but incompletely for Selection's `SelectionRuleSetVersion` (I-2) and entirely absent for `Application.outcome` (C-2). Tenant scoping is the weakest area (C-3, I-7, I-11). Minor constraint gaps (M-4, M-5, M-6) and one missing history trail (M-7) are normal technical debt, not urgent.

---

## 11. Security / Identity / Authority Readiness

No authentication mechanism exists anywhere in `03 Software/` (confirmed by exhaustive grep for `login`, `session[`, `current_user`, `@login_required`, `password`, `authenticate`, `SECRET_KEY` — zero matches in application code; neither Flask app sets a secret key). This is an **expected, documented pre-industrialization gap** per `03 Software/Identity Authority and Security Architecture.md` and is not itself a finding.

What crosses from "expected gap" to "architectural blocker" is C-1: `ownership_service.py` has already built something that *functions as* an authorization system on top of unverified free text, producing artifacts (audit entries, "who's in charge" state) that will be trusted as real once a genuine Identity/Authority layer exists alongside them, unless explicitly reconciled first. This is exactly the kind of code the review brief warned would "make adding shared Identity/Authority later unusually difficult" — not because auth is missing, but because a look-alike is already partially built and load-bearing.

**Classification of the overall gap:** architectural blocker (C-1), not merely an implementation-stage task — specifically because of the free-text authority *comparison* logic, not the mere absence of login.

---

## 12. Multi-Tenant Readiness

**Assessment: difficult, bordering on dangerous if a second customer is onboarded without a dedicated remediation project first.**

- No `company_id`/`tenant_id` column exists anywhere in the schema (C-3).
- Two incompatible location-scoping conventions already coexist (`location_id`/`merchant_id` for Sales/POS vs. `restaurant_id` for business configuration and all of Selection) (C-3).
- `restaurant_id` is baked into 237 call sites across 27 Selection service files, plus ~140+ call sites in the Selection Flask UI, all resolving "the tenant" as "the only row in the Restaurant table" (I-7).
- No test anywhere exercises more than one Restaurant/tenant, so no regression safety net exists for whatever generalization is eventually done.
- Not dangerous *today* because there is only one customer and no cross-tenant boundary can currently be crossed — the risk is entirely in what happens the moment a second customer's data enters the same database.

---

## 13. API / Service Layer Assessment

Selection's ~45 top-level services show a genuinely strong single-writer discipline: every lifecycle table checked (`SelectionOutcomeDecision`, `ApplicationStageTransition`, `CandidateCommunication`, `InboundCommunication`, `InterviewAppointment`, `ApplicationOwnership`, `SelectionCaseMemory`) has exactly one service function that constructs it, and no bypass writes were found anywhere in the ~45 files reviewed. Error handling is inconsistent (four different idioms coexist, no shared exception hierarchy, no application logging layer anywhere) but this is normal pre-industrialization debt rather than a correctness risk, since the dominant pattern (raise `ValueError`, let it propagate) is at least consistent across the large majority of files. Transaction boundaries are consistent except for two named outliers (I-6).

---

## 14. UI / Workflow Structural Assessment

The clearest structural weakness in the entire audit: near-identical state transitions are gated inconsistently depending on which of several UI-exposed routes performs them (C-2's three-tier example: outcome/apply vs. outcome/set vs. workflow-status; and Primary Screening's five-of-six-ungated evaluation routes). This is not a UI polish issue — it means "does this action require authority/attribution" already has a different answer depending on which button a user happens to click, which will make any later Authority retrofit a route-by-route audit rather than a single interception point. The `_bootstrap_restaurant()` single-tenant assumption threaded through 20+ route handlers (D, folded into C-3/I-7) is the second most significant structural issue — every one of those handlers would need rework to accept a tenant identity as a parameter.

---

## 15. Test Quality / False-Confidence Risks

- The `*_validation.py` suites test business-rule correctness thoroughly (date normalization, duplicate detection, payroll totals, stage/outcome projections) but **none touch authority, security, or tenant-isolation concerns** — expected given none of those exist yet, but it means C-1's spoofable `ownership_service` logic has zero regression coverage (I-12), and no test would catch a regression that made spoofing easier or accidentally granted broader access.
- Assertions are outcome-based (no mock/internal-method-call brittleness found) — a genuine positive.
- `selection_validation.py`'s claimed "always rolls back" is not accurate for most of its ~20 `_assert_*` helpers (C-4) — a case of the test suite's own documentation overstating its safety, which is itself a minor instance of "documentation vs. runtime drift" (Section 18).
- `test_purchasing_engine.py` and `Selection/test_batch_upload.py` are the reference-quality examples (proper disposable-DB isolation) that the other suites should be brought in line with.

---

## 16. Legacy / Dead / Transitional Code

- `03 Software/InvoiceIntake/` is **not dead** — confirmed still active and canonically writing through `purchasing_bridge.py` into the same repository the main Purchasing module uses, with Excel correctly reduced to a secondary/debug-only export (I-8 covers the duplication concern, not deadness).
- `governance_service.get_governance_requirement_for_action` is genuinely dead: fully configured, zero callers anywhere in the ~45 files reviewed (I-4).
- `workflow_projection_service.py`'s entire `workflow_status` legacy projection is a well-documented, intentional backward-compatibility shim for "a handful of old UI/routes" — not stale/orphaned, but a second source of truth that must never be written to directly (and one of its own consumers, C-2's workflow-status route, already fails to respect the authority guard its sibling routes use).
- No `TODO`/`FIXME`/`HACK` markers exist anywhere in the reviewed code (O-2).
- `AI/`, `Backend/`, `Database/`, `Frontend/`, `Infrastructure/` under `03 Software/` are confirmed literally empty — pure unused scaffolding, no finding beyond that confirmation.
- Stale path references (M-1) are the only found instance of "intermediate Task-era concepts surviving after later decisions superseded them" at the code-comment level.

---

## 17. Performance / Scalability Risks

- Missing `location_id` indexes across ~10 Sales/POS tables (I-10) — the most concrete, fixable finding in this category.
- Three N+1 query patterns in `Selection/app.py` list views (M-3) — cheap today, will not scale, no eager loading used anywhere in the reviewed hot paths.
- No synchronous-external-call-in-request-path, unbounded-history-load, or large-JSON-re-parsing issues were found in the areas reviewed — the JSON columns used throughout Selection are handled transparently by SQLAlchemy's `JSON` type with no hand-rolled re-parsing.

---

## 18. Documentation vs. Runtime Drift

- **Root `CLAUDE.md` vs. in-repo `CLAUDE.md`** (I-9) — the clearest and most consequential drift found, since both files are read as binding instructions.
- **Stale "Personnel Management/Selection" path references** (M-1) in 4 code locations, superseded by TASK_DOMAINS_003.
- **`selection_validation.py`'s "always rolls back" docstring claim** does not match its actual `_assert_*` implementation (C-4) — documentation overstating runtime safety.
- **No drift found** between `01 Domains/Business Domain/Restaurant/Purchasing/EntityDefinitions.md` and `models.py`'s Purchasing tables — exact terminology match, including the two deliberately-named exceptions (`PurchasingAlert`, `PurchasingValidationLogEntry`) that the domain's own `PURCHASING.md` documents.
- **No drift found** between Selection's `ResumeScreening/README.md`'s "Organization Intelligence is OPEN/TBD" claim and `core/organization_intelligence.py`'s actual `NOT_IMPLEMENTED = True` content (O-5) — the one place this review specifically expected to find a contradiction and did not.

---

## 19. Industrialization Blockers

Explicit list of items Shelbi should **not** build further on top of before correction:

1. **C-1** — Do not extend `ownership_service.py`'s authority-comparison logic, or add new features that trust its output as genuine attribution, before reconciling it with a real Acting Identity.
2. **C-2** — Do not add new outcome/stage/evaluation mutation routes following the `workflow-status`/`outcome/set` pattern (unguarded, actor-less); all new mutation surfaces should funnel through the governed path.
3. **C-3** — Do not onboard a second customer, and do not deepen the `restaurant_id`-as-tenant-key pattern into new Selection features, before the tenant-scoping decision is made explicitly.
4. **C-4** — Do not rely on `selection_validation.py`/`test_payroll_engine.py`/`test_tips_engine.py`/`test_restaurant_profile_bootstrap.py` producing a clean, isolated run without first confirming `RFONE_DATABASE_URL` is set to a disposable database.

## 20. Safe-to-Defer Items

- I-1 (CandidatePerson/Employee linking) — no active harm until Workforce integration is actually built.
- I-2 (RuleSetVersion partial snapshot) — dormant until someone actually edits a referenced live definition after a version is confirmed.
- I-5 (shared infrastructure extraction) — valuable but purely organizational; no correctness risk in leaving it as-is.
- I-8 (InvoiceIntake/Receiving duplication) — both paths currently work correctly; consolidation is a design decision, not an urgent fix.
- I-10 (missing indexes) — fine at current data volume.
- All MINOR findings (M-1 through M-10) and all Observations.

## 21. Recommended Correction Order

1. C-4 (test/validation database isolation) — cheapest, highest immediate-risk-reduction fix.
2. C-1 (Acting Identity for Selection's authority/audit fields), together with I-4 and I-12.
3. C-2 (unify outcome/stage/evaluation mutation through the governed path).
4. I-9 (reconcile the two CLAUDE.md files) — cheap, prevents future taxonomy mistakes.
5. C-3 decision (tenant-scoping model), followed by I-7, I-11.
6. I-3 (CandidatePerson uniqueness constraint + mandatory reassignment audit).
7. I-6 (transaction-boundary consistency in `import_pipeline.py`/`normalization.py`).
8. I-2 (finish the RuleSetVersion snapshot pattern).
9. I-10 (add missing indexes).
10. Remaining IMPORTANT and MINOR items, opportunistically.

*(This is a sequencing list only — not executed as part of this audit.)*

## 22. Final Assessment

**READY WITH IMPORTANT PRECONDITIONS.**

The Core/Domain/Product/Software architecture, the Cross Domain/Business Domain taxonomy, and the non-Selection business logic (Purchasing, Payroll, Sales, Tips) are soundly built, internally consistent, and correctly separated — this is not a repository with a broken foundation. The four CRITICAL findings are concentrated specifically in the seam between Selection's runtime and the Identity/Authority/Accountability architecture this repository canonicalized immediately before this audit, plus one repository-wide operational-safety gap (test database isolation). None require a redesign; all four have a clear, bounded fix already precedented elsewhere in the same codebase (e.g., Purchasing's `*_employee_id` FK pattern for C-1, `test_purchasing_engine.py`'s disposable-DB pattern for C-4). Addressing the four CRITICAL items — and making the C-3 tenant-scoping decision explicitly before any second customer is contracted — should precede further industrialization investment in Selection specifically; the rest of the repository can be built on with more confidence today.
