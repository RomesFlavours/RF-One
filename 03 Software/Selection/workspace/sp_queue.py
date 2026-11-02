"""Durable analysis queue of CV Selection SP — no new table and no new infrastructure.

A job is a `selection_workspace_proposals` row with source "SP_JOB", at most one active (`is_current`) per
candidate: QUEUED → RUNNING → DONE | FAILED | SUPERSEDED. `snapshot_id` is the requirement version requested;
for a job, `created_at` is the time the row entered its current state (enqueued, then lease start);
the payload counts the attempts. Results stay separate (source "SP", see `sp_routes`).

Reliability (App Runner gives an instance CPU only while it serves requests):
- the queue is in the database, so it survives a closed page, a restart or a new instance;
- a job is claimed by a conditional UPDATE (same state and timestamp), so exactly one worker wins, also
  across the two gunicorn workers; a RUNNING job whose 10-minute lease expired (process stopped mid-way)
  is claimed again, at most 3 attempts in all;
- before calling Bedrock a job is dropped when the candidate already has a current analysis for that
  version, or when an older active job exists for the same candidate (the lowest id wins): no duplicate
  AI call on retries, restarts or simultaneous requests; a result is written only by the lease holder;
- workers are threads started by any request to Selection (`kick`, at most every few seconds per
  process): the manager's pages, candidates' pages and the existing per-minute mail-outbox claim of the
  RMAED mail worker (EventBridge rate(1 minute)). So the analysis continues, or resumes within about a
  minute, with every page closed, using only what already runs.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import timedelta

from sqlalchemy import select, update

from rfone_data_store import models as m
from rfone_data_store.selection import persistence
from rfone_data_store.selection import workspace_models as ps

from . import ai_adapter, position_settings
from .sp import analysis as sp_analysis
from .sp import profiles as spp

log = logging.getLogger(__name__)

JOB, RESULT = "SP_JOB", "SP"
QUEUED, RUNNING, DONE, FAILED, SUPERSEDED = "QUEUED", "RUNNING", "DONE", "FAILED", "SUPERSEDED"
LEASE = timedelta(minutes=10)  # longer than one reading with every throttling retry and the JSON retry (about 4 min)
MAX_ATTEMPTS = 3
WORKERS = 3                    # 4 in parallel made Bedrock throttle (1 Nov 2026)
KICK_EVERY = 5.0               # seconds between two kicks of one process
GENERATE = None                # tests replace the AI call here

_state_lock = threading.Lock()
_write_lock = threading.RLock()  # one writer at a time inside a process (SQLite locally); re-entrant
_running = 0
_last_kick = 0.0


def _sessions():
    from .routes import _cfg
    return _cfg.SessionFactory


def has_profile(position) -> bool:
    return position.role_code in spp.ROLES


def sp_state(position) -> dict:
    sp = position_settings.context(position).get("sp")
    return sp if isinstance(sp, dict) else {}


# ---------------------------------------------------------------------------
# Reading the queue
# ---------------------------------------------------------------------------

def active_jobs(db, pc_ids) -> dict[int, ps.Proposal]:
    if not pc_ids:
        return {}
    rows = db.scalars(select(ps.Proposal).where(ps.Proposal.source == JOB, ps.Proposal.is_current.is_(True),
                                                ps.Proposal.group_code.in_((QUEUED, RUNNING)),
                                                ps.Proposal.position_candidate_id.in_(list(pc_ids)))
                      .order_by(ps.Proposal.id)).all()
    out: dict[int, ps.Proposal] = {}
    for row in rows:
        out.setdefault(row.position_candidate_id, row)
    return out


def _current_result(db, pc_id: int) -> ps.Proposal | None:
    return db.scalars(select(ps.Proposal).where(ps.Proposal.position_candidate_id == pc_id,
                                                ps.Proposal.source == RESULT,
                                                ps.Proposal.is_current.is_(True))).first()


def _analyzed_with(result: ps.Proposal | None, version: int) -> bool:
    return bool(result and result.group_code == "ANALYZED" and json.loads(result.payload_json).get("version") == version)


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def enqueue(db, pc_ids, version: int) -> int:
    """Queue these candidates for the approved version, skipping those already queued or already analyzed with
    it. Returns how many jobs were created (the caller commits nothing else)."""
    active = active_jobs(db, pc_ids)
    needed = [pc_id for pc_id in pc_ids
              if pc_id not in active and not _analyzed_with(_current_result(db, pc_id), version)]
    db.commit()  # end the read before writing: on SQLite a read lock is never upgraded (see _claim)
    with _write_lock:
        # The lock a CV deletion takes (`cv_delete`): only candidates that still exist are queued, so a Delete
        # and an Analyze at the same moment never leave a job for a deleted CV.
        needed = list(db.scalars(select(ps.PositionCandidate.id).where(ps.PositionCandidate.id.in_(needed))
                                 .order_by(ps.PositionCandidate.id).with_for_update()).all()) if needed else []
        for pc_id in needed:
            db.add(ps.Proposal(position_candidate_id=pc_id, snapshot_id=version, fit_assessment_id=None, source=JOB,
                               group_code=QUEUED, payload_json=json.dumps({"attempts": 0}), is_current=True,
                               provider_label=None))
        db.commit()
    created = len(needed)
    if created:
        kick(force=True)
    return created


def on_application_completed(db, position, pc) -> None:
    """RMAED/application page: a completed application enters the SP analysis. Never raises into the
    candidate's page; an application still in progress never arrives here."""
    try:
        if not has_profile(position):
            return
        approved = sp_state(position).get("approved")
        if approved and not sp_state(position).get("editing") and position_settings.bind(position).allows("cv_evaluation"):
            enqueue(db, [pc.id], approved["version"])
    except Exception:  # the candidate's application is already saved; the manager can still press Analyze
        log.exception("CV Selection SP: completed application %s not queued", pc.id)


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

