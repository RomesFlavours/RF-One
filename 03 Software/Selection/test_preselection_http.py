#!/usr/bin/env python
"""SELECTION_PRESELECTION_COMPARE_001 — preselection filters and
side-by-side comparison of applications.

ALL RÉSUMÉS BELOW ARE SYNTHETIC (invented people, employers and dates).

Through the real Flask routes on a throwaway SQLite database:
  1. no filter preselected; filters combine; the result count is shown;
     "Clear all filters" resets;
  2. zero vs unknown vs not documented: a real 0 matches "max 0", unknown
     months never match a numeric filter unless "Include data to be
     clarified" is ticked; no coordination evidence = "not documented";
  3. comparing 2 to 4 applications of the same target role;
  4. comparison refused for different or missing target roles, and for
     fewer than 2 or more than 4;
  5. each column links to its application, candidate page and original
     CV; evidence is quoted; the same person in two columns is marked;
  6. notes, stage and outcome of one application leave the others alone.

The AI client is isolated; every file written into uploads/ is removed.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from io import BytesIO

_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_preselection_test_")
os.close(_FD)
os.remove(_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB_PATH.replace(os.sep, '/')}"

import app as selection_app  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.selection import application_service as app_svc  # noqa: E402
from rfone_data_store.selection import outcome_service as outcome_svc  # noqa: E402
from rfone_data_store.selection import stage_service as stage_svc  # noqa: E402
from rfone_data_store.selection.industry.restaurant_templates import seed_default_selection_outcomes  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

ALEX = """Alex Synthetic
alex.synthetic@example.test

EXPERIENCE
Team Leader
Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift
- Trained new hires on service standards

Server
Cafe Campione, Toronto, ON
Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
"""
ALEX_V2 = ALEX + "\nLANGUAGES\nEnglish (fluent)\n"  # same person, another résumé version
BEA = """Bea Synthetic
bea.synthetic@example.test

EXPERIENCE
Server, Cafe Campione
Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
"""
CAL = """Cal Synthetic
cal.synthetic@example.test

EXPERIENCE
Floor Supervisor, Bistro Prova
- Opened and closed the dining room
"""
DAN = """Dan Synthetic
dan.synthetic@example.test

EXPERIENCE
Osteria Finta
Team Leader
Mar 2022 - Present
- Coordinated the floor team
"""
EVE = """Eve Synthetic
eve.synthetic@example.test

EXPERIENCE
Server, Bistro Prova
Jan 2018 - Present
"""
FAY = """Fay Synthetic
fay.synthetic@example.test

