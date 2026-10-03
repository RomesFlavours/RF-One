#!/usr/bin/env python
"""SELECTION_INDICATOR_EXPLANATIONS_001 — explanations of Direct and
Propedeutic Experience, Stability and Career Progression.

ALL RÉSUMÉS BELOW ARE SYNTHETIC (invented people, employers and dates).

  1. the shown value matches the experiences used;
  2. the same CV is explained differently for Server and FOH Team Leader;
  3. missing dates, an uncertain reading or no target role: "to be
     clarified", with the reason and known durations as detail only;
  4. stability and progression restate the existing rules and thresholds.
(Candidate page vs comparison coherence: Selection/test_preselection_http.py.)

No database, no AI provider (isolated).
"""

from __future__ import annotations

import sys

from rfone_data_store.selection import indicator_explanations as expl
from rfone_data_store.selection.analysis import analyze_candidate
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client

import test_selection_cv_structure as cv

UNDATED_SUPERVISOR = """Lee Synthetic
lee.synthetic@example.test

EXPERIENCE
Team Leader
Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift

Floor Supervisor, Bistro Prova
- Opened and closed the dining room
"""
NO_DATES = """Cal Synthetic
cal.synthetic@example.test

EXPERIENCE
Floor Supervisor, Bistro Prova
- Opened and closed the dining room
"""


def ind(view, name):
    return next(i for i in view.indicators if i.name == name)


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    with isolated_ai_client():
        profile = cv.parse(cv.SAME_SEPARATE_LINES)
        foh = analyze_candidate(profile, target_role="FOH_SUPERVISOR")
        srv = analyze_candidate(profile, target_role="SERVER")

        # --- 1. value = experiences used ----------------------------------------
        for label, view in (("FOH Team Leader", foh), ("Server", srv)):
            for name in (expl.DIRECT, expl.PROPEDEUTIC_NAME):
                e = view.explanations[name]
                check(f"1. {label} / {name}: the value is the sum of the experiences used",
                      ind(view, name).raw_value == e.value
                      and e.total_months == sum(u.months for u in e.used)
                      and e.value == f"{e.total_months} month{'s' if e.total_months != 1 else ''}",
                      f"{e.value} {[(u.title, u.months) for u in e.used]}")
        check("1. FOH Team Leader: direct = Team Leader + Floor Supervisor, propedeutic = Server",
              [u.title for u in foh.explanations[expl.DIRECT].used] == ["Team Leader", "Floor Supervisor"]
              and [u.title for u in foh.explanations[expl.PROPEDEUTIC_NAME].used] == ["Server"])
        check("1. each experience used shows its original title, dates as written and duration",
              all(u.start and u.end and u.months is not None for u in foh.explanations[expl.DIRECT].used)
              and foh.explanations[expl.DIRECT].used[0].start == "Mar 2022")

        # --- 2. Server vs FOH Team Leader -----------------------------------------
        fd, sd = foh.explanations[expl.DIRECT], srv.explanations[expl.DIRECT]
        check("2. the same CV is explained differently for the two target roles",
              [u.title for u in sd.used] == ["Server"] and [u.title for u in fd.used] != [u.title for u in sd.used]
              and "the target role FOH Team Leader" in fd.used[0].reason
              and "the target role Server" in sd.used[0].reason
              and "(FOH Team Leader)" in fd.criteria[0] and "(Server)" in sd.criteria[0])
        check("2. propedeutic reasons name the target role",
              "propedeutic for FOH Team Leader" in foh.explanations[expl.PROPEDEUTIC_NAME].used[0].reason)
        check("2. role months come from titles; declared duties are said to be separate",
              all(expl.TITLES_NOT_DUTIES in e.criteria for e in (fd, sd)))

        # --- 3. to be clarified, with the reason -----------------------------------
        view = analyze_candidate(cv.parse(UNDATED_SUPERVISOR), target_role="FOH_SUPERVISOR")
        e = view.explanations[expl.DIRECT]
        check("3. missing dates: direct experience is 'to be clarified' on the page as well",
              e.value == expl.TO_CLARIFY and ind(view, expl.DIRECT).raw_value == expl.TO_CLARIFY
              and e.total_months is None)
        check("3. ...the reason names the experience without usable dates",
              e.to_clarify and "Floor Supervisor" in e.to_clarify and "no usable dates" in e.to_clarify)
        check("3. ...known durations are kept as detail only, not as a total",
              e.known_months_detail == next(u.months for u in e.used if u.title == "Team Leader")
              and e.total_months is None)
        view = analyze_candidate(cv.parse(cv.AMBIGUOUS), target_role="FOH_SUPERVISOR")
        e = view.explanations[expl.DIRECT]
        check("3. uncertain reading: 'to be clarified', said to be about how the CV was read",
              e.value == expl.TO_CLARIFY and "could not be read with certainty" in e.to_clarify)
        view = analyze_candidate(profile, target_role=None)
        e = view.explanations[expl.DIRECT]
        check("3. no target role: 'to be clarified' because the application has no supported target role",
              e.total_months is None and "no supported target role" in e.to_clarify)
        view = analyze_candidate(cv.parse(NO_DATES), target_role="FOH_SUPERVISOR")
        e = view.explanations[expl.STABILITY]
        check("3. stability with no dated job: Unknown, explained by the missing dates",
              e.state == "Unknown" and "No job has a usable duration" in (e.to_clarify or "")
              and any("no usable dates" in l for l in e.limitations))

        # --- 4. the existing rules, restated ------------------------------------------
        st = foh.explanations[expl.STABILITY]
        rules = " ".join(st.criteria)
        check("4. stability: thresholds as implemented (6 months, 50%, 12 months) and the inputs used",
              "under 6 months" in rules and "50% or more" in rules and "under 12 months" in rules
              and "Distinct employers counted: 3" in rules and len(st.used) == 3 and st.state == "Strong")
        pr = foh.explanations[expl.PROGRESSION]
        check("4. progression: each compared pair with its ranks and the kind of move",
              pr.state == "Observed" and len(pr.used) == 2
              and any("rank 2 → 3" in u.reason and "increase in responsibility" in u.reason for u in pr.used)
              and any("rank 3 → 3" in u.reason and "same rank" in u.reason for u in pr.used),
              f"{[u.reason for u in pr.used]}")
        view = analyze_candidate(cv.parse(UNDATED_SUPERVISOR), target_role="FOH_SUPERVISOR")
        pr = view.explanations[expl.PROGRESSION]
        check("4. progression: a job without start date is listed as not compared",
              any("no start date" in l for l in pr.limitations) and pr.state == "Not observed")

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed.")
    print("ALL CHECKS PASSED" if failed == 0 else "SOME CHECKS FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
