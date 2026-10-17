# LOCAL_ENVIRONMENT.md — rebuilding the RF-One local environment on another PC

**Survey date:** 2026-10-14, about 09:30 EDT (UTC−04:00), on PC **MINIPC-KSYR1**.
**Method:** read-only inspection of this PC (processes, ports, files, registry, git, SQLite opened in
read-only mode). Nothing was installed, configured, restarted, exported or sent to AWS.

**Audience:** a new Codex (or Claude Code) session on another PC that knows nothing of the session that
wrote this file. Every statement is tagged:

| Tag | Meaning |
|---|---|
| **[VERIFIED]** | observed on this PC at the survey date (command output, file content, running process) |
| **[CODE]** | read from the source code / config files; not exercised at runtime during the survey |
| **[DOC]** | taken from repository documentation only; not verified on this PC |
| **[MISSING]** | not present on this PC or not determinable |
| **[TODO]** | an operation still needed (by the Product Owner or the next session) |

> **The single most important fact:** the server on port 5080 does **not** run from this repository
> checkout (`RF One`, branch `main`). It runs from the git **worktree**
> `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules` (branch `feature/bank-simple-who-rules`),
> through the tool `03 Software\Infrastructure\Bank Local Environment\`, on a SQLite database **outside**
> OneDrive and outside the repository. A plain `git clone` reproduces none of the data and not all of the code.

---

## 1. PC and project

### 1.1 Operating system and shell [VERIFIED]

| Item | Value |
|---|---|
| Computer name | `MINIPC-KSYR1` (the other configured PC is `ASUS2026`) |
| OS | Microsoft Windows 11 Pro, 10.0.26100, 64-bit |
| Architecture | AMD64 (x64) |
| Windows user / profile | `servi` → `C:\Users\servi` |
| Shell used by the tooling | Windows PowerShell **5.1** (`powershell.exe`); the `.cmd` launchers call `powershell -NoProfile -ExecutionPolicy Bypass -File run.ps1 …`. Git Bash is also present (with Git for Windows) |
| OneDrive | personal OneDrive at `C:\Users\servi\OneDrive` (`%OneDrive%`) — the whole project lives inside it |
| Time zone | US Eastern (timestamps carry −04:00) |

### 1.2 Paths

| What | Path |
|---|---|
| Parent folder (not a git repo) | `C:\Users\servi\OneDrive\AI-RF-ONE\` — contains an outer `CLAUDE.md`, the main checkout, all worktrees, Bank handoff folders and non-repo material (`Api`, `Documents`, `Images`, `Menu`, `Models-Shelby & Pino`, `RF-ONE Manifest.pdf`) |
| Main repository checkout (this file) | `C:\Users\servi\OneDrive\AI-RF-ONE\RF One\` |
| **Code actually served on 5080** | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\` (git worktree) |
| Working directory of the launcher | `…\rf-one-bank-simple-who-rules\03 Software\Infrastructure\Bank Local Environment\` |
| Working directory of the Flask app | `…\rf-one-bank-simple-who-rules\03 Software\RF-One Web\` (`serve.py` does `os.chdir(WEB_DIR)`) [CODE] |

### 1.3 Git [VERIFIED]

| Item | Value |
|---|---|
| Remote | `origin` = `https://github.com/RomesFlavours/RF-One.git` (fetch and push) |
| Git | 2.55.0.windows.5, `core.autocrlf=true`, `core.longpaths=true`, `user.name=Pino` |
| `RF One` (main checkout) | branch `main` @ `ec9c6c4` (2026-10-13 21:12 −04:00, "Compensation: build the run from real Clover hours…") |
| `main` vs `origin/main` (last fetch 2026-10-13 22:38) | **diverged**: 1 local-only commit (`ec9c6c4`) and 23 remote-only commits; `origin/main` has `f63bf66` with the same message as `ec9c6c4` (probably the same change rewritten). Not resolved — Product Owner decision |
| Served worktree | `feature/bank-simple-who-rules` @ `851f437` (2026-10-14 07:33), equal to `origin/feature/bank-simple-who-rules` (0 ahead / 0 behind) |
| Stash in main checkout | `stash@{0}: bank-local-wip-before-realign-20261003t025237z` |
| Submodules / LFS | none |

Other worktrees registered on this PC (all share `RF One\.git`):

```
RF One                          ec9c6c4 [main]
rf-one-2.0-release              e0da1a3 [release/rf-one-2.0]
rf-one-bank-final-integration   34cff6a [integration/bank-final-check]
rf-one-bank-integration-check   c47c70e [integration/bank-reorder-check]
rf-one-bank-monthly-home        13c22f1 [feature/bank-monthly-process-home]
rf-one-bank-new-reconciliation  2953664 [feature/bank-new-reconciliation]
rf-one-bank-simple-who-rules    851f437 [feature/bank-simple-who-rules]   <-- served on 5080
rf-one-project-management       41c3575 [feature/project-management]
rf-one-restaurant-wines         4ccaf2d [feature/restaurant-wines-first-release]
C:\Users\servi\rfone-wt\bank-aws          7d1f3f6 [release/bank-aws]          (outside OneDrive)
C:\Users\servi\rfone-wt\remove-bank-aws   a77e917 [release/remove-bank-aws]   (outside OneDrive)
```

(`AI-RF-ONE\rf-one-main-pristine` exists but is **not** a git checkout.)

Each worktree's `.git` is a one-line file with an **absolute** path, e.g.
`gitdir: C:/Users/servi/OneDrive/AI-RF-ONE/RF One/.git/worktrees/rf-one-bank-simple-who-rules` — it only
works where that exact path exists (see §7.6).

### 1.4 Local changes that a clone would NOT bring [VERIFIED]

