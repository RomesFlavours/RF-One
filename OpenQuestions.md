# Open Questions

This file tracks unresolved semantic and architectural questions across Administration, Restaurant/Purchasing and Labor Cost.

Items listed here are **not canonical rules** until explicitly resolved.

---

## Invoice Tax Treatment — OPEN

Source: originally TASK_INVOICE_001; canonical terminology updated by TASK_PURCHASING_001, which reconciled the Administration `Invoice Intake.md` model into `01 Domains/Restaurant/Purchasing/` and removed the former as a duplicate (see `01 Domains/Restaurant/Purchasing/BusinessRules.md`, Rule 12, and `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md`).

Current principle:

```text
Purchase Document / Purchase Line tax facts must be preserved as atomic source facts.
```

At minimum, RF-One preserves, when available:

- tax amount charged;
- tax source label/type, if disclosed by the supplier;
- jurisdiction, if known;
- source evidence (the original Purchase Document);
- the level at which the tax applies (document-level or Purchase Line-level).

RF-One does **not** yet assume that tax:

- is always part of Effective Product Cost;
- is always excluded from Effective Product Cost;
- is always recoverable/deductible;
- is always non-recoverable/non-deductible.

The economic treatment depends on jurisdiction and the applicable fiscal rule — consistent with the Core Epistemic Boundary, a tax/legal interpretation is Belief or Inference, never silently Fact, until confirmed (`00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md`).

Provisional rule (not yet a closed resolution):

```text
Tax enters Effective Product Cost only when the applicable rule layer
establishes that it is economically borne by the business.
```

For Florida restaurant purchases specifically, resale/exemption treatment must be verified before any automatic inclusion or exclusion of tax in Effective Product Cost.

This question is expected to be resolved once the Taxation Domain (`01 Domains/Taxation/README.md`) or a jurisdiction rule pack establishes the applicable treatment for these suppliers/purchase categories. Restaurant/Purchasing comes before fiscal treatment — see `01 Domains/Restaurant/Purchasing/BusinessRules.md`, "Purchasing Precedes Administration and Taxation."

---

## Resolved

### 0. Rome's Flavours Tip Policy values — RESOLVED (TASK_TIPS_004)

Source: TASK_TIPS_003 (raised), TASK_TIPS_004 (resolved).

The Product Owner supplied the approved policy: Location-specific policies (Winter Park configured; Mount Dora not yet canonical — see `07 Tasks/Reports/TASK_TIPS_004_REPORT.md`), Component 1 SERVICE_OWNER 90%, Component 2 ROLE_PRESENT_AT_PAYMENT (Host) 10% with `no_eligible_behavior=RETURN_TO_SERVICE_OWNER`, `valid_from` = each Location's own earliest real `PaymentTip` evidence. Configured reproducibly via `configure_rome_flavours_tip_policy.py` and now live in the real `data/rfone.db`. Full detail: `07 Tasks/Reports/TASK_TIPS_004_REPORT.md`.

### 1. Whether generic Personnel cost may be allocated to Employees — RESOLVED (TASK_LABOR_COST_001)

Resolution:

```text
If a cost is causally attributable to an Employee
→ Employee Cost

If it is not causally attributable
→ Unallocated Personnel Cost

No artificial Employee allocation.
```

Canonical definition: `01 Domains/Administration/Personnel Cost.md` (`Total Employee Cost`, `Unallocated Personnel Cost`, `Total Personnel Cost = Σ Total Employee Cost + Unallocated Personnel Cost`). The earlier provisional `Direct Employee Labor Cost + Allocated Labor Overhead` framing, and the `Allocated Labor Overhead` concept itself, are rejected — RF-One never distributes a generic/shared personnel cost across Employees merely to make per-Employee totals add up, because doing so would create false comparative evidence for Personnel Management (`Personnel Cost.md` §11).

---

## Resolution rule

When an open question is resolved:

1. Update the appropriate canonical Domain document.
2. Implement or migrate the Runtime model only if needed.
3. Remove the resolved item from this file, or move it to a short `Resolved` section with a reference to the canonical document.
