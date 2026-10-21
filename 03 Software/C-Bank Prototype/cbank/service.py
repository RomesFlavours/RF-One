"""Runs: the same engine for the sample, a month or the whole history (decision 24)."""
from __future__ import annotations

import json

from . import engine as engine_mod, legacy, sample, store


def new_engine(con):
    return engine_mod.Engine(legacy.session(), con)


def execute(con, kind: str, month: str | None = None) -> int:
    eng = new_engine(con)
    cases: dict[int, list[str]] = {}
    if kind == "sample":
        picked = sample.select(eng)
        cases = sample.case_index(picked)
        txns = [eng.by_id[i] for i in sorted(cases)]
        label, scope = "MVP sample", dict(kind="sample", cases=picked)
    elif kind == "month" and month:
        txns = [t for t in eng.txns if str(t.posting_date).startswith(month)]
        label, scope = f"Month {month}", dict(kind="month", month=month)
    else:
        raise ValueError("Choose the sample or a month (YYYY-MM).")
    results = []
    for t in txns:
        r = eng.evaluate(t)
        r["cases"] = cases.get(t.id, [])
        results.append(r)
    return store.save_run(con, label, scope, results, engine_mod.summarize(results))


def reevaluate(con, run_id: int, txn_ids: set[int] | None = None) -> int:
    """New knowledge re-processes ONLY unresolved movements of the run, plus the
    movement just decided (decision 46). Reconciled ones stay as they were."""
    eng = new_engine(con)
    current = store.results(con, run_id)
    updated = []
    changed = 0
    for r in current:
        if r["status"] == engine_mod.RECONCILED and not (txn_ids and r["txn_id"] in txn_ids):
            updated.append(r)
            continue
        txn = eng.by_id.get(r["txn_id"])
        if txn is None:
            updated.append(r)
            continue
        new = eng.evaluate(txn)
        new["cases"] = r.get("cases", [])
        changed += json.dumps(new, sort_keys=True, default=str) != json.dumps(r, sort_keys=True, default=str)
        updated.append(new)
    con.execute("delete from results where run_id=?", (run_id,))
    con.executemany("insert into results(run_id,txn_id,status,payload_json) values(?,?,?,?)",
                    [(run_id, r["txn_id"], r["status"], json.dumps(r, default=str)) for r in updated])
    con.execute("update runs set summary_json=? where id=?", (json.dumps(engine_mod.summarize(updated)), run_id))
    con.commit()
    return changed
