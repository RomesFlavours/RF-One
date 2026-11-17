# RF-One Email Service AWS deployment report

Deployment completed on 17 November 2026. The RF-One Web update completed at
15:58:42 America/New_York. The central queue, API, administrative page and
independent Aruba SMTP worker are deployed. No test email was sent.

## Deployed components

| Component | Release evidence |
| --- | --- |
| Source branch | `codex/rfone-email-service-aws` |
| Image source commit | `7291a4ac84199680e0aa837666ff28bc307f0511` |
| ECR image | `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:email-7291a4ac8419` |
| Image digest | `sha256:9f2b21fac22caacf152db8e5110b4d8f1e605e469900e241fad3c81b2f496e82` |
| CodeBuild | `rfone-web-build:6b745e7b-dde7-4ef1-815a-5583f72cc455` — SUCCEEDED |
| App Runner | `rfone-web` — RUNNING |
| App Runner update | `115e5c11c8964359bad07842ba13585d` — SUCCEEDED |
| ECS cluster/service | `rfone-jobs` / `rfone-email-service` |
| Worker task definition | `rfone-email-service:1` |
| Observed worker task | `2760d36512364148a1a08a90fb0563c0` |
| Worker state | Desired 1, running 1, pending 0; deployment COMPLETED |
| Database revision | `e9a120261117`, previously `t9e120261113` |
| RDS safety snapshot | `rfone-dev-pre-email-20261117t204618z` — available |
| Source archive | `s3://rfone-tips-deploy-418674484214/email/releases/7291a4ac84199680e0aa837666ff28bc307f0511/source.zip` |

The image is an additive overlay on the previously running image, pinned by
digest. It adds email functionality while preserving the deployed MyRF and
other RF-One Web features. It does not deploy the older development checkout
over the running application.

## Database and infrastructure changes

Created `email_requests`, `email_attempts`, `email_audit` and
`email_worker_state`. The migration ran once, in a dedicated ECS task and a
PostgreSQL transaction, after verifying the expected revision and acquiring
an advisory lock. Protected operational table row counts were unchanged.

The shared S3 schema registry and the repository's
`RF-One Data Store/migrations/aws_applied_revision.json` record the applied
revision and release evidence. Its previous S3 value was backed up under
`schema/history/aws_applied_revision.pre-email-7291a4ac8419.json`.

The previously applied Kitchen and Training migration files missing from the
Web image were recovered byte-identically from preserved Git objects. They
were not reapplied. The repaired migration chain has one head.

Reused existing CodeBuild, ECR, RDS, S3 deployment bucket, ECS cluster, private
subnets, security groups, NAT gateway and SMTP password secret. Added only
the worker ECS service/task definitions, its restricted SMTP secret-reading
task role, release task definitions, a 30-day log group, and the safety snapshot.
No new NAT, database, queue broker, ECR repository or CodeBuild project was created.

The worker uses the existing Aruba mailbox and password secret. It retrieves
the password in memory through Secrets Manager, uses certificate-verified TLS
and has a 10-second global queue interval. Existing Domain SMTP callers are
retained pending their separate migrations.

## Verification

Twenty dedicated local email tests passed on the deployed Web source baseline.
The image build verified the migration chain and imported the new routes.

The following ECS release tasks exited with code 0:

| Task | ID | Result |
| --- | --- | --- |
| Preflight | `64112479e4c84d9db06e9f65185541da` | PostgreSQL isolation/concurrency checks and Aruba TLS/authentication/NOOP passed |
| Migration | `4f2bbd73cfea439ebfbbd7640c77c174` | Applied only `e9a120261117`; protected operational row counts unchanged |
| Verification | `4ca666896f46408498ab2ed7c73311a5` | Correct revision, empty central queue, worker IDLE with heartbeat |

PostgreSQL tests used a uniquely named temporary schema, removed afterward.
They exercised concurrent enqueue deduplication, two concurrent workers,
Domain isolation, retry and uncertain-outcome handling with fake delivery.

The Aruba check ran in the private NAT subnets with public IP disabled.
TLS, authentication and NOOP succeeded. No MAIL, RCPT or DATA commands were
issued by that check. The release did not enqueue production messages.

The final verification observed an empty central queue and an IDLE worker
heartbeat at 15:58:58 America/New_York. Worker sending mode is enabled for
future requests explicitly enqueued by Domain integrations.

Public HTTP checks after deployment:

| Path | Before | After |
| --- | --- | --- |
| `/login` | 200 | 200 |
| `/training` | 302 to Training sign-in | Same redirect |
| `/selection/` | 302 to RF-One login | Same redirect |
| `/administration/email` | 404 | 401 without authentication |
| `/api/email/SELECTION/requests` | 404 | 401 without authentication |

RF-One Web, Training and Selection services were observed RUNNING.
Administrative page rendering and authorization were tested locally; a live
authenticated browser session was not used for this release verification.

## Scope and remaining work

The central service is deployed and the worker is operational. The Selection
CV upload auto-responder is not yet connected. Training, Selection and MyRF
callers have not been migrated as part of this deployment.

RMAED, Wix, website configuration, existing Domain queues and existing Domain
deployment configurations were not changed. No SES transport was introduced.

For Shelbi, use this AWS release branch and the updated
`RF-One Data Store/SELECTION_CV_EMAIL_HANDOFF.md`. Do not apply the original
development-only `c7e5a3b9d201` migration to the shared database. Production
already has the canonical email revision `e9a120261117`.

## Access and rollback

Email Control: <https://rfone.romesflavours.com/administration/email>.
An active RF-One administrator session is required.

`deploy.py rollback`, using the retained release state, restores the previous
RF-One Web source configuration and scales the email worker to zero. It
refuses an unexpected current image. It preserves the queue and audit for
reconciliation; accepted and uncertain messages must never be automatically
resent during rollback.

Previous Web image:
`418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:home-no-selection-old-e0cb4ea`.
The additive schema remains compatible with that previous application image.
Do not drop email tables as the normal rollback procedure.
