"""CV Selection SP inside Selection: the Applications tab of a Job (CV upload, analysis, preselection ranking).

Everything is Selection's own: the position (`selection_workspace_positions`), the candidates, documents and
duplicate checks (`engine.import_cv`: exact duplicate by content hash, same person by email/phone, similar
names to verify), the RF-One login, permissions and CSRF of the `positions` blueprint. No new table:
- SP's requirement versions, manual order and upload batches live in the position's existing context
  document (`organization_context_json`, key "sp");
- the analysis queue is durable (`sp_queue`: "SP_JOB" rows of the same proposals table);
- each SP analysis is a `selection_workspace_proposals` row with source "SP" (payload: the verified analysis,
  the requirement version, the model), the newest per candidate being current, like Selection's own proposals.

Successive uploads only add candidates. Only CVs without a current analysis for the approved requirement
version are sent to Bedrock; an analysis made with an older version stays visible and is marked for update.
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask import session as flask_session
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.selection import persistence
from rfone_data_store.selection import workspace_models as ps

from . import cv_delete, engine, position_settings, sp_queue, pdl_rule_application
from .routes import _cfg, _pc, _position, _restaurant_id, access_required, bp, external_url
from .sp import profiles as spp
from .sp import ranking as sp_ranking
from .sp import rules as sp_rules

SOURCE = sp_queue.RESULT
# The CV list's last change (CVs just uploaded or the CV just deleted), handed once to the page, which keeps
# the CVs added during its browser-tab session marked NEW.
CV_LIST_KEY = "sp_cv_list_change"
AI_OFF = ("AI résumé evaluation is off for this Job: turn on “AI résumé and answer evaluation” in the Job "
          "(Selection tab) to analyze.")


# ---------------------------------------------------------------------------
# State in the position's context document
# ---------------------------------------------------------------------------

def has_profile(position) -> bool:
    return position.role_code in spp.ROLES


def state(position) -> dict:
    sp = position_settings.context(position).get("sp")
    if not isinstance(sp, dict):
        sp = {"requirements_draft": spp.default_requirements(position.role_code), "editing": False, "versions": [],
              "approved": None, "manual_order": [], "uploads": [], "run": None}
    sp.setdefault("rules", None)        # the Job's evaluation rules in force (set when the Job is confirmed)
    sp.setdefault("rules_draft", None)  # the Job's rule choices being edited
    return sp


def save_state(position, sp: dict) -> None:
    data = position_settings.context(position)
    data["sp"] = sp
    position.organization_context_json = json.dumps(data, ensure_ascii=False, default=str)


def reset_to_role_standard(position) -> dict:
    """A new Job, or a draft Job whose Role changed: a copy of the Role's standard requirements and rules.
    The standard itself (`position_profiles`, `sp.rules`) is only read."""
    uploads = position_settings.context(position).get("sp", {}).get("uploads", []) \
        if isinstance(position_settings.context(position).get("sp"), dict) else []
    sp = {"requirements_draft": spp.default_requirements(position.role_code), "editing": False, "versions": [],
          "approved": None, "manual_order": [], "uploads": uploads, "run": None, "rules": None,
          "rules_draft": sp_rules.defaults(position.role_code)}
    save_state(position, sp)
    return sp


def active_requirements(draft: list[dict]) -> list[dict]:
    """The requirements switched on for the Job (a requirement without the switch is on)."""
    return [r for r in draft if r.get("active", True)]


def approve(position, sp: dict, actor_name: str) -> str | None:
    """Approve the Job's requirement draft and put its rule choices in force. A new requirement version is
    created only when the switched-on requirements changed, so unchanged requirements never cause a new AI
    reading. Returns an error message, or None when approved."""
    chosen = [{k: v for k, v in r.items() if k != "active"} for r in active_requirements(sp["requirements_draft"])]
    if not any(r["criticality"] == spp.MUST_HAVE for r in chosen):
        return "Mark at least one active requirement as Must-have: the ranking groups depend on it."
    sp["rules"] = sp_rules.effective(position.role_code, sp.get("rules_draft"))
    current = sp.get("approved")
    if current and current["requirements"] == chosen:
        sp["editing"] = False
        return None
    version = len(sp["versions"]) + 1
    approved = {"version": version, "approved_at": ps.utcnow().isoformat(), "approved_by": actor_name,
                "requirements": json.loads(json.dumps(chosen))}
    sp["versions"].append(approved)
    sp["approved"], sp["editing"], sp["manual_order"] = approved, False, []
    return None


@bp.before_app_request
def _sp_kick():
    """Every request to Selection (pages, candidates, the per-minute mail-outbox claim) keeps the queue moving."""
    sp_queue.kick()


@bp.app_context_processor
def _sp_globals():
    return {"SP_ROLES": spp.ROLES, "local_time": _local_time, "CRIT": spp.CRITICALITY_LABELS,
            "level_label": sp_ranking.spp_level, "summary": sp_ranking.summary}


# ---------------------------------------------------------------------------
# Candidates and analyses (Selection's own rows)
# ---------------------------------------------------------------------------

def _results(db, position) -> dict[int, ps.Proposal]:
    rows = db.scalars(select(ps.Proposal).join(ps.PositionCandidate, ps.Proposal.position_candidate_id ==
                                               ps.PositionCandidate.id)
                      .where(ps.PositionCandidate.position_id == position.id, ps.Proposal.source == SOURCE,
                             ps.Proposal.is_current.is_(True))).all()
    return {p.position_candidate_id: p for p in rows}


def last_adding_upload(sp: dict) -> dict | None:
    """The most recent upload that added candidates: an upload of exact duplicates only adds nobody, and must not
    hide the candidates the previous upload brought in."""
    return next((u for u in reversed(sp["uploads"]) if u["imported"]), None)


def candidates(db, position, sp) -> list[dict]:
    approved = sp.get("approved")
    results = _results(db, position)
    last = set((last_adding_upload(sp) or {}).get("imported", []))
    batch_of = {pc_id: u["n"] for u in sp["uploads"] for pc_id in u["imported"]}
    out = []
    pcs = db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                     .order_by(ps.PositionCandidate.added_at)).all()
    jobs = sp_queue.active_jobs(db, [pc.id for pc in pcs])
    blocked = cv_delete.blockers(db, pcs)
    for pc in pcs:
        candidate = persistence.get_candidate(db, pc.candidate_id)
        raw = db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
        prop = results.get(pc.id)
        payload = json.loads(prop.payload_json) if prop else {}
        version = payload.get("version")
        application = engine.candidate_application(db, pc.id)
        decision = engine.current_decision(db, pc.id)
        if pc.id in jobs:
            status = "ANALYZING"
        elif application is not None and application.status != ps.A_SUBMITTED:
            status = "IN_PROGRESS"        # application page / RMAED: analyzed only once the application is complete
        elif payload.get("analysis"):
            status = "DONE" if approved and version == approved["version"] else "OUTDATED"
        elif payload.get("error"):
            status = "ERROR"
        else:
            status = "WAITING"
        out.append({"pc": pc, "id": pc.id, "filename": (raw.original_filename if raw else None) or f"CV {pc.id}",
                    "uploaded_at": pc.added_at.isoformat(), "name": candidate.full_name if candidate else None,
                    "analysis": sp_rules.apply(payload.get("analysis"), position.role_code, sp.get("rules")),
                    "analyzed_version": version, "decision": decision,
                    "rejected": bool(decision and decision.decision == ps.D_NOT_SELECTED),
                    "analyzed_at": payload.get("analyzed_at"), "model": payload.get("model"),
                    "error": payload.get("error"), "status": status, "new": pc.id in last,
                    "batch": batch_of.get(pc.id), "channel": pc.channel,
                    "duplicate_note": " ".join(engine.duplicate_notes(db, pc)) or None,
                    "delete_blocked": "; ".join(blocked[pc.id]) or None})
    return pdl_rule_application.apply(db, position, out)


def _queue(db, sp, pc_ids: list[int]) -> int:
    """Put these CVs in the durable SP queue for the approved version. Returns how many were queued."""
    return sp_queue.enqueue(db, pc_ids, sp["approved"]["version"])


def _ai_allowed(position) -> bool:
    return position_settings.bind(position).allows("cv_evaluation")


def _to_analyze(cands: list[dict]) -> list[int]:
    return [c["id"] for c in cands if c["status"] in ("WAITING", "ERROR", "OUTDATED")]


def ranked(cands: list[dict], sp: dict) -> list[dict]:
    approved = sp.get("approved")
    if not approved:
        return []
    analyzed = [dict(c) for c in cands if c["analysis"]]
    rows = pdl_rule_application.order(sp_ranking.rank(analyzed, approved["requirements"], sp.get("manual_order")))
    for i, row in enumerate(rows, 1):
        row['rank'] = i
        if (row.get('pdl_result') or {}).get('active'):
            row['why_ahead'] = 'Ordine dalle regole PDL: UnFit in fondo, poi priorità decrescente; a parità resta l’ordine precedente.'
    return rows


# ---------------------------------------------------------------------------
# Upload (from the row of the position on the Selection positions page)
# ---------------------------------------------------------------------------

def _resume_rows(db, position):
    """Display extracted facts only; never build candidate assessments."""
    rows = []
    pcs = db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                     .order_by(ps.PositionCandidate.added_at.desc(), ps.PositionCandidate.id.desc()))
    for pc in pcs:
        candidate = persistence.get_candidate(db, pc.candidate_id)
        raw = db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
        rows.append({"pc":pc, "name":(candidate.full_name if candidate else None) or pc.declared_name or "Nome non estratto",
            "filename":raw.original_filename if raw else (candidate.source_file if candidate else ""),
            "original_available": bool(raw and _cfg.documents.exists(raw.storage_path))})
    return rows


@bp.route("/posizioni/<int:position_id>/sp/upload", methods=["GET", "POST"])
@access_required
def sp_upload(db, actor, position_id):
    # Uploading or editing a row must not silently select that PDL.
    position = db.get(ps.Position, position_id)
    if position is None:
        abort(404)
    if not actor.can_view(position):   # an existing Job outside the person's scope (fix A1)
        abort(403)
    if not actor.can_edit(position):
        abort(403)
    modal = request.values.get("modal") == "1"
    if request.method == "GET":
        return render_template("workspace/resume_upload.html", actor=actor, position=position,
            rows=_resume_rows(db, position), batch=None, section="selection", modal=modal)
    files = [f for f in request.files.getlist("cv") if f and f.filename]
    batch = {"at": ps.utcnow().isoformat(), "by": actor.name, "received": len(files), "imported": [],
             "exact_duplicates": [], "possible_duplicates": [], "failed": []}
    for f in files:
        # This endpoint only stores and extracts. Never evaluate, rank or queue a CV,
        # including when the Job has approved requirements and AI evaluation enabled.
        r = engine.import_cv(db, documents=_cfg.documents, restaurant_id=_restaurant_id(db), position=position,
            file_storage=f, channel=ps.MANUAL_UPLOAD, actor_id=actor.id, actor_name=actor.name,
            analyze_after=False, ai_reading=False)
        if r["status"] == "OK":
            batch["imported"].append(r["position_candidate_id"])
            notes = engine.duplicate_notes(db, db.get(ps.PositionCandidate, r["position_candidate_id"]))
            if notes:
                batch["possible_duplicates"].append({"pc_id": r["position_candidate_id"], "filename": r["filename"], "note":" ".join(notes)})
        elif r["status"] == "DUPLICATE":
            batch["exact_duplicates"].append(r["filename"])
        else:
            batch["failed"].append({"filename":r["filename"], "message":r.get("message") or "File non importato."})
    if has_profile(position) and files:
        sp = state(position)
        batch["n"] = len(sp["uploads"]) + 1
        sp["uploads"].append(batch)
        save_state(position, sp)
        db.commit()
        flask_session[CV_LIST_KEY] = {"position":position.id,"added":batch["imported"]}
    return render_template("workspace/resume_upload.html", actor=actor, position=position,
        rows=_resume_rows(db,position), batch=batch, section="selection", modal=modal)


@bp.get("/posizioni/<int:position_id>/resume/<int:pc_id>/dati")
@access_required
def resume_extracted_data(db, actor, position_id, pc_id):
    # Read persisted facts only. Never select a Job, rerun extraction or evaluate.
    position = db.get(ps.Position, position_id)
    if position is None:
        abort(404)
    if not actor.can_view(position):   # an existing Job outside the person's scope (fix A1)
        abort(403)
    pc = _pc(db, position, pc_id)
    candidate = persistence.get_candidate(db, pc.candidate_id)
    if candidate is None:
        abort(404)
    raw = db.get(m.RawResume,candidate.raw_resume_id) if candidate.raw_resume_id else None
    available = bool(raw and _cfg.documents.exists(raw.storage_path))
    import os
    extension = os.path.splitext(raw.original_filename or '')[1].lower() if raw else ''
    return render_template("workspace/_resume_extracted_data.html", profile=persistence.to_profile(candidate),
        include_original=request.args.get('include_original') == '1', original_available=available,
        original_inline=extension in ('.pdf','.txt','.png','.jpg','.jpeg'),
        original_url=url_for('positions.candidate_original',position_id=position.id,pc_id=pc.id,modal='1'))


@bp.route("/posizioni/<int:position_id>/sp/cv/<int:pc_id>/delete", methods=["POST"])
@access_required
def sp_delete_cv(db, actor, position_id, pc_id):
    """Delete one CV from the Applications page, only before it is analyzed (rules and concurrency: `cv_delete`).
    Server-side checks: the Job exists (404), is in the person's scope (403) and editable by them (403)."""
    position = _position(db, actor, position_id, edit=True)
    result = cv_delete.delete_cv(db, documents=_cfg.documents, position_id=position.id, pc_id=pc_id,
                                 actor_id=actor.id, actor_name=actor.name, load_state=state, save_state=save_state)
    if result["status"] == "DELETED":
        flash(f"CV “{result['filename']}” deleted.")
        flask_session[CV_LIST_KEY] = {"position": position.id, "removed": [pc_id]}
    elif result["status"] == "BLOCKED":
        flash(f"CV “{result['filename']}” not deleted: {'; '.join(result['reasons'])}.")
        flask_session[CV_LIST_KEY] = {"position": position.id}
    else:
        flash("This CV is no longer in the list.")
        flask_session[CV_LIST_KEY] = {"position": position.id, "removed": [pc_id]}
    anchor = None if result["status"] != "BLOCKED" else f"candidate-{pc_id}"   # back on the row (UI Rules 5)
    return redirect(url_for(".position_detail", position_id=position.id, tab="candidature", _anchor=anchor))


