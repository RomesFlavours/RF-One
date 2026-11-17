# RF-One Email AWS release

This release adds the centralized email service to the pinned running RF-One
Web image. It preserves the deployed application's existing functionality;
it does not replace it with the older local-development baseline.

Base image: `rfone-web@sha256:94b1a3c07c33aaacb2937a1ff60ad84654b7a27a60d11f297401bce0b07061de`
(`home-no-selection-old-e0cb4ea`).

The existing cluster `rfone-jobs`, private subnets, NAT, CodeBuild project,
ECR repository, database secret and Aruba password secret are reused.
The worker has its own ECS service and a task role restricted to reading
the existing SMTP password secret. The existing ECS execution role injects
the database URL. No credentials are packaged or printed.

The password-only secret is supported alongside the JSON secret format.
Non-secret host, port, username and sender settings are inherited from the
current RF-One Web deployment. Existing Domain transports are retained
until their separate migrations; no RMAED/Wix configuration is changed.
The worker interval is 10 seconds, leaving capacity for those existing callers.

## Schema

The production release uses revision `e9a120261117`, parent `t9e120261113`.
It creates the same four email tables as the development-only migration
`c7e5a3b9d201`; that older revision is not shipped into the production chain.

The running image's migration tree was missing the already-applied Kitchen
revision `k9g120261112` and the already-applied Training enrollment revision
`t9e120261113`. These files are restored byte-identically from preserved Git
objects, without reapplying their migrations. The repaired chain has one head.

Migration runs in one short-lived ECS task and one PostgreSQL transaction,
with an advisory lock and an exact expected-revision check. It refuses
pre-existing email tables or a changed starting revision. A fresh RDS
snapshot must be available first. Normal app and worker startup never migrate.

## Explicit release actions

Run `deploy.py` from an authorized AWS session using profile `rfone-dev-login`.
Each invocation performs one action; `status` is an immediate snapshot.

1. `build`: package committed additions, build an immutable email image tag,
   validate the migration chain and import the web routes. Existing source
   ZIPs and `latest` image tags are not overwritten.
2. `status`: confirm the build succeeded and snapshot is available.
3. `preflight`: run queue checks in a temporary PostgreSQL schema, remove it,
   then verify Aruba TLS authentication and NOOP through the private NAT path.
   No SMTP MAIL, RCPT or DATA commands are issued.
4. `status`: require preflight exit code 0.
5. `migrate`: apply only the email revision and advance the shared version.
6. `status`: require migration exit code 0.
7. `api`: update only RF-One Web's image, preserving its live configuration.
   The action refuses a concurrent change to the original configuration.
8. `worker`: create the independent ECS service, desired count 1, on the
   existing private NAT subnets. Sending is enabled for future queued requests;
   the release itself does not enqueue messages or perform a test send.
9. `verify` and `status`: inspect schema, queue and worker heartbeat. Also
   check the official email routes and existing public application entry points.

The secret-free release state is stored under the operating system's temporary
directory as `rfone-email-aws-release-state.json`. It records image references,
task/build IDs and the original App Runner source configuration for rollback.

## Rollback

`deploy.py rollback` restores the saved RF-One Web image/configuration and
sets the email worker desired count to zero. It refuses to overwrite an
unexpected current image. Queue, audit and schema remain available for
reconciliation; accepted or uncertain messages must not be resent.

After migration, publish `migrations/aws_applied_revision.json` to the shared
S3 schema registry and commit the same evidence. Other release branches must
take the canonical migration files before their next schema-aware build.