def kick(force: bool = False) -> None:
    """Start workers if this process has none busy (called on every request, cheap)."""
    global _running, _last_kick
    now = time.monotonic()
    with _state_lock:
        if (not force and now - _last_kick < KICK_EVERY) or _running >= WORKERS:
            return
        _last_kick = now
        start = WORKERS - _running
        _running += start
    for _ in range(start):
        threading.Thread(target=_worker, name="cv-selection-sp", daemon=True).start()


def _worker() -> None:
    global _running
    try:
        while True:
            claimed = _claim()
            if claimed is None:
                return
            _process(*claimed)
    except Exception:
        log.exception("CV Selection SP worker stopped")
    finally:
        with _state_lock:
            _running -= 1


def _claim():
    """(job id, lease start) of one job now owned by this worker, or None."""
    sessions = _sessions()
    with sessions() as db:
        now = ps.utcnow()
        rows = [(r.id, r.group_code, r.created_at, r.payload_json, r.position_candidate_id, r.snapshot_id)
                for r in db.scalars(select(ps.Proposal).where(
                    ps.Proposal.source == JOB, ps.Proposal.is_current.is_(True),
                    (ps.Proposal.group_code == QUEUED) | ((ps.Proposal.group_code == RUNNING) &
                                                          (ps.Proposal.created_at < now - LEASE)))
                    .order_by(ps.Proposal.id).limit(20)).all()]
        # End the read before any write. On SQLite (deferred BEGIN) a transaction that reads and then writes can
        # deadlock with another writer; every write below starts its own transaction with the UPDATE itself.
        db.rollback()
        for job_id, state, stamp, payload, pc_id, version in rows:
            attempts = json.loads(payload or "{}").get("attempts", 0)
            with _write_lock:
                if attempts >= MAX_ATTEMPTS:
                    won = db.execute(update(ps.Proposal).where(
                        ps.Proposal.id == job_id, ps.Proposal.group_code == state,
                        ps.Proposal.created_at == stamp).values(group_code=FAILED, is_current=False)).rowcount
                    db.commit()
                    if won:
                        _write_result(pc_id, version, None, "Interrupted 3 times: press Analyze to try again.")
                    continue
                won = db.execute(update(ps.Proposal).where(
                    ps.Proposal.id == job_id, ps.Proposal.group_code == state,
                    ps.Proposal.created_at == stamp).values(
                    group_code=RUNNING, created_at=now, payload_json=json.dumps({"attempts": attempts + 1}))).rowcount
                db.commit()
            if won == 1:
                return job_id, now
    return None


