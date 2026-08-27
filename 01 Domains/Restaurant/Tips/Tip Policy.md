# Tip Policy

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Tips
**Origin:** TASK_TIPS_001

---

## Definition

A **Tip Policy** is a Restaurant-configured, temporally valid set of rules describing how a recorded Tip is shared among Employees.

A Tip Policy is Restaurant configuration, never Domain ontology — no percentage, role name, or component structure in this document or in `03 Software/RF-One Data Store/rfone_data_store/models.py` is a default, a universal rule, or a Rome's Flavours value. A Restaurant with no configured Tip Policy simply has no way to calculate Tips yet; RF-One never invents one to make a calculation succeed (see `03 Software/RF-One Data Store/validate_tips_readiness.py`'s explicit read-only-and-honest behavior).

---

## Temporal scope

A Tip Policy is scoped to a Restaurant (and, optionally, to one of its Locations) and is valid for a bounded or open-ended time interval:

```text
restaurant scope
optional Location scope
status
valid_from
valid_to (nullable — open-ended)
```

A calculation for a Payment at timestamp `T` always uses the policy valid **at `T`**, never today's policy applied retroactively to a period when a different policy was actually in force. If a Restaurant changes its Tip Policy, the prior policy's periods are still calculated exactly as they were originally configured — history is never silently recalculated under a newer rule.

---

## Policy components

A Tip Policy is composed of one or more components, each specifying an explicit share of the recorded Tip and to whom it goes. At minimum, two recipient semantics are supported:

### `SERVICE_OWNER`

Allocates the component's share to the Employee(s) resolved by the Order's **service-attribution boundary** (see `Tip Allocation.md`) — never `Order.employee` or `Payment.employee` directly.

### `ROLE_PRESENT_AT_PAYMENT`

Allocates the component's share to Employees who, at the Payment's timestamp:

1. have a Shift active;
2. have a valid Employee Assignment;
3. match the component's configured Restaurant Role and Restaurant scope.

No role name here is universal — a Restaurant configures whichever `RestaurantRole` values it actually uses (see `01 Domains/Restaurant/Organization/Restaurant Role.md`).

Concurrent Employee Assignments may be legitimate (`01 Domains/Restaurant/Restaurant Semantic Model.md` §9; `01 Domains/Restaurant/Organization/Employee Assignment.md`, "Multi-role / multi-area capability" — e.g. an Employee holding both a `Manager` and a `Server` Assignment at once, in the same or different Operational Areas). Tip eligibility is evaluated against the specific policy component being calculated — the presence of another, concurrent, matching-a-different-Role Assignment does not by itself invalidate eligibility for this component.

---

## Share representation

Each component states its share as an exact decimal percentage (e.g. `80.0000` = 80%), never a binary float. Any percentage appearing anywhere in this document, in a test, or in code comments is illustrative only — e.g. "Service owner 80%, Bartender role present at payment 10%, Support role present at payment 10%" is an *example* of a possible configuration, never a default or a Rome's Flavours rule.

---

## No-eligible-recipient behavior

A Restaurant must configure, per component, what happens when nobody qualifies for its share at the relevant time:

```text
RETURN_TO_SERVICE_OWNER              — redirect the share to the resolved service owner
REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS  — redistribute proportionally among this Tip's
                                        other components that DO have an eligible recipient
LEAVE_UNALLOCATED                    — the share remains explicitly, auditably unallocated
```

There is no silent universal default. If the configured behavior itself cannot be applied (e.g. `RETURN_TO_SERVICE_OWNER` when the service owner is also unresolved), RF-One produces an explicit calculation issue rather than guessing — see `Tip Allocation.md`.

---

## Split method

Within a recipient group (more than one eligible Employee for the same component), the first supported method is:

```text
EQUAL_ELIGIBLE_HEADCOUNT — component amount / number of eligible Employees,
                            with deterministic minor-unit rounding
```

Within one `EQUAL_ELIGIBLE_HEADCOUNT` component, an Employee is counted once regardless of how many matching Assignment rows exist (e.g. an Employee validly assigned to the required Role in two different Operational Areas at once still receives exactly one headcount share, never two).

The schema deliberately leaves room for future methods (`PRO_RATA_WORKED_TIME`, `WEIGHTED_ROLE`, `CONTRIBUTION_BASED`, illustrative only) without requiring the economic model itself to be rewritten — `TipPolicyComponent.split_method` is a free string, not a fixed enum.

---

## Business Rules

- A Tip Policy belongs to exactly one Restaurant, and optionally one of its Locations.
- A calculation at timestamp `T` uses the policy valid at `T`, never a later or earlier one.
- Every component states an explicit share, recipient basis, split method, and no-eligible-recipient behavior — none is defaulted silently.
- `ROLE_PRESENT_AT_PAYMENT` never silently reduces to a Clover `SourceRole` — see `01 Domains/Restaurant/Organization/Restaurant Role.md`, "Distinct from Clover named Role, Clover systemRole, and personnel identity."
- No Tip Policy, component, percentage, or role name is created automatically from Clover data or from this Domain's own documentation examples.
