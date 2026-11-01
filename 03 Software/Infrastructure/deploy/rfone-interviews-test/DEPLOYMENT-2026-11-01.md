# Interviews TEST deployment — 2026-11-01

Status: AWS App Runner update SUCCEEDED; service RUNNING. Official entry: https://rfone.romesflavours.com/admin/interviews (normal RF-One authentication required).

## Release identity

- Branch: `codex/interviews-aws-test-20261101`.
- Application commit: `14552ccfc1150408d0964f36830e0894a24e1580`.
- Image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:interviews-test-20261101t195949z`.
- Digest: `sha256:90276880ccf26114bd808fb923c23303c82117cce893fd74e16f116b55cf71a3`.
- Versioned source: `s3://rfone-tips-deploy-418674484214/releases/interviews-test-20261101t195949z/source.zip`.
- CodeBuild: `rfone-web-build:c21aa070-7690-404d-aa2f-6d674a7f6669`, SUCCEEDED.
- App Runner operation: `2c7cdc1cfae94c5ab0660b51fb9dcfd0`, SUCCEEDED.

## Database and rollback

Pre-migration RDS snapshot `rfone-dev-pre-interviews-test-20261101t195736z` was available before migration. ECS task `rfone-jobs/1b522433fe554dd2bcde4c3d7d0d434f` exited 0. Only the additive revision `d9e220261029` -> `e0a120261101` ran, adding interview_sessions and indexes; zero application data rows were created. Existing people/account links were not changed.

Previous image for application rollback: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:home-thumb-20261030t194710z`. Restore only the image identifier while retaining the service configuration. The additive table may remain; do not automatically drop interview data or restore the entire database snapshot.

## Verified

Twelve interview tests passed, including authorization, CSRF, stale revisions, invalid provider output, quotation evidence, canonical directory integration and link revocation. Ten existing directory HTTP/migration tests passed. Docker image layout startup and existing Tips route registration passed. Git diff whitespace checks passed.

Public HTTPS probes: login 200; admin request/results and participant URLs redirect unauthenticated visitors to RF-One login with no-store and noindex/nofollow; new voice JavaScript and TEST banner stylesheet 200; existing directory and Selection entry points still redirect to login; Training menu 200. No anonymous interview access or local login bypass was introduced. Every interview page renders the TEST banner and candidate results require human review.

Limits: authenticated production interviews, real AI responses and microphone operation have not been exercised against real users during deployment. No interviews were created for verification. Edge automatic opening was blocked because the desktop control could not confidently determine the current browser URL; no authentication or browser security bypass was attempted.

This release is isolated from the older dirty handoff checkout. No Git push was performed; the earlier request assigned that operation to Claude. This receipt is a subsequent documentation commit and does not change the deployed application image.
