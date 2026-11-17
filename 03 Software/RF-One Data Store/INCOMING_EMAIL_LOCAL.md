# RF-One incoming email — phase 1 local implementation

Implemented on branch `codex/email-incoming-local`, based on the deployed
email-service branch. This work is local only: no AWS deployment, production
migration, production mailbox connection or real message send was performed.

## Available behavior

Email Control has three views: Outgoing, Mailboxes and New arrivals.
An authenticated RF-One user can add and edit their own IMAP mailbox settings,
pause/resume monitoring, request a background check and inspect check history.
Regular users can manage their own incoming mailboxes; outgoing administrative
controls retain their existing administrator requirement. Administrators do
not automatically gain access to another user's incoming mailboxes or headers.

The independent incoming monitor polls configured, enabled mailboxes whose
owners have an active RF-One identity. Canonical identity revocation is checked before credentials are read; monitoring is paused if access has been revoked. Closing the browser does not stop checking. The web request
only saves configuration or schedules work; it does not connect to IMAP.

The first successful check sets a starting point using UIDVALIDITY and UIDNEXT.
Existing messages are not imported. Later checks record new headers regardless
of whether a person has already read the message in their mail app.

Recorded metadata: sender, recipient, subject, Message-ID when present,
sender-supplied message date, size and RF-One detection time. Bodies and
attachments are not fetched, stored or interpreted. No AI calls, action
extraction, automated replies or configured action execution are implemented.

## Start the local application

From this worktree's repository root:

```powershell
python -B '03 Software/RF-One Web/run_email_control_local.py' --port 8769 --timezone America/New_York
```

Open <http://127.0.0.1:8769/administration/email/mailboxes>.
Choose **Connect a mailbox**, enter its display name, email address, IMAP host,
sign-in username and mailbox/app password. INBOX and a 60-second interval are
the defaults. The worker starts automatically with the local application.

The dedicated loopback application needs no login or signature and adds no
environment banner. It has one local sandbox principal; it does not bypass
authentication in the normal RF-One Web application. HTTP CSRF and trusted-host
checks still apply. This launcher is a local development entry point, not a
production server.

Its private database is `%LOCALAPPDATA%/RF-One/email-control-local.db`.
No `.env` database URL is resolved. The sandbox and receiver opt into immediate SQLite transactions so UI changes and background checks serialize safely; the default engine behavior and PostgreSQL are unchanged. An existing unrelated database is refused
without changing its tables. The normal operational `data/rfone.db` is refused.
The sandbox creates only the tables this local application needs and carries
its own sandbox schema marker, not a misleading full canonical Alembic stamp.

The timezone flag controls display and does not change stored UTC timestamps.
When omitted, UTC is explicitly labelled rather than guessing a Location zone.

For a separate fictional preview:

```powershell
python -B '03 Software/RF-One Web/run_email_control_local.py' --port 8770 --database "$env:TEMP/rfone_email_incoming_preview.db" --timezone America/New_York --demo --no-monitor
```

Demo mailboxes use example.test addresses, are paused and have no real credentials.
No outgoing SMTP worker is started by the local launcher.

## Configuration and credentials

Supported in this phase: public IMAP servers on TLS port 993, with username and
mailbox password or provider-specific app password. Aruba defaults to
`imaps.aruba.it`; incoming connections are not restricted to Aruba. Outgoing
Aruba SMTP configuration and behavior are unchanged.

Local passwords are protected with Windows DPAPI in
`%LOCALAPPDATA%/RF-One/mailbox-secrets`, outside the repository and database.
The database contains only random opaque references. Passwords are not echoed
in forms, audit records or logs. Replacing a password rotates its reference;
failed saves remove the newly created credential and retain the original one.
Changing the server or sign-in username requires a newly entered password, so an existing hidden credential cannot be redirected to another server. Web process and monitor must run as the same Windows user.

No secret is created or accessed in AWS during this phase. For a future Linux/
AWS deployment, replace the local vault backend with a scoped Secrets Manager
implementation and an appropriate credential-management flow. DPAPI files must
not be copied into AWS images or treated as portable secrets.

