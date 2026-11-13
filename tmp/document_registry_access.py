from pathlib import Path
base=Path('tmp/git-anagrafica-release')
addition='''

## Registry authorization integration — local validation, 2026-11-10

Registry is the administrative entry for company memberships, additive role
permissions and direct personal permissions. All RF1 web components must read
the shared effective policy on every request, including direct URL requests.
`rfone_data_store.web_access.install_access_context` validates the selected
company before any domain or Training gate, in the shell and standalone Tips,
Selection and Kitchen. No valid company means direct grants only; it must never
mean the union of roles across companies. Existing direct grants remain global
and additive, so removing a role does not remove independent direct access.

Tips now checks the TIPS entitlement, rather than login alone. Its operational
Training entry redirects to the canonical RF1 Training routes after checking the
current TRAINING entitlement and explicit identity link. A legacy Training cookie
or password cannot bypass Registry. The intentionally public dish guide remains
public. Training uses a request-only effective role; navigation never rewrites
stored domain identity/history. Trainer-to-student downgrade takes effect on the
next request. Trainer password administration checks the target's privileges in
all companies, preventing a student in one company from masking privileges in
another. Identity linkage remains explicit, available from Registry's personal
Domain Access page; names are never used for automatic account matching.

Kitchen tab access uses the shared effective item reader instead of raw direct-
grant SQL. Development Journal responsibility candidates and Training student
candidates also use effective permissions. Shared session validation refuses
inactive accounts and dismissed linked nonowners, including an accidentally
still-ACTIVE administrator. The approved owner access exception remains. A domain
or role grant never creates RF1 platform-administrator powers.

Authorized HTML responses are no-store. Selection schema migrations are explicit
startup/release operations; importing a service must not migrate the shared DB.
No new schema migration is needed for these authorization fixes.

The loopback-only local launcher has a User selector and shared company session
across the actual local components. Selecting an inactive account or revoking a
session cannot fall back to owner. The explicit local selection is independently
signed and never installed in production. External AWS/Clover calls stay blocked;
there is no login/signature or environment banner in this local environment.

This change is local only, pending Product Owner acceptance before AWS publishing.
'''
p=base/'10 System/Identity & Access/Role Profiles and Company Access.md';p.write_text(p.read_text(encoding='utf-8')+addition,encoding='utf-8',newline='\n')
p=base/'PROJECT_STATE.md';s=p.read_text(encoding='utf-8');s=s.replace('# PROJECT_STATE\n','# PROJECT_STATE\n\n## Registry access integration — local only, 2026-11-10\n\nShared effective company context now precedes shell, standalone Tips/Selection/\nKitchen and Training authorization. Registry grant/revoke checks cover all 12\naccess codes; Training roles are evaluated per request without identity writes.\nThe local environment on port 5094 includes an explicit user selector, keeps\ninactive users denied, and retains the original 64 people / 47 dismissals. No AWS\nrelease or Git push for this pass; Product Owner local trial is next.\nSee `07 Tasks/Reports/REGISTRY_AUTHORIZATION_LOCAL_FIX_20261110_REPORT.md`.\n',1);p.write_text(s,encoding='utf-8',newline='\n')
p=Path('tmp/verify_registry_local_users.py');s=p.read_text(encoding='utf-8').replace("'/training/login')","'/training/login','/kitchen/sign-in')");p.write_text(s,encoding='utf-8',newline='\n')
