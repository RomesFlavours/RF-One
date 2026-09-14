# RF-One 2.0 — Review Branch for Shelbi

**Branch:** `review/shelbi-rfone-2.0` · **Base:** `release/rf-one-2.0`

This document orients a review of what has changed since the last review. It is written for a technical/product reader, not as an internal task log.

---

## 1. What RF-One 2.0 is now

RF-One 2.0 is the frozen Core (`00 Core/`) plus a working Restaurant Domain running on a single canonical operational database (SQLAlchemy/Alembic, `03 Software/RF-One Data Store/`). The baseline (`release/rf-one-2.0`) already includes Organizational Responsibility + Attention Management, the Organizational Chart admin page, a first Tips "process-first" pilot, and the Selection/Pills/Training-Service documentation set (reconstructed after a prior working-tree loss). This review branch adds three further, independently-developed lines of completed work on top of that baseline: **Tips end-to-end**, **Cognito's conceptual evolution**, and the **Purchased Shared Domain definition**.

## 2. Major changes since previous review

- **Tips is now end-to-end**, not a pilot: configuration UI, configurable schedules/entitlements/payment cycles, Restaurant-scoped approval authority, a Clover reconciliation gate before any payment, a responsive Payment Control surface, and a Mercury **sandbox** integration — all validated together (see §5).
- **Cognito gained three approved conceptual extensions** — Human Operational State, Ambient Operational Context, and Visual/Video Context as Ambient Evidence — layered onto the frozen Core without reopening it (see §6).
- **A new Shared Domain, Purchased, was defined** — the cross-industry "purchase fact" concept, alongside the repository-wide rename of the `Cross Domain` domain family to `Shared Domains` (see §7).
- One real architectural question surfaced while integrating this branch and was resolved conservatively — see §7 and §9.

## 3. Implemented software (this branch, on top of the baseline)

- **Tips**: `03 Software/Tips/` (configuration + Payment Control UI) and `rfone_data_store/tips/` (schedule service, payment-cycle service, payment readiness, scheduler).
- **Clover Correction/Reconciliation Poller**: `rfone_data_store/technical/connectors/clover/reconciliation_poller.py` — a second, short-interval poll that catches corrections to already-acquired records (voided items, late tip finalization), which the existing Live Sync path cannot see.
- **Payroll/Authority**: `authority_grants.scope_type` widened to allow Restaurant-scoped grants, underpinning Tips' own approval authority.
- Three additive Alembic migrations for the above; **no destructive schema change**.

Everything else in the codebase (Organizational Responsibility, Selection, Clover ingestion, Payroll, Compensation, RF-One Web) is unchanged from the baseline and re-verified by regression (§8).

## 4. Approved architecture / not yet implemented

Approved but **not implemented** in this or any branch — documentation only, no software, schema, or runtime:

- Cognito runtime, mobile Cognito app, wearable integration, computer vision / video ingestion.
- End-user Attention Inbox (only admin/config/test surfaces exist).
- Production Mercury (sandbox only — no production endpoint or token in code).
- Purchased software / a new Invoice Intake → Purchased persistence pipeline (see §7).
- Guidability formal scoring, Training curriculum-to-scale conversion, AI scoring authorization.

## 5. Tips end-to-end status

Implemented and validated: Tips configuration, calculation schedules, daily entitlements, payment cycles, Restaurant-scoped approval authority, the Clover reconciliation gate (payment is blocked until Clover data is live-healthy and recently reconciled, not just "recorded"), a responsive Payment Control UI (desktop/tablet/phone), Mercury **sandbox** payout execution, and integration with the existing Attention capability for persistent reconciliation failures. All three approval modes (manual, automatic-with-approval, automatic-without-approval) funnel through one gate. 259 automated checks across 10 dedicated Tips test suites pass (§8). No production Mercury credential exists anywhere in the code.

## 6. Cognito evolution

Three documents were added to `00 Core/ConceptualArchitecture/` (15, 16, 17), each explicitly marked **APPROVED — Post-Baseline Conceptual Extension** — ratified by the Product Owner, but deliberately *not* folded into the frozen Core 2.0 canonical set (00–14) and not retroactive to `release/rf-one-2.0`:

- **Human Operational State & Adaptive Cognito Interaction** — a person's temporary condition (fatigue, stress, cognitive load) as authorized physiological evidence that may *shape* Cognito's interaction style, never trigger or suppress a process, and never touch Organizational Responsibility.
- **Ambient Operational Context & In-Flow Cognito Assistance** — passive environmental/situational evidence Cognito may use for Context Interpretation; recognizes Restaurant's existing Service Copilot as its first Domain-level consumer, without changing Service Copilot's own approved behavior.
- **Visual/Video Context as Ambient Evidence** — a sub-extension of the above: authorized images/video as one more ambient-evidence source, always scene-level, never an automatic Fact, never a judgment about a person.

All three are concept documents only — no wearable, sensor, microphone, camera, or ML component exists anywhere in the repository for any of them.

## 7. Shared Domains / Purchased

`docs/shared-domains-purchased` is included. It brings:

- The repository-wide rename of the domain family from **Cross Domain** to **Shared Domains** (`01 Domains/Shared Domains/…`).
- **Purchased**, a new top-level Shared Domain: the cross-industry "purchase fact" concept (capture → normalize → publish), functionally scoped and explicitly bounded away from Procurement, Accounts Payable, Accounting, Bank Reconciliation and Inventory.

**Not implemented:** no software exists yet that persists to Purchased, and the existing Invoice Intake prototype (`03 Software/InvoiceIntake/`) still writes to Restaurant/Purchasing's own model on this branch — the alignment work is tracked separately and is **not part of this review branch**.

**Integration note:** `docs/shared-domains-purchased` was branched before the baseline's own Training Service decision (`TRAINING_SERVICE_001.md`, 2026-09-11 — already part of `release/rf-one-2.0`) and still contained older wording asserting a different owner for "closing a trainable gap." This surfaced as a real content conflict in three README files during the merge (Continuous Productivity Development, Operational Knowledge, Selection). Resolved per explicit Product Owner direction: the repository-wide rename was applied everywhere, including these three files, but the already-approved Training Service wording was kept as-is rather than reintroduced with the older claim. No other functional content was chosen between the two branches. See the merge commit for full detail.

## 8. What Shelbi should review

1. **Tips payment gate** — confirm the Clover-reconciliation-before-payment logic (`tips/payment_readiness.py`) matches intended risk tolerance, especially the default 5-minute staleness / 30-minute Attention-escalation thresholds.
2. **The three Cognito extension documents** (15, 16, 17) — conceptual soundness and scope boundaries, ahead of any future runtime work.
3. **The Training Service conflict resolution** in §7 — confirm the kept wording is in fact still current, and decide whether `docs/shared-domains-purchased` needs a rebase before its next update.
4. **Purchased's functional boundary** (`01 Domains/Shared Domains/Purchased/README.md`) — is the domain scope right before any software is built against it.

## 9. Known next steps

- Rebase/update `docs/shared-domains-purchased` against current `release/rf-one-2.0` so it no longer disagrees with the Training Service decision.
- Decide whether/when to build the Invoice Intake → Purchased persistence pipeline (currently Restaurant/Purchasing-only).
- Production Mercury onboarding (credential, endpoint, approval) remains external and unscheduled.
- End-user Attention Inbox remains unbuilt.
