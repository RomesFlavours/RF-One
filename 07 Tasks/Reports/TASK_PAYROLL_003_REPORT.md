# TASK_PAYROLL_003 — Automatic ADP Acquisition & Explicit Payment Executor Closure — Report

**Origin:** TASK_PAYROLL_003
**Builds on:** TASK_PAYROLL_002 (`07 Tasks/Reports/TASK_PAYROLL_002_REPORT.md`)

---

## Executive conclusion

TASK_PAYROLL_002 was wrong to call "a human downloads the ADP `Payroll Detail` report and RF-One imports the file" automatic acquisition — a human still acted every run. This task corrects that, and also corrects a second real defect: the importer silently defaulted every newly created `PayrollRun` to `payment_execution_provider = ADP_DIRECT_DEPOSIT` merely because the source was ADP, conflating "who supplied this result" with "who pays it."

**Both corrections are fully implemented and tested.** Two legitimate, officially supported ADP mechanisms for genuinely automatic acquisition were verified through research (never invented): ADP's **Automatic Export Service (AES) via SFTP**, and ADP's **Payroll Output API for RUN Powered by ADP**. Neither can be activated by repository code alone — both require an external action by the ADP account holder with ADP itself. Every part of the repository-side architecture that can legitimately be built without that external step has been built, tested, and is ready the moment it is granted.

```text
PAYROLL STATUS: PARTIAL — AUTOMATIC ACQUISITION BLOCKED BY EXTERNAL ADP ACCESS
```

---

## What "automatic acquisition" means

> Once configured, RF-One obtains ADP's completed payroll result without a human downloading or uploading anything **for that specific run**, indefinitely.

A human manually visiting ADP's UI and supplying a file to `import_payroll_results.py` requires that human action every payroll cycle forever — it is a legitimate, fully supported fallback, never automatic. Only a mechanism requiring zero per-run human action once configured qualifies. See `01 Domains/Administration/Payroll/Payroll Result Acquisition.md`, "Why manual XLSX download is never 'automatic.'"

---

## Verified ADP acquisition mechanism(s)

Investigated via ADP's own developer portal (developers.adp.com / marketplace-cdn.adp.com) and corroborating third-party integration documentation. Two real, named, documented ADP mechanisms were confirmed to exist — nothing below is invented:

### 1. ADP Automatic Export Service (AES) via SFTP — lower barrier

ADP's own recurring, scheduled report-export mechanism: a report is delivered to a customer-controlled SFTP endpoint on a schedule. Requested through ADP's Reporting module ("request SFTP Export") or directly from an ADP representative; involves a one-time ADP-side setup fee (reported around $200–300) and, for recurring/scheduled delivery specifically via AES, a recurring fee. No OAuth, no Marketplace partnership, no mutual TLS certificate — just standard SFTP credentials once ADP provisions the endpoint.

**Unverified/needs confirmation once SFTP access exists:** whether ADP's exportable report set for a RUN Powered by ADP account includes the specific per-Employee "Payroll Detail" layout `adp_importer.py` already parses, or only a General-Ledger-style journal export (ADP RUN's "General Ledger" feature was also found, a different, coarser report shape). This is flagged honestly rather than assumed — see "External ADP requirements," below.

### 2. ADP Payroll Output API for RUN Powered by ADP — the complete, official API path

A real, documented ADP REST API ("Payroll Output API," internally also referred to as the "Turbo API") that retrieves completed payroll run results — company-level payroll details, associate payment summaries, payment distribution detail, and historic payroll data. Confirmed via ADP's own protected developer-portal PDF guide title ("Payroll Output API Guide for RUN Powered by ADP") and multiple independent third-party integration write-ups.

Access model, confirmed from multiple independent sources:

