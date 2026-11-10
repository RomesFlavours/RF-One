# REPORT — Registry contact details and retained password reset

## 1. Delivered behavior

Accounts is removed from MyRF Home Settings. The existing account and reset routes remain protected and operational. Registry's saved-person modal now exposes Reset password, opening the existing linked-account reset form in a separate tab at #reset-password. The original person form retains unsaved edits. New people must first be saved; opening a provisioned inactive account does not grant access or reactivate it.

Email and Phone are optional, editable Registry contact fields. Employee contacts reuse Employee.email/phone and the central management audit. Unlinked external accounts use contact_email/contact_phone, explicitly separate from the existing recovery email and verification timestamp. Saving contacts does not send messages, change credentials, verify emails, enroll recovery or infer identity matches. Empty input clears a contact; omitted fields preserve it. No Clover writes occur.

## 2. Shared schema and concurrency

The first migration task stopped before any write because the shared database had advanced from f2a120261110 to Kitchen revision k9a020261110. A read-only ECS audit confirmed the new revision. Recovered the exact applied Kitchen migration and its required frozen models, then placed the not-yet-published Registry migration after it. The full chain was rehearsed on a new complete isolated PostgreSQL copy: e2c320261109 → f2a120261110 → k9a020261110 → f3b120261110. The existing local schema was aligned with the recovered Kitchen ancestor without dropping data.

The successful production task executed only k9a020261110 → f3b120261110, adding two nullable external-account contact columns. All original data for 7 accounts, 64 employees and 47 dismissed people were verified unchanged, including password hashes, status, session versions, recovery addresses and verification dates. Kitchen operations were not rerun on AWS. The shared schema marker was updated conditionally by S3 ETag and is committed with the applied migration.

Snapshot: rfone-before-registry-contacts-20261110t160928z.
Migration task: arn:aws:ecs:us-east-1:418674484214:task/rfone-jobs/2ffb982b438d400a98e155f257a1530f (exit 0).

## 3. Release and local copy

Image: registry-contacts-20261110t161756z.
Digest: sha256:b2ef6a54294e53e09f4b7b743264207b597837320f50c17efb320e01a5bf07c4.
Build: rfone-web-build:0d5ef190-ed79-4442-9adf-f475f522d242 (SUCCEEDED).
App Runner operation: acf6645a8a7044ffb82a1143472fe1d1 (SUCCEEDED, RUNNING).

Downloaded and SHA-256-checked the published source ZIP and byte-verified 862 files into the isolated local source. Existing local data, 47 dismissals, no-login access and absence of environment banners are preserved. Production authentication is unchanged. The local database was backed up before migration.

## 4. Verification

87 Registry HTTP checks, 36 MyRF Home checks, 15 service unit tests and 16 connector/artifact checks passed. Tests cover centralized employee and external contacts, invalid input rollback, explicit clearing, omitted-field preservation, unchanged recovery credentials and session state, reset authorization/CSRF, password-hash/session revocation and inactive-account preservation. Password-reset writes were performed only against disposable synthetic test accounts.

Browser inspection confirmed Accounts is absent from Home, Email/Phone and Reset password are visible in Registry, and the reset action opens the existing account form. No real contacts or passwords were changed during browser inspection. Private screenshot: REGISTRY_CONTACTS_LOCAL_20261110.png (excluded from Git).

URLs: https://rfone.romesflavours.com/admin/roles and http://127.0.0.1:5094/admin/roles.

Source, migration, applied schema marker, portable tests and this report are published on codex/anagrafica-aws-20261110. Raw personal records, backups, credentials and screenshots are excluded. Existing pending lifecycle work in the original checkout remains separate.
