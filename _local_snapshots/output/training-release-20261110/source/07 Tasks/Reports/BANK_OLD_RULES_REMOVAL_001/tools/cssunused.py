import os, re, sys
WEB = sys.argv[1]
css_path = os.path.join(WEB, "static", "css", "rf-one.css")
css = open(css_path, encoding="utf-8").read()
corpus = []
for dp, dn, fn in os.walk(os.path.join(WEB)):
    if "__pycache__" in dp or os.sep + "tests" in dp: continue
    for f in fn:
        if f.endswith((".html", ".js", ".py")):
            corpus.append(open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read())
ds = os.path.join(os.path.dirname(WEB), "RF-One Data Store", "rfone_data_store")
for dp, dn, fn in os.walk(ds):
    for f in fn:
        if f.endswith(".py"): corpus.append(open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read())
text = "\n".join(corpus)
tokens = set(re.findall(r"[A-Za-z0-9_-]+", text))
# walk top-level rules with line numbers (ignores nesting inside @media for simplicity: handles one level)
line_of = lambda pos: css.count("\n", 0, pos) + 1
i = 0; out = []
for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
    sel = m.group(1).strip()
    if sel.startswith("@") or not sel: continue
    sel_clean = re.sub(r"/\*.*?\*/", "", sel, flags=re.S).strip()
    classes = set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", sel_clean))
    if not classes: continue
    # a selector list: rule is unused when EVERY comma-separated selector has some unused class
    parts = [p.strip() for p in sel_clean.split(",")]
    def part_used(p):
        cs = re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", p)
        return all(c in tokens for c in cs)
    unused_parts = [p for p in parts if not part_used(p)]
    if unused_parts:
        out.append((line_of(m.start(1) + len(m.group(1)) - len(m.group(1).lstrip())), len(unused_parts) == len(parts), sel_clean.replace("\n", " ")[:150]))
for ln, whole, s in out: print(("WHOLE " if whole else "PART  ") + f"{ln}: {s}")
print(len(out), "rules with unused selectors")
