"""Interviews tab: the evidence collected in a candidate's interview (SELECTION_INTERVIEWS_001).

No new engine and no new table:
- the standard of a Role is Selection's existing interview content, only read: the phone-interview question
  definitions and the in-person interview sections (questions, role plays, practical tests) of that Role, the
  interview focus of the Role profile (`position_profiles`) and the practical scenarios named by the approved
  Interviews model; observation items about presentation or presence are never used (no judgement of
  appearance, accent or personality);
- the points to clarify come from the candidate's CV Selection SP analysis (To verify, red flags), or from
  Selection's existing proposal for Roles without an SP profile;
- answers already given in the AI interview (application page) are shown and reused, never asked twice;
- each candidate's interview is ONE `selection_workspace_proposals` row with source "INTERVIEW" (the pattern
  CV Selection SP already uses): the configuration copied from the standard for this candidate only, the
  answers, the six observation dimensions, the points to clarify and the scenarios, each with its evidence and
  the source of that evidence (in person, phone or AI interview). Status changes and saves are Selection events
  of the candidate, so they appear in the Evaluation history.
Nothing here decides: hiring stays in Decisions. Missing information is never turned into a concern.
"""

from __future__ import annotations

import hashlib
import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask import session as flask_session
from sqlalchemy import select, update

from rfone_data_store.selection import in_person_interview_service as ip_svc
from rfone_data_store.selection import phone_interview_service as pi_svc
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.selection.core import in_person_interview_model as ipm
from rfone_data_store.selection.industry.restaurant_templates import (
    seed_romes_flavours_in_person_interview_structure, seed_romes_flavours_phone_interview_questions,
)

from . import engine, position_profiles
from .routes import _job_candidates, _pc, _position, _restaurant_id, access_required, bp

SOURCE = "INTERVIEW"
CURRENT_CANDIDATE_KEY = "selection_current_candidate"

MODES = {"IN_PERSON": "In Person", "PHONE": "Phone", "AI": "AI Interview", "MIXED": "Mixed"}
EVIDENCE_SOURCES = {"IN_PERSON": "In person", "PHONE": "Phone", "AI": "AI interview"}
RATINGS = {"DEMONSTRATED": "Demonstrated", "PARTIAL": "Partially Demonstrated",
           "CONCERN": "Evidence of Concern", "NOT_ASSESSED": "Not Assessed"}
CLARIFY = {"CLARIFIED": "Clarified", "PARTIAL": "Partially Clarified", "OPEN": "Still Open"}
STATUS = {"NOT_STARTED": "Not started", "CONFIGURED": "Configured", "IN_PROGRESS": "In progress",
          "COMPLETED": "Completed"}

DIMENSIONS = [
    ("professional", "Professional Competence",
     "Knowledge and skills of the Role shown in concrete examples: tasks done, how, with what result."),
    ("problem_solving", "Problem Solving",
     "How the candidate handles an unexpected situation: what they notice, the options, what they did."),
    ("responsibility", "Responsibility",
     "Ownership of tasks and mistakes, reliability, trusted duties (opening, closing, cash, training others)."),
    ("teamwork", "Teamwork",
     "Working with colleagues and other stations: coordination, helping, handling disagreement."),
    ("communication", "Communication",
     "Clarity and listening in the conversation and in the Role situations (guests, kitchen, team). "
     "Content only: never accent or style of speech."),
    ("learning", "Learning & Adaptability",
     "New standards, systems or recipes learned; feedback accepted; habits changed to fit a workplace."),
]

# Scenarios named in the approved Interviews model (1 Nov 2026), added to the Role's existing role plays and
# practical tests; Line Cook has no in-person structure yet, so these are its scenarios.
MODEL_SCENARIOS = {
    "SERVER": [
        ("unhappy_guest", "Unhappy guest", "A guest is unhappy with the dish or the wait. What do you do and say?"),
        ("allergies", "Food allergies", "A guest tells you about a food allergy while ordering. Walk me through it."),
        ("many_tables", "Several tables at once", "Three tables need you at the same moment. How do you decide?"),
    ],
    "LINE_COOK": [
        ("rush_priority", "Priorities during a rush", "Tickets pile up at your station in a rush. How do you prioritize?"),
        ("food_safety", "Food safety", "You find a product past its date or held at the wrong temperature. What do you do?"),
        ("wrong_prep", "Wrong preparation", "A dish leaves your station prepared wrongly and comes back. What happens next?"),
    ],
}


