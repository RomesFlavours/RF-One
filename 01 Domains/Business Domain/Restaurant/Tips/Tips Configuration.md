# Tips Configuration — Calculation Schedule, Payment Schedule, and Payment Cycle

**Version:** 1.1 — extended by TASK_TIPS_RESTAURANT_AUTHORITY_SCOPE_001 (§7) and TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 (§10-§12), noted inline below
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

This CALCULATION-time gate deliberately checks the Live Cursor only — never the Correction/Reconciliation Poller's own Modification Cursor (§10 below). **Clover live is about operational freshness** ("has new data for this Business Date arrived"); **Clover reconciliation is about payment consolidation** ("have corrections to already-acquired data been swept before money actually moves") — two different questions, asked at two different moments of the same overall process, never conflated. §10 formalizes the second one, applied at PAYMENT time (Approve & Pay), not at calculation time.

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

`payment_cycle_service.approve_and_pay_cycle` calls the shared `authority_service.authorize()` (domain `TIPS`, action `APPROVE_AND_PAY`, scope `RESTAURANT`/`scope_id=<this cycle's restaurant_id>`) before any Mercury call — an unauthorized Acting Identity is rejected with no state change and no funding check performed. Funding is still checked once for the whole batch before any instruction submits (unchanged from the original pilot). Immediately after Authority, the SAME function also checks Payment Readiness (§10) — both gates, never either alone, guard every Mercury call regardless of which of the three modes (§11) triggered it.

**Restaurant-scoped Authority (TASK_TIPS_RESTAURANT_AUTHORITY_SCOPE_001 — resolves the gap this section previously reported):** `AuthorityGrant.scope_type` now includes `RESTAURANT` (`models.AUTHORITY_SCOPE_KINDS`), mirroring `Position`/`ProcessOwnership`'s own `POSITION_SCOPE_KINDS`. An Acting Identity authorized for Restaurant A is never thereby authorized for Restaurant B; the same identity may hold one such grant per Restaurant (e.g. Winter Park + Mount Dora), with no duplication/workaround. A `GLOBAL`-scoped grant continues to authorize every Restaurant unconditionally — `authorize()`'s GLOBAL match is unconditional regardless of the requested scope — so a genuine cross-Restaurant authorization is still expressed with a GLOBAL grant, never by omitting scope. The Tips Payment Control page (§12) offers only Acting Identities actually authorized for the Restaurant currently in view.

---

## 8. Attention Management integration

A failed, blocked, cancelled, or reopened (reversed) `TipPaymentInstruction` raises exactly one `AttentionItem` (`attention_service.create_attention` + `route_attention`), scoped `POSITION_SCOPE_RESTAURANT`, routed through the SAME Process Ownership -> Position -> Occupant -> Temporary Coverage -> Backup Position -> Organizational Fallback chain every other Domain already uses — no Tips-specific escalation model, no hardcoded recipient. A successful instruction raises nothing. This closes the exact gap `Tips Payment Execution.md`'s original "What this pilot does NOT implement" section flagged (the Attention/Organizational Responsibility foundation has since been built, independent of Tips, and Tips now consumes it).

---

## 9. Manual and Automatic triggers share one gated entry point

"Run Calculation Now" (Tips Configuration page) and the automatic Calculation scheduler tick both call the identical `payout_process.run_calculation_now` — manual action never bypasses Clover readiness or the already-calculated check. Symmetrically, "Start Payment Cycle Now" and the automatic Payment scheduler tick both call `payment_cycle_service.start_payment_cycle` — but **only** the aggregation step. Whether Approve & Pay itself is automatic depends on the Payment Schedule's `auto_approval_mode` (§11) — §7's Authority gate and §10's Payment Readiness gate apply unconditionally either way, never bypassed by automation.

