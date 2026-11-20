# Selection AI — TEST environment on AWS (SELECTION_AI_TEST_DEPLOY_001, 2026-10-21)

TEST-only deployment of `03 Software/Selection Prototype/` for G. and S. It is **not** production and shares no
data with it. The production Selection (`rfone-selection`), `rfone-web`, `rfone-tips` and the `rfone-dev` database
were not modified.

| Component | Identifier |
|---|---|
| URL | `https://musw2be7hu.us-east-1.awsapprunner.com` (App Runner HTTPS) |
| App Runner | `rfone-selection-ai-test` (1 vCPU / 2 GB, `AutoDeploymentsEnabled: false`), definition [`apprunner-service.json`](apprunner-service.json) |
| Image | ECR `rfone-selection-ai-test:latest`, built by CodeBuild `rfone-selection-ai-test-build` from `s3://rfone-tips-deploy-418674484214/rfone-selection-ai-test-source.zip` |
| Database | **separate** RDS PostgreSQL 18 `rfone-selection-ai-test` (db.t4g.micro, encrypted, not public), DB `selection_ai_test`; security group `rfone-selection-ai-test-db` admits 5432 only from the App Runner VPC connector SG `sg-0a4d4d094ea0d0fc3` |
| Résumés | private S3 bucket `rfone-selection-ai-test-documents-418674484214` (public access blocked, AES256, versioning, TLS only, replaced versions expire after 90 days) |
| Network | existing `rfone-tips-vpc-connector` (reused, unchanged), existing S3 gateway endpoint and Bedrock Runtime endpoint `vpce-0150ede1898b9a0f5` |
| AI | Bedrock `us.anthropic.claude-haiku-4-5-20251001-v1:0` (instance role limited to `bedrock:InvokeModel` on that profile); `RFONE_SELECTION_PROTOTYPE_AI=1`, `RFONE_SELECTION_PROTOTYPE_AI_CV=1` |
| Secrets | Secrets Manager `rfone-selection-ai-test/{database-credentials, database-url, flask-secret-key, setup-token}` — none in code or image |
| IAM | `rfone-selection-ai-test-{codebuild-role, apprunner-ecr-access-role, apprunner-instance-role}`, policies in this folder |

All resources carry the tags `rfone-env=TEST`, `rfone-app=selection-ai-test`.

**Source of the image.** `RF-One Data Store/` from commit `ec9c6c4` + `Selection Prototype/` working files + this
`Dockerfile`/`buildspec.yml`. Not HEAD `491694b`: its Invoice Intake migration `b3f9d2c6e4a1` names a check
constraint `ck_purchased_line_derived_values_product_card_requires_packaging` (64 characters) and fails on
PostgreSQL (limit 63). The Selection services and accounts code are identical in the two commits.

**Behaviour in TEST mode** (`RFONE_SELECTION_PROTOTYPE_PUBLIC=1`): HTTPS-only session cookie; `X-Robots-Tag: noindex,
nofollow` on every response and `robots.txt` disallowing everything; first-owner setup only with the setup token;
new accounts only by one-time invitation link (7 days) where each person chooses the password (minimum 10
characters); public application pages without login, only for approved and open positions.

**Release.** Assemble the package as above (zip with `/` separators), upload to the source key, `codebuild
start-build --project-name rfone-selection-ai-test-build`, then `apprunner start-deployment` on the service. The
schema is migrated by the app at boot (one gunicorn worker).

**Removal.** Delete the App Runner service, the RDS instance (no deletion protection; take a final snapshot if the
test data must be kept), the S3 bucket, the ECR repository, the CodeBuild project, the three IAM roles, the four
secrets and the security group `rfone-selection-ai-test-db`.
