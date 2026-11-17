# Shelbi handoff — Connect Selection CV upload to the deployed RF-One Email Service

## Objective and current status

Connect Selection's successful CV upload/application submission event to the centralized RF-One Email Service so the candidate receives one acknowledgment of receipt.

**The central service is deployed on AWS. The CV upload auto-responder integration is still to be implemented.** The deployed worker is enabled: a committed production queue request is eligible for real sending. Develop and test against isolated databases with fake delivery until activation is explicitly authorized.

## Repository, branch and commits

| Reference | Value |
| --- | --- |
| Repository | `https://github.com/RomesFlavours/RF-One.git` |
| AWS release branch | `codex/rfone-email-service-aws` |
| Verified code and deployment-evidence checkpoint | `e73ce8e87bc6e39f9a4f5cb89778a1e12617d60a` |
| Source commit used to build the running email image | `7291a4ac84199680e0aa837666ff28bc307f0511` |
| Production schema revision applied by this release | `e9a120261117` |
| Development-only revision — do not apply to production | `c7e5a3b9d201` |

Fetch the release branch and inspect the shared API:

```bash
git fetch origin codex/rfone-email-service-aws
git show e73ce8e87bc6e39f9a4f5cb89778a1e12617d60a:"03 Software/RF-One Data Store/rfone_data_store/email_service.py"
```

The release branch contains later documentation updates as well. The checkpoint above pins the deployed implementation and its recorded AWS evidence; the image source commit identifies the exact build input.

Work from Selection's current development/release branch. Do not replace Selection with the older RF-One Web baseline or merge the whole email release branch blindly. Reconcile only the shared module and canonical migration files that Selection needs, preserving its current upload, candidate identity and bridge behavior.

## What was deployed and verified

Deployment completed on 17 November 2026; RF-One Web's update completed at 15:58:42 America/New_York.

- Email API and administrative Email Control page in `rfone-web`.
- Four persistent tables: `email_requests`, `email_attempts`, `email_audit`, `email_worker_state`.
- Independent ECS service `rfone-email-service` in cluster `rfone-jobs`, desired/running count 1 at verification.
- Aruba SMTP over certificate-verified TLS through the existing private-subnet NAT path.
- Secrets Manager access restricted to the worker's SMTP task role; no SMTP credentials are required in Selection for this integration.
- A global worker interval of 10 seconds, persistent leasing and conservative crash recovery.

Release verification observed an empty central queue and an IDLE worker with a current heartbeat. PostgreSQL tests in a temporary schema covered concurrent deduplication, two workers, Domain isolation, retry and uncertain outcomes. Aruba TLS authentication and NOOP succeeded through NAT. **No MAIL, RCPT or DATA commands were issued by the connection check; no test email was sent.**

Twenty dedicated local tests passed on the AWS release source baseline. MyRF login, Training and Selection retained their observed public status/redirect behavior after deployment.

Email Control: <https://rfone.romesflavours.com/administration/email>. An active RF-One administrator session is required. Unauthenticated checks returned 401 for the new administrative and API routes.

These are recorded deployment observations, not a claim of continuously monitored health. Recheck the worker and queue before activation.

## Find the correct upload integration point

Inspect the actual current Selection code before editing. The operational environment has an existing `selection_workspace_email_outbox`, Aruba transport configuration and an RMAED bridge. The original development checkout did not contain those components; its initial missing-component findings are superseded by the AWS inspection.

Identify:

1. Every public CV/application intake route, including submissions arriving through RMAED or another bridge.
2. The server-side service that persists a successfully accepted application and its CV reference.
3. The existing receipt-email trigger and the consumer of `selection_workspace_email_outbox`, if that trigger is already present.
4. Selection's registered Domain code and durable submission/application identifiers.
5. The current transaction boundary and the handling of an uploaded document if the database transaction fails.

Prefer one hook in the shared successful-submission service. Do not independently enqueue in both a bridge route and its downstream application service. A candidate verification code, CV parsing completion and successful application receipt are different events; the acknowledgment belongs to successful receipt.

Do not change Wix, public website configuration, candidate authentication or the existing bridge protocol to add this notification.

## Transactional integration pattern

