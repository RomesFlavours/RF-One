# Payroll Result Acquisition

**Version:** 1.0
**Status:** Approved
**Module:** Administration Domain / Payroll
**Origin:** TASK_PAYROLL_003

---

## Purpose

TASK_PAYROLL_002 treated "a human downloads the ADP `Payroll Detail` report and RF-One imports the file" as fully automatic result acquisition. It is not — a human still performs a manual step for every payroll run. This document corrects that and defines the actual boundary:

```text
Payroll calculation  ≠  Payroll result acquisition  ≠  Payment execution
```

**Automatic acquisition** means: once configured, RF-One obtains ADP's completed payroll result without a human downloading or uploading anything for that specific run. The manual XLSX file remains a valid, fully supported **fallback** acquisition path — it is never redefined as "automatic."

---

## Acquisition adapters — one shared persistence core

`rfone_data_store/payroll/acquisition.py` defines a `PayrollAcquisitionAdapter` contract (`fetch() -> list[AcquiredPayrollFile]`) with three implementations, all normalizing into the exact same `ParsedPayrollDetail` structure the original TASK_PAYROLL_001 parser already produces, and all handing off to the exact same `adp_importer.persist_parsed_import` — the acquisition-method-independent core that owns idempotency, Employee mapping, provenance and correction/supersession. No adapter has its own persistence logic.

```text
LocalFileAcquisitionAdapter   the existing manual/local-file path (TASK_PAYROLL_001), preserved
                                unchanged as the production fallback — not automatic.

AdpSftpAcquisitionAdapter      genuinely automatic. Downloads not-yet-imported files from a
                                customer-controlled SFTP endpoint that ADP's own "Automatic
                                Export Service" (AES) delivers a scheduled report to. Fully
                                implemented; requires only real SFTP connection details,
                                supplied externally (never committed to Git).

AdpApiAcquisitionAdapter       scaffold for ADP's official "Payroll Output API for RUN Powered
                                by ADP." Verified to exist as a real ADP product; its request/
                                response handling is intentionally left unimplemented pending
                                ADP's protected API documentation (see "Verified ADP mechanisms"
                                below and 07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md).
```

---

## Verified ADP mechanisms

Two legitimate, officially supported ADP mechanisms were verified (never invented) for automatically retrieving completed payroll results — see `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md`, "Verified ADP acquisition mechanism," for full research findings and sources:

1. **ADP Automatic Export Service (AES) via SFTP** — ADP's own recurring, scheduled report-export mechanism, delivering a report file to a customer-controlled SFTP endpoint. Requested through ADP's Reporting module / an ADP representative; involves an ADP-side one-time and/or recurring fee. Lower access barrier than the API path — no OAuth/Marketplace partnership required.
2. **ADP Payroll Output API for RUN Powered by ADP** — ADP's official REST API for retrieving completed payroll run results, authenticated via OAuth 2.0 client-credentials plus mutual TLS. Access is relationship-gated: issued only after the ADP account holder requests API Central (or Marketplace Partner) access directly from ADP — never self-serve, never obtainable by writing code alone.

**Neither mechanism can be activated by repository code alone.** Both require an external action by the ADP account holder (Pino) with ADP itself. This document records the architecture that makes RF-One ready to consume either the moment that external step is completed — see the task report for the exact external requirement.

---

## Why manual XLSX download is never "automatic"

A human manually visiting ADP's UI, downloading a report, and supplying it to `import_payroll_results.py` requires that human action **every single payroll run**, indefinitely. This remains a legitimate, fully supported production fallback — but calling it "automatic acquisition" would misrepresent what actually happens operationally. Only a mechanism requiring **zero human action per run** once configured (SFTP delivery, or a future API poll) qualifies.

---

## Provenance: acquisition method is recorded, never assumed

Every `PayrollImportRun` records `acquisition_method` (`ADP_XLSX_FILE`, `ADP_SFTP_AES`, or a future `ADP_API`) alongside the existing `source_file_name`/`source_file_hash` provenance (`Payroll Provider Result.md`, "Import provenance and idempotency"). Idempotency itself remains keyed on content hash (`source_file_hash`), never on acquisition method, filename, or transport — the identical payroll result acquired via SFTP today and re-acquired manually tomorrow (e.g. during a migration between mechanisms) is still recognized as the same import.

---

## Credentials never in Git

Every adapter that needs external credentials (SFTP connection details, future ADP API OAuth/mTLS credentials) loads them exclusively from environment variables at runtime (`AdpSftpAcquisitionAdapter.from_environment`, `AdpApiAcquisitionAdapter.from_environment`) and raises a clear, explicit error naming exactly what is missing when they are absent — never a hard-coded default, never a silently-degraded behavior, never committed to version control.

---

## Related documents

- [Payment Execution.md](Payment%20Execution.md) — the payment-execution boundary this document is distinguished from
- [Payroll Provider Result.md](Payroll%20Provider%20Result.md) — the ADP `Payroll Detail` report structure every acquisition path normalizes into
- `03 Software/RF-One Data Store/rfone_data_store/payroll/acquisition.py` — runtime implementation
- `03 Software/RF-One Data Store/acquire_payroll_results.py` — CLI entry point
- `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md` — task that introduced this document
