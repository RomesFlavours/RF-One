# Administration Domain

**Version:** 1.0
**Status:** Approved (initial foundation — TASK_PAYROLL_001)
**Module:** Domain / Administration

---

## Purpose

**Administration** is the transversal (cross-industry) Domain responsible for the administrative execution of obligations that arise from operating a business — obligations owed to Employees, tax authorities, and other administrative counterparties, once the underlying operational/business facts that create those obligations have already occurred.

Administration does not decide operational value, does not evaluate personnel performance, does not set tax policy, and does not own the business facts it processes. It receives or resolves the inputs required to administratively process an obligation, records what actually happened when an external processor executed it, and exposes the resulting facts for cost analysis and reconciliation.

Administration is transversal in the same sense already established for Personnel Management and Taxation (see `01 Domains/Domain Architecture.md`): it applies wherever an administrative execution obligation exists, consuming content from whichever Domain owns the underlying fact, without duplicating that Domain's knowledge.

---

## Module map

```text
Administration
├── Personnel Cost      (transversal concept — spans Payroll and future cost sources)
└── Payroll
```

Payroll is the first module. Other administrative execution capabilities (e.g. a future Accounts Payable or Benefits Administration module) may be added later as siblings — Administration is not defined narrowly around Payroll alone, but only Payroll is documented and implemented by this task.

`Personnel Cost.md` is not a module — it is the Administration-level canonical cost concept (`Total Employee Cost`, `Unallocated Personnel Cost`, `Total Personnel Cost`) that Payroll and any future Employee-attributable cost source (vehicle, benefit, equipment) both feed. It is documented at Domain level, not inside `Payroll/`, precisely because Employee cost is not exclusively a payroll concern.

| Document | Answers | Status |
|---|---|---|
| [Personnel Cost.md](Personnel%20Cost.md) | What is the causally attributable, canonical economic cost of an Employee, and of Personnel overall? | Documented — TASK_LABOR_COST_001 |
| [Payroll/](Payroll/README.md) | How is Employee compensation administratively processed, and what did it actually cost? | Documented — TASK_PAYROLL_001; repositioned under `Personnel Cost.md` by TASK_LABOR_COST_001 |

---

## Administration ≠ Restaurant, ≠ Personnel Management, ≠ Taxation, ≠ Accounting

```text
Administration ≠ Restaurant
Administration ≠ Personnel Management
Administration ≠ Taxation
Administration ≠ Accounting
```

- **Administration ≠ Restaurant.** Restaurant supplies the operational facts (worked time, Tips, sales) an administrative process consumes; Administration does not own Restaurant semantics and does not run only for restaurants.
- **Administration ≠ Personnel Management.** Personnel Management decides who occupies a role, whether they meet its standard, and what should be done about them (`01 Domains/Personnel Management/README.md`). Administration does not make any of those judgments — it only administratively executes the compensation consequence of an employment relationship that Personnel Management/the business already established.
- **Administration ≠ Taxation.** Taxation reasons about tax obligations, positions and treatments across every Domain (`01 Domains/Taxation/README.md`). Administration (Payroll) consumes jurisdiction/tax-relevant outcomes where applicable but does not itself define tax law, tax rates, or tax treatment — it administratively carries out what has already been determined or delegates the undetermined part.
- **Administration ≠ Accounting.** Accounting records, classifies and reports financial transactions in a ledger. Administration produces the economic facts (e.g. actual payroll cost) that Accounting, where it exists, would post — it does not maintain a ledger or produce financial statements itself.

---

## Relationship to Core 2.0

Administration is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them, in particular Subject/Reality, Decision/Action/Outcome/Learning, and Temporal Coherence (`00 Core/ConceptualArchitecture/`) — an administrative execution is a Reality fact recorded after the fact, not a Decision Administration makes on the Subject's behalf.

---

## Related documents

- [Personnel Cost.md](Personnel%20Cost.md) — the transversal Employee/Personnel cost concept
- [Payroll/README.md](Payroll/README.md) — the Payroll module
- [../Domain Architecture.md](../Domain%20Architecture.md) — cross-Domain conclusions for other transversal Domains
- [../README.md](../README.md) — `01 Domains/` purpose and authority
- [../Personnel Management/README.md](../Personnel%20Management/README.md), [../Taxation/README.md](../Taxation/README.md) — sibling transversal Domains
- `07 Tasks/TASK_PAYROLL_001_Formalize_Administration_Payroll_Data_Model_ADP_Result_Import_and_Labor_Cost.md` — task that created this Domain
