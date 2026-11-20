# Tip

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_001

---

## Definition

A **Tip** is an observable economic fact: an amount a guest voluntarily added to a `Payment`, as recorded by the POS at the time of that Payment.

```text
Order
└── Payment
    └── Tip
```

The canonical Tip fact is attached to the **Payment**, never to the Order, never to a table, never to an Employee directly. This mirrors the existing canonical model — RF-One does not introduce a second Tip source table alongside `PaymentTip` (`03 Software/RF-One Data Store/DATABASE_SCHEMA.md` §10); `PaymentTip` **is** the Tip, and this Domain never duplicates it.

---

## Why Payment, not Order

An Order may have multiple Payments (split checks, partial payments). Each Payment may independently carry its own Tip. Aggregating Tips to the Order level before preserving Payment-level atomicity would destroy information a real restaurant genuinely needs (e.g. two guests on one Order tipping differently on their own Payments) — so RF-One never does this. Every Tip calculation operates Payment-by-Payment; totals at the Order or period level are always a sum computed afterward, never a stored aggregate that replaces the atomic facts.

---

## Temporal anchor

A Tip does not carry its own timestamp. Its temporal anchor is always the parent Payment's own canonical timestamp (`Payment.created_at` — the payment's source timestamp). RF-One never introduces a second, Tip-specific timestamp — doing so would create two competing "when did this happen" answers for the same economic event, and post-hoc calculation requires exactly one unambiguous anchor.

This means: **the time a server enters or adjusts a Tip is irrelevant to eligibility.** Only the Payment's own timestamp matters when determining who was present, assigned, or otherwise eligible for a share of that Tip.

---

## Missing vs. recorded zero

A Tip may be:

- **absent** — the source never reported a Tip field for this Payment at all (no `PaymentTip` row exists);
- **recorded as zero** — the source explicitly reported a Tip field with value `0` (a `PaymentTip` row exists, `amount = 0`, `source_present = true`).

These are different facts, and RF-One never conflates them. A missing Tip is not a zero Tip; a Tip calculation correctly processes zero-amount Tips (producing zero-amount allocations) while never even considering a Payment with no Tip row at all.

---

## Observable Tips only

RF-One may allocate only Tip value that exists as an observable source fact.

Example: a guest hands a server $120 cash against a $100 check; the server records only $100 through the POS and keeps the difference personally. RF-One has no way to know the $20 exists — the POS records no such Tip. This is not:

```text
a zero Tip
an inferable Tip
an estimate RF-One should approximate
```

It is simply outside what RF-One can ever automatically allocate, unless a future, separately trusted source explicitly records it. RF-One never estimates, imputes, or invents an unobserved cash Tip.

---

## Tip ≠ Service Charge

A Clover `Gratuity` or another order-level Service Charge fee (`order_fees`, `fee_type = SERVICE_CHARGE`) is a **different economic fact** from a recorded `PaymentTip`. This Domain's Tip calculation is based exclusively on recorded Payment Tips; a Service Charge is never merged into, derived into, or treated as a Tip. Service Charge distribution is explicitly out of scope for this Domain's Tip calculation (a possible, separate future capability).

---

## Refunds and corrections

A Refund against a Payment does not automatically mean the Payment's Tip was reversed. RF-One only treats a Tip as affected by a Refund when the source data provides explicit evidence of that (e.g. a `Refund.tip_amount` value) — never by assumption. Where the evidence is absent or ambiguous, RF-One surfaces this for human review rather than silently guessing either way. See `Tip Allocation.md` for how calculation runs remain reproducible/auditable so a later correction never silently erases a prior result.