**Served worktree `rf-one-bank-simple-who-rules` — 13 uncommitted entries. These are part of the code
fingerprint the launcher checks, and one of them is the migration the working database is at:**

```
 M 01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_AI_RULES_001.md
 M 03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/ai_rule_operations.py
 M 03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/ai_rules.py
 M 03 Software/RF-One Data Store/rfone_data_store/models.py
 M 03 Software/RF-One Web/bank_ai_rule_routes.py
 M 03 Software/RF-One Web/static/css/rf-one.css
 M 03 Software/RF-One Web/static/js/bank-ai-rules.js
 M 03 Software/RF-One Web/templates/bank_ai_rules.html
 M 03 Software/RF-One Web/templates/base.html
?? 03 Software/RF-One Data Store/data/cleanup_logs/
?? 03 Software/RF-One Data Store/migrations/versions/a6e2c8f4b0d9_ai_rules_user_title.py   <-- DB revision
?? 03 Software/RF-One Web/tests/test_bank_ai_rule_title_http.py
?? 03 Software/RF-One Web/tests/test_bank_ai_rules_search_http.py
```

**Main checkout `RF One` — uncommitted (not used by the 5080 server):**

```
 M 01 Domains/Business Domain/Restaurant/README.md
 M 01 Domains/Shared Domains/Administration/Invoice Intake/README.md
 M 03 Software/RF-One Data Store/PURCHASING.md
 M 03 Software/RF-One Data Store/rfone_data_store/models.py
 M 03 Software/RF-One Data Store/rfone_data_store/purchasing/repository.py
 M CLAUDE.md
?? 01 Domains/Business Domain/Restaurant/MyRF/
?? 03 Software/RF-One Data Store/migrations/versions/540ee75caa65_merge_invoice_intake_and_restaurant_.py
?? 03 Software/RF-One Data Store/migrations/versions/b3f9d2c6e4a1_add_invoice_intake_data_model.py
?? 03 Software/RF-One Data Store/test_invoice_intake_data_model.py
?? 07 Tasks/Invoices/          (partly git-ignored: PDFs/JPGs/ZIPs/JSON stay local by rule)
?? LOCAL_ENVIRONMENT.md        (this file)
```

Git-ignored local material is listed in §4.5.

---

## 2. Runtime and dependencies

### 2.1 Tools and versions [VERIFIED]

| Tool | Version / location | Needed for |
|---|---|---|
| Python | **3.12.10**, per-user install `C:\Users\servi\AppData\Local\Programs\Python\Python312\python.exe`; `py` launcher present (only 3.12 registered) | everything (required: `environment.json` demands 3.12) |
| Bank venv | `C:\Users\servi\AppData\Local\RF-One\Bank\venv` (Python 3.12.10, `include-system-site-packages = false`) | the 5080 server |
| Git for Windows | 2.55.0 | code, launcher (`git rev-parse` for the header) |
| AWS CLI v2 | 2.36.40 at `C:\Program Files\Amazon\AWSCLIV2\aws.exe` | only AWS work — **not** needed for the local Bank |
| VS Code + Claude Code extension | `anthropic.claude-code-2.1.296-win32-x64` in `%USERPROFILE%\.vscode\extensions` | the Bank "SESSION" AI mode (see §6) |
| Node / npm | **[MISSING]** — not installed, not used (`.gitignore` says Node is "not currently used") | — |
| PostgreSQL / psql / pg_dump | **[MISSING]** — not installed; no PostgreSQL service | not needed locally (SQLite) |
| Docker | **[MISSING]** | not needed locally |
| sqlite3 CLI | **[MISSING]** — Python's built-in `sqlite3` (SQLite 3.49.1) is used instead | — |
| `claude` / `codex` on PATH | **[MISSING]** — the Bank code finds `claude.exe` inside the VS Code extension instead [CODE] | — |
| `gh` | **[MISSING]** | optional |

### 2.2 Virtual environment of the 5080 server [VERIFIED]

`pyvenv.cfg` records the exact creation command:

```powershell
C:\Users\servi\AppData\Local\Programs\Python\Python312\python.exe -m venv C:\Users\servi\AppData\Local\RF-One\Bank\venv
```

Installed by "Configura PC" (`bank_local_env setup`) with:

```powershell
& "$env:LOCALAPPDATA\RF-One\Bank\venv\Scripts\python.exe" -m pip install -r "C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\Infrastructure\Bank Local Environment\requirements.lock.txt"
```

There is no "activation" step: the launcher calls the venv's `python.exe` directly (path taken from
`machines\<COMPUTERNAME>.json`). For manual use: `& "$env:LOCALAPPDATA\RF-One\Bank\venv\Scripts\Activate.ps1"`.

Note [VERIFIED + CODE]: the running server process shows the **base** interpreter
(`…\Python312\python.exe -m bank_local_env.serve 5080`). This is intentional: `handoff.py` launches the
venv's base executable with `__PYVENV_LAUNCHER__` set to the venv `python.exe` (a Windows venv `python.exe`
is only a redirector), so the venv's packages are the ones loaded.

`requirements.lock.txt` (exact pins; "Avvia Bank" refuses to start if any installed version differs):

```
Flask==3.1.3  Werkzeug==3.1.8  Jinja2==3.1.6  itsdangerous==2.2.0  MarkupSafe==3.0.3  click==8.5.0
blinker==1.9.0  SQLAlchemy==2.0.52  greenlet==3.5.5  alembic==1.19.2  Mako==1.4.1  typing_extensions==4.16.0
requests==2.34.2  openpyxl==3.1.5  paramiko==3.5.1  boto3==1.43.91  botocore==1.43.91  psycopg2-binary==2.9.13
PyJWT==2.14.0  cryptography==50.0.1  tzdata==2026.3
```

