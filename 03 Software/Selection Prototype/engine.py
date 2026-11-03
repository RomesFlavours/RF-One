"""Glue between a Position and the existing Selection services.

Import: `import_pipeline.import_one_resume` + `application_service`
(duplicate document check, identity resolution, name-match suggestions).
Analysis: `fit_assessment_service` against the position's APPROVED
requirement snapshot, plus `analysis.analyze_candidate` (indicators, flags,
questions). The three proposal groups are derived from the requirement
statuses by ONE transparent rule (`propose_group`), used both for the
rule-based reading and for the AI reading — the AI only reads evidence, it
never decides the group, and nobody is ever excluded automatically.
"""

from __future__ import annotations

import json
import os

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.selection import application_service as app_svc
from rfone_data_store.selection import fit_assessment_service as fa_svc
from rfone_data_store.selection import persistence
from rfone_data_store.selection import requirements_service as req_svc
from rfone_data_store.selection.analysis import analyze_candidate
from rfone_data_store.selection.core import fit_assessment_model as fam
from rfone_data_store.selection.core import requirement_model as rm
from rfone_data_store.selection.core.resume_source import LOCAL_UPLOAD
from rfone_data_store.selection.import_pipeline import COMPLETED, DUPLICATE, PARTIAL, import_one_resume
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
from rfone_data_store.selection.parsing.dedup import compute_content_hash
from rfone_data_store.selection.parsing.text_extraction import SUPPORTED_EXTENSIONS, extract_text

import ai_adapter
import prototype_store as ps