# ---------------------------------------------------------------------------
# Ranking page, requirements, analysis, manual order, detail
# ---------------------------------------------------------------------------

def _local_time(iso: str | None, tz: str) -> str:
    """Times shown to a person are in the position's local time (RF-One UI rule 1); stored times are UTC."""
    if not iso:
        return ""
    try:
        value = datetime.fromisoformat(iso)
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(ZoneInfo(tz)).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso


def _render(template: str, **kw):
    return render_template(template, **kw)


def _sp_position(db, actor, position_id, *, edit=False):
    position = _position(db, actor, position_id, edit=edit)
    if not has_profile(position):
        flash("CV Selection SP has a profile for Server and Line Cook Jobs only.")
        abort(redirect(url_for(".position_detail", position_id=position.id, tab="candidature")))
    return position


@bp.route("/posizioni/<int:position_id>/sp")
@access_required
def sp_page(db, actor, position_id):
    from .old_screening import enabled
    if enabled():
        _position(db, actor, position_id)
        return redirect(url_for('positions.position_detail', position_id=position_id, tab='candidature'))
    position = _position(db,actor,position_id)
    return redirect(url_for("positions.position_detail",position_id=position.id,tab="candidature"))


@bp.route("/posizioni/<int:position_id>/sp/requirements", methods=["POST"])
@access_required
def sp_requirements(db, actor, position_id):
    position = _sp_position(db, actor, position_id, edit=True)
    sp = state(position)
    if request.form.get("action") == "edit" and sp.get("approved"):
        sp["requirements_draft"] = json.loads(json.dumps(sp["approved"]["requirements"]))
        sp["editing"] = True
    else:
        draft = sp["requirements_draft"]
        for r in draft:
            if request.form.get(f"crit_{r['id']}") in spp.CRITICALITY_LABELS:
                r["criticality"] = request.form[f"crit_{r['id']}"]
            weight = request.form.get(f"weight_{r['id']}", type=int)
            if weight is not None:
                r["weight"] = max(0, min(100, weight))
        remove = request.form.get("remove")
        if remove:
            sp["requirements_draft"] = draft = [r for r in draft if r["id"] != remove]
        name = (request.form.get("new_name") or "").strip()
        if name:
            index = 1 + sum(1 for r in draft if r["id"].startswith("custom"))
            draft.append(spp.custom_requirement(index, name, request.form.get("new_look_for") or name,
                                                request.form.get("new_crit") or spp.PREFERRED,
                                                request.form.get("new_weight", type=int) or 5))
        if request.form.get("action") == "approve":
            if not any(r["criticality"] == spp.MUST_HAVE for r in draft):
                flash("Mark at least one requirement as Must-have: the ranking groups depend on it.")
            else:
                version = len(sp["versions"]) + 1
                approved = {"version": version, "approved_at": ps.utcnow().isoformat(), "approved_by": actor.name,
                            "requirements": json.loads(json.dumps(draft))}
                sp["versions"].append(approved)
                had_analyses = sp.get("approved") is not None
                sp["approved"], sp["editing"], sp["manual_order"] = approved, False, []
                flash(f"Requirements approved (version {version})." +
                      (" Earlier analyses used a previous version: Analyze updates them." if had_analyses else
                       " Press Analyze to rank the CVs."))
    save_state(position, sp)
    db.commit()
    return redirect(url_for(".sp_page", position_id=position.id) + "#requirements")


