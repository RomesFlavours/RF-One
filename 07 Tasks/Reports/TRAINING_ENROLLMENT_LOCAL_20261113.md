# REPORT — Local Training enrollment, 13 November 2026

## 1. Requested result and implementation

Training → Students → **Invita studente** provides two entry routes:

| Entry route | Input | Shared outcome |
|---|---|---|
| Confirmed in Selection | Choose a currently HIRED candidate from an authorized position; CV name/email/phone prefill the form | One personal activation link |
| Direct invitation | Email, with optional known name/phone; confirm possible existing Registry matches | The same activation page |

The recipient verifies/completes name and phone against the immutable invited email
and chooses their own password if new. Existing RF-One account holders prove the
current password instead; existing username, password and other grants survive.
Successful activation opens Training and shows the RF-One username.

Pending invitations create no person or login. Activation uses the existing
CandidatePerson registry, PersonAccountLink, TrainingPersonLink and central student
provisioning service in one transaction. Selection reuses its exact person ID;
Training enrollment creates no Employee and makes no employment decision.
Full manual entry and older initial-password activation links remain compatible.

## 2. Identity, access and invitation safeguards

Matches by name/email/phone require explicit trainer confirmation; contact conflicts
and identities created after invitation issuance stop activation without automatic
merging or duplicate creation. This does not reconcile pre-existing ambiguous
historical records automatically.

Selection permission and position scope are checked on the server. Latest decisions
are authoritative: an old HIRED row superseded by another decision is excluded.
The source confirmation and issuer's Training authorization are checked again when
activating. Archived students and incompatible/inactive existing access are refused.

Links are random, 48-hour, single-use tokens, stored only as SHA-256 digests.
Reissue revokes prior pending links for the same email; limits are one minute
between invitations and five per hour. Existing-account password attempts are
limited to five per invitation. CSRF protects POST actions; activation responses
disable caching/referrers and remove the bearer token from subsequent URLs.

## 3. Local scope and schema

The only working database remains PostgreSQL `127.0.0.1:55436/rfone_aws_copy`.
Explicit initialization adds `training_enrollment_invitations`; it is never created
at application startup. The Training branch advances `t9c120261112 → t9d120261113`
while retaining the independent `k9f120261112` head. No historical person, account,
credential, grant or assignment is changed by initialization.

The local interface remains Italian and staff opens it as the existing local
operator without entering credentials. Local invitation creation shows a copyable
loopback URL and does not contact external recipients. The link works only on the
computer running this server. No AWS service/database, production route or Git
remote was modified or published by this task.

## 4. Validation and observed limits

- Rollback-only PostgreSQL integration: direct invitation, no premature identity,
  chosen password, email tampering ignored, STUDENT without employee, exact Registry
  reuse, password preservation, explicit duplicate review, CSRF, expired/replaced
  links, issuance limits, late duplicates, latest Selection decision, withdrawn
  confirmation, revoked issuer access and five failed password attempts all pass.
- Edge browser: actual Students page → invitation page; Selection CV prefill and
  direct mode; recipient activation → Training. Screenshots inspected and input
  layout corrected. All non-loopback browser requests were blocked.
- Existing student Registry/legacy activation integration suite passes, including
  initial password, recovery, mixed-role archive and intercepted delivery failures.
- How Works: RF-One Web has 28 covered pages, zero errors; changed Students help and
  both new page-specific modal help sections are included in the registry.
- The restarted persistent server responds at port 5098; staff auto-sign-in and
  invalid activation refusal are verified by HTTP. Test transactions roll back;
  no synthetic candidates, students, invitations or outgoing emails remain.

The canonical local database currently has no HIRED Selection decisions. Therefore
the real dropdown is empty until confirmed candidates are present. The Selection
path was verified using temporary persisted-model fixtures inside the rolled-back
test transaction, not by inventing operational confirmed candidates.

## 5. Files and traceability

- Specification: `03 Software/Training/ENROLLMENT.md`.
- Data service/model: `03 Software/RF-One Data Store/rfone_data_store/training/enrollment.py`.
- Additive migration: `03 Software/RF-One Data Store/migrations/versions/t9d120261113_training_enrollment.py`.
- Web routes and explicit initializer: `training_enrollment_routes.py`,
  `initialize_training_enrollment.py`, with integration in `training_workspace_routes.py`
  and `training_local.py`, under `03 Software/RF-One Web/`.
- UI: new `templates/training_workspace/enrollment*.html`, Students entry action,
  `static/js/training-enrollment.js`, scoped styles in `training-workspace.css`.
- Help: `templates/help/training_enrollment*.html`, updated `training_students.html`,
  and `03 Software/Shared UI/how_works_registry.json`.
- Tests: `03 Software/RF-One Web/test_training_enrollment_local.py` and existing
  `test_student_registry_local.py`.
- Evidence: `output/training-enrollment-20261113/test-result.json`,
  `live-verification.json`, screenshots `00-selection-prefill.png` through
  `03-training.png`; temporary screenshot tokens no longer have database rows.

Recovery: revert the scoped application/UI changes while retaining the additive
invitation table/history and unrelated schema heads. Do not drop central identity
tables, remove account links or downgrade unrelated work.