TLS certificate/hostname verification is mandatory, with TLS 1.2 minimum.
Server addresses are resolved, checked for public routability and pinned for
the connection, while preserving the configured hostname for certificate
verification. Private, loopback and link-local destinations are rejected.

## Read-only polling and recovery

- IMAP folders are opened read-only. FETCH requests use BODY.PEEK for a bounded
  selection of headers, never full messages, text parts or attachments.
- There are no flag changes, message moves, deletions or SMTP operations.
- Every mailbox has an atomic database lease and a configuration-version fence.
  Multiple monitors cannot commit the same claimed work twice.
- Network work happens outside the database transaction. Cursor advancement
  and arrival inserts commit together, with a uniqueness constraint.
- Identity is mailbox + configuration generation + UIDVALIDITY + UID. Changing
  server, sign-in identity or folder starts a new generation and baseline.
- A UIDVALIDITY change restarts monitoring from the current latest message and
  records an explanatory status; historical headers already recorded are kept.
- A mid-check UIDVALIDITY change discards the batch. Partial failures leave the
  cursor unchanged so the next attempt can safely repeat the read.
- Checks fetch at most 20 headers per batch. Remaining backlog is scheduled
  promptly without skipping later UIDs. Socket operations have 10-second timeouts;
  expired 300-second leases can be reclaimed after a process interruption.
- Pausing prevents future checks and invalidates an in-flight result. An IMAP
  read already in progress may finish, but it cannot advance the paused mailbox.
- Failed checks use bounded backoff. Authentication failures wait one hour
  before another automatic attempt; corrected settings or Check now can schedule
  an earlier check. Errors are fixed categories, never raw provider replies.

## Data and implementation

New local migration: `i9a120261117`, parent `e9a120261117`.
It is **not applied to AWS**; the production schema registry remains unchanged.

| Table | Purpose |
| --- | --- |
| `email_mailboxes` | Owner, public settings, credential reference, scheduling, generation, cursor and lease |
| `email_arrivals` | Header metadata with durable per-mailbox identity and detection time |
| `email_mailbox_checks` | Start/end, fixed outcome/error and count of newly recorded arrivals |
| `email_mailbox_audit` | Owner's add/edit/pause/resume/manual-check operations |

The existing `email_worker_state` table is reused: row 1 remains outgoing SMTP;
row 2 records the incoming monitor's heartbeat. The migration seeds row 2 and
does not change the outgoing queue, attempts, audit or worker configuration.

Reused RF-One components: Base metadata, engine/session factories, existing
RF-One accounts and session revocation, CSRF helper, UTC/local formatting,
breadcrumbs, shared CSS palette, row-return behavior and the outgoing worker's
atomic claim/fencing pattern. The read-only UID convention from the existing
Invoice Intake IMAP connector was reviewed and reused as a reference. A
header-only shared adapter was added because Invoice Intake's acquisition
adapter fetches complete messages and attachments, which this phase excludes.

Created files, relative to `03 Software`:

- `RF-One Data Store/rfone_data_store/incoming_email.py`
- `RF-One Data Store/rfone_data_store/incoming_email_worker.py`
- `RF-One Data Store/rfone_data_store/technical/imap_mailbox.py`
- `RF-One Data Store/rfone_data_store/technical/mailbox_credentials.py`
- `RF-One Data Store/migrations/versions/i9a120261117_incoming_email_monitoring.py`
- `RF-One Data Store/INCOMING_EMAIL_LOCAL.md`
- `RF-One Web/incoming_email_routes.py`
- `RF-One Web/run_email_control_local.py`
- `RF-One Web/templates/email_mailboxes.html`
- `RF-One Web/templates/email_mailbox_form.html`
- `RF-One Web/templates/email_mailbox_checks.html`
- `RF-One Web/templates/email_incoming.html`
- `RF-One Web/tests/test_incoming_email.py`

