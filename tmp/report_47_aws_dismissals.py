from pathlib import Path
import json
root=Path.cwd();logs=(root/'tmp/anagrafica-release/dismissals_task.log').read_text(encoding='utf-8');line=next(v for v in logs.splitlines() if v.startswith('AWS_DISMISSALS_VERIFIED '));result=json.loads(line.split(' ',1)[1]);assert result['applied_count']==47 and not result['held'];(root/'07 Tasks/Reports/CLOVER_47_AWS_DISMISSALS_20261110_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
report='''# REPORT — Authorized 47 employee dismissals applied on AWS

## 1. Result

Applied all 47 explicit employee dismissals requested by the Product Owner on 2026-11-10. The ECS task re-read all 31 current Clover employee records and all 5,209 Clover shifts before changing any data. No target had qualifying activity within the latest 15-day window. No targets were held or previously dismissed.

## 2. Integrity and access

The transaction preserved all 64 employee identities, their history, company/role references and other operational facts. Canonical active flags were set false and the original authorized dismissal dates were recorded in Employee Directory/profile events. Linked non-owner accounts were disabled and their sessions invalidated where applicable. The owner access exception was preserved. Verification confirmed dismissed IDs were absent from active employee selectors before commit; successful commit was followed by the task success marker. No Clover writes, local database import, network rule change or authentication bypass occurred.

For employees with no Clover clock history, the date retains the previously approved local execution-date basis; this is distinguished explicitly in the inactivity audit from an observed last clock-in date. This task does not introduce a recurring automatic 15-day dismissal job.

## 3. Evidence

Task: arn:aws:ecs:us-east-1:418674484214:task/rfone-jobs/6a7b98436c9749d89ebdd27c8baad50c (STOPPED, exit 0).

Snapshot retained: rfone-before-anagrafica-20261110t144835z.
Machine-readable result: CLOVER_47_AWS_DISMISSALS_20261110_RESULT.json.
Detailed task output: tmp/anagrafica-release/dismissals_task.log.
Source implementation: tmp/anagrafica-release/apply_47_inside_aws.py.

Anagrafica: https://rfone.romesflavours.com/admin/roles?tab=people
'''
(root/'07 Tasks/Reports/CLOVER_47_AWS_DISMISSALS_20261110_REPORT.md').write_text(report,encoding='utf-8');print('AWS dismissal result and report saved')
