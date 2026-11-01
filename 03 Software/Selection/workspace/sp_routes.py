"""CV Selection SP inside Selection: CV upload from the positions page, analysis and the preselection ranking.

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
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.selection import persistence
from rfone_data_store.selection import workspace_models as ps

from . import engine, position_settings, sp_queue
from .routes import _cfg, _pc, _position, _restaurant_id, access_required, bp
from .sp import profiles as spp
from .sp import ranking as sp_ranking

SOURCE = sp_queue.RESULT


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
    return sp


def save_state(position, sp: dict) -> None:
    data = position_settings.context(position)
    data["sp"] = sp
    position.organization_context_json = json.dumps(data, ensure_ascii=False, default=str)


@bp.before_app_request
def _sp_kick():
    """Every request to Selection (pages, candidates, the per-minute mail-outbox claim) keeps the queue moving."""
    sp_queue.kick()


@bp.app_context_processor
def _sp_globals():
    return {"SP_ROLES": spp.ROLES}


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
    for pc in pcs:
        candidate = persistence.get_candidate(db, pc.candidate_id)
        raw = db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
        prop = results.get(pc.id)
        payload = json.loads(prop.payload_json) if prop else {}
        version = payload.get("version")
        application = engine.candidate_application(db, pc.id)
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
        out.append({"id": pc.id, "filename": (raw.original_filename if raw else None) or f"CV {pc.id}",
                    "uploaded_at": pc.added_at.isoformat(), "name": candidate.full_name if candidate else None,
                    "analysis": payload.get("analysis"), "analyzed_version": version,
                    "analyzed_at": payload.get("analyzed_at"), "model": payload.get("model"),
                    "error": payload.get("error"), "status": status, "new": pc.id in last,
                    "batch": batch_of.get(pc.id), "channel": pc.channel,
                    "duplicate_note": " ".join(engine.duplicate_notes(db, pc)) or None})
    return out


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
    return sp_ranking.rank(analyzed, approved["requirements"], sp.get("manual_order"))


# ---------------------------------------------------------------------------
# Upload (from the row of the position on the Selection positions page)
# ---------------------------------------------------------------------------

@bp.route("/posizioni/<int:position_id>/sp/upload", methods=["POST"])
@access_required
def sp_upload(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    files = [f for f in request.files.getlist("cv") if f and f.filename]
    if not files:
        flash("Select at least one CV file.")
        return redirect(url_for(".dashboard"))
    sp_role = has_profile(position)
    batch = {"at": ps.utcnow().isoformat(), "by": actor.name, "received": len(files), "imported": [],
             "exact_duplicates": [], "possible_duplicates": [], "failed": []}
    for f in files:
        # SP roles: rule-based reading only and no Selection analysis here; SP's single AI reading follows.
        r = engine.import_cv(db, documents=_cfg.documents, restaurant_id=_restaurant_id(db), position=position,
                             file_storage=f, channel=ps.MANUAL_UPLOAD, actor_id=actor.id, actor_name=actor.name,
                             analyze_after=not sp_role, ai_reading=not sp_role)
        if r["status"] == "OK":
            batch["imported"].append(r["position_candidate_id"])
            notes = engine.duplicate_notes(db, db.get(ps.PositionCandidate, r["position_candidate_id"]))
            if notes:
                batch["possible_duplicates"].append({"pc_id": r["position_candidate_id"], "filename": r["filename"],
                                                     "note": " ".join(notes)})
        elif r["status"] == "DUPLICATE":
            batch["exact_duplicates"].append(r["filename"])
        else:
            batch["failed"].append({"filename": r["filename"], "message": r.get("message") or "Not imported."})
    summary = (f"{batch['received']} CV(s) received · {len(batch['imported'])} new imported · "
               f"{len(batch['exact_duplicates'])} exact duplicate(s) ignored · "
               f"{len(batch['possible_duplicates'])} possible duplicate(s) to verify"
               + (f" · {len(batch['failed'])} not imported" if batch["failed"] else ""))
    if not sp_role:
        flash(summary)
        return redirect(url_for(".position_detail", position_id=position.id, tab="candidature"))
    position = db.get(ps.Position, position.id)
    sp = state(position)
    batch["n"] = len(sp["uploads"]) + 1
    sp["uploads"].append(batch)
    save_state(position, sp)
    db.commit()
    flash(f"Upload {batch['n']}: {summary}.")
    if sp["approved"] and not sp.get("editing") and batch["imported"]:
        if _ai_allowed(position):
            queued = _queue(db, sp, batch["imported"])
            flash(f"Analyzing the {queued} new CV(s); earlier analyses are kept.")
        else:
            flash("AI résumé evaluation is off for this position: turn it on in Configuration to analyze.")
    return redirect(url_for(".sp_page", position_id=position.id))


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
    return render_template(template, local_time=_local_time, STATUS_LABELS=sp_ranking.STATUS_LABELS,
                           CRIT=spp.CRITICALITY_LABELS, level_label=sp_ranking.spp_level, summary=sp_ranking.summary,
                           **kw)


def _sp_position(db, actor, position_id, *, edit=False):
    position = _position(db, actor, position_id, edit=edit)
    if not has_profile(position):
        flash("CV Selection SP has a profile for Server and Line Cook positions only.")
        abort(redirect(url_for(".position_detail", position_id=position.id)))
    return position


@bp.route("/posizioni/<int:position_id>/sp")
@access_required
def sp_page(db, actor, position_id):
    position = _sp_position(db, actor, position_id)
    sp = state(position)
    cands = candidates(db, position, sp)
    rows = ranked(cands, sp)
    view = "last" if request.args.get("view") == "last" else "all"
    shown = [r for r in rows if r["new"]] if view == "last" else rows
    return _render("sp/position.html", p=position, sp=sp, rows=shown, all_rows=rows, cands=cands, view=view,
                   running=sum(1 for c in cands if c["status"] == "ANALYZING"),
                   to_analyze=len(_to_analyze(cands)) if sp.get("approved") else 0,
                   outdated=sum(1 for c in cands if c["status"] == "OUTDATED"),
                   last_upload=sp["uploads"][-1] if sp["uploads"] else None, last_added=last_adding_upload(sp),
                   ai_allowed=_ai_allowed(position), can_edit=actor.can_edit(position))


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
        flash("AI résumé evaluation is off for this position: turn it on in Configuration to analyze.")
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
        order = [r["id"] for r in ranked(candidates(db, position, sp), sp)]
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
    position = _sp_position(db, actor, position_id)
    _pc(db, position, pc_id)
    sp = state(position)
    cands = candidates(db, position, sp)
    rows = ranked(cands, sp)
    c = next(c for c in cands if c["id"] == pc_id)
    row = next((r for r in rows if r["id"] == pc_id), None)
    return _render("sp/candidate.html", p=position, sp=sp, c=c, row=row, total=len(rows))
