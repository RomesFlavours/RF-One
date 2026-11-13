# REPORT — Local Registry authorization audit

## 1. Conclusion and scope

The Registry integration is incomplete. Removing Accounts from MyRF did not remove its stored direct grants: Registry's Other system authorizations still edits those same canonical account rows. The RF1 shell applies those grants and company-scoped role grants, but the local launcher and separate applications do not currently provide a consistent end-to-end authorization experience.

This audit performed no AWS calls, production updates, Git push, real password reset or changes to real users/grants. Real local account configuration was read using a read-only PostgreSQL transaction. Permission mutations and test sessions used disposable synthetic SQLite databases only. The release worktree source remained clean; findings and test artifacts are recorded separately in this audit.

RF1 shell source: the actual private development-source used by localhost:5094. Separate applications tested in-process from their local sources: Tips and Selection under 03 Software, and the frozen previously published Kitchen source under the local output/kitchen-release/source tree. These results are not a fresh inspection of currently running AWS services.

## 2. Running local-copy limitation — confirmed

The private launch_local.py always selects the active owner and overwrites the session identity on each request. Its path allowlist permits Registry, Employee Directory, Accounts and a few shell pages only. Bank, Compensation, Projects, Organization, Wines, Selection and Tips validation are rejected before their normal authorization handlers.

Observed on localhost:5094: Home and Registry HTTP 200; /compensation, /projects, /bank, /admin/organization, /restaurant/wines, /selection and /tips/runs HTTP 403. Therefore the ordinary local browser cannot prove per-user permissions and currently blocks modules even for its forced owner. Authorization tests below used the normal app in isolated test clients, without that local owner override or path allowlist.

## 3. Confirmed application findings

### A. Tips does not enforce the TIPS entitlement at its global boundary

A synthetic ACTIVE non-admin RF1 account with no domain grants entered standalone Tips Home and /roles with HTTP 200. An anonymous client received HTTP 401. The global guard checks that the RF1 account is logged in, but not account_may_enter_domain(..., 'TIPS'). Hiding its Home card does not close direct access. This is the highest-priority authorization defect found.

### B. Kitchen and Selection do not consume company-role grants consistently

Using synthetic company membership and a matching Registry role grant, the separate Kitchen gate returned HTTP 403. Adding the direct KITCHEN account grant returned HTTP 200. The frozen Kitchen account-service implementation reads direct grants and installs no Registry company context.

Selection, tested with RFONE_SELECTION_REQUIRE_RFONE_LOGIN=1, likewise returned HTTP 403 for a role-only SELECTION grant and HTTP 200 after its direct grant was enabled. Its global authorization check has no company-context initialization. The common profile engine deliberately treats company=None as legacy direct grants only; all participating apps must carry and validate the selected company rather than infer an all-company union.

### C. Training checks authorization before Registry company context is installed

In the RF1 shell, both student and trainer profile grants passed the shared domain gate for the selected company, but the actual /training entry returned HTTP 302 back to Home. The Training SSO before-request handler runs before the later-registered Registry company-context handler; it therefore sees no role-only TRAINING grant. A followed redirect can misleadingly end in HTTP 200 on Home, which is why this audit checks the first response.

Additional source observations: Training still validates a separately stored TrainingAccount.role and its student list begins with a direct-grant SQL join. Those paths also need explicit treatment when role-derived permissions change; this audit did not claim that a followed Home redirect demonstrated working Training access.

### D. The employee-directory entitlement has no usable Home entry for ordinary users

A non-platform-admin account explicitly granted EMPLOYEES has no Registry/Employee Directory entry in MyRF. The new Home link is conditional on platform administration, while /admin/roles itself requires platform admin. Policy editing and employee-directory consultation need distinct guards/entries; granting the existing directory entitlement should not lead to an invisible navigation destination.

## 4. What passed

The prior 87 Registry acceptance checks passed against the copied runtime. This audit added 99 checks covering all 12 registered access codes. Within the RF1 shell, each code denied no-grant access, accepted a direct grant edited through the canonical Registry-linked account page, denied access after direct revocation, accepted a role grant in its assigned company and denied that role in another company. Selected Bank functions also denied an unselected configuration URL. Actual mounted destination denials were checked separately from diagnostic gate probes.

The 15 failing audit expectations comprise 12 repeated manifestations of missing company context outside the shell, the employee-directory Home visibility defect and two Training entry cases. They are not 15 unrelated bugs. Independent service tests above establish the Tips, Kitchen and Selection findings.

Personal grants and role grants remain additive by the approved design. Removing one personal grant does not withdraw a permission still granted by a role. This behavior passed and should be made visible in the effective-permission UI rather than mistaken for a deny override.

## 5. Real local accounts and identity review

Read-only review found 6 RF1 accounts: 5 ACTIVE and 1 INACTIVE. Four active accounts have no confirmed employee association; that is valid for external consultants/owner accounts, but intended employee logins must be explicitly reconciled with their canonical employee before changes to that employee's roles can govern the existing login. No association was guessed from names and no account was modified.

Raw account names and grant details remain in the private tmp audit file and are not embedded in this report. This is the existing local data copy, not a new AWS database synchronization.

## 6. Required correction sequence

1. Make the local verification environment exercise selected test users without replacing them with owner; retain the no-signature local requirement and isolate cloud/POS effects.
2. Install one validated company/access context before authorization in every RF1 application and use the shared effective-permission evaluator for roles plus direct grants.
3. Add the missing TIPS domain check, retaining only deliberate public endpoints.
4. Correct Training request ordering and role/identity integration, including role-driven lists and per-company privilege changes.
5. Restore an entitled user's employee-directory entry without granting policy-management privileges.
6. Review explicit person/account links; then verify grant, change and revocation for each actual intended login.

## 7. Evidence (local only)

- tmp/registry-local-running-server-audit.json
- tmp/registry-authorization-main-audit.json and .log
- tmp/registry-authorization-tips-audit.json
- tmp/registry-authorization-kitchen-audit.json
- tmp/registry-authorization-selection-audit.json
- tmp/registry-local-real-accounts-audit.json (private; not for Git)

Reproduction scripts: tmp/audit_running_local_access.py, tmp/audit_registry_authorization_main.py, tmp/audit_registry_tips_local.py, tmp/audit_registry_kitchen_local.py and tmp/audit_registry_selection_local.py. Synthetic fixture files remain under tmp and are excluded from Git.
