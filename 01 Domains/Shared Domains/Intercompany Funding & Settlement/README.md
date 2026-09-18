# Intercompany Funding & Settlement

**Version:** 1.0
**Status:** APPROVED DOMAIN DEFINITION
**Module:** Shared Domain / Intercompany Funding & Settlement

---

## Related documents

- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4 (Shared Domains / Business Domain taxonomy, where this Domain is introduced as a Shared Domain)
- [../../README.md](../../README.md) (`01 Domains/` purpose, the Shared Domains / Business Domain taxonomy)
- [INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md](INTERCOMPANY_FUNDING_AND_SETTLEMENT_001.md) — the full conceptual/domain model: concepts, economic dimensions, boundaries, event/history principle
- [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md) — the SettlementPolicy structure and the current RF Gelati configuration, documented as one example instance of it
- [../Personnel Management/Compensation/README.md](../Personnel%20Management/Compensation/README.md), "Legal Entity is a distinct canonical concept" — the existing `Legal Entity` concept this Domain references, never redefines (`Corporate → Legal Entity → Restaurant (Operational Unit) → Location`)
- [../Administration/README.md](../Administration/README.md) — the Domain that translates this Domain's economic results into accounting/administrative representation
- [../Purchased/README.md](../Purchased/README.md) — the Shared Domain owning the purchase fact itself, distinct from this Domain's intercompany financial consequence of a purchase
- [../Administration/Bank Reconciliation/README.md](../Administration/Bank%20Reconciliation/README.md) — matches real bank transactions; consumes/validates this Domain's financial execution facts without defining their intercompany meaning
- `CLAUDE.md` — Core/Domain/Product/Runtime distinction; this document is Domain-level definition, not Product or Runtime design

---

## Purpose

**Intercompany Funding & Settlement** is a **Shared Domain** that represents and regulates the financial relationships between Legal Entities when one entity funds, pays, receives, allocates, or otherwise financially supports operations on behalf of, for the benefit of, or in relation to another Legal Entity.

> **Cash may be centralized; economic ownership and responsibility must remain attributable to the originating Legal Entity.**

This Domain never decides how a Corporate *must* centralize its financial flows. It supports multiple possible operating models and applies whichever `SettlementPolicy` a Corporate has configured. Two Corporates may use this Domain in structurally different ways — one may treat every centralized payment as immediate prefunding consumption with no intercompany debt; another may treat the same fact as an intercompany receivable requiring periodic settlement. Both are valid; neither is hardcoded here.

Regardless of the configured `SettlementPolicy`, this Domain must always be able to distinguish:

- who economically owns the funds;
- who is economically responsible;
- who benefits;
- who physically pays;
- who physically receives;
- what relationship exists between the Legal Entities;
- what Policy caused the financial consequence.

---

## Scope

This Domain supports, without being limited to:

- prefunding;
- payment on behalf of another entity;
- centralized funding;
- centralized payments;
- centralized receipts;
- shared-cost allocation;
- reimbursement;
- intercompany advance;
- intercompany receivable/payable;
- settlement;
- netting;
- fee/markup handling;
- the financial consequence of centralized purchasing;
- replenishment;
- funding reserve/buffer policies.

**This list is illustrative, not a closed taxonomy of hardcoded transaction types.** The model stays extensible through `SettlementPolicy` and Rule-driven behavior — a future intercompany relationship this list does not name is not, by that omission, out of scope; it is modeled through the same concepts (§ below) and governed the same way, by policy configuration.

---

## What this Domain does NOT own

- **Legal Entity itself** — an existing RF-One concept (`Corporate → Legal Entity → Restaurant (Operational Unit) → Location`, see `Personnel Management/Compensation/README.md`); this Domain references it, never redefines it.
- **Who is owed what for work performed or tips earned** — that is Tips' and Compensation's own decision; this Domain handles only the intercompany financial relationship if a different Legal Entity executes the resulting payment.
- **The supplier relationship, purchasing decision, order, or goods/services acquired** — that is Purchasing's/Purchased's own scope; this Domain handles only the financial/intercompany consequence when one Legal Entity buys, funds, or pays in relation to another.
- **Debit/credit accounting logic, ledger posting, or provider-specific representation** — that is Administration's role, applied *after* this Domain has established the economic relationship. See "Architectural principle" below.
- **Matching real bank transactions** — that is Bank Reconciliation's role; it consumes/validates this Domain's financial execution facts without defining their intercompany economic meaning.
- **Who may approve or execute an action this Domain exposes** — that is Identity/Authority's role; this Domain may require approval for an action without owning the authority model that grants it.
- **Tax treatment, legal validity, or accounting advice for a chosen intercompany structure.** See "Accounting / tax / legal boundary" below.

---

## Architectural principle: Cross Domain, not Administration

This Domain belongs under **Shared Domains**, not under Administration.

The economic relationship between Legal Entities exists *before* any accounting or administrative representation of it — WP economically owns the funds it transferred to RF Gelati the moment the transfer happens, independent of how (or whether) that fact is later posted, reconciled, or reported. Administration may translate the result of this Domain's reasoning into accounting, reconciliation, or provider-specific representations, but it does not originate the economic relationship itself.

> **Intercompany Funding & Settlement represents economic relationships between Legal Entities. Administration represents those relationships for accounting and external administrative purposes.**

> **Settlement behavior is governed by Corporate-configured `SettlementPolicy`, not by hardcoded RF-One assumptions.**

---

## Accounting / tax / legal boundary

Intercompany Funding & Settlement does **not**:

- determine tax treatment;
- certify legal validity;
- provide accounting advice;
- decide whether a chosen intercompany structure is legally or fiscally compliant.

The Corporate/user is responsible for the `SettlementPolicy` it selects. RF-One may support `compliance_warning`, `warning_text`, an acknowledgement mechanism, an external validation reference, and policy versioning/effective dating — but RF-One **executes** the configured Policy; it does not **certify** it.

---

## Future generality

RF Gelati (documented as an example in [SETTLEMENT_POLICY_001.md](SETTLEMENT_POLICY_001.md)) is only the first implementation case, not a special system entity. This Domain must work for any future Corporate structure where several Legal Entities share a financial hub, one entity pays for others, entities prefund a central hub, entities centralize purchasing or receipts, shared services are allocated, intercompany settlements occur, or another model not yet anticipated emerges. Nothing in this Domain's semantics depends on Rome's Flavours, RF Gelati, Mercury, Clover, ADP, or the restaurant industry — those are implementations/examples, never Domain semantics.
