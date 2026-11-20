# Local immutable release preparation

Build and test entirely on the local workstation. A portable QEMU virtual machine runs the Linux Docker engine; no AWS account or production database is available to that VM. Downloads are checksum-verified. SSH is forwarded only to loopback with a generated local key.

Freeze an allowlisted source tree in an independent local Git repository, leaving the working repository and its unrelated changes untouched. Exclude uploads, databases, .env files, credentials, local launchers, local DPAPI helpers and bytecode. Include contextual Help with its pages. English is the release default; the official local launcher retains Italian. Translate controlled interface literals only, never CVs or stored records.

Build the image from the frozen commit, preserve dependency versions and OCI image identity, export it locally and verify the exported archive. Run the exact image against a disposable PostgreSQL clone with synthetic test credentials and mock object storage; test startup, shared login boundaries, current pages, extraction/OCR and failure behavior. Do not apply schema changes at startup. Keep any release gates and unfinished production actions explicit in the release report.

This procedure does not publish an image, change an AWS resource, send candidate messages or alter the operational local database.

## Production-only prerequisites, not applied here

Merge the example OpenAI secret permission into the existing Selection instance role policy, retaining shared database/session and S3 permissions. Replace the exact secret ARN placeholder; this example is not executable unchanged. If a customer-managed KMS key is used, verify its decrypt policy as well. See [App Runner environment references](https://docs.aws.amazon.com/apprunner/latest/dg/env-variable.html).

The service uses a VPC connector for RDS. Before deployment, verify outbound HTTPS to api.openai.com through the existing network path. App Runner VPC egress needs a suitable internet route such as NAT for public APIs; do not remove the VPC connector or expose RDS as a workaround. No network or IAM change is included in local verification. See [App Runner VPC egress](https://docs.aws.amazon.com/apprunner/latest/dg/network-vpc.html).
