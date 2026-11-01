#!/usr/bin/env python
"""CV Selection SP engine (`workspace/sp`) — checks on synthetic data with a FAKE AI (no network, no database).

    python test_sp_engine.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "RF-One Data Store")]

from workspace.sp import analysis as sp_analysis  # noqa: E402
from workspace.sp import profiles as spp  # noqa: E402
from workspace.sp import ranking as sp_ranking  # noqa: E402

TODAY = date(2026, 11, 1)
failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


KIM = """Kim Baxter
kim.b@example.test

EXPERIENCE
Chef de Cuisine, Fusion Lab Bistro | 2022 - 2024
- Created a seasonal menu every quarter and developed 40+ original dishes
- Led a team of 4 cooks
Cook, Burger Barn | 2021
Dishwasher, Golden Wok | 2019 - 2020
"""
DEREK = """Derek Holt
derek.holt@example.test

WORK HISTORY
Server, Sunny Pancake House, Orlando, FL | Aug 2021 - Sep 2023
Server, Lakeview Diner, Orlando, FL | Nov 2023 - Feb 2024
Server, Bella Notte Trattoria, Winter Park, FL | Mar 2024 - Jul 2024
Barista, Coffee Corner, Orlando, FL | Aug 2024 - Dec 2024
SKILLS
Fine dining, wine knowledge, upselling, team player
"""
MARIA = """Maria Rossetti
maria.r@example.test

