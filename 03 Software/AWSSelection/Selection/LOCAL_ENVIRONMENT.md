# Local Selection on the existing shared database

## Current recovery and portable path — 2026-11-15

The prior per-PC database was absent on this PC. A project-wide search found no
SQLite Selection database newer than `RFBank/recovery/rfone.db` (2026-11-13).
That preserved recovery baseline was copied to `RFBank/rfone.db`, and only the
documented November 14 compatibility additions and existing account's Selection
grant were replayed. This is a reconstructed compatible working copy, not a
claim that the missing November 14 file was found. All 282 preexisting tables
were compared; only the documented Selection grant changed. No candidate, Job
or account was created. Recovery evidence is in `output/selection-resume-20261115/`.

The canonical connection is now read from `RFBank/local-database.json`; a relative
`database` value is resolved against that file's directory. The active database
and Selection runtime documents/session key are under the project, excluded
from Git. Start `Avvia Selection.cmd`, or `python local_server.py --port 5096`.
Use one active PC only, close Selection before switching, and wait for OneDrive
to finish syncing. This does not make OneDrive a concurrent database service.

The historical setup notes below describe the original November 14 installation.

The 2026-11-14 local setup reuses the existing database declared by
`RFBank/local-database.json` in the repository (or the sibling RFBank copy).
Only `%LOCALAPPDATA%/RF-One/RFBank/rfone.db` is accepted on this PC. No empty
database, new account, password or owner is created. The explicitly authorized
change enables SELECTION for the existing admin account; other grants remain.

`local_server.py --initialize` makes a SQLite backup, adds only mapped columns
and missing Selection workspace tables, without moving shared Alembic history.
It does not run the complete migration chain. Subsequent starts only verify.
Use the existing shared RF-One venv. Runtime documents, logs and the local cookie
key are outside OneDrive. Run `Avvia Selection.cmd`, then open port 5096.
The server binds to loopback, validates Host, and signs in the existing operator;
all Selection authorization and CSRF checks still apply. No grants are made at
startup. Shared/deployed authentication is unchanged. Local UI uses Italian.

AI drafting/CV processing is opt-in via `--ai` / `--ai-cv`; absent provider and
SMTP configuration remain explicit unavailable capabilities. No real email or
AI request is part of initialization or startup.

## Lifecycle and validation

`Avvia Selection.cmd` starts port 5096; `Ferma Selection.cmd` stops only this
Selection launcher, leaving RFBank and the shared database in place. Both entry
points are also provided in the historical `03 Software/Selection` directory.

Initialization backup:
`%LOCALAPPDATA%/RF-One/backups/selection-before-local-20261114T224418Z.sqlite-backup`.
Twenty missing Selection tables and nine compatible columns were added; the
existing Alembic revision was retained and passes the read-only schema check.
The existing account remained `admin`, active, administrator, not owner.

`test_local_runtime.py` uses a disposable database copy, removed after the test.
It checks five pages, Italian and help, loopback/Host restrictions, CSRF, a draft
creation and immediate refusal after grant revocation. No account is created.
An independent comparison checked all 282 preexisting tables against the backup;
the only data change was the explicitly authorized SELECTION grant. The active
database has one RF-One account, zero candidate accounts and zero trial Jobs.
Live HTTP checks passed on 5096; RFBank remained available on 5111. Pip check
passed. Existing help remains the page-specific explanation below the divider.

To restore, stop both services using this database and compare any work performed
since initialization before restoring the backup to the canonical path. Do not
activate the backup as another permanent working database. Source rollbacks must
not re-enable the superseded separate-database/account-bootstrap launcher.
