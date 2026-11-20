# Local continuity across OneDrive PCs

## Cambio PC (current procedure, Product Owner 2026-11-18)

One command, `Cambio PC.cmd` at the project root (`cambio_pc.py`, standard library only). It picks the mode from `output/cambio-pc/handoff.json`:

| Situation | Mode | What it does |
|---|---|---|
| Not closed, or open on this PC | depart | Stops local RF-One Python servers/workers (by code path or RF-One port), dumps the canonical PostgreSQL (`%LOCALAPPDATA%\RF-One\AWS-Copy\20261025T130037Z`, port 55436) and stops it, stops other local PostgreSQL instances, checkpoints and checks SQLite (`RFBank/rfone.db` in OneDrive; `email-control-local.db` copied from `%LOCALAPPDATA%`), verifies all ports free, writes `output/cambio-pc/current/` (hash manifest), `handoff.json` (closed) and `PASSAGGIO.md`, then waits until OneDrive reports every package file synchronized. |
| Closed by another PC | arrive | Marks the package folders "always keep on this device", verifies hashes (waits for download), refuses if RF-One servers are open or if this PC's local databases changed after its own last closure, backs up this PC's databases to `%LOCALAPPDATA%\RF-One\Backups\cambio-pc\` (one restore point, replaced each time), restores PostgreSQL into the same canonical path/port (creating it from the packaged runtime on a fresh PC), verifies every table count and Alembic revision, restores the SQLite copies and marks the handoff open on this PC. |
| Closed by this PC | — | Says so. `Cambio PC.cmd riapri` reopens here without switching. |

Not done by design: no Git commit/push, no AWS access, no credential copy (DPAPI mailbox secrets, tokens and SMTP settings stay per PC). Only one previous package is kept (`output/cambio-pc/previous`). `output/` is Git-ignored: the package holds private data. The earlier `Prepara cambio PC.cmd` / `Riprendi lavoro locale.cmd` workflow below is superseded by `Cambio PC.cmd` and has been kept unchanged pending the Product Owner's decision on removal.

Scope: preserve the current main-checkout MyRF/Registry/Kitchen/Training/Selection/Tips development state and its actual loopback PostgreSQL database. This tooling does not publish, migrate a schema, grant permissions or change AWS. RFBank remains a separate existing application; do not replace it with an older recovery database.

## Approved workflow

1. `python continuity.py snapshot` creates a transaction-consistent PostgreSQL recovery dump, source archive, portable PostgreSQL runtime and hash manifest under the Git-ignored `output/local-continuity/current/`. It leaves the current database and services unchanged.
2. Before switching computers, close local RF-One applications and run `Prepara cambio PC.cmd` at the project root. It refreshes the checkpoint and verifies that the source database stopped. Wait for OneDrive to finish synchronizing the complete project, including `output/local-continuity/current/`. Select **Always keep on this device** on the destination PC. Never work on both PCs at once. A synchronized marker is advisory, not a distributed lock.
3. On the destination Windows x64 PC with Python 3.12 installed, run `Riprendi lavoro locale.cmd` at the project root. The tool verifies the recovery hashes and source checkpoint, prepares a per-PC isolated Python environment and restores the snapshot only into a new, project-relative PostgreSQL directory. It refuses occupied ports and never overwrites an existing database. Run `python continuity.py check` first to verify the transferred package without restoring anything.
4. The local entry point stays the existing `visual_menu_local.py`: Italian, automatic sign-in as the existing `rfone` operator with its actual grants, no environmental warning banner. Cloud/API/Codex credentials and SMTP configuration are per-PC; they are not copied into the recovery package.
5. `python continuity.py release` stops only the PostgreSQL instance owned by this portable environment, verifies it stopped, exports its latest state first, and marks the handoff closed. Close the web-server console before this command. Wait for OneDrive synchronization before using another PC. The original PC's legacy PostgreSQL instance is never stopped by this tool.

## Safety and restoration

The private dump contains real application data and password hashes. Keep `output/` excluded from Git and never publish its contents. Only the code and instructions here may be versioned. No old backup is automatically restored over existing data. A restore is explicitly a first setup on the destination; future starts reuse that same project-relative working database.

Snapshots record the source host and time. On the source host, normal startup refuses to create a parallel permanent database when the existing canonical installation is present. `--verify-restore` uses a disposable database and compares every table's row count and schema revisions; it removes only that disposable test directory after stopping its server.

Absolute local file references are relocated only in a newly restored database, never in the source database. Remote S3 references remain remote unless a separately documented existing local copy is available. Such documents and cloud AI require that PC's own authorized access. No cloud credential is embedded.

This preparation can be verified on the source computer; OneDrive completion and execution on the second computer must still be checked there.
