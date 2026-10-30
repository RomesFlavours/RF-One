# RMAED.it candidate verification bridge

Approved scope: only Selection on AWS and the candidate entry files on
`www.rmaed.it`. Existing CV import and first-interview services are reused.

## Flow

1. `index.php` visits Selection's `/candidate/bridge/start` to bind the flow
   to an AWS browser session, then receives a signed state on RMAED.it.
2. PHP calls the timestamped HMAC-authenticated relay on Selection. AWS
   creates the existing candidate identity and email-code record. Only the
   authenticated PHP server receives the plaintext code for delivery.
3. PHP sends the code with authenticated SMTP from
   `RomesFlavoursCareers@RMAED.it` over verified TLS to `smtps.aruba.it:465`.
4. AWS checks the submitted code using the existing expiry, attempt and
   resend limits. It issues a random, short-lived, single-use ticket bound
   to the original browser session.
5. The browser returns to Selection, redeems the ticket with CSRF protection
   and continues as the verified external candidate. No staff permission is
   granted. A position-specific entry returns to that position; a generic
   entry lists open positions.

## Aruba upload

The generated upload ZIP contains exactly `index.html`, `index.php`,
`relay.php`, `config.php` and `cacert.pem`, with no enclosing directory. The generated PHP
configuration contains the relay key and SMTP credential and returns 404
when requested directly. Configuration values are never sent to the browser.
`relay.php` is similarly guarded. HTTPS is required by `index.php`.
The CA bundle is supplied explicitly to PHP cURL and SMTP; certificate
verification remains enabled. Candidates enter only their name, email and
the emailed code. Returning candidates use a fresh email code as well.
The legacy account password column is satisfied with an unknown random
value for new identities; no password field is shown or submitted by Aruba.

The SMTP credential is taken from the existing Windows DPAPI-protected
Selection configuration, not from Git. No writable root, local database,
Composer, JavaScript framework, FTP credential or external package is
required on Aruba. PHP sessions use the host's existing session storage.

## AWS release boundary

The release starts from the downloaded production `rfone-selection-source.zip`,
adds Selection's existing workspace/candidate implementation and only its
required data-store modules, then adds `workspace/aruba_bridge.py` and
`workspace/schema.py`. Unrelated local changes are excluded.

`workspace.schema.provision(connection)` creates only new tables whose names
start with `selection_workspace_` or `selection_candidate_`. Run it once in
a transaction after the database snapshot completes and before deploying the
image. It does not change existing tables/rows or the shared Alembic revision:
the current images of the other services remain restart-compatible.

Only the `rfone-selection` App Runner service receives the new image and the
`RFONE_SELECTION_ARUBA_KEY` runtime setting. There are no changes to IAM,
CloudFront, DNS, VPC routing or other App Runner services. No SMTP credential
is added to AWS; mail is sent by Aruba.

Source ZIP backup, tagged previous ECR image and an RDS snapshot are retained
for rollback. A rollback may restore the prior Selection image/configuration;
the additional tables may remain without affecting the prior application.

## Validation

- `test_aruba_bridge.py`: signed relay, wrong OTP, browser binding, CSRF,
  single-use ticket, OTP replay and staff-route isolation, all synthetic.
- `test_selection_workspace_http.py`: existing position, CV, first interview,
  resume, ownership and manager workflow, all synthetic and no email/AI.
- PHP 8.2 syntax validation of the Aruba files.
- Public AWS health/start routes and the deployed service operation are
  checked after release. Final Aruba SMTP delivery and root upload require
  the supplied mailbox credential and the actual uploaded files.

No position or job advertisement is invented by the bridge. At verification
time the production database contained no job postings or workspace positions;
a manager must open a position in Selection before candidates can apply.

## Release verified on 2026-10-26 (US Eastern)

- App Runner operation `7c5e1acaa38740ba85f9c6a40e6ba044`: `SUCCEEDED`.
- Public `/selection/candidate/bridge/health`: HTTP 200, version
  `rmaed-selection-bridge-1`, enabled.
- Browser-bound redirect targets `https://www.rmaed.it/index.php`.
- Live unsigned relay call rejected; signed read-only probe accepted through
  CloudFront. No candidate or verification code was created by the smoke test.
- Staff routes still redirect anonymous visitors to RF-One login.
- Shared Alembic revision remains `d5a120261021`.
- SMTP authentication with the specified RMAED.it mailbox succeeded over TLS;
  no test email was sent.
- Database snapshot: `rfone-dev-pre-selection-rmaed-20261026t235009z`.
- Previous image tag: `pre-rmaed-20261026T235009Z`.
- Upload archive: `output/RMAED-Selection-FINALE.zip` in the RF1 Sviluppo
  workspace; contains the four root files, including the authorized private
  configuration. Final hosting upload and actual code delivery are not yet
  verified because the user will upload the package.

## Passwordless revision

The candidate entry now uses name, email and an emailed code only, for both
new and returning identities. No password form is present on RMAED.it.
Existing verified identities retain their recorded names until authenticated;
requesting a new access code cannot edit them. Legacy registration/password
helpers remain compatible with their existing callers.

The upload archive for this revision is `RMAED-Selection-SOLO-CODICE.zip`.
It includes the explicit CA bundle for both outbound PHP connections.
The real PHP relay was tested against AWS with intentionally invalid input
and received the expected validation JSON over verified TLS. The generic
hosting error was reproduced on the previously uploaded Aruba files; the
updated files must be uploaded before that host can be rechecked.
