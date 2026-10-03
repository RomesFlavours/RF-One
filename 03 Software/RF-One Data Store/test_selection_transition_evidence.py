#!/usr/bin/env python
"""SELECTION_TRANSITION_EVIDENCE_001 — "from another sector" is never
concluded from a missing, unrecognized or uncertainly read role.

ALL DATA BELOW IS SYNTHETIC: invented names, employers and dates.

  1. missing job title            -> "to be clarified", no transition
  2. unrecognized job title       -> "to be clarified", no transition
  3. uncertain title/employer     -> "verify the reading", no transition
  4. role positively classified as another sector -> the neutral transition
     question is still possible, with the résumé text as evidence.

Case 4 uses a SYNTHETIC classification injected by this test (a made-up
role code and category function). It verifies the rule's behaviour only; it
does not show that RF-One recognizes other sectors on real résumés — today
the Restaurant extension classifies no role as outside hospitality.

No database, no AI provider: the AI client is isolated for the whole run.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from rfone_data_store.selection.analysis import analyze_candidate
from rfone_data_store.selection.core import flags as flags_mod
from rfone_data_store.selection.core.profile import CandidateCVProfile, WorkHistoryRecord
from rfone_data_store.selection.core.role_model import RoleConfiguration
from rfone_data_store.selection.core.trajectory import detect_transitions_to_investigate
from rfone_data_store.selection.industry import restaurant
from rfone_data_store.selection.normalization import normalize_profile
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client

import test_selection_cv_structure as cv  # the synthetic résumés and parse() helper


def no_sector_conclusion(view) -> bool:
    """No transition was read and no text anywhere claims another sector."""
    texts = " ".join(f"{f.type} {f.evidence} {f.explanation} {f.suggested_question or ''}" for f in view.flags)
    return not view.transitions_to_investigate and "hospitality" not in texts.lower() \
        and not any(f.type in (flags_mod.ROLE_TRANSITION, "BOH_TO_FOH") for f in view.flags)


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    with isolated_ai_client():
        # --- 1. missing job title (e.g. as an AI reading could return it) ----
        missing = normalize_profile(CandidateCVProfile(
            full_name="Sam Synthetic", email="sam.synthetic@example.test",
            work_history=[
                WorkHistoryRecord(original_job_title="Server", employer="Cafe Campione",
                                  start_date_text="Jun 2017", end_date_text="Dec 2019",
                                  evidence_snippet="Server, Cafe Campione Jun 2017 - Dec 2019"),
                WorkHistoryRecord(original_job_title=None, employer="Trattoria Esempio",
                                  start_date_text="Mar 2022", end_date_text="Present",
                                  evidence_snippet="Trattoria Esempio Mar 2022 - Present"),
            ],
        ))
        view = analyze_candidate(missing, target_role="SERVER")
        check("1. missing title: no transition and no 'non-hospitality' conclusion", no_sector_conclusion(view),
              f"{[(f.type, f.explanation) for f in view.flags]}")
        check("1. missing title: a 'to be clarified' question about the role",
              any(f.type == flags_mod.MISSING_INFORMATION and "to be clarified" in f.explanation
                  and "Trattoria Esempio" in f.evidence for f in view.flags))

        # --- 2. unrecognized job title (title read correctly, not in catalog)
        # A Team Leader whose duties do not tie it to the dining room stays
        # unrecognized (SELECTION_FOH_TEAM_LEADER_001); with "coordinated
        # servers" it would now be read as FOH Supervisor.
        unrecognized = cv.parse(cv.SAME_SEPARATE_LINES.replace(
            "- Coordinated a team of 6 servers per shift\n- Trained new hires on service standards\n",
            "- Trained new hires on safety procedures\n"))
        check("2. setup: the most recent title is read but not recognized",
              unrecognized.work_history[0].original_job_title == "Team Leader"
              and unrecognized.work_history[0].normalized_role is None
              and unrecognized.work_history[0].structure_confidence == "HIGH")
        view = analyze_candidate(unrecognized, target_role="SERVER")
        check("2. unrecognized title: no transition and no 'non-hospitality' conclusion", no_sector_conclusion(view),
              f"{[(f.type, f.explanation) for f in view.flags]}")
        check("2. unrecognized title: a question asks what the role involved",
              any(f.type == flags_mod.TITLE_INCONSISTENCY and "Team Leader" in f.evidence for f in view.flags))

        # --- 3. uncertain title/employer association -------------------------
        uncertain = cv.parse(cv.AMBIGUOUS)
        view = analyze_candidate(uncertain, target_role="SERVER")
        check("3. uncertain reading: no transition and no 'non-hospitality' conclusion", no_sector_conclusion(view),
              f"{[(f.type, f.explanation) for f in view.flags]}")
        check("3. uncertain reading: exactly one request to verify the reading, not a second title question",
              sum(f.type == flags_mod.EXTRACTION_UNCERTAIN for f in view.flags) == 1
              and not any(f.type == flags_mod.MISSING_INFORMATION and "job title" in f.evidence for f in view.flags))

        # --- the status-review résumés: no false sector conclusion anymore --
        for name in ("REVIEW_LAYOUT_A", "REVIEW_LAYOUT_B"):
            view = analyze_candidate(cv.parse(getattr(cv, name)), target_role="SERVER")
            check(f"1-3. {name}: no 'Transition from Non Hospitality' anymore", no_sector_conclusion(view),
                  f"{[(f.type, f.explanation) for f in view.flags]}")

        # --- real catalog: nothing is classified outside hospitality --------
        check("4. Restaurant classifies no role as non-hospitality today (no false positive on real CVs)",
              not restaurant.NON_HOSPITALITY_ROLES
              and all(restaurant.role_category(code) != "NON_HOSPITALITY" for code in restaurant.ALL_CATALOG_ROLES))
        check("4. hotel work is hospitality: HOTEL_GUEST_SERVICE is never non-hospitality",
              restaurant.role_category("HOTEL_GUEST_SERVICE") != "NON_HOSPITALITY"
              and "HOTEL_GUEST_SERVICE" not in restaurant.NON_HOSPITALITY_ROLES)
        check("4. unrecognized and missing roles are 'to be clarified' (no category), not non-hospitality",
              restaurant.role_category(None) is None and restaurant.role_category("UNKNOWN_CODE") is None)

        # --- 4. SYNTHETIC positive classification (behaviour of the rule) ---
        synthetic_config = RoleConfiguration(
            target_role="SERVER", equivalent_roles=set(), propedeutic_roles=set(), adjacent_roles=set(),
            transition_flags={"NON_HOSPITALITY"},
        )

        def synthetic_category(code: str | None) -> str | None:
            return "NON_HOSPITALITY" if code == "SYNTHETIC_OTHER_SECTOR_ROLE" else None

        documented = WorkHistoryRecord(
            original_job_title="Synthetic Sales Associate", employer="Synthetic Hardware Store",
            normalized_role="SYNTHETIC_OTHER_SECTOR_ROLE", structure_confidence="HIGH",
            start_date_text="Jan 2021", start_date=datetime(2021, 1, 1, tzinfo=timezone.utc), end_date_text="Present",
            evidence_snippet="Synthetic Sales Associate, Synthetic Hardware Store Jan 2021 - Present",
        )
        transitions = detect_transitions_to_investigate([documented], synthetic_config,
                                                        role_category_fn=synthetic_category)
        flags = flags_mod.flag_role_transitions(transitions)
        check("4. positively classified other-sector role: the transition question is still raised",
              len(transitions) == 1 and transitions[0].from_category == "NON_HOSPITALITY" and len(flags) == 1)
        if flags:
            flag = flags[0]
            check("4. it stays a neutral question (REVIEW, motivation unknown, no verdict)",
                  flag.attention_level == flags_mod.REVIEW and "Motivation: Unknown" in flag.explanation
                  and flag.suggested_question and flag.suggested_question.startswith("Your recent experience"))
            check("4. it is backed by the original résumé text",
                  documented.evidence_snippet in flag.evidence and "Synthetic Hardware Store" in flag.evidence)

        documented_uncertain = WorkHistoryRecord(**{**documented.__dict__, "structure_confidence": "LOW"})
        check("4. the same role read uncertainly yields no transition (no conclusion from an uncertain reading)",
              detect_transitions_to_investigate([documented_uncertain], synthetic_config,
                                                role_category_fn=synthetic_category) == [])
        unclassified = WorkHistoryRecord(**{**documented.__dict__, "normalized_role": None})
        check("4. the same role without a positive classification yields no transition",
              detect_transitions_to_investigate([unclassified], synthetic_config,
                                                role_category_fn=synthetic_category) == [])

        # --- unchanged: positively classified restaurant transitions ---------
        boh = normalize_profile(CandidateCVProfile(full_name="Kim Synthetic", work_history=[
            WorkHistoryRecord(original_job_title="Line Cook", employer="Osteria Finta",
                              start_date_text="Jan 2020", end_date_text="Present", structure_confidence="HIGH")]))
        view = analyze_candidate(boh, target_role="SERVER")
        check("unchanged: a documented BOH role still raises the BOH -> FOH question",
              any(f.type == "BOH_TO_FOH" for f in view.flags))

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed.")
    print("ALL CHECKS PASSED" if failed == 0 else "SOME CHECKS FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
