# Shared Registry identity for Training and Selection

Approved local task, 2026-11-12. Target: actual loopback 5094 Registry and its
rfone_employee_directory database. Use Employee as the existing central Registry
record, with EmployeeContextLink for candidate, RF-One account and Training
facets. CandidatePerson stays the Selection extension referenced by applications;
TrainingAccount stays the learning-history identity. Neither is a second central
Registry person. Never change existing historical links on a name guess.

One shared identity resolver uses confirmed context links, explicit Registry
selection, or a unique exact contact match. Conflicting contacts and name-only
matches require explicit review. New identities use employee_directory.create_person,
the same creation service as manual Registry. New imports/onboarding are serialized
on PostgreSQL identity evidence. Existing ambiguous historical data are preserved,
not bulk-merged. No schema migration or historical data backfill is required.

Training reuses existing RF-One credentials and Training history, validates active
account and grants separately, and does not write or require STUDENT qualifications.
An EMPLOYEE company relationship establishes course eligibility without a separate
student qualification. Learning access still requires an active authorized account.
Creation remains an explicit authorized POST; GETs do not provision identities.
Only local testing is authorized, with no AWS/production writes or outgoing mail.


## Local implementation and verification

The Registry create action, Selection resolver, Training enrollment and legacy
Training adapters now share registry_identity.py and employee_directory context
resolution. The read resolver also follows already confirmed person/account/
training bridges without rewriting history. A second restaurant application reuses
the same Selection identity; genuinely conflicting historical facets require review.
Employee company status preserves the operational identity when Training is enabled.

The embedded legacy Training creation route redirects to the Registry-backed
RF-One enrollment page. That page supports selecting an existing person and does
not request a new password for an existing account. The explicit loopback launcher
marks offline operation so this local test sends no invitation email. No new
schema migration or historical mass reconciliation was needed.

Evidence: test_registry_domain_identity.py (shared resolution, idempotency,
legacy bridges, credential/grant preservation, no STUDENT requirement), existing
test_registry_person_status.py, and RF-One Web/test_registry_domains_5094.py.
The actual 5094 E2E uses Registry and Training POSTs, the exact Selection
application service and its HTTP view, then opens assigned course content as the
Registry employee. Synthetic rows are removed in finally; watched original
Registry/Selection/Training history and grants must retain their pre-test digests.
Proof and source backups: C:/Users/servi/AppData/Local/RF-One/Backups/
registry-training-selection-20261112. No AWS or production operation was performed.


Final result: 11 identity integration tests and 21 Registry/role/company
regression tests passed (32 total). Actual 5094 E2E passed after the final
service restart; Registry, Training enrollment and Selection home returned HTTP
200. Account-only company qualifications are retained when explicitly linking
the same person to the central Registry. No STUDENT qualification was created.
The local 5094 launcher remains running with its external-integration guards.