EXPERIENCE
Lead Server, Osteria del Lago, Orlando, FL | Apr 2022 - Present
- Recommend wine pairings from a 90-label list; top seller of the monthly wine feature
- Train new servers on steps of service and close the floor two nights a week
Server, Harbor Grill Steakhouse, Tavares, FL | Jun 2019 - Mar 2022
- Full table service, menu guidance, cash-out at end of shift
"""


def fake_ai(prompt: str) -> dict:
    if "Kim Baxter" in prompt:
        return {"full_name": "Kim Baxter", "jobs": [
            {"employer": "Fusion Lab Bistro", "title": "Chef de Cuisine", "date_text": "2022 - 2024", "relevant": False},
            {"employer": "Burger Barn", "title": "Cook", "date_text": "2021", "relevant": True},
            {"employer": "Golden Wok", "title": "Dishwasher", "date_text": None, "relevant": False}],
            "requirements": {"kitchen_stations": {"level": 1, "quotes": ["Cook, Burger Barn"]}},
            "risk_flags": [{"flag": "Currently a chef", "fact": "Chef for 2 years", "quote": "Chef de Cuisine"},
                           {"flag": "Role-expectation alignment", "fact": "Menu creation background",
                            "quote": "Created a seasonal menu every quarter"},
                           {"flag": "Lives far away", "fact": "Long commute", "quote": "Kim Baxter"},
                           {"flag": "Unverifiable", "fact": "x", "quote": "words not in the CV"}],
            "unknowns": ["Where the person lives and the commute", "Stations worked"]}
    if "Derek Holt" in prompt:
        return {"full_name": "Derek Holt", "jobs": [
            {"employer": "Coffee Corner", "title": "Barista", "date_text": "Aug 2024 - Dec 2024", "relevant": False},
            {"employer": "Bella Notte Trattoria", "title": "Server", "date_text": "Mar 2024 - Jul 2024", "relevant": True},
            {"employer": "Lakeview Diner", "title": "Server", "date_text": "Nov 2023 - Feb 2024", "relevant": True},
            {"employer": "Sunny Pancake House", "title": "Server", "date_text": "Jan 2021 - Sep 2023", "relevant": True}],
            "requirements": {"table_service": {"level": 2, "quotes": ["Server, Lakeview Diner"]},
                             "guest_selling": {"level": 3, "quotes": ["wine knowledge, upselling"]}},
            "competences": [{"name": "Upselling", "level": "executed", "quote": "upselling"}],
            "risk_flags": [{"flag": "Gap after IHOP", "fact": "3-month gap", "quote": "Server, Lakeview Diner"}]}
    return {"full_name": "Maria Rossetti", "jobs": [
        {"employer": "Osteria del Lago", "title": "Lead Server", "date_text": "Apr 2022 - Present", "relevant": True},
        {"employer": "Harbor Grill Steakhouse", "title": "Server", "date_text": "Jun 2019 - Mar 2022", "relevant": True}],
        "requirements": {"table_service": {"level": 4, "quotes": ["Full table service, menu guidance"]},
                         "guest_selling": {"level": 4, "quotes": ["Recommend wine pairings from a 90-label list"]},
                         "trusted": {"level": 3, "quotes": ["close the floor two nights a week"]},
                         "learning": {"level": 2, "quotes": ["a sentence that is not in the CV"]},
                         "progression": {"level": 2, "quotes": ["Lead Server"], "assessable": False}},
        "risk_flags": [{"flag": "No documented opening duties", "fact": "x", "quote": "Lead Server"},
                       {"flag": "Mostly Italian full-service", "fact": "Worked in a family Italian restaurant",
                        "quote": "Osteria del Lago"}],
        "competences": [{"name": "Wine service", "level": "owned", "quote": "Recommend wine pairings"}],
        "strengths": [{"text": "Trains new servers", "quote": "Train new servers"}],
        "stated_availability": {"text": "Evenings", "quote": "not in the CV"}}


try:
    # --- Verified dates and computed durations (the Kim case from the Bedrock comparison) ---------------------
    reqs_lc = spp.default_requirements("LINE_COOK")
    kim = sp_analysis.analyze_cv(role_code="LINE_COOK", requirements=reqs_lc, cv_text=KIM, today=TODAY, generate=fake_ai)
    fusion, burger, wok = kim["jobs"]
    check("dates: '2022 - 2024' is a past job of 14-36 months (Dec 2022-Jan 2024 to Jan 2022-Dec 2024), never 'current'",
          fusion["date_status"] == "OK" and not fusion["is_current"] and (fusion["months_min"], fusion["months_max"]) == (14, 36),
          fusion)
    check("dates: a single year ('2021') is some months within that year, not missing",
          burger["date_status"] == "OK" and (burger["months_min"], burger["months_max"]) == (1, 12), burger)
    check("dates: when the AI gives no dates (as Bedrock did for Kim), code finds '2019 - 2020' on the job's line",
          wok["date_status"] == "OK" and wok["date_text"] == "2019 - 2020" and "by code" in wok.get("date_source", ""), wok)
    check("flags: a flag without a CV quote becomes a point to verify", "Unverifiable" in kim["unknowns"], kim["unknowns"])
    check("stability: year-only dates are assessed, not unknown, and raise no short-job flag",
          kim["stability"]["known"] and not kim["stability"]["flags"], kim["stability"])
    flags = [f["flag"] for f in kim["flags"]]
    check("flags: a flag stating a duration written by the AI is dropped", "Currently a chef" not in flags, flags)
    check("flags: a flag about where the person lives is dropped", "Lives far away" not in flags, flags)
    check("flags: a flag without a quote in the CV is dropped", "Unverifiable" not in flags, flags)
    check("flags: a role flag supported by a CV quote is kept", "Role-expectation alignment" in flags, flags)
    check("missing information: residence/commute lines are dropped, others kept",
          not any("lives" in u for u in kim["unknowns"]) and "Stations worked" in kim["unknowns"], kim["unknowns"])
    check("verification log lists every correction", len(kim["verification_log"]) >= 4, kim["verification_log"])

    reqs_sv = spp.default_requirements("SERVER")
    derek = sp_analysis.analyze_cv(role_code="SERVER", requirements=reqs_sv, cv_text=DEREK, today=TODAY, generate=fake_ai)
    check("dates: dates not found in the CV are not used (AI wrote Jan 2021, CV says Aug 2021)",
          derek["jobs"][3]["date_status"] == "NOT_IN_CV", derek["jobs"][3])
    check("stability: three consecutive jobs under 6 months computed from the dates",
          any(f["code"] == "THREE_SHORT" for f in derek["stability"]["flags"]) and derek["stability"]["level"] == 1)
    check("skills list: evidence only in the skills section is capped at 'claimed'",
          derek["requirements"]["guest_selling"]["level"] == 1 and derek["competences"][0]["level"] == "claimed",
          (derek["requirements"]["guest_selling"], derek["competences"]))
    check("flags: the AI's '3-month gap' is dropped (gaps are computed)", not any("Gap after" in f["flag"] for f in derek["flags"]))

    maria = sp_analysis.analyze_cv(role_code="SERVER", requirements=reqs_sv, cv_text=MARIA, today=TODAY, generate=fake_ai)
    check("quotes: a level backed by a quote not in the CV becomes 'not documented'",
          maria["requirements"]["learning"]["level"] == 0)
    check("dates: 'Present' only when the CV says it; duration computed to today",
          maria["jobs"][0]["is_current"] and maria["jobs"][0]["months_min"] == 56, maria["jobs"][0])
    check("stated availability without a CV quote is not used", maria["stated_availability"] is None)
    check("stability: 3+ years at one relevant employer is the top level", maria["stability"]["level"] == 4)
    check("profile requirements are always assessable from a CV (the AI cannot exclude them)",
          maria["requirements"]["progression"]["assessable"] is True)
    check("flags: 'No documented …' is missing information, moved to To verify",
          "No documented opening duties" in maria["unknowns"] and not any("No documented" in f["flag"] for f in maria["flags"]))
    check("flags: 'family Italian restaurant' is not treated as a personal characteristic",
          any(f["flag"] == "Mostly Italian full-service" for f in maria["flags"]), maria["verification_log"])

    v = sp_analysis.Verifier(DEREK)
    diner_only = [{"employer": "Lakeview Diner", "environment": "Diner, breakfast chain"},
                  {"employer": "Coffee Corner", "environment": "Unrelated work"}]
    check("role flag: Server background only in diner models is flagged by code (provisional, not a ban)",
          (sp_analysis._environment_flag("SERVER", diner_only, v) or {}).get("source") == "PROFILE")
    check("role flag: later full-service experience removes it; never raised for Line Cook",
          sp_analysis._environment_flag("SERVER", diner_only + [{"employer": "Bella Notte Trattoria",
                                                                "environment": "Italian full-service"}], v) is None
          and sp_analysis._environment_flag("LINE_COOK", diner_only, v) is None)

    # --- Ranking ------------------------------------------------------------------------------------------------
    cands = [{"id": "d", "filename": "derek.txt", "analysis": derek, "uploaded_at": "1"},
             {"id": "m", "filename": "maria.txt", "analysis": maria, "uploaded_at": "2"}]
    order = sp_ranking.rank([dict(c) for c in cands], reqs_sv, None)
    check("ranking: Maria (every must-have shown) before Derek (short-job pattern computed from dates)",
          [c["id"] for c in order] == ["m", "d"] and order[0]["assessment"]["group"] == "A"
          and order[1]["assessment"]["group"] == "D", [(c["id"], c["assessment"]["group"]) for c in order])
    check("ranking: the reason for the order is explicit", "group A" in (order[0]["why_ahead"] or ""), order[0]["why_ahead"])
    manual = sp_ranking.rank([dict(c) for c in cands], reqs_sv, ["d", "m"])
    check("ranking: the manager's order wins and is labelled",
          [c["id"] for c in manual] == ["d", "m"] and manual[0]["rank_moved"] and "by the manager" in manual[0]["why_ahead"])
    unknown_stab = dict(maria, requirements=dict(maria["requirements"], stability={"level": None, "assessable": False,
                                                                                   "computed": True, "quotes": []}))
    a = sp_ranking.assess(unknown_stab, reqs_sv)
    check("ranking: stability with no usable dates is 'to verify', not zero",
          next(i for i in a["items"] if i["id"] == "stability")["status"] == sp_ranking.NOT_ASSESSABLE and a["group"] == "B")
finally:
    pass

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED")
sys.exit(1 if failures else 0)
