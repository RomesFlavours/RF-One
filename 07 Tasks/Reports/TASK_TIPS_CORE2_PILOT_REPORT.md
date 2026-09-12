# TASK_TIPS_CORE2_PILOT — Report

## 0. Scope confirmation

RF-One Tips Core 2.0 Process-First pilot: reused the existing, untouched Tip Distribution Engine; added Payment Instruction identity, a Mercury Sandbox connector, funding check, per-payee isolation, Outcome Verification, and readiness/trigger restructuring; added automated tests and a real-sandbox e2e demonstration; published on `review/tips-core2-pilot` for JP/Shelbi review. No Core file was modified. No production endpoint, token, or deploy was touched.

## 1. Pre-existing dirty state (not touched by this task)

`git status` at task start showed pre-existing, unrelated uncommitted changes from a separate "Selection/Pills/Cognitive Model" workstream (`.env.example`, several `01 Domains/Cross Domain/...` files, `00 Core/ConceptualArchitecture/20_...md`, two new Selection/Training docs). None of these were staged, committed, or otherwise touched by this task, on this branch or any other.

A second, unrelated finding: an untracked `Secrets/secretsmercury_sandbox_token.txt` file existed at the repo root, **not** covered by `.gitignore`. Added a defensive `Secrets/` entry to `.gitignore` (this task) so it can never be accidentally staged — the file itself was never read, moved, or staged.

## 2. Files created

- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/mercury/__init__.py`, `client.py` — Mercury Sandbox connector
- `03 Software/RF-One Data Store/rfone_data_store/tips/readiness.py` — Process Activation / readiness
- `03 Software/RF-One Data Store/rfone_data_store/tips/payment_instruction.py` — Payment Instruction identity, idempotency, Outcome Verification, failure classification
- `03 Software/RF-One Data Store/rfone_data_store/tips/payout_process.py` — orchestration (Channel Independence: no UI dependency)
- `03 Software/RF-One Data Store/migrations/versions/efe49dbc7321_add_tip_payment_execution.py` — `employee_external_payment_accounts`, `tip_payment_instructions`
- `03 Software/RF-One Data Store/rfone_data_store/tips_payment_execution_validation.py`, `test_tips_payment_execution.py` — automated tests (fake Mercury client, no network)
- `03 Software/Tips/templates/payouts.html` — exception-handling/configuration UI
- `03 Software/Tips/sandbox_pilot_e2e.py` — real-sandbox demonstration script (separate from automated tests, per task §18)
- `01 Domains/Business Domain/Restaurant/Tips/Tips Payment Execution.md` — Domain documentation
- `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md` — this report

## 3. Files modified

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — added `EmployeeExternalPaymentAccount`, `TipPaymentInstruction`
- `03 Software/Tips/app.py` — added `/payouts*` routes
- `03 Software/Tips/templates/base.html` — added "Payouts" nav link
- `01 Domains/Business Domain/Restaurant/Tips/README.md` — indexed the new document
- `.gitignore` — defensive `Secrets/` entry (see §1)

## 4. Core 2.0 concepts consumed (not redefined)

See `Tips Payment Execution.md`'s own table. No Core file was modified.

## 5. Blocker reported, not worked around (task §12/§14)

**Attention Management runtime, Organizational Responsibility runtime, and any mobile/push/PWA Attention Inbox do not exist anywhere in this codebase.** Building any of them correctly (as a genuinely reusable, cross-domain Foundation, per Core 2.0) is out of scope for a Tips pilot and is not attempted here — this task stops at the point Core 2.0 itself distinguishes: `TipPaymentInstruction` records `priority`/`failure_class`/`reason_for_failure` as plain Domain data, visible only through this pilot's own `/payouts` exception UI, never routed, escalated, or pushed to any person. Recommend a dedicated, separate Documentation-First task before any Domain (Tips included) builds its own notification path.

## 6. Real-sandbox finding requiring a design correction (found and fixed during this task)

Empirically, Mercury returns `HTTP 409` (no body message) when the SAME `idempotencyKey` is resent with a DIFFERENT payload (a corrected `recipientId`) — not the documented "safe replay." The original design (`idempotency_key` derived from `run_id + employee_id` only, fixed at instruction creation) would have permanently wedged an instruction the first time its recipient reference was corrected after a failure. Corrected to derive the key from `(run_id, employee_id, active_recipient_reference_id)`, computed at first submit rather than at creation (`TipPaymentInstruction.idempotency_key` is now nullable until then). Verified against the real sandbox: the corrected instruction reached `OUTCOME_VERIFIED` after relinking and retrying. This correction was made directly to the new migration/model (never yet released), not as a second migration.

## 7. Tests performed

- `test_tips_distribution_engine.py` — 29/29 (regression, unaffected by this task)
- `test_tips_distribution_rules.py` — 27/27 (regression, unaffected)
- `test_tips_import_concurrency_guard.py` — 26/26 (regression, unaffected)
- `test_tips_payment_execution.py` (new) — 16/16: readiness/trigger, RF-One duplicate protection, payout success, synchronous failure, one-payee isolation, insufficient funding (whole batch blocked, zero submitted), reversed/reopened Outcome, retry of only the failed instruction
- `03 Software/Tips/sandbox_pilot_e2e.py` — run against the REAL Mercury Sandbox: **PASS** (see task's final chat report for the full transcript) — real funding check, one real successful payout (`SENT`), one real isolated synchronous failure, isolation confirmed, retry-after-correction reached `OUTCOME_VERIFIED`. No production data, no production Mercury, no recipient created.

## 8. Unresolved / open items

- Attention Management / Organizational Responsibility / mobile delivery — see §5.
- Mercury's `RequestSendMoney` (approval) token scope was not exercised by this pilot — only direct `Read and Write`-equivalent submission, matching what the provided sandbox token supports.
- The pilot's `_pilot_source_account_id` auto-selection (first active Mercury checking account with a positive balance) is pilot-only convenience — a real deployment needs an explicit, Restaurant-scoped configuration (mirroring Payroll's `PayrollExecutionConfiguration`), not built here (out of this pilot's minimal scope).

## 9. Confirmation

No Core file modified. No production endpoint/token/deploy touched. Mercury Sandbox only. Branch `review/tips-core2-pilot`, not merged.