`tips/scheduler.py` runs two independent loops (mirroring `technical/connectors/clover/live_sync.py`'s own polling-process shape) — Calculation and Payment never share a scheduler process, matching §1's principle at the automation layer too.

---

## 10. Payment Readiness — the Clover reconciliation gate before Approve & Pay

TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 implements the Correction/Reconciliation Poller `CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` §3 approved but §3 above's Calculation-time gate predates — `technical/connectors/clover/reconciliation_poller.py`, a continuous, ~60s-default, configurable process that revisits already-acquired Clover records by `modifiedTime` (not `createdTime`), catching a correction to a record regardless of how long ago it was originally created (a voided line item, a finalized tip, a corrected employee reassignment). Reuses the exact same `acquisition.import_clover_period()` path Live Sync/Backfill already use (`mode=RECONCILIATION`) — no second database, no Clover event ledger, no full POS history.

`tips/payment_readiness.describe_payment_readiness(session, restaurant_id)` is the new, separate PAYMENT-time gate (never confused with §3's CALCULATION-time gate) `payment_cycle_service.approve_and_pay_cycle` checks immediately after Authority, before any Mercury call:

```text
Payment Cycle
  -> Clover live healthy (Live Sync/Backfill running and succeeding, not stalled)
  -> reconciliation recent and successful (Correction/Reconciliation Poller,
     within a bounded staleness window, default 5 minutes)
  -> no blocking (CRITICAL) Attention pertinent to this Restaurant's Tips
  -> READY FOR PAYMENT
```

Stale, failed, or incomplete reconciliation makes the Payment Cycle **NOT READY** — a normal, expected, non-alarming wait (never treated as a financial error, never itself raising Attention), reported via `PaymentNotReadyError` and shown calmly in Payment Control (§12). Only a **persistently** failing reconciliation (stale/failed beyond a longer threshold, default 30 minutes) is escalated to a human, via `payment_cycle_service.maybe_raise_attention_for_payment_readiness` — reusing the existing Attention Management capability (§8) unchanged, never a Tips-specific escalation mechanism. A Restaurant with no Clover-sourced Location at all is never gated (nothing to reconcile).

---

## 11. Three Tips payment modes

```text
MANUAL                        a human starts the cycle AND Approves & Pays it
                               (Payment Control, §12)

AUTOMATIC + WITH_APPROVAL      the scheduler opens the cycle when due; a
(TipsPaymentScheduleConfig.    human still Approves & Pays it — the
 auto_approval_mode, default)  pre-existing, unchanged behavior

AUTOMATIC + WITHOUT_APPROVAL   the scheduler opens the cycle when due, and
                               auto-approves it AS SOON AS §10 reports READY
                               — no human step
```

`auto_approval_mode` is a separate field from `mode` on `TipsPaymentScheduleConfig` (meaningful only when `mode=AUTOMATIC`; `NULL` means `WITH_APPROVAL`, the pre-existing behavior, so no existing configuration's behavior changed when this field was added). For `WITHOUT_APPROVAL`, `tips/scheduler.run_due_payment_cycle_auto_approvals` Approves & Pays using the stable **SYSTEM Acting Identity** (`acting_identity_service.get_or_create_system_identity`) — Core `09_Identity_Authority_and_Accountability.md` §5.1's "AI-Authorized Execution... strictly within explicit Delegated Authority": the SYSTEM identity must hold its own `TIPS`/`APPROVE_AND_PAY` `AuthorityGrant` for that Restaurant (§7), explicitly configured by that Restaurant — never implied merely by choosing `WITHOUT_APPROVAL`. Every mode passes through the identical §7 Authority gate and §10 Payment Readiness gate inside `approve_and_pay_cycle` — no mode has a shortcut around either.

---

## 12. Payment Control — authorized visual control surface, not a workflow engine

`03 Software/Tips/templates/payment_control.html` / `/payment-control` (TASK_TIPS_COMPLETE_001 §13, extended by TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001) is **one** responsive web surface for PC, smartphone and tablet — no separate mobile app, no separate mobile stylesheet. It shows, before any scrolling: Restaurant, Payment Cycle/period, Business Dates included, payee count, total due, Mercury available balance, Clover reconciliation status, and a single READY/NOT READY signal (§10) — Approve & Pay is offered only when both authorized (§7) and READY (§10), though the server-side gates inside `approve_and_pay_cycle` remain authoritative regardless of what the page shows. A per-payee Detail view (Business Dates included, gross/source tips, amounts transferred in/out, final payable, payment/provider status, Attention) is available without ever showing a full account number, routing number, token, or secret — none of which this schema even persists (`EmployeeExternalPaymentAccount` stores only Mercury's own opaque recipient id).

**Payment Control is the authorized visual control surface over the Payment Cycle — it is not the workflow engine.** Every business rule it displays or triggers (readiness, Authority, aggregation, Approve & Pay, retry) lives in `tips/payment_cycle_service.py`/`tips/payment_readiness.py`/`tips/scheduler.py`, called identically by this page, by `tips/scheduler.py`'s automatic ticks, and by a future Cognito capability — never a rule that exists only in a route or template.

`/payment-control/cycle/<cycle_id>` is a stable, resolvable deep-link route to one specific Payment Cycle, independent of whichever Restaurant this pilot's single-Restaurant `_default_restaurant()` convention would otherwise show — the concrete target a future Cognito capability (*"Le Tips di Winter Park sono pronte... Vuoi controllarle?"* → opens directly here) can link to. No Cognito capability is implemented by this route; it only makes that future integration possible without a later route/URL redesign.

---

## Related documents

- [Tips Payment Execution.md](Tips%20Payment%20Execution.md) — the Mercury sandbox payout pilot this document extends; its own "What this pilot does NOT implement" section is superseded where noted above
- [Tip.md](Tip.md), [Tip Policy.md](Tip%20Policy.md), [Tip Allocation.md](Tip%20Allocation.md) — untouched Business Rules
- `03 Software/RF-One Data Store/CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md` — the Cognito-vs-consolidation principle §2/§3 above mirrors, and the Correction/Reconciliation Poller architecture §10 implements
- `00 Core/ConceptualArchitecture/12_Attention_Management.md`, `Organizational Responsibility.md` — the shared runtime §8/§10 consume, unchanged
- `00 Core/ConceptualArchitecture/09_Identity_Authority_and_Accountability.md` §5.1 — AI-Authorized Execution, the concept §11's AUTOMATIC WITHOUT APPROVAL mode applies
- `03 Software/RF-One Data Store/rfone_data_store/tips/{schedule_service,payment_cycle_service,payment_readiness,scheduler}.py` — this document's own modules
- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/clover/reconciliation_poller.py` — the Correction/Reconciliation Poller §10 describes
- `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md`, `TIP_DISTRIBUTION_ENGINE_001.md` — prior implementation reports this document builds on
