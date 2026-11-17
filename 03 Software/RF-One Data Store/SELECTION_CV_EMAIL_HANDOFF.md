# Handoff to Shelbi — RF-One Email Service and Selection CV Upload Auto-Responder

AWS release note: the missing-component findings below describe the original
development checkout. Subsequent AWS inspection confirmed an existing NAT,
Aruba SMTP configuration and the operational Selection outbox. The additive
AWS release is maintained on `codex/rfone-email-service-aws`; see
`03 Software/Infrastructure/deploy/rfone-email/README.md` and its release report
for deployment evidence. The CV upload integration remains a separate step.

The centralized RF-One Email Service has been implemented and tested locally. It provides the foundation for sending an automatic acknowledgment after a candidate uploads a CV.

**The email service is implemented locally. The CV upload auto-responder has not yet been connected to the upload workflow.**

## 1. Available components

- A shared API for enqueueing email, checking status and history, cancelling pending requests, and manually resubmitting failed messages.
- A persistent queue in the RF-One database, with deduplication, status tracking, attempt counts, and timestamps.
- A standalone worker that sends through Aruba SMTP.
- An **Administration → Email Control** page with search, errors, attempt details, administrative operations, and worker status.
- SMTP credentials retrieved by the worker from AWS Secrets Manager.

Email processing does not depend on the candidate's or operator's web session.

## 2. Required CV auto-responder integration

Implement the following workflow:

1. Selection receives and successfully saves the CV and its associated application.
2. Selection enqueues the acknowledgment within the same database transaction.
3. The commit persists both the application and the email request.
4. The standalone worker subsequently sends the message through Aruba.
5. Email Control exposes the processing outcome.

The acknowledgment must confirm receipt only. It must not imply a positive assessment, shortlisting, or an interview invitation.

The upload HTTP request must not wait for SMTP delivery.

## 3. Integration contract

The internal Python API is available as follows:

```python
from rfone_data_store import email_service

email_service.enqueue(
    db,
    domain="SELECTION",
    recipient=candidate_email,
    subject="Application received",
    body=confirmation_text,
    event=f"selection.cv_received:{submission_id}",
    dedup_key=f"cv_received:{submission_id}:v1",
)
```

This is an **integration example**, not code already installed in the upload workflow. Shelbi must verify the registered Domain code and use the actual persistent application or submission identifier.

The caller owns the transaction commit or rollback. Use the same database session as the application-saving operation to preserve atomicity.

The deduplication key must remain stable when the same operation is retried. Do not generate a new random key for each attempt. Reusing a key with different message content is rejected.

The sender address and Aruba credentials belong to the centralized service. Do not add SMTP credentials or a separate SMTP sender to Selection.

## 4. Processing outcomes

| Status | Meaning |
| --- | --- |
| `QUEUED` | The request has been persisted. |
| `SENDING` | A send attempt is in progress. |
| `RETRY` | A temporary failure occurred and another attempt is scheduled. |
| `ACCEPTED` | The SMTP server accepted the message. |
| `FAILED` | Sending failed. |
| `UNCERTAIN` | SMTP acceptance could not be determined reliably. |
| `CANCELLED` | The request was cancelled. |

**`ACCEPTED` does not mean delivered to the recipient.** Recipient delivery and bounce tracking are not implemented.

Messages with uncertain outcomes are excluded from automatic and manual resubmission. An interrupted worker leaves an in-progress request to be recovered conservatively as uncertain once its lease expires. Reconcile the outcome before authorizing a new message.

## 5. Completed validation

The following checks passed:

- **20 dedicated email service tests.**
- **38 RF-One account and Domain access regression checks.**
- **4 startup checks confirming that startup does not run migrations or write to the database.**

Local coverage includes enqueueing, deduplication, concurrent workers, concurrent enqueueing, temporary and permanent failures, retries, retry exhaustion, uncertain outcomes, worker restart behavior, authorization, administrative audit, and page rendering.

The full database migration chain was also executed against a temporary SQLite database, creating all four email service tables.

These checks used simulated SMTP transport. They do not establish real Aruba connectivity or successful routing through the AWS NAT.

## 6. Checks required before connecting Selection

The inspected checkout does not contain:

- `account_email.py`;
- `smtp_email.py`;
- `selection_workspace_email_outbox`;
- the RMAED bridge.

Selection currently contains a mock email provider. Shelbi must compare this implementation with the operational codebase, identify the actual CV upload entry point, and check for existing email consumers.

The same event must not be processed by both the old and new systems. Do not remove RMAED until its callers and pending work have been identified, migrated, and verified.

Real Aruba connectivity through the configured NAT and an explicitly authorized test send remain outstanding. No AWS deployment, real email send, or production database change was performed during this work.

## 7. Next implementation steps for Shelbi

Connect enqueueing to successful CV persistence and define the acknowledgment text. Verify that:

- A successful upload creates one email request.
- Retrying the same submission does not create a duplicate.
- Rolling back the application transaction also rolls back the email request.
- A subsequent SMTP failure does not invalidate the saved application.
- Reverting the integration does not resend messages already accepted by SMTP or marked uncertain.

The overall migration order remains **Training → Selection → MyRF → other Domains**. Coordinate Selection activation with that sequence.

Use Aruba SMTP exclusively for the new integration. Do not introduce SES, change Wix, or modify website configuration. AWS deployment, production migrations, and real sends require explicit authorization.

## 8. Implementation references

Paths below are relative to the repository root:

| File | Purpose |
| --- | --- |
| `03 Software/RF-One Data Store/rfone_data_store/email_service.py` | Queue models and transactional Python API. |
| `03 Software/RF-One Data Store/rfone_data_store/email_worker.py` | Standalone worker, persistent lease, rate limiting, and retry processing. |
| `03 Software/RF-One Data Store/rfone_data_store/technical/aruba_smtp.py` | Aruba SMTP transport and Secrets Manager configuration. |
| `03 Software/RF-One Data Store/migrations/versions/c7e5a3b9d201_shared_email_service.py` | Email queue, attempts, audit, and worker state migration. |
| `03 Software/RF-One Web/email_routes.py` | HTTP API and Email Control routes. |
| `03 Software/RF-One Web/tests/test_email_service.py` | Dedicated local tests. |
| `03 Software/RF-One Data Store/EMAIL_SERVICE.md` | Full technical report, deployment proposal, migration plan, and rollback guidance. |
