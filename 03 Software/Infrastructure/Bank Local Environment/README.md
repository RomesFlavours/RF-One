# Bank Local Environment — one Bank, two PCs

**Task:** BANK_LOCAL_ENVIRONMENT_001 (2026-10-11). **Status:** implemented and verified on copies on ASUS2026;
**MINIPC-KSYR1 not yet verified**; the authoritative work database not yet adopted (see "First adoption").

Local dev-environment tooling (see `../README.md`): not RF-One product code. It makes the Bank working
environment the same on ASUS2026 and MINIPC-KSYR1, so that the Product Owner can close on one PC, wait for the
delivery, open on the other and work — with no configuration, path or procedure rebuilt by hand.

## The three commands

Double-click in this folder (or run `run.ps1 <command>` from PowerShell):

| Command | What it does |
|---|---|
| **Configura PC.cmd** | Once per PC (and after a change of `requirements.lock.txt`): checks Python, installs the locked dependencies when they differ, checks OneDrive, migrations and port, and marks `machines/<PC>.json` verified. |
| **Avvia Bank.cmd** | Checks data, code, migrations, dependencies and port; takes the authoritative database from OneDrive when it is newer; starts Bank on **http://127.0.0.1:5080/bank**. If anything is missing it says exactly what and starts **nothing** — never an old version, never another database. |
| **Chiudi Bank.cmd** | Stops the server, makes a consistent copy of the database, delivers it to OneDrive and waits for OneDrive to confirm the upload. It says separately **FILE PREPARATO** and **SINCRONIZZAZIONE COMPLETATA** (or NON ANCORA CONFERMATA). |
| Stato Bank.cmd | Shows manifest, lease, local state, server and OneDrive state. Changes nothing. |

**Changing PC:** *Chiudi Bank* on the first PC → wait for **SINCRONIZZAZIONE COMPLETATA** → *Avvia Bank* on the
other PC. *Avvia Bank* verifies the SHA-256 of what arrived: that is the definitive proof of the delivery.

Options (append to the command, e.g. `run.ps1 start --migrate`):

| Option | Use |
|---|---|
| `start --migrate` | The database needs migrations the code has: a copy is kept, then they are applied. |
| `start --accept-code` | The code differs from the code the database was closed with, on purpose (you changed it). Without it, a difference means OneDrive has not finished syncing the code. |
| `start --ai PROVIDER` | Use the AI provider (`RFONE_AI_PROVIDER`, e.g. AWS Bedrock) instead of the Claude Code session — explicit only. |
| `close --check` | Only verify again that OneDrive delivered the last close. |
| `--profile test` | The same procedure on the TEST copy: port 5082, `RF-One Bank Handoff TEST`, and the page says **COPIA DI PROVA**. |

## Where things are