STATUS_LABELS = {
    fam.EVIDENCED: "Dimostrato nel CV",
    fam.PARTIALLY_EVIDENCED: "Dimostrato in parte",
    fam.NOT_EVIDENCED: "Non dimostrato nel CV (informazione mancante, non prova di assenza)",
    fam.CONFLICTING_EVIDENCE: "Evidenze contraddittorie",
    fam.NOT_ASSESSED_AT_THIS_STAGE: "Non valutabile dal CV: da verificare al colloquio",
}
CRITICALITY_LABELS = {
    rm.MUST_HAVE: "Essenziale", rm.PREFERRED: "Preferenziale", rm.OPTIONAL: "Facoltativo",
    rm.DISQUALIFIER: "Condizione da verificare",
}
TRAINABILITY_LABELS = {
    rm.TRAINABLE: "Si può formare", rm.PARTIALLY_TRAINABLE: "In parte formabile",
    rm.NOT_TRAINABLE: "Non formabile", rm.TRAINABILITY_UNKNOWN: "Non indicato",
}
DEFAULT_STAGES = [rm.RESUME, rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_cv(session, *, documents, restaurant_id: int, position: ps.Position, file_storage, channel: str,
              actor_id: int | None, actor_name: str, declared: dict | None = None) -> dict:
    """One file -> one PositionCandidate. Never raises; returns a result dict."""
    filename = file_storage.filename or "(file senza nome)"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {"filename": filename, "status": "FAILED", "message": "Formato non supportato (usare PDF, DOCX o TXT)."}
    try:
        staged = documents.stage(file_storage, filename)
        raw_text = extract_text(staged.local_path, ext)
    except Exception:
        return {"filename": filename, "status": "FAILED", "message": "Impossibile leggere il file."}

    result = import_one_resume(
        session, restaurant_id=restaurant_id, source_type=LOCAL_UPLOAD, original_filename=filename,
        storage_path=staged.storage_path, raw_text=raw_text, content_hash=compute_content_hash(raw_text, filename),
    )
    application, note = None, None
    if result.status == DUPLICATE and result.duplicate_of_raw_resume_id is not None:
        application, created = app_svc.application_for_known_resume(
            session, raw_resume_id=result.duplicate_of_raw_resume_id, restaurant_id=restaurant_id,
            target_role=position.role_code)
        note = "CV già presente nell'archivio: riutilizzato il documento esistente."
        session.commit()
    elif result.status in (COMPLETED, PARTIAL) and result.candidate_id is not None:
        application = app_svc.create_application(
            session, candidate_id=result.candidate_id, restaurant_id=restaurant_id, target_role=position.role_code)
        session.commit()
    if application is None:
        return {"filename": filename, "status": "FAILED", "message": result.error or "Importazione non riuscita."}

    existing = session.scalars(select(ps.PositionCandidate).where(
        ps.PositionCandidate.position_id == position.id,
        ps.PositionCandidate.application_id == application.id)).first()
    if existing is not None:
        return {"filename": filename, "status": "DUPLICATE", "position_candidate_id": existing.id,
                "message": "Questo CV è già tra i candidati della posizione: nessun nuovo inserimento."}

    if result.status == PARTIAL:
        note = ((note or "") + " Lettura del CV parziale: alcune parti vanno verificate.").strip()
    declared = declared or {}
    pc = ps.PositionCandidate(
        position_id=position.id, application_id=application.id, candidate_id=application.candidate_id,
        channel=channel, added_by_account_id=actor_id, import_note=note,
        declared_name=declared.get("name"), declared_email=declared.get("email"),
        declared_phone=declared.get("phone"))
    session.add(pc)
    session.flush()
    candidate = persistence.get_candidate(session, application.candidate_id)
    ps.log_event(session, position_id=position.id, position_candidate_id=pc.id, kind="CANDIDATE_ADDED",
                 detail=f"Aggiunto {candidate.full_name or filename} ({filename})", actor_id=actor_id,
                 actor_name=actor_name)
    session.commit()
    if position.approved_snapshot_id:
        analyze(session, position, pc, actor_id=actor_id, actor_name=actor_name)
    return {"filename": filename, "status": "OK", "position_candidate_id": pc.id,
            "name": candidate.full_name, "message": note, "pc": pc}


# ---------------------------------------------------------------------------
# Duplicates / same person
# ---------------------------------------------------------------------------

def duplicate_notes(session, pc: ps.PositionCandidate) -> list[str]:
    notes = []
    application = app_svc.get_application(session, pc.application_id)
    if application is None:
        return notes
    others = [a for a in app_svc.list_applications_for_person(session, application.person_id) if a.id != application.id]
    if others:
        notes.append(f"Stessa persona (email o telefono identici) di {len(others)} altra/e candidatura/e già in archivio.")
    pending = session.scalars(select(m.PersonMatchCandidate).where(
        m.PersonMatchCandidate.application_id == application.id,
        m.PersonMatchCandidate.status == "PENDING")).all() if hasattr(m.PersonMatchCandidate, "status") else []
    for match in pending:
        person = session.get(m.CandidatePerson, match.suggested_person_id)
        notes.append(f"Possibile duplicato: nome simile a {person.full_name if person else 'altra persona'} "
                     f"({match.confidence}). Da verificare.")
    return notes


# ---------------------------------------------------------------------------
# Analysis and proposal
# ---------------------------------------------------------------------------

def propose_group(items: list[dict], reading_uncertain: bool) -> tuple[str, list[str]]:
    """items: [{"criticality", "status", "name"}]. Returns (group, reasons)."""
    essentials = [i for i in items if i["criticality"] == rm.MUST_HAVE]
    conditions = [i for i in items if i["criticality"] == rm.DISQUALIFIER
                  and i["status"] in (fam.EVIDENCED, fam.PARTIALLY_EVIDENCED)]
    not_shown = [i for i in essentials if i["status"] == fam.NOT_EVIDENCED]
    unclear = [i for i in essentials if i["status"] in (fam.PARTIALLY_EVIDENCED, fam.CONFLICTING_EVIDENCE)]
    shown = [i for i in essentials if i["status"] == fam.EVIDENCED]
    reasons = []
    if not essentials:
        return ps.G_DEEPEN, ["Nessun requisito essenziale approvato: la proposta non può distinguere i candidati."]
    if not_shown:
        reasons.append("Requisiti essenziali non dimostrati nel CV: " + "; ".join(i["name"] for i in not_shown)
                       + ". È un'informazione mancante, non una prova di assenza: si può verificare col candidato.")
        if reading_uncertain:
            reasons.append("La lettura del CV è incerta in alcune parti: controllare il documento originale.")
        return ps.G_ESSENTIALS_NOT_SHOWN, reasons
    if unclear:
        reasons.append("Essenziali dimostrati solo in parte o in modo contraddittorio: "
                       + "; ".join(i["name"] for i in unclear) + ".")
    if conditions:
        reasons.append("Condizioni da verificare con il candidato: " + "; ".join(i["name"] for i in conditions) + ".")
    if reading_uncertain:
        reasons.append("Lettura del CV incerta in alcune parti: controllare il documento originale.")
    if unclear or conditions or reading_uncertain or not shown:
        if not shown and not unclear:
            reasons.append("Gli essenziali non sono valutabili dal CV: vanno verificati al colloquio.")
        return ps.G_DEEPEN, reasons
    to_verify = [i for i in essentials if i["status"] == fam.NOT_ASSESSED_AT_THIS_STAGE]
    reasons.append("Tutti gli essenziali valutabili dal CV sono dimostrati: " + "; ".join(i["name"] for i in shown) + ".")
    if to_verify:
        reasons.append("Da verificare al colloquio: " + "; ".join(i["name"] for i in to_verify) + ".")
    return ps.G_INTERVIEW, reasons


def _fit_assessment_for(session, candidate_id: int, snapshot_id: int) -> m.FitAssessment:
    for fa in fa_svc.list_fit_assessments_for_candidate(session, candidate_id):
        if fa.requirement_set_snapshot_id == snapshot_id:
            return fa_svc.generate_resume_stage_assessment(session, fa.id)
    return fa_svc.create_fit_assessment_from_snapshot(session, candidate_id=candidate_id, snapshot_id=snapshot_id)


def candidate_view(session, pc: ps.PositionCandidate, position: ps.Position):
    candidate = persistence.get_candidate(session, pc.candidate_id)
    profile = persistence.to_profile(candidate)
    return candidate, profile, analyze_candidate(profile, target_role=position.role_code)


def _reading_uncertain(profile) -> bool:
    return any((w.structure_confidence or "").upper() == "LOW" for w in profile.work_history)


def _questions_from_analysis(view, items: list[dict]) -> list[str]:
    questions = []
    for item in items:
        if item["criticality"] in (rm.MUST_HAVE, rm.PREFERRED) and item["status"] != fam.EVIDENCED:
            questions.append(f"Verificare: {item['name']}")
    for flag in view.flags:
        if flag.suggested_question:
            questions.append(flag.suggested_question)
    questions += list(view.coordination_questions or [])
    seen, unique = set(), []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:12]