Use the internal Python API with Selection's existing SQLAlchemy session. This avoids a second web session, HTTP authentication and a distributed transaction.

The following is an adapter pattern, not an existing Selection function or field mapping:

```python
from rfone_data_store import email_service

# Inside the existing transaction that successfully saves the application.
# Resolve these values from Selection's real durable submission model.
db.flush()  # Obtain the persistent submission ID if the database assigns it.

receipt = email_service.enqueue(
    db,
    domain="SELECTION",  # Verify this against the actual RF-One Domain registry.
    recipient=receipt_recipient,
    subject=receipt_subject,
    body=receipt_text,
    event=f"selection.cv_received:{submission_id}",
    dedup_key=f"cv_received:{submission_id}:v1",
)

# If the application already has a suitable event/reference field, retain
# receipt.id there. Do not introduce a production column without a reviewed migration.
# The existing caller commits or rolls back BOTH business data and the queue.
```

Requirements:

- Enqueue after the application and CV reference have been saved successfully, before the enclosing transaction commits.
- Do not add an internal commit to the notification helper.
- A database rollback must remove the email request along with the new application data.
- Do not run SMTP or wait for the worker inside the upload request.
- An SMTP failure after commit must not invalidate the saved application.
- Preserve the established document-storage cleanup/recovery behavior if a database transaction fails.

`enqueue` requires `domain`, `recipient`, `subject`, `body`, `event` and `dedup_key`. It returns an `EmailRequest` with its UUID. The central service uses its configured sender; there is no per-request sender or credential parameter.

The internal Python API assumes trusted server code. Do not expose arbitrary enqueue fields directly to an anonymous upload client; Selection must derive the Domain, event, key and acknowledgment text server-side.

## Idempotency and acknowledgment content

Use the durable identity of the accepted submission, not a request timestamp or a new random UUID on each retry. Repeated processing of the same business submission must reuse the same key. If Selection creates a new submission record for every HTTP retry, fix or reuse its intake idempotency mechanism first; email deduplication alone cannot identify those records as the same event.

Uniqueness is enforced on `(domain, dedup_key)`. Reusing the key with an identical payload returns the existing request. Reusing it with different content is rejected. Keep the receipt's recipient and content stable for a replay; do not regenerate timestamps, mutable candidate details or changing template text under an existing key. Keep an existing queue reference/payload snapshot where the current model supports it.

A genuinely new application may generate a new acknowledgment according to Selection's business rules. Do not use the candidate's email address or CV hash alone as the event identity: either can appear across separate legitimate submissions.

The acknowledgment confirms receipt only. It must not imply a positive assessment, shortlisting or an interview. Agree the final wording and language before activation. Do not attach the CV or include unnecessary personal data.

## Prevent duplicate sending during migration

There must be one active receipt-email path for a given submission event.

- Determine whether the legacy outbox already holds receipt notifications for the same events.
- Add an explicit integration switch using Selection's established configuration conventions; a switch for this integration has not yet been implemented.
- During local testing, use isolated databases and fake transports. Do not test by enqueueing against the shared production queue: its worker is active.
- Before switching the receipt trigger, reconcile legacy pending, accepted and uncertain records with central request IDs/event keys.
- Disable the old receipt trigger/consumer for the transferred events before enabling the new one. Preserve other notifications and verification-code flows.
- Do not import old requests as new unsent requests without reconciling their sending history.

Do not delete the legacy outbox or remove RMAED as part of this initial hookup.

## Status and administration

| Status | Meaning and required handling |
| --- | --- |
| `QUEUED` | Persisted and waiting for the worker. |
| `SENDING` | Processing has started. |
| `RETRY` | A temporary failure is scheduled for another attempt. |
| `ACCEPTED` | Accepted by the SMTP server; recipient delivery is not confirmed. |
| `FAILED` | Terminal failure; an authorized administrator may request a controlled resend. |
| `UNCERTAIN` | Acceptance could not be determined; automatic and manual resubmission are blocked. |
| `CANCELLED` | A pending request was cancelled. |

Never create a fresh key to bypass an uncertain outcome. Reconcile with Aruba and obtain an explicit decision before requesting a genuinely new message. Worker crash recovery can take up to the 300-second lease period.

