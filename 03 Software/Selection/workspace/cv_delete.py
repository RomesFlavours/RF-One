"""Delete a CV from a Job's Applications list, only before its evaluation starts.

A CV can be deleted only while nothing has been built on it: uploaded by the manager, never queued for or
read by the AI, and without any later data (decisions, interviews, messages, online application, history).
Every row that points at the Job's candidate through a foreign key blocks the deletion, so data added by a
future module is protected too.

What is removed, in ONE transaction:
- the Job's link to the CV (`PositionCandidate`) and its "CV received" event, and its id in the Job's upload
  history (an id freed by SQLite may be given again to a later CV);
- the archive records the upload created (application, résumé snapshot, document record, identity) only when
  nothing else uses them: a document, an application or a person shared with another Job, another
  application or another module is kept;
- the stored file after the commit, only when its document record was removed: a record never points at a
  missing file.

Concurrency: the candidate row is locked (`FOR UPDATE` on PostgreSQL; on SQLite the queue's writer lock and
the database's single writer) and the blockers are checked again inside that lock. `sp_queue.enqueue` takes
the same lock and queues only candidates that still exist, so a Delete and an Analyze at the same moment
end either with the CV deleted and not analyzed, or with the CV queued and not deleted.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, inspect, select

from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps

from . import sp_queue

log = logging.getLogger(__name__)

PC_TABLE = ps.PositionCandidate.__tablename__
ADDED = "CANDIDATE_ADDED"

# Why a CV cannot be deleted, by the table holding the later data.
_TABLE_REASONS = {
    ps.Decision.__tablename__: "a decision is recorded",
    ps.Appointment.__tablename__: "an interview is scheduled or recorded",
    ps.SlotOffer.__tablename__: "interview times were offered",
    ps.Message.__tablename__: "messages to the candidate are recorded",
    "selection_workspace_email_outbox": "messages to the candidate are recorded",
    ps.CandidateApplication.__tablename__: "the candidate's online application is recorded",
}


_tables: dict[str, set[str]] = {}


def _existing_tables(db) -> set[str]:
    """Tables of this database (read once per process through the session's own connection: the schema only
    changes with a migration, at start)."""
    key = str(db.get_bind().url)
    if key not in _tables:
        _tables[key] = set(inspect(db.connection()).get_table_names())
    return _tables[key]


def _foreign_keys_to(table_name: str, tables: set[str]):
    """(table, column) pairs pointing at `table_name.id`, for tables present in this database."""
    for table in m.Base.metadata.tables.values():
        if table.name not in tables:
            continue
        for fk in table.foreign_keys:
            if fk.column.table.name == table_name and fk.column.name == "id":
                yield table, fk.parent


def _references(db, table_name: str, row_ids: list[int], tables: set[str], skip=()) -> dict[int, list[str]]:
    """Per row id, the tables (outside `skip`) that have rows pointing at it."""
    out: dict[int, list[str]] = {i: [] for i in row_ids}
    if not row_ids:
        return out
    for table, column in _foreign_keys_to(table_name, tables):
        if table.name in skip:
            continue
        for ref_id, count in db.execute(select(column, func.count()).where(column.in_(row_ids))
                                        .group_by(column)).all():
            if count:
                out[ref_id].append(table.name)
    return out


# ---------------------------------------------------------------------------
# Blockers
# ---------------------------------------------------------------------------

def blockers(db, pcs: list[ps.PositionCandidate]) -> dict[int, list[str]]:
    """Per candidate of the Job, why its CV cannot be deleted (empty list: it can)."""
    ids = [pc.id for pc in pcs]
    out: dict[int, list[str]] = {i: [] for i in ids}
    if not ids:
        return out
    for pc in pcs:
        if pc.channel != ps.MANUAL_UPLOAD or pc.candidate_account_id is not None:
            out[pc.id].append("the candidate sent it from the application page")
    proposals: dict[int, list[tuple[str, str, bool]]] = {i: [] for i in ids}
    for pc_id, source, state, current in db.execute(
            select(ps.Proposal.position_candidate_id, ps.Proposal.source, ps.Proposal.group_code,
                   ps.Proposal.is_current).where(ps.Proposal.position_candidate_id.in_(ids))).all():
        proposals[pc_id].append((source, state, current))
    for pc_id, rows in proposals.items():
        active = [s for src, s, cur in rows if src == sp_queue.JOB and cur and s in (sp_queue.QUEUED, sp_queue.RUNNING)]
        if sp_queue.RUNNING in active:
            out[pc_id].append("the AI analysis is in progress")
        elif active:
            out[pc_id].append("it is queued for the AI analysis")
        elif any(src == sp_queue.RESULT for src, _, _ in rows):
            out[pc_id].append("it has already been analyzed")
        elif any(src == sp_queue.JOB for src, _, _ in rows):
            out[pc_id].append("the AI analysis has already started")
        if any(src not in (sp_queue.JOB, sp_queue.RESULT) for src, _, _ in rows):
            out[pc_id].append("evaluation data is recorded")
    refs = _references(db, PC_TABLE, ids, _existing_tables(db), skip={ps.Proposal.__tablename__})
    for pc_id, tables in refs.items():
        for name in dict.fromkeys(_TABLE_REASONS.get(t, f"later data is recorded ({t})") for t in tables):
            out[pc_id].append(name)
    for pc_id, count in db.execute(select(ps.Event.position_candidate_id, func.count())
                                   .where(ps.Event.position_candidate_id.in_(ids), ps.Event.kind != ADDED)
                                   .group_by(ps.Event.position_candidate_id)).all():
        if count:
            out[pc_id].append("its history already has later events")
    return out


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def _cascade_children(model) -> set[str]:
    """Tables deleted together with a row of `model` (its own parts, e.g. the résumé snapshot's work history)."""
    return {r.mapper.local_table.name for r in inspect(model).relationships if r.cascade.delete}


def _remove_upload_reference(sp: dict, pc_id: int, filename: str, at: str, by: str) -> None:
    for upload in sp.get("uploads", []):
        if pc_id in upload.get("imported", []):
            upload["imported"] = [i for i in upload["imported"] if i != pc_id]
            upload["possible_duplicates"] = [d for d in upload.get("possible_duplicates", []) if d.get("pc_id") != pc_id]
            upload.setdefault("deleted", []).append({"filename": filename, "at": at, "by": by})
    sp["manual_order"] = [i for i in sp.get("manual_order", []) if i != pc_id]


def delete_cv(db, *, documents, position_id: int, pc_id: int, actor_id: int | None, actor_name: str,
              load_state, save_state) -> dict:
    """Delete one CV of the Job. Returns {"status": "DELETED" | "BLOCKED" | "MISSING", "filename", "reasons",
    "kept": [what was kept because shared]}. `load_state` / `save_state` read and write the Job's SP state."""
    db.commit()  # end any read before writing: on SQLite a read lock is never upgraded (see sp_queue._claim)
    with sp_queue._write_lock:
        pc = db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.id == pc_id,
                                                           ps.PositionCandidate.position_id == position_id)
                        .with_for_update()).first()
        if pc is None:
            db.rollback()
            return {"status": "MISSING", "filename": None, "reasons": [], "kept": []}
        application = db.get(m.Application, pc.application_id)
        candidate = db.get(m.Candidate, pc.candidate_id)
        raw = db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
        filename = (raw.original_filename if raw else None) or f"CV {pc.id}"
        reasons = blockers(db, [pc])[pc.id]
        if reasons:
            db.rollback()
            return {"status": "BLOCKED", "filename": filename, "reasons": reasons, "kept": []}

        tables, kept, remove_file = _existing_tables(db), [], None
        db.execute(sql_delete(ps.Event).where(ps.Event.position_candidate_id == pc.id, ps.Event.kind == ADDED))
        db.delete(pc)
        db.flush()

        # Application: kept when another Job or any other record uses it (a pending name-match suggestion
        # created for this application at import is part of it and goes with it).
        match_table = m.PersonMatchCandidate.__tablename__
        app_refs = _references(db, m.Application.__tablename__, [application.id], tables,
                               skip={match_table})[application.id]
        reviewed = db.scalar(select(func.count()).select_from(m.PersonMatchCandidate).where(
            m.PersonMatchCandidate.application_id == application.id, m.PersonMatchCandidate.status != "PENDING"))
        person_id = application.person_id
        if app_refs or reviewed:
            kept.append("application (used elsewhere)")
        else:
            db.execute(sql_delete(m.PersonMatchCandidate).where(
                m.PersonMatchCandidate.application_id == application.id))
            db.delete(application)
            db.flush()

            # Résumé snapshot: kept when anything other than its own parts uses it.
            cand_refs = _references(db, m.Candidate.__tablename__, [candidate.id], tables,
                                    skip=_cascade_children(m.Candidate))[candidate.id]
            if cand_refs:
                kept.append("résumé snapshot (used elsewhere)")
            else:
                db.delete(candidate)
                db.flush()
                # Document: shared when another snapshot (another application of the same file) uses it.
                if raw is not None:
                    if _references(db, m.RawResume.__tablename__, [raw.id], tables)[raw.id]:
                        kept.append("document (shared with another application)")
                    else:
                        shared_path = db.scalar(select(func.count()).select_from(m.RawResume).where(
                            m.RawResume.storage_path == raw.storage_path, m.RawResume.id != raw.id))
                        remove_file = None if shared_path or not raw.storage_path else raw.storage_path
                        db.delete(raw)
                        db.flush()

            # Identity: removed only when this upload created it and nothing at all refers to it.
            person = db.get(m.CandidatePerson, person_id)
            if person is not None:
                if _references(db, m.CandidatePerson.__tablename__, [person.id], tables)[person.id]:
                    kept.append("candidate identity (used elsewhere)")
                else:
                    db.delete(person)
                    db.flush()

        position = db.get(ps.Position, position_id)
        sp = load_state(position)
        now = ps.utcnow().isoformat()
        _remove_upload_reference(sp, pc_id, filename, now, actor_name)
        save_state(position, sp)
        ps.log_event(db, position_id=position_id, kind="CV_DELETED", actor_id=actor_id, actor_name=actor_name,
                     detail=f"CV deleted before its evaluation: {filename}"
                            + (f" (kept: {', '.join(kept)})" if kept else ""))
        db.commit()

    if remove_file:
        try:
            documents.delete(remove_file)
        except Exception:  # the records are gone; a leftover file is never shown or read again
            log.exception("Selection: file of deleted CV %s not removed", pc_id)
    return {"status": "DELETED", "filename": filename, "reasons": [], "kept": kept}
