# Tips Payment Execution — Core 2.0 Process-First Pilot

**Version:** 0.1 — pilot, for technical review (JP, Shelbi); operational context extended by `Tips Configuration.md` (Payment Cycle, Payment Readiness, connector-neutral execution, STEP 12B) — noted inline below
**Status:** PILOT — IMPLEMENTED items below are real, working, sandbox-only code; nothing here is deployed or authorized for production. Payment execution now runs inside the Payment Cycle model and the connector-neutral resolver `Tips Configuration.md` describes — this document's own "What this pilot did NOT implement" section is historical (see its updated note below).
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

**IMPLEMENTED (STEP 12B integration).** `tips/payment_connector.py` is the connector-neutral seam this decision required: a small, explicit, deterministic registry (`resolve_connector`) maps `TipsPaymentScheduleConfig.connector_code` (the "Payment mode / configuration" setting above, see `Tips Configuration.md` §7) to a registered connector implementation. `payment_instruction.py`/`payment_cycle_service.py`/`scheduler.py` execute against whichever `PaymentConnector` they are given and catch only connector-neutral exceptions (`payment_connector.PaymentConnectorError` and its subclasses) — they never import `technical.connectors.mercury` directly. Missing or unknown connector configuration **fails closed** (`ConnectorNotConfiguredError`/`UnknownConnectorError`) — there is no code path that falls back to Mercury silently. Mercury (`MercuryPaymentConnector`, wrapping `technical/connectors/mercury/`) is registered exactly like any future second connector would be, under the code `MERCURY` — it remains this pilot's one currently-*real* connector, never the canonical payment model, and every Mercury-specific detail below (its sandbox endpoints, its recipient/idempotency model, its failure classes) stays inside that one adapter.

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

Untouched. The persisted calculation is `calculation_run_service.save_calculation_run` (the Location's Business Day, `build_employee_review` reused as-is); this pilot only consumes `EmployeeReviewRow.net_before_adjustments_minor` as the per-Employee Final Payable, and only from a FINAL run (BANK_FINAL_RELEASE_BLOCKERS_001).

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

### UI — superseded by Payment Control (STEP 12B)

The `/payouts` route/template this section originally described has been **replaced** by `/payment-control` (`03 Software/Tips/templates/payment_control.html`) and `/tips-configuration` (`tips_configuration.html`) — see `Tips Configuration.md` §12 for the current UI. It offers the same read-only readiness summary, per-instruction status/priority/reason, retry, and recipient-linking actions this section described, now against the Payment Cycle model (§6 there) rather than one calculation run at a time, and remains **exception handling / configuration** UI, never a required step of the normal Process.

---

## What this pilot did NOT implement at v0.1 — since built (STEP 12B integration)

Per this task's own original instruction (§12/§14): where Attention Management or Organizational Responsibility needed a genuinely new, cross-domain, reusable Foundation to implement correctly, this pilot stopped and reported rather than building a Tips-specific shortcut. That Foundation has SINCE been built, independent of Tips (TASK_ATTENTION_ORG_RUNTIME and later organizational-runtime work), and Tips now consumes it — this section is historical record, not the current state:

- **Attention Management runtime** (Core 2.0 `12_Attention_Management.md`): now exists (`attention_service.py`) and is consumed directly by `tips/payment_cycle_service.py` — a failed/reopened `TipPaymentInstruction`, or a persistently-failing Payment Readiness gate, raises exactly one `AttentionItem`, routed through the shared Process Ownership -> Position -> Occupant -> Temporary Coverage -> Backup Position -> Organizational Fallback chain, never a Tips-specific escalation path. See `Tips Configuration.md` §8/§10.
- **Organizational Responsibility runtime** (Position/Occupant/Delegation): now exists and is what the Attention routing above resolves through.
- **Mobile/Attention Inbox delivery**: still not built as a dedicated push/PWA mechanism — a failure remains visible by opening Payment Control in a browser (now a responsive, phone/tablet/PC-friendly surface, `Tips Configuration.md` §12, rather than a PC-only page).

---

## External Funding Dependency

Chase → Mercury funding is out of scope (unchanged from the earlier Mercury discovery tasks). This pilot only reads what Mercury already reports as `availableBalance`; it never assumes RF-One can command Chase.

---

## Residual role of existing Tips UI

- `Calculate Tips` / `History` / `Distribution Rules` / `Roles`: **unchanged**, still the configuration/inspection/exception surfaces they already were.
- `Tips Configuration` / `Payment Control`: **current** (STEP 12B, superseding `/payouts` above) — exception handling & configuration only, never a required step of the normal Process. See `Tips Configuration.md`.

---

## Related documents

- [Tip.md](Tip.md), [Tip Policy.md](Tip%20Policy.md), [Tip Allocation.md](Tip%20Allocation.md) — untouched Business Rules this pilot pays out
- [Tips Configuration.md](Tips%20Configuration.md) — the current Calculation/Payment Schedule, Payment Cycle, Payment Readiness, and Payment Control UI this document's payout mechanics now operate inside
- `00 Core/ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md`, `12_Attention_Management.md`, `13_Process_Activation_and_Trigger_Intelligence.md` — Core 2.0 principles consumed
- `01 Domains/Shared Domains/Administration/Payroll/Payment Execution.md` — the analogous, earlier Payroll boundary (`payment_execution_provider`, evidence-vs-status separation) this pilot's Tips-side design mirrors
- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/mercury/` — the one currently-real connector
- `03 Software/RF-One Data Store/rfone_data_store/tips/payment_connector.py` — the connector-neutral registry/resolver (STEP 12B) this document's "Canonical payment-connector decision" is implemented by
- `03 Software/RF-One Data Store/rfone_data_store/tips/{readiness,payment_instruction,payout_process,payment_cycle_service,payment_readiness,schedule_service,scheduler}.py` — the pilot's own modules, as integrated
- `03 Software/Tips/sandbox_pilot_e2e.py` — the real-sandbox demonstration script (never part of the automated test suite)
- `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md` — full implementation report (v0.1, pilot)
