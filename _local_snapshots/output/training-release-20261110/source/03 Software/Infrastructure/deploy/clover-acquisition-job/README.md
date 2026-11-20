# Clover acquisition job runner (AWS)

CLOVER_ACQUISITION_JOBS_001. **Status: created 2026-09-26** (Product Owner
approval: ECS Fargate runner, then the ECS API VPC endpoint).

## Why a separate runner

Sync Now and Historical Backfill no longer run inside a web request
(`rfone_data_store/technical/connectors/clover/acquisition_jobs.py`). The
page accepts the job and a separate process runs it. On AWS that process
cannot live inside App Runner:

| Fact (observed 2026-09-26) | Consequence |
|---|---|
| App Runner throttles a container's CPU whenever it is not serving a request (AWS documentation) | a job left running inside `rfone-tips` after the page returns would crawl or stall |
| `rfone-tips` egresses through its VPC connector; the VPC (`vpc-0f0832ffeddd4e2e2`, default VPC) has **no NAT gateway** | `rfone-tips` cannot reach the Internet, so it cannot reach Clover: the 2026-09-26 12:20 UTC Backfill hung on the first TCP connect to Clover until gunicorn killed the worker at 60 s |
| The subnets route `0.0.0.0/0` to an Internet Gateway; RDS `rfone-dev` accepts port 5432 from `sg-0a4d4d094ea0d0fc3` | a Fargate task in those subnets, with a public IP and that security group, reaches both Clover and RDS — no NAT needed |

## What it is

One ECS Fargate task per job, running the **same `rfone-tips` image** with
`python -m rfone_data_store.technical.connectors.clover.acquisition_jobs --run-id N`.
Paid only while a job runs. Logs in CloudWatch `/ecs/rfone-clover-acquisition-job`.

| Resource | Name / file |
|---|---|
| ECS cluster (Fargate) | `rfone-jobs` |
| Task definition | [`task-definition.json`](task-definition.json) (family `rfone-clover-acquisition-job`) |
| Execution role | `rfone-clover-acquisition-job-execution-role` — `AmazonECSTaskExecutionRolePolicy` + [`execution-role-secrets-policy.json`](execution-role-secrets-policy.json) + `logs:CreateLogGroup` |
| Permission for the web service | [`apprunner-instance-role-runtask-policy.json`](apprunner-instance-role-runtask-policy.json), inline on `rfone-web-apprunner-instance-role` (policy `rfone-web-run-clover-acquisition-job`). Since CLOVER_ACQUISITION_IDENTITY_001 only RF-One Web starts jobs (behind the RF-One login and the CLOVER_ACQUISITION access); the permission and launcher variables were removed from `rfone-tips`. |
| ECS API VPC endpoint | `vpce-03dc68cffc4932f8b` (`com.amazonaws.us-east-1.ecs`, private DNS, subnets 1a/1b), security group `sg-0503f48dd3ae94599` `rfone-ecs-endpoint-sg`: 443 only from `sg-0a4d4d094ea0d0fc3` (the VPC connector shared by `rfone-web` and `rfone-tips`). Needed because `rfone-tips` has no Internet egress, so it could not reach the public ECS API either (first production attempt hung 60 s → 500). About 15 $/month. |

`rfone-web` environment (App Runner) — `rfone-tips` no longer starts jobs:

| Variable | Value |
|---|---|
| `RFONE_CLOVER_JOB_LAUNCHER` | `ecs` |
| `RFONE_CLOVER_JOB_ECS_CLUSTER` | `rfone-jobs` |
| `RFONE_CLOVER_JOB_ECS_TASK_DEFINITION` | `rfone-clover-acquisition-job` |
| `RFONE_CLOVER_JOB_ECS_SUBNETS` | the VPC connector's subnets |
| `RFONE_CLOVER_JOB_ECS_SECURITY_GROUPS` | `sg-0a4d4d094ea0d0fc3` |
| `AWS_REGION` | `us-east-1` |

The task reads `CLOVER_MERCHANT_ID` from `rfone-tips/clover-merchant-id`; it
must equal the Location's `source_location_id`. On 2026-09-26 it held a wrong
value, which made Clover reject Employees/Tenders/Shifts/catalog (401) while
Payments/Orders still worked — corrected the same day (see
`07 Tasks/Reports/CLOVER_ACQUISITION_JOBS_001.md` §3).

`RFONE_CLOVER_LIVE_SYNC_ENABLED` stays **unset**: Live Sync is prepared but
not active until the Product Owner enables it (Cognito).

## Release order

1. RDS snapshot, then `alembic upgrade head` (revision `b8d4e2f7a1c9`, additive).
2. Build and push the `rfone-tips` image (`deploy/rfone-tips/`, CodeBuild `rfone-tips-build`).
3. Create the cluster, roles, task definition and ECS endpoint above (ECS's
   own service-linked role `AWSServiceRoleForECS` already existed).
4. Set the environment variables on `rfone-web` (the only service that starts jobs), redeploy it; rebuild `rfone-tips` too, since its image is the one the job task runs.
5. Minimal check: one Sync Now (or a one-day Backfill), watch QUEUED → RUNNING → COMPLETE.
