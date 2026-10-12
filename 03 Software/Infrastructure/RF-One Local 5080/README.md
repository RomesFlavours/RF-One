# RF-One Local 5080 — start and stop RF-One on this PC

**Status:** local development tooling (see `../README.md`), not RF-One product code. Added 2026-10-12.

This folder starts and stops the **whole RF-One web application** (Bank, Project Management and every other RF-One
Web page) at **http://127.0.0.1:5080**. It uses:

- this worktree's code;
- the database in use today: `03 Software/RF-One Data Store/data/rfone.db`.

It does **not**:

- adopt a database;
- synchronise through OneDrive;
- hand over between PCs;
- migrate anything.

All of that belongs to the Bank Local Environment (`../Bank Local Environment/`, "Avvia Bank"), which this folder
does not use. The server is the same one "Avvia Bank" runs (`bank_local_env.serve`), with the same parameters:

- this PC is signed in automatically as the local `admin`, and only this PC;
- the header bar shows PC, database, code and AI mode;
- the AI mode is SESSION.

## Commands

Double-click in this folder, or run `run.ps1 <command>` from PowerShell:

| Command | What it does |
|---|---|
| **Avvia RF-One 5080.cmd** | Checks that port 5080 is free and that the database revision equals the code's migration head, then starts the server detached and waits until `/bank` answers. If RF-One is already running on 5080, it starts nothing. If another program holds the port, or the revision differs, it refuses and starts nothing. |
| **Ferma RF-One 5080.cmd** | Stops only the RF-One server listening on 5080 (`bank_local_env.serve 5080`). Any other program on the port is left alone. |
| **Stato RF-One 5080.cmd** | Shows the database, the server process and the HTTP status of `/bank` and `/projects`. Changes nothing. |

`--port N` runs the same commands on another port, for example to try a change without touching 5080.

- Python: the one named in `../Bank Local Environment/machines/<COMPUTERNAME>.json`.
- Log: `%LOCALAPPDATA%\RF-One\Local 5080\server.log`.
- State: `%LOCALAPPDATA%\RF-One\Local 5080\state-<port>.json`.

## Why the server does not die with whoever started it

On Windows, a venv's `python.exe` is only a redirector: it runs the real interpreter inside a kill-on-close job and
waits for it. A server started through it died, with no traceback, as soon as the redirector was ended. This
happened on MINIPC-KSYR1 on 2026-10-12, when the server was started from a Claude Code session.

The launcher therefore starts the base interpreter directly and tells it which venv to use (`__PYVENV_LAUNCHER__`),
exactly as the redirector itself does. The server is detached, depends on no other process, and keeps running after
the window, terminal or session that started it is closed.

The same correction is applied to "Avvia Bank" (`bank_local_env/handoff.py`, `_spawn`).

## Code changes

The server keeps the code it started with. After a change to the code or to the templates: **Ferma**, then
**Avvia**. When a migration is needed, Avvia refuses. Apply the migration first, with a backup copy of the
database, then start again.
