# Open Questions

This file tracks unresolved semantic and architectural questions for the Administration / Payroll and Labor Cost model.

Items listed here are **not canonical rules** until explicitly resolved.

---

## Resolved

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
