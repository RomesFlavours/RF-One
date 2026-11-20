#!/usr/bin/env python
"""SELECTION_FOH_TEAM_LEADER_001 — FOH Team Leader recognition and analysis
for the application's target role.

ALL DATA BELOW IS SYNTHETIC: invented names, employers, dates and duties.

Covered:
  1. explicit FOH titles are read as FOH_SUPERVISOR (FOH Team Leader);
  2. generic coordination titles (Team Leader, Team Lead, Shift Leader,
     Shift Lead, Floor Leader) only with a dining-room context — in the
     title, or a duty coordinating servers, hosts, runners or table service;
  3. kitchen and warehouse team leaders, and contexts that are missing or
     conflicting, are NOT read as FOH: the title is kept and clarified;
  4. Chef de rang is a Server, not kitchen; Head Waiter, Maître, Captain and
     Lead Server are unchanged;
  5. the same résumé analysed for Server and for FOH Team Leader;
  6. with FOH Team Leader as target, no transition "into Server";
  7. a missing or unsupported target role asks for clarification and is
     never replaced by Server.

No database, no AI provider (isolated). `--dump` prints the comparison of
section 5.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from rfone_data_store.selection.analysis import (
    TARGET_ROLE_MISSING, TARGET_ROLE_UNSUPPORTED, analyze_candidate,
)
from rfone_data_store.selection.core import flags as flags_mod
from rfone_data_store.selection.core.indicators import TARGET_ROLE_TO_CLARIFY
from rfone_data_store.selection.core.profile import CandidateCVProfile, WorkHistoryRecord
from rfone_data_store.selection.industry import restaurant
from rfone_data_store.selection.normalization import normalize_profile
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client

import test_selection_cv_structure as cv  # synthetic résumés + parse() helper


def read(title: str, duties: str | None = None, employer: str = "Synthetic Employer") -> WorkHistoryRecord:
    profile = normalize_profile(CandidateCVProfile(full_name="Synthetic", work_history=[
        WorkHistoryRecord(original_job_title=title, employer=employer, responsibilities=duties,
                          start_date_text="Jan 2021", end_date_text="Present", structure_confidence="HIGH"),
    ]))
    return profile.work_history[0]


def profile_with(*records: WorkHistoryRecord) -> CandidateCVProfile:
    return normalize_profile(CandidateCVProfile(full_name="Synthetic", email="s@example.test",
                                                work_history=list(records)))


def indicator(view, name: str) -> str:
    return next(i.raw_value for i in view.indicators if i.name == name)


def comparison(text: str) -> dict:
    profile = cv.parse(text)
    out = {}
    for target in ("SERVER", "FOH_SUPERVISOR"):
        view = analyze_candidate(profile, target_role=target)
        out[target] = {
            "label": view.target_role_label,
            "direct": indicator(view, "Direct Role Experience"),
            "propedeutic": indicator(view, "Relevant / Propedeutic Experience"),
            "supervisory": indicator(view, "Supervisory Responsibility"),
            "classes": [(w.original_job_title, w.normalized_role,
                         __import__("rfone_data_store.selection.core.role_model", fromlist=["x"])
                         .classify_role(w.normalized_role, view.role_config))
                        for w in profile.work_history],
            "transition_flags": [f.explanation for f in view.flags
                                 if f.type in (flags_mod.ROLE_TRANSITION, "BOH_TO_FOH")],
        }
    return out


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    with isolated_ai_client():
        # --- 1. explicit FOH titles ---------------------------------------
        explicit = ["FOH Team Leader", "Front of House Team Leader", "FOH Supervisor", "Floor Supervisor",
                    "Capo sala", "Caposala", "Responsabile di sala"]
        got = {t: read(t).normalized_role for t in explicit}
        check("1. explicit FOH titles are FOH_SUPERVISOR (FOH Team Leader)",
              all(v == "FOH_SUPERVISOR" for v in got.values()), f"{got}")
        check("1. the recognized role is labelled 'FOH Supervisor / Team Leader'",
              read("Capo sala").normalized_title == "FOH Supervisor / Team Leader")

        # --- 2. generic titles WITH dining-room context ---------------------
        with_context = {
            "Team Leader / duty with servers": read("Team Leader", "Coordinated a team of 6 servers per shift"),
            "Team Lead / table service": read("Team Lead", "Managed table service on weekends"),
            "Shift Leader / hosts and runners": read("Shift Leader", "Assigned sections to hosts and runners"),
            "Shift Lead, Front of House (title)": read("Shift Lead, Front of House"),
            "Floor Leader / servizio al tavolo": read("Floor Leader", "Coordinavo il servizio al tavolo; supervised servers"),
            "Team Leader di sala (title)": read("Team Leader di sala"),
        }
        check("2. generic titles with a dining-room context are FOH_SUPERVISOR",
              all(r.normalized_role == "FOH_SUPERVISOR" for r in with_context.values()),
              f"{[(k, r.normalized_role) for k, r in with_context.items()]}")
        check("2. read from the duties -> MEDIUM title confidence; from the title -> HIGH",
              with_context["Team Leader / duty with servers"].title_normalization_confidence == "MEDIUM"
              and with_context["Shift Lead, Front of House (title)"].title_normalization_confidence == "HIGH")

        # --- 3. NOT FOH: kitchen, warehouse, no or conflicting context -----
        not_foh = {
            "Kitchen Team Leader": read("Kitchen Team Leader", "Coordinated line cooks during service"),
            "Team Leader in a restaurant, kitchen duties": read(
                "Team Leader", "Coordinated cooks and prep during dinner service", employer="Trattoria Esempio"),
            "Team Leader in a restaurant, no duties": read("Team Leader", None, employer="Trattoria Esempio"),
            "Warehouse Team Leader": read("Warehouse Team Leader", "Trained new hires on safety"),
            "Team Leader, warehouse duties": read(
                "Team Leader", "Coordinated pickers and forklift drivers", employer="Synthetic Logistics"),
            "Shift Leader, served guests only": read("Shift Leader", "Served guests and handled payments"),
            "Team Leader, both servers and cooks": read(
                "Team Leader", "Coordinated servers at the pass. Supervised line cooks"),
        }
        check("3. kitchen / warehouse / missing or conflicting context: never FOH_SUPERVISOR",
              all(r.normalized_role is None for r in not_foh.values()),
              f"{[(k, r.normalized_role) for k, r in not_foh.items()]}")
        check("3. the original title is kept as written, with no normalized title or family invented",
              not_foh["Kitchen Team Leader"].original_job_title == "Kitchen Team Leader"
              and not_foh["Team Leader in a restaurant, no duties"].original_job_title == "Team Leader"
              and all(r.normalized_title is None and r.role_family is None for r in not_foh.values()))
        view = analyze_candidate(profile_with(not_foh["Team Leader in a restaurant, no duties"]),
                                 target_role="FOH_SUPERVISOR")
        clar = [f for f in view.flags if f.type == flags_mod.TITLE_INCONSISTENCY]
        check("3. a generic title without context asks which team and area (to be clarified)",
              len(clar) == 1 and "To be clarified" in clar[0].explanation
              and "which team did you coordinate" in (clar[0].suggested_question or ""), f"{clar}")
        view = analyze_candidate(profile_with(not_foh["Kitchen Team Leader"]), target_role="FOH_SUPERVISOR")
        clar = [f for f in view.flags if f.type == flags_mod.TITLE_INCONSISTENCY]
        check("3. a kitchen team leader says why it is not read as FOH",
              len(clar) == 1 and "refers to the kitchen" in clar[0].explanation)
        check("3. none of these counts as supervisory months",
              all(indicator(analyze_candidate(profile_with(r), target_role="FOH_SUPERVISOR"),
                            "Supervisory Responsibility") == "0 months" for r in not_foh.values()))

        # --- 3b. "Supervisor" follows the same context rule ----------------
        sup = {
            "FOH Supervisor": read("FOH Supervisor"),
            "Floor Supervisor": read("Floor Supervisor"),
            "Supervisor + dining-room duties": read("Supervisor", "Supervised servers and hosts on the floor"),
            "Kitchen Supervisor": read("Kitchen Supervisor", "Supervised line cooks and prep"),
            "Supervisor, no context": read("Supervisor"),
            "Restaurant Supervisor, no context": read("Restaurant Supervisor", employer="Trattoria Esempio"),
            "Shift Supervisor, no context": read("Shift Supervisor"),
            "Warehouse Supervisor": read("Warehouse Supervisor", "Supervised pickers and forklift drivers"),
            "Supervisor, mixed duties": read("Supervisor", "Supervised servers. Supervised line cooks"),
        }
        foh = {k for k, r in sup.items() if r.normalized_role == "FOH_SUPERVISOR"}
        check("3b. only explicit FOH titles or dining-room duties make a Supervisor FOH",
              foh == {"FOH Supervisor", "Floor Supervisor", "Supervisor + dining-room duties"},
              f"{[(k, r.normalized_role) for k, r in sup.items()]}")
        check("3b. kitchen, warehouse, mixed or missing context: no role assigned (no kitchen role fits either)",
              all(sup[k].normalized_role is None for k in sup if k not in foh))
        kitchen_view = analyze_candidate(profile_with(sup["Kitchen Supervisor"]), target_role="FOH_SUPERVISOR")
        check("3b. Kitchen Supervisor adds no supervisory or FOH Team Leader months, and is to be clarified",
              indicator(kitchen_view, "Supervisory Responsibility") == "0 months"
              and indicator(kitchen_view, "Direct Role Experience") == "0 months"
              and any(f.type == flags_mod.TITLE_INCONSISTENCY and "refers to the kitchen" in f.explanation
                      for f in kitchen_view.flags))
        check("3b. Supervisor without context and Warehouse Supervisor are to be clarified",
              all(any(f.type == flags_mod.TITLE_INCONSISTENCY and "To be clarified" in f.explanation
                      for f in analyze_candidate(profile_with(sup[k]), target_role="FOH_SUPERVISOR").flags)
                  for k in ("Supervisor, no context", "Warehouse Supervisor")))

        # --- 4. Chef de rang + unchanged titles ----------------------------
        cdr = read("Chef de rang")
        check("4. Chef de rang is a Server (FOH Service), not kitchen and not supervisory",
              cdr.normalized_role == "SERVER" and cdr.role_family == "FOH Service"
              and restaurant.role_category(cdr.normalized_role) == "FOH"
              and cdr.normalized_role not in restaurant.SUPERVISORY_ROLES)
        unchanged = {t: read(t).normalized_role for t in ("Head Waiter", "Maître d'", "Captain", "Lead Server")}
        check("4. Head Waiter, Maître, Captain, Lead Server unchanged (WAITER, none, none, SERVER)",
              unchanged == {"Head Waiter": "WAITER", "Maître d'": None, "Captain": None, "Lead Server": "SERVER"},
              f"{unchanged}")

        # --- 5. same résumé, two target roles -------------------------------
        cmp = comparison(cv.SAME_SEPARATE_LINES)
        s, t = cmp["SERVER"], cmp["FOH_SUPERVISOR"]
        check("5. the Team Leader line (duty: coordinating servers) is FOH_SUPERVISOR in both analyses",
              s["classes"][0][1] == "FOH_SUPERVISOR" == t["classes"][0][1])
        check("5. for Server: direct = the Server job, the two supervisory jobs are OTHER",
              [c[2] for c in s["classes"]] == ["OTHER", "OTHER", "TARGET"] and s["direct"] == "30 months",
              f"{s}")
        check("5. for FOH Team Leader: direct = Team Leader + Floor Supervisor, Server is propedeutic",
              [c[2] for c in t["classes"]] == ["TARGET", "TARGET", "PROPEDEUTIC"]
              and t["propedeutic"] == "30 months" and t["direct"] != s["direct"], f"{t}")
        check("5. supervisory months do not depend on the target role",
              s["supervisory"] == t["supervisory"])

        # --- 6. FOH Team Leader target: never "into Server" -----------------
        def started(year: int) -> dict:
            return dict(start_date_text=f"Jan {year}", end_date_text="Present", structure_confidence="HIGH")
        kitchen = profile_with(WorkHistoryRecord(original_job_title="Line Cook", employer="Osteria Finta",
                                                 evidence_snippet="Line Cook, Osteria Finta Jan 2021 - Present",
                                                 **started(2021)))
        manager = profile_with(WorkHistoryRecord(original_job_title="Restaurant Manager", employer="Bistro Prova",
                                                 evidence_snippet="Restaurant Manager, Bistro Prova Jan 2020 - Present",
                                                 **started(2020)))
        for name, prof in (("kitchen", kitchen), ("management", manager)):
            view = analyze_candidate(prof, target_role="FOH_SUPERVISOR")
            tf = [f for f in view.flags if f.type in (flags_mod.ROLE_TRANSITION, "BOH_TO_FOH")]
            text = " ".join(f"{f.explanation} {f.suggested_question}" for f in tf)
            check(f"6. from {name} to FOH Team Leader: one neutral question naming FOH Team Leader, never Server",
                  len(tf) == 1 and "FOH Team Leader" in text and "Server" not in text
                  and "Motivation: Unknown" in tf[0].explanation and tf[0].attention_level == flags_mod.REVIEW,
                  f"{[(f.type, f.explanation, f.suggested_question) for f in tf]}")
            check(f"6. the {name} question is backed by the résumé text", "Résumé text:" in tf[0].evidence if tf else False)
        view = analyze_candidate(cv.parse(cv.REVIEW_LAYOUT_A), target_role="FOH_SUPERVISOR")
        check("6. the status-review résumé for FOH Team Leader: no flag or question mentions Server",
              not any("Server" in f"{f.explanation} {f.suggested_question or ''}" for f in view.flags))

        # --- 7. missing / unsupported target role ---------------------------
        profile = cv.parse(cv.SAME_SEPARATE_LINES)
        for target, issue in ((None, TARGET_ROLE_MISSING), ("BARTENDER", TARGET_ROLE_UNSUPPORTED)):
            view = analyze_candidate(profile, target_role=target)
            check(f"7. target {target!r}: to be clarified, no role assumed",
                  view.role_config is None and view.target_role_issue == issue
                  and indicator(view, "Direct Role Experience") == TARGET_ROLE_TO_CLARIFY
                  and indicator(view, "Relevant / Propedeutic Experience") == TARGET_ROLE_TO_CLARIFY
                  and not view.transitions_to_investigate
                  and not any("Server" in f"{f.explanation} {f.suggested_question or ''}" for f in view.flags))
        view = analyze_candidate(profile, target_role=None)
        check("7. role-independent analysis is still shown (stability, supervisory months)",
              indicator(view, "Supervisory Responsibility") != "0 months"
              and next(i for i in view.indicators if i.name == "Stability").state == "Strong")
        check("7. the résumé reader no longer sets a target role on its own",
              cv.parse(cv.SAME_SEPARATE_LINES).target_role is None)

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed.")
    print("ALL CHECKS PASSED" if failed == 0 else "SOME CHECKS FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--dump" in sys.argv:
        with isolated_ai_client():
            for target, data in comparison(cv.SAME_SEPARATE_LINES).items():
                print(target, data)
        sys.exit(0)
    sys.exit(main())