The venv additionally contains their transitive dependencies (bcrypt 5.0.0, PyNaCl 1.6.2, cffi, pycparser,
certifi, urllib3, idna, charset-normalizer, jmespath, s3transfer, python-dateutil, six, et_xmlfile).
**pytest is not installed** in the venv nor in the system Python.

### 2.3 Other dependency files [VERIFIED]

| File | Content (ranges, not pins) |
|---|---|
| `03 Software/RF-One Web/requirements.txt` | Flask>=3.0, SQLAlchemy>=2.0,<3.0 |
| `03 Software/RF-One Data Store/requirements.txt` | SQLAlchemy, alembic, requests, openpyxl, paramiko, boto3, botocore[crt], psycopg2-binary, PyJWT[crypto], tzdata |
| `03 Software/InvoiceIntake/requirements.txt` (main checkout) | Flask, pytesseract, Pillow, pdfplumber, pdf2image, openpyxl, boto3 |

### 2.4 System Python (used by work outside the Bank server) [VERIFIED]

48 packages, installed directly into the per-user Python (no venv), notably **different pins** from the lock
(alembic 1.19.1, boto3 1.43.89, paramiko 5.0.0, PyJWT 2.13.0, psycopg2-binary 2.9.12) — which is why the
Bank uses its own venv. Full list at survey time:

```
alembic==1.19.1, awscrt==0.36.0, bcrypt==5.0.0, blinker==1.9.0, boto3==1.43.89, botocore==1.43.89,
certifi==2026.7.22, cffi==2.1.1, charset-normalizer==3.5.1, click==8.5.0, cryptography==50.0.1,
et_xmlfile==2.0.0, Flask==3.1.3, greenlet==3.5.5, idna==3.19, invoke==3.0.3, itsdangerous==2.2.0,
Jinja2==3.1.6, jmespath==1.1.0, lxml==6.1.2, Mako==1.4.1, MarkupSafe==3.0.3, openpyxl==3.1.5,
packaging==26.3, paramiko==5.0.0, pdf2image==1.17.0, pdfminer.six==20260107, pdfplumber==0.11.10,
pillow==12.3.0, pip==25.0.1, psycopg2-binary==2.9.12, pycparser==3.0, PyJWT==2.13.0, PyNaCl==1.6.2,
pypdfium2==5.13.0, pytesseract==0.3.13, python-dateutil==2.9.0.post0, python-docx==1.2.0, pyxlsb==1.0.10,
reportlab==5.0.1, requests==2.34.2, s3transfer==0.19.2, six==1.17.0, SQLAlchemy==2.0.52,
typing_extensions==4.16.0, tzdata==2026.3, urllib3==2.7.0, Werkzeug==3.1.8
```

### 2.5 Invoice / PDF reading tools

| Component | State on this PC |
|---|---|
| Python wrappers `pytesseract`, `pdf2image`, `pdfplumber`, `pypdfium2`, `pdfminer.six`, `Pillow`, `reportlab` | installed in the **system** Python (not in the Bank venv) [VERIFIED] |
| **Tesseract OCR binary** (`tesseract.exe`) | **[MISSING]** — not on PATH, not in `C:\Program Files\Tesseract-OCR` [VERIFIED] |
| **Poppler** (`pdftoppm`, needed by `pdf2image`) | **[MISSING]** [VERIFIED] |
| AWS Textract provider (`03 Software/InvoiceIntake/providers/textract_provider.py`) | code present; needs AWS credentials and network [CODE] |
| Bedrock vision trials (`07 Tasks/Invoices/Risultati AI visiva/run_bedrock_vision.py`) | scripts present; need AWS [CODE] |

So on this PC the local OCR path of InvoiceIntake cannot work (the InvoiceIntake tests skip OCR cases when
`tesseract`/`pdftoppm` are absent [CODE]); text-layer PDF reading via `pdfplumber` works with the system
Python. InvoiceIntake is **not** part of the 5080 server; it is a separate prototype (`app.py`, port 5000).

---

## 3. Local configuration

### 3.1 Configuration files

