# Trainable Gap

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Selection

---

## Purpose

A **Trainable Gap** is a gap between current candidate capability/Evidence and the desired role standard that may reasonably be addressed through learning, training, practice, onboarding, or experience.

Trainable Gap lets Selection reason about a candidate who does not yet fully meet a [Selection Requirement](SelectionRequirement.md) without automatically treating that gap as disqualifying.

---

## Important distinctions

```text
Trainable Gap
  ≠ hard Constraint
  ≠ disqualifying incompatibility
  ≠ missing Evidence
  ≠ demonstrated inability
```

- A **hard Constraint** (e.g. a legal work-authorization requirement) cannot be closed by training, and is not a Trainable Gap regardless of how capable the candidate otherwise is.
- A **disqualifying incompatibility** (e.g. a fundamental mismatch with a mandatory Requirement, demonstrated rather than assumed) is not something Selection should relabel as "trainable" to avoid an uncomfortable conclusion.
- **Missing Evidence** is an Unknown — the gap has not been observed at all, so there is nothing yet to characterize as trainable or not (see [CandidateEvidence.md](CandidateEvidence.md)). A Trainable Gap requires the underlying gap to actually be evidenced, not merely assumed from absence of information.
- **Demonstrated inability** — evidence that the candidate has already attempted to close the gap and been unable to — is distinct from a gap that simply has not been addressed yet.

Confusing any of these with a Trainable Gap either wrongly disqualifies a candidate who could reasonably close the gap, or wrongly proceeds with a candidate whose gap cannot in fact be closed.

---

## What Trainable Gap helps Selection reason about

- **expected training effort** — how much training/practice the gap is likely to require;
- **estimated time to standard** — how long until the candidate is likely to meet the Requirement;
- **uncertainty of improvement** — how confident that estimate actually is;
- **business cost/risk** — what it costs the organization to carry the gap during that period, and what happens if the estimate is wrong;
- **acceptability relative to other candidate strengths** — whether the gap is worth accepting given what else the candidate brings.

This reasoning feeds directly into a [Fit Assessment](FitAssessment.md)'s "Trainability / Growth Potential" dimension and may become an explicit condition attached to a [Selection Decision](SelectionDecision.md) (e.g. "select with known Trainable Gaps").

---

## What this document does not do

- It does not define a Training Domain. No Training Domain is created by this task — see [README.md](README.md), "Relationship to future Training and Performance."
- It does not prescribe universal training durations, curricula, or methods. "Estimated time to standard" is a case-by-case judgment informed by the specific gap and role, not a fixed table.
- It does not define how training is delivered, tracked, or verified — that is future Training/Product/Runtime scope.

---

## Restaurant example (illustrative only)

Restaurant technical/behavioral requirements can illustrate the distinction cleanly (see `08 External/Shelbi/Training-Content-Shot-List.pdf` for the kind of concrete, teachable technique this draws on):

```text
Requirement:       Wine service to house standard (presenting the bottle,
                    opening at the table, correct pour)
Evidence:          Candidate has general front-of-house experience but no
                    documented wine-service training
Classification:    Trainable Gap
Rationale:         The gap is procedural and demonstrably teachable — a
                    known technique with a known correct/incorrect version
                    (e.g. holding a glass by the stem vs. the rim) — not a
                    disqualifying incompatibility or hard Constraint
Estimated effort:  Low; a single structured training session plus supervised
                    practice
```

Contrast with a gap that is **not** trainable in the same way:

```text
Requirement:       Legal authorization to work in this jurisdiction
Evidence:          Candidate does not currently hold it
Classification:    Hard Constraint, not a Trainable Gap
Rationale:         No amount of training closes an authorization gap;
                    it depends on a legal/administrative process outside
                    Selection's or the candidate's control
```

And a gap where the correct classification is simply **Unknown**:

```text
Requirement:       Ability to run dinner service independently
Evidence:          No trial shift has been performed yet
Classification:    Missing Evidence (Unknown), not yet a Trainable Gap
                    and not yet a demonstrated capability
Rationale:         There is no Evidence yet that a gap exists at all —
                    characterizing it as "trainable" would be premature
```

---

## Related concepts

- [Selection.md](Selection.md)
- [SelectionRequirement.md](SelectionRequirement.md)
- [CandidateEvidence.md](CandidateEvidence.md)
- [FitAssessment.md](FitAssessment.md)
- [SelectionDecision.md](SelectionDecision.md)