EXPERIENCE
Host, Osteria Finta
Jan 2020 - Present
"""


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    existing_uploads = set(os.listdir(selection_app.UPLOAD_DIR))
    try:
        with isolated_ai_client():
            client = selection_app.app.test_client()

            def upload(text: str, name: str, role: str) -> dict:
                return client.post("/api/upload", data={
                    "target_role": role, "resume_file": (BytesIO(text.encode()), name),
                }, content_type="multipart/form-data").get_json()

            ids = {
                "alex": upload(ALEX, "alex.txt", "FOH_SUPERVISOR")["application_id"],
                "alex2": upload(ALEX_V2, "alex_v2.txt", "FOH_SUPERVISOR")["application_id"],
                "bea": upload(BEA, "bea.txt", "FOH_SUPERVISOR")["application_id"],
                "cal": upload(CAL, "cal.txt", "FOH_SUPERVISOR")["application_id"],
                "dan": upload(DAN, "dan.txt", "FOH_SUPERVISOR")["application_id"],
                "eve": upload(EVE, "eve.txt", "SERVER")["application_id"],
                "fay": upload(FAY, "fay.txt", "SERVER")["application_id"],
            }
            with selection_app.SessionFactory() as session:
                app_svc.set_target_role(session, ids["fay"], None)  # an application with no target role
                session.commit()
            name_of = {v: k for k, v in ids.items()}

            def listed(query: str = "") -> tuple[set[str], str]:
                html = client.get("/applications" + query).get_data(as_text=True)
                found = {name_of[int(i)] for i in re.findall(r'name="ids" value="(\d+)"', html) if int(i) in name_of}
                return found, html

            # --- 1. no preselected filter, combination, count, reset ---------
            everything, html = listed()
            filters_part = html.split("Review Queue")[0]
            preselected = re.findall(r'<option value="([^"]+)" selected', filters_part)
            check("1. no filter preselected (only the existing default sort order): every application is "
                  "listed, with the result count",
                  everything == set(ids) and 'data-result-count>7<' in html
                  and preselected == ["applied_at"] and 'checked' not in filters_part, f"{preselected}")
            combined, html = listed("?role=FOH_SUPERVISOR&coordination=none")
            check("1. filters combine: FOH Team Leader AND coordination not documented",
                  combined == {"bea", "cal"} and 'data-result-count>2<' in html, f"{combined}")
            training, _ = listed("?coordination=TRAINING")
            check("1. coordination filter by category (training)", training == {"alex", "alex2"}, f"{training}")
            uncertain, _ = listed("?issues=uncertain")
            check("1. filter on uncertain readings", uncertain == {"dan"}, f"{uncertain}")
            check("1. 'Clear all filters' links back to the unfiltered list",
                  'href="/applications" class="btn secondary">Clear all filters' in html)

            # --- 2. zero vs unknown vs not documented -------------------------
            min1, _ = listed("?role=FOH_SUPERVISOR&direct_min=1")
            check("2. direct >= 1 month: only the known values (unknown and real zero excluded)",
                  min1 == {"alex", "alex2"}, f"{min1}")
            min1u, _ = listed("?role=FOH_SUPERVISOR&direct_min=1&unclear=1")
            check("2. ...plus 'Include data to be clarified': the unknown ones come in, the real zero does not",
                  min1u == {"alex", "alex2", "cal", "dan"}, f"{min1u}")
            zero, html = listed("?role=FOH_SUPERVISOR&direct_max=0")
            check("2. direct <= 0: the documented zero only, never the unknown ones",
                  zero == {"bea"}, f"{zero}")
            _, html = listed("?role=FOH_SUPERVISOR")
            row = {name_of[int(i)]: chunk for i, chunk in re.findall(r'name="ids" value="(\d+)"(.*?)</tr>', html, re.S)}
            check("2. the list shows 0 as '0 mo', unknown as 'to be clarified', no coordination as 'not documented'",
                  "<td>0 mo</td>" in row["bea"] and "to be clarified" in row["cal"]
                  and "not documented" in row["bea"] and "2 declared" in row["alex"])
            stable, _ = listed("?role=FOH_SUPERVISOR&stability=Strong")
            stable_u, _ = listed("?role=FOH_SUPERVISOR&stability=Strong&unclear=1")
            check("2. stability: 'to be clarified' only with the explicit choice",
                  "cal" not in stable and "cal" in stable_u, f"{stable} / {stable_u}")

            # --- 3. compare 2 to 4 of the same role ---------------------------
            def compare(*names: str):
                return client.get("/applications/compare?" + "&".join(f"ids={ids[n]}" for n in names))

            two = compare("alex", "bea")
            four = compare("alex", "alex2", "bea", "cal")
            check("3. 2 and 4 applications of the same target role open side by side",
                  two.status_code == 200 and four.status_code == 200
                  and four.get_data(as_text=True).count("Application #") == 4)
            page = four.get_data(as_text=True)
            check("3. the table shows experience, stability, history, coordination, missing info, questions, stage "
                  "and outcome",
                  all(t in page for t in ("Direct experience", "Propedeutic experience", "Stability", "Work history",
                                          "Declared coordination responsibilities", "Missing or uncertain information",
                                          "Questions to explore", "Stage &middot; outcome")))
            check("3. unknown stays 'to be clarified' and absence stays 'not documented' in the comparison",
                  "to be clarified" in page and "Not documented in the CV." in page)
            check("3. no score, ranking or recommendation is introduced",
                  not re.search(r"\b(rank(ed|ing)? #|score:|recommended|best candidate)\b", page, re.I))

            # --- 4. refused comparisons --------------------------------------
            mixed = compare("alex", "eve")
            missing = compare("eve", "fay")
            one = compare("alex")
            five = client.get("/applications/compare?" + "&".join(
                f"ids={ids[n]}" for n in ("alex", "alex2", "bea", "cal", "dan")))
            check("4. different target roles: refused, asking for applications of the same role",
                  mixed.status_code == 400 and "same target role" in mixed.get_data(as_text=True))
            check("4. a missing target role: refused, asking to set it first",
                  missing.status_code == 400 and "without a target role" in missing.get_data(as_text=True))
            check("4. fewer than 2 or more than 4: refused", one.status_code == 400 and five.status_code == 400
                  and "from 2 to 4" in one.get_data(as_text=True))

            # --- 5. evidence, links, original CV, same person ------------------
            check("5. every column links to its application, its candidate page and the original CV",
                  all(f'href="/applications/{ids[n]}"' in page for n in ("alex", "alex2", "bea", "cal"))
                  and page.count("Open Original CV") == 4 and page.count("Candidate page") == 4)
            check("5. declared evidence is quoted as written", "&ldquo;Coordinated a team of 6 servers per shift&rdquo;" in page)
            cv_link = re.search(r'href="(/candidate/\d+/original-cv)"', page).group(1)
            check("5. the original CV opens", client.get(cv_link).status_code == 200)
            check("5. two columns for the same person are marked", "Same person as column 1" in page)

            # --- 6. independence of notes, stage, outcome ----------------------
            with selection_app.SessionFactory() as session:
                restaurant = selection_app._bootstrap_restaurant(session)
                outcomes = seed_default_selection_outcomes(session, restaurant_id=restaurant.id)
                session.commit()
                definition_id = next(iter(outcomes.values()))
                app_svc.add_note(session, ids["alex"], "Synthetic note for the first application")
                stage_svc.set_stage(session, ids["alex"], "PHONE_INTERVIEW")
                outcome_svc.apply_outcome(session, ids["alex"], definition_id,
                                          reason="Synthetic reason", note_text="Synthetic outcome note")
                session.commit()
            with selection_app.SessionFactory() as session:
                other = ids["alex2"]
                untouched = (
                    not any("Synthetic" in (n.note_text or "") for n in app_svc.list_notes(session, other))
                    and stage_svc.get_current_stage(session, other) != "PHONE_INTERVIEW"
                    and outcome_svc.get_current_outcome_decision(session, other) is None
                    and outcome_svc.get_current_outcome_decision(session, ids["alex"]) is not None
                )
            check("6. a note, stage and outcome on one application leave the same person's other one unchanged",
                  untouched)
            staged, _ = listed("?stage=PHONE_INTERVIEW")
            check("6. the stage filter reflects that one application only", staged == {"alex"}, f"{staged}")
    finally:
        for name in set(os.listdir(selection_app.UPLOAD_DIR)) - existing_uploads:
            try:
                os.remove(os.path.join(selection_app.UPLOAD_DIR, name))
            except OSError:
                pass
        selection_app._engine.dispose()
        for suffix in ("", "-wal", "-shm", "-journal"):
            if os.path.exists(_DB_PATH + suffix):
                try:
                    os.remove(_DB_PATH + suffix)
                except OSError:
                    pass

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed.")
    print("ALL CHECKS PASSED" if failed == 0 else "SOME CHECKS FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
