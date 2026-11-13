# REPORT — Employee Directory AWS-to-local copy

Date: 2026-11-10 (America/New_York). Outcome: COMPLETE.

## 1. Delivered local environment

Folder: `C:\Users\servi\AppData\Local\RF-One\Employee Directory\AWS-20261110T120743Z`.
URL: http://127.0.0.1:5094/administration/employees
Start/stop: `Avvia Anagrafica.cmd` / `Ferma Anagrafica.cmd` in that folder.
The application and portable PostgreSQL are currently running on loopback only.
Local access is automatic using the existing copied owner/admin session, as explicitly
requested by the Product Owner. No login/signature is required. No account or
password in the copied database was changed. Environment warning banners are hidden.
Existing local environments and development changes were not overwritten.

## 2. Provenance and scope

Copied the application files from the ECR image referenced by the actual RUNNING
rfone-web service, verifying each downloaded image layer digest before extraction.
Image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:interviews-consent-20261103t140633z`.
Digest: `sha256:74e8e188ab16f41816c792e008dd5944ed8ef3346997e055a8da01490fdaa4b1`.
Verified source files: 849.
A separate current S3 build-source ZIP is retained as additional provenance; it
has differences from the running runtime and was not substituted for that runtime.
The new local launcher is outside the preserved source tree.

Exported the complete shared application database to retain Employee Directory
foreign keys and historical consumers, using a read-only REPEATABLE READ snapshot
shared with pg_dump. No AWS personnel records or schema were changed.
Snapshot: 2026-11-10 12:09:07.942860+00:00.
Schema revision: `e2c320261109`.
Tables: 297. Rows: 1073016.
Employees: 64.
Clover links: 70.
RF1 accounts: 6.
Dump SHA-256: `16cf6c202ca51db482689a50e4acd9f5cf96fa088a7e2785c56c19a03e8774ee`.
Restore changes ownership to the isolated local database user; AWS roles/grants
and cloud credentials are not imported. S3 document attachments belonging to other
modules are outside this Employee Directory copy.

## 3. Verification

- All restored table row counts match the exported source snapshot.
- Employee, Clover/context links, identity aliases, RF1 accounts and shifts content
  hashes match where those tables exist in the snapshot.
- The schema revision matches the snapshot; no migration or seed was run.
- A fresh local Directory request returns HTTP 200 directly, without login or
  environment warning banners. The login URL redirects to Directory.
- Local authenticated Home, Directory list and employee detail return HTTP 200.
- The running localhost endpoint responds directly; automatic access is restricted
  to loopback and expected localhost Host headers.
- AWS service remains RUNNING with the original image identifier.
- Temporary RDS ingress was limited to the current public IPv4 /32 and TCP 5432,
  removed after export, and its rule ID was confirmed absent in a final AWS read.

## 4. Local operation and recovery

Portable PostgreSQL 18.3: `127.0.0.1:55571`;
database `rfone_employee_directory`. The server is not installed as a
Windows service and has no automatic startup task. The launcher removes cloud
configuration, disables AWS clients/external network access and POS synchronization,
and serves only Directory/account/login paths. It uses a separate local cookie key.
Other domain routes and outbound synchronizations are blocked in this local UI.
Local edits remain local; the initial `rfone-aws.dump` is retained for recovery.
Do not transfer this database back to AWS. It contains personal records and account
hashes and is stored outside Git and OneDrive.

This is the currently deployed AWS implementation, not the unshipped local
employee lifecycle changes. The observed schema is newer than the older handoff;
this copy does not alter or consolidate either implementation.

Full file hashes, database table counts, snapshot evidence and local connection
metadata: `verification.json`; usage: `README.txt`, both in the local folder.
No deployment, cloud source synchronization, production migration or Clover write.