- **Relationship-gated, never self-serve.** Issued only after the ADP account holder (Pino, for the Rome's Flavours ADP account) requests **API Central** access through their own ADP account, or after becoming a registered **ADP Marketplace Partner** (a sales-led, certification-gated program).
- **Authentication:** OAuth 2.0 client-credentials tokens (issued per client relationship, not per user) **plus** mutual TLS — a client certificate issued through ADP's own onboarding process. Both must be obtained from ADP; neither can be generated or invented by RF-One.
- **Timeline:** third-party integration consultancies report implementation "typically takes several months," reflecting the relationship/approval process, not engineering effort.
- The exact endpoint path and JSON response schema live in ADP's **protected** developer documentation (a PDF that renders only after authenticated access), which this research could not retrieve in readable form — attempting to guess it would mean inventing an API contract, which this task explicitly forbids.

**Neither mechanism can be activated by writing code.** Both require Pino to take an action with ADP directly.

Sources consulted: ADP Developer Resources (developers.adp.com), "Payroll Output API Guide for RUN Powered by ADP" and "Payroll Data Input API Guide for RUN Powered by ADP" (marketplace-cdn.adp.com protected PDFs — titles and existence confirmed, content protected), ADP® API Central for ADP Workforce Now (ADP Marketplace listing), and third-party integration guides (jobspipe.dev, bindbee.dev) independently corroborating the relationship-gated access model and OAuth2 + mutual TLS requirement.

---

## Implementation performed

### Part B — repository-side architecture (credential-independent parts)

1. **`rfone_data_store/payroll/acquisition.py`** (new) — the acquisition-adapter layer:
   - `PayrollAcquisitionAdapter` protocol (`fetch() -> list[AcquiredPayrollFile]`).
   - `LocalFileAcquisitionAdapter` — wraps the existing manual/local-file path, unchanged behavior, formalized as an adapter (`acquisition_method="ADP_XLSX_FILE"`).
   - `AdpSftpAcquisitionAdapter` — **fully implemented and tested**, not a scaffold. Connects via `paramiko` (imported lazily), lists a configured remote directory, downloads not-yet-seen `.xlsx` files, tags `acquisition_method="ADP_SFTP_AES"`. Connection details load only from environment variables (`ADP_SFTP_HOST`, `ADP_SFTP_USERNAME`, `ADP_SFTP_REMOTE_DIRECTORY`, `ADP_SFTP_PORT`, `ADP_SFTP_PASSWORD`/`ADP_SFTP_PRIVATE_KEY_PATH`); `from_environment()` raises `AcquisitionNotConfiguredError` naming exactly what is missing. The SFTP transport is expressed as a small `SftpTransport` Protocol (`listdir`/`open`), injectable via `transport_factory=`, so the adapter's real logic (listing, filtering, downloading, tagging) is fully unit-tested without any real network access or ADP credentials.
   - `AdpApiAcquisitionAdapter` — scaffold only, by design. `from_environment()` validates OAuth/mTLS credential-shaped configuration (`ADP_API_BASE_URL`, `ADP_API_CLIENT_ID`, `ADP_API_CLIENT_SECRET`, `ADP_API_CLIENT_CERT_PATH`, `ADP_API_CLIENT_KEY_PATH`); `fetch()` always raises `AdpApiNotImplementedError`, explicitly stating why: the endpoint/schema are behind ADP's protected documentation.
   - `acquire_and_import(session, adapter, ...)` — shared orchestrator: every adapter's output flows through the exact same persistence core, below.

2. **`rfone_data_store/payroll/adp_importer.py`** refactored (not redesigned) into two layers:
   - `persist_import(session, *, file_path, ...)` — thin, file-based entry point; unchanged public behavior.
   - `persist_parsed_import(session, *, parsed, source_file_name, source_file_hash, acquisition_method, ...)` — the acquisition-method-independent core, extracted from the old `persist_import` body verbatim (idempotency, Employee mapping, provenance, supersession — none of this logic changed). Every adapter calls this same function.
   - `parse_payroll_detail_workbook_bytes(data: bytes)` — new, parses an in-memory result the same way the existing `parse_payroll_detail_workbook(path)` parses a file; both delegate to the same `_parse_loaded_workbook`.
   - `dry_run_parsed_import(...)` — the read-only counterpart, same split.

3. **`payroll_execution_configurations` table + `payment_execution.approved_provider_at`** — see "Explicit payment-executor design," below.

4. **`payroll_import_runs.acquisition_method`** column — records how each import's bytes actually arrived (`ADP_XLSX_FILE`/`ADP_SFTP_AES`/future `ADP_API`), alongside the pre-existing `source_file_name`/`source_file_hash`.

5. **`acquire_payroll_results.py`** (new CLI) — the unattended-capable entry point (`--source {file,sftp,api}`), dry-run by default, `--persist` to write; prints acquisition method and payment executor per acquired file.

6. **`import_payroll_results.py`** — unchanged behavior except the `--payment-execution-provider` default (Part C, below); still the fully supported manual/local-file fallback.

7. **`requirements.txt`** — added `paramiko>=3.4,<4.0` (the standard Python SFTP client library; a genuine commodity dependency, not reimplemented).

### Part A — what remains external

Nothing more can be legitimately built without: (a) confirmation of which report ADP AES can actually export for a RUN Powered by ADP account, and SFTP connection details once ADP provisions the endpoint; or (b) API Central/Marketplace credentials and ADP's protected API guide content. See "ADP credentials/entitlements still required," below.

---

## ADP credentials/entitlements still required

To activate automatic acquisition, Pino (the Rome's Flavours ADP account holder) must obtain, directly from ADP:

**For the SFTP path (recommended first — lower barrier):**
1. Request "SFTP Export" / Automatic Export Service setup through ADP's Reporting module or an ADP representative for the Rome's Flavours RUN account.
2. Confirm which report ADP will export to that endpoint actually matches (or can be configured to match) the per-Employee "Payroll Detail" layout `adp_importer.py` parses — if only a General-Ledger-style export is available, a small additional parser may be needed later (out of this task's scope, since the exact export format cannot be confirmed without the SFTP access itself).
3. Provide RF-One's operator with the resulting SFTP host, port, username, and credential (password or a generated key pair) to set as `ADP_SFTP_HOST`/`ADP_SFTP_USERNAME`/`ADP_SFTP_REMOTE_DIRECTORY`/`ADP_SFTP_PASSWORD` (or `ADP_SFTP_PRIVATE_KEY_PATH`) environment variables — never committed to Git.

**For the API path (the complete long-term solution):**
1. Request ADP API Central access (or ADP Marketplace Partner enrollment) for the Rome's Flavours ADP account.
2. Once granted, obtain: an OAuth 2.0 client ID/secret, a mutual TLS client certificate/key pair, and — critically — the actual "Payroll Output API Guide for RUN Powered by ADP" content (the exact endpoint path and JSON response schema), which is required before `AdpApiAcquisitionAdapter.fetch()` can be completed.

Until at least one of these is obtained, `acquire_payroll_results.py --source sftp` and `--source api` will both raise clear, actionable configuration errors — never fabricate a successful acquisition.

---

## Explicit payment-executor design (Part C)

**Removed:** the implicit default that assigned `ADP_DIRECT_DEPOSIT` to every newly created Run merely because the source was ADP.

**New resolution order**, applied identically by `persist_import`, `persist_parsed_import`, and `acquire_and_import`:

```text
1. an explicit selection passed by the caller (e.g. --payment-execution-provider), else
2. the Restaurant's approved PayrollExecutionConfiguration valid at the Run's pay_date, else
3. left unassigned (NULL) — never guessed
```

**`PayrollExecutionConfiguration`** (new table, `payroll_execution_configurations`) — Restaurant-scoped, temporal (`valid_from`/`valid_to`), mirroring the existing `EmployeeCompensationTerm`/`TipPolicy` pattern exactly: a change closes the prior row and opens a new one, never overwritten in place. `payment_execution.approved_provider_at(session, restaurant_id=, at=)` resolves the provider valid at a given instant, deterministically (most-recently-started wins on the rare case of overlap — never ambiguous), returning `None` when nothing is configured.

**Temporal safety, verified:** because a Run's own `payment_execution_provider` is separately immutable once assigned (`assign_payment_execution_provider`, unchanged from TASK_PAYROLL_002), changing the approved configuration later can never retroactively alter an already-created Run — demonstrated live: a Run created before any configuration existed keeps `payment_execution_provider = NULL` forever; a Run created after a configuration was added derives it automatically; a later configuration change to `MERCURY_ACH` leaves the earlier Run's `ADP_DIRECT_DEPOSIT` assignment completely untouched (Scenario 8, below).

---

## Double-payment protection

Unchanged and re-verified: `assign_payment_execution_provider` still rejects reassigning an already-assigned Run to a *different* provider (raises `ValueError`), and re-asserting the same value is still a safe no-op. This guard is untouched by this task — it now simply gets called with a resolved-rather-than-assumed value.

---

## Current Rome's Flavours ADP_DIRECT_DEPOSIT configuration

**Not yet written to the real production database.** Part D states, as an approved fact, that `ADP_DIRECT_DEPOSIT` is the current approved production executor — the mechanism to record that (`PayrollExecutionConfiguration`) is fully implemented and tested. What is **not** given anywhere in this task is an effective date (`valid_from`) for that configuration, and inventing one would be fabricating a business detail this task does not authorize. Consistent with this session's established practice (TASK_TIPS_003 took the identical stance on the real `TipPolicy`), the real Rome's Flavours row was **not** inserted. The exact activation command, once Pino confirms an effective date:

```python
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store import models as m
from rfone_data_store.payroll import payment_execution as pe

session = create_session_factory(create_configured_engine())()
session.add(m.PayrollExecutionConfiguration(
    restaurant_id=1, provider=pe.ADP_DIRECT_DEPOSIT,
    valid_from=<effective date Pino confirms>, valid_to=None,
    source_note="Rome's Flavours approved production executor (TASK_PAYROLL_003 Part D)",
))
session.commit()
```

---

## Future Mercury boundary

Unchanged from TASK_PAYROLL_002 and re-confirmed: `MERCURY_ACH` remains a structural placeholder only. No Mercury API call, ACH instruction, credential, or sandbox behavior exists anywhere in this task's code (verified by the same source-inspection assertion pattern as before — check 30 in the test suite). `PayrollExecutionConfiguration` and `payment_execution_provider` can both represent `MERCURY_ACH` today, purely as data, so a future Mercury integration will not require another Payroll redesign.

---

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Automatic-acquisition adapter contract | **PASS** — `PayrollAcquisitionAdapter` protocol satisfied by all three adapters; unit-tested (checks 41-46). |
| 2 | Same acquired payroll result twice → idempotent | **PASS** — content-hash keyed idempotency proven both via `acquire_and_import` called twice (check 42) and via the CLI across two real process invocations. |
| 3 | Process restart | **PASS** — CLI run 1 (persist) then a brand-new Python process (run 2, persist again) against the same disposable SQLite file correctly recognized run 2 as idempotent (`created=False`), proving no in-memory state is required. |
| 4 | Unknown Employee | **PASS** — inherited unchanged: `persist_parsed_import` is the exact same function `persist_import` always was; the `AMBIGUOUS_EMPLOYEE_MAPPING`/`UNRESOLVED_EMPLOYEE_MAPPING` behavior (check 23) applies identically regardless of acquisition method, since acquisition adapters share this one persistence core. |
| 5 | Corrected provider report | **PASS** — `supersedes_import_run_id` unchanged and re-verified (check 24) on the file-based path; not yet exposed on `acquire_and_import`'s batch interface — see Future Enhancements. |
| 6 | ADP acquisition with ADP_DIRECT_DEPOSIT explicitly configured | **PASS** — CLI: `import_payroll_results.py ... --payment-execution-provider ADP_DIRECT_DEPOSIT` produced a Run with that provider assigned. |
| 7 | ADP acquisition with payment executor not specified → must not silently assign ADP | **PASS** — CLI: with no `PayrollExecutionConfiguration` present, `acquire_payroll_results.py --persist` (no `--payment-execution-provider`) produced `Payment execution provider: None`. Verified live, not only in the test suite. |
| 8 | ADP source + future MERCURY_ACH representation remains architecturally possible | **PASS** — checks 30, 37, 38; live demonstration: a later `PayrollExecutionConfiguration` change to `MERCURY_ACH` correctly applied to a subsequently created Run while leaving an earlier ADP-assigned Run untouched. |
| 9 | Attempt to assign two executors to same PayrollRun → blocked | **PASS** — check 31, unchanged, re-verified. |
| 10 | Payment evidence absent → UNKNOWN, never PAID by inference | **PASS** — check 33, unchanged, re-verified. |
| 11 | Existing XLSX manual-import fallback still works | **PASS** — checks 22/22a/22b/24 all still pass unchanged; live CLI smoke test via `import_payroll_results.py`. |
| 12 | Payroll tests remain green | **PASS** — 52/52 (39 pre-existing + 13 new). |
| 13 | Tips tests remain green | **PASS** — 46/46, unchanged. |
| 14 | Organization tests remain green | **PASS** — 14/14, unchanged. |
| 15 | Purchasing tests remain green | **PASS** — 24/24, unchanged. |
| 16 | Migration upgrade/downgrade safe | **PASS** — clean round-trip on a disposable DB (`downgrade -2` / `upgrade head`), and applied cleanly to a disposable copy of the real, populated database. |
| 17 | No real production database mutation during validation | **PASS** — MD5 of `data/rfone.db` identical (`179c12e7442c4ffa5a8f23e30e63ac83`) before and after every step in this task. |

All 17 minimum-test-list items **PASS**.

---

## Tests

All run against fresh or disposable databases (never the live `data/rfone.db`), scratch-directory only:

| Command | Result |
|---|---|
| `create_database.py` (fresh DB, 12 migrations incl. this task's two new ones) | **SUCCESS** — 75 tables, schema validation 29/29 |
| `test_payroll_engine.py` | **SUCCESS** — 52/52 (39 pre-existing + 13 new: 29b corrected, 35, 35b, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46a, 46b) |
| `test_tips_engine.py` | **SUCCESS** — 46/46, unchanged |
| `test_organization_validation.py` | **SUCCESS** — 14/14, unchanged |
| `test_restaurant_profile_bootstrap.py` | **SUCCESS** — 14/14, unchanged |
| `test_purchasing_engine.py` | **SUCCESS** — 24/24, unchanged |
| `alembic downgrade -2` / `upgrade head` (disposable DB) | **SUCCESS** — clean round-trip |
| `alembic upgrade head` on a disposable copy of the real, populated `data/rfone.db` | **SUCCESS** — 24 EmployeeAssignments, 4,368 Shifts, 3,326 PaymentTips unaffected; `payroll_execution_configurations` created empty (0 rows, correct — none ever configured) |
| CLI end-to-end (`acquire_payroll_results.py --source file`, real SQLite file, separate process per step) | Dry-run → persist (provider=None, no config) → **new process** → persist again (idempotent, `created=False`) → configure `PayrollExecutionConfiguration` → persist a new period (provider auto-derived `ADP_DIRECT_DEPOSIT`) → confirmed the first Run's provider remained `None` |
| CLI (`import_payroll_results.py --payment-execution-provider ADP_DIRECT_DEPOSIT`) | **SUCCESS** — explicit selection honored |
| MD5 of `data/rfone.db` before/after all of the above | **Identical** — never written to |

---

## Exact files changed

**New files:**
- `01 Domains/Administration/Payroll/Payroll Result Acquisition.md`
- `03 Software/RF-One Data Store/rfone_data_store/payroll/acquisition.py`
- `03 Software/RF-One Data Store/acquire_payroll_results.py`
- `03 Software/RF-One Data Store/migrations/versions/f2c8b6d4e1a7_add_payroll_execution_configuration.py`
- `03 Software/RF-One Data Store/migrations/versions/a9d3e5f7c2b4_add_payroll_import_run_acquisition_.py`
- `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md` (this report)

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/models.py` (new `PayrollExecutionConfiguration` class; new `PayrollImportRun.acquisition_method` column)
- `03 Software/RF-One Data Store/rfone_data_store/payroll/adp_importer.py` (extracted `persist_parsed_import`/`dry_run_parsed_import`; added `parse_payroll_detail_workbook_bytes`/`sha256_bytes`; removed implicit `ADP_DIRECT_DEPOSIT` default)
- `03 Software/RF-One Data Store/rfone_data_store/payroll/payment_execution.py` (new `approved_provider_at`)
- `03 Software/RF-One Data Store/rfone_data_store/payroll_validation.py` (13 new/corrected checks)
- `03 Software/RF-One Data Store/import_payroll_results.py` (`--payment-execution-provider` default changed to unset)
- `03 Software/RF-One Data Store/requirements.txt` (added `paramiko`)
- `03 Software/RF-One Data Store/PAYROLL.md`
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md`
- `01 Domains/Administration/Payroll/README.md`
- `01 Domains/Administration/Payroll/Payment Execution.md`
- `01 Domains/Administration/Payroll/Payroll Provider Result.md`

No file outside this list was touched. `Payment Execution.md`/`payment_execution.py` show as untracked in `git status` because they were newly created (and never committed) in the immediately preceding TASK_PAYROLL_002 within this same session — this task only edited their already-uncommitted content.

---

## Product Owner decisions required

1. **Which ADP acquisition path to pursue first** — SFTP (AES, lower barrier, faster) vs. API (complete, higher barrier) vs. both. This task recommends starting with SFTP given its materially lower access barrier, while still building toward the API as the long-term path.
2. **`PayrollExecutionConfiguration.valid_from`** — the effective date from which `ADP_DIRECT_DEPOSIT` should be recorded as Rome's Flavours' approved executor (see "Current Rome's Flavours ADP_DIRECT_DEPOSIT configuration" — the row is ready to create, only this date is undecided).
3. **Whether ADP AES can export the per-Employee "Payroll Detail" report specifically** (vs. only a General-Ledger-style export) — this can only be confirmed once SFTP access exists; if only the GL format is available, a follow-up task would be needed to parse it.

---

## Future enhancements

- Complete `AdpApiAcquisitionAdapter.fetch()` once ADP grants API Central/Marketplace access and its protected endpoint/schema documentation is obtained.
- Confirm and, if needed, adapt to the actual report format ADP AES delivers once SFTP access is provisioned.
- Batch-level `supersedes_import_run_id` support on `acquire_and_import` for multi-file acquisition runs (today, correcting a specific prior Run still requires the file-based `import_payroll_results.py --supersedes-run` path, which remains fully available).
- Scheduling `acquire_payroll_results.py --source sftp` itself (cron/Task Scheduler) once SFTP access exists — out of this task's scope (no infrastructure/deployment work was requested).
- Everything already carried forward as non-blocking from TASK_PAYROLL_002 (additional report formats, direct RF-One Tips → Payroll consumer, etc.).

---

## Git status

No commit was created and nothing was pushed during this task. All work is in the working tree only. Pre-existing uncommitted changes present at task start (across Purchasing, Organization, Tips, InvoiceIntake, Core documentation, and this session's own earlier Server Performance work) were left exactly as found — this task only added the six new files and made the eleven scoped edits listed in "Exact files changed," all Payroll-acquisition/payment-executor related.

---

## Final readiness statement

`PAYROLL STATUS: PARTIAL — AUTOMATIC ACQUISITION BLOCKED BY EXTERNAL ADP ACCESS`

What must be obtained from ADP to close this:

1. **SFTP path (recommended first step):** Pino requests ADP Automatic Export Service / SFTP Export setup for the Rome's Flavours RUN account (via ADP's Reporting module or an ADP representative), confirms the exported report matches the per-Employee Payroll Detail layout, and provides the resulting SFTP host/credentials.
2. **API path (complete long-term solution):** Pino requests ADP API Central access (or Marketplace Partner enrollment) for the Rome's Flavours ADP account, and the resulting OAuth 2.0 client credentials, mutual TLS certificate, and the "Payroll Output API Guide for RUN Powered by ADP" documentation are obtained and used to complete `AdpApiAcquisitionAdapter.fetch()`.

Until at least one of these external steps is completed, RF-One cannot actually acquire payroll results from ADP without a human manually downloading the report — the manual XLSX path remains fully supported as the production fallback, exactly as it was before this task, never redefined as automatic.