def analyze(session, position: ps.Position, pc: ps.PositionCandidate, *, actor_id: int | None, actor_name: str) -> None:
    snapshot_id = position.approved_snapshot_id
    if not snapshot_id:
        return
    fa = _fit_assessment_for(session, pc.candidate_id, snapshot_id)
    candidate, profile, view = candidate_view(session, pc, position)
    uncertain = _reading_uncertain(profile)

    items = []
    for ra in sorted(fa.requirement_assessments, key=lambda r: r.display_order):
        item = ra.requirement_snapshot_item
        items.append({
            "id": item.id, "name": item.name, "description": item.description, "criticality": item.criticality,
            "status": ra.effective_status,
            "evidence": [{"text": e.evidence_text, "ref": e.source_reference, "relationship": e.evidence_relationship,
                          "explanation": e.explanation} for e in ra.evidence_items],
        })
    group, reasons = propose_group(items, uncertain)
    _store_proposal(session, pc, snapshot_id, fa.id, ps.SOURCE_RULES, group, {
        "items": items, "reasons": reasons, "questions": _questions_from_analysis(view, items),
        "reading_uncertain": uncertain,
    }, "Fit Assessment e analisi CV esistenti di Selection")

    if ai_adapter.POLICY.cv_ai_authorized:
        raw = session.get(m.RawResume, candidate.raw_resume_id) if candidate.raw_resume_id else None
        try:
            result = ai_adapter.evaluate_candidate(
                requirements=[{k: i[k] for k in ("id", "name", "description", "criticality")} for i in items],
                cv_text=raw.raw_text if raw else "", answers_text=answers_text(session, pc.id))
            ai_items = []
            for i in items:
                r = result["requirements"][i["id"]]
                ai_items.append({"id": i["id"], "name": i["name"], "criticality": i["criticality"],
                                 "status": r["status"], "quotes": r["quotes"], "explanation": r["explanation"],
                                 "dropped_quotes": r["dropped_quotes"]})
            ai_group, ai_reasons = propose_group(ai_items, uncertain)
            _store_proposal(session, pc, snapshot_id, fa.id, ps.SOURCE_AI, ai_group, {
                "items": ai_items, "reasons": ai_reasons, "questions": result["interview_questions"],
            }, ai_adapter.POLICY.provider_label)
        except AIProviderUnavailable as exc:
            ps.log_event(session, position_id=position.id, position_candidate_id=pc.id, kind="AI_UNAVAILABLE",
                         detail=f"Valutazione AI non eseguita: {exc}", actor_id=actor_id, actor_name=actor_name)
    ps.log_event(session, position_id=position.id, position_candidate_id=pc.id, kind="ANALYZED",
                 detail=f"Analizzato {candidate.full_name or 'candidato'}: proposta «{ps.GROUP_LABELS[group]}»",
                 actor_id=actor_id, actor_name=actor_name)
    session.commit()


