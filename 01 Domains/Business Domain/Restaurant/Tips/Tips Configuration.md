# Tips Configuration — Calculation Schedule, Payment Schedule, and Payment Cycle

**Version:** 1.0
**Status:** IMPLEMENTED — sandbox-only Mercury payout; see `Tips Payment Execution.md` for the payout-pilot boundary this document does not change
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_COMPLETE_001

---

## Purpose

Completes Tips as a configurable, end-to-end, Restaurant-scoped process:

```text
Clover Operational Data
  -> Daily Tips Calculation
  -> Saved Tip Entitlements
  -> Configurable Payment Cycle
  -> Authorization (Approve & Pay)
  -> Mercury
  -> Outcome Verification
  -> Attention Management on exceptions only
```

This document does not redefine any Tip Business Rule (`Tip.md`, `Tip Policy.md`, `Tip Allocation.md`, `TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md`) or the Mercury payout pilot boundary (`Tips Payment Execution.md`) — it formalizes the three timing/aggregation concepts those documents assumed would eventually need to exist: **when to calculate**, **when to pay**, and **how unpaid results accumulate between the two**.

---

## 1. Three distinct concepts — never conflated

**Calculation Schedule != Payment Schedule != Distribution Rules.**

| Concept | Answers | Owned by |
|---|---|---|
| **Calculation Schedule** | *When* does RF-One compute and save each Business Date's Tip result? | `TipsCalculationScheduleConfig` / `tips/schedule_service.py` |
| **Payment Schedule** | *When* does RF-One aggregate unpaid results into a payout batch? | `TipsPaymentScheduleConfig` / `tips/schedule_service.py` |
| **Distribution Rules** | *How much* does each Recipient Role receive from each Source Role, and from *which* base? | `TipDistributionRule`/`TipDistributionRuleVersion` / `tips/distribution_rule_service.py` (unchanged by this document) |

A Restaurant may calculate daily while paying out weekly — or any other independent combination. Neither schedule is ever inferred from the other, and neither is inferred from Distribution Rules (a rate change and a cadence change are configured, and effective-dated, completely independently).

Both schedules share the same shape: `mode` (`MANUAL` | `AUTOMATIC`), and, only when `AUTOMATIC`, `interval_days` ("every N days"), `execution_time`, and an `anchor_date` the interval counts from. Neither hardcodes daily or weekly — a Restaurant that never configures a schedule stays `MANUAL` only, exactly like Distribution Rules already require explicit configuration before anything is calculated.

---

## 2. Cognito vs. Tips — two different freshness contracts

This is the same distinction `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` establishes for Clover data generally, restated here for Tips specifically:

```text
Cognito  -> reads live RF-One operational data, accepts a short eventual-
            consistency window (seconds), privileges responsiveness
Tips     -> reads only RECONCILED/CONSOLIDATED Business Date data,
            privileges correctness over freshness
```

Concretely: `tips/readiness.describe_readiness()`'s `clover_ready` gate (§3 below) means a Business Date is never calculated while its Clover data might still be incomplete — Tips is willing to wait; Cognito, by design, is not. Neither module reads the other's gate.

---

## 3. Clover readiness gate (Calculation Schedule only)

Automatic (or manual) calculation never runs merely because the scheduled time arrived or a human clicked a button:

```text
Schedule / Manual Trigger
  -> Clover Live Sync cursor has this Business Date's own end already passed?
       NO  -> record NOT READY (blocked_reason), no calculation, retried next
              scheduler tick or next manual click — never a false financial error
       YES -> calculate
```

`tips/readiness._clover_live_sync_readiness` checks the Restaurant's Clover-sourced Location(s)' `IngestionRun.source_window_end` (the same Live Cursor `technical/connectors/clover/live_sync.py` already maintains) against the Business Date's own end. A Location with no Clover source at all is never gated (nothing to check).

