# Codex independent review checklist

**Governing decision:** [RF1_OPERATIONAL_DATABASE_001](../../../10%20System/Operational%20Database%20and%20Data%20Governance/README.md), §7.
**Role:** Codex is the **independent reviewer**. It verifies conformity, tests, regressions,
dependencies, schema and risks against the approved specification. **Codex does not change
requirements and does not redesign.** Every deviation or gap is reported before deployment and
returns to design (Product Owner + ChatGPT). Release happens only after explicit Product Owner
approval ([RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)).

Use this checklist for every commit or branch handed over for review. Report each item as
**PASS / FAIL / NOT APPLICABLE**, with file and line evidence for every FAIL.

## A. Specification conformity

1. The change implements an **approved** specification; identify it (document, section, date).
2. Nothing beyond the specification was added: no extra workflow, schema, table, column, API,
   algorithm, UI flow or architectural decision (RF1_OPERATIONAL_DATABASE_001 §6.4, §7).
3. Every choice the specification left undefined was **stopped and submitted to design**, not
   decided in code. List any undecided choice found in the change.
4. No column or table name was invented without verification in existing code (§5).

## B. Operational database principle

5. Domain logic reads business data only through RF-One canonical data and interfaces — never
   directly from a provider API, a provider schema or a connector staging table (§2, §6.2).
6. No new acquisition engine for one Domain or one period (§6.1); external POS data comes through
   the one shared acquisition service (§3).
7. No systematic duplication of the same business fact per module (§4, §6.3).
8. External IDs and origin are kept as provenance for audit, never as the conceptual primary key (§3).
9. Checkpoints advance only after a valid write; upserts are idempotent; late updates,
   cancellations, corrections, pagination, retries and gaps are handled without duplicate
   events (§3).
10. Locations/merchants and companies remain separated; credentials stay per location (§3).
11. Frequency is set by the common service, not by a Domain (§3). Any claimed API capability is
    verified, not assumed.
12. Bank: enrichers write only the enrichment field of the RF-One movement; WHO/WHY read only
    canonical transaction fields (§4).
13. Replacing the source (e.g. Clover → RF POS) would not require changes to the consuming Domain
    touched by this change (§1, §4).

## C. Schema, data and environment safety

14. Migrations are additive and reviewed; no destructive migration, no production change and no
    AWS write without explicit approval (§6.5). Migrations are never applied at application
    startup (RELEASE_CHECKLIST step 5).
15. No credentials, local databases or private runtime data in the commit.
16. Local data policy respected (`CLAUDE.md`, *Local Database Policy*): no new permanent
    database copies; AWS → local alignment only.

## D. Tests and regressions

17. Relevant tests exist for the change and pass; report commands and results verbatim.
18. Pre-existing suites affected by the change still pass; report any test weakened or removed.
19. Dependencies added or changed are justified by the specification.

## E. Documentation and help

20. Documentation affected by the change is updated consistently and links to the single
    reference specification instead of restating it.
21. Contextual help / How Works matches the implemented behaviour (`CLAUDE.md`,
    UI_CONTEXTUAL_HELP_001; `check_how_works.py` before release).
22. No remaining instruction in the repository contradicts RF1_OPERATIONAL_DATABASE_001; any found
    is listed as a gap for design, not silently resolved.

## Review output

A short report with: reviewed commit(s); specification(s) checked; result table A–E; deviations
(file, line, rule, risk); gaps returned to design; explicit statement whether the change is
**ready for Product Owner release approval** or **not ready**.
