# Tips Payment Execution — Core 2.0 Process-First Pilot

**Version:** 0.1 — pilot, for technical review (JP, Shelbi)
**Status:** PILOT — IMPLEMENTED items below are real, working, sandbox-only code on `review/tips-core2-pilot`; nothing here is deployed or authorized for production
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_CORE2_PILOT

---

## Purpose

This document describes how the Tips Distribution Engine's finalized, per-Employee net amount (`Tip Allocation.md`'s atomic allocations, aggregated) is paid out through an external Payment Executor (Mercury, sandbox only in this pilot), and how that payout's Outcome is verified — consuming, never redefining, RF-One Core 2.0.

It does **not** redefine any Tip Business Rule (`Tip.md`, `Tip Policy.md`, `Tip Allocation.md`) — the Tip Distribution Engine (`rfone_data_store/tips/distribution_engine.py`) is reused exactly as it exists today.

**Clover freshness vs. consolidation:** `readiness.py`'s "latest `Order.business_date` on file" is the concrete instance of the consolidation boundary formalized in `03 Software/RF-One Data Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §7 — Tips privileges a reconciled Business Date over live Clover freshness; it does not calculate or pay out against a Business Date before that data has passed through both the Fast Live Extractor and the Correction/Reconciliation Poller described there. Not redefined by this document.

---

## Canonical payment-connector decision (Product Owner, external-review closure)

Payment method is **variable and configurable**, not fixed to any one provider. RF-One owns the payment instruction and its workflow; a configured payment-mode setting determines WHICH connector actually executes it:

- **`TipPaymentInstruction`** = what RF-One has decided must be paid — provider-neutral, and must remain so.
- **Payment mode / configuration** = HOW that payment is to be executed.
- **Configured connector** (Mercury today; other providers possible later) = the technical executor of that payment.

Everything below this point that names Mercury specifically (the connector, its sandbox endpoints, its recipient/idempotency model, its failure classes) describes **this pilot's one implemented connector**, not the canonical payment model — it must not be read as making Tips dependent on Mercury-specific concepts, and future connectors are expected to implement the same instruction-level contract (`TipPaymentInstruction` + Outcome Verification) without requiring Tips-side changes. No new connector API is introduced by this note; it records the boundary the existing Mercury connector already sits behind (`technical/connectors/mercury/`).

---

## Core 2.0 concepts consumed

| Concept | Core 2.0 source | How this pilot consumes it |
|---|---|---|
| Process Autonomy / verified completion | `ConceptualArchitecture/11_...md` §3 | Completion requires `sent` + `postedAt`, never a dispatched command — see "Outcome Verification" |
| Process Activation / Trigger | `ConceptualArchitecture/13_...md` | `tips/readiness.py` exposes readiness as a data condition, callable by any channel |
| Channel Independence | `ImplementationGuidelines.md` | `tips/payout_process.py` has no UI dependency; the Flask route and a script call the identical function |
| Identity/Authority | `ConceptualArchitecture/09_...md` | Not extended by this pilot — see "What this pilot does NOT implement" |
| Attention Management | `ConceptualArchitecture/12_...md` | **NOT implemented as a runtime capability** — see "What this pilot does NOT implement" |
| Organizational Responsibility | `Organizational Responsibility.md` | **NOT implemented** — same gap as above |

---

## IMPLEMENTED (this pilot, sandbox only)

### Process / Trigger / readiness

`rfone_data_store/tips/readiness.py` exposes `describe_readiness(session, restaurant_id)`: the latest `Order.business_date` on file, whether it is already calculated, how many Payment Instructions exist/need attention/are Outcome-verified, and whether it is fully settled. This is a pure read, callable identically from the Flask UI, a script, or a future scheduler/Cognito — no "run at 02:00" rule exists anywhere; readiness is a data condition (Core 2.0 §5, "Time is just an event"), not a wall-clock trigger.

### Tips Engine

Untouched. `distribution_engine.run_tip_distribution_calculation` / `build_employee_review` are reused as-is; this pilot only consumes `EmployeeReviewRow.net_before_adjustments_minor` as the per-Employee Final Payable.

### Payment Instruction identity (RF-One's own primary duplicate-payment guard)

`TipPaymentInstruction` (one row per `(calculation_run_id, employee_id)`, DB-unique) — `rfone_data_store/tips/payment_instruction.py`. Re-running readiness/payout for an already-instructed Employee never creates a second instruction and never resubmits an already-`SENT`/`OUTCOME_VERIFIED` one.

**Idempotency key correction found during this pilot's own real-sandbox run:** the key is derived from `(run_id, employee_id, active_recipient_reference_id)`, not just `(run_id, employee_id)`. Empirically, Mercury returns `HTTP 409` (no body message) when the SAME `idempotencyKey` is resent with a different `recipientId` — reusing a fixed key across a recipient correction would have permanently wedged that instruction. A key is only re-derived when the active reference actually changes; a retry against the same reference reuses the same key.

### Mercury Sandbox connector

`rfone_data_store/technical/connectors/mercury/` — `get_accounts`, `get_recipients`/`find_recipient_by_name`, `create_transaction`, `get_transaction`. Sandbox base URL and `MERCURY_SANDBOX_API_TOKEN` only; no production endpoint or token anywhere in this package. Every field/endpoint used was verified empirically against the real sandbox. Sensitive fields (`accountNumber`, `routingNumber`, nested routing info) are stripped from every response before leaving the connector.