| File | Tracked in git? | Role |
|---|---|---|
| `…\Bank Local Environment\environment.json` | yes | profiles (`work` port 5080, `test` port 5082), handoff and local dirs, `ai_mode: SESSION`, `claude_code_cli: auto`, code paths for the fingerprint, `sync_wait_seconds: 600` |
| `…\Bank Local Environment\machines\MINIPC-KSYR1.json` | yes | **the only per-PC file**: `python` = `C:\Users\servi\AppData\Local\RF-One\Bank\venv\Scripts\python.exe`, `onedrive` = `C:\Users\servi\OneDrive`, `verified` timestamp |
| `…\Bank Local Environment\machines\ASUS2026.json` | yes | same for ASUS2026 (uses the **system** Python there, not a venv) |
| `…\Bank Local Environment\requirements.lock.txt` | yes | exact dependency pins |
| `%LOCALAPPDATA%\RF-One\Bank\state.json` | no (local) | launcher state: generation 3, PID 19180, port 5080, status RUNNING, AI SESSION |
| `RF One\.env` (main checkout only) | **no** (git-ignored) | secrets for Clover, Mercury sandbox, Aruba IMAP, AI provider — see 3.3 |
| `RF One\.env.example` | yes | template of the variables |
| `RF One\Secrets\` | no (git-ignored) | **empty** at survey time (historically held a Mercury sandbox token file) |
| `%USERPROFILE%\.aws\config`, `credentials`, `login\`, `cli\` | no | AWS CLI profiles (see §6) |

`.env` lookup [CODE]: `rfone_data_store/database.py` walks up to 8 parent folders from
`rfone_data_store/` looking for a `.env`. From the served worktree there is **no** `.env` on that path
(`rf-one-bank-simple-who-rules\` has only `.env.example`; `AI-RF-ONE\.env` does not exist) — so the 5080
server reads **no `.env` file**. Code run from `RF One\` does read `RF One\.env`.

User- and machine-level Windows environment variables: **none** with names matching
RFONE/AWS/ANTHROPIC/CLAUDE/DATABASE/FLASK/MERCURY/CLOVER/ARUBA/PG [VERIFIED].

### 3.2 Environment variables of the 5080 server

All set by `bank_local_env start` (`handoff.py`) on top of the launching shell's environment, then
`serve.py` [CODE]:

| Variable | Function | Required | Value / source |
|---|---|---|---|
| `RFONE_DATABASE_URL` | database URL | **yes** (`serve.py` refuses without it) | `sqlite:///C:/Users/servi/AppData/Local/RF-One/Bank/rfone.db` (built by `start`) |
| `RFONE_LOCAL_ENV_PC` | PC name in header; also a guard | **yes** (`serve.py` refuses without it) | `%COMPUTERNAME%` |
| `RFONE_LOCAL_ENV_KIND` / `_LABEL` / `_DB` / `_GENERATION` / `_CODE` | header bar (WORK/TEST, DB path, generation, branch@commit · fingerprint) | set by `start` | from `environment.json`, manifest, git |
| `RFONE_BANK_AI_MODE` | `SESSION` (no AI provider call from Preview) or `PROVIDER` | set by `start` | `SESSION` (`environment.json`; override `start --ai PROVIDER`) |
| `RFONE_BANK_CLAUDE_CODE_CLI` | SESSION only: `auto` = Preview asks the local Claude Code CLI | set by `start` | `auto` |
| `RFONE_BANK_CLAUDE_CODE_MODEL` | model for that CLI | optional | default `claude-opus-5-5` |
| `RFONE_WEB_TEST_SECRET_KEY` | Flask session secret when `RFONE_FLASK_SECRET_KEY` is absent | set by `serve.py` (`setdefault`) | a fixed local-only literal in `serve.py` (not a secret) |
| `RFONE_FLASK_SECRET_KEY` | production Flask secret | not used locally | **never set it locally to the production value** |
| `AWS_REGION` | SES e-mail / AWS clients | optional | default `us-east-1` in `app.py` |
| `RFONE_EMAIL_FROM_ADDRESS` | sender for account e-mails (AWS SES) | optional | empty locally → e-mail flows not functional |
| `RFONE_TIPS_URL` | link to Tips home | optional | default `/tips/` |
| `ALEMBIC_DATABASE_URL_OVERRIDE` | overrides the DB URL for `alembic` only | optional | not set — **dangerous if pointed at production** |
| `RFONE_CLOVER_JOB_*`, `PAYPAL_*`, `MERCURY_SANDBOX_API_TOKEN` | integrations (Clover ECS job, PayPal API, Mercury sandbox) | optional | not set for the Bank server |

Caveat: the server inherits the environment of the shell that ran "Avvia Bank". At the survey the
User/Machine scopes contain none of the variables above, so only the ones set by `start` apply — unless that
shell had extra variables exported (not observable for an already-running process).

### 3.3 Secrets — what exists and how to obtain it (values intentionally omitted)

`RF One\.env` contains these keys [VERIFIED, values not read except the non-secret ones]:

| Key | Secret? | How to recover safely |
|---|---|---|
| `CLOVER_MERCHANT_ID`, `CLOVER_API_TOKEN` | yes | Clover merchant dashboard → API tokens; or copy `.env` privately (USB / password manager), never via git or chat |
| `MERCURY_SANDBOX_API_TOKEN` | yes | Mercury sandbox dashboard |
| `ARUBA_IMAP_USERNAME`, `ARUBA_IMAP_PASSWORD` | yes | Aruba mailbox owner (Product Owner) |
| `RFONE_AI_PROVIDER` | no | `BEDROCK` |
| `RFONE_BEDROCK_MODEL_ID` | no | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `AWS_REGION` | no | `us-east-1` |

Other variables documented in `.env.example` but not set here: `RFONE_DATABASE_URL`, `RFONE_FLASK_SECRET_KEY`,
`RFONE_WEB_BASE_URL`, `ANTHROPIC_API_KEY`, `ARUBA_IMAP_HOST/PORT/MAILBOX/POLL_INTERVAL_SECONDS/USE_SSL`.

The local Bank server needs **none** of these secrets.

### 3.4 PC-specific absolute paths to adapt

| Where | Value here | Adapt when |
|---|---|---|
| `machines\<COMPUTERNAME>.json` → `python` | `C:\Users\servi\AppData\Local\RF-One\Bank\venv\Scripts\python.exe` | always on a new PC (new file named after the new `COMPUTERNAME`) |
| `machines\<COMPUTERNAME>.json` → `onedrive` | `C:\Users\servi\OneDrive` | user name or OneDrive folder differs |
| `environment.json` → `handoff_dir` | `{onedrive}\AI-RF-ONE\RF-One Bank Handoff` | project not under `<OneDrive>\AI-RF-ONE` |
| `environment.json` → `local_dir` | `{localappdata}\RF-One\Bank` | normally never |
| worktree `.git` files | `gitdir: C:/Users/servi/OneDrive/AI-RF-ONE/RF One/.git/worktrees/…` | user profile path differs (`git worktree repair`) |
| `03 Software\Infrastructure\README.md`, `aws-dev-access.ps1` | hard-coded `C:\Users\servi\OneDrive\AI-RF-ONE\RF One\…` and AWS CLI path | only for AWS work |

