# Intercompany Funding & Settlement — Domain Model Specification V1

**Version:** 1.0
**Status:** APPROVED DOMAIN DEFINITION
**Module:** Shared Domain / Intercompany Funding & Settlement
**Origin:** TASK — CREATE CROSS-DOMAIN: INTERCOMPANY FUNDING & SETTLEMENT

---

## Related documents

- [README.md](README.md) — Domain purpose, scope, boundaries, and the Cross-Domain-not-Administration architectural principle
- [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) — the `SettlementPolicy` structure this document's concepts are governed by, and the current RF Gelati configuration documented as one example instance
- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4 — Shared Domains / Business Domain taxonomy
- [../Personnel Management/Compensation/README.md](../Personnel%20Management/Compensation/README.md) — the existing `Legal Entity` concept, referenced not redefined
- [../Administration/README.md](../Administration/README.md), [../Administration/Bank Reconciliation/README.md](../Administration/Bank%20Reconciliation/README.md) — the accounting/reconciliation boundary
- [../Purchased/README.md](../Purchased/README.md) — the purchase-fact boundary
- [../../Business Domain/Restaurant/Tips/README.md](../../Business%20Domain/Restaurant/Tips/README.md) — the Tips boundary

---

## 1. Purpose

This document defines the conceptual entities, boundaries, and required economic dimensions of the Intercompany Funding & Settlement Domain. It is a **conceptual model only** — it defines no database schema, no API, and no software behavior. See [README.md](README.md) for the Domain's purpose and scope in summary form; this document goes one level deeper into its concepts.

Intercompany Funding & Settlement exists to answer one recurring question, in a way that works regardless of how any one Corporate chooses to operate: **when money moves, or a financial consequence arises, between two Legal Entities that are not each simply paying their own way, what actually happened economically, and what does the applicable `SettlementPolicy` say should happen as a result?**

---

## 2. Core concepts

### A. Legal Entity

An existing RF-One concept, referenced only — never redefined here. The actual juridical/employing entity (`Corporate → Legal Entity → Restaurant (Operational Unit) → Location`; see `Personnel Management/Compensation/README.md`, "Legal Entity is a distinct canonical concept"). Every concept below is expressed in terms of one or more Legal Entities.

### B. Funding Balance

The amount of prefunded liquidity economically attributable to a specific Legal Entity within a centralized funding structure. Funding Balance answers "how much of the money sitting in a (possibly shared) account still belongs, economically, to this Legal Entity?" — it is a running balance of pre-positioned liquidity, not a receivable/payable.

**Funding Balance is not the same concept as Settlement Balance (§C) — they must never be collapsed into one.** See §5 below for the full distinction.

### C. Settlement Balance

The intercompany receivables/payables arising from economic consequences that have already matured according to the applicable `SettlementPolicy`. Settlement Balance answers "does one Legal Entity now owe another, as a result of something the Policy says creates a debt, independent of any prefunding relationship?"

A Corporate's `SettlementPolicy` may choose to keep Settlement Balance at zero permanently (everything routes through Funding Balance consumption, as in the current RF Gelati configuration — see [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) §5), or may use Settlement Balance extensively (fees, allocations, advances). Both are valid configurations of the same Domain.

### D. Funding Transfer

A movement of funds from one Legal Entity to another for funding purposes — the act of prefunding. A Funding Transfer increases the receiving side's Funding Balance economically attributable to the originating Legal Entity; it does not, by itself, decide whether the funds are "at risk" of going negative, how they may later be consumed, or whether they create a Settlement Balance — that is `FundingPolicy`'s decision (see [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) §3).

### E. Payment On Behalf

One Legal Entity physically executes a payment that is economically attributable to another Legal Entity. The paying Legal Entity is not necessarily the economically responsible one — see §4, "Required economic dimensions," for how this Domain keeps the two distinct in every fact it records.

### F. Receipt On Behalf

One Legal Entity physically receives money that is economically attributable to another Legal Entity — the receiving-side mirror of Payment On Behalf (§E).

### G. Intercompany Position

A receivable/payable relationship between two Legal Entities, created when the applicable `SettlementPolicy` requires one (as opposed to a Payment/Receipt On Behalf that consumes an existing Funding Balance without creating one). An Intercompany Position is what Settlement (§H) ultimately resolves.

### H. Settlement

The act or process by which Intercompany Positions are regulated, netted, replenished, reimbursed, or otherwise resolved. Settlement may be manual or automatic, and may run on any cadence — both are `SettlementPolicy` decisions (see `SettlementSchedule`, [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) §3).

### I. Allocation

The attribution of a shared amount to one or more beneficiary/responsible Legal Entities according to an applicable policy or rule — e.g. a shared service cost split proportionally across the Legal Entities that benefited from it. Allocation is how a single financial fact becomes economically attributed to more than one Legal Entity when no single entity is the sole beneficiary.

---

## 3. SettlementPolicy — pointer

`SettlementPolicy` (concept J) and its component sub-policies (`FundingPolicy`, `ReplenishmentPolicy`, `PaymentPolicy`, `NettingPolicy`, `AllocationPolicy`, `PurchasingPolicy`, `FeeMarkupPolicy`, `ReceiptPolicy`, `SettlementSchedule` — concepts K through S) are documented in full in [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md), including the current RF Gelati configuration as one example instance. They are not repeated here to avoid two documents drifting out of sync on the same concept; every concept in §2 above is governed by whichever `SettlementPolicy` a Corporate has configured.

---

## 4. Funding Balance vs. Settlement Balance

This distinction is prominent because collapsing it is the single most likely modeling error this Domain could make.

**Funding Balance:**

