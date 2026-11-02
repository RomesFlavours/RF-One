#!/usr/bin/env python
"""CV Selection SP integrated in Selection — successive uploads, duplicates, NEW / Last Upload, one ranking.
ALL DATA IS SYNTHETIC. Throwaway SQLite database, FAKE AI (no network, calls counted), no email.

Path (the Product Owner's verification list, 1 Nov 2026): position created on the Selection page → 12 CVs
uploaded from the position's row and analyzed → 8 more uploaded → 20 candidates → an identical CV is not
imported again → a same-email CV is flagged as a possible duplicate → Last Upload filter and NEW → the
ranking holds every candidate → earlier analyses are not repeated; a requirement change marks them for update.

    python test_sp_integration_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import json
import tempfile
import threading
import time
from datetime import timedelta
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selection_sp_integration_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-sp-integration-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace import ai_adapter, sp_queue  # noqa: E402

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


FIRST = ["Ava", "Ben", "Cleo", "Dan", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jade", "Kai", "Lia",
         "Max", "Nia", "Oto", "Pia", "Quin", "Rae", "Sol", "Tess"]


def cv(i: int, email: str | None = None) -> str:
    name = f"{FIRST[i]} Sample{i}"
    years = 1 + i % 5
    return (f"{name}\n{email or FIRST[i].lower() + str(i) + '@example.test'}\n\nEXPERIENCE\n"
            f"Server, Trattoria Esempio {i}, Mount Dora, FL | Jan {2025 - years} - Present\n"
            f"- Full table service for {10 + i} covers\n")


calls = {"sp": 0, "import": 0, "other_cv": 0}
lock = threading.Lock()


def fake_ai(prompt: str) -> dict:
    if "You do not decide and you do not rank" in prompt:          # CV Selection SP's single reading
        with lock:
            calls["sp"] += 1
        name = re.search(r"<<<(\w+ Sample\d+)", prompt).group(1)
        date_text = re.search(r"\| (Jan \d{4} - Present)", prompt).group(1)
        i = int(re.search(r"Sample(\d+)", name).group(1))
        return {"full_name": name, "jobs": [{"employer": f"Trattoria Esempio {i}", "title": "Server",
                                            "date_text": date_text, "environment": "Italian full-service",
                                            "relevant": True}],
                "requirements": {"table_service": {"level": 2 + i % 3, "quotes": ["Full table service"]}},
                "competences": [{"name": "table service", "level": "executed", "quote": "Full table service"}],
                "unknowns": ["Desired weekly hours"]}
    if "extracting structured information from a résumé" in prompt:   # the AI reading at import
        with lock:
            calls["import"] += 1
        lines = prompt.split("---" + chr(10), 1)[1].splitlines()
        return {"full_name": lines[0].strip(), "email": lines[1].strip(), "work_history": [], "skills": []}
    with lock:
        calls["other_cv"] += 1   # any other résumé reading (Selection's own evaluation)
    from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
    raise AIProviderUnavailable("fake: not used by the SP path")


def wait_analysis(client, pid, expected_done, seconds=30):
    status = {}
    for _ in range(seconds * 10):
        status = client.get(f"/selection/posizioni/{pid}/sp/status").get_json()
        if not status.get("ANALYZING") and status.get("DONE", 0) >= expected_done:
            return status
        time.sleep(0.1)
    return status


def upload(client, t, pid, items):
    files = [(BytesIO(body.encode()), name) for name, body in items]
    return client.post(f"/selection/posizioni/{pid}/sp/upload", data={"csrf_token": t, "cv": files},
                       content_type="multipart/form-data", follow_redirects=True)


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
        t = re.search(r'name="csrf_token" value="([^"]+)"', text(owner.get("/selection/posizioni/nuova"))).group(1)
        ai_adapter._REAL_GENERATE_JSON = fake_ai
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
        sp_queue.GENERATE = None   # the real seam (ai_adapter._transport) with the fake transport above

        # 1. Position from the Selection page; AI résumé evaluation on; SP requirements approved
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "title": "Server SP test", "role_code": "SERVER", "location": "Mount Dora",
            "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(owner_id[0]),
            "description": "Synthetic position."}, follow_redirects=True)
        pid = int(re.search(r"/selection/posizioni/(\d+)/", text(r)).group(1))
        owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
            "csrf_token": t, "name": "Restaurant table service", "description": "server restaurant",
            "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
        owner.post(f"/selection/posizioni/{pid}/dettagli", data={
            "csrf_token": t, "headcount": "1", "job_ad_en": "Synthetic ad.", "questions": "When could you start?"})
        owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
        owner.post(f"/selection/posizioni/{pid}/configuration", data={"csrf_token": t, "cv_evaluation": "1"})
        dash = text(owner.get("/selection/"))
        tab = owner.get(f"/selection/posizioni/{pid}?tab=candidature")
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        check("one Upload CVs only: in Applications (the SP page), never on the Jobs list",
              tab.status_code == 302 and tab.headers["Location"].endswith(f"/posizioni/{pid}/sp")
              and f"/selection/posizioni/{pid}/sp/upload" in page and page.count('type="file"') == 1
              and 'type="file"' not in dash and f"/selection/posizioni/{pid}/cv\"" not in page)
        check("Jobs list: the Active Job's Process opens Applications (the SP ranking)",
              f'href="/selection/posizioni/{pid}/sp">Process</a>' in dash)
        check("SP page: Shelbi's Server profile as the Job's requirements",
              "Relevant table-service experience" in page)
        owner.post(f"/selection/posizioni/{pid}/sp/requirements", data={"csrf_token": t, "action": "approve"})

        # 2-3. First upload: 12 CVs, analyzed automatically
        r = upload(owner, t, pid, [(f"cv{i}.txt", cv(i)) for i in range(12)])
        body = text(r)
        check("upload 1: summary 12 received · 12 new · 0 exact · 0 possible",
              "Upload 1: 12 CV(s) received · 12 new imported · 0 exact duplicate(s) ignored · 0 possible duplicate(s)"
              in body, re.findall(r"Upload 1:[^<]+", body))
        s = wait_analysis(owner, pid, 12)
        check("analysis 1: the 12 CVs analyzed, one AI reading at import (name, email, phone) and one SP "
              "evaluation each, no Selection evaluation", s.get("DONE") == 12
              and calls == {"sp": 12, "import": 12, "other_cv": 0}, (s, calls))

        # 4-5. Second upload: 8 more; only those analyzed; total 20
        r = upload(owner, t, pid, [(f"cv{i}.txt", cv(i)) for i in range(12, 20)])
        check("upload 2: 8 received · 8 new imported", "Upload 2: 8 CV(s) received · 8 new imported" in text(r))
        s = wait_analysis(owner, pid, 20)
        with selection_app.SessionFactory() as db:
            total = db.scalar(select(func.count()).select_from(ws.PositionCandidate)
                              .where(ws.PositionCandidate.position_id == pid))
        check("total: 20 candidates in the position, all analyzed", total == 20 and s.get("DONE") == 20, (total, s))
        check("Bedrock not repeated: 20 SP readings in all (12 + 8), earlier analyses reused", calls["sp"] == 20, calls)

        # 6. Identical CV again: not imported
        r = upload(owner, t, pid, [("cv3-again.txt", cv(3))])
        with selection_app.SessionFactory() as db:
            total = db.scalar(select(func.count()).select_from(ws.PositionCandidate)
                              .where(ws.PositionCandidate.position_id == pid))
        check("exact duplicate: the identical CV is ignored, total still 20, no AI call",
              "1 exact duplicate(s) ignored" in text(r) and total == 20 and calls["sp"] == 20, (total, calls))
        last_page = text(owner.get(f"/selection/posizioni/{pid}/sp?view=last"))
        check("Last Upload after a duplicates-only upload: still the 8 of upload #2, and it says why",
              len(re.findall(r'<div class="rank">', last_page)) == 8 and "upload #3 added no new CV" in last_page)

        # Possible duplicate: same email, different CV -> imported and flagged, never merged
        r = upload(owner, t, pid, [("cv5-new-version.txt", cv(5).replace("Full table service", "Wine service")
                                    + "- Trained two new servers\n")])
        body = text(r)
        check("possible duplicate: same email, different CV → imported and flagged for the manager",
              "1 new imported" in body and "1 possible duplicate(s) to verify" in body
              and "Possible duplicate" in body, re.findall(r"Upload 4:[^<]+", body))
        wait_analysis(owner, pid, 21)

        # 7. Last Upload filter and NEW
        all_page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        last_page = text(owner.get(f"/selection/posizioni/{pid}/sp?view=last"))
        ranked_all = re.findall(r'<div class="rank">(\d+)</div>', all_page)
        ranked_last = re.findall(r'<div class="rank">(\d+)</div>', last_page)
        check("filter: All Candidates shows every analyzed candidate (21), Last Upload only the last upload (1)",
              len(ranked_all) == 21 and len(ranked_last) == 1 and "Last Upload" in all_page, (len(ranked_all), len(ranked_last)))
        check("NEW: only the last upload's candidate carries NEW in the ranking",
              all_page.count('<span class="badge gB">NEW</span>') >= 1 and "Sample5" in last_page
              and "Sample0" not in last_page)
        check("uploads stay identifiable after reopening: history lists uploads #1-#4",
              all(f"<td>#{n}</td>" in all_page for n in (1, 2, 3, 4)))

        # 8-9. One ranking with everyone; Analyze again sends nothing
        r = owner.post(f"/selection/posizioni/{pid}/sp/analyze", data={"csrf_token": t}, follow_redirects=True)
        check("Analyze again: nothing sent to the AI", "nothing sent to the AI" in text(r) and calls["sp"] == 21, calls)
        with selection_app.SessionFactory() as db:
            props = db.scalar(select(func.count()).select_from(ws.Proposal).where(ws.Proposal.source == "SP"))
        check("storage: one SP proposal per candidate in Selection's table (no second archive)", props == 21, props)

        # Manual order kept
        first_id = re.findall(r'name="cid" value="(\d+)"', all_page)[1]
        owner.post(f"/selection/posizioni/{pid}/sp/move", data={"csrf_token": t, "cid": first_id, "dir": "up"})
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        check("manual order: moving a candidate up is kept and labelled", "Moved by the manager" in page)

        # 7-8. Application page / RMAED: analyzed only once completed, automatically
        with selection_app.SessionFactory() as db:
            account = ws.CandidateAccount(email="uma25@example.test", full_name="Uma Sample25", password_hash="x",
                                          status=ws.CANDIDATE_ACTIVE, email_verified_at=ws.utcnow())
            db.add(account)
            db.commit()
            account_id = account.id
            job_url = "/selection/jobs/" + db.get(ws.Position, pid).public_token
        cand = app.test_client()
        with cand.session_transaction() as sess:
            sess["selection_candidate_account_id"] = account_id
        page = text(cand.get(job_url))
        ct = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        sp_before = calls["sp"]
        cv_uma = ("Uma Sample25\numa25@example.test\n\nEXPERIENCE\n"
                  "Server, Trattoria Esempio 25, Mount Dora, FL | Jan 2022 - Present\n- Full table service for 35 covers\n")
        r = cand.post(job_url, data={"csrf_token": ct, "phone": "(407) 555-0125", "consent": "1",
                                     "cv": (BytesIO(cv_uma.encode()), "uma.txt")}, content_type="multipart/form-data")
        apply_url = r.headers.get("Location", "")
        sp_queue.kick(force=True)
        time.sleep(1.0)
        status = owner.get(f"/selection/posizioni/{pid}/sp/status").get_json()
        r = owner.post(f"/selection/posizioni/{pid}/sp/analyze", data={"csrf_token": t}, follow_redirects=True)
        time.sleep(0.5)
        check("in progress: the application page CV is not analyzed (status IN_PROGRESS, Analyze skips it)",
              "/selection/my-application/" in apply_url and status.get("IN_PROGRESS") == 1
              and calls["sp"] == sp_before and "nothing sent to the AI" in text(r), (apply_url, status, calls))
        page = text(cand.get(apply_url))
        cand.post(apply_url, data={"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', page).group(1),
                                   "action": "submit"})
        s = wait_analysis(owner, pid, 22)
        check("completed: the application enters CV Selection SP automatically, one reading, ranking updated",
              s.get("DONE") == 22 and calls["sp"] == sp_before + 1
              and "Uma Sample25" in text(owner.get(f"/selection/posizioni/{pid}/sp")), (s, calls))
        page = text(cand.get(apply_url))
        cand.post(apply_url, data={"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
                                   if re.search(r'name="csrf_token"', page) else "", "action": "submit"})
        time.sleep(0.5)
        check("completed again (repeated submit): no second analysis", calls["sp"] == sp_before + 1, calls)

        # Requirement change: earlier analyses marked for update, still in the ranking
        owner.post(f"/selection/posizioni/{pid}/sp/requirements", data={"csrf_token": t, "action": "edit"})
        owner.post(f"/selection/posizioni/{pid}/sp/requirements", data={
            "csrf_token": t, "action": "approve", "new_name": "Italian menu knowledge", "new_weight": "5"})
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        check("requirements v2: earlier analyses kept in the ranking and marked 'update recommended'",
              len(re.findall(r'<div class="rank">', page)) == 22 and "update recommended" in page
              and "22 analysis(es) used an earlier version" in page and calls["sp"] == 22, calls)

        # 9. Interrupted analysis resumes; 10. no duplicate AI call (retry, restart, simultaneous requests)
        with selection_app.SessionFactory() as db:
            version = 2
            pcs = [pc.id for pc in db.scalars(select(ws.PositionCandidate).where(
                ws.PositionCandidate.position_id == pid).order_by(ws.PositionCandidate.id)).all()]
            db.add(ws.Proposal(position_candidate_id=pcs[0], snapshot_id=version, source="SP_JOB", group_code="RUNNING",
                               payload_json='{"attempts": 1}', is_current=True,
                               created_at=ws.utcnow() - sp_queue.LEASE - timedelta(minutes=1)))   # worker died
            for _ in range(2):   # the same candidate queued twice by two simultaneous requests
                db.add(ws.Proposal(position_candidate_id=pcs[1], snapshot_id=version, source="SP_JOB",
                                   group_code="QUEUED", payload_json='{"attempts": 0}', is_current=True))
            db.commit()
            again = sp_queue.enqueue(db, [pcs[0], pcs[1]], version)
        before = calls["sp"]
        sp_queue.kick(force=True)
        for _ in range(100):
            with selection_app.SessionFactory() as db:
                left = db.scalar(select(func.count()).select_from(ws.Proposal).where(
                    ws.Proposal.source == "SP_JOB", ws.Proposal.is_current.is_(True)))
            if not left:
                break
            time.sleep(0.1)
        with selection_app.SessionFactory() as db:
            states = dict(db.execute(select(ws.Proposal.group_code, func.count()).where(
                ws.Proposal.source == "SP_JOB", ws.Proposal.position_candidate_id.in_(pcs[:2]),
                ws.Proposal.snapshot_id == 2).group_by(ws.Proposal.group_code)).all())
            v2 = [json.loads(p.payload_json).get("version") for p in db.scalars(select(ws.Proposal).where(
                ws.Proposal.source == "SP", ws.Proposal.is_current.is_(True),
                ws.Proposal.position_candidate_id.in_(pcs[:2]))).all()]
        check("resume: a job interrupted mid-way (lease expired) is analyzed again and completed",
              v2 == [2, 2] and not left and states.get("DONE", 0) >= 2, (v2, states))
        check("no duplicates: already-queued candidates are not queued again; the same candidate queued twice "
              "costs one AI call", again == 0 and calls["sp"] == before + 2 and sum(states.values()) == 3,
              (again, calls["sp"] - before, states))
        r = owner.post(f"/selection/posizioni/{pid}/sp/analyze", data={"csrf_token": t}, follow_redirects=True)
        s = wait_analysis(owner, pid, 22)
        page = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        check("Analyze after the change: only the 20 still outdated, each once; no 'update recommended' left",
              calls["sp"] == before + 22 and s.get("DONE") == 22 and "update recommended" not in page, (calls, s))
        old_detail = owner.get(f"/selection/posizioni/{pid}/sp/c/{first_id}")
        detail = text(owner.get(f"/selection/posizioni/{pid}/candidati/{first_id}"))
        check("detail: the former SP detail opens the Evaluation dossier, with the analysis and Selection's CV link",
              old_detail.status_code == 302 and f"/candidati/{first_id}#sp" in old_detail.headers["Location"]
              and 'href="/selection/">Selection</a>' in detail and "CV Selection SP analysis" in detail
              and f"/selection/posizioni/{pid}/candidati/{first_id}/cv-originale" in detail)
        check("original CV opens through Selection",
              owner.get(f"/selection/posizioni/{pid}/candidati/{first_id}/cv-originale").status_code == 200)
        other = app.test_client()
        check("access: not signed in → no SP page", other.get(f"/selection/posizioni/{pid}/sp").status_code in (302, 401, 403))
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
