# Clover Correction Sync (AWS)

CORRECTION_POLLER_ACTIVATION_001. **Status: created 2026-09-28** (Product
Owner decision: option A — a permanent service at the approved ~60 s).

## What it is

The Correction/Reconciliation Poller
(`rfone_data_store/technical/connectors/clover/correction_sync.py`,
[`CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md`](../../../RF-One%20Data%20Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md) §3)
running continuously on AWS. Every ~60 s it asks Clover for the Orders and
Payments **modified** since its own last checkpoint (minus a 5-minute
overlap) and for the Refunds of the last 48 h, and applies them through the
same upserts Sync Now and Historical Backfill use. It catches what Sync Now
cannot: a record changed in Clover after it was first acquired (e.g. a tip
added after the payment, the 26/09 Messick/Ceban case).

It is **one ECS Fargate service**, desired count 1, in the existing cluster,
running the **same `rfone-tips` image** as the Clover acquisition jobs:

| Resource | Name / file |
|---|---|
| ECS cluster | `rfone-jobs` (existing) |
| Task definition | [`task-definition.json`](task-definition.json), family `rfone-clover-correction-sync` (0.25 vCPU, 512 MB) |
| ECS service | `rfone-clover-correction-sync`, desired count 1, Fargate, public IP |
| Network | same subnets and security group `sg-0a4d4d094ea0d0fc3` as the acquisition jobs (Clover over the Internet Gateway, RDS on 5432) |
| Execution role | `rfone-clover-acquisition-job-execution-role` (existing: the same three secrets, CloudWatch logs) |
| Logs | CloudWatch `/ecs/rfone-clover-correction-sync`, stream prefix `poller` |

Why a permanent service and not one task per run: at ~60 s a Fargate task
started per run would spend most of the interval starting. App Runner
cannot host it either (CPU throttled outside requests, no Internet egress —
see [`../clover-acquisition-job/README.md`](../clover-acquisition-job/README.md)).

## Behaviour that matters operationally

- **Command:** `python -m rfone_data_store.technical.connectors.clover.correction_sync --location-id 1 --interval-seconds 60 --skip-migrations`. It never applies migrations: those stay a separate, snapshotted release step.
- **Lock:** it shares the Location's one acquisition lock with Sync Now and Backfill. If Sync Now or a Backfill is running, the cycle is skipped. If a person presses Sync Now during the few seconds a cycle runs, they get the usual "already in progress" and press again (accepted with option A).
- **Stop:** on SIGTERM (redeploy, scale-down) it finishes the cycle in flight and stops between cycles (`stopTimeout` 120 s). A cycle cut off anyway carries a heartbeat, so its lock is recovered after 5 minutes, not 30.
- **History:** each cycle writes one `ingestion_runs` row of mode `CORRECTION` (the cycle: status, what it applied, errors) plus one cursor row per resource (`resource_type` orders/payments/refunds: the window scanned). RF-One Web's Clover Acquisition history lists them as **Correction Sync**, the latest cycle and the recent failed ones.
- **First run:** 24 h back per resource, then it resumes from its own checkpoints.

## Created with

```powershell
aws logs create-log-group --log-group-name /ecs/rfone-clover-correction-sync   # the execution role may create only the jobs' log group
aws ecs register-task-definition --cli-input-json file://task-definition.json
aws ecs create-service --cluster rfone-jobs --service-name rfone-clover-correction-sync `
  --task-definition rfone-clover-correction-sync:1 --desired-count 1 --launch-type FARGATE `
  --network-configuration "awsvpcConfiguration={subnets=[<the acquisition jobs' subnets>],securityGroups=[sg-0a4d4d094ea0d0fc3],assignPublicIp=ENABLED}" `
  --deployment-configuration "maximumPercent=100,minimumHealthyPercent=0"
```

`maximumPercent=100` / `minimumHealthyPercent=0`: a deployment stops the
old poller before starting the new one (the shared lock would serialize two
anyway). A task stopped while it is still booting — before the SIGTERM
handler exists — runs until ECS kills it after `stopTimeout`; observed on
2026-09-28 (exit 137 after two complete cycles, no lock left behind).

## Operate

```powershell
# pause / resume
aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --desired-count 0 --profile rfone-dev-login --region us-east-1
aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --desired-count 1 --profile rfone-dev-login --region us-east-1
# pick up a new rfone-tips image after a release
aws ecs update-service --cluster rfone-jobs --service rfone-clover-correction-sync --force-new-deployment --profile rfone-dev-login --region us-east-1
```

A new `rfone-tips:latest` is **not** picked up automatically: after a
`rfone-tips` release, force a new deployment of this service too.