def _key(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Role standard (read only)
# ---------------------------------------------------------------------------

def standard(db, role_code: str) -> dict:
    """The Role's standard questions and scenarios, from Selection's existing interview models."""
    restaurant_id = _restaurant_id(db)
    seed_romes_flavours_phone_interview_questions(db, restaurant_id=restaurant_id)
    seed_romes_flavours_in_person_interview_structure(db, restaurant_id=restaurant_id)
    questions, scenarios, seen = [], [], set()

    def add_question(qid, text, source):
        if text and _key(text) not in seen:
            seen.add(_key(text))
            questions.append({"id": qid, "text": text.strip(), "source": source, "active": True})

    for d in pi_svc.list_question_definitions(db, restaurant_id=restaurant_id, target_role=role_code, is_courtesy=False):
        add_question(f"p{d.id}", d.question_text, "Phone interview model")
    for section in ip_svc.list_section_definitions(db, restaurant_id=restaurant_id, target_role=role_code):
        for item in ip_svc.list_item_definitions(db, section_id=section.id):
            if item.item_type == ipm.QUESTION:
                add_question(f"i{item.id}", item.title_or_question, "In-person interview model")
            elif item.item_type in (ipm.ROLE_PLAY, ipm.PRACTICAL_TEST):
                scenarios.append({"id": f"s{item.id}", "title": item.title_or_question,
                                  "detail": item.scenario or item.objective or "", "source": "In-person interview model",
                                  "active": True})
            # OBSERVATION (presentation, presence) and COURTESY items are not used.
    profile = position_profiles.PROFILES.get(role_code)
    for i, text in enumerate((profile or {}).get("interview_focus", [])):
        add_question(f"f{i}", text, "Role profile")
    for sid, title, detail in MODEL_SCENARIOS.get(role_code, []):
        scenarios.append({"id": f"m-{sid}", "title": title, "detail": detail, "source": "Interviews model",
                          "active": True})
    return {"questions": questions, "scenarios": scenarios}


def points_to_clarify(db, position, pc) -> tuple[list[dict], list[dict]]:
    """(points to clarify, suggested questions) from the candidate's analysis, never as concerns."""
    from . import sp_routes
    points, suggested = [], []
    candidate = (sp_routes.dossier(db, position, pc.id) or {}).get("c")
    analysis = candidate.get("analysis") if candidate else None
    if analysis:
        for u in analysis.get("unknowns") or []:
            points.append({"id": "c" + _key(u), "text": u, "source": "CV Selection SP · To verify", "active": True})
        for f in analysis.get("flags") or []:
            text = f["flag"] + (f" — {f['question']}" if f.get("question") else "")
            points.append({"id": "c" + _key(text), "text": text, "source": "CV Selection SP · Red flag", "active": True})
        for q in analysis.get("questions") or []:
            suggested.append({"id": "a" + _key(q), "text": q, "source": "CV Selection SP", "active": True})
    else:
        lead = engine.leading_proposal(engine.current_proposals(db, pc.id))
        for q in (lead.payload.get("questions") if lead else None) or []:
            points.append({"id": "c" + _key(q), "text": q, "source": "Selection proposal", "active": True})
    return points, suggested


# ---------------------------------------------------------------------------
# The candidate's interview (one row)
# ---------------------------------------------------------------------------

def _row(db, pc_id: int) -> ps.Proposal | None:
    return db.scalars(select(ps.Proposal).where(ps.Proposal.position_candidate_id == pc_id,
                                                ps.Proposal.source == SOURCE,
                                                ps.Proposal.is_current.is_(True))).first()


def load(db, pc_id: int) -> dict:
    row = _row(db, pc_id)
    data = json.loads(row.payload_json) if row else {}
    data.setdefault("status", "NOT_STARTED")
    data.setdefault("mode", "IN_PERSON")
    for key in ("answers", "dimensions", "clarify", "scenarios"):
        data.setdefault(key, {})
    data.setdefault("log", [])
    return data


def store(db, pc_id: int, data: dict) -> None:
    row = _row(db, pc_id)
    payload = json.dumps(data, ensure_ascii=False, default=str)
    if row is None:
        db.add(ps.Proposal(position_candidate_id=pc_id, snapshot_id=0, fit_assessment_id=None, source=SOURCE,
                           group_code=data["status"], payload_json=payload, is_current=True, provider_label=None))
    else:
        db.execute(update(ps.Proposal).where(ps.Proposal.id == row.id)
                   .values(payload_json=payload, group_code=data["status"]))


def configuration(db, position, pc, data: dict) -> dict:
    """The candidate's configuration: the saved one, else a fresh copy of the Role standard and the analysis."""
    if data.get("config"):
        return data["config"]
    std = standard(db, position.role_code)
    points, suggested = points_to_clarify(db, position, pc)
    seen = {_key(q["text"]) for q in std["questions"]}
    questions = std["questions"] + [q for q in suggested if _key(q["text"]) not in seen]
    return {"questions": questions, "scenarios": std["scenarios"], "clarify": points}


def summary(config: dict, data: dict) -> dict:
    """Demonstrated / Needs Clarification / Concerns Documented, each line with the evidence recorded."""
    out = {"demonstrated": [], "clarify": [], "concerns": [], "not_assessed": []}
    items = [(name, data["dimensions"].get(did, {})) for did, name, _ in DIMENSIONS]
    items += [(f"Scenario: {s['title']}", data["scenarios"].get(s["id"], {})) for s in config["scenarios"] if s["active"]]
    for name, rec in items:
        line = {"name": name, "evidence": (rec.get("evidence") or "").strip(),
                "source": EVIDENCE_SOURCES.get(rec.get("src"), "")}
        rating = rec.get("rating") or "NOT_ASSESSED"
        {"DEMONSTRATED": out["demonstrated"], "PARTIAL": out["clarify"], "CONCERN": out["concerns"],
         "NOT_ASSESSED": out["not_assessed"]}[rating].append(line)
    for c in config["clarify"]:
        if not c["active"]:
            continue
        rec = data["clarify"].get(c["id"], {})
        if (rec.get("status") or "OPEN") != "CLARIFIED":   # still open is something to ask, never a concern
            out["clarify"].append({"name": c["text"], "evidence": (rec.get("evidence") or rec.get("answer") or "").strip(),
                                   "source": EVIDENCE_SOURCES.get(rec.get("src"), ""),
                                   "status": CLARIFY[rec.get("status") or "OPEN"]})
    return out


def _summary_line(s: dict) -> str:
    return (f"{len(s['demonstrated'])} demonstrated, {len(s['clarify'])} to clarify, "
            f"{len(s['concerns'])} concern(s) documented")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/posizioni/<int:position_id>/interviews")
@access_required
def interviews(db, actor, position_id):
    position = _position(db, actor, position_id)
    rows = _job_candidates(db, position)
    ids = {r["pc"].id for r in rows}
    pc_id = request.args.get("pc", type=int) or flask_session.get(CURRENT_CANDIDATE_KEY)
    pc = _pc(db, position, pc_id) if pc_id in ids else None
    context = {"actor": actor, "position": position, "rows": rows, "pc": pc, "section": "interviews",
               "crumbs": [("Interviews", None)], "can_edit": actor.can_edit(position), "MODES": MODES,
               "EVIDENCE_SOURCES": EVIDENCE_SOURCES, "RATINGS": RATINGS, "CLARIFY": CLARIFY,
               "INTERVIEW_STATUS": STATUS, "DIMENSIONS": DIMENSIONS}
    if pc is not None:
        flask_session[CURRENT_CANDIDATE_KEY] = pc.id
        data = load(db, pc.id)
        config = configuration(db, position, pc, data)
        context.update(data=data, config=config, summary=summary(config, data),
                       name=next(r["name"] for r in rows if r["pc"].id == pc.id),
                       ai_answers=engine.answers(db, pc.id), application=engine.candidate_application(db, pc.id),
                       standard_ids={q["id"] for q in standard(db, position.role_code)["questions"]})
    db.commit()
    return render_template("workspace/interviews.html", **context)


@bp.route("/posizioni/<int:position_id>/interviews/<int:pc_id>/config", methods=["POST"])
@access_required
def interview_config(db, actor, position_id, pc_id):
    """Configure Interview: only this candidate's copy changes; the Role standard is never written."""
    position = _position(db, actor, position_id, edit=True)
    pc = _pc(db, position, pc_id)
    data = load(db, pc.id)
    config = configuration(db, position, pc, data)
    form = request.form
    for q in config["questions"]:
        q["active"] = bool(form.get(f"q_active_{q['id']}"))
        text = (form.get(f"q_text_{q['id']}") or "").strip()
        if text:
            q["text"] = text[:500]
    n = 1 + sum(1 for q in config["questions"] if q["id"].startswith("x"))
    for line in (form.get("new_questions") or "").splitlines():
        if line.strip():
            config["questions"].append({"id": f"x{n}", "text": line.strip()[:500], "source": "Added for this candidate",
                                        "active": True})
            n += 1
    for c in config["clarify"]:
        c["active"] = bool(form.get(f"cl_active_{c['id']}"))
    for s in config["scenarios"]:
        s["active"] = bool(form.get(f"sc_active_{s['id']}"))
    data["config"] = config
    if data["status"] == "NOT_STARTED":
        data["status"] = "CONFIGURED"
    store(db, pc.id, data)
    ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="INTERVIEW", actor_id=actor.id,
                 actor_name=actor.name,
                 detail=f"Interview configured: {sum(q['active'] for q in config['questions'])} questions, "
                        f"{sum(c['active'] for c in config['clarify'])} points to clarify, "
                        f"{sum(s['active'] for s in config['scenarios'])} scenarios")
    db.commit()
    flash("Interview configured for this candidate. The Role standard is unchanged.")
    return redirect(url_for(".interviews", position_id=position.id, pc=pc.id))


