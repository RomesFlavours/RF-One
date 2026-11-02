#!/usr/bin/env python
"""CV Selection SP on real-shaped CVs (SELECTION_SP_REAL_CVS_001) with a FAKE AI (no network, no database).

The other SP tests use short, clean CVs: headings in capitals, one job at a time, the name on the first line,
PDFs with text inside. Real CVs are not like that. Each case here is the shape of a real CV (names and contacts
invented) and the mistake it used to cause.

    python test_sp_real_cvs.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "RF-One Data Store")]

from workspace import ai_adapter, cv_reading  # noqa: E402
from workspace.sp import analysis as sp_analysis  # noqa: E402
from workspace.sp import profiles as spp  # noqa: E402
from workspace.sp import ranking as sp_ranking  # noqa: E402
from workspace.sp import rules as sp_rules  # noqa: E402
from workspace.sp import timeline as sp_timeline  # noqa: E402

TODAY = date(2026, 11, 2)
failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


# 1. Title Case headings, Skills BEFORE Experience (the most common layout in the Friday CVs).
SKILLS_FIRST = """Ana Ruiz
Server | Mount Dora, FL

Skills
Wine service, POS (Toast), upselling
Menu knowledge

Experience
Lead Server, Osteria Verde | Mar 2021 - Present
Provided wine service to 40 tables nightly and trained 6 new servers
Server, Blue Plate Diner | Jun 2018 - Feb 2021
Full table service in a 120-seat dining room

Education
Lake Sumter State College
"""

# 2. A long job with two short second jobs held at the same time (normal in restaurants).
SECOND_JOBS = """Tom Becker

WORK HISTORY
Line Cook, Harbor Grill | Jan 2015 - Present
Grill and sauté station, 300 covers a night
Prep Cook, Sunday Brunch Club | Mar 2019 - Jul 2019
Weekend prep for brunch service
Banquet Cook, Lakeside Events | Apr 2022 - Aug 2022
Seasonal banquet line for weddings
"""

# 3. Short stays that are the person's real history (studies, caring): with the rule off they must not count.
SHORT_STAYS = """Lee Park