def _store_proposal(session, pc, snapshot_id, fa_id, source, group, payload, provider_label) -> None:
    for old in session.scalars(select(ps.Proposal).where(
            ps.Proposal.position_candidate_id == pc.id, ps.Proposal.source == source,
            ps.Proposal.is_current.is_(True))).all():
        old.is_current = False
    session.add(ps.Proposal(position_candidate_id=pc.id, snapshot_id=snapshot_id, fit_assessment_id=fa_id,
                            source=source, group_code=group, payload_json=json.dumps(payload, default=str),
                            provider_label=provider_label))
    session.flush()


def current_proposals(session, pc_id: int) -> dict[str, ps.Proposal]:
    rows = session.scalars(select(ps.Proposal).where(ps.Proposal.position_candidate_id == pc_id,
                                                     ps.Proposal.is_current.is_(True))).all()
    return {p.source: p for p in rows}


def leading_proposal(proposals: dict[str, ps.Proposal]) -> ps.Proposal | None:
    """The AI reading when available (it reads the full text), else the rule-based one."""
    return proposals.get(ps.SOURCE_AI) or proposals.get(ps.SOURCE_RULES)


def current_decision(session, pc_id: int) -> ps.Decision | None:
    decision = session.scalars(select(ps.Decision).where(ps.Decision.position_candidate_id == pc_id)
                               .order_by(ps.Decision.id.desc())).first()
    return None if decision is None or decision.decision == ps.D_UNDECIDED else decision


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

def requirements_changed_since_approval(session, position: ps.Position) -> bool:
    if not position.approved_snapshot_id:
        return False
    snapshot = req_svc.get_snapshot(session, position.approved_snapshot_id)
    requirement_set = req_svc.get_requirement_set(session, position.requirement_set_id)
    return snapshot is not None and requirement_set is not None and snapshot.version != requirement_set.version


def active_requirements(session, position: ps.Position) -> list[m.Requirement]:
    # A fresh query, not `requirement_set.requirements` (stale after add_requirement; see requirements_service).
    return list(session.scalars(select(m.Requirement).where(
        m.Requirement.requirement_set_id == position.requirement_set_id, m.Requirement.is_active.is_(True))
        .order_by(m.Requirement.display_order)).all())


