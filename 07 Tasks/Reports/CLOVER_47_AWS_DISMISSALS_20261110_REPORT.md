# REPORT — Authorized 47 employee dismissals applied on AWS

## 1. Result

Applied all 47 explicit employee dismissals requested by the Product Owner on 2026-11-10. The ECS task re-read all 31 current Clover employee records and all 5,209 Clover shifts before changing any data. No target had qualifying activity within the latest 15-day window. No targets were held or previously dismissed.

## 2. Integrity and access

The transaction preserved all 64 employee identities, their history, company/role references and other operational facts. Canonical active flags were set false and the original authorized dismissal dates were recorded in Employee Directory/profile events. Linked non-owner accounts were disabled and their sessions invalidated where applicable. The owner access exception was preserved. Verification confirmed dismissed IDs were absent from active employee selectors before commit; successful commit was followed by the task success marker. No Clover writes, local database import, network rule change or authentication bypass occurred.

For employees with no Clover clock history, the date retains the previously approved local execution-date basis; this is distinguished explicitly in the inactivity audit from an observed last clock-in date. This task does not introduce a recurring automatic 15-day dismissal job.

## 3. Evidence

Task: arn:aws:ecs:us-east-1:418674484214:task/rfone-jobs/6a7b98436c9749d89ebdd27c8baad50c (STOPPED, exit 0).

Snapshot retained: rfone-before-anagrafica-20261110t144835z.
Machine-readable employee result remains in the authorized private workspace, excluded from Git.
Detailed task output remains in the private workspace and AWS CloudWatch.
Source operation remains in the private release workspace.

Anagrafica: https://rfone.romesflavours.com/admin/roles?tab=people
