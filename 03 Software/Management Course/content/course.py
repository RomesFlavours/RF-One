"""The training course, read from a master course file.

The engine teaches whatever course file it's given: units in levels, each
unit with its modules (what the person must show, and a situation to start
from), its short multiple-choice test, its prerequisites and its practical
checks. Another role or subject is another course file in content/courses,
chosen with RFONE_TRAINER_COURSE; nothing in the engine changes.

The course's own text (the master document) is what the AI Trainer teaches
from; each unit's section of it is also its downloadable guide.

Selection (the candidate interview) still uses content/modules.py.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent / "courses"
FILE = os.environ.get("RFONE_TRAINER_COURSE", "rf-server-course-v1.json")

COURSE = json.loads((DIR / FILE).read_text(encoding="utf-8"))
MASTER = (DIR / COURSE["master_text"]).read_text(encoding="utf-8")
LEVELS = {lv["id"]: lv for lv in COURSE["levels"]}
PASS_MARK = int(COURSE.get("pass_mark", 4))
# "server" (taught and tested) or "management" (reasoning kept as evidence, no tests).
KIND = COURSE.get("kind", "server")
SESSION_MINUTES = int(COURSE.get("session_minutes", 20))

UNITS: list[dict] = []
for n, u in enumerate(COURSE["units"], 1):
    draw = min(int(u.get("draw") or len(u["test"])), len(u["test"]))
    # A test is a random draw from the unit's bank. A safety unit needs every
    # answer right; the others need PASS_MARK of the draw.
    unit = dict(u, number=n, level_title=LEVELS[u["level"]]["title"], draw=draw,
                pass_mark=draw if u.get("safety_critical") else min(PASS_MARK, draw),
                pills=[dict(m, module=u["id"]) for m in u["modules"]])
    unit.pop("modules", None)
    UNITS.append(unit)
UNIT_BY_ID = {u["id"]: u for u in UNITS}
PILLS = {p["id"]: p for u in UNITS for p in u["pills"]}
QUESTIONS = {q["id"]: dict(q, unit=u["id"]) for u in UNITS for q in u["test"]}


def unit_text(uid: str) -> str:
    """The unit's own section of the master document (### A1. ... up to the next unit or chapter)."""
    m = re.search(rf"^### {re.escape(uid)}\. .*?(?=^### |^## |\Z)", MASTER, flags=re.M | re.S)
    return m.group(0).strip() if m else ""


for _u in UNITS:
    assert unit_text(_u["id"]), f"No section for unit {_u['id']} in {COURSE['master_text']}"
    for _p in _u["prerequisites"]:
        assert _p in UNIT_BY_ID, f"Unknown prerequisite {_p} in {_u['id']}"
