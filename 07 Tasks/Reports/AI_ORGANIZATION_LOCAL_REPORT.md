# AI Organization local prototype — implementation report

Date: 2026-10-18. Scope: existing RF-One checkout, local synthetic data only.

Further Product Owner correction: the agent must propose solutions, not ask the
user to design them. Removed the sequential resources/constraints/process
questionnaire from the demo. A provisional proposal and trade-off comparison now
appear on the first response, with one discriminating fact to clarify. Added two
primary references actually researched online on 2026-10-18 (Bain RAPID and
McKinsey decision making), preserving URL, consultation/publication dates,
findings and applicability limits. These are development-time references, not a
live per-interview search engine or proof of the best company-specific structure.
The direct-provider instruction follows the same proposal-first contract.
Verification after this change: 11/11 offline integration tests passed, including
the first-turn proposal, attributed research sources and absence of the previous
design-it-yourself prompts. The loopback server was restarted with the update.

Latest Product Owner refinement: restart the experience from a clean page. The
landing page now contains only the path explanation and an empty desire field.
The five reasoning steps remain visible in a sticky strip during scrolling.
Previous interview contents are not loaded into this page; saved sessions remain
behind a closed disclosure. The new landing page was checked with Flask's client
(200, no password, no current organization/draft on entry), and reopened in Edge.

## Outcome

Running at `http://127.0.0.1:5091/ai-organization`. Microsoft Edge was launched
with the saved demonstration interview URL. Per subsequent Product Owner
instruction, the isolated launcher enters the demo account automatically; there
is no username/password prompt. HTTP verification returned 200 directly at the
interview home. The internal browser was used for initial UI verification before
that instruction; no internal tabs remained in the subsequent inventory.

This is explicitly DEMO, with scripted prompts and an editable organization draft.
It is not a claim that a real AI completed the interview. Configuration inspection
showed Bedrock, with no direct provider credentials; AWS is forbidden by this task.
The opt-in direct-provider adapter is prepared and tested through injected
responses. No real provider call or external research was performed.

## Reused implementation

Organization retains its existing LegalEntity/Restaurant/Location, functional and
physical areas, RestaurantRole and temporal EmployeeAssignment model. Shared
Position, PositionScope and ProcessOwnership are the actual application targets,
using the existing organizational responsibility service. Accounts and domain
access remain separate. Current Core 2.0 is authoritative; archived Legacy remains
historical input. See `03 Software/RF-One Web/AI_ORGANIZATION.md` for the inspected
references, runtime/documentation distinction and functional contract.

## Changes

Created Data Store services `ai_organization.py` and `ai_organization_provider.py`;
Web routes, Italian template, local launcher, runtime documentation and integration
tests. Modified only the web shell's optional local route registration and domain
registry. Other pre-existing working-tree changes were left in place.

Conversation/evidence, editable draft/history, explicit approval and applied
canonical organization IDs are separate. Each fact retains author, source, date
and status. Corrections invalidate approvals. The comparison checks organization
drift before approval/application. Application is transactional, restricted to
the isolated local SQLite database, and repeatable without duplicate records.
MyRF export preserves approved scope and canonical responsibility IDs without
notifications or a second routing engine. Company grants and author ownership
are checked server-side, in addition to existing domain/session/CSRF mechanisms.

## Acceptance evidence

10 integration tests passed: full interview, correction, invalidated approval,
application, repeat confirmation, reopened persistent state; company and author
isolation; read-only grants; concurrent organization change; shared-position
protection; reuse across sessions without access grants; malformed provider
response; injected adaptive provider contract; no-AWS credential guard; HTTP
entry, CSRF, stale revision and unauthorized company access.

Initial browser verification exercised login, initial desire, three interview
replies, uncovered position, summary, generated draft and before/after comparison.
Then the server was actually stopped and restarted for passwordless local entry;
the original saved session remained on disk. HTTP verified the restarted server
returns the conversation home without a login redirect or password field.

## Effective limits

- Demo dialogue is scripted; it does not interpret arbitrary corrections as AI.
  Users edit the draft explicitly. The real provider adapter can produce adaptive
  questions/proposals but was not exercised against a live service.
- Application supports scoped Position/ProcessOwnership additions and description
  updates. It does not assign people, alter accounts, infer competencies, grant
  spending authority, remove prior ownerships or automate every planning element.
- Multi-company work uses separate authorized sessions; no aggregated cross-company
  interview is provided. Cross-author collaborative approval is not provided.
- External references can be recorded in conversation; no web-search integration,
  voice service, production migration, deployment or notifications were added.

## Restart / backup / traceability

From `03 Software/RF-One Web`: `python ai_organization_local.py`.
First initialization only: `python ai_organization_local.py --init`.
Optional direct AI: provide `ANTHROPIC_API_KEY` in the process environment and the
existing `anthropic` dependency, then start with `--ai`, using demo data only.
Default launch never reads `.env` or uses AWS. Open the URL in Edge.

Local state: `output/ai-organization/ai-organization-local.sqlite3` and
`output/ai-organization/session.key`. Stop the server before copying both files
for backup; restore them to the same directory while stopped. Tests use a separate
temporary database. No production or remote database was opened or modified.
