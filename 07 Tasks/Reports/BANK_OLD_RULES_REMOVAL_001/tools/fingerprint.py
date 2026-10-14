"""Per-table row count and content hash of an SQLite DB (read-only)."""
import sqlite3, hashlib, json, sys
src, out = sys.argv[1], sys.argv[2]
con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
res = {}
for (t,) in con.execute("select name from sqlite_master where type='table' order by name"):
    cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
    h = hashlib.sha256(); n = 0
    for row in con.execute(f'select * from "{t}" order by rowid' if t!='alembic_version' else f'select * from "{t}"'):
        h.update(repr(row).encode()); n += 1
    res[t] = {"rows": n, "sha": h.hexdigest()[:16], "cols": cols}
res["_alembic"] = con.execute("select version_num from alembic_version").fetchall()
json.dump(res, open(out, "w"), indent=1)
print(len(res), "tables;", res["_alembic"])
for t in ["financial_transactions","raw_bank_transactions","bank_transaction_explanations","bank_occurrences","bank_transaction_reasons","bank_ai_rules","bank_ai_rule_versions","bank_ai_rule_interpretations","bank_ai_rule_applications","bank_ai_rule_application_items","bank_recognition_rules","bank_general_rules","bank_why_rules","bank_learning_runs","bank_pattern_suggestions","bank_reconciliation_standards","bank_who_recognitions"]:
    print(t, res.get(t, {}).get("rows"))
