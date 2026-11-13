# Training students and the RF-One Registry

## Identity, qualification and access

`CandidatePerson` (`candidate_persons`) is the existing central person identity.
`person_account_links` connects a person to their RF-One login; `training_person_links`
connects the same person to their existing Training account. `person_qualifications`
stores the explicit `STUDENT` qualification independently of enabled Domain grants.
No employee is created and no employment is inferred from a Training permission.
The administrative People directory retains all persons, including students; its
employee links remain empty for student-only persons. Bank and Organization new
operational identity choices exclude student identities unless explicit employee
links exist. Existing assignments are preserved.

## Trainer workflow

`Invita studente` now supports direct invitation and currently confirmed Selection
candidates through the same activation page, without creating an account before
the recipient completes it. See [Enrollment](../Training/ENROLLMENT.md). The
generated-initial-password procedure below remains the full manual-entry path
under `Nuovo studente`; existing activation links remain compatible.

Open Training → Students as an authorized trainer. «Nuovo studente» asks only for
first name, surname, email and optional phone. The system then:

1. resolves the person in the one Registry (`student_registry.resolve`): possible
   matches by name, email or username require explicit confirmation; a match is
   evidence for review, never permission to merge different people. Conflicting
   owners or legacy Training usernames stop creation. Person, STUDENT
   qualification, login, Training identity and TRAINING/student access are saved
   in one transaction; no employee is created;
2. generates the username (`training_integration.generate_username`): first name
   plus the first three letters of the surname, each starting uppercase (Mario
   Rossi → `MarioRos`; a shorter surname uses the letters available). Accents are
   folded, spaces and apostrophes dropped. A name already used by an RF-One or
   legacy Training account gets the first free number (`MarioRos2`, …); existing
   accounts are never overwritten. Login normalization is unchanged: usernames
   are stored and compared in lowercase, so `MarioRos` signs in as `marioros`
   with any capitalization. The confirmation message shows the assigned name;
3. generates a random initial password (14 characters, upper/lower case and
   digits, no ambiguous characters) and marks the mandatory replacement;
4. after the commit, emails username, initial password and a personal activation
   link `<origin>/training/activation/<token>`.

The token is `secrets.token_urlsafe(32)`, stored only as an HMAC in the existing
`rfone_account_verification_codes` row (purpose `EMAIL_VERIFICATION`), bound to
the account and its email, single use and valid for 48 hours. No credential is in
the URL. A link may be forwarded, but it cannot be reused and alone it never signs
in. The 6-digit code page refuses link tokens.

When a confirmed match is an existing login, its username, password, status and
grants are preserved and no initial password is generated: verified accounts get
an access invitation; unverified existing accounts use the existing 6-digit
activation-code path. A disabled or incompatible TRAINING grant is not repaired.

Delivery failure does not undo the saved identity: use «Reinvia invito». For a
login created by this flow and never activated (unverified email, mandatory
replacement, Training-student only), resending issues a new initial password and
a new link and invalidates the previous ones; the original password is never
stored in clear. Resends are rate limited (60 seconds, 5 per hour).

## Learner activation, access and recovery

1. Open the personal link. The browser is redirected to `/training/activation`;
   any previous session in that browser ends and nothing is signed in.
2. Enter username and initial password. A wrong password, an expired/used link or
   another account's credentials give one generic refusal.
3. Choose and confirm a new password of at least eight characters, different from
   the initial one. Until this step completes the learner has no RF-One session:
   MyRF and modules redirect to sign-in. Initial credentials alone are refused on
   `/training/access`; a shared `/login` session with them is ended at once.
4. Completion consumes the link, verifies the email, replaces the password (the
   initial one stops working, older sessions are revoked), clears the mandatory
   replacement and opens MyRF (`/`) with only the authorized Domains, including
   Training.

Link origin: the official HTTPS origin from `RFONE_PUBLIC_BASE_URL`
(`public_entry.public_base_url`, recorded deployed value
`https://rfone.romesflavours.com`); when it is unset (official local launcher) the
origin of the trainer's request, e.g. `http://127.0.0.1:5098`, which works only on
the computer running Training. The local browser is never sent to production.

Forgot password requires the username and verified email. Its generic response
does not disclose whether an account exists. On the reset page enter username,
the emailed code and a new password twice. Codes are single-use, expire after ten
minutes and are invalidated after five wrong attempts. Changing the password revokes
previous sessions. A student who never activated asks the trainer to resend the
invitation. An archived student cannot access Training.

Archiving preserves person identity, qualification, assignments and results. For a
student with other grants it blocks Training and revokes old sessions while keeping
other grants and active account status. Trainer password editing is denied for
administrators and accounts with other enabled modules. A trainer-set new password
for an already activated student keeps using the first-access replacement page.

## Storage, migration and deployment

`t9b120261112` follows `k9b120261112`; it adds the two person-source link tables if
absent, explicit qualifications and Training-person links. It does not reconcile
historical students, alter credentials or grant permissions. `checkfirst=True`
does not validate an existing table's shape: a preflight must inspect columns,
foreign keys, uniqueness and the exact live revision. The downgrade deliberately
refuses destructive schema removal. Roll back application images and retain data.

See [AWS readiness and rollback plan](../Infrastructure/deploy/rfone-training/STUDENT_REGISTRY_RELEASE_PLAN.md).
Legacy students 6 and 7 require approved identity reconciliation, retaining their
Training IDs and history; do not use the new-student flow to duplicate them.

## Verification

`test_student_registry_local.py` checks, in a rolled-back canonical PostgreSQL
transaction: username rule and collisions (including legacy Training names),
initial password, Registry/STUDENT without employee, duplicate confirmation,
existing credentials/grants preserved, link alone / wrong password / another
account / token-as-code refused, mandatory different password, MyRF with only
Training, link reuse and expiry, resend invalidating old credentials, recovery,
delivery failure, mixed-role archive and the official HTTPS origin.
`test_student_registry_browser_local.py` drives the actual local pages with the
Microsoft Edge renderer through the whole flow, blocking non-loopback resources
and intercepting email. Both leave no test rows. SMTP interception proves message
generation, not remote SMTP acceptance or delivery to an inbox.
