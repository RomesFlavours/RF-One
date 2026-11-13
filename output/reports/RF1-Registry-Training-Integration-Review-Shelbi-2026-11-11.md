# RF1 Registry and Training — Integration Review

**For:** Shelbi  
**Date:** November 11, 2026  
**Scope:** Identity, authentication, authorization, student records, and course assignments  
**Review type:** Static code review of the local RF1 checkout and retained Training release sources

## Overall assessment

Registry and Training are partially integrated. Registry controls effective RF1 access, but Training still maintains its own student identities, profile fields, and enrollment workflows. The connections between these records are not consistently completed or reused.

The main issue is that granting Training access, identifying the person, and assigning that person a course are separate processes. They can produce different outcomes for the same individual.

Training should continue to own courses, assignments, progress, and results. Registry should provide the canonical person, contact details, company memberships, employment status, and effective system permissions.

## Scope and limitations

This review examined local source code and retained source packages associated with the Training AWS release. It did not query the live AWS database, verify the currently running image against those packages, or run new end-to-end tests.

The findings identify behavior and gaps in the reviewed code. They do not establish how many production records are affected or prove that a particular production user has experienced every issue described below. No code, data, or production configuration was changed during this review.

## 1. Authentication and authorization

### Current integrated behavior

Training has a dedicated sign-in page. In the integrated flow, this page checks RF1 account credentials rather than requiring a separately managed Training password.

Access requires all three of the following:

- An active RF1 account.
- Effective permission to use Training in the current company context.
- A Training identity linked to that RF1 account.

The integration rechecks access on each request. It maps Training permissions to `student` or `trainer`; a Training domain administrator receives trainer capabilities.

Registry permissions are additive: direct grants and grants inherited from assigned roles are combined. Removing one grant does not remove access if another grant still provides it.

### Legacy mechanisms still present

Training retains its own account table, stored role, password hash, and legacy login functions. Their continued presence does not, by itself, mean that users can bypass RF1 authentication. The reviewed AWS entry point redirects legacy trainer pages to the newer workspace and blocks legacy trainer POST operations.

However, these mechanisms leave multiple representations of identity and privilege in the code. Some downstream operations still use the stored Training role instead of the effective role calculated by Registry.

## 2. Course assignment

Training owns the learning workflow: content, published versions, learning objectives, assignments, progress, quiz attempts, and results. This is an appropriate domain responsibility.

The recipient workflow is less consistent:

- The current Students page reads Training's own roster.
- It explicitly excludes profiles marked as employee-directory recipients.
- It does not automatically offer all active Registry people who are eligible for Training.
- Having an active Registry record and Training permission does not automatically create or complete the required Training identity link.

As a result, a person can have Training permission but still be unable to enter Training or appear in the expected assignment list.

## 3. How names and identities move between Registry and Training

| Workflow | Observed behavior |
| --- | --- |
| Create a new student in Training | Creates an RF1 account, a Training identity, and a link between them. It does not automatically create a Registry employee record. |
| Enable an existing RF1 account | Administrative functions can explicitly link an existing Training identity or create a new linked identity. |
| Assign content to a Registry employee through the employee-recipient service path | Can create a Training identity and store the employee ID in a Training profile. That path does not complete the link to the employee's existing RF1 account. |
| Resolve the canonical person | Registry follows explicit person/account/Training identity links. It does not automatically merge records based on matching names. |

The employee-recipient service path exists in the code, but the reviewed current student-assignment page submits Training student recipients. Its existence should not be confused with a complete employee enrollment feature in the current interface.

There is no single, consistent enrollment process covering all these paths.

## 4. Findings and practical impact

### A. Permission does not complete Training enrollment

Registry can grant Training access while the RF1 account has no linked Training identity. The access check then rejects entry.

**Required correction:** Provide an explicit enrollment operation that reuses or creates the Training identity and completes the link without creating a second login.

### B. Employee assignments can create a disconnected identity

The employee-recipient path can create a new Training identity without first reusing the identity already linked to the employee's RF1 account. The new profile's employee reference is also separate from the canonical identity-link mechanism.

**Risk:** Assignments may be attached to an identity the employee cannot reach through their normal RF1 login, or learning history may become split across identities.

### C. Company boundaries are incomplete

Trainer access is evaluated in the company context, but roster queries and recipient assignment checks do not apply an equivalent company filter to the target students.

**Risk:** A trainer authorized for one company may be able to manage students outside that company's intended scope.