Updated: the engine factory with an opt-in local SQLite transaction mode, migration metadata registration, RF-One Web route registration and Home
link, shared Email Control layout/navigation/CSS, outgoing template navigation
and its isolated test harness. Touched integration source files use explicit
UTF-8 handling to preserve existing punctuation and displayed text.

## UI routes and standalone monitor

| Route | Behavior |
| --- | --- |
| GET `/administration/email/mailboxes` | Current user's mailboxes, status, counts and controls |
| GET/POST `/administration/email/mailboxes/new` | Add mailbox and protected credentials |
| GET/POST `/administration/email/mailboxes/{id}/edit` | Edit owned settings; optionally rotate password |
| POST `/administration/email/mailboxes/{id}/{pause,resume,check}` | Authorized, CSRF-protected operations |
| GET `/administration/email/mailboxes/{id}/checks` | Owned mailbox check and configuration history |
| GET `/administration/email/incoming` | Owned arrival register, mailbox filter and sender/subject search |

Foreign mailbox identifiers return 404 without exposing existence or headers.
The standard application uses the existing active/revocable RF-One session.

The monitor can also be started independently against an explicitly chosen
local database whose incoming schema has been prepared:

```powershell
# Run from 03 Software/RF-One Data Store.
python -B -m rfone_data_store.incoming_email_worker --database-url sqlite:///C:/path/to/private.db --run
```

Without `--run` it is a dry-run and never connects to a mailbox. `--once`
performs one iteration. The monitor never reads `.env`, creates schema or
automatically applies canonical migrations at startup.

## Validation

```powershell
python -B '03 Software/RF-One Web/tests/test_incoming_email.py'
python -B '03 Software/RF-One Web/tests/test_email_service.py'
python -B '03 Software/RF-One Web/tests/test_startup_no_migration_no_write.py'
python -B '03 Software/RF-One Data Store/check_migration_chain.py' --aws-revision e9a120261117
```

27 incoming tests and 23 existing outgoing tests pass (50 total). They cover
initial baselining, new arrivals, replay deduplication, batches, mailbox reset,
configuration generations, failures and credential loss, concurrent workers,
pause fencing, crash/restart, inactive/revoked identities, credential redirection protection, owner isolation, CSRF, session
revocation, password rotation and failed-save cleanup, escaped headers, read-only
PEEK commands, public-server validation, Windows DPAPI round-trip, migration
round-trip, dry-run behavior, local login-free access and unrelated-DB protection.

Four additional startup checks pass, confirming that normal RF-One Web imports perform no migrations or database writes.

The migration chain has one head and contains the currently recorded AWS
revision as an ancestor. No shared schema marker was advanced.

Browser checks used only the local sandbox and fictional paused preview records:
mailbox setup, mailbox cards, arrival register, metadata disclosure and mobile
layout. A real independent local monitor was started against an empty private
sandbox and its heartbeat checked. No real mailbox credential was supplied;
live provider authentication and real-arrival detection remain to be verified
when the user configures a mailbox locally.

Protocol references:
[Python imaplib](https://docs.python.org/3.14/library/imaplib.html) and
[IMAP RFC 9051](https://www.rfc-editor.org/rfc/rfc9051.html).

## Limits and next steps

OAuth-only providers, private IMAP hosts, nonstandard ports, non-ASCII folder
names, historical imports, shared-mailbox delegation and permanent disconnection/
retention tooling are not implemented. Monitoring can be paused and settings
can be changed without deleting the provider's messages.

AI reading, body/attachment acquisition, chat-configured rules, action proposals
and action execution remain separate future work. The stable arrival ID and
source UID identity provide the boundary for that work without doing it now. Future content retrieval must recheck the current configuration generation and UIDVALIDITY; retained headers can outlive an old connection identity.

A future AWS release needs explicit authorization, a snapshot and staging
validation of the additive migration, a production vault backend, and a dedicated
receiver process with least-privilege secret access. It must preserve the current
outgoing deployment and existing Selection/Training/MyRF flows. This branch
contains none of those production mutations.
