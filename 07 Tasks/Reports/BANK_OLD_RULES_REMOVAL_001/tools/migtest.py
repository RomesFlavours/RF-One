"""Try d2b6f8a4c0e7 on a COPY of the live DB: upgrade, compare every kept table, integrity, downgrade, upgrade."""
import os, sys, sqlite3, hashlib, json
DS, LIVE, WORK = sys.argv[1:4]
copy = os.path.join(WORK, "migtest_copy.db")
if os.path.exists(copy): os.remove(copy)
src = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True); dst = sqlite3.connect(copy); src.backup(dst); dst.close(); src.close()
os.environ["RFONE_DATABASE_URL"] = "sqlite:///" + copy.replace("\\", "/")
sys.path.insert(0, DS); os.chdir(DS)
from alembic.config import Config
from alembic import command
cfg = Config("alembic.ini")
OLD = {"bank_recognition_rules","bank_who_recognitions","bank_reconciliation_standards","bank_general_rules","bank_why_rules","bank_pattern_suggestions","bank_learning_runs"}
DROPPED_COLS = {"bank_transaction_explanations": {"recognition_rule_id","reconciliation_standard_id"},
                "bank_transaction_allocations": {"reconciliation_standard_id"}, "bank_occurrences": {"manual_only"}}
def snap(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True); out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
        cols = [r[1] for r in c.execute(f'pragma table_info("{t}")')]
        out[t] = (cols, c.execute(f'select * from "{t}"').fetchall())
    rev = c.execute("select version_num from alembic_version").fetchall(); c.close(); return out, rev
def digest(cols, rows, keep):
    idx = [cols.index(k) for k in keep]
    key = cols.index("id") if "id" in cols else None
    rs = sorted((tuple(r[i] for i in idx) for r in rows), key=lambda r: repr(r))
    return len(rs), hashlib.sha256(repr(rs).encode()).hexdigest()[:16]
before, rev0 = snap(copy)
counts = {t: len(before[t][1]) for t in OLD}
command.upgrade(cfg, "head")
after, rev1 = snap(copy)
problems = []
for t, (cols, rows) in before.items():
    if t in OLD:
        if t in after: problems.append(f"{t} still exists")
        continue
    if t == "alembic_version": continue
    if t not in after: problems.append(f"{t} missing after upgrade"); continue
    acols, arows = after[t]
    gone = set(cols) - set(acols)
    if gone != DROPPED_COLS.get(t, set()): problems.append(f"{t}: dropped columns {gone}")
    if set(acols) - set(cols): problems.append(f"{t}: new columns {set(acols)-set(cols)}")
    keep = [c for c in cols if c in acols]
    if digest(cols, rows, keep) != digest(acols, arows, keep): problems.append(f"{t}: CONTENT CHANGED")
c = sqlite3.connect(copy)
fk = c.execute("pragma foreign_key_check").fetchall(); ic = c.execute("pragma integrity_check").fetchone()[0]
schema_bte = c.execute("select sql from sqlite_master where name='bank_transaction_explanations'").fetchone()[0]
c.close()
summary = {"revision_before": rev0, "revision_after": rev1, "old_table_rows_before": counts,
           "tables_compared": len([t for t in before if t not in OLD and t != "alembic_version"]),
           "problems": problems, "foreign_key_check": len(fk), "integrity_check": ic,
           "standard_in_check": "STANDARD" in schema_bte}
# roundtrip
command.downgrade(cfg, "a3c7e5b9d1f4"); down, revd = snap(copy)
summary["downgrade_revision"] = revd
summary["downgrade_old_tables_back_empty"] = all(t in down and len(down[t][1]) == 0 for t in OLD)
summary["downgrade_columns_back"] = all(set(DROPPED_COLS[t]) <= set(down[t][0]) for t in DROPPED_COLS)
command.upgrade(cfg, "head"); again, reva = snap(copy)
summary["reupgrade_revision"] = reva
summary["reupgrade_same_as_first_upgrade"] = all(
    digest(*again[t], again[t][0]) == digest(*after[t], after[t][0]) for t in after if t != "alembic_version")
print(json.dumps(summary, indent=1, default=str))
json.dump(summary, open(os.path.join(WORK, "migtest_summary.json"), "w"), indent=1, default=str)
