# REPORT

## 1. Result

Selection is prepared and running locally at http://127.0.0.1:5096/selection/,
using the current source in `03 Software/AWSSelection/Selection`. Both local
launch locations now use this runtime. The shared SQLite database is the existing
`%LOCALAPPDATA%/RF-One/RFBank/rfone.db`; no new working database was created.

## 2. Identity and data

The PO explicitly authorized enabling SELECTION for existing account admin on
2026-11-14. This single grant was enabled; no new account, owner designation,
password or other grant was created. Startup authenticates the existing operator
only on loopback and enforces existing Selection authorization and CSRF.

An explicit initialization added 20 missing Selection tables and nine compatible
mapped columns, without running general migrations or changing Alembic history.
A consistent backup passed integrity verification before initialization. An
independent comparison of all 282 preexisting tables found no data differences
except the authorized grant. The database has one RF-One account, no external
candidate account and no test Jobs. RFBank continues to answer on port 5111.

## 3. Validation

Dependencies pdfplumber and python-docx are installed in the existing shared
RF-One venv; pip check passes. Five principal pages returned 200, with Italian
UI and contextual help. A disposable-copy workflow verified a configured role,
draft creation with CSRF, refusal without CSRF, non-loopback and Host refusal,
and immediate refusal after disabling the Selection grant. The test database
was removed. Live HTTP checks and restart passed. No email or AI request was
sent during setup/testing. AI drafting/CV flags remain opt-in; real provider and
email integration are not certified by these tests.

## 4. Changes and recovery

New `local_runtime.py`, `test_local_runtime.py`, `LOCAL_ENVIRONMENT.md` and stop
scripts in AWSSelection/Selection; local_server.py and start commands updated in
both Selection locations; README startup references updated. No shared/deployed
authentication or product flow was modified. Existing page help was verified;
launcher and schema changes are technical only.

Backup: `%LOCALAPPDATA%/RF-One/backups/selection-before-local-20261114T224418Z.sqlite-backup`.
Logs: `%LOCALAPPDATA%/RF-One/Selection/server.stdout.log` and `server.stderr.log`.
Recovery and lifecycle: `03 Software/AWSSelection/Selection/LOCAL_ENVIRONMENT.md`.
No push or deployment was performed.