### D. Dismissal checks are inconsistent

RF1 session validation checks the linked person's employment status. Training assignment code instead relies on a combination of RF1 account status, Training profile archiving, or a direct check of `employee.active`.

**Risk:** Access and assignment eligibility can disagree. The centralized active-person rule is not consistently applied to recipient selection and assignment submission.

### E. The Training role has two sources

Request authorization uses Registry's effective role. Roster selection and the assignment service still inspect the role stored on the Training account.

**Risk:** Someone authorized as a trainer through Registry may be rejected by the assignment service if the stored Training role remains `student`. Company-specific roles also do not fit cleanly into one globally stored Training role.

### F. Personal information is duplicated

Training maintains a display name through its own identity record and a phone number in its student profile. The phone field is not consistently sourced from Registry's centralized contact information.

**Risk:** Registry and Training can show different contact details or names for the same person.

### G. Training archiving can affect platform access

For students it is allowed to manage, Training's archive operation can set the linked RF1 account to inactive. The code includes safeguards that restrict this management to eligible Training-only students.

**Concern:** A domain-level archive action still changes a platform account's status. Course participation, employment dismissal, and RF1 account suspension need distinct meanings and explicit authority.

### H. Revocation needs visibility into all permission sources

Direct permissions and role-derived permissions are combined by design.

**Required correction:** Show why a user has access, including every contributing grant. Verify revocation after all relevant sources have been removed, rather than assuming that removing one role is sufficient.

## 5. Recommended ownership

| Information or capability | Responsible component |
| --- | --- |
| Canonical person ID and name | Registry |
| Email and phone | Registry, with a defined policy for login email verification |
| Company memberships and organizational roles | Registry |
| Employment status and dismissal | Registry; external learners must not be treated as employees solely because they take training |
| RF1 credentials, account state, and session validation | Shared identity and access services |
| Effective domain permissions | Registry-managed authorization policy |
| Training enrollment linked to the canonical person | Training, using shared identity links |
| Courses, versions, assignments, progress, and results | Training |

A person should not need a duplicate personal record to participate in Training. External learners should also have a canonical identity, without being forced into an employment relationship.

## 6. Recommended correction sequence

1. Audit existing person, RF1 account, Training account, and student-profile links. Identify duplicates, missing links, and conflicting associations before changing records.
2. Define one enrollment operation that resolves the canonical person and reuses the correct RF1 and Training identities. Do not merge people by name alone.
3. Build recipient selection from the centralized identity and eligibility rules, with authorized company filtering. Recheck eligibility when saving assignments.
4. Make effective Registry authorization authoritative throughout Training, including assignment services. Remove reliance on stale stored roles for permission decisions.
5. Centralize personal contact information and separate Training archiving from employment dismissal and platform account suspension.
6. Retire redundant legacy creation and credential-management paths after confirming that existing identities and learning history remain accessible.

## 7. Acceptance checks

Before publishing corrections, verify that:

- Granting Training access and completing enrollment allows the intended person to sign in through RF1.
- Repeating enrollment reuses the same identities and preserves all history.
- Removing all effective Training grants blocks subsequent requests, including an already-open browser session.
- A trainer cannot list, inspect, or assign content to recipients outside their authorized company scope, including through a direct POST request.
- A dismissed person cannot receive new assignments, while their learning history remains available to authorized reviewers.
- Different roles across companies work without rewriting a global Training role during navigation.
- Employee and external-learner workflows both use confirmed canonical identity links.
- Updating centralized contact information produces consistent results in Training.
- Training archiving has only the explicitly agreed effect on RF1 account access.

## Technical reference

Relevant source locations, relative to the RF1 repository or retained Training release package:

- `03 Software/RF-One Web/training_integration.py` — RF1 authorization and Training identity links.
- `03 Software/RF-One Web/training_cloud.py` — AWS Training entry point and legacy route boundaries.
- `03 Software/RF-One Web/training_workspace_routes.py` — student management, sign-in, and assignment endpoints.
- `03 Software/RF-One Data Store/rfone_data_store/training/workspace.py` — roster, profiles, archiving, and assignment orchestration.
- `03 Software/RF-One Data Store/rfone_data_store/access_profiles.py` — effective role and direct permissions.
- `03 Software/RF-One Data Store/rfone_data_store/employee_directory.py` — canonical person resolution and explicit identity links.
- `03 Software/RF-One Data Store/rfone_data_store/rfone_web_session.py` — shared session and active-person validation.