The service does not implement recipient delivery confirmation, bounce/DSN handling or attachments. A saved CV must not be presented as emailed/delivered merely because its acknowledgment is QUEUED or ACCEPTED.

HTTP endpoints also exist under `/api/email/{domain}/requests` for enqueue, history, detail, cancellation and controlled resend. They require an active RF-One session, Domain access and CSRF on mutations. They are not an anonymous upload API or a machine-token API. Use the internal transactional Python API for this server-side integration.

## Tests required for the Selection adapter

Use disposable databases and fake delivery to verify:

- A successful accepted submission creates one central request with the correct recipient and server-generated event.
- Replaying the same submission, including concurrent retries, creates no duplicate.
- Failed uploads and rejected applications do not enqueue a receipt.
- Rolling back application persistence also rolls back enqueueing.
- An accepted submission arriving through the bridge does not enqueue twice.
- Frozen payloads remain identical across event retries.
- Temporary failures retry; permanent failures become FAILED; uncertain outcomes never auto-resubmit.
- Worker unavailability does not make a committed upload depend on the web session.
- Another Domain cannot read or change Selection requests through the HTTP API.
- Switching the receipt integration off preserves existing intake behavior without reactivating duplicate legacy work.

For the service regression suite:

```bash
python "03 Software/RF-One Web/tests/test_email_service.py"
```

## Schema, rollout and rollback

Production already has `e9a120261117`. Do not rerun the email migration, apply `c7e5a3b9d201`, or run an older branch's `alembic upgrade head` against the shared database. Reconcile the canonical migration chain before any future schema-aware release. Normal service startup must not migrate.

The original migration sequence remains Training → Selection → MyRF → other Domains. Deployment of the shared service did not migrate those callers. Confirm readiness of the Selection activation within that sequence; do not assume Training migration is complete.

Implement and test the adapter locally first. Selection deployment, activation of real receipt requests and a real test email require explicit authorization for that step. The previous authorization deployed the shared service; it did not activate this CV acknowledgment flow.

For an authorized activation, recheck worker health, central and legacy queues, Domain code, stable event identity and final wording. Use one approved canary recipient and inspect the request in Email Control. Record SMTP acceptance separately from any independently confirmed receipt.

Adapter rollback: disable the new Selection receipt trigger, reconcile QUEUED/RETRY requests and cancel eligible pending requests through the authorized service operations before restoring any legacy receipt path. Do not resend ACCEPTED or UNCERTAIN messages. Preserve application data and both audit histories.

Central-service rollback is a separate operation documented in the AWS release report; do not roll back the shared service merely to disable the Selection adapter.

## Files and deployment evidence

| Repository path | Purpose |
| --- | --- |
| `03 Software/RF-One Data Store/rfone_data_store/email_service.py` | Shared transactional queue API and models. |
| `03 Software/RF-One Data Store/rfone_data_store/email_worker.py` | Independent worker, lease, rate limiting and retries. |
| `03 Software/RF-One Data Store/rfone_data_store/technical/aruba_smtp.py` | Aruba transport and secret loading. |
| `03 Software/RF-One Data Store/migrations/versions/e9a120261117_shared_email_service_aws.py` | Canonical email migration already applied on AWS. |
| `03 Software/RF-One Data Store/migrations/aws_applied_revision.json` | Recorded shared schema revision and evidence. |
| `03 Software/RF-One Web/email_routes.py` | HTTP API and administrative routes. |
| `03 Software/RF-One Web/tests/test_email_service.py` | Dedicated email regression suite. |
| `03 Software/Infrastructure/deploy/rfone-email/README.md` | Release tooling and rollback procedure. |
| `03 Software/Infrastructure/deploy/rfone-email/RELEASE_REPORT.md` | Actual AWS deployment evidence. |

[GitHub release branch](https://github.com/RomesFlavours/RF-One/tree/codex/rfone-email-service-aws)

[Verified deployment checkpoint](https://github.com/RomesFlavours/RF-One/commit/e73ce8e87bc6e39f9a4f5cb89778a1e12617d60a)

[AWS deployment report](https://github.com/RomesFlavours/RF-One/blob/codex/rfone-email-service-aws/03%20Software/Infrastructure/deploy/rfone-email/RELEASE_REPORT.md)