**Known scope boundary of this gate (see this task's final report "Known gaps"):** this baseline predates the separately-approved Correction/Reconciliation Poller architecture decision (`CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md`), which is not implemented on this branch. This gate therefore checks the Live Cursor only — a fuller reconciliation-based gate (checking that *corrections* to already-acquired records have also been swept, not just that new records have been acquired) is future work layered on top of this same `describe_readiness()` entry point, not a redesign of it.

---

## 4. Daily calculation, less-frequent payment

The recommended pattern: `TipsCalculationScheduleConfig.interval_days = 1` (daily) with `TipsPaymentScheduleConfig.interval_days = 7` (weekly). Each daily calculation run persists one `TipEntitlement` row per Employee (§5) via `distribution_engine.populate_entitlements_for_run` — the SAME per-Employee aggregate `build_employee_review` already computed on the fly, now durable. Nothing here recalculates already-consolidated history: `run_tip_distribution_calculation`'s own existing supersession discipline (recalculating the EXACT same period marks the prior run superseded; a different, overlapping period is refused) is unchanged.

---

## 5. Tip Entitlement — the persisted daily result

`TipEntitlement` (`03 Software/RF-One Data Store/rfone_data_store/models.py`): one row per (calculation run, Employee) — Business Date, Restaurant, employee, gross amount, outbound/inbound distribution, final payable, which calculation run produced it, and (once assigned) which `TipPaymentInstruction` will pay it. `tip_payment_instruction_id IS NULL` is the "unpaid" state a Payment Cycle (§6) queries directly, across as many Business Dates as have accrued.

---

## 6. Payment Cycle — aggregating unpaid entitlements

`TipPaymentCycle` (`tips/payment_cycle_service.py`) replaces the original Mercury pilot's "exactly one calculation run per payout" assumption. `start_payment_cycle` aggregates **every** currently-unpaid `TipEntitlement` for a Restaurant — spanning as many Business Dates as accrued since the previous cycle — into one `TipPaymentInstruction` per Employee. Starting a cycle is idempotent (an already-OPEN cycle is returned unchanged, never duplicated) and does **not** submit anything to Mercury by itself.

```text
Payment Cycle status:
  OPEN      -> entitlements aggregated into READY instructions; REVIEW state
  APPROVED  -> an authorized Acting Identity ran Approve & Pay (§7); per-
               Employee outcome lives on the instructions themselves, never
               re-derived on the cycle row
```

---

## 7. Approve & Pay — Authority, never `is_admin`

`payment_cycle_service.approve_and_pay_cycle` calls the shared `authority_service.authorize()` (domain `TIPS`, action `APPROVE_AND_PAY`) before any Mercury call — an unauthorized Acting Identity is rejected with no state change and no funding check performed. Funding is still checked once for the whole batch before any instruction submits (unchanged from the original pilot).

**Reported Authority-model gap (not invented around):** `AuthorityGrant.scope_type` (`models.AUTHORITY_SCOPE_KINDS`) has no `RESTAURANT` value today, unlike `Position`/`ProcessOwnership`'s own `POSITION_SCOPE_KINDS`, which already does. Approve & Pay grants are therefore `GLOBAL`-scoped ("may Approve & Pay Tips at all"), not yet Restaurant-scoped. Extending `AuthorityGrant`'s scope vocabulary is a Core/Authority-model decision outside this document's scope.

---

## 8. Attention Management integration

A failed, blocked, cancelled, or reopened (reversed) `TipPaymentInstruction` raises exactly one `AttentionItem` (`attention_service.create_attention` + `route_attention`), scoped `POSITION_SCOPE_RESTAURANT`, routed through the SAME Process Ownership -> Position -> Occupant -> Temporary Coverage -> Backup Position -> Organizational Fallback chain every other Domain already uses — no Tips-specific escalation model, no hardcoded recipient. A successful instruction raises nothing. This closes the exact gap `Tips Payment Execution.md`'s original "What this pilot does NOT implement" section flagged (the Attention/Organizational Responsibility foundation has since been built, independent of Tips, and Tips now consumes it).

---

## 9. Manual and Automatic triggers share one gated entry point

"Run Calculation Now" (Tips Configuration page) and the automatic Calculation scheduler tick both call the identical `payout_process.run_calculation_now` — manual action never bypasses Clover readiness or the already-calculated check. Symmetrically, "Start Payment Cycle Now" and the automatic Payment scheduler tick both call `payment_cycle_service.start_payment_cycle` — but **only** the aggregation step; Approve & Pay is never automatic, regardless of trigger source (§7's Authority gate always applies).

`tips/scheduler.py` runs two independent loops (mirroring `technical/connectors/clover/live_sync.py`'s own polling-process shape) — Calculation and Payment never share a scheduler process, matching §1's principle at the automation layer too.

---

## Related documents

- [Tips Payment Execution.md](Tips%20Payment%20Execution.md) — the Mercury sandbox payout pilot this document extends; its own "What this pilot does NOT implement" section is superseded where noted above
- [Tip.md](Tip.md), [Tip Policy.md](Tip%20Policy.md), [Tip Allocation.md](Tip%20Allocation.md) — untouched Business Rules
- `03 Software/RF-One Data Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` — the Cognito-vs-consolidation principle §2/§3 above mirrors
- `00 Core/ConceptualArchitecture/12_Attention_Management.md`, `Organizational Responsibility.md` — the shared runtime §8 consumes, unchanged
- `03 Software/RF-One Data Store/rfone_data_store/tips/{schedule_service,payment_cycle_service,scheduler}.py` — this document's own new modules
- `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md`, `TIP_DISTRIBUTION_ENGINE_001.md` — prior implementation reports this document builds on