---

## 4. Database and data

### 4.1 Engines

| Database | Engine | Where | Role |
|---|---|---|---|
| **Bank working DB (served on 5080)** | **SQLite 3.49.1** (Python built-in), journal mode `delete`, file-based, no server process, no port | `C:\Users\servi\AppData\Local\RF-One\Bank\rfone.db` (22,126,592 bytes) — **outside OneDrive** | **LOCAL** |
| Bank handoff snapshots | SQLite files (closed, never open) | `C:\Users\servi\OneDrive\AI-RF-ONE\RF-One Bank Handoff\snapshots\` | local copies synced by OneDrive between the two PCs |
| Production RF-One | PostgreSQL on AWS RDS behind ECS (`rfone-web`, `rfone-tips`, `rfone-selection`, …) | AWS `us-east-1` | **REMOTE — never used by the local server** [DOC: `03 Software/Infrastructure/deploy/`] |

No PostgreSQL, MySQL or Docker is running or installed locally [VERIFIED].

### 4.2 State of the working database [VERIFIED, opened read-only]

| Item | Value |
|---|---|
| Alembic revision | `a6e2c8f4b0d9` — defined only in the **untracked** file `migrations/versions/a6e2c8f4b0d9_ai_rules_user_title.py` of the served worktree (its parent is `d2b6f8a4c0e7`) |
| Tables | 263 |
| Rows (non-empty tables, main ones) | `raw_bank_transactions` 3234, `financial_transactions` 3234, `bank_transaction_explanations` 1835, `bank_ai_rule_preview_items` 4186, `bank_ai_rule_application_items` 2178, `bank_accounting_classifications` 137, `bank_occurrences` 118, `bank_transaction_reasons` 98, `bank_ai_rule_interpretations` 40, `bank_ai_rules` 9, `payment_instruments` 13, `bank_import_batches` 13, `rfone_accounts` 1 (the local `admin`), `project` 1 … |
| Handoff manifest | generation **3**, parent 2, snapshot `snapshots/rfone_g0003_MINIPC-KSYR1_20261014_092215.db`, SHA-256 `d94c2f42…67be0`, closed by MINIPC-KSYR1 at 2026-10-14 09:22:17, code `feature/bank-simple-who-rules@851f437 · code 12d9066f7b` |
| Lease | **`OPEN` on MINIPC-KSYR1 since 2026-10-14 09:22:50, generation 3** — another PC will refuse to start until "Chiudi Bank" is run here |

Other SQLite files (not served on 5080):

| File | Revision | Note |
|---|---|---|
| `rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\data\rfone.db` | `d2b6f8a4c0e7` | the pre-launcher working DB of the worktree (+ ~20 `rfone_backup_before_*.db`, `rfone-Asus2026.db`, `rfone-MINIPC-KSYR1.db`) |
| `RF One\03 Software\RF-One Data Store\data\rfone.db` | `b3f9d2c6e4a1` (untracked Invoice Intake migration) | 253 tables, 3.6 MB; the default DB when RF-One Web is run from the main checkout |
| `RF One\03 Software\InvoiceIntake\data\*.db` | — | `document_acquisitions.db`, `mailbox_acquisition.db`, `supplier_format_training.db` |
| `%LOCALAPPDATA%\RF-One\Bank\previous\` | — | 4 files, 84 MB: copies kept before replacing/migrating |
| `%LOCALAPPDATA%\RF-One\Bank\transfer-final-20261013\`, `transfer-review-20261012\`, `rules-cleanup-20261014\` | — | artifacts of earlier Bank sessions (≈21 MB) |

### 4.3 Empty working schema on a new PC [CODE — not executed]

Migrations are Alembic (`03 Software/RF-One Data Store/alembic.ini`, `migrations/`); the URL comes from
`ALEMBIC_DATABASE_URL_OVERRIDE` → `RFONE_DATABASE_URL` → `.env` → default `data/rfone.db`. Use an explicit,
throw-away SQLite path so nothing else is touched:

```powershell
# working directory: <worktree>\03 Software\RF-One Data Store
$env:RFONE_DATABASE_URL = "sqlite:///C:/RFOneScratch/empty.db"
& "$env:LOCALAPPDATA\RF-One\Bank\venv\Scripts\python.exe" -m alembic upgrade head
# optional: an admin account (password typed interactively, never on the command line)
Set-Location "..\RF-One Web"
& "$env:LOCALAPPDATA\RF-One\Bank\venv\Scripts\python.exe" create_admin.py --username admin --display-name "Local Admin"
Remove-Item Env:RFONE_DATABASE_URL
```

The local launcher auto-logs in as the account with `username == "admin"` (status ACTIVE) for requests from
127.0.0.1 [CODE]. To serve an empty DB through the launcher use the `test` profile and
`run.ps1 --profile test adopt --from C:\RFOneScratch\empty.db --note "empty schema"` — never the work profile.

### 4.4 Copy of the current data [DOC + CODE — not executed]

The supported path is the launcher's own handoff, not a manual copy:

1. On MINIPC-KSYR1: **Chiudi Bank.cmd** → wait for **SINCRONIZZAZIONE COMPLETATA**. This stops the server,
   writes a consistent snapshot `snapshots/rfone_g0004_…db`, updates `manifest.json`, sets the lease CLOSED.
2. On the new PC (OneDrive synced): **Avvia Bank.cmd** → it copies that snapshot to
   `%LOCALAPPDATA%\RF-One\Bank\rfone.db` after verifying its SHA-256.

Without OneDrive: after step 1, copy `RF-One Bank Handoff\` (manifest, lease, snapshots) to the same relative
place on the new PC. Never copy `%LOCALAPPDATA%\RF-One\Bank\rfone.db` while the server is running.

### 4.5 Local data outside git (needed for a full reproduction) [VERIFIED sizes]

| Path | Size | Needed for |
|---|---|---|
| `%LOCALAPPDATA%\RF-One\Bank\` (excluding `venv`) | ≈130 MB | Bank working DB, previous copies, logs, state — **not synced** |
| `AI-RF-ONE\RF-One Bank Handoff\` | 3 snapshots × 22 MB | the authoritative Bank data — synced by OneDrive |
| `AI-RF-ONE\RF-One Bank Handoff TEST\` | — | test profile (port 5082) |
| `RF One\Bank\` (git-ignored) | 45 files, 17 MB | bank downloads/exports, `RfBank.xlsx`, `WHY WHO.xlsx`, historic data, baseline manifest |
| `RF One\03 Software\InvoiceIntake\uploads\` | 722 files, 19.5 MB | uploaded invoices (real supplier documents) |
| `RF One\03 Software\InvoiceIntake\data\` | 5 files | InvoiceIntake SQLite + legacy Excel |
| `RF One\01 Domains\Shared Domains\Administration\Invoice Intake\Invoices\Raw\` | 11 files, 12 MB | real invoice reference copies |
| `RF One\07 Tasks\Invoices\` (PDF/JPG/ZIP/JSON ignored) | 92 files, 121 MB | invoice-reading trials (Textract / Bedrock) |
| `RF One\03 Software\Clover Data Explorer\data\` (raw/reference/generated ignored) and `\Download\` | ≈66 MB | Clover exports |
| `RF One\03 Software\Selection\uploads\` | 43 files | résumés (personal data) |
| `RF One\03 Software\RF-One Data Store\data\` | 3.5 MB | main-checkout DB + an AWS Tips export (`aws_tips_domain_export_pre_reset_*.json`) |
| `RF One\.env` | 399 B | secrets (§3.3) |
| `%USERPROFILE%\.aws\` | — | AWS profiles/credentials (only for AWS work) |
| `AI-RF-ONE\` non-repo folders (`Api`, `Documents`, `Images`, `Menu`, `Models-Shelby & Pino`, `RF-ONE Manifest.pdf`) | — | not used by the software; reference material |

Many of these contain personal or financial data: transfer them only via OneDrive / encrypted media,
never via git, chat or a public share.

---

## 5. Local server

### 5.1 How it runs now [VERIFIED]

| Item | Value |
|---|---|
| Listener | `127.0.0.1:5080` (loopback only), PID 19180, started 2026-10-14 09:22:50 |
| Process command line | `C:\Users\servi\AppData\Local\Programs\Python\Python312\python.exe -m bank_local_env.serve 5080` (base interpreter of the venv, see §2.2) |
| Started by | `Avvia Bank.cmd` → `run.ps1 start` → `<venv python> -m bank_local_env start` (log line `===== 2026-10-14T09:22:50-04:00 start generation 3 port 5080`) |
| Process cwd at launch | `…\rf-one-bank-simple-who-rules\03 Software\Infrastructure\Bank Local Environment\`; then `serve.py` changes to `…\03 Software\RF-One Web\` and imports `app` |
| Web server | Flask/Werkzeug development server (`app.run(host="127.0.0.1", port=5080, debug=False, use_reloader=False, threaded=True)`), detached (`DETACHED_PROCESS`, no window) |
| Configuration loaded | `environment.json` (profile `work`), `machines\MINIPC-KSYR1.json`, manifest/lease in the handoff folder, env vars of §3.2; **no `.env`** |
| URL | **http://127.0.0.1:5080/bank** (also `/`, `/projects`, `/bank/ai-rules`, …) — local auto-login as `admin` |
| Logs | `%LOCALAPPDATA%\RF-One\Bank\server.log` (stdout+stderr appended; older `server.log.err/.out`) |
| Other processes | none required: no worker, no queue, no container, no DB server. Two other `python.exe` processes were present (PIDs 16528 system Python, 17192 venv Python) with no listening port; their command lines were not readable — probably leftover/helper processes, not part of the server |
| Autostart | **none**: no scheduled task, startup-folder entry or Windows service for RF-One [VERIFIED] |

An older parallel launcher left traces in `%LOCALAPPDATA%\RF-One\Local 5080\` (`state-5080.json`: PID 47208,
DB `…\rf-one-bank-simple-who-rules\…\data\rfone.db`, 2026-10-14 06:48; it is not running and its code is not
in the repository). CLAUDE.md forbids ad-hoc launchers: use only the commands below.

### 5.2 Start / stop / restart / status

Run from Explorer by double-click, or from PowerShell (any directory):

```powershell
$B = "C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\Infrastructure\Bank Local Environment"
& "$B\run.ps1" status           # Stato Bank   — changes nothing
& "$B\run.ps1" start            # Avvia Bank   — port 5080
& "$B\run.ps1" close            # Chiudi Bank  — stop + snapshot + OneDrive delivery
& "$B\run.ps1" setup            # Configura PC — once per PC / after a lock-file change
```

Restart = `close` then `start`. Useful options: `start --migrate` (DB needs migrations the code has; a copy
is kept first), `start --accept-code` (code changed on purpose), `start --ai PROVIDER`, `close --check`,
`--profile test` (port 5082, "COPIA DI PROVA"). Full behaviour: `Bank Local Environment\README.md`.

### 5.3 Alternatives (suggested, not the current setup)

- Running RF-One Web directly (`python app.py` in `03 Software\RF-One Web`) uses `RFONE_DATABASE_URL` /
  `.env` / the repo default DB and has no handoff protection — avoid for Bank work.
- Production uses a WSGI server (Gunicorn) on AWS ECS — not applicable locally.

---

## 6. External services

| Service | Used by | Local status |
|---|---|---|
| **OneDrive** | carries code (worktree folders) and Bank snapshots between PCs | **required** for the two-PC Bank workflow |
| **Claude Code (VS Code extension)** | Bank AI Rules in SESSION mode: Preview asks the local `claude.exe` (from `%USERPROFILE%\.vscode\extensions\anthropic.claude-code-*\resources\native-binary\`) with the user's Claude login; see `SESSION_INTERPRETATION.md` | needs network + Claude login; no AWS |
| GitHub `RomesFlavours/RF-One` | source code | network + GitHub credentials (Git Credential Manager) |
| AWS (`us-east-1`, account `418674484214`) | production RF-One (ECS/RDS/S3/CloudFront/CloudWatch/ECR), SES e-mail, Bedrock (`RFONE_AI_PROVIDER=BEDROCK`), Textract, Clover ECS jobs | **not used by the local Bank server** in SESSION mode |
| Anthropic API (`ANTHROPIC_API_KEY`) | alternative AI provider (Selection parsing etc.) | not configured |
| Clover API, Mercury sandbox, PayPal API, Aruba IMAP | acquisition/integration modules in the main checkout | need the `.env` secrets and network |

AWS CLI profiles in `%USERPROFILE%\.aws\config` [VERIFIED, names only]: `default` (region us-east-1, no
credentials), `rfone-dev` (region us-east-1; **has long-lived keys in `credentials`**), `rfone-dev-login`
(region us-east-1; `aws login` session, cached in `.aws\login\`). The check/login helper is
`03 Software\Infrastructure\aws-dev-access.ps1` (profile `rfone-dev-login`, expected account 418674484214).
Recreate on a new PC with `aws configure --profile …` / `aws login --profile rfone-dev-login` — never copy
keys through chat or git.

**Works fully offline:** the Bank server, its SQLite DB, migrations, `compare`, the test profile.
**Needs network/authorisation:** OneDrive sync, the Claude Code auto-interpretation, git push/pull, anything
AWS, Clover/Mercury/PayPal/Aruba.

### 6.1 Precautions against writing to production

1. Start the Bank **only** with `run.ps1 start` / Avvia Bank: it always sets `RFONE_DATABASE_URL` to the local
   SQLite file, and `serve.py` refuses to run otherwise.
2. Never set `RFONE_DATABASE_URL` or `ALEMBIC_DATABASE_URL_OVERRIDE` to a `postgresql://` URL in a User/Machine
   variable or in a `.env` on a local PC; before `alembic upgrade`, print the resolved URL
   (`rfone_data_store.database.redact_database_url(get_database_url())`).
