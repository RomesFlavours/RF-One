# SettlementPolicy — Structure and RF Gelati Example Configuration

**Version:** 1.0
**Status:** APPROVED DOMAIN DEFINITION
**Module:** Shared Domain / Intercompany Funding & Settlement
**Origin:** TASK — CREATE CROSS-DOMAIN: INTERCOMPANY FUNDING & SETTLEMENT

---

## Related documents

- [README.md](README.md) — Domain purpose, scope, and boundaries
- [INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md](INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md) — the concepts (Funding Balance, Settlement Balance, Funding Transfer, Payment/Receipt On Behalf, Intercompany Position, Settlement, Allocation) this Policy governs

---

## 1. Purpose

`SettlementPolicy` is the central, configurable policy object governing how a Corporate wants funding and settlement to behave. It is the single mechanism through which Intercompany Funding & Settlement stays a general Domain rather than an encoding of any one Corporate's current operating model.

**Every behavioral decision named in this document belongs to `SettlementPolicy`, never to the Domain's own hardcoded logic.** Where this document illustrates a decision using RF Gelati's current configuration (§5), that illustration is one example instance of a Policy, not the Domain's general rule.

---

## 2. General rule

Intercompany Funding & Settlement does not impose a universal centralized-finance model. Each Corporate configures its own `SettlementPolicy`. A `SettlementPolicy` may determine, among other things:

- whether funding is treated as prefunding;
- whether funding creates an immediate intercompany receivable/payable;
- whether balances may go negative;
- replenishment rules and thresholds;
- reserve/buffer percentage;
- payment eligibility;
- approval requirements;
- settlement frequency;
- whether settlement is automatic or manual;
- netting rules;
- allocation methods;
- service fees and markup;
- treatment of centralized purchasing;
- treatment of centralized receipts;
- intercompany advances;
- reimbursement behavior;
- whether Payment On Behalf consumes prefunding or creates a settlement position;
- whether a specific relation requires external validation or approval;
- correction/reversal behavior.

**Current Rome's Flavours/RF Gelati behavior is not the general rule** — it is documented in §5 strictly as one example configuration of the Policy structure defined below.

---

## 3. SettlementPolicy structure

`SettlementPolicy` is organized into the following conceptual sub-policies. They are documented here as sections of one Policy object, not as separate files or separate persisted entities — that composition decision is left open for whatever later implementation task actually builds this Domain in software.

**FundingPolicy** — governs Funding Transfers and Funding Balance behavior: whether funding is treated as prefunding at all, whether a Funding Balance may go negative, and what happens economically when it is consumed (see RF Gelati example, §5.C–E).

**ReplenishmentPolicy** — governs when and how a depleted Funding Balance is topped up: thresholds, triggers (manual request, automatic estimate, scheduled), and whether replenishment requires approval before execution (see §5.F).

**PaymentPolicy** — governs Payment On Behalf: eligibility (which payments a hub Legal Entity may execute on behalf of another), and whether such a payment consumes prefunding or instead creates a Settlement Balance (Intercompany Position).

**NettingPolicy** — governs whether and how multiple Intercompany Positions between the same Legal Entities are netted into a single settlement figure rather than settled individually.

**AllocationPolicy** — governs how a shared amount is attributed across beneficiary/responsible Legal Entities when no single entity is the sole beneficiary (Allocation, concept I).

**PurchasingPolicy** — governs the financial-consequence treatment of centralized purchasing: whether a Legal Entity that centrally purchases on behalf of others treats that as Payment On Behalf, creates a Settlement Balance, or applies some other configured consequence. This Policy never redefines the purchasing decision itself — that remains Purchasing's/Purchased's own scope (see [INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md](INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md) §6).

**FeeMarkupPolicy** — governs whether, and how, a hub Legal Entity applies a service fee or markup for the funding/payment services it provides to other Legal Entities.

**ReceiptPolicy** — governs the financial-consequence treatment of centralized receipts: how money received by one Legal Entity on behalf of another (Receipt On Behalf) is attributed and, where applicable, settled.

**SettlementSchedule** — governs settlement cadence: manual or automatic, and on what frequency (e.g. weekly, monthly, on-demand). See RF Gelati's current weekly cycle, §5.G.

