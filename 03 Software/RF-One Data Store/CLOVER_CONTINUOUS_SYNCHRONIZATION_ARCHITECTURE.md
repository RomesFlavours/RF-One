# Clover Continuous Synchronization Architecture

**Status:** APPROVED ARCHITECTURAL DECISION
**Module:** Software / RF-One Data Store / Technical Connectors (Clover)
**Scope:** Documentation-only architectural decision. No software, database, or connector behavior is changed by this document.

---

## Related documents

- [CLOVER_INGESTION.md](CLOVER_INGESTION.md) — the one-off, manually-triggered bulk historical pipeline (`ingest_clover.py`) and its design decisions. That document's own §1 already distinguishes it from the live/automated runtime path (`acquisition.py`'s `import_clover_period()`); **this document is the canonical description of that live/automated runtime path**, which `CLOVER_INGESTION.md` only mentions in passing.
- [CLOVER_INGESTION_RECONCILIATION.md](CLOVER_INGESTION_RECONCILIATION.md) — results of one specific bulk-pipeline run's post-ingestion reconciliation (counts/checks/monetary/weekly confidence). Distinct from the **continuous** Correction/Reconciliation Poller this document formalizes (§3) — the bulk pipeline's reconciliation is a one-time validation of a completed historical load, not a running process that revisits already-ingested live data.
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — canonical schema reference, including `SourceRecord` (Provider Mirror) and the `source_created_at`/`source_modified_at` precedent this document's §9 builds on.
- `rfone_data_store/technical/connectors/clover/acquisition.py`, `live_sync.py`, `freshness.py`, `reconciliation.py` — the existing code this document names, formalizes the role of, and extends conceptually. Their own module docstrings remain the authoritative low-level design reference; this document does not restate or supersede them, only names the architectural pattern they already partially implement and the pattern still missing (§3–§4).
- `07 Tasks/Reports/CLOVER_DATA_ACQUISITION_ARCHITECTURE_001.md`, `07 Tasks/Reports/TECHNICAL_CONNECTORS_STRUCTURE_001.md` — implementation history of the existing Live Sync / Historical Backfill / concurrency-guard mechanics this document builds on without repeating.
- [../../01 Domains/Business Domain/Restaurant/Sales/Restaurant Sales Model.md](../../01%20Domains/Business%20Domain/Restaurant/Sales/Restaurant%20Sales%20Model.md) §6a — **Business Date**, the existing canonical concept §7 below anchors Tips consolidation to. Not redefined here.
- [../../01 Domains/Business Domain/Restaurant/Tips/Tips Payment Execution.md](../../01%20Domains/Business%20Domain/Restaurant/Tips/Tips%20Payment%20Execution.md) — `tips/readiness.py`'s existing `describe_readiness()`, the existing concrete instance of the "Business Date consolidated/ready" gate §7 below describes conceptually. Not redefined here.
- [../../00 Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md](../../00%20Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md) — Cognito reasons with canonical RF-One knowledge, never a competing copy of it (§4 there). §6 below is the concrete instance of that principle for Clover-sourced operational data specifically. This document does not modify Core; the reference is one-directional.
- [../../00 Core/ConceptualArchitecture/12_Attention_Management.md](../../00%20Core/ConceptualArchitecture/12_Attention_Management.md) — cross-referenced only where it already exists (its own "Real-time operational intervention" §4 concerns *when a human is alerted*, not *data freshness*, and is not affected by anything in this document). No new Attention Management logic is introduced here.

---

## Purpose

This document is the canonical architectural decision governing how Clover data continuously reaches RF-One's canonical operational database, and how "fresh enough" is deliberately balanced against "correct enough," for two different consumers with two different needs: Cognito (operational interaction) and Tips (financial payout).

It formalizes a decision, not a redesign: Live Sync (already implemented) is confirmed as the correct shape for near-real-time acquisition; a Correction/Reconciliation Poller (not yet implemented) is approved as the necessary complement to it, closing a real, verified gap (§3). No code, schema, or connector behavior changes as a result of this document.

---

## 1. General principle

RF-One uses Clover as the **source operational system** for Restaurant point-of-sale facts. RF-One does **not** exist to replicate Clover's full POS/transactional history.

RF-One maintains three distinct properties, deliberately kept separate:

```text
A. a very fresh operational state       (seconds behind Clover)
B. a corrected state within a short interval   (about a minute behind, for rare corrections)
C. a separate, deliberately slower consolidation level for financial processes
```

