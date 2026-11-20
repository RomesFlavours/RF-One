"""Primary Screening — generic, AI-assisted Criterion evaluator (Task
3D-FIX). Task 3D's `_auto_evaluate_from_signal` only ever resolves a
Criterion explicitly linked to a Signal Definition; every other
restaurant-authored Criterion stayed `NOT_EVALUATED` until a Selezionatore
manually entered a level — defeating the "200 Applications -> automatically
proposed evaluations -> ~15-20 reviewed first" operational purpose. This
module is the generic fallback: it interprets an ARBITRARY restaurant-
authored `PrimaryScreeningCriterionSnapshot` (its own level 0-4 meanings,
guidance, and allowed evidence sources) against a structured evidence
package built from evidence already persisted in Selection, using the
existing `parsing/ai_client.py` abstraction — never criterion-specific
if/else logic (task §1).

Boundary this module enforces (task §2/§5/§17): the model must choose among
THIS restaurant's own configured level meanings, never invent a universal
0-4 scale; every conclusion must be traceable to evidence already present
in Selection; a weak/ambiguous case must be answered conservatively (a
lower level, lower confidence) or with `INSUFFICIENT_EVIDENCE` — never
silently coerced to level 0. `AIEvaluationUnavailable` is the single
sentinel any caller must catch (no AI provider configured, a request
failure, or malformed/out-of-contract AI output) — the caller's job is to
leave the Criterion unresolved, never to fabricate a level (task §8).

Primary Screening happens before Phone/In-Person Interview (task §3), so
the evidence package never reads Phone/In-Person/Consistency data, even if
a Criterion's `evidence_sources_allowed` lists `CONSISTENCY_INFORMATION`
for a later, explicit re-evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import fit_assessment_service as fa_svc
from . import outcome_service as outcome_svc
from . import persistence
from . import signal_service as sig_svc
from .core import fit_assessment_model as fam
from .core import primary_screening_model as psm
from .core import signal_model as sm
from .parsing import ai_client


class AIEvaluationUnavailable(Exception):
    """No usable automatic evaluation could be produced for this Criterion
    right now — no AI provider configured, the request failed/timed out, or
    the response did not satisfy the structured-output contract. Callers
    must treat this exactly like Task 2A's `ProviderUnavailable`: fall back
    (here, leave the Criterion Evaluation unresolved), never surface as an
    application error, never fabricate a level."""


@dataclass
class EvidenceRef:
    source_type: str
    evidence_text: str
    source_reference: str | None = None
    interpretation: str | None = None


@dataclass
class AIEvaluationResult:
    status: str  # EVALUATED | INSUFFICIENT_EVIDENCE | NOT_APPLICABLE
    level: int | None
    confidence: str
    explanation: str
    evidence: list[EvidenceRef] = field(default_factory=list)


_VALID_RESULT_STATUSES = (psm.EVALUATED, psm.INSUFFICIENT_EVIDENCE, psm.NOT_APPLICABLE)


# ---------------------------------------------------------------------------
# Evidence package (task §3) — built entirely from evidence already
# persisted in Selection; nothing here invents a candidate fact. Every item
# carries a `source_reference` so the AI's cited evidence stays traceable
# back to something concrete already in the system (task §4).
# ---------------------------------------------------------------------------

def _resume_evidence(profile) -> list[EvidenceRef]:
    items: list[EvidenceRef] = []
    for w in profile.work_history:
        when = None
        if w.start_date:
            end_label = "present" if w.is_current else (w.end_date.strftime("%b %Y") if w.end_date else "unknown end")
            when = f"{w.start_date.strftime('%b %Y')} to {end_label}"
        text = f"{w.original_job_title or '(title not stated)'} at {w.employer or '(employer not stated)'}"
        if when:
            text += f", {when}"
        if w.role_family:
            text += f". Role family: {w.role_family}."
        if w.responsibilities:
            text += f" Responsibilities: {w.responsibilities}"
        items.append(EvidenceRef(
            source_type=psm.RESUME_FACT, evidence_text=text,
            source_reference=f"work_history: {w.employer or '(employer not stated)'}",
        ))
    for e in profile.education:
        text = f"{e.qualification or '(qualification not stated)'}"
        if e.institution:
            text += f" — {e.institution}"
        if e.completion_status:
            text += f" ({e.completion_status})"
        items.append(EvidenceRef(
            source_type=psm.RESUME_FACT, evidence_text=text,
            source_reference=f"education: {e.institution or '(institution not stated)'}",
        ))
    if profile.skills:
        items.append(EvidenceRef(
            source_type=psm.RESUME_FACT, evidence_text="Skills listed: " + ", ".join(profile.skills),
            source_reference="skills",
        ))
    for c in profile.certifications:
        items.append(EvidenceRef(
            source_type=psm.RESUME_FACT, evidence_text=f"Certification: {c.name or '(name not stated)'}"
            + (f" ({c.issuer})" if c.issuer else ""),
            source_reference="certifications",
        ))
    if profile.languages_detail:
        langs = ", ".join(
            f"{l.language}{f' ({l.proficiency})' if l.proficiency else ''}" for l in profile.languages_detail if l.language
        )
        if langs:
            items.append(EvidenceRef(source_type=psm.RESUME_FACT, evidence_text=f"Languages: {langs}", source_reference="languages"))
    if profile.summary:
        items.append(EvidenceRef(
            source_type=psm.RESUME_FACT, evidence_text=f"Résumé summary/objective: {profile.summary}",
            source_reference="summary",
        ))
    if profile.declared_availability:
        items.append(EvidenceRef(
            source_type=psm.RESUME_FACT, evidence_text=f"Declared availability: {profile.declared_availability}",
            source_reference="declared_availability",
        ))
    if profile.location:
        items.append(EvidenceRef(source_type=psm.RESUME_FACT, evidence_text=f"Location: {profile.location}", source_reference="location"))
    return items


def _application_evidence(application: m.Application) -> list[EvidenceRef]:
    text = (
        f"Target role: {application.target_role or '(unspecified)'}. "
        f"Applied: {application.applied_at.strftime('%Y-%m-%d') if application.applied_at else '(unknown date)'}. "
        f"Source: {application.candidate.source or '(unspecified)'}."
    )
    return [EvidenceRef(source_type=psm.APPLICATION, evidence_text=text, source_reference="application")]


def _prior_outcome_evidence_text(session: Session, prior_application_id: int) -> str:
    """GLOBAL_INTEGRITY_FIX_003 / C-2 §11 — the prior Application's outcome
    as evidence must come from the authoritative decision history, never
    the stale `Application.outcome` scalar. A historical Application that
    predates the Outcome Engine and only has a legacy value is still
    surfaced (task's own "legacy fallback may be used explicitly as
    historical compatibility evidence"), but explicitly labeled as legacy
    rather than presented as if it were a governed decision."""

    effective = outcome_svc.get_effective_application_outcome(session, prior_application_id)
    if effective.source == outcome_svc.SOURCE_GOVERNED_DECISION:
        return effective.label
    if effective.source == outcome_svc.SOURCE_LEGACY_FIELD:
        return f"{effective.label} (legacy pre-Outcome-Engine record, not a governed decision)"
    return "(none recorded)"


def _application_history_evidence(session: Session, application: m.Application) -> list[EvidenceRef]:
    prior = app_svc.list_prior_applications(session, application.id)
    if not prior:
        return []
    items = [EvidenceRef(
        source_type=psm.APPLICATION_HISTORY,
        evidence_text=(
            f"{len(prior)} prior application(s) by this person. Most recent prior target role: "
            f"{prior[-1].target_role or '(unspecified)'}; "
            f"recorded outcome: {_prior_outcome_evidence_text(session, prior[-1].id)}."
        ),
        source_reference="application_history",
    )]
    change_summary = app_svc.get_application_change_summary(session, application.id)
    if change_summary is not None:
        items.append(EvidenceRef(
            source_type=psm.APPLICATION_HISTORY, evidence_text=" ".join(change_summary.changes),
            source_reference="change_since_prior_application",
        ))
    items.extend(_candidate_flag_evidence(session, application))
    return items


def _candidate_flag_evidence(session: Session, application: m.Application) -> list[EvidenceRef]:
    """Task 5A-ALIGN §12 — a currently-active Candidate Flag (e.g. a prior
    "Training Check Not Passed") is a historical fact about this PERSON,
    exactly like prior-Application history — surfacing it here is what lets
    a restaurant configure a Criterion using it as a (possibly Hard
    Disqualifying) factor, without RF-One ever hard-coding that judgment
    itself. Grouped under APPLICATION_HISTORY rather than a new evidence
    source, since it is the same kind of "facts about this person from
    before this Application" category."""

    from . import candidate_flag_service as flag_svc

    flags = flag_svc.list_active_flags_for_application(session, application.id)
    if not flags:
        return []
    return [
        EvidenceRef(
            source_type=psm.APPLICATION_HISTORY,
            evidence_text=(
                f"Candidate Flag \"{flag.name}\" (scope {flag.scope}, effect {flag.operational_effect})"
                + (f": {flag.reason}" if flag.reason else "") + (f" — note: {flag.note}" if flag.note else "")
            ),
            source_reference=f"candidate_flag:{flag.id}",
        )
        for flag in flags
    ]


def _fit_assessment_evidence(session: Session, application: m.Application) -> list[EvidenceRef]:
    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
    if not fit_assessments:
        return []
    items: list[EvidenceRef] = []
    for ra in fa_svc.list_requirement_assessments(session, fit_assessments[0].id):
        if ra.effective_status not in (fam.EVIDENCED, fam.PARTIALLY_EVIDENCED, fam.CONFLICTING_EVIDENCE):
            continue
        name = ra.requirement_snapshot_item.name
        text = f"Requirement '{name}': {ra.effective_status}"
        if ra.evidence_items:
            snippet = ra.evidence_items[0].evidence_text or ra.evidence_items[0].explanation
            if snippet:
                text += f" — {snippet}"
        items.append(EvidenceRef(source_type=psm.FIT_ASSESSMENT, evidence_text=text, source_reference=f"requirement: {name}"))
    return items


def _signal_evidence(session: Session, application: m.Application) -> list[EvidenceRef]:
    items: list[EvidenceRef] = []
    for obs in sig_svc.list_observations(session, application.id):
        if obs.status not in (sm.DETECTED, sm.POSSIBLE, sm.CONFLICTING):
            continue
        text = f"Signal '{obs.signal_definition.name}' ({obs.signal_definition.signal_family}): {obs.status}"
        if obs.rationale:
            text += f" — {obs.rationale}"
        elif obs.detected_pattern:
            text += f" — {obs.detected_pattern}"
        items.append(EvidenceRef(source_type=psm.SELECTION_SIGNAL, evidence_text=text, source_reference=f"signal: {obs.signal_definition.name}"))
    return items


def _selezionatore_input_evidence(session: Session, application: m.Application) -> list[EvidenceRef]:
    items: list[EvidenceRef] = []
    for note in app_svc.list_notes(session, application.id):
        items.append(EvidenceRef(
            source_type=psm.SELEZIONATORE_INPUT, evidence_text=note.note_text,
            source_reference=f"note @ {note.created_at.strftime('%Y-%m-%d %H:%M') if note.created_at else '(undated)'}",
        ))
    return items


def build_evidence_package(session: Session, application: m.Application, criterion_snapshot: m.PrimaryScreeningCriterionSnapshot) -> dict[str, list[EvidenceRef]]:
    """Task §3 — gathers RESUME/APPLICATION/APPLICATION_HISTORY/
    FIT_ASSESSMENT/SELECTION_SIGNAL/SELEZIONATORE_INPUT evidence already
    persisted in Selection; never Phone/In-Person/Consistency data (task's
    own "must NOT depend on Phone or In-Person evidence for the initial
    run"). Gathers every available category regardless of the Criterion's
    own `evidence_sources_allowed` (that list is passed to the prompt as
    restaurant guidance, mirroring how `evidence_sources_allowed` is
    already documentation-only elsewhere in Selection, e.g.
    `signal_service.add_evidence` never filters by it either) — an
    incompletely-configured allow-list must never silently starve the
    evaluator of evidence that plainly exists."""

    profile = persistence.to_profile(application.candidate)
    package: dict[str, list[EvidenceRef]] = {
        psm.RESUME_FACT: _resume_evidence(profile),
        psm.APPLICATION: _application_evidence(application),
        psm.APPLICATION_HISTORY: _application_history_evidence(session, application),
        psm.FIT_ASSESSMENT: _fit_assessment_evidence(session, application),
        psm.SELECTION_SIGNAL: _signal_evidence(session, application),
        psm.SELEZIONATORE_INPUT: _selezionatore_input_evidence(session, application),
    }
    return {source: items for source, items in package.items() if items}


def _format_level_descriptions(criterion_snapshot: m.PrimaryScreeningCriterionSnapshot) -> str:
    lines = []
    for level in ("0", "1", "2", "3", "4"):
        desc = (criterion_snapshot.level_descriptions or {}).get(level)
        if desc:
            lines.append(f"  Level {level}: {desc}")
    return "\n".join(lines) if lines else "  (no level descriptions configured by the restaurant for this Criterion)"


def _format_evidence_package(package: dict[str, list[EvidenceRef]]) -> str:
    if not package:
        return "(no evidence available in Selection for this Application)"
    lines = []
    for source_type, items in package.items():
        lines.append(f"\n[{source_type}]")
        for item in items:
            lines.append(f"  - ({item.source_reference or source_type}) {item.evidence_text}")
    return "\n".join(lines)


def build_prompt(criterion_snapshot: m.PrimaryScreeningCriterionSnapshot, package: dict[str, list[EvidenceRef]]) -> str:
    allowed = ", ".join(criterion_snapshot.evidence_sources_allowed or []) or "(not restricted by the restaurant — use judgment)"

    return f"""You are assisting a restaurant's Selezionatore (hiring reviewer) with Primary Screening of a job Application. Evaluate exactly ONE restaurant-defined Screening Criterion, strictly against the evidence listed below. You must NEVER invent a candidate fact that is not present in that evidence.

CRITERION
Name: {criterion_snapshot.name}
Category: {criterion_snapshot.category or '(none)'}
Target role: {criterion_snapshot.target_role or '(any role)'}
Description: {criterion_snapshot.description or '(none provided)'}
Evaluation guidance: {criterion_snapshot.evaluation_guidance or '(none provided)'}
Supporting-evidence guidance: {criterion_snapshot.evidence_positive or '(none provided)'}
Contrary-evidence guidance: {criterion_snapshot.evidence_contrary or '(none provided)'}
Insufficient-evidence guidance: {criterion_snapshot.evidence_insufficient or '(none provided)'}
Evidence sources this restaurant considers most relevant for this Criterion: {allowed}

LEVEL MEANINGS — these are THIS restaurant's own definitions. Use ONLY these meanings; never invent a generic/universal meaning for the 0-4 scale:
{_format_level_descriptions(criterion_snapshot)}

APPLICATION EVIDENCE (grouped by source; you may not use anything outside this list):
{_format_evidence_package(package)}

INSTRUCTIONS
1. Decide which ONE of the restaurant's level descriptions above (0-4) is BEST SUPPORTED by the evidence.
2. Distinguish FACT (directly stated in the evidence) from DERIVED INFORMATION (a conservative, reasonable interpretation of stated facts, e.g. computing tenure from dates) from INFERENCE (a plausible but unproven guess) — never present an inference as if it were a fact, and never treat a weak, unrelated proxy (e.g. "worked as a Server for three years") as proof of a specific trait (e.g. reliability, attitude, honesty, motivation) unless the evidence actually and specifically supports that trait.
3. If two levels are both plausible and the evidence is weak, choose the LOWER, more conservative level and set confidence to LOW.
4. If no level is reasonably supportable from the evidence, return status "INSUFFICIENT_EVIDENCE" and level null. Do not guess, and do not default to level 0 merely because evidence is thin — INSUFFICIENT_EVIDENCE is the honest answer, not level 0.
5. If this Criterion plainly does not apply to this Application, return status "NOT_APPLICABLE".
6. Every evidence item you cite must correspond to something actually present in the APPLICATION EVIDENCE above (same source_reference/evidence_text) — never fabricate an evidence item, and if status is EVALUATED you must cite at least one.
7. Return ONLY the JSON object below. No extra commentary, no markdown code fences.

{{
  "status": "EVALUATED | INSUFFICIENT_EVIDENCE | NOT_APPLICABLE",
  "level": <0-4, or null unless status is EVALUATED>,
  "confidence": "HIGH | MEDIUM | LOW | UNKNOWN",
  "explanation": "<one or two concise sentences explaining the conclusion>",
  "evidence": [
    {{"source_type": "<one of: {', '.join(psm.EVIDENCE_SOURCES)}>", "source_reference": "<from the evidence above>", "evidence_text": "<from the evidence above>", "interpretation": "<how it relates to this Criterion>"}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Structured-output validation (task §7) — reject malformed/out-of-range
# output outright; never silently repair it into a usable evaluation.
# ---------------------------------------------------------------------------

def _validate_and_parse(raw: object) -> AIEvaluationResult:
    if not isinstance(raw, dict):
        raise ValueError("AI response was not a JSON object.")

    status = raw.get("status")
    if status not in _VALID_RESULT_STATUSES:
        raise ValueError(f"AI response status {status!r} is not one of {_VALID_RESULT_STATUSES}.")

    level_raw = raw.get("level")
    level: int | None
    if status == psm.EVALUATED:
        if isinstance(level_raw, bool) or not isinstance(level_raw, (int, float)):
            raise ValueError(f"AI response level {level_raw!r} is not a number.")
        if float(level_raw) != int(level_raw):
            raise ValueError(f"AI response level {level_raw!r} is not a whole number.")
        level = int(level_raw)
        if level not in psm.LEVEL_SCALE:
            raise ValueError(f"AI response level {level!r} is outside the 0-4 scale.")
    else:
        level = None

    confidence = raw.get("confidence")
    if confidence not in psm.CONFIDENCE_LEVELS:
        confidence = fam.CONFIDENCE_UNKNOWN

    explanation = raw.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("AI response explanation is missing or empty.")
    explanation = explanation.strip()

    raw_evidence = raw.get("evidence")
    if not isinstance(raw_evidence, list):
        raise ValueError("AI response 'evidence' is not a list.")

    evidence: list[EvidenceRef] = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        text = item.get("evidence_text")
        if not isinstance(text, str) or not text.strip():
            continue
        source_type = item.get("source_type")
        if source_type not in psm.EVIDENCE_SOURCES:
            source_type = psm.OTHER_EVIDENCE_SOURCE
        source_reference = item.get("source_reference")
        interpretation = item.get("interpretation")
        evidence.append(EvidenceRef(
            source_type=source_type, evidence_text=text.strip(),
            source_reference=str(source_reference)[:255] if source_reference else None,
            interpretation=str(interpretation) if interpretation else None,
        ))

    if status == psm.EVALUATED and not evidence:
        # Task §4/§17 — every material conclusion must be traceable to
        # evidence; an EVALUATED status with zero cited evidence is not
        # evidence-grounded, so it is downgraded, never accepted as-is.
        status = psm.INSUFFICIENT_EVIDENCE
        level = None
        explanation = f"{explanation} (Downgraded to insufficient evidence: no supporting evidence was cited.)"

    return AIEvaluationResult(status=status, level=level, confidence=confidence, explanation=explanation, evidence=evidence)


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------

def evaluate_criterion_with_ai(
    session: Session, application: m.Application, criterion_snapshot: m.PrimaryScreeningCriterionSnapshot,
    *, generate_json_fn=None,
) -> AIEvaluationResult:
    """Task §6/§8 — the entire generic-evaluator contract. Raises
    `AIEvaluationUnavailable` for every failure mode (no provider
    configured, request failure, malformed/out-of-contract output);
    returns a validated `AIEvaluationResult` otherwise. `generate_json_fn`
    defaults to `ai_client.generate_json` and exists as an injection seam
    for tests to supply a canned/failing response without needing live AI
    credentials — mirrors no existing convention because Task 3D/4A/4B had
    no AI-assisted evaluator yet; this is the first one, so this seam is
    new but follows the same "fall back, never fabricate" contract
    `parsing/resolve.py` already established for résumé parsing."""

    generate_json = generate_json_fn or ai_client.generate_json
    package = build_evidence_package(session, application, criterion_snapshot)
    prompt = build_prompt(criterion_snapshot, package)

    try:
        raw = generate_json(prompt)
    except ai_client.AIProviderUnavailable as exc:
        raise AIEvaluationUnavailable(str(exc)) from exc
    except Exception as exc:  # a custom generate_json_fn, network layer, etc.
        raise AIEvaluationUnavailable(f"AI evaluation call failed: {exc}") from exc

    try:
        return _validate_and_parse(raw)
    except ValueError as exc:
        raise AIEvaluationUnavailable(f"AI returned an invalid/malformed response: {exc}") from exc
