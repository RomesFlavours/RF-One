# REPORT — English Training AWS release

## 1. Published behavior

Training is published in English at https://rfone.romesflavours.com/training.
Content provides the versioned course repository. Students provides student
management and the per-row Assign content modal with available-course checkboxes.
The separate Assignments tab is removed. Credentials require replacement at first
sign-in after provisioning/reset. Available courses contain only Visual Menu;
54 individual-dish entries are withdrawn without deleting historical records.

## 2. Release evidence

- Runtime source commit: `88c4d0a8198f55fbeba3cda3d17003bdfb066b9a`.
- Runtime image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:training-88c4d0a8198f`.
- Immutable image digest: `sha256:7217ab178b6e7d28e965c1c56d30a39ad58488e87e286d9ffc852f12d9d9d28d`.
- Source archive SHA-256: `dfd0a7cf9b29b922206a5a0ebdc66ebda38479ef2577419a2e8193005d9bbe31`.
- Source object: `s3://rfone-tips-deploy-418674484214/training/releases/88c4d0a8198f55fbeba3cda3d17003bdfb066b9a/source.zip`.
- CodeBuild: `rfone-web-build:7149b60b-4bb0-42f8-a541-e757261912f4` — SUCCEEDED.
- App Runner service: `arn:aws:apprunner:us-east-1:418674484214:service/rfone-training/36d02eb0109247128a831b34dd3306c4` — RUNNING; rebuild operation SUCCEEDED after the initial creation failed before application startup.
- Published schema: `f3b120261110 → t9a120261110`.
- Shared schema marker updated conditionally using the previous S3 ETag.

## 3. Verification

English transactional workspace/course tests pass, including assignment ownership,
CSRF, archive, first-access password replacement, immutable versions, upload/file
authorization and conflict handling. Test records were rolled back. The immutable
image-layout startup check passes without a database connection, migration or seed.
The exact release artifact passes How Works for 14 pages, with zero missing pages
and zero errors. JavaScript syntax checks pass.

The AWS migration/content procedure was rehearsed inside a rolled-back transaction
before application. Final protected-data fingerprints confirm that accounts, grants,
identity links, assignments, questions/results, restaurants and Kitchen recipes,
components and photos were unchanged. Existing Training assignments: 56.

Authenticated read-only checks pass on the official domain for student management,
course catalog and Visual Menu. Anonymous management access is denied. UI pages use
English and the student-row checkbox modal; the catalog contains only Visual Menu.
No existing account was created, reset or granted new permissions for verification.
Visual browser/screenshot verification was unavailable in this environment and is
not claimed. The Italian local UI was hash-checked and remains unchanged/operational.

## 4. Scope and recovery

Training uses an isolated service with the existing shared RF-One session/grants.
Existing Web, Kitchen, Tips and Selection services were not redeployed by this task.
Course uploads use the persistent shared managed database. Visual Menu reads the
existing WP restaurant and D125 Kitchen recipe; no restaurant or recipe is created.
Mount Dora is not registered in AWS and no new shared directory entry was introduced.

Snapshot protecting the current pre-Training schema and concurrent Registry work:
`rfone-dev-pre-training-f3-24f64624fd38`. Prior candidate snapshot: `rfone-dev-pre-training-8af847f218e1`.
The prior CloudFront configuration is retained in the release evidence as
`cloudfront-immediately-before-routing.json`. Recovery restores prior Training/
Visual Menu routing to the existing Web origin and retains additive data. Do not
drop historical course versions/files or downgrade shared directory work.

Temporary developer database access is removed after final verification. No local
working database, student record or local uploaded file was synchronized to AWS.
The scoped release branch is `codex/training-english-release`; push follows successful
deployment and official-domain verification.