# ---------------------------------------------------------------------------
# Interview answers
# ---------------------------------------------------------------------------

def candidate_application(session, pc_id: int) -> ps.CandidateApplication | None:
    return session.scalars(select(ps.CandidateApplication).where(
        ps.CandidateApplication.position_candidate_id == pc_id)).first()


def answers(session, pc_id: int) -> list[ps.Answer]:
    application = candidate_application(session, pc_id)
    if application is None:
        return []
    return list(session.scalars(select(ps.Answer).where(ps.Answer.candidate_application_id == application.id)
                                .order_by(ps.Answer.question_index)).all())


def answers_text(session, pc_id: int) -> str:
    return "\n".join(f"Q: {a.question_text}\nA: {a.answer_text}" for a in answers(session, pc_id))


# ---------------------------------------------------------------------------
# Standard English messages (used when AI drafting is not active)
# ---------------------------------------------------------------------------

STANDARD_MESSAGES = {
    "INVITE": ("Hi [Candidate first name],\n\nThank you for applying for the {title} position at {location}. "
               "We would like to meet you for a {facts}.\nPlease reply to confirm.\n\nBest regards,\n[Manager name]"),
    "SLOTS": ("Hi [Candidate first name],\n\nThank you for applying for the {title} position at {location}. "
              "We would like to schedule an interview. Please choose the time that works best for you here: {facts}\n\n"
              "Best regards,\n[Manager name]"),
    "REJECTION": ("Hi [Candidate first name],\n\nThank you for your interest in the {title} position at {location} "
                  "and for the time you gave us. After careful consideration, we have decided to move forward with "
                  "other candidates at this time. We wish you all the best.\n\nBest regards,\n[Manager name]"),
    "HIRE": ("Hi [Candidate first name],\n\nWe are happy to let you know that we would like to offer you the {title} "
             "position at {location}. {facts}\nPlease reply to confirm, and we will share the next steps.\n\n"
             "Best regards,\n[Manager name]"),
    "ON_HOLD": ("Hi [Candidate first name],\n\nThank you for applying for the {title} position at {location}. "
                "Your application is still being considered and we will get back to you soon.\n\n"
                "Best regards,\n[Manager name]"),
}


def fill_placeholders(body: str, *, first_name: str | None, manager_name: str) -> str:
    return body.replace("[Candidate first name]", first_name or "there").replace("[Manager name]", manager_name)


# ---------------------------------------------------------------------------
# Comparison (no new scoring: the stored requirement statuses side by side)
# ---------------------------------------------------------------------------

def comparison(session, position: ps.Position, pcs: list[ps.PositionCandidate]) -> dict:
    columns, requirement_names = [], {}
    for pc in pcs:
        candidate, profile, view = candidate_view(session, pc, position)
        proposals = current_proposals(session, pc.id)
        lead = leading_proposal(proposals)
        statuses = {}
        if lead:
            for item in lead.payload["items"]:
                requirement_names[item["id"]] = (item["name"], item["criticality"])
                statuses[item["id"]] = item["status"]
        latest = sorted(profile.work_history, key=lambda w: (not w.is_current, -(w.start_date.timestamp() if w.start_date else 0)))
        columns.append({
            "pc": pc, "name": candidate.full_name or pc.declared_name or "(nome non letto)", "proposal": lead,
            "statuses": statuses, "decision": current_decision(session, pc.id),
            "roles": [f"{w.original_job_title or '?'} · {w.employer or '?'}" for w in latest[:3]],
            "direct_months": view.breakdown.direct_role_months if view.role_config else None,
            "answers": {a.question_text: a.answer_text for a in answers(session, pc.id)},
        })
    questions = []
    for col in columns:
        for q in col["answers"]:
            if q not in questions:
                questions.append(q)
    return {"columns": columns, "requirements": requirement_names, "questions": questions}