@bp.route("/posizioni/<int:position_id>/interviews/<int:pc_id>/save", methods=["POST"])
@access_required
def interview_save(db, actor, position_id, pc_id):
    """Save the sheet (also saved automatically while typing); Complete / Reopen change the status."""
    position = _position(db, actor, position_id, edit=True)
    pc = _pc(db, position, pc_id)
    data = load(db, pc.id)
    config = configuration(db, position, pc, data)
    data["config"] = config
    form = request.form
    if form.get("mode") in MODES:
        data["mode"] = form["mode"]
    default_src = data["mode"] if data["mode"] in EVIDENCE_SOURCES else "IN_PERSON"

    def src(name):
        value = form.get(name)
        return value if value in EVIDENCE_SOURCES else default_src

    for q in config["questions"]:
        if f"q_{q['id']}_answer" in form:
            data["answers"][q["id"]] = {"answer": form[f"q_{q['id']}_answer"].strip(), "src": src(f"q_{q['id']}_src")}
    for did, _, _ in DIMENSIONS:
        if f"dim_{did}_evidence" in form:
            rating = form.get(f"dim_{did}_rating")
            data["dimensions"][did] = {"rating": rating if rating in RATINGS else "NOT_ASSESSED",
                                       "evidence": form[f"dim_{did}_evidence"].strip(), "src": src(f"dim_{did}_src")}
    for c in config["clarify"]:
        if f"cl_{c['id']}_answer" in form:
            status = form.get(f"cl_{c['id']}_status")
            data["clarify"][c["id"]] = {"status": status if status in CLARIFY else "OPEN",
                                        "answer": form[f"cl_{c['id']}_answer"].strip(),
                                        "evidence": form.get(f"cl_{c['id']}_evidence", "").strip(),
                                        "src": src(f"cl_{c['id']}_src")}
    for s in config["scenarios"]:
        if f"sc_{s['id']}_answer" in form:
            rating = form.get(f"sc_{s['id']}_rating")
            data["scenarios"][s["id"]] = {"rating": rating if rating in RATINGS else "NOT_ASSESSED",
                                          "answer": form[f"sc_{s['id']}_answer"].strip(),
                                          "evidence": form.get(f"sc_{s['id']}_evidence", "").strip(),
                                          "src": src(f"sc_{s['id']}_src")}
    action = form.get("action")
    now = ps.utcnow().isoformat(timespec="seconds")
    data["updated_at"], data["updated_by"] = now, actor.name
    data.setdefault("started_at", now)
    if action == "complete":
        data["status"], data["completed_at"] = "COMPLETED", now
    elif action == "reopen" or data["status"] in ("NOT_STARTED", "CONFIGURED"):
        data["status"] = "IN_PROGRESS"
    autosave = form.get("autosave") == "1"
    if not autosave:
        data["log"].append({"at": now, "by": actor.name, "mode": data["mode"], "action": action or "save"})
    store(db, pc.id, data)
    if not autosave:
        s = summary(config, data)
        detail = {"complete": f"Interview completed ({MODES[data['mode']]}, {actor.name}): {_summary_line(s)}",
                  "reopen": f"Interview reopened ({actor.name})"}.get(
            action, f"Interview saved ({MODES[data['mode']]}, {actor.name}): {_summary_line(s)}")
        ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="INTERVIEW", actor_id=actor.id,
                     actor_name=actor.name, detail=detail)
    db.commit()
    if autosave:
        return jsonify({"ok": True, "status": STATUS[data["status"]]})
    flash({"complete": "Interview completed. The decision stays in Decisions.",
           "reopen": "Interview reopened."}.get(action, "Interview saved."))
    return redirect(url_for(".interviews", position_id=position.id, pc=pc.id) + "#summary")


def status_of(db, pc_id: int) -> str:
    return STATUS[load(db, pc_id)["status"]]
