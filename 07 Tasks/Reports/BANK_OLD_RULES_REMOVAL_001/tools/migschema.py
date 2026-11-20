import os, sys, sqlite3, re
DS, LIVE, WORK = sys.argv[1:4]
copy = os.path.join(WORK, "migtest_copy.db")   # already at head after migtest.py
live = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True); new = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
def objs(c):
    return {(t, n): re.sub(r"\s+", " ", (s or "")) for t, n, s in c.execute("select type, name, sql from sqlite_master where name not like 'sqlite_%'")}
a, b = objs(live), objs(new)
OLD = ("bank_recognition_rules","bank_who_recognitions","bank_reconciliation_standards","bank_general_rules","bank_why_rules","bank_pattern_suggestions","bank_learning_runs")
REBUILT = ("bank_transaction_explanations", "bank_transaction_allocations", "bank_occurrences")
only_live = sorted(k for k in a if k not in b); only_new = sorted(k for k in b if k not in a)
changed = sorted(k for k in a if k in b and a[k] != b[k])
print("only before:", [k for k in only_live if not any(o in k[1] for o in OLD)])
print("  (old-table objects removed:", len([k for k in only_live if any(o in k[1] for o in OLD)]), ")")
print("only after:", only_new)
print("changed:", changed)
# indexes on rebuilt tables
for t in REBUILT:
    il = sorted(r[1] for r in live.execute(f"pragma index_list('{t}')")); inew = sorted(r[1] for r in new.execute(f"pragma index_list('{t}')"))
    print(t, "indexes lost:", sorted(set(il)-set(inew)), "gained:", sorted(set(inew)-set(il)))
    fl = sorted(tuple(r[2:5]) for r in live.execute(f"pragma foreign_key_list('{t}')")); fn = sorted(tuple(r[2:5]) for r in new.execute(f"pragma foreign_key_list('{t}')"))
    print("   FKs lost:", sorted(set(fl)-set(fn)), "gained:", sorted(set(fn)-set(fl)))
    cl = set(re.findall(r"CONSTRAINT (\w+) CHECK", a[("table", t)])); cn = set(re.findall(r"CONSTRAINT (\w+) CHECK", b[("table", t)]))
    print("   CHECKs lost:", sorted(cl-cn), "gained:", sorted(cn-cl))
