"""Move the experimental C-Bank store into the operational Bank database (Bank unification Phase 3A).

Requires migration e3a120261024. In one transaction, idempotent (origin ids prevent any duplicate):

* every C-Bank run header -> `bank_engine_runs` (origin CBANK, origin_run_id);
* the per-movement results of the LATEST whole-history run -> `bank_engine_results` (earlier runs' results stay
  in the frozen `cbank.db`, kept as the archive);
* the matched pairs -> `financial_transaction_matches` (method ENGINE; a pair already present is left as it is);
* AI investigations and conversations -> `bank_flow_artifacts` (ENGINE_INVESTIGATION / ENGINE_CONVERSATION);
* the C-Bank human decisions -> `bank_flow_artifacts` (ENGINE_HUMAN_DECISION) with their provenance. Never a
  classification by itself: one is applied through Bank's manual decision service only when it is still valid
  (active WHO and usable WHY) and the movement has no human decision in Bank; otherwise it is reported.

No movement is reclassified. Run without --apply for a dry run (rolled back).

    python migrate_cbank_store.py --cbank <cbank.db> --db <rfone.db> [--apply] [--log <file.json>]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import select, text

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow, recognition, why_what
from rfone_data_store.database import create_configured_engine, create_session_factory

ORIGIN = "CBANK"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cbank", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log")
    args = parser.parse_args()
    src = sqlite3.connect(f"file:{Path(args.cbank).resolve().as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    engine = create_configured_engine(f"sqlite:///{Path(args.db).resolve().as_posix()}")
    db = create_session_factory(engine)()
    log = dict(applied=args.apply, runs=0, results=0, results_run=None, matches_new=0, matches_present=0,
               investigations=0, conversations=0, human_applied=[], human_conflicts=[])
    try:
        db.info["bank_restore"] = False
        done = {r for (r,) in db.execute(text("select origin_run_id from bank_engine_runs where origin=:o"), {"o": ORIGIN})}
        run_map = dict(db.execute(text("select origin_run_id, id from bank_engine_runs where origin=:o"), {"o": ORIGIN}).all())
        for r in src.execute("select * from runs order by id"):
            if r["id"] in done:
                continue
            row = m.BankEngineRun(created_at=r["created_at"], label=r["label"], scope_json=r["scope_json"],
                                  summary_json=r["summary_json"], origin=ORIGIN, origin_run_id=r["id"])
            db.add(row)
            db.flush()
            run_map[r["id"]] = row.id
            log["runs"] += 1
        last = src.execute("select id from runs where json_extract(scope_json,'$.kind')='all' order by id desc limit 1").fetchone()
        if last:
            target = run_map[last["id"]]
            log["results_run"] = dict(origin_run_id=last["id"], run_id=target)
            if not db.execute(text("select 1 from bank_engine_results where run_id=:r limit 1"), {"r": target}).first():
                rows = [dict(run_id=target, financial_transaction_id=x["txn_id"], status=x["status"], payload_json=x["payload_json"])
                        for x in src.execute("select * from results where run_id=?", (last["id"],))]
                db.execute(m.BankEngineResult.__table__.insert(), rows)
                log["results"] = len(rows)
        for x in src.execute("select * from matches"):
            present = db.execute(text("select match_method from financial_transaction_matches where transaction_a_id=:a "
                                      "and transaction_b_id=:b"), {"a": x["txn_a"], "b": x["txn_b"]}).first()
            if present:
                log["matches_present"] += 1
                continue
            a = db.get(m.FinancialTransaction, x["txn_a"])
            db.add(m.FinancialTransactionMatch(
                transaction_a_id=x["txn_a"], transaction_b_id=x["txn_b"], match_type=x["kind"], match_method="ENGINE",
                match_basis=x["basis"], matched_amount_minor=abs(a.amount_minor), owner_relationship=x["relationship"],
                posting_transaction_id=x["posting_txn"], first_engine_run_id=run_map.get(x["first_run_id"]),
                last_engine_run_id=run_map.get(x["last_run_id"])))
            log["matches_new"] += 1
        db.flush()

        def migrated(kind, origin_id):
            return db.execute(text("select 1 from bank_flow_artifacts where kind=:k and "
                                   "json_extract(payload,'$.origin_id')=:i"), {"k": kind, "i": origin_id}).first()

        def artifact(kind, payload, created_at):
            db.add(m.BankFlowArtifact(kind=kind, payload=json.dumps(payload, default=str)))
            db.flush()

        for x in src.execute("select * from investigations order by id"):
            if not migrated("ENGINE_INVESTIGATION", x["id"]):
                artifact("ENGINE_INVESTIGATION", dict(origin=ORIGIN, origin_id=x["id"], created_at=x["created_at"],
                                                      group_key=x["group_key"], txn_ids=json.loads(x["txn_ids_json"]),
                                                      provider=x["provider"], prompt=x["prompt"],
                                                      answer=json.loads(x["answer_json"]) if x["answer_json"] else None,
                                                      error=x["error"]), x["created_at"])
                log["investigations"] += 1
        for x in src.execute("select * from conversations order by id"):
            if not migrated("ENGINE_CONVERSATION", x["id"]):
                artifact("ENGINE_CONVERSATION", dict(origin=ORIGIN, origin_id=x["id"], created_at=x["created_at"],
                                                     txn_id=x["txn_id"], role=x["role"], text=x["text"],
                                                     payload=json.loads(x["payload_json"]) if x["payload_json"] else None),
                         x["created_at"])
                log["conversations"] += 1
        for h in src.execute("select * from human_decisions order by id"):
            if migrated("ENGINE_HUMAN_DECISION", h["id"]):
                continue
            txn = db.get(m.FinancialTransaction, h["txn_id"])
            current = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn and txn.explanation_id else None
            reason = db.get(m.BankTransactionReason, h["why_id"]) if h["why_id"] else None
            who = next((o for o in db.scalars(select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))
                        if flow.clean(o.canonical_name) == flow.clean(h["who_name"])), None)
            problems = []
            if not h["active"]:
                problems.append("superseded inside C-Bank")
            if current is not None and current.decision_source == "HUMAN":
                problems.append("the movement already has a human decision in Bank (kept)")
            if reason is None or reason.status != "ACTIVE":
                problems.append(f"WHY id {h['why_id']} is no longer in the catalog")
            elif why_what.assignment_problem(db, reason):
                problems.append(why_what.assignment_problem(db, reason))
            if who is None:
                problems.append(f"WHO {h['who_name']!r} is not in the catalog")
            applied_id = None
            if not problems:
                applied_id = recognition.record_human_decision(db, recognition.HumanDecisionRequest(
                    transaction_id=h["txn_id"], occurrence_id=who.id, confirmed_by_account_id=None,
                    transaction_reason_id=reason.id, notes=f"C-Bank human decision #{h['id']} ({h['note'] or ''})")).id
            artifact("ENGINE_HUMAN_DECISION", dict(origin=ORIGIN, origin_id=h["id"], txn_id=h["txn_id"],
                                                   who_name=h["who_name"], why_id=h["why_id"], category_id=h["category_id"],
                                                   beneficiary_id=h["beneficiary_id"], note=h["note"],
                                                   created_at=h["created_at"], active=bool(h["active"]),
                                                   applied_explanation_id=applied_id, not_applied_because=problems),
                     h["created_at"])
            (log["human_applied"] if applied_id else log["human_conflicts"]).append(
                dict(origin_id=h["id"], txn_id=h["txn_id"], who=h["who_name"], why_id=h["why_id"], problems=problems))
        if args.apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()
    if args.log:
        Path(args.log).write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print(("APPLIED" if args.apply else "DRY RUN (rolled back)") + " — " + json.dumps(
        {k: (len(v) if isinstance(v, list) else v) for k, v in log.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
