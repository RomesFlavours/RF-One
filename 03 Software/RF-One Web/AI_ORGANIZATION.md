# AI Organization — local cross-domain prototype

## Verified domain analysis (2026-10-18)

The current naming convention is **Shared Domains**, formerly Cross Domain
(`01 Domains/Domain Architecture.md`). AI Organization is a transversal runtime
consumer, not a replacement for Restaurant Organization or Core definitions.
The user-supplied specification authorizes this local implementation.

Implemented organization: `LegalEntity` owns `Restaurant`, linked to `Location`;
`OperationalArea`, `PhysicalArea`, `RestaurantRole`, `OperationalAreaRole`,
`EmployeeAssignment` express restaurant configuration and dated work assignments.
The shared foundation separately implements `Position`, `PositionScope`,
`PositionAssignment`, temporary coverage, backups and `ProcessOwnership`.
`organizational_responsibility_service` owns their creation and routing.
Account/domain access is separate; a Position never grants login rights.
The existing organization admin pages and coverage checker are real runtime.
MyRF's full operational interface and general cognitive orchestration are not.

Current authority: Core 2.0 `02_Desire_Goal_and_Reality_Check.md`,
`05_Epistemic_Boundary_and_Subject_Sovereignty.md`,
`00 Core/Organizational Responsibility.md`, `ImplementationGuidelines.md`.
Legacy under `90 Archive/Legacy Repository/X00 Knowledge Repository/` is historical
input only (including the draft Decision Framework and Desire); it cannot override
current Core. The interview follows desire, resources, constraints, process and
verification without requiring five forms.

Existing AI client: Selection's `parsing/ai_client.py`, also consumed by Tips,
supports Anthropic and AWS Bedrock. No voice or web-research capability exists in
this checkout's web shell. Configuration inspection found BEDROCK configured,
but neither a direct Anthropic key nor an OpenAI key in environment/root `.env`.
Bedrock is excluded by the user's no-AWS requirement. Default startup does not
load repository secrets, use AWS or contact external services. It starts in
clearly labeled DEMO mode. `ai_organization_provider.py` adapts the existing direct
Anthropic transport; the service validates its response. It cannot dispatch to
Bedrock. To opt in, supply `ANTHROPIC_API_KEY` in the process environment,
ensure the existing `anthropic` dependency is installed, and start with `--ai`.
Use demo data only. No live provider calls were made during verification.
Other approved providers can implement the same callable contract. No fake web results.

The proposal-first demo now includes primary references actually researched online
on 2026-10-18: Bain's RAPID decision accountability and McKinsey's decision-making
typology. `ai_organization_research.py` preserves the URLs, consultation dates and
limits. They inform comparison, never become mandatory Core concepts or prove a
company-specific recommendation. This is not live research on each conversation.
The first response prepares a provisional solution and alternatives, then asks
one discriminating fact; it does not ask the user to design the organization.

## Contract and safety

Flask/Jinja/SQLAlchemy, existing account/session/CSRF helpers and domain registry.
New tables store interview documents/revisions and explicit per-company grants;
they do not duplicate approved organization. Non-admin users need AI_ORGANIZATION
domain access plus company grants; application additionally needs `can_apply`.
Admins still need domain entry. Each session belongs to its author and one company.
Multi-company selection is deliberately unavailable until a cross-company grant
contract is defined; separate company sessions are supported.

Draft changes are limited to scoped Position and ProcessOwnership additions or
description updates. People, competencies, budgets, handoffs, decision limits,
dependencies and verification remain attributed evidence/planning material until
their corresponding operations are explicitly supported. No implicit person or
authority assignment. The review shows supported changes and these limits.
Approval records a revision; any further interview turn invalidates it. Apply
checks current organization against the preview, is atomic, local-only and
idempotent, and never writes account access. MyRF export contains approved evidence
and canonical Position/ProcessOwnership IDs for the existing resolver; it sends
no notification and does not claim all decision limits are executable.

## Run

From this directory: `python ai_organization_local.py --init` then
`python ai_organization_local.py`. Open http://127.0.0.1:5091/ai-organization .
The launcher uses only `output/ai-organization/ai-organization-local.sqlite3`, creates no data on
ordinary boot, binds loopback, and never reads `.env`. Initialization is explicit
and repeatable. Per Product Owner instruction, the isolated loopback launcher
enters the demo account automatically: **no username/password prompt**. This
does not change the production shell's authentication or company/domain grants.
Open the address in Microsoft Edge; do not open the internal Codex browser.
Stop with Ctrl+C; restart with the same command. Back up the SQLite file while
stopped. Tests: `python tests/test_ai_organization.py`.