def _finish(job_id: int, lease, status: str) -> bool:
    """Close the job if this worker still holds its lease. False when the lease was lost."""
    with _write_lock, _sessions()() as db:
        won = db.execute(update(ps.Proposal).where(ps.Proposal.id == job_id, ps.Proposal.group_code == RUNNING,
                                                   ps.Proposal.created_at == lease)
                         .values(group_code=status, is_current=False)).rowcount
        db.commit()
        return won == 1


def _process(job_id: int, lease) -> None:
    with _sessions()() as db:
        job = db.get(ps.Proposal, job_id)
        pc = db.get(ps.PositionCandidate, job.position_candidate_id)
        position = db.get(ps.Position, pc.position_id)
        approved = sp_state(position).get("approved")
        older = db.scalars(select(ps.Proposal.id).where(
            ps.Proposal.source == JOB, ps.Proposal.is_current.is_(True), ps.Proposal.position_candidate_id == pc.id,
            ps.Proposal.group_code.in_((QUEUED, RUNNING)), ps.Proposal.id < job_id)).first()
        if older is not None or not approved or not has_profile(position):
            skip = SUPERSEDED if older is not None else DONE
        elif _analyzed_with(_current_result(db, pc.id), approved["version"]):
            skip = DONE                                   # already analyzed with these requirements: no AI call
        else:
            skip = None
            version, requirements, role = approved["version"], approved["requirements"], position.role_code
            position_settings.bind(position)              # the position's AI permissions, in this thread too
            candidate = persistence.get_candidate(db, pc.candidate_id)
            raw = db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
            cv_text = (raw.raw_text if raw else "") or ""
            pc_id = pc.id
    if skip:
        _finish(job_id, lease, skip)
        return
    # No database session is open during the AI call (an open read blocks other writers on SQLite).
    analysis, error = None, None
    try:
        analysis = sp_analysis.analyze_cv(role_code=role, requirements=requirements, cv_text=cv_text,
                                          generate=GENERATE)
    except Exception as exc:  # one CV failing never stops the others
        error = str(exc)[:500]
    _write_result(pc_id, version, analysis, error, job=(job_id, lease))


def _write_result(pc_id: int, version: int, analysis: dict | None, error: str | None, job=None) -> None:
    """Store the result; with `job`, close that job in the SAME transaction and only if this worker still holds
    its lease. One transaction leaves no moment with neither an active job nor the result, so a second job for
    the same candidate can never pass both checks and call the AI again."""
    payload = ({"version": version, "analysis": analysis, "model": ai_adapter.POLICY.provider_label,
                "analyzed_at": ps.utcnow().isoformat()} if analysis else {"version": version, "error": error})
    with _write_lock, _sessions()() as db:
        if job is not None:
            won = db.execute(update(ps.Proposal).where(ps.Proposal.id == job[0], ps.Proposal.group_code == RUNNING,
                                                       ps.Proposal.created_at == job[1])
                             .values(group_code=DONE if analysis else FAILED, is_current=False)).rowcount
            if won != 1:          # lease lost: another worker owns this job now
                db.rollback()
                return
        db.execute(update(ps.Proposal).where(ps.Proposal.position_candidate_id == pc_id, ps.Proposal.source == RESULT,
                                             ps.Proposal.is_current.is_(True)).values(is_current=False))
        db.add(ps.Proposal(position_candidate_id=pc_id, snapshot_id=version, fit_assessment_id=None, source=RESULT,
                           group_code="ANALYZED" if analysis else "ERROR", payload_json=json.dumps(payload, default=str),
                           provider_label=payload.get("model")))
        db.commit()