Clover remains the system of record for POS/transactional history. RF-One's canonical operational database reflects the **operational reality currently needed by RF-One's own processes** — not a parallel, permanent replica of every intermediate POS state that ever existed.

---

## 2. Fast Live Extractor

**Fast Live Extractor** is the continuous, always-running process that keeps RF-One's canonical operational data close to real time.

**This role is already implemented today** by `technical/connectors/clover/live_sync.py` (`run_live_sync_cycle()` / `_run_forever()`), reusing the shared `acquisition.import_clover_period()` fetch/mapping/upsert path. Nothing here proposes a second implementation of it.

- **Frequency:** default 15 seconds (`DEFAULT_POLL_INTERVAL_SECONDS`), configurable per deployment (`--interval-seconds`) — within this document's recommended ~10–15 second range.
- **Cursor today:** one **Live Cursor** per Clover-sourced Location, persisted as the latest COMPLETE/PARTIAL `IngestionRun.source_window_end` for that Location (`compute_next_sync_window()`), advanced every cycle, with a small overlap buffer (default 2 minutes) so a record settling moments after a prior cycle's fetch is still reliably captured on the next one.
- **Scope today:** the reduced, continuously-relevant operational entity set (Orders, Order Items, Order Item Modifiers, Payments, Payment Tips, Refunds, Order Fees, Shifts, Employees) — not the full catalog/reference set, which only Historical Backfill refreshes (`CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001`).
- **Purpose:** minimize transferred volume and keep RF-One's operational data close to Clover's current state, for newly-created records.

**Cursor granularity — current state vs. this decision's target shape.** Today's Live Cursor is scoped **per Location**, shared by every entity type fetched in that Location's cycle — not one independent cursor per Location *and* per resource/table, as this document's ideal model (§4) describes. This is recorded as a known, non-blocking granularity gap (see Report §K), not a defect: a single per-Location cursor is a correct, safe implementation of the *current* Live Sync scope (a fixed, small set of entities always fetched together). Splitting the Live Cursor into independent per-resource/table cursors is a legitimate future refinement — useful mainly if different entity types eventually need materially different polling cadences — but is **not implemented and not decided by this document**; it is not required to make the Fast Live Extractor role, as it exists today, sound.

---

## 3. Correction / Reconciliation Poller

**Correction/Reconciliation Poller** is a second, distinct, continuous process — **not yet implemented** — approved by this decision as a required complement to the Fast Live Extractor, not an alternative to it.

**Why it is needed — a verified, real gap, not a hypothetical one.** `import_clover_period()` filters Clover's Orders/Payments API calls by `createdTime` only (`acquisition.py`, `filter=[createdTime>=..., createdTime<=...]`). Live Sync's window therefore only ever revisits records **created** inside its own short recent window (plus its 2-minute overlap buffer). A correction made to a record whose `createdTime` has already scrolled out of that window — an order line item voided an hour later, a payment refunded the next day, an employee reassignment corrected after the shift — is **structurally invisible to Live Sync**, no matter how long it keeps running. `acquisition.py`'s own existing comment already anticipates exactly this failure mode for one case ("Card tips can finalize after `Payment.createdTime`, so a re-import MUST refresh the tip from Clover's current value") — but today's mechanism only catches it if the correction happens to land inside Live Sync's short window. This document formalizes the general-purpose process needed to catch it regardless of how much time has passed.

- **Frequency:** recommended ~60 seconds, configurable per deployment.
- **Purpose:** detect changes to Clover records **already previously acquired**, regardless of how long ago they were created, and correct RF-One's own canonical rows accordingly.
- **What it must intercept, where Clover exposes it:** modified Orders; removed/voided line items; modified Payments; Refunds; Employee reassignment; other equivalent corrections.
- **What it corrects:** the same RF-One Data Store the Fast Live Extractor writes to. It does **not** create a second database. It does **not** create a Clover event ledger/history — `SourceRecord` (Provider Mirror) remains what it already is today: an append-only, unmapped mirror of raw fetched payloads for audit/reconciliation/reprocessing, never read back for business logic, and this document does not expand its role into a general event-sourcing store.
- **Relationship to existing `reconciliation.py`:** the existing module performs a one-time, post-bulk-ingestion validation (counts/monetary/empirical checks) against a completed historical load. The Correction/Reconciliation Poller is conceptually related (both compare source to canonical) but operationally distinct: it runs continuously against live, already-canonical data, looking for **changed** records, not validating a completed batch. Whether it is eventually implemented as a new module, an extension of `live_sync.py`, or a variant of `freshness.py`'s on-demand pattern is an open implementation decision (§ Open decisions in the final report), not fixed here.

