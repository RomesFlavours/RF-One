#!/usr/bin/env python
"""Selection reorganized as one process in five tabs (SELECTION_PROCESS_REORGANIZATION_001).
ALL DATA IS SYNTHETIC. Throwaway SQLite database, FAKE AI (no network), no email.

The Product Owner's verification list (1 Nov 2026): Selection tab with the Jobs list → New Job (Server) →
the Server standard loads → the Job's rules are customized → Save Draft → the Draft reopens intact →
Confirm & Publish → Process → the five tabs keep the current Job → Upload CVs and SP ranking → Reject and
Restore → Evaluation from the ranking and by search → the candidate's history → no Configuration tab →
Interviews and Decisions unchanged → Selection Old unchanged → the Role standard is never modified.

    python test_selection_process_http.py
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import sys
import tempfile
import time
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selection_process_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-process-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace import ai_adapter, engine, sp_queue, sp_routes  # noqa: E402
from workspace import position_profiles  # noqa: E402
from workspace.sp import profiles as spp  # noqa: E402
from workspace.sp import rules as sp_rules  # noqa: E402

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


FIRST = ["Ava", "Ben", "Cleo", "Dan", "Eli", "Fay"]


def cv(i: int) -> str:
    return (f"{FIRST[i]} Sample{i}\n{FIRST[i].lower()}{i}@example.test\n\nEXPERIENCE\n"
            f"Server, Trattoria Esempio {i}, Mount Dora, FL | Jan {2024 - i} - Present\n"
            f"- Full table service for {10 + i} covers\n")


def fake_ai(prompt: str) -> dict:
    if "You do not decide and you do not rank" in prompt:          # CV Selection SP's single reading
        name = re.search(r"<<<(\w+ Sample\d+)", prompt).group(1)
        i = int(re.search(r"Sample(\d+)", name).group(1))
        return {"full_name": name, "jobs": [{"employer": f"Trattoria Esempio {i}", "title": "Server",
                                            "date_text": re.search(r"\| (Jan \d{4} - Present)", prompt).group(1),
                                            "environment": "Italian full-service", "relevant": True}],
                "requirements": {"table_service": {"level": 1 + i % 4, "quotes": ["Full table service"]}},
                "competences": [{"name": "table service", "level": "executed", "quote": "Full table service"}],
                "unknowns": ["Desired weekly hours"]}
    from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
    raise AIProviderUnavailable("fake: not used here")


def wait_analysis(client, pid, expected_done, seconds=30):
    status = {}
    for _ in range(seconds * 10):
        status = client.get(f"/selection/posizioni/{pid}/sp/status").get_json()
        if not status.get("ANALYZING") and status.get("DONE", 0) >= expected_done:
            return status
        time.sleep(0.1)
    return status


def nav(html: str) -> str:
    m = re.search(r'<nav class="nav-tabs selection-navigation".*?</nav>', html, re.S)
    return m.group(0) if m else ""


SERVER_STANDARD = copy.deepcopy(position_profiles.SERVER)
STANDARD_REQUIREMENTS = spp.default_requirements("SERVER")
STANDARD_RULES = sp_rules.defaults("SERVER")

try:
    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as db:
            acc = account_svc.create_account(db, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(db, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            db.commit()
            owner_id = (acc.id, acc.session_version)
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_id
        ai_adapter._REAL_GENERATE_JSON = fake_ai
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
        sp_queue.GENERATE = None

        # 1. Selection opens on the Jobs list, five tabs at the same level, no Configuration
        home = text(owner.get("/selection/"))
        tabs = re.findall(r'>(Selection|Applications|Evaluation|Interviews|Decisions)<', nav(home))
        check("1. Selection opens on the Jobs list with the five tabs (later ones off until a Job is chosen)",
              "<h1>Jobs</h1>" in home and tabs == ["Selection", "Applications", "Evaluation", "Interviews", "Decisions"]
              and nav(home).count('class="tab-off"') == 4 and "+ New Job" in home, tabs)
        t = re.search(r'name="csrf_token" value="([^"]+)"', text(owner.get("/selection/posizioni/nuova"))).group(1)

        # 2. New Job: Server
        new_page = text(owner.get("/selection/posizioni/nuova"))
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "role_code": "SERVER", "location": "Mount Dora", "headcount": "2",
            "timezone": "America/New_York", "manager_account_id": str(owner_id[0]),
            "description": "Synthetic Job: evening servers."})
        pid = int(re.search(r"/selection/posizioni/(\d+)/job", r.headers["Location"]).group(1))
        with selection_app.SessionFactory() as db:
            job = db.get(ws.Position, pid)
            created = (job.status, job.role_code, job.title, job.headcount)
        check("2. New Job (Server): created as a Draft, title from the Role, form opens in the Selection tab",
              created == ("DRAFT", "SERVER", "Server", 2) and "Relevant table-service experience" in new_page, created)

        # 3. Server standard loaded
        form = text(owner.get(f"/selection/posizioni/{pid}/job"))
        names = [d["name"] for d in SERVER_STANDARD["dimensions"]]
        check("3. Server standard loaded: 8 requirements and the rules (short stays, gaps, environments, red flags)",
              all(n in form for n in names) and all(f'name="rule_{k}"' in form for k in STANDARD_RULES)
              and "Professional environments" in form and 'class="active">Selection<' in nav(form)
              and "Save Draft" in form and "Confirm &amp; Publish" in form)

        # 4-5. Customize and Save Draft
        data = {"csrf_token": t, "role_code": "SERVER", "location": "Mount Dora", "headcount": "2", "title": "Server",
                "timezone": "America/New_York", "description": "Synthetic Job: evening servers.",
                "job_ad_en": "Synthetic ad for evening servers.", "questions": "When could you start?\nWeekends?",
                "profile": "Evening table service.", "feat_cv_evaluation": "1", "sp_new_name": "Wine knowledge",
                "sp_new_look_for": "wine, sommelier", "sp_new_crit": "PREFERRED", "sp_new_weight": "8",
                "action": "draft"}
        for r_ in STANDARD_REQUIREMENTS:
            data[f"sp_crit_{r_['id']}"] = r_["criticality"]
            data[f"sp_weight_{r_['id']}"] = "20" if r_["id"] == "guest_selling" else str(r_["weight"])
            if r_["id"] != "recency":
                data[f"sp_active_{r_['id']}"] = "1"
        for rule in STANDARD_RULES:
            if rule != "gaps":
                data[f"rule_{rule}"] = "1"
        r = owner.post(f"/selection/posizioni/{pid}/job", data=data)
        with selection_app.SessionFactory() as db:
            job = db.get(ws.Position, pid)
            sp = sp_routes.state(job)
            saved = (job.status, job.job_ad_en, len(job.questions))
        draft = {x["id"]: x for x in sp["requirements_draft"]}
        check("4. Rules customized for this Job: recency off, guest selling weight 20, Wine knowledge added, gaps off",
              draft["recency"]["active"] is False and draft["guest_selling"]["weight"] == 20
              and draft["custom1"]["name"] == "Wine knowledge" and sp["rules_draft"]["gaps"] is False
              and sp["rules_draft"]["environment"] is True, (draft.get("recency"), sp["rules_draft"]))
        check("5. Save Draft: everything saved, still Draft, back to the Jobs list",
              r.status_code == 302 and r.headers["Location"].endswith("/selection/")
              and saved == ("DRAFT", "Synthetic ad for evening servers.", 2), saved)

        # 6. Reopen the Draft
        dash = text(owner.get("/selection/"))
        form = text(owner.get(f"/selection/posizioni/{pid}/job"))
        check("6. Draft reopens from Complete & Publish with nothing lost",
              f"/selection/posizioni/{pid}/job" in dash and "Complete &amp; Publish" in dash
              and 'name="sp_active_recency" value="1"  aria-label' in form.replace("checked", "")
              and 'name="sp_active_recency" value="1" checked' not in form
              and 'name="sp_weight_guest_selling" value="20"' in form and "Wine knowledge" in form
              and 'name="rule_gaps" value="1"  aria' in form and "Synthetic ad for evening servers." in form)

        # 7. Confirm & Publish
        r = owner.post(f"/selection/posizioni/{pid}/job", data={**data, "action": "publish", "sp_new_name": "",
                                                                "sp_active_custom1": "1", "sp_crit_custom1": "PREFERRED",
                                                                "sp_weight_custom1": "8"})
        with selection_app.SessionFactory() as db:
            job = db.get(ws.Position, pid)
            sp = sp_routes.state(job)
            selection_reqs = [x.name for x in engine.active_requirements(db, job)]
            published = (job.status, bool(job.approved_snapshot_id))
        approved_ids = [x["id"] for x in sp["approved"]["requirements"]]
        check("7. Confirm & Publish: Job Active, requirements v1 approved (recency excluded), rules in force, back to the list",
              published == ("OPEN", True) and r.headers["Location"].endswith("/selection/")
              and "recency" not in approved_ids and "custom1" in approved_ids and sp["rules"]["gaps"] is False
              and len(selection_reqs) == len(approved_ids), (published, approved_ids, selection_reqs))

        # 8. Process
        dash = text(owner.get("/selection/"))
        check("8. Active Job shows Process, which opens Applications for that Job",
              f'href="/selection/posizioni/{pid}/sp">Process</a>' in dash)
        apps = text(owner.get(f"/selection/posizioni/{pid}/sp"))

        # 9. Five tabs keep the current Job
        urls = re.findall(r'<a href="([^"]+)" class="[^"]*">(?:Applications|Evaluation|Interviews|Decisions)<', nav(apps))
        pages = [text(owner.get(u)) for u in urls]
        back_home = text(owner.get("/selection/"))
        check("9. The five tabs keep the current Job (Role, location, status always visible)",
              len(urls) == 4 and all(f"/posizioni/{pid}" in u for u in urls)
              and all('class="job-bar"' in p and "<b>Server</b>" in p and "Mount Dora" in p and ">Active<" in p
                      for p in pages + [apps, back_home])
              and 'class="active">Applications<' in nav(apps) and 'class="active">Interviews<' in nav(pages[2])
              and 'class="active">Decisions<' in nav(pages[3]) and 'class="active">Evaluation<' in nav(pages[1]), urls)

        # 10. Upload CVs and SP ranking
        files = [(BytesIO(cv(i).encode()), f"cv{i}.txt") for i in range(5)]
        r = owner.post(f"/selection/posizioni/{pid}/sp/upload", data={"csrf_token": t, "cv": files},
                       content_type="multipart/form-data", follow_redirects=True)
        status = wait_analysis(owner, pid, 5)
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        ranked_ids = re.findall(rf'<b><a href="/selection/posizioni/{pid}/candidati/(\d+)">', page)
        check("10. Upload CVs in Applications: 5 imported and analyzed, ranked with reasons",
              'type="file"' in page and "Upload 1: 5 CV(s) received · 5 new imported" in text(r)
              and status.get("DONE") == 5 and len(ranked_ids) == 5 and page.count('class="why"') >= 1, status)

        # 11. Reject and restore
        target = ranked_ids[0]
        r = owner.post(f"/selection/posizioni/{pid}/decisioni", data={
            "csrf_token": t, "pc_id": target, "decision": "NOT_SELECTED", "reason": "OTHER",
            "note": "Synthetic rejection", "back": f"/selection/posizioni/{pid}/sp#ranking"})
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        ranked_after = re.findall(rf'<tr>\s*<td><div class="rank">', page)
        rejected_block = page.split("<h2 style=\"margin-top:18px\">Rejected", 1)
        with selection_app.SessionFactory() as db:
            kept = db.query(ws.Proposal).filter(ws.Proposal.position_candidate_id == int(target),
                                                ws.Proposal.source == "SP", ws.Proposal.is_current.is_(True)).count()
            decision = engine.current_decision(db, int(target))
            rejected = (decision.decision, decision.actor_name, decision.note, decision.reason_code)
        rejected_ok = (len(ranked_after) == 4 and len(rejected_block) == 2 and f"candidati/{target}" in rejected_block[1]
                       and "Synthetic rejection" in rejected_block[1] and kept == 1
                       and rejected == ("NOT_SELECTED", "Synthetic Owner", "Synthetic rejection", "OTHER"))
        owner.post(f"/selection/posizioni/{pid}/decisioni", data={
            "csrf_token": t, "pc_id": target, "decision": "UNDECIDED", "note": "Rejection withdrawn: back in the ranking",
            "back": f"/selection/posizioni/{pid}/sp#ranking"})
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        check("11. Reject: out of the ranking, listed with date, user and reason, CV and analysis kept; Restore brings it back",
              rejected_ok and len(re.findall(r'<tr>\s*<td><div class="rank">', page)) == 5
              and "margin-top:18px\">Rejected" not in page, (len(ranked_after), rejected, kept))

        # 12. Evaluation from the ranking
        dossier = text(owner.get(f"/selection/posizioni/{pid}/candidati/{target}"))
        check("12. A name in the ranking opens Evaluation with that candidate and the SP analysis",
              'class="active">Evaluation<' in nav(dossier) and "CV Selection SP analysis" in dossier
              and "Approved requirements" in dossier and "Red flags" in dossier and "To verify" in dossier
              and "Work history" in dossier and "Original résumé" in dossier and 'class="job-bar"' in dossier)

        # 13. Evaluation opened directly: search
        found = text(owner.get(f"/selection/posizioni/{pid}/evaluation?q=Ben"))
        jump = owner.get(f"/selection/posizioni/{pid}/evaluation?pc={target}")
        check("13. Evaluation by search: finds the candidate of the current Job and opens the dossier",
              "Ben Sample1" in found and "Ava Sample0" not in found and jump.status_code == 302
              and jump.headers["Location"].endswith(f"/candidati/{target}"))

        # 14. History
        history = dossier = text(owner.get(f"/selection/posizioni/{pid}/candidati/{target}"))
        history = history.split('id="storico"', 1)[1].split("</table>", 1)[0]
        check("14. History: CV received, upload, AI analysis, rejection and restore, in order",
              all(x in history for x in ("Upload #1", "CV Selection SP analysis with requirements v1",
                                         "Not selected", "Synthetic rejection", "Rejection withdrawn")))

        # 15. No Configuration tab
        all_pages = [home, form, apps, dossier, found] + pages
        legacy = owner.get(f"/selection/posizioni/{pid}?tab=configuration")
        check("15. No Configuration tab anywhere; its old address opens the Job form",
              all("Configuration" not in nav(p) for p in all_pages)
              and all("Configuration</a>" not in p for p in all_pages)
              and legacy.status_code == 302 and legacy.headers["Location"].endswith(f"/posizioni/{pid}/job"))

        # 16. Interviews and Decisions unchanged
        owner.post(f"/selection/posizioni/{pid}/candidati/{target}/colloquio", data={
            "csrf_token": t, "kind": "IN_PERSON", "duration": "30", "place": "Restaurant", "mode": "book",
            "starts_at": "2030-01-15T10:00"})
        owner.post(f"/selection/posizioni/{pid}/decisioni", data={
            "csrf_token": t, "pc_id": ranked_ids[1], "decision": "HIRED", "back": f"/selection/posizioni/{pid}?tab=decisioni"})
        interviews = text(owner.get(f"/selection/posizioni/{pid}?tab=colloqui"))
        decisions = text(owner.get(f"/selection/posizioni/{pid}?tab=decisioni"))
        check("16. Interviews and Decisions work as before (calendar, booking, outcomes, history, close)",
              "Calendar" in interviews and "Restaurant" in interviews and "In person" in interviews
              and "Hired" in decisions and "Close Job" in decisions and "History" in decisions)

        # Interviews tab: candidate sheet, configuration, observation, clarify, scenarios, save and resume
        from workspace import interviews as iv
        with selection_app.SessionFactory() as db:
            std_before = copy.deepcopy(iv.standard(db, "SERVER"))
            line_cook = iv.standard(db, "LINE_COOK")
            db.commit()
        page = text(owner.get(f"/selection/posizioni/{pid}/interviews?pc={target}"))
        check("I1. Interviews: opens directly on a candidate of the current Job, with Evaluation link and status",
              'class="active">Interviews<' in nav(page) and f'<option value="{target}" selected' in page
              and f"/candidati/{target}" in page and ">Not started<" in page and "Configure Interview" in page
              and "Desired weekly hours" in page and "Unhappy guest" in page)
        q_ids = re.findall(r'name="q_active_([\w-]+)"', page)
        sc_ids = re.findall(r'name="sc_active_([\w-]+)"', page)
        cl_ids = re.findall(r'name="cl_active_([\w-]+)"', page)
        cfg = {"csrf_token": t, "new_questions": "Synthetic question for this candidate only?"}
        for i, q in enumerate(q_ids):
            if i != 0:
                cfg[f"q_active_{q}"] = "1"
        cfg[f"q_text_{q_ids[1]}"] = "Edited synthetic question?"
        for s_ in sc_ids:
            if s_ != "m-allergies":
                cfg[f"sc_active_{s_}"] = "1"
        for c in cl_ids:
            cfg[f"cl_active_{c}"] = "1"
        owner.post(f"/selection/posizioni/{pid}/interviews/{target}/config", data=cfg)
        page = text(owner.get(f"/selection/posizioni/{pid}/interviews?pc={target}"))
        sheet = page.split('id="iv-config"')[0]
        with selection_app.SessionFactory() as db:
            std_after = iv.standard(db, "SERVER")
            other = iv.configuration(db, db.get(ws.Position, pid), db.get(ws.PositionCandidate, int(ranked_ids[2])),
                                     iv.load(db, int(ranked_ids[2])))
            db.commit()
        check("I2. Configure Interview: saved for this candidate (question off, edited, added; scenario off)",
              ">Configured<" in page and "Edited synthetic question?" in sheet
              and "Synthetic question for this candidate only?" in sheet and f'name="q_{q_ids[0]}_answer"' not in sheet
              and 'name="sc_m-allergies_answer"' not in sheet and 'name="sc_m-unhappy_guest_answer"' in sheet)
        check("I3. The Role standard is unchanged and another candidate starts from it whole",
              std_after == std_before and all(q["active"] for q in other["questions"])
              and other["questions"][1]["text"] != "Edited synthetic question?"
              and [s_["title"] for s_ in line_cook["scenarios"]] == ["Priorities during a rush", "Food safety",
                                                                    "Wrong preparation"])
        clar = cl_ids[0]
        sheet_data = {"csrf_token": t, "mode": "MIXED",
                      "dim_professional_rating": "DEMONSTRATED", "dim_professional_evidence": "Ran 6 tables alone",
                      "dim_professional_src": "IN_PERSON",
                      "dim_teamwork_rating": "CONCERN", "dim_teamwork_evidence": "Said he never helps other stations",
                      "dim_teamwork_src": "PHONE",
                      f"cl_{clar}_status": "PARTIAL", f"cl_{clar}_answer": "About 25 hours", f"cl_{clar}_evidence": "Stated",
                      "sc_m-unhappy_guest_rating": "PARTIAL", "sc_m-unhappy_guest_answer": "Apologize and call the manager",
                      "sc_m-unhappy_guest_evidence": "Did not offer a solution", "autosave": "1"}
        auto = owner.post(f"/selection/posizioni/{pid}/interviews/{target}/save", data=sheet_data)
        page = text(owner.get(f"/selection/posizioni/{pid}/interviews?pc={target}"))
        check("I4-I6. Observation, clarify and scenario saved progressively (autosave) and resumed with their sources",
              auto.get_json() == {"ok": True, "status": "In progress"} and "Ran 6 tables alone" in page
              and 'value="DEMONSTRATED" checked' in page and "About 25 hours" in page
              and 'value="PARTIAL" checked' in page and "Did not offer a solution" in page
              and '<option value="PHONE" selected' in page and '<option value="MIXED" selected' in page)
        sheet_data.pop("autosave")
        owner.post(f"/selection/posizioni/{pid}/interviews/{target}/save", data={**sheet_data, "action": "complete"})
        page = text(owner.get(f"/selection/posizioni/{pid}/interviews?pc={target}"))
        summ = page.split('id="summary"')[1].split('id="iv-config"')[0]
        check("I7. Complete: status Completed, summary motivated by the evidence; still-open points are not concerns",
              ">Completed<" in page and "Demonstrated <span class=\"badge\">1</span>" in summ
              and "Concerns Documented <span class=\"badge\">1</span>" in summ and "Ran 6 tables alone" in summ
              and "Said he never helps other stations" in summ
              and "Partially Clarified" in summ.split("Concerns Documented")[0].split("Needs Clarification")[1])
        dossier_now = text(owner.get(f"/selection/posizioni/{pid}/candidati/{target}"))
        hist = dossier_now.split('id="storico"', 1)[1].split("</table>", 1)[0]
        check("I8. Evaluation history: interview configured, saved and completed (mode, interviewer, summary)",
              "Interview configured" in hist and "Interview completed (Mixed, Synthetic Owner)" in hist
              and "1 concern(s) documented" in hist and "Interview sheet" in dossier_now)
        with selection_app.SessionFactory() as db:
            rows_iv = db.query(ws.Proposal).filter(ws.Proposal.source == "INTERVIEW").count()
            lead_ok = engine.leading_proposal(engine.current_proposals(db, int(target))) is None or                 engine.leading_proposal(engine.current_proposals(db, int(target))).source != "INTERVIEW"
        check("I9. One interview record per candidate, never taken as a proposal", rows_iv == 1 and lead_ok, rows_iv)

        # 17. Selection Old
        old = owner.get("/selection/candidates")
        check("17. Selection Old still opens (/selection/candidates)", old.status_code == 200, old.status_code)

        # Modal window: New Job and Complete & Publish open the same form over the Jobs list
        modal_new = text(owner.get("/selection/posizioni/nuova?modal=1"))
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "modal": "1", "role_code": "SERVER", "location": "Tavares", "headcount": "1",
            "timezone": "America/New_York", "manager_account_id": str(owner_id[0])})
        mpid = int(re.search(r"/selection/posizioni/(\d+)/job\?modal=1", r.headers["Location"]).group(1))
        modal_form = text(owner.get(f"/selection/posizioni/{mpid}/job?modal=1"))
        saved = owner.post(f"/selection/posizioni/{mpid}/job", data={
            "csrf_token": t, "modal": "1", "role_code": "SERVER", "location": "Tavares", "headcount": "3",
            "title": "Server", "timezone": "America/New_York", "job_ad_en": "Modal ad.", "questions": "Weekends?",
            "feat_cv_evaluation": "1", "action": "draft",
            **{f"sp_active_{x['id']}": "1" for x in STANDARD_REQUIREMENTS},
            **{f"sp_crit_{x['id']}": x["criticality"] for x in STANDARD_REQUIREMENTS},
            **{f"sp_weight_{x['id']}": str(x["weight"]) for x in STANDARD_REQUIREMENTS}})
        listing = text(owner.get("/selection/"))
        reopened = text(owner.get(f"/selection/posizioni/{mpid}/job?modal=1"))
        published = owner.post(f"/selection/posizioni/{mpid}/job", data={
            "csrf_token": t, "modal": "1", "role_code": "SERVER", "location": "Tavares", "headcount": "3",
            "title": "Server", "timezone": "America/New_York", "job_ad_en": "Modal ad.", "questions": "Weekends?",
            "feat_cv_evaluation": "1", "action": "publish",
            **{f"sp_active_{x['id']}": "1" for x in STANDARD_REQUIREMENTS},
            **{f"sp_crit_{x['id']}": x["criticality"] for x in STANDARD_REQUIREMENTS},
            **{f"sp_weight_{x['id']}": str(x["weight"]) for x in STANDARD_REQUIREMENTS}})
        with selection_app.SessionFactory() as db:
            mstatus = db.get(ws.Position, mpid).status
        check("modal: New Job and Complete & Publish open the same form in a modal over the Jobs list",
              'data-job-modal="New Job"' in listing and 'id="job-modal"' in listing and "job-modal-x" in listing)
        check("modal: the form in the modal has no shell, keeps modal=1 and a Cancel that closes the window",
              "nav-tabs" not in modal_new and 'name="modal" value="1"' in modal_new and "data-modal-cancel" in modal_new
              and "nav-tabs" not in modal_form and "Relevant table-service experience" in modal_form
              and "jobFormDirty" in modal_form)
        check("modal: Save Draft closes the window and reloads the list; the Draft reopens with its data",
              "SelectionModal.done()" in text(saved) and "Draft saved" in listing
              and f'href="/selection/posizioni/{mpid}/job" data-job-modal=' in listing
              and 'name="headcount" value="3"' in reopened and "Modal ad." in reopened)
        check("modal: Confirm & Publish closes the window, the Job is Active",
              "SelectionModal.done()" in text(published) and mstatus == "OPEN", mstatus)

        # Role standard never modified by a Job
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "role_code": "SERVER", "location": "Eustis", "headcount": "1",
            "timezone": "America/New_York", "manager_account_id": str(owner_id[0])})
        pid2 = int(re.search(r"/selection/posizioni/(\d+)/job", r.headers["Location"]).group(1))
        with selection_app.SessionFactory() as db:
            sp2 = sp_routes.state(db.get(ws.Position, pid2))
        check("standard: the Server standard is unchanged and a new Server Job gets it whole",
              position_profiles.SERVER == SERVER_STANDARD and spp.default_requirements("SERVER") == STANDARD_REQUIREMENTS
              and sp_rules.defaults("SERVER") == STANDARD_RULES
              and sp2["requirements_draft"] == STANDARD_REQUIREMENTS and sp2["rules_draft"] == STANDARD_RULES)

        # Rule filter: a switched-off rule hides what it produces, the stored analysis stays whole
        analysis = {"flags": [{"flag": "a", "source": "CV"}, {"flag": "b", "source": "DATES"},
                              {"flag": "c", "source": "PROFILE"}],
                    "gaps": [{"text": "4 months"}], "unknowns": ["Gap of 4 months: x", "Desired hours"],
                    "stability": {"flags": [{"code": "TWO_SHORT"}]}}
        shown = sp_rules.apply(analysis, "SERVER", {"gaps": False, "short_stays": False})
        check("rules: gaps and short stays off hide only their output; the stored analysis is not changed",
              [f["flag"] for f in shown["flags"]] == ["a", "c"] and shown["gaps"] == []
              and shown["unknowns"] == ["Desired hours"] and len(analysis["flags"]) == 3 and analysis["gaps"])
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