| What | Where | Synced? |
|---|---|---|
| Code, migrations, this tool | the repository worktree (`rf-one-bank-simple-who-rules`) | OneDrive (and git) |
| Shared configuration | `environment.json`, `requirements.lock.txt` | yes |
| What differs per PC (Python path, OneDrive folder) | `machines/<COMPUTERNAME>.json` — nothing else | yes |
| **Working database** (open while Bank runs) | `%LOCALAPPDATA%\RF-One\Bank\rfone.db` | **no — never** |
| Delivered snapshots + `manifest.json` + `lease.json` | `OneDrive\AI-RF-ONE\RF-One Bank Handoff\` | yes |
| Copies kept before replacing / migrating | `%LOCALAPPDATA%\RF-One\Bank\previous\` | no |
| Server log | `%LOCALAPPDATA%\RF-One\Bank\server.log` | no |

OneDrive never syncs an open SQLite file: the working database is local, and OneDrive carries only closed,
verified snapshots, each under a new name (`snapshots/rfone_gNNNN_<PC>_<time>.db`), never overwritten.

## What protects newer work

| Situation | What happens |
|---|---|
| Bank is open on the other PC (lease OPEN there) | *Avvia Bank* refuses: close there first. |
| The snapshot has not fully arrived | *Avvia Bank* refuses (file missing, or SHA-256 ≠ manifest): wait for OneDrive. |
| The manifest here is older than this PC's database | *Avvia Bank* refuses: OneDrive has not delivered the latest manifest. |
| The code differs from the closing code | *Avvia Bank* refuses (unless `--accept-code`). |
| Data newer than the code (unknown migration) | *Avvia Bank* refuses. |
| Port 5080 used by another process | *Avvia Bank* refuses and names the process; it never stops what it did not start. |
| OneDrive conflict copies `manifest-<PC>.json` / `lease-<PC>.json` | Both commands refuse. |
| **Two lines of work** (see below) | Both commands refuse; every copy is kept. |

### Two lines of work

It happens only if both PCs changed data from the same generation (e.g. Bank opened on a PC while the other was
still open, or work done outside *Avvia Bank*). Nothing is overwritten: the local database stays in
`%LOCALAPPDATA%\RF-One\Bank\rfone.db` and every delivered generation stays in `snapshots/`. Compare them:

```powershell
run.ps1 compare "<older or local>.db" "<newer>.db"
```

`compare` lists, table by table, rows only in the first, only in the second, and changed (movements, WHO/WHY
decisions, allocations, WHO/WHY catalogs, WHO/General Rules, Standards, AI rules, interpretations…). Decide which
work to keep — a Product Owner decision — then adopt the result (`adopt --replace-authority <PC>`).

### Conflict copies

OneDrive writes `manifest-<PC>.json` when two PCs changed `manifest.json` before syncing. Open both, keep the one
with the higher `generation` whose snapshot exists, delete the other, then run *Stato Bank*.

## First adoption (once)

The authoritative database is chosen by comparing content, never by file date (`compare`). Once chosen, on the
PC that holds it, with its old server stopped:

```powershell
run.ps1 adopt --from "<path of the chosen rfone.db>" --note "why this one"
```

It becomes generation 1; the original file is not modified or moved. From then on only *Avvia* / *Chiudi*.

## AI Rules: the Claude Code session

The default AI mode is **SESSION** (`environment.json`): the Preview button never calls an AI provider. See
[SESSION_INTERPRETATION.md](SESSION_INTERPRETATION.md).

## The page header

Every page served by *Avvia Bank* shows a bar with the **PC**, the **database path and generation**, the **code
version** (branch@commit · code fingerprint) and the **AI mode**; on the test profile it says **COPIA DI PROVA**
in a warning colour. Servers not started by *Avvia Bank* (AWS, tests) show no bar.

## Verification

| Where | What was verified | When |
|---|---|---|
| ASUS2026 | Configura PC; adopt; start refused without `--migrate`, then migrated; header bar; SESSION preview waits, session interprets, preview runs with 0 AI calls; close → FILE PREPARATO + SINCRONIZZAZIONE COMPLETATA; second PC simulated (`COMPUTERNAME=MINIPC-KSYR1`): takes the generation with SHA-256 verified, the first PC refused while the lease is open, round trip back; refusals: two lines of work, conflict copy, incomplete snapshot, busy port, data newer than code | 2026-10-11, test profile |
| MINIPC-KSYR1 | **not yet** — see "Checks on the second PC" | — |

### Checks on the second PC (MINIPC-KSYR1)

1. Wait until OneDrive shows this folder in sync. Run **Configura PC.cmd**: it must end with **PC CONFIGURATO**
   and the same `code` fingerprint as ASUS2026 shows; if it reports a different Python path or OneDrive folder,
   correct `machines/MINIPC-KSYR1.json` (the only per-PC file).
2. **Stato Bank.cmd** (`--profile test`): manifest and lease visible, no conflict copies.
3. Test round trip: `run.ps1 --profile test start` → open http://127.0.0.1:5082/bank (bar: MINIPC-KSYR1,
   COPIA DI PROVA, AI SESSIONE) → `run.ps1 --profile test close` → **SINCRONIZZAZIONE COMPLETATA** → on
   ASUS2026 `run.ps1 --profile test start` takes the new generation (SHA-256 verified).
4. Only then: first adoption of the work database on MINIPC-KSYR1 (its current `rfone.db`, server stopped).