**This is not optional relative to the Fast Live Extractor.** Per §14, the two are both required; the Fast Live Extractor alone is fresh but does not self-correct outside its own short window, and the Correction/Reconciliation Poller alone would not deliver the near-real-time freshness Cognito needs. Neither replaces the other.

---

## 4. Two distinct cursors

Two cursors must be kept conceptually separate. **"Latest record acquired" is never assumed sufficient to detect that an already-acquired record was later modified.**

```text
LIVE CURSOR
→ marks how far forward new records have been acquired
→ today: IngestionRun.source_window_end, per Clover-sourced Location
  (§2 — shared across that Location's Live Sync entity scope)

MODIFICATION CURSOR
→ marks the last verified modifiedTime (or equivalent) checked for
  corrections, per Location / per resource-table
→ not yet implemented as a distinct construct
```

**What already exists toward a Modification Cursor.** Clover's `modifiedTime` is already captured as raw evidence on ingestion — `mapping.py` maps it into `source_modified_at` (Item, Employee, and other catalog/reference entities) or `modified_at` (Order, Payment). This gives the Correction/Reconciliation Poller (§3) the raw signal it needs once built; it does not, by itself, constitute the Modification Cursor — no process today reads these columns to decide "what changed since I last checked." Extending `source_modified_at`/`modified_at` coverage to every entity type the Poller must correct, and deciding where the cursor value itself is persisted (e.g. an `IngestionRun`-shaped record analogous to today's Live Cursor, or a new dedicated table), are open implementation decisions, not resolved by this document (no schema change is made here).

---

## 5. Eventual consistency is accepted, for Cognito, by design

For Cognito's operational use of Clover-sourced data, a short eventual consistency window is **an intentional product decision**, not a defect:

```text
RF-One may be a few seconds behind Clover on newly created records
     (bounded by the Fast Live Extractor's polling interval, §2)

RF-One may be up to about one minute behind Clover on rare corrections
     (bounded by the Correction/Reconciliation Poller's polling interval, §3)
```

**Rationale:** the probability that Cognito gives a materially wrong answer because of one single correction made in the last minute is judged operationally acceptable. This trade-off exists specifically because it makes Cognito's Human Interaction meaningfully faster and cheaper to operate than a design that always waits for full reconciliation before answering — the same "absorb complexity, keep the reason accessible" spirit already established for RF-One's user relationship, applied here to data timing rather than explanation depth. This is **not** described as a defect, a known bug, or a temporary limitation to be engineered away — it is the deliberately accepted boundary condition of this architecture.

---

## 6. Cognito usage boundary

Cognito does **not** query Clover directly, at any point, for any purpose.

Cognito consumes **RF-One Canonical Operational Data** — the same canonical schema every other Domain consumes — kept current by the Fast Live Extractor (§2) and corrected by the Correction/Reconciliation Poller (§3).

> **Cognito privileges operational freshness.** It accepts the short eventual consistency window of §5 in exchange for near-real-time responsiveness.

This is the Clover-specific instance of the general principle already established for Cognito ([14](../../00%20Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md) §1): Cognito reasons with canonical RF-One knowledge, never a second, independent, or provider-specific copy of it.

---

## 7. Tips / financial usage boundary

Tips does **not** treat live Clover data as the definitive basis for payout. Tips privileges **consolidation** over freshness:

```text
Clover live data
→ RF-One operational data (Fast Live Extractor, §2)
→ reconciliation (Correction/Reconciliation Poller, §3)
→ Business Date consolidated / ready
→ Tips calculation
→ payment cycle
→ Mercury
```

**"Business Date consolidated / ready" is not a new concept this document introduces** — it is the existing `Order.business_date` concept (Restaurant Sales Model §6a) together with the existing readiness gate `tips/readiness.py`'s `describe_readiness()` already exposes (latest `Order.business_date` on file, whether it is already calculated, Payment Instruction status, settlement). This document only states the general principle those existing mechanisms already embody: **Tips must not calculate or pay against a Business Date before that Business Date's Clover data has had the opportunity to pass through both the Fast Live Extractor and the Correction/Reconciliation Poller.** It does not change `readiness.py`'s logic, its schema, or its UI.

---

## 8. RF-One does not preserve POS operator errors as history

Example (illustrative, non-normative): a server enters Dish A, notices the mistake, removes it, and enters Dish B instead.

