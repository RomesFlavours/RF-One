# Selection → Training → Registry — documentation reconciliation (2026-11-21)

**Status:** Audit and proposed reconciliation only. No existing approved specification is silently superseded.
**Branch baseline:** `integration/live-2026-11-20`. No runtime change or deployment.

## 1. Conflict confirmed

The current operational workflow approved by the Product Owner is:

1. Selection's **Send to Training** sends the person to Training and creates/reuses **one Registry person** with **Trainee** status; a personalized Training invitation is issued.
2. Training tracks course completion, practical checks, lead sign-off and paid training time.
3. An authorized manager confirms hiring after requirements are met; Registry becomes **Employee** and the confirmation records who/when. Owner override requires a recorded reason.
4. A person remains one person throughout. Employment/payroll records are separate from Registry identity.

This operational workflow must not be conflated with an abstract Selection Decision to proceed or with an employment/payroll transaction.

## 2. Existing repository sources requiring reconciliation

- `01 Domains/Shared Domains/PERSON_CONTINUITY_001.md` §1, §3, §6: presents Candidate → Employee → Training and speaks of evidence after hiring. **Draft** conceptual document; preserve its cross-Domain identity continuity principle, but revise the illustrative lifecycle only after checking all consumers.
- `01 Domains/Shared Domains/Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md` §3 and §6: says assessment is handed to Training **at hiring**; requires explicit separation of Selection approval to train and later employment confirmation.
- `01 Domains/Shared Domains/Selection/SELECTION_GUIDABILITY_AND_TRAINING_HANDOFF_001.md` §7: describes the handoff to Employee identity. Must reconcile the handoff's semantic identity and timing.
- `01 Domains/Shared Domains/Selection/README.md`: points to the handoff at hiring. Cross-reference must be updated consistently.
- `03 Software/Training/ENROLLMENT.md` (approved 2026-11-13): describes an entry route from a currently HIRED Selection candidate, delayed identity/account creation on activation, and no Employee record created. **This is a distinct approved implementation specification that conflicts in timing/identity with the newer operational workflow.** It must be reconciled explicitly rather than overwritten.
- `01 Domains/Shared Domains/TRAINING_SERVICE_001.md`: approved conceptual service boundary; do not change its domain/service classification to solve a runtime lifecycle problem.

## 3. Required consistency tests for any eventual edit

- No duplicate Registry person across Selection, Training, locations, or external providers.
- No automatic employment merely because Selection approves training or sends an invitation.
- Status Trainee is distinct from Employee and from Training enrollment/account access.
- Hire confirmation is authorized, auditable and follows completed requirements; owner override with reason is explicit.
- Existing invitations and accounts preserve identity, credentials and history; no automatic merge based on names/email.
- Training time is paid, but payment execution remains a separate controlled process.
- Selection/Training/Registry are not independent identity masters.
- No new backend blocker or architectural abstraction without Product Owner approval.

## 4. Scope and next action

This report records the contradictions and the Product Owner's more recent operational direction. It does **not** claim that production implements it, and it does **not** modify older approved documents before reviewing the exact service/database state and the November 13 enrollment decision. The next change must update the relevant canonical and software documents together with an explicit supersession note and Codex review. No merge or deploy is authorized by this report.