- represents prefunded liquidity economically attributable to a Legal Entity;
- may be physically pooled in a shared bank account with other Legal Entities' funds;
- remains economically attributable to its originating Legal Entity regardless of physical pooling;
- under the current RF Gelati `SettlementPolicy`, can never go negative (see [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) §5.D) — but this is a Policy choice, not a Domain-level rule; a different Corporate's `SettlementPolicy` could permit a negative Funding Balance.

**Settlement Balance:**

- represents matured intercompany receivables/payables;
- exists only when the applicable `SettlementPolicy` requires one — it is not automatically created every time Funding Balance is consumed;
- is a separate concept from Funding Balance, never a re-expression of it;
- may result from fees, allocations, reimbursements, advances, corrections, or any other configured relationship.

A Legal Entity can simultaneously have a nonzero Funding Balance and a nonzero Settlement Balance with the same counterpart Legal Entity — they answer different questions and must be readable independently.

---

## 5. Required economic dimensions

Every intercompany financial fact this Domain represents must be capable of preserving at least the following dimensions. This is a conceptual requirement, not a database schema — no table, column, or persistence mechanism is defined by this document.

| Dimension | Answers |
|---|---|
| `source_entity` | Which Legal Entity did the money/fact originate from? |
| `beneficiary_entity` | Which Legal Entity economically benefits? |
| `paying_entity` | Which Legal Entity physically pays? |
| `receiving_entity` (where applicable) | Which Legal Entity physically receives? |
| `amount` / `currency` | How much, in what currency? |
| `purpose` / relationship type | Why did this fact arise (funding, payment on behalf, allocation, fee, etc.)? |
| `source_domain` | Which Domain's own fact caused this (Tips, Purchasing, Compensation, …)? |
| `source_reference` | The specific fact in that Domain this consequence traces back to |
| `effective_date` | When did this fact economically take effect? |
| `payment_reference` (where applicable) | The specific payment execution this fact corresponds to |
| applicable `SettlementPolicy` | Which Policy (and version) governed this fact? |
| applicable Rule / Rule version (where relevant) | Which specific Rule, if any, produced this fact? |
| `status` | Where is this fact in its lifecycle (e.g. pending, settled, reversed)? |
| provenance | Where did this fact come from, and how was it acquired/derived? |
| approval/acknowledgement references (where required) | Who approved this, per the applicable Policy's requirements? |

`paying_entity` and `beneficiary_entity` are frequently different Legal Entities — that difference is the entire reason this Domain exists. A fact that cannot distinguish them is not a valid representation of an intercompany financial consequence.

---

## 6. Domain boundaries

**Tips.** Tips determines who is owed what. Intercompany Funding & Settlement handles the financial relationship only if a different Legal Entity executes the resulting payment — Tips never needs to know whether the paying Legal Entity is itself or another.

**Compensation.** Compensation determines and approves the economic consequences of work performed. Intercompany Funding & Settlement handles only the intercompany funding/payment consequence when that approved consequence is paid across a Legal Entity boundary.

**Purchasing.** Purchasing (and Purchased) own the supplier relationship, the purchasing decision, the order, the goods/services acquired, and the allocation/business logic of the purchase itself. Intercompany Funding & Settlement handles only the financial/intercompany consequence when one Legal Entity buys, funds, or pays in relation to another — it never re-decides what was purchased or from whom.

**Administration.** Administration translates this Domain's economic result into accounting/administrative representation. Intercompany Funding & Settlement must never own debit/credit accounting logic itself — see the README's "Architectural principle" section.

**Bank Reconciliation.** Bank Reconciliation matches real bank transactions. It consumes/validates this Domain's financial execution facts (e.g. confirming a Funding Transfer actually settled) but does not define the intercompany economic meaning of those facts — that meaning is established here, before Bank Reconciliation ever sees the transaction.

**Identity / Authority.** This Domain may expose actions that require approval (e.g. a proposed Funding Transfer above a threshold). Authority determines who may approve or execute them; this Domain does not own the authority model itself.

---

## 7. Accounting / tax / legal boundary

See [README.md](README.md), "Accounting / tax / legal boundary" — repeated here only as a pointer, not restated, to avoid drift: this Domain executes the configured `SettlementPolicy`; it does not certify its legal or fiscal validity.

---

## 8. Event / history principle

Corrections must never destroy history, per RF-One's existing principle: the original fact is preserved; a correction or reversal references the original rather than overwriting it. No historical economic event is ever destructively overwritten.

`SettlementPolicy` itself must be versioned and effective-dated (see [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) §4). Historical reconstruction of any intercompany relationship must be possible using: the original facts, the applicable Policy version at the time, the applicable Rules at the time, any corrections/reversals, and the final settlement results. A design that cannot answer "what did this look like under the Policy that was actually in force at the time" is not a valid implementation of this Domain.

---

## 9. Future generality

See [README.md](README.md), "Future generality." RF Gelati is the first implementation case, not a special system entity; this Domain's concepts carry no dependency on Rome's Flavours, RF Gelati, Mercury, Clover, ADP, or the restaurant industry.

---

## 10. Open questions

- **Relationship to a future general ledger / chart of accounts, if RF-One ever builds one.** This document establishes that Administration translates this Domain's results into accounting representation, but does not design that translation — left for a future Administration-side task.
- **Whether Settlement Balance, once created, can itself be prefunded against** (i.e. whether the two concepts can compose, not just coexist) is not decided here — left to `SettlementPolicy` design as a genuine future question, not assumed either way.
- **Multi-currency intercompany relationships** are acknowledged (`currency` is a required dimension, §5) but no cross-currency conversion/valuation policy is designed by this document.
