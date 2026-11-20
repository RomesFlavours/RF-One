# CLOVER_TIPS_DATA_PROBE_001 — Rome's Flavours Tip/Gratuity Data Structure

**Scope:** Read-only investigation only. No Clover data was created, updated, deleted, or voided. Only `GET` requests were issued, using the repository's existing read-only `clover_explorer.client.CloverClient` (a client that has no write methods at all — see `03 Software/Clover Data Explorer/clover_explorer/client.py`). No Tips module code was changed. No employee payout calculation was performed.

**Credentials used (not exposed):**
- Merchant ID: loaded from `CLOVER_MERCHANT_ID` (13 characters), masked here as `PYQ...V31`.
- API base URL: `https://api.clover.com` (production), from `clover_explorer.config.CLOVER_PRODUCTION_BASE_URL`.
- Token source: `CLOVER_API_TOKEN`, resolved from the process environment or a local `.env` file (`clover_explorer/config.py`'s existing, already-configured loader). The token value itself was never printed, logged, or written to any file by this investigation.

**Live sample queried today:** the 20 most recent `result=SUCCESS` payments (`GET /v3/merchants/{mId}/payments?expand=order,tender,employee,refunds,additionalCharges,cardTransaction&orderBy=createdTime DESC&limit=20`), plus their 20 corresponding orders (`GET /v3/merchants/{mId}/orders/{orderId}?expand=payments,employee,lineItems,refunds,payments.tender,payments.refunds`). To locate specific patterns task item 8 asks for (zero-tip, split-payment, gratuity line item) that did not appear in that 20-payment window, the live payments query was widened, still read-only, to the 300 most recent payments and their orders — nothing beyond `GET` was issued at any point. Where a pattern still did not appear live today (see Refund/Void below), this report explicitly says so and cites this repository's existing, already-verified full-history findings (`CLOVER_DATA_CAPABILITY_MATRIX.md`, `CLOVER_ATOMIC_DERIVED_FACTS.md`, `CLOVER_EXPORT_RECONCILIATION.md`) rather than fabricating a live example.

This investigation substantially reconfirms — with fresh, live, exact-ID-matched evidence — findings this repository had already established from prior Clover tasks. Nothing here overturns those findings; several are sharpened with a new, cleanly-reconciled live example (§7 below).

---

## 1. Clover Objects Involved

- **Payment** — the actual money movement; carries the voluntary tip.
- **Order** — the tab/ticket; carries line items, including the synthetic gratuity/service-charge line item; references its Payment(s).
- **LineItem** (nested under Order) — ordinary menu items, plus a **synthetic fee line item** (`isOrderFee: true`) that is how automatic gratuity/service charge is represented — see §3.
- **Tender** (nested under Payment) — the payment method (`Credit Card`, `Cash`, ...).
- **CardTransaction** (expandable on Payment) — card network/authorization detail and **cardholder name** — contains real customer PII; deliberately excluded from this report's examples and recommended out of scope for Tips ingestion entirely (§9).
- **Employee** (referenced from both Payment and Order) — see §5.
- **Refund** — a separate top-level resource, not a field on Payment or Order (see §8).
- **Device** — the terminal that processed the payment (referenced, not investigated further here — out of scope for tips).
- **`additionalCharges`** — requested per this task's instructions on the Payments expansion; **not observed on any of the 300 live-sampled payments, and not mentioned in any prior Clover task's findings for this merchant.** No distinct "additional charges" concept exists for this merchant beyond the Order-level gratuity line item (§3).

## 2. Authoritative Field for Voluntary Tip

**`Payment.tipAmount`** (integer, minor units/cents). Confirmed live:
- **Present and non-zero** for 16/20 payments in the initial sample, and 253/300 (net of the specific patterns pulled out) in the widened window — the ordinary tipped-card case.
- **Present and exactly `0`** for some card payments — a customer who was asked/offered a tip and declined, or whose payment device recorded no tip (15 examples found live in the widened 300-payment window; see Example B).
- **Entirely absent (key not present at all)** for Cash tenders in every case observed (4/20 in the initial sample) — Clover does not track a discretionary "tip" concept the same way for cash; this is a missing key, never a `0`, and must not be coerced to `0` on ingestion (this repository's ingestion code already gets this right — `application_service`/`export_payments.py`'s `cents_to_amount_str` leaves it blank rather than `0.00`).

No other field on Payment carries a tip-like concept.

## 3. Authoritative Field for Gratuity/Service Charge

**There is no dedicated field for this anywhere in the Clover object model for this merchant.** It is represented exclusively as a **synthetic Order line item**:

```
name: "Gratuity"
note: "Service Charge"
isOrderFee: true
isRevenue: false
percentage: <e.g. 180000 = 18.0000%>
price: <computed amount, minor units>
```

This line item:
- lives inside `Order.lineItems.elements[]`, never on Payment;
- is included in `Order.total` (it is a real charge the customer paid), and therefore in `Payment.amount` for the payment(s) that settled that order;
- is **structurally and semantically separate from `Payment.tipAmount`** — confirmed directly today (§7), not assumed.

Found live in 4/272 orders in the widened window (~1.5%), consistent with this repository's prior full-history finding of ~1.8% of all line items / ~12% of orders carrying this line item at some point in the merchant's history (`CLOVER_DATA_CAPABILITY_MATRIX.md` §N). A separate, configuration-level `order_types.fee` field also exists but was reconfirmed (again) as never having actually populated a real order for this merchant — a distinct, dormant concept, not investigated further here (out of this probe's scope).

## 4. Relationship: Order → Payment

- One Order has zero, one, or **more than one** Payment, via `Order.payments.elements[]` (confirmed live — see §6, split payment). The reverse reference, `Payment.order`, is always a single Order.
- **`Order.total` equals the sum of `Payment.amount` across that order's payments — it does NOT include tip.** Confirmed exactly in the split-payment example (§6: `4000 + 11017 = 15017` = `Order.total`) and in the single-payment gratuity example (§7: `Payment.amount 6723` = `Order.total 6723`, with `Payment.tipAmount` separately `0`).
- `Order.total` **does** include the synthetic Gratuity/Service-Charge line item's price, since that line item is a real order charge, unlike a voluntary tip.
- `Order.state` was `locked` and `Order.paymentState` was `PAID` for every completed transaction sampled (all 20/20 and all in the widened window's SUCCESS-linked orders) — consistent with "completed."

## 5. Employee: Order vs Payment

Both Order and Payment carry an `employee` reference (by id). Two asymmetries confirmed live today:
1. **Expansion depth differs by parent resource.** `Order.employee` (via `expand=employee`) returns a fuller object — id, `name`, `nickname`, `customId`, `role` — while `Payment.employee` (via the identical `expand=employee` parameter) returns **only `{id: ...}`**, no name. A full employee name/customId for the Payment-side employee requires a separate `/employees` lookup keyed by that id — exactly the pattern this repository's existing `export_payments.py`/`export_orders.py` already implement (`raw.employee_fields(...)`), reconfirmed correct.
2. **Value equality:** in every one of the 20 sampled completed transactions, `Payment.employee.id` equaled `Order.employee.id` — no divergence observed live today. This repository's prior reconciliation work tracks them as two independently-sourced columns (implying they *can* differ, e.g. a different staff member finalizing a payment than opened the order), but no such divergent case was found in today's sample; this remains theoretical for this merchant based on current evidence.

## 6. Split-Payment Behavior (confirmed real example)

One real order in the widened sample had **two** payments:

| | Payment 1 | Payment 2 |
|---|---|---|
| Amount | 40.00 | 110.17 |
| Tip | 10.00 | 19.83 |
| Tender | Credit Card | Credit Card |
| Result | SUCCESS | SUCCESS |

`Order.total` = **150.17** = `40.00 + 110.17` exactly (tips excluded, confirming §4). Each payment carries its **own independent `tipAmount`** — a split-check tip is not a single order-level amount divided between payments; it is genuinely two separate discretionary tips, one per payment, and RF-One Tips ingestion must sum `tipAmount` **per payment**, then attribute per the employee on each individual payment (which, per §5, is not guaranteed to be the same employee on every payment of a split order, though it was in this specific example — both payments shared the same order-level employee).

19/272 orders (~7%) in the widened window had more than one payment.

## 7. Is the "Gratuity" a Tip, a Service Charge, or a Reporting Projection? — Directly Verified

**Verified conclusively against one real, exact, matching Order + Payment pair — not assumed.**

Masked example (Order `T3SR...K5DW`, Payment `37A8...HX9W`):

| Line item | Amount |
|---|---|
| Spritz | 16.00 |
| Sparkling Water 500ml | 8.00 |
| Large Sicilia Pizza | 30.00 |
| **Gratuity** (`isOrderFee: true`, `note: "Service Charge"`, `percentage: 18.0000%`) | **9.72** |
| Tax (6.5%, on the 54.00 food subtotal) | 3.51 |
| **Order total** | **67.23** |

| | |
|---|---|
| `Payment.amount` | 67.23 (matches Order total exactly) |
| `Payment.tipAmount` | **0** |

**Conclusion:** the "gratuity" here is **an automatic Order-level service charge** (18% of the food subtotal, computed and applied to the order as a line item), and it is **completely independent of `Payment.tipAmount`**, which was explicitly `0` in this exact example — the customer was not asked for (or did not add) any further discretionary tip on top of the automatic 18% already collected via the order. It is **not** an export/reporting projection invented by Clover's dashboard: it is a genuine, persisted `LineItem` row on the real Order, present in the raw API object itself (not only in a CSV/dashboard export).

This directly reconfirms, with a fresh live example, this repository's prior finding (`CLOVER_EXPORT_RECONCILIATION.md` §5.3): **Tip and Service Charge are two separate amounts that must both be read, from two different objects, to get the true total gratuity a customer paid.** A calculation reading only `Payment.tipAmount` would report `0` for this transaction despite the customer having paid a real 9.72 mandatory gratuity.

## 8. Refund/Void Implications

No refunded or voided payment existed in today's 300-payment live window (0/300) — this cannot be freshly re-verified today. Citing this repository's existing, already exact-ID-matched full-history findings (`CLOVER_DATA_CAPABILITY_MATRIX.md` §R, `CLOVER_ATOMIC_DERIVED_FACTS.md` §6):

- Refund is a **separate top-level Clover resource** (`/v3/merchants/{mId}/refunds`), not a field on Payment or Order by default.
- Requesting `expand=refunds` on a Payment (as this probe did) **does** surface an addressable `refunds.elements[]` array on the Payment object (confirmed structurally today — empty for all 300 sampled payments, since none were refunded). Whether that array actually populates correctly for a genuine refund was **not independently re-confirmed today** (no live refund example existed to test); the prior report's finding (Refund only discoverable from the Refund resource's own side, carrying a `payment` back-reference) predates this probe's specific `expand=refunds` check and is the more authoritative, cross-checked source — flagged as a residual uncertainty below.
- Critically: **`Payment.result`, `Order.paymentState`, and `LineItem.refunded` do NOT change when a refund occurs** — confirmed for both of the two known full-history refund examples, by exact ID. A refunded payment still shows `result: SUCCESS`.
- `Refund.voided` exists as a field but has **never been observed `true`** anywhere in this merchant's accessible history — whether/how a genuinely voided (as opposed to refunded) transaction is represented is **not confirmed**.
- **Implication for RF-One Tips:** if a payment's tip/gratuity is ever ingested into payroll, the ingestion must separately check the Refund resource (by Payment id) to know whether that payment was later refunded — the Payment object's own fields will not reveal it.

## 9. Timing: Order Creation vs Payment/Tip Finalization

Confirmed live, and not previously documented in `CLOVER_INGESTION.md`/`CLOVER_INGESTION_RECONCILIATION.md`:

- **`Order.createdTime` consistently precedes `Payment.createdTime`** by roughly 45 minutes to 2+ hours across the sample — consistent with an order being opened when a table/tab starts and paid later at checkout, as expected.
- **`Payment.modifiedTime` can be hours later than `Payment.createdTime`.** In the initial sample, several unrelated payments (different `createdTime`s, spread over ~1.5 hours) all shared the **same** later `modifiedTime`, down to the second — strongly suggesting a batch process (end-of-day settlement, or a bulk post-hoc tip-adjustment/reconciliation step) touches multiple payments' `modifiedTime` at once, well after the payment was first created.
- Cash payments (no `tipAmount` key) had `modifiedTime == createdTime` exactly — no later modification observed, consistent with cash tips (if any) being decided at the moment of payment rather than adjusted afterward.
- **Implication for RF-One Tips:** a payment's `tipAmount` read once shortly after `createdTime` may not yet reflect its final value for card payments — a later re-read (keyed by `modifiedTime`, or a delayed/end-of-day ingestion pass) may be necessary to capture tip amounts finalized after initial authorization. This is a genuine open question (§11), not something this probe's scope allows resolving further (no Tips-module design work was performed).

## 10. Anonymized Real Examples (5)

All IDs masked (`first4...last4`). No customer name, card number, or other cardholder PII is included anywhere below or elsewhere in this report, even though it is present in the raw Clover `cardTransaction` expansion this probe queried.

**A — Normal tipped credit-card transaction.** Payment `7MRK...VHW4` / Order `4BCG...SQWT`: amount 86.27, tip 15.53, tax 5.27, tender Credit Card, result SUCCESS, single payment, `Payment.employee` == `Order.employee`.

**B — Zero-tip credit-card transaction.** Payment `ZQPC...HAS2` / Order `S28Q...23YA`: amount 132.06, `tipAmount` **present and `0`** (not absent), tax 8.06, tender Credit Card, result SUCCESS.

**C — Cash payment, no tip concept tracked.** Payment `XFBA...1FBP` / Order `SR6J...1ZHA`: amount 109.70, `tipAmount` key **absent entirely**, tax 6.70, tender Cash, result SUCCESS, `createdTime == modifiedTime`.

**D — Split-payment order.** Order `JF55...0CMT`, total 150.17: Payment `0KG6...RTF6` (40.00 + 10.00 tip) and Payment `QTNY...74ZA` (110.17 + 19.83 tip), both Credit Card, both SUCCESS.

**E — Automatic gratuity/service charge, separate from tip.** Order `T3SR...K5DW` / Payment `37A8...HX9W`: order total 67.23 (food 54.00 + 18% Gratuity line item 9.72 + tax 3.51), `Payment.amount` 67.23, `Payment.tipAmount` **0** — full detail in §7.

## 11. Exact Fields RF-One Tips Should Ingest

Per payment (from `GET .../payments?expand=order,tender,employee,refunds`):
- `id`, `order.id`, `employee.id`, `amount`, `tipAmount` (preserve missing-vs-zero distinction — never default to `0`), `taxAmount`, `createdTime`, `modifiedTime`, `result`, `tender.label`.

Per order (from `GET .../orders/{id}?expand=employee,lineItems,payments`):
- `id`, `employee.id`, `total`, `createdTime`, `modifiedTime`, `state`, `paymentState`, `payments.elements[].id` (for split-payment attribution), and every `lineItems.elements[]` entry where `isOrderFee: true` (the Gratuity/Service-Charge amount — read `price`, not `percentage`, as the authoritative charged amount).

Per refund (separate call, keyed by payment id, from `GET .../refunds`):
- `payment.id`, `amount`, `tipAmount`, `voided`, `status` — needed to detect that an already-ingested payment's tip was later refunded, since Payment's own fields never reflect this.

A full employee name/customId requires a separate `/employees` lookup by id (§5) — do not rely on the Payment-side `employee` expansion for a display name.

## 12. Uncertainties Still Requiring Investigation

1. **Whether `expand=refunds` on Payment reliably populates for a genuine refund** — structurally present today (always empty), but no live refund existed to test it; the Refund-resource-side lookup remains the only cross-checked-correct method from prior work.
2. **`Refund.voided: true` behavior is entirely unconfirmed** — no such example has ever been observed for this merchant; how a true void (vs. a refund) is represented is unknown.
3. **The exact trigger/cadence of the batch `Payment.modifiedTime` update observed in §9** — is it end-of-day settlement, manual tip adjustment, or something else? Not determinable from the API alone within this probe's read-only, non-designing scope.
4. **Whether `Payment.employee` can ever differ from `Order.employee`** for this merchant — theoretically implied by this repository's prior reconciliation design (separate columns) but never observed in either today's or prior samples.
5. **Partial refunds** — every previously-known refund example is a full-amount refund; partial-refund structure is unconfirmed (carried over from prior work, not newly investigated here).
6. **The dormant `order_types.fee` configuration field** — never observed to produce an actual order charge for this merchant; unclear if it is unused, misconfigured, or reserved for a different order-type/channel not currently active.

No employee payout calculation, Tips-module change, or Clover write operation was performed by this investigation.
