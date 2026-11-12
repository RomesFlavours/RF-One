# Training student onboarding

Approved mandate: Product Owner, 2026-11-12 (Training Overview).

The trainer enters name, email and username in Students. RF-One searches the
existing CandidatePerson directory and account records before writing anything.
Any name/email/username match requires explicit confirmation; conflicting account
and person matches are refused. Confirmation links the existing identity; it never
changes existing credentials or non-Training grants. A new person receives the
explicit STUDENT qualification, independent of login permissions. Employee source
links remain independent evidence of employment; onboarding creates none.

Provisioning person, qualification, RF-One login, Training identity and links is one
transaction. Email follows commit; failed delivery leaves a recoverable account,
with a visible retry action. Activation verifies ownership of the recorded email
and sets the sole RF-One password using the existing expiring, single-use HMAC code
service. Recovery uses that same service and requires a verified address. SMTP uses
the existing TLS adapter and RFOne@romesflavours.com; no provider fallback.

Training history keeps its existing IDs. Archive blocks Training and revokes old
sessions; other legitimate grants and account status survive for mixed-role users.
Credential administration for privileged/mixed-role accounts remains with RF-One
administrators. Student-only identities are excluded from Bank/Organization
candidate lists using Training/person facts, never Domain grants. Registry includes
students as people, without creating or labeling them as employees.

Schema additions are person qualifications and a unique Training-to-person link.
No automatic historical identity matching/backfill or permission repair occurs.
Existing ambiguous records require explicit reconciliation. No hiring workflow,
AWS deployment or production data migration is authorized by this task.
