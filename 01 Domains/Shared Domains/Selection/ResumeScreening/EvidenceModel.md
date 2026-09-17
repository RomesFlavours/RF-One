# Evidence Model (Resume Screening)

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Domain:** Selection / Resume Screening
**Origin:** TASK_SELECTION_001

---

## Purpose

Every résumé analysis RF-One produces must keep four categories of information visibly separate. This is a Resume-Screening-specific specialization of the Core Epistemic Boundary (`00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md`) and of [CandidateEvidence.md](../CandidateEvidence.md) — it does not redefine either, it applies them concretely to a parsed résumé.

```text
FACT                  information explicitly present in the résumé
DERIVED INFORMATION   information calculated or inferred from Facts
FLAG                  something that requires verification or human attention
INDICATOR             a formal, measurable dimension used by the Resume Engine
```

Never present an inference as a Fact. A Flag is not automatically negative — it marks something worth the evaluator's attention, positive, negative, or simply unresolved.

---

## Worked example

```text
FACT:
Candidate worked as Server from March 2023 to June 2025.

DERIVED:
27 months of direct Server experience.

FLAG:
Three consecutive jobs shorter than six months.

INDICATOR:
Career Stability: Moderate.
```

The Fact is exactly what the résumé states (a role and two dates). The Derived value is a calculation performed *on* that Fact (a month count — see [ExperienceAndTrajectory.md](ExperienceAndTrajectory.md)). The Flag is a pattern detected *across* several Facts, surfaced for the evaluator to look at, not a conclusion. The Indicator is a named, structured dimension the Resume Engine reports on (see [FlagsAndIndicators.md](FlagsAndIndicators.md)) — never a single blended score.

---

## "Claim ≠ Evidence"

A **claim** is something the candidate states about themselves without a demonstrated instance. **Evidence** is a specific, checkable instance that supports the claim.

```text
CLAIM (weaker):     "Teamwork" listed under Skills.
EVIDENCE (stronger): "Trained new servers and coordinated closing duties."
```

Both may be preserved as Facts (the résumé really does say both things), but they are not equivalent: a bare Skills-section claim is a Fact about *what the candidate wrote*, not a Fact about *what the candidate did*. Résumé Screening must keep the distinction visible rather than treating every listed skill as equally strong evidence of the underlying capability — this is what lets [Indicators](FlagsAndIndicators.md) like Evidence Density (see also [Information Quality](FlagsAndIndicators.md#information-quality)) mean something.

---

## Category boundaries

### FACT

Directly present in the résumé text: a name, an employer, a start/end date, a listed skill, a stated qualification. A Fact is preserved with its **evidence snippet** — the résumé text it came from — whenever practical (`CandidateCVProfile.md`, "Work History"), so the UI can show *where* a Fact came from, not just assert it.

A Fact may itself be a claim rather than evidence of ability (see "Claim ≠ Evidence" above) — that distinction is about the *strength* of a Fact, not whether it is a Fact at all. Both a Skills-list entry and a described accomplishment are Facts; only the latter is Evidence in the stronger sense.

### DERIVED INFORMATION

Anything calculated or inferred *from* Facts: a duration in months, a total years-of-experience figure, a role classification (target/equivalent/propedeutic/adjacent — [RoleModel.md](RoleModel.md)), an experience breakdown by category. Derived Information must always be traceable back to the Fact(s) it was computed from, and must never be redisplayed as if it were itself explicitly stated in the résumé.

### FLAG

A signal that something needs the evaluator's attention — a pattern, an inconsistency, a gap, a transition worth asking about. See [FlagsAndIndicators.md](FlagsAndIndicators.md) for the structured Flag model and the initial flag types. A Flag never carries an implicit verdict; **absence of evidence is not automatically negative evidence** (Information Quality, [FlagsAndIndicators.md](FlagsAndIndicators.md)) — a Flag exists to prompt a question, not to pre-answer it.

### INDICATOR

A named, formal, measurable dimension the Resume Engine reports separately (Direct Role Experience, Stability, Career Progression, ...). Indicators are built from Derived Information, are never combined into one CV score (`README.md`, "No universal CV score"), and always keep enough raw value alongside any descriptive state (e.g. "44 months" alongside "Strong") that the evaluator can see the underlying number, not just a label.

---

## What this document does not do

- It does not define the specific Indicator list (see [FlagsAndIndicators.md](FlagsAndIndicators.md)).
- It does not define specific Flag types (same document).
- It does not redefine `CandidateEvidence.md`'s general provenance/epistemic-status model — it specializes it for the résumé-parsing case only.