3. Do not run anything under `03 Software\Infrastructure\deploy\` or the `release/*` worktrees
   (`C:\Users\servi\rfone-wt\…`) unless the task is explicitly an AWS task; per project notes, AWS Bank
   removal is deployed only from `release/remove-bank-aws` and must never be run locally.
4. Keep AWS credentials out of the default profile (as now): code using boto3 without `AWS_PROFILE` then finds
   no credentials instead of the `rfone-dev` keys.
5. Keep `RFONE_BANK_AI_MODE=SESSION` (default) so Preview never calls Bedrock.
6. Never put the production `RFONE_FLASK_SECRET_KEY` on a local PC.

---

## 7. Restore on another PC

### 7.0 Decide the scenario

| Scenario | When | Code arrives via | Data arrives via |
|---|---|---|---|
| **A (designed, recommended)** | same Microsoft account / OneDrive, same Windows user `servi` | OneDrive (whole `AI-RF-ONE` folder, worktrees included, uncommitted files included) | Chiudi Bank → OneDrive → Avvia Bank |
| B | different user path or no OneDrive | `git clone` **plus** copied uncommitted files (or a commit/push decided by the Product Owner) | copied handoff folder |

`ASUS2026` is already configured (`machines\ASUS2026.json`); a PC with another name needs a new machine file.

### 7.1 On THIS PC first (MINIPC-KSYR1) — [TODO, Product Owner]

```powershell
& "C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\Infrastructure\Bank Local Environment\run.ps1" close
```

Wait for **FILE PREPARATO** and **SINCRONIZZAZIONE COMPLETATA**. Until then the lease stays OPEN here and the
other PC refuses to start. Optionally decide whether to commit/push the 13 uncommitted files of the
worktree (needed for Scenario B; harmless for A).

### 7.2 Install (new PC)

1. **Python 3.12.10** from python.org, per-user install (default path
   `C:\Users\<user>\AppData\Local\Programs\Python\Python312\`), with the `py` launcher. Must be 3.12.x.
2. **Git for Windows** (2.55 or later); then `git config --global core.longpaths true`.
3. **OneDrive** signed in with the same account (Scenario A). Mark `OneDrive\AI-RF-ONE` as
   "Always keep on this device" and wait until it shows as synced.
4. **VS Code + Claude Code extension**, signed in (for the SESSION auto-interpretation).
5. Optional: AWS CLI v2 (only for AWS work); Tesseract OCR + Poppler (only for InvoiceIntake local OCR —
   not present on the source PC either).

### 7.3 Clone (Scenario B only)

```powershell
# working directory: C:\Users\<user>\OneDrive\AI-RF-ONE   (or any parent you choose)
git clone https://github.com/RomesFlavours/RF-One.git "RF One"
cd "RF One"
git worktree add "..\rf-one-bank-simple-who-rules" feature/bank-simple-who-rules
```

Then copy into `..\rf-one-bank-simple-who-rules\` the 13 uncommitted files listed in §1.4 (at least
`migrations\versions\a6e2c8f4b0d9_ai_rules_user_title.py` and the 9 modified code files), otherwise "Avvia
Bank" refuses: unknown DB revision and different code fingerprint.

### 7.4 Copy

| What | From → To |
|---|---|
| Bank data | Scenario A: nothing (OneDrive). Scenario B: `AI-RF-ONE\RF-One Bank Handoff\` (after 7.1) → same relative place under the new `onedrive` folder |
| `RF One\.env` | private channel → `RF One\.env` (only if Clover/Mercury/Aruba/Bedrock work is needed) |
| Git-ignored business data of §4.5 (`RF One\Bank\`, InvoiceIntake uploads/data, Invoices Raw, `07 Tasks\Invoices`, Clover data, Selection uploads) | Scenario A: they sync with OneDrive (verify); Scenario B: copy manually, encrypted |
| `%LOCALAPPDATA%\RF-One\Bank\previous\` and session folders | optional (history only) |

### 7.5 Reconfigure

```powershell
# 1) Bank venv (working directory: any)
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv "$env:LOCALAPPDATA\RF-One\Bank\venv"
$B = "$env:OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\Infrastructure\Bank Local Environment"
& "$env:LOCALAPPDATA\RF-One\Bank\venv\Scripts\python.exe" -m pip install -r "$B\requirements.lock.txt"

# 2) Machine file — only if machines\$env:COMPUTERNAME.json does not exist yet.
#    (run.ps1 setup would create it pointing at the *system* Python; write it directly for the venv.)
#    Written WITHOUT a BOM: Set-Content -Encoding utf8 in PowerShell 5.1 adds one and
#    config.py (json.loads of read_text("utf-8")) would then fail.
$machineJson = @{
  _comment      = "Everything that differs on this PC. Keep it minimal."
  computer_name = $env:COMPUTERNAME
  python        = "$env:LOCALAPPDATA\RF-One\Bank\venv\Scripts\python.exe"
  onedrive      = $env:OneDrive
  verified      = $null
} | ConvertTo-Json
[IO.File]::WriteAllText("$B\machines\$env:COMPUTERNAME.json", $machineJson, (New-Object Text.UTF8Encoding $false))

# 3) Configura PC — must end with "PC CONFIGURATO"
& "$B\run.ps1" setup
```

Commit the new machine file only if the Product Owner agrees (the README says to commit it).
If the Windows user path differs from `C:\Users\servi` and the worktrees came via OneDrive, repair the links
from the main checkout: `git -C "$env:OneDrive\AI-RF-ONE\RF One" worktree repair` (Scenario A with another
user path is **not verified**).

### 7.6 Differences for another operating system

The Bank Local Environment is **Windows-only** [CODE]: `.cmd`/PowerShell launchers, `%LOCALAPPDATA%`,
`COMPUTERNAME`, `taskkill`, `netstat`, PowerShell calls for OneDrive status, Windows process-creation flags.
On macOS/Linux the RF-One code itself (Flask + SQLAlchemy + SQLite, Python 3.12) runs, but the launcher does
not; you would have to set `RFONE_DATABASE_URL=sqlite:////<path>/rfone.db`, `RFONE_LOCAL_ENV_PC=<name>` and
run `python -m bank_local_env.serve 5080` from the tool folder, **without** handoff/lease protection — an
unverified, unsupported alternative that must not be used on the authoritative data without a Product Owner
decision. Paths with spaces must be quoted everywhere.

### 7.7 Start and minimum checks

```powershell
& "$B\run.ps1" status     # manifest generation ≥ 4, lease CLOSED by MINIPC-KSYR1, no conflict copies
& "$B\run.ps1" start      # must print the start of the new generation, SHA-256 verified
```

| Check | Expected |
|---|---|
| Server | `Get-NetTCPConnection -LocalPort 5080 -State Listen` shows a `python` process |
| Pages | http://127.0.0.1:5080/bank opens without login; header bar shows the new PC, `…\RF-One\Bank\rfone.db`, the generation, `feature/bank-simple-who-rules@851f437 · code 12d9066f7b` (same fingerprint as the source PC), AI SESSIONE |
| Database | `alembic_version` = `a6e2c8f4b0d9` (or a later one if migrations were added); log at `%LOCALAPPDATA%\RF-One\Bank\server.log` has no traceback |
| Data | `/bank` shows the movements; ≈3234 raw bank transactions and 9 AI rules (counts at survey time, may have grown) |
| Other pages | `/projects`, `/bank/ai-rules` answer 200 (seen in the source PC's log) |

---

## 8. Summary: verified, missing, still to do

| Verified | Missing on this PC | Still to do |
|---|---|---|
| Windows 11 Pro x64, PowerShell 5.1, Python 3.12.10, Git 2.55, AWS CLI 2.36.40 | Node, PostgreSQL, Docker, sqlite3 CLI, pytest, Tesseract, Poppler, `claude`/`codex` on PATH | **Chiudi Bank** on MINIPC-KSYR1 before using another PC |
| Server 5080 = Bank Local Environment from worktree `rf-one-bank-simple-who-rules`, venv, SQLite in `%LOCALAPPDATA%` | Command lines of PIDs 16528/17192 | Decide whether to commit/push the 13 uncommitted worktree files (DB revision `a6e2c8f4b0d9` lives only there) |
| DB revision `a6e2c8f4b0d9`, 263 tables, generation 3, lease OPEN here | Live verification of AWS state (deliberately not touched) | Resolve `main` ↔ `origin/main` divergence (1 vs 23 commits) |
| No autostart, no other services | Scenario A with a different user path; any non-Windows run | Transfer `.env` and the git-ignored business data of §4.5 privately, if needed |
