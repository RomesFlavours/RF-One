# REPORT — Registry authorization integration (local only)

## 1. Outcome and scope

Implemented in `tmp/git-anagrafica-release`, branch `codex/registry-access-local`,
starting from the released Registry source. The original worktree's pending
employee-lifecycle changes remain untouched. No AWS operation, deploy, Git push,
real-user permission change or automatic person/account matching in this pass.
No new schema migration; local PostgreSQL stays at `f3b120261110`.

## 2. Corrections

- A shared Flask adapter resolves a validated company before all authorization
  gates in RF1 Web, Tips, Selection and Kitchen. Permissions are re-read on every
  request. Direct personal grants and role grants stay additive; role revocation
  does not remove an independent personal grant. No context never unions all
  companies. Browser HTML responses are no-store.
- Tips requires a TIPS entitlement, not merely an RF1 login. Its operational
  Training entry validates the shared Training grant/link and sends the user to
  canonical RF1 Training. The legacy Training login/cookie cannot bypass policy.
  The intentionally public dish guide remains public.
- Training uses the effective company role without rewriting identity/history
  on GET. Trainer-to-student downgrade closes trainer routes immediately.
  Password administration checks target privileges across all companies.
- Kitchen navigation/item gates use the common effective policy, replacing raw
  direct-grant SQL. Its published business source was recovered from the frozen
  Kitchen release without editing that separate source/repository.
- Development Journal responsibility choices and Training student choices no
  longer depend only on direct-grant SQL.
- Shared session validation blocks inactive accounts and dismissed nonowners,
  including a stale ACTIVE administrator. The approved owner exception remains.
- A nonadministrator granted EMPLOYEES can reach the permitted directory from
  MyRF; this does not grant Registry policy administration.
- Registry Domain Access exposes the existing explicit Training identity/history
  management entry. Existing links/history are reused; no name matching or
  automatic identity creation is performed. A grant does not replace required
  domain identity setup or activate an inactive RF1 account.
- Selection no longer migrates the shared database merely by importing the app.
  Schema updates remain explicit operations.

## 3. Verification

All final checks below pass, using disposable SQLite fixtures except the final
read-only loopback PostgreSQL/HTTP matrix:

| Suite | Passed |
| --- | ---: |
| Registry HTTP: all 12 access codes, actual protected URLs, direct/role grants and revocation, selected items, company separation, trainer downgrade, cross-company password protection | 192 |
| Standalone Tips actual pages and legacy Training bypass denial | 27 |
| Standalone Selection actual pages | 16 |
| Standalone Kitchen dashboard, recipes, configuration | 24 |
| Shared role/company policy unit tests | 15 |
| Training role/read-only regression checks | 23 |
| Training integration HTTP | 29 |
| MyRF Home HTTP | 36 |
| Clover immutable artifact/worker guard | 16 |
| Existing local accounts: 6 accounts × 10 actual component entries | 60 |

The real local matrix checks preserved access, denial, selected Organization
entry and inactive-account denial, without changing grants. Counts remain
64 people and 47 dismissed. The inactive user never falls back to owner. Existing
accounts without a Training identity or a valid Training role stay denied; no
relationship was invented to make a test pass. Invalid/anonymous/inactive states
may redirect to the canonical login rather than return 403; that is a denial,
not successful entry. Browser inspection confirmed Registry, the User selector,
collapsed People (21) and Dismissis (47), without login or environment banners.

## 4. Local trial and recovery

- MyRF: http://127.0.0.1:5094/
- Registry: http://127.0.0.1:5094/admin/roles?tab=people
- User chooser, reachable even after denial: http://127.0.0.1:5094/local/users

The User selector is local-only and preserves an explicitly selected account
across denial/logout with a separate signed choice, without refreshing revoked
RF1 session versions. The actual component apps share the real local DB and
company session. AWS/Clover and other outbound calls remain blocked. There is
no production authentication shortcut in application code.

Private runtime: `C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z`.
Its immutable `source` and `rfone-aws.dump` are retained. `development_source`
points to this reviewed source. The previous launcher is retained as
`launch_local.before-registry-access.py`; repository runtime instructions are in
`03 Software/Infrastructure/Registry Local/README.md`.

Next step is Product Owner trial. AWS publication remains pending that trial.


## Switch user administrator restriction — 2026-11-10

At the Product Owner request, the local selector is visible and usable only by a
currently valid RF1 platform administrator/owner. Both chooser GET and switch POST
check the current account server-side. Domain administration alone is insufficient.
After switching to an ordinary user the selector disappears and both endpoints
return 403; inactive/revoked sessions are also denied. No retained administrator
privilege is attached to the impersonated user's session. Verified against the
7 accounts currently in the local database: 31 checks passed. No account grants,
AWS configuration or production source were changed by this restriction.


## Anthony local identity clarification — 2026-11-10

The user configured KITCHEN-only on Anthony Watler, employee 45, linked explicitly
to inactive account 16. The active login `anthony`, account 15, was a distinct,
unlinked external account with nine direct legacy grants and no KITCHEN grant.
No authentication failure or stale permission cache caused that discrepancy.
At the user's instruction that Anthony should see only Kitchen, the existing
Registry Domain Access POST was used to set account 15 to KITCHEN-only locally.
The two identities were not merged, linked, reactivated or renamed. Existing
record 45/account 16 was untouched. Actual HTTP checks as account 15 verified
Kitchen on MyRF, four working Kitchen entries, seven other components returning
403 and no Switch user for this nonadministrator. AWS was not modified.
The person modal now identifies the exact linked RF1 username and account status
beside the authorization controls to make similar-name discrepancies visible.