### Employee ↔ Mercury recipient reference

`EmployeeExternalPaymentAccount` — Mercury's own opaque recipient id only, never a routing/account number. Not auto-created; linked to an **existing** sandbox recipient only (`/payouts/employee/<id>/link-recipient`, by name).

### Funding check

`payment_instruction.check_funding` reads Mercury's real `availableBalance` and compares it to the FULL batch total before any instruction is submitted. Insufficient funds blocks the whole batch (no arbitrary partial payout) — every instruction stays `READY`.

### Per-payee isolation

`payout_process.run_business_date_payout` submits and refreshes each instruction independently; one instruction's failure never affects, blocks, or rolls back another. Verified against the real sandbox (see "Sandbox E2E result" in the task report) and by automated tests.

### Outcome Verification

`payment_instruction.refresh_outcome` polls `GET /transaction/{id}` (sandbox has no webhook). Uses ONLY Mercury's real states: `pending, sent, cancelled, failed, reversed, blocked`. `OUTCOME_VERIFIED` requires `status == 'sent'` AND `postedAt` populated — never a dispatched command alone. A LATER `reversed` observation reopens a previously verified Outcome back to `NEEDS_ATTENTION` (never treated as immutable).

### Failure classification (isolated in the connector/Domain layer, never guessed by UI code)

`MercuryAuthError`, `MercuryValidationError`, `MercuryDuplicateProtectionError`, `MercuryNotFoundError`, `MercuryUnavailableError` → `TipPaymentInstruction.failure_class` ∈ `RECIPIENT_NOT_CONFIGURED, SYNCHRONOUS_VALIDATION, DUPLICATE_PROTECTION, PROVIDER_STATUS_FAILURE, PROVIDER_UNAVAILABLE, OUTCOME_REOPENED`, with a contextual `priority` (CRITICAL/HIGH/MEDIUM/LOW) — never a fixed event→priority table.

### Retry of a single failed instruction

`payout_process.retry_instruction` resubmits exactly one instruction; every sibling instruction is untouched (verified both by automated tests and by the real sandbox run).

### UI (exception handling & configuration only — `03 Software/Tips/templates/payouts.html`, `/payouts*` routes)

Read-only readiness summary, per-instruction status/priority/reason, a manual "submit/refresh" trigger (standing in for a future automatic Process Activation call), a "link existing recipient" form, and a "retry this instruction only" action. This is explicitly classified as **exception handling / configuration** UI (task §15) — the normal Process does not require opening it.

---

## What this pilot does NOT implement (blocker reported, not worked around)

Per this task's own explicit instruction (§12/§14): where Attention Management or Organizational Responsibility would need a genuinely new, cross-domain, reusable Foundation to implement correctly, this pilot stops and reports rather than building a Tips-specific shortcut.

- **Attention Management runtime** (Core 2.0 `12_Attention_Management.md`): does not exist anywhere in this codebase today. `TipPaymentInstruction.priority`/`failure_class`/`reason_for_failure` are plain Domain data — a genuine transversal capability that determines **who** receives an item, through **what channel**, with escalation policy, does not exist and is not built here.
- **Organizational Responsibility runtime** (Position/Occupant/Delegation): does not exist anywhere in this codebase today. No Position is attributed to this Process or its exceptions in software (only conceptually, in this document).
- **Mobile/Attention Inbox delivery** (task §14): no PWA, native app, or push-notification infrastructure exists in this repository today (confirmed by inspection — `03 Software/RF-One Web` is a server-rendered Flask app, mobile-responsive at best, with no manifest/service worker/push mechanism). Building a reusable, cross-domain Attention Inbox is a new Foundation, not a Tips concern — **not built here**. Today, a failure is only visible by opening `/payouts` in a browser.

**Recommendation:** a dedicated, separate task/spec (Documentation First, per CLAUDE.md) to design the actual Attention Management + Organizational Responsibility runtime, reusable by Tips and every other Domain, before any Domain builds its own notification path.

---

## External Funding Dependency

Chase → Mercury funding is out of scope (unchanged from the earlier Mercury discovery tasks). This pilot only reads what Mercury already reports as `availableBalance`; it never assumes RF-One can command Chase.

---

## Residual role of existing Tips UI

- `Calculate Tips` / `History` / `Distribution Rules` / `Roles`: **unchanged**, still the configuration/inspection/exception surfaces they already were.
- `/payouts`: **new**, exception handling & configuration only (see above) — never a required step of the normal Process.

---

## Related documents

- [Tip.md](Tip.md), [Tip Policy.md](Tip%20Policy.md), [Tip Allocation.md](Tip%20Allocation.md) — untouched Business Rules this pilot pays out
- `00 Core/ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`, `12_Attention_Management.md`, `13_Process_Activation_and_Trigger_Intelligence.md` — Core 2.0 principles consumed
- `01 Domains/Shared Domains/Administration/Payroll/Payment Execution.md` — the analogous, earlier Payroll boundary (`payment_execution_provider`, evidence-vs-status separation) this pilot's Tips-side design mirrors
- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/mercury/` — the connector
- `03 Software/RF-One Data Store/rfone_data_store/tips/{readiness,payment_instruction,payout_process}.py` — the pilot's own modules
- `03 Software/Tips/sandbox_pilot_e2e.py` — the real-sandbox demonstration script (never part of the automated test suite)
- `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md` — full implementation report
