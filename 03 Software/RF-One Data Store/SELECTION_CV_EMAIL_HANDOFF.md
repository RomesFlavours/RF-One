# Shelbi handoff — Connect Selection CV upload to the deployed RF-One Email Service

## Objective and current status

Connect Selection's successful CV upload/application submission event to the centralized RF-One Email Service so the candidate receives one acknowledgment of receipt.

**The central service and redesigned Email Control panel are deployed on AWS. This release does not implement the Selection CV upload auto-responder adapter.** The deployed worker is enabled: a committed production queue request is eligible for real sending. Develop and test against isolated databases with fake delivery until activation is explicitly authorized.

## Repository, branch and commits

| Reference | Value |
| --- | --- |
| Repository | `https://github.com/RomesFlavours/RF-One.git` |
| AWS release branch | `codex/rfone-email-service-aws` |
| Latest verified implementation and release-evidence checkpoint | `37f115478889674e417ab467f92c5e2ec7053a28` |
| Redesigned Email Control image source commit | `577705cb03db83b24409aa05d9ecd53a880ff38c` |
| Initial email-service deployment checkpoint | `e73ce8e87bc6e39f9a4f5cb89778a1e12617d60a` |
| SMTP worker image source commit — unchanged by the UI release | `7291a4ac84199680e0aa837666ff28bc307f0511` |
| Running Web image after the UI release | `rfone-web:email-ui-577705cb03db` |
| Production schema revision applied by this release | `e9a120261117` |
| Development-only revision — do not apply to production | `c7e5a3b9d201` |

Fetch the release branch and inspect the shared API:

```bash
git fetch origin codex/rfone-email-service-aws
git show 37f115478889674e417ab467f92c5e2ec7053a28:"03 Software/RF-One Data Store/rfone_data_store/email_service.py"
```

The branch also contains documentation-only updates. The checkpoint above pins the latest verified implementation and deployment evidence. Web UI and SMTP worker image source commits are listed separately because the UI refresh did not rebuild or redeploy the worker. Use the branch HEAD for the latest version of this handoff.

Work from Selection's current development/release branch. Do not replace Selection with the older RF-One Web baseline or merge the whole email release branch blindly. Reconcile only the shared module and canonical migration files that Selection needs, preserving its current upload, candidate identity and bridge behavior.

## What was deployed and verified

The initial service deployment completed on 17 November 2026 at 15:58:42 America/New_York. The redesigned Email Control panel was subsequently deployed at 16:37:25 America/New_York that day.

- Email API and administrative Email Control page in `rfone-web`.
- Four persistent tables: `email_requests`, `email_attempts`, `email_audit`, `email_worker_state`.
- Independent ECS service `rfone-email-service` in cluster `rfone-jobs`, desired/running count 1 at verification.
- Aruba SMTP over certificate-verified TLS through the existing private-subnet NAT path.
- Secrets Manager access restricted to the worker's SMTP task role; no SMTP credentials are required in Selection for this integration.
- A global worker interval of 10 seconds, persistent leasing and conservative crash recovery.

Release verification observed an empty central queue and an IDLE worker with a current heartbeat. PostgreSQL tests in a temporary schema covered concurrent deduplication, two workers, Domain isolation, retry and uncertain outcomes. Aruba TLS authentication and NOOP succeeded through NAT. **No MAIL, RCPT or DATA commands were issued by the connection check; no test email was sent.**

The initial service release passed 20 dedicated tests. The UI release passed the expanded suite of **23 tests**, both locally and inside the built Linux image. Browser checks covered the desktop register, attention filtering, message details, preserved list context and mobile layout. MyRF login, Training and Selection retained their observed public status/redirect behavior after both deployments.

Email Control: <https://rfone.romesflavours.com/administration/email>. An active RF-One administrator session is required. Unauthenticated checks returned 401 for the new administrative and API routes.

These are recorded deployment observations, not a claim of continuously monitored health. Recheck the worker and queue before activation.

## Redesigned Email Control panel

