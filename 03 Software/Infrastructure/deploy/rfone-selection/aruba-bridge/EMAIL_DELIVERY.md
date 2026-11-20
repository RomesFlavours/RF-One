# Selection communications through RMAED

AWS owns message preparation, explicit approval, recipient selection, queue,
appointments, retry state and history. Aruba owns only SMTP transport from
`RomesFlavoursCareers@RMAED.it`. The SMTP password stays on Aruba.

## Included workflows

- Interview invitations and proposed time links.
- Confirmation when a candidate selects an appointment time.
- Cancellation notices prepared for the manager to approve and send.
- Menu-study invitations using the existing public training menu.
- Offers, rejection notices, on-hold notices and custom communications.

Drafts and previously approved messages are not sent in bulk or silently.
The manager selects **Approve and send**, or sends an already approved
message. Only candidate-confirmed appointment confirmations are queued
automatically. Existing approval-only behavior remains available.

## State and transport

`selection_workspace_email_outbox` is a new Selection-only table. Existing
tables, records and shared Alembic revision remain unchanged. Message IDs and
source keys deduplicate repeated clicks and appointment submissions.

Aruba claims one ready item using a short lease, acknowledges the start,
sends SMTP and returns the acceptance receipt. HTTP calls use the existing
timestamped HMAC and verified TLS. The queue records server acceptance,
not guaranteed inbox delivery or whether a candidate has read the message.

Temporary failures before acceptance back off, at most three attempts.
A lost/ambiguous result after sending is marked UNKNOWN, never automatically
resent. The manager can explicitly retry after checking. Receipt retries
are idempotent. Recipients, body and credentials are absent from worker logs.

`mail-worker.php` requires an authenticated POST; GET and unsigned POST are
refused. Its authenticated health operation does not claim messages or send
mail. It uses the existing protected `config.php` and `cacert.pem`; no new
Aruba database, writable directory or SMTP setup is needed.

## Proposed wake-up infrastructure

The Selection App Runner VPC cannot reach public SMTP or RMAED directly.
The dedicated `rfone-selection-mail-worker` Lambda runs outside the VPC and
only wakes `https://www.rmaed.it/mail-worker.php`. It has no database/S3
access or SMTP credentials. The execution role permits writing only to its
own CloudWatch log group. An EventBridge rule invokes it once per minute.
Its invocation policy is restricted to that rule in the current account.

Resource creation/activation requires the user's explicit approval of this
infrastructure. The schedule is created DISABLED and is enabled only after
both the uploaded PHP health check and Selection version 3 are verified.
Other RF-One services, VPC routing, DNS and domains are not changed.

## Validation and rollback

Synthetic HTTP tests cover approval before queueing, repeated clicks,
verified recipient resolution, authenticated claims, exclusive leases,
receipt ordering/idempotence, retry backoff, ambiguous outcome handling,
explicit manager retry, and a single confirmation after booking refresh.
CV, interview, candidate/staff access and manager workflows remain tested.
Tests never send real messages.

Source ZIP and ECR image are backed up before release. An RDS snapshot is
required before provisioning the outbox. Rollback: disable the dedicated
schedule, restore the previous Selection image, and retain the outbox table
and rows for investigation. The previous image tolerates the extra table.

## Current release state

- Selection deployment `23349bd7c3eb4849bc98ed9ef493b3c6` succeeded.
- Public bridge version is `rmaed-selection-bridge-3`.
- Live mail API authentication and validation checks passed without claiming
  a message. The production outbox was empty at the read-only audit.
- Synthetic application/mail tests and PHP transport tests passed.
- Shared Alembic revision remains `d5a120261021`.
- Snapshot: `rfone-dev-pre-selection-mail-20261027t002909z`.
- Upload package: `RMAED-Aggiornamento-Email.zip` (only `relay.php` and
  `mail-worker.php`). The uploaded authenticated health check now passes.
- The user explicitly authorized the dedicated Lambda, EventBridge schedule
  and logs-only IAM role. All three were created successfully. The Lambda
  is Active and the EventBridge schedule is ENABLED (one check per minute).
  A complete Lambda → RMAED → Selection outbox invocation succeeded with
  HTTP 200, returning `processed: 0, result: idle`; no test email was sent.

Activation is complete. For future health checks use `probe_mail_host.py`
and `setup_mail_worker.py status`. Do not send a test to a real candidate.
