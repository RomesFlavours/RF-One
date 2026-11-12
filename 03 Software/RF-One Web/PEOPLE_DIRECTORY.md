# One people directory

Training integration: the explicit `STUDENT` qualification and Training-person link
reuse this same directory. A student remains visible as a central person without
becoming an employee; Bank/Organization operational candidate lists exclude
student-only identities. Qualifications do not grant module permissions. See
[Student Registry](STUDENT_REGISTRY.md) for onboarding, activation and recovery.

Product Owner decision, 2026-11-01: the directory includes employees and external people. Do not maintain two separate people registries. An RF-One account is a login, not a second person.

The existing `CandidatePerson` identity records (`candidate_persons`, historical physical name) provide the person reference. This change reuses those records and adds only explicit links to existing Employee and RFOneAccount records; it does not add another table of names or migrate/delete employee, account or Selection history. The shared directory is `/people`. Legacy `/employees` navigation redirects there; the specialized employee data editor remains available from linked records.

All known person records and unlinked employee/account records are visible to administrators in the same directory. Reconciliation is explicit: link a source to an existing person, or explicitly create a person from that source. No name/email matching silently merges identities. One account belongs to one person and the first workflow supports one RF-One account per person; several location-specific employee records may link to the same person. Conflicting links are rejected, not reassigned. These links grant no Domain permissions and do not expose Selection assessments.

An external person can exist without login. Interview requests select a person; an active linked RF-One account is required to deliver a MyRF task. The request stores the stable person ID and the delivery account ID. Existing interview rows without person IDs are resolved only through explicit account links, never name comparison. Administrator result access stays limited to the requesting administrator. A participant sees their own identity on the interview page without being granted access to the administrative directory.

The person record links to requesting interviews and to the requesting administrator's interview history/results. The three interview pages link to or identify that same person. Account administration is relabeled as login/access management; it remains a technical settings function, not the people directory.

The additive migration follows `f8d120261101`. No automatic write or schema creation occurs at startup or on directory GET. Existing source records need explicit reconciliation; this prototype does not claim all historical cross-domain duplicates have already been resolved. No shared/operational database is migrated during development.