EXPERIENCE
Server, Cafe Uno | Jan 2025 - Apr 2025
Table service at lunch
Server, Pasta House | May 2025 - Aug 2025
Table service at dinner, 8 tables
Server, Trattoria Roma | Sep 2025 - Present
Full table service, wine pairing suggestions, closing duties
"""


def fake_skills_first(prompt):
    return {"full_name": "Ana Ruiz",
            "jobs": [{"employer": "Osteria Verde", "title": "Lead Server", "date_text": "Mar 2021 - Present",
                      "environment": "Italian full-service", "relevant": True,
                      "duties": "Wine service and training; she is a US citizen"},
                     {"employer": "Blue Plate Diner", "title": "Server", "date_text": "Jun 2018 - Feb 2021",
                      "environment": "Diner, breakfast chain", "relevant": True}],
            "requirements": {
                "table_service": {"level": 4, "quotes": ["Provided wine service to 40 tables nightly"],
                                  "explanation": "Clear table and wine service."},
                "guest_selling": {"level": 3, "quotes": ["Server"],
                                        "explanation": "A young server, which suits the team."}},
            "competences": [{"name": "wine service", "level": "executed",
                             "quote": "Provided wine service to 40 tables nightly"},
                            {"name": "POS", "level": "owned", "quote": "POS (Toast)"}],
            "risk_flags": [{"flag": "Visa status unclear", "fact": "", "quote": "Server"}]}


try:
    reqs = spp.default_requirements("SERVER")
    req_ids = {r["id"] for r in reqs}

    # --- 1. Skills before Experience -------------------------------------------------------------------------
    skills = sp_analysis.skills_text(SKILLS_FIRST)
    check("Title Case: the Skills section ends at 'Experience'", "wine service, pos" in skills
          and "provided wine service to 40 tables" not in skills and "osteria" not in skills, skills)
    a = sp_analysis.analyze_cv(role_code="SERVER", requirements=reqs, cv_text=SKILLS_FIRST, today=TODAY,
                               generate=fake_skills_first)
    if "table_service" in req_ids:
        check("Title Case: a duty under Experience stays strong evidence (level 4, not 'claimed')",
              a["requirements"]["table_service"]["level"] == 4, a["requirements"]["table_service"])
    comp = {c["name"]: c["level"] for c in a["competences"]}
    check("a duty under Experience stays 'executed'", comp.get("wine service") == "executed", comp)
    check("a two-word quote cannot make a competence 'owned'", comp.get("POS") == "claimed", comp)
    if "guest_selling" in req_ids:
        g = a["requirements"]["guest_selling"]
        check("a one-word quote ('Server') supports a claim at most (level 1)", g["level"] == 1, g)
        check("an explanation mentioning age is removed", "young" not in g["explanation"], g["explanation"])
    check("a flag about visa status is dropped", not any("Visa" in f["flag"] for f in a["flags"]), a["flags"])
    check("job duties mentioning citizenship are not shown", a["jobs"][0]["duties"] is None, a["jobs"][0])

    # --- 2. Jobs held at the same time ----------------------------------------------------------------------
    jobs = [{"employer": "Harbor Grill", "date_text": "Jan 2015 - Present", "relevant": True},
            {"employer": "Sunday Brunch Club", "date_text": "Mar 2019 - Jul 2019", "relevant": True},
            {"employer": "Lakeside Events", "date_text": "Apr 2022 - Aug 2022", "relevant": True}]
    t = sp_timeline.analyze(jobs, SECOND_JOBS, TODAY)
    check("second jobs: no gap is invented inside a job that never stopped", t["gaps"] == [], t["gaps"])
    check("second jobs: two short side jobs are not 'two consecutive short jobs'",
          not t["stability"]["flags"], t["stability"])
    check("second jobs: 11 years at one kitchen is the top stability level", t["stability"]["level"] == 4,
          t["stability"])
    real_gap = sp_timeline.analyze(
        [{"employer": "Harbor Grill", "date_text": "Jan 2015 - Present", "relevant": True}][:0]
        + [{"employer": "Cafe Uno", "date_text": "Jan 2025 - Apr 2025"},
           {"employer": "Trattoria Roma", "date_text": "Sep 2025 - Present"}], SHORT_STAYS, TODAY)
    check("a real gap between two jobs is still listed", len(real_gap["gaps"]) == 1, real_gap["gaps"])

    # --- 3. Short stays switched off -------------------------------------------------------------------------
    def fake_short(prompt):
        return {"full_name": "Lee Park",
                "jobs": [{"employer": "Cafe Uno", "date_text": "Jan 2025 - Apr 2025", "relevant": True},
                         {"employer": "Pasta House", "date_text": "May 2025 - Aug 2025", "relevant": True},
                         {"employer": "Trattoria Roma", "date_text": "Sep 2025 - Present", "relevant": True}],
                "requirements": {r["id"]: {"level": 3, "quotes": ["Full table service, wine pairing suggestions"]}
                                 for r in reqs if not r.get("computed")}}
    lee = sp_analysis.analyze_cv(role_code="SERVER", requirements=reqs, cv_text=SHORT_STAYS, today=TODAY,
                                 generate=fake_short)
    must = [dict(r, criticality=spp.MUST_HAVE) if r.get("computed") else r for r in reqs]
    on = sp_ranking.assess(lee, must)
    off = sp_ranking.assess(sp_rules.apply(lee, "SERVER", {"short_stays": False}), must)
    check("short stays on, stability as Must-have: the pattern is to verify (B), never D alone",
          on["group"] == "B", (on["group"], on["group_reason"]))
    check("short stays off: stability no longer counts in the group", off["group"] == "A",
          (off["group"], off["group_reason"]))
    check("short stays off: stability is shown as not counted",
          next(i for i in off["items"] if i.get("computed"))["status"] == sp_ranking.NOT_ASSESSABLE)
    check("the stored analysis is not changed by the switch", lee["requirements"]["stability"]["level"] is not None)

    # --- 4. A scanned PDF (no text inside) -------------------------------------------------------------------
    try:
        from PIL import Image, ImageDraw
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "scan.pdf")
        img = Image.new("RGB", (850, 1100), "white")
        ImageDraw.Draw(img).text((60, 60), "Maria Lopez  Server  2019 - 2024", fill="black")
        img.save(path, "PDF")
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            empty = not (pdf.pages[0].extract_text() or "").strip()
        check("scan: the PDF really has no text inside", empty)
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
        seen = {}
        original = cv_reading._transcribe_transport
        cv_reading._transcribe_transport = lambda images: (seen.setdefault("pages", len(images)),
                                                            "Maria Lopez\nServer, 2019 - 2024")[1]
        try:
            text = cv_reading.transcribe_pdf(path)
        finally:
            cv_reading._transcribe_transport = original
        check("scan: its page goes to the AI as an image and comes back as text",
              seen.get("pages") == 1 and text.startswith("Maria Lopez"), (seen, text))
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=False)
        try:
            cv_reading.transcribe_pdf(path)
            refused = False
        except Exception:
            refused = True
        check("scan: nothing is sent when AI résumé reading is off", refused)
    except ImportError as exc:
        check("scan: Pillow and pdfplumber available", False, exc)

    # --- 5. The AI answer cap --------------------------------------------------------------------------------
    from rfone_data_store.selection.parsing import ai_client
    check("long CVs: the AI answer cap is 16,000 tokens", ai_client.MAX_OUTPUT_TOKENS == 16000)
finally:
    pass

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED")
sys.exit(1 if failures else 0)
