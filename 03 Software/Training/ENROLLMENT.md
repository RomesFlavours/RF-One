# Local Training enrollment — approved 13 November 2026

Two trainer entry routes converge on one invitation and activation page: choose a
currently HIRED candidate from Selection (restricted to the operator's authorized
positions), or invite directly with email and optional known name/phone. Full
manual student entry remains available. Selection supplies the existing person ID
and contact evidence; it never creates employment or rewrites hiring decisions.

Invitations are pending enrollment requests, not another person directory. No
person/login/Training account is created until activation completes. Possible
existing identities require explicit trainer confirmation. Changed/conflicting
evidence blocks activation and returns resolution to the trainer; names/contacts
are never grounds for automatic merging. Reuse the central CandidatePerson,
PersonAccountLink, TrainingPersonLink and existing student provisioning service.

The single-use random invitation link expires in 48 hours; only its digest is
stored. Reissue revokes earlier pending links for that email. Activation verifies
the invited email through possession of the link, collects/validates name and
phone, and sets the password directly for a new account. Reusing an existing RF-One
account additionally requires its current password, preserving username/password,
status and existing grants. Disabled/conflicting Training access is not repaired.
Successful activation atomically attaches STUDENT/Training access, consumes the
invitation and creates the normal authenticated learner session. No employee record
is created. Legacy initial-password activation links remain compatible.

Local invitations show a copyable loopback link instead of contacting real people.
Local tests intercept email, use the single canonical PostgreSQL database inside
rolled-back transactions, and leave no students or invitations behind. Schema
initialization is an explicit local command, never application startup. Production,
AWS, delivery to external recipients, deployment and push are outside this task.