@bp.route("/posizioni/<int:position_id>/sp/analyze", methods=["POST"])
@access_required
def sp_analyze(db, actor, position_id):
    position = _sp_position(db, actor, position_id, edit=True)
    sp = state(position)
    if not sp.get("approved") or sp.get("editing"):
        flash("Approve the requirements first: the analysis applies the approved version.")
    elif not _ai_allowed(position):
        flash(AI_OFF)
    else:
        cands = candidates(db, position, sp)
        ids = [c["id"] for c in cands if c["status"] != "ANALYZING"] if request.form.get("all") == "1" \
            else _to_analyze(cands)
        if request.form.get("all") == "1":
            sp["manual_order"] = []
        queued = _queue(db, sp, ids)
        flash(f"Analyzing {queued} CV(s)…" if queued else
              "Every CV is already analyzed with the approved requirements: nothing sent to the AI.")
    return redirect(url_for(".sp_page", position_id=position.id))


@bp.route("/posizioni/<int:position_id>/sp/status")
@access_required
def sp_status(db, actor, position_id):
    position = _sp_position(db, actor, position_id)
    counts: dict[str, int] = {}
    for c in candidates(db, position, state(position)):
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return jsonify(counts)


@bp.route("/posizioni/<int:position_id>/sp/move", methods=["POST"])
@access_required
def sp_move(db, actor, position_id):
    position = _sp_position(db, actor, position_id, edit=True)
    sp = state(position)
    if request.form.get("reset"):
        sp["manual_order"] = []
    else:
        order = [r["id"] for r in ranked([c for c in candidates(db, position, sp) if not c["rejected"]], sp)]
        cid, direction = request.form.get("cid", type=int), request.form.get("dir")
        if cid in order:
            i = order.index(cid)
            j = i - 1 if direction == "up" else i + 1
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
            sp["manual_order"] = order
    save_state(position, sp)
    db.commit()
    view = request.form.get("view")
    return redirect(url_for(".sp_page", position_id=position.id, **({"view": view} if view == "last" else {}))
                    + "#ranking")


