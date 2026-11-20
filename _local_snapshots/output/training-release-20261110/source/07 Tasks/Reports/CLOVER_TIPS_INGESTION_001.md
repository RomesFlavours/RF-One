# CLOVER_TIPS_INGESTION_001 — Live Clover Import for the Tips Module (Source Facts Layer)

**Scope:** the Source Facts / Clover ingestion layer required by `01 Domains/Business Domain/Restaurant/Functional Specifications/TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md`, using the field-level findings established in `07 Tasks/Reports/CLOVER_TIPS_DATA_PROBE_001.md`. No Tip Distribution Rules, no Host/Bartender tip-out calculation, no Zelle, no payroll, and no Tips-module redesign were implemented. No broad integrity/architecture review was performed.

---

## 1. Files Changed

**Created:**
- `03 Software/RF-One Data Store/migrations/versions/f4c9a2e7b1d3_add_order_fee_note_raw.py` — one additive, nullable-column migration.
- `03 Software/RF-One Data Store/rfone_data_store/tips/clover_import_service.py` — the live, windowed import service and the `get_order_settlement_time()` helper.
- `03 Software/RF-One Data Store/rfone_data_store/tips_clover_import_validation.py` — the automated test suite.
- `03 Software/RF-One Data Store/test_tips_clover_import.py` — its disposable-database runner.
- `03 Software/Tips/app.py`, `03 Software/Tips/templates/base.html`, `03 Software/Tips/templates/home.html`, `03 Software/Tips/requirements.txt` — the minimal UI.
- `07 Tasks/Reports/CLOVER_TIPS_DATA_PROBE_001.md` (prior task; listed only because it remained uncommitted).

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/models.py` — added `OrderFee.note_raw` (nullable `String(255)`); the only schema change across this whole task.
- `03 Software/RF-One Data Store/rfone_data_store/ingestion/clover/mapping.py` — `map_order_fee()` also returns `note_raw` (the verbatim Clover `note` string), reused unchanged by both this importer and the existing full-history `ingest_clover.py` pipeline.

**Deliberately NOT created:** a second Clover ingestion system, any Tip Distribution Rule/Rate/Calculation-Base model, any allocation/payout code, any Zelle/ACH integration.

---

## 2. Inspection Performed First (task §1)

Read in full before writing anything: `CLOVER_TIPS_DATA_PROBE_001.md`, `TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md`, the existing `rfone_data_store/tips/` package, and the existing `rfone_data_store/ingestion/clover/` package (`mapping.py`, `ingest.py`, `reader.py`, `enrichment.py`, `reconciliation.py`) plus the Clover Data Explorer's read-only client.

**Reused, not rebuilt:**
- The canonical schema (`Payment`, `PaymentTip` — already distinguishing absent/zero/positive tip — `Order`, `OrderFee`, `Refund`, `Employee`, `Tender`, `Device`, `Shift`, `SourceSystem`, `Location`, `IngestionRun`) already existed from earlier Clover tasks and already held Rome's Flavours' full history.
- The pure mapping functions (`map_payment`, `map_payment_tip`, `map_order`, `map_order_fee`, `map_refund`, `map_employee`, `map_tender`, `map_device`, `map_shift`) — reused verbatim.
- The generic idempotent `upsert()` helper — reused directly for Refunds and Shifts.
- The read-only `CloverClient`/`paginate()` primitives and the `Clover Data Explorer` reuse boundary `ingestion/clover/enrichment.py` already established (same `sys.path` bootstrap, same "no Explorer business logic" rule).

**What is new:** the *fetch strategy* — a small, live, windowed read directly against the Clover production API for a requested period, since `ingest_clover.py`'s existing pipeline only knows how to replay a previously-collected, locally-cached full-history export. `tips/clover_import_service.py` writes to the SAME canonical tables via the SAME unique-constraint-keyed upsert convention, so it can never conflict or duplicate rows against the full pipeline, in either run order. Deliberately still not ingested here (left to the full pipeline; not tip/gratuity source facts): OrderItem/menu/catalog detail, per-item tax, discounts, source roles.

---

## 3. Migration / Database Changes

One migration, `f4c9a2e7b1d3` (`down_revision = e1a4c8f2b6d9`, now head): adds nullable `order_fees.note_raw` — the verbatim Clover `note` string a gratuity/service-charge line item carried, alongside the existing derived `fee_type`. Purely additive; every existing row gets `note_raw = NULL`; nothing historical was rewritten.

**No other schema change was made or needed** — Shift ingestion, Settlement Time, and every other new capability in this task's second pass reuse columns/tables that already existed.

---

## 4. Clover Endpoints Used

All `GET` only, via the read-only `CloverClient` (structurally incapable of any write):

- `GET /v3/merchants/{mId}/payments?expand=order,tender,employee&filter=createdTime>=...&filter=createdTime<=...&orderBy=createdTime ASC` — the period's Payments.
- `GET /v3/merchants/{mId}/orders/{orderId}?expand=employee,lineItems` — one call per distinct Order referenced by those Payments.
- `GET /v3/merchants/{mId}/employees`, `/tenders`, `/devices` — small, largely-static catalogs, fetched in full each run.
- `GET /v3/merchants/{mId}/refunds?filter=createdTime>=...&filter=createdTime<=...` — the period's Refunds.
- `GET /v3/merchants/{mId}/shifts` — **new this pass**. Confirmed empirically, live and read-only, that this endpoint **rejects** both a `filter=inTime>=...` time-range query and `orderBy=inTime DESC` with HTTP 400 (unlike Payments/Refunds) — Clover does not support server-side time filtering for Shifts. The importer therefore fetches the full collection via plain pagination and filters client-side to Shifts whose clock-in falls within the requested period before upserting.

**Never requested:** `expand=cardTransaction` or any customer/cardholder field. An automated test asserts no call in the whole suite ever requests it.

---

## 5. Resulting Source-Data Model

Per period, `import_clover_period()`:

1. Resolves the Restaurant's Clover-sourced `Location` (does not create Merchant/Location — `ingest_clover.py`'s onboarding concern).
2. Fetches Payments for the window, their Orders, Employees/Tenders/Devices in full, the full Shift collection (filtered client-side to the window), and Refunds for the window.
3. Upserts, in order: Employees/Tenders/Devices → Orders → qualifying fee line items (`OrderFee`) → Payments → `PaymentTip` → Shifts → employee-mismatch detection → Refunds.
4. Records one `IngestionRun` row per invocation (`source_window_start/end`, a `TIPS_LIVE_IMPORT`-prefixed `notes` summary).

`Order → Payments` (spec §2's "Source Facts" list, including split-payment Orders) is the schema's own pre-existing `Payment.order_id` FK/relationship — every ingested Payment already points at its Order; nothing new was needed to represent it.

---

## 6. Voluntary Tip Handling

Unchanged from the probe's rule: `Payment.tipAmount`, mapped via `mapping.map_payment_tip()`. Three states preserved distinctly — positive amount; explicit `0` (a real `PaymentTip` row, `source_present=True`); entirely absent (no `PaymentTip` row at all, never coerced to `0`). A re-import refreshes an existing tip from Clover's current value (verified: a test changes 1000→1500 between two import calls and asserts the stored value updates). If a *previously-present* tip is later found *absent* on the same Payment, the existing row is left unchanged and an anomaly is logged for review, rather than deleted — never observed in the probe's data, treated as a likely transient issue rather than destroyed confirmed data.

---

## 7. Automatic Gratuity / Service-Charge Handling

`Order.lineItems.elements[]` entries with `isOrderFee: true`, stored as `OrderFee` rows, keyed by `(order_id, source_line_item_id)`. The charged amount is read verbatim from `lineItem.price` — never derived from `percentage`. Classification remains `fee_type = "SERVICE_CHARGE"` (Clover's own `note` for this merchant has only ever been `"Service Charge"`); the spec's "AUTOMATIC_GRATUITY" name is documented as a synonym for this same real-world value, not a second, unobserved classification. `note_raw` (new column) preserves the exact source text regardless.

**Counted once per Order, not once per Payment (spec §3):** `_ingest_fee_line_items()` is called exactly once per Order — from the Order-ingestion loop, never from the per-Payment loop — so a gratuity line item is written once and summed once in the import summary regardless of how many Payments settle that Order. Verified directly: a synthetic Order with 3 Payments (2 successful, 1 failed) and one gratuity line item ends the run with exactly one `OrderFee` row and the summary's `automatic_gratuity_count`/`_total_minor` reflecting it exactly once.

Never merged into `PaymentTip` — both facts are written independently; an Order can (and, per the probe's own real example, typically does) show `Payment.tipAmount = 0` alongside a real automatic gratuity.

---

## 8. Order/Payment Relationship & "Order is the Business Unit" (task §3, spec §3/§4)

- `Order.employee` is ingested and preserved as the **future authoritative tip owner** (spec §4) — no ownership decision or allocation is made by this task; the field is simply carried through from `map_order()`'s existing `source_employee_id`/`employee_id`.
- `Payment.employee` is preserved **independently**, on every Payment, for audit/anomaly detection — it never overwrites or is overwritten by `Order.employee`.
- Split payments remain linked to one Order via the pre-existing `Payment.order_id` FK; each Payment keeps its own independent `tipAmount`. Verified with a real synthetic 3-Payment split Order (§7 above) plus the original 2-Payment split-order test from this task's first pass.
- `ImportSummary.split_payment_orders_count` counts Orders with more than one ingested Payment, regardless of Payment result.

---

## 9. Employee Handling

`Employee` is resolved via `GET /employees` (full catalog, small, fetched every run) and upserted via the unchanged `map_employee()`. `Order.employee`/`Payment.employee` are both stored (task §8/spec §4):

- **No automatic ownership change** occurs when they differ.
- Every discrepancy is recorded in `ImportSummary.employee_mismatches` (both Clover source ids, on both sides) for operator review, recomputed fresh each run over the Orders that run touched — not a durable, persisted flag surviving across unrelated future runs.

`ImportSummary.employees_resolved` reports the count of distinct Employees resolved (upserted) in the run.

---

## 10. Settlement-Time Handling (task §7, spec §5) — new this pass

`get_order_settlement_time(session, order_id)` — a pure, on-demand query (`MAX(Payment.created_at) WHERE Payment.order_id = ... AND Payment.result = 'SUCCESS'`) — implements the spec's exact definition: **the timestamp of the last successful Payment that completes the Order**, never the moment a tip was later entered/adjusted (`Payment.modified_at` is never consulted here), and never `Order.createdTime`/`modifiedTime`.

**Deliberately not a stored/cached column.** It is always exactly reproducible from already-ingested Payment rows, so it can never drift and needs no "recompute when a late tip changes" workflow — directly satisfying this task's explicit "do not create a pending-tip/finalization workflow." The function is exported from `tips/clover_import_service.py` for the future Tip Distribution Engine to call directly rather than reimplementing the rule, and is used today by the Tips UI to display each imported Order's Settlement Time.

Verified with a synthetic Order carrying 3 Payments where the chronologically **latest** Payment is a **FAILED** one: Settlement Time correctly resolves to the earlier of the two successful Payments' timestamps, ignoring the later failed attempt entirely.

---

## 11. Clock-In / Clock-Out Handling (task §9, spec §2/§12) — new this pass

Investigated and confirmed: Clover's existing `/v3/merchants/{mId}/shifts` endpoint (already read by `ingest_clover.py`'s full pipeline via `mapping.map_shift()`/the `Shift` model — nothing new needed there) is the source of clock-in/clock-out facts. It does **not** support server-side date filtering (confirmed by a live, read-only 400 response to both a `filter` and an `orderBy` attempt) — the importer fetches the full collection and filters client-side to Shifts whose `inTime` falls within the requested period before upserting, so a weekly run does not repeatedly rewrite an ever-growing unrelated history.

Persisted per Shift: Clover employee id (resolved to canonical `Employee.id`), clock-in, clock-out, source shift id, plus the pre-existing override-employee/override-time fields `map_shift()` already carried. `Shift.location_id` is left `NULL`, exactly as the full pipeline already does — Clover's Shift object carries no location field for this merchant, so none is fabricated.

**No eligibility or distribution logic reads these rows** — they are made available as source facts only, per this task's own explicit "do not yet use this to distribute tips." A future ACTIVE_AT_SETTLEMENT eligibility check (spec §12) would query `Shift` by `employee_id`/`clock_in`/`clock_out` against an Order's Settlement Time — not implemented here.

---

## 12. Refunds (task §10, spec §18)

Ingested exclusively from the dedicated `/refunds` resource; `Payment.result == "SUCCESS"` is never treated as proof a payment was never refunded (the probe's own confirmed finding). Persisted: Clover refund id, payment id (when resolvable within the run), order id, amount, tax amount, tip amount, status, `voided`, employee id, created time.

**A refund never automatically reverses or modifies a tip** — verified directly: after ingesting a refund fact for a payment, that payment's own `PaymentTip.amount` is asserted unchanged. This is structural, not merely tested-and-hoped: `_ingest_refund()` writes only to the `Refund` table and never touches `Payment`/`PaymentTip` at all.

---

## 13. Idempotency / Update Behavior

Every upsert is keyed by the existing `UniqueConstraint(source_system_id, source_*_id)` on each table. Verified directly: after two consecutive imports of the identical period (including the Shift added this pass), every entity's row count for every synthetic external id is still exactly 1 — Payments, Orders, and the Shift alike. Re-importing refreshes every mapped column on every existing row from Clover's current values (Payment/Order/PaymentTip/Employee/Tender/Device/Shift) rather than treating the first observation as final — directly tested via a tip amount changed between two import calls in the same test run.

---

## 14. Money

All monetary fields (`Payment.amount`/`.tax_amount_source`, `PaymentTip.amount`, `OrderFee.amount`, `Order.total`, `Refund.amount`/`.tax_amount`/`.tip_amount`) are `Integer` columns storing minor units (cents) throughout the ingestion path — no floating-point arithmetic is performed on any monetary value anywhere in `clover_import_service.py`. (The Tips UI divides by 100 only for on-screen `%.2f` display formatting — a presentation concern, not a stored or calculated figure.)

---

## 15. Clover Safety

Read-only throughout: only `CloverClient.get()` is ever called (a client with no write methods at all, by construction). No API token, cardholder name, card number, or `cardTransaction` field is ever requested, logged, or stored — an automated test asserts no call in the suite ever requests the `cardTransaction` expansion. The existing, already-configured `CLOVER_MERCHANT_ID`/`CLOVER_API_TOKEN` mechanism is reused unchanged.

---

## 16. UI (task §12)

`03 Software/Tips/app.py` + `home.html` — From/Through date inputs, an "Import from Clover" button, and:

- An **Import Summary** card with every count task §13 lists (payments/orders imported+updated, voluntary tip count/total, automatic gratuity count/total, split-payment orders, zero-tip and missing-tip counts, employees resolved, shifts imported, refunds found, employee mismatches with detail rows, errors/anomalies).
- An **Imported Orders** table (new this pass, per §3's "Order is the business unit") — Order id, Order employee, total, Payment count (flagged when split), gratuity total, **Settlement Time**, state, payment state.
- An **Imported Payments** audit table — explicitly labeled as an audit view, showing `Payment.employee` (never used for tip ownership).
- An **Imported Shifts** table (new this pass) — employee id, clock-in, clock-out, source shift id, explicitly labeled "not yet used for any eligibility or distribution decision."
- A "Recent Clover Tips import runs" table reading the last 5 `IngestionRun` rows this importer created.

Database: unchanged from this task's first pass — this app uses RF-One's shared operational `rfone.db` by default (like `calculate_tips.py`), not an isolated sandbox. **No live production run was performed as part of building this feature** — `data/rfone.db`'s file timestamp was confirmed unchanged (Aug 31) throughout the entirety of this task, across both passes; every test and smoke-check used a disposable database and a fake in-memory Clover client.

---

## 17. Tests / Results

`rfone_data_store/tips_clover_import_validation.py` + `test_tips_clover_import.py`, run against a disposable SQLite database, never contacting Clover production (`FakeCloverClient`, an in-memory stand-in returning only synthetic, hand-built dicts). **38/38 checks pass**, covering every item task §16 lists:

| Area | Result |
|---|---|
| Positive voluntary tip | ✅ |
| Zero voluntary tip (present, not absent) | ✅ |
| Absent tipAmount remains NULL (no row) | ✅ |
| Gratuity distinct from voluntary tip | ✅ |
| **Gratuity counted only once per Order** (3-Payment split Order, 1 OrderFee row) | ✅ (new) |
| Split payment structure (2- and 3-Payment Orders) | ✅ |
| Order.employee preserved as owner source fact | ✅ |
| Payment.employee preserved independently | ✅ |
| Employee mismatch detection | ✅ |
| **Settlement Time from final SUCCESSFUL Payment**, ignoring a later FAILED one | ✅ (new) |
| Idempotent import (no duplicate rows, including Shift) | ✅ |
| Source update on re-import (tip 1000→1500) | ✅ |
| **Clock-in/clock-out ingestion**, period-filtered client-side | ✅ (new) |
| **Refund ingestion without automatic tip reversal** (explicit before/after assertion) | ✅ (new, explicit) |
| Duplicate external IDs prevented | ✅ |
| No `cardTransaction` expansion ever requested | ✅ |

**Existing suites re-run** (task §17 — only where touched shared code required it):

| Suite | Result |
|---|---|
| `test_tips_engine.py` (existing Tips calculation engine — untouched logic) | SUCCESS — 54/54 |
| `test_tips_clover_import.py` (new) | SUCCESS — 38/38 |

`models.py`/`ingestion/clover/mapping.py` were touched only in this task's first pass; at that time the broader suites (`test_selection_engine.py`, Organization, Payroll, Restaurant Profile, Sales, Purchasing — all previously reported SUCCESS) were re-run and passed. This second pass touched no shared schema/mapping code beyond what those runs already covered, so per task §17's "only run other RF-One suites if touched shared code genuinely requires them," they were not re-run again. Migration `f4c9a2e7b1d3` applies cleanly to head (confirmed: single Alembic head, `f4c9a2e7b1d3`).

---

## 18. Remaining Blockers Before Tip Distribution Engine Implementation

Explicit, not hidden:

1. **No Distribution Rule, Rate, Calculation Base, or Rule Version model exists yet** — spec §7-§9/§16 define an entirely new configuration surface (Source Role, Recipient Role, Calculation Base, Rate, effective-dated Rule Versions) that this task does not create.
2. **No eligibility engine exists.** `Shift` facts are ingested but nothing yet answers spec §12's "was employee X clocked-in at timestamp Y" as a queryable eligibility check against a given Order's Settlement Time.
3. **No Distribution Method (`EQUAL`/`HOURS_PROPORTIONAL`/`WEIGHTED_HOURS`) or rounding/reconciliation logic exists** (spec §13/§17) — the future engine will need integer-cent, deterministic-remainder splitting, not yet implemented anywhere.
4. **No Distribution Period / OPEN→CALCULATED→REVIEWED→APPROVED/LOCKED workflow exists** (spec §15/§20).
5. **No Manual Adjustment model exists** (spec §19).
6. **No Explainability/reconstruction view exists** (spec §21) — today's Import Summary shows source-fact totals only, not a per-employee Gross/Outbound/Inbound/Adjustment/Final breakdown.
7. **Business-date / operating-day-cutoff alignment is not applied** to the From/Through date UI inputs — plain calendar-day boundaries are used; `Location.operating_day_cutoff_time` is not consulted.
8. **Employee mismatches and the present→absent-tip anomaly are surfaced per run, not durably tracked** across runs until resolved.
9. **Partial refunds remain unconfirmed** (carried over from the probe report).

No unrelated Domain, migration rewrite, or Clover write occurred. Nothing was committed or pushed.