Open [Email Control](https://rfone.romesflavours.com/administration/email) from RF-One → Administration → Email Control, using an active RF-One administrator session.

The panel is now an operational view rather than a list of internal queue states:

- **Compact summary:** total messages, in progress, accepted by Aruba and needs attention. Summary tiles link to the corresponding message lists.
- **Readable register:** subject, recipient, Domain, status and requested time, with 25 messages per page.
- **Search and filters:** recipient or subject, Domain, status and date range. Date filters use inclusive local civil days in the displayed Location timezone.
- **Attention queue:** one click shows failed requests and uncertain outcomes, each with a **Review** action.
- **Message details:** content, current outcome, permitted next action and chronological activity. The **Technical details** disclosure contains the request UUID, originating event and SMTP error codes.
- **Context preservation:** returning from a detail page retains the list's search/filter context and links back to the message row.
- **RF-One styling:** olive palette, shared typography and breadcrumbs, responsive desktop/mobile layout and keyboard focus indicators.

Available administrative actions remain constrained by the central service:

| Message state | Panel action |
| --- | --- |
| Waiting or retry scheduled | **Cancel this email** |
| Failed | Review the issue, then **Authorize another attempt** if appropriate |
| Outcome uncertain | Reconcile with Aruba; no resend button is offered |
| Sending, accepted or cancelled | Inspect details; no resend/cancel action is offered for that state |

**Accepted by Aruba is SMTP acceptance, not confirmed recipient delivery.** The redesign does not change queue semantics, authorization or retry policy. Its local-day date controls are UI behavior; do not infer a change to the HTTP API's date-filter contract.

For Shelbi's authorized end-to-end verification after connecting the CV adapter:

1. Filter the register to Selection's confirmed Domain code and search for the approved canary recipient or receipt subject.
2. Open the request and check its subject, recipient and content.
3. Expand **Technical details** to match the queue request UUID and originating event to the saved submission.
4. Inspect activity and sending attempts. Allow automatic temporary-error retries instead of creating a second request.
5. Review **Needs attention** if the outcome is failed or uncertain; do not bypass uncertainty with a new deduplication key.
6. Record SMTP acceptance separately from any independently confirmed receipt by the candidate/test recipient.

The UI release changed no production schema and did not redeploy or reconfigure the SMTP worker. No production test requests were enqueued. Authenticated rendering was verified with isolated test sessions; the production HTTP check verified that the panel remains protected with 401 without authentication.

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
| `03 Software/RF-One Web/email_routes.py` | HTTP API, administrative queries, readable statuses and safe list return context. |
| `03 Software/RF-One Web/templates/_email_layout.html` | Shared Email Control layout and display macros. |
| `03 Software/RF-One Web/templates/email_control.html` | Redesigned summary, filters and message register. |
| `03 Software/RF-One Web/templates/email_detail.html` | Message content, activity, permitted actions and technical disclosure. |
| `03 Software/RF-One Web/static/css/email-control.css` | Scoped RF-One visual styling and responsive layouts. |
| `03 Software/RF-One Web/tests/test_email_service.py` | Dedicated email regression suite. |
| `03 Software/Infrastructure/deploy/rfone-email/README.md` | Release tooling and rollback procedure. |
| `03 Software/Infrastructure/deploy/rfone-email/RELEASE_REPORT.md` | Initial central-service AWS deployment evidence. |
| `03 Software/Infrastructure/deploy/rfone-email/UI_RELEASE_REPORT.md` | Redesigned panel deployment evidence, validation and UI-only rollback. |
| `03 Software/Infrastructure/deploy/rfone-email/deploy_ui.py` | UI-only release tooling; not required to implement the Selection adapter. |

[GitHub release branch](https://github.com/RomesFlavours/RF-One/tree/codex/rfone-email-service-aws)

[Latest verified implementation and deployment checkpoint](https://github.com/RomesFlavours/RF-One/commit/37f115478889674e417ab467f92c5e2ec7053a28)

[AWS deployment report](https://github.com/RomesFlavours/RF-One/blob/codex/rfone-email-service-aws/03%20Software/Infrastructure/deploy/rfone-email/RELEASE_REPORT.md)

[Email Control UI release report](https://github.com/RomesFlavours/RF-One/blob/codex/rfone-email-service-aws/03%20Software/Infrastructure/deploy/rfone-email/UI_RELEASE_REPORT.md)