None of these sub-policies is required to exist as a separate file, table, or object in any future implementation — this document defines them conceptually so the Domain model (§2 of [INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md](INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md)) has a complete, named vocabulary of the decisions a `SettlementPolicy` must be able to make.

---

## 4. Versioning and effective dating

`SettlementPolicy` must be versioned and effective-dated, per the Domain's event/history principle ([INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md](INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md) §8). A change to a Corporate's Policy must never retroactively alter how an already-recorded fact is interpreted — historical reconstruction relies on knowing which Policy version was in force when each fact was recorded.

---

## 5. Current RF Gelati configuration — EXAMPLE ONLY

This section documents the **current** Rome's Flavours configuration as **one instance** of a `SettlementPolicy`, for illustration. **RF Gelati is not a special system entity** — it is an ordinary Legal Entity acting as an operational hub under this configuration, and it may later be renamed RF Corporate without changing any Domain semantics. Nothing in §§1–4 above depends on this example; a different Corporate could configure an entirely different `SettlementPolicy` and remain fully supported by this Domain.

**A. Operational hub.** RF Gelati acts as an operational hub for the Rome's Flavours Corporate structure.

**B. Manual prefunding, pre-RF-One-operational.** WP, and later MD, manually transfer a fixed weekly retainer/prefund to RF Gelati while RF-One is not yet fully operational for this purpose.

**C. Funding model — prefunding attributed to the originating Legal Entity (`FundingPolicy`).** Example: WP transfers 10,000 to RF Gelati. RF-One represents this as *WP's Funding Balance at the hub = 10,000*. The cash may physically sit in a single Mercury account; economic attribution remains with WP throughout, per this Domain's general principle (§ README.md).

**D. Funding Balance can never go negative under this Policy (`FundingPolicy`).** Reason: operating income belongs to WP and MD, not to RF Gelati. Under the current configuration, RF Gelati must never implicitly finance the operating companies. A different Corporate's `FundingPolicy` could permit a negative balance; RF Gelati's current one deliberately does not.

**E. Payment On Behalf consumes Funding Balance, without creating a Settlement Balance (`PaymentPolicy`).** Example: WP Funding Balance = 10,000. RF Gelati pays 3,000 of WP's obligations on WP's behalf. WP Funding Balance becomes 7,000. **No automatic intercompany payable is created merely because prefunded money was consumed** — under this Policy, Payment On Behalf is a pure Funding Balance debit, not an event that creates an Intercompany Position.

**F. Future estimate-driven replenishment, initially requiring human approval (`ReplenishmentPolicy`).** Once RF-One is operational, it will estimate expected funding needs (e.g. expected Tips obligations) and may calculate a configurable reserve/markup percentage over the expected amount. Initially, the proposed funding transfer will require human approval before execution; the authorization model may later permit greater automation. This progression (manual approval today, more automation later) is itself a `ReplenishmentPolicy` configuration choice, not a Domain-level constraint.

**G. Weekly settlement cadence (`SettlementSchedule`).** The current settlement frequency is a weekly automatic reset/settlement cycle. This is represented via `SettlementSchedule` within `SettlementPolicy` — never hardcoded into the Domain itself; a different Corporate could configure daily, monthly, or purely on-demand settlement.

**H. Netting.** Netting behavior remains configurable through `NettingPolicy`; the current RF Gelati configuration does not require this document to fix a specific netting rule.

**I. Central purchasing.** The financial-consequence treatment of any future centralized purchasing remains configurable through `PurchasingPolicy`.

**J. Fees/markup.** Any service fee or markup remains configurable through `FeeMarkupPolicy`.

**K. Centralized receipts.** The financial-consequence treatment of any future centralized receipts remains configurable through `ReceiptPolicy`.

**L. Any other future intercompany relationship.** Remains Rule/`SettlementPolicy`-driven, not hardcoded — consistent with §1's core purpose for this document.

---

## 6. Compliance boundary reminder

RF-One executes the `SettlementPolicy` a Corporate configures; it does not certify that the configured structure is legally or fiscally compliant. See [README.md](README.md), "Accounting / tax / legal boundary," for the full statement — not restated here to avoid drift between the two documents.
