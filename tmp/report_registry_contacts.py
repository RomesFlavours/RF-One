from pathlib import Path
import json
root=Path.cwd();repo=root/'tmp/git-anagrafica-release';release=root/'tmp/registry-contacts-release';d=json.loads((release/'state.json').read_text());marker=json.loads((release/'schema-marker.json').read_text());meta={k:d[k] for k in ('tag','image_digest','source_sha256','source_s3_key','build_id','deploy_operation','migration_task','rds_snapshot','expected_previous_image')};meta.update(deployment_status='SUCCEEDED',schema_revision='f3b120261110',schema_parent='k9a020261110',tests={'registry_http':87,'myrf_home':36,'profile_service':15,'connector_guard':16},existing_account_records_preserved=7,employees_preserved=64,dismissed_preserved=47,local_files_verified=862)
(repo/'07 Tasks/Reports/REGISTRY_CONTACTS_RESET_20261110_RELEASE.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
report=f'''# REPORT — Registry contact details and retained password reset

## 1. Delivered behavior

Accounts is removed from MyRF Home Settings. The existing account and reset routes remain protected and operational. Registry's saved-person modal now exposes Reset password, opening the existing linked-account reset form in a separate tab at #reset-password. The original person form retains unsaved edits. New people must first be saved; opening a provisioned inactive account does not grant access or reactivate it.

Email and Phone are optional, editable Registry contact fields. Employee contacts reuse Employee.email/phone and the central management audit. Unlinked external accounts use contact_email/contact_phone, explicitly separate from the existing recovery email and verification timestamp. Saving contacts does not send messages, change credentials, verify emails, enroll recovery or infer identity matches. Empty input clears a contact; omitted fields preserve it. No Clover writes occur.

## 2. Shared schema and concurrency

The first migration task stopped before any write because the shared database had advanced from f2a120261110 to Kitchen revision k9a020261110. A read-only ECS audit confirmed the new revision. Recovered the exact applied Kitchen migration and its required frozen models, then placed the not-yet-published Registry migration after it. The full chain was rehearsed on a new complete isolated PostgreSQL copy: e2c320261109 → f2a120261110 → k9a020261110 → f3b120261110. The existing local schema was aligned with the recovered Kitchen ancestor without dropping data.

The successful production task executed only k9a020261110 → f3b120261110, adding two nullable external-account contact columns. All original data for 7 accounts, 64 employees and 47 dismissed people were verified unchanged, including password hashes, status, session versions, recovery addresses and verification dates. Kitchen operations were not rerun on AWS. The shared schema marker was updated conditionally by S3 ETag and is committed with the applied migration.

Snapshot: {d['rds_snapshot']}.
Migration task: {d['migration_task']} (exit 0).

## 3. Release and local copy

Image: {d['tag']}.
Digest: {d['image_digest']}.
Build: {d['build_id']} (SUCCEEDED).
App Runner operation: {d['deploy_operation']} (SUCCEEDED, RUNNING).

Downloaded and SHA-256-checked the published source ZIP and byte-verified 862 files into the isolated local source. Existing local data, 47 dismissals, no-login access and absence of environment banners are preserved. Production authentication is unchanged. The local database was backed up before migration.

## 4. Verification

87 Registry HTTP checks, 36 MyRF Home checks, 15 service unit tests and 16 connector/artifact checks passed. Tests cover centralized employee and external contacts, invalid input rollback, explicit clearing, omitted-field preservation, unchanged recovery credentials and session state, reset authorization/CSRF, password-hash/session revocation and inactive-account preservation. Password-reset writes were performed only against disposable synthetic test accounts.

Browser inspection confirmed Accounts is absent from Home, Email/Phone and Reset password are visible in Registry, and the reset action opens the existing account form. No real contacts or passwords were changed during browser inspection. Private screenshot: REGISTRY_CONTACTS_LOCAL_20261110.png (excluded from Git).

URLs: https://rfone.romesflavours.com/admin/roles and http://127.0.0.1:5094/admin/roles.

Source, migration, applied schema marker, portable tests and this report are published on codex/anagrafica-aws-20261110. Raw personal records, backups, credentials and screenshots are excluded. Existing pending lifecycle work in the original checkout remains separate.
'''
(repo/'07 Tasks/Reports/REGISTRY_CONTACTS_RESET_20261110_REPORT.md').write_text(report,encoding='utf-8');(root/'07 Tasks/Reports/REGISTRY_CONTACTS_RESET_20261110_REPORT.md').write_text(report,encoding='utf-8')