@bp.route("/posizioni/<int:position_id>/sp/c/<int:pc_id>")
@access_required
def sp_candidate(db, actor, position_id, pc_id):
    """Former SP detail page: the candidate's analysis now lives in the Evaluation dossier."""
    position = _sp_position(db, actor, position_id)
    _pc(db, position, pc_id)
    return redirect(url_for(".candidate_detail", position_id=position.id, pc_id=pc_id) + "#sp")


def dossier(db, position, pc_id: int) -> dict | None:
    from .old_screening import enabled
    if enabled():
        return None
    """The candidate's SP analysis for the Evaluation dossier (None for Roles without an SP profile)."""
    if not has_profile(position):
        return None
    sp = state(position)
    cands = candidates(db, position, sp)
    rows = ranked([c for c in cands if not c["rejected"]], sp)
    c = next((c for c in cands if c["id"] == pc_id), None)
    row = next((r for r in rows if r["id"] == pc_id), None)
    if row is None and c and c["analysis"] and sp.get("approved"):
        row = ranked([c], sp)[0]          # a rejected candidate keeps its assessment, without a place
        row["rank"] = None
    return {"sp": sp, "c": c, "row": row, "total": len(rows)}


def history(db, position, pc) -> list[dict]:
    """Every recorded event of one candidate, oldest first, from data Selection already keeps: the candidate's
    events (CV received, decisions, rejection and restore, interviews, messages), the uploads that brought the
    CV, the application, and each SP analysis (current and earlier ones)."""
    out = [{"at": e.created_at, "what": e.detail, "who": e.actor_name, "kind": e.kind}
           for e in db.scalars(select(ps.Event).where(ps.Event.position_candidate_id == pc.id)).all()]
    if has_profile(position):
        for u in state(position)["uploads"]:
            if pc.id in u["imported"]:
                out.append({"at": datetime.fromisoformat(u["at"]), "who": u["by"], "kind": "UPLOAD",
                            "what": f"Upload #{u['n']}: {u['received']} CV(s) received, "
                                    f"{len(u['imported'])} new (this CV among them)"})
        for p in db.scalars(select(ps.Proposal).where(ps.Proposal.position_candidate_id == pc.id,
                                                      ps.Proposal.source == SOURCE)).all():
            payload = json.loads(p.payload_json)
            out.append({"at": p.created_at, "who": payload.get("model") or "AI", "kind": "AI_ANALYSIS",
                        "what": (f"CV Selection SP analysis with requirements v{payload.get('version')}"
                                 + ("" if p.is_current else " (replaced by a later one)")) if payload.get("analysis")
                        else f"CV Selection SP analysis failed: {payload.get('error')}"})
    application = engine.candidate_application(db, pc.id)
    if application is not None and application.submitted_at:
        out.append({"at": application.submitted_at, "who": "Candidate", "kind": "APPLICATION",
                    "what": "Application completed on the application page"})
    for item in out:
        if item["at"] is not None and item["at"].tzinfo is not None:
            item["at"] = item["at"].replace(tzinfo=None)
    return sorted(out, key=lambda i: (i["at"] is None, i["at"]))
