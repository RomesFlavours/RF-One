#!/usr/bin/env python
"""SELECTION_FOH_TEAM_LEADER_001 — the target role is chosen at upload,
saved on the application and used by the candidate page.

ALL RÉSUMÉS BELOW ARE SYNTHETIC (invented people, employers and dates).

Covered, through the real Flask routes on a throwaway SQLite database:
  1. no target role (or an unsupported one) -> nothing is imported, a clear
     message asks for the choice (single JSON upload and batch form);
  2. single upload for FOH Team Leader -> saved on the application and read
     back from the database;
  3. batch upload -> the one choice applies to every application of the
     batch;
  4. the same person applying for another role -> a second application with
     its own target role;
  5. the candidate page and list use the application's target role;
  6. an application with no or an unsupported target role -> the page asks
     for clarification and never falls back to Server.

The AI client is isolated; every file written into uploads/ is removed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from io import BytesIO

_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_target_role_test_")
os.close(_FD)
os.remove(_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB_PATH.replace(os.sep, '/')}"

import app as selection_app  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.selection import application_service as app_svc  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

TL_RESUME = """Alex Synthetic
alex.synthetic@example.test | +1 555 0100 | Hamilton, ON

EXPERIENCE
Team Leader
Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift

Server
Cafe Campione, Toronto, ON
Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
"""
# The same person, a later version of the résumé (different content, so it
# is a new résumé snapshot rather than a duplicate).
TL_RESUME_V2 = TL_RESUME + "\nLANGUAGES\nEnglish (fluent)\n"
BATCH = [
    ("Robin Synthetic\nrobin.synthetic@example.test\n\nEXPERIENCE\nServer, Bistro Prova\nJan 2020 - Present\n", "robin.txt"),
    ("Casey Synthetic\ncasey.synthetic@example.test\n\nEXPERIENCE\nHost, Osteria Finta\nJan 2021 - Present\n", "casey.txt"),
]


def upload_json(client, text: str, name: str, target_role: str | None):
    data = {"resume_file": (BytesIO(text.encode("utf-8")), name)}
    if target_role is not None:
        data["target_role"] = target_role
    return client.post("/api/upload", data=data, content_type="multipart/form-data")


def stored_target(application_id: int) -> str | None:
    with selection_app.SessionFactory() as session:  # a fresh session: what is really saved
        return session.get(m.Application, application_id).target_role


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    existing_uploads = set(os.listdir(selection_app.UPLOAD_DIR))
    try:
        with isolated_ai_client():
            client = selection_app.app.test_client()

            def candidate_count() -> int:
                with selection_app.SessionFactory() as session:
                    return session.query(m.Candidate).count()

            # --- 1. no / unsupported target role -> nothing imported -------
            home = client.get("/").get_data(as_text=True)
            check("1. the upload form has a required target-role choice with no preselection",
                  'name="target_role" required' in home and 'value="" selected disabled' in home
                  and '<option value="SERVER">Server</option>' in home
                  and '<option value="FOH_SUPERVISOR">FOH Team Leader</option>' in home)
            missing = upload_json(client, TL_RESUME, "tl.txt", None)
            unsupported = upload_json(client, TL_RESUME, "tl.txt", "CHEF")
            check("1. JSON upload without a target role: refused with a clear message, nothing imported",
                  missing.status_code == 400 and missing.get_json()["status"] == "FAILED"
                  and "Choose the target role" in missing.get_json()["error"])
            check("1. JSON upload with an unsupported target role: refused", unsupported.status_code == 400)
            batch_missing = client.post("/upload", data={"resume_file": [
                (BytesIO(t.encode()), n) for t, n in BATCH]}, content_type="multipart/form-data")
            check("1. batch form without a target role: refused, nothing imported",
                  batch_missing.status_code == 400 and "Choose the target role" in batch_missing.get_data(as_text=True)
                  and candidate_count() == 0)

            # --- 2. single upload for FOH Team Leader ----------------------
            tl = upload_json(client, TL_RESUME, "tl.txt", "FOH_SUPERVISOR").get_json()
            check("2. single upload for FOH Team Leader is imported", tl["status"] == "COMPLETED", f"{tl}")
            check("2. the target role is saved on the application and read back from the database",
                  stored_target(tl["application_id"]) == "FOH_SUPERVISOR")

            # --- 3. batch: one choice for the whole batch --------------------
            batch = client.post("/upload", data={"target_role": "SERVER", "resume_file": [
                (BytesIO(t.encode()), n) for t, n in BATCH]}, content_type="multipart/form-data")
            with selection_app.SessionFactory() as session:
                apps = [a for a in session.query(m.Application).all() if a.id != tl["application_id"]]
            check("3. batch upload: every application of the batch gets the chosen target role",
                  batch.status_code == 200 and len(apps) == 2 and all(a.target_role == "SERVER" for a in apps),
                  f"{[(a.id, a.target_role) for a in apps]}")

            # --- 4. same person, another role ------------------------------
            second = upload_json(client, TL_RESUME_V2, "tl_v2.txt", "SERVER").get_json()
            with selection_app.SessionFactory() as session:
                first_app = session.get(m.Application, tl["application_id"])
                second_app = session.get(m.Application, second["application_id"])
                same_person = first_app.person_id == second_app.person_id
            check("4. the same person can hold two applications with different target roles",
                  same_person and stored_target(tl["application_id"]) == "FOH_SUPERVISOR"
                  and stored_target(second["application_id"]) == "SERVER")

            # --- 5. candidate page and list use the application's role ------
            page_tl = client.get(f"/candidate/{tl['candidate_id']}").get_data(as_text=True)
            page_sv = client.get(f"/candidate/{second['candidate_id']}").get_data(as_text=True)
            check("5. FOH Team Leader page: role shown, breakdown and indicators for FOH Team Leader",
                  "Target Role (application)" in page_tl and "Target role experience (FOH Team Leader)" in page_tl
                  and "refer to the target role <strong>FOH Team Leader</strong>" in page_tl)
            check("5. FOH Team Leader page: no transition or question into Server",
                  "into Server" not in page_tl and "move into Server" not in page_tl)
            check("5. FOH Team Leader page: the Team Leader job is the declared role, duties not verified",
                  "Declared role only: the coordination actually performed is not verified" in page_tl)
            check("5. the page lists the declared coordination responsibility with its experience, area, "
                  "people and original text, plus a neutral question",
                  "Declared coordination responsibilities" in page_tl
                  and "Coordinating the team or the service" in page_tl
                  and "Dining room (FOH)" in page_tl and "6 (declared)" in page_tl
                  and "&ldquo;Coordinated a team of 6 servers per shift&rdquo;" in page_tl
                  and "which decisions were yours to take" in page_tl)
            check("5. the same person's Server application is analysed for Server",
                  "Target role experience (Server)" in page_sv)
            listing = client.get("/").get_data(as_text=True)
            check("5. the candidate list shows each application's target role",
                  "<td>FOH Team Leader</td>" in listing and "<td>Server</td>" in listing)

            # --- 7. the SAME file for another target role -------------------
            def counts() -> tuple[int, int, int]:
                with selection_app.SessionFactory() as session:
                    return (session.query(m.RawResume).count(), session.query(m.Candidate).count(),
                            session.query(m.Application).count())

            before = counts()
            reused = upload_json(client, TL_RESUME, "tl_again_for_server.txt", "SERVER").get_json()
            after = counts()
            with selection_app.SessionFactory() as session:
                first_app = session.get(m.Application, tl["application_id"])
                new_app = session.get(m.Application, reused["application_id"])
                first_snap = session.get(m.Candidate, first_app.candidate_id)
                new_snap = session.get(m.Candidate, new_app.candidate_id)
                same_document = first_snap.raw_resume_id == new_snap.raw_resume_id
                same_facts = [(w.original_job_title, w.employer, w.start_date_text) for w in first_snap.work_history] \
                    == [(w.original_job_title, w.employer, w.start_date_text) for w in new_snap.work_history]
                same_person_again = first_app.person_id == new_app.person_id
            check("7. same CV for another role: a new application, the document reused (no new document)",
                  reused["status"] == "COMPLETED" and reused.get("reused_document") is True
                  and after == (before[0], before[1] + 1, before[2] + 1) and same_document, f"{reused} {before}->{after}")
            check("7. the extracted facts are reused unchanged and the person is the same (same email)",
                  same_facts and same_person_again)
            check("7. each application keeps its own target role; the first one is untouched",
                  stored_target(tl["application_id"]) == "FOH_SUPERVISOR"
                  and stored_target(reused["application_id"]) == "SERVER")
            page_new = client.get(f"/candidate/{reused['candidate_id']}").get_data(as_text=True)
            page_first = client.get(f"/candidate/{tl['candidate_id']}").get_data(as_text=True)
            check("7. two coherent analyses of one CV: Server page for Server, FOH page for FOH Team Leader",
                  "Target role experience (Server)" in page_new
                  and "Target role experience (FOH Team Leader)" in page_first)

            # --- 8. the same file for the same role: duplicate -----------------
            before = counts()
            again = upload_json(client, TL_RESUME, "tl_once_more.txt", "FOH_SUPERVISOR").get_json()
            check("8. same CV for the same target role: reported as a duplicate, no new application",
                  again["status"] == "DUPLICATE" and again["application_id"] == tl["application_id"]
                  and counts() == before and "no new application" in (again["error"] or ""), f"{again}")

            # --- 9. notes / stage of one application leave the other alone -----
            from rfone_data_store.selection import stage_service as stage_svc
            with selection_app.SessionFactory() as session:
                app_svc.add_note(session, tl["application_id"], "Synthetic note on the FOH Team Leader application")
                stage_svc.set_stage(session, tl["application_id"], "PRIMARY_SCREENING")
                session.commit()
            with selection_app.SessionFactory() as session:
                other = session.get(m.Application, reused["application_id"])
                other_notes = app_svc.list_notes(session, reused["application_id"])
                check("9. a note and a stage change on one application leave the other unchanged",
                      not any("Synthetic note" in (n.note_text or "") for n in other_notes)
                      and stage_svc.get_current_stage(session, reused["application_id"]) != "PRIMARY_SCREENING"
                      and stage_svc.get_current_stage(session, tl["application_id"]) == "PRIMARY_SCREENING"
                      and other.target_role == "SERVER")

            # --- 10. uncertain identity: never merged automatically -----------
            nameless = "Jamie Synthetic\n\nEXPERIENCE\nServer, Bistro Prova\nJan 2020 - Present\n"
            a1 = upload_json(client, nameless, "jamie.txt", "SERVER").get_json()
            a2 = upload_json(client, nameless, "jamie_again.txt", "FOH_SUPERVISOR").get_json()
            with selection_app.SessionFactory() as session:
                p1 = session.get(m.Application, a1["application_id"]).person_id
                p2 = session.get(m.Application, a2["application_id"]).person_id
                pending = session.query(m.PersonMatchCandidate).filter_by(application_id=a2["application_id"]).count()
            check("10. no email or phone: the second application is not merged automatically, a match is "
                  "proposed for verification", p1 != p2 and pending >= 1, f"{p1} {p2} {pending}")

            # --- 6. missing / unsupported target role on an application -----
            for value, wording in ((None, "has no target role recorded"), ("BARTENDER", "is not one this")):
                with selection_app.SessionFactory() as session:
                    app_svc.set_target_role(session, tl["application_id"], value)
                    session.commit()
                page = client.get(f"/candidate/{tl['candidate_id']}").get_data(as_text=True)
                check(f"6. target role {value!r}: the page asks for clarification and assumes no role",
                      "Target role to be clarified." in page and wording in page
                      and "Target role experience (" not in page and "Target role experience (Server)" not in page
                      and "move into Server" not in page)
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
