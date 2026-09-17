# Experience Analysis and Career Trajectory

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Domain:** Selection / Resume Screening
**Origin:** TASK_SELECTION_001

---

## Purpose

Defines how Work History Facts ([CandidateCVProfile.md](CandidateCVProfile.md)) become Derived experience figures and career-trajectory observations ([EvidenceModel.md](EvidenceModel.md)). Every calculation here is Derived Information, not Fact — it must remain traceable back to the Work History records it was computed from.

---

## Experience calculations

Computed where possible from Work History, using the [Role Model](RoleModel.md)'s classification of each `normalized_role` against the active Role Configuration:

- total documented work experience
- target-role experience
- equivalent-role experience
- propedeutic-role experience
- adjacent-role experience
- industry experience
- customer-facing experience
- commercial/sales exposure
- supervisory/leadership exposure

The last three (customer-facing, commercial, supervisory) require an Industry Extension to classify which normalized roles qualify — Selection Core only defines the aggregation, never a hard-coded role list (`README.md`, domain architecture).

## Tenure and pattern calculations

- employer count
- average tenure
- median tenure
- longest tenure
- tenure in recent jobs
- number of jobs under 3 months
- number of jobs under 6 months
- jobs over 12 months
- jobs over 24 months
- observable employment gaps
- overlapping employments

## Overlap-safe total span

**Total career span must never double-count overlapping calendar months**, while individual per-role experience is still preserved and reported in full. Concretely: total span is computed from the *union* of each Work History record's `[start_date, end_date]` interval (merging overlapping intervals before summing), while target-role/equivalent-role/etc. experience each sum their own matching records' months independently, overlap included — a candidate holding two concurrent part-time roles has their real calendar span reported once, but each role's own experience figure still reflects its own full duration.

## Date precision

A résumé rarely states exact days. Dates are preserved at whatever precision the résumé gives (month/year is typical; year-only is common for older entries) and every downstream calculation must carry that precision's uncertainty forward rather than silently assuming day-1 or day-31 — see [FlagsAndIndicators.md](FlagsAndIndicators.md), "Information Quality," `date precision`.

---

## Career trajectory

Detected, not asserted as certain, from the ordered sequence of Work History records:

- promotions
- increases in responsibility
- lateral moves
- apparent decreases in responsibility
- role changes
- industry changes
- return to a previous employer
- continuity inside the same industry
- role transitions requiring investigation

### Do not infer motive

Trajectory detection identifies *that* a transition happened, never *why*. A Cook applying for a Server role is a BOH → FOH transition — full stop. RF-One must never write "the candidate is moving because of tips" or any other motive; motive is unknown until the candidate says otherwise.

```text
ROLE_TRANSITION
From: BOH
To: FOH / Server
Motivation: Unknown

Suggested interview question:
"Your recent experience has primarily been in the kitchen. What is making
you want to move into serving?"
```

This becomes a [Flag](FlagsAndIndicators.md) (`ROLE_TRANSITION`, industry extensions may add a more specific detail code such as `BOH_TO_FOH`) carrying exactly this shape: the transition itself, `Motivation: Unknown`, and a suggested, motive-neutral interview question — never a conclusion about the candidate's reasons.

---

## Contextual career / age information

The system may retain contextual age/career information if present or reasonably derivable, kept structurally outside every automated Indicator and ranking:

- If age is explicitly declared, store it as **declared context**.
- If a reasonable age range can be derived from a clearly dated high-school completion record, it may be shown as **derived context**, always with its derivation and a confidence level attached.
- Do not force an estimate from weak evidence (e.g. an ambiguous university date is not sufficient on its own).
- An estimated age/range must remain outside all automated Indicators and rankings ([FlagsAndIndicators.md](FlagsAndIndicators.md)) — it is legal/fairness-sensitive context (`../README.md`, "Legal / fairness / governance safeguards": "sensitive/protected attributes must not be inferred or used improperly"), never a scoring input.
- It must be labeled clearly as **context-only** wherever shown.

Related, but independently computed, career-context figures (also context, not Indicators):

- estimated career span
- documented workforce years
- industry years
- role-specific years

---

## Employer, preserved as a Fact only

`CandidateWorkHistory.employer` is stored and displayed, but nothing in this document — or anywhere in Resume Screening today — reasons about *which* employer it is, what that employer's operating standard was, or how one employer's "3 years" compares in weight to another's. That reasoning belongs to a future Organization Intelligence capability, explicitly not defined here — see `README.md`, "Organization Intelligence — OPEN / TBD."
