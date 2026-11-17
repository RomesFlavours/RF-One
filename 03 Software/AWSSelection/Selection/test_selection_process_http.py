#!/usr/bin/env python
"""Selection reorganized as one process in five tabs (SELECTION_PROCESS_REORGANIZATION_001).
ALL DATA IS SYNTHETIC. Throwaway SQLite database, FAKE AI (no network), no email.

The Product Owner's verification list (1 Nov 2026): Selection tab with the Jobs list → New Job (Server) →
the Server standard loads → the Job's rules are customized → Save Draft → the Draft reopens intact →
Confirm & Publish → Process → the five tabs keep the current Job → Upload CVs and SP ranking → Reject and
Restore → Evaluation from the ranking and by search → the candidate's history → no Configuration tab →
Interviews and Decisions unchanged → Selection Old unchanged → the Role standard is never modified.

Updated 2026-11-15 (A7) to the navigation and flow approved after 1 Nov: the first tab is "Job Position",
Evaluation is no longer a tab (the candidate dossier is opened from Applications), Configurations is a tab,
CV upload only stores the CVs and the analysis starts with an explicit Analyze, and Applications is the
candidate list of the Job (the old SP ranking address redirects there).

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
            # A new Job needs an active Role defined in Configurations (approved after this test was written).
            from workspace.role_catalog import JobRole
            db.add(JobRole(code="SERVER", name="Server", name_key="server", active=True, version=1))
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
        tabs = re.findall(r'>(Job Position|Applications|Interviews|Decisions|Requirements &amp; Priorities|Configurations)<', nav(home))
        check("1. Selection opens on the Job Position list with its tabs (Job tabs off until a Job is chosen)",
              "<h1>Job Position</h1>" in home and tabs == ["Job Position", "Applications", "Interviews", "Decisions",
                                                           "Requirements &amp; Priorities", "Configurations"]
              and nav(home).count('class="tab-off"') == 3 and "New Job" in home, tabs)
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
              and "Professional environments" in form and 'class="active">Job Position<' in nav(form)
              and "Save Draft" in form and "Confirm &amp; Publish" in form)

        # 4-5. Customize and Save Draft
        data = {"csrf_token": t, "role_code": "SERVER", "location": "Mount Dora", "headcount": "2", "title": "Server",
                "timezone": "America/New_York", "description": "Synthetic Job: evening servers.",
                "job_ad_en": "Synthetic ad for evening servers. We are looking for a Server who looks after our guests and keeps every table moving.", "questions": "When could you start?\nWeekends?",
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
              and saved == ("DRAFT", "Synthetic ad for evening servers. We are looking for a Server who looks after our guests and keeps every table moving.", 2), saved)

        # 6. Reopen the Draft
        dash = text(owner.get("/selection/"))
        form = text(owner.get(f"/selection/posizioni/{pid}/job"))
        check("6. Draft reopens from Edit with nothing lost",
              f'href="/selection/posizioni/{pid}/job"' in dash and ">Edit<" in dash
              and 'name="sp_active_recency" value="1"  aria-label' in form.replace("checked", "")
              and 'name="sp_active_recency" value="1" checked' not in form
              and 'name="sp_weight_guest_selling" value="20"' in form and "Wine knowledge" in form
              and 'name="rule_gaps" value="1"  aria' in form and "Synthetic ad for evening servers. We are looking for a Server who looks after our guests and keeps every table moving." in form)

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
        old_ranking = owner.get(f"/selection/posizioni/{pid}/sp")
        apps = text(owner.get(f"/selection/posizioni/{pid}?tab=candidature"))
        check("8. Active Job opens Applications for that Job (the old ranking address redirects there)",
              f'href="/selection/posizioni/{pid}?tab=candidature"' in dash and "Select and set the Job Position" in dash
              and old_ranking.status_code == 302 and old_ranking.headers["Location"].endswith(f"/posizioni/{pid}?tab=candidature")
              and 'class="active">Applications<' in nav(apps))

        # 9. Five tabs keep the current Job
        urls = re.findall(r'<a href="([^"]+)" class="[^"]*">(?:Applications|Interviews|Decisions)<', nav(apps))
        pages = [text(owner.get(u)) for u in urls]
        back_home = text(owner.get("/selection/"))
        check("9. The Job tabs keep the current Job (Role and location always visible)",
              len(urls) == 3 and all(f"/posizioni/{pid}" in u for u in urls)
              and all('class="job-bar"' in p and "<b>Server</b>" in p and "Mount Dora" in p
                      for p in pages + [apps, back_home])
              and 'class="active">Applications<' in nav(pages[0]) and 'class="active">Interviews<' in nav(pages[1])
              and 'class="active">Decisions<' in nav(pages[2]), urls)

        # 10. Upload CVs and SP ranking
        files = [(BytesIO(cv(i).encode()), f"cv{i}.txt") for i in range(5)]
        r = owner.post(f"/selection/posizioni/{pid}/sp/upload", data={"csrf_token": t, "cv": files},
                       content_type="multipart/form-data", follow_redirects=True)
        waiting = owner.get(f"/selection/posizioni/{pid}/sp/status").get_json()
        owner.post(f"/selection/posizioni/{pid}/sp/analyze", data={"csrf_token": t})
        status = wait_analysis(owner, pid, 5)
        page = text(owner.get(f"/selection/posizioni/{pid}?tab=candidature"))
        ranked_ids = re.findall(r'<tr id="candidate-(\d+)"', page)
        check("10. Upload CVs in Applications: 5 stored without analysis, Analyze reads them, all 5 listed",
              waiting == {"WAITING": 5} and status.get("DONE") == 5 and len(ranked_ids) == 5, (waiting, status))

        # 11. Reject and restore
        target = ranked_ids[0]
        r = owner.post(f"/selection/posizioni/{pid}/decisioni", data={
            "csrf_token": t, "pc_id": target, "decision": "NOT_SELECTED", "reason": "OTHER",
            "note": "Synthetic rejection", "back": f"/selection/posizioni/{pid}/sp#ranking"})
        with selection_app.SessionFactory() as db:
            kept = db.query(ws.Proposal).filter(ws.Proposal.position_candidate_id == int(target),
                                                ws.Proposal.source == "SP", ws.Proposal.is_current.is_(True)).count()
            decision = engine.current_decision(db, int(target))
            rejected = (decision.decision, decision.actor_name, decision.note, decision.reason_code)
        rejected_ok = kept == 1 and rejected == ("NOT_SELECTED", "Synthetic Owner", "Synthetic rejection", "OTHER")
        owner.post(f"/selection/posizioni/{pid}/decisioni", data={
            "csrf_token": t, "pc_id": target, "decision": "UNDECIDED", "note": "Rejection withdrawn: back in the ranking",
            "back": f"/selection/posizioni/{pid}/sp#ranking"})
        page = text(owner.get(f"/selection/posizioni/{pid}?tab=candidature"))
        with selection_app.SessionFactory() as db:
            restored = engine.current_decision(db, int(target))
        check("11. Reject: recorded with user and reason, CV and analysis kept; Restore withdraws it",
              rejected_ok and len(re.findall(r'<tr id="candidate-(\d+)"', page)) == 5
              and (restored is None or restored.decision == "UNDECIDED"), (rejected, kept))

        # 12. Evaluation from the ranking
        dossier = text(owner.get(f"/selection/posizioni/{pid}/candidati/{target}"))
        check("12. A name in Applications opens the candidate dossier with the SP analysis",
              f'/selection/posizioni/{pid}/candidati/{target}' in page and "CV Selection SP analysis" in dossier
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
        check("15. Configurations is its own tab on every page; the old Job configuration address opens the Job form",
              all('href="/selection/configurazioni"' in nav(p) for p in all_pages if nav(p))
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
              and "Send to Training" in decisions and "Close Job" in decisions and "History" in decisions)

        # Interviews tab: candidate sheet, configuration, observation, clarify, scenarios, save and resume
        from workspace import interviews as iv
        with selection_app.SessionFactory() as db:
            std_before = copy.deepcopy(iv.standard(db, "SERVER"))
            line_cook = iv.standard(db, "LINE_COOK")
            db.commit()
        page = text(owner.get(f"/selection/posizioni/{pid}/interviews?pc={target}"))
        check("I1. Interviews: opens directly on a candidate of the current Job, with dossier link and status",
              'class="active">Interviews<' in nav(page) and f'<option value="{target}" selected' in page
              and f"/candidati/{target}" in page and ">Not started<" in page
              and "Desired weekly hours" in page and "Unhappy guest" in page)
        cl_ids = re.findall(r'name="cl_([\w-]+)_status"', page)
        # The per-candidate "Configure Interview" was replaced by observation templates per Role and location
        # in Configurations (test_observation_templates.py): the sheet shows the Role standard's questions.
        legacy_config = owner.post(f"/selection/posizioni/{pid}/interviews/{target}/config", data={"csrf_token": t})
        with selection_app.SessionFactory() as db:
            std_after = iv.standard(db, "SERVER")
            db.commit()
        check("I2. The interview sheet comes from the Role standard; no per-candidate configuration endpoint remains",
              legacy_config.status_code in (404, 405) and 'name="sc_m-allergies_answer"' in page
              and 'name="sc_m-unhappy_guest_answer"' in page and len(cl_ids) >= 1 and "Configure Interview" not in page,
              legacy_config.status_code)
        check("I3. The Role standard is unchanged by interviews",
              std_after == std_before
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
        check("I8. Dossier history: interview completed (mode, interviewer, summary)",
              "Interview completed (Mixed, Synthetic Owner)" in hist
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
            "title": "Server", "timezone": "America/New_York", "job_ad_en": "Modal ad. We are looking for a Server who looks after our guests, explains the menu and keeps every table moving.", "questions": "Weekends?",
            "feat_cv_evaluation": "1", "action": "draft",
            **{f"sp_active_{x['id']}": "1" for x in STANDARD_REQUIREMENTS},
            **{f"sp_crit_{x['id']}": x["criticality"] for x in STANDARD_REQUIREMENTS},
            **{f"sp_weight_{x['id']}": str(x["weight"]) for x in STANDARD_REQUIREMENTS}})
        listing = text(owner.get("/selection/"))
        reopened = text(owner.get(f"/selection/posizioni/{mpid}/job?modal=1"))
        published = owner.post(f"/selection/posizioni/{mpid}/job", data={
            "csrf_token": t, "modal": "1", "role_code": "SERVER", "location": "Tavares", "headcount": "3",
            "title": "Server", "timezone": "America/New_York", "job_ad_en": "Modal ad. We are looking for a Server who looks after our guests, explains the menu and keeps every table moving.", "questions": "Weekends?",
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
              and 'name="headcount" value="3"' in reopened and "Modal ad. We are looking for a Server who looks after our guests, explains the menu and keeps every table moving." in reopened)
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
