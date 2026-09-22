# Finalized Tips Period

*Business Domain → Restaurant → Tips. Canonical for what it means to close,
validate and finalize a Tips period, and for what Payroll may consume.*

Established by `TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001`.

---

## 1. Why this exists

Tips are calculated on demand, from source facts, for any period an
operator asks about. That answers *"what do these days look like?"* and it
is deliberately stateless — any period can be recalculated freely, as often
as needed.

It does not answer a different and equally necessary question: *"which
figure are we actually paying, who approved it, and can it still change?"*

A **Finalized Tips Period** is the answer to that second question. It is a
calculated period that has been **closed**: saved together with the
configuration and rules it was computed under, checked against one control,
approved by a named person (or by an explicitly configured automatic rule),
and thereafter immutable.

Calculating is not closing. Looking at a screen writes nothing.

---

## 2. Rule Version lifecycle

A Tip Distribution Rule is effective-dated. When a new version takes effect
from date **F**, running to **T** (possibly open-ended), every existing
version is resolved in one simple pass:

| Situation of the existing version | Outcome |
|---|---|
| It started **before F** | Becomes **OLD**. It keeps governing everything up to F and stops there. |
| It was scheduled to start **inside** the new version's coverage | Becomes **CANCELLED**. It never governs anything. |
| It starts **at or after T** | Stays **ACTIVE** — it is genuinely still to come. |
| The new version is **open-ended** | There is no "after", so every covered future version is CANCELLED. |

A version's **terms are never rewritten**: rate, calculation base, roles,
modes and `effective_from` stay exactly as entered. Only the status moves,
and for an OLD version its own `effective_to` closes at F — which is what
closing a window means.

Consequences that matter operationally:

- An **OLD** version still governs its own closed past, so a period
  calculated before the rule changed reconstructs exactly as it did then.
- A **CANCELLED** version governs no instant at all, past or future.
- Inserting a rule with a **backdated** start needs no special mechanism.
  It is the same pass. That is the point: a historical correction is an
  ordinary rule change, not a separate feature.

**No order may be left without a rule.** A period whose earlier nights fall
outside every rule's coverage is a configuration defect, not an acceptable
zero.

---

## 3. The one control

    Total Tips + Gratuity  ==  Total Employee Entitlements

This is the **only** monetary control. Every cent the Restaurant collected
in the period lands on exactly one employee's entitlement.

A non-zero difference is **reported, never repaired**. A period that does
not balance cannot become final by any path, manual or automatic.

Three figures are **audit information and never controls**:

- what was distributed to other recipients;
- what would have been distributed had an eligible recipient existed;
- per-person retained amounts.

### No eligible recipient is not an exception

When no eligible recipient was on shift at the deciding instant, **no
distribution obligation arose**. The Service Owner keeps 100% of that
Order. This is a normal, resolved, payable outcome — not an unresolved
amount, not a warning, and not a reason to flag the employee.

---

## 4. Validation and finalization

Two states, two ways to reach the second:

| State | Meaning |
|---|---|
| **CALCULATED** | Saved. Freely recalculable. **Not** a Payroll source. |
| **FINAL** | Definitive. Immutable. The only Payroll source. |

**Validation Mode** is a per-Restaurant setting with its own configuration,
deliberately separate from Review Mode (which decides only which report the
UI emphasises — the two share a word, not a meaning):

- **MANUAL** — the default, in every direction. An unconfigured Restaurant
  is MANUAL. Nothing resolves to AUTOMATIC by omission.
- **AUTOMATIC** — only ever the result of an explicit, recorded decision.

### Who validates

The validator is identified through **the one existing RF-One login**.
Never a second login, never a Tips-specific access, never a typed-in name,
never an anonymous validator.

When no RF-One identity can be resolved, validation is **refused** and the
reason is stated. An approval RF-One cannot attach to a person is worse
than a blocked one, because it looks signed.

An automatically finalized period names **no** validator, because none
exists, and saying otherwise would be a fabrication.

---

## 5. Immutability

A FINAL period's figures, period, validator and per-employee entitlements
do not move. Correcting a final period means calculating a **new** run; the
final one stays exactly as it was approved.

**Open decision.** RF-One has no supersession policy between two final runs
covering the same Business Dates. Rather than pick a winner silently, it
**refuses** the second finalization and names the first. Both runs are
kept. Which of the two Payroll should pay, if a period genuinely has to be
re-finalized, is a Product Owner decision that has not been made.

---

## 6. The Calculation Run Report

Opening a report **does not recalculate**. Every figure is read from what
was saved when the period was closed.

This is not an optimisation. A final report reopened later must be the
document that was approved — even if a rule, a shift or an order has been
edited since. A report that quietly re-derived itself would be a different
document carrying the same signature.

The **Run History** lists every saved period, final or not. A history that
showed only approved periods would hide the recalculations that led to
them.

---

## 7. The Payroll contract

- Payroll reads a **FINAL** Calculation Run. Nothing else is a Tips source
  — not a CALCULATED run, however recent, and not a screen.
- Payroll **never recalculates from Orders**. The entitlements are
  persisted on the final run; re-deriving them would reintroduce exactly
  the drift finalization exists to prevent.
- If no final run exists for the period, Payroll gets **nothing** and a
  reason. It does not fall back to an unapproved run and it does not pay a
  provisional figure.

The export format itself is not defined by this document.

---

## 8. Where this lives

| Concern | Implementation |
|---|---|
| Rule Version lifecycle | `03 Software/RF-One Data Store/rfone_data_store/tips/distribution_rule_service.py` |
| Closing, validating, finalizing, reporting | `.../tips/calculation_run_service.py` |
| Validation Mode configuration | `.../tips/validation_mode_service.py` |
| Shared RF-One identity | `.../rfone_web_session.py`, `03 Software/Tips/rfone_identity.py` |
| Tests | `03 Software/RF-One Data Store/test_tips_finalized_period.py` |

Runtime behaviour is described here only where it carries business meaning.
`03 Software/` remains the authority for how it is implemented.
