"""Plan every ACTIVE AI rule over every in-scope movement, writing nothing.
Usage: plan_compare.py <Data Store dir> <db file> <out json>"""
import sys, os, json, hashlib
ds, db, out = sys.argv[1:4]
sys.path.insert(0, ds)
os.environ["RFONE_DATABASE_URL"] = "sqlite:///" + db.replace("\\", "/")
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules
import rfone_data_store
assert os.path.abspath(rfone_data_store.__file__).startswith(os.path.abspath(ds)), rfone_data_store.__file__
eng = create_engine(os.environ["RFONE_DATABASE_URL"])
res = {}
with Session(eng) as s:
    rows = ai_rules.scope_rows(s, scope=ai_rules.SCOPE_ALL, date_from=None, date_to=None, selected_ids=None)
    res["_rows"] = len(rows)
    for rule_id, spec in ai_rules._active_rule_specs(s):
        planner = ai_rules.Planner(s, rule_id=rule_id)
        for cmw in (False, True):
            outcomes = []
            for row in rows:
                ex = ai_rules.execute(spec, row)
                if ex.outcome != "MATCH":
                    continue
                target = planner.target_of(ex)
                p = planner.plan_full(row, target, create_missing_who=cmw)
                outcomes.append([row.id, p.outcome, p.note, p.who_after, p.why_after, list(p.changes),
                                 list(p.overridden), p.withdraw_acceptance, list(p.overlaps)])
            key = f"rule{rule_id}_cmw{int(cmw)}"
            res[key] = {"matched": len(outcomes),
                        "by_outcome": {o: sum(1 for x in outcomes if x[1] == o) for o in sorted({x[1] for x in outcomes})},
                        "sha": hashlib.sha256(json.dumps(outcomes, ensure_ascii=False).encode()).hexdigest()[:16],
                        "items": outcomes}
    s.rollback()
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("rows", res["_rows"], {k: (v["matched"], v["by_outcome"], v["sha"]) for k, v in res.items() if k != "_rows"})
