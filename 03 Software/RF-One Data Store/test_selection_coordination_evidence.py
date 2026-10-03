#!/usr/bin/env python
"""SELECTION_COORDINATION_EVIDENCE_001 — coordination responsibilities
declared in the duties, kept apart from the declared role.

ALL RÉSUMÉS BELOW ARE SYNTHETIC (invented people, employers and dates).

Covered: explicit responsibilities under a Server title; a Team Leader with
no duties; training with no stated trainees; managing tasks without people;
coordination in the kitchen; duties of different experiences kept apart; an
uncertain structural reading (attribution to verify); generic phrases and
supporting a superior are not evidence; no role change, no months, no
score; one neutral question per evidence, else the one general question.

No database, no AI provider (isolated).
"""

from __future__ import annotations

import sys

from rfone_data_store.selection.analysis import analyze_candidate
from rfone_data_store.selection.core import coordination_evidence as ce
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client

import test_selection_cv_structure as cv

HEAD = "Sam Synthetic\nsam.synthetic@example.test\n\nEXPERIENCE\n"

SERVER_WITH_DUTIES = HEAD + """Server, Cafe Campione
Jun 2017 - Dec 2019
- Trained new hires on the menu
- Coordinated a team of 6 servers on weekend shifts
- Managed reservations and the waiting list
- Team player with strong leadership skills
- Assisted the supervisor with closing duties
"""

TEAM_LEADER_NO_DUTIES = HEAD + """Team Leader, Trattoria Esempio
Mar 2022 - Present
"""

TRAINING_NO_TRAINEES = HEAD + """Server, Cafe Campione
Jun 2017 - Dec 2019
- Delivered training sessions on wine service
- Completed food safety training
"""

KITCHEN = HEAD + """Line Cook, Osteria Finta
Jan 2021 - Present
- Coordinated kitchen staff during dinner service
"""

TWO_EXPERIENCES = HEAD + """Floor Supervisor
Bistro Prova, Toronto, ON
Jan 2020 - Feb 2022
- Assigned sections to four servers each shift
Server
Cafe Campione, Toronto, ON
Jun 2017 - Dec 2019
- Trained new hires on the menu
"""


def evidence_for(text: str, target: str = "FOH_SUPERVISOR"):
    profile = cv.parse(text)
    return profile, analyze_candidate(profile, target_role=target)


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    with isolated_ai_client():
        # --- 1. explicit responsibilities under a Server title ---------------
        profile, view = evidence_for(SERVER_WITH_DUTIES)
        ev = view.coordination_evidence
        found = {(e.category, e.sentence) for e in ev}
        check("1. two declared responsibilities found under the Server job",
              found == {(ce.TRAINING, "Trained new hires on the menu"),
                        (ce.COORDINATION, "Coordinated a team of 6 servers on weekend shifts")},
              f"{found}")
        coord = next((e for e in ev if e.category == ce.COORDINATION), None)
        train = next((e for e in ev if e.category == ce.TRAINING), None)
        check("1. 'coordinated a team of 6 servers': 6 people declared, dining room",
              coord is not None and coord.people_count == 6 and coord.area == "FOH")
        check("1. 'trained new hires': training declared, area to be clarified, no number invented",
              train is not None and train.area == ce.AREA_TO_CLARIFY and train.people_count is None
              and train.recipients_stated)
        check("1. each evidence keeps its experience and original text",
              all(e.experience_index == 0 and e.experience_title == "Server"
                  and e.experience_employer == "Cafe Campione" for e in ev))
        check("1. reservations, 'team player', 'leadership skills' and assisting the supervisor are not evidence",
              not any(w in " ".join(e.sentence for e in ev).lower()
                      for w in ("reservations", "team player", "assisted")))
        check("1. the Server stays a Server: the normalized role is unchanged",
              profile.work_history[0].normalized_role == "SERVER")
        check("1. no new months: FOH Team Leader direct experience and supervisory months stay 0",
              next(i.raw_value for i in view.indicators if i.name == "Direct Role Experience") == "0 months"
              and next(i.raw_value for i in view.indicators if i.name == "Supervisory Responsibility") == "0 months")
        check("1. one neutral question per evidence, quoting it; no general question",
              len(view.coordination_questions) == 2
              and all(e.question in view.coordination_questions and f'"{e.sentence}"' in e.question for e in ev)
              and ce.GENERAL_QUESTION not in view.coordination_questions)

        # --- 2. Team Leader without described duties -------------------------
        _, view = evidence_for(TEAM_LEADER_NO_DUTIES)
        check("2. Team Leader with no duties: no evidence, only the general question",
              view.coordination_evidence == [] and view.coordination_questions == [ce.GENERAL_QUESTION])

        # --- 3. training with no stated trainees ----------------------------
        _, view = evidence_for(TRAINING_NO_TRAINEES)
        ev = view.coordination_evidence
        check("3. training delivered without trainees: training, who was trained not specified",
              len(ev) == 1 and ev[0].category == ce.TRAINING and ev[0].recipients_stated is False,
              f"{[(e.category, e.sentence, e.recipients_stated) for e in ev]}")
        check("3. completing a training oneself is not training others",
              not any("Completed" in e.sentence for e in ev))

        # --- 4. tasks without people ------------------------------------------
        check("4. 'managed reservations' alone is not coordination of people",
              ce.classify_sentence("Managed reservations and inventory") is None)

        # --- 5. kitchen coordination -------------------------------------------
        profile, view = evidence_for(KITCHEN)
        ev = view.coordination_evidence
        check("5. coordinating kitchen staff: declared coordination in the kitchen",
              len(ev) == 1 and ev[0].category == ce.COORDINATION and ev[0].area == "KITCHEN")
        check("5. it is not FOH Supervisor experience: role unchanged, no direct FOH Team Leader months",
              profile.work_history[0].normalized_role == "LINE_COOK"
              and next(i.raw_value for i in view.indicators if i.name == "Direct Role Experience") == "0 months")

        # --- 6. different experiences are not mixed ---------------------------
        profile, view = evidence_for(TWO_EXPERIENCES)
        pairs = [(e.experience_title, e.category, e.sentence) for e in view.coordination_evidence]
        check("6. each duty stays with its own experience (entries without blank lines)",
              pairs == [("Floor Supervisor", ce.ASSIGNMENT, "Assigned sections to four servers each shift"),
                        ("Server", ce.TRAINING, "Trained new hires on the menu")], f"{pairs}")
        check("6. 'four servers' is read as 4 declared people in the dining room",
              view.coordination_evidence[0].people_count == 4 and view.coordination_evidence[0].area == "FOH")

        # --- 7. uncertain structural reading -------------------------------------
        profile, view = evidence_for(cv.AMBIGUOUS)
        ev = view.coordination_evidence
        check("7. uncertain reading: the duty is shown, but its experience must be verified first",
              len(ev) == 1 and ev[0].attribution_to_verify and ev[0].experience_title is None
              and ev[0].experience_employer is None, f"{ev}")

        # --- separation from role, indicators and score -------------------------
        _, without = evidence_for(TEAM_LEADER_NO_DUTIES)
        _, with_ev = evidence_for(SERVER_WITH_DUTIES)
        check("no new Indicator and no score: the Indicator list is the same with or without evidence",
              [i.name for i in without.indicators] == [i.name for i in with_ev.indicators])

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed.")
    print("ALL CHECKS PASSED" if failed == 0 else "SOME CHECKS FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