RF-One does **not** need to preserve the historical sequence of that error. After the Correction/Reconciliation Poller (§3) has processed the correction, RF-One's canonical operational data reflects the corrected state its own processes need — not a replay of the order the mistake happened to be made and fixed in.

**Clover remains the system of record for POS/transactional history.** RF-One retains the operational reality its own processes require, not a parallel historical ledger of every intermediate POS state — this is the concrete meaning of "RF-One does not replicate the full POS history" (§1).

---

## 9. Minimal useful metadata

Without fixing a schema here, it is useful for RF-One's canonical rows to be able to answer "how recent is this data":

- **`source_created_at`** — when the record was created on Clover.
- **`source_modified_at`** (or the existing `modified_at` naming already used on `Order`/`Payment`) — when the record was last modified on Clover, per §4's Modification Cursor.
- **`rfone_synced_at`**, or an equivalent freshness/status signal — when RF-One last confirmed this row against Clover.

**This precedent already partially exists**: `source_created_at`/`source_modified_at` are already present on several canonical tables (e.g. `Employee`, and others per `DATABASE_SCHEMA.md`), and `modified_at` already exists on `Order` and `Payment`. `SourceRecord.retrieved_at` and `IngestionRun.started_at`/`finished_at` today serve as the closest equivalent of an "RF-One last synced" signal, at the ingestion-run level rather than the individual-row level. Extending this metadata pattern consistently to every entity type the Correction/Reconciliation Poller must correct is a natural, minimal future step — **not decided, scheduled, or implemented by this document.**

**This metadata exists to answer "how fresh is this," never to build a complete event history.** It must not be read as an instruction to reconstruct a full change log per row.

---

## 10. Validation boundary

Four distinct concerns must not be collapsed into one:

```text
A. Ingestion
   → acquiring a Clover record into RF-One for the first time
   → owned by the Fast Live Extractor (§2) and Historical Backfill

B. Correction / Reconciliation
   → detecting and applying changes to already-ingested records
   → owned by the Correction/Reconciliation Poller (§3)

C. Operational freshness
   → "is this data current enough for Cognito to act on"
   → the eventual-consistency boundary of §5, consumed per §6

D. Financial consolidation
   → "is this Business Date settled enough for Tips to calculate/pay against"
   → the readiness boundary of §7
```

No confidence-scoring formula is introduced for any of these four. No medical or diagnostic concept is introduced. No new Attention Management logic is introduced — where Attention Management is referenced (§ Related documents), it is only the pre-existing capability, unchanged.

---

## 11. Canonical architecture

```text
Clover
  │
  ├──► Fast Live Extractor (~10-15 sec, configurable)
  │      │
  │      ▼
  │    Validation / Mapping
  │      │
  │      ▼
  │    RF-One Data Store  ─────────────►  Cognito / Operational Consumers
  │      ▲                                 (accepts eventual consistency, §5-§6)
  │      │
  └──► Correction / Reconciliation Poller (~60 sec, configurable)
         (corrects the same RF-One Data Store above — no second store)

RF-One Data Store
  │
  ▼
Reconciled Business Date  ──►  Tips Calculation  ──►  Tip Entitlements
                                                          │
                                                          ▼
                                                    Payment Cycle
                                                          │
                                                          ▼
                                                       Mercury
```

Both arrows into the RF-One Data Store are required. They are not two alternative designs for the same problem — the Fast Live Extractor cannot self-correct outside its own short window (§3), and the Correction/Reconciliation Poller alone cannot deliver near-real-time freshness (§2). Both are necessary; neither is sufficient alone.

---

## Non-assumptions

Do not assume:

```text
this document changes any software, schema, migration, or connector behavior
Live Sync and the Correction/Reconciliation Poller are alternative designs —
  both are required, per §14 of the originating decision and §3/§11 above
RF-One is intended to become a full historical replica of Clover's POS data
webhooks are introduced or required by this document
event sourcing, or a Clover event ledger, is introduced by this document
  (SourceRecord/Provider Mirror is unchanged in role — audit/reconciliation
  mirror only, never read back for business logic)
a confidence-scoring formula for freshness or correctness is defined here
any medical, diagnostic, or Attention Management concept is introduced here
the Modification Cursor (§4) is implemented, persisted, or scheduled by
  this document — it is an approved target shape, not a shipped mechanism
per-resource/table Live Cursor granularity (§2) is implemented — today's
  Live Cursor remains per-Location, as it already is in production code
the eventual consistency window of §5 is a defect to be minimized to zero —
  it is an intentional, accepted product boundary
```
