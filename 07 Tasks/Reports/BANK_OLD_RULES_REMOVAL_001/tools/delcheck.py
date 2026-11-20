import os, re, sys, hashlib, subprocess
WT = r"C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules"
SW = os.path.join(WT, "03 Software"); DS = os.path.join(SW, "RF-One Data Store"); BR = os.path.join(DS, "rfone_data_store", "bank_reconciliation")
mods = ["pattern_discovery","why_rules","general_rules","receiver_candidates","structural_why","purpose_evidence","reconciliation_standards"]
scripts = ["apply_deterministic_bank_classification","apply_structural_why","apply_who_recognition","analyze_bank_purpose_evidence","analyze_historical_import"]
tests_ds = ["test_bank_deterministic_classification_who_safety","test_bank_structural_why","test_bank_structural_why_baseline","test_bank_who_recognition","test_bank_who_recognition_merge_safety","test_bank_recognition_expert_system","test_bank_memo_purpose_classification","test_bank_who_why_invariant"]
files = [os.path.join(BR, m + ".py") for m in mods] + [os.path.join(DS, s + ".py") for s in scripts] + [os.path.join(DS, t + ".py") for t in tests_ds] + [os.path.join(SW, "RF-One Web", "tests", "test_bank_reconciliation_standards_http.py")]
names = mods + scripts + tests_ds + ["test_bank_reconciliation_standards_http"]
delset = {os.path.normcase(f) for f in files}
snap = "snapshot/bank-worktree-20261012"
rows = []
for f in files:
    rel = os.path.relpath(f, WT).replace("\\", "/")
    data = open(f, "rb").read()
    blob = subprocess.run(["git", "-C", WT, "rev-parse", f"{snap}:{rel}"], capture_output=True, text=True).stdout.strip()
    here = subprocess.run(["git", "-C", WT, "hash-object", f], capture_output=True, text=True).stdout.strip()
    rows.append((f, len(data), hashlib.sha256(data).hexdigest()[:16], "identical" if blob == here else "DIFFERENT"))
# importers among kept files (.py, .html, .js, .ps1, .cmd, .json, .ini) anywhere in 03 Software
hits = []
pat = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
for dp, dn, fn in os.walk(SW):
    if "__pycache__" in dp: continue
    for x in fn:
        p = os.path.join(dp, x)
        if os.path.normcase(p) in delset or not x.endswith((".py", ".html", ".js", ".ps1", ".cmd", ".json", ".ini", ".toml", ".cfg", ".txt")): continue
        try: txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        for i, line in enumerate(txt.splitlines(), 1):
            m = pat.search(line)
            if m and re.search(r"\bimport\b|from\s+\S+\s+import|importlib|runpy|subprocess|\.py\b|python", line):
                hits.append(f"{os.path.relpath(p, WT)}:{i}: {line.strip()[:140]}")
for r in rows: print(f"{r[3]:9} {r[1]:7} {r[2]} {r[0]}")
print("count", len(rows))
print("IMPORT/RUN REFERENCES FROM KEPT FILES:", len(hits))
for h in hits: print("  ", h)
